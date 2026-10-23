'use strict';
(() => {
  const $=id=>document.getElementById(id),reviewMode=location.pathname==='/merchant/review';
  const states={DRAFT:'草稿',SUBMITTED:'待审核',IN_REVIEW:'审核中',CORRECTION_REQUIRED:'待补件',REJECTED:'已驳回',APPROVED:'入驻审核通过',WITHDRAWN:'已撤回'};
  let current=null,catalog=null,csrf='',busy=false,generation=0,cursor=null,wechatRecord=null;
  let historyGeneration=0,historyCursor=null,historyRequest=null;
  let noticeGeneration=0,noticeCursor=null,noticeRequest=null,noticeRecords=new Map();
  const wechatControls=new Map(),sceneControls=new Map();
  const storeScene='SALES_SCENES_STORE',miniScene='SALES_SCENES_MINI_PROGRAM';
  let invalidLoadedScenes=false;
  const selectedScenes=()=>[...sceneControls].filter(([,input])=>input.checked).map(([scene])=>scene);
  function setScenes(scenes){
    invalidLoadedScenes=scenes!==undefined&&(!Array.isArray(scenes)||!scenes.length||new Set(scenes).size!==scenes.length||scenes.some(scene=>scene!==miniScene&&scene!==storeScene));
    const admitted=invalidLoadedScenes?[]:scenes===undefined?[miniScene]:scenes;
    for(const [scene,input]of sceneControls)input.checked=admitted.includes(scene);
    if(invalidLoadedScenes)message('已保存的经营场景配置无效或尚未支持，请人工核对；禁止覆盖保存。');
  }
  let materialContext=0;
  const passport='IDENTIFICATION_TYPE_OVERSEA_PASSPORT';
  const controlValue=path=>wechatControls.get(path)?.value||'';
  function materialKinds(app){
    const kinds=new Set([...app.required_materials,'settlement_proof','operator_authorization','storefront_photo','interior_photo','mini_program_screenshot',...Object.keys(app.materials)]);
    if(controlValue('contact_info.contact_type')==='SUPER'){kinds.add('operator_identity');if(controlValue('contact_info.contact_id_doc_type')!==passport)kinds.add('operator_identity_back');}
    if(app.entity_type==='ENTERPRISE')for(let i=0;i<4;i++){
      const prefix='subject_info.ubo_info_list.'+i+'.';
      if([...wechatControls].some(([path,input])=>path.startsWith(prefix)&&input.type!=='hidden'&&input.value)){kinds.add('ubo_'+(i+1)+'_front');if(controlValue(prefix+'ubo_id_doc_type')!==passport)kinds.add('ubo_'+(i+1)+'_back');}
    }
    return [...kinds].filter(kind=>catalog.materials.some(m=>m.id===kind));
  }
  function clearWechat(){materialContext++;wechatRecord=null;setScenes();for(const e of wechatControls.values())e.value='';$('wechatState').textContent='';$('wechatOpinion').value='';}
  // The existing customer host passes its current CSRF value after login. No
  // second login form, password store or reusable browser token is introduced.
  window.configureCommunityOnboarding=context=>{generation++;busy=false;csrf=typeof context?.csrf==='string'?context.csrf:'';
    clearWechat();resetHistory();resetNotices();current=null;cursor=null;$('withdrawConfirmed').checked=false;withdrawalControls();$('detail').hidden=true;$('openingActions').hidden=true;$('moreApplications').hidden=true;
    for(const id of ['mine','applications','summary','materials','reviewNote','opening','openingWorkspace'])$(id).replaceChildren();
    $('applicationTitle').textContent='入驻申请';$('applicationState').textContent='';$('applicationVersion').textContent='';
    for(const id of ['legal_name','store_name','address','contact','note'])$(id).value='';setForm(null);$('statusFilter').value='ALL';
    message('正在读取当前账号的入驻信息…');return load();};
  function message(text){$('status').textContent=text;}
  async function request(operation,params={}) {
    if(current?.status==='WITHDRAWN'&&['save','upload','submit','withdraw','review','review_material','open_workbench',
      'wechat_save','wechat_submit_review','wechat_review','wechat_media','wechat_execute'].includes(operation))throw Error('本申请已撤回，不能编辑；可另建申请。');
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
      $('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=!!current&&!['DRAFT','CORRECTION_REQUIRED'].includes(current.status));withdrawalControls();refreshLicense();}}}
  function button(text,handler){const b=document.createElement('button');b.type='button';b.textContent=text;b.addEventListener('click',()=>run(handler));return b;}
  function draftFields(){return Object.fromEntries(['legal_name','store_name','address','contact'].map(k=>[k,$(k).value]));}
  function setForm(app){for(const [k,v] of Object.entries(app?.fields||{}))if($(k))$(k).value=v;
    $('identity_type').value=app?.identity_type||'IDENTIFICATION_TYPE_IDCARD';$('entity_type').value=app?.entity_type||'ENTERPRISE';$('category').value=app?.category||'GENERAL';$('delegated').checked=app?.delegated||false;setScenes(app?.sales_scenes_type);if(!wechatRecord&&wechatControls.has('contact_info.contact_type'))wechatControls.get('contact_info.contact_type').value=app?.delegated?'SUPER':'LEGAL';}
  function withdrawalControls(){
    const withdrawn=current?.status==='WITHDRAWN';
    $('withdrawActions').hidden=reviewMode||!current||!['DRAFT','CORRECTION_REQUIRED'].includes(current.status);
    $('withdrawalState').textContent=withdrawn?'本申请已撤回，保留历史且不可编辑；如需继续，请另建申请。微信原进件状态请由授权人员独立查询。':'';
    $('wechatProfile').querySelectorAll('input,select,button').forEach(e=>e.disabled=withdrawn);
    $('wechatMedia').querySelectorAll('button').forEach(e=>e.disabled=withdrawn);
    for(const id of ['wechatSubmitReview','wechatApprove','wechatCorrect','wechatExecute'])$(id).disabled=withdrawn;
  }
  function render(app){
    if(current?.application!==app?.application||current?.revision!==app?.revision){resetHistory();resetNotices();}
    if(current?.application!==app?.application)clearWechat();current=app;$('withdrawConfirmed').checked=false;withdrawalControls();$('detail').hidden=!app;refreshLicense();if(!app)return;
    $('applicationVersion').textContent='申请编号 '+app.application+' · 版本 '+app.revision;
    $('applicationTitle').textContent=app.fields.store_name||'入驻申请';$('applicationState').textContent=states[app.status]||app.status;
    $('summary').replaceChildren();for(const [label,value] of [['主体名称',app.fields.legal_name],['门店名称',app.fields.store_name],['经营地址',app.fields.address],['联系人',app.fields.contact]]){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('summary').append(dt,dd);}
    $('reviewNote').textContent=app.reviewer_note?'审核说明：'+app.reviewer_note:'';
    const editable=['DRAFT','CORRECTION_REQUIRED'].includes(app.status),reviewable=['SUBMITTED','IN_REVIEW'].includes(app.status);
    $('submitApplication').hidden=reviewMode||!editable;$('reviewActions').hidden=!reviewMode||!reviewable&&!['APPROVED','REJECTED'].includes(app.status);
    document.querySelectorAll('[data-action]').forEach(b=>{b.hidden=b.dataset.action==='REOPEN'?app.status!=='REJECTED':app.status==='REJECTED'||app.status==='APPROVED'&&b.dataset.action!=='CORRECTION';
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
  function resetHistory(){
    historyGeneration++;historyCursor=null;historyRequest=null;
    $('historyRows').replaceChildren();$('historyMaterials').replaceChildren();$('moreHistory').hidden=true;$('historyStatus').textContent='';
  }
  async function loadHistory(more=false){
    if(!current)throw Error('请先打开原申请。');
    if(more&&historyCursor===null)return;
    if(!more)resetHistory();
    const token={generation,selection:historyGeneration,application:current.application,revision:current.revision};
    historyRequest=token;
    const isCurrent=()=>historyRequest===token&&generation===token.generation&&historyGeneration===token.selection&&
      current?.application===token.application&&current?.revision===token.revision;
    const after=more?historyCursor:0;
    try{
      const result=await request(reviewMode?'review_history':'history',{application:token.application,after_revision:after});
      if(!isCurrent())return;
      if(!result||result.application!==token.application||!Array.isArray(result.records)||result.records.length>50||
        typeof result.has_more!=='boolean'||!Array.isArray(result.material_versions)||typeof result.material_versions_truncated!=='boolean')throw Error('申请历史返回未确认。');
      let previous=after;
      for(const record of result.records){
        if(!record||!Number.isSafeInteger(record.revision)||record.revision<=previous||typeof record.event!=='string'||typeof record.actor!=='string'||
          record.occurred_at!==null&&!Number.isSafeInteger(record.occurred_at)||
          !['CAPTURED_AT_EVENT','LEGACY_EVENT_ONLY'].includes(record.evidence)||record.note!==null&&typeof record.note!=='string'||
          record.materials!==null&&!Array.isArray(record.materials))throw Error('申请历史返回未确认。');
        previous=record.revision;
      }
      if(result.has_more?(result.records.length!==50||result.next_revision!==previous):result.next_revision!==null)throw Error('申请历史分页返回未确认。');
      const nodes=[];
      for(const record of result.records){
        const row=document.createElement('article'),title=document.createElement('strong'),detail=document.createElement('p'),reason=document.createElement('p');
        title.textContent='版本 '+record.revision+' · '+record.event+' · '+(states[record.status_after]||record.status_after||'历史状态未知');
        detail.textContent='操作账号 '+record.actor+' · '+(record.occurred_at===null?'原事件时间未能唯一关联':new Date(record.occurred_at*1000).toISOString());
        reason.textContent=record.note===null?'旧审核原因未完整留存，不以当前意见补填。':record.note?'当次说明：'+record.note:'本次事件无审核说明。';
        row.append(title,detail,reason);
        const materials=document.createElement('p');materials.textContent=record.materials===null?'旧审核与材料版本的关联未留存。':
          record.materials.map(m=>(catalog.materials.find(item=>item.id===m.kind)?.title||m.kind)+'：第'+m.sequence+'版（'+m.version+'）'+(m.review?' · '+m.review.decision+' '+m.review.note:'')).join('；')||'该版本尚无上传资料';
        row.append(materials);nodes.push(row);
      }
      if(!isCurrent())return;
      $('historyRows').append(...nodes);historyCursor=result.next_revision;$('moreHistory').hidden=!result.has_more;
      $('historyMaterials').replaceChildren();
      for(const material of result.material_versions){const row=document.createElement('p');row.textContent=(catalog.materials.find(item=>item.id===material.kind)?.title||material.kind)+' · 第'+material.sequence+'版 · '+material.version+' · 上传账号 '+material.actor+' · '+new Date(material.created_at*1000).toISOString();$('historyMaterials').append(row);}
      $('historyStatus').textContent=(result.has_more?'已读取本页，可继续加载历史。':'本申请历史已读取至末页。')+(result.material_versions_truncated?'原资料版本档案超过显示上限，请由原系统核对。':'');
    }catch(error){if(isCurrent()){resetHistory();$('historyStatus').textContent='历史读取未确认，请重新核对当前权限与申请。';throw Error('历史读取未确认，请重新核对当前权限与申请。');}}
    finally{if(historyRequest===token)historyRequest=null;}
  }
  $('loadHistory').addEventListener('click',()=>run(()=>loadHistory()));
  $('moreHistory').addEventListener('click',()=>run(()=>loadHistory(true)));
  function resetNotices(){
    noticeGeneration++;noticeCursor=null;noticeRequest=null;noticeRecords=new Map();
    $('admissionNotices').replaceChildren();$('moreAdmissionNotices').hidden=true;$('admissionNoticeStatus').textContent='';
  }
  const noticeSelection=()=>({generation,selection:noticeGeneration,application:current?.application,revision:current?.revision});
  const noticeSelected=token=>generation===token.generation&&noticeGeneration===token.selection&&current?.application===token.application&&current?.revision===token.revision;
  function validNotice(record,token){
    const statuses={CORRECTION:'CORRECTION_REQUIRED',REJECT:'REJECTED',APPROVE:'APPROVED',REOPEN:'CORRECTION_REQUIRED'};
    return record&&record.application===token.application&&typeof record.id==='string'&&/^[0-9a-f]{64}$/.test(record.id)&&
      Number.isSafeInteger(record.revision)&&record.revision>0&&
      record.kind==='MERCHANT_ONBOARDING_RESULT_V1'&&record.reference===token.application+':'+record.revision&&
      Object.hasOwn(statuses,record.event)&&record.status===statuses[record.event]&&typeof record.read==='boolean'&&
      typeof record.message==='string'&&Number.isSafeInteger(record.created_at)&&record.created_at>=0&&record.created_at<=253402300799;
  }
  function renderNotices(){
    $('admissionNotices').replaceChildren();
    for(const record of noticeRecords.values()){
      const row=document.createElement('article'),heading=document.createElement('strong'),text=document.createElement('p');
      heading.textContent='第'+record.revision+'版 · '+states[record.status]+' · '+(record.read?'已读':'未读');text.textContent=record.message;
      row.append(heading,text);if(!record.read)row.append(button('标为已读',()=>markAdmissionNotice(record)));
      row.append(button('查看申请最新状态',async()=>{
        if(noticeRecords.get(record.id)!==record)return;
        const selected=noticeSelection();
        try{
          const app=await request('read',{application:selected.application});
          if(!noticeSelected(selected))return;
          if(app.application!==selected.application)throw Error('申请返回归属未确认。');
          render(app);message('已读取申请最新状态；审核说明请查看受保护时间线。');
        }catch(error){if(noticeSelected(selected)){resetNotices();throw Error('申请状态读取未确认，请重新核对当前权限。');}}
      }));
      $('admissionNotices').append(row);
    }
  }
  async function loadAdmissionNotices(more=false){
    if(reviewMode)return;
    if(!current)throw Error('请先打开本人的申请。');
    if(more&&noticeCursor===null)return;
    if(!more)resetNotices();
    const token=noticeSelection();noticeRequest=token;
    const valid=()=>noticeRequest===token&&noticeSelected(token),after=more?noticeCursor:'';
    try{
      const result=await request('notices',{application:token.application,after_id:after});
      if(!valid())return;
      if(!result||result.application!==token.application||!Array.isArray(result.records)||result.records.length>50||typeof result.has_more!=='boolean')throw Error('通知返回未确认。');
      let previous=after;
      for(const record of result.records){if(!validNotice(record,token)||record.id<=previous)throw Error('通知归属或顺序未确认。');previous=record.id;}
      if(result.has_more?(result.records.length!==50||result.next_cursor!==previous):result.next_cursor!==null)throw Error('通知分页未确认。');
      for(const record of result.records)noticeRecords.set(record.id,record);
      noticeCursor=result.next_cursor;renderNotices();$('moreAdmissionNotices').hidden=!result.has_more;
      $('admissionNoticeStatus').textContent=noticeRecords.size?'已读取本申请通知；刷新可查看新结果。':'本申请尚无已留存的结果通知；旧记录请查看审核时间线。';
    }catch(error){if(valid()){resetNotices();throw Error('通知读取未确认，请重新核对当前账号与申请。');}}
    finally{if(noticeRequest===token)noticeRequest=null;}
  }
  async function markAdmissionNotice(record){
    if(reviewMode||noticeRecords.get(record.id)!==record||record.read)return;
    const token=noticeSelection();noticeRequest=token;const valid=()=>noticeRequest===token&&noticeSelected(token);
    try{
      const result=await request('notice_read',{application:token.application,notice_id:record.id});
      if(!valid())return;
      if(!validNotice(result,token)||result.id!==record.id||result.revision!==record.revision||result.event!==record.event||!result.read)throw Error('已读结果未确认。');
      noticeRecords.set(record.id,result);renderNotices();$('admissionNoticeStatus').textContent='已标为已读。';
    }catch(error){if(valid()){resetNotices();throw Error('通知已读结果未确认，请刷新后核对。');}}
    finally{if(noticeRequest===token)noticeRequest=null;}
  }
  $('applicationNotices').hidden=reviewMode;
  $('loadAdmissionNotices').addEventListener('click',()=>run(()=>loadAdmissionNotices()));
  $('moreAdmissionNotices').addEventListener('click',()=>run(()=>loadAdmissionNotices(true)));
  function renderMaterials(app){
    if(!app)return;
    const editable=['DRAFT','CORRECTION_REQUIRED'].includes(app.status),reviewable=['SUBMITTED','IN_REVIEW'].includes(app.status);
    $('materials').replaceChildren();if(!reviewMode)$('licenseUpload').replaceChildren();
    for(const kind of materialKinds(app)){const description=catalog.materials.find(m=>m.id===kind),record=app.materials[kind];
      const row=document.createElement('div');row.className='material';row.dataset.kind=kind;
      const title=document.createElement('strong');title.textContent=(description?.title||kind)+(app.required_materials.includes(kind)?' *':'（选填）');row.append(title);
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
      (!reviewMode&&kind==='business_license'?$('licenseUpload'):$('materials')).append(row);
    }
  }
  async function list(append=false){const result=await request(reviewMode?'review_list':'mine',{status:$('statusFilter').value,...(append&&cursor?{cursor}:{})}),target=$(reviewMode?'applications':'mine');if(!append)target.replaceChildren();
    for(const app of result.applications)target.append(button((app.fields.store_name||'未命名申请')+' · '+(states[app.status]||app.status),async()=>{render(await request(reviewMode?'review_read':'read',{application:app.application}));}));
    cursor=result.next_cursor||null;$('moreApplications').hidden=!cursor;
    if(!reviewMode&&!append){render(result.applications[0]||null);}
    message(result.applications.length?'已读取最新入驻状态。':reviewMode?'暂无入驻申请。':'尚无申请，请填写经营信息并保存草稿。');}
  async function load(){return run(async()=>{catalog=await request('catalog');await list();});}
  $('profile').addEventListener('submit',event=>{event.preventDefault();run(async()=>{const licenseDraft=[...wechatControls].filter(([path])=>path.startsWith('subject_info.business_license_info.')).map(([path,input])=>[path,input.value]);render(await request('save',{application:current?.application||null,revision:current?.revision||0,
    sales_scenes_type:selectedScenes(),identity_type:$('identity_type').value,fields:draftFields(),entity_type:$('entity_type').value,category:$('category').value,delegated:$('delegated').checked}));for(const [path,value]of licenseDraft)wechatControls.get(path).value=value;message('申请草稿已保存，请按清单上传资料；未保存的执照字段请点击保存执照资料草稿。');});});
  $('newApplication').addEventListener('click',()=>{if(busy)return;clearWechat();resetHistory();resetNotices();current=null;for(const key of ['legal_name','store_name','address','contact'])$(key).value='';setForm(null);$('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=false);render(null);message('请填写新申请。');});
  $('submitApplication').addEventListener('click',()=>run(async()=>{render(await request('submit',{application:current.application,revision:current.revision}));message('申请已提交，请等待平台审核。');}));
  $('withdrawApplication').addEventListener('click',()=>run(async()=>{
    if(reviewMode||!current||!['DRAFT','CORRECTION_REQUIRED'].includes(current.status))return;
    if(!$('withdrawConfirmed').checked)throw Error('请先确认撤回当前申请及不可编辑的后果。');
    const token={generation,application:current.application,revision:current.revision};
    const selected=()=>generation===token.generation&&current?.application===token.application&&current?.revision===token.revision;
    try{
      const result=await request('withdraw',{application:token.application,revision:token.revision});
      if(!selected())return;
      if(result.application!==token.application||!Number.isSafeInteger(result.revision)||result.revision!==token.revision+1||result.status!=='WITHDRAWN')throw Error('WITHDRAWAL_REPLY_UNCONFIRMED');
      render(result);message('本申请已撤回，历史资料保留；如需继续，请另建申请。');
    }catch(error){if(selected()){$('withdrawConfirmed').checked=false;throw Error('撤回结果未确认，请先刷新本申请状态，勿盲目重复提交。');}}
  }));
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
  for(let i=0;i<4;i++)for(const [field,title]of [['ubo_id_doc_type','证件类型'],['ubo_id_doc_name','姓名'],['ubo_id_doc_number','证件号'],['ubo_id_doc_address','住址'],['ubo_period_begin','证件有效期开始'],['ubo_period_end','证件有效期结束或长期']])definitions.push(['subject_info.ubo_info_list.'+i+'.'+field,'受益人'+(i+1)+'：'+title+'（按官方适用条件填写完整受益人名单，含适用法人）']);
  for(const [scene,title]of [[miniScene,'小程序经营（默认）'],[storeScene,'线下门店经营']]){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.scene=scene;input.checked=scene===miniScene;input.addEventListener('change',()=>{materialContext++;refreshConditions();});label.textContent=title;label.append(input);sceneControls.set(scene,input);$('wechatFields').append(label);}
  definitions.push(['business_info.sales_info.biz_store_info.biz_store_name','线下门店名称'],['business_info.sales_info.biz_store_info.biz_address_code','线下门店地区代码（填写已核实的官方代码）'],['business_info.sales_info.biz_store_info.biz_store_address','线下门店详细地址']);
  for(const [path,title]of definitions){const label=document.createElement('label');label.textContent=title;const input=document.createElement('input');input.autocomplete='off';input.dataset.path=path;input.maxLength=512;wechatControls.set(path,input);label.append(input);if(!reviewMode&&path.startsWith('subject_info.business_license_info.')){input.setAttribute('form','wechatProfile');$('licenseFields').append(label);}else $('wechatFields').append(label);}
  const mediaFields={business_license:'subject_info.business_license_info.license_copy',identity_front:'subject_info.identity_info.id_card_info.id_card_copy',identity_back:'subject_info.identity_info.id_card_info.id_card_national',mini_program_screenshot:'business_info.sales_info.mini_program_info.mini_program_pics'};
  Object.assign(mediaFields,{storefront_photo:'business_info.sales_info.biz_store_info.store_entrance_pic',interior_photo:'business_info.sales_info.biz_store_info.indoor_pic',operator_identity:'contact_info.contact_id_doc_copy',operator_identity_back:'contact_info.contact_id_doc_copy_back',operator_authorization:'contact_info.business_authorization_letter',industry_permit:'settlement_info.qualifications'});
  for(let i=0;i<4;i++){mediaFields['ubo_'+(i+1)+'_front']='subject_info.ubo_info_list.'+i+'.ubo_id_doc_copy';mediaFields['ubo_'+(i+1)+'_back']='subject_info.ubo_info_list.'+i+'.ubo_id_doc_copy_back';}
  for(const [kind,path]of Object.entries(mediaFields)){const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.path=path;wechatControls.set(path,hidden);$('wechatFields').append(hidden);const button=document.createElement('button');button.type='button';button.dataset.material=kind;button.textContent='同步已上传的'+(({business_license:'营业执照',identity_front:'身份证人像面',identity_back:'身份证国徽面',mini_program_screenshot:'小程序页面截图',storefront_photo:'门店门头照片',interior_photo:'门店经营场所照片'})[kind]||kind);button.onclick=()=>run(async()=>{if(!current)throw Error('先打开申请');if(invalidLoadedScenes)throw Error('经营场景配置需人工核对，不能同步资料。');const scene=['storefront_photo','interior_photo'].includes(kind)?storeScene:kind==='mini_program_screenshot'?miniScene:null;if(scene&&!selectedScenes().includes(scene))throw Error('请先选择对应经营场景。');const context=materialContext,application=current.application,type=controlValue('subject_info.identity_info.id_doc_type')||current.identity_type||'IDENTIFICATION_TYPE_IDCARD';const r=await request('wechat_media',{application,kind});if(context!==materialContext||application!==current?.application)throw Error('资料条件已变化，请重新同步。');if(kind==='identity_front'||kind==='identity_back'){if(type!=='IDENTIFICATION_TYPE_IDCARD'){const target='subject_info.identity_info.id_doc_info.'+(kind==='identity_front'?'id_doc_copy':'id_doc_copy_back');setPath((wechatRecord??={version:0,profile:{}}).profile??={},target,r.media_id);}else hidden.value=r.media_id;}else hidden.value=r.media_id;message('资料已上传微信；请保存微信资料草稿。');});$('wechatMedia').append(button);}
  function refreshLicense(){
    const inline=$('licenseInline'),entity=$('entity_type'),entityLabel=entity.closest?entity.closest('label'):entity.parentNode;
    if(entityLabel?.parentNode)entityLabel.parentNode.insertBefore(inline,entityLabel.nextSibling);
    inline.hidden=reviewMode;
    $('saveLicense').disabled=busy||!current||current.status==='WITHDRAWN';
    $('licenseFields').querySelectorAll('input').forEach(input=>input.disabled=busy||current?.status==='WITHDRAWN');
    if(!current)$('licenseUpload').textContent='保存申请草稿后可在此上传营业执照。';
  }
  $('entity_type').addEventListener('change',refreshLicense);
  function refreshConditions(){
    refreshLicense();
    const contactType=controlValue('contact_info.contact_type')||(current?.delegated?'SUPER':'LEGAL');
    const contactLabels={'contact_info.contact_name':contactType==='SUPER'?'超级管理员姓名':'法人/经营者姓名','contact_info.mobile_phone':contactType==='SUPER'?'超级管理员手机':'法人/经营者联系电话','contact_info.contact_email':contactType==='SUPER'?'超级管理员邮箱':'法人/经营者邮箱'};
    for(const [path,labelText] of Object.entries(contactLabels)){const input=wechatControls.get(path),label=input?.parentNode,textNode=label?.firstChild;if(textNode&&textNode.nodeType===3)textNode.textContent=labelText;}
    const docType=controlValue('subject_info.identity_info.id_doc_type')||current?.identity_type||'IDENTIFICATION_TYPE_IDCARD';
    for(const [path,input]of wechatControls)if(input.type!=='hidden'){
      if(path.startsWith('contact_info.contact_')&&!['contact_info.contact_type','contact_info.contact_name','contact_info.contact_email'].includes(path))input.parentNode.hidden=contactType!=='SUPER';
      if(path.includes('.identity_info.id_card_info.'))input.parentNode.hidden=docType!=='IDENTIFICATION_TYPE_IDCARD';
      if(path.includes('.identity_info.id_doc_info.'))input.parentNode.hidden=docType==='IDENTIFICATION_TYPE_IDCARD';
    }
    for(const [path,input]of wechatControls)if(path.startsWith('subject_info.ubo_info_list.')&&input.type!=='hidden')input.parentNode.hidden=current?.entity_type!=='ENTERPRISE';
    for(const [path,input]of wechatControls)if(path.startsWith('business_info.sales_info.biz_store_info.')&&input.type!=='hidden')input.parentNode.hidden=!selectedScenes().includes(storeScene);
    for(const button of $('wechatMedia').children){const scene=['storefront_photo','interior_photo'].includes(button.dataset.material)?storeScene:button.dataset.material==='mini_program_screenshot'?miniScene:null;if(scene)button.hidden=!selectedScenes().includes(scene);}
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
  function showWechat(r){wechatRecord=r;setScenes(r.profile?.business_info?.sales_info?.sales_scenes_type);$('wechatState').textContent=JSON.stringify({version:r.version,state:r.state,provider_state:r.provider_state,applyment_id:r.applyment_id,opinion:r.opinion,audit_detail:r.audit_detail},null,2);for(const [path,e]of wechatControls){const value=getPath(r.profile,path);e.value=Array.isArray(value)?value.join(','):value??'';}materialContext++;refreshConditions();}
  const wechatVersion=()=>{if(!current)throw Error('先打开申请');return wechatRecord?.version||0;};
  $('wechatRead').onclick=()=>run(async()=>{if(!current)throw Error('先打开申请');showWechat(await request(reviewMode?'wechat_review_read':'wechat_read',{application:current.application}));});
  $('wechatProfile').onsubmit=e=>{e.preventDefault();run(async()=>{const expected_version=wechatVersion();if(invalidLoadedScenes)throw Error('已保存的经营场景配置无效或尚未支持，请人工核对；禁止覆盖保存。');const scenes=selectedScenes(),context=materialContext,application=current.application;if(!scenes.length)throw Error('请至少选择一个经营场景。');const profile=wechatRecord?.profile?structuredClone(wechatRecord.profile):{};for(const [path,input]of wechatControls){if(input.value)setPath(profile,path,path.endsWith('_pics')||path.endsWith('qualifications')||path.endsWith('store_entrance_pic')||path.endsWith('indoor_pic')?input.value.split(',').map(s=>s.trim()).filter(Boolean):input.value);else{const parts=path.split('.');const at=parts.slice(0,-1).reduce((o,k)=>o?.[k],profile);if(at)delete at[parts.at(-1)];}}if(profile.subject_info?.ubo_info_list)profile.subject_info.ubo_info_list=profile.subject_info.ubo_info_list.filter(u=>u&&Object.keys(u).length);if(profile.subject_info&&(!profile.subject_info.ubo_info_list?.length||current.entity_type!=='ENTERPRISE'))delete profile.subject_info.ubo_info_list;
    if(profile.contact_info?.contact_type!=='SUPER')for(const field of ['contact_id_doc_type','contact_id_number','contact_id_doc_copy','contact_id_doc_copy_back','contact_period_begin','contact_period_end'])delete profile.contact_info?.[field];
    else if(profile.contact_info.contact_id_doc_type===passport)delete profile.contact_info.contact_id_doc_copy_back;
    for(const ubo of profile.subject_info?.ubo_info_list||[])if(ubo.ubo_id_doc_type===passport)delete ubo.ubo_id_doc_copy_back;setPath(profile,'subject_info.subject_type',current.entity_type==='ENTERPRISE'?'SUBJECT_TYPE_ENTERPRISE':'SUBJECT_TYPE_INDIVIDUAL');setPath(profile,'subject_info.identity_info.id_holder_type','LEGAL');if(!profile.subject_info.identity_info.id_doc_type)setPath(profile,'subject_info.identity_info.id_doc_type',current.identity_type||'IDENTIFICATION_TYPE_IDCARD');if(!profile.contact_info?.contact_type)setPath(profile,'contact_info.contact_type','LEGAL');if(profile.subject_info.identity_info.id_doc_type==='IDENTIFICATION_TYPE_IDCARD')delete profile.subject_info.identity_info.id_doc_info;else delete profile.subject_info.identity_info.id_card_info;setPath(profile,'business_info.sales_info.sales_scenes_type',scenes);const saved=await request('wechat_save',{application,expected_version,profile});if(context!==materialContext||application!==current?.application)throw Error('资料条件已变化；保存结果请刷新后核对。');render(await request(reviewMode?'review_read':'read',{application}));showWechat(saved);});};
  $('wechatSubmitReview').onclick=()=>run(async()=>showWechat(await request('wechat_submit_review',{application:current.application,expected_version:wechatVersion()})));
  for(const [id,decision]of [['wechatApprove','INTERNAL_APPROVED'],['wechatCorrect','CORRECTION']])$(id).onclick=()=>run(async()=>showWechat(await request('wechat_review',{application:current.application,expected_version:wechatVersion(),decision,opinion:$('wechatOpinion').value})));
  $('wechatExecute').onclick=()=>run(async()=>showWechat(await request('wechat_execute',{application:current.application,expected_version:wechatVersion()})));
  $('wechatQuery').onclick=()=>run(async()=>showWechat(await request('wechat_query',{application:current.application})));
  refreshLicense();
  load();
})();
