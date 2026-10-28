const {parseScene,createSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
Page({
  scanStore(){return auth.scanStore(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goBack(){return auth.back(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  data:{status:'未连接业务后端',authenticated:false,pending:false,loaded:false,activeSection:'profile',needsScene:true,version:null,nickname:'',contact:'',userId:'',customerId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',selectedNotice:null,noticeDetailOpen:false},
  onShow(){const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this._sceneStale){this._sceneStale=true;this.customerSessionRevoked('授权场景已切换，当前客户资料已清除，请重新进入对应门店');}},
  onLoad(options){this._dead=false;this._sceneStale=false;this._authEpoch=auth.current();try{this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});}catch(e){this.scene=null;this.sceneInvalid=!!(options&&options.scene);this.clearPrivate('登录后可办理本人商家入驻。选择门店后再读取该门店下的个人资料。');this.setData({needsScene:true});return;}this.setData({needsScene:false});this.loginAndLoad();},
  onUnload(){this._dead=true;this._noticeRequest=null;if(this.session)this.session.clear();},
  async loginAndLoad(){
    if(this.data.pending)return;
    if(this.sceneInvalid){this.setData({status:'门店入口无效，请返回首页或重新扫描有效门店码'});return;}
    const attempt=this._loginAttempt=(this._loginAttempt||0)+1;const epoch=auth.current();this._authEpoch=epoch;
    this.setData({pending:true,status:'正在登录',authenticated:false,loaded:false});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法读取本人资料');
      this.session=createSession(wx,config.baseUrl);
      await this.session.login();
      if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch)){if(this.session)this.session.clear();return;}
      this.setData({authenticated:true});
      if(this.scene)await this.loadProfile(epoch,attempt);
      else this.setData({status:'微信身份已验证，可办理本人商家入驻；未读取任何门店资料'});
    }catch(e){if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch)){if(e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED')auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'登录已失效，请重新登录');else{if(this.session)this.session.clear();this.session=null;this.clearPrivate(customerError(e));}}}
    finally{if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.setData({pending:false});}
  },
  clearPrivate(status){this._noticeRequest=null;this.setData({authenticated:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:'',notices:[],noticeCursor:null,noticesMore:false,noticesLoaded:false,noticePending:false,noticeStatus:'',selectedNotice:null,noticeDetailOpen:false,status});},
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
  customerSessionRevoked(status='登录已退出，请重新登录'){this._noticeRequest=null;this._loginAttempt=(this._loginAttempt||0)+1;if(this.session)this.session.clear();this.session=null;if(!this._dead){this.clearPrivate(status);this.setData({pending:false});}},
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const s=this.session;const task=s?s.logout():Promise.resolve();
    const revokedEpoch=auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'已退出登录');
    try{await task;}
    catch(e){if(!this._dead&&auth.active(revokedEpoch)&&!this.session)this.setData({pending:false,status:'退出结果未确认，本地会话已清除'});}
  }
});
