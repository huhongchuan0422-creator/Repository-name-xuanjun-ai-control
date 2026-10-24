export const BASE='/customer/center/api/';
export class ApiFailure extends Error { constructor(message,status=0,uncertain=false){super(message);this.status=status;this.uncertain=uncertain;} }
const projectId=id=>{if(typeof id!=='string'||!/^[-\w]{1,128}$/.test(id))throw Error('INVALID_PROJECT');return id};
const pageVersion=x=>{if(typeof x!=='string'||! /^[a-f0-9]{64}$/.test(x))throw Error('INVALID_VERSION');return x};
export function makeApi(fetcher=fetch,csrf=()=>sessionStorage.getItem('xj_csrf')||''){
 async function request(op,body){let r;try{r=await fetcher(BASE+op,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:body===undefined?undefined:JSON.stringify(body)});}catch{throw new ApiFailure('TRANSPORT_RESULT_UNKNOWN',0,body!==undefined)}let d;try{d=await r.json()}catch{throw new ApiFailure('INVALID_SERVER_RESPONSE',r.status,body!==undefined)}if(!r.ok){const ambiguous=body!==undefined&&(r.status===408||r.status>=500);throw new ApiFailure(d.error||'REQUEST_REJECTED',r.status,ambiguous)}return d}
 return {me:()=>request('me'),login:(email,password)=>request('login',{email,password}),logout:()=>request('logout',{}),checklist:p=>request('checklist/'+encodeURIComponent(projectId(p))),previews:p=>request('previews/'+encodeURIComponent(projectId(p))),changes:p=>request('changes/'+encodeURIComponent(projectId(p))),messages:p=>request('messages/'+encodeURIComponent(projectId(p))),message:(project,body)=>request('message',{project,body}),save:(project,item,revision,kind,content,expires)=>request('save',{project,item,revision,kind,content,expires}),context:(project,page,version)=>request('change_context',{project,page,version:pageVersion(version)}),submit:(project,page,version,text,intent='RECTIFICATION')=>request('change_submit',{project,page,version:pageVersion(version),text,intent}),submitIdempotent:x=>{if(!/^[A-Za-z0-9_-]{16,128}$/.test(x.idempotency_key||''))throw Error('INVALID_IDEMPOTENCY_KEY');return request('change_submit_idempotent',{...x,version:pageVersion(x.version)})},updates:(project,page,version)=>request('change_updates',{project,page,version:pageVersion(version)}),retest:x=>request('change_retest',{project:x.project,case:x.caseId,revision:x.revision,page:x.page,version:pageVersion(x.version),delivery_sha256:x.delivery_sha256,action:x.action,reason:x.reason})};
}
export function verifiedPreviewUrl(raw,project,version){
 projectId(project);pageVersion(version);
 if(typeof raw!=='string'||!raw.startsWith('/')||raw.includes('\\')||raw.includes('%')||raw.includes('?')||raw.includes('#'))throw Error('UNTRUSTED_PREVIEW_URL');
 let u;try{u=new URL(raw,'https://xuanjun.invalid')}catch{throw Error('UNTRUSTED_PREVIEW_URL')}
 if(u.origin!=='https://xuanjun.invalid'||u.search||u.hash)throw Error('UNTRUSTED_PREVIEW_URL');
 const prefix='/customer/center/preview/'+project+'/';
 if(!u.pathname.startsWith(prefix))throw Error('UNTRUSTED_PREVIEW_URL');
 const rest=u.pathname.slice(prefix.length).split('/');
 if(rest.length!==2||!/^[a-f0-9]{64}$/.test(rest[0])||rest[1]!==version)throw Error('UNTRUSTED_PREVIEW_URL');
 return u.pathname;
}
