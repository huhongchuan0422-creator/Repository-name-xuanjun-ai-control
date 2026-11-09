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
 const history=node('section','');history.setAttribute('aria-label','本页已保存意见');slot.append(node('h2','本页已保存意见'),history);
 const pendingKey='xj_review_pending:'+me.user_id+':'+JSON.stringify([project,page,version]);
 const readHistory=async()=>{const response=await fetch(base+'changes/'+encodeURIComponent(project),{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('本页意见历史暂不可读');const data=await response.json();const rows=data.cases.filter(c=>c.events[0]?.kind==='REQUEST'&&c.events[0].payload.page===page&&c.events[0].payload.page_sha256===version);history.replaceChildren(...rows.map(c=>node('p',c.events[0].payload.request)));if(!rows.length)history.append(node('p','本页暂无已保存意见。'));return rows;};
 try{const rows=await readHistory(),pending=sessionStorage.getItem(pendingKey);if(pending&&rows.some(c=>c.events[0].payload.idempotency_key===pending))sessionStorage.removeItem(pendingKey);}catch(error){history.append(node('p',error.message));}
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
 if(sessionStorage.getItem(pendingKey))status.textContent='上次提交结果待核对；再次点击只查询原记录。';
 form.addEventListener('submit',async e=>{e.preventDefault();button.disabled=true;let committed=false;try{
  const previous=sessionStorage.getItem(pendingKey);
  if(previous){const rows=await readHistory(),found=rows.find(c=>c.events[0].payload.idempotency_key===previous);if(found){sessionStorage.removeItem(pendingKey);status.textContent='已读回上次保存的意见。编号：'+found.id;}else status.textContent='原提交结果仍待核对，未重复发送。';return;}
  const key=crypto.randomUUID();sessionStorage.setItem(pendingKey,key);
  const r=await fetch(base+'change_submit_idempotent',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('xj_csrf')||''},body:JSON.stringify({project,page,version,text:text.value,intent:intent.value,idempotency_key:key})});
  if(!r.ok){if(r.status<500)sessionStorage.removeItem(pendingKey);throw Error('意见未保存，请核实登录、权限或页面版本。');}
  const d=await r.json();committed=true;sessionStorage.removeItem(pendingKey);status.textContent='意见已归档。编号：'+d.id;text.value='';await readHistory();
 }catch(err){status.textContent=committed?'意见已保存，历史读取暂不可用；请重载查询。':sessionStorage.getItem(pendingKey)?'提交结果待核对，未自动重发；请保留草稿并查询原记录。':err.message;}finally{button.disabled=false;}});

}
})();
