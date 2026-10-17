'use strict';
(() => {
  const $=id=>document.getElementById(id),reviewMode=location.pathname==='/merchant/review';
  const states={DRAFT:'草稿',SUBMITTED:'待审核',IN_REVIEW:'审核中',CORRECTION_REQUIRED:'待补件',REJECTED:'已驳回',APPROVED:'入驻审核通过'};
  let current=null,catalog=null,csrf='',busy=false,generation=0,cursor=null;
  // The existing customer host passes its current CSRF value after login. No
  // second login form, password store or reusable browser token is introduced.
  window.configureCommunityOnboarding=context=>{generation++;busy=false;csrf=typeof context?.csrf==='string'?context.csrf:'';
    current=null;cursor=null;$('detail').hidden=true;$('openingActions').hidden=true;$('moreApplications').hidden=true;
    for(const id of ['mine','applications','summary','materials','reviewNote','opening','openingWorkspace'])$(id).replaceChildren();
    $('applicationTitle').textContent='入驻申请';$('applicationState').textContent='';
    for(const id of ['legal_name','store_name','address','contact','note'])$(id).value='';setForm(null);$('statusFilter').value='ALL';
    message('正在读取当前账号的入驻信息…');return load();};
  function message(text){$('status').textContent=text;}
  async function request(operation,params={}) {
    const version=generation;
    const response=await fetch('/merchant/onboarding',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({operation,params})});
    if(version!==generation)throw Error('登录状态已变化，请重新读取。');
    if(response.status===403)throw Error('请先登录客户中心，并确认当前账号拥有此项权限。');
    if(!response.ok)throw Error(response.status===400?'资料、状态或版本不符合要求，请刷新后检查。':'服务暂不可用，结果可能尚未确认，请先刷新状态。');
    const reply=await response.json();
    if(version!==generation)throw Error('登录状态已变化，请重新读取。');
    if(reply.payment_enabled!==false||!reply.result)throw Error('服务返回无效，请刷新状态。');
    return reply.result;
  }
  async function run(action){if(busy)return;const version=generation;busy=true;$('statusFilter').disabled=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{await action();}catch(error){if(version===generation)message(error.message);}finally{if(version===generation){busy=false;$('statusFilter').disabled=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);
      $('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=!!current&&!['DRAFT','CORRECTION_REQUIRED'].includes(current.status));}}}
  function button(text,handler){const b=document.createElement('button');b.type='button';b.textContent=text;b.addEventListener('click',()=>run(handler));return b;}
  function draftFields(){return Object.fromEntries(['legal_name','store_name','address','contact'].map(k=>[k,$(k).value]));}
  function setForm(app){for(const [k,v] of Object.entries(app?.fields||{}))if($(k))$(k).value=v;
    $('entity_type').value=app?.entity_type||'ENTERPRISE';$('category').value=app?.category||'GENERAL';$('delegated').checked=app?.delegated||false;}
  function render(app){current=app;$('detail').hidden=!app;if(!app)return;
    $('applicationTitle').textContent=app.fields.store_name||'入驻申请';$('applicationState').textContent=states[app.status]||app.status;
    $('summary').replaceChildren();for(const [label,value] of [['主体名称',app.fields.legal_name],['门店名称',app.fields.store_name],['经营地址',app.fields.address],['联系人',app.fields.contact]]){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('summary').append(dt,dd);}
    $('reviewNote').textContent=app.reviewer_note?'审核说明：'+app.reviewer_note:'';
    const editable=['DRAFT','CORRECTION_REQUIRED'].includes(app.status),reviewable=['SUBMITTED','IN_REVIEW'].includes(app.status);
    $('submitApplication').hidden=reviewMode||!editable;$('reviewActions').hidden=!reviewMode||!reviewable&&app.status!=='APPROVED';
    document.querySelectorAll('[data-action]').forEach(b=>{b.hidden=app.status==='APPROVED'&&b.dataset.action!=='CORRECTION';
      if(b.dataset.action==='CORRECTION')b.textContent=app.status==='APPROVED'?'要求重新核验':'要求补件';});
    $('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=!editable);
    $('opening').textContent=app.status!=='APPROVED'?'':app.opening_state==='OPENED'?'商家工作台已开通；微信特约商户进件和收款权限尚未核验。':
      app.opening_state==='OPENING_PENDING'?'入驻审核已通过；工作台开通尚未完成，请由平台核对后恢复。':
      app.opening_state==='ACCESS_SUSPENDED'?'工作台访问已暂停，请联系平台核验资料与项目权限。':'平台入驻审核已通过；工作台权限待绑定。微信特约商户进件和收款权限尚未核验。';
    $('openingActions').hidden=!reviewMode||app.status!=='APPROVED'||app.opening_state==='OPENED'||!app.opening_workspaces?.length;
    $('openingWorkspace').replaceChildren();for(const workspace of app.opening_workspaces||[]){const option=document.createElement('option');option.value=workspace;option.textContent=workspace;$('openingWorkspace').append(option);}
    $('materials').replaceChildren();
    for(const kind of app.required_materials){const description=catalog.materials.find(m=>m.id===kind),record=app.materials[kind];
      const row=document.createElement('div');row.className='material';row.dataset.kind=kind;
      const title=document.createElement('strong');title.textContent=description?.title||kind;row.append(title);
      const state=document.createElement('p');state.textContent=record?`已上传 · ${record.review==='ACCEPTED'?'资料审核通过':record.review==='NEEDS_CORRECTION'?'需要补件':'待核验'}${record.review_note?' · '+record.review_note:''}`:'待上传';row.append(state);
      if(record)row.append(button('查看已提交资料',async()=>{const result=await request('download',{application:current.application,kind});
        if(!['application/pdf','image/png','image/jpeg'].includes(result.mime))throw Error('资料格式无效');
        const bytes=Uint8Array.from(atob(result.content_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:result.mime}));
        const a=document.createElement('a');a.href=url;a.download=kind+(result.mime==='application/pdf'?'.pdf':result.mime==='image/png'?'.png':'.jpg');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
      if(!reviewMode&&editable){const input=document.createElement('input');input.type='file';input.accept='.pdf,.png,.jpg,.jpeg';input.setAttribute('aria-label',title.textContent);
        const expiry=document.createElement('input');expiry.type='date';expiry.setAttribute('aria-label','资料有效期');const expiryLabel=document.createElement('label');expiryLabel.textContent='有效期至（长期有效可留空）';expiryLabel.append(expiry);row.append(input,expiryLabel);
        row.append(button('上传资料',async()=>{const file=input.files[0];if(!file||file.size<1||file.size>5000000)throw Error('请选择不超过5 MB的资料。');
          const version=generation,application=current.application,revision=current.revision;
          const bytes=new Uint8Array(await file.arrayBuffer());if(version!==generation)throw Error('登录状态已变化，请重新读取。');
          let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
          const expires_at=expiry.value?Math.floor(Date.parse(expiry.value+'T23:59:59+08:00')/1000):null;
          render(await request('upload',{application,revision,kind,content_base64:btoa(binary),expires_at}));message('资料已保存。');}));}
      if(reviewMode&&reviewable&&record){for(const [label,decision] of [['资料通过','ACCEPTED'],['资料需补充','NEEDS_CORRECTION']])row.append(button(label,async()=>{
          const note=$('note').value.trim();if(!note)throw Error('请填写本次审核说明。');render(await request('review_material',{application:current.application,revision:current.revision,kind,decision,note}));message('资料审核结果已保存。');}));}
      $('materials').append(row);
    }
    if(!reviewMode)setForm(app);
  }
  async function list(append=false){const result=await request(reviewMode?'review_list':'mine',{status:$('statusFilter').value,...(append&&cursor?{cursor}:{})}),target=$(reviewMode?'applications':'mine');if(!append)target.replaceChildren();
    for(const app of result.applications)target.append(button((app.fields.store_name||'未命名申请')+' · '+(states[app.status]||app.status),async()=>{render(await request(reviewMode?'review_read':'read',{application:app.application}));}));
    cursor=result.next_cursor||null;$('moreApplications').hidden=!cursor;
    if(!reviewMode&&!append){render(result.applications[0]||null);}
    message(result.applications.length?'已读取最新入驻状态。':reviewMode?'暂无入驻申请。':'尚无申请，请填写经营信息并保存草稿。');}
  async function load(){return run(async()=>{catalog=await request('catalog');await list();});}
  $('profile').addEventListener('submit',event=>{event.preventDefault();run(async()=>{render(await request('save',{application:current?.application||null,revision:current?.revision||0,
    fields:draftFields(),entity_type:$('entity_type').value,category:$('category').value,delegated:$('delegated').checked}));message('草稿已保存，请按清单上传资料。');});});
  $('newApplication').addEventListener('click',()=>{if(busy)return;current=null;for(const key of ['legal_name','store_name','address','contact'])$(key).value='';setForm(null);$('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=false);render(null);message('请填写新申请。');});
  $('submitApplication').addEventListener('click',()=>run(async()=>{render(await request('submit',{application:current.application,revision:current.revision}));message('申请已提交，请等待平台审核。');}));
  document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>run(async()=>{if(!$('note').value.trim())throw Error('请填写审核说明。');
    render(await request('review',{application:current.application,revision:current.revision,action:b.dataset.action,note:$('note').value.trim()}));message('审核处理已保存。');})));
  $('reloadQueue').addEventListener('click',()=>run(list));$('queue').hidden=!reviewMode;$('applicant').hidden=reviewMode;$('title').textContent=reviewMode?'商家入驻审核':'申请商家入驻';
  $('reloadMine').addEventListener('click',()=>run(list));
  $('statusFilter').addEventListener('change',()=>run(list));$('moreApplications').addEventListener('click',()=>run(()=>list(true)));
  $('openWorkbench').addEventListener('click',()=>run(async()=>{render(await request('open_workbench',{application:current.application,revision:current.revision,workspace:$('openingWorkspace').value}));message('工作台开通状态已更新。');}));
  load();
})();
