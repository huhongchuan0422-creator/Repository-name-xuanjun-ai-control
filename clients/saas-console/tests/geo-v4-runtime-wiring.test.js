import test from'node:test';
import assert from'node:assert/strict';
import {buildGeoView,applyGeoRuntimeView} from'../src/geo-v4-runtime.js';

class E{
 constructor(text=''){this.textContent=text;this.value='';this.disabled=false;this.style={};this.attrs={};this.children={};this.childNodes=[];this.innerHTML=''}
 querySelector(s){return this.children[s]||null}querySelectorAll(s){return this.children[s+'[]']||[]}replaceChildren(...x){this.childNodes=[...x];this.textContent=''}setAttribute(k,v){this.attrs[k]=v}removeAttribute(k){delete this.attrs[k]}remove(){this.removed=true}
}
function fakeDoc(){
 const d=new E(),body=new E();d.body=body;const map=new Map,arr=new Map;
 d.querySelector=s=>map.get(s)||null;d.querySelectorAll=s=>arr.get(s)||[];d.getElementById=id=>map.get('#'+id)||null;
 d.set=(s,e)=>{map.set(s,e);return e};d.setAll=(s,x)=>{arr.set(s,x);return x};
 const side=d.set('.sideplan',new E());side.children={'span':new E(),'b':new E(),'small':new E('.sideplan-small-demo'),'.progress i':new E()};
 d.set('#sidebarbrand',new E('青禾'));d.set('.brandmini',new E('青'));d.set('.livebadge',new E('演示数据'));
 const bar=d.set('.demobar span',new E('演示数据 · 操作仅模拟'));
 d.set('.reportbanner div',new E('本期效果 · 演示数据'));
 for(const sel of ['.tablewrap','.chartwrap','.scope','#issuelist','.nextaction','.hero','.planitem','.execstep','.detailhero','.history','.emptyhistory','.sourcebox','.ownerline','.comparison','.rowline','.explain','.chartplot svg','select'])d.setAll(sel,[]);
 const review=d.setAll('.review',[new E('演示审阅')]);review[0].children={'.mini':new E('发布预览 · 第 3 版')};
 d.setAll('.comment',[new E('我的内容意见演示评论'),new E('我的内容意见第二条演示评论')]);
 d.setAll('.evidencebox',[new E('演示证据')]);d.setAll('.quotebox',[new E('演示引用')]);
 const cn=d.setAll('.callnext',[new E('让下一轮，从尚未改善的地方开始。')]);cn[0].children={'h2':new E('让下一轮，从尚未改善的地方开始。'),'p':new E('保留本轮历史。')};
 d.setAll('.chartnote',[new E('演示注记')]);
 d.set('meta[name="description"]',new E());const g=d.set('#geo-runtime-guard',new E());return d;
}
const connected=snapshot=>({mode:'CONNECTED',project:{id:'p',tenant:'ta'},state:{role:'OWNER',entitlement:{enabled:true}},snapshot:{tenant_id:'ta',connection:'CONNECTED',actions:{},...snapshot}});

