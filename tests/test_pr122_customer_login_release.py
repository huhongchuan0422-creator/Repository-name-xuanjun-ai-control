"""Offline login-scope and signed five-hour boundaries; no host operations."""
import copy
import unittest
from unittest.mock import patch
from scripts import pr122_customer_profile as profile
from scripts import pr122_customer_review as review
from scripts.pr122_customer_core import Denied,canonical,digest
from tests import test_pr122_customer_workflow_signature as fixtures

class LoginReleaseTests(unittest.TestCase):
    setUp=fixtures.WholeWorkflowSignatureTests.setUp
    prepare=fixtures.WholeWorkflowSignatureTests.prepare
    fetch=fixtures.WholeWorkflowSignatureTests.fetch
    gate=fixtures.WholeWorkflowSignatureTests.gate
    whole=fixtures.WholeWorkflowSignatureTests.whole
    def setup_login(self):
        self.whole()
        self.plan.pop('telegram_credential_evidence_sha256',None)
        self.plan.pop('publisher_config_sha256',None)
        self.plan.update(deployment_profile=profile.LOGIN_ONLY,permit_window_seconds=18000,login_acceptance_sha256='a'*64)
        self.approval.update(deployment_profile=profile.LOGIN_ONLY,permit_window_seconds=18000,login_acceptance_sha256='a'*64)
        self.approval['expires_unix']=self.approval['issued_unix']+18000
        self.payload.update(deployment_profile=profile.LOGIN_ONLY,permit_window_seconds=18000,login_acceptance_sha256='a'*64)
        self.payload['findings']['R3']['evidence_sha256']=['a'*64]
    def test_exact_signed_login_five_hour_passes(self):
        self.setup_login();self.prepare();self.assertEqual(self.gate()['permit_window_seconds'],18000)
    def test_old_full_signature_cannot_authorize_login(self):
        self.setup_login();self.payload.pop('deployment_profile');self.prepare()
        with self.assertRaisesRegex(Denied,'REVIEW_PAYLOAD_SCHEMA'):self.gate()
    def test_unsigned_five_hour_extension_rejected(self):
        self.whole();self.plan['permit_window_seconds']=18000;self.approval.update(permit_window_seconds=18000,expires_unix=self.approval['issued_unix']+18000);self.prepare()
        with self.assertRaisesRegex(Denied,'REVIEW_PAYLOAD_SCHEMA'):self.gate()
    def test_signed_full_five_hour_passes(self):
        self.whole();self.plan['permit_window_seconds']=18000;self.approval.update(permit_window_seconds=18000,expires_unix=self.approval['issued_unix']+18000);self.payload['permit_window_seconds']=18000;self.prepare()
        self.assertEqual(self.gate()['permit_window_seconds'],18000)
    def test_changed_profile_in_signature_rejected(self):
        self.setup_login();self.payload['deployment_profile']=profile.FULL;self.prepare()
        with self.assertRaisesRegex(Denied,'EXACT_INDEPENDENT_LOGIN_SCOPE'):self.gate()
    def test_changed_acceptance_in_signature_rejected(self):
        self.setup_login();self.payload['login_acceptance_sha256']='b'*64;self.prepare()
        with self.assertRaisesRegex(Denied,'EXACT_INDEPENDENT_LOGIN_SCOPE'):self.gate()
    def test_legacy_window_stays_two_hours(self):
        self.whole();self.approval['expires_unix']=self.approval['issued_unix']+18000;self.prepare()
        with self.assertRaisesRegex(Denied,'APPROVAL_EXPIRY'):self.gate()
    def test_five_hour_requires_exact_five_attempt_existing_policy(self):
        self.setup_login();self.approval['max_executions']=4;self.prepare()
        with self.assertRaisesRegex(Denied,'FIVE_HOUR_EXISTING_WHOLE_BUDGET_REQUIRED'):self.gate()
    def test_window_boundaries_and_types(self):
        for seconds in (True,17999,18001,0,'18000'):
            with self.subTest(seconds=seconds):
                a={'issued_unix':0,'expires_unix':18000,'permit_window_seconds':seconds,'max_executions':5,'attempt_policy':'CONTROLLED_WHOLE_WEBSITE_V3'}
                with self.assertRaises(Denied):profile.validate_window(a,{'permit_window_seconds':18000},1)
    def test_expired_and_not_yet_valid_rejected(self):
        a={'issued_unix':10,'expires_unix':18010,'permit_window_seconds':18000,'max_executions':5,'attempt_policy':'CONTROLLED_WHOLE_WEBSITE_V3'}
        for now in (9,18010):
            with self.assertRaises(Denied):profile.validate_window(a,{'permit_window_seconds':18000},now)
    def test_only_login_service_and_mail_timer_selected(self):
        units=tuple('unit'+str(i) for i in range(6));plan={'deployment_profile':profile.LOGIN_ONLY}
        self.assertEqual(profile.units(plan,units),units[:3]);self.assertEqual(profile.triggers(plan,units),(units[2],))
        self.assertEqual(profile.units({},units),units)
    def test_unknown_profile_is_not_full(self):
        with self.assertRaises(Denied):profile.profile({'deployment_profile':'LOGIN'})
    def test_runtime_scope_must_match_and_no_business_provider(self):
        c={'deployment_profile':profile.LOGIN_ONLY,'providers':{'smtp':{'host':'fixture'}}}
        self.assertEqual(profile.validate_pair(c,copy.deepcopy(c)),profile.LOGIN_ONLY)
        for r in ({'providers':c['providers']},{**c,'providers':{**c['providers'],'telegram':{}}}):
            with self.assertRaises(Denied):profile.validate_pair(c,r)

