'use strict';
// 提交链/OCR 链埋点与幂等保护（零正文、零证件、零密钥、零完整请求体）。
// correlation 只接受服务端已脱敏的 SHA256 关联号（32 hex），客户端截短为 16 位展示。
const SUBMIT_STAGES=Object.freeze(['SUBMIT_01','SUBMIT_02','SUBMIT_03','SUBMIT_04','SUBMIT_05','SUBMIT_06']);
const OCR_STAGES=Object.freeze(['OCR_01','OCR_02','OCR_03','OCR_04','OCR_05']);
const SUBMIT_READBACK_COOLDOWN_MS=300000; // 5 分钟冷却窗口：仅状态回读收敛（readback_reconciled），不得自动重发。
const ERROR_BUCKET=new Map([
 ['OK','ok'],['INVALID_REQUEST','client'],['ACCESS_DENIED','auth'],['AUTHENTICATION_FAILED','auth'],['APPLICATION_ACCESS_DENIED','auth'],
 ['RATE_LIMIT','throttle'],['RATE_LIMITED','throttle'],['REQUEST_TIMEOUT','network'],['SERVICE_UNAVAILABLE','service'],['NETWORK','network'],
 ['VERSION_CONFLICT','version'],['SNAPSHOT_CHANGED','version'],['APPLICATION_REVISION_CHANGED','version'],['PROVIDER_VERSION_CHANGED','version'],['SOURCE_BINDING_CHANGED','version'],['ATTACHMENT_CHANGED','version'],['SOURCE_EXPIRED','version'],
 ['OCR_CONFIRMATION_REQUIRED','flow'],['SUBMISSION_GATE_CLOSED','flow'],['DECLARATION_REQUIRED','flow'],['QUERY_ONLY','flow'],['IDEMPOTENCY_CONFLICT','flow'],['JOB_NOT_FOUND','flow'],['QUEUE','flow'],['EXECUTION','flow'],['ADMISSION','flow'],
 ['PROVIDER_RESULT_UNKNOWN','result_unknown'],['SUBMISSION_UNKNOWN','result_unknown'],['OCR_EMPTY_RESPONSE','empty_response'],['PROVIDER_EMPTY_RESPONSE','empty_response'],['REQUEST_IN_PROGRESS','in_progress'],['ANOTHER_REQUEST_IN_PROGRESS','in_progress'],['HOST_NOT_READY','service'],['OCR_UNAVAILABLE','service'],
 ['MATERIAL_CHECK_FAILED','validation'],['PROFILE_CHECK_FAILED','validation'],['IDENTITY_MISMATCH','validation'],['INDUSTRY_CHECK_FAILED','validation'],['MEDIA_CHECK_FAILED','validation'],['ENCRYPTION_FAILED','internal'],['UNEXPECTED_FAILURE','internal'],['OCR_RECOVERY_BINDING_MISSING','version']
]);
function errorBucket(code){
 if(typeof code!=='string')return 'unclassified';
 return ERROR_BUCKET.get(code)||'unclassified';
}
function shortCorrelation(value){
 if(typeof value!=='string')return '';
 const lower=value.toLowerCase();
 if(/^[0-9a-f]{32}$/.test(lower))return lower.slice(0,16); // SHA256 截 16
 if(/^[0-9a-f]{16,}$/.test(lower))return lower.slice(0,16);
 return '';
}
function createChainTelemetry(limit){
 const max=Number.isSafeInteger(limit)&&limit>0?Math.min(limit,256):64;
 const events=[];
 function record(chain,stage,diagnostic){
  const stages=chain==='submit'?SUBMIT_STAGES:chain==='ocr'?OCR_STAGES:null;
  if(!stages||!stages.includes(stage))return null; // 拒绝任意自由文本
  const source=diagnostic&&typeof diagnostic==='object'?diagnostic:{};
  const event={chain,stage,bucket:errorBucket(source.code||source.reason||'OK'),correlation:shortCorrelation(source.correlation_id||source.diagnostic_id||''),ts:Date.now()};
  events.push(event);
  if(events.length>max)events.shift();
  return event;
 }
 return {record,snapshot(){return events.slice();},clear(){events.length=0;}};
}
function shouldBlockResubmit(state,now){
 // state:{until:毫秒期限, application:结果未知时绑定的申请号};返回 true=禁止任何自动/重复提交，只允许状态回读。
 if(!state||!Number.isSafeInteger(state.until)||state.until<=now)return false;
 return true;
}
// Only provider receipt-backed states can reconcile an unknown provider submission.
// PENDING_INTERNAL_REVIEW / INTERNAL_APPROVED are local review states, not provider receipts.
const CONVERGED_REVIEW_STATES=['SUBMITTED_TO_PROVIDER','CORRECTION'];
function readbackReconciled(state){
 return !!state&&CONVERGED_REVIEW_STATES.includes(state.reviewState);
}
function classifyOcrEmptyResponse(response){
 // 空响应正确分类：HTTP 200 但正文缺失/空不是“缺件”，是可重试的 empty_response，保留原任务，勿重复上传。
 if(response===undefined||response===null)return true;
 if(typeof response==='string')return response.trim()==='';
 if(typeof response==='object')return Object.keys(response).length===0;
 return false;
}
module.exports={SUBMIT_STAGES,OCR_STAGES,SUBMIT_READBACK_COOLDOWN_MS,errorBucket,shortCorrelation,createChainTelemetry,shouldBlockResubmit,readbackReconciled,classifyOcrEmptyResponse};
