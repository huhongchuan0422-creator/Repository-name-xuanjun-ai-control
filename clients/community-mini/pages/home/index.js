const {parseScene,getSharedSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
Page({
  scanStore(){return auth.scanStore(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goBack(){return auth.back(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  data:{scene:'',status:'未连接业务后端',authenticated:false,pending:false,activeSection:'home',needsScene:true,privacyStatus:''},
  async onShow(){const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this._sceneStale){this._sceneStale=true;this.customerSessionRevoked('授权场景已切换，当前客户资料已清除，请重新进入对应门店',false);}if(this.session&&typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated()&&!this.data.pending&&!this.sceneInvalid&&!this._sceneStale&&!this.sceneStale){await this.login({automatic:true});}},
  async onLoad(options){this._dead=false;this._sceneStale=false;this._authEpoch=auth.current();try{this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});getApp().globalData.scene=this.scene;this.setData({scene:this.scene,needsScene:false});}catch(e){this.scene=null;this.sceneInvalid=!!(options&&options.scene);this.setData({authenticated:false,needsScene:true,status:'未选择门店。可浏览公共页面、微信登录或直接办理商家入驻。'});if(!this.sceneInvalid&&getApp().globalData.baseUrl)await this.login({automatic:true});return;}await this.login({automatic:true});},
  onUnload(){this._dead=true;if(this.session&&this.session.detachPage)this.session.detachPage(this);this.session=null;},
  async login(options={}){
    if(this.data.pending)return;
    if(this.sceneInvalid){this.setData({status:'门店入口无效，请返回首页或重新扫描有效门店码'});return;}
    let attempt=this._loginAttempt=(this._loginAttempt||0)+1;let epoch=auth.current();this._authEpoch=epoch;
    this.setData({pending:true,status:'正在登录'});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法登录客户中心');
      this.session=getSharedSession(wx,config,undefined,this);
      epoch=this._authEpoch=auth.current();attempt=this._loginAttempt=(this._loginAttempt||0)+1;this.setData({pending:true});
      await this.session.ensureLogin({automatic:options.automatic===true,prepared:true});
      if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch)){return;}
      this.setData({authenticated:true,status:this.scene?'客户身份已验证':'微信身份已验证，可办理本人商家入驻；尚未关联门店'});
    }catch(e){if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch)){this.session=null;this.setData({authenticated:false,status:customerError(e)});}}
    finally{if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.setData({pending:false});}
  },
  retryLogin(){return this.login();},
  openPrivacy(){
    if(this._dead)return;
    const fail=()=>{if(!this._dead)this.setData({privacyStatus:'暂时无法打开隐私保护指引，请稍后重试或联系项目负责人'});};
    if(typeof wx.openPrivacyContract!=='function'){fail();return;}
    this.setData({privacyStatus:''});
    try{wx.openPrivacyContract({fail});}catch(_){fail();}
  },
  navigateSection(e){return auth.navigate(this,e.currentTarget.dataset.section,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  openProfile(){this.navigateSection({currentTarget:{dataset:{section:'profile'}}});},
  openCheckout(){this.navigateSection({currentTarget:{dataset:{section:'orders'}}});},
  openStorefront(){this.navigateSection({currentTarget:{dataset:{section:'store-detail'}}});},
  openRecommendations(){this.navigateSection({currentTarget:{dataset:{section:'recommendations'}}});},
  openMerchantJoin(){return auth.navigate(this,'join',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  openMerchant(){return auth.navigate(this,'merchant',wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  customerSessionRevoked(status='登录已退出，请重新登录',revokeIdentity=true){this._loginAttempt=(this._loginAttempt||0)+1;if(revokeIdentity&&this.session)this.session.clear();this.session=null;if(!this._dead)this.setData({authenticated:false,pending:false,status});},
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const session=this.session;const task=session?session.logout():Promise.resolve();
    const revokedEpoch=auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'已退出登录');
    try{await task;}
    catch(e){if(!this._dead&&auth.active(revokedEpoch)&&!this.session)this.setData({pending:false,status:'退出结果未确认，本地会话已清除'});}
  }
});
