import contextlib
import copy
import errno
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'deploy/pr122-oauth-candidate'), str(ROOT/'deploy/pr122-backend-migration')]
import custody
import private_source
from private_identity import PrivateIdentityVerifier


class FakeFence:
    def __init__(self, second=None):
        self.calls = 0
        self.second = second

    def check(self):
        self.calls += 1
        if self.calls == 2 and self.second:
            self.second()
        return {'ActiveState':'inactive','SubState':'dead','MainPID':'0'}


class PrivateAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr122-private-adapter-test-')
        self.root = Path(self.temp.name)
        self.state = self.root/'state';self.state.mkdir(mode=0o700)
        self.operations = self.root/'operations';self.operations.mkdir(mode=0o700)
        for name in ('values','metadata'):(self.operations/name).mkdir(mode=0o700)
        (self.state/'sessions').mkdir(mode=0o700)
        self.files = private_source.PrivateFiles(self.state,self.operations,uid=os.geteuid())
        self.guard = FakeFence()
        self.secret = 'SYNTHETIC_PRIVATE_ADAPTER_SECRET'
        self.session = dict(submission_id='portal_fixture',required_credential_types=['tiktok'])
        self.write(self.state/'sessions/portal_fixture.json',self.session)

    def tearDown(self):
        self.temp.cleanup()

    def write(self,path,value,text=False):
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        path.write_text(value if text else json.dumps(value))
        path.chmod(0o600)

    def secret_pair(self):
        self.write(self.operations/'values/TIKTOK_CLIENT_KEY.secret',self.secret,text=True)
        self.write(self.operations/'metadata/TIKTOK_CLIENT_KEY.json',dict(ref='TIKTOK_CLIENT_KEY',
            provider='tiktok',configured=True,value_path='/not/read/by/this/adapter',metadata={}))

    def read(self,**kwargs):
        return private_source.read_fenced_snapshot(cutover_id='fixture',session_ids=['portal_fixture'],
            providers=['tiktok'],account_identity_hashes={},files=self.files,guard=kwargs.get('guard',self.guard))

    def test_private_data_returned_in_memory_never_printed_or_source_changed(self):
        self.secret_pair()
        original=(self.operations/'values/TIKTOK_CLIENT_KEY.secret').read_bytes()
        output=io.StringIO()
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
            snapshot,fence,receipt=self.read()
        self.assertEqual(output.getvalue(),'')
        self.assertEqual(snapshot['secrets']['TIKTOK_CLIENT_KEY']['value'],self.secret)
        self.assertEqual((self.operations/'values/TIKTOK_CLIENT_KEY.secret').read_bytes(),original)
        self.assertNotIn(self.secret,json.dumps(receipt))
        self.assertEqual(self.guard.calls,2)
        self.assertTrue(fence['portal_service_fenced'])
        self.assertFalse(fence['writer_fenced'])

    def test_portal_only_fence_not_misrepresented_as_all_writer_custody(self):
        snapshot,fence,_=self.read()
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_FENCED_SOURCE_ATTESTATION_REQUIRED'):
            custody.normalise(snapshot,generation=snapshot['source_generation'],cutover_id='fixture',fence=fence)

    def test_file_metadata_drift_during_second_guard_rejected(self):
        guard=FakeFence(second=lambda:self.write(self.state/'sessions/portal_fixture.json',dict(self.session,status='changed')))
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_SOURCE_GENERATION_CHANGED'):
            self.read(guard=guard)

    def test_failed_first_guard_does_not_read_private_files(self):
        class Denied:
            def check(self):raise custody.Hold('PORTAL_NOT_FENCED')
        with mock.patch.object(self.files,'read',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(custody.Hold,'PORTAL_NOT_FENCED'):
                self.read(guard=Denied())

    def test_missing_required_session_not_treated_as_empty(self):
        (self.state/'sessions/portal_fixture.json').unlink()
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_REQUIRED_FILE_MISSING'):
            self.read()

    def test_symbolic_link_secret_not_followed(self):
        target=self.root/'outside';self.write(target,self.secret,text=True)
        (self.operations/'values/TIKTOK_CLIENT_KEY.secret').symlink_to(target)
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_SNAPSHOT_READ_UNKNOWN_PRESERVE_SOURCE'):
            self.read()

    def test_world_readable_private_file_rejected(self):
        (self.state/'sessions/portal_fixture.json').chmod(0o644)
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_SOURCE_FILE_IDENTITY'):
            self.read()

    def test_duplicate_json_key_rejected_without_echoing_value(self):
        self.write(self.state/'sessions/portal_fixture.json','{"x":"'+self.secret+'","x":2}',text=True)
        with self.assertRaisesRegex(custody.Hold,'DUPLICATE_PRIVATE_JSON_KEY') as caught:
            self.read()
        self.assertNotIn(self.secret,str(caught.exception))

    def test_unpaired_secret_metadata_rejected(self):
        self.write(self.operations/'metadata/TIKTOK_CLIENT_KEY.json',dict(ref='TIKTOK_CLIENT_KEY',provider='tiktok',configured=True))
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_SECRET_PAIR_INCOMPLETE'):
            self.read()

    def test_session_filename_or_provider_mismatch_rejected(self):
        for changed,code in [(dict(self.session,submission_id='wrong'),'PRIVATE_SESSION_FILENAME_MISMATCH'),
                             (dict(self.session,required_credential_types=['binance']),'PRIVATE_SESSION_PROVIDER_SCOPE_MISMATCH')]:
            with self.subTest(code=code):
                self.write(self.state/'sessions/portal_fixture.json',changed)
                with self.assertRaisesRegex(custody.Hold,code):self.read()

    def test_unexpected_state_entry_or_filename_rejected(self):
        directory=self.state/'tiktok-oauth-state';directory.mkdir(mode=0o700)
        self.write(directory/'unexpected.txt','no',text=True)
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_STATE_DIRECTORY_UNEXPECTED_ENTRY'):self.read()
        (directory/'unexpected.txt').unlink()
        self.write(directory/('a'*64+'.json'),dict(state_hash='b'*64))
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_STATE_FILENAME_MISMATCH'):self.read()

    def test_size_limit_rejected_before_any_target_exists(self):
        self.write(self.state/'sessions/portal_fixture.json','x'*131073,text=True)
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_READ_SIZE_LIMIT'):self.read()
        self.assertFalse((self.root/'target').exists())

    def test_default_guard_rejects_wrong_host_before_systemctl(self):
        with mock.patch.object(private_source.os,'uname',return_value=type('Host',(),{'nodename':'wrong'})()):
            with mock.patch.object(private_source.subprocess,'run',side_effect=AssertionError('must not run')):
                with self.assertRaisesRegex(custody.Hold,'TOKYO_ROOT_REQUIRED'):
                    private_source.PortalFence().check()

    def test_invalid_scope_types_rejected(self):
        for path in (('../outside',),('..',),('/absolute',),(None,)):
            with self.subTest(path=path),self.assertRaisesRegex(custody.Hold,'PRIVATE_PATH_INVALID'):
                self.files.read('state',path)
        for key,bad in [('session_ids',[{}]),('providers',[{}]),('account_identity_hashes',{'tiktok':'not-a-hash'})]:
            kwargs=dict(cutover_id='fixture',session_ids=[],providers=['tiktok'],account_identity_hashes={},files=self.files,guard=self.guard)
            kwargs[key]=bad
            with self.subTest(key=key):
                with self.assertRaises(custody.Hold):private_source.read_fenced_snapshot(**kwargs)

    def check_default_guard(self, unit, socket_error, *, expected_sha=None):
        entry=self.root/'entry.py';entry.write_bytes(b'synthetic source only');entry.chmod(0o755)
        actual_stat=os.fstat
        def fake_stat(fd):
            value=actual_stat(fd)
            return type('Identity',(),dict(st_mode=value.st_mode,st_uid=1000,st_nlink=value.st_nlink))()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(private_source.os,'geteuid',return_value=0))
            stack.enter_context(mock.patch.object(private_source.os,'uname',return_value=type('Host',(),{'nodename':custody.SOURCE_HOST})()))
            stack.enter_context(mock.patch.object(private_source.subprocess,'run',return_value=type('Result',(),{'stdout':unit})()))
            stack.enter_context(mock.patch.object(private_source.socket,'create_connection',side_effect=socket_error))
            stack.enter_context(mock.patch.object(private_source,'ENTRY',entry))
            stack.enter_context(mock.patch.object(private_source,'SOURCE_SHA256',expected_sha or custody.digest(entry.read_text())))
            stack.enter_context(mock.patch.object(private_source.os,'fstat',side_effect=fake_stat))
            return private_source.PortalFence().check()

    def test_fixed_guard_requires_inactive_dead_and_zero_pid(self):
        for unit in ('ActiveState=active\nSubState=running\nMainPID=123\n',
                     'ActiveState=inactive\nSubState=dead\nMainPID=123\n'):
            with self.subTest(unit=unit),self.assertRaisesRegex(custody.Hold,'PORTAL_NOT_FENCED'):
                self.check_default_guard(unit,ConnectionRefusedError(errno.ECONNREFUSED,'synthetic'))

    def test_fixed_guard_refused_socket_and_exact_source_pass(self):
        result=self.check_default_guard('ActiveState=inactive\nSubState=dead\nMainPID=0\n',
                                       ConnectionRefusedError(errno.ECONNREFUSED,'synthetic'))
        self.assertEqual(result['MainPID'],'0')

    def test_fixed_guard_socket_timeout_is_unknown_not_fenced(self):
        with self.assertRaisesRegex(custody.Hold,'PORTAL_SOCKET_FENCE_UNKNOWN'):
            self.check_default_guard('ActiveState=inactive\nSubState=dead\nMainPID=0\n',TimeoutError())

    def test_fixed_guard_source_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(custody.Hold,'PORTAL_SOURCE_VERSION_CHANGED'):
            self.check_default_guard('ActiveState=inactive\nSubState=dead\nMainPID=0\n',
                ConnectionRefusedError(errno.ECONNREFUSED,'synthetic'),expected_sha='a'*64)

    def test_private_verifier_has_no_default_network_client(self):
        verifier=PrivateIdentityVerifier({'tiktok':'private-account'})
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_PROVIDER_CLIENT_NOT_ADMITTED'):
            verifier('tiktok',{})
        self.assertNotIn('private-account',repr(verifier))

    def test_tiktok_verifier_uses_exact_raw_identity_and_token_not_mask(self):
        expected='prefix-EXACT-identity-suffix'
        calls=[]
        class Client:
            def user_info(self,**kwargs):
                calls.append(kwargs)
                return {'data':{'user':{'open_id':expected,'display_name':'Synthetic'}}}
        records={'TIKTOK_ACCESS_TOKEN':{'value':self.secret}}
        actual=PrivateIdentityVerifier({'tiktok':expected},tiktok_client=Client())('tiktok',records)
        self.assertEqual(actual['raw_open_id'],expected)
        self.assertEqual(actual['access_token_sha256'],custody.digest(self.secret))
        self.assertEqual(calls,[{'access_token':self.secret}])
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_ACCOUNT_VERIFICATION_MISMATCH'):
            PrivateIdentityVerifier({'tiktok':'prefix-WRONG-identity-suffix'},tiktok_client=Client())('tiktok',records)

    def test_douyin_exact_identity_verification_and_safe_failure(self):
        expected='synthetic-douyin-account'
        class Client:
            def user_info(self,**kwargs):
                self.kwargs=kwargs
                return {'data':{'open_id':expected,'error_code':0,'nickname':'Synthetic'}}
        client=Client();records={'DOUYIN_ACCESS_TOKEN':{'value':self.secret}}
        result=PrivateIdentityVerifier({'douyin':expected},douyin_client=client)('douyin',records)
        self.assertEqual(client.kwargs,{'access_token':self.secret,'open_id':expected})
        self.assertEqual(result['raw_open_id'],expected)
        secret = self.secret
        class Failed:
            def user_info(self,**kwargs):raise ValueError(secret)
        with self.assertRaisesRegex(custody.Hold,'PRIVATE_IDENTITY_CHECK_UNKNOWN'):
            PrivateIdentityVerifier({'douyin':expected},douyin_client=Failed())('douyin',records)


if __name__=='__main__':unittest.main(verbosity=2)
