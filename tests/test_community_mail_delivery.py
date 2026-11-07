"""Frozen mail routing contract tests; all transports are isolated fakes."""
import json,multiprocessing,tempfile,unittest,sqlite3,os
_sqlite_connect=sqlite3.connect
sqlite3.connect=lambda path,*args,**kwargs:_sqlite_connect(os.fspath(path),*args,**kwargs)
from email.message import Message
from scripts.pr122_customer_core import Center,Unavailable
from scripts.community_mail_delivery import MailDelivery,ProviderBinding,UNCONFIGURED_RESEND_TEST_BASELINE,install
from scripts.community_web_session import WebSession
KEY={'testkey':b'k'*32}
class FakeTransport:
    def __init__(self,*results,reconcile=None):self.results=list(results);self.reconcile_result=reconcile or {'outcome':'UNKNOWN'};self.submissions=[];self.reconciliations=[]
    def authenticated(self,binding):return True
    def submit(self,binding,message,attempt_id):
        self.submissions.append((binding.provider,message,attempt_id));result=self.results.pop(0) if self.results else {'outcome':'ACCEPTED','provider_ref':'ref-'+attempt_id}
        if isinstance(result,BaseException):raise result
        return result
    def reconcile(self,binding,provider_ref,attempt_id):self.reconciliations.append((binding.provider,attempt_id));return self.reconcile_result
def binding(provider='Resend',daily=100,monthly=3000,extra=None):
    limits={'daily':daily,'monthly':monthly};limits.update(extra or {});return ProviderBinding(provider,provider.lower()+'-account','HTTP','https://fixture.invalid:443',limits,True)
def quota_worker(root,index,queue):
    db=sqlite3.connect(os.path.join(root,'center.sqlite'),isolation_level=None,timeout=15);db.row_factory=sqlite3.Row;t=FakeTransport();d=MailDelivery(db,[binding(daily=10,monthly=100)],{'Resend':t});queue.put(d.send('concurrent-'+str(index),{'n':index})['state']);db.close()
class MailContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1794000000;self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now)
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def configured(self,bindings=None,transports=None):
        bindings=bindings or [binding()];transports=transports or {b.provider:FakeTransport() for b in bindings};return install(self.c,bindings,transports),transports
    def outbox(self,kind):
        r=self.c.db.execute('SELECT * FROM outbox WHERE kind=? ORDER BY rowid DESC LIMIT 1',(kind,)).fetchone();return r,json.loads(self.c.decrypt(r['payload'],'outbox:'+r['id']))
    def account(self,address='person@example.org',password='InitialPassword123!'):
        self.c.register(address,password);row,payload=self.outbox('VERIFY');self.c.verify(payload['token'],password);return self.c.login(address,password)
    def test_backward_compatible_migration_preserves_existing_identity(self):
        self.c.mail_ready=True;self.c.register('legacy@example.org','InitialPassword123!');row,payload=self.outbox('VERIFY');self.c.verify(payload['token'],'InitialPassword123!');uid=self.c.login('legacy@example.org','InitialPassword123!')['user_id'];d=install(self.c);self.assertFalse(d.ready);self.assertEqual(self.c.login('legacy@example.org','InitialPassword123!')['user_id'],uid);tables={r[0] for r in self.c.db.execute("SELECT name FROM sqlite_master WHERE type='table'")};self.assertIn('mail_provider_attempts',tables);self.assertIn('mail_quota_windows',tables)
    def test_not_configured_is_not_ready_and_never_sends(self):
        d=install(self.c);self.assertFalse(d.ready);self.assertEqual(set(d.provider_state.values()),{'NOT_CONFIGURED'});self.assertFalse(self.c.mail_ready)
        with self.assertRaisesRegex(Unavailable,'VERIFICATION_CHANNEL_PENDING'):self.c.register('a@example.org','InitialPassword123!')
    def test_binding_requires_authenticated_443_or_smtp_465_587_and_limit_readback(self):
        for args in [('Resend','a','HTTP','http://bad',{'daily':100},True),('Brevo','a','SMTP','smtp.invalid:25',{'monthly':2},True),('SMTP2GO','a','SMTP','smtp.invalid:587',{},True)]:
            with self.assertRaises(ValueError):ProviderBinding(*args)
        self.assertEqual(ProviderBinding('Brevo','a','SMTP','smtp.invalid:465',{'daily':1},True).transport,'SMTP');self.assertEqual(UNCONFIGURED_RESEND_TEST_BASELINE,{'daily':100,'monthly':3000});self.assertEqual({k:int(v*.9) for k,v in UNCONFIGURED_RESEND_TEST_BASELINE.items()},{'daily':90,'monthly':2700})
    def test_register_resend_same_code_and_expiry_then_new_after_expiry(self):
        self.configured();self.c.register('same@example.org','InitialPassword123!');r1,p1=self.outbox('VERIFY');e1=self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(self.c._mail_canonical and __import__('hashlib').sha256(p1['token'].encode()).hexdigest(),)).fetchone()[0]
        self.now+=300;self.c.register('same@example.org','DifferentPassword123!');r2,p2=self.outbox('VERIFY');e2=self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(__import__('hashlib').sha256(p2['token'].encode()).hexdigest(),)).fetchone()[0]
        self.assertEqual(p1['token'],p2['token']);self.assertEqual(e1,e2);self.assertEqual(e1,1794000600)
        self.now=e1;self.c.register('same@example.org','DifferentPassword123!');_,p3=self.outbox('VERIFY');self.assertNotEqual(p1['token'],p3['token'])
    def test_login_reset_and_change_password_revoke_sessions(self):
        self.configured();session=self.account();self.c.request_reset('person@example.org');r1,p1=self.outbox('RESET');e1=self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(__import__('hashlib').sha256(p1['token'].encode()).hexdigest(),)).fetchone()[0]
        self.now+=100;self.c.request_reset('person@example.org');_,p2=self.outbox('RESET');self.assertEqual(p1['token'],p2['token']);self.assertEqual(e1,self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(__import__('hashlib').sha256(p2['token'].encode()).hexdigest(),)).fetchone()[0])
        self.c.reset(p2['token'],'ResetPassword123!');self.assertEqual(self.c.login('person@example.org','ResetPassword123!')['user_id'],session['user_id'])
        service=WebSession(self.c);result,cookie=service.dispatch('/community/session/login',Message(),{'email':'person@example.org','password':'ResetPassword123!'},'fixture');headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf'];service.dispatch('/community/session/password',headers,{'current_password':'ResetPassword123!','new_password':'ChangedPassword123!'},'fixture')
        with self.assertRaises(PermissionError):self.c.session(cookie.split('=',1)[1].split(';')[0]);self.assertEqual(self.c.login('person@example.org','ChangedPassword123!')['user_id'],session['user_id'])
    def test_daily_boundary_and_any_window_switch_to_backup(self):
        bs=[binding('Brevo',100,100),binding('Resend',10,100)];ts={p:FakeTransport() for p in ('Resend','Brevo')};d,_=self.configured(bs,ts)
        for i in range(9):self.assertEqual(d.send('d'+str(i),{'i':i})['provider'],'Resend')
        self.assertEqual(d.send('boundary',{})['provider'],'Brevo')
        self.c.db.execute('DELETE FROM mail_idempotency');self.c.db.execute('DELETE FROM mail_provider_attempts');self.c.db.execute('DELETE FROM mail_reservations');self.c.db.execute('DELETE FROM mail_quota_windows');d.bindings=tuple(sorted([binding('Resend',100,2),binding('Brevo',100,100)],key=lambda b:('Resend','SMTP2GO','Brevo').index(b.provider)))
        self.assertEqual(d.send('m1',{})['provider'],'Resend');self.assertEqual(d.send('m2',{})['provider'],'Brevo')
    def test_429_falls_back_timeout_stays_unknown_and_reconciles_same_provider(self):
        bs=[binding('Resend'),binding('SMTP2GO')];primary=FakeTransport({'outcome':'429'});backup=FakeTransport();d,_=self.configured(bs,{'Resend':primary,'SMTP2GO':backup});self.assertEqual(d.send('rate',{})['provider'],'SMTP2GO');self.assertEqual(len(backup.submissions),1)
        primary.results=[TimeoutError()];result=d.send('timeout',{});self.assertEqual(result['state'],'UNKNOWN');self.assertEqual(len(backup.submissions),1);primary.reconcile_result={'outcome':'DELIVERED'};self.assertEqual(d.reconcile_unknown(result['attempt_id'])['state'],'DELIVERED');self.assertEqual(primary.reconciliations[0][0],'Resend')
    def test_repeated_definite_not_submitted_can_retry_without_attempt_collision(self):
        t=FakeTransport({'outcome':'429'},{'outcome':'429'},{'outcome':'ACCEPTED','provider_ref':'ok'});d,_=self.configured(transports={'Resend':t});self.assertEqual(d.send('retryable',{})['state'],'UNAVAILABLE');self.assertEqual(d.send('retryable',{})['state'],'UNAVAILABLE');self.assertEqual(d.send('retryable',{})['state'],'ACCEPTED');self.assertEqual(self.c.db.execute("SELECT count(*) FROM mail_provider_attempts WHERE message_key='retryable'").fetchone()[0],3);self.assertEqual(self.c.db.execute("SELECT count(*) FROM mail_reservations WHERE state='RELEASED'").fetchone()[0],4)
    def test_reject_is_distinct_and_only_not_submitted_releases(self):
        t=FakeTransport({'outcome':'DEFINITE_REJECTED','detail':'policy'});d,_=self.configured(transports={'Resend':t});r=d.send('reject',{});self.assertEqual(r['state'],'DEFINITE_REJECTED');self.assertEqual(self.c.db.execute("SELECT DISTINCT state FROM mail_reservations WHERE attempt_id=?",(r['attempt_id'],)).fetchone()[0],'COUNTED')
    def test_accepted_becomes_delivered_only_from_receipt_and_is_idempotent(self):
        t=FakeTransport({'outcome':'ACCEPTED','provider_ref':'provider-1'});d,_=self.configured(transports={'Resend':t});r=d.send('once',{'x':1});self.assertEqual(r['state'],'ACCEPTED');self.assertEqual(d.send('once',{'x':1})['state'],'ACCEPTED');self.assertEqual(len(t.submissions),1);self.assertEqual(d.record_receipt('Resend','provider-1')['state'],'DELIVERED')
    def test_restart_preserves_unknown_attempt_and_no_duplicate_submission(self):
        t=FakeTransport(TimeoutError());d,_=self.configured(transports={'Resend':t});r=d.send('crash',{});aid=r['attempt_id'];self.c.db.close();self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now);t2=FakeTransport(reconcile={'outcome':'ACCEPTED','provider_ref':'same'});d2=install(self.c,[binding()],{'Resend':t2});self.assertEqual(d2.send('crash',{})['state'],'UNKNOWN');self.assertEqual(t2.submissions,[]);self.assertEqual(d2.reconcile_unknown(aid)['state'],'ACCEPTED');self.assertEqual(t2.reconciliations[0][0],'Resend')
    def test_multi_process_global_atomic_reservation(self):
        self.c.db.close();self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now);install(self.c);self.c.db.close();ctx=multiprocessing.get_context('fork');q=ctx.Queue();ps=[ctx.Process(target=quota_worker,args=(self.tmp.name,i,q)) for i in range(12)]
        for p in ps:p.start()
        for p in ps:p.join(20);self.assertEqual(p.exitcode,0)
        states=[q.get(timeout=2) for _ in ps];self.assertEqual(states.count('ACCEPTED'),9);self.assertEqual(states.count('UNAVAILABLE'),3);self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now)
if __name__=='__main__':unittest.main()
