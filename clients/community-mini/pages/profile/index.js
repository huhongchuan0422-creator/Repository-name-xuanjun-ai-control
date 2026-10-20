const {parseScene,createSession}=require('../../session');
Page({
  data:{status:'未连接业务后端',authenticated:false,pending:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:''},
  onLoad(options){try{this.scene=parseScene(options);}catch(e){this.setData({status:e.message});return;}this.loginAndLoad();},
  onUnload(){this._dead=true;if(this.session)this.session.clear();},
  async loginAndLoad(){
    if(this.data.pending)return;this.setData({pending:true,status:'正在登录',authenticated:false,loaded:false});
    try{
      const config=getApp().globalData;
      if(!config.baseUrl)throw Error('未配置业务后端，无法读取本人资料');
      this.session=createSession(wx,config.baseUrl);
      await this.session.login();
      if(this._dead)return;
      this.setData({authenticated:true});
      await this.loadProfile();
    }catch(e){if(!this._dead){if(this.session)this.session.clear();this.session=null;this.clearPrivate(e.message);}}
    finally{if(!this._dead)this.setData({pending:false});}
  },
  clearPrivate(status){this.setData({authenticated:false,loaded:false,version:null,nickname:'',contact:'',userId:'',customerId:'',status});},
  validateProfile(r){
    if(!r||typeof r.user_id!=='string'||typeof r.project_customer_id!=='string'||typeof r.nickname!=='string'||typeof r.contact!=='string'||!Number.isSafeInteger(r.version)||r.version<0)throw Error('本人资料返回无效');
    return r;
  },
  async loadProfile(){
    if(!this.session||!this.scene)throw Error('SESSION_EXPIRED');
    const r=this.validateProfile(await this.session.commerce(this.scene,'profile_read',{}));
    if(this._dead)return;
    this.setData({loaded:true,version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:'本人资料已读取'});
  },
  retryLogin(){return this.loginAndLoad();},
  input(e){const f=e.currentTarget.dataset.field;if(f==='nickname'||f==='contact')this.setData({[f]:e.detail.value});},
  async save(){
    if(this.data.pending||!this.data.authenticated||!this.data.loaded||!this.session)return;
    this.setData({pending:true,status:'正在保存'});
    try{
      const r=this.validateProfile(await this.session.commerce(this.scene,'profile_update',{nickname:this.data.nickname,contact:this.data.contact,expected_version:this.data.version}));
      if(this._dead)return;
      this.setData({version:r.version,nickname:r.nickname,contact:r.contact,userId:r.user_id,customerId:r.project_customer_id,status:'本人资料已保存'});
    }catch(e){if(!this._dead){if(e.code==='ACCESS_DENIED'||e.message==='SESSION_EXPIRED'){if(this.session)this.session.clear();this.session=null;this.clearPrivate('登录已失效，请重新登录');}else this.setData({status:e.message});}}
    finally{if(!this._dead)this.setData({pending:false});}
  },
  async logout(){
    if(this.data.pending)return;this.setData({pending:true});
    const s=this.session;this.session=null;
    try{if(s)await s.logout();this.clearPrivate('已退出登录');}
    catch(e){if(s)s.clear();this.clearPrivate('退出结果未确认，本地会话已清除');}
    finally{if(!this._dead)this.setData({pending:false});}
  }
});
