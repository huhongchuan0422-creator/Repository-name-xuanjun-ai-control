'use strict';
// Phone-only inference; the protected backend supplies one body-bound short-lived proof.
const URL='https://ocr-api.cn-hangzhou.aliyuncs.com/';
const ACTION=Object.freeze({business_license:'RecognizeBusinessLicense',id_front:'RecognizeIdcard',id_back:'RecognizeIdcard',bank_card:'RecognizeBankCard'});
const MAP={
 business_license:{companyName:'company_name',creditCode:'credit_code',legalPerson:'legal_representative',businessAddress:'registered_address'},
 id_front:{name:'id_name',idNumber:'id_number',address:'registered_address'},
 id_back:{issueAuthority:'issuing_authority'},
 bank_card:{cardNumber:'account_number',bankName:'account_bank'}
};
const has=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const HEX=/^[0-9a-f]{64}$/;
const HEADERS='authorization,content-type,x-acs-action,x-acs-content-sha256,x-acs-date,x-acs-signature-nonce,x-acs-version';
const SIGNED='content-type;host;x-acs-action;x-acs-content-sha256;x-acs-date;x-acs-signature-nonce;x-acs-version';
function validHeaders(h,kind,digest){
 if(!h||Object.keys(h).sort().join(',')!==HEADERS||Object.keys(h).some(k=>typeof h[k]!=='string'))return false;
 const auth=/^ACS3-HMAC-SHA256 Credential=[A-Za-z0-9_-]{1,128},SignedHeaders=([a-z0-9;-]+),Signature=[a-f0-9]{64}$/.exec(h.authorization);
 return !!auth&&auth[1]===SIGNED&&h['content-type']==='application/octet-stream'&&h['x-acs-action']===ACTION[kind]&&
 h['x-acs-version']==='2021-07-07'&&h['x-acs-content-sha256']===digest&&
 /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(h['x-acs-date'])&&Number.isFinite(Date.parse(h['x-acs-date']))&&Date.now()-Date.parse(h['x-acs-date'])<=90000&&Date.parse(h['x-acs-date'])-Date.now()<=30000&&/^[A-Za-z0-9_-]{16,128}$/.test(h['x-acs-signature-nonce']);
}
function dateValue(y,m,d){
 const v=new Date(Date.UTC(+y,+m-1,+d));
 return v.getUTCFullYear()===+y&&v.getUTCMonth()+1===+m&&v.getUTCDate()===+d?
  [y,String(m).padStart(2,'0'),String(d).padStart(2,'0')].join('-'):'';
}
function suggestions(kind,envelope){
 if(!has(MAP,kind)||!envelope||envelope.Code)throw Error('DIRECT_OCR_RESPONSE_INVALID');
 let payload;
 try{payload=typeof envelope.Data==='string'?JSON.parse(envelope.Data):envelope.Data;}catch{throw Error('DIRECT_OCR_RESPONSE_INVALID');}
 let node=payload;
 if(kind==='id_front'||kind==='id_back')node=payload&&payload.data&&payload.data[kind==='id_front'?'face':'back'];
 const data=node&&node.data;
 if(!data||typeof data!=='object'||Array.isArray(data))throw Error('DIRECT_OCR_RESPONSE_INVALID');
 const fields={};
 for(const [from,to] of Object.entries(MAP[kind])){
  let v=typeof data[from]==='string'?data[from].trim():'';
  if(to==='account_number'){v=v.replace(/\s+/g,'');if(!/^[0-9]+$/.test(v))v='';}
  if(to==='id_number'){v=v.replace(/\s+/g,'').toUpperCase();if(!/^[1-9][0-9]{16}[0-9X]$/.test(v))v='';}
  if(v)fields[to]=v;
 }
 if(kind==='id_back'&&typeof data.validPeriod==='string'){
  const values=[];
  data.validPeriod.replace(/(\d{4})[.\-\/年](\d{1,2})[.\-\/月](\d{1,2})日?/g,(_,y,m,d)=>{values.push(dateValue(y,m,d));return '';});
  if(values.length===1&&values[0]&&/长期\s*$/.test(data.validPeriod)){
   fields.valid_from=values[0];fields.valid_to='长期';
  }else if(values.length===2&&values[0]&&values[1]&&values[0]<=values[1]){
   fields.valid_from=values[0];fields.valid_to=values[1];
  }
 }
 return {origin:'phone_only_unverified',fields,requiresHumanReview:true};
}
// sha256 and signDigest are explicit dependencies, not implemented here.
// No key or reusable signing authority may be supplied to the app.
function startDirectOcr({kind,original,sha256,signDigest,savePrivate,request,isCurrent,onSave,onSuggestion,
                         timing=null}){
 if(!has(ACTION,kind)||!(original instanceof ArrayBuffer)||!original.byteLength||original.byteLength>10_000_000)
  throw Error('DIRECT_OCR_INPUT_INVALID');
 const bytes=original.slice(0);
 // A proof request and private image storage are independent. A failed or
 // slow proof must never gate storage; a failed/slow save never gates OCR.
 const authorization=Promise.resolve().then(()=>sha256(bytes.slice(0))).then(async digest=>{
  if(!isCurrent())return null;
  if(typeof digest!=='string'||!HEX.test(digest))return null;
  const header=await signDigest({kind,digest,size:bytes.byteLength});
  return isCurrent()&&validHeaders(header,kind,digest)?header:null;
 }).catch(()=>null);
 const storage=Promise.resolve().then(()=>isCurrent()?savePrivate(bytes.slice(0)):null).then(ack=>{
  if(ack!==null&&isCurrent())onSave(ack);return ack!==null;
 },()=>{if(isCurrent())onSave(null);return false;});
 const ocr=authorization.then(async header=>{
  if(!isCurrent())return false;
  if(!header)throw Error('DIRECT_OCR_PROOF_UNAVAILABLE');
  const clock=timing&&typeof timing.now==='function'?timing.now:null;
  const timestamp=()=>{try{return clock?clock():null;}catch{return null;}};
  const sent=timestamp();
  let received=null;
  const packet=await new Promise((resolve,reject)=>request({url:URL,method:'POST',data:bytes,header:{...header},dataType:'json',
   success:r=>{received=timestamp();resolve(r);},fail:()=>reject(Error('DIRECT_OCR_REQUEST_FAILED'))}));
  if(!isCurrent())return false;
  if(!packet||packet.statusCode!==200){
   if(timing&&typeof timing.record==='function'&&Number.isFinite(sent)&&Number.isFinite(received)&&received>=sent){
    try{timing.record({ocr_round_trip_ms:Math.round(received-sent),ocr_http_status:Number.isInteger(packet?.statusCode)?packet.statusCode:0,request_id_present:typeof packet?.data?.RequestId==='string'&&!!packet.data.RequestId});}catch{}
   }
   throw Error('DIRECT_OCR_REQUEST_FAILED');
  }
  const result=suggestions(kind,packet.data);
  // The consumer returns true only once setData's callback confirms the
  // current suggestion has been rendered. Never infer that from receipt.
  const rendered=await onSuggestion(result);
  if(rendered===true&&isCurrent()&&Object.keys(result.fields).length&&timing&&typeof timing.record==='function'){
   const filled=timestamp(),picked=timing.pickedAt;
   if([picked,sent,received,filled].every(Number.isFinite)&&picked<=sent&&sent<=received&&received<=filled){
    try{timing.record({kind,ocr_round_trip_ms:Math.round(received-sent),
      pick_to_front_filled_ms:Math.round(filled-picked),request_id_present:typeof packet.data?.RequestId==='string'&&!!packet.data.RequestId});}catch{/* metrics cannot fail OCR */}
   }
  }
  return isCurrent();
 }).catch(()=>{if(isCurrent())onSuggestion(null);return false;});
 return {storage,ocr};
}
module.exports={startDirectOcr,suggestions,ACTION};
