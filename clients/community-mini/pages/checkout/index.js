const {makeClient} = require('../../client');
const {createPaymentFlow}=require('../../payment');
const {parseScene,createSession} = require('../../session');
const auth=require('../../customer-auth');
Page({
  data: {viewMode:'recommendations',activeSection:'recommendations',sessionReady:false,detailsCollapsed:false,selectedRecommendation:null,communities:[],communityCursor:null,communitiesMore:false,communityId:'',promotionCode:'',amount:'', reference:'', merchant:'', beforeAd:'', afterAd:'',afterAdVerified:false, status:'正在连接门店服务', pending:false,paymentsEnabled:false,commerceEnabled:false,profileVersion:null,nickname:'',profileContact:'',referralCode:'',projectCustomerId:'',userId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',products:[],productCursor:null,productsMore:false,productsPending:false,productsStatus:'',orders:[],orderCursor:null,ordersMore:false,orderDetails:null,orderDetailsPending:false,orderDetailsStatus:'',refundCurrent:null,refundRecoveryLoaded:false,refundRecoveryPending:false,refundRecoveryStatus:'',refundApplication:"",refundAmount:"",refundReason:"",projectTitle:"",projectRole:"",projectChecklist:[],projectMessages:[],projectMessagesCursor:null,projectMessagesMore:false,projectMessagesLoaded:false,projectMessagesStatus:'',projectFeedback:"",projectReference:"",projectReferenceKind:"SECRETREF",projectReferenceItem:"",projectReferenceRevision:0,projectState:""},
  openMerchantJoin(){if(this.scene)wx.navigateTo({url:'/pages/merchant-join/index?scene='+encodeURIComponent(this.scene)});},
  openMerchant(){if(this.scene)wx.navigateTo({url:'/pages/merchant/index?scene='+encodeURIComponent(this.scene)});},
  navigateSection(e){if(this._sceneStale){this.setData({status:'授权场景已切换，请重新进入对应门店'});return;}const section=e.currentTarget.dataset.section;const scene=this.scene||getApp().globalData.scene;if(!scene){this.setData({status:'缺少门店场景，无法切换页面'});return;}getApp().globalData.scene=scene;if(section==='recommendations'){this.setData({viewMode:'recommendations',activeSection:'recommendations',selectedRecommendation:null});return;}if(section==='orders'){this.setData({viewMode:'orders',activeSection:'orders',selectedRecommendation:null});return;}const url=section==='home'?'/pages/home/index':'/pages/profile/index';wx.navigateTo({url:url+'?scene='+encodeURIComponent(scene)});},
  onShow(){const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this._sceneStale){this._sceneStale=true;this.customerSessionRevoked('授权场景已切换，当前订单和客户资料已清除，请重新进入对应门店');return;}if(this._sceneStale)return;const mode=getApp().globalData.checkoutMode;getApp().globalData.checkoutMode='';const view=mode||this.data.viewMode||'recommendations';const selectedRecommendation=view==='store-detail'?(this.data.selectedRecommendation||{name:'示例门店 A',description:'门店资料来源待接入；商家资质未核验。'}):null;this.setData({viewMode:view,activeSection:view==='orders'?'orders':view==='profile'?'profile':'recommendations',selectedRecommendation});},
  openRecommendation(){this.setData({viewMode:'store-detail',activeSection:'recommendations',selectedRecommendation:{name:'示例门店 A',description:'平台推荐数据源待接入；此为展示样例，不代表真实推荐、资质或排名。'}});},
  backRecommendations(){this.setData({viewMode:'recommendations',activeSection:'recommendations',selectedRecommendation:null});},
  openOrders(){this.setData({viewMode:'orders',activeSection:'orders',selectedRecommendation:null});},
  hideOrderDetails(){this.setData({detailsCollapsed:true});},
  showOrderDetails(){this.setData({detailsCollapsed:false});},
  async onLoad(options) {
    this._sceneStale=false;
    if(options&&['recommendations','orders','store-detail'].includes(options.view)){const view=options.view;this.setData({viewMode:view,selectedRecommendation:view==='store-detail'?{name:'示例门店 A',description:'门店资料来源待接入；商家资质未核验。'}:null});}
    this._pageUnloaded=false;this._authEpoch=auth.current();this._consumerRequest=null;this._productRequest=null;this._projectMessagesContext=null;
    this.setData({projectMessages:[],projectMessagesCursor:null,projectMessagesMore:false,projectMessagesLoaded:false,projectMessagesStatus:''});
    this.setData({products:[],productCursor:null,productsMore:false,productsPending:false,productsStatus:''});
    this.resetOrderDetails();
    this._noticeContext=null;this._noticeRequest=null;
    this.setData({notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:''});
    const lifecycle=this._pageGeneration=(this._pageGeneration||0)+1;
    const current=()=>!this._pageUnloaded&&this._pageGeneration===lifecycle&&auth.active(this._authEpoch);
    try {
      const config = getApp().globalData;
      if (config.mode !== 'OFFLINE') {
        const scene = parseScene(options&&options.scene?options:{scene:config.scene});
        this.scene=scene;config.scene=scene;
        if(typeof options.promotion==='string'&&/^cp_[0-9a-f]{32}$/.test(options.promotion))this.setData({promotionCode:options.promotion});
        this.session = createSession(wx,config.baseUrl);
        await this.session.login();
        if(!current())return;
        if(config.commerce===true){this.setData({commerceEnabled:true,status:'支付尚未开放，可浏览商品和查询订单'});await this.reloadProducts();if(!current())return;}
        this.client = makeClient(body => this.session.transport(scene,body));
        this.setData({sessionReady:!!this.session&&auth.active(this._authEpoch)});
        if(config.payments===true){this.paymentFlow=createPaymentFlow(wx,(op,reference)=>this.session.payment(scene,op,reference));this.setData({paymentsEnabled:true,status:'请创建订单，或输入原订单号查询微信结果'});}
      } else {
    this.client = makeClient(body => new Promise((resolve,reject) => {
      const {baseUrl,token} = getApp().globalData;
      if (!baseUrl || !token) return reject(Error('请先配置本地开发服务'));
      wx.request({url:baseUrl+'/offline/saas', method:'POST', data:body,
        header:{'content-type':'application/json','X-Offline-Token':token}, timeout:5000,
        success:r=>r.statusCode===200?resolve(r.data):reject(Error('请求被拒绝')),
        fail:reject});
    }));
      }
    this.client.storefront().then(s=>current()&&this.setData({merchant:s.merchant.name,
      beforeAd:s.ads.AD_SLOT_PAYMENT_AMOUNT ? s.ads.AD_SLOT_PAYMENT_AMOUNT.title : ''}))
      .catch(e=>{if(current())this.setData({status:e.message});});
    } catch(e) {if(current())this.setData({status:e.message});}
  },
  onUnload() {this.setData({sessionReady:false});this._consumerRequest=null;this._productRequest=null;this._pageUnloaded=true;this._pageGeneration=(this._pageGeneration||0)+1;this._projectRequest=null;this._noticeRequest=null;if(this.client)this.client.reset();if(this.paymentFlow)this.paymentFlow.reset();if(this.session)this.session.clear();},
  customerSessionRevoked(status='登录已退出，请重新登录'){
    this._pageGeneration=(this._pageGeneration||0)+1;this._consumerRequest=null;this._productRequest=null;this._projectRequest=null;this._noticeRequest=null;this._profileRequest=null;
    if(this.client)this.client.reset();if(this.paymentFlow)this.paymentFlow.reset();if(this.session)this.session.clear();
    this.session=null;this.client=null;this.paymentFlow=null;
    if(!this._pageUnloaded)this.setData({sessionReady:false,commerceEnabled:false,paymentsEnabled:false,profileVersion:null,nickname:'',profileContact:'',referralCode:'',projectCustomerId:'',userId:'',
      notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',
      orders:[],orderCursor:null,ordersMore:false,orderDetails:null,orderDetailsPending:false,orderDetailsStatus:'',
      reference:'',amount:'',afterAd:'',afterAdVerified:false,
      refundCurrent:null,refundRecoveryLoaded:false,refundRecoveryPending:false,refundRecoveryStatus:'',refundApplication:'',refundAmount:'',refundReason:'',
      projectTitle:'',projectRole:'',projectChecklist:[],projectMessages:[],projectMessagesCursor:null,projectMessagesMore:false,projectMessagesLoaded:false,projectMessagesStatus:'',
      projectFeedback:'',projectReference:'',projectReferenceItem:'',projectReferenceRevision:0,projectState:'',pending:false,status});
  },
  openCustomerHome(){if(!this.scene){this.setData({status:'缺少门店场景，无法进入客户中心'});return;}getApp().globalData.scene=this.scene;wx.switchTab({url:'/pages/home/index'});},
  quantity(e) {const id=e.currentTarget.dataset.id;const quantity=Number(e.detail.value);if(!Number.isSafeInteger(quantity)||quantity<0||quantity>10000)return;this.setData({products:this.data.products.map(p=>p.item_id===id?{...p,quantity}:p)});},
  inputProfile(e) {const field=e.currentTarget.dataset.field;if(['nickname','profileContact','referralCode'].includes(field))this.setData({[field]:e.detail.value});},
  inputProject(e) {this.setData({projectFeedback:e.detail.value});},
  selectProjectRequirement(e) {
    if(this.data.pending)return;
    const item=e.currentTarget.dataset.item,revision=Number(e.currentTarget.dataset.revision);
    const source=this.data.projectChecklist.find(entry=>entry.id===item);
    if(!source||!Number.isSafeInteger(revision)||revision!==source.revision)return;
    if(!['SECRETREF','OAUTH','SERVER_CHALLENGE'].includes(source.submission_type)){
      this.setData({status:'此材料需要通过原客户中心私有文件上传，不允许用引用编号代替'});return;
    }
    this._projectRequest=null;
    this.setData({projectReferenceItem:item,projectReferenceRevision:revision,
      projectReferenceKind:source.submission_type,projectReference:''});
  },
  inputProjectReference(e){this.setData({projectReference:e.detail.value});},
  inputProjectReferenceKind(e){const items=['SECRETREF','OAUTH','SERVER_CHALLENGE'];const i=Number(e.detail.value);if(Number.isSafeInteger(i)&&items[i])this.setData({projectReferenceKind:items[i]});},
  beginProjectRequest() {
    const request={generation:this._pageGeneration,session:this.session,scene:this.scene,
      sessionGeneration:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined,
      customer:this.data.projectCustomerId,user:this.data.userId,item:this.data.projectReferenceItem,
      revision:this.data.projectReferenceRevision};
    this._projectRequest=request;
    this.setData({pending:true});
    return request;
  },
  projectRequestCurrent(request) {
    return !this._pageUnloaded&&this._projectRequest===request&&
      this._pageGeneration===request.generation&&this.session===request.session&&
      (typeof request.session.getGeneration!=='function'||request.session.getGeneration()===request.sessionGeneration)&&
      this.scene===request.scene&&this.data.projectCustomerId===request.customer&&this.data.userId===request.user&&
      this.data.projectReferenceItem===request.item&&this.data.projectReferenceRevision===request.revision;
  },
  async saveProjectReference() {
    if(this._pageUnloaded||this.data.pending||!this.session||!this.data.projectReferenceItem)return;
    if(typeof this.data.projectReference!=='string'||!this.data.projectReference.trim()||this.data.projectReference.length>256){this.setData({status:'材料引用编号不能为空且不得超过256字符'});return;}
    if(!['SECRETREF','OAUTH','SERVER_CHALLENGE'].includes(this.data.projectReferenceKind))return;
    const request=this.beginProjectRequest();
    try{
      const r=await request.session.commerce(request.scene,'project_save_reference',{
        item:this.data.projectReferenceItem,revision:this.data.projectReferenceRevision,
        kind:this.data.projectReferenceKind,reference:this.data.projectReference});
      if(!this.projectRequestCurrent(request))return;
      request.revision=r.revision;
      this.setData({projectReference:'',projectReferenceRevision:r.revision,status:'可信材料引用已保存，需单独提交审核'});
      const checklist=await request.session.commerce(request.scene,'project_checklist',{});
      if(!this.projectRequestCurrent(request))return;
      this.setData({projectChecklist:checklist.items.map(v=>({
        id:v.id,state:v.state,required:v.required,revision:v.revision,title:v.title,instructions:v.instructions,submission_type:v.submission_type}))});
    }catch(error){if(this.projectRequestCurrent(request))this.setData({status:error.message});}
    finally{if(this.projectRequestCurrent(request)){this._projectRequest=null;this.setData({pending:false});}}
  },

  async uploadProjectDocument(e) {
    if(this._pageUnloaded||this.data.pending||!this.session)return;
    const item=e.currentTarget.dataset.item,revision=Number(e.currentTarget.dataset.revision);
    const source=this.data.projectChecklist.find(entry=>entry.id===item);
    if(!source||source.submission_type!=='PRIVATE_DOCUMENT'||!Number.isSafeInteger(revision)||revision<0||revision!==source.revision)return;
    this.setData({projectReferenceItem:item,projectReferenceRevision:revision,
      projectReferenceKind:'PRIVATE_DOCUMENT',projectReference:''});
    const request=this.beginProjectRequest();
    let uploading=false;
    try {
      const selected=await new Promise((resolve,reject)=>wx.chooseMessageFile({
        count:1,type:'file',extension:['pdf','png','jpg','jpeg'],success:resolve,
        fail:error=>reject(Error(error&&typeof error.errMsg==='string'&&/cancel/i.test(error.errMsg)?'DOCUMENT_PICK_CANCELLED':'DOCUMENT_PICK_FAILED'))
      }));
      if(!this.projectRequestCurrent(request))return;
      const file=selected&&selected.tempFiles&&selected.tempFiles.length===1?selected.tempFiles[0]:null;
      if(!file||typeof file.name!=='string'||!file.name||file.name.length>180||
         !/\.(pdf|png|jpe?g)$/i.test(file.name)||typeof file.path!=='string'||!file.path||
         !Number.isSafeInteger(file.size)||file.size<1||file.size>5000000)throw Error('仅支持不超过5MB的PDF、PNG或JPEG文件');
      const read=await new Promise((resolve,reject)=>wx.getFileSystemManager().readFile({
        filePath:file.path,encoding:'base64',success:resolve,fail:()=>reject(Error('文件读取失败，请重新选择'))
      }));
      if(!this.projectRequestCurrent(request))return;
      uploading=true;
      const result=await request.session.projectDocument(request.scene,{
        item,revision,filename:file.name,content_base64:read.data
      },request.sessionGeneration);
      if(!this.projectRequestCurrent(request))return;
      request.revision=result.revision;
      this.setData({projectReferenceRevision:result.revision,
        projectChecklist:this.data.projectChecklist.map(entry=>entry.id===item?{...entry,revision:result.revision,state:result.state}:entry),
        status:'私有材料版本已保存，需单独提交审核'});
    } catch(error) {
      if(this.projectRequestCurrent(request))this.setData({status:error.message==='DOCUMENT_PICK_CANCELLED'?'已取消选择文件':
        error.message==='INVALID_PROJECT_DOCUMENT'?'文件名称、格式或内容无效，请重新选择PDF、PNG或JPEG文件':
        error.message==='SESSION_EXPIRED'?'登录已过期，请重新登录后重新选择文件':
        uploading?'上传结果未确认；请先刷新资料清单核对当前版本，不要重复上传':error.message});
    } finally {
      if(this.projectRequestCurrent(request)){this._projectRequest=null;this.setData({pending:false});}
    }
  },

  async submitProjectItem(e) {
    if(this._pageUnloaded||this.data.pending||!this.session)return;
    const item=e.currentTarget.dataset.item;
    const revision=Number(e.currentTarget.dataset.revision);
    if(typeof item!=='string'||!Number.isSafeInteger(revision)||revision<0)return;
    const request=this.beginProjectRequest();
    try {
      const result=await request.session.commerce(request.scene,'project_submit',{item,revision});
      if(!this.projectRequestCurrent(request))return;
      this.setData({status:'资料版本已提交审核：'+result.state});
      const checklist=await request.session.commerce(request.scene,'project_checklist',{});
      if(!this.projectRequestCurrent(request))return;
      this.setData({projectChecklist:checklist.items.map(entry=>({
        id:entry.id,state:entry.state,required:entry.required,revision:entry.revision,title:entry.title,instructions:entry.instructions,submission_type:entry.submission_type
      }))});
    } catch(error){if(this.projectRequestCurrent(request))this.setData({status:error.message});}
    finally {if(this.projectRequestCurrent(request)){this._projectRequest=null;this.setData({pending:false});}}
  },

  async projectAction(e) {
    if(this._pageUnloaded||this.data.pending||!this.session)return;
    const op=e.currentTarget.dataset.operation;
    if(!['project_summary','project_checklist','project_feedback','project_messages'].includes(op))return;
    const more=op==='project_messages'&&e.currentTarget.dataset.more==='true';
    if(op==='project_messages'){
      this.prepareProjectMessagesContext();
      if(more&&(!this.data.projectMessagesLoaded||!this.data.projectMessagesMore||!this.data.projectMessagesCursor))return;
    }
    const after=more?this.data.projectMessagesCursor:'';
    const request=this.beginProjectRequest();
    try {
      const params=op==='project_feedback'?{message:this.data.projectFeedback}:
        op==='project_messages'?{after_id:after}:{};
      const r=await request.session.commerce(request.scene,op,params);
      if(!this.projectRequestCurrent(request))return;
      if(op==='project_summary')request.customer=r.customer_id;
      if(op==='project_summary')this.setData({projectTitle:r.title,projectRole:r.role,
        projectCustomerId:r.customer_id,projectState:r.checklist_overall});
      else if(op==='project_checklist')this.setData({projectChecklist:r.items.map(item=>({
        id:item.id,state:item.state,required:item.required,revision:item.revision,title:item.title,instructions:item.instructions,submission_type:item.submission_type}))});
      else if(op==='project_messages'){
        const records=this.projectMessagePage(r,after);
        const merged=new Map((more?this.data.projectMessages:[]).map(record=>[record.id,record]));
        for(const record of records)merged.set(record.id,record);
        this.setData({projectMessages:Array.from(merged.values()),projectMessagesCursor:r.next_cursor,
          projectMessagesMore:r.has_more,projectMessagesLoaded:true,status:'读取原项目归档记录；不代表已获得人工回复',projectMessagesStatus:'读取原项目归档记录；不代表已获得人工回复'});
      }
      else this.setData({projectFeedback:'',status:'项目反馈已归档，尚未确认人工回复：'+r.id});
      if(op==='project_summary'&&this._noticeContext)this.prepareNoticeContext();
      if(op==='project_summary'&&this._projectMessagesContext)this.prepareProjectMessagesContext();
    } catch(error) {if(this.projectRequestCurrent(request))this.setData(op==='project_messages'?{projectMessagesStatus:error.message}:{status:error.message});}
    finally {if(this.projectRequestCurrent(request)){this._projectRequest=null;this.setData({pending:false});}}
  },
  prepareProjectMessagesContext() {
    if(!this.noticeContextCurrent(this._projectMessagesContext)){
      this._projectMessagesContext={generation:this._pageGeneration,session:this.session,scene:this.scene,
        user:this.data.userId,customer:this.data.projectCustomerId,
        sessionGeneration:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined};
      this.setData({projectMessages:[],projectMessagesCursor:null,projectMessagesMore:false,
        projectMessagesLoaded:false,projectMessagesStatus:''});
    }
    return this._projectMessagesContext;
  },
  projectMessagePage(result,after) {
    const invalid=()=>{throw Error('项目反馈列表返回无效，请重试');};
    const key=record=>[record.created,record.id];
    const greater=(a,b)=>a[0]>b[0]||(a[0]===b[0]&&a[1]>b[1]);
    if(!result||result.source!=='ORIGINAL_CENTER_ARCHIVE'||result.provider_reply_verified!==false||
      !Array.isArray(result.records)||result.records.length>50||typeof result.has_more!=='boolean')invalid();
    let previous=null;
    if(after){
      try{previous=JSON.parse(after);}catch(_){invalid();}
      if(!Array.isArray(previous)||previous.length!==2||!Number.isSafeInteger(previous[0])||
        typeof previous[1]!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(previous[1]))invalid();
    }
    const ids=new Set(),records=[];
    for(const record of result.records){
      if(!record||typeof record.id!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(record.id)||ids.has(record.id)||
        !Number.isSafeInteger(record.created)||typeof record.channel!=='string'||typeof record.body!=='string'||
        typeof record.status!=='string'||(previous&&!greater(key(record),previous)))invalid();
      ids.add(record.id);previous=key(record);
      // Keep precisely the original customer projection, never evidence/raw fields.
      records.push({id:record.id,channel:record.channel,body:record.body,status:record.status,created:record.created});
    }
    if(result.has_more){
      if(records.length!==50||typeof result.next_cursor!=='string'||result.next_cursor!==JSON.stringify(previous))invalid();
    }else if(result.next_cursor!==null)invalid();
    return records;
  },
  noticeContextCurrent(context) {
    return !!context&&!this._pageUnloaded&&auth.active(this._authEpoch)&&context.generation===this._pageGeneration&&
      context.session===this.session&&context.scene===this.scene&&
      context.user===this.data.userId&&context.customer===this.data.projectCustomerId&&
      (typeof context.session.getGeneration!=='function'||context.session.getGeneration()===context.sessionGeneration);
  },
  prepareNoticeContext() {
    if(!this.noticeContextCurrent(this._noticeContext)){
      this._noticeRequest=null;
      this._noticeContext={generation:this._pageGeneration,session:this.session,scene:this.scene,
        user:this.data.userId,customer:this.data.projectCustomerId,
        sessionGeneration:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined};
      this.setData({notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:''});
    }
    return this._noticeContext;
  },
  noticeRequestCurrent(request) {
    return this._noticeRequest===request&&this.noticeContextCurrent(request.context);
  },
  noticeRequestFailed(request,error) {
    if(!this.noticeRequestCurrent(request))return;
    const denied=error&&(error.code==='ACCESS_DENIED'||error.message==='SESSION_EXPIRED');
    this.setData({...(denied?{notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false}:{}),
      noticeStatus:denied?'通知访问已被拒绝或会话已过期，请重新确认授权后读取':error.message});
  },
  async loadNotices(e) {
    if(this._pageUnloaded||!this.session||this.data.pending)return;
    const context=this.prepareNoticeContext();
    if(this.data.noticePending)return;
    const more=e&&e.currentTarget&&e.currentTarget.dataset.more==='true';
    if(more&&(!this.data.noticesLoaded||!this.data.noticesMore||!this.data.noticeCursor))return;
    const after=more?this.data.noticeCursor:'';
    const request={context};this._noticeRequest=request;this.setData({noticePending:true,noticeStatus:''});
    try {
      const r=await context.session.commerce(context.scene,'notices',{after_id:after});
      if(!this.noticeRequestCurrent(request))return;
      if(!r||!Array.isArray(r.records)||r.records.length>50||typeof r.has_more!=='boolean'||
         r.records.some(record=>!record||typeof record.id!=='string'||!/^[0-9a-f]{64}$/.test(record.id)||
           typeof record.message!=='string'||typeof record.read!=='boolean')||
         (r.has_more?(!r.records.length||typeof r.next_cursor!=='string'||!/^[0-9a-f]{64}$/.test(r.next_cursor)||r.next_cursor<=after):r.next_cursor!==null))
        throw Error('通知列表返回无效，请重试');
      const records=new Map((more?this.data.notices:[]).map(record=>[record.id,record]));
      for(const record of r.records){const prior=records.get(record.id);records.set(record.id,{...record,read:record.read||!!(prior&&prior.read)});}
      this.setData({notices:Array.from(records.values()),noticeCursor:r.next_cursor,
        noticesMore:r.has_more,noticesLoaded:true});
    } catch(error) {this.noticeRequestFailed(request,error);}
    finally {if(this.noticeRequestCurrent(request)){this._noticeRequest=null;this.setData({noticePending:false});}}
  },
  async markNoticeRead(e) {
    if(this._pageUnloaded||!this.session||this.data.pending)return;
    const context=this.prepareNoticeContext();
    if(this.data.noticePending)return;
    const id=e.currentTarget.dataset.id;
    const record=this.data.notices.find(notice=>notice.id===id);
    if(typeof id!=='string'||!/^[0-9a-f]{64}$/.test(id)||!record||record.read)return;
    const request={context};this._noticeRequest=request;this.setData({noticePending:true,noticeStatus:''});
    try {
      const r=await context.session.commerce(context.scene,'notice_read',{notice_id:id});
      if(!this.noticeRequestCurrent(request))return;
      if(!r||r.id!==id||r.read!==true)throw Error('通知已读状态未确认，请重试或刷新通知');
      this.setData({notices:this.data.notices.map(notice=>notice.id===id?{...notice,read:true}:notice)});
    } catch(error) {this.noticeRequestFailed(request,error);}
    finally {if(this.noticeRequestCurrent(request)){this._noticeRequest=null;this.setData({noticePending:false});}}
  },
  async profileAction(e) {
    if(e.currentTarget.dataset.operation==='notices')return this.loadNotices(e);
    if(this._pageUnloaded||this.data.pending||!this.session)return;
    const context={...this.prepareNoticeContext()};this._profileRequest=context;
    const current=()=>this._profileRequest===context&&this.noticeContextCurrent(context);
    this.setData({pending:true});
    try{const op=e.currentTarget.dataset.operation;let params={};
      if(op==='profile_update'){if(this.data.profileVersion===null)throw Error('先读取个人资料');params={nickname:this.data.nickname,contact:this.data.profileContact,expected_version:this.data.profileVersion};}
      else if(op==='referral_bind')params={code:this.data.referralCode};
      if(!['profile_read','profile_update','referral_code','referral_bind'].includes(op))throw Error('无效操作');
      const r=await context.session.commerce(context.scene,op,params);
      if(!current())return;
      if(op==='profile_read'||op==='profile_update'){
        context.user=r.user_id;context.customer=r.project_customer_id;
        this.setData({profileVersion:r.version,nickname:r.nickname,profileContact:r.contact,userId:r.user_id,projectCustomerId:r.project_customer_id});
        this.prepareNoticeContext();
        if(this._projectMessagesContext)this.prepareProjectMessagesContext();
      }
      else if(op==='referral_code')this.setData({referralCode:r.code});
      this.setData({status:op==='referral_bind'?'推荐关系已绑定':'个人中心已更新'});
    }catch(error){if(current())this.setData({status:error.message});}
    finally{if(this._profileRequest===context&&!this._pageUnloaded&&this._pageGeneration===context.generation){this._profileRequest=null;this.setData({pending:false});}}
  },
  cancelConsumerRead(kind) {
    const request=this._consumerRequest;
    if(!request||request.mutating||request.kind!==kind)return false;
    this._consumerRequest=null;this.setData({pending:false});return true;
  },
  prepareConsumerRead() {
    const request=this._consumerRequest;
    if(request&&!request.mutating&&!this.consumerRequestCurrent(request))this.cancelConsumerRead(request.kind);
  },
  beginConsumerRequest(kind,mutating=false) {
    const request={...this.orderReadContext(),kind,mutating,
      refundGeneration:this._refundInputGeneration,communityGeneration:this._communityInputGeneration,
      application:this.data.refundApplication,amount:this.data.refundAmount,reason:this.data.refundReason,
      community:this.data.communityId,promotion:this.data.promotionCode};
    this._consumerRequest=request;this.setData({pending:true});return request;
  },
  consumerRequestCurrent(request) {
    return this._consumerRequest===request&&this.noticeContextCurrent(request)&&
      (request.kind!=='refund'||this.orderReadCurrent(request)&&request.refundGeneration===this._refundInputGeneration&&
        request.application===this.data.refundApplication&&request.amount===this.data.refundAmount&&request.reason===this.data.refundReason)&&
      (request.kind!=='community'||request.communityGeneration===this._communityInputGeneration&&
        request.community===this.data.communityId&&request.promotion===this.data.promotionCode);
  },
  finishConsumerRequest(request) {
    if(this.consumerRequestCurrent(request)){this._consumerRequest=null;this.setData({pending:false});}
  },
  inputCommunity(e) {
    if(this.data.pending&&!this.cancelConsumerRead('community'))return;
    const field=e.currentTarget.dataset.field;
    if(['communityId','promotionCode'].includes(field)){
      this._communityInputGeneration=(this._communityInputGeneration||0)+1;
      this.setData({[field]:e.detail.value});
    }
  },
  async communityAction(e) {
    if(this._pageUnloaded||!this.session)return;this.prepareConsumerRead();if(this.data.pending)return;
    const op=e.currentTarget.dataset.operation,more=e.currentTarget.dataset.more==='true';
    if(!['communities','community_mine','community_join','community_leave','promotion_redeem'].includes(op))return;
    if(op==='communities'&&more&&(!this.data.communitiesMore||!this.data.communityCursor))return;
    const request=this.beginConsumerRequest('community',!['communities','community_mine'].includes(op));
    try{let params={};
      if(op==='communities')params={after_id:more?this.data.communityCursor:''};
      else if(op==='community_join'||op==='community_leave')params={community_id:e.currentTarget.dataset.id||request.community};
      else if(op==='promotion_redeem')params={code:request.promotion};
      const r=await request.session.commerce(request.scene,op,params);
      if(!this.consumerRequestCurrent(request))return;
      if(op==='communities'){
        if(!r||!Array.isArray(r.records)||typeof r.has_more!=='boolean'||
          (r.has_more?(typeof r.next_cursor!=='string'||!r.next_cursor||r.next_cursor===params.after_id):r.next_cursor!==null))throw Error('社区列表返回未确认');
        this.setData({communities:r.records,communityCursor:r.next_cursor,communitiesMore:r.has_more});
      }else{
        if(!r||typeof r.active!=='boolean'||r.active&&typeof r.community_id!=='string'||
          ['community_join','community_leave'].includes(op)&&r.community_id!==params.community_id)throw Error('社区关系返回未确认');
        request.community=r.active?r.community_id:'';
        this.setData({communityId:request.community,status:r.active?'社区关系已确认':'当前未加入社区'});
      }
    }catch(error){if(this.consumerRequestCurrent(request))this.setData({status:error.message});}
    finally{this.finishConsumerRequest(request);}
  },
  async reloadProducts(e) {
    if(this._pageUnloaded||this.data.pending||!this.session)return;
    if(this._productRequest&&this.noticeContextCurrent(this._productRequest.context))return;
    const more=e?.currentTarget?.dataset?.more==='true';
    if(more&&(!this.data.productsMore||!this.data.productCursor))return;
    const context={generation:this._pageGeneration,session:this.session,scene:this.scene,user:this.data.userId,
      customer:this.data.projectCustomerId,sessionGeneration:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined};
    const request={context,after:more?this.data.productCursor:''};this._productRequest=request;
    if(!more)this.setData({products:[],productCursor:null,productsMore:false});
    this.setData({productsPending:true,productsStatus:''});
    const current=()=>this._productRequest===request&&this.noticeContextCurrent(context);
    try {
      const r=await context.session.commerce(context.scene,'products',request.after?{after_id:request.after}:{});
      if(!current())return;
      if(!r||!Array.isArray(r.products)||r.products.some(p=>!p||typeof p.item_id!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(p.item_id)||typeof p.name!=='string'||!Number.isSafeInteger(p.unit_minor)||p.unit_minor<1||!Number.isSafeInteger(p.revision)||p.revision<1||typeof p.available!=='boolean')||
        (r.has_more!==undefined&&typeof r.has_more!=='boolean')||(r.has_more&&(typeof r.next_cursor!=='string'||!r.next_cursor||r.next_cursor===request.after)))throw Error('商品分页结果无效，请刷新重试');
      const products=more?[...this.data.products]:[],known=new Set(products.map(p=>p.item_id));
      for(const product of r.products)if(!known.has(product.item_id)){known.add(product.item_id);products.push({...product,quantity:0});}
      this.setData({products,productCursor:r.has_more?r.next_cursor:null,productsMore:r.has_more===true,
        productsStatus:r.has_more?(r.products.length?'本页商品已加载，可继续加载更多':'本页没有可售商品，后续仍有商品待查'):products.length?'当前商品已全部加载':'当前没有可售商品'});
    } catch(error){if(current())this.setData({productsStatus:error.message+'；已有订单可继续查询和申请售后'});}
    finally {if(this._productRequest===request){this._productRequest=null;if(!this._pageUnloaded&&this._pageGeneration===context.generation)this.setData({productsPending:false});}}
  },
  async loadOrders(e) {
    if(this._pageUnloaded||!this.session)return;this.prepareConsumerRead();if(this.data.pending)return;
    const more=e?.currentTarget?.dataset?.more==='true';
    if(more&&(!this.data.ordersMore||!this.data.orderCursor))return;
    const request=this.beginConsumerRequest('orders');
    try{
      const r=await request.session.commerce(request.scene,'orders',{after_id:more?this.data.orderCursor:''});
      if(!this.consumerRequestCurrent(request))return;
      if(!r||!Array.isArray(r.records)||typeof r.has_more!=='boolean'||
        (r.has_more?(typeof r.next_cursor!=='string'||!r.next_cursor):r.next_cursor!==null))throw Error('订单列表返回未确认');
      this.setData({orders:r.records,orderCursor:r.next_cursor,ordersMore:r.has_more});
    }catch(error){if(this.consumerRequestCurrent(request))this.setData({status:error.message});}
    finally{this.finishConsumerRequest(request);}
  },
  resetOrderDetails() {
    this._orderSelectionGeneration=(this._orderSelectionGeneration||0)+1;
    this._orderDetailsRequest=null;this._refundRecoveryRequest=null;
    if(this._purchaseRecoveryRequest)this.setData({pending:false});
    this._purchaseRecoveryRequest=null;
    this.setData({orderDetails:null,detailsCollapsed:false,orderDetailsPending:false,orderDetailsStatus:'',
      refundCurrent:null,refundRecoveryLoaded:false,refundRecoveryPending:false,refundRecoveryStatus:'',
      refundApplication:'',refundAmount:'',refundReason:''});
  },
  orderReadContext() {
    return {generation:this._pageGeneration,session:this.session,scene:this.scene,
      user:this.data.userId,customer:this.data.projectCustomerId,
      sessionGeneration:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined,
      reference:this.data.reference,selection:this._orderSelectionGeneration};
  },
  orderReadCurrent(context) {
    return this.noticeContextCurrent(context)&&context.reference===this.data.reference&&context.selection===this._orderSelectionGeneration;
  },
  async recoverPurchase() {
    if(this._pageUnloaded||!this.session||this.data.pending||!this.data.commerceEnabled||
      typeof this.data.reference!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(this.data.reference))return;
    const request=this.orderReadContext();this._purchaseRecoveryRequest=request;
    this.setData({pending:true,afterAd:'',afterAdVerified:false,status:'正在恢复原商品订单；保留原订单编号'});
    const current=()=>this._purchaseRecoveryRequest===request&&this.orderReadCurrent(request);
    try {
      const r=await request.session.commerce(request.scene,'purchase_recover',{reference:request.reference});
      if(!current())return;
      if(!r||r.reference!==request.reference||(request.user&&r.user_id!==request.user)||
        !Number.isSafeInteger(r.amount_minor)||r.amount_minor<1||r.currency!=='CNY'||
        !r.order||!['PENDING','SUCCESS','FAILED','CANCELLED','REFUNDED'].includes(r.order.state)||
        r.order.amount_minor!==r.amount_minor||r.order.currency!==r.currency||
        !Array.isArray(r.lines)||r.lines.length<1||r.lines.length>50||
        r.lines.some(line=>!line||typeof line.item_id!=='string'||typeof line.name!=='string'||
          !Number.isSafeInteger(line.revision)||line.revision<1||!Number.isSafeInteger(line.quantity)||line.quantity<1||
          !Number.isSafeInteger(line.unit_minor)||line.unit_minor<1||!Number.isSafeInteger(line.subtotal_minor)||
          line.subtotal_minor!==line.quantity*line.unit_minor)||
        new Set(r.lines.map(line=>line.item_id)).size!==r.lines.length||
        r.lines.reduce((total,line)=>total+line.subtotal_minor,0)!==r.amount_minor)
        throw Error('原订单恢复结果未确认');
      this.setData({amount:String(r.amount_minor),status:'原商品订单：'+r.order.state+'；未发起支付，金额来自原商品快照',
        orders:this.data.orders.map(order=>order.reference===request.reference?{...order,order:r.order,lines:r.lines}:order)});
    } catch(error) {if(current())this.setData({status:error.message+'；保留原订单编号，可再次显式恢复，勿重新下单'});}
    finally {if(current()){this._purchaseRecoveryRequest=null;this.setData({pending:false});}}
  },
  async loadOrderDetails() {
    if(this._pageUnloaded||!this.session||this.data.pending||!this.data.commerceEnabled||
      typeof this.data.reference!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(this.data.reference))return;
    if(this._orderDetailsRequest&&this.orderReadCurrent(this._orderDetailsRequest))return;
    const request=this.orderReadContext();this._orderDetailsRequest=request;
    this.setData({orderDetails:null,detailsCollapsed:false,orderDetailsPending:true,orderDetailsStatus:''});
    try {
      const r=await request.session.commerce(request.scene,'purchase_read',{reference:request.reference});
      if(this._orderDetailsRequest!==request||!this.orderReadCurrent(request))return;
      if(!r||r.reference!==request.reference||(request.user&&r.user_id!==request.user)||
        !Array.isArray(r.lines)||r.lines.length<1||r.lines.length>50||
        !Number.isSafeInteger(r.amount_minor)||r.amount_minor<1||r.currency!=='CNY'||
        !r.order||typeof r.order.state!=='string'||r.order.amount_minor!==r.amount_minor||r.order.currency!==r.currency||
        r.lines.some(line=>!line||typeof line.item_id!=='string'||typeof line.name!=='string'||
          !Number.isSafeInteger(line.revision)||line.revision<1||!Number.isSafeInteger(line.quantity)||line.quantity<1||
          !Number.isSafeInteger(line.unit_minor)||line.unit_minor<1||!Number.isSafeInteger(line.subtotal_minor)||
          line.subtotal_minor!==line.quantity*line.unit_minor)||
        new Set(r.lines.map(line=>line.item_id)).size!==r.lines.length||
        r.lines.reduce((total,line)=>total+line.subtotal_minor,0)!==r.amount_minor)
        throw Error('原订单商品快照未确认，请重新读取当前订单');
      this.setData({orderDetails:{reference:r.reference,amount_minor:r.amount_minor,currency:r.currency,
        lines:r.lines.map(line=>({item_id:line.item_id,name:line.name,revision:line.revision,
          quantity:line.quantity,unit_minor:line.unit_minor,subtotal_minor:line.subtotal_minor})),
        order_state:r.order.state,fulfillment_state:typeof r.fulfillment_state==='string'?r.fulfillment_state:'',
        fulfillment_revision:Number.isSafeInteger(r.fulfillment_revision)?r.fulfillment_revision:null,
        completion_note:typeof r.completion_note==='string'?r.completion_note:'',
        completed_at:Number.isSafeInteger(r.completed_at)?r.completed_at:null}});
    } catch(error) {if(this._orderDetailsRequest===request&&this.orderReadCurrent(request))this.setData({orderDetailsStatus:error.message});}
    finally {if(this._orderDetailsRequest===request&&!this._pageUnloaded&&this._pageGeneration===request.generation){this._orderDetailsRequest=null;this.setData({orderDetailsPending:false});}}
  },
  async recoverRefundApplication() {
    if(this._pageUnloaded||!this.session||this.data.pending||!this.data.commerceEnabled||
      typeof this.data.reference!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(this.data.reference))return;
    if(this._refundRecoveryRequest&&this.orderReadCurrent(this._refundRecoveryRequest))return;
    const request=this.orderReadContext();request.inputGeneration=this._refundInputGeneration;
    request.form={application:this.data.refundApplication,amount:this.data.refundAmount,reason:this.data.refundReason,status:this.data.status};
    this._refundRecoveryRequest=request;
    this.setData({refundCurrent:null,refundRecoveryLoaded:false,refundRecoveryPending:true,refundRecoveryStatus:''});
    const current=()=>this._refundRecoveryRequest===request&&this.orderReadCurrent(request)&&request.inputGeneration===this._refundInputGeneration&&
      !this.data.pending&&this.data.status===request.form.status&&this.data.refundApplication===request.form.application&&
      this.data.refundAmount===request.form.amount&&this.data.refundReason===request.form.reason;
    try {
      const r=await request.session.commerce(request.scene,'refund_current',{reference:request.reference});
      if(!current())return;
      if(!r||r.reference!==request.reference||!Object.prototype.hasOwnProperty.call(r,'application'))throw Error('原售后申请尚未确认，请重试');
      const a=r.application;
      if(a===null){this.setData({refundCurrent:null,refundRecoveryLoaded:true,refundApplication:'',refundAmount:'',refundReason:''});return;}
      if(!a||a.reference!==request.reference||(request.user&&a.user_id!==request.user)||
        typeof a.application_id!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(a.application_id)||
        !Number.isSafeInteger(a.revision)||a.revision<1||!Number.isSafeInteger(a.amount_minor)||a.amount_minor<1||
        typeof a.reason!=='string'||typeof a.status!=='string'||!a.status||typeof a.opinion!=='string')
        throw Error('原售后申请绑定或版本未确认，请重试');
      this.setData({refundCurrent:{reference:a.reference,application_id:a.application_id,revision:a.revision,
        amount_minor:a.amount_minor,reason:a.reason,status:a.status,opinion:a.opinion},
        refundRecoveryLoaded:true,refundApplication:a.application_id,refundAmount:String(a.amount_minor),refundReason:a.reason});
    } catch(error) {if(current())this.setData({refundRecoveryStatus:error.message});}
    finally {if(this._refundRecoveryRequest===request&&!this._pageUnloaded&&this._pageGeneration===request.generation){this._refundRecoveryRequest=null;this.setData({refundRecoveryPending:false});}}
  },
  selectOrder(e) {if(this.data.pending)return;this.resetOrderDetails();if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({reference:e.currentTarget.dataset.reference,refundApplication:'',afterAd:'',afterAdVerified:false});},
  inputRefund(e) {
    if(this.data.pending&&!this.cancelConsumerRead('refund'))return;
    const field=e.currentTarget.dataset.field;
    if(['refundAmount','refundReason','refundApplication'].includes(field)){
      this._refundInputGeneration=(this._refundInputGeneration||0)+1;this.setData({[field]:e.detail.value});
    }
  },
  async refundAction(submit) {
    if(this._pageUnloaded||!this.session||submit&&!this.data.commerceEnabled)return;
    this.prepareConsumerRead();if(this.data.pending)return;
    if(submit&&!this.data.refundApplication)this.setData({refundApplication:'ra_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,14)});
    const request=this.beginConsumerRequest('refund',submit);
    try{
      const params={reference:request.reference,application_id:request.application};
      if(submit)Object.assign(params,{amount_minor:Number(request.amount),reason:request.reason});
      const r=await request.session.commerce(request.scene,submit?'refund_apply':'refund_application',params);
      if(!this.consumerRequestCurrent(request))return;
      if(!r||r.reference!==request.reference||r.application_id!==request.application||
        request.user&&r.user_id!==request.user||typeof r.status!=='string'||!r.status||typeof r.opinion!=='string'||
        !Number.isSafeInteger(r.revision)||r.revision<1)throw Error('原退款申请绑定或版本未确认');
      this.setData({status:'退款申请：'+r.status+(submit?'；编号 '+r.application_id:' '+r.opinion)});
    }catch(error){if(this.consumerRequestCurrent(request))this.setData({status:error.message+(submit?'；保留原申请编号查询':'')});}
    finally{this.finishConsumerRequest(request);}
  },
  async requestRefund() {return this.refundAction(true);},
  async refundStatus() {return this.refundAction(false);},
  inputAmount(e) {if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({amount:e.detail.value,afterAd:'',afterAdVerified:false});},
  inputReference(e) {if(this.data.pending&&!this._purchaseRecoveryRequest&&!this.cancelConsumerRead('refund'))return;this.resetOrderDetails();if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({reference:e.detail.value,afterAd:'',afterAdVerified:false});},
  async checkout() {
    if (this.data.pending||this.data.productsPending) return;
    if (!this.client) return this.setData({status:'请先完成登录与门店绑定'});
    this.setData({pending:true,afterAd:'',afterAdVerified:false,status:this.data.commerceEnabled?'正在创建订单':'正在创建模拟订单'});
    try {if(this.data.commerceEnabled){const lines=this.data.products.filter(p=>p.quantity>0).map(p=>({item_id:p.item_id,revision:p.revision,quantity:p.quantity}));const r=await this.session.commerce(this.scene,'purchase',{reference:this.data.reference,lines});this.setData({amount:String(r.amount_minor)});}else await this.client.checkout(this.data.amount,this.data.reference);this.setData({status:this.data.paymentsEnabled?'订单已建立，请点击微信支付':(this.data.commerceEnabled?'订单已建立，支付尚未开放；未发生扣款':'模拟待支付；不发起微信扣款')});}
    catch(e) {this.setData({status:e.message});}
    finally {this.setData({pending:false});}
  },
  async cancelOrder() {
    if(this.data.pending||!this.session)return;this.setData({pending:true,afterAd:'',afterAdVerified:false});
    try{const r=await this.session.payment(this.scene,'cancel',this.data.reference);if(this.paymentFlow)this.paymentFlow.reset();this.setData({status:r.order_state==='CANCELLED'?'订单已取消，库存已恢复或可按原订单恢复处理':r.order_state+'；以服务端确认状态为准'});}
    catch(e){this.setData({status:e.message+'；请查询原订单，不要重新提交资金操作'});}finally{this.setData({pending:false});}
  },
  async pay() {return this.runPayment(false);},
  async recoverPayment() {return this.runPayment(true);},
  async runPayment(recover) {
    if(this.data.pending||!this.paymentFlow)return;
    this.setData({pending:true,afterAd:'',afterAdVerified:false,status:recover?'正在恢复原支付单':'正在准备微信支付'});
    try {const r=await this.paymentFlow.pay(this.data.reference,recover);await this.showPayment(r);}
    catch(e){this.setData({status:e.message+'；请查询原订单，勿重新创建支付单'});}
    finally{this.setData({pending:false});}
  },
  async showPayment(r) {
    const reference=this.data.reference;
    this.setData({amount:String(r.amount_minor),status:r.provider_state==='SUCCESS'?'微信查单已支付；财务尚未核销':r.provider_state+'；财务尚未核销',afterAd:'',afterAdVerified:false});
    if(r.provider_state!=='SUCCESS'||!this.data.commerceEnabled||!this.session)return;
    try {
      const reply=await this.session.commerce(this.scene,'receipt_ad',{reference});
      if(this.data.reference!==reference)return;
      if(reply.payment_success_verified===true&&reply.creative&&typeof reply.creative.title==='string')
        this.setData({afterAd:reply.creative.title,afterAdVerified:true});
    } catch(_) { /* Advertisement failure never changes payment status. */ }
  },
  async queryPayment() {
    if(this.data.pending||!this.paymentFlow)return;
    this.setData({pending:true,afterAd:'',afterAdVerified:false});
    try{await this.showPayment(await this.paymentFlow.query(this.data.reference));}
    catch(e){this.setData({status:e.message+'；支付结果未知'});}
    finally{this.setData({pending:false});}
  },
  async refresh() {
    if (!this.client) return this.setData({status:'请先完成登录与门店绑定'});
    this.setData({afterAd:'',afterAdVerified:false});
    try {if(this.data.commerceEnabled){const r=await this.session.commerce(this.scene,'purchase_read',{reference:this.data.reference});this.setData({amount:String(r.amount_minor),status:r.order.state+'；金额来自服务端商品快照'});return;}const r=await this.client.resume(this.data.reference);this.setData({amount:String(r.order.amount_minor),status:r.payment_state+'（模拟，非收款凭证）',
      afterAd:r.ads.AD_SLOT_PAYMENT_SUCCESS ? r.ads.AD_SLOT_PAYMENT_SUCCESS.title : ''});}
    catch(e) {this.setData({status:e.message});}
  }
});
