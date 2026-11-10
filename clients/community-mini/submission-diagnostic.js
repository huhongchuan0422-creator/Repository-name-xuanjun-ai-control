'use strict';
const OPERATIONS=new Set(["UNKNOWN", "read", "wechat_read", "submit", "wechat_apply", "wechat_status", "wechat_media"]);
const STAGES=new Set(["HTTP_REQUEST", "AUTHENTICATION", "REQUEST_BODY", "BODY_PARSE", "DISPATCH", "VERSION", "OCR_CONFIRMATION", "SUBMISSION_GATE", "DECLARATIONS", "PROVIDER_BINDING", "MATERIALS", "PROFILE", "IDENTITY", "INDUSTRY", "MEDIA", "ENCRYPTION", "INTENT_TRANSACTION", "PROVIDER_POST", "RECEIPT_TRANSACTION", "PROVIDER_QUERY"]);
const CODES=new Set(["OK", "INVALID_REQUEST", "ACCESS_DENIED", "RATE_LIMIT", "REQUEST_TIMEOUT", "SERVICE_UNAVAILABLE", "MINI_LICENSE_REGION_INVALID", "VERSION_CONFLICT", "OCR_CONFIRMATION_REQUIRED", "SUBMISSION_GATE_CLOSED", "DECLARATION_REQUIRED", "QUERY_ONLY", "MATERIAL_CHECK_FAILED", "PROFILE_CHECK_FAILED", "IDENTITY_MISMATCH", "INDUSTRY_CHECK_FAILED", "MEDIA_CHECK_FAILED", "ENCRYPTION_FAILED", "SNAPSHOT_CHANGED", "PROVIDER_RESULT_UNKNOWN", "IDENTITY_CHECK_FAILED", "SNAPSHOT_CHECK_FAILED"]);
function safeSubmissionDiagnostic(v){
 if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).sort().join(',')!=='code,correlation_id,operation,stage,status,timestamp'||!OPERATIONS.has(v.operation)||!STAGES.has(v.stage)||!CODES.has(v.code)||!['STARTED','SUCCEEDED','FAILED'].includes(v.status)||typeof v.correlation_id!=='string'||!/^[0-9a-f]{32}$/.test(v.correlation_id)||!Number.isSafeInteger(v.timestamp)||v.timestamp<0||v.timestamp>4102444800)return null;
 return {operation:v.operation,stage:v.stage,code:v.code,correlation_id:v.correlation_id,timestamp:v.timestamp,status:v.status};
}
function submissionDiagnosticFeedback(error){const v=safeSubmissionDiagnostic(error&&error.submissionDiagnostic);return v?'（诊断 '+v.operation+'/'+v.stage+'/'+v.code+'，编号 '+v.correlation_id+'）':'';}
module.exports={safeSubmissionDiagnostic,submissionDiagnosticFeedback};
