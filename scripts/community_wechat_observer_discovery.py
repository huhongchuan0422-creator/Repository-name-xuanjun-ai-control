"""Serial original-service discovery; no credentials, new grants or persistence.
Reuses committed original application ownership and signed submission evidence.
"""
import copy,re,threading
from scripts.community_wechat_observer import policy
class OriginalApplicationPolicy:
 def __init__(self,applyment,expected_project,interval_seconds=60):
  self.applyment=applyment;self.center=applyment.center;self.project=expected_project;self.interval=interval_seconds;self.thread=threading.get_ident();self.diagnostics={}
 def __call__(self):
  if threading.get_ident()!=self.thread:raise PermissionError('SERIAL_OWNER_THREAD_REQUIRED')
  grants={};diagnostics={};c=self.center
  rows=c.db.execute("SELECT subject_idx,user_id,project FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND active=1 ORDER BY subject_idx").fetchall()
  for application,owner,scope in rows:
   reason='ORIGINAL_BINDING_MISMATCH'
   try:
    if scope!=application:raise ValueError()
    linked=c.db.execute("SELECT user_id FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
    if linked is None or linked[0]!=owner:raise ValueError()
    reason='ORIGINAL_ACCOUNT_NOT_ACTIVE'
    account=c.db.execute('SELECT verified,epoch FROM accounts WHERE id=?',(owner,)).fetchone()
    if account is None or account[0]!=1:raise ValueError()
    reason='ORIGINAL_PROJECT_NOT_ACTIVE'
    project=c.db.execute('SELECT active,expires FROM projects WHERE id=?',(self.project,)).fetchone()
    if project is None or project[0]!=1 or project[1]<=c.now():raise ValueError()
    reason='ORIGINAL_APPLICATION_UNAVAILABLE'
    actual,meta,platform=self.applyment.onboarding._load(application,owner,False)
    if actual!=owner:raise ValueError()
    reason='WITHDRAWN'
    if platform['status']=='WITHDRAWN':raise ValueError()
    record=self.applyment._read(application);reason='ORIGINAL_PROJECT_MISMATCH'
    from scripts.community_single_restore_realm import realm_compatible
    if not realm_compatible(c,application,owner,meta,record,self.project):raise ValueError()
    reason='NO_VERIFIED_SUBMISSION'
    if type(record)is not dict or record.get('state')=='SUBMISSION_UNKNOWN':raise ValueError()
    code=record.get('business_code');aid=record.get('applyment_id');merchant=record.get('provider_sp_mchid')
    from scripts.community_wechat_applyment import submission_evidence_class
    if submission_evidence_class(record)=='DRAFT':
     reason='NOT_SUBMITTED';raise ValueError()
    reason='PROVIDER_MERCHANT_MISMATCH'
    if merchant!=self.applyment.reader_for_record(record)._mchid:raise ValueError()
    reason='NO_VERIFIED_SUBMISSION'
    receipts=list(record.get('submission_receipts',[]))
    if type(record.get('submission_recovery_receipt'))is dict:receipts.append(record['submission_recovery_receipt'])
    if not any(type(x)is dict and x.get('business_code')==code and x.get('applyment_id')==aid and type(x.get('signed_at'))is int and re.fullmatch('[a-f0-9]{64}',str(x.get('signature_sha256',''))) for x in receipts):raise ValueError()
    binding={'project':self.project,'owner':owner,'application':application,'business_code':code,'applyment_id':aid,'provider_merchant':merchant,'revision':1,'active':True}
    policy({'version':1,'enabled':True,'interval_seconds':self.interval,'grants':{application:binding}})
    grants[application]=binding
   except (ValueError,TypeError,KeyError,PermissionError):diagnostics[application]=reason
  self.diagnostics=diagnostics
  return policy({'version':1,'enabled':True,'interval_seconds':self.interval,'grants':grants})
 def status(self,application):return self.diagnostics.get(application)
