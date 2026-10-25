'use strict';
const assert=require('assert');
const ui=require('../demos/task-center-digital-twin/app.js');
const data={mode:'TEST_ONLY',boards:[{board_id:'research-development',task_count:2,active_count:1,blocked_count:1,health:'BLOCKED'}],anomalies:[{task_id:'t-a',board_id:'research-development',project_id:'p-1',missing:'DEPENDENCY_WAIT',impact:'DEPENDENT_TASK_NOT_STARTABLE',depends_on:['t-b'],responsible_party:'qa',task_responsible_party:'dev',resolution_responsible_party:'qa',next_action:'WAIT',evidence_ref:['qa-proof']}],tasks:[{task_id:'t-a',project_id:'p-1',node_id:'n-a',board_id:'research-development',state:'READY',runtime_status:'WAITING_DEPENDENCY',responsible_party:'dev',task_responsible_party:'dev',attempt_id:'UNKNOWN',epoch:null,next_action:'WAIT_DEPENDENCIES',blocker:'DEPENDENCY_WAIT',authority_state:'NONE',checkpoint_sha256:'a',writer_identity:'UNKNOWN',run_id:'UNKNOWN',session_id:'UNKNOWN',session_state:'UNKNOWN',process_state:'UNKNOWN',last_real_progress_at:null,effects_reconciled:'UNKNOWN',writer_stopped:'UNKNOWN'}]};
assert.deepStrictEqual(ui.parseRoute('#task/research-development/t-a?project=p-1'),{view:'task',board:'research-development',task:'t-a',query:{project:'p-1'}});
assert.strictEqual(ui.filterTasks(data,ui.parseRoute('#board/research-development?project=p-1')).length,1);
assert.match(ui.render(data,ui.parseRoute('#overview')),/七板块运行概况/);
assert.match(ui.render(data,ui.parseRoute('#overview')),/定位卡点/);
assert.match(ui.render(data,ui.parseRoute('#board\/research-development?project=p-1')),/研发工作台/);
assert.match(ui.render(data,ui.parseRoute('#board\/research-development?project=p-1')),/项目详情/);
assert.match(ui.render(data,ui.parseRoute('#project\/research-development\/p-1')),/1 个任务/);
assert.match(ui.render(data,ui.parseRoute('#task/research-development/t-a?project=p-1')),/异常证据/);
assert.match(ui.render(data,ui.parseRoute('#task/research-development/t-a?project=p-1')),/任务负责人：dev/);
assert.match(ui.render(data,ui.parseRoute('#task/research-development/t-a?project=p-1')),/解除责任方：qa/);
assert.match(ui.render(data,ui.parseRoute('#task/research-development/t-a?project=p-1')),/进程：UNKNOWN/);
assert.match(ui.render(data,ui.parseRoute('#task/research-development/t-a?project=p-1')),/运行投影：WAITING_DEPENDENCY/);
assert.match(ui.href('board','research-development',null,{project:'p-1'}),/^#board\/research-development\?project=p-1$/);
for(const id of ['task-normal','任务/设计','task with space']){
  const target=ui.href('task','research-development',id,{project:'项目/一'});
  const parsed=ui.parseRoute(target);
  assert.strictEqual(parsed.task,id);
  assert.strictEqual(parsed.query.project,'项目/一');
}
const special=JSON.parse(JSON.stringify(data));
special.tasks[0].task_id='任务/设计';special.anomalies[0].task_id='任务/设计';
assert.match(ui.render(special,ui.parseRoute(ui.href('task','research-development','任务/设计',{}))),/任务\/设计/);
assert.match(ui.render(special,ui.parseRoute(ui.href('task','research-development','任务/设计',{}))),/异常证据/);
assert.strictEqual(ui.parseRoute('#task/research-development/%E0%A4%A').view,'invalid');
ui.loadProjection(()=>Promise.resolve({ok:true,json:()=>Promise.resolve(data)})).then(x=>{assert.strictEqual(x,data);console.log('task_center_digital_twin.test: PASS');});
