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
 assert.doesNotMatch(html.replace(/<[^>]*>/g,''),/TEST_ONLY|UNKNOWN|UNAVAILABLE|Writer|READY|RUNNING/);assert.match(html,/资料来源和负责身份尚未核实/);assert.match(html,/<option value="READY">待开始<\/option>/);assert.match(html,/历史资料/);assert.match(html,/尚未确认/);
 assert.match(html,/研发任务中心事实/);assert.match(html,/三方交接未从此来源确认/);assert.match(html,/接件记录时间 尚未确认/);
 assert.match(ui.render(data,route,null,null),/台账暂不可用或无权查看/);
 assert.match(ui.render(data,route,null,{...ledger,ledger_state:'UNAVAILABLE'}),/台账不可用；不代表没有任务/);
 const handoffSource=require('../evidence/development-handoff/main-relayed-20261117.json');const handoffHtml=ui.render(data,route,null,{...ledger,observations:{development_handoff:handoffSource}});assert.match(handoffHtml,/来源消息时间 1794846300397/);assert.match(handoffHtml,/交接实际发生时间未核实/);assert.doesNotMatch(handoffHtml,/记录时间 1794846300397/);
 const backupObs={observed_at:'2026-11-16T18:23:23.889Z',schedule_enabled:true,interval_ms:300000,backup_at:'2026-11-16T18:19:59Z',backup_status:'ok',files:401,excluded_count:34,changed:false,remote_verified_reported:true};const staticBackup={source_observation_verified:'MAIN_RELAYED_SNAPSHOT_BYTES_MATCH',freshness:'snapshot-not-live',backup_observation:backupObs};const backupRender=b=>ui.render(data,route,null,{...ledger,backup:b});const staticHtml=backupRender(staticBackup);assert.match(staticHtml,/截至时间 2026-11-16T18:23:23.889Z/);assert.doesNotMatch(staticHtml,/读取时间 2026-11-16T18:23:23.889Z/);const localBackup={source_observation_verified:'LOCAL_RECEIPT_REPORTED_NOT_AUTHENTICATED',freshness:'local-receipt-not-live-scheduler',backup_observation:{...backupObs,observed_at:'2026-11-16T18:32:11Z'}};assert.match(backupRender(localBackup),/读取时间 2026-11-16T18:32:11Z/);const both=backupRender({...localBackup,static_snapshot:staticBackup});assert.match(both,/读取时间 2026-11-16T18:32:11Z/);assert.match(both,/每5分钟（截至 2026-11-16T18:23:23.889Z）/);
 const done={...ledger,tasks:[{...ledger.tasks[0],handoffs:[{...ledger.tasks[0].handoffs[0],status:'交接完成(范围)'}]}]};assert.match(ui.render(data,route,null,done),/资料显示交接完成，真实性尚待核实/);
 const twin={observed_at:null,records:{ai_instances:[{role_id:'role',role_instance_id:'UNKNOWN',task_ids:['dev-1'],run_id:'UNKNOWN',session_id:'UNKNOWN'}],tasks:[{task_id:'dev-1',attempt_id:'attempt-1',state:'READY',artifact_sha256:'UNKNOWN'}],evidence:[]}};const twinText=ui.render(data,route,twin,ledger).replace(/<[^>]*>/g,'');assert.doesNotMatch(twinText,/TEST_ONLY|UNKNOWN|UNAVAILABLE|Writer|READY|RUNNING/);assert.match(twinText,/资料是否为最新尚未确认/);
 assert.doesNotMatch(ui.render(data,ui.parseRoute('#overview'),null,ledger),/任务与三方交接资料/);
 await assert.rejects(ui.loadDevelopmentLedger(()=>Promise.resolve({ok:false,status:403})),/LEDGER_HTTP_403/);
 await assert.rejects(ui.loadDevelopmentLedger(()=>Promise.resolve({ok:true,json:()=>Promise.resolve({mode:'PRODUCTION',tasks:[]})})),/LEDGER_PROJECTION_MISMATCH/);
 // Exercise the real boot path: actual endpoint names, async paint and board-only scope.
 const app={innerHTML:'',querySelectorAll:()=>[]},mode={textContent:''},home={};
 const doc={getElementById:(id)=>({app:app,dataMode:mode,home:home})[id]||null};
 const requests=[];let hashchange;const win={location:{protocol:'https:',hash:'#board/research-development'},addEventListener:(name,fn)=>{if(name==='hashchange')hashchange=fn;},fetch:(url)=>{requests.push(url);if(url==='api/projection')return Promise.resolve({ok:true,json:()=>Promise.resolve({...data,tenant_id:'tenant-test'})});if(url==='api/admin/delivery-ledger')return Promise.resolve({ok:true,json:()=>Promise.resolve(ledger)});return Promise.resolve({ok:false,status:403});}};
 ui.boot(doc,win,null);await new Promise(resolve=>setTimeout(resolve,10));
 assert.deepStrictEqual(requests.sort(),['api/admin/delivery-ledger','api/admin/digital-twin','api/projection'].sort());assert.match(app.innerHTML,/有缺项/);assert.match(app.innerHTML,/资料来源和负责身份尚未核实/);assert.match(mode.textContent,/交接情况尚待核实/);win.location.hash='#overview';hashchange();assert.match(mode.textContent,/LIVE_SQLITE/);
 console.log('development_ledger_delta: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
