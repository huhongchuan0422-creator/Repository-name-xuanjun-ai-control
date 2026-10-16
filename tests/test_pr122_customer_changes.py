import unittest
import json
import copy
import hashlib
import hmac
from tests.test_pr122_customer_center import CustomerTests
from tests.test_pr122_customer_http import HttpTests
from scripts.pr122_customer_http import COOKIE
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_core import Denied, Conflict
from scripts.pr122_customer_core import canonical,digest
from scripts.pr122_customer_change_authority import import_snapshot
from tests.pr122_customer_change_fixture import seed,doc,snapshot,PAGE_SHA


class ChangeTests(unittest.TestCase):
    imported=CustomerTests.imported
    # Reuse the exact authenticated identity/authority fixture, not its tests.
    def setUp(self):
        CustomerTests.setUp(self);self.service=Changes(self.c);self.sha=PAGE_SHA;self.path='/project/consumer/';seed(self,documents=[doc(self)])

    def request(self,intent='RECTIFICATION'):return self.service.submit(self.owner,'project-a',self.path,self.sha,'把按钮移动到页面底部',intent)
    def quote(self,request,category='NEW_SCOPE',evidence=None):return self.service.assess(self.reviewer,'project-a',request['id'],request['revision'],category,120,[{'description':'新增交互与回归测试','cny_minor':20000,'usd_minor':3000}],evidence or [],'已评估页面、相关角色和回归工作量')

    def test_change_private_and_revocation(self):
        self.request()
        with self.assertRaises(Denied):self.service.list(self.other,'project-a')
        self.imported(2,[])
        with self.assertRaises(Denied):self.service.list(self.owner,'project-a')

    def test_unknown_or_missing_prior_evidence_cannot_blame_or_charge(self):
        q=self.quote(self.request(),'CLIENT_CHANGE');self.assertEqual(q['state'],'NEEDS_EVIDENCE');self.assertEqual(q['lines'],[])
        with self.assertRaises(Conflict):self.service.respond(self.owner,'project-a',q['id'],q['revision'],'CONFIRM','同意')

    def test_prior_requirement_shows_actual_customer_actor_time_and_hash(self):
        base=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1')
        q=self.quote(self.request(),'CLIENT_CHANGE',[base['event_id']]);self.assertEqual(q['state'],'QUOTED')
        proof=q['evidence'][0];self.assertEqual(proof['actor'],self.owner);self.assertEqual(proof['requirement'],'确认按钮放在页面顶部');self.assertEqual(len(proof['sha256']),64)

    def test_later_or_wrong_version_baseline_is_rejected(self):
        request=self.request();base=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1')
        with self.assertRaises(Denied):self.quote(request,'CLIENT_CHANGE',[base['event_id']])
        with self.assertRaises(Denied):self.service.baseline(self.owner,'project-a',self.path,'b'*64,'contract-version-1')

    def test_fee_confirmation_exact_revision_owner_only_and_no_automatic_charge(self):
        base=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1')
        q=self.quote(self.request(),'CLIENT_CHANGE',[base['event_id']])
        with self.assertRaises(Denied):self.service.respond(self.reviewer,'project-a',q['id'],q['revision'],'CONFIRM','同意')
        with self.assertRaises(Conflict):self.service.respond(self.owner,'project-a',q['id'],1,'CONFIRM','同意')
        result=self.service.respond(self.owner,'project-a',q['id'],q['revision'],'CONFIRM','确认费用与范围')
        self.assertFalse(result['automatic_charge']);self.assertFalse(result['automatic_execution'])

    def test_our_defects_cannot_have_a_fee(self):
        r=self.request()
        with self.assertRaises(Denied):self.quote(r,'PROVIDER_DEFECT')
        q=self.service.assess(self.reviewer,'project-a',r['id'],r['revision'],'PROVIDER_DEFECT',60,[],[],'未达到已确认验收标准，由我方修复')
        self.assertEqual(q['state'],'FREE_APPROVED')

    def test_customer_cannot_self_assess_or_confirm_other_customer_baseline(self):
        with self.assertRaises(Denied):self.service.baseline(self.other,'project-a',self.path,self.sha,'假确认')
        r=self.request()
        with self.assertRaises(Denied):self.service.assess(self.owner,'project-a',r['id'],1,'IN_SCOPE_SMALL',10,[],[],'自行审批')

    def test_evidence_and_feedback_are_encrypted_and_append_only(self):
        r=self.request();row=self.c.db.execute('SELECT payload FROM change_events WHERE case_id=?',(r['id'],)).fetchone();self.assertNotIn('按钮'.encode(),row[0])
        with self.assertRaises(Exception):self.c.db.execute('DELETE FROM change_events')

    def test_new_scope_cannot_bypass_missing_history_or_new_order(self):
        q=self.quote(self.request(),'NEW_SCOPE');self.assertEqual(q['state'],'NEEDS_EVIDENCE');self.assertEqual(q['lines'],[]);self.assertIsNone(q['totals'])
        with self.assertRaises(Conflict):self.service.respond(self.owner,'project-a',q['id'],q['revision'],'CONFIRM','确认')

    def test_separate_customer_new_order_and_signed_confirmation_can_quote(self):
        r=self.request('NEW_ORDER');events=self.service._events(self.owner,'project-a',r['id']);request=events[0]['payload']
        seed(self,revision=2,documents=[doc(self,kind='NEW_ORDER',text=request['request'],request_sha=self.service._request_sha(events),document_id='new-order-source')])
        confirm=self.service.confirm_new_scope(self.owner,'project-a',r['id'],r['revision'],'new-order-source')
        q=self.quote(confirm,'NEW_SCOPE',[confirm['event_id']]);self.assertEqual(q['state'],'QUOTED')

    def test_disputed_rectification_cannot_be_relabelled_new_order(self):
        r=self.request()
        with self.assertRaises(Denied):self.service.confirm_new_scope(self.owner,'project-a',r['id'],1,'contract-version-1')

    def test_arbitrary_customer_text_is_not_contract_evidence(self):
        with self.assertRaises((Denied,ValueError)):self.service.baseline(self.owner,'project-a',self.path,self.sha,'这是我补录的合同要求')

    def test_fake_page_sha_other_path_and_unbound_project_are_rejected(self):
        for path,sha in [(self.path,'b'*64),('/unknown/',self.sha)]:
            with self.assertRaises(Denied):self.service.submit(self.owner,'project-a',path,sha,'意见')

    def test_signature_manifest_and_actual_page_bytes_checked(self):
        import hashlib,hmac
        for attack in ('signature','manifest','bytes'):
            envelope=snapshot(self,revision=2,documents=[doc(self)])
            if attack=='signature':envelope['signature']='f'*64
            else:
                entry=envelope['payload']['previews'][0]
                if attack=='manifest':entry['manifest']['source_commit']='b'*40
                else:entry['blobs'][PAGE_SHA]='Zm9yZ2Vk'
                envelope['signature']=hmac.new(self.auth,canonical(envelope['payload']),hashlib.sha256).hexdigest()
            with self.assertRaises(Denied):import_snapshot(self.c,envelope,self.auth)

    def test_expired_or_revoked_preview_and_document_block_confirmation(self):
        b=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1');r=self.request();q=self.quote(r,'CLIENT_CHANGE',[b['event_id']])
        seed(self,revision=2,documents=[])
        with self.assertRaises(Denied):self.service.respond(self.owner,'project-a',q['id'],q['revision'],'CONFIRM','确认')
        self.now+=3601
        with self.assertRaises(Denied):self.request()

    def test_non_customer_member_cannot_submit_or_get_footer(self):
        self.c.db.execute('INSERT INTO members VALUES(?,?,?,1)',('project-a',self.member,'VIEWER'))
        with self.assertRaises(Denied):self.service.submit(self.member,'project-a',self.path,self.sha,'冒充客户')
        with self.assertRaises(Denied):self.service.preview_footer(self.member,'project-a',self.path,self.sha)

    def sign(self,envelope):
        envelope['signature']=hmac.new(self.auth,canonical(envelope['payload']),hashlib.sha256).hexdigest();return envelope

    def test_source_replay_and_expiry_are_rejected(self):
        with self.assertRaises(Conflict):import_snapshot(self.c,snapshot(self),self.auth)
        envelope=snapshot(self,revision=2);envelope['payload']['expires']=self.now+10;import_snapshot(self.c,self.sign(envelope),self.auth)
        self.now+=11
        with self.assertRaisesRegex(Denied,'CHANGE_AUTHORITY_EXPIRED'):self.request()

    def test_contract_bytes_identity_version_and_cross_project_checks(self):
        for attack in ('bytes','version','customer','project'):
            envelope=snapshot(self,revision=2,documents=[doc(self)])
            entry=envelope['payload']['documents'][0]
            if attack=='bytes':entry['document_utf8']+=' '
            elif attack=='version':entry['version_sha256']='b'*64
            else:
                payload=json.loads(entry['document_utf8']);payload['confirmed_by' if attack=='customer' else 'project']=self.other if attack=='customer' else 'project-other'
                entry['document_utf8']=canonical(payload).decode();entry['document_sha256']=digest(entry['document_utf8'].encode())
            with self.assertRaises(Denied):import_snapshot(self.c,self.sign(envelope),self.auth)

    def test_legacy_or_late_baseline_cannot_be_historical_contract(self):
        legacy=self.service._append(self.owner,'project-a','legacy-baseline',0,'BASELINE',{'state':'CUSTOMER_CONFIRMED','page':self.path,'page_sha256':self.sha,'confirmed_requirement':'以前手工补录的文字'})
        r=self.request()
        with self.assertRaisesRegex(Denied,'LEGACY_TEXT'):self.quote(r,'CLIENT_CHANGE',[legacy['event_id']])
        seed(self,revision=2,documents=[doc(self)])
        late=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1')
        with self.assertRaisesRegex(Denied,'PRIOR_CONTRACT'):self.quote(r,'CLIENT_CHANGE',[late['event_id']])

    def test_preview_revocation_and_project_authority_change_invalidate(self):
        b=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1');q=self.quote(self.request(),'CLIENT_CHANGE',[b['event_id']])
        seed(self,revision=2,documents=[doc(self)],paths=['/another-page/'])
        with self.assertRaises(Denied):self.service.respond(self.owner,'project-a',q['id'],q['revision'],'CONFIRM','确认')
        self.imported(2,[self.p])
        with self.assertRaises(Denied):self.request()

    def test_new_order_document_cannot_be_reused_for_another_request(self):
        first=self.request('NEW_ORDER');events=self.service._events(self.owner,'project-a',first['id'])
        seed(self,revision=2,documents=[doc(self,kind='NEW_ORDER',text=events[0]['payload']['request'],request_sha=self.service._request_sha(events),document_id='new-order-source')])
        second=self.request('NEW_ORDER')
        with self.assertRaises(Denied):self.service.confirm_new_scope(self.owner,'project-a',second['id'],1,'new-order-source')

    def test_revocation_between_check_and_commit_is_rejected(self):
        base=self.service.baseline(self.owner,'project-a',self.path,self.sha,'contract-version-1');q=self.quote(self.request(),'CLIENT_CHANGE',[base['event_id']]);original=self.service._append
        def revoke_then_append(*args,**kwargs):
            seed(self,revision=2,documents=[])
            return original(*args,**kwargs)
        self.service._append=revoke_then_append
        with self.assertRaises(Denied):self.service.respond(self.owner,'project-a',q['id'],q['revision'],'CONFIRM','确认')
        self.assertEqual(self.service._events(self.owner,'project-a',q['id'])[-1]['kind'],'ASSESSMENT')

    def test_original_signed_source_and_document_bytes_retained(self):
        raw=self.c.db.execute('SELECT payload FROM change_authority_history WHERE revision=1').fetchone()[0]
        source=json.loads(self.c.decrypt(raw,'change-authority-source:1'));document=source['payload']['documents'][0]
        self.assertEqual(digest(document['document_utf8'].encode()),document['document_sha256'])
        with self.assertRaises(Exception):self.c.db.execute('DELETE FROM change_authority_history')


class ChangeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=HttpTests();self.addCleanup(self.fixture.doCleanups);self.fixture.setUp();seed(self.fixture)

    def test_real_http_feedback_and_project_isolation(self):
        f=self.fixture;request={'project':'project-a','page':'/preview/consumer/','version':PAGE_SHA,'text':'调整付款按钮位置','intent':'RECTIFICATION'}
        status,_,body=f.request('api/change_submit',request,f.auth_headers());self.assertEqual(status,200);self.assertEqual(json.loads(body)['state'],'REQUESTED')
        status,_,body=f.request('api/changes/project-a',headers=f.auth_headers());self.assertEqual(status,200);self.assertIn('调整付款按钮位置',body.decode())
        self.assertEqual(f.request('api/changes/project-a',headers={'Cookie':COOKIE+'='+f.users['other']['token']})[0],403)

    def test_real_http_csrf_actor_injection_and_static_widget(self):
        f=self.fixture;request={'project':'project-a','page':'/preview/consumer/','version':PAGE_SHA,'text':'调整付款按钮位置','intent':'RECTIFICATION'}
        self.assertEqual(f.request('api/change_submit',request,{**f.auth_headers(),'X-CSRF-Token':'bad'})[0],403)
        self.assertEqual(f.request('api/change_submit',{**request,'actor':f.other},f.auth_headers())[0],400)
        status,headers,body=f.request('feedback.js');self.assertEqual(status,200);self.assertIn('javascript',headers['Content-Type']);self.assertIn(b'change_submit',body)

    def test_real_http_fake_manifest_and_old_text_baseline_cannot_pass(self):
        f=self.fixture;body={'project':'project-a','page':'/preview/consumer/','version':'a'*64,'text':'假页面','intent':'RECTIFICATION'}
        self.assertEqual(f.request('api/change_submit',body,f.auth_headers())[0],403)
        self.assertEqual(f.request('api/change_baseline',{'project':'project-a','page':'/preview/consumer/','version':PAGE_SHA,'text':'伪造旧需求'},f.auth_headers())[0],400)
        self.assertEqual(f.request('api/import-change-authority',{'payload':{},'signature':'a'*64},f.auth_headers())[0],404)


