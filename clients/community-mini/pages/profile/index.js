const {parseScene,getSharedSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
Page({
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

  showProfile(){this.setData({pageMode:'profile-edit'});},
  showNotices(){if(this.data.authenticated&&this.data.loaded){this.setData({pageMode:'notices'});}else{this.setData({status:'选择门店并验证本人身份后读取通知；未读取其他门店或他人的记录'});this.showProfile();}},
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
  data:{pageMode:'profile',privacyStatus:'',merchantEntry:'unknown',merchantEntryPending:false,merchantEntryLabel:'商家入驻',merchantEntryHint:'登录后核实本人入驻状态',status:'未连接业务后端',authenticated:false,pending:false,loaded:false,activeSection:'profile',needsScene:true,version:null,nickname:'',contact:'',userId:'',customerId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',selectedNotice:null,noticeDetailOpen:false},
  async onShow(){const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this._sceneStale){this._sceneStale=true;this.customerSessionRevoked('授权场景已切换，当前客户资料已清除，请重新进入对应门店',false);}if(this.session&&typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated()&&!this.data.pending&&!this.sceneInvalid&&!this._sceneStale&&!this.sceneStale){await this.loginAndLoad({automatic:true});}if(this.data.authenticated&&!this.data.merchantEntryPending&&!this._sceneStale)this.loadMerchantEntry();},
  async onLoad(options){this._dead=false;this._sceneStale=false;this._authEpoch=auth.current();try{this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});}catch(e){this.scene=null;this.sceneInvalid=!!(options&&options.scene);this.clearPrivate('登录后可办理本人商家入驻。选择门店后再读取该门店下的个人资料。');this.setData({needsScene:true});if(!this.sceneInvalid&&getApp().globalData.baseUrl)await this.loginAndLoad({automatic:true});return;}this.setData({needsScene:false});await this.loginAndLoad({automatic:true});},
  onUnload(){this._dead=true;this._noticeRequest=null;if(this.session&&this.session.detachPage)this.session.detachPage(this);this.session=null;},
  async loginAndLoad(options={}){
    if(this.data.pending)return;
    if(this.sceneInvalid){this.setData({status:'门店入口无效，请返回首页或重新扫描有效门店码'});return;}
    let attempt=this._loginAttempt=(this._loginAttempt||0)+1;let epoch=auth.current();this._authEpoch=epoch;
    this._merchantRequest=null;this.setData({pending:true,status:'正在登录',authenticated:false,loaded:false,merchantEntry:'unknown',merchantEntryPending:false,merchantEntryLabel:'商家入驻',merchantEntryHint:'正在核实本人商家资格'});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法读取本人资料');
      this.session=getSharedSession(wx,config,undefined,this);
      epoch=this._authEpoch=auth.current();attempt=this._loginAttempt=(this._loginAttempt||0)+1;this.setData({pending:true});
      await this.session.ensureLogin({automatic:options.automatic===true,prepared:true});
      if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch)){return;}
      this.setData({authenticated:true});
      if(this.scene)await this.loadProfile(epoch,attempt);
      else this.setData({status:'微信身份已验证，可办理本人商家入驻；未读取任何门店资料'});
      if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.loadMerchantEntry(epoch,attempt);
    }catch(e){if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch)){if(e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED')auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'登录已失效，请重新登录');else{this.session=null;this.clearPrivate(customerError(e));}}}
    finally{if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.setData({pending:false});}
  },
  clearPrivate(status){this._reviewerRequest=null;this.setData({reviewerDescription:null,reviewerChallenge:'',reviewerStatus:'',reviewerPending:false});this._merchantRequest=null;this._noticeRequest=null;this.setData({pageMode:'profile',merchantEntry:'unknown',merchantEntryPending:false,merchantEntryLabel:'商家入驻',merchantEntryHint:'登录后核实本人入驻状态',authenticated:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',selectedNotice:null,noticeDetailOpen:false,status});},
  async loadMerchantEntry(epoch=this._authEpoch,attempt=this._loginAttempt){
    if(!this.session||!this.data.authenticated)return;
    const request={session:this.session,scene:this.scene||'',epoch,attempt};this._merchantRequest=request;
    // Empty-scene sessions are valid for onboarding, never a fabricated workspace.
    const valid=()=>!this._dead&&!this._sceneStale&&this._merchantRequest===request&&this.session===request.session&&(this.scene||'')===request.scene&&auth.active(epoch)&&attempt===this._loginAttempt;
    this.setData({merchantEntry:'unknown',merchantEntryPending:true,merchantEntryLabel:'商家入驻',merchantEntryHint:'正在核实本人商家资格'});
    try{
      if(request.scene){
        const workspace=await request.session.merchant(request.scene,'workspaces',{});
        if(!valid())return;
        if(!workspace||!Array.isArray(workspace.workspaces)||workspace.workspaces.some(x=>typeof x!=='string'||!x))throw Error('商家授权返回未确认');
        if(workspace.workspaces.length){this.setData({merchantEntry:'ready',merchantEntryLabel:'商家工作台',merchantEntryHint:'管理已授权门店的日常经营'});return;}
      }
      const result=await request.session.merchant(request.scene,'onboarding',{operation:'mine',params:{}});
      if(!valid())return;
      if(!result||!Array.isArray(result.applications)||result.applications.some(a=>!a||typeof a.application!=='string'||typeof a.status!=='string'))throw Error('入驻申请返回未确认');
      this.setData(result.applications.length?{merchantEntry:'progress',merchantEntryLabel:'入驻进度',merchantEntryHint:'查看原申请、审核意见与开通状态'}:{merchantEntry:'none',merchantEntryLabel:'申请入驻',merchantEntryHint:'开始办理商家入驻'});
    }catch(e){if(valid())this.setData({merchantEntry:'unknown',merchantEntryLabel:'商家入驻',merchantEntryHint:'入驻状态暂未确认，请重试；未开放工作台'});}
    finally{if(valid()){this._merchantRequest=null;this.setData({merchantEntryPending:false});}}
  },
  openMerchantEntry(){if(this.data.merchantEntryPending)return;return this.data.authenticated&&!this.data.pending&&this.data.merchantEntry==='ready'?this.openMerchant():this.openJoin();},
  validateProfile(r){
    if(!r||typeof r.user_id!=='string'||typeof r.project_customer_id!=='string'||typeof r.nickname!=='string'||typeof r.contact!=='string'||!Number.isSafeInteger(r.version)||r.version<0)throw Error('本人资料返回无效');
    return r;
  },
  async loadProfile(epoch=this._authEpoch,attempt=this._loginAttempt){
    if(!this.session||!this.scene)throw Error('SESSION_EXPIRED');
    const r=this.validateProfile(await this.session.commerce(this.scene,'profile_read',{}));
    if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch))return;
    this.setData({loaded:true,version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:'本人资料已读取'});
    this.loadNotices(null,epoch,attempt,false);
  },
  noticeCurrent(request){return !this._dead&&request===this._noticeRequest&&request.attempt===this._loginAttempt&&request.epoch===this._authEpoch&&auth.active(request.epoch)&&this.data.authenticated&&this.session===request.session&&this.scene===request.scene;},
  async loadNotices(e,epoch=this._authEpoch,attempt=this._loginAttempt,more=!!(e&&e.currentTarget&&e.currentTarget.dataset.more==='true')){
    if(this._dead||!this.data.authenticated||!this.data.loaded||!this.session||!this.scene||this.data.noticePending)return;
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
  openMerchant(){return auth.navigate(this,'merchant',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  navigateSection(e){return auth.navigate(this,e.currentTarget.dataset.section,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  openOrders(){this.navigateSection({currentTarget:{dataset:{section:'orders'}}});},
  input(e){const f=e.currentTarget.dataset.field;if(f==='nickname'||f==='contact')this.setData({[f]:e.detail.value});},
  async save(){
    if(this.data.pending||!this.data.authenticated||!this.data.loaded||!this.session)return;
    const epoch=this._authEpoch,attempt=this._loginAttempt,session=this.session;
    const saveAttempt=this._saveAttempt=(this._saveAttempt||0)+1;
    const current=()=>!this._dead&&saveAttempt===this._saveAttempt&&attempt===this._loginAttempt&&
      auth.active(epoch)&&this.session===session;
    this.setData({pending:true,status:'正在保存'});
    try{
      const r=this.validateProfile(await session.commerce(this.scene,'profile_update',{nickname:this.data.nickname,contact:this.data.contact,expected_version:this.data.version}));
      if(!current())return;
      this.setData({version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:'本人资料已保存'});
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
