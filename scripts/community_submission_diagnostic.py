"""Bounded submission diagnostics: fixed enums and fresh random identifiers only.

No request/record objects, exception text, credentials or applicant identifiers
are emitted. Telemetry failures must not affect business behavior.
"""
import contextvars,functools,json,secrets,sys,time,queue,threading
_CONTEXT=contextvars.ContextVar('submission_diagnostic',default=None)
OPERATIONS=frozenset(('UNKNOWN','read','wechat_read','submit','wechat_apply','wechat_status','wechat_media'))
STAGES=frozenset(('HTTP_REQUEST','AUTHENTICATION','REQUEST_BODY','BODY_PARSE','DISPATCH','VERSION','OCR_CONFIRMATION','SUBMISSION_GATE','DECLARATIONS','PROVIDER_BINDING','MATERIALS','PROFILE','IDENTITY','INDUSTRY','MEDIA','ENCRYPTION','INTENT_TRANSACTION','PROVIDER_POST','RECEIPT_TRANSACTION','PROVIDER_QUERY'))
CODES=frozenset(('OK','INVALID_REQUEST','ACCESS_DENIED','RATE_LIMIT','REQUEST_TIMEOUT','SERVICE_UNAVAILABLE','MINI_LICENSE_REGION_INVALID','VERSION_CONFLICT','OCR_CONFIRMATION_REQUIRED','SUBMISSION_GATE_CLOSED','DECLARATION_REQUIRED','QUERY_ONLY','MATERIAL_CHECK_FAILED','PROFILE_CHECK_FAILED','IDENTITY_MISMATCH','INDUSTRY_CHECK_FAILED','MEDIA_CHECK_FAILED','ENCRYPTION_FAILED','SNAPSHOT_CHANGED','PROVIDER_RESULT_UNKNOWN','IDENTITY_CHECK_FAILED','SNAPSHOT_CHECK_FAILED'))
EXACT={'WECHAT_APPLYMENT_VERSION_CONFLICT':'VERSION_CONFLICT','MINI_SUBMIT_VERSION_CONFLICT':'VERSION_CONFLICT','OCR_DRAFT_CONFIRMATION_REQUIRED':'OCR_CONFIRMATION_REQUIRED','REAL_MERCHANT_SUBMISSION_GATE_CLOSED':'SUBMISSION_GATE_CLOSED','QUERY_EXISTING_APPLICATION_ONLY':'QUERY_ONLY','PLATFORM_IDENTITY_TYPE_MISMATCH':'IDENTITY_MISMATCH','WECHAT_APPLYMENT_CHANGED':'SNAPSHOT_CHANGED','RATE_LIMIT':'RATE_LIMIT'}

