'use strict';
(()=>{
 const root=document.getElementById('community-session'), form=root.querySelector('form');
 const message=root.querySelector('[role=status]'), select=root.querySelector('select');
 const key='community-original-csrf';let csrf=sessionStorage.getItem(key)||'',generation=0,active=null,workspaces=[];
 const reviewerPage=location.pathname.endsWith('/merchant/review'),kind=location.pathname.endsWith('/community/portal')?'COMMUNITY':'MERCHANT';
 // Same-origin tabs share the HttpOnly cookie. Hold the browser lock until the
 // entire mutation response settles, so late Set-Cookie cannot overtake a
 // subsequent login/logout. No bearer, CSRF or identity travels on this channel.
 let coordinated=false,channel=null,tabId='';
 try{
  if(typeof navigator.locks?.request==='function'&&typeof BroadcastChannel==='function'){
   const tabWindow=window.top||window;
   tabId=tabWindow.__communityOriginalSessionTabId||(tabWindow.__communityOriginalSessionTabId=crypto.randomUUID());
   channel=new BroadcastChannel('community-original-session');coordinated=true;
  }
 }catch(_){/* Unavailable coordination must clear saved state before any IO. */}
 // Explicit selections only; these names were separately authorized by session/check.
 const financeSelectors={};
 if(kind==='MERCHANT')for(const [name,title]of [['provider','门店财务'],['merchant_bill','商家账单']]){
  const label=document.createElement('label'),selector=document.createElement('select');label.className='finance-session-selector';label.textContent=title;selector.setAttribute('aria-label',title);label.append(selector);root.append(label);financeSelectors[name]={label,selector};
  selector.addEventListener('change',()=>{if(active===null)configure(selectedContext());});
 }
 function resetFinanceSelectors(){
  const selected=workspaces.find(w=>w.workspace===select.value);
  for(const [name,{label,selector}]of Object.entries(financeSelectors)){
   selector.replaceChildren();const blank=document.createElement('option');blank.value='';blank.textContent='未选择（不启用）';selector.append(blank);
   const options=selected?.finance_options?.[name];
   if(Array.isArray(options))for(const item of options){if(!item||typeof item.workspace!=='string'||! /^[A-Za-z0-9_-]{1,64}$/.test(item.workspace))continue;const option=document.createElement('option');option.value=item.workspace;option.textContent=item.workspace;selector.append(option);}
   selector.value='';label.hidden=selector.children.length===1;
  }
 }
 // This panel extends the original session UI; it is not another login system.
 const adminTarget=document.getElementById('community-admin-permissions-content');const adminPanel=adminTarget&&typeof adminTarget.replaceChildren==='function'?adminTarget:document.createElement('section');adminPanel.hidden=true;if(!adminPanel.parentNode)root.append(adminPanel);
 let adminIdentity=null,adminCatalog=null,adminRecords=[],adminNextCursor=null,adminDaily=null,adminSettingsOpen=false,adminSettingsState='idle';
 const syncShell=value=>{
  const body=document.body,role=value?.role||(adminIdentity?.kind==='ROOT'?'COMMUNITY_ADMIN':null),logged=!!csrf;
  const admitted=logged&&(typeof value?.workspace==='string'&&value.workspace||(reviewerPage&&value?.reviewer===true));
  if(root.dataset)root.dataset.authenticated=logged?'true':'false';
  body?.classList?.toggle('admin-logged-in',logged);body?.classList?.toggle('admin-logged-out',!logged);
  body?.classList?.toggle('admin-no-workspace',logged&&!admitted);
  body?.classList?.toggle('admin-role-platform',logged&&['PLATFORM_OWNER','PLATFORM_REVIEWER'].includes(role));
  body?.classList?.toggle('admin-role-community',logged&&!['PLATFORM_OWNER','PLATFORM_REVIEWER'].includes(role));
  const label=['PLATFORM_OWNER','PLATFORM_REVIEWER'].includes(role)?'平台管理者后台':logged?'社区管理者后台':'待确认角色';
  for(const node of document.querySelectorAll?.('.admin-role-badge,.admin-brand-role')||[])node.textContent=label;
 };
 function adminReset(){adminIdentity=null;adminCatalog=null;adminRecords=[];adminNextCursor=null;adminDaily=null;adminSettingsOpen=false;adminSettingsState='idle';adminPanel.replaceChildren();adminPanel.hidden=true;}
 async function adminCall(operation,params,t){
  if(!current(t)||!csrf)throw Error('身份已变化');
  const response=await fetch('/community-preview/community/admin',{method:'POST',credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({operation,params})});
  const data=await response.json();if(!current(t))throw Error('身份已变化');
  if(!response.ok)throw Error('管理操作未确认，请查询当前状态；不会自动重放。');
  return data.result;
 }
 async function adminAction(work){
  if(active!==null||!coordinated||!adminIdentity||adminIdentity.kind!=='ROOT')return;
  const t=generation;active=t;controls();
  try{await navigator.locks.request('community-original-session',async()=>{if(current(t))await work(t);});}
  catch(_){if(current(t))message.textContent='管理员操作未确认，请刷新账户列表核实；未自动重试。';}
  finally{if(active===t)active=null;controls();}
 }
 async function adminRefresh(t){const page=await adminCall('list',{after_uid:''},t);adminRecords=page.records;adminNextCursor=page.has_more?page.next_cursor:null;adminDaily=page.daily_overview;publishAdminHomeMetrics();}
 const permissionDefinitions=[
  ['orders','订单查看与对账',value=>/(order|checkout|receipt|reconciliation|bill_)/.test(value)],
  ['refunds','退款与售后',value=>/refund/.test(value)],
  ['splits','微信分账设置与记录',value=>/(split|receiver|community_earnings)/.test(value)],
  ['advertising','广告管理与审核',value=>/(\.ad_|\.ads$|\.ads_page$|ad_report|ad_review|ad_state)/.test(value)],
  ['merchants','商家、门店与商品',value=>/(merchant|store|profile|item|price|staff|qr|storefront)/.test(value)],
  ['communities','社区运营与推广',value=>/(community_|promotion|referral|join|leave|members|notices|notice_read)/.test(value)],
  ['reviews','审核与用户查询',value=>/(review|platform_|onboarding)/.test(value)],
  ['projects','项目与履约资料',value=>/(project|fulfillment|saas-api|checklist|download)/.test(value)],
  ['other','其他基础业务',()=>true]
 ];
 function publishAdminHomeMetrics(){
  if(!adminDaily||typeof window.communityHomeMetrics!=='function')return;
  window.communityHomeMetrics({kind:'daily',...adminDaily});
 }
 window.communityLoadAdminHomeMetrics=()=>adminAction(async t=>{adminSettingsState='loading';if(adminSettingsOpen)adminRender();try{adminCatalog=await adminCall('catalog',{},t);await adminRefresh(t);adminSettingsState='ready';adminRender();}catch(error){adminSettingsState='error';adminRender();throw error;}});
 function permissionPicker(items,selected=[]){
  const box=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='业务权限';box.append(legend);box.className='admin-permission-groups';
  const groups=new Map(permissionDefinitions.map(([id,label])=>[id,{id,label,values:[]}]));
  for(const value of items){const definition=permissionDefinitions.find(([, ,match])=>match(value));groups.get(definition[0]).values.push(value);}
  const inputs=[];
  for(const group of groups.values()){
   if(!group.values.length)continue;
   const row=document.createElement('label'),input=document.createElement('input'),copy=document.createElement('span'),count=document.createElement('small');row.className='admin-permission-option permission-'+group.id;input.type='checkbox';input.dataset.permissionGroup=group.id;copy.textContent=group.label;count.textContent='包含 '+group.values.length+' 项相关操作';copy.append(count);row.append(input,copy);box.append(row);
   const included=group.values.filter(value=>selected.includes(value));input.checked=included.length===group.values.length;input.indeterminate=included.length>0&&!input.checked;let touched=false;input.addEventListener('change',()=>{touched=true;input.indeterminate=false;});inputs.push({input,group,preserved:included,touched:()=>touched});
  }
  return {box,inputs,values:()=>inputs.flatMap(({input,group,preserved,touched})=>input.indeterminate&&!touched()?preserved:input.checked?group.values:[])};
 }
 function scopePicker(items,selected=[]){
  const box=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='管理范围';box.append(legend);box.className='admin-scope-groups';const inputs=[];
  items.forEach((value,index)=>{const row=document.createElement('label'),input=document.createElement('input'),copy=document.createElement('span');row.className='admin-scope-option';input.type='checkbox';input.value=value;input.checked=selected.includes(value);copy.textContent='已授权业务范围 '+(index+1);row.append(input,copy);box.append(row);inputs.push(input);});
  if(!items.length){const empty=document.createElement('p');empty.textContent='当前尚未配置可分配的业务范围。';box.append(empty);}
  return {box,values:()=>inputs.filter(input=>input.checked).map(input=>input.value)};
 }
 function adminRender(){
  adminPanel.replaceChildren();adminPanel.hidden=!adminIdentity;
  if(!adminIdentity)return;
  const title=document.createElement('h3');title.textContent=adminIdentity.kind==='ROOT'?'本社区超级管理员':'本社区受限管理员';adminPanel.append(title);
  const scope=document.createElement('p');scope.textContent='只作用于当前社区项目，不包含服务器或其他项目权限。';adminPanel.append(scope);
  if(adminIdentity.kind!=='ROOT')return;
  const refresh=document.createElement('button'),settingsStatus=document.createElement('p');refresh.type='button';refresh.textContent='设置管理员';refresh.setAttribute('aria-expanded',adminSettingsOpen?'true':'false');settingsStatus.className='admin-settings-status';settingsStatus.setAttribute('role','status');adminPanel.append(refresh,settingsStatus);
  refresh.onclick=()=>{adminSettingsOpen=true;if(adminCatalog){adminSettingsState='ready';adminRender();return;}if(active!==null){adminSettingsState=adminSettingsState==='loading'?'loading':'busy';adminRender();return;}window.communityLoadAdminHomeMetrics();};
  if(!adminSettingsOpen){settingsStatus.textContent='点击“设置管理员”后，可添加管理员并设置具体业务权限。';return;}
  if(!adminCatalog){settingsStatus.textContent=adminSettingsState==='error'?'管理员设置读取失败，请点击“设置管理员”重试。':adminSettingsState==='busy'?'当前操作完成后，请再次点击“设置管理员”。':'正在读取管理员与权限设置…';return;}
  settingsStatus.textContent='可按业务功能设置权限；不会授予服务器或其他项目权限。';
  const f=document.createElement('form'),email=document.createElement('input'),password=document.createElement('input');f.className='admin-settings-form';
  email.type='email';email.required=true;email.placeholder='新管理员登录邮箱';email.autocomplete='off';email.setAttribute('aria-label','新管理员登录邮箱');
  password.type='text';password.required=true;password.minLength=12;password.maxLength=128;password.autocomplete='new-password';password.spellcheck=false;password.setAttribute('autocapitalize','none');password.placeholder='初始密码（可见，请核对后保存）';password.setAttribute('aria-label','新管理员初始密码');
  f.append(email,password);
  const businessCapabilities=adminCatalog.capabilities.filter(x=>!x.startsWith('/community/admin#')),capabilities=permissionPicker(businessCapabilities),scopes=scopePicker(adminCatalog.workspace_scopes);
  const templateLabel=document.createElement('label'),templateTitle=document.createElement('span'),template=document.createElement('select');templateLabel.className='admin-role-template';templateTitle.textContent='常用角色模板';for(const [value,label]of [['','请选择'],['viewer','只读查看'],['operator','社区运营'],['finance','财务分账'],['platform','平台管理']]){const option=document.createElement('option');option.value=value;option.textContent=label;template.append(option);}templateLabel.append(templateTitle,template);template.onchange=()=>{const enabled={viewer:['orders','communities'],operator:['orders','advertising','merchants','communities'],finance:['orders','refunds','splits'],platform:permissionDefinitions.map(x=>x[0])}[template.value]||[];for(const {input}of capabilities.inputs){input.indeterminate=false;input.checked=enabled.includes(input.dataset.permissionGroup);input.dispatchEvent(new Event('change'));}};
  f.append(templateLabel,capabilities.box,scopes.box);const create=document.createElement('button');create.type='submit';create.textContent='保存设置';f.append(create);adminPanel.append(f);
  f.onsubmit=event=>{event.preventDefault();if(active!==null||!f.reportValidity())return;const params={email:email.value,password:password.value,capabilities:capabilities.values(),workspace_scopes:scopes.values(),request_id:'admin_'+crypto.randomUUID().replaceAll('-','')};password.value='';void adminAction(async t=>{try{await adminCall('create',params,t);}finally{params.password='';}await adminRefresh(t);adminRender();});};
  for(const record of adminRecords){const row=document.createElement('div'),text=document.createElement('p');row.className='admin-manager-card';text.textContent=(record.login_label||'管理员账户')+' · '+(record.active?'已启用':'已撤销');row.append(text);if(record.kind==='DELEGATE'&&record.active){const cp=permissionPicker(businessCapabilities,record.capabilities),sp=scopePicker(adminCatalog.workspace_scopes,record.workspace_scopes);row.append(cp.box,sp.box);const save=document.createElement('button');save.type='button';save.textContent='保存权限';save.onclick=()=>adminAction(async t=>{await adminCall('grant',{uid:record.uid,capabilities:cp.values(),workspace_scopes:sp.values(),expected_revision:record.revision,request_id:'admin_'+crypto.randomUUID().replaceAll('-','')},t);await adminRefresh(t);adminRender();});const revoke=document.createElement('button');revoke.type='button';revoke.textContent='撤销此管理员';revoke.onclick=()=>{if(!confirm('确认撤销该社区管理员权限？'))return;void adminAction(async t=>{await adminCall('revoke',{uid:record.uid,expected_revision:record.revision,request_id:'admin_'+crypto.randomUUID().replaceAll('-','')},t);await adminRefresh(t);adminRender();});};row.append(save,revoke);}adminPanel.append(row);}
  if(adminNextCursor){const more=document.createElement('button');more.type='button';more.textContent='加载下一页管理员';more.onclick=()=>adminAction(async t=>{const page=await adminCall('list',{after_uid:adminNextCursor},t);adminRecords.push(...page.records);adminNextCursor=page.has_more?page.next_cursor:null;publishAdminHomeMetrics();adminRender();});adminPanel.append(more);}
 }

 const current=t=>t===generation;
 const controls=()=>{
  for(const button of root.querySelectorAll('button'))button.disabled=active!==null||!coordinated;
  select.disabled=active!==null||!csrf||!workspaces.length;
  for(const {selector}of Object.values(financeSelectors))selector.disabled=active!==null||!csrf||!workspaces.length;
 };
 const configure=value=>{
  syncShell(value);
  if(window.communityHomeContext)window.communityHomeContext(value?{...value,...(adminIdentity?{admin:{kind:adminIdentity.kind,capabilities:adminIdentity.capabilities}}:{})}:null);
  if(window.configureCommunityWorkbench)window.configureCommunityWorkbench(value);
  if(window.configureCommunityPortal)window.configureCommunityPortal(value);
  if(window.configureCommunityOnboarding)window.configureCommunityOnboarding(value);
  controls();
 };
 const clear=text=>{adminReset();reviewerAccess=false;csrf='';sessionStorage.removeItem(key);workspaces=[];select.replaceChildren();resetFinanceSelectors();configure(null);message.textContent=text;};
 if(channel)channel.onmessage=event=>{
  if(event.data?.type!=='changed'||event.data.tabId===tabId)return;
  generation++;clear('其他窗口已变更原会话，请重新登录。');
 };
 async function call(action,body,t,value=csrf){
  if(!current(t))throw Error('身份已变化');
  const response=await fetch('/community-preview/community/session/'+action,{method:'POST',credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json',...(value?{'X-CSRF-Token':value}:{})},body:JSON.stringify(body)});
  const result=await response.json();if(!current(t))throw Error('身份已变化');
  if(!response.ok)throw Error(response.status===403?'登录已失效或没有权限，请重新登录。':'请求未确认，请检查状态后再操作。');
  return result.result;
 }
 // Role is navigation metadata from this session check, never a grant.
 const communityRoles=new Set(['CUSTOMER','COMMUNITY_ADMIN','MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER']);
 function selectedContext(){
  if(!csrf)return null;
  const selected=workspaces.find(w=>w.workspace===select.value);
  const financial={};
  if(selected&&kind==='MERCHANT')for(const [name,key]of [['provider','providerWorkspace'],['merchant_bill','merchantBillWorkspace']]){
   const value=financeSelectors[name].selector.value,options=selected.finance_options?.[name];
   if(value&&Array.isArray(options)&&options.some(item=>item&&item.workspace===value))financial[key]=value;
  }
  return {csrf,...(selected?{workspace:selected.workspace}:{}),...(kind==='COMMUNITY'?{role:selected&&communityRoles.has(selected.role)?selected.role:null,reviewer:reviewerAccess}:reviewerPage&&reviewerAccess?{role:'PLATFORM_REVIEWER',reviewer:true}:{}),...financial};
 }
 function choose(){
  if(active!==null)return;
  resetFinanceSelectors();configure(selectedContext());
 }
 async function check(t){
  const result=await call('check',{},t,csrf);if(!current(t))return;
  adminIdentity=result.community_admin||null;reviewerAccess=result.reviewer===true;adminRender();
  workspaces=result.workspaces.filter(w=>w.kind===kind);
  select.replaceChildren();
  if(!workspaces.length){const option=document.createElement('option');option.value='';option.textContent='暂无管理权限';select.append(option);}
  else for(const w of workspaces){const option=document.createElement('option');option.value=w.workspace;option.textContent=({PLATFORM_OWNER:'平台管理',PLATFORM_REVIEWER:'商家审核',COMMUNITY_ADMIN:'社区管理',MERCHANT_ADMIN:'商家管理',CUSTOMER:'个人中心'})[w.role]||'管理后台';select.append(option);}
  resetFinanceSelectors();
  const review=location.pathname.endsWith('/merchant/review');
  message.textContent=review?(result.reviewer?'已进入商家审核。':'当前账号暂无商家审核权限。'):(workspaces.length?'已登录。':'当前账号暂无管理权限。');
  configure(selectedContext());
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
    }finally{if(issued)channel.postMessage({type:'changed',tabId});}
   });
  }catch(_){if(current(t))clear(action==='login'?'登录未确认，请核对原账户；未自动重试。':'退出结果未确认；请勿继续业务操作。');}
  finally{
   if(active===t)active=null;
   if(current(t))form.querySelector('[name=password]').value='';
   if(current(t)&&adminIdentity?.kind==='ROOT'&&!adminCatalog)queueMicrotask(()=>window.communityLoadAdminHomeMetrics());
   controls();
  }
 }
 let reviewerAccess=false;

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
