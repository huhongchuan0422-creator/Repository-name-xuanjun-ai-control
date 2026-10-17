import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest import mock

ROOT=Path(__file__).parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('domestic_owner')
h=load('domestic_helper')


def sample():
    permit=dict(schema=1,source_writer_principal='source-person',reviewer_principal='task5-person',
                owner_principal='owner-person',custody_evidence_sha256='a'*64,nonce='b'*64,
                issued_at='2026-10-17T10:00:00Z',expires_at='2026-10-17T10:30:00Z',
                helper_sha256='c'*64,wrapper_sha256='d'*64,policy_sha256='e'*64,
                review_source='original-task5-pr122',github_author_id=332398908,github_app_id=1144995,
                scope=h.SCOPE,host=h.HOST,runner_uid=1002,max_executions=1,channel_sha256=h.CHANNEL_SHA,
                payload_sha256=h.PAYLOAD_SHA,probe_sha256=h.PROBE_SHA,creation_authorized=False)
    body=h.PREFIX+json.dumps(permit)
    comment=dict(id=123,body=body,url=f'https://api.github.com/repos/{h.REPO}/issues/comments/123',
                 issue_url=f'https://api.github.com/repos/{h.REPO}/issues/122',html_url=f'https://github.com/{h.REPO}/pull/122#issuecomment-123',
                 user={'id':332398908},performed_via_github_app={'id':1144995})
    return permit,comment,hashlib.sha256(body.encode()).hexdigest()


