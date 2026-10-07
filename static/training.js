'use strict';
let trainingPanelVersion = 0, installedTrainingModels = [];
async function loadTrainingPanel() {
  const host=$('#real-training-panel');if(!host)return;
  const version=++trainingPanelVersion;
  try{
    const [cap,workspace]=await Promise.all([api('/api/training').catch(error=>({available:false,models:[],message:error.message})),api('/api/workspace')]);
    if(version!==trainingPanelVersion || nav!=='recipes' || !host.isConnected)return;
    builderState.cap=cap;installedTrainingModels=cap.models||[];builderState.datasets=workspace.datasets||[];
    refreshBuilderChoices();updateBuilderReview();updateBuilderReadiness();
  }catch(error){if(version===trainingPanelVersion && nav==='recipes')builderProblem(error.message);}
}
function refreshBuilderChoices(){
  if(!$('#recipe-form'))return;
  const real=builderState.source==='real',kind=$('#recipe-form [name=kind]').value;
  const datasets=builderState.datasets.filter(ds=>ds.split && ds.kind===kind), models=installedTrainingModels.filter(model=>model.installed && model.kind===kind);
  const oldDataset=$('#recipe-form [name=dataset]').value, oldModel=$('#recipe-form [name=model]').value;
  $('#builder-real-dataset').hidden=!real;$('#builder-demo-dataset').hidden=real;
  $('#builder-installed-model').hidden=!real;$('#browse-hf-models').hidden=!real;
  $('#recipe-form [name=dataset]').readOnly=real;
  $('#training-dataset').innerHTML=datasets.map(ds=>`<option value="${escapeHtml(ds.id)}" data-kind="${ds.kind}">${escapeHtml(ds.name)} · ${ds.kind}</option>`).join('')||`<option value="">${t('Save and split a dataset first')}</option>`;
  $('#training-dataset').value=datasets.some(ds=>ds.id===oldDataset)?oldDataset:datasets[0]?.id||'';
  $('#training-model').innerHTML=models.map(model=>`<option value="${escapeHtml(model.id)}">${escapeHtml(model.id)}</option>`).join('')||`<option value="">${t('No installed model')}</option>`;
  $('#training-model').value=models.some(model=>model.id===oldModel)?oldModel:models[0]?.id||'';
  const syncDataset=()=>{if(real)$('#recipe-form [name=dataset]').value=$('#training-dataset').value;const ds=datasets.find(ds=>ds.id===$('#training-dataset').value);$('#builder-dataset-note').textContent=ds ? `${ds.count} ${t('examples · saved split')} · ${t(ds.synthetic?'Synthetic dataset':'Uploaded dataset')}`:t('Save and split a dataset first');};
  const syncModel=()=>{const model=models.find(model=>model.id===$('#training-model').value);if(model){selectedHubModel=model;$('#recipe-form [name=model]').value=model.id;renderSelectedModel();}updateBuilderReview();updateBuilderReadiness();};
  $('#training-dataset').onchange=()=>{syncDataset();invalidateBuilderChecks();};
  $('#training-model').onchange=()=>{syncModel();invalidateBuilderChecks();};
  if(real){syncDataset();if(builderState.pendingInitial || !oldModel || oldModel.startsWith('demo/'))syncModel();else {selectedHubModel=installedTrainingModels.find(model=>model.id===oldModel)|| (selectedHubModel?.id===oldModel?selectedHubModel:null);renderSelectedModel();}}
  else {if(!oldDataset || oldDataset.startsWith('dataset-'))$('#recipe-form [name=dataset]').value=kind==='VLM'?'synthetic-image-captions':'synthetic-instructions';if(!oldModel || oldModel===selectedHubModel?.id)$('#recipe-form [name=model]').value=kind==='VLM'?'demo/vlm-3b':'demo/llm-3b';$('#selected-model-info').hidden=true;}
  builderState.pendingInitial=false;
  for(const [name,max]of Object.entries(real?{batch_size:4,gradient_accumulation:32,lora_rank:32,sequence_length:2048}:{batch_size:32,gradient_accumulation:128,lora_rank:128,sequence_length:8192}))$('#recipe-form [name="'+name+'"]').max=max;
  $('#builder-model-note').textContent=t(real?'An installed model is required. Catalog selection alone does not establish training readiness.':'Demo model label · no weights are opened.');
  updateBuilderReview();updateBuilderReadiness();
}
async function uploadDatasetImages(datasetId, files) {
  for (const file of files) {
    if (file.size>2097152 || !/\.(png|jpe?g)$/i.test(file.name))throw new Error(t('Upload PNG/JPEG images up to 2 MB each.'));
    const bytes=new Uint8Array(await file.arrayBuffer());
    let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
    await api(`/api/datasets/${encodeURIComponent(datasetId)}/images`,{label:`images/${file.name}`,content_base64:btoa(binary)});
  }
  toast(t('Dataset images uploaded'));
}
function renderTrainingSource() {
  const enabled=Boolean(snapshot?.training?.available), gpu=snapshot?.gpu||{};
  const measuredSource=gpu.simulated===false;
  const measured=measuredSource && gpu.source!=='measurement_unavailable' && [gpu.used_gb,gpu.total_gb,gpu.utilization,gpu.temp_c].some(Number.isFinite), synthetic=gpu.simulated===true, fixture=Boolean(snapshot?.ui_fixture);
  const notice=$('.demo-notice');
  if(notice)notice.innerHTML=`<div><strong>${t(enabled?'GPU training enabled':'Local GPU training and labeled demos')}</strong><span>${t('Real jobs use uploaded datasets and save adapter weights. Demo jobs are labeled separately and remain synthetic.')}</span></div>`;
  const set=(selector,value)=>{const node=$(selector);if(node)node.textContent=value;};
  set('#gpu-telemetry-label',t(fixture?'UI fixture telemetry':measured?'Measured telemetry':synthetic?'Simulated telemetry':'Telemetry unavailable'));
  set('#gpu-mode',t(fixture?'UI fixture':measured?'Measured':synthetic?'DEMO':'Unavailable'));
  set('#gpu-model-label',gpu.name||t('Telemetry unavailable'));
  set('#gpu-memory-note',t(fixture?'Synthetic values · measured-source shape':measured?'Measured on this server':synthetic?'Demo assumption · not measured':'No GPU observation available'));
  set('#gpu-linked',t(fixture?'UI fixture':measured?'Yes':synthetic?'No':'Unavailable'));
  set('#gpu-disclaimer',t(fixture?'Synthetic UI fixture. No GPU probe or worker is connected.':measured?'GPU readings come from nvidia-smi on this server.':synthetic?'Readings are generated by the demo engine, never read from your computer.':'GPU readings unavailable · no values substituted'));
  set('#worker-caption',t(enabled?'Local LoRA/QLoRA worker ready.':'Deterministic simulation · local API'));
  set('.demo-tag',t(enabled?'LOCAL GPU WORKSPACE':'DEMO ENVIRONMENT'));
  set('.worker-value',t(enabled?'CUDA worker':'Demo engine'));
  set('#gpu-source-label',t(measured?'MEASURED VRAM':'SIMULATED VRAM'));
  set('#gpu-source-caption',t(measured?'Measured on this server':'Demo assumption · not measured'));
}