# Only code-owned reason names and paths may leave PROFILE. Never expose
# values, raw exception strings, traceback text, or arbitrary object methods.
_PROFILE_PATHS=frozenset(['addition_info', 'addition_info.business_addition_pics', 'bank_account_info', 'bank_account_info.account_bank', 'bank_account_info.account_name', 'bank_account_info.account_number', 'bank_account_info.bank_account_type', 'bank_account_info.bank_branch_id', 'bank_account_info.bank_name', 'business_info', 'business_info.merchant_shortname', 'business_info.sales_info', 'business_info.sales_info.biz_store_info', 'business_info.sales_info.biz_store_info.biz_address_code', 'business_info.sales_info.biz_store_info.biz_store_address', 'business_info.sales_info.biz_store_info.biz_store_name', 'business_info.sales_info.biz_store_info.indoor_pic', 'business_info.sales_info.biz_store_info.store_entrance_pic', 'business_info.sales_info.mini_program_info', 'business_info.sales_info.mini_program_info.appid', 'business_info.sales_info.mini_program_info.mini_program_appid', 'business_info.sales_info.mini_program_info.mini_program_pics', 'business_info.sales_info.mini_program_info.mini_program_sub_appid', 'business_info.sales_info.sales_scenes_type', 'business_info.service_phone', 'contact_info', 'contact_info.contact_email', 'contact_info.contact_id_doc_copy', 'contact_info.contact_id_doc_copy_back', 'contact_info.contact_id_doc_type', 'contact_info.contact_id_number', 'contact_info.contact_name', 'contact_info.contact_period_begin', 'contact_info.contact_period_end', 'contact_info.contact_type', 'contact_info.mobile_phone', 'settlement_info', 'settlement_info.activities_additions', 'settlement_info.activities_id', 'settlement_info.credit_activities_rate', 'settlement_info.debit_activities_rate', 'settlement_info.qualification_type', 'settlement_info.qualifications', 'settlement_info.settlement_id', 'subject_info', 'subject_info.business_license_info', 'subject_info.business_license_info.legal_person', 'subject_info.business_license_info.license_copy', 'subject_info.business_license_info.license_number', 'subject_info.business_license_info.merchant_name', 'subject_info.finance_institution', 'subject_info.finance_institution_info', 'subject_info.finance_institution_info.finance_license_pics', 'subject_info.finance_institution_info.finance_type', 'subject_info.identity_info', 'subject_info.identity_info.id_card_info', 'subject_info.identity_info.id_card_info.card_period_begin', 'subject_info.identity_info.id_card_info.card_period_end', 'subject_info.identity_info.id_card_info.id_card_address', 'subject_info.identity_info.id_card_info.id_card_copy', 'subject_info.identity_info.id_card_info.id_card_name', 'subject_info.identity_info.id_card_info.id_card_national', 'subject_info.identity_info.id_card_info.id_card_number', 'subject_info.identity_info.id_doc_info', 'subject_info.identity_info.id_doc_info.doc_period_begin', 'subject_info.identity_info.id_doc_info.doc_period_end', 'subject_info.identity_info.id_doc_info.id_doc_address', 'subject_info.identity_info.id_doc_info.id_doc_copy', 'subject_info.identity_info.id_doc_info.id_doc_copy_back', 'subject_info.identity_info.id_doc_info.id_doc_name', 'subject_info.identity_info.id_doc_info.id_doc_number', 'subject_info.identity_info.id_doc_type', 'subject_info.identity_info.id_holder_type', 'subject_info.subject_type', 'subject_info.ubo_info_list', 'subject_info.ubo_info_list.0', 'subject_info.ubo_info_list.0.ubo_id_doc_address', 'subject_info.ubo_info_list.0.ubo_id_doc_copy', 'subject_info.ubo_info_list.0.ubo_id_doc_copy_back', 'subject_info.ubo_info_list.0.ubo_id_doc_name', 'subject_info.ubo_info_list.0.ubo_id_doc_number', 'subject_info.ubo_info_list.0.ubo_id_doc_type', 'subject_info.ubo_info_list.0.ubo_period_begin', 'subject_info.ubo_info_list.0.ubo_period_end', 'subject_info.ubo_info_list.1', 'subject_info.ubo_info_list.1.ubo_id_doc_address', 'subject_info.ubo_info_list.1.ubo_id_doc_copy', 'subject_info.ubo_info_list.1.ubo_id_doc_copy_back', 'subject_info.ubo_info_list.1.ubo_id_doc_name', 'subject_info.ubo_info_list.1.ubo_id_doc_number', 'subject_info.ubo_info_list.1.ubo_id_doc_type', 'subject_info.ubo_info_list.1.ubo_period_begin', 'subject_info.ubo_info_list.1.ubo_period_end', 'subject_info.ubo_info_list.2', 'subject_info.ubo_info_list.2.ubo_id_doc_address', 'subject_info.ubo_info_list.2.ubo_id_doc_copy', 'subject_info.ubo_info_list.2.ubo_id_doc_copy_back', 'subject_info.ubo_info_list.2.ubo_id_doc_name', 'subject_info.ubo_info_list.2.ubo_id_doc_number', 'subject_info.ubo_info_list.2.ubo_id_doc_type', 'subject_info.ubo_info_list.2.ubo_period_begin', 'subject_info.ubo_info_list.2.ubo_period_end', 'subject_info.ubo_info_list.3', 'subject_info.ubo_info_list.3.ubo_id_doc_address', 'subject_info.ubo_info_list.3.ubo_id_doc_copy', 'subject_info.ubo_info_list.3.ubo_id_doc_copy_back', 'subject_info.ubo_info_list.3.ubo_id_doc_name', 'subject_info.ubo_info_list.3.ubo_id_doc_number', 'subject_info.ubo_info_list.3.ubo_id_doc_type', 'subject_info.ubo_info_list.3.ubo_period_begin', 'subject_info.ubo_info_list.3.ubo_period_end'])
_PROFILE_EXACT={'OFFICIAL_APPLYMENT_SECTIONS_REQUIRED': [], 'APPLYMENT_PROFILE_TOO_LARGE': [], 'OFFICIAL_SUBJECT_TYPE_MISMATCH': ['subject_info.subject_type'], 'OFFICIAL_BANK_ACCOUNT_TYPE_MISMATCH': ['bank_account_info.bank_account_type'], 'OFFICIAL_LICENSE_AND_IDENTITY_OBJECTS_REQUIRED': ['subject_info.business_license_info', 'subject_info.identity_info'], 'OFFICIAL_ID_CARD_INFO_REQUIRED': ['subject_info.identity_info.id_card_info'], 'OFFICIAL_ACCOUNT_HOLDER_NAME_MISMATCH': ['bank_account_info.account_name'], 'INVALID_ADDITION_INFO': ['addition_info'], 'INVALID_BUSINESS_ADDITION_PICS': ['addition_info.business_addition_pics'], 'MINI_PROGRAM_LIVE_DECLARATION_REQUIRED': ['business_info.sales_info.mini_program_info'], 'INVALID_OFFICIAL_CONTACT_TYPE': ['contact_info.contact_type'], 'INVALID_OFFICIAL_CONTACT_FORMAT': ['contact_info.mobile_phone', 'contact_info.contact_email'], 'ENTERPRISE_OR_INDIVIDUAL_LEGAL_IDENTITY_REQUIRED': ['subject_info.identity_info.id_holder_type'], 'OFFICIAL_LEGAL_DOCUMENT_TYPE_REQUIRED': ['subject_info.identity_info.id_doc_type'], 'OFFICIAL_BANK_BRANCH_REQUIRED': ['bank_account_info.bank_branch_id', 'bank_account_info.bank_name'], 'INVALID_OFFICIAL_UBO_LIST': ['subject_info.ubo_info_list'], 'DUPLICATE_OFFICIAL_UBO_DOCUMENT': ['subject_info.ubo_info_list'], 'INVALID_FINANCE_INSTITUTION_TYPE': ['subject_info.finance_institution_info.finance_type'], 'INVALID_FINANCE_INSTITUTION_FLAG': ['subject_info.finance_institution'], 'CURRENT_PROJECT_MINI_OR_STORE_SCENES_REQUIRED': ['business_info.sales_info.sales_scenes_type'], 'OFFICIAL_MINI_SCENE_REQUIRED': ['business_info.sales_info.mini_program_info'], 'INVALID_OFFICIAL_ACTIVITY_RATE': ['settlement_info.debit_activities_rate', 'settlement_info.credit_activities_rate']}
_PROFILE_PREFIXES=frozenset(['OFFICIAL_OBJECT_REQUIRED', 'MISSING_OFFICIAL_FIELDS', 'INVALID_OFFICIAL_TEXT', 'INVALID_OFFICIAL_PERIOD', 'INVALID_OR_EXPIRED_OFFICIAL_PERIOD', 'INVALID_OFFICIAL_DOCUMENT_TYPE', 'INVALID_OFFICIAL_DOCUMENT_NUMBER', 'INVALID_OFFICIAL_MEDIA_LIST'])

