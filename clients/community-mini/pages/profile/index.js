const {parseScene,createSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
Page({
  data:{status:'未连接业务后端',authenticated:false,pending:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:''},
  onShow(){const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this._sceneStale){this._sceneStale=true;this.customerSessionRevoked('授权场景已切换，当前客户资料已清除，请重新进入对应门店');}},
  onLoad(options){this._dead=false;this._sceneStale=false;this._authEpoch=auth.current();try{this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});}catch(e){this.scene=null;this.clearPrivate('缺少门店场景，无法读取本人资料');return;}this.loginAndLoad();},
  onUnload(){this._dead=true;if(this.session)this.session.clear();},
  async loginAndLoad(){
    if(this.data.pending)return;
    if(!this.scene){this.customerSessionRevoked('缺少门店场景，无法读取本人资料');return;}
    const attempt=this._loginAttempt=(this._loginAttempt||0)+1;const epoch=auth.current();this._authEpoch=epoch;
    this.setData({pending:true,status:'正在登录',authenticated:false,loaded:false});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法读取本人资料');
      this.session=createSession(wx,config.baseUrl);
      await this.session.login();
      if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch)){if(this.session)this.session.clear();return;}
      this.setData({authenticated:true});
      await this.loadProfile(epoch,attempt);
    }catch(e){if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch)){if(e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED')auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'登录已失效，请重新登录');else{if(this.session)this.session.clear();this.session=null;this.clearPrivate(customerError(e));}}}
    finally{if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.setData({pending:false});}
  },
  clearPrivate(status){this.setData({authenticated:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:'',status});},
  validateProfile(r){
    if(!r||typeof r.user_id!=='string'||typeof r.project_customer_id!=='string'||typeof r.nickname!=='string'||typeof r.contact!=='string'||!Number.isSafeInteger(r.version)||r.version<0)throw Error('本人资料返回无效');
    return r;
  },
  async loadProfile(epoch=this._authEpoch,attempt=this._loginAttempt){
    if(!this.session||!this.scene)throw Error('SESSION_EXPIRED');
    const r=this.validateProfile(await this.session.commerce(this.scene,'profile_read',{}));
    if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch))return;
    this.setData({loaded:true,version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:'本人资料已读取'});
  },
  retryLogin(){return this.loginAndLoad();},
  openJoin(){const s=this.scene||getApp().globalData.scene;if(s)wx.navigateTo({url:'/pages/merchant-join/index?scene='+encodeURIComponent(s)});},
  openMerchant(){const s=this.scene||getApp().globalData.scene;if(s)wx.navigateTo({url:'/pages/merchant/index?scene='+encodeURIComponent(s)});},
navigateSection(e){if(this._sceneStale){this.setData({status:'授权场景已切换，请从对应门店重新进入'});return;}const section=e.currentTarget.dataset.section;const scene=this.scene||getApp().globalData.scene;if(!scene){this.setData({status:'缺少门店场景，无法切换页面'});return;}getApp().globalData.scene=scene;const urls={home:'/pages/home/index',recommendations:'/pages/checkout/index?view=recommendations',orders:'/pages/checkout/index?view=orders',profile:'/pages/profile/index'};const url=urls[section];if(url)wx.navigateTo({url:url+(url.includes('?')?'&':'?')+'scene='+encodeURIComponent(scene)});},
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
  customerSessionRevoked(status='登录已退出，请重新登录'){this._loginAttempt=(this._loginAttempt||0)+1;if(this.session)this.session.clear();this.session=null;if(!this._dead){this.clearPrivate(status);this.setData({pending:false});}},
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const s=this.session;const task=s?s.logout():Promise.resolve();
    const revokedEpoch=auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'已退出登录');
    try{await task;}
    catch(e){if(!this._dead&&auth.active(revokedEpoch)&&!this.session)this.setData({pending:false,status:'退出结果未确认，本地会话已清除'});}
  }
});
