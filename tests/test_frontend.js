// DOM-stub rendering/handler tests, not a browser or pixel/layout test.
// Run with node tests/test_frontend.js. No npm dependencies.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const fixture = JSON.parse(fs.readFileSync('docs/sample-snapshot.json','utf8'));
class Element {
  constructor(dataset = {}) { this.dataset=dataset; this.innerHTML=''; this.textContent=''; this.hidden=false; this.style={}; this.disabled=false; this.value=''; this.scrollTop=0; this.scrollHeight=100; this.clientHeight=100; this.listeners={}; this.attributes={}; this.classes=new Set(); this.classList={toggle:(k,v)=>{if(v===undefined)v=!this.classes.has(k);v?this.classes.add(k):this.classes.delete(k);}}; }
  addEventListener(event,fn){this.listeners[event]=fn;}
  setAttribute(key,value){this.attributes[key]=value;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  scrollIntoView(){}
  getBoundingClientRect(){return {left:0,top:0,right:100,bottom:100};}
  querySelectorAll(){return [];}
  querySelector(selector){return get('#stub '+selector);}
  reset(){this.testData={};}
}
function checkMarkupNesting(html){const stack=[];const voids=new Set(['input','br','hr','img','meta','link','source','wbr']);for(const match of html.matchAll(/<\/?([a-z][a-z0-9-]*)\b[^>]*>/gi)){const tag=match[1].toLowerCase(),token=match[0];if(token.startsWith('</'))assert.equal(stack.pop(),tag,'markup nesting');else if(!voids.has(tag)&&!token.endsWith('/>'))stack.push(tag);}assert.deepEqual(stack,[],'unclosed markup');}
const nodes=new Map(), get=(s)=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};
const groups={'.filter':['all','LLM','VLM'].map(filter=>new Element({filter})),'.tab':['logs','checkpoints','configuration'].map(tab=>new Element({tab})),'.nav-item':['overview','runs','worker'].map(nav=>new Element({nav}))};
let calls=[], failure=null, mutation=null, routeResponses={};
const storedPreferences = new Map();
const document={hidden:false,querySelector:get,querySelectorAll:s=>{
  if(groups[s])return groups[s];
  if(s==='#runs-body tr[data-run]') return [...get('#runs-body').innerHTML.matchAll(/data-run="([^"]+)"/g)].map(m=>new Element({run:m[1]}));
  if(s==='#run-controls button') return [...get('#run-controls').innerHTML.matchAll(/data-action="([^"]+)"/g)].map(m=>new Element({action:m[1]}));
  return [];
},addEventListener(){}};
const ctx=vm.createContext({document,console,Date,JSON,Math,Number,String,Object,Array,Promise,AbortController,encodeURIComponent,localStorage:{getItem:key=>storedPreferences.get(key)||null,setItem:(key,value)=>storedPreferences.set(key,value)},setInterval(){},setTimeout(){return 1;},clearTimeout(){},FormData:class{constructor(form){return Object.entries(form.testData||{});}},fetch:async(path,options)=>{calls.push({path,options});if(failure)throw new Error(failure);return {ok:true,json:async()=>routeResponses[path] || (options.method==='POST' ? (mutation||{run:fixture.runs[0],snapshot:fixture}) : structuredClone(fixture))};}});
vm.runInContext(fs.readFileSync('static/theme.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('static/i18n.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx), flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  let tests=0;
  await flush();
  assert.equal(get('#summary-total').textContent,4);assert.match(get('#runs-body').innerHTML,/running/);assert.match(get('#runs-body').innerHTML,/LLM/);assert.equal((get('#runs-body').innerHTML.match(/<tr /g)||[]).length,4);assert.match(get('#loss-chart').innerHTML,/<svg/);assert.equal(get('#run-error').hidden,true);tests++;
  run("nav='runs';filter='VLM';render()");assert.match(get('#runs-body').innerHTML,/VLM/);assert.equal((get('#runs-body').innerHTML.match(/<tr /g)||[]).length,2);tests++;
  run("filter='all';selectRun(snapshot.runs.find(r=>r.status==='failed').id)");assert.equal(get('#run-error').hidden,false);assert.match(get('#run-controls').innerHTML,/Retry/);tests++;
  run("currentTab='checkpoints';selectRun(snapshot.runs.find(r=>r.status==='completed').id)");assert.match(get('#tab-content').innerHTML,/Virtual checkpoint/);assert.match(get('#tab-content').innerHTML,/no weights saved/);tests++;
  run("currentTab='configuration';render()");assert.match(get('#tab-content').innerHTML,/learning rate/);tests++;
  run("snapshot.runs[0].name='<img src=x onerror=evil()>';selectRun(snapshot.runs[0].id)");assert.ok(!get('#runs-body').innerHTML.includes('<img src=x'));assert.match(get('#runs-body').innerHTML,/&lt;img/);tests++;
  assert.equal(run("chart([],120)"),'<div class="chart-empty">Learning curves appear after a demo run starts</div>');assert.ok(!run("chart([{step:0,loss:NaN,eval_loss:null}],100)").includes('NaN'));tests++;
  run("setNav('environment')");assert.equal(get('#workspace-view').hidden,false);assert.equal(get('#run-detail').hidden,true);run("setNav('overview')");assert.equal(get('#run-detail').hidden,false);tests++;
  get('#new-run').onclick();assert.equal(get('#workspace-view').hidden,false);run('openDialog()');assert.equal(get('#run-dialog').open,true);get('#cancel-dialog').onclick();assert.equal(get('#run-dialog').open,false);tests++;
  get('#run-form select[name="kind"]').onchange({target:{value:'VLM'}});assert.equal(get('#run-form select[name="model"]').value,'demo/vlm-3b');assert.equal(get('#run-form input[name="dataset"]').value,'synthetic-image-captions');tests++;
  const before=calls.length;const p1=run("performAction(snapshot.runs[0].id,'pause')"),p2=run("performAction(snapshot.runs[0].id,'pause')");await Promise.all([p1,p2]);assert.equal(calls.filter(c=>c.path.endsWith('/pause')).length,1);assert.ok(calls.length>before);tests++;
  failure='offline';await run('refresh()');assert.match(get('#connection').innerHTML,/stale/);tests++;
  failure=null;
  const form=get('#run-form');form.testData={name:'front-end-demo',kind:'LLM',model:'demo/llm-3b',dataset:'synthetic',learning_rate:'0.0002',batch_size:'1',lora_rank:'16',epochs:'3',gradient_accumulation:'8',max_steps:'300',failure_mode:'none'};
  await form.listeners.submit({preventDefault(){},target:form});const created=calls.find(c=>c.path==='/api/runs');const body=JSON.parse(created.options.body);assert.equal(body.max_steps,300);assert.equal(typeof body.learning_rate,'number');assert.equal(get('#run-dialog').open,false);tests++;
  failure='rejected';await form.listeners.submit({preventDefault(){},target:form});assert.equal(get('#form-error').hidden,false);assert.equal(get('#form-error').textContent,'rejected');tests++;
  failure=null;
  vm.runInContext(fs.readFileSync('static/workspace.js','utf8'),ctx);
  for(const file of ['huggingface','training','builder'])vm.runInContext(fs.readFileSync('static/'+file+'.js','utf8'),ctx);
  await flush();
  run("renderDatasets({datasets:[{id:'dataset-0001',name:'<img onerror=x>',kind:'LLM',count:3}]})");assert.match(get('#workspace-view').innerHTML,/Validate &amp; save/);assert.match(get('#workspace-view').innerHTML,/&lt;img/);assert.match(get('#workspace-view').innerHTML,/Export validation/);tests++;
  get('#dataset-form').testData={name:'stub-data',kind:'LLM',text:'{\"instruction\":\"Hi\",\"output\":\"Hello\"}'};routeResponses['/api/datasets/validate']={valid:true,count:1,errors:[],warnings:[],preview:[{line:1,record:{instruction:'Hi',output:'Hello'}}]};await run('submitDataset(false)');assert.match(get('#dataset-result').innerHTML,/validation passed/);tests++;
  run("renderRecipes({presets:[]})");checkMarkupNesting(get('#workspace-view').innerHTML);assert.match(get('#workspace-view').innerHTML,/GPU training controls/);assert.match(get('#workspace-view').innerHTML,/Dry-run checks/);tests++;
  run("renderDryRun({valid:true,estimated_memory_gb:6.1,assumed_vram_gb:12,warnings:[{message:'Fit is not guaranteed'}]})");assert.match(get('#recipe-result').innerHTML,/6.1/);assert.match(get('#recipe-result').innerHTML,/Fit is not guaranteed/);tests++;
  run("snapshot=OFFLINE_TEST_SNAPSHOT;renderCompare()".replace('OFFLINE_TEST_SNAPSHOT',JSON.stringify(fixture)));get('#compare-a').value=fixture.runs[0].id;get('#compare-b').value=fixture.runs[1].id;run('updateComparison()');assert.match(get('#compare-output').innerHTML,/Export A/);assert.match(get('#compare-output').innerHTML,/<svg/);tests++;
  run("renderEnvironment({python:{version:'3.12'},os:{name:'Linux'},disk:{free_bytes:10737418240},gpu:{detected:false,message:'GPU missing'},warnings:[]})");assert.match(get('#workspace-view').innerHTML,/10.0 GB/);assert.match(get('#workspace-view').innerHTML,/Not detected/);assert.match(get('#workspace-view').innerHTML,/does not guarantee model compatibility/);tests++;
  run("renderSettings({authenticated:false,must_change_password:true,local_peer:true,settings:{configured:{lan_access:true,remote_view:true,remote_control:true},effective:{lan_access:false},bootstrap_required:true}})");assert.match(get('#workspace-view').innerHTML,/LAN is locked/);assert.match(get('#workspace-view').innerHTML,/Sign in locally/);tests++;
  run("renderSettings({authenticated:true,username:'admin',must_change_password:true,local_peer:true,settings:{configured:{lan_access:true,remote_view:true,remote_control:true},effective:{lan_access:false,remote_view:false,remote_control:false},bootstrap_required:true}})");assert.match(get('#workspace-view').innerHTML,/Configured: ON · Effective: OFF/);assert.match(get('#workspace-view').innerHTML,/Change password/);assert.match(get('#workspace-view').innerHTML,/disabled/);tests++;
  run("renderSettings({authenticated:true,username:'admin',must_change_password:false,local_peer:true,settings:{configured:{lan_access:true,remote_view:true,remote_control:true},effective:{lan_access:false,remote_view:false,remote_control:false},bootstrap_required:false,listener_lan:false,tls:false}})");checkMarkupNesting(get('#workspace-view').innerHTML);assert.match(get('#workspace-view').innerHTML,/PASSWORD GATE COMPLETE/);assert.match(get('#workspace-view').innerHTML,/loopback only/);tests++;
  assert.match(get('#workspace-view').innerHTML,/PASSWORD GATE COMPLETE/);run("renderDatasets({datasets:[]})");checkMarkupNesting(get('#workspace-view').innerHTML);assert.match(get('#workspace-view').innerHTML,/CSV, Parquet, JSON arrays and ZIP are not supported/);assert.match(get('#workspace-view').innerHTML,/Download VLM JSONL/);tests++;
  assert.match(run("describeIssue({line:2,field:'messages[0].content',code:'invalid_record',message:'Missing text'})"),/Line 2 · messages/);tests++;
  const redacted=run("safeTechnicalText('password=synthetic-secret hf_abcdefghijklmnop')");assert.ok(!redacted.includes('synthetic-secret'));assert.ok(!redacted.includes('hf_abcdefghijklmnop'));assert.match(redacted,/REDACTED/);tests++;
  const advice=run("actionableErrorHtml({code:'weak_password',message:'Use a stronger password'},'Authentication')");assert.match(advice,/Next step/);assert.match(advice,/Technical details/);assert.match(advice,/weak_password/);tests++;
  const badFileTarget={files:[{name:'data.parquet',size:20,text(){throw Error('must not read unsupported file');}}],value:'selected'};await get('#dataset-file').onchange({target:badFileTarget});assert.equal(badFileTarget.value,'');assert.match(get('#toast').textContent,/unsupported file type/);tests++;
  const chatRows=run('chatSample()').trim().split('\n').map(JSON.parse);assert.equal(chatRows.length,3);assert.ok(chatRows.every(row=>row.messages.length===2));const instructionRows=run('instructionSample()').trim().split('\n').map(JSON.parse);assert.ok(instructionRows.every(row=>row.instruction&&row.output));tests++;
  run("I18n.setLanguage('ko');renderDatasets({datasets:[{id:'dataset-user',name:'Overview',kind:'LLM',count:3}]})");assert.match(get('#workspace-view').innerHTML,/검증 후 저장/);assert.match(get('#workspace-view').innerHTML,/Overview/);assert.equal(storedPreferences.get('forge.language'),'ko');tests++;
  const statusBeforeLocaleRender = run('snapshot.runs[0].status');run("snapshot.runs[0].name='Overview';nav='runs';filter='all';selectRun(snapshot.runs[0].id)");assert.match(get('#runs-body').innerHTML,/Overview/);assert.match(get('#runs-body').innerHTML,/실행 중/);assert.equal(run('snapshot.runs[0].status'),statusBeforeLocaleRender);tests++;
  run("renderRecipes({presets:[]})");checkMarkupNesting(get('#workspace-view').innerHTML);assert.match(get('#workspace-view').innerHTML,/실행 전 검증/);assert.equal(run("defaultRecipe().method"),'qlora');tests++;
  run("renderSettings({authenticated:false,settings:{}})");checkMarkupNesting(get('#workspace-view').innerHTML);assert.match(get('#workspace-view').innerHTML,/표시 언어/);assert.match(get('#workspace-view').innerHTML,/<option value="ko" selected>한국어/);tests++;
  assert.equal(run("jsonPreview({name:'Overview',messages:[{role:'user',content:'Training setup'}]})"),'<pre class="preview-record">'+JSON.stringify({name:'Overview',messages:[{role:'user',content:'Training setup'}]},null,2).replaceAll('"','&quot;')+'</pre>');tests++;
  run("I18n.setLanguage('en');renderSettings({authenticated:false,settings:{}})");assert.match(get('#workspace-view').innerHTML,/Display language/);assert.match(get('#workspace-view').innerHTML,/<option value="en" selected>English/);assert.equal(storedPreferences.get('forge.language'),'en');tests++;
  run("renderDetail({...snapshot.runs[0],simulated:false,allowed_actions:['pause','cancel'],checkpoints:[{name:'checkpoint-000010',step:10,virtual:false,size_mb:2}]})");assert.match(get('#run-controls').innerHTML,/Checkpoint & pause/);assert.ok(!get('#chart-context').textContent.includes('simulated'));tests++;
  run("currentTab='evaluation';renderDetail({...snapshot.runs[0],simulated:false,evaluation:{baseline_eval_loss:3,eval_loss:2,generated_response:'<img src=x onerror=evil()>',reference:'Synthetic'}})");assert.match(get('#tab-content').innerHTML,/Held-out evaluation/);assert.ok(!get('#tab-content').innerHTML.includes('<img src=x'));tests++;
  // Workbench surfaces always refer to the selected run, including read-only configuration and exports.
  run("nav='runs';currentTab='configuration';selectRun(snapshot.runs[0].id)");assert.equal(get('#run-source').textContent,'Demo');assert.match(get('#inspector-config').innerHTML,/model/);assert.ok(get('#run-export-json').href.includes(run('selectedId')));tests++;
  run("snapshot.ui_fixture={id:'test'};renderDetail({...snapshot.runs[0],simulated:false,status:'pausing',allowed_actions:[]})");assert.equal(get('#run-state').textContent,'pausing');assert.match(get('#run-source').textContent,/Real GPU.*UI fixture/);assert.ok(!get('#run-controls').innerHTML.includes('data-action'));assert.match(get('#chart-context').textContent,/UI fixture/);tests++;
  run("snapshot.runs=[];render()");assert.equal(get('#workbench-empty').hidden,false);assert.equal(get('#run-detail').hidden,true);run('snapshot='+JSON.stringify(fixture));tests++;
  const gap=run("chart([{step:1,loss:3,eval_loss:null},{step:2,loss:null,eval_loss:null},{step:4,loss:2,eval_loss:2.1}],10,false)");assert.match(gap,/d="M[^"]+ M/);assert.ok(!gap.includes('NaN'));assert.ok(!gap.includes('undefined'));tests++;
  // Gate both launch routes on the exact reviewed config and prevent duplicate writes.
  const reviewed={name:'reviewed-run',kind:'LLM',model:'fixture/model',dataset:'dataset-fixture',method:'lora',learning_rate:'0.00015',batch_size:'1',gradient_accumulation:'8',lora_rank:'16',sequence_length:'512',epochs:'3',max_steps:'120',failure_mode:'none'};
  get('#recipe-form').testData=reviewed;get('#assumed-vram').value='12';
  run("nav='recipes';builderState.source='real';builderState.cap={available:true};builderState.datasets=[{id:'dataset-fixture',kind:'LLM',split:{warnings:[]}}];installedTrainingModels=[{id:'fixture/model',kind:'LLM',installed:true,training_candidate:true}];selectedHubModel=null;builderState.busy=false;builderState.drySignature=null;builderState.preflightSignature=null;remoteControlsAllowed=true");
  assert.equal(run("builderLaunchReady('real')"),false);run('builderState.drySignature=builderSignature()');assert.equal(run("builderLaunchReady('real')"),false);tests++;
  routeResponses['/api/training/preflight']={valid:true,can_train:true};await run("runBuilderCheck('preflight')");assert.equal(run("builderLaunchReady('real')"),true);tests++;
  run('remoteControlsAllowed=false');assert.equal(run("builderLaunchReady('real')"),false);run('remoteControlsAllowed=true');tests++;
  run('installedTrainingModels[0].training_candidate=false');assert.equal(run("builderLaunchReady('real')"),false);run('installedTrainingModels[0].training_candidate=true');tests++;
  const launchesBefore=calls.filter(c=>c.path==='/api/training/runs').length;
  await Promise.all([run("launchBuilder('real')"),run("launchBuilder('real')")]);
  const realCalls=calls.filter(c=>c.path==='/api/training/runs');assert.equal(realCalls.length,launchesBefore+1);
  const realConfig=JSON.parse(realCalls.at(-1).options.body);assert.equal(realConfig.dataset,'dataset-fixture');assert.equal(realConfig.model,'fixture/model');assert.equal(realConfig.learning_rate,0.00015);assert.equal(realConfig.batch_size,1);assert.equal(realConfig.seed,42);assert.ok(!('source' in realConfig));tests++;
  run("nav='recipes';builderState.drySignature=builderSignature();builderState.preflightSignature=builderSignature()");get('#recipe-form').testData.learning_rate='0.0002';run('invalidateBuilderChecks()');assert.equal(run("builderLaunchReady('real')"),false);const staleCalls=calls.length;await run("launchBuilder('real')");assert.equal(calls.length,staleCalls);tests++;
  run("builderState.source='demo';builderState.drySignature=builderSignature()");assert.equal(run("builderLaunchReady('demo')"),true);assert.equal(run("builderLaunchReady('real')"),false);tests++;
  const demoBefore=calls.filter(c=>c.path==='/api/runs').length;await run("launchBuilder('demo')");assert.equal(calls.filter(c=>c.path==='/api/runs').length,demoBefore+1);tests++;
  run("nav='recipes';builderState.source='real';builderState.drySignature=builderSignature();builderState.preflightSignature=null");failure='preflight rejected';await run("runBuilderCheck('preflight')");assert.equal(run('builderState.preflightSignature'),null);assert.equal(run("builderLaunchReady('real')"),false);failure=null;tests++;
  run("builderState.datasets[0].split.warnings=[{code:'duplicate_leakage_risk'}]");assert.equal(run('builderDatasetReady(readRecipe())'),false);tests++;
  run("I18n.setLanguage('ko')");assert.equal(run("t('Review the experiment')"),'실험 검토');assert.match(run("t('points · measured-source UI fixture')"),/픽스처/);run("I18n.setLanguage('en')");tests++;
  // Hub account rejection must not be confused with dashboard session expiry.
  run("fetch=async()=>({ok:false,status:401,json:async()=>({error:{code:'hf_auth_required',message:'Connect a valid token'}})})");
  get('#login-dialog').open=false;
  await assert.rejects(run("api('/api/huggingface/connect',{token:'hf_synthetic'})"));assert.equal(get('#login-dialog').open,false);tests++;
  run("fetch=async()=>({ok:false,status:401,json:async()=>({error:{code:'authentication_required',message:'Sign in'}})})");
  await assert.rejects(run("api('/api/status')"));assert.equal(get('#login-dialog').open,true);tests++;
  run("snapshot=null;clearRunSurfaces();setNav('runs')");assert.equal(get('#run-detail').hidden,true);assert.equal(get('#inspector-config').innerHTML,'');assert.equal(get('#mobile-run').innerHTML,'');tests++;
  // Font-ready redraw touches only charts, preserving an in-progress form/log scroll.
  run("snapshot="+JSON.stringify(fixture)+";selectedId=snapshot.runs[0].id;nav='recipes'");
  get('#recipe-form').testData={name:'unsaved typography draft'};get('.log-view').scrollTop=37;
  const fontCalls=calls.length, formHtml=get('#workspace-view').innerHTML, tabHtml=get('#tab-content').innerHTML;
  run('redrawTypographyCharts()');assert.equal(get('#workspace-view').innerHTML,formHtml);assert.equal(get('#tab-content').innerHTML,tabHtml);assert.equal(get('.log-view').scrollTop,37);assert.equal(get('#recipe-form').testData.name,'unsaved typography draft');assert.equal(calls.length,fontCalls);tests++;
  // The newly styled model/step subtitle still escapes server-supplied identifiers.
  run("snapshot.runs[0].config.model='<img src=x onerror=evil()>';snapshot.runs[0].kind='<svg onload=evil()>';renderDetail(snapshot.runs[0])");
  assert.ok(!get('#selected-subtitle').innerHTML.includes('<img'));assert.match(get('#selected-subtitle').innerHTML,/&lt;img/);assert.match(get('#selected-subtitle').innerHTML,/&lt;svg/);tests++;
  console.log(`${tests} frontend DOM-stub tests passed (browser layout/integration not covered)`);
})().catch(error=>{console.error(error);process.exitCode=1;});