def profile_issue(error):
 try:
  if type(error) in (TypeError,KeyError,AttributeError):
   return dict(reason={TypeError:'LOCAL_TYPE_ERROR',KeyError:'LOCAL_KEY_ERROR',AttributeError:'LOCAL_ATTRIBUTE_ERROR'}[type(error)],fields=[])
  raw=error.args[0] if type(error) is ValueError and error.args else None
  if type(raw) is str and len(raw)<=4096:
   if raw in _PROFILE_EXACT:return dict(reason=raw,fields=list(_PROFILE_EXACT[raw]))
   reason,sep,tail=raw.partition(':')
   if sep and reason in _PROFILE_PREFIXES:
    fields=tail.split(',')
    if 1<=len(fields)<=32 and len(set(fields))==len(fields) and all(field in _PROFILE_PATHS for field in fields):
     return dict(reason=reason,fields=fields)
 except Exception:pass
 return dict(reason='UNCLASSIFIED',fields=[])

def request_scope(fn):
 @functools.wraps(fn)
 def wrapped(*args,**kwargs):
  token=_CONTEXT.set(None)
  try:return fn(*args,**kwargs)
  finally:_CONTEXT.reset(token)
 return wrapped

def begin():
 try:
  _CONTEXT.set(dict(operation='UNKNOWN',stage='HTTP_REQUEST',correlation_id=secrets.token_hex(16),code='OK'))
  emit('STARTED')
 except Exception:pass

