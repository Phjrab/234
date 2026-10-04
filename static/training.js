'use strict';
let trainingPanelVersion = 0;
async function loadTrainingPanel() {
  const host = $('#real-training-panel');
  if (!host) return;
  const version = ++trainingPanelVersion;
  try {
    const [cap, workspace] = await Promise.all([api('/api/training'), api('/api/workspace')]);
    if (version !== trainingPanelVersion || nav !== 'recipes') return;
    const datasets = (workspace.datasets || []).filter(ds => ds.split);
    host.innerHTML = `<h3>${t('Real GPU training')}</h3><p>${escapeHtml(t(cap.message))}</p><label>${t('Installed base model')}<select id="training-model">${cap.models.filter(m=>m.installed).map(m=>`<option value="${escapeHtml(m.id)}">${escapeHtml(m.id)} · ${m.kind}</option>`).join('')}</select></label><label>${t('Prepared train/validation dataset')}<select id="training-dataset">${datasets.map(ds=>`<option value="${escapeHtml(ds.id)}" data-kind="${ds.kind}">${escapeHtml(ds.name)} · ${ds.kind}</option>`).join('') || `<option value="">${t('Save and split a dataset first')}</option>`}</select></label><p class="field-note">${t('Uses the recipe above. Real jobs allocate the GPU and save adapter weights. Max steps caps optimizer updates; epochs may finish earlier.')}</p><div class="feature-actions"><button type="button" class="button secondary" id="training-preflight">${t('Check real training')}</button><button type="button" class="button primary" id="training-start" ${!cap.available || !remoteControlsAllowed ? 'disabled' : ''}>${t('Start real GPU training')}</button></div><div id="training-result" hidden></div>`;
    function syncModel() {
      const model = cap.models.find(m=>m.id===$('#training-model').value);
      if (!model) return;
      $('#recipe-form [name=model]').value=model.id;
      $('#recipe-form [name=kind]').value=model.kind;
      $('#recipe-form [name=sequence_length]').value=model.kind==='VLM'?1536:512;
      if (!datasets.some(ds=>ds.id===$('#training-dataset').value && ds.kind===model.kind)) $('#training-dataset').value=datasets.find(ds=>ds.kind===model.kind)?.id||'';
      syncDataset();
    }
    function syncDataset(){ $('#recipe-form [name=dataset]').value=$('#training-dataset').value; }
    $('#training-model').onchange=syncModel;
    $('#training-dataset').onchange=syncDataset;
    if (cap.models.some(m=>m.id===$('#recipe-form [name=model]').value && m.installed)) $('#training-model').value=$('#recipe-form [name=model]').value;
    if(datasets.some(ds=>ds.id===$('#recipe-form [name=dataset]').value))$('#training-dataset').value=$('#recipe-form [name=dataset]').value;
    if(cap.models.some(m=>m.id===$('#recipe-form [name=model]').value && m.installed))syncDataset();else syncModel();
    $('#training-preflight').onclick=async()=>{try{syncDataset();const result=await api('/api/training/preflight',readRecipe());const output=$('#training-result');output.hidden=false;output.className='feature-result';output.innerHTML=`<h4>${t('Real training checks passed')}</h4>${jsonPreview(result)}`;}catch(error){renderFeatureError('#training-result',error);}};
    $('#training-start').onclick=async()=>{const button=$('#training-start');button.disabled=true;try{syncDataset();const result=await api('/api/training/runs',readRecipe());snapshot=result.snapshot||snapshot;selectedId=result.run.id;toast(t('Real training queued'));setNav('runs');await refresh();}catch(error){renderFeatureError('#training-result',error);}finally{button.disabled=!remoteControlsAllowed;}};
  } catch(error) {
    if(version!==trainingPanelVersion || nav!=='recipes')return;
    host.innerHTML=`<h3>${t('Real GPU training')}</h3><p>${escapeHtml(error.message)}</p><p>${t('The operator must enable the installed training environment.')}</p>`;
  }
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
  const enabled=Boolean(snapshot?.training?.available);
  const notice=$('.demo-notice');
  if(notice && enabled) notice.innerHTML=`<span class="notice-icon">◉</span><div><strong>${t('GPU training enabled')}</strong><span>${t('Real jobs use uploaded datasets and save adapter weights. Demo jobs are labeled separately and remain synthetic.')}</span></div><span class="pill">CUDA</span>`;
  if(enabled && connectionLabel==='Demo API online'){connectionLabel='Dashboard API online';$('#connection').innerHTML=`<i></i> ${t('Dashboard API online')}`;}
  const measured=snapshot?.gpu?.simulated===false;
  const set=(selector,value)=>{const node=$(selector);if(node)node.textContent=value;};
  set('#gpu-telemetry-label',t(measured?'Measured telemetry':'Simulated telemetry'));
  set('#gpu-mode',measured?'CUDA':t('DEMO'));
  set('#gpu-chip-mode',measured?'CUDA':'SIM');
  set('#gpu-model-label',measured?snapshot.gpu.name:t('RTX 3060 profile'));
  set('#gpu-memory-note',t(measured?'Measured on this server':'12 GB assumed for this demo'));
  set('#gpu-linked',t(measured?'Yes':'No'));
  set('#gpu-disclaimer',t(measured?'GPU readings come from nvidia-smi on this server.':'Readings are generated by the demo engine, never read from your computer.'));
  set('#worker-caption',t(enabled?'Local LoRA/QLoRA worker ready.':'Deterministic simulation · local API'));
  set('.demo-tag',t(enabled?'LOCAL GPU WORKSPACE':'DEMO ENVIRONMENT'));
  const worker=$('.worker-value');if(worker && enabled)worker.textContent=t('CUDA worker');
  const label=$('#gpu-source-label');if(label)label.textContent=t(snapshot?.gpu?.simulated===false?'MEASURED VRAM':'SIMULATED VRAM');
  const caption=$('#gpu-source-caption');if(caption)caption.textContent=t(snapshot?.gpu?.simulated===false?'Measured on this server':'12 GB demo assumption · not measured');
}
