'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value, digits = 3) => Number.isFinite(Number(value)) && value !== null && value !== undefined ? Number(value).toFixed(digits) : '—';
const pct = value => Math.max(0, Math.min(100, Number(value) || 0));
let authToken = null, remoteControlsAllowed = true, connectionLabel = 'Connecting';
let snapshot = null, selectedId = null, filter = 'all', currentTab = 'logs', requestBusy = false, refreshBusy = false, toastTimer, nav = 'overview';
try { selectedId = localStorage.getItem('forge.selectedRun'); } catch {}
function toast(message, error = false) { const el = $('#toast'); el.textContent = t(message); el.hidden = false; el.classList.toggle('error', error); clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4200); }
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), path.startsWith('/api/huggingface/') ? 45000 : 8000);
  try {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? {} : {'Content-Type': 'application/json',...(authToken ? {'X-CSRF-Token':authToken} : {})}, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store', signal:controller.signal});
    let payload; try { payload = await response.json(); } catch { throw new Error(t("The local API returned an unreadable response")); }
    if (!response.ok) { const error = new Error(t(payload.error?.message || payload.error || `${t("Request failed (")}${response.status})`)); error.status = response.status; error.code = payload.error?.code; error.details = payload.error?.details; if(response.status === 401 && !String(error.code).startsWith('hf_') && typeof showLogin === 'function') showLogin(); throw error; }
    return payload;
  } catch(error) {
    if(error.name === 'AbortError') throw new Error(t("The local API timed out. Check that the demo server is running."));
    throw error;
  } finally { clearTimeout(timeout); }
}
function setConnection(ok) { connectionLabel = ok ? 'Demo API online' : 'API offline · data stale'; const el = $('#connection'); el.className = 'connection ' + (ok ? 'ok' : 'error'); el.innerHTML = `<i></i> ${ok ? t("Demo API online") : t("API offline · data stale")}`; }
async function refresh() {
  if (refreshBusy) return; refreshBusy = true;
  try { snapshot = await api('/api/status'); setConnection(true); render(); }
  catch(error) { setConnection(false); if(error.status === 401) { snapshot=null; $('#run-detail').hidden=true; $('#tab-content').innerHTML=''; $('#loss-chart').innerHTML=''; } if(error.status === 401 || error.code === 'bootstrap_required' || error.code === 'password_change_required') { connectionLabel = 'Local sign-in required'; $('#connection').innerHTML=`<i></i> ${t("Local sign-in required")}`; if(typeof checkAccess === 'function') checkAccess(); } if (!snapshot) { $('#runs-body').innerHTML = `<tr><td colspan="6" class="empty">${t("Sign in locally to finish setup, or check that python server.py is running.")}</td></tr>`; $('#selected-title').textContent = t("Waiting for the local demo API"); } }
  finally { refreshBusy = false; }
}
function selectRun(id) { selectedId = id; try { localStorage.setItem('forge.selectedRun', id); } catch {} render(); }
function latest(run) { return run.latest_metrics || run.metrics?.at(-1) || {}; }
function render() {
  if (!snapshot) return;
  const focused = document.activeElement;
  const focusRun = focused?.dataset?.run;
  const focusAction = focused?.dataset?.action;
  const focusHref = focused?.closest?.('#tab-content') ? focused.getAttribute('href') : null;
  const focusId = focused?.id;
  const focusLog = focused?.matches?.('.technical-logs > summary');
  $$('.filter').forEach(btn => btn.setAttribute('aria-pressed', String(btn.dataset.filter === filter)));
  const runs = snapshot.runs || [], gpu = snapshot.gpu || {};
  if (!runs.some(run => run.id === selectedId)) selectedId = snapshot.active_run_id || runs[0]?.id;
  $('#summary-total').textContent = runs.length; $('#nav-count').textContent = runs.length; $('#experiment-count').textContent = runs.length;
  const completed = runs.filter(r => r.status === 'completed').length, queued = runs.filter(r => r.status === 'queued').length;
  $('#summary-caption').textContent = `${completed} ${t("completed ·")} ${queued} ${t("queued")}`;
  const failedRuns=runs.filter(run=>run.status==='failed'); const pausedRuns=runs.filter(run=>run.status==='paused');
  $('#workspace-alerts').hidden = nav!=='overview' || (!failedRuns.length && !pausedRuns.length);
  $('#workspace-alerts').innerHTML = `${failedRuns.length?`<span>◉ ${t(snapshot.training?.available ? "Experiment failures recorded. Review the worker error and configuration." : failedRuns.length === 1 ? "{count} demo failure recorded. Review the injected scenario and next steps." : "{count} demo failures recorded. Review the injected scenario and next steps.", {count: failedRuns.length})}</span><button id="inspect-latest-failure" class="button secondary">${t("Review failure")}</button>`:''}${pausedRuns.length?`<span>${t(snapshot.training?.available?"Paused jobs reserve their queue. Resume or cancel to continue.":"Ⅱ A paused demo job reserves the GPU slot. Resume or cancel it to release the queue.")}</span>`:''}`;
  if(failedRuns.length) $('#inspect-latest-failure').onclick=()=>{selectedId=failedRuns[0].id;setNav('runs');};
  $('#summary-active').innerHTML = `${runs.filter(r => r.status === 'running').length} <small>${t("running")}</small>`;
  $('#summary-vram').innerHTML = `${fmt(gpu.used_gb,1)} <small>/ ${fmt(gpu.total_gb,0)} GB</small>`;
  $('#vram-bar').style.width = `${pct(gpu.used_gb / gpu.total_gb * 100)}%`;
  $('#gpu-util').textContent = `${fmt(gpu.utilization,0)}%`; $('#gpu-util-bar').style.width = `${pct(gpu.utilization)}%`;
  $('#gpu-memory').textContent = `${fmt(gpu.used_gb,1)} / ${fmt(gpu.total_gb,0)} GB`; $('#gpu-memory-bar').style.width = `${pct(gpu.used_gb / gpu.total_gb * 100)}%`;
  $('#gpu-temp').textContent = `${fmt(gpu.temp_c,0)} °C`;
  const shown = runs.filter(run => (filter === 'all' || run.kind === filter) && (nav !== 'overview' || ['running','paused'].includes(run.status)));
  $('#no-runs').textContent = nav === 'overview' ? t("No active demo jobs. Open Experiments to start or inspect a queued run.") : t("No experiments in this view yet");
  if(nav === 'overview' && !runs.some(run => run.id === selectedId && ['running','paused'].includes(run.status))) selectedId = snapshot.active_run_id || runs.find(run => run.status === 'paused')?.id || null;
  if(['overview','runs'].includes(nav)) $('#run-detail').hidden = nav === 'overview' && !selectedId;
  $('.run-data').hidden = nav === 'overview';
  $('#no-runs').hidden = shown.length > 0;
  $('#runs-body').innerHTML = shown.map(run => {
    const progress = pct(run.progress ?? run.step / run.total_steps * 100), metric = latest(run);
    return `<tr tabindex="0" data-run="${escapeHtml(run.id)}" class="${run.id === selectedId ? 'selected' : ''}" aria-label="${t("Select")} ${escapeHtml(run.name)}"><td><div class="run-name"><span class="type-icon ${run.kind === 'VLM' ? 'vlm' : ''}">${run.kind === 'VLM' ? '▧' : '≋'}</span><div>${escapeHtml(run.name)}<div class="run-meta">${escapeHtml(run.kind)} · ${escapeHtml(t(run.simulated===false?"Real GPU":"Demo"))} · ${escapeHtml(run.config?.model || run.model_id || t("demo model"))}</div></div></div></td><td><span class="status ${escapeHtml(run.status)}">${escapeHtml(t(run.status))}</span></td><td><div class="progress-line"><div class="meter"><span style="width:${progress}%"></span></div><span>${Math.round(progress)}%</span></div></td><td>${fmt(metric.loss)}</td><td><span class="method-tag">${escapeHtml((run.method || run.config?.method || 'QLoRA').toUpperCase())} · r${escapeHtml(run.config?.lora_rank || 16)}</span></td><td class="row-arrow">↗</td></tr>`;
  }).join('');
  $$('#runs-body tr[data-run]').forEach(row => { row.onclick = () => selectRun(row.dataset.run); row.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectRun(row.dataset.run); } }; });
  const run = runs.find(r => r.id === selectedId); if (run) renderDetail(run);
  if(typeof renderTrainingSource==='function')renderTrainingSource();
  if(nav==='compare' && typeof updateComparison==='function' && $('#compare-output')) updateComparison();
  if (focused && !focused.isConnected) {
    const replacement = focusRun ? $$('#runs-body tr[data-run]').find(el => el.dataset.run === focusRun)
      : focusAction ? $$('#run-controls button').find(el => el.dataset.action === focusAction)
      : focusHref ? $$('#tab-content a').find(el => el.getAttribute('href') === focusHref)
      : focusLog ? $('.technical-logs > summary') : focusId ? document.getElementById?.(focusId) : null;
    if (replacement && !replacement.disabled) replacement.focus({preventScroll:true});
  }
}
function renderDetail(run) {
  const real=run.simulated===false;
  const metric = latest(run), step = run.step ?? run.current_step ?? 0;
  $('#selected-title').textContent = run.name; $('#selected-subtitle').textContent = `${run.kind} · ${(run.method || 'qlora').toUpperCase()} · ${step.toLocaleString()} / ${Number(run.total_steps).toLocaleString()} ${t("steps ·")} ${t(run.status)}`;
  $('#train-loss').textContent = fmt(metric.loss); $('#eval-loss').textContent = fmt(metric.eval_loss); $('#learning-rate').textContent = metric.learning_rate ? Number(metric.learning_rate).toExponential(1) : '—';
  $('#current-step').textContent = `${step} / ${run.total_steps}`; $('#chart-context').textContent = `${run.metrics?.length || 0} ${t(real?"points · measured":"points · simulated")}`;
  $('#loss-chart').innerHTML = chart(run.metrics || [], run.total_steps, !real);
  const defaultActions = {queued:['start','cancel'],running:['pause','cancel'],paused:['resume','cancel'],failed:['retry'],canceled:['retry'],completed:[]};
  const actions = run.allowed_actions || defaultActions[run.status] || [];
  const labels = {start:t(real?"▷ Start training":"▷ Start demo"),pause:t(real?"Ⅱ Checkpoint & pause":"Ⅱ Pause demo"),resume:t(real?"▷ Resume training":"▷ Resume demo"),cancel:t(real?"× Cancel training":"× Cancel demo"),retry:t("↻ Retry as new run")};
  $('#run-controls').innerHTML = actions.map(action => `<button class="button ${action === 'cancel' ? 'danger' : action === 'start' || action === 'resume' || action === 'retry' ? 'primary' : 'secondary'}" data-action="${escapeHtml(action)}" ${requestBusy || !remoteControlsAllowed ? 'disabled' : ''}>${labels[action] || escapeHtml(action)}</button>`).join('') || `<span class="status completed">${t("Run finished")}</span>`;
  $$('#run-controls button').forEach(btn => { btn.onclick = () => performAction(run.id, btn.dataset.action); });
  const error = run.error; $('#run-error').hidden = !error;
  if(error) { const message = typeof error === 'string' ? error : error.message || JSON.stringify(error); const injected = run.config?.failure_mode === 'oom'; $('#run-error').innerHTML = `<strong>${t(real?"Training failure:":"Demo failure:")}</strong> ${escapeHtml(t(message))}<div class="field-note" style="margin-top:7px">${injected ? t("Injected OOM scenario. Retry preserves the injection, so it can fail again. Review batch, context and rank in Training setup; a revised recipe uses the normal demo scenario.") : t("Retry creates a new queued run and preserves this original record.")}</div><button id="review-failed-recipe" class="button secondary" style="margin-top:9px">${t("Review training recipe")}</button>`; $('#review-failed-recipe').onclick = () => { if(typeof prepareRecipeFromRun === 'function') prepareRecipeFromRun(run); else setNav('recipes'); }; }
  else $('#run-error').textContent = '';
  $('#log-count').textContent = run.logs?.length || 0;
  if (currentTab === 'logs') {
    const wasNearBottom = !$('.log-view') || $('.log-view').scrollHeight - $('.log-view').scrollTop - $('.log-view').clientHeight < 35;
    const oldScroll = $('.log-view')?.scrollTop || 0; const logsOpen = $('.technical-logs')?.open || false;
    $('#tab-content').innerHTML = `<details class="technical-logs" ${logsOpen ? 'open' : ''}><summary>${t(real?"Training worker log":"Technical demo log · synthetic, token-like text redacted")}</summary><div class="log-view" aria-label="${t("Synthetic training logs")}">${run.logs?.length ? run.logs.map(log => `<div class="log-line"><span class="log-time">${escapeHtml(formatTime(log.time))}</span><span class="log-level ${String(log.level).toLowerCase()}">${escapeHtml(String(log.level).toUpperCase())}</span><span class="log-message">${escapeHtml(typeof safeTechnicalText === 'function' ? safeTechnicalText(log.message) : log.message)}</span></div>`).join('') : `<span class="log-message">${t("No log events yet. Start this queued demo run to generate events.")}</span>`}</div></details>`;
    $('.log-view').scrollTop = wasNearBottom ? $('.log-view').scrollHeight : oldScroll;
  } else if (currentTab === 'checkpoints') {
    $('#tab-content').innerHTML = `<div class="checkpoint-list">${run.checkpoints?.length ? run.checkpoints.map(cp => `<div class="checkpoint"><span>▱</span><div>${escapeHtml(cp.name || cp.label)}<div class="run-meta">${cp.virtual===false?`<a class="button secondary" href="/api/runs/${encodeURIComponent(run.id)}/artifacts/${encodeURIComponent(cp.name)}">${t("Download adapter weights")}</a>`:t("Virtual checkpoint · no weights saved")}</div></div><small>${t("Step")} ${escapeHtml(cp.step)}${cp.size_mb ? ` · ${escapeHtml(cp.size_mb)} ${t(cp.virtual===false?"MB":"MB (simulated)")}` : ''}</small></div>`).join('') : `<div class="empty">${t(real?"No checkpoints yet":"No virtual checkpoints yet. Real model weights are never saved.")}</div>`}</div>`;
  } else if (currentTab === 'evaluation') {
    $('#tab-content').innerHTML = run.evaluation ? `<h4>${t("Held-out evaluation")}</h4><div class="config-list"><div><span>${t("Baseline eval loss")}</span><strong>${fmt(run.evaluation.baseline_eval_loss)}</strong></div><div><span>${t("Final eval loss")}</span><strong>${fmt(run.evaluation.eval_loss)}</strong></div></div><p>${t("Generated response")}</p><pre class="preview-record">${escapeHtml(run.evaluation.generated_response)}</pre><p>${t("Reference answer")}</p><pre class="preview-record">${escapeHtml(run.evaluation.reference)}</pre><p>${t("Small synthetic checks establish pipeline operation, not model quality.")}</p>` : `<div class="empty">${t("Evaluation appears after real training completes")}</div>`;
  } else {
    const entries = Object.entries(run.config || {}).filter(([key]) => !['name'].includes(key));
    $('#tab-content').innerHTML = `<div class="config-list">${entries.map(([key,value]) => `<div><span>${escapeHtml(t(key.replaceAll('_',' ')))}</span><strong>${escapeHtml(value)}</strong></div>`).join('')}</div>`;
  }
}
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(11,19); }
function chart(metrics, totalSteps, simulated=true) {
  if (!metrics.length) return `<div class="chart-empty">${t("Learning curves appear after a demo run starts")}</div>`;
  const width = 620, height = 175, left = 32, right = 8, top = 12, bottom = 25;
  const values = metrics.flatMap(m => [m.loss,m.eval_loss]).filter(v => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
  if (!values.length) return `<div class="chart-empty">${t("Waiting for valid metric points")}</div>`;
  const lo = Math.max(0,Math.floor(Math.min(...values)*2)/2-.25), hi = Math.ceil(Math.max(...values)*2)/2+.25;
  const xmax = Math.max(10,metrics.at(-1).step); const x = v => left + v/xmax*(width-left-right), y = v => top + (hi-v)/(hi-lo)*(height-top-bottom);
  const line = key => metrics.filter(m => m[key] !== null && m[key] !== undefined && Number.isFinite(Number(m[key]))).map((m,i) => `${i ? 'L' : 'M'}${x(m.step).toFixed(1)},${y(Number(m[key])).toFixed(1)}`).join(' ');
  let grid = '';
  for(let i=0;i<4;i++){ const v = lo + (hi-lo)*i/3, py = y(v); grid += `<line x1="${left}" x2="${width-right}" y1="${py}" y2="${py}" stroke="#2a2e39" stroke-dasharray="3 5"/><text x="0" y="${py+3}" fill="var(--faint)" font-size="8">${v.toFixed(1)}</text>`; }
  for(let i=0;i<5;i++){ const v = xmax*i/4; grid += `<text x="${x(v)}" y="${height-5}" text-anchor="middle" fill="var(--faint)" font-size="8">${Math.round(v)}</text>`; }
  const train = line('loss'), evalPath = line('eval_loss');
  const last = metrics.at(-1);
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${t(simulated?"Synthetic loss chart, {count} points, latest training loss {loss}":"Measured loss chart, {count} points, latest training loss {loss}", {count: metrics.length, loss: fmt(last.loss)})}"><defs><linearGradient id="loss-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#b0a0ff" stop-opacity=".17"/><stop offset="1" stop-color="#b0a0ff" stop-opacity="0"/></linearGradient></defs>${grid}${train ? `<path d="${train} L${x(last.step)},${height-bottom} L${x(metrics[0].step)},${height-bottom} Z" fill="url(#loss-fill)"/>` : ''}<path d="${train}" fill="none" stroke="#b0a0ff" stroke-width="2" stroke-linejoin="round"/><path d="${evalPath}" fill="none" stroke="#8ee3cc" stroke-width="1.7" stroke-dasharray="4 3" stroke-linejoin="round"/>${Number.isFinite(last.loss) ? `<circle cx="${x(last.step)}" cy="${y(last.loss)}" r="3" fill="#b0a0ff" stroke="#181b22" stroke-width="2"/>` : ''}</svg>`;
}
async function performAction(id, action) {
  if (requestBusy) return; requestBusy = true; render();
  try { const payload = await api(`/api/runs/${encodeURIComponent(id)}/${action}`, {}); snapshot = payload.snapshot || snapshot; if (payload.run) selectedId = payload.run.id; toast(id.startsWith('train-') ? t('Worker request acknowledged') : {start:t("Demo run started"),pause:t("Demo run paused"),resume:t("Demo run resumed"),cancel:t("Demo run canceled"),retry:t("New retry queued. Starts when the simulated GPU is free.")}[action]); await refresh(); }
  catch (error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
}
function openDialog(){ $('#form-error').hidden = true; $('#run-dialog').showModal(); }
$('#new-run').onclick = ()=>snapshot?.training?.available?setNav('recipes'):openDialog(); $('#close-dialog').onclick = () => $('#run-dialog').close(); $('#cancel-dialog').onclick = () => $('#run-dialog').close();
$('#run-dialog').addEventListener('click', e => { if (e.target === $('#run-dialog')) { const box = $('#run-dialog').getBoundingClientRect(); if(e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) $('#run-dialog').close(); } });
$('#run-form').addEventListener('submit', async e => {
  e.preventDefault(); if(requestBusy) return; requestBusy = true; const submit = $('#run-form button[type="submit"]'); submit.disabled = true; $('#form-error').hidden = true;
  const data = Object.fromEntries(new FormData(e.target)); for(const key of ['learning_rate','batch_size','lora_rank','epochs','gradient_accumulation','max_steps']) data[key] = Number(data[key]);
  try { const payload = await api('/api/runs',data); snapshot = payload.snapshot || snapshot; selectedId = payload.run.id; filter = 'all'; $$('.filter').forEach(btn => btn.classList.toggle('active',btn.dataset.filter === filter)); $('#run-dialog').close(); toast(t("Demo experiment queued. Starts when the simulated GPU is free.")); await refresh(); setNav('runs'); $('#run-detail').scrollIntoView({behavior:'smooth',block:'start'}); }
  catch(error) { $('#form-error').textContent = error.message; $('#form-error').hidden = false; }
  finally { requestBusy = false; submit.disabled = false; render(); }
});
$$('.filter').forEach(btn => { btn.onclick = () => { filter = btn.dataset.filter; $$('.filter').forEach(other => other.classList.toggle('active',other === btn)); render(); }; });
$$('.tab').forEach(btn => {
  btn.id = `tab-${btn.dataset.tab}`;
  btn.setAttribute('aria-controls', 'tab-content');
  btn.setAttribute('tabindex', btn.dataset.tab === currentTab ? '0' : '-1');
  btn.onclick = () => {
    currentTab = btn.dataset.tab;
    $$('.tab').forEach(other => { other.classList.toggle('active',other === btn); other.setAttribute('aria-selected', String(other === btn)); other.setAttribute('tabindex',other === btn ? '0' : '-1'); });
    $('#tab-content').setAttribute('aria-labelledby', btn.id);
    render();
  };
  btn.onkeydown = event => {
    const tabs = $$('.tab'), index = tabs.indexOf(btn);
    const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index - 1 + tabs.length) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
    if (next === null) return;
    event.preventDefault(); tabs[next].focus(); tabs[next].click();
  };
});
function setNav(value) {
  nav = value;
  $$('.nav-item').forEach(btn => { btn.classList.toggle('active',btn.dataset.nav === value); btn.setAttribute('aria-current',btn.dataset.nav === value ? 'page' : 'false'); });
  const advanced = !['overview','runs'].includes(value);
  $('#worker-info').hidden = true;
  $('#workspace-view').hidden = !advanced;
  $('#run-detail').hidden = advanced;
  $('#experiments').hidden = advanced;
  $('.summary-grid').hidden = advanced;
  $('#mobile-view').value = value;
  const names = {overview:t("Overview"),runs:t("Experiments"),datasets:t("Datasets"),recipes:t("Training setup"),compare:t("Compare runs"),environment:t("Environment"),settings:t("Access settings")};
  $('.breadcrumbs strong').textContent = names[value] || value;
  render();
  if (advanced && typeof loadWorkspaceView === 'function') loadWorkspaceView(value);
  if(value === 'runs') $('#experiments').scrollIntoView({behavior:'smooth',block:'start'});
}
$$('.nav-item').forEach(btn => { btn.onclick = () => setNav(btn.dataset.nav); });
refresh(); setInterval(refresh,2000); document.addEventListener('visibilitychange', () => { if(!document.hidden) refresh(); });

$('#run-form select[name="kind"]').onchange = (e) => { const vlm = e.target.value === 'VLM'; $('#run-form select[name="model"]').value = vlm ? 'demo/vlm-3b' : 'demo/llm-3b'; $('#run-form input[name="dataset"]').value = vlm ? 'synthetic-image-captions' : 'synthetic-instructions'; };

$('#mobile-view').onchange = (event) => setNav(event.target.value);
