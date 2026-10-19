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


class FirstLoginCredentialTests(unittest.TestCase):
    def config(self):
        return {'deployment_profile':profile.LOGIN_ONLY,
                'initialization_mode':profile.INITIAL_LOGIN,
                'keys':{'v1':base64.b64encode(b'D'*32).decode()},'active_key':'v1',
                'backup_key':base64.b64encode(b'B'*32).decode(),
                'backup_key_ref':'synthetic-planned-custody',
                'providers':{'smtp':{'host':'fixture.invalid'}}}
    def test_only_explicit_first_login_can_omit_authority(self):
        config=self.config()
        self.assertEqual(profile.initialization_mode(config),profile.INITIAL_LOGIN)
        self.assertIs(profile.validate_admin_keys(config),True)
        config.pop('initialization_mode')
        self.assertIsNone(profile.initialization_mode(config))
        with self.assertRaises(Denied):profile.validate_admin_keys(config)
        config['deployment_profile']=profile.FULL
        with self.assertRaises(Denied):profile.validate_admin_keys(config)
        config['authority_verify_key']=base64.b64encode(b'A'*32).decode()
        self.assertIs(profile.validate_admin_keys(config),True)
        config.pop('deployment_profile')
        self.assertIs(profile.validate_admin_keys(config),True)
    def test_first_rejects_full_unknown_marker_and_present_authority(self):
        cases=[('initialization_mode',x) for x in (None,True,'',{},'FIRST',profile.INITIAL_LOGIN+' ')]
        cases += [('deployment_profile',profile.FULL),('deployment_profile','LOGIN_ONLY')]
        cases += [('authority_verify_key',x) for x in (None,'',False,base64.b64encode(b'A'*32).decode())]
        for field,value in cases:
            with self.subTest(field=field,value=repr(value)):
                config=self.config();config[field]=value
                with self.assertRaises(Denied):profile.initialization_mode(config)
    def test_first_keys_backup_reference_and_separation_stay_required(self):
        for field in ('keys','active_key','backup_key','backup_key_ref'):
            with self.subTest(missing=field):
                config=self.config();config.pop(field)
                with self.assertRaises(Denied):profile.validate_admin_keys(config)
        for value in ('',None,False):
            with self.subTest(backup_ref=repr(value)):
                config=self.config();config['backup_key_ref']=value
                with self.assertRaises(Denied):profile.validate_admin_keys(config)
        for key_id in ('v1','retired'):
            with self.subTest(equal_backup=key_id):
                config=self.config();config['keys'][key_id]=config['backup_key']
                with self.assertRaises(Denied):profile.validate_admin_keys(config)
        for value in ('bad!',base64.b64encode(b'D'*31).decode(),None,True):
            with self.subTest(data=repr(value)):
                config=self.config();config['keys']['v1']=value
                with self.assertRaises(Denied):profile.validate_admin_keys(config)
    def test_admin_self_validation_is_distinct_from_real_runtime_whitelist(self):
        from scripts import pr122_customer_ops as ops
        config=self.config()
        self.assertEqual(profile.validate_pair(config,config),profile.LOGIN_ONLY)
        runtime={k:copy.deepcopy(config[k]) for k in ('deployment_profile','keys','active_key','providers')}
        self.assertTrue(ops.validate_runtime_contexts(config,runtime))
        runtime['initialization_mode']=profile.INITIAL_LOGIN
        with self.assertRaises(Denied):ops.validate_runtime_contexts(config,runtime)
    def test_first_configuration_reuse_does_not_require_new_authority(self):
        from scripts import pr122_customer_ops as ops
        config=self.config();config['keys']['retired']=base64.b64encode(b'R'*32).decode()
        before=copy.deepcopy(config)
        with patch.object(ops,'Center') as center:
            self.assertIs(ops.factory(config),center.return_value)
        self.assertEqual(config,before)
        self.assertEqual(center.call_args.args[1],{'v1':b'D'*32,'retired':b'R'*32})
        self.assertEqual(center.call_args.args[2],'v1')
        self.assertNotIn('authority_verify_key',config)


