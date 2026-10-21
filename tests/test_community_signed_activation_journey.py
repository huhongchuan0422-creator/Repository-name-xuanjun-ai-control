"""Real synthetic RSA query -> original encrypted record -> formal composition.

Only the provider fetch boundary is substituted. No external provider or money.
"""
import base64,hashlib,tempfile,unittest
from pathlib import Path
import test_community_applyment_rejection_recovery as signed_fixture
from scripts.community_merchant_store import open_store
from scripts.community_merchant_opening import open_workbench
from scripts.community_center_operations import CenterOperations
from scripts.community_stage_local import LocalStage
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_host_config import stores

class SignedActivationJourney(unittest.TestCase):
 @classmethod
 def setUpClass(cls):signed_fixture.RejectionRecovery.setUpClass()
 def test_finished_verified_query_persists_and_configures_original_payments(self):
  fx=signed_fixture.RejectionRecovery();fx.setUp();self.addCleanup(fx.doCleanups)
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  merchant=open_store(str(Path(tmp.name)/'merchant.sqlite'));self.addCleanup(merchant.close)
  fx.fx.fx.stage.demo.merchant_db=merchant
  grants={'merchant':dict(user_id=fx.fx.fx.uid1,project='project1',project_roles=['OWNER'],
      principal=fx.fx.fx.stage.merchant,onboarding_required=True)}
  ops=CenterOperations(fx.center,fx.fx.fx.stage.api,grants,onboarding=fx.fx.service)
  fx.fx.service.operations=ops
  open_workbench(fx.fx.service,ops,fx.fx.fx.uid2,fx.application,'merchant',fx.platform['revision'])
  fx.signed_initial_submission()
  data=fx.query_data('APPLYMENT_STATE_FINISHED',sub_mchid='1234567891')
  headers,raw=wire=fx.signed_wire(data)
  with fx.wire_response(wire) as fetch:record=fx.call('wechat_query')
  self.assertEqual(fetch.call_count,1)
  saved=fx.service._read(fx.application)
  self.assertEqual(saved['provider_response_sha256'],hashlib.sha256(raw).hexdigest())
  self.assertEqual(saved['provider_query_signature_sha256'],hashlib.sha256(
      base64.b64decode(headers['Wechatpay-Signature'])).hexdigest())
  self.assertEqual(saved['provider_query_signed_at'],int(headers['Wechatpay-Timestamp']))
  stage=LocalStage(Path(tmp.name)/'runtime',fx.fx.fx.stage.api.bindings,
      fx.fx.fx.stage.api.bindings[fx.fx.fx.stage.customer],clock=fx.center.now)
  self.addCleanup(stage.close);merchant.backup(stage.demo.merchant_db)
  config=dict(version=1,appid=fx.fx.fx.identity.appid,
      https_origin='https://community-preview.wenwenwenyiyiyi.work',
      scenes={'shop1':dict(project='project1',principal='customer')},
      stores={name:db.execute('PRAGMA database_list').fetchone()[2]
              for name,db in stores(fx.center,stage.runtime).items()})
  admissions={'shop1':dict(channel='WECHAT',description='Synthetic fixture',
      notify_url='https://example.org/notify',profit_sharing=False,
      jsapi_admitted=True,profit_sharing_admitted=False)}
  for replay in range(2):
   with MiniApplication.from_existing_runtime(fx.center,stage.runtime,
       {'customer':fx.fx.fx.stage.customer},config,'a'*32) as app:
    app.configure_onboarding({fx.fx.fx.uid2:'project1'});app.configure_operations(grants)
    applyment=app.configure_wechat_applyment(fx.reader)
    self.assertEqual(applyment._read(fx.application)['provider_response_sha256'],hashlib.sha256(raw).hexdigest())
    payments=app.configure_payments_from_applyments(fx.reader,admissions)
    self.assertEqual(payments.merchants['shop1']['record']['sub_mchid'],'1234567891')
    self.assertIs(payments.prepay.center,fx.center)

if __name__=='__main__':unittest.main()
