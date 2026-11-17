'use strict';
const assert=require('assert'),fs=require('fs'),ui=require('../demos/task-center-digital-twin/app.js');
const data={mode:'TEST_ONLY',tenant_id:'tenant-test',tasks:[{task_id:'dev-1',board_id:'research-development',project_id:'p',state:'READY'}],boards:[],anomalies:[]};
const internal={tasks:[{task_id:'dev-1',handoffs:[{status:'INTERNAL_SENTINEL',supervisor:'SUPERVISOR_SENTINEL'}]}],backup:{backup_observation:{backup_status:'BACKUP_SENTINEL'}}};
const absent=/任务与三方交接资料|源码备份|三方监督|交接资料|台账|delivery-ledger|delivery-handoff|INTERNAL_SENTINEL|SUPERVISOR_SENTINEL|BACKUP_SENTINEL/;
(async()=>{
 for(const route of ['#board/research-development','#overview']){const html=ui.render(data,ui.parseRoute(route),null,internal);assert.doesNotMatch(html,absent);}
 const board=ui.render(data,ui.parseRoute('#board/research-development'),null,internal);for(const x of ['研发工作台','dev-1','研发任务中心事实','AI 工作现场','项目详情'])assert(board.includes(x),x);
 assert.doesNotMatch(fs.readFileSync('demos/task-center-digital-twin/admin.html','utf8'),/delivery-ledger|交接资料/);
 assert.strictEqual(fs.existsSync('demos/task-center-digital-twin/delivery-ledger.html'),false);assert.strictEqual(fs.existsSync('demos/task-center-digital-twin/delivery-ledger.js'),false);
 const app={innerHTML:'',querySelectorAll:()=>[]},mode={textContent:''},home={},doc={getElementById:id=>({app,dataMode:mode,home})[id]||null};
 const requests=[];let hashchange;const win={location:{protocol:'https:',hash:'#board/research-development'},addEventListener:(name,fn)=>{if(name==='hashchange')hashchange=fn;},fetch:url=>{requests.push(url);return url==='api/projection'?Promise.resolve({ok:true,json:()=>Promise.resolve(data)}):Promise.resolve({ok:false,status:403});}};
 ui.boot(doc,win,null);await new Promise(r=>setTimeout(r,10));assert.deepStrictEqual(requests.sort(),['api/admin/digital-twin','api/projection'].sort());assert.doesNotMatch(app.innerHTML,absent);assert.match(app.innerHTML,/研发工作台/);win.location.hash='#overview';hashchange();assert.match(mode.textContent,/LIVE_SQLITE/);assert.doesNotMatch(app.innerHTML,absent);
 console.log('development_ledger_delta: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
