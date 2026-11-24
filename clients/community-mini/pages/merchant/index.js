const {parseScene,getSharedSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
// Display-only projection; original minor units and state values stay unchanged.
const ORDER_STATE_ZH={CREATED:'已创建',PENDING:'待处理',PAID:'已支付（须以微信核验为准）',COMPLETED:'已完成',CANCELLED:'已取消',CANCELED:'已取消',REFUND_PENDING:'退款处理中',REFUNDED:'已退款',FAILED:'处理失败'};
function stateLabel(code){return Object.hasOwn(ORDER_STATE_ZH,code)?ORDER_STATE_ZH[code]:'状态待核实';}
function amountLabel(minor){if(!Number.isSafeInteger(minor))return '金额待核实';const absolute=Math.abs(minor),whole=Math.floor(absolute/100),cents=String(absolute%100).padStart(2,'0');return (minor<0?'-':'')+'¥'+whole+'.'+cents;}
const HOME_STATES=[['PENDING','待处理'],['SUCCESS','已支付'],['FAILED','处理失败'],['CANCELLED','已取消'],['REFUNDED','已退款']];
const nonnegative=x=>Number.isSafeInteger(x)&&x>=0;
const verifiedMoney=x=>nonnegative(x)?amountLabel(x):null;
function homeMetrics(summary){
 const m=summary&&summary.merchant_metrics;
 return {
   donation:verifiedMoney(m?.donation_minor),
   pointsOffset:verifiedMoney(m?.points_offset_minor),
   pointsBalance:Number.isSafeInteger(m?.merchant_points_balance)?String(m.merchant_points_balance)+' 分':null
 };
}
function homeAnalysisFromSummary(summary){
 if(!summary||!summary.counts||typeof summary.counts!=='object'||Array.isArray(summary.counts))return null;
 const counts=HOME_STATES.map(([key])=>summary.counts[key]);
 if(!counts.every(nonnegative))return null;
 const total=counts.reduce((a,b)=>a+b,0);
 if(!Number.isSafeInteger(total))return null;
 const metrics=homeMetrics(summary);
 return {total,view:{
   turnover:verifiedMoney(summary.order_total_minor),
   ...metrics,
   states:HOME_STATES.map(([key,label],i)=>({key,label,count:counts[i]})),
   refundedObserved:verifiedMoney(summary.provider_refund_observations_minor),
 }};
}
Page({
  scanStore(){return auth.scanStore(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goBack(){return auth.back(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
 data:{homeOrderState:'unavailable',homeOrders:[],homeOrderCount:null,homeAnalysis:null,workspaceDisplayName:'',workspaceDisplayNames:[],collectionCodeAllowed:false,codeRequestPending:false,pending:false,status:'',activeSection:'profile',needsScene:true,workspaces:[],workspace:'',view:'home',orders:[],summary:null,summaryDisplay:null,detail:null,detailDisplay:null,settings:null,codePath:'',codeReady:false,permissions:{},editor:null},
 onShow(){const activeScene=getApp().globalData.scene;if(this.scene&&(this._boundOpening?activeScene!==this._boundOpening.ambient:this._nativeOpening?activeScene!==this._nativeOpening.ambient:activeScene&&this.scene!==activeScene)&&!this.sceneStale){this.sceneStale=true;this.dead=true;this.clearHomeSummary();this.clearCode();this.session=null;this.setData({workspaces:[],workspace:'',orders:[],summary:null,detail:null,settings:null,codePath:'',codeReady:false,collectionCodeAllowed:false,editor:null,permissions:{},pending:false,status:'授权场景已切换，商家私有数据已清除，请重新进入对应门店'});}if(this.session&&typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated()&&!this.data.pending&&!this.sceneInvalid&&!this._sceneStale&&!this.sceneStale){this.connect({automatic:true});}else if(this._resumeCollection){this._resumeCollection=false;this.refreshCollectionPermission();}},
 async onLoad(options){this.profileWorkspace=options&&typeof options.profileWorkspace==='string'?options.profileWorkspace:'';this.dead=false;this.sceneStale=false;this.epoch=auth.current();try{
    if(options?.fromNativeOpening==='1'){
      if(typeof options.scene!=='string'||!/^wxn_[a-f0-9]{28}$/.test(options.scene)||
         !/^wxw_[a-f0-9]{48}$/.test(this.profileWorkspace))throw Error('WORKSPACE_NOT_VERIFIED');
      this._nativeOpening={ambient:getApp().globalData.scene,workspace:this.profileWorkspace};
      this.scene=parseScene({scene:options.scene});this.setData({needsScene:false});
      await this.connect({automatic:true});return;
    }
    if(options?.fromVerifiedOpening==='1'){
      this._boundOpening=auth.takeOpening(getApp());
      if(!this._boundOpening){this.setData({status:'该申请对应的工作台暂不可用，请返回查看进度'});return;}
      this.scene=parseScene({scene:this._boundOpening.scene});this.setData({needsScene:false});
      await this.connect({automatic:true});return;
    }
    if(!(options&&options.scene)&&!getApp().globalData.scene){this.scene='';this.setData({needsScene:true,status:'工作台仅向已有门店授权的商家开放；首次经营请先办理本人入驻。'});return;}this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});this.setData({needsScene:false});await this.connect({automatic:true});}catch(e){if(this.current())this.setData({status:customerError(e)});}},
 current(){return !this.dead&&!this.sceneStale&&auth.active(this.epoch);},
 async connect(options={}){if(this.data.pending)return;this.clearCode();this.clearHomeSummary();this.setData({collectionCodeAllowed:false,workspaces:[],workspace:'',permissions:{}});this.epoch=auth.current();if(!this.scene){this.setData({status:'请先扫码选择已授权门店；首次经营可直接办理入驻'});return;}this.setData({pending:true,status:'正在读取商家权限'});try{this.session=getSharedSession(wx,getApp().globalData,undefined,this);this.epoch=auth.current();this.setData({pending:true});await this.session.ensureLogin({automatic:options.automatic===true,prepared:true});const i=this._boundOpening;if(i&&(this.session!==i.s||!auth.openingSession(i.s,i.g,i.e)))return;
  const session=this.session,scene=this.scene,generation=session.getGeneration();
  const r=await session.merchant(scene,'workspaces',{});if(!this.current()||this.session!==session||this.scene!==scene||session.getGeneration()!==generation||!session.isAuthenticated()||i&&(this.session!==i.s||!auth.openingSession(i.s,i.g,i.e)))return;
  if(!r||!Array.isArray(r.workspaces)||r.workspaces.some(x=>typeof x!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(x)))throw Error('WORKSPACE_NOT_VERIFIED');
  const native=i||this._nativeOpening;
  if(/^wxn_[a-f0-9]{28}$/.test(scene)&&(!native||!/^wxw_[a-f0-9]{48}$/.test(native.workspace)||r.workspaces.length!==1||r.workspaces[0]!==native.workspace||
     getApp().globalData.scene!==native.ambient))throw Error('WORKSPACE_NOT_VERIFIED');
  const workspaces=i?(Array.isArray(r.workspaces)&&r.workspaces.includes(i.workspace)?[i.workspace]:[]):this.profileWorkspace?(r.workspaces.includes(this.profileWorkspace)?[this.profileWorkspace]:[]):r.workspaces;
  this.setData({workspaces,workspace:workspaces[0]||'',permissions:r.permissions||{},collectionCodeAllowed:this.collectionAllowed(workspaces[0],r.permissions),status:workspaces.length?'':'当前账号尚无已开通商家权限，可查看本人入驻进度'});
  if(workspaces.length)this.loadHome();}catch(e){if(this.current())this.setData({status:customerError(e)});}finally{if(this.current()){this.setData({pending:false});if(this.data.collectionCodeAllowed)this.collectionCode();}}},
 chooseWorkspace(e){if(this.data.pending||this._boundOpening||this._nativeOpening)return;this.clearCode();this.setData({workspace:this.data.workspaces[Number(e.detail.value)]||'',collectionCodeAllowed:this.collectionAllowed(this.data.workspaces[Number(e.detail.value)],this.data.permissions),orders:[],summary:null,detail:null,settings:null,codePath:'',codeReady:false,editor:null});this.loadHome();if(this.data.collectionCodeAllowed)this.collectionCode();},
 clearHomeSummary(){this.homeFlight=null;this.setData({homeOrders:[],homeOrderCount:null,homeAnalysis:null,homeOrderState:'unavailable',workspaceDisplayName:'',workspaceDisplayNames:[]});},
 async loadHome(){
  const session=this.session,scene=this.scene,workspace=this.data.workspace,epoch=this.epoch;
  if(!session||!workspace||typeof session.getGeneration!=='function'||!session.isAuthenticated())return;
  const generation=session.getGeneration(),flight={};this.homeFlight=flight;
  const current=()=>this.homeFlight===flight&&this.current()&&this.epoch===epoch&&this.session===session&&this.scene===scene&&
    this.data.workspace===workspace&&session.getGeneration()===generation&&session.isAuthenticated();
  this.setData({homeOrderState:'loading',homeOrders:[],homeOrderCount:null,homeAnalysis:null,workspaceDisplayName:'',workspaceDisplayNames:[]});
  try{
    const summary=await session.merchant(scene,'read',{workspace,operation:'community.summary',params:{}});
    if(!current())return;
    const analysis=homeAnalysisFromSummary(summary);
    this.setData({homeAnalysis:analysis?analysis.view:null});
    const total=analysis?analysis.total:null;
    if(total===0)this.setData({homeOrderState:'ready',homeOrderCount:0});
    else{
      // First five original records by reference, not most recent by time.
      const page=await session.merchant(scene,'read',{workspace,operation:'community.orders_page',params:{limit:5,after_id:'',status:'ALL'}});
      if(!current())return;
      const rows=page&&page.orders;
      if(Array.isArray(rows)&&rows.length<=5&&rows.every(x=>x&&typeof x.reference==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(x.reference))){
        this.setData({homeOrderState:'ready',homeOrderCount:Number.isSafeInteger(total)?total:null,
          homeOrders:rows.map(x=>({reference:x.reference,displayState:x.state==='SUCCESS'?'已支付（须以微信核验为准）':stateLabel(x.state),displayAmount:amountLabel(x.amount_minor)}))});
      }else this.setData({homeOrderState:'unavailable'});
    }
    const settings=await session.merchant(scene,'read',{workspace,operation:'community.merchant_settings',params:{}});
    if(!current())return;
    const name=settings&&settings.profile&&settings.profile.name;
    if(typeof name==='string'&&name.length<=120)this.setData({workspaceDisplayName:name});
  }catch(e){if(current()&&this.data.homeOrderState==='loading')this.setData({homeOrderState:'unavailable'});}
 },
 openSettings(){return this.open({currentTarget:{dataset:{view:'settings'}}});},
 async open(e){if(this.data.pending||!this.data.workspace)return;const view=e.currentTarget.dataset.view;const operations={orders:'community.orders',summary:'community.summary',settings:'community.merchant_settings'};if(!operations[view])return;this.setData({pending:true,status:'正在读取'});try{const r=await this.session.merchant(this.scene,'read',{workspace:this.data.workspace,operation:operations[view],params:{}});if(!this.current())return;this.setData({view,status:'',...(view==='orders'?{orders:r.orders.map(o=>({...o,displayState:stateLabel(o.state),displayAmount:amountLabel(o.amount_minor)}))}:view==='summary'?{summary:r,summaryDisplay:{turnover:verifiedMoney(r.order_total_minor),...homeMetrics(r),refunded:verifiedMoney(r.provider_refund_observations_minor)}}:{settings:r})});}catch(e){if(this.current()){this.setData({orders:[],summary:null,settings:null,status:customerError(e)});}}finally{if(this.current())this.setData({pending:false});}},
 async detail(e){if(this.data.pending)return;this.setData({pending:true,status:'正在读取订单'});try{const r=await this.session.merchant(this.scene,'read',{workspace:this.data.workspace,operation:'community.order_detail',params:{reference:e.currentTarget.dataset.reference}});if(this.current())this.setData({view:'detail',detail:r,detailDisplay:{state:stateLabel(r.order.state),amount:amountLabel(r.order.amount_minor)},status:''});}catch(e){if(this.current())this.setData({detail:null,status:customerError(e)});}finally{if(this.current())this.setData({pending:false});}},
 editProfile(){if(this.data.pending||!this.data.settings||!this.data.settings.profile||!this.data.permissions[this.data.workspace]?.profile_edit)return;const {name,description,contact,status,version}=this.data.settings.profile;this.editorVersion=version;this.setData({view:'profile-edit',editor:{name,description,contact,status}});},
 editInput(e){const key=e.currentTarget.dataset.key;if(this.data.editor&&['name','description','contact'].includes(key))this.setData({editor:{...this.data.editor,[key]:e.detail.value}});},
 async saveProfile(){if(this.data.pending||!this.data.editor)return;this.setData({pending:true,status:'正在保存门店资料'});try{await this.session.merchant(this.scene,'write',{workspace:this.data.workspace,operation:'community.profile',params:{record:this.data.editor,expected_version:this.editorVersion}});if(!this.current())return;const settings=await this.session.merchant(this.scene,'read',{workspace:this.data.workspace,operation:'community.merchant_settings',params:{}});if(this.current())this.setData({view:'settings',settings,editor:null,status:'门店资料已保存'});}catch(e){if(this.current())this.setData({status:customerError(e)+'；请先重新读取资料确认结果'});}finally{if(this.current())this.setData({pending:false});}},
 async refreshCollectionPermission(){
  const session=this.session,scene=this.scene,workspace=this.data.workspace,epoch=this.epoch;
  if(!this.current()||this.data.pending||!workspace||!session||!session.isAuthenticated())return;
  const generation=session.getGeneration(),flight={};
  this._collectionRefresh=flight;
  const current=()=>this._collectionRefresh===flight&&this.current()&&this.session===session&&
    this.scene===scene&&this.data.workspace===workspace&&this.epoch===epoch&&session.isAuthenticated()&&session.getGeneration()===generation;
  try{
    const r=await session.merchant(scene,'workspaces',{});
    if(!current())return;
    const exact=Array.isArray(r?.workspaces)&&r.workspaces.includes(workspace)&&
      (!(this._nativeOpening||this._boundOpening)||r.workspaces.length===1);
    const allowed=exact&&this.collectionAllowed(workspace,r.permissions||{});
    if(!allowed)this.clearCode();
    const permissions={...this.data.permissions,[workspace]:{...this.data.permissions?.[workspace],collection_code:!!allowed}};
    this.setData({permissions,collectionCodeAllowed:!!allowed});
    if(allowed&&!this.data.codeReady)this.collectionCode();
  }catch(e){
    if(current()){
      this.clearCode();
      this.setData({permissions:{...this.data.permissions,[workspace]:{...this.data.permissions?.[workspace],collection_code:false}},collectionCodeAllowed:false});
    }
  }finally{if(this._collectionRefresh===flight)this._collectionRefresh=null;}
 },
 collectionAllowed(workspace,permissions=this.data.permissions){
  return typeof workspace==='string'&&!!workspace&&permissions&&Object.prototype.hasOwnProperty.call(permissions,workspace)&&
     permissions[workspace]&&permissions[workspace].collection_code===true||false;
 },
 collectionBinding(){
  const session=this.session,scene=this.scene,workspace=this.data.workspace,epoch=this.epoch;
  if(!this.current()||!session||typeof session.getGeneration!=='function'||typeof session.isAuthenticated!=='function'||
     !session.isAuthenticated()||!this.collectionAllowed(workspace))return null;
  const generation=session.getGeneration();
  return {session,scene,workspace,current:()=>this.current()&&this.session===session&&this.scene===scene&&this.epoch===epoch&&
      this.data.workspace===workspace&&session.getGeneration()===generation&&session.isAuthenticated()&&this.collectionAllowed(workspace)};
 },
 async collectionCode(){
  if(this.data.pending||this.data.codeRequestPending)return;
  const captured=this.collectionBinding();if(!captured)return;
  this.clearCode();const request={...captured};this._codeRequest=request;
  const current=()=>this._codeRequest===request&&request.current();
  this.setData({codeRequestPending:true,status:'正在读取本店二维码'});
  let path=null;
  try{
   const r=await request.session.merchant(request.scene,'collection_code',{workspace:request.workspace});
   if(!current())return;
   const ownQr=r&&r.kind==='SELF_HOSTED_CASHIER_ENTRY_QR'&&r.mime==='image/png'&&r.payable===false&&r.approval_verified===true&&r.payment_product_admitted===false&&typeof r.locator==='string'&&/^fx[0-9a-f]{24}$/.test(r.locator)&&r.fixed_url==='https://uk.wenwenwenyiyiyi.work/community-preview/go/'+r.locator;
   const miniEntry=r&&r.kind==='RELEASE_MINI_COLLECTION_CODE'&&r.page==='pages/checkout/index';
   if(!r||!(ownQr||miniEntry)||r.scene!==request.scene||r.payment_completed!==false||
      !['image/png','image/jpeg'].includes(r.mime)||typeof r.content_base64!=='string'||r.content_base64.length<44||r.content_base64.length>1333336||
      r.content_base64.length%4!==0||!/^[A-Za-z0-9+/]+={0,2}$/.test(r.content_base64)||!/^([0-9a-f]{64})$/.test(r.sha256)||
      !(r.mime==='image/png'?r.content_base64.startsWith('iVBORw0KGgo'):r.content_base64.startsWith('/9j/')))throw Error('UNTRUSTED_COLLECTION_CODE');
   path=wx.env.USER_DATA_PATH+'/community-collection-code-'+Date.now()+'-'+Math.random().toString(16).slice(2)+'.'+(r.mime==='image/png'?'png':'jpg');
   await new Promise((resolve,reject)=>wx.getFileSystemManager().writeFile({filePath:path,data:r.content_base64,encoding:'base64',success:resolve,fail:reject}));
   if(!current())return;
   this.codeFile=path;this._codeBinding=captured;path=null;
   this.setData({codePath:this.codeFile,codeReady:true,status:'二维码已就绪；付款能力仍待核实'});
  }catch(e){if(current())this.setData({codePath:'',codeReady:false,status:'暂未取得本店二维码'});}
  finally{
   if(path)this.deleteCollectionFile(path);
   if(this._codeRequest===request){
      this._codeRequest=null;
      if(this.current())this.setData({codeRequestPending:false,collectionCodeAllowed:request.current()});
   }
  }
 },
 saveCollectionCode(){
  const binding=this._codeBinding,path=this.codeFile;
  const current=()=>this._codeBinding===binding&&this.codeFile===path&&binding.current();
  if(!binding||!path||!this.data.codeReady||this.data.pending||this.data.codeRequestPending||!current())return;
  wx.saveImageToPhotosAlbum({filePath:path,success:()=>{if(current())this.setData({status:'收款码已保存相册'});},
     fail:()=>{if(current())this.setData({status:'未能保存相册；请检查相册权限后重试'});}});
 },
 deleteCollectionFile(path){if(path)try{wx.getFileSystemManager().unlink({filePath:path,fail(){}});}catch(e){}},
 clearCode(){
   this._codeRequest=null;this._codeBinding=null;
   const path=this.codeFile;this.codeFile=null;this.deleteCollectionFile(path);
   this.setData({codePath:'',codeReady:false,codeRequestPending:false});
 },
 showCollection(){if(this.data.pending||!this.collectionAllowed(this.data.workspace))return;this.setData({view:'collection'});},
 backSettings(){if(this.data.pending)return;this.setData({view:this.data.settings?'settings':'home',editor:null});},
 back(){this.setData({view:'home',detail:null,editor:null});},
  navigateSection(e){return auth.navigate(this,e.currentTarget.dataset.section,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  join(){return auth.navigate(this,'join',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goHome(){return auth.navigate(this,'home',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goRecommendations(){return auth.navigate(this,'recommendations',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goProfile(){return auth.navigate(this,'profile',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
 customerSessionRevoked(){this.clearHomeSummary();this.clearCode();if(this.session)this.session.clear();this.setData({workspaces:[],workspace:'',orders:[],summary:null,detail:null,settings:null,codePath:'',codeReady:false,collectionCodeAllowed:false,editor:null,permissions:{},pending:false,status:'登录已退出，请重新进入'});},
 onHide(){this._resumeCollection=true;this._collectionRefresh=null;this.clearCode();},
 onUnload(){this.dead=true;this._collectionRefresh=null;this.clearCode();if(this.session&&this.session.detachPage)this.session.detachPage(this);this.session=null;}
});
