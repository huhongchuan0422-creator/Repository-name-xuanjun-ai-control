import copy
import json
import unittest
from unittest.mock import Mock,patch
import test_community_platform_host as host_fixture
from scripts.pr122_customer_core import canonical,digest
from scripts.community_platform_host import PlatformHost
from scripts.community_platform_reviewer_admission import ReviewerAdmission
import scripts.community_reviewer_maintenance as maintenance

class Maintenance(unittest.TestCase):
    def setUp(self):
        self.fx=host_fixture.FormalHost();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.fx.plan['operations']={};self.fx.plan['reviewers']={}
        self.fx.write('host.json',self.fx.plan)
        with self.fx.open() as host:
            host.center.db.execute("UPDATE projects SET owner='system_community_platform' WHERE id='project1'")
        self.fx.plan['registration_scenes']=['shop1'];self.fx.write('host.json',self.fx.plan)
        with self.fx.open() as host:
            host.application.gateway.provider.exchange=Mock(return_value=dict(appid=self.fx.wechat['appid'],openid='maintenance_fixture'))
            token=host.application.gateway.login({'code':'maintenance_fixture'})['session_token']
            self.uid=host.center.session(token)
            snapshot=ReviewerAdmission(host.center,host.application.identity).inspect('project1',self.uid)
        body='SYNTHETIC OWNER: GRANT REVIEWER '+self.uid+' project1 admission1'
        self.approval=self.fx.write('owner.json',dict(owner_message_id='synthetic_owner_record',body=body))
        self.plan=dict(version=1,action='GRANT',role='REVIEWER',request_id='admission1',project='project1',uid=self.uid,
            expected_revision=0,snapshot=snapshot,approval=dict(owner_message_id='synthetic_owner_record',owner_body_sha256=digest(body.encode())))
        self.bind()
    def bind(self):
        self.admission=self.fx.write('admission.json',self.plan)
        self.sha=digest(canonical(self.plan));self.base=digest(canonical(json.loads(self.fx.plan_path.read_text())))
        self.pin=dict(self.plan['approval'],plan_sha256=self.sha,host_base_sha256=self.base,
            **{k:self.plan[k] for k in ('project','uid','action','request_id')})
    def call(self,operation='grant'):
        return maintenance.execute(str(self.fx.plan_path),str(self.fx.keys_path),str(self.fx.wechat_path),operation,
            admission_path=str(self.admission),approval_path=str(self.approval),plan_sha256=self.sha,host_base_sha256=self.base)
    def test_unfilled_pin_cannot_be_supplied_by_file(self):
        with self.assertRaisesRegex(PermissionError,'NOT_YET_BOUND'):self.call()
    def test_actual_host_grant_config_and_query(self):
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin):
            result=self.call();self.assertEqual(result['config_status'],'CONFIG_APPLIED')
            self.assertEqual(self.call()['config_status'],'CONFIG_ALREADY_APPLIED')
            self.assertEqual(self.call('recover')['revision'],1)
        with self.fx.open() as host:
            host.application.onboarding._reviewer(self.uid)
            self.assertEqual(host.application.identity.registration['shop1']['project'],'project1')
        config=json.loads(self.fx.plan_path.read_text())
        self.assertEqual(config['reviewers'],{self.uid:'project1'})
        self.assertEqual(config['operations'],{})
    def test_exact_owner_body_mismatch(self):
        self.fx.write('owner.json',dict(owner_message_id='synthetic_owner_record',body='different'))
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin),self.assertRaises(PermissionError):self.call()
    def test_original_host_lock_refuses_second_writer(self):
        with self.fx.open(),patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin),self.assertRaises(BlockingIOError):self.call()
    def test_config_failure_recovery_does_not_regrant(self):
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin):
            with patch.object(maintenance,'_cas_mapping',side_effect=OSError('synthetic disk error')):
                result=self.call();self.assertEqual(result['config_status'],'MEMBER_COMMITTED_CONFIG_PENDING')
            self.assertEqual(self.call('recover')['config_status'],'CONFIG_APPLIED')
            self.assertEqual(self.call('recover')['revision'],1)
    def test_config_cas_preserves_unrelated_edits(self):
        before=json.loads(self.fx.plan_path.read_text());before['nginx_gid']+=1
        self.fx.write('host.json',before)
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin):
            result=self.call();self.assertEqual(result['config_status'],'MEMBER_COMMITTED_CONFIG_PENDING')
        self.assertEqual(json.loads(self.fx.plan_path.read_text()),before)
    def test_revoke_original_runtime_and_config(self):
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin):self.call()
        self.plan.update(action='REVOKE',request_id='revoke1',expected_revision=1)
        body='SYNTHETIC OWNER: REVOKE REVIEWER '+self.uid+' project1 revoke1'
        self.plan['approval']['owner_body_sha256']=digest(body.encode())
        self.fx.write('owner.json',dict(owner_message_id='synthetic_owner_record',body=body));self.bind()
        from scripts.pr122_customer_core import Center
        with patch.object(maintenance,'OWNER_CONFIRMATION_PIN',self.pin),patch.object(Center,'now',return_value=self.plan['snapshot']['project']['expires']+1):
            self.assertEqual(self.call('revoke')['config_status'],'CONFIG_APPLIED')
        with self.fx.open() as host:
            with self.assertRaises(PermissionError):host.center.project(self.uid,'project1',('REVIEWER',))
        self.assertEqual(json.loads(self.fx.plan_path.read_text())['reviewers'],{})

if __name__=='__main__':unittest.main()