if __name__=='__main__':unittest.main()

from tests import test_pr122_customer_workflow_apply as childfixtures
from scripts import pr122_customer_release as release
from scripts import pr122_customer_workflow_apply as child
from scripts import pr122_customer_resume as resume

class LoginInstallCheckpointTests(unittest.TestCase):
    inventory=childfixtures.CustomerWorkflowApplyTests.inventory
    patches=childfixtures.CustomerWorkflowApplyTests.patches
    fake_run=childfixtures.CustomerWorkflowApplyTests.fake_run
    execute=childfixtures.CustomerWorkflowApplyTests.execute
    receipt=childfixtures.CustomerWorkflowApplyTests.receipt
    reconcile=childfixtures.CustomerWorkflowApplyTests.reconcile
    def setUp(self):
        childfixtures.CustomerWorkflowApplyTests.setUp(self)
        self.base.update(deployment_profile=profile.LOGIN_ONLY,permit_window_seconds=18000,login_acceptance_sha256='a'*64)
        self.approval.update(deployment_profile=profile.LOGIN_ONLY,permit_window_seconds=18000)
        self.lease=childfixtures.FakeWholeLease(self)
    def test_login_install_has_no_publication_effects_or_units(self):
        self.execute()
        for command in self.calls:
            self.assertFalse(any('publication' in arg for arg in command),command)
        for unit in release.UNITS[3:]:self.assertFalse((release.UNIT/unit).exists())
        self.assertIn(['/usr/bin/systemctl','enable','--now',release.UNITS[2]],self.calls)
        self.assertNotIn('PUBLISHER_ROOT_TO_NONROOT_VERIFIED',self.receipt()['completed'])
        self.assertEqual(self.receipt()['state'],resume.SUCCESS)
    def test_failed_readonly_smoke_resumes_without_restarting_successful_services(self):
        failed=[]
        def error(args):
            if args[0].endswith('curl') and not failed:
                failed.append(True);return release.CommandFailure(args,7,b'fixture')
        self.command_failure=error
        with self.assertRaises(resume.Recoverable):self.execute()
        self.assertEqual(self.reconcile()['status'],'SAFE_TO_RETRY')
        self.lease.admit(2);self.execute()
        self.assertEqual(self.calls.count(['/usr/bin/systemctl','start',release.UNITS[0]]),1)
        self.assertFalse(any('publication' in arg for command in self.calls for arg in command))

from tests import test_pr122_customer_workflow_request as requestfixtures
from scripts import pr122_customer_workflow_request as request

class LoginRequestTests(unittest.TestCase):
    def login_inputs(self):
        manifest,raw,files,obs=requestfixtures.fixture()
        static=obs['static_plan'];static.pop('publisher_config_sha256');static.pop('telegram_credential_evidence_sha256')
        static.update(deployment_profile=profile.LOGIN_ONLY,permit_window_seconds=18000,login_acceptance_sha256='a'*64)
        obs['inputs']['stages']['CUSTOMER_APPLY']['static_plan']=copy.deepcopy(static)
        return manifest,raw,obs
    def test_exact_login_scope_request_still_not_executable(self):
        m,r,o=self.login_inputs();v=request.make_request(m,r,o)
        self.assertEqual(v['state'],'NOT_EXECUTABLE');self.assertEqual(v['plan_candidate']['deployment_profile'],profile.LOGIN_ONLY)
        self.assertNotIn('PROTECTED_CONFIG_RUNTIME_PUBLISHER_AND_12_ACCEPTANCE_RECORDS',v['required_external_acceptance'])
        self.assertIn('PROTECTED_LOGIN_CONFIG_SMTP_AND_FOUR_LOGIN_ACCEPTANCE_RECORDS',v['required_external_acceptance'])
    def test_missing_login_real_evidence_never_emits_plan(self):
        m,r,o=self.login_inputs();o['static_plan']['login_acceptance_sha256']='UNKNOWN'
        v=request.make_request(m,r,o);self.assertIsNone(v['plan_candidate']);self.assertIn('static_plan.login_acceptance_sha256',v['missing_inputs'])
    def test_unknown_login_window_rejected(self):
        m,r,o=self.login_inputs();o['static_plan']['permit_window_seconds']=7200
        o['inputs']['stages']['CUSTOMER_APPLY']['static_plan']=copy.deepcopy(o['static_plan'])
        with self.assertRaisesRegex(Denied,'REQUEST_FIVE_HOUR_WINDOW'):request.make_request(m,r,o)

