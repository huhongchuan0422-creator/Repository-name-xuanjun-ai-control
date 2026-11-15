(function(root){
'use strict';
var SOURCE='https://uk.wenwenwenyiyiyi.work/task-center-test/api/public-projection';
function esc(v){return String(v==null?'UNKNOWN':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function count(v){return Number.isSafeInteger(v)&&v>=0?v:'UNKNOWN';}
function project(p){
 if(!p||p.mode!=='TEST_ONLY'||!Array.isArray(p.boards))throw Error('公共投影格式不匹配');
 var matches=p.boards.filter(function(b){return b&&b.board_id==='research-development';}),b=matches.length===1?matches[0]:{};
 var observed=typeof p.observed_at==='number'&&Number.isFinite(p.observed_at)&&p.observed_at>0&&p.observed_at<=8640000000000?p.observed_at:null;
 var keys=['source','schema_version','snapshot_sha256','observed_at_unit','observed_at_semantics','valid_until','freshness'];
 var metadata=null;
 if(keys.some(function(k){return Object.prototype.hasOwnProperty.call(p,k);})){
  if(p.source!=='task-center-public-projection'||p.schema_version!==1||typeof p.snapshot_sha256!=='string'||!/^[a-f0-9]{64}$/.test(p.snapshot_sha256)||p.observed_at_unit!=='unix_seconds'||p.observed_at_semantics!=='MAX_CANONICAL_TASK_LAST_EVENT_AT'||p.valid_until!==null||p.freshness!=='UNKNOWN')throw Error('公共摘要版本不匹配');
  metadata={source:p.source,schema_version:1,snapshot_sha256:p.snapshot_sha256,observed_at_unit:p.observed_at_unit,observed_at_semantics:p.observed_at_semantics,valid_until:null,freshness:'UNKNOWN'};
 }
 // One response supplies counts, source event time and snapshot identity; never merge refreshes.
 // Digest is a producer identity, not a client-verified signature or freshness proof.
 // Explicit allowlist. Never forward task bodies, tenants, IDs, logs or unknown properties.
 return {metadata:metadata,mode:'TEST_ONLY',production_status:p.production_status==='NOT_IMPLEMENTED'?'NOT_IMPLEMENTED':'UNKNOWN',observed_at:observed,task_count:count(b.task_count),active_count:count(b.active_count),blocked_count:count(b.blocked_count),health:['ACTIVE','NO_DATA','BLOCKED','HEALTHY','UNKNOWN'].includes(b.health)?b.health:'UNKNOWN'};
}
function render(p,receivedAt){
 function label(v){return v==='UNKNOWN'?'待确认':esc(v);}
 return '<article class="card"><h2>研发公共摘要</h2><p>任务 '+label(p.task_count)+' · 活跃汇总 '+label(p.active_count)+' · 阻塞 '+label(p.blocked_count)+'</p><p>数据观察时间：'+esc(p.observed_at===null?'待确认':new Date(p.observed_at*1000).toISOString())+'</p><p>数据时效待确认；刷新不代表有新的任务进展。</p><p>项目、执行人员及实例详情尚未接入；活跃汇总不代表具体实例正在运行。</p></article>';
}
function mount(container,options){
 options=options||{};var generation=0,disposed=false;
 async function refresh(){var request=++generation;container.innerHTML='<p role="status">正在读取公开摘要…</p>';
 try{var response=await (options.fetch||root.fetch)(options.endpoint||SOURCE,{method:'GET',credentials:'omit',cache:'no-store',redirect:'error'});if(!response.ok)throw Error('HTTP '+response.status);var p=project(await response.json());if(disposed||request!==generation)return;container.innerHTML=render(p,new Date().toISOString());}
 catch(error){if(disposed||request!==generation)return;container.innerHTML='<p role="status">公开摘要读取失败；当前数据待确认。未保留上次成功数值。请重试。</p>';}
 }
 refresh();return {refresh:refresh,destroy:function(){disposed=true;generation++;container.innerHTML='';}};
}
var api={source:SOURCE,project:project,render:render,mount:mount};if(typeof module!=='undefined')module.exports=api;else root.XuanjunPublicProjection=api;
})(typeof window!=='undefined'?window:this);