def select(body):
 try:
  params=body.get('params') if type(body) is dict and body.get('operation')=='onboarding' else None
  op=params.get('operation') if type(params) is dict else None
  if type(op) is not str or op not in OPERATIONS or op=='UNKNOWN':
   _CONTEXT.set(None);return
  if _CONTEXT.get() is None:begin()
  _CONTEXT.get()['operation']=op
  mark('DISPATCH')
 except Exception:pass

def snapshot(status):
 c=_CONTEXT.get()
 if c is None:return None
 value=dict(operation=c['operation'],stage=c['stage'],correlation_id=c['correlation_id'],timestamp=int(time.time()),status=status,code=c['code'])
 if status=='FAILED' and c['stage']=='PROFILE' and c['code']=='PROFILE_CHECK_FAILED' and 'profile_issue' in c:
  value['profile_issue']=dict(reason=c['profile_issue']['reason'],fields=list(c['profile_issue']['fields']))
 return value

# A full queue drops telemetry instead of blocking the submission. One daemon
# owns the potentially blocking stderr sink. No customer object enters the queue.
_EVENTS=queue.Queue(maxsize=256)
def _write_line(line):
 sys.stderr.write(line)
def _drain():
 while True:
  line=_EVENTS.get()
  try:_write_line(line)
  except Exception:pass
  finally:_EVENTS.task_done()
try:
 _worker=threading.Thread(target=_drain,name='submission-diagnostic',daemon=True)
 _worker.start()
except Exception:pass

def emit(status):
 try:
  value=snapshot(status)
  if value is not None:_EVENTS.put_nowait('SUBMISSION_DIAGNOSTIC '+json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
 except Exception:pass

def mark(stage):
 try:
  c=_CONTEXT.get()
  if c is not None and stage in STAGES:c['stage']=stage;emit('STARTED')
 except Exception:pass

def failure(error):
 try:
  c=_CONTEXT.get()
  if c is None:return
  # Inspect only a primitive exact enum, never call an exception's __str__.
  raw=error.args[0] if type(error) in (ValueError,PermissionError,TypeError,KeyError,TimeoutError) and error.args else None
  code=EXACT.get(raw) if type(raw) is str else None
  if code is None:
   code={'MATERIALS':'MATERIAL_CHECK_FAILED','PROFILE':'PROFILE_CHECK_FAILED','IDENTITY':'IDENTITY_CHECK_FAILED','INDUSTRY':'INDUSTRY_CHECK_FAILED','MEDIA':'MEDIA_CHECK_FAILED','ENCRYPTION':'ENCRYPTION_FAILED','INTENT_TRANSACTION':'SNAPSHOT_CHECK_FAILED','PROVIDER_POST':'PROVIDER_RESULT_UNKNOWN','RECEIPT_TRANSACTION':'PROVIDER_RESULT_UNKNOWN'}.get(c['stage'])
  fallback='INVALID_REQUEST' if isinstance(error,(ValueError,TypeError,KeyError)) else 'ACCESS_DENIED' if isinstance(error,PermissionError) else 'REQUEST_TIMEOUT' if isinstance(error,TimeoutError) else 'SERVICE_UNAVAILABLE'
  c['code']=code or fallback
  if c['stage']=='PROFILE' and c['code']=='PROFILE_CHECK_FAILED':c['profile_issue']=profile_issue(error)
 except Exception:pass

def response(status,value):
 try:
  c=_CONTEXT.get()
  if c is None or type(value) is not dict:return value
  if status>=400:
   public=value.get('error')
   if type(public) is str and public in ('RATE_LIMIT','MINI_LICENSE_REGION_INVALID'):c['code']=public
   elif c['code']=='OK':c['code']=public if type(public) is str and public in CODES else 'ACCESS_DENIED' if status in (401,403) else 'INVALID_REQUEST' if status==400 else 'SERVICE_UNAVAILABLE'
  emit('SUCCEEDED' if status<400 else 'FAILED')
  return dict(value,submission_diagnostic=snapshot('SUCCEEDED' if status<400 else 'FAILED'))
 except Exception:return value
