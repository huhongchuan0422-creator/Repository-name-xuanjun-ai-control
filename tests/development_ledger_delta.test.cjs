'use strict';
const assert=require('assert');
const ui=require('../demos/task-center-digital-twin/app.js');
const route=ui.parseRoute('#board/research-development');
const data={mode:'TEST_ONLY',tasks:[{task_id:'dev-1',board_id:'research-development',project_id:'p',state:'READY'},{task_id:'other',board_id:'finance',project_id:'q'}],boards:[],anomalies:[]};
const ledger={mode:'TEST_ONLY',ledger_state:'AVAILABLE_METADATA_ONLY',source_trust:'UNAVAILABLE',writer_verification:'UNKNOWN',tasks:[{task_id:'dev-1',state:'RUNNING',validity:'HISTORICAL',handoffs:[{status:'有缺项',version:2,outgoing:'<unsafe>',receiving:'UNKNOWN',supervisor:'UNAVAILABLE'}]},{task_id:'other',state:'SECRET_OTHER',handoffs:[]}]};
(async()=>{
 let called=[];const result=await ui.loadDevelopmentLedger((url,opts)=>{called.push([url,opts]);return Promise.resolve({ok:true,json:()=>Promise.resolve(ledger)});});
 assert.strictEqual(result,ledger);assert.strictEqual(called[0][0],'api/admin/delivery-ledger');assert.strictEqual(called[0][1].credentials,'same-origin');
 const html=ui.render(data,route,null,result);assert.match(html,/任务与三方交接资料/);assert.match(html,/有缺项/);assert.match(html,/&lt;unsafe&gt;/);assert.doesNotMatch(html,/SECRET_OTHER|<unsafe>/);assert.match(html,/不构成实际接件/);
 assert.match(html,/研发任务中心事实/);assert.match(html,/三方交接未从此来源确认/);assert.match(html,/接件记录时间 UNKNOWN/);
 assert.match(ui.render(data,route,null,null),/台账不可用或无权访问/);
 assert.match(ui.render(data,route,null,{...ledger,ledger_state:'UNAVAILABLE'}),/台账不可用；不代表没有任务/);
 assert.doesNotMatch(ui.render(data,ui.parseRoute('#overview'),null,ledger),/任务与三方交接资料/);
 await assert.rejects(ui.loadDevelopmentLedger(()=>Promise.resolve({ok:false,status:403})),/LEDGER_HTTP_403/);
 await assert.rejects(ui.loadDevelopmentLedger(()=>Promise.resolve({ok:true,json:()=>Promise.resolve({mode:'PRODUCTION',tasks:[]})})),/LEDGER_PROJECTION_MISMATCH/);
 // Exercise the real boot path: actual endpoint names, async paint and board-only scope.
 const app={innerHTML:'',querySelectorAll:()=>[]},mode={textContent:''},home={};
 const doc={getElementById:(id)=>({app:app,dataMode:mode,home:home})[id]||null};
 const requests=[];const win={location:{protocol:'https:',hash:'#board/research-development'},addEventListener:()=>{},fetch:(url)=>{requests.push(url);if(url==='api/projection')return Promise.resolve({ok:true,json:()=>Promise.resolve({...data,tenant_id:'tenant-test'})});if(url==='api/admin/delivery-ledger')return Promise.resolve({ok:true,json:()=>Promise.resolve(ledger)});return Promise.resolve({ok:false,status:403});}};
 ui.boot(doc,win,null);await new Promise(resolve=>setTimeout(resolve,10));
 assert.deepStrictEqual(requests.sort(),['api/admin/delivery-ledger','api/admin/digital-twin','api/projection'].sort());assert.match(app.innerHTML,/有缺项/);assert.match(app.innerHTML,/来源信任 UNAVAILABLE/);
 console.log('development_ledger_delta: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
