"""Original-host GET-only reconciliation of explicit owner submission intents.
No session impersonation, POST, new tables, account grants or service credentials.
Workers receive only original public business-code/provider binding; SQLite and
state validation stay on the existing serial host thread.
"""
import copy,re,threading,time
from concurrent.futures import ThreadPoolExecutor
from scripts.community_provider_transport import request
from scripts.community_wechat_applyment import WechatApplyment

def need(value):
    if not value:raise PermissionError('ORIGINAL_OWNER_RECOVERY_BINDING_CHANGED')

class OwnerSubmissionRecovery:
    def __init__(self,applyment,project,interval=60):
        self.a=applyment;self.c=applyment.center;self.project=project;self.interval=interval
        self.thread=threading.get_ident();self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='owner-submit-get')
        self.pending=None;self.due={};self.closed=False
    def owner_thread(self):need(threading.get_ident()==self.thread)
    def snapshot(self,application):
        self.owner_thread();c=self.c
        link=c.db.execute("SELECT user_id,project FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND active=1",(application,)).fetchall()
        need(len(link)==1 and link[0][1]==application);owner=link[0][0]
        linked=c.db.execute("SELECT user_id FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
        need(linked is not None and linked[0]==owner)
        account=c.db.execute('SELECT verified,epoch FROM accounts WHERE id=?',(owner,)).fetchone()
        realm=c.db.execute('SELECT active,expires FROM projects WHERE id=?',(self.project,)).fetchone()
        need(account is not None and account[0]==1 and realm is not None and realm[0]==1 and realm[1]>c.now())
        actual,meta,platform=self.a.onboarding._load(application,owner,False)
        need(actual==owner and platform['status']!='WITHDRAWN')
        origin=meta.get('ocr_origin');need(origin is None or type(origin)is dict and origin.get('project')==self.project)
        record=self.a._read(application)
        need(WechatApplyment._owner_intent_matches(record,application,owner))
        need(record['owner_submit_confirmation'].get('account_epoch')==account[1])
        need(record['owner_submit_confirmation'].get('project')==self.project)
        code=record.get('business_code');merchant=record.get('provider_sp_mchid')
        need(type(code)is str and re.fullmatch('[A-Za-z0-9_-]{1,64}',code) and merchant==self.a.reader_for_record(record)._mchid)
        return copy.deepcopy(dict(application=application,owner=owner,record=record,meta=meta,platform=platform,
            account=tuple(account),realm=tuple(realm),project=self.project,merchant=merchant,code=code))
    @staticmethod
    def network(reader,binding):
        need(reader._mchid==binding['merchant'])
        return request(reader,'GET','/v3/applyment4sub/applyment/business_code/'+binding['code'],include_verification=True)
    def commit(self,snapshot,result):
        self.owner_thread();application=snapshot['application'];need(self.snapshot(application)==snapshot)
        def reauthorize():
            need(self.snapshot(application)==snapshot);return snapshot['owner']
        return self.a._commit_provider_query(application,snapshot['owner'],snapshot['record'],snapshot['merchant'],
            result,snapshot['owner'],reauthorize,owner_recovery=True,audit_actor='system_owner_submit_recovery')
    def failed(self,snapshot):
        self.owner_thread()
        with self.c.tx():
            need(self.snapshot(snapshot['application'])==snapshot)
            record=copy.deepcopy(snapshot['record'])
            record['owner_recovery_error']='PROVIDER_RECOVERY_UNAVAILABLE';record['owner_recovery_error_at']=self.c.now()
            self.a._save(snapshot['application'],snapshot['owner'],record)
    def service_actions(self):
        self.owner_thread()
        if self.closed:return
        if self.pending:
            snapshot,future=self.pending
            if not future.done():return
            self.pending=None;application=snapshot['application']
            try:self.commit(snapshot,future.result())
            except Exception:
                try:self.failed(snapshot)
                except Exception:pass # no write on revoked binding or changed source
            self.due[application]=time.monotonic()+self.interval
        rows=self.c.db.execute("SELECT subject_idx FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND active=1 ORDER BY subject_idx").fetchall()
        for row in rows:
            application=row[0]
            if self.due.get(application,0)>time.monotonic():continue
            try:snapshot=self.snapshot(application)
            except (PermissionError,ValueError,KeyError,TypeError):
                self.due[application]=time.monotonic()+self.interval;continue
            binding={'merchant':snapshot['merchant'],'code':snapshot['code']}
            self.pending=(snapshot,self.worker.submit(self.network,self.a.reader_for_record(snapshot['record']),binding));break
    def close(self):
        self.owner_thread();self.closed=True
        if self.pending:self.pending[1].cancel()
        self.worker.shutdown(wait=True);self.pending=None
