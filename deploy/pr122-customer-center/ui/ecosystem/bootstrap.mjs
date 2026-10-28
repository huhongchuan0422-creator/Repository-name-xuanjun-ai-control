import {makeApi} from './api.mjs';
import {mountPendingEcosystem} from './ecosystem-view.mjs';
export async function bootEcosystem(doc=globalThis.document,api=makeApi(),storage=globalThis.sessionStorage){
 const status=doc.querySelector('#entry-status'),picker=doc.querySelector('#project-picker'),content=doc.querySelector('#pending-content');let view=null,disposed=false,activeProject=null;
 status.textContent='正在验证原登录与项目成员关系…';picker.disabled=true;
 const me=await api.me();if(!Array.isArray(me.projects)||!me.projects.length)throw Error('PROJECT_MEMBERSHIP_REQUIRED');
 picker.replaceChildren(...me.projects.map(p=>{if(typeof p.id!=='string'||!/^[-\w]{1,128}$/.test(p.id))throw Error('INVALID_PROJECT');const n=doc.createElement('option');n.value=p.id;n.textContent=p.title+' · '+p.role;return n}));picker.value=me.projects[0].id;picker.disabled=false;
 async function open(){if(disposed)return;if(view?.hasPending()){picker.value=activeProject;status.textContent='当前项目登记仍在处理中或结果 UNKNOWN；请保留原幂等键并回读，不能切换丢弃。';return}view?.dispose();const p=me.projects.find(x=>x.id===picker.value);if(!p||!['OWNER','EDITOR','VIEWER','REVIEWER'].includes(p.role))throw Error('PROJECT_MEMBERSHIP_REQUIRED');activeProject=p.id;status.textContent='原项目权限：'+p.role+'；实际操作仍由服务器逐次核权。';view=mountPendingEcosystem(content,{api,project:p.id,storage},doc);await view.ready}
 picker.addEventListener('change',()=>open().catch(e=>{status.textContent='无法读取项目：'+e.message}));await open();return {dispose(){disposed=true;view?.dispose();picker.disabled=true}};
}
if(typeof document!=='undefined')bootEcosystem().catch(e=>{document.querySelector('#entry-status').textContent='访问未完成：'+e.message+'。请返回原控制台登录。'});
