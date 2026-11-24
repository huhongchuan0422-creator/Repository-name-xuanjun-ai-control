"""Synthetic-only end-to-end seam: real Center entries, real PR122 mapping,
real mail ledger, real Boundary issue/consume, receipt and error read-back.
Frozen provider IO substitutes; no HTTP server, no production binding, no outbound mail.
"""
import hashlib,json,os,sqlite3,tempfile,unittest
from scripts.pr122_customer_core import Center,Denied,canonical
from scripts.pr122_customer_identity import (Boundary,SCHEMA,MAPPING_SCHEMA,SUBJECT,
    EVIDENCE,signature,import_mapping)
from scripts.community_mail_delivery import install,ProviderBinding
_original_connect=sqlite3.connect
sqlite3.connect=lambda path,*a,**k:_original_connect(os.fspath(path),*a,**k)
KEY={'testkey':b'k'*32}
AUTH=b'a'*32
SERVICE=b's'*32
class Transport:
    idempotent_submission=True
    def __init__(self,results=()):self.calls=[];self.results=list(results)
    def authenticated(self,b):return True
    def submit(self,b,message,aid,key):
        self.calls.append((aid,key))
        if self.results:return self.results.pop(0)
        return {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'synthetic-'+aid}
class Chain(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=1800000000
        self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now)
        self.addCleanup(self.c.db.close)
        self.transport=Transport();self.delivery=install(self.c,[ProviderBinding('Resend','synthetic','HTTP','https://api.resend.com',{'daily':100,'monthly':3000},True)],{'Resend':self.transport})
    def enroll(self,address='entry@example.invalid',password='SyntheticPassword123!'):
        self.assertEqual(self.c.register(address,password)['status'],'CHECK_VERIFICATION_CHANNEL')
        row=self.c.db.execute("SELECT * FROM outbox WHERE user_id IN (SELECT id FROM accounts) AND kind='VERIFY' ORDER BY at DESC,rowid DESC LIMIT 1").fetchone()
        uid=row['user_id'];token=json.loads(self.c.decrypt(row['payload'],'outbox:'+row['id']))['token']
        self.c.verify(token,password);self.session=self.c.login(address,password)
        self.assertEqual(uid,self.session['user_id']);return uid,token
    def bind_mapping(self,uid,mapping_id='map-entry'):
        self.c.activity_ready=False
        self.c.db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,1)',('project-a','tenant-a','local-not-domestic',uid,'synthetic-ref',1,self.now+3600,self.c.encrypt(canonical({}),'project:project-a')))
        self.c.db.execute('INSERT INTO members VALUES(?,?,?,1)',('project-a',uid,'OWNER'))
        p=dict(schema=MAPPING_SCHEMA,mapping_id=mapping_id,version=1,status='ACTIVE',user_id=uid,tenant_id='tenant-a',project_id='project-a',domestic_customer_id='domestic-entry',confirmed_by='synthetic-authority',issued_unix=self.now,expires_unix=self.now+1800)
        proofs={}
        for field,kind in EVIDENCE.items():
            raw=canonical(dict(schema='PR122_IDENTITY_EVIDENCE_V1',kind=kind,confirmed_by='synthetic-authority',verified=True,expires_unix=self.now+1800,**{f:p[f] for f in SUBJECT}))
            proofs[field]=raw;p[field]=dict(ref=field,sha256=hashlib.sha256(raw).hexdigest())
        import_mapping(self.c,dict(payload=p,signature=signature(AUTH,MAPPING_SCHEMA,p)),AUTH,['synthetic-authority'],proofs.__getitem__);return p
    def boundary(self):
        self.b=Boundary({'crm-local':dict(key=SERVICE,audience='domestic-crm',operations={'crm.customer.read':['OWNER']})})
    def scope(self,uid,rid='entry-1',**changes):
        d=dict(schema=SCHEMA,request_id=rid,caller='crm-local',audience='domestic-crm',user_id=uid,tenant_id='tenant-a',project_id='project-a',operation='crm.customer.read',issued_unix=self.now,expires_unix=self.now+30)
        d.update(changes);return d
    def issue(self,uid,rid='entry-1'):
        grant=self.b.issue(self.c,self.session['token'],self.session['csrf'],self.scope(uid,rid));grant.pop('store_authorized');return dict(payload=grant,signature=signature(SERVICE,'/customer/center/api/authorization/consume',grant))
    def test_register_mail_verify_mapping_consume_receipt_readback(self):
        uid,_=self.enroll();self.boundary()
        self.assertEqual(self.transport.calls.__len__(),1)
        attempt=self.c.db.execute("SELECT id,provider_ref FROM mail_provider_attempts WHERE message_key IN (SELECT 'outbox:'||id FROM outbox WHERE user_id=?)",(uid,)).fetchone()
        self.assertEqual(self.delivery.record_receipt('Resend',attempt['provider_ref'])['state'],'DELIVERED')
        receipt=self.c.mail_receipt(uid,'VERIFY')
        self.assertEqual((receipt['state'],receipt['detail_code']),('DELIVERED','DELIVERED_RECEIPT'))
        self.assertEqual(set(receipt),{'outbox_id','state','created','provider','attempt_id','updated','detail_code','provider_ref'})
        self.bind_mapping(uid)
        document=self.issue(uid);result=self.b.consume(self.c,document);p=result['payload']
        self.assertEqual((p['user_id'],p['tenant_id'],p['project_id'],p['domestic_customer_id']),(uid,'tenant-a','project-a','domestic-entry'))
        self.assertEqual(result['signature'],signature(SERVICE,SCHEMA+':response',p))
        self.assertFalse(p['store_authorized'])
        with self.assertRaises(Denied):self.b.consume(self.c,document)
        self.assertIsNone(self.c.mail_receipt(uid,'RESET'))
        with self.assertRaises(Denied):self.b.issue(self.c,self.session['token'],self.session['csrf'],self.scope(uid,'wrong',tenant_id='tenant-b'))
    def test_provider_rejection_returns_controlled_error_then_retry(self):
        self.transport.results=[{'outcome':'DEFINITE_REJECTED','detail_code':'PROVIDER_REJECTED','provider_ref':None},
                                {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'retry-1'}]
        uid,_=self.enroll()
        first=self.c.mail_receipt(uid,'VERIFY')
        self.assertEqual((first['state'],first['detail_code']),('DEFINITE_REJECTED','PROVIDER_REJECTED'))
        self.c.request_reset('entry@example.invalid')
        row=self.c.db.execute("SELECT id FROM outbox WHERE user_id=? AND kind='RESET'",(uid,)).fetchone()
        self.assertEqual(self.transport.calls.__len__(),2)
        second=self.c.mail_receipt(uid,'RESET')
        self.assertEqual((second['state'],second['detail_code']),('ACCEPTED','ACCEPTED_BY_PROVIDER'))
        self.assertNotIn('email',json.dumps(second));self.assertNotIn('token',json.dumps(second))
    def test_reset_invalidates_old_grant_keeps_same_domestic_user(self):
        uid,_=self.enroll();self.boundary();self.bind_mapping(uid)
        old=self.issue(uid);self.c.request_reset('entry@example.invalid')
        row=self.c.db.execute("SELECT * FROM outbox WHERE kind='RESET' ORDER BY at DESC,rowid DESC LIMIT 1").fetchone()
        self.assertEqual(row['user_id'],uid)
        token=json.loads(self.c.decrypt(row['payload'],'outbox:'+row['id']))['token'];self.c.reset(token,'ChangedPassword123!')
        with self.assertRaises(Denied):self.b.consume(self.c,old)
        self.session=self.c.login('entry@example.invalid','ChangedPassword123!');self.assertEqual(self.session['user_id'],uid)
        p=self.b.consume(self.c,self.issue(uid,'after-reset'))['payload']
        self.assertEqual(p['domestic_customer_id'],'domestic-entry');self.assertEqual(p['user_id'],uid)
        self.assertEqual(self.transport.calls.__len__(),2)
        self.assertEqual(self.c.mail_receipt(uid,'RESET')['state'],'ACCEPTED')
