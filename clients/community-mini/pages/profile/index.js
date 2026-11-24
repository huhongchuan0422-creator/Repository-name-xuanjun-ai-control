const {parseScene,getSharedSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
function nativeOpeningTarget(a){
  return a&&a.opening_state==='OPENED'&&typeof a.application==='string'&&
    typeof a.opening_scene==='string'&&/^wxn_[a-f0-9]{28}$/.test(a.opening_scene)&&
    typeof a.opening_workspace==='string'&&/^wxw_[a-f0-9]{48}$/.test(a.opening_workspace)?
      {scene:a.opening_scene,workspace:a.opening_workspace}:null;
}
async function discover(contexts, currentScene, readWorkspaces, alive) {
 if(!contexts||contexts.scope!=='CURRENT_CUSTOMER_AUTHORIZED_CONTEXTS'||contexts.has_more!==false||
    contexts.next_cursor!==null||!Array.isArray(contexts.contexts)||!alive())return null;
 const scenes=[...new Set(contexts.contexts.map(x=>x&&x.scene))];
 if(scenes.some(scene=>typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)))return null;
 let found=null;
 for(const scene of scenes){
  if(!alive())return null;
  if(scene===currentScene)continue; // caller has verified its authoritative empty result
  const result=await readWorkspaces(scene);
  if(!alive())return null;
  if(!result||!Array.isArray(result.workspaces)||result.workspaces.some(w=>typeof w!=='string'||!w))return null;
  if(!result.workspaces.length)continue;
  if(found||result.workspaces.length!==1)return null;
  const workspace=result.workspaces[0];
  if(result.permissions?.[workspace]?.profile_edit!==true)return null;
  found={scene,workspace};
 }
 return found;
}
Page({
  openH5Confirm(){if(!this.data.pending)wx.navigateTo({url:"/pages/h5-confirm/index"});},
  reviewerInput(e){
    this._reviewerRequest=null;
    const field=e.currentTarget.dataset.field;
    if(field==='reviewerChallenge'||field==='reviewerScene')this.setData({[field]:e.detail.value,reviewerDescription:null,reviewerStatus:'内容已变化，请重新核对。',reviewerPending:false});
  },
  reviewerCancel(){this._reviewerRequest=null;this.setData({reviewerDescription:null,reviewerPending:false,reviewerStatus:'已关闭本次确认；如已提交确认，请在原浏览器取消该请求。'});},
  async reviewerDescribe(){
    if(this._dead||this.data.reviewerPending||!this.session||!this.data.authenticated)return;
    const request={session:this.session,epoch:auth.current(),scene:(this.data.reviewerScene||this.scene||'').trim(),challenge:(this.data.reviewerChallenge||'').trim()};
    this._reviewerRequest=request;this.setData({reviewerPending:true,reviewerDescription:null,reviewerStatus:'正在核对本人权限与浏览器…'});
    const current=()=>!this._dead&&this._reviewerRequest===request&&this.session===request.session&&auth.active(request.epoch)&&this.data.authenticated;
    try{const result=await request.session.reviewerBrowser(request.scene,'DESCRIBE',request.challenge);if(!current())return;this.setData({reviewerDescription:result,reviewerStatus:'核对网址与浏览器校验码；仅确认本人正在操作的浏览器。'});}
    catch(_){if(current())this.setData({reviewerStatus:'未能核实：可能无审核权限、请求失效或身份变化；未授予任何权限。'});}
    finally{if(current())this.setData({reviewerPending:false});}
  },
  async reviewerConfirm(){
    const request=this._reviewerRequest,description=this.data.reviewerDescription;
    if(this._dead||this.data.reviewerPending||!request||!description||this.session!==request.session||!auth.active(request.epoch)||!this.data.authenticated)return;
    this.setData({reviewerPending:true});
    const current=()=>!this._dead&&this._reviewerRequest===request&&this.session===request.session&&auth.active(request.epoch)&&this.data.authenticated;
    try{
      const accepted=await new Promise(resolve=>wx.showModal({title:'确认本人浏览器登录',content:'网址：'+description.origin+'\n项目：'+description.project+'\n校验码：'+description.verification+'\n我已逐字核对本人浏览器，不是他人发来的请求。',confirmText:'本人确认',cancelText:'取消',success:r=>resolve(r.confirm===true),fail:()=>resolve(false)}));
      if(!current()||!accepted)return;
      await request.session.reviewerBrowser(request.scene,'CONFIRM_THIS_BROWSER',request.challenge,description.verification);
      if(current()){this.setData({reviewerDescription:null,reviewerStatus:'已确认。请回到本人浏览器完成登录；本操作未授予角色。'});this._reviewerRequest=null;}
    }catch(_){if(current())this.setData({reviewerDescription:null,reviewerStatus:'确认结果未知；请在原浏览器查询或取消。不会自动重试。'});}
    finally{if(!this._dead&&(this._reviewerRequest===request||this._reviewerRequest===null)&&this.session===request.session&&auth.active(request.epoch))this.setData({reviewerPending:false});}
  },

  profileAgreement(){
    // Host loads only the actual approved documents. Empty configuration
    // means no phone-capable profile request, not a synthetic agreement.
    const d=getApp().globalData.profilePhonePolicy;
    if(!d||typeof d.version!=='string'||!d.version||
      typeof d.agreementPage!=='string'||!/^\/pages\/[A-Za-z0-9_/-]+$/.test(d.agreementPage))return null;
    return d;
  },
  profilePhoneDocs(){
    const d=this.profileAgreement();
    return d&&d.privacyContractPublished===true&&typeof wx.openPrivacyContract==='function'?d:null;
  },
  showProfile(){this.setData({pageMode:'profile-edit',phoneAgreementAvailable:!!this.profileAgreement(),phoneDocsAvailable:!!this.profilePhoneDocs()});},
  openUserAgreement(){
    const d=this.profileAgreement();
    if(!d){this.setData({privacyStatus:'暂时无法打开用户服务协议'});return;}
    wx.navigateTo({url:d.agreementPage,fail:()=>{if(!this._dead)this.setData({privacyStatus:'暂时无法打开用户服务协议'});}});
  },
  hasProfilePhoneConsent(){
    const d=this.profilePhoneDocs(), a=this._profilePhoneConsent;
    return !!(d&&a&&a.version===d.version&&a.session===this.session&&a.scene===this.scene&&
      a.attempt===this._loginAttempt&&a.epoch===this._authEpoch&&auth.active(a.epoch)&&!this._dead&&
      !this._sceneStale&&this.data.authenticated);
  },
  async agreeProfilePhone(){
    const docs=this.profilePhoneDocs();
    if(!docs||!this.session||!this.scene||!this.data.authenticated||this.data.pending||this.data.pageMode!=='profile-edit'){
      if(!this._dead)this.setData({privacyStatus:'请先登录并查看已发布的用户服务协议和隐私政策'});
      return;
    }
    const a={version:docs.version,session:this.session,scene:this.scene,attempt:this._loginAttempt,epoch:this._authEpoch};
    this._profilePhoneConsent=a;
    this.setData({phoneConsent:true,pending:true,privacyStatus:''});
    try{await this.loadProfile(a.epoch,a.attempt);}
    catch(_){if(this._profilePhoneConsent===a&&this.hasProfilePhoneConsent())this.setData({privacyStatus:'暂未读取个人资料，请稍后重试'});}
    finally{if(!this._dead&&this._profilePhoneConsent===a)this.setData({pending:false});}
  },
  clearProfilePhoneConsent(){
    this._profilePhoneConsent=null;
    this._saveAttempt=(this._saveAttempt||0)+1;
    if(!this._dead)this.setData({phoneConsent:false,loaded:false,nickname:'',contact:'',version:null,userId:'',customerId:''});
  },
  declineProfilePhone(){
    const wasPhone=!!this._profilePhoneConsent;
    this.clearProfilePhoneConsent();
    if(!this._dead)this.setData({privacyStatus:'已停止在本页读取或编辑手机号；订单、通知和商家服务仍可用',...(wasPhone?{pending:false}:{})});
  },
  showNotices(){this.setData({pageMode:'notices'});if(this.data.authenticated&&!this.data.noticesLoaded)this.loadNotices();},
  scanStore(){return auth.scanStore(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goBack(){return auth.back(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  showAccount(){this.setData({pageMode:'account'});},
  backProfile(){this.setData({pageMode:'profile'});},
  openPrivacy(){
    if(this._dead)return;
    const fail=()=>{if(!this._dead)this.setData({privacyStatus:'暂时无法打开隐私保护指引，请稍后重试或联系项目负责人'});};
    if(typeof wx.openPrivacyContract!=='function'){fail();return;}
    this.setData({privacyStatus:''});
    try{wx.openPrivacyContract({fail});}catch(_){fail();}
  },
  data:{h5EntryAvailable:false,pageMode:'profile',privacyStatus:'',phoneConsent:false,phoneDocsAvailable:false,phoneAgreementAvailable:false,merchantEntry:'unknown',merchantEntryPending:false,merchantEntryLabel:'商家服务',merchantEntryHint:'正在核对工作台',status:'',authenticated:false,pending:false,loaded:false,activeSection:'profile',needsScene:true,version:null,nickname:'',contact:'',userId:'',customerId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',selectedNotice:null,noticeDetailOpen:false},
  async onShow(){if(this._profilePhoneConsent&&!this.hasProfilePhoneConsent()){this.clearProfilePhoneConsent();this.setData({pending:false});}const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this._sceneStale){this._sceneStale=true;this.customerSessionRevoked('授权场景已切换，当前客户资料已清除，请重新进入对应门店',false);}if(this.session&&typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated()&&!this.data.pending&&!this.sceneInvalid&&!this._sceneStale&&!this.sceneStale){await this.loginAndLoad({automatic:true});}if(this.data.authenticated&&!this.data.merchantEntryPending&&!this._sceneStale)this.loadMerchantEntry();},
  async onLoad(options){this.setData({h5EntryAvailable:typeof window==='undefined'});this._dead=false;this._sceneStale=false;this._authEpoch=auth.current();try{this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});}catch(e){this.scene=null;this.sceneInvalid=!!(options&&options.scene);this.clearPrivate('');this.setData({needsScene:true});if(!this.sceneInvalid&&getApp().globalData.baseUrl)await this.loginAndLoad({automatic:true});return;}this.setData({needsScene:false});await this.loginAndLoad({automatic:true});},
  onUnload(){this._dead=true;this._profilePhoneConsent=null;this._noticeRequest=null;if(this.session&&this.session.detachPage)this.session.detachPage(this);this.session=null;},
  async loginAndLoad(options={}){
    if(this.data.pending)return;
    if(this.sceneInvalid){this.setData({status:'门店入口无效，请返回首页或重新扫描有效门店码'});return;}
    let attempt=this._loginAttempt=(this._loginAttempt||0)+1;let epoch=auth.current();this._authEpoch=epoch;
    this.clearProfilePhoneConsent();this._merchantRequest=null;this.setData({pending:true,status:'',authenticated:false,loaded:false,merchantEntry:'unknown',merchantEntryPending:false,merchantEntryLabel:'商家服务',merchantEntryHint:'正在核对工作台'});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法读取本人资料');
      this.session=getSharedSession(wx,config,undefined,this);
      epoch=this._authEpoch=auth.current();attempt=this._loginAttempt=(this._loginAttempt||0)+1;this.setData({pending:true});
      await this.session.ensureLogin({automatic:options.automatic===true,prepared:true});
      if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch)){return;}
      this.setData({authenticated:true});
      if(!this.scene)await this.resolveProfileScene(epoch,attempt);
      if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.loadMerchantEntry(epoch,attempt);
    }catch(e){if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch)){if(e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED')auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'登录已失效，请重新登录');else{this.session=null;this.clearPrivate(customerError(e));}}}
    finally{if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.setData({pending:false});}
  },
  clearPrivate(status){this.clearProfilePhoneConsent();this._reviewerRequest=null;this.setData({reviewerDescription:null,reviewerChallenge:'',reviewerStatus:'',reviewerPending:false});this._merchantRequest=null;this._noticeRequest=null;this.setData({pageMode:'profile',merchantEntry:'unknown',merchantEntryPending:false,merchantEntryLabel:'商家服务',merchantEntryHint:'正在核对工作台',authenticated:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',selectedNotice:null,noticeDetailOpen:false,status});},
  async resolveProfileScene(epoch=this._authEpoch,attempt=this._loginAttempt){
    if(!this.session||this.scene)return;
    const r=await this.session.customer('contexts',{});
    if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch))return;
    if(!r||!Array.isArray(r.contexts)||r.contexts.some(c=>!c||typeof c.scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(c.scene)))throw Error('个人资料暂时无法加载');
    this._merchantDefaultContext={r,session:this.session,generation:typeof this.session.getGeneration==='function'?this.session.getGeneration():null,epoch,attempt,scene:r.contexts[0]?.scene||''};
    if(r.contexts.length){this.scene=r.contexts[0].scene;this.setData({needsScene:false});}
  },
  async loadMerchantEntry(epoch=this._authEpoch,attempt=this._loginAttempt){
    if(!this.session||!this.data.authenticated)return;
    const oldNative=this._boundMerchant;
    const nativeCurrent=()=>oldNative&&oldNative.direct&&this._boundMerchant===oldNative&&
      !this._dead&&!this._sceneStale&&this.data.authenticated&&this.session===oldNative.request.session&&
      this._loginAttempt===oldNative.request.attempt&&(this.scene||'')===oldNative.request.scene&&
      getApp().globalData.scene===oldNative.request.globalScene&&auth.active(oldNative.request.epoch)&&
      oldNative.request.generation!==null&&this.session.getGeneration()===oldNative.request.generation&&this.session.isAuthenticated();
    const stillRecent=()=>Date.now()-oldNative.verifiedAt>=0&&Date.now()-oldNative.verifiedAt<60000;
    const keepNative=this.data.merchantEntry==='ready'&&nativeCurrent();
    const transient=e=>e&&e.code!=='ACCESS_DENIED'&&e.message!=='SESSION_EXPIRED'&&e.message!=='SIGNED_OUT'&&
      (e.networkKind==='TIMEOUT'||[408,502,503,504].includes(e.httpStatus||e.statusCode||e.accessHttpStatus));
    const clearBound=()=>{this._boundMerchant=null;};
    let phase='OWNER_MINE';
    const note=e=>{
      const reason=e&&e.code==='ACCESS_DENIED'?'ACCESS_DENIED':transient(e)?'TIMEOUT_OR_UPSTREAM':null;
      if(reason&&typeof console!=='undefined'&&typeof console.debug==='function')
        console.debug('MERCHANT_ENTRY_DISCOVERY',phase,reason);
    };
    const unavailable={merchantEntry:'unknown',merchantEntryLabel:'商家服务',merchantEntryHint:'暂不能确认工作台，点击重新查询'};
    const request={session:this.session,scene:this.scene||'',epoch,attempt,generation:typeof this.session.getGeneration==='function'?this.session.getGeneration():null,globalScene:getApp().globalData.scene};this._merchantRequest=request;this._merchantTarget=null;if(!keepNative)clearBound();
    // Empty-scene sessions are valid for onboarding, never a fabricated workspace.
    const valid=()=>!this._dead&&!this._sceneStale&&this._merchantRequest===request&&this.session===request.session&&(this.scene||'')===request.scene&&auth.active(epoch)&&attempt===this._loginAttempt&&getApp().globalData.scene===request.globalScene&&(request.generation===null||request.session.getGeneration()===request.generation);
    this.setData(keepNative?{merchantEntryPending:true}:{merchantEntry:'unknown',merchantEntryPending:true,merchantEntryLabel:'商家服务',merchantEntryHint:'正在核对工作台'});
    try{
      let exact=null,nativeRead=null;
      try{
        const fresh=await request.session.merchant('','onboarding',{operation:'mine',params:{}});
        if(!valid())return;nativeRead=fresh;
        const rows=Array.isArray(fresh?.applications)?fresh.applications.filter(x=>nativeOpeningTarget(x)||auth.openingTarget(x)):[];
        if(rows.length===1&&fresh.next_cursor==null)exact=rows[0];
        else if(rows.length>1||rows.length===1&&fresh.next_cursor!=null){clearBound();this.setData({merchantEntry:'progress',merchantEntryLabel:'入驻进度',merchantEntryHint:'请打开对应的申请查看门店'});return;}
      }catch(e){if(!valid())return;throw e;}
      if(exact){
        phase='EXACT_WORKSPACE';
        const direct=nativeOpeningTarget(exact);const target=direct||auth.openingTarget(exact);
        // Retain a verified route only when a transient reply concerns same app/workspace.
        if(keepNative&&(!direct||direct.scene!==oldNative.direct.scene||direct.workspace!==oldNative.direct.workspace||
           exact.application!==oldNative.exact.application))clearBound();
        const granted=await request.session.merchant(target.scene,'workspaces',{});
        if(!valid())return;
        const native=/^wxn_[a-f0-9]{28}$/.test(target.scene);
        if(!Array.isArray(granted?.workspaces)||!granted.workspaces.includes(target.workspace)||
           native&&(granted.workspaces.length!==1||!/^wxw_[a-f0-9]{48}$/.test(target.workspace))){
          clearBound();this.setData(unavailable);return;
        }
        this._boundMerchant={exact,request,direct,verifiedAt:Date.now()};
        this.setData({merchantEntry:'ready',merchantEntryLabel:'商家工作台',merchantEntryHint:'管理已授权门店的日常经营'});return;
      }
      clearBound();
      if(request.scene){
        phase='CURRENT_WORKSPACE';
        const workspace=await request.session.merchant(request.scene,'workspaces',{});
        if(!valid())return;
        if(!workspace||!Array.isArray(workspace.workspaces)||workspace.workspaces.some(x=>typeof x!=='string'||!x))throw Error('商家授权返回未确认');
        if(workspace.workspaces.length){this.setData({merchantEntry:'ready',merchantEntryLabel:'商家工作台',merchantEntryHint:'管理已授权门店的日常经营'});return;}
      }
      const defaults=this._merchantDefaultContext;
      if(!request.globalScene&&defaults&&defaults.scene===request.scene&&defaults.session===request.session&&defaults.epoch===epoch&&defaults.attempt===attempt&&defaults.generation===request.generation){
        phase='LEGACY_DISCOVERY';
        const target=await discover(defaults.r,request.scene,scene=>request.session.merchant(scene,'workspaces',{}),valid);
        if(!valid())return;
        if(target){this._merchantTarget={...target,request};this.setData({merchantEntry:'ready',merchantEntryLabel:'商家工作台',merchantEntryHint:'管理已授权门店的日常经营'});return;}
      }
      phase='APPLICATION_LIST';
      const result=nativeRead;
      if(!valid())return;
      if(!result||!Array.isArray(result.applications)||result.applications.some(a=>!a||typeof a.application!=='string'||typeof a.status!=='string'))throw Error('入驻申请返回未确认');
      if(!result.applications.length&&result.next_cursor!=null){this.setData(unavailable);return;}
      this.setData(result.applications.length?{merchantEntry:'progress',merchantEntryLabel:'入驻进度',merchantEntryHint:'查看申请进度和审核意见'}:{merchantEntry:'none',merchantEntryLabel:'申请入驻',merchantEntryHint:'开始申请成为商家'});
    }catch(e){note(e);if(valid()&&!(keepNative&&nativeCurrent()&&stillRecent()&&transient(e))){clearBound();this.setData(unavailable);}}
    finally{
      if(valid()){this._merchantRequest=null;this.setData({merchantEntryPending:false});}
      else if(this._merchantRequest===request&&this.session===request.session&&this._loginAttempt===request.attempt){
        this._merchantRequest=null;this._merchantTarget=null;clearBound();
        this.setData({...unavailable,merchantEntryPending:false});
      }
    }
  },
  openMerchantEntry(){
    if(!this.data.authenticated||this.data.pending||this.data.merchantEntryPending)return;
    if(this.data.merchantEntry==='ready')return this.openMerchant();
    if(['none','progress'].includes(this.data.merchantEntry))return this.openJoin();
    return this.loadMerchantEntry();
  },
  validateProfile(r){
    if(!r||typeof r.user_id!=='string'||typeof r.project_customer_id!=='string'||typeof r.nickname!=='string'||typeof r.contact!=='string'||!Number.isSafeInteger(r.version)||r.version<0)throw Error('本人资料返回无效');
    return r;
  },
  async loadProfile(epoch=this._authEpoch,attempt=this._loginAttempt){
    const consent=this._profilePhoneConsent;
    if(!this.hasProfilePhoneConsent())return;
    const raw=await this.session.commerce(this.scene,'profile_read',{});
    if(this._profilePhoneConsent!==consent||!this.hasProfilePhoneConsent()||
      attempt!==this._loginAttempt||!auth.active(epoch))return;
    const r=this.validateProfile(raw);
    this.setData({loaded:true,version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:''});
  },
  noticeCurrent(request){return !this._dead&&request===this._noticeRequest&&request.attempt===this._loginAttempt&&request.epoch===this._authEpoch&&auth.active(request.epoch)&&this.data.authenticated&&this.session===request.session&&this.scene===request.scene;},
  async loadNotices(e,epoch=this._authEpoch,attempt=this._loginAttempt,more=!!(e&&e.currentTarget&&e.currentTarget.dataset.more==='true')){
    if(this._dead||!this.data.authenticated||!this.session||!this.scene||this.data.noticePending)return;
    if(more&&(!this.data.noticesLoaded||!this.data.noticesMore||!this.data.noticeCursor))return;
    const request={epoch,attempt,session:this.session,scene:this.scene,after:more?this.data.noticeCursor:''};
    this._noticeRequest=request;this.setData({noticePending:true,noticeStatus:''});
    try{
      const r=await request.session.commerce(request.scene,'notices',{after_id:request.after});
      if(!this.noticeCurrent(request))return;
      if(!r||!Array.isArray(r.records)||r.records.length>50||typeof r.has_more!=='boolean'||r.records.some(n=>!n||typeof n.id!=='string'||!/^[0-9a-f]{64}$/.test(n.id)||typeof n.message!=='string'||typeof n.read!=='boolean')||(r.has_more?(!r.records.length||typeof r.next_cursor!=='string'||!/^[0-9a-f]{64}$/.test(r.next_cursor)||r.next_cursor<=request.after):r.next_cursor!==null))throw Error('通知列表返回未确认');
      const map=new Map((more?this.data.notices:[]).map(n=>[n.id,n]));for(const n of r.records){const prior=map.get(n.id);map.set(n.id,{...n,read:n.read||!!(prior&&prior.read)});}
      this.setData({notices:Array.from(map.values()),noticeCursor:r.next_cursor,noticesMore:r.has_more,noticesLoaded:true});
    }catch(e){if(this.noticeCurrent(request)){const denied=e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED';this.setData({...(denied?{notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false}:{}),noticeStatus:denied?'通知访问被拒绝或会话已过期，请重新登录':e.message});}}
    finally{if(this.noticeCurrent(request)){this._noticeRequest=null;this.setData({noticePending:false});}}
  },
  openNotice(e){const id=e.currentTarget.dataset.id;const notice=this.data.notices.find(x=>x.id===id);if(!notice)return;this.setData({selectedNotice:notice,noticeDetailOpen:true});},
  backNoticeList(){this.setData({selectedNotice:null,noticeDetailOpen:false});},
  async markNoticeRead(e){
    if(this._dead||!this.data.authenticated||!this.session||this.data.noticePending)return;
    const id=e.currentTarget.dataset.id,n=this.data.notices.find(x=>x.id===id);if(!n||n.read||typeof id!=='string'||!/^[0-9a-f]{64}$/.test(id))return;
    const request={epoch:this._authEpoch,attempt:this._loginAttempt,session:this.session,scene:this.scene,after:''};this._noticeRequest=request;this.setData({noticePending:true,noticeStatus:''});
    try{const r=await request.session.commerce(request.scene,'notice_read',{notice_id:id});if(!this.noticeCurrent(request))return;if(!r||r.id!==id||r.read!==true)throw Error('通知已读状态未确认');const updated=this.data.notices.map(x=>x.id===id?{...x,read:true}:x);this.setData({notices:updated,selectedNotice:this.data.selectedNotice&&this.data.selectedNotice.id===id?{...this.data.selectedNotice,read:true}:this.data.selectedNotice});}
    catch(err){if(this.noticeCurrent(request)){const denied=err.code==='ACCESS_DENIED'||err.message==='SESSION_EXPIRED';this.setData({...(denied?{notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false}:{}),noticeStatus:denied?'通知访问被拒绝或会话已过期，请重新登录':err.message});}}
    finally{if(this.noticeCurrent(request)){this._noticeRequest=null;this.setData({noticePending:false});}}
  },
  retryLogin(){return this.loginAndLoad();},
  openJoin(){return auth.navigate(this,'join',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  openMerchant(){
    const bound=this._boundMerchant;
    if(!bound)return this._openLegacyMerchant();
    const r=bound.request;
    if(this.session!==r.session||this._loginAttempt!==r.attempt||(this.scene||'')!==r.scene||
       getApp().globalData.scene!==r.globalScene)return;
    if(bound.direct){
      if(!auth.active(r.epoch)||r.generation===null||r.session.getGeneration()!==r.generation||!r.session.isAuthenticated())return;
      if(this._navigationPending||!this.data.authenticated||this.data.pending)return;
      this._navigationPending=true;
      const clear=()=>{this._navigationPending=false;};
      try{return wx.navigateTo({url:'/pages/merchant/index?fromNativeOpening=1&scene='+encodeURIComponent(bound.direct.scene)+'&profileWorkspace='+encodeURIComponent(bound.direct.workspace),complete:clear});}
      catch(_){clear();return;}
    }
    if(!auth.openingSession(r.session,r.generation,r.epoch))return;
    return auth.navigateOpening(this,bound.exact,wx,getApp());
  },
  _openLegacyMerchant(){
    const t=this._merchantTarget;
if(!t)return auth.navigate(this,'merchant',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);
    const r=t.request;
    if(this._dead||this._sceneStale||this._navigationPending||this.data.pending||this.data.merchantEntry!=='ready'||this.session!==r.session||
       !auth.active(r.epoch)||this._loginAttempt!==r.attempt||(this.scene||'')!==r.scene||getApp().globalData.scene!==r.globalScene||
       (r.generation!==null&&r.session.getGeneration()!==r.generation))return;
    this._navigationPending=true;
    const clear=()=>{this._navigationPending=false;};
    try{wx.navigateTo({url:'/pages/merchant/index?scene='+encodeURIComponent(t.scene)+'&profileWorkspace='+encodeURIComponent(t.workspace),complete:clear});}catch(_){clear();}
  },
  navigateSection(e){return auth.navigate(this,e.currentTarget.dataset.section,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  openOrders(){this.navigateSection({currentTarget:{dataset:{section:'orders'}}});},
  input(e){const f=e.currentTarget.dataset.field;if(this.hasProfilePhoneConsent()&&(f==='nickname'||f==='contact'))this.setData({[f]:e.detail.value});},
  async save(){
    if(this.data.pending||!this.data.loaded||!this.hasProfilePhoneConsent())return;
    const epoch=this._authEpoch,attempt=this._loginAttempt,session=this.session;
    const saveAttempt=this._saveAttempt=(this._saveAttempt||0)+1;
    const current=()=>!this._dead&&saveAttempt===this._saveAttempt&&attempt===this._loginAttempt&&
      auth.active(epoch)&&this.session===session&&this.hasProfilePhoneConsent();
    this.setData({pending:true,status:'正在保存'});
    try{
      const r=this.validateProfile(await session.commerce(this.scene,'profile_update',{nickname:this.data.nickname,contact:this.data.contact,expected_version:this.data.version}));
      if(!current())return;
      this.setData({version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:'已保存'});
    }catch(e){if(current()){if(e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED')auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'登录已失效，请重新登录');else this.setData({status:customerError(e)});}}
    finally{if(current())this.setData({pending:false});}
  },
  customerSessionRevoked(status='登录已退出，请重新登录',revokeIdentity=true){this._noticeRequest=null;this._loginAttempt=(this._loginAttempt||0)+1;if(revokeIdentity&&this.session)this.session.clear();this.session=null;if(!this._dead){this.clearPrivate(status);this.setData({pending:false});}},
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const s=this.session;const task=s?s.logout():Promise.resolve();
    const revokedEpoch=auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'已退出登录');
    try{await task;}
    catch(e){if(!this._dead&&auth.active(revokedEpoch)&&!this.session)this.setData({pending:false,status:'退出结果未确认，本地会话已清除'});}
  }
});
