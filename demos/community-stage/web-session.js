'use strict';
(()=>{
 const root=document.getElementById('community-session'), form=root.querySelector('form');
 const message=root.querySelector('[role=status]'), select=root.querySelector('select');
 const key='community-original-csrf';let csrf=sessionStorage.getItem(key)||'',generation=0,active=null,workspaces=[];
 const kind=location.pathname.endsWith('/community/portal')?'COMMUNITY':'MERCHANT';
 // Same-origin tabs share the HttpOnly cookie. Hold the browser lock until the
 // entire mutation response settles, so late Set-Cookie cannot overtake a
 // subsequent login/logout. No bearer, CSRF or identity travels on this channel.
 let coordinated=false,channel=null;
 try{
  if(typeof navigator.locks?.request==='function'&&typeof BroadcastChannel==='function'){
   channel=new BroadcastChannel('community-original-session');coordinated=true;
  }
 }catch(_){/* Unavailable coordination must clear saved state before any IO. */}
 const current=t=>t===generation;
 const controls=()=>{
  for(const button of root.querySelectorAll('button'))button.disabled=active!==null||!coordinated;
  select.disabled=active!==null||!csrf||!workspaces.length;
 };
 const configure=value=>{
  if(window.configureCommunityWorkbench)window.configureCommunityWorkbench(value);
  if(window.configureCommunityPortal)window.configureCommunityPortal(value);
  if(window.configureCommunityOnboarding)window.configureCommunityOnboarding(value);
  controls();
 };
 const clear=text=>{csrf='';sessionStorage.removeItem(key);workspaces=[];select.replaceChildren();configure(null);message.textContent=text;};
 if(channel)channel.onmessage=event=>{
  if(event.data!=='changed')return;
  generation++;clear('其他窗口已变更原会话，请重新登录。');
 };
 async function call(action,body,t,value=csrf){
  if(!current(t))throw Error('身份已变化');
  const response=await fetch('/community-preview/community/session/'+action,{method:'POST',credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json',...(value?{'X-CSRF-Token':value}:{})},body:JSON.stringify(body)});
  const result=await response.json();if(!current(t))throw Error('身份已变化');
  if(!response.ok)throw Error(response.status===403?'登录已失效或没有权限，请重新登录。':'请求未确认，请检查状态后再操作。');
  return result.result;
 }
 function choose(){
  if(active!==null)return;
  const workspace=select.value;
  configure(csrf?{csrf,...(workspaces.some(w=>w.workspace===workspace)?{workspace}:{})}:null);
 }
 async function check(t){
  const result=await call('check',{},t,csrf);if(!current(t))return;
  workspaces=result.workspaces.filter(w=>w.kind===kind);
  select.replaceChildren();for(const w of workspaces){const option=document.createElement('option');option.value=w.workspace;option.textContent=w.workspace;select.append(option);}
  const review=location.pathname.endsWith('/merchant/review');
  message.textContent=review?(result.reviewer?'已登录原平台审核账户。':'已登录；当前账户没有平台审核权限。'):(workspaces.length?'已登录，请选择已授权工作区。':'已登录；当前账户没有此角色的工作区。');
  const workspace=select.value;
  configure({csrf,...(workspace?{workspace}:{})});
 }
 async function mutation(action,body){
  // This guard also rejects synthetic submit/click events on disabled buttons.
  if(active!==null||!coordinated)return;
  const t=++generation,previous=csrf;active=t;clear(action==='login'?'正在登录…':'正在退出…');
  try{
   await navigator.locks.request('community-original-session',async()=>{
    if(!current(t))return;
    let issued=false;
    try{
     issued=true;const result=await call(action,body,t,action==='logout'?previous:'');
     if(!current(t))return;
     if(action==='logout'){clear('已退出登录。');return;}
     if(typeof result.csrf!=='string'||!result.csrf)throw Error('原会话未确认');
     csrf=result.csrf;sessionStorage.setItem(key,csrf);form.reset();await check(t);
    }finally{if(issued)channel.postMessage('changed');}
   });
  }catch(_){if(current(t))clear(action==='login'?'登录未确认，请核对原账户；未自动重试。':'退出结果未确认；请勿继续业务操作。');}
  finally{
   if(active===t)active=null;
   if(current(t))form.querySelector('[name=password]').value='';
   controls();
  }
 }
 form.addEventListener('submit',event=>{
  event.preventDefault();if(active!==null||!coordinated)return;
  const data=new FormData(form);void mutation('login',{email:data.get('email'),password:data.get('password')});
 });
 root.querySelector('[data-logout]').addEventListener('click',()=>{void mutation('logout',{});});
 select.addEventListener('change',choose);
 configure(null);
 if(!coordinated){clear('当前浏览器不支持安全会话协调，请使用新版浏览器登录。');return;}
 if(csrf){const t=++generation;void check(t).catch(()=>{if(current(t))clear('原会话已失效，请重新登录。');});}
})();
