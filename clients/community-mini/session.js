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
  const request=(path,data,credential,scene)=>new Promise((resolve,reject)=>{
    wx.request({url:baseUrl+path,method:'POST',data,timeout:5000,
      header:{'content-type':'application/json',...(credential?{'X-Community-Session':credential}:{}),...(scene?{'X-Community-Scene':scene}:{})},
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
    async commerce(scene, operation, params) {
      if(!token||now()>=expires)throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)||!['communities','community_mine','community_join','community_leave','promotion_redeem','profile_read','profile_update','referral_code','referral_bind','notices','notice_read','orders','products','purchase','purchase_read','receipt_ad','project_summary','project_checklist','project_feedback','project_messages','project_save_reference','project_submit','refund_apply','refund_application','refund_current'].includes(operation))throw Error('INVALID_COMMERCE_REQUEST');
      const version=generation;
      const reply=await request('/mini/api',{scene,operation:'commerce.'+operation,params},token);
      if(version!==generation)throw Error('STALE_SESSION');
      if(!reply||!reply.result||reply.payment_enabled!==false)throw Error('UNTRUSTED_COMMERCE_REPLY');
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
module.exports={parseScene,createSession};
