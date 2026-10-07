// Run inside Codex cua_repl after binding `tab` (IAB) and `browser` and signing
// into tools/ui_fixture_server.py. This is an actual browser suite, not a Node DOM stub.
// The only POSTs invoked here are JSONL validation, config dry-run and denied fixture preflight.
// It never clicks Launch, run lifecycle, model download, credentials or access settings writes.
async function captureForgeWorkbench({tab,browser,directory,commitSha}) {
  const fs=await import('node:fs/promises');
  await fs.mkdir(directory,{recursive:true});
  const report={status:'RUNNING',fixture_id:'forge-workbench-v1',started_at:new Date().toISOString(),checks:[],captures:[],console:[]};
  const viewport=await browser.capabilities.get('viewport');
  let size={width:1440,height:900};
  const check=(name,value)=>{report.checks.push({name,status:value?'PASS':'FAIL'});if(!value)throw Error(name);};
  const snapshot=()=>tab.playwright.domSnapshot();
  async function capture(name,scenario){
    const state=await snapshot();
    check(name+' fixture watermark',state.includes('UI DEMO / SYNTHETIC FIXTURE'));
    const filename=name+'.jpg';
    await fs.writeFile(directory+'/'+filename,await tab.screenshot({fullPage:false}));
    report.captures.push({filename,repo:'Phjrab/forge-finetune-dashboard',commit_sha:commitSha,captured_at:new Date().toISOString(),viewport:size.width+'x'+size.height,route:await tab.url(),scenario,fixture_id:report.fixture_id,data_provenance:'synthetic UI fixture; real-source shape and demo are explicit',live_actions:'none; only isolated validation/dry-run',privacy_review:'PASS synthetic data only'});
  }
  async function navigate(view){
    if(size.width>760)await tab.playwright.locator('[data-nav='+view+']').click();
    else await tab.playwright.locator('#mobile-view').selectOption(view);
    await snapshot();
  }
  async function select(id){
    if(size.width>760)await tab.playwright.locator('tr[data-run="'+id+'"]').press('Enter');
    else await tab.playwright.locator('#mobile-run').selectOption(id);
    await snapshot();
  }
  try{
    await viewport.set(size);
    await navigate('settings');await tab.playwright.locator('#language-select').selectOption('en');await snapshot();
    await navigate('overview');await select('train-000000000001');await tab.playwright.locator('[data-tab=logs]').click();
    if(await tab.playwright.locator('#inspector-toggle').getAttribute('aria-expanded')==='false')await tab.playwright.locator('#inspector-toggle').click();
    await capture('after-workspace-1440','same selected real-source run as baseline');
    report.styles=await tab.playwright.evaluate(()=>['body','.sidebar','.nav-item.active','.button.primary','.chart-foot','.run-data','.tab.active','.filter.active','.loss-panel path'].map(selector=>{const node=document.querySelector(selector);if(!node)return null;const style=getComputedStyle(node);return{selector,color:style.color,background:style.backgroundColor,border:style.borderColor,stroke:style.stroke};}));
    // A real timer is necessary to exercise the existing two-second poll and focus restoration.
    await tab.playwright.locator('tr[data-run="train-000000000004"]').press('Enter');
    await tab.playwright.waitForTimeout(2300);
    check('explorer keyboard focus survives polling',await tab.playwright.evaluate(()=>document.activeElement?.dataset.run)==='train-000000000004');
    check('paused actions remain server-owned',(await snapshot()).includes('Resume training'));
    for(const [id,state]of [['train-000000000002','queued'],['train-000000000003','pausing'],['train-000000000004','paused'],['train-000000000005','completed'],['train-000000000006','failed'],['train-000000000007','canceled']]){
      await select(id);check('real-source state '+state,(await tab.playwright.locator('#run-state').textContent())===state);
    }
    await select('train-000000000001');await tab.playwright.locator('[data-tab=evaluation]').click();
    check('missing evaluation stays missing',(await snapshot()).includes('Evaluation appears after real training completes'));
    await select('train-000000000005');await tab.playwright.locator('[data-tab=checkpoints]').click();
    check('checkpoint download uses selected run',(await tab.playwright.locator('#tab-content a').getAttribute('href')).includes('train-000000000005/artifacts/checkpoint-000010'));
    await capture('after-checkpoints-1440','real-source fixture checkpoint metadata; no file opened');
    await tab.playwright.locator('[data-tab=evaluation]').click();await capture('after-evaluation-1440','held-out/generated-response fixture; no model quality claim');
    await tab.playwright.getByRole('row',{name:/Research assistant/}).press('Enter');
    check('demo source remains explicit',(await tab.playwright.locator('#run-source').textContent()).includes('Demo'));
    await tab.playwright.locator('[data-tab=logs]').click();await capture('after-demo-1440','demo-vs-real source distinction');
    await tab.playwright.getByRole('row',{name:/Vision adapter · memory test/}).press('Enter');
    check('injected OOM guidance visible',(await snapshot()).includes('Injected OOM scenario'));
    await capture('after-demo-oom-1440','synthetic injected failure; retry not invoked');
    for(const view of ['compare','environment']){await navigate(view);check(view+' rendered',await tab.playwright.locator('#workspace-view').isVisible());}
    await navigate('datasets');await tab.playwright.locator('#dataset-validate').click();await snapshot();
    check('actual isolated schema validation',(await tab.playwright.locator('#dataset-result').textContent()).includes('schema validation passed'));
    await tab.playwright.locator('#dataset-result h4').click();await capture('after-dataset-validation-1440','actual backend validation of synthetic JSONL');
    await navigate('models');await tab.playwright.locator('[data-hf-model="Qwen/Qwen2.5-0.5B-Instruct"]').click();await snapshot();
    check('installed model separate from download',!(await tab.playwright.locator('#hf-download-model').isEnabled()));
    await capture('after-model-readiness-1440','installed model metadata; no download');
    await tab.playwright.locator('[data-hf-model="fixture/unsupported-GGUF"]').click();await snapshot();
    check('unsupported model cannot download',!(await tab.playwright.locator('#hf-download-model').isEnabled()));
    await capture('after-model-unsupported-1440','GGUF unsupported/missing safetensors fixture');
    await tab.playwright.locator('#hf-search').fill('unreachable');await tab.playwright.locator('#hf-search-form button[type=submit]').click();await snapshot();
    check('Hub failure is actionable',(await tab.playwright.locator('#hf-results').textContent()).includes('Hugging Face is unavailable'));
    await navigate('recipes');await tab.playwright.locator('#builder-reset').click();
    await tab.playwright.locator('#training-model option[value="Qwen/Qwen2.5-0.5B-Instruct"]').waitFor({state:'attached'});
    await tab.playwright.locator('#recipe-form input[name=name]').fill('instruction-lora-review');
    await tab.playwright.locator('#builder-next').click();await snapshot();
    await tab.playwright.locator('#builder-next').click();await tab.playwright.locator('#recipe-form select[name=method]').selectOption('lora');
    await tab.playwright.locator('#builder-next').click();await snapshot();
    await tab.playwright.locator('#recipe-form input[name=learning_rate]').fill('0.00015');
    await tab.playwright.locator('#recipe-form input[name=batch_size]').fill('5');await tab.playwright.locator('#builder-next').click();
    check('real batch cap blocks navigation',await tab.playwright.locator('[data-builder-panel="3"]').isVisible());
    await tab.playwright.locator('#recipe-form input[name=batch_size]').fill('1');await tab.playwright.locator('#builder-next').click();await snapshot();
    await tab.playwright.locator('#workspace-view').press('Control+Home');
    check('review preserves edited recipe',(await tab.playwright.locator('#builder-review').textContent()).includes('0.00015'));
    await capture('after-builder-review-1440','six-step exact recipe review');
    await tab.playwright.locator('#builder-dry-run').click();await snapshot();
    check('dry-run distinct from GPU preflight',(await tab.playwright.locator('#builder-check-status').textContent()).includes('preflight still required'));
    await tab.playwright.locator('#training-preflight').click();await snapshot();
    check('fixture preflight denied',(await tab.playwright.locator('#training-result').textContent()).includes('UI fixture: execution'));
    await tab.playwright.locator('#builder-next').click();await snapshot();
    check('GPU launch blocked after denied preflight',!(await tab.playwright.locator('#training-start').isEnabled()));
    await navigate('settings');await tab.playwright.locator('#language-select').selectOption('ko');await snapshot();await navigate('recipes');
    check('language redraw retains name',await tab.playwright.locator('#recipe-form input[name=name]').getAttribute('value')==='instruction-lora-review' || await tab.playwright.evaluate(()=>document.querySelector('#recipe-form input[name=name]').value)==='instruction-lora-review');
    check('language redraw retains learning rate',await tab.playwright.evaluate(()=>document.querySelector('#recipe-form input[name=learning_rate]').value)==='0.00015');
    check('Korean builder rendered',(await snapshot()).includes('하이퍼파라미터'));
    await navigate('overview');await select('train-000000000001');await tab.playwright.locator('[data-tab=logs]').click();
    await capture('after-workspace-ko-1440','Korean selected-run workspace');
    await navigate('settings');await tab.playwright.locator('#language-select').selectOption('en');await snapshot();await navigate('overview');await select('train-000000000001');
    for(const viewportSize of [{width:1366,height:768},{width:1024,height:768},{width:390,height:844}]){
      size=viewportSize;await viewport.set(size);await snapshot();
      const geometry=await tab.playwright.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,curve:document.querySelector('#loss-chart').getBoundingClientRect().height}));
      check(size.width+' no page horizontal overflow',geometry.scroll<=geometry.width+1);check(size.width+' curve nonempty',geometry.curve>80);
      await capture('after-workspace-'+size.width,'selected run responsive layout');
    }
    await tab.playwright.locator('.mobile-surfaces button[data-surface=inspector]').click();await snapshot();
    check('mobile inspector exposed',await tab.playwright.locator('#run-inspector').isVisible());
    await capture('after-inspector-390','mobile inspector and immutable config');
    await tab.playwright.locator('.mobile-surfaces button[data-surface=console]').click();await tab.playwright.locator('[data-tab=logs]').press('ArrowRight');await snapshot();
    check('console keyboard arrows',await tab.playwright.locator('[data-tab=checkpoints]').getAttribute('aria-selected')==='true');
    await tab.playwright.locator('[data-tab=checkpoints]').press('End');await snapshot();
    check('console keyboard End',await tab.playwright.locator('[data-tab=configuration]').getAttribute('aria-selected')==='true');
    await capture('after-console-390','mobile console tabs');
    await navigate('recipes');await tab.playwright.locator('[data-builder-step="4"]').click();await snapshot();await tab.playwright.locator('#workspace-view').press('Control+Home');
    await capture('after-builder-review-390','mobile draft remains intact');
    size={width:720,height:450};await viewport.set(size);await navigate('overview');
    check('200 percent equivalent reflow',await tab.playwright.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
    report.zoom_scope='720x450 CSS viewport reflow; native browser zoom not claimed';
    size={width:1440,height:900};await viewport.set(size);
    await tab.goto('http://127.0.0.1:18765/__fixture__/empty');await snapshot();
    check('empty run creation path',await tab.playwright.locator('#empty-new').isVisible());await capture('after-empty-1440','empty fixture with builder entry');
    await tab.goto('http://127.0.0.1:18765/__fixture__/stale');await snapshot();
    check('offline/stale is explicit',(await tab.playwright.locator('#connection').textContent()).includes('stale'));
    await tab.goto('http://127.0.0.1:18765/');await snapshot();
    report.console=await tab.dev.logs({levels:['error','warn'],limit:100});
    report.console=report.console.filter(entry=>entry.timestamp>=report.started_at);
    report.expected_console_patterns=['404 avatar fixture','503 Hub unavailable fixture','409 denied preflight fixture','503 API stale fixture'];
    const unexpected=report.console.filter(entry=>!/Failed to load resource.*(?:404|409|503)|(?:404|409|503).*Failed to load resource/.test(entry.message));
    check('no unexpected browser errors',unexpected.length===0);
    report.status='PASS';
  }catch(error){report.status='FAIL';report.error=String(error.message);throw error;}
  finally{report.completed_at=new Date().toISOString();await fs.writeFile(directory+'/browser-report.json',JSON.stringify(report,null,2)+'\n');}
  return {status:report.status,checks:report.checks.length,captures:report.captures.length};
}
