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
}
const nodes=new Map(), get=(s)=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};
const groups={'.filter':['all','LLM','VLM'].map(filter=>new Element({filter})),'.tab':['logs','checkpoints','configuration'].map(tab=>new Element({tab})),'.nav-item':['overview','runs','worker'].map(nav=>new Element({nav}))};
let calls=[], failure=null, mutation=null;
const document={hidden:false,querySelector:get,querySelectorAll:s=>{
  if(groups[s])return groups[s];
  if(s==='#runs-body tr[data-run]') return [...get('#runs-body').innerHTML.matchAll(/data-run="([^"]+)"/g)].map(m=>new Element({run:m[1]}));
  if(s==='#run-controls button') return [...get('#run-controls').innerHTML.matchAll(/data-action="([^"]+)"/g)].map(m=>new Element({action:m[1]}));
  return [];
},addEventListener(){}};
const ctx=vm.createContext({document,console,Date,JSON,Math,Number,String,Object,Array,Promise,AbortController,encodeURIComponent,localStorage:{getItem:()=>null,setItem(){}},setInterval(){},setTimeout(){return 1;},clearTimeout(){},FormData:class{constructor(form){return Object.entries(form.testData);}},fetch:async(path,options)=>{calls.push({path,options});if(failure)throw new Error(failure);return {ok:true,json:async()=>options.method==='POST' ? (mutation||{run:fixture.runs[0],snapshot:fixture}) : structuredClone(fixture)};}});
vm.runInContext(fs.readFileSync('static/app.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx), flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  let tests=0;
  await flush();
  assert.equal(get('#summary-total').textContent,4);assert.match(get('#runs-body').innerHTML,/running/);assert.match(get('#runs-body').innerHTML,/VLM/);assert.match(get('#loss-chart').innerHTML,/<svg/);assert.equal(get('#run-error').hidden,true);tests++;
  run("filter='VLM';render()");assert.match(get('#runs-body').innerHTML,/VLM/);assert.equal((get('#runs-body').innerHTML.match(/<tr /g)||[]).length,2);tests++;
  run("filter='all';selectRun(snapshot.runs.find(r=>r.status==='failed').id)");assert.equal(get('#run-error').hidden,false);assert.match(get('#run-controls').innerHTML,/Retry/);tests++;
  run("currentTab='checkpoints';selectRun(snapshot.runs.find(r=>r.status==='completed').id)");assert.match(get('#tab-content').innerHTML,/Virtual checkpoint/);assert.match(get('#tab-content').innerHTML,/no weights saved/);tests++;
  run("currentTab='configuration';render()");assert.match(get('#tab-content').innerHTML,/learning rate/);tests++;
  run("snapshot.runs[0].name='<img src=x onerror=evil()>';selectRun(snapshot.runs[0].id)");assert.ok(!get('#runs-body').innerHTML.includes('<img src=x'));assert.match(get('#runs-body').innerHTML,/&lt;img/);tests++;
  assert.equal(run("chart([],120)"),'<div class="chart-empty">Learning curves appear after a demo run starts</div>');assert.ok(!run("chart([{step:0,loss:NaN,eval_loss:null}],100)").includes('NaN'));tests++;
  run("setNav('worker')");assert.equal(get('#worker-info').hidden,false);assert.equal(get('#run-detail').hidden,true);run("setNav('overview')");assert.equal(get('#run-detail').hidden,false);tests++;
  get('#new-run').onclick();assert.equal(get('#run-dialog').open,true);get('#cancel-dialog').onclick();assert.equal(get('#run-dialog').open,false);tests++;
  get('#run-form select[name="kind"]').onchange({target:{value:'VLM'}});assert.equal(get('#run-form select[name="model"]').value,'demo/vlm-3b');assert.equal(get('#run-form input[name="dataset"]').value,'synthetic-image-captions');tests++;
  const before=calls.length;const p1=run("performAction(snapshot.runs[0].id,'pause')"),p2=run("performAction(snapshot.runs[0].id,'pause')");await Promise.all([p1,p2]);assert.equal(calls.filter(c=>c.path.endsWith('/pause')).length,1);assert.ok(calls.length>before);tests++;
  failure='offline';await run('refresh()');assert.match(get('#connection').innerHTML,/stale/);tests++;
  failure=null;
  const form=get('#run-form');form.testData={name:'front-end-demo',kind:'LLM',model:'demo/llm-3b',dataset:'synthetic',learning_rate:'0.0002',batch_size:'1',lora_rank:'16',epochs:'3',gradient_accumulation:'8',max_steps:'300',failure_mode:'none'};
  await form.listeners.submit({preventDefault(){},target:form});const created=calls.find(c=>c.path==='/api/runs');const body=JSON.parse(created.options.body);assert.equal(body.max_steps,300);assert.equal(typeof body.learning_rate,'number');assert.equal(get('#run-dialog').open,false);tests++;
  failure='rejected';await form.listeners.submit({preventDefault(){},target:form});assert.equal(get('#form-error').hidden,false);assert.equal(get('#form-error').textContent,'rejected');tests++;
  console.log(`${tests} frontend DOM-stub tests passed (browser layout/integration not covered)`);
})().catch(error=>{console.error(error);process.exitCode=1;});
