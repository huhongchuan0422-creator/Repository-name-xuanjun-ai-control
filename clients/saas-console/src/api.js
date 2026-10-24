export const BASE='/customer/center/api/';
export class ApiFailure extends Error { constructor(message,status=0,uncertain=false){super(message);this.status=status;this.uncertain=uncertain;} }
const projectId = id => { if(typeof id!=='string'||!/^[-\w]{1,128}$/.test(id))throw new Error('INVALID_PROJECT'); return encodeURIComponent(id); };
const pageVersion = x => { if(typeof x!=='string'||! /^[a-f0-9]{64}$/.test(x))throw new Error('INVALID_VERSION');return x; };
export function makeApi(fetcher=fetch,csrf=()=>sessionStorage.getItem('xj_csrf')||''){
 async function request(op,body,signal){let r;try{r=await fetcher(BASE+op,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:body===undefined?undefined:JSON.stringify(body),signal});}catch(e){throw new ApiFailure('TRANSPORT_RESULT_UNKNOWN',0,body!==undefined);}let data;try{data=await r.json();}catch{throw new ApiFailure('INVALID_SERVER_RESPONSE',r.status,body!==undefined);}if(!r.ok)throw new ApiFailure(data.error||'REQUEST_REJECTED',r.status);return data;}
 return {
  me:()=>request('me'),
  checklist:project=>request('checklist/'+projectId(project)),
  previews:project=>request('previews/'+projectId(project)),
  changes:project=>request('changes/'+projectId(project)),
  messages:project=>request('messages/'+projectId(project)),
  message:(project,body)=>request('message',{project,body}),
  context:(project,page,version)=>request('change_context',{project,page,version:pageVersion(version)}),
  submit:(project,page,version,text,intent='RECTIFICATION')=>request('change_submit',{project,page,version:pageVersion(version),text,intent}),
  submitIdempotent:({project,page,version,text,intent='RECTIFICATION',idempotency_key})=>{if(typeof idempotency_key!=='string'||! /^[A-Za-z0-9_-]{16,128}$/.test(idempotency_key))throw Error('INVALID_IDEMPOTENCY_KEY');return request('change_submit_idempotent',{project,page,version:pageVersion(version),text,intent,idempotency_key});},
  updates:(project,page,version)=>request('change_updates',{project,page,version:pageVersion(version)}),
  retest:({project,caseId,revision,page,version,delivery_sha256,action,reason})=>request('change_retest',{project,case:caseId,revision,page,version:pageVersion(version),delivery_sha256,action,reason})
 };
}
export function verifiedPreviewUrl(raw){if(typeof raw!=='string'||!raw.startsWith('/customer/center/preview/')||raw.includes('?')||raw.includes('#')||raw.includes('//')||raw.includes('..'))throw new Error('UNTRUSTED_PREVIEW_URL');return raw;}
