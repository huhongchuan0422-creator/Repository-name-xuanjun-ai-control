const {parseScene,createSession,customerError}=require('../../session');
const auth=require('../../customer-auth');
Page({
  data:{scene:'',status:'未连接业务后端',authenticated:false,pending:false},
  onLoad(options){this._dead=false;this._authEpoch=auth.current();try{this.scene=parseScene(options&&options.scene?options:{scene:getApp().globalData.scene});getApp().globalData.scene=this.scene;this.setData({scene:this.scene});}catch(e){this.scene=null;this.setData({authenticated:false,status:'缺少门店场景，无法登录客户中心'});return;}this.login();},
  onUnload(){this._dead=true;if(this.session)this.session.clear();},
  async login(){
    if(this.data.pending)return;
    if(!this.scene){this.customerSessionRevoked('缺少门店场景，无法登录客户中心');return;}
    const attempt=this._loginAttempt=(this._loginAttempt||0)+1;const epoch=auth.current();this._authEpoch=epoch;
    this.setData({pending:true,status:'正在登录'});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法登录客户中心');
      this.session=createSession(wx,config.baseUrl);
      await this.session.login();
      if(this._dead||attempt!==this._loginAttempt||!auth.active(epoch)){if(this.session)this.session.clear();return;}
      this.setData({authenticated:true,status:'客户身份已验证'});
    }catch(e){if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch)){if(this.session)this.session.clear();this.session=null;this.setData({authenticated:false,status:customerError(e)});}}
    finally{if(!this._dead&&attempt===this._loginAttempt&&auth.active(epoch))this.setData({pending:false});}
  },
  retryLogin(){return this.login();},
navigateSection(e){const section=e.currentTarget.dataset.section;const scene=this.scene||getApp().globalData.scene;if(!scene){this.setData({status:'缺少门店场景，无法切换页面'});return;}getApp().globalData.scene=scene;const urls={home:'/pages/home/index',recommendations:'/pages/checkout/index?view=recommendations',orders:'/pages/checkout/index?view=orders',profile:'/pages/profile/index'};const url=urls[section];if(url)wx.navigateTo({url:url+(url.includes('?')?'&':'?')+'scene='+encodeURIComponent(scene)});},
  openProfile(){this.navigateSection({currentTarget:{dataset:{section:'profile'}}});},
  openCheckout(){this.navigateSection({currentTarget:{dataset:{section:'orders'}}});},
  openStorefront(){getApp().globalData.checkoutMode='store-detail';wx.switchTab({url:'/pages/checkout/index'});},
  openRecommendations(){this.navigateSection({currentTarget:{dataset:{section:'recommendations'}}});},
  openMerchantJoin(){const s=this.scene||getApp().globalData.scene;if(s)wx.navigateTo({url:'/pages/merchant-join/index?scene='+encodeURIComponent(s)});},
  openMerchant(){const s=this.scene||getApp().globalData.scene;if(s)wx.navigateTo({url:'/pages/merchant/index?scene='+encodeURIComponent(s)});},
  customerSessionRevoked(status='登录已退出，请重新登录'){this._loginAttempt=(this._loginAttempt||0)+1;if(this.session)this.session.clear();this.session=null;if(!this._dead)this.setData({authenticated:false,pending:false,status});},
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const session=this.session;const task=session?session.logout():Promise.resolve();
    const revokedEpoch=auth.revokePages(typeof getCurrentPages==='function'?getCurrentPages():[this],'已退出登录');
    try{await task;}
    catch(e){if(!this._dead&&auth.active(revokedEpoch)&&!this.session)this.setData({pending:false,status:'退出结果未确认，本地会话已清除'});}
  }
});
