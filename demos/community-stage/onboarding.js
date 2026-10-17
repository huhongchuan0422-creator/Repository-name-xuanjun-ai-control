'use strict';
(() => {
  const $=id=>document.getElementById(id),reviewMode=location.pathname==='/merchant/review';
  const states={DRAFT:'草稿',SUBMITTED:'待审核',IN_REVIEW:'审核中',CORRECTION_REQUIRED:'待补件',REJECTED:'已驳回',APPROVED:'入驻审核通过'};
  let current=null,catalog=null,csrf='',busy=false,generation=0,cursor=null,wechatRecord=null;
  const wechatControls=new Map();
  let materialContext=0;
  const passport='IDENTIFICATION_TYPE_OVERSEA_PASSPORT';
  const controlValue=path=>wechatControls.get(path)?.value||'';
  function materialKinds(app){
    const kinds=new Set([...app.required_materials,'mini_program_screenshot',...Object.keys(app.materials)]);
    if(controlValue('contact_info.contact_type')==='SUPER'){kinds.add('operator_identity');if(controlValue('contact_info.contact_id_doc_type')!==passport)kinds.add('operator_identity_back');}
    if(app.entity_type==='ENTERPRISE')for(let i=0;i<4;i++){
      const prefix='subject_info.ubo_info_list.'+i+'.';
      if([...wechatControls].some(([path,input])=>path.startsWith(prefix)&&input.type!=='hidden'&&input.value)){kinds.add('ubo_'+(i+1)+'_front');if(controlValue(prefix+'ubo_id_doc_type')!==passport)kinds.add('ubo_'+(i+1)+'_back');}
    }
    return [...kinds].filter(kind=>catalog.materials.some(m=>m.id===kind));
  }
  function clearWechat(){materialContext++;wechatRecord=null;for(const e of wechatControls.values())e.value='';$('wechatState').textContent='';$('wechatOpinion').value='';}
  // The existing customer host passes its current CSRF value after login. No
  // second login form, password store or reusable browser token is introduced.
  window.configureCommunityOnboarding=context=>{generation++;busy=false;csrf=typeof context?.csrf==='string'?context.csrf:'';
    clearWechat();current=null;cursor=null;$('detail').hidden=true;$('openingActions').hidden=true;$('moreApplications').hidden=true;
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
    $('identity_type').value=app?.identity_type||'IDENTIFICATION_TYPE_IDCARD';$('entity_type').value=app?.entity_type||'ENTERPRISE';$('category').value=app?.category||'GENERAL';$('delegated').checked=app?.delegated||false;}
  function render(app){
    if(current?.application!==app?.application)clearWechat();current=app;$('detail').hidden=!app;if(!app)return;
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
    if(app.opening_state==='OPENED'){const link=document.createElement('a');link.href='/merchant/workbench';link.textContent='进入商家工作台';$('opening').append(document.createTextNode(' '),link);}
    $('openingActions').hidden=!reviewMode||app.status!=='APPROVED'||app.opening_state==='OPENED'||!app.opening_workspaces?.length;
    $('openingWorkspace').replaceChildren();for(const workspace of app.opening_workspaces||[]){const option=document.createElement('option');option.value=workspace;option.textContent=workspace;$('openingWorkspace').append(option);}
    refreshConditions();
    if(!reviewMode)setForm(app);
  }
  function renderMaterials(app){
    if(!app)return;
    const editable=['DRAFT','CORRECTION_REQUIRED'].includes(app.status),reviewable=['SUBMITTED','IN_REVIEW'].includes(app.status);
    $('materials').replaceChildren();
    for(const kind of materialKinds(app)){const description=catalog.materials.find(m=>m.id===kind),record=app.materials[kind];
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
          const version=generation,context=materialContext,application=current.application,revision=current.revision;
          const bytes=new Uint8Array(await file.arrayBuffer());if(version!==generation||context!==materialContext||application!==current?.application)throw Error('资料条件已变化，请重新选择文件。');
          let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
          const expires_at=expiry.value?Math.floor(Date.parse(expiry.value+'T23:59:59+08:00')/1000):null;
          const result=await request('upload',{application,revision,kind,content_base64:btoa(binary),expires_at});
          if(version!==generation||context!==materialContext||application!==current?.application)throw Error('资料条件已变化；上传结果请刷新后核对。');
          render(result);message('资料已保存。');}));}
      if(reviewMode&&reviewable&&record){for(const [label,decision] of [['资料通过','ACCEPTED'],['资料需补充','NEEDS_CORRECTION']])row.append(button(label,async()=>{
          const note=$('note').value.trim();if(!note)throw Error('请填写本次审核说明。');render(await request('review_material',{application:current.application,revision:current.revision,kind,decision,note}));message('资料审核结果已保存。');}));}
      $('materials').append(row);
    }
  }
  async function list(append=false){const result=await request(reviewMode?'review_list':'mine',{status:$('statusFilter').value,...(append&&cursor?{cursor}:{})}),target=$(reviewMode?'applications':'mine');if(!append)target.replaceChildren();
    for(const app of result.applications)target.append(button((app.fields.store_name||'未命名申请')+' · '+(states[app.status]||app.status),async()=>{render(await request(reviewMode?'review_read':'read',{application:app.application}));}));
    cursor=result.next_cursor||null;$('moreApplications').hidden=!cursor;
    if(!reviewMode&&!append){render(result.applications[0]||null);}
    message(result.applications.length?'已读取最新入驻状态。':reviewMode?'暂无入驻申请。':'尚无申请，请填写经营信息并保存草稿。');}
  async function load(){return run(async()=>{catalog=await request('catalog');await list();});}
  $('profile').addEventListener('submit',event=>{event.preventDefault();run(async()=>{render(await request('save',{application:current?.application||null,revision:current?.revision||0,
    identity_type:$('identity_type').value,fields:draftFields(),entity_type:$('entity_type').value,category:$('category').value,delegated:$('delegated').checked}));message('草稿已保存，请按清单上传资料。');});});
  $('newApplication').addEventListener('click',()=>{if(busy)return;current=null;for(const key of ['legal_name','store_name','address','contact'])$(key).value='';setForm(null);$('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=false);render(null);message('请填写新申请。');});
  $('submitApplication').addEventListener('click',()=>run(async()=>{render(await request('submit',{application:current.application,revision:current.revision}));message('申请已提交，请等待平台审核。');}));
  document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>run(async()=>{if(!$('note').value.trim())throw Error('请填写审核说明。');
    render(await request('review',{application:current.application,revision:current.revision,action:b.dataset.action,note:$('note').value.trim()}));message('审核处理已保存。');})));
  $('reloadQueue').addEventListener('click',()=>run(list));$('queue').hidden=!reviewMode;$('applicant').hidden=reviewMode;$('title').textContent=reviewMode?'商家入驻审核':'申请商家入驻';
  $('reloadMine').addEventListener('click',()=>run(list));
  $('statusFilter').addEventListener('change',()=>run(list));$('moreApplications').addEventListener('click',()=>run(()=>list(true)));
  $('openWorkbench').addEventListener('click',()=>run(async()=>{render(await request('open_workbench',{application:current.application,revision:current.revision,workspace:$('openingWorkspace').value}));message('工作台开通状态已更新。');}));
  const definitions=[
    ['contact_info.contact_type','管理员类型：LEGAL 法人 / SUPER 经办人'],['contact_info.contact_id_doc_type','经办人证件类型（官方枚举）'],['contact_info.contact_id_number','经办人证件号码'],['contact_info.contact_period_begin','经办人证件有效期开始'],['contact_info.contact_period_end','经办人证件有效期结束或长期'],['contact_info.contact_name','超级管理员姓名'],['contact_info.mobile_phone','超级管理员手机'],['contact_info.contact_email','超级管理员邮箱'],
    ['subject_info.business_license_info.license_number','统一社会信用代码或注册号'],['subject_info.business_license_info.merchant_name','营业执照商户名称'],['subject_info.business_license_info.legal_person','法定代表人或经营者姓名'],['subject_info.business_license_info.license_address','营业执照注册地址'],['subject_info.business_license_info.period_begin','营业执照有效期开始'],['subject_info.business_license_info.period_end','营业执照有效期结束或长期'],
    ['subject_info.identity_info.id_doc_type','法人证件类型（身份证 IDENTIFICATION_TYPE_IDCARD 或其他官方枚举）'],['subject_info.identity_info.id_doc_info.id_doc_name','其他证件姓名'],['subject_info.identity_info.id_doc_info.id_doc_number','其他证件号码'],['subject_info.identity_info.id_doc_info.id_doc_address','其他证件住址（企业适用）'],['subject_info.identity_info.id_doc_info.doc_period_begin','其他证件有效期开始'],['subject_info.identity_info.id_doc_info.doc_period_end','其他证件有效期结束或长期'],['subject_info.identity_info.id_card_info.id_card_name','经营者或法人证件姓名'],['subject_info.identity_info.id_card_info.id_card_number','经营者或法人身份证号'],['subject_info.identity_info.id_card_info.id_card_address','身份证住址（企业适用）'],['subject_info.identity_info.id_card_info.card_period_begin','身份证有效期开始'],['subject_info.identity_info.id_card_info.card_period_end','身份证有效期结束或长期'],
    ['business_info.merchant_shortname','商户简称'],['business_info.service_phone','客服电话'],['business_info.sales_info.mini_program_info.mini_program_appid','服务商小程序AppID'],['settlement_info.settlement_id','微信结算规则编号'],['settlement_info.qualification_type','微信结算行业名称'],
    ['bank_account_info.bank_account_type','账户类型：BANK_ACCOUNT_TYPE_CORPORATE 或 BANK_ACCOUNT_TYPE_PERSONAL'],['bank_account_info.account_name','结算开户名称'],['bank_account_info.account_bank','开户银行'],['bank_account_info.bank_branch_id','支行联行号（银行要求时填写）'],['bank_account_info.bank_name','开户银行全称（银行要求时填写）'],['bank_account_info.account_number','结算银行账号']];
  for(let i=0;i<4;i++)for(const [field,title]of [['ubo_id_doc_type','证件类型'],['ubo_id_doc_name','姓名'],['ubo_id_doc_number','证件号'],['ubo_id_doc_address','住址'],['ubo_period_begin','证件有效期开始'],['ubo_period_end','证件有效期结束或长期']])definitions.push(['subject_info.ubo_info_list.'+i+'.'+field,'受益人'+(i+1)+'：'+title+'（仅非单一法人受益人时填写完整列表）']);
  for(const [path,title]of definitions){const label=document.createElement('label');label.textContent=title;const input=document.createElement('input');input.autocomplete='off';input.dataset.path=path;input.maxLength=512;wechatControls.set(path,input);label.append(input);$('wechatFields').append(label);}
  const mediaFields={business_license:'subject_info.business_license_info.license_copy',identity_front:'subject_info.identity_info.id_card_info.id_card_copy',identity_back:'subject_info.identity_info.id_card_info.id_card_national',mini_program_screenshot:'business_info.sales_info.mini_program_info.mini_program_pics'};
  Object.assign(mediaFields,{operator_identity:'contact_info.contact_id_doc_copy',operator_identity_back:'contact_info.contact_id_doc_copy_back',operator_authorization:'contact_info.business_authorization_letter',industry_permit:'settlement_info.qualifications'});
  for(let i=0;i<4;i++){mediaFields['ubo_'+(i+1)+'_front']='subject_info.ubo_info_list.'+i+'.ubo_id_doc_copy';mediaFields['ubo_'+(i+1)+'_back']='subject_info.ubo_info_list.'+i+'.ubo_id_doc_copy_back';}
  for(const [kind,path]of Object.entries(mediaFields)){const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.path=path;wechatControls.set(path,hidden);$('wechatFields').append(hidden);const button=document.createElement('button');button.type='button';button.textContent='同步已上传的'+(({business_license:'营业执照',identity_front:'身份证人像面',identity_back:'身份证国徽面',mini_program_screenshot:'小程序页面截图'})[kind]||kind);button.onclick=()=>run(async()=>{if(!current)throw Error('先打开申请');const context=materialContext,application=current.application,type=controlValue('subject_info.identity_info.id_doc_type')||current.identity_type||'IDENTIFICATION_TYPE_IDCARD';const r=await request('wechat_media',{application,kind});if(context!==materialContext||application!==current?.application)throw Error('资料条件已变化，请重新同步。');if(kind==='identity_front'||kind==='identity_back'){if(type!=='IDENTIFICATION_TYPE_IDCARD'){const target='subject_info.identity_info.id_doc_info.'+(kind==='identity_front'?'id_doc_copy':'id_doc_copy_back');setPath((wechatRecord??={version:0,profile:{}}).profile??={},target,r.media_id);}else hidden.value=r.media_id;}else hidden.value=r.media_id;message('资料已上传微信；请保存微信资料草稿。');});$('wechatMedia').append(button);}
  function refreshConditions(){
    for(const [path,input]of wechatControls)if(path.startsWith('subject_info.ubo_info_list.')&&input.type!=='hidden')input.parentNode.hidden=current?.entity_type!=='ENTERPRISE';
    if(current)renderMaterials(current);
  }
  for(const [path,input]of wechatControls)if(input.type!=='hidden')input.addEventListener('input',()=>{
    materialContext++;
    if(path.endsWith('id_doc_type')){
      const prefix=path.slice(0,path.lastIndexOf('.')+1);
      for(const [other,field]of wechatControls)if(field.type==='hidden'&&(other.startsWith(prefix)||path==='subject_info.identity_info.id_doc_type'&&other.startsWith('subject_info.identity_info.')))field.value='';
      if(path==='subject_info.identity_info.id_doc_type'&&wechatRecord?.profile?.subject_info?.identity_info){delete wechatRecord.profile.subject_info.identity_info.id_doc_info?.id_doc_copy;delete wechatRecord.profile.subject_info.identity_info.id_doc_info?.id_doc_copy_back;}
    }
    for(let i=0;i<4;i++){const prefix='subject_info.ubo_info_list.'+i+'.';if(![...wechatControls].some(([p,e])=>p.startsWith(prefix)&&e.type!=='hidden'&&e.value))for(const [p,e]of wechatControls)if(p.startsWith(prefix)&&e.type==='hidden')e.value='';}
    refreshConditions();
  });
  function getPath(o,path){return path.split('.').reduce((v,k)=>v?.[k],o);}
  function setPath(o,path,value){const parts=path.split('.');let at=o;for(let i=0;i<parts.length-1;i++)at=at[parts[i]]??=(/^\d+$/.test(parts[i+1])?[]:{});at[parts.at(-1)]=value;}
  function showWechat(r){wechatRecord=r;$('wechatState').textContent=JSON.stringify({version:r.version,state:r.state,provider_state:r.provider_state,applyment_id:r.applyment_id,opinion:r.opinion,audit_detail:r.audit_detail},null,2);for(const [path,e]of wechatControls){const value=getPath(r.profile,path);e.value=Array.isArray(value)?value.join(','):value??'';}materialContext++;refreshConditions();}
  const wechatVersion=()=>{if(!current)throw Error('先打开申请');return wechatRecord?.version||0;};
  $('wechatRead').onclick=()=>run(async()=>{if(!current)throw Error('先打开申请');showWechat(await request(reviewMode?'wechat_review_read':'wechat_read',{application:current.application}));});
  $('wechatProfile').onsubmit=e=>{e.preventDefault();run(async()=>{const expected_version=wechatVersion();const profile=wechatRecord?.profile?structuredClone(wechatRecord.profile):{};for(const [path,input]of wechatControls){if(input.value)setPath(profile,path,path.endsWith('_pics')||path.endsWith('qualifications')?input.value.split(',').map(s=>s.trim()).filter(Boolean):input.value);else{const parts=path.split('.');const at=parts.slice(0,-1).reduce((o,k)=>o?.[k],profile);if(at)delete at[parts.at(-1)];}}if(profile.subject_info?.ubo_info_list)profile.subject_info.ubo_info_list=profile.subject_info.ubo_info_list.filter(u=>u&&Object.keys(u).length);if(profile.subject_info&&(!profile.subject_info.ubo_info_list?.length||current.entity_type!=='ENTERPRISE'))delete profile.subject_info.ubo_info_list;
    if(profile.contact_info?.contact_type!=='SUPER')for(const field of ['contact_id_doc_type','contact_id_number','contact_id_doc_copy','contact_id_doc_copy_back','contact_period_begin','contact_period_end'])delete profile.contact_info?.[field];
    else if(profile.contact_info.contact_id_doc_type===passport)delete profile.contact_info.contact_id_doc_copy_back;
    for(const ubo of profile.subject_info?.ubo_info_list||[])if(ubo.ubo_id_doc_type===passport)delete ubo.ubo_id_doc_copy_back;setPath(profile,'subject_info.subject_type',current.entity_type==='ENTERPRISE'?'SUBJECT_TYPE_ENTERPRISE':'SUBJECT_TYPE_INDIVIDUAL');setPath(profile,'subject_info.identity_info.id_holder_type','LEGAL');if(!profile.subject_info.identity_info.id_doc_type)setPath(profile,'subject_info.identity_info.id_doc_type',current.identity_type||'IDENTIFICATION_TYPE_IDCARD');if(!profile.contact_info?.contact_type)setPath(profile,'contact_info.contact_type','LEGAL');if(profile.subject_info.identity_info.id_doc_type==='IDENTIFICATION_TYPE_IDCARD')delete profile.subject_info.identity_info.id_doc_info;else delete profile.subject_info.identity_info.id_card_info;if(!profile.business_info?.sales_info?.sales_scenes_type)setPath(profile,'business_info.sales_info.sales_scenes_type',['SALES_SCENES_MINI_PROGRAM']);showWechat(await request('wechat_save',{application:current.application,expected_version,profile}));});};
  $('wechatSubmitReview').onclick=()=>run(async()=>showWechat(await request('wechat_submit_review',{application:current.application,expected_version:wechatVersion()})));
  for(const [id,decision]of [['wechatApprove','INTERNAL_APPROVED'],['wechatCorrect','CORRECTION']])$(id).onclick=()=>run(async()=>showWechat(await request('wechat_review',{application:current.application,expected_version:wechatVersion(),decision,opinion:$('wechatOpinion').value})));
  $('wechatExecute').onclick=()=>run(async()=>showWechat(await request('wechat_execute',{application:current.application,expected_version:wechatVersion()})));
  $('wechatQuery').onclick=()=>run(async()=>showWechat(await request('wechat_query',{application:current.application})));
  load();
})();
