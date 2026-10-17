const {makeClient} = require('../../client');
const {createPaymentFlow}=require('../../payment');
const {parseScene,createSession} = require('../../session');
Page({
  data: {communities:[],communityCursor:null,communitiesMore:false,communityId:'',promotionCode:'',amount:'', reference:'', merchant:'', beforeAd:'', afterAd:'',afterAdVerified:false, status:'本地模拟；未连接微信支付', pending:false,paymentsEnabled:false,commerceEnabled:false,profileVersion:null,nickname:'',profileContact:'',referralCode:'',projectCustomerId:'',userId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',products:[],orders:[],orderCursor:null,ordersMore:false,orderDetails:null,orderDetailsPending:false,orderDetailsStatus:'',refundCurrent:null,refundRecoveryLoaded:false,refundRecoveryPending:false,refundRecoveryStatus:'',refundApplication:"",refundAmount:"",refundReason:"",projectTitle:"",projectRole:"",projectChecklist:[],projectMessages:[],projectFeedback:"",projectReference:"",projectReferenceKind:"SECRETREF",projectReferenceItem:"",projectReferenceRevision:0,projectState:""},
  async onLoad(options) {
    this._pageUnloaded=false;
    this.resetOrderDetails();
    this._noticeContext=null;this._noticeRequest=null;
    this.setData({notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:''});
    const lifecycle=this._pageGeneration=(this._pageGeneration||0)+1;
    const current=()=>!this._pageUnloaded&&this._pageGeneration===lifecycle;
    try {
      const config = getApp().globalData;
      if (config.mode !== 'OFFLINE') {
        const scene = parseScene(options);
        this.scene=scene;
        if(typeof options.promotion==='string'&&/^cp_[0-9a-f]{32}$/.test(options.promotion))this.setData({promotionCode:options.promotion});
        this.session = createSession(wx,config.baseUrl);
        await this.session.login();
        if(!current())return;
        if(config.commerce===true){this.setData({commerceEnabled:true});try{const listing=await this.session.commerce(scene,'products',{});if(!current())return;this.setData({products:listing.products.map(p=>({...p,quantity:0}))});}catch(error){if(!current())return;this.setData({products:[],status:error.message+'；已有订单可继续查询和申请售后'});}}
        this.client = makeClient(body => this.session.transport(scene,body));
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
  onUnload() {this._pageUnloaded=true;this._pageGeneration=(this._pageGeneration||0)+1;this._projectRequest=null;this._noticeRequest=null;if(this.client)this.client.reset();if(this.paymentFlow)this.paymentFlow.reset();if(this.session)this.session.clear();},
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
      customer:this.data.projectCustomerId,item:this.data.projectReferenceItem,
      revision:this.data.projectReferenceRevision};
    this._projectRequest=request;
    this.setData({pending:true});
    return request;
  },
  projectRequestCurrent(request) {
    return !this._pageUnloaded&&this._projectRequest===request&&
      this._pageGeneration===request.generation&&this.session===request.session&&
      (typeof request.session.getGeneration!=='function'||request.session.getGeneration()===request.sessionGeneration)&&
      this.scene===request.scene&&this.data.projectCustomerId===request.customer&&
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
    const request=this.beginProjectRequest();
    try {
      const params=op==='project_feedback'?{message:this.data.projectFeedback}:{};
      const r=await request.session.commerce(request.scene,op,params);
      if(!this.projectRequestCurrent(request))return;
      if(op==='project_summary')request.customer=r.customer_id;
      if(op==='project_summary')this.setData({projectTitle:r.title,projectRole:r.role,
        projectCustomerId:r.customer_id,projectState:r.checklist_overall});
      else if(op==='project_checklist')this.setData({projectChecklist:r.items.map(item=>({
        id:item.id,state:item.state,required:item.required,revision:item.revision,title:item.title,instructions:item.instructions,submission_type:item.submission_type}))});
      else if(op==='project_messages')this.setData({projectMessages:r.records,status:'读取原项目归档记录；不代表已获得人工回复'});
      else this.setData({projectFeedback:'',status:'项目反馈已归档，尚未确认人工回复：'+r.id});
      if(op==='project_summary'&&this._noticeContext)this.prepareNoticeContext();
    } catch(error) {if(this.projectRequestCurrent(request))this.setData({status:error.message});}
    finally {if(this.projectRequestCurrent(request)){this._projectRequest=null;this.setData({pending:false});}}
  },
  noticeContextCurrent(context) {
    return !!context&&!this._pageUnloaded&&context.generation===this._pageGeneration&&
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
    } catch(error) {if(this.noticeRequestCurrent(request))this.setData({noticeStatus:error.message});}
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
    } catch(error) {if(this.noticeRequestCurrent(request))this.setData({noticeStatus:error.message});}
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
      }
      else if(op==='referral_code')this.setData({referralCode:r.code});
      this.setData({status:op==='referral_bind'?'推荐关系已绑定':'个人中心已更新'});
    }catch(error){if(current())this.setData({status:error.message});}
    finally{if(this._profileRequest===context&&!this._pageUnloaded&&this._pageGeneration===context.generation){this._profileRequest=null;this.setData({pending:false});}}
  },
  inputCommunity(e) {const field=e.currentTarget.dataset.field;if(['communityId','promotionCode'].includes(field))this.setData({[field]:e.detail.value});},
  async communityAction(e) {
    if(this.data.pending||!this.session)return;this.setData({pending:true});
    try{const op=e.currentTarget.dataset.operation;let params={};
      if(op==='communities')params={after_id:e.currentTarget.dataset.more==='true'?this.data.communityCursor||'':''};
      else if(op==='community_join'||op==='community_leave')params={community_id:e.currentTarget.dataset.id||this.data.communityId};
      else if(op==='promotion_redeem')params={code:this.data.promotionCode};
      if(!['communities','community_mine','community_join','community_leave','promotion_redeem'].includes(op))throw Error('无效社区操作');
      const r=await this.session.commerce(this.scene,op,params);
      if(op==='communities')this.setData({communities:r.records,communityCursor:r.next_cursor,communitiesMore:r.has_more});
      else this.setData({communityId:r.active?r.community_id:'',status:r.active?'社区关系已确认':'当前未加入社区'});
    }catch(error){this.setData({status:error.message});}finally{this.setData({pending:false});}
  },
  async reloadProducts() {
    if(this.data.pending||!this.session)return;this.setData({pending:true});
    try{const r=await this.session.commerce(this.scene,'products',{});this.setData({products:r.products.map(p=>({...p,quantity:0})),status:'商品价格库存已更新'});}catch(e){this.setData({status:e.message});}finally{this.setData({pending:false});}
  },
  async loadOrders(e) {
    if(this.data.pending||!this.session)return;this.setData({pending:true});
    const more=e?.currentTarget?.dataset?.more==='true';
    try{const r=await this.session.commerce(this.scene,'orders',{after_id:more?this.data.orderCursor||'':''});this.setData({orders:r.records,orderCursor:r.next_cursor,ordersMore:r.has_more});}catch(error){this.setData({status:error.message});}finally{this.setData({pending:false});}
  },
  resetOrderDetails() {
    this._orderSelectionGeneration=(this._orderSelectionGeneration||0)+1;
    this._orderDetailsRequest=null;this._refundRecoveryRequest=null;
    this.setData({orderDetails:null,orderDetailsPending:false,orderDetailsStatus:'',
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
  async loadOrderDetails() {
    if(this._pageUnloaded||!this.session||this.data.pending||!this.data.commerceEnabled||
      typeof this.data.reference!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(this.data.reference))return;
    if(this._orderDetailsRequest&&this.orderReadCurrent(this._orderDetailsRequest))return;
    const request=this.orderReadContext();this._orderDetailsRequest=request;
    this.setData({orderDetails:null,orderDetailsPending:true,orderDetailsStatus:''});
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
  inputRefund(e) {const field=e.currentTarget.dataset.field;if(['refundAmount','refundReason','refundApplication'].includes(field)){this._refundInputGeneration=(this._refundInputGeneration||0)+1;this.setData({[field]:e.detail.value});}},
  async requestRefund() {
    if(this.data.pending||!this.session||!this.data.commerceEnabled)return;
    if(!this.data.refundApplication)this.setData({refundApplication:'ra_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,14)});
    this.setData({pending:true});
    try{const r=await this.session.commerce(this.scene,'refund_apply',{reference:this.data.reference,application_id:this.data.refundApplication,amount_minor:Number(this.data.refundAmount),reason:this.data.refundReason});this.setData({status:'退款申请：'+r.status+'；编号 '+r.application_id});}
    catch(e){this.setData({status:e.message+'；保留原申请编号查询'});}finally{this.setData({pending:false});}
  },
  async refundStatus() {
    if(this.data.pending||!this.session)return;this.setData({pending:true});
    try{const r=await this.session.commerce(this.scene,'refund_application',{reference:this.data.reference,application_id:this.data.refundApplication});this.setData({status:'退款申请：'+r.status+' '+r.opinion});}catch(e){this.setData({status:e.message});}finally{this.setData({pending:false});}
  },
  inputAmount(e) {if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({amount:e.detail.value,afterAd:'',afterAdVerified:false});},
  inputReference(e) {this.resetOrderDetails();if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({reference:e.detail.value,afterAd:'',afterAdVerified:false});},
  async checkout() {
    if (this.data.pending) return;
    if (!this.client) return this.setData({status:'请先完成登录与门店绑定'});
    this.setData({pending:true,afterAd:'',afterAdVerified:false,status:this.data.paymentsEnabled?'正在创建订单':'正在创建模拟订单'});
    try {if(this.data.commerceEnabled){const lines=this.data.products.filter(p=>p.quantity>0).map(p=>({item_id:p.item_id,revision:p.revision,quantity:p.quantity}));const r=await this.session.commerce(this.scene,'purchase',{reference:this.data.reference,lines});this.setData({amount:String(r.amount_minor)});}else await this.client.checkout(this.data.amount,this.data.reference);this.setData({status:this.data.paymentsEnabled?'订单已建立，请点击微信支付':'模拟待支付；不发起微信扣款'});}
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
