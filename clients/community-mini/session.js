'use strict';
function parseScene(options) {
  if (!options || typeof options.scene !== 'string') throw Error('SCENE_REQUIRED');
  let scene;
  try { scene=decodeURIComponent(options.scene); } catch (_) {throw Error('INVALID_SCENE');}
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(scene))throw Error('INVALID_SCENE');
  return scene;
}
function createSession(wx, baseUrl, now=()=>Math.floor(Date.now()/1000)) {
  if (!/^https:\/\/[A-Za-z0-9.-]+(?::443)?$/.test(baseUrl) &&
      !/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(baseUrl))throw Error('TRUSTED_BACKEND_REQUIRED');
  let token=null,expires=0,generation=0;
  const request=(path,data,credential)=>new Promise((resolve,reject)=>{
    wx.request({url:baseUrl+path,method:'POST',data,timeout:5000,
      header:{'content-type':'application/json',...(credential?{'X-Community-Session':credential}:{})},
      success:r=>r.statusCode===200?resolve(r.data):reject(Error('SERVICE_REQUEST_REJECTED')),
      fail:()=>reject(Error('SERVICE_RESULT_UNKNOWN'))});
  });
  return {
    async login() {
      const version=++generation;token=null;expires=0;
      const code=await new Promise((resolve,reject)=>wx.login({timeout:5000,
        success:r=>r&&typeof r.code==='string'&&r.code?resolve(r.code):reject(Error('LOGIN_CODE_REQUIRED')),
        fail:()=>reject(Error('WECHAT_LOGIN_FAILED'))}));
      if(version!==generation)throw Error('STALE_LOGIN');
      const reply=await request('/mini/login',{code});
      if(version!==generation)throw Error('STALE_LOGIN');
      const s=reply&&reply.result;
      if(reply.payment_enabled!==false||!s||s.provider!=='WECHAT_MINIPROGRAM'||s.payment_enabled!==false||
         typeof s.session_token!=='string'||!/^[A-Za-z0-9_-]{32,256}$/.test(s.session_token)||
         !Number.isSafeInteger(s.expires_at)||s.expires_at<=now()||s.expires_at>now()+86400||
         Object.keys(s).some(k=>!['session_token','expires_at','provider','payment_enabled'].includes(k)))
        throw Error('UNTRUSTED_SESSION');
      token=s.session_token;expires=s.expires_at;
      return {authenticated:true,payment_enabled:false};
    },
    async transport(scene, body) {
      if(!token||now()>=expires)throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene))throw Error('INVALID_SCENE');
      const version=generation;
      const reply=await request('/mini/api',{scene,operation:body.operation,params:body.params},token);
      if(version!==generation)throw Error('STALE_SESSION');
      if(reply.payment_enabled!==false||!reply.result)throw Error('UNTRUSTED_BUSINESS_REPLY');
      // Business remains explicitly simulated even when WeChat login is real.
      return {offline_only:true,result:reply.result};
    },
    async logout() {
      const old=token;generation++;token=null;expires=0;
      if(old)await request('/mini/logout',{},old);
    },
    clear() {generation++;token=null;expires=0;}
  };
}
module.exports={parseScene,createSession};
