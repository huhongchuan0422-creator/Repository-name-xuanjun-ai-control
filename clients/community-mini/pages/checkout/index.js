const {makeClient} = require('../../client');
Page({
  data: {amount:'', reference:'', merchant:'', beforeAd:'', afterAd:'', status:'本地模拟；未连接微信支付', pending:false},
  onLoad() {
    this.client = makeClient(body => new Promise((resolve,reject) => {
      const {baseUrl,token} = getApp().globalData;
      if (!baseUrl || !token) return reject(Error('请先配置本地开发服务'));
      wx.request({url:baseUrl+'/offline/saas', method:'POST', data:body,
        header:{'content-type':'application/json','X-Offline-Token':token}, timeout:5000,
        success:r=>r.statusCode===200?resolve(r.data):reject(Error('请求被拒绝')),
        fail:reject});
    }));
    this.client.storefront().then(s=>this.setData({merchant:s.merchant.name,
      beforeAd:s.ads.AD_SLOT_PAYMENT_AMOUNT ? s.ads.AD_SLOT_PAYMENT_AMOUNT.title : ''}))
      .catch(e=>this.setData({status:e.message}));
  },
  onUnload() {this.client.reset();},
  inputAmount(e) {this.client.reset();this.setData({amount:e.detail.value,afterAd:''});},
  inputReference(e) {this.client.reset();this.setData({reference:e.detail.value,afterAd:''});},
  async checkout() {
    if (this.data.pending) return;
    this.setData({pending:true,afterAd:'',status:'正在创建模拟订单'});
    try {await this.client.checkout(this.data.amount,this.data.reference);this.setData({status:'模拟待支付；不发起微信扣款'});}
    catch(e) {this.setData({status:e.message});}
    finally {this.setData({pending:false});}
  },
  async refresh() {
    this.setData({afterAd:''});
    try {const r=await this.client.receipt();this.setData({status:r.payment_state+'（模拟，非收款凭证）',
      afterAd:r.ads.AD_SLOT_PAYMENT_SUCCESS ? r.ads.AD_SLOT_PAYMENT_SUCCESS.title : ''});}
    catch(e) {this.setData({status:e.message});}
  }
});
