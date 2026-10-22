/* Shared footer for authorized private previews. Does not grant project access. */
'use strict';
(async()=>{
const base='/customer/center/api/';
const slots=[...document.querySelectorAll('[data-project-feedback]')];if(!slots.length)return;
const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
let me;try{const r=await fetch(base+'me',{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;me=await r.json();}catch{return;}
for(const slot of slots){
 const project=slot.dataset.projectFeedback,page=slot.dataset.pagePath,version=slot.dataset.pageSha256;
 if(!me.projects.some(p=>p.id===project)||!/^\/[A-Za-z0-9/_\-.]+$/.test(page||'')||!/^[0-9a-f]{64}$/.test(version||''))continue;
 try{const check=await fetch(base+'change_context',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('xj_csrf')||''},body:JSON.stringify({project,page,version})});if(!check.ok)continue;}catch{continue;}
 const call=async(name,data)=>{const r=await fetch(base+name,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('xj_csrf')||''},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error('暂时无法核验整改记录，请稍后重试');return d;};
 const updates=node('section','');updates.setAttribute('aria-label','本页整改与复验记录');slot.append(updates);
 const refresh=async()=>{updates.replaceChildren();const data=await call('change_updates',{project,page,version});for(const item of data.updates){
  const card=node('article','');card.append(node('p',item.label),node('p',item.summary));
  const proof=node('details',''),title=node('summary','查看修改记录与版本凭证');proof.append(title,node('p','修改前：'+item.before_sha256),node('p','修改后：'+item.after_sha256),node('p','发布凭证：'+item.deployment_receipt_sha256));card.append(proof);
  if(item.state==='AWAIT_RETEST'){const reason=document.createElement('textarea');reason.setAttribute('aria-label','复验反馈');reason.maxLength=4000;card.append(reason);for(const [action,label] of [['ACCEPT','确认通过'],['FEEDBACK','继续反馈']]){const b=node('button',label);b.type='button';b.addEventListener('click',async()=>{b.disabled=true;try{await call('change_retest',{project,case:item.case,revision:item.revision,page,version,delivery_sha256:item.delivery_sha256,action,reason:reason.value.trim()||(action==='ACCEPT'?'确认本次调整通过':'本次调整仍需继续修改')});await refresh();}catch(e){card.append(node('p',e.message));}finally{b.disabled=false;}});card.append(b);}}
  updates.append(card);
 }};try{await refresh();}catch{updates.append(node('p','整改记录暂时无法核验；不会标记为已完成。'));}
 const heading=node('h2','对本页提出整改意见'),form=document.createElement('form'),label=node('label','请描述需要调整的位置与预期效果'),text=document.createElement('textarea'),button=node('button','提交整改意见'),status=node('p','');
 text.required=true;text.maxLength=4000;label.append(text);button.type='submit';const intentLabel=node('label','意见类型'),intent=document.createElement('select');for(const [value,title] of [['RECTIFICATION','原项目整改意见'],['NEW_ORDER','独立新增功能需求']]){const option=node('option',title);option.value=value;intent.append(option);}intentLabel.append(intent);form.append(intentLabel,label,button);slot.append(heading,form,status);
 const fees=node('a','查看本项目整改费用明细');fees.href='/customer/center/#project='+encodeURIComponent(project)+'&view=changes';slot.append(fees);
 form.addEventListener('submit',async e=>{e.preventDefault();button.disabled=true;try{
  const r=await fetch(base+'change_submit',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('xj_csrf')||''},body:JSON.stringify({project,page,version,text:text.value,intent:intent.value})});const d=await r.json();if(!r.ok)throw Error(d.error||'提交未完成');status.textContent='意见已归档；小整改优先直接处理，较大变更再核对原约定。当前尚未执行或收费。编号：'+d.id;text.value='';
 }catch(err){status.textContent=err.message;}finally{button.disabled=false;}});
}
})();
