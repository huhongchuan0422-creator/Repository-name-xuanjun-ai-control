'use strict';
const OPERATIONS=new Set(["UNKNOWN", "read", "wechat_read", "submit", "wechat_apply", "wechat_status", "wechat_media"]);
const STAGES=new Set(["HTTP_REQUEST", "AUTHENTICATION", "REQUEST_BODY", "BODY_PARSE", "DISPATCH", "VERSION", "OCR_CONFIRMATION", "SUBMISSION_GATE", "DECLARATIONS", "PROVIDER_BINDING", "MATERIALS", "PROFILE", "IDENTITY", "INDUSTRY", "MEDIA", "ENCRYPTION", "INTENT_TRANSACTION", "PROVIDER_POST", "RECEIPT_TRANSACTION", "PROVIDER_QUERY"]);
const CODES=new Set(["OK", "INVALID_REQUEST", "ACCESS_DENIED", "RATE_LIMIT", "REQUEST_TIMEOUT", "SERVICE_UNAVAILABLE", "MINI_LICENSE_REGION_INVALID", "VERSION_CONFLICT", "OCR_CONFIRMATION_REQUIRED", "SUBMISSION_GATE_CLOSED", "DECLARATION_REQUIRED", "QUERY_ONLY", "MATERIAL_CHECK_FAILED", "PROFILE_CHECK_FAILED", "IDENTITY_MISMATCH", "INDUSTRY_CHECK_FAILED", "MEDIA_CHECK_FAILED", "ENCRYPTION_FAILED", "SNAPSHOT_CHANGED", "PROVIDER_RESULT_UNKNOWN", "IDENTITY_CHECK_FAILED", "SNAPSHOT_CHECK_FAILED"]);
const PROFILE_REASONS=new Set(["APPLYMENT_PROFILE_TOO_LARGE", "CURRENT_PROJECT_MINI_OR_STORE_SCENES_REQUIRED", "DUPLICATE_OFFICIAL_UBO_DOCUMENT", "ENTERPRISE_OR_INDIVIDUAL_LEGAL_IDENTITY_REQUIRED", "INVALID_ADDITION_INFO", "INVALID_BUSINESS_ADDITION_PICS", "INVALID_FINANCE_INSTITUTION_FLAG", "INVALID_FINANCE_INSTITUTION_TYPE", "INVALID_OFFICIAL_ACTIVITY_RATE", "INVALID_OFFICIAL_CONTACT_FORMAT", "INVALID_OFFICIAL_CONTACT_TYPE", "INVALID_OFFICIAL_DOCUMENT_NUMBER", "INVALID_OFFICIAL_DOCUMENT_TYPE", "INVALID_OFFICIAL_MEDIA_LIST", "INVALID_OFFICIAL_PERIOD", "INVALID_OFFICIAL_TEXT", "INVALID_OFFICIAL_UBO_LIST", "INVALID_OR_EXPIRED_OFFICIAL_PERIOD", "LOCAL_ATTRIBUTE_ERROR", "LOCAL_KEY_ERROR", "LOCAL_TYPE_ERROR", "MINI_PROGRAM_LIVE_DECLARATION_REQUIRED", "MISSING_OFFICIAL_FIELDS", "OFFICIAL_ACCOUNT_HOLDER_NAME_MISMATCH", "OFFICIAL_APPLYMENT_SECTIONS_REQUIRED", "OFFICIAL_BANK_ACCOUNT_TYPE_MISMATCH", "OFFICIAL_BANK_BRANCH_REQUIRED", "OFFICIAL_ID_CARD_INFO_REQUIRED", "OFFICIAL_LEGAL_DOCUMENT_TYPE_REQUIRED", "OFFICIAL_LICENSE_AND_IDENTITY_OBJECTS_REQUIRED", "OFFICIAL_MINI_SCENE_REQUIRED", "OFFICIAL_OBJECT_REQUIRED", "OFFICIAL_SUBJECT_TYPE_MISMATCH", "UNCLASSIFIED"]);
const PROFILE_PATHS=new Set(["addition_info", "addition_info.business_addition_pics", "bank_account_info", "bank_account_info.account_bank", "bank_account_info.account_name", "bank_account_info.account_number", "bank_account_info.bank_account_type", "bank_account_info.bank_branch_id", "bank_account_info.bank_name", "business_info", "business_info.merchant_shortname", "business_info.sales_info", "business_info.sales_info.biz_store_info", "business_info.sales_info.biz_store_info.biz_address_code", "business_info.sales_info.biz_store_info.biz_store_address", "business_info.sales_info.biz_store_info.biz_store_name", "business_info.sales_info.biz_store_info.indoor_pic", "business_info.sales_info.biz_store_info.store_entrance_pic", "business_info.sales_info.mini_program_info", "business_info.sales_info.mini_program_info.appid", "business_info.sales_info.mini_program_info.mini_program_appid", "business_info.sales_info.mini_program_info.mini_program_pics", "business_info.sales_info.mini_program_info.mini_program_sub_appid", "business_info.sales_info.sales_scenes_type", "business_info.service_phone", "contact_info", "contact_info.contact_email", "contact_info.contact_id_doc_copy", "contact_info.contact_id_doc_copy_back", "contact_info.contact_id_doc_type", "contact_info.contact_id_number", "contact_info.contact_name", "contact_info.contact_period_begin", "contact_info.contact_period_end", "contact_info.contact_type", "contact_info.mobile_phone", "settlement_info", "settlement_info.activities_additions", "settlement_info.activities_id", "settlement_info.credit_activities_rate", "settlement_info.debit_activities_rate", "settlement_info.qualification_type", "settlement_info.qualifications", "settlement_info.settlement_id", "subject_info", "subject_info.business_license_info", "subject_info.business_license_info.legal_person", "subject_info.business_license_info.license_copy", "subject_info.business_license_info.license_number", "subject_info.business_license_info.merchant_name", "subject_info.finance_institution", "subject_info.finance_institution_info", "subject_info.finance_institution_info.finance_license_pics", "subject_info.finance_institution_info.finance_type", "subject_info.identity_info", "subject_info.identity_info.id_card_info", "subject_info.identity_info.id_card_info.card_period_begin", "subject_info.identity_info.id_card_info.card_period_end", "subject_info.identity_info.id_card_info.id_card_address", "subject_info.identity_info.id_card_info.id_card_copy", "subject_info.identity_info.id_card_info.id_card_name", "subject_info.identity_info.id_card_info.id_card_national", "subject_info.identity_info.id_card_info.id_card_number", "subject_info.identity_info.id_doc_info", "subject_info.identity_info.id_doc_info.doc_period_begin", "subject_info.identity_info.id_doc_info.doc_period_end", "subject_info.identity_info.id_doc_info.id_doc_address", "subject_info.identity_info.id_doc_info.id_doc_copy", "subject_info.identity_info.id_doc_info.id_doc_copy_back", "subject_info.identity_info.id_doc_info.id_doc_name", "subject_info.identity_info.id_doc_info.id_doc_number", "subject_info.identity_info.id_doc_type", "subject_info.identity_info.id_holder_type", "subject_info.subject_type", "subject_info.ubo_info_list", "subject_info.ubo_info_list.0", "subject_info.ubo_info_list.0.ubo_id_doc_address", "subject_info.ubo_info_list.0.ubo_id_doc_copy", "subject_info.ubo_info_list.0.ubo_id_doc_copy_back", "subject_info.ubo_info_list.0.ubo_id_doc_name", "subject_info.ubo_info_list.0.ubo_id_doc_number", "subject_info.ubo_info_list.0.ubo_id_doc_type", "subject_info.ubo_info_list.0.ubo_period_begin", "subject_info.ubo_info_list.0.ubo_period_end", "subject_info.ubo_info_list.1", "subject_info.ubo_info_list.1.ubo_id_doc_address", "subject_info.ubo_info_list.1.ubo_id_doc_copy", "subject_info.ubo_info_list.1.ubo_id_doc_copy_back", "subject_info.ubo_info_list.1.ubo_id_doc_name", "subject_info.ubo_info_list.1.ubo_id_doc_number", "subject_info.ubo_info_list.1.ubo_id_doc_type", "subject_info.ubo_info_list.1.ubo_period_begin", "subject_info.ubo_info_list.1.ubo_period_end", "subject_info.ubo_info_list.2", "subject_info.ubo_info_list.2.ubo_id_doc_address", "subject_info.ubo_info_list.2.ubo_id_doc_copy", "subject_info.ubo_info_list.2.ubo_id_doc_copy_back", "subject_info.ubo_info_list.2.ubo_id_doc_name", "subject_info.ubo_info_list.2.ubo_id_doc_number", "subject_info.ubo_info_list.2.ubo_id_doc_type", "subject_info.ubo_info_list.2.ubo_period_begin", "subject_info.ubo_info_list.2.ubo_period_end", "subject_info.ubo_info_list.3", "subject_info.ubo_info_list.3.ubo_id_doc_address", "subject_info.ubo_info_list.3.ubo_id_doc_copy", "subject_info.ubo_info_list.3.ubo_id_doc_copy_back", "subject_info.ubo_info_list.3.ubo_id_doc_name", "subject_info.ubo_info_list.3.ubo_id_doc_number", "subject_info.ubo_info_list.3.ubo_id_doc_type", "subject_info.ubo_info_list.3.ubo_period_begin", "subject_info.ubo_info_list.3.ubo_period_end"]);
function safeProfileIssue(v){
 if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).sort().join(',')!=='fields,reason'||!PROFILE_REASONS.has(v.reason)||!Array.isArray(v.fields)||v.fields.length>32||new Set(v.fields).size!==v.fields.length||!v.fields.every(field=>typeof field==='string'&&PROFILE_PATHS.has(field)))return null;
 return {reason:v.reason,fields:v.fields.slice()};
}
function safeSubmissionDiagnostic(v){
 if(!v||typeof v!=='object'||Array.isArray(v)||!['code,correlation_id,operation,stage,status,timestamp','code,correlation_id,operation,profile_issue,stage,status,timestamp'].includes(Object.keys(v).sort().join(','))||!OPERATIONS.has(v.operation)||!STAGES.has(v.stage)||!CODES.has(v.code)||!['STARTED','SUCCEEDED','FAILED'].includes(v.status)||typeof v.correlation_id!=='string'||!/^[0-9a-f]{32}$/.test(v.correlation_id)||!Number.isSafeInteger(v.timestamp)||v.timestamp<0||v.timestamp>4102444800)return null;
 const result={operation:v.operation,stage:v.stage,code:v.code,correlation_id:v.correlation_id,timestamp:v.timestamp,status:v.status};
 if(Object.prototype.hasOwnProperty.call(v,'profile_issue')){const issue=safeProfileIssue(v.profile_issue);if(v.stage!=='PROFILE'||v.code!=='PROFILE_CHECK_FAILED'||v.status!=='FAILED'||!issue)return null;result.profile_issue=issue;}
 return result;
}
function submissionDiagnosticFeedback(error){const v=safeSubmissionDiagnostic(error&&error.submissionDiagnostic);return v?'（诊断 '+v.operation+'/'+v.stage+'/'+v.code+(v.profile_issue?'，校验原因 '+v.profile_issue.reason+(v.profile_issue.fields.length?'，字段 '+v.profile_issue.fields.join('、'):''):'')+'，编号 '+v.correlation_id+'）':'';}
const PROFILE_MESSAGES={
 MISSING_OFFICIAL_FIELDS:'请核对缺少的必填字段',
 OFFICIAL_OBJECT_REQUIRED:'资料分组结构不正确',OFFICIAL_APPLYMENT_SECTIONS_REQUIRED:'资料分组缺失或结构不正确',
 APPLYMENT_PROFILE_TOO_LARGE:'原资料超过已有大小限制，请保留原内容并联系处理',
 INVALID_OFFICIAL_TEXT:'字段首尾空格或控制字符不符合原格式要求',
 INVALID_OFFICIAL_PERIOD:'证件有效期格式不正确，请按 YYYY-MM-DD 填写，长期有效请填“长期”',
 INVALID_OR_EXPIRED_OFFICIAL_PERIOD:'证件有效期不符合原日期校验，请核对起止日期和是否过期',
 INVALID_OFFICIAL_DOCUMENT_TYPE:'证件类型不在原支持范围',OFFICIAL_LEGAL_DOCUMENT_TYPE_REQUIRED:'请核对法人或经营者证件类型',
 INVALID_OFFICIAL_DOCUMENT_NUMBER:'证件号码格式与所选证件类型不符',
 INVALID_OFFICIAL_CONTACT_FORMAT:'联系电话或邮箱格式不正确',INVALID_OFFICIAL_CONTACT_TYPE:'请核对办理人类型',
 OFFICIAL_ACCOUNT_HOLDER_NAME_MISMATCH:'结算户名与所选账户类型对应的营业执照名称或证件姓名不一致',
 OFFICIAL_BANK_ACCOUNT_TYPE_MISMATCH:'所选账户类型与主体类型不符合原规则',
 OFFICIAL_SUBJECT_TYPE_MISMATCH:'微信资料主体类型与原申请主体类型不一致',
 OFFICIAL_LICENSE_AND_IDENTITY_OBJECTS_REQUIRED:'营业执照或身份资料分组结构不正确',
 OFFICIAL_ID_CARD_INFO_REQUIRED:'身份证资料分组缺失或结构不正确',
 ENTERPRISE_OR_INDIVIDUAL_LEGAL_IDENTITY_REQUIRED:'请核对原申请法人或经营者身份',
 OFFICIAL_BANK_BRANCH_REQUIRED:'其他银行需核对已有支行联行号或支行全称',
 INVALID_OFFICIAL_MEDIA_LIST:'所列照片资料的列表格式或数量不符合原规则',
 INVALID_OFFICIAL_UBO_LIST:'受益人名单与主体类型或原人数规则不符',
 DUPLICATE_OFFICIAL_UBO_DOCUMENT:'受益人名单存在重复证件',
 INVALID_FINANCE_INSTITUTION_TYPE:'金融机构类型不符合原枚举',INVALID_FINANCE_INSTITUTION_FLAG:'金融机构声明格式不正确',
 CURRENT_PROJECT_MINI_OR_STORE_SCENES_REQUIRED:'经营场景资料不符合原场景规则',
 OFFICIAL_MINI_SCENE_REQUIRED:'小程序经营资料分组缺失或结构不正确',
 INVALID_OFFICIAL_ACTIVITY_RATE:'活动费率格式不符合原规则',
 INVALID_ADDITION_INFO:'补充资料分组结构不正确',INVALID_BUSINESS_ADDITION_PICS:'补充照片格式或数量不符合原规则',
 MINI_PROGRAM_LIVE_DECLARATION_REQUIRED:'小程序上线声明格式不正确',
 LOCAL_TYPE_ERROR:'资料校验发生内部类型异常，请等待定位处理，不必重新填写',
 LOCAL_KEY_ERROR:'资料校验读取字段时发生内部异常，请等待定位处理，不必重新填写',
 LOCAL_ATTRIBUTE_ERROR:'资料校验发生内部结构异常，请等待定位处理，不必重新填写',
 UNCLASSIFIED:'具体原因尚未确定，请先定位原因，不必重新填写'
};
function profileValidationDetails(error,groups=[]){
 const diagnostic=safeSubmissionDiagnostic(error&&error.submissionDiagnostic);
 if(!diagnostic||diagnostic.operation!=='wechat_apply'||diagnostic.stage!=='PROFILE'||diagnostic.code!=='PROFILE_CHECK_FAILED'||diagnostic.status!=='FAILED')return null;
 const issue=diagnostic.profile_issue,reason=issue?PROFILE_MESSAGES[issue.reason]:PROFILE_MESSAGES.UNCLASSIFIED;
 const issues=[];
 for(const path of issue?issue.fields:[]){
  let group=groups.find(g=>(g.items||[]).some(item=>item.path===path));
  if(!group){const ubo=/^subject_info\.ubo_info_list\.([0-3])(?:\.|$)/.exec(path);const id=path==='bank_account_info'||path.startsWith('bank_account_info.')?'bank':path==='contact_info'||path.startsWith('contact_info.')?'contact':path.startsWith('subject_info.identity_info')?'legal':path.startsWith('subject_info.business_license_info')?'license':path.startsWith('business_info.sales_info.biz_store_info')?'store':path.startsWith('business_info.sales_info.mini_program_info')?'mini':ubo?'ubo'+ubo[1]:path==='subject_info.ubo_info_list'?'beneficiaries':path==='settlement_info.qualifications'?'qualification':path.startsWith('settlement_info.')?'bank':null;group=groups.find(g=>g.id===id);}
  if(!group)group=groups.find(g=>(g.items||[]).some(item=>item.path.startsWith(path+'.')));
  if(group){const field=(group.items||[]).find(item=>item.path===path);issues.push({id:issues.length,path,group:group.id,step:group.step,message:(field?field.label:group.title)+'：'+reason});}
 }
 return {feedback:'本次资料校验未通过，未发送本次微信进件。'+reason,issues};
}
module.exports={safeSubmissionDiagnostic,submissionDiagnosticFeedback,profileValidationDetails};
