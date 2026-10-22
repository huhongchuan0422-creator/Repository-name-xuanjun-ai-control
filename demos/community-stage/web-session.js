'use strict';
(()=>{
 const root=document.getElementById('community-session'), form=root.querySelector('form');
 const message=root.querySelector('[role=status]'), select=root.querySelector('select');
 const key='community-original-csrf';let csrf=sessionStorage.getItem(key)||'',generation=0,workspaces=[];
 const kind=location.pathname.endsWith('/community/portal')?'COMMUNITY':'MERCHANT';
 const configure=value=>{
  if(window.configureCommunityWorkbench)window.configureCommunityWorkbench(value);
  if(window.configureCommunityPortal)window.configureCommunityPortal(value);
  if(window.configureCommunityOnboarding)window.configureCommunityOnboarding(value);
  for(const button of root.querySelectorAll('button'))button.disabled=false;
 };
 async function call(action,body,t){
  const response=await fetch('/community-preview/community/session/'+action,{method:'POST',credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{})},body:JSON.stringify(body)});
  const value=await response.json();if(t!==generation)throw Error('身份已变化');
  if(!response.ok)throw Error(response.status===403?'登录已失效或没有权限，请重新登录。':'请求未确认，请检查状态后再操作。');
  return value.result;
 }
 function choose(){const workspace=select.value;configure(csrf?{csrf,...(workspace?{workspace}:{})}:null);}
 async function check(t){
  const result=await call('check',{},t);workspaces=result.workspaces.filter(w=>w.kind===kind);
  select.replaceChildren();for(const w of workspaces){const option=document.createElement('option');option.value=w.workspace;option.textContent=w.workspace;select.append(option);}
  const review=location.pathname.endsWith('/merchant/review');
  message.textContent=review?(result.reviewer?'已登录原平台审核账户。':'已登录；当前账户没有平台审核权限。'):(workspaces.length?'已登录，请选择已授权工作区。':'已登录；当前账户没有此角色的工作区。');
  choose();
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();const t=++generation;const data=new FormData(form);configure(null);
  try{const result=await call('login',{email:data.get('email'),password:data.get('password')},t);csrf=result.csrf;sessionStorage.setItem(key,csrf);form.reset();await check(t);}
  catch(_){csrf='';sessionStorage.removeItem(key);message.textContent='登录未确认，请核对原账户；未自动重试。';}
  finally{form.querySelector('[name=password]').value='';}
 });
 root.querySelector('[data-logout]').addEventListener('click',async()=>{
  const t=++generation;try{await call('logout',{},t);message.textContent='已退出登录。';}
  catch(_){message.textContent='退出结果未确认；请勿继续业务操作。';}
  finally{csrf='';sessionStorage.removeItem(key);select.replaceChildren();configure(null);}
 });
 select.addEventListener('change',choose);
 configure(null);if(csrf){const t=++generation;check(t).catch(()=>{csrf='';sessionStorage.removeItem(key);configure(null);message.textContent='原会话已失效，请重新登录。';});}
})();