class FirstLoginIdentityRecordTests(unittest.TestCase):
    def setUp(self):
        self.observation={'target':release.HOST if hasattr(release,'HOST') else 'iZvt5t8tlrm8oiZ',
                          'observed_unix':100000,'subject':'CANONICAL_IDENTITY_INVENTORY',
                          'synthetic_note':'NOT_TARGET_EVIDENCE'}
        self.record={'schema':1,'target':self.observation['target'],
                     'deployment_profile':profile.LOGIN_ONLY,'initialization_mode':profile.INITIAL_LOGIN,
                     'manifest_sha256':'a'*64,'target_state':'ABSENT',
                     'identity_decision':'NO_EXISTING_AUTHORITATIVE_IDENTITY',
                     'observation_ref':'/var/lib/xuanjun-customer-preflight/synthetic-observation.json',
                     'observation_sha256':digest(canonical(self.observation)),'observed_unix':100000}
    def validate(self,record=None,observation=None,**options):
        return profile.validate_first_identity_record(
            self.record if record is None else record,self.observation if observation is None else observation,
            **{'manifest_sha256':'a'*64,'now':100001,**options})
    def test_record_paths_and_source_unicode_are_strict_utf8(self):
        for surrogate in ('\ud800','\udc00'):
            path='/var/lib/xuanjun-customer-preflight/synthetic-'+surrogate+'.json'
            with self.subTest(path_codepoint=hex(ord(surrogate))):
                with self.assertRaises(Denied):profile.first_evidence_path(path)
                with self.assertRaises(Denied):self.validate({**self.record,'observation_ref':path})
            for kind in ('top_value','nested_value','top_key','nested_key'):
                with self.subTest(source=kind,codepoint=hex(ord(surrogate))):
                    observation=copy.deepcopy(self.observation)
                    if kind=='top_value':observation['extra']='synthetic-'+surrogate
                    elif kind=='nested_value':observation['extra']={'rows':[1,{'value':'synthetic-'+surrogate}]}
                    elif kind=='top_key':observation['synthetic-'+surrogate]='value'
                    else:observation['extra']={'rows':[{'synthetic-'+surrogate:'value'}]}
                    with self.assertRaises(Denied):self.validate(observation=observation)
        value={**self.observation,'extra':{'rows':[{'测试':'\U0001f680'}]}}
        for escaped in (False,True):
            with self.subTest(valid_unicode_escaped=escaped):
                observation=json.loads(json.dumps(value,ensure_ascii=escaped))
                self.assertIs(self.validate(observation=observation),True)
        self.assertEqual(profile.first_evidence_path('/var/lib/xuanjun-customer-preflight/测试.json'),
                         '/var/lib/xuanjun-customer-preflight/测试.json')
    def test_exact_record_and_nonsecret_source_header_are_bound(self):
        self.assertIs(self.validate(),True)
        self.assertIs(self.validate(now=100000),True)
        self.assertIs(self.validate(now=118000),True)
        self.assertIs(self.validate(now=100001.5),True)
        self.assertIs(self.validate(observation={**self.observation,'additional_inventory':[]}),True)
    def test_exact_schema_types_and_required_fields_fail_closed(self):
        for field in self.record:
            with self.subTest(missing=field):
                record=copy.deepcopy(self.record);record.pop(field)
                with self.assertRaises(Denied):self.validate(record)
        for record in (None,[],{}, {**self.record,'schema':True},{**self.record,'approved':True}):
            with self.subTest(record=repr(record)),self.assertRaises(Denied):
                profile.validate_first_identity_record(record,self.observation,manifest_sha256='a'*64,now=100001)
    def test_unknown_existing_restore_conflict_and_mapped_identity_never_qualify(self):
        for value in ('UNKNOWN','EXISTING','RESTORE','PARTIAL','CONFLICT',None,True):
            with self.subTest(state=repr(value)),self.assertRaises(Denied):
                self.validate({**self.record,'target_state':value})
        for value in ('MAPPED_EXISTING','APPROVED_MAPPING','UNKNOWN','',None):
            with self.subTest(identity=value),self.assertRaises(Denied):
                self.validate({**self.record,'identity_decision':value})
    def test_target_profile_manifest_and_source_header_mismatch_rejected(self):
        for field,value in (('target','foreign-host'),('deployment_profile','FULL'),
                            ('initialization_mode','UNKNOWN'),('manifest_sha256','b'*64),
                            ('observation_sha256','Z'*64)):
            with self.subTest(record=field),self.assertRaises(Denied):self.validate({**self.record,field:value})
        for field,value in (('target','foreign-host'),('observed_unix',99999),
                            ('subject','OTHER_INVENTORY')):
            with self.subTest(observation=field),self.assertRaises(Denied):
                self.validate(observation={**self.observation,field:value})
    def test_expiry_future_and_boolean_or_noninteger_times_rejected(self):
        for now in (99999,118001,True,float('nan'),float('inf'),-float('inf'),'100001',-1):
            with self.subTest(now=repr(now)),self.assertRaises(Denied):self.validate(now=now)
        for value in (True,100000.0,'100000',-1):
            with self.subTest(observed=repr(value)),self.assertRaises(Denied):
                self.validate({**self.record,'observed_unix':value},
                              {**self.observation,'observed_unix':value})
    def test_observation_path_must_be_canonical_and_in_original_scope(self):
        paths=('relative.json','/etc/secret','/var/lib/xuanjun-customer-preflight',
               '/var/lib/xuanjun-customer-preflight/../outside',
               '/var/lib/xuanjun-customer-preflight//source.json',
               '/var/lib/xuanjun-customer-preflight/./source.json',
               '//var/lib/xuanjun-customer-preflight/source.json')
        for path in paths:
            with self.subTest(path=path),self.assertRaises(Denied):
                self.validate({**self.record,'observation_ref':path})


