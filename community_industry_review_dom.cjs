'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.dataset={};this.listeners={};this.textContent='';}
 append(...nodes){for(const n of nodes){n.parentNode=this;this.children.push(n);}}
 replaceChildren(...nodes){this.children=[];this.append(...nodes);}
 setAttribute(){}
 addEventListener(event,fn){this.listeners[event]=fn;}
 querySelectorAll(selector){return walk(this).slice(1).filter(n=>selector.split(',').includes(n.tagName));}
 click(){if(!this.disabled)return (this.onclick||this.listeners.click)?.({preventDefault(){}});}
}
const walk=e=>[e,...e.children.flatMap(walk)],nodes={};
const document={getElementById:id=>nodes[id]??=(new Element()),createElement:tag=>new Element(tag),createTextNode:t=>Object.assign(new Element(),{textContent:t}),querySelectorAll:s=>s==='button'?Object.values(nodes).flatMap(walk).filter(n=>n.tagName==='button'):[]};
let app={application:'app1',revision:1,status:'DRAFT',entity_type:'ENTERPRISE',fields:{},required_materials:['business_license'],materials:{}},profile={},calls=[],pending=null,denied=false,holdUpload=false,uploadReply=null;
const kinds=['business_license','mini_program_screenshot','operator_identity','operator_identity_back',...Array.from({length:4},(_,i)=>['ubo_'+(i+1)+'_front','ubo_'+(i+1)+'_back']).flat()];
const reply=result=>({ok:true,status:200,json:async()=>({result:structuredClone(result),payment_enabled:false})});
const testPath='/merchant/review';
const context={document,window:{},location:{pathname:testPath,search:testPath==='/merchant/review'?'?embedded=1':'',hash:'',replace(){}},URLSearchParams,structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const b=JSON.parse(options.body);calls.push(b);if(denied)return{ok:false,status:403};
 if(b.operation==='catalog')return reply({materials:kinds.map(id=>({id,title:id}))});
 if(b.operation==='mine'||b.operation==='review_list')return reply({applications:[app]});
 if(b.operation==='read'||b.operation==='review_read')return reply(app);
 if(b.operation==='wechat_read'||b.operation==='wechat_review_read')return reply({version:1,profile,industry_review:{status:'READY',plan:{qualification_type:'宠物医院',requires_explicit_review:true,branches:[{description:'动物诊疗许可证'}],current_qualifications:[{kind:'industry_permit',sha256:'a'.repeat(64),media_id:'synthetic'}]}}});
 if(b.operation==='wechat_review')return reply({version:2,profile,state:b.params.decision});
 if(b.operation==='wechat_save'){profile=b.params.profile;return reply({version:2,profile});}
 if(b.operation==='wechat_media')return new Promise(resolve=>{pending=resolve;});
 if(b.operation==='upload'&&holdUpload)return new Promise(resolve=>uploadReply=resolve);
 if(b.operation==='upload'){app.materials[b.params.kind]={review:'PENDING'};app.revision++;return reply(app);}
 if(b.operation==='review_material'){app.materials[b.params.kind].review=b.params.decision;app.revision++;return reply(app);}
 throw Error('Unexpected mock operation '+b.operation);
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
const control=path=>walk(nodes.wechatFields).find(e=>e.dataset.path===path);
const edit=(path,value)=>{const e=control(path);e.value=value;e.listeners.input?.();};
const rows=()=>nodes.materials.children.map(e=>e.dataset.kind);
const reload=async()=>{await context.window.configureCommunityOnboarding({csrf:'test'});await flush();if(context.location.pathname==='/merchant/review'){walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();}};
const read=async()=>{nodes.wechatRead.click();await flush();};
const save=async()=>{nodes.wechatProfile.onsubmit({preventDefault(){}});await flush();};
(async()=>{
 await flush();await reload();await read();
 const fields=walk(nodes.wechatState),select=fields.find(x=>x.tagName==='select'),reason=fields.find(x=>x.tagName==='textarea'),check=fields.find(x=>x.tagName==='input');
 assert.ok(select&&reason&&check);assert.equal(select.value,'','approval must not default to satisfied');assert.ok(!check.checked);
 nodes.wechatOpinion.value='Synthetic reviewer opinion';nodes.wechatApprove.click();await flush();
 assert.equal(calls.filter(x=>x.operation==='wechat_review').length,0,'missing conditions must not be submitted');
 select.value='APPLICABLE_SATISFIED';reason.value='Synthetic checked current certificate';check.checked=true;
 nodes.wechatApprove.click();await flush();
 const sent=calls.find(x=>x.operation==='wechat_review');assert.ok(sent);
 assert.deepEqual(JSON.parse(JSON.stringify(sent.params.industry_branch_assessments)),[{branch_index:0,applicability:'APPLICABLE_SATISFIED',material_kinds:['industry_permit'],rationale:'Synthetic checked current certificate'}]);
 assert.ok(!('reviewer_id' in sent.params));assert.ok(!('rule_sha256' in sent.params));
 await read();nodes.wechatCorrect.click();await flush();
 const correction=calls.filter(x=>x.operation==='wechat_review').at(-1);assert.equal(correction.params.decision,'CORRECTION');assert.ok(!('industry_branch_assessments' in correction.params));
 console.log('industry reviewer explicit evidence UI PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
