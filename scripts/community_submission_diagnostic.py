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
 return dict(operation=c['operation'],stage=c['stage'],correlation_id=c['correlation_id'],timestamp=int(time.time()),status=status,code=c['code'])

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
