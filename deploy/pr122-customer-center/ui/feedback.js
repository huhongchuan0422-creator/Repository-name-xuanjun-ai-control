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
 const heading=node('h2','对本页提出整改意见'),form=document.createElement('form'),label=node('label','请描述需要调整的位置与预期效果'),text=document.createElement('textarea'),button=node('button','提交整改意见'),status=node('p','');
 text.required=true;text.maxLength=4000;label.append(text);button.type='submit';const intentLabel=node('label','意见类型'),intent=document.createElement('select');for(const [value,title] of [['RECTIFICATION','原项目整改意见'],['NEW_ORDER','独立新增功能需求']]){const option=node('option',title);option.value=value;intent.append(option);}intentLabel.append(intent);form.append(intentLabel,label,button);slot.append(heading,form,status);
 const fees=node('a','查看本项目整改费用明细');fees.href='/customer/center/#changes';slot.append(fees);
 form.addEventListener('submit',async e=>{e.preventDefault();button.disabled=true;try{
  const r=await fetch(base+'change_submit',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':sessionStorage.getItem('xj_csrf')||''},body:JSON.stringify({project,page,version,text:text.value,intent:intent.value})});const d=await r.json();if(!r.ok)throw Error(d.error||'提交未完成');status.textContent='意见已归档，等待工作量及范围评估。尚未收费或执行。编号：'+d.id;text.value='';
 }catch(err){status.textContent=err.message;}finally{button.disabled=false;}});
}
})();