class OwnerTests(unittest.TestCase):
    def test_owner_rejects_runner(self):
        with mock.patch.object(m.os,'getuid',return_value=1002):
            with self.assertRaisesRegex(ValueError,'OWNER_ROOT_REQUIRED'):m.owner()

    def test_owner_rejects_sudo_runner(self):
        with mock.patch.object(m.os,'getuid',return_value=0),mock.patch.object(m.os,'geteuid',return_value=0),mock.patch.object(m.os,'uname',return_value=types.SimpleNamespace(nodename=m.HOST)),mock.patch.dict(m.os.environ,{'SUDO_UID':'1002'}):
            with self.assertRaisesRegex(ValueError,'OWNER_ROOT_REQUIRED'):m.owner()

    def test_manifest_mismatch_never_imports(self):
        plan={'manifest':{'schema':1,'scope':'DOMESTIC_READONLY_BOOTSTRAP_20261017','files':{}}}
        with mock.patch.object(m,'owner'),mock.patch.object(m,'read_fixed',side_effect=[json.dumps(plan).encode(),b'{}']),mock.patch.object(m,'exec',create=True) as ex:
            with self.assertRaisesRegex(ValueError,'STAGED_MANIFEST_DRIFT'):m.load_helper()
            ex.assert_not_called()

    def test_helper_digest_mismatch_never_imports(self):
        manifest={'schema':1,'scope':'DOMESTIC_READONLY_BOOTSTRAP_20261017','files':{'domestic_owner.py':{'sha256':hashlib.sha256(b'owner').hexdigest(),'size':5},'domestic-readonly-helper.py':{'sha256':'a'*64,'size':6}}}
        reads=[json.dumps({'manifest':manifest}).encode(),json.dumps(manifest).encode(),b'owner',b'helper']
        with mock.patch.object(m,'owner'),mock.patch.object(m,'read_fixed',side_effect=reads),mock.patch.object(m,'exec',create=True) as ex:
            with self.assertRaisesRegex(ValueError,'HELPER_MANIFEST_HASH'):m.load_helper()
            ex.assert_not_called()

    def helper_context(self,stack):
        permit,comment,sha=sample()
        stack.enter_context(mock.patch.object(h,'_owner_check_baseline',create=True))
        stack.enter_context(mock.patch.object(h,'fetch_comment',return_value=comment))
        stack.enter_context(mock.patch.object(h,'now',return_value=h.timestamp('2026-10-17T10:10:00Z')))
        stack.enter_context(mock.patch.object(h,'check_files'))
        return permit,comment,sha

    def test_pin_exact_external_evidence(self):
        with contextlib.ExitStack() as stack:
            _,_,sha=self.helper_context(stack)
            pin=m.pin_from_comment(h,123,sha,'a'*64)
            self.assertEqual(pin['comment_id'],123)
            self.assertEqual(set(pin),h.PIN_FIELDS)

    def test_wrong_body_or_custody_evidence(self):
        with contextlib.ExitStack() as stack:
            _,_,sha=self.helper_context(stack)
            for body,custody in [('f'*64,'a'*64),(sha,'f'*64)]:
                with self.subTest(body=body,custody=custody):
                    with self.assertRaises(ValueError):m.pin_from_comment(h,123,body,custody)

    def test_enroll_exclusive_and_no_execution(self):
        with contextlib.ExitStack() as stack:
            _,_,sha=self.helper_context(stack)
            stack.enter_context(mock.patch.object(m,'load_helper',return_value=h))
            stack.enter_context(mock.patch.object(m,'locks',return_value=contextlib.nullcontext()))
            stack.enter_context(mock.patch.object(m,'absent'))
            create=stack.enter_context(mock.patch.object(m,'create_fixed'))
            run=stack.enter_context(mock.patch.object(m.subprocess,'run'))
            result=m.enroll(123,sha,'a'*64)
            self.assertFalse(result['probe_executed']);run.assert_not_called()
            self.assertEqual(create.call_args.args[0],m.TRUST)
            self.assertEqual(create.call_args.args[2],0o600)

    def test_existing_pin_denies_enrollment(self):
        with mock.patch.object(h,'_owner_check_baseline',create=True),mock.patch.object(m,'load_helper',return_value=h),mock.patch.object(m,'locks',return_value=contextlib.nullcontext()),mock.patch.object(m,'absent',side_effect=ValueError('exists')),mock.patch.object(m,'create_fixed') as create:
            with self.assertRaises(ValueError):m.enroll(123,'a'*64,'b'*64)
            create.assert_not_called()

    def execute_context(self,stack):
        _,_,sha=self.helper_context(stack)
        pin=m.pin_from_comment(h,123,sha,'a'*64)
        stack.enter_context(mock.patch.object(m,'load_helper',return_value=h))
        stack.enter_context(mock.patch.object(m,'locks',side_effect=lambda p:contextlib.nullcontext()))
        stack.enter_context(mock.patch.object(m,'absent'))
        stack.enter_context(mock.patch.object(m,'read_fixed',return_value=json.dumps(pin).encode()))
        stack.enter_context(mock.patch.object(m.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1002)))
        create=stack.enter_context(mock.patch.object(m,'create_fixed'))
        return create

    def test_exact_double_sudo_and_intent_before_dispatch(self):
        with contextlib.ExitStack() as stack:
            create=self.execute_context(stack)
            def dispatch(*args,**kw):
                create.assert_called_once();self.assertEqual(create.call_args.args[0],m.INTENT)
                self.assertEqual(args[0],m.COMMAND);self.assertFalse(kw['shell'])
                return types.SimpleNamespace(returncode=0,stdout=b'{}',stderr=b'')
            run=stack.enter_context(mock.patch.object(m.subprocess,'run',side_effect=dispatch))
            stack.enter_context(mock.patch.object(m,'export_result',return_value={'state':'READONLY_OBSERVED_ACCOUNT_CREATION_HOLD'}))
            m.execute();run.assert_called_once()

    def test_failed_dispatch_no_retry_and_non_success(self):
        with contextlib.ExitStack() as stack:
            self.execute_context(stack)
            run=stack.enter_context(mock.patch.object(m.subprocess,'run',side_effect=TimeoutError))
            with self.assertRaisesRegex(ValueError,'UNKNOWN_DISPATCH_NO_RETRY'):m.execute()
            run.assert_called_once()

    def test_preexisting_attempt_denies_dispatch(self):
        with contextlib.ExitStack() as stack:
            self.execute_context(stack)
            stack.enter_context(mock.patch.object(m,'absent',side_effect=ValueError('exists')))
            run=stack.enter_context(mock.patch.object(m.subprocess,'run'))
            with self.assertRaises(ValueError):m.execute()
            run.assert_not_called()

    def test_runner_name_must_still_be_uid1002(self):
        with contextlib.ExitStack() as stack:
            self.execute_context(stack)
            stack.enter_context(mock.patch.object(m.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=2000)))
            run=stack.enter_context(mock.patch.object(m.subprocess,'run'))
            with self.assertRaisesRegex(ValueError,'RUNNER_UID_DRIFT'):m.execute()
            run.assert_not_called()

    def test_execute_lifecycle_denial_before_dispatch(self):
        with contextlib.ExitStack() as stack:
            self.execute_context(stack)
            stack.enter_context(mock.patch.object(h,'check_files',side_effect=ValueError('ROLLBACK_STARTED')))
            run=stack.enter_context(mock.patch.object(m.subprocess,'run'))
            with self.assertRaisesRegex(ValueError,'ROLLBACK_STARTED'):m.execute()
            run.assert_not_called()

    def test_nested_metadata_preserved_without_unbounded_data(self):
        data={'state':'READONLY_OBSERVED_ACCOUNT_CREATION_HOLD','hostname':m.HOST,'account':'xuanjun-customer',
              'paths':{'/home':{'state':'PRESENT','uid':0,'secret':'bad'},'/secret':{'state':'PRESENT'}},
              'platform':{'uid_min':100,'ranges_ordered':True,'arbitrary':'bad'},
              'tools':{'/usr/sbin/useradd':{'metadata':{'state':'PRESENT','mode':33261},'identity':{'state':'OBSERVED','sha256':'a'*64,'size':123,'secret':'bad'}}},
              'canonical_lock':{'acquired_at_observation':True,'named_inode_stable':True,'metadata':{'state':'PRESENT','ino':123}},
              'target_package_identity':{'name':'shadow-utils','version':'1.2','actual_digest_matches':True,'secret':'bad'}}
        result=m.sanitize_result(data)
        self.assertEqual(result['paths'],{'/home':{'state':'PRESENT','uid':0}})
        self.assertEqual(result['platform'],{'ranges_ordered':True,'uid_min':100})
        self.assertEqual(result['tools']['/usr/sbin/useradd']['identity']['sha256'],'a'*64)
        self.assertTrue(result['canonical_lock']['named_inode_stable'])
        self.assertNotIn('bad',json.dumps(result))

    def test_export_allowlist(self):
        result=m.sanitize_result({'state':'READONLY_OBSERVED_ACCOUNT_CREATION_HOLD','hostname':m.HOST,
                                  'account':'xuanjun-customer','secret':'DO NOT EXPORT','paths':{'secret':'x'},
                                  'account_absence':'ABSENT','absence_snapshot_stable':True,'admission':{'comment_id':123,'arbitrary':'secret'}})
        self.assertNotIn('secret',result);self.assertEqual(result['paths'],{})
        self.assertEqual(result['account_absence'],'ABSENT');self.assertEqual(result['comment_id'],123)

    def test_unknown_export_remains_unknown(self):
        self.assertEqual(m.sanitize_result({'state':'UNKNOWN_CONSUMED_NO_RETRY','secret':'x'}),
                         {'state':'UNKNOWN_CONSUMED_NO_RETRY','retry_allowed':False,'creation_authorized':False})

    def test_unexpected_result_rejected(self):
        with self.assertRaises(ValueError):m.sanitize_result({'state':'success'})

    def test_no_arbitrary_write(self):
        with self.assertRaises(ValueError):m.create_fixed('/tmp/anything',{},0o600)

    def test_no_default_stage(self):
        with mock.patch('sys.argv',['owner']),mock.patch.object(m,'execute') as execute:
            with self.assertRaises(SystemExit):m.main()
            execute.assert_not_called()

    def test_enroll_exact_flags(self):
        with mock.patch('sys.argv',['owner','enroll','--comment-id','123','--body-sha256','a'*64,'--custody-sha256','b'*64]),mock.patch.object(m,'enroll',return_value={'state':'OWNER_PIN_ENROLLED'}) as enroll, mock.patch('builtins.print'):
            m.main();enroll.assert_called_once_with(123,'a'*64,'b'*64)

    def test_execute_extra_command_rejected(self):
        with mock.patch('sys.argv',['owner','execute','/bin/sh']),mock.patch.object(m,'execute') as execute:
            with self.assertRaises(SystemExit):m.main()
            execute.assert_not_called()

if __name__=='__main__':unittest.main()
