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
const context={document,window:{},location:{pathname:process.argv[3]||'/merchant/apply'},structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const b=JSON.parse(options.body);calls.push(b);if(denied)return{ok:false,status:403};
 if(b.operation==='catalog')return reply({materials:kinds.map(id=>({id,title:id}))});
 if(b.operation==='mine'||b.operation==='review_list')return reply({applications:[app]});
 if(b.operation==='read'||b.operation==='review_read')return reply(app);
 if(b.operation==='wechat_read'||b.operation==='wechat_review_read')return reply({version:1,profile});
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
const reload=async()=>{await context.window.configureCommunityOnboarding({csrf:'test'});await flush();if(context.location.pathname==='/merchant/review'){nodes.applications.children[0].click();await flush();}};
const read=async()=>{nodes.wechatRead.click();await flush();};
const save=async()=>{nodes.wechatProfile.onsubmit({preventDefault(){}});await flush();};
(async()=>{
 await flush();await reload();
 if(context.location.pathname==='/merchant/review'){
  app.status='SUBMITTED';app.materials.ubo_4_back={review:'PENDING'};await reload();
  assert(rows().includes('ubo_4_back'));nodes.note.value='Synthetic review';
  nodes.materials.children.find(e=>e.dataset.kind==='ubo_4_back').children.find(e=>e.textContent==='资料通过').click();await flush();
  assert.equal(app.materials.ubo_4_back.review,'ACCEPTED');console.log('conditional reviewer PASS');return;
 }
 assert.equal(nodes.licenseInline.hidden,false,'enterprise license section visible on initial application');nodes.entity_type.value='SOLE_PROPRIETOR';nodes.entity_type.listeners.change?.();assert.equal(nodes.licenseInline.hidden,true,'license section hidden for non-enterprise');nodes.entity_type.value='ENTERPRISE';nodes.entity_type.listeners.change?.();assert.equal(nodes.licenseInline.hidden,false,'license section restored for enterprise');
 assert(!rows().includes('operator_identity_back'));edit('contact_info.contact_type','SUPER');edit('contact_info.contact_id_doc_type','IDENTIFICATION_TYPE_IDCARD');assert(rows().includes('operator_identity_back'));
 edit('contact_info.contact_id_doc_type','IDENTIFICATION_TYPE_OVERSEA_PASSPORT');assert(!rows().includes('operator_identity_back'));
 for(let i=0;i<4;i++){edit('subject_info.ubo_info_list.'+i+'.ubo_id_doc_type','IDENTIFICATION_TYPE_IDCARD');assert(rows().includes('ubo_'+(i+1)+'_front'));assert(rows().includes('ubo_'+(i+1)+'_back'));}
 edit('subject_info.ubo_info_list.0.ubo_id_doc_type','IDENTIFICATION_TYPE_OVERSEA_PASSPORT');assert(!rows().includes('ubo_1_back'));
 // Existing optional objects remain visible, downloadable and reviewable after conditions change.
 app.materials.ubo_1_back={review:'PENDING'};await reload();assert(rows().includes('ubo_1_back'));
 app.entity_type='SOLE_PROPRIETOR';await reload();assert(control('subject_info.ubo_info_list.0.ubo_id_doc_type').parentNode.hidden);assert(rows().includes('ubo_1_back'));assert(!rows().includes('ubo_2_front'));
 profile={subject_info:{ubo_info_list:[{ubo_id_doc_type:'old',ubo_id_doc_copy:'old'}]},business_info:{sales_info:{sales_scenes_type:['SALES_SCENES_STORE'],biz_store_info:{biz_store_name:'Keep'}}}};await read();await save();assert(!profile.subject_info.ubo_info_list,nodes.status.textContent);assert.deepEqual(profile.business_info.sales_info.sales_scenes_type,['SALES_SCENES_STORE']);assert.equal(profile.business_info.sales_info.biz_store_info.biz_store_name,'Keep');
 app.entity_type='ENTERPRISE';await reload();edit('contact_info.contact_type','SUPER');edit('contact_info.contact_id_doc_type','IDENTIFICATION_TYPE_IDCARD');
 const row=nodes.materials.children.find(e=>e.dataset.kind==='operator_identity_back'),file=row.children.find(e=>e.type==='file');let readFile;
 file.files=[{size:5,arrayBuffer:()=>new Promise(resolve=>readFile=resolve)}];row.children.find(e=>e.textContent==='上传资料').click();await flush();const before=calls.length;edit('contact_info.contact_id_doc_type','IDENTIFICATION_TYPE_OVERSEA_PASSPORT');readFile(new Uint8Array([1,2,3]).buffer);await flush();assert.equal(calls.length,before);
 // A current conditional file uses the original upload operation and revision.
 const active=nodes.materials.children.find(e=>e.dataset.kind==='operator_identity');active.children.find(e=>e.type==='file').files=[{size:5,arrayBuffer:async()=>new Uint8Array([37,80,68,70,45]).buffer}];active.children.find(e=>e.textContent==='上传资料').click();await flush();assert(app.materials.operator_identity);assert.equal(calls.at(-1).operation,'upload');
 // A completed original upload cannot render an obsolete conditional context.
 holdUpload=true;const delayedRow=nodes.materials.children.find(e=>e.dataset.kind==='operator_identity');delayedRow.children.find(e=>e.type==='file').files=[{size:5,arrayBuffer:async()=>new Uint8Array([37,80,68,70,45]).buffer}];delayedRow.children.find(e=>e.textContent==='上传资料').click();await flush();assert(uploadReply);edit('contact_info.contact_type','LEGAL');uploadReply(reply({...app,fields:{store_name:'STALE-UPLOAD'}}));await flush();assert.notEqual(nodes.applicationTitle.textContent,'STALE-UPLOAD');assert(nodes.status.textContent.includes('刷新后核对'));holdUpload=false;
 // Clearing an optional UBO slot removes its media references from the draft, not stored objects.
 profile={subject_info:{ubo_info_list:[{ubo_id_doc_type:'IDENTIFICATION_TYPE_IDCARD',ubo_id_doc_copy:'old-front',ubo_id_doc_copy_back:'old-back'}]}};await read();edit('subject_info.ubo_info_list.0.ubo_id_doc_type','');await save();assert(!profile.subject_info.ubo_info_list);assert(app.materials.ubo_1_back);
 // A mocked provider reply cannot contaminate a newly selected legal identity type.
 const sync=nodes.wechatMedia.children.find(e=>e.textContent==='同步已上传的身份证人像面');sync.click();await flush();edit('subject_info.identity_info.id_doc_type','IDENTIFICATION_TYPE_OVERSEA_PASSPORT');pending(reply({media_id:'stale-media'}));await flush();assert.equal(control('subject_info.identity_info.id_card_info.id_card_copy').value,'');await save();assert(!JSON.stringify(profile).includes('stale-media'));
 // Legal contact clears obsolete operator references; passport clears reverse reference only.
 profile={contact_info:{contact_type:'SUPER',contact_id_doc_type:'IDENTIFICATION_TYPE_IDCARD',contact_id_doc_copy:'front',contact_id_doc_copy_back:'back'},subject_info:{}};await read();edit('contact_info.contact_type','LEGAL');await save();assert(!profile.contact_info.contact_id_doc_copy);assert(app.materials.ubo_1_back);
 denied=true;nodes.wechatRead.click();await flush();assert(nodes.status.textContent.includes('权限'));
 console.log('conditional materials DOM PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
