"""Frozen mail contract: all provider IO uses isolated substitutes."""
import hashlib,json,multiprocessing,os,sqlite3,tempfile,unittest
from email.message import Message
from scripts.pr122_customer_core import Center,Unavailable
from scripts.community_mail_delivery import (MailDelivery,ProviderBinding,ProviderHTTPTransport,ProviderSMTPTransport,RESEND_CEILINGS,build_mail_configuration,install)
from scripts.community_web_session import WebSession
_original_connect=sqlite3.connect
sqlite3.connect=lambda path,*a,**k:_original_connect(os.fspath(path),*a,**k)
KEY={'testkey':b'k'*32}
ENDPOINTS={'Resend':'https://api.resend.com','SMTP2GO':'https://api.smtp2go.com','Brevo':'https://api.brevo.com'}
class FakeTransport:
    def __init__(self,*results,reconcile=None):self.results=list(results);self.reconcile_result=reconcile or {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'};self.submissions=[];self.reconciliations=[]
    def authenticated(self,binding):return True
    def submit(self,binding,message,attempt_id):
        self.submissions.append((binding.provider,message,attempt_id));result=self.results.pop(0) if self.results else {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':binding.provider+'-'+attempt_id}
        if isinstance(result,BaseException):raise result
        return result
    def reconcile(self,binding,provider_ref,attempt_id):self.reconciliations.append((binding.provider,attempt_id));return self.reconcile_result
class Response:
    def __init__(self,value):self.value=value
    def read(self):return json.dumps(self.value).encode()
class FakeSMTP:
    def __init__(self,events):self.events=events
    def ehlo(self):self.events.append('EHLO')
    def starttls(self,context=None):self.events.append(('STARTTLS',context is not None))
    def login(self,user,password):self.events.append(('LOGIN',bool(user),bool(password)))
    def send_message(self,message):self.events.append(('SEND',message['Message-ID']));return {}
    def quit(self):self.events.append('QUIT')
def binding(provider='Resend',account=None,limits=None,scope='center-default',pool=None,transport='HTTP',endpoint=None):
    limits=limits or {'daily':100,'monthly':3000};return ProviderBinding(provider,account or provider.lower()+'-account',transport,endpoint or ENDPOINTS[provider],limits,True,scope,pool or limits,'sender@example.org')
def worker(dbpath,index,provider,queue):
    db=sqlite3.connect(dbpath,isolation_level=None,timeout=15);db.row_factory=sqlite3.Row;b=binding(provider,limits={'daily':100,'monthly':3000},scope='shared-pool',pool={'daily':10});t=FakeTransport();d=MailDelivery(db,[b],{provider:t});queue.put(d.send('worker-'+str(index),{'email':'x@example.org','kind':'VERIFY','code':'x'})['state']);db.close()
class Contract(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.now=1794000000;self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now)
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def configured(self,bindings=None,transports=None):
        bindings=bindings or [binding()];transports=transports or {b.provider:FakeTransport() for b in bindings};return install(self.c,bindings,transports),transports
    def outbox(self,kind):
        row=self.c.db.execute('SELECT * FROM outbox WHERE kind=? ORDER BY rowid DESC LIMIT 1',(kind,)).fetchone();return row,json.loads(self.c.decrypt(row['payload'],'outbox:'+row['id']))
    def account(self,password='InitialPassword123!'):
        self.c.register('person@example.org',password);row,payload=self.outbox('VERIFY');self.c.verify(payload['token'],password);return self.c.login('person@example.org',password)
    def test_unconfigured_not_ready_no_send_and_migration_preserves_identity(self):
        self.c.mail_ready=True;self.c.register('legacy@example.org','InitialPassword123!');row,payload=self.outbox('VERIFY');self.c.verify(payload['token'],'InitialPassword123!');uid=self.c.login('legacy@example.org','InitialPassword123!')['user_id'];d=install(self.c);self.assertFalse(d.ready);self.assertEqual(set(d.provider_state.values()),{'NOT_CONFIGURED'});self.assertFalse(self.c.mail_ready);self.assertEqual(self.c.login('legacy@example.org','InitialPassword123!')['user_id'],uid)
        with self.assertRaisesRegex(Unavailable,'VERIFICATION_CHANNEL_PENDING'):self.c.register('none@example.org','InitialPassword123!')
    def test_v1_reservations_migrate_into_account_and_shared_pool_events(self):
        self.c.db.executescript("CREATE TABLE mail_provider_attempts(id TEXT PRIMARY KEY,message_key TEXT NOT NULL,provider TEXT NOT NULL,account_id TEXT NOT NULL,outcome TEXT NOT NULL,provider_ref TEXT,detail TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL);CREATE TABLE mail_reservations(attempt_id TEXT NOT NULL,provider TEXT NOT NULL,account_id TEXT NOT NULL,window_name TEXT NOT NULL,window_start INTEGER NOT NULL,state TEXT NOT NULL,PRIMARY KEY(attempt_id,window_name,window_start));");self.c.db.execute("INSERT INTO mail_provider_attempts VALUES('old','old-message','Resend','resend-account','ACCEPTED','old-ref','legacy',?,?)",(self.now,self.now));self.c.db.execute("INSERT INTO mail_reservations VALUES('old','Resend','resend-account','daily',?,'COUNTED')",(self.now,));install(self.c,[binding('Resend',account='resend-account',scope='shared')],{'Resend':FakeTransport()});events=self.c.db.execute("SELECT quota_kind,scope_key,state FROM mail_quota_events WHERE attempt_id='old' ORDER BY quota_kind").fetchall();self.assertEqual([(r[0],r[1],r[2]) for r in events],[('ACCOUNT','Resend:resend-account','COUNTED'),('POOL','shared','COUNTED')]);self.assertEqual(self.c.db.execute("SELECT v FROM settings WHERE k='mail_schema_version'").fetchone()[0],'2')
    def test_same_code_no_expiry_extension_and_identity_flows(self):
        self.configured();self.c.register('person@example.org','InitialPassword123!');r1,p1=self.outbox('VERIFY');token_hash=hashlib.sha256(p1['token'].encode()).hexdigest();e1=self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(token_hash,)).fetchone()[0];self.now+=300;self.c.register('person@example.org','OtherPassword123!');r2,p2=self.outbox('VERIFY');self.assertEqual((p1['token'],e1),(p2['token'],self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(token_hash,)).fetchone()[0]));self.now=e1;self.c.register('person@example.org','OtherPassword123!');_,p3=self.outbox('VERIFY');self.assertNotEqual(p1['token'],p3['token']);self.c.verify(p3['token'],'InitialPassword123!');session=self.c.login('person@example.org','InitialPassword123!');self.c.request_reset('person@example.org');_,reset1=self.outbox('RESET');expiry=self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(hashlib.sha256(reset1['token'].encode()).hexdigest(),)).fetchone()[0];self.now+=1;self.c.request_reset('person@example.org');_,reset2=self.outbox('RESET');self.assertEqual(reset1['token'],reset2['token']);self.assertEqual(expiry,self.c.db.execute('SELECT expires FROM challenges WHERE token=?',(hashlib.sha256(reset2['token'].encode()).hexdigest(),)).fetchone()[0]);self.c.reset(reset2['token'],'ResetPassword123!');service=WebSession(self.c);result,cookie=service.dispatch('/community/session/login',Message(),{'email':'person@example.org','password':'ResetPassword123!'},'fixture');headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf'];service.dispatch('/community/session/password',headers,{'current_password':'ResetPassword123!','new_password':'ChangedPassword123!'},'fixture');self.assertEqual(self.c.login('person@example.org','ChangedPassword123!')['user_id'],session['user_id'])
    def test_shared_pool_blocks_cross_provider_bypass_but_independent_pool_switches(self):
        same=[binding('Resend',limits={'daily':100,'monthly':3000},scope='same',pool={'daily':10}),binding('Brevo',limits={'daily':100},scope='same',pool={'daily':10})];ts={'Resend':FakeTransport(),'Brevo':FakeTransport()};d,_=self.configured(same,ts)
        for i in range(9):self.assertEqual(d.send('same-'+str(i),{'n':i})['provider'],'Resend')
        self.assertEqual(d.send('same-blocked',{})['state'],'UNAVAILABLE');self.assertEqual(len(ts['Brevo'].submissions),0)
        self.c.db.close();self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory();self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now);ind=[binding('Resend',limits={'daily':10,'monthly':3000},scope='primary',pool={'daily':100}),binding('Brevo',limits={'daily':100},scope='backup',pool={'daily':100})];d,_=self.configured(ind,{'Resend':FakeTransport(),'Brevo':FakeTransport()})
        for i in range(9):self.assertEqual(d.send('ind-'+str(i),{})['provider'],'Resend')
        self.assertEqual(d.send('ind-switch',{})['provider'],'Brevo')
    def test_resend_production_ceilings_and_true_rolling_boundary(self):
        b=binding('Resend',limits={'daily':1000,'monthly':10000,'rolling:10':10},scope='rolling',pool={'daily':10000,'monthly':10000,'rolling:10':100});d,_=self.configured([b],{'Resend':FakeTransport()});self.assertEqual(d._ceiling(b,'daily',1000,'ACCOUNT'),90);self.assertEqual(d._ceiling(b,'monthly',10000,'ACCOUNT'),2700);self.assertEqual(RESEND_CEILINGS,{'daily':90,'monthly':2700})
        with self.assertRaisesRegex(ValueError,'RESEND_DAILY_MONTHLY'):binding('Resend',limits={'rolling:10':10})
        for i in range(9):self.now=1794000000+i;self.assertEqual(d.send('roll-'+str(i),{})['state'],'ACCEPTED')
        self.now=1794000009;self.assertEqual(d.send('roll-block',{})['state'],'UNAVAILABLE');self.now=1794000010;self.assertEqual(d.send('roll-open',{})['state'],'ACCEPTED')
    def test_cross_provider_multi_process_pool_is_atomic(self):
        install(self.c);dbpath=os.path.join(self.tmp.name,'center.sqlite');ctx=multiprocessing.get_context('fork');q=ctx.Queue();ps=[ctx.Process(target=worker,args=(dbpath,i,'Resend' if i%2==0 else 'Brevo',q)) for i in range(12)]
        for p in ps:p.start()
        for p in ps:p.join(20);self.assertEqual(p.exitcode,0)
        states=[q.get(timeout=2) for p in ps];self.assertEqual(states.count('ACCEPTED'),9);self.assertEqual(states.count('UNAVAILABLE'),3)
    def test_not_submitted_releases_and_retries_or_switches_without_string_429(self):
        primary=FakeTransport({'outcome':'NOT_SUBMITTED','detail_code':'AUTH_FAILED'});backup=FakeTransport();d,_=self.configured([binding('Resend',scope='a'),binding('SMTP2GO',scope='b')],{'Resend':primary,'SMTP2GO':backup});self.assertEqual(d.send('fallback',{})['provider'],'SMTP2GO');self.assertEqual(self.c.db.execute("SELECT count(*) FROM mail_quota_events WHERE state='RELEASED'").fetchone()[0],4)
        self.c.db.close();self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory();self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now);single=FakeTransport({'outcome':'NOT_SUBMITTED','detail_code':'AUTH_FAILED'},{'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'retry'});d,_=self.configured([binding()],{'Resend':single});self.assertEqual(d.send('retry',{})['state'],'UNAVAILABLE');self.assertEqual(d.send('retry',{})['state'],'ACCEPTED');self.assertEqual(len(single.submissions),2)
    def test_reconciled_not_submitted_releases_then_switches_backup(self):
        first=binding('Resend',scope='primary');second=binding('Brevo',scope='backup');primary=FakeTransport(reconcile={'outcome':'NOT_SUBMITTED','detail_code':'RECONCILED_NOT_SUBMITTED'});backup=FakeTransport();d,_=self.configured([first,second],{'Resend':primary,'Brevo':backup});aid,_=d._reserve('reconciled-switch',hashlib.sha256(b'{}').hexdigest(),first,self.now);self.assertEqual(d.reconcile(aid)['state'],'NOT_SUBMITTED');result=d.send('reconciled-switch',{});self.assertEqual(result['provider'],'Brevo');self.assertEqual(len(backup.submissions),1);self.assertEqual(set(r[0] for r in self.c.db.execute("SELECT state FROM mail_quota_events WHERE attempt_id=?",(aid,))),{'RELEASED'})
    def test_inflight_crash_restart_reconciliation_and_delivered_terminal(self):
        b=binding();t=FakeTransport(reconcile={'outcome':'NOT_SUBMITTED','detail_code':'RECONCILED_NOT_SUBMITTED'});d,_=self.configured([b],{'Resend':t});aid,_=d._reserve('crash',hashlib.sha256(b'{}').hexdigest(),b,self.now);self.assertEqual(d._result('crash')['state'],'INFLIGHT');self.c.db.close();self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now);t2=FakeTransport(reconcile={'outcome':'NOT_SUBMITTED','detail_code':'RECONCILED_NOT_SUBMITTED'});d2=install(self.c,[b],{'Resend':t2});self.assertEqual(d2.send('crash',{})['state'],'INFLIGHT');self.assertEqual(t2.submissions,[]);self.assertEqual(d2.reconcile(aid)['state'],'NOT_SUBMITTED');t2.results=[{'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'receipt-1'}];accepted=d2.send('crash',{});self.assertEqual(accepted['state'],'ACCEPTED');delivered=d2.record_receipt('Resend','receipt-1');self.assertEqual(delivered['state'],'DELIVERED');self.assertEqual(self.c.db.execute('SELECT outcome FROM mail_provider_attempts WHERE id=?',(delivered['attempt_id'],)).fetchone()[0],'DELIVERED')
    def test_timeout_unknown_never_cross_provider_and_same_provider_reconciles_delivered(self):
        primary=FakeTransport(TimeoutError(),reconcile={'outcome':'DELIVERED','detail_code':'DELIVERED_RECEIPT','provider_ref':'same-provider'});backup=FakeTransport();d,_=self.configured([binding('Resend',scope='p'),binding('Brevo',scope='b')],{'Resend':primary,'Brevo':backup});result=d.send('unknown',{});self.assertEqual(result['state'],'UNKNOWN');self.assertEqual(backup.submissions,[]);self.assertEqual(d.reconcile(result['attempt_id'])['state'],'DELIVERED');self.assertEqual(primary.reconciliations[0][0],'Resend');self.assertEqual(self.c.db.execute('SELECT outcome FROM mail_provider_attempts WHERE id=?',(result['attempt_id'],)).fetchone()[0],'DELIVERED')
    def test_definite_reject_is_terminal_and_counted(self):
        t=FakeTransport({'outcome':'DEFINITE_REJECTED','detail_code':'PROVIDER_REJECTED'});d,_=self.configured(transports={'Resend':t});result=d.send('reject',{});self.assertEqual(result['state'],'DEFINITE_REJECTED');self.assertEqual(set(r[0] for r in self.c.db.execute('SELECT state FROM mail_quota_events WHERE attempt_id=?',(result['attempt_id'],))),{'COUNTED'});self.assertEqual(len(t.submissions),1);self.assertEqual(d.send('reject',{})['state'],'DEFINITE_REJECTED');self.assertEqual(len(t.submissions),1)
    def test_provider_ref_unique_and_detail_is_controlled_digest_only(self):
        t=FakeTransport({'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'duplicate'},{'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'duplicate','detail':'Bearer secret body'});d,_=self.configured(transports={'Resend':t});d.send('one',{})
        with self.assertRaises(sqlite3.IntegrityError):d.send('two',{})
        row=self.c.db.execute("SELECT detail,detail_sha256 FROM mail_provider_attempts WHERE message_key='one'").fetchone();self.assertEqual(row['detail'],'ACCEPTED_BY_PROVIDER');self.assertEqual(row['detail_sha256'],hashlib.sha256(b'ACCEPTED_BY_PROVIDER').hexdigest());self.assertNotIn('secret',json.dumps(dict(row)))
    def test_http_adapter_real_contract_and_ssrf_allowlist(self):
        calls=[]
        def opener(request,timeout):
            calls.append((request.full_url,request.get_method(),timeout,sorted(request.headers)))
            if request.full_url.endswith('/domains?limit=1'):return Response({'data':[]})
            if request.full_url.endswith('/emails'):return Response({'id':'resend-ref'})
            return Response({'status':'delivered'})
        config={'version':1,'endpoint_allowlist':['https://api.resend.com'],'bindings':[{'provider':'Resend','account_id':'r1','transport':'HTTP','endpoint':'https://api.resend.com','quota_scope':'rpool','from_address':'sender@example.org','secret_ref':'secret://resend'}]}
        resolver=lambda ref,p,a:{'secret':'fixture-secret','limits':{'daily':100,'monthly':3000},'pool_limits':{'daily':100,'monthly':3000}}
        bs,ts=build_mail_configuration(config,resolver,opener);d=MailDelivery(self.c.db,bs,ts,clock=lambda:self.now);self.assertEqual(d.send('http',{'email':'x@example.org','kind':'VERIFY','code':'123'})['provider'],'Resend');self.assertTrue(any(url.endswith('/emails') for url,method,timeout,headers in calls));self.assertFalse(any('fixture-secret' in json.dumps(call) for call in calls))
        def brevo_opener(request,timeout):
            if request.full_url.endswith('/v3/account'):return Response({'email':'fixture'})
            return Response({'messageId':'brevo-ref'})
        brevo={'version':1,'endpoint_allowlist':['https://api.brevo.com'],'bindings':[{'provider':'Brevo','account_id':'b1','transport':'HTTP','endpoint':'https://api.brevo.com','quota_scope':'bpool','from_address':'sender@example.org','secret_ref':'secret://brevo'}]};bbs,bts=build_mail_configuration(brevo,resolver,brevo_opener);bd=MailDelivery(self.c.db,bbs,bts,clock=lambda:self.now);self.assertEqual(bd.send('brevo-http',{'email':'x@example.org','kind':'RESET','code':'123'})['provider'],'Brevo')
        bad=dict(config);bad['endpoint_allowlist']=['https://127.0.0.1'];bad['bindings']=[dict(config['bindings'][0],endpoint='https://127.0.0.1')]
        with self.assertRaises(ValueError):build_mail_configuration(bad,resolver,opener)
    def test_smtp_465_implicit_tls_and_587_starttls_certificate_context(self):
        for endpoint,expected_starttls in [('smtp.smtp2go.com:465',False),('smtp.smtp2go.com:587',True)]:
            events=[]
            def factory(host,port,**kwargs):events.append(('CONNECT',port,kwargs.get('context') is not None));return FakeSMTP(events)
            transport=ProviderSMTPTransport('SMTP2GO',endpoint,'user','password',[endpoint],factory);transport.authenticate();b=binding('SMTP2GO',transport='SMTP',endpoint=endpoint);result=transport.submit(b,{'email':'x@example.org','kind':'VERIFY','code':'123'},'aid');self.assertEqual(result['outcome'],'ACCEPTED');self.assertEqual(any(x[0]=='STARTTLS' for x in events if isinstance(x,tuple)),expected_starttls);connect=next(x for x in events if isinstance(x,tuple) and x[0]=='CONNECT');self.assertEqual(connect[2],not expected_starttls)
if __name__=='__main__':unittest.main()
