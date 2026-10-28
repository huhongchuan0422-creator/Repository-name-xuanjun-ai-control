import copy,hashlib,http.client,json,threading,unittest
from http.server import HTTPServer
from pathlib import Path
from scripts.pr122_customer_core import Center
from scripts.pr122_customer_http import App,COOKIE
from scripts.pr122_customer_providers import Providers
from scripts import community_saas_modules as modules,community_saas_offer_catalog as offers
from scripts.saas_ecosystem_adapter import EcosystemAdapter
from scripts.saas_ecosystem_http import PendingEcosystemHTTP
from scripts.saas_pending_packages import install as install_pending
from scripts.pr122_customer_twin import TwinProjectionHTTP
from tests.test_pr122_customer_center import CustomerTests

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'deploy/pr122-customer-center/ui'

class HostTests(unittest.TestCase):
 def setUp(self):
  self.f=CustomerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.db=modules.connect();offers.install(self.db);self.addCleanup(self.db.close)
  self.adapter=EcosystemAdapter(modules,offers,self.db)
  self.artifact=b'fictional-source-package-v1'
  self.manifest={'module_id':'storefront_catalog','version':'1.0.0','artifact_sha256':hashlib.sha256(self.artifact).hexdigest(),'capabilities':['catalog.read','storefront.read'],'dependencies':{},'private_note':'NEVER_EXPORT'}
  self.provider=lambda tenant,pid:(self.adapter,{'storefront_catalog':copy.deepcopy(self.manifest)},{'storefront_catalog':self.artifact},{},{})
  install_pending(self.f.c)
  self.twin={'schema':3,'mode':'TEST_ONLY','production_status':'NOT_IMPLEMENTED','observed_at':123,'tasks':[{'task_id':'TASK-1','project_id':'project-a','node_id':'node-a','attempt_id':'attempt-a','module_id':'kernel','state':'STARTED','runtime_status':'UNKNOWN','responsible_party':'owner','blocker':'UNKNOWN','writer_identity':'writer','checkpoint_sha256':'a'*64,'resources_json':'SECRET','checkpoints':[{'attempt_id':'attempt-a','checkpoint_id':'cp1','effects_state':'COMPLETE','created_at':123}],'dependencies':[]}],'timeline':[{'task_id':'TASK-1','attempt_id':'attempt-a','event_id':'ev1','kind':'PROGRESS','observed_at':123,'evidence_ref':'ref1','payload':'SECRET'}], 'admin_secret':'NEVER_EXPORT'}
  self.factory=lambda:Center(self.f.root,{'v1':self.f.key},'v1',clock=lambda:self.f.now,mail_ready=True,scanner=lambda b:True)
  self.server=None
 def start(self,profile='FULL',ecosystem=True,twin=True):
  e=PendingEcosystemHTTP(self.provider) if ecosystem else None
  t=TwinProjectionHTTP(lambda tenant,pid:copy.deepcopy(self.twin)) if twin else None
  self.server=HTTPServer(('127.0.0.1',0),App(self.factory,Providers({}),'https://wenwenwenyiyiyi.work',ASSETS,source_identity=lambda c,h:'fixture',deployment_profile=profile,ecosystem=e,twin=t).handler())
  th=threading.Thread(target=self.server.serve_forever,daemon=True);th.start();self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),th.join()))
 def request(self,path,who='owner',method='GET',body=None,csrf=True):
  u=self.f.users[who];headers={'Host':'wenwenwenyiyiyi.work','Cookie':COOKIE+'='+u['token']}
  if body is not None:
   headers.update({'Origin':'https://wenwenwenyiyiyi.work','Content-Type':'application/json','Content-Length':str(len(json.dumps(body)))})
   if csrf:headers['X-CSRF-Token']=u['csrf']
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5);payload=json.dumps(body) if body is not None else None
  c.request(method,path,payload,headers);r=c.getresponse();raw=r.read();ctype=r.getheader('Content-Type','');c.close();return r.status,(json.loads(raw) if 'json' in ctype else raw)
 def test_full_same_origin_assets_and_project_scoped_ecosystem(self):
  self.start();s,raw=self.request('/customer/center/ecosystem/');self.assertEqual(s,200);self.assertIn(b'SaaS',raw)
  s,d=self.request('/customer/center/api/ecosystem/packages/project-a');self.assertEqual(s,200);self.assertEqual(d['catalog_revision'],0)
  body={'module_id':'storefront_catalog','version':'1.0.0','expected_revision':0,'idempotency_key':'host_pending_key_0001'}
  s,d=self.request('/customer/center/api/ecosystem/register_pending/project-a',method='POST',body=body);self.assertEqual(s,200);self.assertFalse(d['published'])
  s,d2=self.request('/customer/center/api/ecosystem/receipts/project-a/host_pending_key_0001');self.assertEqual(s,200);self.assertEqual(d2['record_id'],d['record_id'])
 def test_ecosystem_permissions_and_csrf_default_deny(self):
  self.start();body={'module_id':'storefront_catalog','version':'1.0.0','expected_revision':0,'idempotency_key':'host_pending_key_0002'}
  self.assertEqual(self.request('/customer/center/api/ecosystem/register_pending/project-a',who='reviewer',method='POST',body=body)[0],403)
  self.assertEqual(self.request('/customer/center/api/ecosystem/register_pending/project-a',method='POST',body=body,csrf=False)[0],403)
  self.assertEqual(self.request('/customer/center/api/ecosystem/packages/project-a',who='other')[0],403)
 def test_twin_projection_server_whitelist_and_role_redaction(self):
  self.start();s,d=self.request('/customer/center/api/twin/projection/project-a');self.assertEqual(s,200);raw=json.dumps(d);self.assertNotIn('SECRET',raw);self.assertNotIn('admin_secret',raw);self.assertEqual(d['ack'],'UNKNOWN');self.assertFalse(d['write_allowed'])
  self.f.c.db.execute('INSERT OR REPLACE INTO members VALUES(?,?,?,1)',('project-a',self.f.member,'VIEWER'));self.f.c.db.commit()
  s,d=self.request('/customer/center/api/twin/projection/project-a',who='member');self.assertEqual(s,200);self.assertNotIn('writer_identity',d['tasks'][0]);self.assertNotIn('checkpoint_sha256',d['tasks'][0])
 def test_twin_source_missing_and_cross_project_fail_closed(self):
  self.start(twin=False);self.assertEqual(self.request('/customer/center/twin/')[0],404)
  self.server.shutdown();self.server.server_close();self.server=None
  e=PendingEcosystemHTTP(self.provider);t=TwinProjectionHTTP(lambda tenant,pid:copy.deepcopy(self.twin))
  self.server=HTTPServer(('127.0.0.1',0),App(self.factory,Providers({}),'https://wenwenwenyiyiyi.work',ASSETS,source_identity=lambda c,h:'fixture',ecosystem=e,twin=t).handler())
  th=threading.Thread(target=self.server.serve_forever,daemon=True);th.start();self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),th.join()))
  self.assertEqual(self.request('/customer/center/api/twin/projection/project-a',who='other')[0],403)
 def test_login_only_never_exposes_extensions(self):
  self.start(profile='OFFICIAL_LOGIN_ONLY_V1')
  self.assertEqual(self.request('/customer/center/ecosystem/')[0],403)
  self.assertEqual(self.request('/customer/center/twin/')[0],403)
  self.assertEqual(self.request('/customer/center/api/twin/projection/project-a')[0],403)

if __name__=='__main__':unittest.main()