test('GEO view ignores non-READY versions and next_round sections',()=>{
 const v=buildGeoView(connected({versions:{status:'STALE',current_version:9},next_round:{eligibility:'ELIGIBLE'}}));
 assert.equal(v.versions,null);assert.equal(v.next_round,null);
});
test('GEO view parses READY versions and next_round content',()=>{
 const v=buildGeoView(connected({versions:{status:'READY',current_version:4,comments:['补充出处'],confirmation_state:'PENDING'},next_round:{status:'READY',eligibility:'ELIGIBLE',source_result:'引用提升',task_creation_state:'PENDING'}}));
 assert.equal(v.versions.current_version,4);assert.equal(v.next_round.eligibility,'ELIGIBLE');
});
test('GEO connected versions bind real review comments and confirmation state instead of demo text',()=>{
 const d=fakeDoc();
 applyGeoRuntimeView(d,connected({versions:{status:'READY',current_version:4,confirmation_state:'APPROVED',comments:['第三版补充了出处与适用条件。']}}));
 assert.equal(d.querySelectorAll('.review')[0].querySelector('.mini').textContent,'发布预览 · 第 4 版 · 已批准');
 const cs=d.querySelectorAll('.comment');
 assert.equal(cs[0].textContent,'我的内容意见 第三版补充了出处与适用条件。');
 assert.equal(cs[1].textContent,'其余版本评论未接入展示');
 assert.equal(d.querySelectorAll('.evidencebox')[0].textContent,'真实明细未接入或数据不足');
 assert.equal(d.querySelectorAll('.quotebox')[0].textContent,'真实明细未接入或数据不足');
});
test('GEO connected without versions masks review and comment demo content',()=>{
 const d=fakeDoc();applyGeoRuntimeView(d,connected({}));
 assert.equal(d.querySelectorAll('.review')[0].textContent,'真实版本与确认状态未接入');
 assert.equal(d.querySelectorAll('.comment')[0].textContent,'真实版本与确认状态未接入');
});
test('GEO unknown confirmation state never renders as approved',()=>{
 const d=fakeDoc();
 applyGeoRuntimeView(d,connected({versions:{status:'READY',current_version:3,comments:[]}}));
 assert.match(d.querySelectorAll('.review')[0].querySelector('.mini').textContent,/确认状态未知/);
 assert.equal(d.querySelectorAll('.comment')[0].textContent,'暂无版本评论记录');
});
test('GEO next_round binds eligibility source result and task creation state',()=>{
 const d=fakeDoc();
 applyGeoRuntimeView(d,connected({results:{status:'READY',summary:'真实摘要',comparison_scope:'2026-11-01 至 11-07 · 24 题',sample_size:240},next_round:{status:'READY',eligibility:'ELIGIBLE',source_result:'安全说明引用 4→10',task_creation_state:'CREATED'}}));
 assert.equal(d.querySelectorAll('.callnext')[0].querySelector('h2').textContent,'本轮结果可转入下一轮');
 assert.equal(d.querySelectorAll('.callnext')[0].querySelector('p').textContent,'来源结果：安全说明引用 4→10；新任务已创建');
 assert.equal(d.querySelectorAll('.chartnote')[0].textContent,'2026-11-01 至 11-07 · 24 题 · 样本 240 条');
});
test('GEO next_round masked when results ready but next-round authority missing',()=>{
 const d=fakeDoc();
 applyGeoRuntimeView(d,connected({results:{status:'READY',summary:'真实摘要'}}));
 assert.equal(d.querySelectorAll('.callnext')[0].textContent,'下一轮资格与任务创建状态未接入');
});
test('GEO billing usage shows authoritative source and remaining fallback',()=>{
 const d=fakeDoc();
 applyGeoRuntimeView(d,connected({usage:{status:'READY',plan:'企业版',used:12,quota:100,source:'统一计费服务'}}));
 assert.equal(d.querySelector('.sideplan').querySelector('small').textContent,'我的观察用量 12 / 100 · 来源 统一计费服务');
 const d2=fakeDoc();
 applyGeoRuntimeView(d2,connected({usage:{status:'READY',quota:100,remaining:760,source:'平台账单'}}));
 assert.equal(d2.querySelector('.sideplan').querySelector('small').textContent,'我的剩余观察额度 760 / 100 · 来源 平台账单');
 const d3=fakeDoc();
 applyGeoRuntimeView(d3,connected({usage:{status:'READY',used:12,quota:100}}));
 assert.equal(d3.querySelector('.sideplan').querySelector('small').textContent,'我的观察用量 12 / 100');
});
test('GEO not-connected path never renders bound versions next-round or usage as real',()=>{
 const d=fakeDoc();applyGeoRuntimeView(d,{mode:'NOT_CONNECTED',state:{entitlement:{}},snapshot:null});
 assert.equal(d.querySelector('.sideplan').querySelector('small').textContent,'观察用量未接入');
 assert.equal(d.querySelectorAll('.callnext')[0].textContent,'真实效果数据未接入或数据不足');
 assert.equal(d.querySelectorAll('.comment')[0].textContent,'真实版本与确认状态未接入');
});
