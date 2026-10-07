'use strict';
// Drafts stay in memory. Tokens, paths and credentials never enter this state.
let builderState = {step:0,source:null,config:null,assumed:12,cap:null,datasets:[],drySignature:null,preflightSignature:null,busy:false};
let builderCheckVersion=0;
const builderSteps=['Dataset','Base model','Method','Hyperparameters','Review','Launch'];
function renderExperimentBuilder(data){
  const presets=Array.isArray(data)?data:data.presets||[];
  const draft=recipeDraft||builderState.config;
  recipeDraft=null;
  recipeConfig={...defaultRecipe(),...(draft||presets[0]?.config)};
  builderState.config=recipeConfig;builderState.pendingInitial=!draft;
  builderState.source=builderState.source|| (snapshot?.training?.available?'real':'demo');
  $('#workspace-view').innerHTML=featureHeading('recipes',t('Dataset → Model → Method → Hyperparameters → Review → Launch'))+`
    <ol class="builder-steps" aria-label="${t('Experiment builder steps')}">${builderSteps.map((step,index)=>`<li><button type="button" class="builder-step" data-builder-step="${index}"><span>${String(index+1).padStart(2,'0')}</span>${t(step)}</button></li>`).join('')}</ol>
    <div class="builder-layout"><div class="builder-panels"><form id="recipe-form">
      <fieldset class="builder-panel" data-builder-panel="0"><legend>${t('Choose the dataset')}</legend><p>${t('Real training uses a saved train/validation split. Demo data stays synthetic.')}</p>
        <label>${t('Experiment name')}<input name="name" maxlength="80" required></label>
        <div class="form-grid"><label>${t('Execution source')}<select id="builder-source"><option value="real">${t('Real GPU')}</option><option value="demo">${t('Demo · synthetic')}</option></select></label><label>${t('Model type')}<select name="kind"><option>LLM</option><option>VLM</option></select></label></div>
        <div id="builder-real-dataset"><label>${t('Prepared train/validation dataset')}<select id="training-dataset"><option value="">${t('Loading…')}</option></select></label><p class="builder-source-note" id="builder-dataset-note"></p><button type="button" class="button secondary" id="builder-prepare-data">${t('Open dataset preparation')}</button></div>
        <label id="builder-demo-dataset">${t('Dataset label')}<input name="dataset" maxlength="120" required><small>${t('Demo uses this label only. No dataset files are opened.')}</small></label>
      </fieldset>
      <fieldset class="builder-panel" data-builder-panel="1" hidden><legend>${t('Choose the base model')}</legend><p>${t('Search, installed files, runtime support and training readiness are separate checks.')}</p>
        <section id="real-training-panel"><div id="selected-model-info" class="model-selection"></div><label id="builder-installed-model">${t('Installed base model')}<select id="training-model"><option value="">${t('Loading…')}</option></select></label>
        <label>${t('Model label')}<input name="model" maxlength="200" required></label><button type="button" class="button secondary" id="browse-hf-models">${t('Browse Hugging Face models')}</button><p id="builder-model-note" class="field-note"></p></section>
      </fieldset>
      <fieldset class="builder-panel" data-builder-panel="2" hidden><legend>${t('Choose the method')}</legend><p>${t('LoRA trains adapters. QLoRA uses a 4-bit NF4 base model; runtime support is required.')}</p>
        <label>${t('Method')}<select name="method"><option value="qlora">QLoRA</option><option value="lora">LoRA</option></select></label><label>${t('Preset')}<select id="recipe-preset"><option value="">${t('Keep current draft')}</option>${presets.map((preset,index)=>`<option value="${index}">${escapeHtml(t(preset.name||preset.label||preset.id))}</option>`).join('')}</select></label>
      </fieldset>
      <fieldset class="builder-panel" data-builder-panel="3" hidden><legend>${t('Set hyperparameters')}</legend><p>${t('Max steps caps optimizer updates. Epochs can finish earlier. The server validates the final configuration.')}</p>
        <div class="form-grid three">${[['Learning rate','learning_rate','0.0000001','0.1','any'],['Batch size','batch_size',1,4,1],['Grad. accumulation','gradient_accumulation',1,32,1],['LoRA rank','lora_rank',1,32,1],['Context length','sequence_length',64,2048,1],['Epochs','epochs',1,20,1],['Steps · maximum updates','max_steps',10,2000,1]].map(([label,name,min,max,step])=>`<label>${t(label)}<input name="${name}" type="number" min="${min}" max="${max}" step="${step}" required></label>`).join('')}
        <label>${t('Assumed VRAM · GB')}<input id="assumed-vram" type="number" min="2" max="192" value="${builderState.assumed}" required><small>${t('Planning assumption · heuristic estimate, not a GPU measurement.')}</small></label></div>
        <details class="parameter-guide"><summary>${t('Batch size, learning rate and LoRA')}</summary><p>${t('Effective batch size = batch size × gradient accumulation. Actual context and VRAM are checked by the worker.')}</p></details>
      </fieldset>
      <fieldset class="builder-panel" data-builder-panel="4" hidden><legend>${t('Review the experiment')}</legend><p>${t('Review the exact recipe sent to the server. Data/config dry-run and real GPU preflight are separate.')}</p>
        <dl id="builder-review" class="builder-review"></dl><div class="feature-actions"><button type="submit" class="button primary" id="builder-dry-run">${t('Dry-run checks')}</button><button type="button" class="button secondary" id="training-preflight">${t('Check real training')}</button><button type="button" class="button secondary" id="recipe-export">${t('Export config')}</button></div>
      </fieldset>
      <fieldset class="builder-panel" data-builder-panel="5" hidden><legend>${t('Launch')}</legend><p>${t('Launching creates a queued run. A single GPU executes real jobs in FIFO order.')}</p>
        <div class="launch-choice" id="builder-real-launch"><h3>${t('Real GPU training')}</h3><p>${t('Uses the reviewed dataset snapshot and model revision. Pause saves a checkpoint before the server confirms paused.')}</p><button type="button" class="button primary" id="training-start" disabled>${t('Start real GPU training')}</button></div>
        <div class="launch-choice" id="builder-demo-launch"><h3>${t('Demo · synthetic')}</h3><p>${t('No model download or GPU allocation. Loss, progress and checkpoints are synthetic.')}</p><label>${t('Demo scenario')}<select name="failure_mode"><option value="none">${t('Normal completion')}</option><option value="oom">${t('Simulated out-of-memory failure')}</option></select></label><button type="button" class="button primary" id="recipe-demo" disabled>${t('Queue demo only')}</button></div>
      </fieldset>
      <div id="builder-check-status" class="builder-check-status" role="status"></div><div id="builder-error" class="feature-result error" role="alert" hidden></div><div id="recipe-result" hidden></div><div id="training-result" hidden></div>
      <div class="builder-actions"><button type="button" class="button secondary" id="builder-back">${t('Back')}</button><div><button type="button" class="button secondary" id="builder-reset">${t('Reset draft')}</button><button type="button" class="button primary" id="builder-next">${t('Next')}</button></div></div>
    </form></div><aside class="builder-reference"><h3>${t('GPU training controls')}</h3><p>${t('Dry-run checks validate data/configuration. Real GPU preflight checks installed models and snapshots; it does not launch optimization.')}</p><p>${t('Single GPU · FIFO')}</p><p>${t('VRAM estimates are planning assumptions. Missing measurements remain unavailable.')}</p><h3>${t('Parameter reference')}</h3><p>${t('A loss decrease on a small synthetic dataset does not establish model quality.')}</p><div id="builder-mini-config"></div></aside></div>`;
  populateRecipe(recipeConfig);
  $('#builder-source').value=builderState.source;
  $('#recipe-form').onsubmit=event=>{event.preventDefault();runBuilderCheck('dry');};
  $('#recipe-form').oninput=event=>{if(event.target.id==='recipe-preset')return;invalidateBuilderChecks();};
  $('#recipe-form').onchange=event=>{if(event.target.id==='builder-source'){builderState.source=event.target.value;$('#recipe-form [name=failure_mode]').value='none';refreshBuilderChoices();}if(event.target.name==='kind')refreshBuilderChoices();invalidateBuilderChecks();};
  $('#recipe-preset').onchange=event=>{if(event.target.value==='')return;const preset=presets[Number(event.target.value)]?.config;if(preset){populateRecipe({...readRecipe(),...preset});refreshBuilderChoices();invalidateBuilderChecks();}};
  $('#browse-hf-models').onclick=openModelCatalog;
  $('#builder-prepare-data').onclick=()=>setNav('datasets');
  $('#builder-back').onclick=()=>showBuilderStep(builderState.step-1);
  $('#builder-next').onclick=()=>{if(validateBuilderStep(builderState.step))showBuilderStep(builderState.step+1);};
  $$('.builder-step').forEach(button=>button.onclick=()=>{const step=Number(button.dataset.builderStep);if(step<=builderState.step || validateBuilderRange(step))showBuilderStep(step);});
  $('#builder-reset').onclick=()=>{builderState.config=null;recipeDraft=null;builderState.step=0;builderState.drySignature=null;builderState.preflightSignature=null;renderExperimentBuilder(data);};
  $('#training-preflight').onclick=()=>runBuilderCheck('preflight');
  $('#recipe-export').onclick=()=>runBuilderCheck('export');
  $('#recipe-demo').onclick=()=>launchBuilder('demo');
  $('#training-start').onclick=()=>launchBuilder('real');
  showBuilderStep(builderState.step);
  if(typeof loadTrainingPanel==='function')return loadTrainingPanel();
}
function builderSignature(config=readRecipe()){return JSON.stringify(config);}
function invalidateBuilderChecks(){
  builderCheckVersion++;
  builderState.config=readRecipe();builderState.assumed=Number($('#assumed-vram').value);
  builderState.drySignature=null;builderState.preflightSignature=null;
  $('#recipe-result').hidden=true;$('#training-result').hidden=true;
  updateBuilderReview();updateBuilderReadiness();
}
function showBuilderStep(step){
  builderState.step=Math.max(0,Math.min(5,step));
  $$('[data-builder-panel]').forEach(panel=>panel.hidden=Number(panel.dataset.builderPanel)!==builderState.step);
  $$('.builder-step').forEach(button=>button.setAttribute('aria-current',Number(button.dataset.builderStep)===builderState.step?'step':'false'));
  $('#builder-back').disabled=builderState.step===0;
  $('#builder-next').hidden=builderState.step===5;
  $('#builder-error').hidden=true;
  updateBuilderReview();updateBuilderReadiness();
}
function updateBuilderReview(){
  const config=readRecipe();
  $('#builder-review').innerHTML=Object.entries(config).map(([key,value])=>`<dt>${escapeHtml(t(key.replaceAll('_',' ')))}</dt><dd>${escapeHtml(value)}</dd>`).join('');
  $('#builder-mini-config').innerHTML=jsonPreview({source:builderState.source,method:config.method,model:config.model,dataset:config.dataset});
}
function builderProblem(message,step){if(step!==undefined)showBuilderStep(step);$('#builder-error').hidden=false;$('#builder-error').textContent=t(message);return false;}
function validateBuilderStep(step){
  const config=readRecipe(), fields=[['name','kind','dataset'],['model'],['method'],['learning_rate','batch_size','gradient_accumulation','lora_rank','sequence_length','epochs','max_steps'],[],[]][step];
  for(const name of fields){const input=$(`#recipe-form [name="${name}"]`);if(input?.checkValidity && !input.checkValidity()){showBuilderStep(step);input.reportValidity();return false;}}
  if(builderState.source==='real' && step===0 && !builderDatasetReady(config))return builderProblem('Save and split a matching dataset before continuing.',0);
  if(builderState.source==='real' && step===1 && !builderModelReady(config))return builderProblem('Choose an installed, compatible model matching the dataset kind.',1);
  return true;
}
function validateBuilderRange(step){for(let index=0;index<step;index++)if(!validateBuilderStep(index))return false;return true;}
function builderDatasetReady(config){const ds=builderState.datasets.find(ds=>ds.id===config.dataset);return Boolean(ds?.split && ds.kind===config.kind && !ds.split.warnings?.some(w=>w.code==='duplicate_leakage_risk'));}
function builderModelReady(config){const model=typeof selectedHubModel!=='undefined' && selectedHubModel?.id===config.model ? selectedHubModel : installedTrainingModels.find(m=>m.id===config.model);return Boolean(model?.installed && model.training_candidate!==false && model.kind===config.kind && ['LLM','VLM'].includes(model.kind));}
function builderLaunchReady(source,config=readRecipe()){
  const checked=builderState.drySignature===builderSignature(config);
  return !builderState.busy && remoteControlsAllowed && source===builderState.source && checked && (source==='demo' || (builderState.cap?.available && builderDatasetReady(config) && builderModelReady(config) && builderState.preflightSignature===builderSignature(config)));
}
function updateBuilderReadiness(){
  const config=readRecipe(), real=builderState.source==='real';
  $('#builder-real-launch').hidden=!real;$('#builder-demo-launch').hidden=real;
  $('#training-start').disabled=!builderLaunchReady('real',config);
  $('#recipe-demo').disabled=!builderLaunchReady('demo',config);
  $('#training-preflight').disabled=builderState.busy || !real || !builderState.cap?.available || !builderDatasetReady(config) || !builderModelReady(config);
  for(const id of ['#builder-dry-run','#recipe-export'])$(id).disabled=builderState.busy;
  $('#builder-check-status').textContent=t(builderState.busy?'Checking…':!remoteControlsAllowed?'Read-only access · launch disabled':builderState.drySignature!==builderSignature(config)?'Configuration changed · run dry-run checks before launch':real && builderState.preflightSignature!==builderSignature(config)?'Dry-run complete · real GPU preflight still required':'Reviewed configuration · ready to queue');
}
async function runBuilderCheck(kind){
  if(builderState.busy || !validateBuilderRange(4))return;
  const config=readRecipe(), signature=builderSignature(config), version=++builderCheckVersion;
  builderState.busy=true;updateBuilderReadiness();
  try{
    if(kind==='preflight'){
      const result=await api('/api/training/preflight',config);
      if(version!==builderCheckVersion || nav!=='recipes')return;
      builderState.preflightSignature=result.valid===true && result.can_train===true?signature:null;
      $('#training-result').hidden=false;$('#training-result').className='feature-result';
      $('#training-result').innerHTML=`<h4>${t('Real training checks passed')}</h4><p>${t('Preflight only · no optimizer process launched.')}</p>${jsonPreview(result)}`;
    }else{
      const result=await api('/api/config/dry-run',{config,assumed_vram_gb:Number($('#assumed-vram').value)});
      if(version!==builderCheckVersion || nav!=='recipes')return;
      if(result.valid===true && result.config)populateRecipe(result.config);
      builderState.config=readRecipe();builderState.drySignature=result.valid===true?builderSignature():null;updateBuilderReview();
      renderDryRun(result);
      if(kind==='export' && result.valid===true)downloadJson('forge-training-recipe.json',{mode:'preparation_only',real_training:false,assumed_vram_gb:Number($('#assumed-vram').value),config:result.config||config,warnings:result.warnings||[]});
    }
  }catch(error){if(version===builderCheckVersion && nav==='recipes')renderFeatureError(kind==='preflight'?'#training-result':'#recipe-result',error);}
  finally{builderState.busy=false;if(nav==='recipes' && $('#recipe-form'))updateBuilderReadiness();}
}
async function launchBuilder(source){
  if(!builderLaunchReady(source))return;
  const config=readRecipe(), version=builderCheckVersion;
  builderState.busy=true;updateBuilderReadiness();
  try{
    const result=await api(source==='real'?'/api/training/runs':'/api/runs',config);
    // The server alone owns the run lifecycle; keep its queued/pausing/canceling state.
    if(nav!=='recipes' || version!==builderCheckVersion)return;
    snapshot=result.snapshot||snapshot;selectedId=result.run.id;
    toast(t(source==='real'?'Real training queued':'Recipe queued in the synthetic demo engine'));
    setNav('runs');await refresh();
  }catch(error){if(nav==='recipes')renderFeatureError(source==='real'?'#training-result':'#recipe-result',error);}
  finally{builderState.busy=false;if(nav==='recipes')updateBuilderReadiness();}
}