if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Chain))
    print('ORIGINAL_ENTRY_CHAIN; SYNTHETIC_ACCOUNTS_PROJECT_TRANSPORT; NO_HTTP_SERVER; NO_PRODUCTION_BINDING; NO_OUTBOUND')
    raise SystemExit(0 if r.wasSuccessful() else 1)

class MappingRules(unittest.TestCase):
    """PR122_IDENTITY_MAPPING_V1 rejection rules through the actual import entry."""
    chain=None
    def setUp(self):self.inner=Chain('test_register_mail_verify_mapping_consume_receipt_readback');self.inner.setUp();self.addCleanup(self.inner.tmp.cleanup)
    def test_exact_triple_and_rejections(self):
        uid,_=self.inner.enroll();p=self.inner.bind_mapping(uid)
        self.assertEqual(p['domestic_customer_id'],'domestic-entry')
        bad=dict(p,mapping_id='map-b',email_extra='x');
        with self.assertRaises(Exception):import_mapping(self.inner.c,dict(payload=bad,signature=signature(AUTH,MAPPING_SCHEMA,bad)),AUTH,['synthetic-authority'],lambda r:hashlib.sha256(b'').hexdigest() and b'')
        q=dict(p,mapping_id='map-c');q['domestic_customer_id']='domestic-other'
        with self.assertRaises(Exception):import_mapping(self.inner.c,dict(payload=q,signature=signature(AUTH,MAPPING_SCHEMA,q)),AUTH,['synthetic-authority'],lambda r:hashlib.sha256(b'').hexdigest() and b'')
        v=dict(p,version=2,domestic_customer_id='domestic-entry');v.pop('expires_unix');v['expires_unix']=self.inner.now+1800
        for field in EVIDENCE:
            raw=canonical(dict(schema='PR122_IDENTITY_EVIDENCE_V1',kind=EVIDENCE[field],confirmed_by='synthetic-authority',verified=True,expires_unix=self.inner.now+1800,**{f:v[f] for f in SUBJECT}))
            v[field]=dict(ref=field,sha256=hashlib.sha256(raw).hexdigest())
        proofs={field:raw for field in EVIDENCE for raw in [canonical(dict(schema='PR122_IDENTITY_EVIDENCE_V1',kind=EVIDENCE[field],confirmed_by='synthetic-authority',verified=True,expires_unix=self.inner.now+1800,**{f:v[f] for f in SUBJECT}))]}
        import_mapping(self.inner.c,dict(payload=v,signature=signature(AUTH,MAPPING_SCHEMA,v)),AUTH,['synthetic-authority'],proofs.__getitem__)
        w=dict(v,version=3,user_id='someone-else')
        with self.assertRaises(Exception):import_mapping(self.inner.c,dict(payload=w,signature=signature(AUTH,MAPPING_SCHEMA,w)),AUTH,['synthetic-authority'],proofs.__getitem__)
