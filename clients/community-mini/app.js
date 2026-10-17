App({
  globalData: {baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false},
  // Inject a LOCAL test server and test capability in developer tools memory.
  // No credential storage. Real payment requires explicit server and UI opt-in.
  configureOffline(baseUrl, token) {
    if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(baseUrl) ||
        typeof token !== 'string' || token.length < 32) throw Error('LOCAL_CONFIG_REQUIRED');
    this.globalData = {baseUrl, token, mode: 'OFFLINE'};
  },
  configureService(baseUrl, payments=false, commerce=false) {
    if (!/^https:\/\/[A-Za-z0-9.-]+$/.test(baseUrl)) throw Error('HTTPS_BACKEND_REQUIRED');
    if(typeof payments!=='boolean'||typeof commerce!=='boolean')throw Error('INVALID_PAYMENT_CONFIGURATION');
    this.globalData = {baseUrl, token: '', mode: 'WECHAT_LOGIN', payments, commerce};
  }
});
