import unittest
import json
from tests.test_pr122_customer_center import CustomerTests
from tests.test_pr122_customer_http import HttpTests
from scripts.pr122_customer_http import COOKIE
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_core import Denied, Conflict


class ChangeTests(unittest.TestCase):
    imported=CustomerTests.imported
    # Reuse the exact authenticated identity/authority fixture, not its tests.
    def setUp(self):
        CustomerTests.setUp(self);self.service=Changes(self.c);self.sha='a'*64;self.path='/project/consumer/'

    def request(self):return self.service.submit(self.owner,'project-a',self.path,self.sha,'把按钮移动到页面底部')
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
        base=self.service.baseline(self.owner,'project-a',self.path,self.sha,'确认按钮放在页面顶部')
        q=self.quote(self.request(),'CLIENT_CHANGE',[base['event_id']]);self.assertEqual(q['state'],'QUOTED')
        proof=q['evidence'][0];self.assertEqual(proof['actor'],self.owner);self.assertEqual(proof['requirement'],'确认按钮放在页面顶部');self.assertEqual(len(proof['sha256']),64)

    def test_later_or_wrong_version_baseline_is_rejected(self):
        request=self.request();base=self.service.baseline(self.owner,'project-a',self.path,self.sha,'后来才确认的需求')
        with self.assertRaises(Denied):self.quote(request,'CLIENT_CHANGE',[base['event_id']])
        base=self.service.baseline(self.owner,'project-a',self.path,'b'*64,'另一个页面版本')
        with self.assertRaises(Denied):self.quote(self.request(),'CLIENT_CHANGE',[base['event_id']])

    def test_fee_confirmation_exact_revision_owner_only_and_no_automatic_charge(self):
        q=self.quote(self.request())
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


class ChangeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=HttpTests();self.addCleanup(self.fixture.doCleanups);self.fixture.setUp()

    def test_real_http_feedback_and_project_isolation(self):
        f=self.fixture;request={'project':'project-a','page':'/preview/consumer/','version':'a'*64,'text':'调整付款按钮位置'}
        status,_,body=f.request('api/change_submit',request,f.auth_headers());self.assertEqual(status,200);self.assertEqual(json.loads(body)['state'],'REQUESTED')
        status,_,body=f.request('api/changes/project-a',headers=f.auth_headers());self.assertEqual(status,200);self.assertIn('调整付款按钮位置',body.decode())
        self.assertEqual(f.request('api/changes/project-a',headers={'Cookie':COOKIE+'='+f.users['other']['token']})[0],403)

    def test_real_http_csrf_actor_injection_and_static_widget(self):
        f=self.fixture;request={'project':'project-a','page':'/preview/consumer/','version':'a'*64,'text':'调整付款按钮位置'}
        self.assertEqual(f.request('api/change_submit',request,{**f.auth_headers(),'X-CSRF-Token':'bad'})[0],403)
        self.assertEqual(f.request('api/change_submit',{**request,'actor':f.other},f.auth_headers())[0],400)
        status,headers,body=f.request('feedback.js');self.assertEqual(status,200);self.assertIn('javascript',headers['Content-Type']);self.assertIn(b'change_submit',body)


