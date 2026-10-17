const {makeClient} = require('../../client');
const {parseScene,createSession} = require('../../session');
Page({
  data: {amount:'', reference:'', merchant:'', beforeAd:'', afterAd:'', status:'本地模拟；未连接微信支付', pending:false},
  async onLoad(options) {
    try {
      const config = getApp().globalData;
      if (config.mode !== 'OFFLINE') {
        const scene = parseScene(options);
        this.session = createSession(wx,config.baseUrl);
        await this.session.login();
        this.client = makeClient(body => this.session.transport(scene,body));
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
  onUnload() {if(this.client)this.client.reset();if(this.session)this.session.clear();},
  inputAmount(e) {if(this.client)this.client.reset();this.setData({amount:e.detail.value,afterAd:''});},
  inputReference(e) {if(this.client)this.client.reset();this.setData({reference:e.detail.value,afterAd:''});},
  async checkout() {
    if (this.data.pending) return;
    if (!this.client) return this.setData({status:'请先完成登录与门店绑定'});
    this.setData({pending:true,afterAd:'',status:'正在创建模拟订单'});
    try {await this.client.checkout(this.data.amount,this.data.reference);this.setData({status:'模拟待支付；不发起微信扣款'});}
    catch(e) {this.setData({status:e.message});}
    finally {this.setData({pending:false});}
  },
  async refresh() {
    if (!this.client) return this.setData({status:'请先完成登录与门店绑定'});
    this.setData({afterAd:''});
    try {const r=await this.client.resume(this.data.reference);this.setData({amount:String(r.order.amount_minor),status:r.payment_state+'（模拟，非收款凭证）',
      afterAd:r.ads.AD_SLOT_PAYMENT_SUCCESS ? r.ads.AD_SLOT_PAYMENT_SUCCESS.title : ''});}
    catch(e) {this.setData({status:e.message});}
  }
});