import base64,json
from pathlib import Path
from types import SimpleNamespace
from contextlib import ExitStack
from tests import test_pr122_customer_release as releasefixtures

class LoginActualPlanTests(unittest.TestCase):
    def setUp(self):
        releasefixtures.ReleaseTests.setUp(self)
        del self.fail
        key=base64.b64encode(b'x'*32).decode()
        self.config={'deployment_profile':profile.LOGIN_ONLY,'keys':{'k':key},'active_key':'k',
                     'providers':{'smtp':{'host':'fixture.invalid'}},'backup_key':key,
                     'backup_key_ref':'fixture-backup','authority_verify_key':key}
        self.runtime={k:self.config[k] for k in ('deployment_profile','keys','active_key','providers')}
        self.evidence=b'fixture real evidence stand-in, no target claim'
        self.manifest=json.loads((self.source/'CUSTOMER_MANIFEST.json').read_bytes());self.manifest['source_tree']='b'*40
        self.raw=canonical(self.manifest)
        self.acceptance={'manifest_sha256':digest(self.raw),'evidence':{k:{'sha256':digest(self.evidence),'path':'/var/lib/xuanjun-customer-preflight/'+k+'.json'} for k in profile.LOGIN_ACCEPTANCE}}
        self.reads=[]
    def invoke(self):
        configs={'config.json':self.config,'runtime.json':self.runtime,'TARGET_ACCEPTANCE.json':self.acceptance,
                 'INDEPENDENT_REVIEW_TRUST.json':{'install_anchors':{}}}
        for name,value in configs.items():(release.CONFIG/name).write_bytes(canonical(value))
        def config(path):
            self.reads.append(path.name)
            if path.name=='publisher.json':raise Denied('HOLD:FIXTURE_PUBLISHER_NOT_PROVIDED')
            return copy.deepcopy(configs[path.name])
        class Evidence:
            def __init__(s,path):s.path=str(path)
            def __str__(s):return s.path
            def is_absolute(s):return True
            def stat(s):return SimpleNamespace(st_uid=0,st_mode=0o600)
            def read_bytes(s):return self.evidence
        def safe(path):
            return Evidence(path) if str(path).startswith('/var/lib/xuanjun-customer-preflight/') else Path(path)
        with ExitStack() as stack:
            for p in (patch.object(release,'source',return_value=(self.manifest,self.raw,{})),
                patch.object(release,'private_config',side_effect=config),patch.object(release,'private_path',side_effect=safe),
                patch.object(release,'isolated_python_identity',return_value={'sha256':'a'*64}),
                patch('cryptography.__version__','46.0.3'),
                patch.object(release.os,'geteuid',return_value=0),
                patch.object(release.os,'uname',return_value=SimpleNamespace(nodename='iZvt5t8tlrm8oiZ')),
                patch.object(release.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=12345,pw_gid=12345,pw_shell='/usr/sbin/nologin')),
                patch('grp.getgrnam',return_value=SimpleNamespace(gr_gid=100)),
                patch.object(release,'run',return_value=b'user nginx;'),patch.object(release,'inventory',return_value={'files':{},'master':'fixture'}),
                patch.object(release,'archive_binding',return_value='c'*64)):
                stack.enter_context(p)
            return release.plan(self.source)
    def test_actual_plan_smtp_four_evidence_without_publisher(self):
        result=self.invoke()
        self.assertEqual(result['deployment_profile'],profile.LOGIN_ONLY)
        self.assertNotIn('publisher.json',self.reads)
        self.assertNotIn('publisher_config_sha256',result)
        self.assertNotIn('telegram_credential_evidence_sha256',result)
        self.assertEqual(result['permit_window_seconds'],18000)
    def test_actual_full_plan_does_not_accept_login_materials(self):
        self.config.pop('deployment_profile');self.runtime.pop('deployment_profile')
        with self.assertRaises(Denied):self.invoke()
    def test_actual_plan_profile_mismatch_rejected(self):
        self.runtime.pop('deployment_profile')
        with self.assertRaisesRegex(Denied,'DEPLOYMENT_PROFILE_BINDING'):self.invoke()
    def test_actual_plan_missing_login_security_evidence_rejected(self):
        self.acceptance['evidence'].pop('login_session_security')
        with self.assertRaisesRegex(Denied,'TARGET_ACCEPTANCE_BINDING'):self.invoke()
