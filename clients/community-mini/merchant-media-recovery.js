'use strict';
function unknown(){const e=Error('WECHAT_MEDIA_RESULT_UNKNOWN');e.mediaCode=e.message;return e;}
function validStatus(value,application,kind,sha){
 if(!value||value.application!==application||value.kind!==kind||typeof value.source_sha256!=='string'||!/^[0-9a-f]{64}$/.test(value.source_sha256)||(sha&&value.source_sha256!==sha)||!['NOT_STARTED','PENDING_OR_UNKNOWN','READY'].includes(value.state)||(value.state==='READY'&&(typeof value.media_id!=='string'||value.media_id.length<1||value.media_id.length>1024)))throw Error('INVALID_SAVED_PROVIDER_MEDIA_RECEIPT');
 return value;
}
async function resolveMedia({request,application,kind,current}){
 const active=()=>{if(!current())throw Error('STALE_MEDIA_CONTEXT');};
 active();const initial=validStatus(await request('wechat_media_status',{application,kind,expected_source_sha256:null}),application,kind);active();
 if(initial.state==='READY')return {...initial,recovered:true};
 
 const sha=initial.source_sha256;
 try{
  const value=await request('wechat_media',{application,kind,expected_source_sha256:sha});active();
  if(!value||value.kind!==kind||value.source_sha256!==sha||typeof value.media_id!=='string'||!value.media_id.length||value.media_id.length>1024)throw Error('INVALID_PROVIDER_MEDIA_ID');
  return {...value,recovered:false};
 }catch(error){
  active();if(!error||error.mediaCode!=='WECHAT_MEDIA_RESULT_UNKNOWN'&&error.message!=='WECHAT_MEDIA_RESULT_UNKNOWN')throw error;
  let value;
  try{value=validStatus(await request('wechat_media_status',{application,kind,expected_source_sha256:sha}),application,kind,sha);}catch(_){active();throw error;}
  active();if(value.state!=='READY')throw error;
  return {...value,recovered:true};
 }
}
module.exports={resolveMedia};
