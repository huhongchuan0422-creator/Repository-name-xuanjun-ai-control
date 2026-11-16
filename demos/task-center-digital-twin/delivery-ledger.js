(function(){'use strict';
var area=document.getElementById('tasks'),status=document.getElementById('status'),observations=document.getElementById('observations');
function text(v){if(Array.isArray(v))return v.length?v.join('、'):'UNKNOWN';return v===null||v===undefined||v===''?'UNKNOWN':String(v);}
function line(box,key,value){var p=document.createElement('p');p.textContent=key+'：'+text(value);box.appendChild(p);}
function receipt(v){return v&&typeof v==='object'?text(v.observed_at)+' · '+text(v.validity):'UNKNOWN';}
function observationView(ob){observations.textContent='';var h=document.createElement('h2');h.textContent='台账实现与独审 · 观察资料';observations.appendChild(h);
 if(!ob||ob.state!=='OBSERVED_METADATA_ONLY'){line(observations,'观察来源','UNAVAILABLE');return;}
 line(observations,'范围','仅台账自身，不代表独立354业务');line(observations,'来源核对','协调方提供的固定快照；非身份或权限认证');line(observations,'新鲜度 / 全域空闲',text(ob.freshness)+' / '+text(ob.global_idle));
 ob.records.forEach(function(r){var p=document.createElement('p');p.textContent=text(r.role_label)+' · '+(r.observation_kind==='TOOL_RESULT_OBSERVED'?'观察到工具执行回执':'观察到角色结果回执')+' · '+text(r.record_timestamp_ms)+' · '+text(r.message_ref)+' · '+text(r.freshness);observations.appendChild(p);});
 line(observations,'实际接件 / 开始 / 业务完成','UNKNOWN / UNKNOWN / UNKNOWN');var a=document.createElement('a');a.href='api/admin/delivery-handoff?scope=ledger-self-observation';a.textContent='导出观察资料（非交接确认）';observations.appendChild(a);}
function render(data){area.textContent='';status.textContent='本地资料 · Writer 身份 UNKNOWN · 非业务验收';observationView(data.observations);
 if(!data.tasks.length){area.textContent=data.ledger_state==='UNAVAILABLE'?'任务台账不可用；不代表没有任务。':'暂无登记资料；不代表没有任务。';return;}
 data.tasks.forEach(function(t){var card=document.createElement('article');card.className='card';var title=document.createElement('h2');title.textContent=text(t.task_id);card.appendChild(title);
 line(card,'目标',t.goal);line(card,'负责人',t.writer);line(card,'资料有效性',t.validity);line(card,'资料状态',t.state);
 (t.roles.length?t.roles:[{}]).forEach(function(r){line(card,'角色与会话',text(r.role_id)+' / '+text(r.session)+' / '+text(r.validity));});
 line(card,'发送受理',receipt(t.receipt.sent));line(card,'接件资料（来源未核）',receipt(t.receipt.received));line(card,'开始',receipt(t.receipt.started));line(card,'最后进展',receipt(t.receipt.progress));line(card,'结果',receipt(t.receipt.result));line(card,'审核',receipt(t.receipt.review));line(card,'验收',receipt(t.receipt.accept));
 (t.sources.length?t.sources:[{}]).forEach(function(s){line(card,'源码',text(s.repo)+' / '+text(s.branch)+' / '+text(s.commit)+' / '+text(s.validity));line(card,'构建和产物',text(s.build)+' / '+text(s.manifest)+' / '+text(s.artifact));line(card,'部署',s.deploy);});
 (t.services.length?t.services:[{}]).forEach(function(s){line(card,'运行环境',text(s.class)+' / '+text(s.host)+' / '+text(s.running)+' / '+text(s.validity));});
 line(card,'阻点',t.blocker);line(card,'下一步',t.next_action);line(card,'原入口',t.entry);
 (t.permissions.length?t.permissions:[{}]).forEach(function(p){line(card,'权限',text(p.validity)+' / '+text(p.scope)+' / '+text(p.expires_at));});
 (t.handoffs.length?t.handoffs:[{}]).forEach(function(h){line(card,'交接',text(h.status)+' / 版本 '+text(h.version));line(card,'三方回执',text(h.outgoing)+' / '+text(h.receiving)+' / '+text(h.supervisor));line(card,'接收核对 / 监督结论',text((h.summary||{}).alignment_event_id)+' / '+text((h.summary||{}).verification_ref));line(card,'范围及缺项',text(h.scope)+' / '+text(h.excluded)+' / '+text(h.gaps));});
 var a=document.createElement('a');a.href='api/admin/delivery-handoff?task_id='+encodeURIComponent(t.task_id);a.textContent='导出交接资料';card.appendChild(a);area.appendChild(card);});}
function load(){status.textContent='正在读取……';return fetch('api/admin/delivery-ledger',{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw Error('UNAVAILABLE');return r.json();}).then(function(v){if(v.mode!=='TEST_ONLY')throw Error('UNAVAILABLE');render(v);}).catch(function(){area.textContent='';observations.textContent='';status.textContent='资料不可用或无权访问；状态 UNKNOWN。';});}
document.getElementById('refresh').addEventListener('click',load);load();
})();
