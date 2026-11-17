'use strict';
const assert=require('assert');
const ui=require(process.argv[2]);
const data={mode:'TEST_ONLY',tenant_id:'tenant-test',tasks:[{task_id:'task-1',board_id:'research-development',project_id:'project-1'}],anomalies:[],timeline:[]};
const ledger={mode:'TEST_ONLY',tenant_id:'tenant-test',ledger_state:'AVAILABLE_METADATA_ONLY',tasks:[{task_id:'task-1',state:'UNKNOWN',validity:'HISTORICAL',handoffs:[]}],observations:{}};
const links=[];
for(const route of ['#board/research-development','#task/research-development/task-1']){
 const html=ui.render(data,ui.parseRoute(route),null,ledger);
 assert.match(html,/任务与交接资料见本页/);
 assert.match(html,/task-1/);
 assert.doesNotMatch(html,/delivery-ledger\.html/);
 const match=html.match(/<a href="([^"]+)">返回任务调度中心（公开调度摘要）<\/a>/);
 assert(match);assert.match(html,/<\/a><span>返回后将退出当前详情。<\/span>/);links.push(match[1]);
}
const denied=ui.render(data,ui.parseRoute('#board/research-development'),null,{...ledger,tenant_id:'other-tenant'});
assert.match(denied,/台账暂不可用或无权查看/);
assert.doesNotMatch(denied,/HISTORICAL/);
process.stdout.write(JSON.stringify(links));
