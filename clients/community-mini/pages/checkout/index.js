const {makeClient} = require('../../client');
const {createPaymentFlow}=require('../../payment');
const {parseScene,createSession} = require('../../session');
Page({
  data: {communities:[],communityCursor:null,communitiesMore:false,communityId:'',promotionCode:'',amount:'', reference:'', merchant:'', beforeAd:'', afterAd:'',afterAdVerified:false, status:'本地模拟；未连接微信支付', pending:false,paymentsEnabled:false,commerceEnabled:false,profileVersion:null,nickname:'',profileContact:'',referralCode:'',projectCustomerId:'',userId:'',notices:[],products:[],orders:[],orderCursor:null,ordersMore:false,refundApplication:"",refundAmount:"",refundReason:"",projectTitle:"",projectRole:"",projectChecklist:[],projectMessages:[],projectFeedback:"",projectReference:"",projectReferenceKind:"SECRETREF",projectReferenceItem:"",projectReferenceRevision:0,projectState:""},
  async onLoad(options) {
    try {
      const config = getApp().globalData;
      if (config.mode !== 'OFFLINE') {
        const scene = parseScene(options);
        this.scene=scene;
        if(typeof options.promotion==='string'&&/^cp_[0-9a-f]{32}$/.test(options.promotion))this.setData({promotionCode:options.promotion});
        this.session = createSession(wx,config.baseUrl);
        await this.session.login();
        if(config.commerce===true){this.setData({commerceEnabled:true});try{const listing=await this.session.commerce(scene,'products',{});this.setData({products:listing.products.map(p=>({...p,quantity:0}))});}catch(error){this.setData({products:[],status:error.message+'；已有订单可继续查询和申请售后'});}}
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
    this.client.storefront().then(s=>this.setData({merchant:s.merchant.name,
      beforeAd:s.ads.AD_SLOT_PAYMENT_AMOUNT ? s.ads.AD_SLOT_PAYMENT_AMOUNT.title : ''}))
      .catch(e=>this.setData({status:e.message}));
    } catch(e) {this.setData({status:e.message});}
  },
  onUnload() {if(this.client)this.client.reset();if(this.paymentFlow)this.paymentFlow.reset();if(this.session)this.session.clear();},
  quantity(e) {const id=e.currentTarget.dataset.id;const quantity=Number(e.detail.value);if(!Number.isSafeInteger(quantity)||quantity<0||quantity>10000)return;this.setData({products:this.data.products.map(p=>p.item_id===id?{...p,quantity}:p)});},
  inputProfile(e) {const field=e.currentTarget.dataset.field;if(['nickname','profileContact','referralCode'].includes(field))this.setData({[field]:e.detail.value});},
  inputProject(e) {this.setData({projectFeedback:e.detail.value});},
  selectProjectRequirement(e) {
    if(this.data.pending)return;
    const item=e.currentTarget.dataset.item,revision=Number(e.currentTarget.dataset.revision);
    if(typeof item==='string'&&Number.isSafeInteger(revision)&&revision>=0)
      this.setData({projectReferenceItem:item,projectReferenceRevision:revision,projectReference:''});
  },
  inputProjectReference(e){this.setData({projectReference:e.detail.value});},
  inputProjectReferenceKind(e){const items=['SECRETREF','OAUTH','SERVER_CHALLENGE'];const i=Number(e.detail.value);if(Number.isSafeInteger(i)&&items[i])this.setData({projectReferenceKind:items[i]});},
  async saveProjectReference() {
    if(this.data.pending||!this.session||!this.data.projectReferenceItem)return;
    if(typeof this.data.projectReference!=='string'||!this.data.projectReference.trim()||this.data.projectReference.length>256){this.setData({status:'材料引用编号不能为空且不得超过256字符'});return;}
    if(!['SECRETREF','OAUTH','SERVER_CHALLENGE'].includes(this.data.projectReferenceKind))return;
    const originalItem=this.data.projectReferenceItem,originalRevision=this.data.projectReferenceRevision;
    this.setData({pending:true});
    try{
      const r=await this.session.commerce(this.scene,'project_save_reference',{
        item:this.data.projectReferenceItem,revision:this.data.projectReferenceRevision,
        kind:this.data.projectReferenceKind,reference:this.data.projectReference});
      if(this.data.projectReferenceItem!==originalItem||this.data.projectReferenceRevision!==originalRevision)return;
      this.setData({projectReference:'',projectReferenceRevision:r.revision,status:'可信材料引用已保存，需单独提交审核'});
      const checklist=await this.session.commerce(this.scene,'project_checklist',{});
      this.setData({projectChecklist:checklist.items.map(v=>({
        id:v.id,state:v.state,required:v.required,revision:v.revision,title:v.title,instructions:v.instructions,submission_type:v.submission_type}))});
    }catch(error){this.setData({status:error.message});}
    finally{this.setData({pending:false});}
  },

  async submitProjectItem(e) {
    if(this.data.pending||!this.session)return;
    const item=e.currentTarget.dataset.item;
    const revision=Number(e.currentTarget.dataset.revision);
    if(typeof item!=='string'||!Number.isSafeInteger(revision)||revision<0)return;
    this.setData({pending:true});
    try {
      const result=await this.session.commerce(this.scene,'project_submit',{item,revision});
      this.setData({status:'资料版本已提交审核：'+result.state});
      const checklist=await this.session.commerce(this.scene,'project_checklist',{});
      this.setData({projectChecklist:checklist.items.map(entry=>({
        id:entry.id,state:entry.state,required:entry.required,revision:entry.revision,title:entry.title,instructions:entry.instructions,submission_type:entry.submission_type
      }))});
    } catch(error){this.setData({status:error.message});}
    finally {this.setData({pending:false});}
  },

  async projectAction(e) {
    if(this.data.pending||!this.session)return;
    const op=e.currentTarget.dataset.operation;
    if(!['project_summary','project_checklist','project_feedback','project_messages'].includes(op))return;
    this.setData({pending:true});
    try {
      const params=op==='project_feedback'?{message:this.data.projectFeedback}:{};
      const r=await this.session.commerce(this.scene,op,params);
      if(op==='project_summary')this.setData({projectTitle:r.title,projectRole:r.role,
        projectCustomerId:r.customer_id,projectState:r.checklist_overall});
      else if(op==='project_checklist')this.setData({projectChecklist:r.items.map(item=>({
        id:item.id,state:item.state,required:item.required,revision:item.revision,title:item.title,instructions:item.instructions,submission_type:item.submission_type}))});
      else if(op==='project_messages')this.setData({projectMessages:r.records,status:'读取原项目归档记录；不代表已获得人工回复'});
      else this.setData({projectFeedback:'',status:'项目反馈已归档，尚未确认人工回复：'+r.id});
    } catch(error) {this.setData({status:error.message});}
    finally {this.setData({pending:false});}
  },
  async profileAction(e) {
    if(this.data.pending||!this.session)return;this.setData({pending:true});
    try{const op=e.currentTarget.dataset.operation;let params={};
      if(op==='profile_update'){if(this.data.profileVersion===null)throw Error('先读取个人资料');params={nickname:this.data.nickname,contact:this.data.profileContact,expected_version:this.data.profileVersion};}
      else if(op==='referral_bind')params={code:this.data.referralCode};else if(op==='notices')params={after_id:''};
      if(!['profile_read','profile_update','referral_code','referral_bind','notices'].includes(op))throw Error('无效操作');
      const r=await this.session.commerce(this.scene,op,params);
      if(op==='profile_read'||op==='profile_update')this.setData({profileVersion:r.version,nickname:r.nickname,profileContact:r.contact,userId:r.user_id,projectCustomerId:r.project_customer_id});
      else if(op==='referral_code')this.setData({referralCode:r.code});else if(op==='notices')this.setData({notices:r.records});
      this.setData({status:op==='referral_bind'?'推荐关系已绑定':'个人中心已更新'});
    }catch(error){this.setData({status:error.message});}finally{this.setData({pending:false});}
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
  selectOrder(e) {if(this.data.pending)return;if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({reference:e.currentTarget.dataset.reference,refundApplication:'',afterAd:'',afterAdVerified:false});},
  inputRefund(e) {const field=e.currentTarget.dataset.field;if(['refundAmount','refundReason','refundApplication'].includes(field))this.setData({[field]:e.detail.value});},
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
  inputReference(e) {if(this.paymentFlow)this.paymentFlow.reset();if(this.client)this.client.reset();this.setData({reference:e.detail.value,afterAd:'',afterAdVerified:false});},
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
