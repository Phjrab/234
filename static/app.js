'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value, digits = 3) => Number.isFinite(Number(value)) && value !== null && value !== undefined ? Number(value).toFixed(digits) : '—';
const pct = value => Math.max(0, Math.min(100, Number(value) || 0));
let authToken = null, remoteControlsAllowed = true;
let snapshot = null, selectedId = null, filter = 'all', currentTab = 'logs', requestBusy = false, refreshBusy = false, toastTimer, nav = 'overview';
try { selectedId = localStorage.getItem('forge.selectedRun'); } catch {}
function toast(message, error = false) { const el = $('#toast'); el.textContent = message; el.hidden = false; el.classList.toggle('error', error); clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4200); }
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? {} : {'Content-Type': 'application/json',...(authToken ? {'X-CSRF-Token':authToken} : {})}, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store', signal:controller.signal});
    let payload; try { payload = await response.json(); } catch { throw new Error('The local API returned an unreadable response'); }
    if (!response.ok) { const error = new Error(payload.error?.message || payload.error || `Request failed (${response.status})`); error.status = response.status; error.code = payload.error?.code; error.details = payload.error?.details; if(response.status === 401 && typeof showLogin === 'function') showLogin(); throw error; }
    return payload;
  } catch(error) {
    if(error.name === 'AbortError') throw new Error('The local API timed out. Check that the demo server is running.');
    throw error;
  } finally { clearTimeout(timeout); }
}
function setConnection(ok) { const el = $('#connection'); el.className = 'connection ' + (ok ? 'ok' : 'error'); el.innerHTML = `<i></i> ${ok ? 'Demo API online' : 'API offline · data stale'}`; }
async function refresh() {
  if (refreshBusy) return; refreshBusy = true;
  try { snapshot = await api('/api/status'); setConnection(true); render(); }
  catch(error) { setConnection(false); if(error.status === 401) { snapshot=null; $('#run-detail').hidden=true; $('#tab-content').innerHTML=''; $('#loss-chart').innerHTML=''; } if(error.status === 401 || error.code === 'bootstrap_required' || error.code === 'password_change_required') { $('#connection').innerHTML='<i></i> Local sign-in required'; if(typeof checkAccess === 'function') checkAccess(); } if (!snapshot) { $('#runs-body').innerHTML = '<tr><td colspan="6" class="empty">Sign in locally to finish setup, or check that python server.py is running.</td></tr>'; $('#selected-title').textContent = 'Waiting for the local demo API'; } }
  finally { refreshBusy = false; }
}
function selectRun(id) { selectedId = id; try { localStorage.setItem('forge.selectedRun', id); } catch {} render(); }
function latest(run) { return run.latest_metrics || run.metrics?.at(-1) || {}; }
function render() {
  if (!snapshot) return;
  const runs = snapshot.runs || [], gpu = snapshot.gpu || {};
  if (!runs.some(run => run.id === selectedId)) selectedId = snapshot.active_run_id || runs[0]?.id;
  $('#summary-total').textContent = runs.length; $('#nav-count').textContent = runs.length; $('#experiment-count').textContent = runs.length;
  const completed = runs.filter(r => r.status === 'completed').length, queued = runs.filter(r => r.status === 'queued').length;
  $('#summary-caption').textContent = `${completed} completed · ${queued} queued`;
  const failedRuns=runs.filter(run=>run.status==='failed'); const pausedRuns=runs.filter(run=>run.status==='paused');
  $('#workspace-alerts').hidden = nav!=='overview' || (!failedRuns.length && !pausedRuns.length);
  $('#workspace-alerts').innerHTML = `${failedRuns.length?`<span>◉ ${failedRuns.length} demo failure${failedRuns.length===1?'':'s'} recorded. Review the injected scenario and next steps.</span><button id="inspect-latest-failure" class="button secondary">Review failure</button>`:''}${pausedRuns.length?'<span>Ⅱ A paused demo job reserves the GPU slot. Resume or cancel it to release the queue.</span>':''}`;
  if(failedRuns.length) $('#inspect-latest-failure').onclick=()=>{selectedId=failedRuns[0].id;setNav('runs');};
  $('#summary-active').innerHTML = `${runs.filter(r => r.status === 'running').length} <small>running</small>`;
  $('#summary-vram').innerHTML = `${fmt(gpu.used_gb,1)} <small>/ ${fmt(gpu.total_gb,0)} GB</small>`;
  $('#vram-bar').style.width = `${pct(gpu.used_gb / gpu.total_gb * 100)}%`;
  $('#gpu-util').textContent = `${fmt(gpu.utilization,0)}%`; $('#gpu-util-bar').style.width = `${pct(gpu.utilization)}%`;
  $('#gpu-memory').textContent = `${fmt(gpu.used_gb,1)} / ${fmt(gpu.total_gb,0)} GB`; $('#gpu-memory-bar').style.width = `${pct(gpu.used_gb / gpu.total_gb * 100)}%`;
  $('#gpu-temp').textContent = `${fmt(gpu.temp_c,0)} °C`;
  const shown = runs.filter(run => (filter === 'all' || run.kind === filter) && (nav !== 'overview' || ['running','paused'].includes(run.status)));
  $('#no-runs').textContent = nav === 'overview' ? 'No active demo jobs. Open Experiments to start or inspect a queued run.' : 'No experiments in this view yet';
  if(nav === 'overview' && !runs.some(run => run.id === selectedId && ['running','paused'].includes(run.status))) selectedId = snapshot.active_run_id || runs.find(run => run.status === 'paused')?.id || null;
  if(['overview','runs'].includes(nav)) $('#run-detail').hidden = nav === 'overview' && !selectedId;
  $('.run-data').hidden = nav === 'overview';
  $('#no-runs').hidden = shown.length > 0;
  $('#runs-body').innerHTML = shown.map(run => {
    const progress = pct(run.progress ?? run.step / run.total_steps * 100), metric = latest(run);
    return `<tr tabindex="0" data-run="${escapeHtml(run.id)}" class="${run.id === selectedId ? 'selected' : ''}" aria-label="Select ${escapeHtml(run.name)}"><td><div class="run-name"><span class="type-icon ${run.kind === 'VLM' ? 'vlm' : ''}">${run.kind === 'VLM' ? '▧' : '≋'}</span><div>${escapeHtml(run.name)}<div class="run-meta">${escapeHtml(run.kind)} · ${escapeHtml(run.config?.model || run.model_id || 'demo model')}</div></div></div></td><td><span class="status ${escapeHtml(run.status)}">${escapeHtml(run.status)}</span></td><td><div class="progress-line"><div class="meter"><span style="width:${progress}%"></span></div><span>${Math.round(progress)}%</span></div></td><td>${fmt(metric.loss)}</td><td><span class="method-tag">${escapeHtml((run.method || run.config?.method || 'QLoRA').toUpperCase())} · r${escapeHtml(run.config?.lora_rank || 16)}</span></td><td class="row-arrow">↗</td></tr>`;
  }).join('');
  $$('#runs-body tr[data-run]').forEach(row => { row.onclick = () => selectRun(row.dataset.run); row.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectRun(row.dataset.run); } }; });
  const run = runs.find(r => r.id === selectedId); if (run) renderDetail(run);
  if(nav==='compare' && typeof updateComparison==='function' && $('#compare-output')) updateComparison();
}
function renderDetail(run) {
  const metric = latest(run), step = run.step ?? run.current_step ?? 0;
  $('#selected-title').textContent = run.name; $('#selected-subtitle').textContent = `${run.kind} · ${(run.method || 'qlora').toUpperCase()} · ${step.toLocaleString()} / ${Number(run.total_steps).toLocaleString()} steps · ${run.status}`;
  $('#train-loss').textContent = fmt(metric.loss); $('#eval-loss').textContent = fmt(metric.eval_loss); $('#learning-rate').textContent = metric.learning_rate ? Number(metric.learning_rate).toExponential(1) : '—';
  $('#current-step').textContent = `${step} / ${run.total_steps}`; $('#chart-context').textContent = `${run.metrics?.length || 0} points · simulated`;
  $('#loss-chart').innerHTML = chart(run.metrics || [], run.total_steps);
  const defaultActions = {queued:['start','cancel'],running:['pause','cancel'],paused:['resume','cancel'],failed:['retry'],canceled:['retry'],completed:[]};
  const actions = run.allowed_actions || defaultActions[run.status] || [];
  const labels = {start:'▷ Start demo',pause:'Ⅱ Pause demo',resume:'▷ Resume demo',cancel:'× Cancel demo',retry:'↻ Retry as new run'};
  $('#run-controls').innerHTML = actions.map(action => `<button class="button ${action === 'cancel' ? 'danger' : action === 'start' || action === 'resume' || action === 'retry' ? 'primary' : 'secondary'}" data-action="${escapeHtml(action)}" ${requestBusy || !remoteControlsAllowed ? 'disabled' : ''}>${labels[action] || escapeHtml(action)}</button>`).join('') || '<span class="status completed">Run finished</span>';
  $$('#run-controls button').forEach(btn => { btn.onclick = () => performAction(run.id, btn.dataset.action); });
  const error = run.error; $('#run-error').hidden = !error;
  if(error) { const message = typeof error === 'string' ? error : error.message || JSON.stringify(error); const injected = run.config?.failure_mode === 'oom'; $('#run-error').innerHTML = `<strong>Demo failure:</strong> ${escapeHtml(message)}<div class="field-note" style="margin-top:7px">${injected ? 'Injected OOM scenario. Retry preserves the injection, so it can fail again. Review batch, context and rank in Training setup; a revised recipe uses the normal demo scenario.' : 'Retry creates a new queued run and preserves this original record.'}</div><button id="review-failed-recipe" class="button secondary" style="margin-top:9px">Review training recipe</button>`; $('#review-failed-recipe').onclick = () => { if(typeof prepareRecipeFromRun === 'function') prepareRecipeFromRun(run); else setNav('recipes'); }; }
  else $('#run-error').textContent = '';
  $('#log-count').textContent = run.logs?.length || 0;
  if (currentTab === 'logs') {
    const wasNearBottom = !$('.log-view') || $('.log-view').scrollHeight - $('.log-view').scrollTop - $('.log-view').clientHeight < 35;
    const oldScroll = $('.log-view')?.scrollTop || 0; const logsOpen = $('.technical-logs')?.open || false;
    $('#tab-content').innerHTML = `<details class="technical-logs" ${logsOpen ? 'open' : ''}><summary>Technical demo log · synthetic, token-like text redacted</summary><div class="log-view" aria-label="Synthetic training logs">${run.logs?.length ? run.logs.map(log => `<div class="log-line"><span class="log-time">${escapeHtml(formatTime(log.time))}</span><span class="log-level ${String(log.level).toLowerCase()}">${escapeHtml(String(log.level).toUpperCase())}</span><span class="log-message">${escapeHtml(typeof safeTechnicalText === 'function' ? safeTechnicalText(log.message) : log.message)}</span></div>`).join('') : '<span class="log-message">No log events yet. Start this queued demo run to generate events.</span>'}</div></details>`;
    $('.log-view').scrollTop = wasNearBottom ? $('.log-view').scrollHeight : oldScroll;
  } else if (currentTab === 'checkpoints') {
    $('#tab-content').innerHTML = `<div class="checkpoint-list">${run.checkpoints?.length ? run.checkpoints.map(cp => `<div class="checkpoint"><span>▱</span><div>${escapeHtml(cp.name || cp.label)}<div class="run-meta">Virtual checkpoint · no weights saved</div></div><small>Step ${escapeHtml(cp.step)}${cp.size_mb ? ` · ${escapeHtml(cp.size_mb)} MB (simulated)` : ''}</small></div>`).join('') : '<div class="empty">No virtual checkpoints yet. Real model weights are never saved.</div>'}</div>`;
  } else {
    const entries = Object.entries(run.config || {}).filter(([key]) => !['name'].includes(key));
    $('#tab-content').innerHTML = `<div class="config-list">${entries.map(([key,value]) => `<div><span>${escapeHtml(key.replaceAll('_',' '))}</span><strong>${escapeHtml(value)}</strong></div>`).join('')}</div>`;
  }
}
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(11,19); }
function chart(metrics, totalSteps) {
  if (!metrics.length) return '<div class="chart-empty">Learning curves appear after a demo run starts</div>';
  const width = 620, height = 175, left = 32, right = 8, top = 12, bottom = 25;
  const values = metrics.flatMap(m => [m.loss,m.eval_loss]).filter(v => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
  if (!values.length) return '<div class="chart-empty">Waiting for valid metric points</div>';
  const lo = Math.max(0,Math.floor(Math.min(...values)*2)/2-.25), hi = Math.ceil(Math.max(...values)*2)/2+.25;
  const xmax = Math.max(10,metrics.at(-1).step); const x = v => left + v/xmax*(width-left-right), y = v => top + (hi-v)/(hi-lo)*(height-top-bottom);
  const line = key => metrics.filter(m => m[key] !== null && m[key] !== undefined && Number.isFinite(Number(m[key]))).map((m,i) => `${i ? 'L' : 'M'}${x(m.step).toFixed(1)},${y(Number(m[key])).toFixed(1)}`).join(' ');
  let grid = '';
  for(let i=0;i<4;i++){ const v = lo + (hi-lo)*i/3, py = y(v); grid += `<line x1="${left}" x2="${width-right}" y1="${py}" y2="${py}" stroke="#2a2e39" stroke-dasharray="3 5"/><text x="0" y="${py+3}" fill="#626a7d" font-size="8">${v.toFixed(1)}</text>`; }
  for(let i=0;i<5;i++){ const v = xmax*i/4; grid += `<text x="${x(v)}" y="${height-5}" text-anchor="middle" fill="#626a7d" font-size="8">${Math.round(v)}</text>`; }
  const train = line('loss'), evalPath = line('eval_loss');
  const last = metrics.at(-1);
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Synthetic loss chart, ${metrics.length} points, latest training loss ${escapeHtml(fmt(last.loss))}"><defs><linearGradient id="loss-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#b0a0ff" stop-opacity=".17"/><stop offset="1" stop-color="#b0a0ff" stop-opacity="0"/></linearGradient></defs>${grid}${train ? `<path d="${train} L${x(last.step)},${height-bottom} L${x(metrics[0].step)},${height-bottom} Z" fill="url(#loss-fill)"/>` : ''}<path d="${train}" fill="none" stroke="#b0a0ff" stroke-width="2" stroke-linejoin="round"/><path d="${evalPath}" fill="none" stroke="#8ee3cc" stroke-width="1.7" stroke-dasharray="4 3" stroke-linejoin="round"/>${Number.isFinite(last.loss) ? `<circle cx="${x(last.step)}" cy="${y(last.loss)}" r="3" fill="#b0a0ff" stroke="#181b22" stroke-width="2"/>` : ''}</svg>`;
}
async function performAction(id, action) {
  if (requestBusy) return; requestBusy = true; render();
  try { const payload = await api(`/api/runs/${encodeURIComponent(id)}/${action}`, {}); snapshot = payload.snapshot || snapshot; if (payload.run) selectedId = payload.run.id; toast({start:'Demo run started',pause:'Demo run paused',resume:'Demo run resumed',cancel:'Demo run canceled',retry:'New retry queued. Starts when the simulated GPU is free.'}[action]); await refresh(); }
  catch (error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
}
function openDialog(){ $('#form-error').hidden = true; $('#run-dialog').showModal(); }
$('#new-run').onclick = openDialog; $('#close-dialog').onclick = () => $('#run-dialog').close(); $('#cancel-dialog').onclick = () => $('#run-dialog').close();
$('#run-dialog').addEventListener('click', e => { if (e.target === $('#run-dialog')) { const box = $('#run-dialog').getBoundingClientRect(); if(e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) $('#run-dialog').close(); } });
$('#run-form').addEventListener('submit', async e => {
  e.preventDefault(); if(requestBusy) return; requestBusy = true; const submit = $('#run-form button[type="submit"]'); submit.disabled = true; $('#form-error').hidden = true;
  const data = Object.fromEntries(new FormData(e.target)); for(const key of ['learning_rate','batch_size','lora_rank','epochs','gradient_accumulation','max_steps']) data[key] = Number(data[key]);
  try { const payload = await api('/api/runs',data); snapshot = payload.snapshot || snapshot; selectedId = payload.run.id; filter = 'all'; $$('.filter').forEach(btn => btn.classList.toggle('active',btn.dataset.filter === filter)); $('#run-dialog').close(); toast('Demo experiment queued. Starts when the simulated GPU is free.'); await refresh(); setNav('runs'); $('#run-detail').scrollIntoView({behavior:'smooth',block:'start'}); }
  catch(error) { $('#form-error').textContent = error.message; $('#form-error').hidden = false; }
  finally { requestBusy = false; submit.disabled = false; render(); }
});
$$('.filter').forEach(btn => { btn.onclick = () => { filter = btn.dataset.filter; $$('.filter').forEach(other => other.classList.toggle('active',other === btn)); render(); }; });
$$('.tab').forEach(btn => { btn.onclick = () => { currentTab = btn.dataset.tab; $$('.tab').forEach(other => { other.classList.toggle('active',other === btn); other.setAttribute('aria-selected', String(other === btn)); }); render(); }; });
function setNav(value) {
  nav = value;
  $$('.nav-item').forEach(btn => btn.classList.toggle('active',btn.dataset.nav === value));
  const advanced = !['overview','runs'].includes(value);
  $('#worker-info').hidden = true;
  $('#workspace-view').hidden = !advanced;
  $('#run-detail').hidden = advanced;
  $('#experiments').hidden = advanced;
  $('.summary-grid').hidden = advanced;
  $('#mobile-view').value = value === 'runs' ? 'overview' : value;
  const names = {overview:'Overview',runs:'Experiments',datasets:'Datasets',recipes:'Training setup',compare:'Compare runs',environment:'Environment',settings:'Access settings'};
  $('.breadcrumbs strong').textContent = names[value] || value;
  render();
  if (advanced && typeof loadWorkspaceView === 'function') loadWorkspaceView(value);
  if(value === 'runs') $('#experiments').scrollIntoView({behavior:'smooth',block:'start'});
}
$$('.nav-item').forEach(btn => { btn.onclick = () => setNav(btn.dataset.nav); });
refresh(); setInterval(refresh,2000); document.addEventListener('visibilitychange', () => { if(!document.hidden) refresh(); });

$('#run-form select[name="kind"]').onchange = (e) => { const vlm = e.target.value === 'VLM'; $('#run-form select[name="model"]').value = vlm ? 'demo/vlm-3b' : 'demo/llm-3b'; $('#run-form input[name="dataset"]').value = vlm ? 'synthetic-image-captions' : 'synthetic-instructions'; };

$('#mobile-view').onchange = (event) => setNav(event.target.value);
