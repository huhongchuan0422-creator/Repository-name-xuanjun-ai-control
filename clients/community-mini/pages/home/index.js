const {parseScene,createSession}=require('../../session');
Page({
  data:{scene:'',status:'未连接业务后端',authenticated:false,pending:false},
  onLoad(options){try{this.scene=parseScene(options);this.setData({scene:this.scene});}catch(e){this.setData({status:e.message});return;}this.login();},
  onUnload(){this._dead=true;if(this.session)this.session.clear();},
  async login(){
    if(this.data.pending)return;this.setData({pending:true,status:'正在登录'});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法登录客户中心');
      this.session=createSession(wx,config.baseUrl);
      await this.session.login();
      if(this._dead)return;
      this.setData({authenticated:true,status:'客户身份已验证'});
    }catch(e){if(!this._dead){if(this.session)this.session.clear();this.session=null;this.setData({authenticated:false,status:e.message});}}
    finally{if(!this._dead)this.setData({pending:false});}
  },
  retryLogin(){return this.login();},
  openProfile(){if(!this.data.authenticated||!this.scene){this.setData({status:'请先完成登录'});return;}wx.navigateTo({url:'/pages/profile/index?scene='+encodeURIComponent(this.scene)});},
  openCheckout(){if(!this.scene){this.setData({status:'缺少门店场景'});return;}wx.navigateTo({url:'/pages/checkout/index?scene='+encodeURIComponent(this.scene)});},
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const session=this.session;this.session=null;
    try{if(session)await session.logout();this.setData({authenticated:false,status:'已退出登录'});}
    catch(e){if(session)session.clear();this.setData({authenticated:false,status:'退出结果未确认，本地会话已清除'});}
    finally{if(!this._dead)this.setData({pending:false});}
  }
});
