'use strict';
let selectedHubModel=null, hfCatalogVersion=0, hfCatalogModels=[], hfNextCursor=null, hfDownloadTimer=null;
function hfSettingsCard(){return `<section class="feature-box hf-settings"><h3>Hugging Face</h3><p>${t('Personal access token connection · not OAuth')}</p><div id="hf-account-status" role="status">${t('Loading…')}</div><p>${t('Connect with a Hugging Face read token to download private or gated models. Public models do not require sign-in.')}</p><form id="hf-connect-form"><label for="hf-token">${t('Hugging Face access token')}<input id="hf-token" name="token" type="password" autocomplete="off" spellcheck="false" maxlength="259" placeholder="hf_…" required></label><div class="feature-actions"><button class="button primary" type="submit">${t('Connect account')}</button><button class="button secondary" type="button" id="hf-disconnect">${t('Disconnect account')}</button><a class="button secondary" href="https://huggingface.co/login?next=%2Fsettings%2Ftokens" target="_blank" rel="noopener noreferrer">${t('Hugging Face sign-in ↗')}</a><a class="button secondary" href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener noreferrer">${t('Create read token ↗')}</a></div></form><p class="field-note">${t('The token is stored on this server with owner-only file permissions. It is never returned to the browser or included in experiments.')}</p><div id="hf-account-error" hidden></div></section>`;}
async function loadHFSettings(){
 const host=$('#hf-account-status');if(!host)return;
 function status(account){if(!host.isConnected)return;host.textContent=account.connected?t('Connected as {username}',{username:account.username}):t('Not connected');$('#hf-disconnect').disabled=!account.connected||!remoteControlsAllowed;$('#hf-connect-form button[type=submit]').disabled=!remoteControlsAllowed;}
 $('#hf-connect-form').onsubmit=async event=>{event.preventDefault();const button=event.target.querySelector('button[type=submit]');button.disabled=true;try{const result=await api('/api/huggingface/connect',{token:$('#hf-token').value.trim()});$('#hf-token').value='';$('#hf-account-error').hidden=true;status(result);toast(t('Hugging Face account connected'));}catch(error){renderFeatureError('#hf-account-error',error);}finally{button.disabled=!remoteControlsAllowed;}};
 $('#hf-disconnect').onclick=async()=>{try{status(await api('/api/huggingface/disconnect',{}));$('#hf-token').value='';toast(t('Hugging Face account disconnected'));}catch(error){renderFeatureError('#hf-account-error',error);}};
 try{status(await api('/api/huggingface/account'));}catch(error){if(host.isConnected)host.textContent=error.message;}
}
function modelIcon(model){const author=model.publisher||model.id.split('/')[0];return `<span class="publisher-icon"><span aria-hidden="true">${escapeHtml(author.slice(0,2).toUpperCase())}</span><img src="/api/huggingface/avatar?author=${encodeURIComponent(author)}" alt="" loading="lazy"></span>`;}
function bindModelIcons(host){host.querySelectorAll('.publisher-icon img').forEach(img=>{img.onerror=()=>img.remove();});}
function modelKind(kind){return ['LLM','VLM'].includes(kind)?kind:t(kind==='OTHER'?'Other task':'Unclassified');}
function compactNumber(value){return Number.isFinite(value)?Intl.NumberFormat(I18n.language==='ko'?'ko-KR':'en-US',{notation:'compact',maximumFractionDigits:1}).format(value):'—';}
function formatModelBytes(value){return Number.isFinite(value)?(value>=1024**3?(value/1024**3).toFixed(2)+' GiB':(value/1024**2).toFixed(1)+' MiB'):'—';}
function modelSummary(model){return `${modelIcon(model)}<span class="model-name"><strong>${escapeHtml(model.name||model.id.split('/').at(-1))}</strong><small>${escapeHtml(model.publisher||model.id.split('/')[0])} · ${escapeHtml(model.family||t('Unknown family'))}</small></span><span class="model-type ${model.kind==='VLM'?'vlm':''}">${escapeHtml(modelKind(model.kind))}</span>`;}
function renderSelectedModel(){
 const host=$('#selected-model-info');if(!host)return;if(!selectedHubModel){host.hidden=true;return;}host.hidden=false;
 host.innerHTML=modelSummary(selectedHubModel);bindModelIcons(host);
 const ready=selectedHubModel.installed&&selectedHubModel.training_candidate!==false&&['LLM','VLM'].includes(selectedHubModel.kind);
 $('#training-start').disabled=!ready||!remoteControlsAllowed||!snapshot?.training?.available;
 $('#training-preflight').disabled=!ready;
 if(typeof updateBuilderReadiness==='function' && $('#recipe-form'))updateBuilderReadiness();
}
async function renderModels(){
 $('#workspace-view').innerHTML=featureHeading('models',t('Search, installed files, runtime support and training readiness are separate checks.'))+'<div id="model-catalog"></div>';
 return openModelCatalog(true);
}
async function openModelCatalog(embedded=false){
 embedded=embedded===true;
 const dialog=$('#model-dialog');
 const mount=embedded?$('#model-catalog'):$('#model-dialog-catalog');
 mount.innerHTML=`<form id="hf-search-form"><div class="hf-search-line"><label>${t('Model search or repository ID')}<input id="hf-search" type="search" maxlength="200" placeholder="Qwen, Llama, publisher/model"></label><button class="button primary" type="submit">${t('Search')}</button><button class="button secondary" type="button" id="hf-exact">${t('Open model ID')}</button></div><div class="hf-filters"><label>${t('Publisher')}<input id="hf-author" placeholder="Qwen, meta-llama…" maxlength="96"></label><label>${t('Model family')}<input id="hf-family" placeholder="qwen2, llama…" maxlength="80"></label><label>${t('Model type')}<select id="hf-kind"><option value="ALL">${t('All')}</option><option>LLM</option><option>VLM</option></select></label><label>${t('Language model format')}<select id="hf-text-task" disabled><option value="causal">${t('Decoder-only')}</option><option value="seq2seq">${t('Encoder-decoder')}</option></select></label><label>${t('Sort')}<select id="hf-sort"><option value="downloads">${t('Downloads')}</option><option value="trendingScore">${t('Trending')}</option><option value="lastModified">${t('Recently updated')}</option></select></label><label>${t('Group by')}<select id="hf-group"><option value="publisher">${t('Publisher')}</option><option value="family">${t('Model family')}</option></select></label></div></form><p class="field-note">${t('Types and families come from Hub task and architecture metadata. All model repositories can be selected; training requires a compatible LLM/VLM snapshot.')}</p><div class="hf-catalog-grid"><section aria-label="${t('Model results')}"><div id="hf-results" aria-live="polite"></div><button type="button" class="button secondary" id="hf-more" hidden>${t('Load more')}</button></section><section id="hf-detail" class="hf-detail" aria-live="polite"><div class="empty">${t('Select a model to view details')}</div></section></div><div id="hf-download-status" role="status"></div><div class="feature-actions"><button type="button" class="button secondary" id="hf-account-settings">${t('Hugging Face account settings')}</button></div>`;
 $('#close-model-dialog').onclick=()=>dialog.close();
 $('#hf-account-settings').onclick=()=>{dialog.close();setNav('settings');};
 $('#hf-search-form').onsubmit=event=>{event.preventDefault();searchHFModels(false);};
 $('#hf-more').onclick=()=>searchHFModels(true);
 $('#hf-group').onchange=renderHFResults;
 for(const id of ['#hf-kind','#hf-text-task','#hf-sort','#hf-author','#hf-family'])$(id).onchange=()=>{$('#hf-text-task').disabled=$('#hf-kind').value!=='LLM';searchHFModels(false);};
 $('#hf-exact').onclick=()=>showHFModel($('#hf-search').value.trim());
 if(!embedded && !dialog.open)dialog.showModal();
 await searchHFModels(false);pollHFDownload();
}
async function searchHFModels(append){
 const version=++hfCatalogVersion,host=$('#hf-results');
 if(!append){hfCatalogModels=[];host.innerHTML=`<div class="empty">${t('Loading…')}</div>`;}
 const params=new URLSearchParams({search:$('#hf-search').value.trim(),author:$('#hf-author').value.trim(),kind:$('#hf-kind').value,family:$('#hf-family').value.trim(),sort:$('#hf-sort').value,text_task:$('#hf-text-task').value});
 if(append&&hfNextCursor)params.set('cursor',hfNextCursor);
 $('#hf-more').disabled=true;
 try{const result=await api('/api/huggingface/models?'+params);if(version!==hfCatalogVersion||!host.isConnected)return;const unique=new Map((append?hfCatalogModels:[]).concat(result.models||[]).map(model=>[model.id,model]));hfCatalogModels=[...unique.values()];hfNextCursor=result.next_cursor;renderHFResults();$('#hf-more').hidden=!hfNextCursor;}catch(error){if(version===hfCatalogVersion)host.innerHTML=`<div class="feature-result error">${escapeHtml(error.message)}</div>`;}finally{if($('#hf-more'))$('#hf-more').disabled=false;}
}
function renderHFResults(){
 const host=$('#hf-results');if(!host)return;const group=$('#hf-group').value,groups=new Map();
 for(const model of hfCatalogModels){const key=model[group]||t('Unknown family');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(model);}
 host.innerHTML=hfCatalogModels.length?[...groups].map(([key,models])=>`<div class="hf-model-group"><h3>${escapeHtml(key)}</h3>${models.map(model=>`<button type="button" class="hf-model-card" data-hf-model="${escapeHtml(model.id)}">${modelSummary(model)}<span class="model-meta">${t('Parameters')}: ${compactNumber(model.parameters)} · ${t('Downloads')}: ${compactNumber(model.downloads)}${model.gated?' · '+t('Gated'):''}</span></button>`).join('')}</div>`).join(''):`<div class="empty">${t('No models found. Change the filters or open a repository ID.')}</div>`;
 host.querySelectorAll('[data-hf-model]').forEach(button=>{button.onclick=()=>showHFModel(button.dataset.hfModel);});bindModelIcons(host);
}
let hfDetailVersion=0, hfDetailModelId=null, hfCompletedRevision=null;
async function showHFModel(id){
 const version=++hfDetailVersion,host=$('#hf-detail');host.innerHTML=`<div class="empty">${t('Loading…')}</div>`;
 try{
  const model=await api('/api/huggingface/model?id='+encodeURIComponent(id));hfDetailModelId=model.id;if(version!==hfDetailVersion||!host.isConnected)return;
  host.innerHTML=`<div class="model-selection">${modelSummary(model)}</div><p class="hf-repo-id">${escapeHtml(model.id)}</p><dl class="hf-metadata"><dt>${t('Publisher')}</dt><dd>${escapeHtml(model.publisher_info?.name||model.publisher)}</dd><dt>${t('Model family')}</dt><dd>${escapeHtml(model.family||t('Unknown family'))}</dd><dt>${t('Task')}</dt><dd>${escapeHtml(model.task||'—')}</dd><dt>${t('Architecture')}</dt><dd>${escapeHtml(model.architectures.join(', ')||'—')}</dd><dt>${t('Training format')}</dt><dd>${escapeHtml(t(model.training_architecture==='seq2seq'?'Encoder-decoder':model.training_architecture==='causal'?'Decoder-only':model.training_architecture==='image_text_to_text'?'Image and text':'Not specified'))}</dd><dt>${t('Parameters')}</dt><dd>${compactNumber(model.parameters)}</dd><dt>${t('Download size')}</dt><dd>${formatModelBytes(model.download_bytes)}</dd><dt>${t('License')}</dt><dd>${escapeHtml(model.license||t('Not specified'))}</dd><dt>${t('Local status')}</dt><dd>${t(model.installed?'Installed':'Not installed')}</dd><dt>${t('Access')}</dt><dd>${t(model.private?'Private':model.gated?'Gated':'Public')}</dd></dl>${model.reasons.length?`<ul class="field-note">${model.reasons.map(reason=>`<li>${escapeHtml(t(reason))}</li>`).join('')}</ul>`:`<p class="field-note">${t('The worker checks tokenizer, image processing and VRAM before optimization. Catalog compatibility does not guarantee a successful training run.')}</p>`}<p class="field-note">${t('For gated models, accept the publisher terms on Hugging Face and connect an authorized read token in Settings.')}</p><div class="feature-actions"><button type="button" class="button primary" id="hf-select-model">${t('Select model')}</button><button type="button" class="button secondary" id="hf-download-model" ${model.installed||!model.training_candidate||!remoteControlsAllowed?'disabled':''}>${t(model.installed?'Installed':'Download model')}</button><a class="button secondary" href="${escapeHtml(model.url)}" target="_blank" rel="noopener noreferrer">${t('Model page ↗')}</a></div>`;
  bindModelIcons(host);
  if(matchMedia('(max-width:700px)').matches)host.scrollIntoView({block:'start'});
  $('#hf-select-model').onclick=()=>{
   selectedHubModel=model;
   if(!$('#recipe-form')){recipeDraft={...defaultRecipe(),model:model.id,kind:['LLM','VLM'].includes(model.kind)?model.kind:'LLM',dataset:''};builderState.source='real';builderState.step=1;builderState.drySignature=null;builderState.preflightSignature=null;$('#model-dialog').close();setNav('recipes');return;}
   $('#recipe-form [name=model]').value=model.id;
   if(['LLM','VLM'].includes(model.kind))$('#recipe-form [name=kind]').value=model.kind;
   if(model.installed)$('#training-model').value=model.id;
   renderSelectedModel();refreshBuilderChoices();invalidateBuilderChecks();$('#model-dialog').close();
  };
  $('#hf-download-model').onclick=async()=>{const button=$('#hf-download-model');button.disabled=true;try{await api('/api/huggingface/download',{model:model.id,revision:model.revision});pollHFDownload();}catch(error){toast(error.message,true);button.disabled=false;}};
 }catch(error){if(version===hfDetailVersion)host.innerHTML=`<div class="feature-result error">${escapeHtml(error.message)}</div>`;}
}
async function pollHFDownload(){
 clearTimeout(hfDownloadTimer);
 try{
  const state=await api('/api/huggingface/download');const host=$('#hf-download-status');
  if(host&&host.isConnected){host.innerHTML=state.status==='idle'?'':`<div class="feature-result"><b>${escapeHtml(state.model||'')}</b><p>${escapeHtml(t(state.message||''))} · ${formatModelBytes(state.downloaded_bytes||0)} / ${formatModelBytes(state.expected_bytes)}</p>${state.status==='downloading'?`<button type="button" class="button secondary" id="hf-cancel-download">${t('Cancel download')}</button>`:''}</div>`;if($('#hf-cancel-download'))$('#hf-cancel-download').onclick=async()=>{try{await api('/api/huggingface/download/cancel',{});pollHFDownload();}catch(error){toast(error.message,true);}};}
  if(state.status==='downloading'){hfDownloadTimer=setTimeout(pollHFDownload,2000);}
  if(state.status==='completed'&&nav==='recipes'){
   const key=state.model+'@'+state.revision;
   if(hfCompletedRevision!==key && $('#model-dialog').open && hfDetailModelId===state.model){hfCompletedRevision=key;await showHFModel(state.model);}
   const cap=await api('/api/training');installedTrainingModels=cap.models;builderState.cap=cap;
   const select=$('#training-model');if(select){const current=$('#recipe-form [name=model]').value;select.innerHTML=cap.models.filter(m=>m.installed).map(m=>`<option value="${escapeHtml(m.id)}">${escapeHtml(m.id)} · ${m.kind} · ${escapeHtml(m.family||'—')}</option>`).join('');select.value=current;const installed=cap.models.find(m=>m.id===current&&m.installed);if(installed){selectedHubModel={...selectedHubModel,...installed};renderSelectedModel();invalidateBuilderChecks();}}
  }
 }catch(error){const host=$('#hf-download-status');if(host&&host.isConnected)host.textContent=error.message;}
}
