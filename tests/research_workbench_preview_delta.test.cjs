'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const ui=require('../demos/task-center-digital-twin/research-workbench/workbench.js');
const pending=[];let refresh,updates=[];
const app={innerHTML:'',addEventListener(){},contains(){return true;}};
const window={XuanjunResearchWorkbench:{mount(el,opts){refresh=opts.onRefresh;const m=ui.mount(el,opts);return {update(...a){updates.push(a);m.update(...a);}};}},XuanjunPublicProjection:{mount(){return {refresh(){}};}}};
const context={window,document:{baseURI:'https://example.test/task-center-test/research-workbench/',getElementById(id){return id==='app'?app:{};}},URL,Promise,fetch(url,options){return new Promise(resolve=>pending.push({url,options,resolve}));}};
const data={mode:'TEST_ONLY',tenant_id:'t',tasks:[{board_id:'research-development',project_id:'p',task_id:'task-one'}],anomalies:[]};
const twin={mode:'TEST_ONLY',tenant_id:'t',records:{tasks:[],ai_instances:[],evidence:[]}};
const ledger={mode:'TEST_ONLY',ledger_state:'AVAILABLE_METADATA_ONLY',tasks:[{task_id:'task-one',handoffs:[{version:2,outgoing:'<out>',receiving:'in',supervisor:'review'}]}],observations:{development_handoff:{repository:'repo',branch:'branch',entry:'entry',next_action:'breakpoint',records:[{phase:'交出',role:'dev',commit:'sha',message_ref:'ref'}]}}};
const respond=(p,status,body)=>p.resolve({ok:status===200,status,json:()=>Promise.resolve(body)}),tick=()=>new Promise(r=>setImmediate(r));
function batch(start,a,b,c){respond(pending[start],...a);respond(pending[start+1],...b);respond(pending[start+2],...c);}
(async()=>{vm.runInNewContext(fs.readFileSync('demos/task-center-digital-twin/research-workbench/preview.js','utf8'),context);assert.equal(pending.length,3);assert(pending[2].url.endsWith('/task-center-test/api/admin/delivery-ledger'));assert.equal(pending[2].options.credentials,'same-origin');batch(0,[200,data],[200,twin],[200,ledger]);await tick();assert.match(app.innerHTML,/breakpoint/);assert.match(app.innerHTML,/&lt;out&gt;/);assert.match(app.innerHTML,/现时权限 UNKNOWN/);assert.match(ui.render(data,ui.parseRoute('#task/research-development/task-one'),twin,ledger),/review/);assert.doesNotMatch(ui.render(data,ui.parseRoute('#task/research-development/other'),twin,ledger),/breakpoint/);
 refresh();assert.doesNotMatch(app.innerHTML,/breakpoint/);batch(3,[200,data],[403,{}],[403,{}]);await tick();assert.match(app.innerHTML,/无权查看/);assert.doesNotMatch(app.innerHTML,/breakpoint/);
 refresh();batch(6,[200,data],[200,twin],[200,{...ledger,tenant_id:'other'}]);await tick();assert.doesNotMatch(app.innerHTML,/breakpoint/);assert.match(app.innerHTML,/无权查看/);
 refresh();batch(9,[200,data],[200,twin],[503,{}]);await tick();assert.match(app.innerHTML,/无权查看/);
 refresh();refresh();batch(15,[200,data],[200,twin],[200,ledger]);await tick();let n=updates.length;batch(12,[401,{}],[403,{}],[403,{}]);await tick();assert.equal(updates.length,n);assert.match(app.innerHTML,/breakpoint/);
 refresh();batch(18,[401,{}],[403,{}],[200,ledger]);await tick();assert.doesNotMatch(app.innerHTML,/breakpoint/);console.log('preview observation delta passed');})().catch(e=>{console.error(e);process.exitCode=1;});
