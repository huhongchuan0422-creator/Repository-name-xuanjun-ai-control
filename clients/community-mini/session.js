'use strict';
function customerError(error) {
  const code=error&&error.message;
  if(error&&error.networkKind==='DOMAIN')return '小程序服务域名校验未通过（NET_DOMAIN），请联系项目负责人';
  if(error&&error.networkKind==='TLS')return '安全连接未建立（NET_TLS），请联系项目负责人';
  if(error&&error.networkKind==='TIMEOUT')return '登录连接超时（NET_TIMEOUT），请点击重新登录；不会自动重复请求';
  if(error&&error.code==='ACCESS_DENIED')return '当前账号暂无访问权限，请联系项目负责人确认';
  if(code==='SERVICE_RESULT_UNKNOWN')return '暂时无法连接服务，请检查网络后重试；若仍失败，请联系项目负责人';
  if(code==='SERVICE_UNAVAILABLE')return '服务暂不可用，请稍后重试';
  if(code==='SERVICE_REQUEST_REJECTED')return '请求未能完成，请稍后重试';
  if(code==='WECHAT_LOGIN_FAILED'||code==='LOGIN_CODE_REQUIRED')return '微信登录未完成，请点击重新登录';
  if(code==='SESSION_EXPIRED')return '登录已失效，请重新登录';
  if(code==='UNTRUSTED_SESSION')return '登录结果未通过验证，请联系项目负责人';
  if(typeof code==='string'&&/^未配置业务后端/.test(code))return '当前服务尚未接通，请联系项目负责人';
  return '操作未能完成，请稍后重试';
}
function parseScene(options) {
  if (!options || typeof options.scene !== 'string') throw Error('SCENE_REQUIRED');
  let scene;
  try { scene=decodeURIComponent(options.scene); } catch (_) {throw Error('INVALID_SCENE');}
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(scene))throw Error('INVALID_SCENE');
  return scene;
}
function createSession(wx, baseUrl, now=()=>Math.floor(Date.now()/1000)) {
  if (!/^https:\/\/[A-Za-z0-9.-]+(?::443)?$/.test(baseUrl) &&
      !/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(baseUrl) &&
      baseUrl!=='https://uk.wenwenwenyiyiyi.work/community-preview')throw Error('TRUSTED_BACKEND_REQUIRED');
  let token=null,expires=0,generation=0;
  const request=(path,data,credential,scene)=>new Promise((resolve,reject)=>{
    wx.request({url:baseUrl+path,method:'POST',data,timeout:path==='/mini/login'||path==='/mini/merchant'&&data.operation==='collection_code'?15000:5000,
      header:{'content-type':'application/json',...(credential?{'X-Community-Session':credential}:{}),...(scene?{'X-Community-Scene':scene}:{})},
      success:r=>{
        if(r.statusCode===200){resolve(r.data);return;}
        const error=Error('SERVICE_REQUEST_REJECTED');
        // Keep definite access refusal distinct from transport uncertainty. Never expose its body.
        if(r.statusCode===401||r.statusCode===403)error.code='ACCESS_DENIED';
        if(path==='/mini/merchant'&&data.operation==='ocr'&&['OCR_SOURCE_CHANGED','OCR_AUTH_DENIED','OCR_UNAVAILABLE'].includes(r.data&&r.data.error))error.ocrCode=r.data.error;
        reject(error);
      },
      fail:detail=>{
        const error=Error('SERVICE_RESULT_UNKNOWN');
        // Classify locally; never retain or display raw platform error text or URLs.
        const message=detail&&typeof detail.errMsg==='string'?detail.errMsg.toLowerCase():'';
        if(/not in domain list|url not in domain|合法域名/.test(message))error.networkKind='DOMAIN';
        else if(/ssl|tls|certificate|cert authority/.test(message))error.networkKind='TLS';
        else if(/timeout|timed out/.test(message))error.networkKind='TIMEOUT';
        reject(error);
      }});
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
    async commerce(scene, operation, params) {
      if(!token||now()>=expires)throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)||!['communities','community_mine','community_join','community_leave','promotion_redeem','profile_read','profile_update','referral_code','referral_bind','notices','notice_read','orders','products','purchase','purchase_read','purchase_recover','receipt_ad','project_summary','project_checklist','project_feedback','project_messages','project_save_reference','project_submit','refund_apply','refund_application','refund_current'].includes(operation))throw Error('INVALID_COMMERCE_REQUEST');
      const version=generation;
      const reply=await request('/mini/api',{scene,operation:'commerce.'+operation,params},token);
      if(version!==generation)throw Error('STALE_SESSION');
      if(!reply||!reply.result||reply.payment_enabled!==false)throw Error('UNTRUSTED_COMMERCE_REPLY');
      return reply.result;
    },
    async merchant(scene, operation, params) {
      if(!token||now()>=expires)throw Error('SESSION_EXPIRED');
      const applicantOcr=scene===''&&operation==='ocr'&&params&&['submit','read','confirm','delete'].includes(params.action);
      const applicantOnly=applicantOcr||scene===''&&operation==='onboarding'&&params&&
        ['catalog','mine','read','save','upload','remove_material','submit','withdraw','history','notices','notice_read','wechat_read','wechat_save','wechat_submit_review','wechat_media','wechat_cashier_link'].includes(params.operation);
      if((!applicantOnly&&(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)))||
         !['workspaces','onboarding','read','write','collection_code','ocr'].includes(operation)||!params||typeof params!=='object'||Array.isArray(params))throw Error('INVALID_MERCHANT_REQUEST');
      const version=generation;
      const reply=await request('/mini/merchant',{operation,params},token,scene);
      if(version!==generation)throw Error('STALE_SESSION');
      if(!reply||reply.payment_enabled!==false||!reply.result)throw Error('UNTRUSTED_MERCHANT_REPLY');
      return reply.result;
    },
    getGeneration() {return generation;},
    async projectDocument(scene, params, expectedGeneration=generation) {
      if(expectedGeneration!==generation)throw Error('STALE_SESSION');
      if(!token||now()>=expires)throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)||
         !params||Object.keys(params).sort().join(',')!=='content_base64,filename,item,revision'||
         typeof params.item!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(params.item)||
         !Number.isSafeInteger(params.revision)||params.revision<0||
         typeof params.filename!=='string'||params.filename.length<1||params.filename.length>180||
         params.filename.trim()!==params.filename||/[\\/:\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/.test(params.filename)||
         !/\.(pdf|png|jpe?g)$/i.test(params.filename))throw Error('INVALID_PROJECT_DOCUMENT');
      const content=params.content_base64;
      if(typeof content!=='string'||!content.length||content.length>6666668||content.length%4!==0||
         !/^[A-Za-z0-9+/]+={0,2}$/.test(content))throw Error('INVALID_PROJECT_DOCUMENT');
      const padding=content.endsWith('==')?2:content.endsWith('=')?1:0;
      const size=content.length/4*3-padding;
      const last='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'.indexOf(content[content.length-padding-1]);
      if(size<1||size>5000000||(padding===2&&(last&15)!==0)||(padding===1&&(last&3)!==0))throw Error('INVALID_PROJECT_DOCUMENT');
      // File names alone do not establish type; the server still owns scanning and final validation.
      let magic='',bits=0,value=0;
      const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
      for(const character of content.slice(0,12)){
        if(character==='=')break;
        value=(value<<6)|alphabet.indexOf(character);bits+=6;
        if(bits>=8){bits-=8;magic+=String.fromCharCode((value>>bits)&255);}
      }
      const extension=magic.startsWith('%PDF-')?/\.pdf$/i:
        magic.startsWith('\x89PNG\r\n\x1a\n')?/\.png$/i:magic.startsWith('\xff\xd8\xff')?/\.jpe?g$/i:null;
      if(!extension||!extension.test(params.filename))throw Error('INVALID_PROJECT_DOCUMENT');
      const version=generation;
      const reply=await request('/mini/project-materials',params,token,scene);
      if(version!==generation)throw Error('STALE_SESSION');
      const result=reply&&reply.result;
      if(!reply||reply.payment_enabled!==false||!result||
         Object.keys(result).sort().join(',')!=='revision,state,version'||
         typeof result.version!=='string'||!/^v_[0-9a-f]{32}$/.test(result.version)||
         !Number.isSafeInteger(result.revision)||result.revision!==params.revision+1||
         result.state!=='PARTIAL')throw Error('UNTRUSTED_PROJECT_DOCUMENT_REPLY');
      return result;
    },
    async payment(scene, operation, reference) {
      if(!token||now()>=expires)throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)||
         !['prepare','recover','query','cancel'].includes(operation)||typeof reference!=='string'||
         !/^[A-Za-z0-9_-]{1,64}$/.test(reference))throw Error('INVALID_PAYMENT_REQUEST');
      const version=generation;
      const reply=await request('/mini/payment',{scene,operation,reference},token);
      if(version!==generation)throw Error('STALE_SESSION');
      if(reply.payment_enabled!==true||!reply.result)throw Error('PAYMENT_NOT_ENABLED');
      return reply.result;
    },
    async logout() {
      const old=token;generation++;token=null;expires=0;
      if(old)await request('/mini/logout',{},old);
    },
    clear() {generation++;token=null;expires=0;}
  };
}
module.exports={parseScene,createSession,customerError};
