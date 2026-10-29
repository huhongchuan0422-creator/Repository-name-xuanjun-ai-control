"""Isolated original store fixtures; no provider/network/funds execution."""
import json,hashlib,unittest
import test_community_reports as report_fixture
from scripts.pr122_customer_core import canonical
from scripts.community_demo_bootstrap import DEMO_SCOPE

class ReceiverRead(unittest.TestCase):
 @classmethod
 def setUpClass(cls):report_fixture.CommunityReportJourney.setUpClass()
 def setUp(self):self.fx=report_fixture.CommunityReportJourney();self.fx.setUp();self.fx.reader._fetch=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NO_NETWORK'))
 def tearDown(self):self.fx.tearDown()
 def bind(self):return self.fx.call('community_receiver_bind',dict(community_id=self.fx.cid,provider_workspace='finance',receiver_id='comm',expected_version=0),workspace='platform')
 def call(self,operation='community_receiver_read',**kw):
  p=dict(community_id=self.fx.cid,provider_workspace='finance');p.update({'receiver_id':'comm'} if operation.endswith('_read') else {'after_id':''});p.update(kw)
  return self.fx.call(operation,p,workspace='platform')
 def write(self,key,value):
  c=self.fx.c
  c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_RECEIVER_BINDING' AND subject_idx=?",(c.encrypt(canonical(value),'community-receiver:'+key),key))
 def key(self):return hashlib.sha256(canonical([DEMO_SCOPE,'comm'])).hexdigest()
 def test_bind_real_workspace_and_read_list_preserve_no_funds(self):
  bound=self.bind();self.assertEqual(bound['provider_workspace'],'finance')
  r=self.call();self.assertEqual(r['version'],1);self.assertEqual(r['provider_workspace_status'],'RECORDED');self.assertFalse(r['funds_operation_executed']);self.assertNotIn('account',json.dumps(r));self.assertNotIn('approved_by',r)
  page=self.call('community_receiver_list');self.assertEqual(page['records'],[r]);self.assertFalse(page['has_more'])
 def test_legacy_workspace_is_not_guessed_or_written_by_read(self):
  value=self.bind();value={k:v for k,v in value.items() if k not in ('provider_workspace','applies_to','funds_operation_executed')};self.write(self.key(),value)
  before=self.fx.c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_RECEIVER_BINDING'").fetchone()[0]
  r=self.call();self.assertIsNone(r['provider_workspace']);self.assertEqual(r['provider_workspace_status'],'LEGACY_NOT_RECORDED');self.assertEqual(r['requested_provider_workspace'],'finance')
  after=self.fx.c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_RECEIVER_BINDING'").fetchone()[0];self.assertEqual(before,after)
 def test_owner_and_finance_grants_required(self):
  self.bind();p=dict(community_id=self.fx.cid,provider_workspace='finance',receiver_id='comm')
  for workspace,web in [('community',None),('reviewer',self.fx.reviewer),('other',self.fx.reviewer)]:
   with self.assertRaises(PermissionError):self.fx.call('community_receiver_read',p,workspace=workspace,web=web)
  with self.assertRaises(PermissionError):self.call(provider_workspace='missing')
  with self.assertRaises(PermissionError):self.call(receiver_id='not-admitted')
 def test_old_scope_and_community_not_exposed(self):
  value=self.bind();value['scope']=dict(DEMO_SCOPE,tenant_id='foreign');self.write(self.key(),value)
  self.assertEqual(self.call('community_receiver_list')['records'],[])
  with self.assertRaisesRegex(ValueError,'RECEIVER_BINDING_NOT_FOUND'):self.call()
 def test_paused_community_still_readable_but_bind_gate_unchanged(self):
  self.bind();self.fx.call('review',dict(community_id=self.fx.cid,expected_version=3,decision='PAUSED',opinion='fixture'),workspace='reviewer',web=self.fx.reviewer)
  self.assertEqual(self.call()['version'],1)
  with self.assertRaises(PermissionError):self.fx.call('community_receiver_bind',dict(community_id=self.fx.cid,provider_workspace='finance',receiver_id='comm',expected_version=1),workspace='platform')
 def test_sparse_cursor_not_fake_empty_terminal(self):
  c=self.fx.c
  for i in range(51):
   key=format(i,'064x');value=dict(scope=dict(DEMO_SCOPE,tenant_id='foreign'),community_id=self.fx.cid)
   c.db.execute("INSERT INTO links VALUES('COMMUNITY_RECEIVER_BINDING',?,?,?,?,1)",(key,self.fx.fx.uid1,'project1',c.encrypt(canonical(value),'community-receiver:'+key)))
  r=self.call('community_receiver_list');self.assertEqual(r['records'],[]);self.assertTrue(r['has_more']);self.assertEqual(r['next_cursor'],format(49,'064x'))
  nextpage=self.call('community_receiver_list',after_id=r['next_cursor']);self.assertFalse(nextpage['has_more'])
 def test_invalid_version_or_bound_key_fails_closed(self):
  value=self.bind();value['version']=True;self.write(self.key(),value)
  with self.assertRaisesRegex(ValueError,'RECEIVER_BINDING_INTEGRITY_CONFLICT'):self.call()
 def test_no_record_and_cursor_validation(self):
  with self.assertRaisesRegex(ValueError,'RECEIVER_BINDING_NOT_FOUND'):self.call()
  with self.assertRaisesRegex(ValueError,'INVALID_RECEIVER_BINDING_CURSOR'):self.call('community_receiver_list',after_id='bad')

if __name__=='__main__':unittest.main()
