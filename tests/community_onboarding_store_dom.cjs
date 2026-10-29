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
let app={application:'app1',revision:1,status:'DRAFT',entity_type:'ENTERPRISE',fields:{},required_materials:['business_license'],materials:{}},profile={},calls=[],pending=null,denied=false,holdUpload=false,uploadReply=null,holdSave=false,saveReply=null;
const kinds=['business_license','mini_program_screenshot','operator_identity','operator_identity_back',...Array.from({length:4},(_,i)=>['ubo_'+(i+1)+'_front','ubo_'+(i+1)+'_back']).flat()];
const reply=result=>({ok:true,status:200,json:async()=>({result:structuredClone(result),payment_enabled:false})});
const context={document,window:{},location:{pathname:process.argv[3]||'/merchant/apply'},structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const b=JSON.parse(options.body);calls.push(b);if(denied)return{ok:false,status:403};
 if(b.operation==='catalog')return reply({materials:kinds.map(id=>({id,title:id}))});
 if(b.operation==='mine'||b.operation==='review_list')return reply({applications:[app]});
 if(b.operation==='read'||b.operation==='review_read')return reply(app);
 if(b.operation==='wechat_read'||b.operation==='wechat_review_read')return reply({version:1,profile});
 if(b.operation==='wechat_save'&&holdSave)return new Promise(resolve=>saveReply=resolve);
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
const scene=key=>walk(nodes.wechatFields).find(e=>e.dataset.scene===key);
const choose=(key,checked)=>{scene(key).checked=checked;scene(key).listeners.change();};
const media=kind=>nodes.wechatMedia.children.find(e=>e.dataset.material===kind);
const store='SALES_SCENES_STORE',mini='SALES_SCENES_MINI_PROGRAM',prefix='business_info.sales_info.biz_store_info.';
(async()=>{
 await flush();await reload();assert.equal(scene(mini).checked,true);assert.equal(scene(store).checked,false);assert(media('storefront_photo').hidden);
 choose(store,true);assert(!control(prefix+'biz_store_name').parentNode.hidden);
 edit(prefix+'biz_store_name','Synthetic store');edit(prefix+'biz_address_code','verified-fixture-code');edit(prefix+'biz_store_address','Synthetic address');
 media('storefront_photo').click();await flush();pending(reply({media_id:'store-front'}));await flush();
 media('interior_photo').click();await flush();pending(reply({media_id:'store-inside'}));await flush();await save();
 assert.deepEqual(profile.business_info.sales_info.sales_scenes_type,[mini,store]);assert.deepEqual(profile.business_info.sales_info.biz_store_info,{biz_store_name:'Synthetic store',biz_address_code:'verified-fixture-code',biz_store_address:'Synthetic address',store_entrance_pic:['store-front'],indoor_pic:['store-inside']});
 choose(mini,false);await save();assert.deepEqual(profile.business_info.sales_info.sales_scenes_type,[store]);await read();assert(!scene(mini).checked);assert(scene(store).checked);assert.equal(control(prefix+'biz_address_code').value,'verified-fixture-code');
 const before=JSON.stringify(profile);await save();assert.equal(JSON.stringify(profile),before);
 choose(store,false);const count=calls.length;await save();assert.equal(calls.length,count);assert(nodes.status.textContent.includes('至少选择'));media('storefront_photo').click();await flush();assert.equal(calls.length,count);
 // Scene changes invalidate late media without losing historical stored objects.
 choose(store,true);media('storefront_photo').click();await flush();choose(store,false);pending(reply({media_id:'stale-store'}));await flush();assert.equal(control(prefix+'store_entrance_pic').value,'store-front');
 choose(mini,true);await save();assert.deepEqual(profile.business_info.sales_info.sales_scenes_type,[mini]);assert.deepEqual(profile.business_info.sales_info.biz_store_info.store_entrance_pic,['store-front']);
 // A late saved draft must not reset newer scene selections.
 holdSave=true;nodes.wechatProfile.onsubmit({preventDefault(){}});await flush();choose(store,true);saveReply(reply({version:9,profile}));await flush();assert(scene(store).checked);assert(nodes.status.textContent.includes('保存结果请刷新'));holdSave=false;
 // Rebinding the original account/application also prevents an old response from rendering.
 choose(store,true);media('interior_photo').click();await flush();const old=pending;app={...app,application:'app2'};await reload();old(reply({media_id:'old-application'}));await flush();assert.equal(control(prefix+'indoor_pic').value,'');
 assert(scene(mini).checked);assert(!scene(store).checked);assert(!calls.some(c=>['wechat_execute','wechat_query'].includes(c.operation)));
 // Unknown or malformed saved scenes must never be silently narrowed on save.
 for(const invalid of [[mini,'SALES_SCENES_UNREGISTERED'],[mini,mini],[],null,mini,{},[7]]){
  profile={business_info:{sales_info:{sales_scenes_type:invalid}}};await read();const before=calls.length;choose(mini,true);await save();assert.equal(calls.length,before);assert(nodes.status.textContent.includes('人工核对'));assert.deepEqual(profile.business_info.sales_info.sales_scenes_type,invalid);media('mini_program_screenshot').click();await flush();assert.equal(calls.length,before);
 }
 profile={};await read();assert(scene(mini).checked);await save();assert.deepEqual(profile.business_info.sales_info.sales_scenes_type,[mini]);
 console.log('STORE scenes DOM PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
