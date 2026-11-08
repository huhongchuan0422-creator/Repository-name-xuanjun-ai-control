'use strict';
module.exports=function create({prefix='/h5',csrf='',fetch:request=globalThis.fetch,saveCsrf=()=>{}}={}){
 let generation=0,authenticated=false,loginFlight=null,platformAppid='';const listeners=new Set();let authTail=Promise.resolve();function serializeAuth(work){const result=authTail.then(work,work);authTail=result.catch(()=>{});return result;}
 function clear(notify=true){generation++;authenticated=false;csrf='';platformAppid='';saveCsrf('');if(notify)for(const f of listeners){try{f()}catch(_){/* One stale page cannot prevent remaining identity cleanup. */}}}
 async function call(path,body,requireAuth=true){
  const captured=generation;
  if(requireAuth&&!csrf)throw Error('SESSION_EXPIRED');
  let response;try{response=await request(prefix+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{})},body:JSON.stringify(body)});}catch(e){const error=Error('网络中断，结果尚未确认；请查询原记录');error.networkKind='NETWORK';if(path==='/merchant'&&body.operation==='onboarding'&&body.params.operation==='upload')error.uploadResultUnknown=true;throw error;}
  if(captured!==generation)throw Error('STALE_SESSION');
  const data=await response.json();if(captured!==generation)throw Error('STALE_SESSION');
  if(!response.ok){const e=Error('SERVICE_REQUEST_REJECTED');e.statusCode=response.status;
   const code=data&&typeof data.error==='string'?data.error:'';
   if(response.status===429&&code==='RATE_LIMIT'){e.message='RATE_LIMIT';e.retryable=true;e.sessionPreserved=true}
   if(response.status===401||response.status===403)e.code='ACCESS_DENIED';
   if(path==='/merchant'&&body.operation==='ocr'){
    e.ocrDiagnostic=require('../community-mini/session').safeOcrDiagnostic(data&&data.ocr_diagnostic);
    if(['OCR_SOURCE_CHANGED','OCR_AUTH_DENIED','OCR_UNAVAILABLE','OCR_REQUEST_PENDING'].includes(code))e.ocrCode=code;
   }
   if(response.status===400&&path==='/merchant'&&body.operation==='onboarding'&&['submit','wechat_submit_review'].includes(body.params?.operation)&&code==='MINI_LICENSE_REGION_INVALID'&&['INVALID_ADDRESS','INCOMPLETE_ADDRESS','UNRECOGNIZED_ADDRESS','DIRECTORY_MISMATCH','AMBIGUOUS_ADDRESS','INVALID_REGION_CODE','REGION_CODE_MISMATCH'].includes(data.reason))e.regionReason=data.reason;
   const preserve=response.status===403&&path==='/merchant'&&((body.operation==='ocr'&&['OCR_UNAVAILABLE','OCR_REQUEST_PENDING'].includes(code))||(body.operation==='onboarding'&&body.params?.operation==='wechat_media'&&code==='WECHAT_MEDIA_UNAVAILABLE'));
   if(preserve){e.sessionPreserved=true;if(code==='WECHAT_MEDIA_UNAVAILABLE')e.mediaCode=code}
   if(path==='/merchant'&&body.operation==='onboarding'&&body.params?.operation==='upload'&&[408,502,503,504].includes(response.status))e.uploadResultUnknown=true;
   if(response.status===401||response.status===403&&!preserve)clear();
   throw e;
  }
  if(!data||data.payment_enabled!==false||!data.result||typeof data.result!=='object'||Array.isArray(data.result))throw Error('UNTRUSTED_BUSINESS_REPLY');
  return data.result;
 }
 async function platform(){if(platformAppid)return;const r=await call('/platform',{});if(Object.keys(r).sort().join(',')!=='appid,source'||r.source!=='ORIGINAL_CENTER_CONFIGURATION'||typeof r.appid!=='string'||!/^wx[0-9a-f]{16}$/.test(r.appid))throw Error('UNTRUSTED_PLATFORM_CONFIGURATION');platformAppid=r.appid;}
 const port={
  hasSession:()=>!!csrf,getPlatformAppid:()=>platformAppid,
  onRevoke(f){listeners.add(f);return()=>listeners.delete(f)},isAuthenticated:()=>authenticated,getGeneration:()=>generation,
  async login(email,password){return serializeAuth(async()=>{clear(false);const current=generation;const r=await call('/session/login',{email,password},false);if(current!==generation)throw Error('STALE_SESSION');if(typeof r.csrf!=='string'||!r.csrf||typeof r.user_id!=='string'||!r.user_id||Object.keys(r).some(k=>!['csrf','user_id'].includes(k)))throw Error('UNTRUSTED_SESSION');csrf=r.csrf;saveCsrf(csrf);authenticated=true;await platform();return r;});},
  async ensureLogin(){if(authenticated){await platform();return;}if(loginFlight)return loginFlight;if(!csrf)throw Error('请先登录现有账户');loginFlight=call('/session/check',{}).then(async r=>{if(typeof r.user_id!=='string'||!r.user_id||Object.keys(r).length!==1)throw Error('UNTRUSTED_SESSION');authenticated=true;await platform();return r}).finally(()=>{loginFlight=null});return loginFlight;},
  async logout(){return serializeAuth(async()=>{const version=generation;const work=csrf?call('/session/logout',{}):Promise.resolve();try{return await work}finally{if(version===generation)clear()}})},clear,
  async transport(scene,body){return {offline_only:true,result:await call('/api',{scene,operation:body.operation,params:body.params})}},
  customer(operation,params={}){return call('/api',{scene:'',operation:'customer.'+operation,params})},
  commerce(scene,operation,params){return call('/api',{scene,operation:'commerce.'+operation,params})},
  merchant(scene,operation,params){return call('/merchant',{scene,operation,params})},
  projectDocument(scene,params,expected=generation){if(expected!==generation)return Promise.reject(Error('STALE_SESSION'));return call('/project-materials',{scene,params})},
  payment(){return Promise.reject(Error('真实支付尚未接入，此处不会扣款'))},reviewerBrowser(){return Promise.reject(Error('运营审核不在本次消费者端范围'))}
 };Object.assign(port,require('./business-contract')({call,isAuthenticated:port.isAuthenticated,getGeneration:port.getGeneration}));return port;
};
