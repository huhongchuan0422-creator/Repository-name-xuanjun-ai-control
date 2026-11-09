'use strict';
(() => {
  const $=id=>document.getElementById(id),reviewMode=location.pathname==='/merchant/review';
  const states={DRAFT:'草稿',SUBMITTED:'待审核',IN_REVIEW:'审核中',CORRECTION_REQUIRED:'待补件',REJECTED:'已驳回',APPROVED:'入驻审核通过',WITHDRAWN:'已撤回'};
  let current=null,catalog=null,csrf='',busy=false,generation=0,cursor=null,wechatRecord=null,reviewQueueRevision=0,reviewLayout=null;
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
  const materialKindTitles={business_license:'营业执照',identity_front:'经营者证件正面',identity_back:'经营者证件反面',mini_program_screenshot:'小程序页面截图',storefront_photo:'门店门头照片',interior_photo:'门店经营场所照片',cashier_photo:'收银台照片',settlement_proof:'结算账户证明',operator_identity:'经办人证件正面',operator_identity_back:'经办人证件反面',operator_authorization:'经办人授权书',industry_permit:'行业经营许可',ubo_1_front:'受益人1证件正面',ubo_1_back:'受益人1证件反面',ubo_2_front:'受益人2证件正面',ubo_2_back:'受益人2证件反面',ubo_3_front:'受益人3证件正面',ubo_3_back:'受益人3证件反面',ubo_4_front:'受益人4证件正面',ubo_4_back:'受益人4证件反面'};
  const materialKindTitle=kind=>materialKindTitles[kind]||'其他补充材料';
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
  window.configureCommunityOnboarding=context=>{generation++;reviewQueueRevision++;busy=false;csrf=typeof context?.csrf==='string'?context.csrf:'';
    clearWechat();resetHistory();resetNotices();current=null;cursor=null;$('withdrawConfirmed').checked=false;withdrawalControls();$('detail').hidden=true;$('openingActions').hidden=true;$('moreApplications').hidden=true;
    preserveReviewVersion();for(const id of ['mine','applications','summary','materials','reviewNote','opening','openingWorkspace'])$(id).replaceChildren();if(reviewMode)renderReviewList($('applications'),[],async()=>{});
    $('applicationTitle').textContent='入驻申请';$('applicationState').textContent='';$('applicationVersion').textContent='';
    for(const id of ['legal_name','store_name','address','contact','note'])$(id).value='';setForm(null);$('statusFilter').value='ALL';
    syncReviewLayout(null);if(!csrf){message('请先登录客户中心，再读取入驻信息。');return Promise.resolve();}message('正在读取当前账号的入驻信息…');return load();};
  function message(text){const node=$('status');node.textContent=text;if(reviewMode){const failed=/暂不可用|未确认|不能执行|失效|请先登录/.test(text);node.dataset.tone=failed?'warning':/正在|读取/.test(text)?'loading':'ready';}}
  async function request(operation,params={}) {
    if(current?.status==='WITHDRAWN'&&['save','upload','submit','withdraw','review','review_material','open_workbench',
      'wechat_save','wechat_submit_review','wechat_review','wechat_media','wechat_execute'].includes(operation))throw Error('本申请已撤回，不能编辑；可另建申请。');
    const version=generation;
    const response=await fetch('/merchant/onboarding',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({operation,params})});
    if(version!==generation)throw Error('登录状态已变化，请重新读取。');
    if(response.status===403)throw Error('当前账号暂无商家审核权限。');
    if(!response.ok)throw Error(response.status===400?'资料、状态或版本不符合要求，请刷新后检查。':'服务暂不可用，结果可能尚未确认，请先刷新状态。');
    const reply=await response.json();
    if(version!==generation)throw Error('登录状态已变化，请重新读取。');
    if(reply.payment_enabled!==false||!reply.result)throw Error('服务返回无效，请刷新状态。');
    return reply.result;
  }
  async function run(action){if(busy)return;const version=generation;busy=true;$('statusFilter').disabled=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{await action();}catch(error){if(version===generation)message(error.message);}finally{if(version===generation){busy=false;$('statusFilter').disabled=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);
      $('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=!!current&&!['DRAFT','CORRECTION_REQUIRED'].includes(current.status));if(!current||['DRAFT','CORRECTION_REQUIRED'].includes(current.status))$('requested_split_percent').disabled=!$('split_participation').checked;withdrawalControls();refreshLicense();}}}
  function button(text,handler){const b=document.createElement('button');b.type='button';b.textContent=text;b.addEventListener('click',()=>run(handler));return b;}
  function draftFields(){return Object.fromEntries(['legal_name','store_name','address','contact'].map(k=>[k,$(k).value]));}
  function setForm(app){for(const [k,v] of Object.entries(app?.fields||{}))if($(k))$(k).value=v;
    $('redemption_percent').value=String(app?.redemption_percent??0);
    $('split_participation').checked=app?.split_participation===true;$('requested_split_percent').value=app?.split_participation?(Number(app.requested_split_bps)/100).toFixed(2):'0';$('requested_split_percent').disabled=!$('split_participation').checked;
    $('identity_type').value=app?.identity_type||'IDENTIFICATION_TYPE_IDCARD';$('entity_type').value=app?.entity_type||'ENTERPRISE';$('category').value=app?.category||'GENERAL';$('delegated').checked=app?.delegated||false;setScenes(app?.sales_scenes_type);if(!wechatRecord&&wechatControls.has('contact_info.contact_type'))wechatControls.get('contact_info.contact_type').value=app?.delegated?'SUPER':'LEGAL';}
  function withdrawalControls(){
    const withdrawn=current?.status==='WITHDRAWN';
    $('withdrawActions').hidden=reviewMode||!current||!['DRAFT','CORRECTION_REQUIRED'].includes(current.status);
    $('withdrawalState').textContent=withdrawn?'本申请已撤回且不可编辑；如需继续，请另建申请。':'';
    $('wechatProfile').querySelectorAll('input,select,button').forEach(e=>e.disabled=withdrawn);
    $('wechatMedia').querySelectorAll('button').forEach(e=>e.disabled=withdrawn);
    for(const id of ['wechatSubmitReview','wechatApprove','wechatCorrect','wechatExecute'])$(id).disabled=withdrawn;
  }
  function render(app){
    if(current?.application!==app?.application||current?.revision!==app?.revision){resetHistory();resetNotices();}
    if(current?.application!==app?.application)clearWechat();current=app;$('withdrawConfirmed').checked=false;withdrawalControls();$('detail').hidden=!app;refreshLicense();if(!app)return;
    $('applicationVersion').textContent='申请编号 '+app.application+' · 版本 '+app.revision;
    $('applicationTitle').textContent=app.fields.store_name||'入驻申请';$('applicationState').textContent=states[app.status]||app.status;
    const bps=value=>Number.isSafeInteger(value)?(value/100).toFixed(2)+'%':'尚未核定';preserveReviewVersion();$('summary').replaceChildren();for(const [label,value] of [['主体名称',app.fields.legal_name],['门店名称',app.fields.store_name],['经营地址',app.fields.address],['联系人',app.fields.contact],['分账参与意愿',app.split_participation?'自愿参加':'不参加'],['申请分账比例',bps(app.requested_split_bps)],['微信核定最高比例',bps(app.provider_max_split_bps)],['最终生效分账比例',bps(app.effective_split_bps)],['爱心积分抵扣比例（申请值）',String(app.redemption_percent??0)+'%'],['爱心积分抵扣比例（审核生效）',app.approved_redemption_percent==null?'尚未审批':String(app.approved_redemption_percent)+'%']]){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('summary').append(dt,dd);}
    $('reviewNote').textContent=app.reviewer_note?'审核说明：'+app.reviewer_note:'';
    $('redemptionReview').textContent='分账参与意愿：'+(app.split_participation?'自愿参加':'不参加')+'；申请比例：'+bps(app.requested_split_bps)+'；微信核定最高比例：'+bps(app.provider_max_split_bps)+'；最终生效比例：'+bps(app.effective_split_bps)+'。爱心积分抵扣比例独立为 '+String(app.redemption_percent??0)+'%，不与分账比例混用。';
    const editable=['DRAFT','CORRECTION_REQUIRED'].includes(app.status),reviewable=['SUBMITTED','IN_REVIEW'].includes(app.status);
    $('submitApplication').hidden=reviewMode||!editable;$('reviewActions').hidden=!reviewMode||!reviewable&&!['APPROVED','REJECTED'].includes(app.status);
    document.querySelectorAll('[data-action]').forEach(b=>{b.hidden=b.dataset.action==='REOPEN'?app.status!=='REJECTED':app.status==='REJECTED'||app.status==='APPROVED'&&b.dataset.action!=='CORRECTION';
      if(b.dataset.action==='CORRECTION')b.textContent=app.status==='APPROVED'?'要求重新核验':'要求补件';});
    $('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=!editable);
    $('opening').textContent=app.status!=='APPROVED'?'':app.opening_state==='OPENED'?'商家后台已开通；微信支付状态待核验。':
      app.opening_state==='OPENING_PENDING'?'入驻审核已通过；商家后台正在开通。':
      app.opening_state==='ACCESS_SUSPENDED'?'商家后台已暂停，请联系平台管理员。':'入驻审核已通过；商家后台待开通。';
    if(app.opening_state==='OPENED'){const link=document.createElement('a');link.href='/merchant/workbench';link.textContent='进入商家工作台';$('opening').append(document.createTextNode(' '),link);}
    $('openingActions').hidden=!reviewMode||app.status!=='APPROVED'||app.opening_state==='OPENED'||!app.opening_workspaces?.length;
    $('openingWorkspace').replaceChildren();for(const workspace of app.opening_workspaces||[]){const option=document.createElement('option');option.value=workspace;option.textContent=workspace;$('openingWorkspace').append(option);}
    refreshConditions();
    if(!reviewMode)setForm(app);else syncReviewLayout(app);
  }
  function resetHistory(){
    historyGeneration++;historyCursor=null;historyRequest=null;
    $('historyRows').replaceChildren();$('historyMaterials').replaceChildren();$('moreHistory').hidden=true;$('historyStatus').textContent='';
  }
  async function loadHistory(more=false){
    if(!current)throw Error('请先打开申请详情。');
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
        detail.textContent='操作账号 '+record.actor+' · '+(record.occurred_at===null?'时间未记录':new Date(record.occurred_at*1000).toISOString());
        reason.textContent=record.note===null?'旧审核原因未完整留存，不以当前意见补填。':record.note?'当次说明：'+record.note:'本次事件无审核说明。';
        row.append(title,detail,reason);
        const materials=document.createElement('p');materials.textContent=record.materials===null?'旧审核与材料版本的关联未留存。':
          record.materials.map(m=>materialKindTitle(m.kind)+'：第'+m.sequence+'版（'+m.version+'）'+(m.review?' · '+m.review.decision+' '+m.review.note:'')).join('；')||'该版本尚无上传资料';
        row.append(materials);nodes.push(row);
      }
      if(!isCurrent())return;
      $('historyRows').append(...nodes);historyCursor=result.next_revision;$('moreHistory').hidden=!result.has_more;
      $('historyMaterials').replaceChildren();
      for(const material of result.material_versions){const row=document.createElement('p');row.textContent=materialKindTitle(material.kind)+' · 第'+material.sequence+'版 · '+material.version+' · 上传账号 '+material.actor+' · '+new Date(material.created_at*1000).toISOString();$('historyMaterials').append(row);}
      $('historyStatus').textContent=(result.has_more?'已读取本页，可继续加载历史。':'本申请历史已读取至末页。')+(result.material_versions_truncated?'历史资料较多，请联系管理员核对。':'');
    }catch(error){if(isCurrent()){resetHistory();$('historyStatus').textContent='申请历史读取失败，请重试。';throw Error('申请历史读取失败，请重试。');}}
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
        }catch(error){if(noticeSelected(selected)){resetNotices();throw Error('申请状态读取失败，请重试。');}}
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
    for(const kind of materialKinds(app)){const record=app.materials[kind];
      const row=document.createElement('div');row.className='material';row.dataset.kind=kind;
      const title=document.createElement('strong');title.textContent=materialKindTitle(kind)+(app.required_materials.includes(kind)?' *':'（选填）');row.append(title);
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
  // Discard only browser-held reviewer detail before reading another application.
  // A refused/unknown read must not leave the previous applicant actionable.
  function clearReviewSelection(){
    clearWechat();resetHistory();resetNotices();current=null;
    preserveReviewVersion();for(const id of ['summary','materials','reviewNote','opening','openingWorkspace'])$(id).replaceChildren();
    for(const id of ['legal_name','store_name','address','contact','note'])$(id).value='';
    $('applicationTitle').textContent='入驻申请';$('applicationState').textContent='';$('applicationVersion').textContent='';
    $('detail').hidden=true;$('reviewActions').hidden=true;$('openingActions').hidden=true;
    $('withdrawConfirmed').checked=false;withdrawalControls();syncReviewLayout(null);
  }
  const providerBucket=value=>({APPLYMENT_STATE_AUDITING:'PENDING_REVIEW',APPLYMENT_STATE_TO_BE_CONFIRMED:'PENDING_CONFIRMATION',APPLYMENT_STATE_TO_BE_SIGNED:'PENDING_CONFIRMATION',APPLYMENT_STATE_SIGNING:'OPENING',APPLYMENT_STATE_EDITTING:'CORRECTION_OR_REJECTION',APPLYMENT_STATE_REJECTED:'CORRECTION_OR_REJECTION',APPLYMENT_STATE_CANCELED:'EXCEPTION',APPLYMENT_STATE_FINISHED:'COMPLETED'}[value]||(['NOT_SUBMITTED','NOT_VERIFIED',undefined,null].includes(value)?'PENDING_SUBMISSION':'EXCEPTION'));
  const providerBucketText=value=>({PENDING_SUBMISSION:'尚未提交微信',PENDING_REVIEW:'待微信审核',PENDING_CONFIRMATION:'待商家实名确认',OPENING:'微信开通处理中',CORRECTION_OR_REJECTION:'待补正 / 已驳回',EXCEPTION:'异常待处理',COMPLETED:'微信进件已完成'}[value]||'微信状态待确认');
  function renderReviewList(target,applications,openApplication){
    const scroll=document.createElement('div'),table=document.createElement('table'),head=document.createElement('thead'),body=document.createElement('tbody'),header=document.createElement('tr');scroll.className='review-list-scroll admission-record-card';table.className='review-list-table';
    for(const label of ['申请编号','商家名称','门店名称','主体类型','联系人','经营类目','商家审核状态','微信审核状态','申请分账比例','更新时间','操作']){const th=document.createElement('th');th.textContent=label;header.append(th);}head.append(header);table.append(head,body);scroll.append(table);target.append(scroll);
    for(const app of applications){const row=document.createElement('tr'),workflow=app.wechat_provider_workflow||{},split=app.split_participation===true&&Number.isSafeInteger(app.requested_split_bps)?(app.requested_split_bps/100).toFixed(2)+'%':'不参与',updated=Number.isInteger(app.updated_at)?new Date(app.updated_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):app.updated_at||workflow.observed_at||'—',values=[app.application,app.fields.legal_name||'未填写',app.fields.store_name||'未填写',app.entity_type==='ENTERPRISE'?'企业':app.entity_type==='SOLE_PROPRIETOR'?'个体工商户':'未填写',app.fields.contact||'未填写',app.category==='FOOD'?'餐饮/食品':app.category==='GENERAL'?'一般经营类目':'未填写',states[app.status]||'状态待确认',providerBucketText(workflow.bucket),split,updated];for(const value of values){const td=document.createElement('td');td.textContent=value;row.append(td);}const action=document.createElement('td'),open=button('查看详情',()=>openApplication(app));open.className='admission-review-button';action.append(open);row.append(action);body.append(row);const compatibilityOpen=button('查看详情',()=>openApplication(app));compatibilityOpen.hidden=true;target.append(compatibilityOpen);}
    if(!applications.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=11;cell.className='review-empty-state';cell.textContent='暂无符合条件的商家申请';row.append(cell);body.append(row);}
  }
  async function readListedApplication(application){
    const revision=reviewQueueRevision,filter=$('statusFilter').value;if(reviewMode)clearReviewSelection();
    const result=await request(reviewMode?'review_read':'read',{application});if(reviewMode&&(revision!==reviewQueueRevision||filter!==$('statusFilter').value))return;render(result);
    if(reviewMode&&result.wechat_provider_workflow&&result.wechat_provider_workflow.bucket!=='PENDING_SUBMISSION')await automaticWechatQuery(application);
  }
  async function list(append=false){const target=$(reviewMode?'applications':'mine'),identity=generation,filter=$('statusFilter').value;if(reviewMode&&!append){reviewQueueRevision++;clearReviewSelection();target.replaceChildren();cursor=null;$('moreApplications').hidden=true;}const revision=reviewQueueRevision;
    try{const result=await request(reviewMode?'review_list':'mine',{status:filter,...(append&&cursor?{cursor}:{})});if(reviewMode&&(identity!==generation||revision!==reviewQueueRevision||filter!==$('statusFilter').value))return;if(!append)target.replaceChildren();const keywords=reviewMode&&$('reviewMerchantKeyword')?$('reviewMerchantKeyword').value.trim().toLowerCase().split(/\s+/).filter(Boolean):[],wechatFilter=reviewMode&&$('wechatTaskFilter')?$('wechatTaskFilter').value:'ALL',visibleApplications=result.applications.filter(app=>{const text=[app.application,app.fields.store_name,app.fields.legal_name,app.fields.contact,app.entity_type,app.category,app.status,app.wechat_provider_workflow?.bucket].join(' ').toLowerCase();return keywords.every(keyword=>text.includes(keyword))&&(wechatFilter==='ALL'||(wechatFilter==='COMPLETED'?app.wechat_provider_workflow?.bucket==='COMPLETED':app.wechat_provider_workflow?.bucket!=='COMPLETED'));});
      if(reviewMode)renderReviewList(target,visibleApplications,async app=>{if(identity!==generation||revision!==reviewQueueRevision||filter!==$('statusFilter').value)return;await readListedApplication(app.application);});else for(const app of visibleApplications)target.append(button((app.fields.store_name||'未命名申请')+' · '+(states[app.status]||app.status),async()=>readListedApplication(app.application)));
      if(reviewMode&&$('reviewQueueCount'))$('reviewQueueCount').textContent=visibleApplications.length+' 条'+(result.next_cursor?' · 可加载下一页':'');
      cursor=result.next_cursor||null;$('moreApplications').hidden=!cursor;
      if(!reviewMode&&!append)render(result.applications[0]||null);
      message(reviewMode?'':result.applications.length?'已读取最新入驻状态。':'尚无申请，请填写经营信息并保存草稿。');
    }catch(error){if(reviewMode&&identity===generation&&revision===reviewQueueRevision){reviewQueueRevision++;target.replaceChildren();cursor=null;$('moreApplications').hidden=true;clearReviewSelection();if($('reviewQueueCount'))$('reviewQueueCount').textContent='读取失败 · 0 条商家申请';}throw error;}}

  async function load(){return run(async()=>{catalog=await request('catalog');await list();});}
  $('split_participation').addEventListener('change',()=>{const enabled=$('split_participation').checked;$('requested_split_percent').disabled=!enabled;if(!enabled)$('requested_split_percent').value='0';else if(Number($('requested_split_percent').value)<=0)$('requested_split_percent').value='1.00';});
  $('profile').addEventListener('submit',event=>{event.preventDefault();run(async()=>{const licenseDraft=[...wechatControls].filter(([path])=>path.startsWith('subject_info.business_license_info.')).map(([path,input])=>[path,input.value]),participates=$('split_participation').checked,requested=Math.round(Number($('requested_split_percent').value)*100);if(participates&&(!Number.isSafeInteger(requested)||requested<=0||requested>10000))throw Error('请填写 0.01% 至 100% 的申请分账比例。');render(await request('save',{application:current?.application||null,revision:current?.revision||0,
    sales_scenes_type:selectedScenes(),identity_type:$('identity_type').value,redemption_percent:Number($('redemption_percent').value),split_participation:participates,requested_split_bps:participates?requested:0,fields:draftFields(),entity_type:$('entity_type').value,category:$('category').value,delegated:$('delegated').checked}));for(const [path,value]of licenseDraft)wechatControls.get(path).value=value;message('申请草稿已保存；分账参与为自愿选择，爱心积分抵扣比例单独保存。');});});
  $('newApplication').addEventListener('click',()=>{if(busy)return;clearWechat();resetHistory();resetNotices();current=null;for(const key of ['legal_name','store_name','address','contact'])$(key).value='';setForm(null);$('profile').querySelectorAll('input,select,button').forEach(e=>e.disabled=false);$('requested_split_percent').disabled=true;render(null);message('请填写新申请。');});
  $('submitApplication').addEventListener('click',()=>run(async()=>{render(await request('submit',{application:current.application,revision:current.revision}));message('申请已提交，请等待入驻审核。');}));
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
  $('statusFilter').addEventListener('change',()=>{if(reviewMode){reviewQueueRevision++;$('applications').replaceChildren();cursor=null;$('moreApplications').hidden=true;clearReviewSelection();}return run(list);});$('moreApplications').addEventListener('click',()=>run(()=>list(true)));
  $('openWorkbench').addEventListener('click',()=>run(async()=>{render(await request('open_workbench',{application:current.application,revision:current.revision,workspace:$('openingWorkspace').value}));message('工作台开通状态已更新。');}));
  const definitions=[
    ['contact_info.contact_type','管理员身份（法人/经营者或授权经办人）'],['contact_info.contact_id_doc_type','经办人证件类型'],['contact_info.contact_id_number','经办人证件号码'],['contact_info.contact_period_begin','经办人证件有效期开始'],['contact_info.contact_period_end','经办人证件有效期结束或长期'],['contact_info.contact_name','超级管理员姓名'],['contact_info.mobile_phone','超级管理员手机'],['contact_info.contact_email','超级管理员邮箱'],
    ['subject_info.business_license_info.license_number','统一社会信用代码或注册号'],['subject_info.business_license_info.merchant_name','营业执照商户名称'],['subject_info.business_license_info.legal_person','法定代表人或经营者姓名'],['subject_info.business_license_info.license_address','营业执照注册地址'],['subject_info.business_license_info.period_begin','营业执照有效期开始'],['subject_info.business_license_info.period_end','营业执照有效期结束或长期'],
    ['subject_info.identity_info.id_doc_type','法人/经营者证件类型'],['subject_info.identity_info.id_doc_info.id_doc_name','其他证件姓名'],['subject_info.identity_info.id_doc_info.id_doc_number','其他证件号码'],['subject_info.identity_info.id_doc_info.id_doc_address','其他证件住址（企业适用）'],['subject_info.identity_info.id_doc_info.doc_period_begin','其他证件有效期开始'],['subject_info.identity_info.id_doc_info.doc_period_end','其他证件有效期结束或长期'],['subject_info.identity_info.id_card_info.id_card_name','经营者或法人证件姓名'],['subject_info.identity_info.id_card_info.id_card_number','经营者或法人身份证号'],['subject_info.identity_info.id_card_info.id_card_address','身份证住址（企业适用）'],['subject_info.identity_info.id_card_info.card_period_begin','身份证有效期开始'],['subject_info.identity_info.id_card_info.card_period_end','身份证有效期结束或长期'],
    ['business_info.merchant_shortname','商户简称'],['business_info.service_phone','客服电话'],['business_info.sales_info.mini_program_info.mini_program_appid','服务商小程序AppID'],['settlement_info.settlement_id','微信结算规则编号'],['settlement_info.qualification_type','微信结算行业名称'],
    ['bank_account_info.bank_account_type','结算账户类型（对公账户或个人银行卡）'],['bank_account_info.account_name','结算开户名称'],['bank_account_info.account_bank','开户银行'],['bank_account_info.bank_branch_id','支行联行号（银行要求时填写）'],['bank_account_info.bank_name','开户银行全称（银行要求时填写）'],['bank_account_info.account_number','结算银行账号']];
  for(let i=0;i<4;i++)for(const [field,title]of [['ubo_id_doc_type','证件类型'],['ubo_id_doc_name','姓名'],['ubo_id_doc_number','证件号'],['ubo_id_doc_address','住址'],['ubo_period_begin','证件有效期开始'],['ubo_period_end','证件有效期结束或长期']])definitions.push(['subject_info.ubo_info_list.'+i+'.'+field,'受益人'+(i+1)+'：'+title+'（按官方适用条件填写完整受益人名单，含适用法人）']);
  for(const [scene,title]of [[miniScene,'小程序经营（默认）'],[storeScene,'线下门店经营']]){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.scene=scene;input.checked=scene===miniScene;input.addEventListener('change',()=>{materialContext++;refreshConditions();});label.textContent=title;label.append(input);sceneControls.set(scene,input);$('wechatFields').append(label);}
  definitions.push(['business_info.sales_info.biz_store_info.biz_store_name','线下门店名称'],['business_info.sales_info.biz_store_info.biz_address_code','线下门店地区代码（填写已核实的官方代码）'],['business_info.sales_info.biz_store_info.biz_store_address','线下门店详细地址']);
  const enumControls={
    'contact_info.contact_type':[['LEGAL','法人/经营者'],['SUPER','授权经办人']],
    'subject_info.identity_info.id_doc_type':[['IDENTIFICATION_TYPE_IDCARD','居民身份证'],['IDENTIFICATION_TYPE_OVERSEA_PASSPORT','境外护照'],['IDENTIFICATION_TYPE_HONGKONG_MACAO','港澳居民证件'],['IDENTIFICATION_TYPE_TAIWAN','台湾居民证件']],
    'bank_account_info.bank_account_type':[['BANK_ACCOUNT_TYPE_CORPORATE','对公账户'],['BANK_ACCOUNT_TYPE_PERSONAL','个人银行卡']]
  };
  for(const [path,title]of definitions){const label=document.createElement('label'),input=document.createElement(enumControls[path]?'select':'input');label.textContent=title;input.autocomplete='off';input.dataset.path=path;if(enumControls[path])for(const [value,text]of enumControls[path]){const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option);}else input.maxLength=512;wechatControls.set(path,input);label.append(input);if(!reviewMode&&path.startsWith('subject_info.business_license_info.')){input.setAttribute('form','wechatProfile');$('licenseFields').append(label);}else $('wechatFields').append(label);}
  const mediaFields={business_license:'subject_info.business_license_info.license_copy',identity_front:'subject_info.identity_info.id_card_info.id_card_copy',identity_back:'subject_info.identity_info.id_card_info.id_card_national',mini_program_screenshot:'business_info.sales_info.mini_program_info.mini_program_pics'};
  Object.assign(mediaFields,{storefront_photo:'business_info.sales_info.biz_store_info.store_entrance_pic',interior_photo:'business_info.sales_info.biz_store_info.indoor_pic',operator_identity:'contact_info.contact_id_doc_copy',operator_identity_back:'contact_info.contact_id_doc_copy_back',operator_authorization:'contact_info.business_authorization_letter',industry_permit:'settlement_info.qualifications'});
  for(let i=0;i<4;i++){mediaFields['ubo_'+(i+1)+'_front']='subject_info.ubo_info_list.'+i+'.ubo_id_doc_copy';mediaFields['ubo_'+(i+1)+'_back']='subject_info.ubo_info_list.'+i+'.ubo_id_doc_copy_back';}
  for(const [kind,path]of Object.entries(mediaFields)){const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.path=path;wechatControls.set(path,hidden);$('wechatFields').append(hidden);const button=document.createElement('button');button.type='button';button.dataset.material=kind;button.textContent='同步已上传的'+materialKindTitle(kind);button.onclick=()=>run(async()=>{if(!current)throw Error('先打开申请');if(invalidLoadedScenes)throw Error('经营场景配置需人工核对，不能同步资料。');const scene=['storefront_photo','interior_photo'].includes(kind)?storeScene:kind==='mini_program_screenshot'?miniScene:null;if(scene&&!selectedScenes().includes(scene))throw Error('请先选择对应经营场景。');const context=materialContext,application=current.application,type=controlValue('subject_info.identity_info.id_doc_type')||current.identity_type||'IDENTIFICATION_TYPE_IDCARD';const r=await request('wechat_media',{application,kind});if(context!==materialContext||application!==current?.application)throw Error('资料条件已变化，请重新同步。');if(kind==='identity_front'||kind==='identity_back'){if(type!=='IDENTIFICATION_TYPE_IDCARD'){const target='subject_info.identity_info.id_doc_info.'+(kind==='identity_front'?'id_doc_copy':'id_doc_copy_back');setPath((wechatRecord??={version:0,profile:{}}).profile??={},target,r.media_id);}else hidden.value=r.media_id;}else hidden.value=r.media_id;message('资料已上传微信；请保存微信资料草稿。');});$('wechatMedia').append(button);}
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
  const wechatStateText=value=>({DRAFT:'资料草稿',INTERNAL_REVIEW:'平台审核中',INTERNAL_APPROVED:'平台审核通过',CORRECTION:'待补充资料',SUBMITTED:'已提交微信',APPLYMENT_STATE_EDITTING:'待完善资料',APPLYMENT_STATE_AUDITING:'微信审核中',APPLYMENT_STATE_REJECTED:'微信审核驳回',APPLYMENT_STATE_TO_BE_CONFIRMED:'待账户确认',APPLYMENT_STATE_TO_BE_SIGNED:'待签约',APPLYMENT_STATE_SIGNING:'签约处理中',APPLYMENT_STATE_FINISHED:'签约完成',APPLYMENT_STATE_CANCELED:'申请已取消'}[value]||'状态待确认');
  let industryReviewControls=[];
  function renderIndustryReview(record,state){
    industryReviewControls=[];
    if(!reviewMode||!record.industry_review)return;
    const section=document.createElement('section'),title=document.createElement('h3');title.textContent='行业资质条件审核';section.append(title);
    const review=record.industry_review;
    if(review.status!=='READY'){
      const warning=document.createElement('p');warning.textContent='行业或当前资质资料尚不完整，请核对原申请并要求补充；不能按照片数量认定资质满足。';section.append(warning);state.append(section);return;
    }
    const plan=review.plan;
    const heading=document.createElement('p');heading.textContent='实际行业：'+plan.qualification_type+'。请按真实业务核对官方条件，备选与同时提供要求不能混淆。';section.append(heading);
    if(!plan.requires_explicit_review){const note=document.createElement('p');note.textContent='当前行业无额外条件分支；原资料审核仍须完成。';section.append(note);state.append(section);return;}
    plan.branches.forEach((branch,index)=>{
      const field=document.createElement('fieldset'),legend=document.createElement('legend'),description=document.createElement('p'),select=document.createElement('select'),reason=document.createElement('textarea');
      legend.textContent='官方条件 '+(index+1);description.textContent=branch.description;
      for(const [value,text] of [['','请选择实际适用结论'],['APPLICABLE_SATISFIED','适用，已核对完整满足'],['NOT_APPLICABLE','本商户实际业务不适用']]){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
      select.setAttribute('aria-label','条件'+(index+1)+'适用结论');reason.setAttribute('aria-label','条件'+(index+1)+'核验说明');reason.placeholder='说明所核证据或不适用原因，不得以照片张数替代条件判断';
      const materials=[];field.append(legend,description,select);
      for(const binding of plan.current_qualifications){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=binding.kind;label.append(input,document.createTextNode('本条件对应：'+binding.kind));field.append(label);materials.push(input);}
      field.append(reason);section.append(field);industryReviewControls.push({branch_index:index,select,reason,materials});
    });
    state.append(section);
  }
  function industryBranchAssessments(){
    const review=wechatRecord?.industry_review;
    if(!review||review.status!=='READY')throw Error('请重新读取完整行业资料后审核');
    if(!review.plan.requires_explicit_review)return undefined;
    if(industryReviewControls.length!==review.plan.branches.length)throw Error('行业审核条件尚未完整载入');
    return industryReviewControls.map(item=>{
      if(!item.select.value||!item.reason.value.trim())throw Error('请逐项选择真实适用结论并填写核验说明');
      return {branch_index:item.branch_index,applicability:item.select.value,material_kinds:item.materials.filter(x=>x.checked).map(x=>x.value),rationale:item.reason.value.trim()};
    });
  }
  function showWechat(r){
    wechatRecord=r;setScenes(r.profile?.business_info?.sales_info?.sales_scenes_type);
    const state=$('wechatState'),card=document.createElement('dl'),bucket=providerBucket(r.provider_state);state.replaceChildren();
    for(const [label,value]of [['资料状态',wechatStateText(r.state)],['微信处理阶段',providerBucketText(bucket)],['微信审核状态',wechatStateText(r.provider_state)],['微信申请编号',r.applyment_id||'尚未生成'],['最近同步',r.provider_observed_at||'尚未同步'],['审核意见',r.opinion||r.audit_detail||'暂无审核意见']]){
      const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=typeof value==='string'?value:JSON.stringify(value);card.append(dt,dd);
    }
    const version=document.createElement('span');version.hidden=true;version.textContent='version '+String(r.version??0);state.append(card,version);renderIndustryReview(r,state);
    if(bucket==='PENDING_CONFIRMATION'&&r.provider_sign_url&&r.provider_sign_url_proof){
      const actions=document.createElement('div'),hint=document.createElement('p'),link=document.createElement('a'),copy=button('复制微信实名确认链接',async()=>{await navigator.clipboard.writeText(r.provider_sign_url);message('官方实名确认链接已复制，可转发给商家超级管理员。');});actions.className='wechat-sign-actions';hint.textContent='微信审核已进入商家实名确认 / 签约阶段。以下入口来自微信支付已验签查询结果，可复制转发给商家超级管理员。';link.href=r.provider_sign_url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='打开微信支付官方实名确认入口';actions.append(hint,link,copy);
      if(navigator.share){const share=button('转发确认入口',async()=>navigator.share({title:'微信支付商家实名确认',text:'请由商家超级管理员完成微信支付实名确认 / 签约。',url:r.provider_sign_url}));actions.append(share);}state.append(actions);
      const application=current?.application,figure=document.createElement('figure'),caption=document.createElement('figcaption');figure.className='wechat-certification-qr';caption.textContent='服务商认证二维码';figure.append(caption);actions.prepend(figure);request('wechat_sign_qr',{application}).then(result=>{if(application!==current?.application||result.application!==application)return;const image=document.createElement('img');image.src=result.svg_data;image.alt='微信支付服务商认证二维码';image.width=240;image.height=240;figure.insertBefore(image,caption);}).catch(()=>{if(application===current?.application){const unavailable=document.createElement('p');unavailable.textContent='认证二维码暂未生成，请使用上方官方确认入口。';figure.prepend(unavailable);}});
    }
    for(const [path,e]of wechatControls){const value=getPath(r.profile,path);e.value=Array.isArray(value)?value.join(','):value??'';}materialContext++;refreshConditions();
  }
  const wechatVersion=()=>{if(!current)throw Error('先打开申请');return wechatRecord?.version||0;};
  async function automaticWechatQuery(application){
    const record=await request('wechat_review_read',{application});
    if(application!==current?.application)return;
    showWechat(record);
    const bucket=providerBucket(record.provider_state);
    if(record.business_code&&!['COMPLETED','EXCEPTION'].includes(bucket)){
      try{const synced=await request('wechat_query',{application});if(application===current?.application)showWechat(synced);}
      catch(error){if(application===current?.application)message('已显示最近保存状态；微信官方状态自动同步失败：'+error.message,'warning');}
    }
  }
  $('wechatRead').onclick=()=>run(async()=>{if(!current)throw Error('先打开申请');showWechat(await request(reviewMode?'wechat_review_read':'wechat_read',{application:current.application}));});
  $('wechatProfile').onsubmit=e=>{e.preventDefault();run(async()=>{const expected_version=wechatVersion();if(invalidLoadedScenes)throw Error('已保存的经营场景配置无效或尚未支持，请人工核对；禁止覆盖保存。');const scenes=selectedScenes(),context=materialContext,application=current.application;if(!scenes.length)throw Error('请至少选择一个经营场景。');const profile=wechatRecord?.profile?structuredClone(wechatRecord.profile):{};for(const [path,input]of wechatControls){if(input.value)setPath(profile,path,path.endsWith('_pics')||path.endsWith('qualifications')||path.endsWith('store_entrance_pic')||path.endsWith('indoor_pic')?input.value.split(',').map(s=>s.trim()).filter(Boolean):input.value);else{const parts=path.split('.');const at=parts.slice(0,-1).reduce((o,k)=>o?.[k],profile);if(at)delete at[parts.at(-1)];}}if(profile.subject_info?.ubo_info_list)profile.subject_info.ubo_info_list=profile.subject_info.ubo_info_list.filter(u=>u&&Object.keys(u).length);if(profile.subject_info&&(!profile.subject_info.ubo_info_list?.length||current.entity_type!=='ENTERPRISE'))delete profile.subject_info.ubo_info_list;
    if(profile.contact_info?.contact_type!=='SUPER')for(const field of ['contact_id_doc_type','contact_id_number','contact_id_doc_copy','contact_id_doc_copy_back','contact_period_begin','contact_period_end'])delete profile.contact_info?.[field];
    else if(profile.contact_info.contact_id_doc_type===passport)delete profile.contact_info.contact_id_doc_copy_back;
    for(const ubo of profile.subject_info?.ubo_info_list||[])if(ubo.ubo_id_doc_type===passport)delete ubo.ubo_id_doc_copy_back;setPath(profile,'subject_info.subject_type',current.entity_type==='ENTERPRISE'?'SUBJECT_TYPE_ENTERPRISE':'SUBJECT_TYPE_INDIVIDUAL');setPath(profile,'subject_info.identity_info.id_holder_type','LEGAL');if(!profile.subject_info.identity_info.id_doc_type)setPath(profile,'subject_info.identity_info.id_doc_type',current.identity_type||'IDENTIFICATION_TYPE_IDCARD');if(!profile.contact_info?.contact_type)setPath(profile,'contact_info.contact_type','LEGAL');if(profile.subject_info.identity_info.id_doc_type==='IDENTIFICATION_TYPE_IDCARD')delete profile.subject_info.identity_info.id_doc_info;else delete profile.subject_info.identity_info.id_card_info;setPath(profile,'business_info.sales_info.sales_scenes_type',scenes);const saved=await request('wechat_save',{application,expected_version,profile});if(context!==materialContext||application!==current?.application)throw Error('资料条件已变化；保存结果请刷新后核对。');render(await request(reviewMode?'review_read':'read',{application}));showWechat(saved);});};
  $('wechatSubmitReview').onclick=()=>run(async()=>showWechat(await request('wechat_submit_review',{application:current.application,expected_version:wechatVersion()})));
  for(const [id,decision]of [['wechatApprove','INTERNAL_APPROVED'],['wechatCorrect','CORRECTION']])$(id).onclick=()=>run(async()=>{const params={application:current.application,expected_version:wechatVersion(),decision,opinion:$('wechatOpinion').value};if(decision==='INTERNAL_APPROVED'&&wechatRecord?.industry_review){const assessments=industryBranchAssessments();if(assessments)params.industry_branch_assessments=assessments;}showWechat(await request('wechat_review',params));});
  $('wechatExecute').onclick=()=>run(async()=>showWechat(await request('wechat_execute',{application:current.application,expected_version:wechatVersion()})));
  $('wechatQuery').onclick=()=>run(async()=>showWechat(await request('wechat_query',{application:current.application})));
  // ADMISSION_REVIEW_LAYOUT_BEGIN: review route only, original controls moved not duplicated.
  function preserveReviewVersion(){if(reviewLayout){const node=$('applicationVersion');if(node)reviewLayout.card.append(node);}}
  function syncReviewLayout(app){if(!reviewMode||!reviewLayout)return;reviewLayout.app=app;applyReviewStage();if(!app){reviewLayout.controls.open=false;reviewLayout.contextFields.replaceChildren();return;}const versionNode=$('applicationVersion'),splitPercent=value=>Number.isSafeInteger(value)?(value/100).toFixed(2)+'%':'尚未核定',providerText=value=>typeof providerBucketText==='function'?providerBucketText(value):'微信状态待确认';$('summary').replaceChildren();const extra=[['申请编号 / 版本',versionNode],['商家名称',app.fields.legal_name||'未填写'],['门店名称',app.fields.store_name||'未填写'],['经营地址',app.fields.address||'未填写'],['联系人',app.fields.contact||'未填写'],['主体类型',app.entity_type==='ENTERPRISE'?'企业':app.entity_type==='SOLE_PROPRIETOR'?'个体工商户':'未填写'],['办理人',app.delegated===true?'授权经办人':app.delegated===false?'法人或经营者本人':'未填写'],['资料清单',(app.required_materials||[]).map(k=>catalog.materials.find(m=>m.id===k)?.title||k).join('、')||'无'],['材料核验说明','未在本摘要核验'],['分账参与意愿',app.split_participation===true?'自愿参加':'不参加'],['申请分账比例',splitPercent(app.requested_split_bps)],['微信核定最高比例',splitPercent(app.provider_max_split_bps)],['最终生效分账比例',splitPercent(app.effective_split_bps)],['爱心积分抵扣比例（申请值）',String(app.redemption_percent??0)+'%'],['爱心积分抵扣比例（审核生效）',String(app.approved_redemption_percent??0)+'%'],['审核状态',(states[app.status]||app.status)+(app.reviewer_note?'；'+app.reviewer_note:'')],['微信进件状态',providerText(app.wechat_provider_workflow?.bucket)]];for(const [label,value]of extra){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;if(value===versionNode)dd.append(versionNode);else dd.textContent=value===undefined?'未填写':String(value);$('summary').append(dt,dd);}reviewLayout.contextFields.replaceChildren();for(const [label,value]of [['门店',app.fields.store_name||'未填写'],['审核状态',states[app.status]||app.status],['微信进件',providerText(app.wechat_provider_workflow?.bucket)]]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;reviewLayout.contextFields.append(dt,dd);}applyReviewStage();}

  function returnReviewList(){if(!reviewLayout)return;reviewLayout.app=null;reviewLayout.controls.open=false;$('detail').hidden=true;applyReviewStage();}
  function applyReviewStage(){
    if(!reviewLayout)return;const r=reviewLayout,selected=!!r.app,operations=selected&&r.controls.open;
    $('queue').hidden=selected;$('moreApplications').hidden=selected||!cursor;r.filters.hidden=selected;
    r.card.hidden=operations;r.back.hidden=operations;r.operationContext.hidden=!operations;r.operationBack.hidden=!operations;
    r.top.hidden=!selected;r.top.textContent='‹ 返回商家审核';r.top.href='#admission-list';
    $('title').textContent=operations?'商家审核 · 审核操作':selected?'商家审核 · 详情':'商家审核';
    r.controlsSummary.textContent=operations?'收起审核操作，返回申请详情':'进入审核操作';
    (operations?r.operationContext:r.card).append(r.stateRow);
  }
  function installReviewAdminShell(){
    document.title='商家审核 · 社区分账管理后台';
    const header=document.querySelector('body>header'),main=document.querySelector('body>main');if(!header||!main||header===main||typeof document.body.insertBefore!=='function'||typeof header.replaceChildren!=='function')return;
    header.className='review-admin-brand';const brand=document.createElement('strong'),role=document.createElement('span');brand.textContent='社区分账管理后台';role.textContent='平台管理者后台';header.replaceChildren(brand,role);
    const aside=document.createElement('aside'),disclosure=document.createElement('details'),navigationSummary=document.createElement('summary'),navigationIcon=document.createElement('span'),navigationLabel=document.createElement('span'),backdrop=document.createElement('button'),nav=document.createElement('nav');aside.className='review-admin-sidebar';disclosure.className='review-navigation-disclosure';navigationIcon.className='review-navigation-icon';navigationIcon.setAttribute('aria-hidden','true');navigationIcon.textContent='☰';navigationLabel.className='review-navigation-label';navigationLabel.textContent='功能导航';navigationSummary.append(navigationIcon,navigationLabel);backdrop.type='button';backdrop.className='review-navigation-backdrop';backdrop.setAttribute('aria-label','关闭功能导航');nav.setAttribute?.('aria-label','商家审核功能');
    const groups=[['总览',[['首页','/community-preview/community/portal']]],['商家管理',[]]];
    const topGroups=[];
    for(const [title,items]of groups){const group=document.createElement('details'),summary=document.createElement('summary');group.open=title==='商家管理';summary.textContent=title;group.addEventListener('toggle',()=>{if(!group.open)return;for(const other of topGroups)if(other!==group)other.open=false;});topGroups.push(group);group.append(summary);for(const [label,route]of items){const link=document.createElement('a');link.href=route;link.textContent=label;group.append(link);}if(title==='商家管理'){const reviewGroup=document.createElement('details'),reviewSummary=document.createElement('summary');reviewGroup.className='review-task-navigation';reviewGroup.open=true;reviewSummary.textContent='商家审核';reviewGroup.append(reviewSummary);const filters=[];for(const [label,filter]of [['待处理申请','ACTIVE'],['全部申请','ALL'],['已完成申请','COMPLETED']]){const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.wechatFilter=filter;button.className=filter==='ACTIVE'?'active':'';button.addEventListener('click',()=>{const select=$('wechatTaskFilter');if(select){select.value=filter;for(const item of filters)item.classList.toggle('active',item===button);returnReviewList();run(list);}history.replaceState(null,'',location.pathname);disclosure.open=false;});filters.push(button);reviewGroup.append(button);}group.append(reviewGroup);}nav.append(group);}
    disclosure.append(navigationSummary,backdrop,nav);aside.append(disclosure);document.body.insertBefore(aside,main);
    const syncNavigation=()=>document.body.classList.toggle('review-navigation-open',disclosure.open);disclosure.open=false;disclosure.addEventListener('toggle',syncNavigation);backdrop.addEventListener('click',()=>{disclosure.open=false;});syncNavigation();
  }
  function setupReviewLayout(){if(!reviewMode||!document.body)return;document.body.classList.add('admission-review');const header=document.querySelector('header > span');if(header)header.textContent='社区服务 · 平台';const intro=document.querySelector('.intro');if(intro)for(const node of intro.children)if(node!==$('title'))node.hidden=true;const queueHeading=$('queue').querySelector('h2');if(queueHeading){queueHeading.hidden=true;queueHeading.textContent='';}
    const card=document.createElement('article'),h=document.createElement('h3'),controls=document.createElement('details'),summary=document.createElement('summary'),back=button('返回入驻审核列表',async()=>returnReviewList());card.className='admission-record-card';h.textContent='记录详情';card.append(h);controls.id='reviewOriginalControls';summary.textContent='进入审核操作';controls.append(summary);back.className='admission-review-button';
    const operationContext=document.createElement('article'),contextTitle=document.createElement('h3'),contextFields=document.createElement('dl'),operationBack=button('返回申请详情',async()=>{controls.open=false;applyReviewStage();});operationContext.className='admission-operation-context';contextTitle.textContent='当前申请';operationContext.append(contextTitle,contextFields);operationBack.className='admission-review-secondary';
    function group(id,label){const d=document.createElement('details'),title=document.createElement('summary');d.id=id;d.className='admission-operation-group';title.textContent=label;d.append(title);return d;}
    const materials=group('reviewMaterialsGroup','申请资质与逐份材料核对'),decisions=group('reviewDecisionGroup','入驻审核、补件与工作台开通'),history=group('reviewHistoryGroup','申请版本、审核历史与通知'),wechat=group('reviewWechatGroup','微信进件资料、审核与签约状态');decisions.open=true;
    let stateRow=null;for(const node of [...$('detail').children]){if(node.contains($('applicationTitle'))){stateRow=node;card.append(node);}else if(['applicationVersion','summary','reviewNote'].includes(node.id))card.append(node);else if(['reviewActions','opening','openingActions'].includes(node.id))decisions.append(node);else if(['applicationHistory','applicationNotices'].includes(node.id))history.append(node);else materials.append(node);}
    wechat.append($('wechatApplication'));controls.append(operationContext,decisions,materials,wechat,history,operationBack);$('detail').append(card,back,controls);
    const filters=document.createElement('div'),filterLabel=$('statusFilter').closest('label'),keywordLabel=document.createElement('label'),keyword=document.createElement('input'),wechatLabel=document.createElement('label'),wechatFilter=document.createElement('select'),queueMeta=document.createElement('div'),queueCount=document.createElement('span');filters.id='reviewListFilters';filters.className='review-filter-panel';keyword.id='reviewMerchantKeyword';keyword.type='search';keyword.placeholder='申请编号、商家名称、门店名称、联系人、经营类目、申请状态';keywordLabel.textContent='搜索';keywordLabel.append(keyword);keyword.addEventListener('change',()=>run(list));wechatFilter.id='wechatTaskFilter';for(const [value,label]of [['ACTIVE','待处理'],['COMPLETED','已完成'],['ALL','全部']]){const option=document.createElement('option');option.value=value;option.textContent=label;wechatFilter.append(option);}wechatLabel.textContent='微信进件';wechatLabel.append(wechatFilter);wechatFilter.addEventListener('change',()=>run(list));queueMeta.className='review-queue-heading';queueCount.id='reviewQueueCount';queueCount.textContent='正在加载';queueMeta.append(queueCount);$('reloadQueue').textContent='查询';filters.append(keywordLabel,filterLabel,wechatLabel,$('reloadQueue'));$('queue').prepend(queueMeta,filters);
    $('moreApplications').textContent='下一页';
    const top=document.createElement('a');top.id='reviewTopBack';top.className='admission-top-back';intro.prepend(top);top.addEventListener('click',event=>{if(reviewLayout.app){event.preventDefault();run(async()=>returnReviewList());}});
    reviewLayout={controls,controlsSummary:summary,card,back,filters,top,operationContext,contextFields,operationBack,stateRow,app:null};controls.addEventListener('toggle',applyReviewStage);installReviewAdminShell();syncReviewLayout(null);
  }
  setupReviewLayout();
  // ADMISSION_REVIEW_LAYOUT_END
  refreshLicense();
  // Raw entry pages must fail closed before the customer-center session bridge
  // supplies a current identity.  The bridge calls this again after login.
  window.configureCommunityOnboarding(null);
  if(typeof setInterval==='function')setInterval(()=>{if(reviewMode&&current&&!busy&&document.visibilityState==='visible')run(async()=>automaticWechatQuery(current.application));},300000);
})();
