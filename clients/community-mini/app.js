App({
  globalData: {baseUrl: '', token: ''},
  // Inject a LOCAL test server and test capability in developer tools memory.
  // No storage of credentials, wx.login claims, requestPayment or live order API.
  configureOffline(baseUrl, token) {
    if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(baseUrl) ||
        typeof token !== 'string' || token.length < 32) throw Error('LOCAL_CONFIG_REQUIRED');
    this.globalData = {baseUrl, token};
  }
});
