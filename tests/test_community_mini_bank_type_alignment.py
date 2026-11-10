"""Existing provider bank rules mirrored by the Mini form; synthetic only."""
import copy,json,subprocess,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from types import SimpleNamespace
from test_community_applyment_conditions import profile,NOW
import test_community_applicant_applyment as applicant_fixture
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_mini_http import serve

ROOT=Path(__file__).resolve().parents[1]

class BankTypeAlignment(unittest.TestCase):
 def test_frontend_acceptance_matches_original_backend_for_both_entities_and_all_types(self):
  service=WechatApplyment.__new__(WechatApplyment);service.center=SimpleNamespace(now=lambda:NOW)
  cases=[]
  for entity in ('ENTERPRISE','SOLE_PROPRIETOR'):
   for account_type in ('BANK_ACCOUNT_TYPE_CORPORATE','BANK_ACCOUNT_TYPE_PERSONAL','SYNTHETIC_UNKNOWN','',None,0,{},[]):
    p=profile();p['subject_info']['subject_type']='SUBJECT_TYPE_ENTERPRISE' if entity=='ENTERPRISE' else 'SUBJECT_TYPE_INDIVIDUAL'
    p['bank_account_info']['bank_account_type']=account_type
    p['bank_account_info']['account_name']='Fixture Owner' if account_type=='BANK_ACCOUNT_TYPE_PERSONAL' else 'Fixture Company'
    before=copy.deepcopy(p)
    try:service._validate(p,entity);accepted=True
    except (ValueError,TypeError,KeyError):accepted=False
    self.assertEqual(p,before)
    cases.append({'entity':entity,'profile':p,'expected':accepted})
  js="""const fs=require('node:fs'),assert=require('node:assert/strict'),form=require('./clients/community-mini/merchant-form');const cases=JSON.parse(fs.readFileSync(0,'utf8'));let count=0;for(const c of cases){const before=JSON.stringify(c.profile),groups=form.reviewRequirements(c.profile,{entity:c.entity,contact:'LEGAL',doc:form.docs[0],scene:'mini',ubos:0},[]),bank=groups.find(g=>g.id==='bank');let accepted=true;try{form.assertReviewComplete([bank],null,{wechat:true,platform:false});}catch(e){accepted=false;assert.ok(e.submitIssues.some(i=>i.path==='bank_account_info.bank_account_type'));}assert.equal(accepted,c.expected,c.entity+'/'+JSON.stringify(c.profile.bank_account_info.bank_account_type));assert.equal(JSON.stringify(c.profile),before);count++;}process.stdout.write(JSON.stringify({parity_cases:count,unchanged:true}));"""
  result=subprocess.run(['node','-e',js],input=json.dumps(cases),text=True,capture_output=True,cwd=ROOT,check=True)
  self.assertEqual(json.loads(result.stdout),{'parity_cases':16,'unchanged':True})
 def test_actual_http_enterprise_personal_is_specific_and_does_not_mutate_or_post(self):
  applicant_fixture.ApplicantApplyment.setUpClass();fx=applicant_fixture.ApplicantApplyment();fx.setUp();self.addCleanup(fx.doCleanups)
  app=fx.call('read');fx.fx.draft(app,fields={**app['fields'],'contact':'13800000000'},sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'])
  p=copy.deepcopy(fx.read()['profile']);p['subject_info']['business_license_info']['license_address']='北京市东城区合成地址';p['bank_account_info'].update(bank_account_type='BANK_ACCOUNT_TYPE_PERSONAL',account_name='Fixture Owner')
  fx.call('wechat_save',expected_version=fx.read()['version'],profile=p)
  before=copy.deepcopy(fx.read());platform=fx.call('read');token=fx.fx.fx.token();server=serve(fx.fx.fx.gateway,onboarding=fx.fx.service);self.addCleanup(server.server_close);server.timeout=2;responses=[]
  def client():
   body={'operation':'onboarding','params':{'operation':'wechat_apply','params':{'application':fx.application,'expected_version':before['version'],'application_revision':platform['revision']}}}
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Community-Session':token,'X-Community-Scene':'shop1'})
   try:
    with urllib.request.urlopen(req,timeout=3) as r:responses.append((r.status,json.load(r)))
   except urllib.error.HTTPError as e:responses.append((e.code,json.load(e)))
  for _ in range(2):
   t=threading.Thread(target=client);t.start();server.handle_request();t.join(4);self.assertFalse(t.is_alive())
  for status,body in responses:
   self.assertEqual(status,400);diag=body['submission_diagnostic'];self.assertEqual((diag['stage'],diag['code']),('PROFILE','PROFILE_CHECK_FAILED'))
   self.assertEqual(diag['profile_issue'],{'reason':'OFFICIAL_BANK_ACCOUNT_TYPE_MISMATCH','fields':['bank_account_info.bank_account_type']});self.assertNotIn('Fixture Owner',json.dumps(body))
  fx.provider.assert_not_called();self.assertEqual(fx.attempts(),[]);self.assertEqual(fx.read(),before);self.assertEqual(fx.call('read'),platform)
