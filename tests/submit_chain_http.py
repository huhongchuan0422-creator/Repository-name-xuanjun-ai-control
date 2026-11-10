"""Original Page/session HTTP to original services; synthetic provider boundary only."""
import os,sys,subprocess,time,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_community_applicant_applyment import ApplicantApplyment
from scripts.community_mini_http import serve
ApplicantApplyment.setUpClass();fx=ApplicantApplyment();fx.setUp();server=None;child=None
try:
 app=fx.call('read');app=fx.fx.draft(app,fields={**app['fields'],'contact':'13800000000'},sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'])
 p=copy.deepcopy(fx.read()['profile']);p['subject_info']['business_license_info']['license_address']='北京市东城区合成地址';fx.call('wechat_save',expected_version=fx.read()['version'],profile=p)
 case=os.environ.get('CASE','success')
 if case=='gate':fx.service.enabled=False
 from unittest.mock import patch
 from scripts.community_mini_merchant import MiniMerchant
 original_validate=MiniMerchant._validate_contact_for_submit
 injected=[False]
 def validate(mini,uid,body):
  if body['operation']=='wechat_apply' and not injected[0] and case in ('platform-phone','stale-platform','legacy'):
   injected[0]=True
   current=fx.call('read')
   fx.fx.draft(current,fields={**current['fields'],'contact':'INVALID SYNTHETIC' if case in ('platform-phone','legacy') else '13800000000','store_name':'Synthetic concurrent edit'},sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'])
  return original_validate(mini,uid,body)
 validation_patch=patch.object(MiniMerchant,'_validate_contact_for_submit',validate);validation_patch.start();fx.addCleanup(validation_patch.stop)
 server=serve(fx.fx.fx.gateway,onboarding=fx.fx.service);server.timeout=.1
 with fx.response({'applyment_id':123456789},error=TimeoutError('SYNTHETIC_UNKNOWN') if case=='unknown' else None):
  child=subprocess.Popen(['node','tests/submit_chain_http.cjs'],cwd=ROOT,env={**os.environ,'COMMUNITY_TEST_ORIGIN':'http://127.0.0.1:'+str(server.server_port),'SYNTHETIC_APPLICATION':fx.application},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  deadline=time.monotonic()+30
  while child.poll() is None and time.monotonic()<deadline:server.handle_request()
  if child.poll() is None:child.kill()
  output=child.communicate()[0];print(output);assert child.returncode==0
 state=fx.call('read');record=fx.read();posts=sum(c.args[1]=='POST' for c in fx.provider.call_args_list)
 if case in ('gate','platform-phone','stale-platform'):
  assert state['status']=='DRAFT';assert record['state']=='DRAFT';assert len(fx.attempts())==0;assert posts==0
 elif case=='original-gap':
  assert state['status']=='SUBMITTED';assert record['state']=='DRAFT';assert len(fx.attempts())==0;assert posts==0
 else:
  assert state['status']=='SUBMITTED';assert record['state']==('SUBMISSION_UNKNOWN' if case=='unknown' else 'SUBMITTED_TO_PROVIDER');assert len(fx.attempts())==1;assert posts==1
 assert state['payment_enabled'] is False
 print('PASS_ORIGINAL_PAGE_HTTP_'+case.upper()+'_SYNTHETIC_ONLY')
finally:
 if child and child.poll() is None:child.kill();child.wait()
 if server:server.server_close()
 fx.doCleanups()