class FirstLoginActualPlanTests(unittest.TestCase):
    def setUp(self):
        LoginActualPlanTests.setUp(self)
        self.config.pop('authority_verify_key')
        self.config['initialization_mode']=profile.INITIAL_LOGIN
        self.config['backup_key']=base64.b64encode(b'B'*32).decode()
        self.now=100001
        self.observation={'target':'iZvt5t8tlrm8oiZ','observed_unix':100000,
                          'subject':'CANONICAL_IDENTITY_INVENTORY','synthetic_note':'NOT_TARGET_EVIDENCE'}
        self.record={'schema':1,'target':'iZvt5t8tlrm8oiZ','deployment_profile':profile.LOGIN_ONLY,
                     'initialization_mode':profile.INITIAL_LOGIN,'manifest_sha256':digest(self.raw),
                     'target_state':'ABSENT','identity_decision':'NO_EXISTING_AUTHORITATIVE_IDENTITY',
                     'observation_ref':'/var/lib/xuanjun-customer-preflight/synthetic-observation.json',
                     'observation_sha256':digest(canonical(self.observation)),'observed_unix':100000}
        self.source_bytes=canonical(self.observation)
        self.source_error=None
        self.protected_reads=[]
    def invoke(self):
        self.evidence=canonical(self.record)
        for item in self.acceptance['evidence'].values():item['sha256']=digest(self.evidence)
        def protected(path,*args,**kwargs):
            self.assertIs(kwargs.get('protected'),True)
            self.protected_reads.append(str(path))
            if str(path)==self.record['observation_ref']:
                if self.source_error:raise self.source_error
                return self.source_bytes
            if str(path)==self.acceptance['evidence']['canonical_identity_mapping']['path']:
                return self.evidence
            raise AssertionError('Unexpected protected read: '+str(path))
        with patch.object(request,'read_bytes',side_effect=protected),patch.object(release.time,'time',return_value=self.now):
            return LoginActualPlanTests.invoke(self)
    def test_record_and_source_do_not_autodetect_utf16_or_utf32(self):
        from unittest.mock import call
        record_path=self.acceptance['evidence']['canonical_identity_mapping']['path']
        for encoding in ('utf-16-le','utf-16-be','utf-32-le','utf-32-be'):
            for encoded_part in ('record','source'):
                with self.subTest(encoding=encoding,encoded_part=encoded_part):
                    source_raw=(json.dumps(self.observation,ensure_ascii=True).encode(encoding)
                                if encoded_part=='source' else canonical(self.observation))
                    record={**self.record,'observation_sha256':digest(source_raw)}
                    record_raw=(json.dumps(record,ensure_ascii=True).encode(encoding)
                                if encoded_part=='record' else canonical(record))
                    descriptor={'path':record_path,'sha256':digest(record_raw)}
                    # Both raw hashes are exact. Rejection must come from parsing
                    # UTF-8 text, never JSON's byte-input encoding autodetection.
                    with patch.object(request,'read_bytes',side_effect=[record_raw,source_raw]) as reader:
                        with self.assertRaises(Denied):
                            release.first_identity_evidence(descriptor,digest(self.raw),self.now)
                    expected=[call(record_path,protected=True)]
                    if encoded_part=='source':expected.append(call(record['observation_ref'],protected=True))
                    self.assertEqual(reader.call_args_list,expected)
    def test_protected_record_paths_and_raw_source_enforce_utf8(self):
        record_path=self.acceptance['evidence']['canonical_identity_mapping']['path']
        for surrogate in ('\ud800','\udc00'):
            bad_path='/var/lib/xuanjun-customer-preflight/synthetic-'+surrogate+'.json'
            with self.subTest(descriptor_path_codepoint=hex(ord(surrogate))), \
                 patch.object(request,'read_bytes') as reader:
                with self.assertRaises(Denied):
                    release.first_identity_evidence({'path':bad_path,'sha256':'a'*64},digest(self.raw),self.now)
                reader.assert_not_called()
            record={**self.record,'observation_ref':bad_path}
            for escaped in (False,True):
                with self.subTest(record_escaped=escaped,codepoint=hex(ord(surrogate))):
                    raw=json.dumps(record,ensure_ascii=escaped).encode('utf-8','surrogatepass')
                    with patch.object(request,'read_bytes',return_value=raw) as reader:
                        with self.assertRaises(Denied):
                            release.first_identity_evidence({'path':record_path,'sha256':digest(raw)},
                                                            digest(self.raw),self.now)
                        reader.assert_called_once_with(record_path,protected=True)
            for kind in ('top_value','nested_value','top_key','nested_key','invalid_utf8'):
                with self.subTest(source=kind,codepoint=hex(ord(surrogate))):
                    observation=copy.deepcopy(self.observation)
                    if kind in ('top_value','invalid_utf8'):observation['extra']='synthetic-'+surrogate
                    elif kind=='nested_value':observation['extra']={'rows':[1,{'value':'synthetic-'+surrogate}]}
                    elif kind=='top_key':observation['synthetic-'+surrogate]='value'
                    else:observation['extra']={'rows':[{'synthetic-'+surrogate:'value'}]}
                    self.source_bytes=(json.dumps(observation,ensure_ascii=False).encode('utf-8','surrogatepass')
                                       if kind=='invalid_utf8' else json.dumps(observation,ensure_ascii=True).encode('utf-8'))
                    self.record['observation_sha256']=digest(self.source_bytes)
                    with self.assertRaises(Denied):self.invoke()
        observation={**self.observation,'extra':{'rows':[{'测试':'\U0001f680'}]}}
        for escaped in (False,True):
            with self.subTest(valid_source_unicode_escaped=escaped):
                self.source_bytes=json.dumps(observation,ensure_ascii=escaped).encode('utf-8')
                self.record['observation_sha256']=digest(self.source_bytes)
                self.assertEqual(self.invoke()['state'],'READONLY_PLAN')
    def test_fresh_authority_free_plan_keeps_four_evidence_and_bound_digests(self):
        result=self.invoke()
        self.assertEqual(result['state'],'READONLY_PLAN')
        self.assertEqual(result['production_changes'],0)
        self.assertEqual(set(self.acceptance['evidence']),set(profile.LOGIN_ACCEPTANCE))
        self.assertEqual(len(profile.LOGIN_ACCEPTANCE),4)
        self.assertEqual(result['config_sha256'],digest(canonical(self.config)))
        self.assertEqual(result['runtime_config_sha256'],digest(canonical(self.runtime)))
        self.assertEqual(result['target_acceptance_sha256'],digest(canonical(self.acceptance)))
        self.assertEqual(result['login_acceptance_sha256'],digest(canonical(self.acceptance['evidence'])))
        self.assertIn(self.record['observation_ref'],self.protected_reads)
        self.assertNotIn('publisher.json',self.reads)
        self.assertNotIn('authority_verify_key',self.config)
        self.assertEqual(result['permit_window_seconds'],18000)
    def test_preexisting_data_code_transaction_units_and_symlinks_precede_config(self):
        import os
        targets=(release.DATA,release.CODE,release.STATE/release.TXN,release.SNIPPET.parent,
                 *(release.UNIT/unit for unit in release.UNITS))
        for target in targets:
            for kind in ('file','directory','dangling-symlink'):
                with self.subTest(target=str(target),kind=kind):
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if kind=='file':target.write_bytes(b'synthetic-existing-state')
                    elif kind=='directory':target.mkdir()
                    else:target.symlink_to(self.b/'synthetic-missing')
                    self.reads.clear();self.protected_reads.clear()
                    try:
                        with self.assertRaisesRegex(Denied,'PREEXISTING'):self.invoke()
                        self.assertEqual(self.reads,[])
                        self.assertEqual(self.protected_reads,[])
                        self.assertTrue(os.path.lexists(target))
                    finally:
                        if kind=='directory':target.rmdir()
                        else:target.unlink()
    def test_unknown_existing_restore_or_conflict_assessment_refuses_plan(self):
        for state in ('UNKNOWN','EXISTING','RESTORE','PARTIAL','CONFLICT'):
            with self.subTest(state=state):
                self.record['target_state']=state
                with self.assertRaises(Denied):self.invoke()
        self.record['target_state']='ABSENT'
        self.record['identity_decision']='MAPPED_EXISTING'
        with self.assertRaises(Denied):self.invoke()
    def test_observation_raw_hash_and_header_drift_refuse_plan(self):
        original=self.source_bytes
        for source in (original+b' ',canonical({**self.observation,'target':'foreign-host'})):
            with self.subTest(source=source):
                self.source_bytes=source
                with self.assertRaises(Denied):self.invoke()
        self.source_bytes=canonical({**self.observation,'subject':'OTHER_INVENTORY'})
        self.record['observation_sha256']=digest(self.source_bytes)
        with self.assertRaises(Denied):self.invoke()
    def test_hash_bound_duplicate_or_nonfinite_source_is_rejected(self):
        valid=canonical(self.observation)
        for source in (valid[:-1]+b',"extra":1,"extra":2}',
                       valid[:-1]+b',"extra":NaN}',
                       valid[:-1]+b',"extra":1e999}',
                       valid[:-1]+b',"extra":{"rows":[1,{"value":-1e999}]}}',b'{not-json}'):
            with self.subTest(source=source):
                self.source_bytes=source
                self.record['observation_sha256']=digest(source)
                with self.assertRaises(Denied):self.invoke()
        self.source_bytes=canonical({**self.observation,'extra':{'rows':[1.25,{'value':-2.5}]}})
        self.record['observation_sha256']=digest(self.source_bytes)
        self.assertEqual(self.invoke()['state'],'READONLY_PLAN')
    def test_stale_future_or_unbound_manifest_refuse_plan(self):
        for now in (99999,118001):
            with self.subTest(now=now):
                self.now=now
                with self.assertRaises(Denied):self.invoke()
        self.now=100001;self.record['manifest_sha256']='f'*64
        with self.assertRaises(Denied):self.invoke()
    def test_original_protected_reader_denials_are_not_bypassed(self):
        for reason in ('ROOT_CONFIG_MODE','PROTECTED_SINGLE_LINK','PROTECTED_SYMLINK','PROTECTED_CHANGED_DURING_READ'):
            with self.subTest(reason=reason):
                self.source_error=Denied(reason)
                with self.assertRaisesRegex(Denied,reason):self.invoke()
    def test_first_missing_or_extra_evidence_category_cannot_emit_plan(self):
        original=copy.deepcopy(self.acceptance)
        for field in profile.LOGIN_ACCEPTANCE:
            with self.subTest(missing=field):
                self.acceptance=copy.deepcopy(original)
                self.acceptance['evidence'].pop(field)
                with self.assertRaisesRegex(Denied,'TARGET_ACCEPTANCE_BINDING'):self.invoke()
        self.acceptance=copy.deepcopy(original)
        self.acceptance['evidence']['new_fifth_category']=copy.deepcopy(self.acceptance['evidence']['key_backup_recovery'])
        with self.assertRaisesRegex(Denied,'TARGET_ACCEPTANCE_BINDING'):self.invoke()
    def test_first_mismatched_runtime_and_relabelled_full_are_rejected(self):
        runtime=copy.deepcopy(self.runtime)
        for field,value in (('deployment_profile',profile.FULL),('active_key','other'),
                            ('keys',{'k':base64.b64encode(b'Q'*32).decode()}),
                            ('initialization_mode',profile.INITIAL_LOGIN)):
            with self.subTest(field=field):
                self.runtime={**copy.deepcopy(runtime),field:value}
                with self.assertRaises(Denied):self.invoke()
        self.runtime=runtime;self.config['deployment_profile']=profile.FULL
        self.runtime['deployment_profile']=profile.FULL
        with self.assertRaises(Denied):self.invoke()
