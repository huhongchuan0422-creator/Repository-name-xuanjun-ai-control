"""Pure policy and injected proc/descriptor tests; no host capability actions."""
import copy
import hashlib
import json
import os
import pathlib
import stat
import struct
import sys
import types
import unittest
from unittest import mock

# Staged-kit adapter: use only authenticated runtime imports.
import owner_process_identity as s
ROOT=pathlib.Path(s.__file__).resolve().parents[1]


def sha(raw):return hashlib.sha256(raw).hexdigest()


def info(**changes):
    data=dict(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o644,st_uid=0,st_gid=0,
              st_nlink=1,st_size=4,st_mtime_ns=10,st_ctime_ns=10)
    data.update(changes)
    return types.SimpleNamespace(**data)


class FakeConnection(object):
    def __init__(self, pid, uid, request):
        self.pid, self.uid = pid, uid
        self.raw = (json.dumps(request) + '\n').encode()
        self.sent = b''
        self.timeout = None
    def gettimeout(self): return self.timeout
    def settimeout(self, value): self.timeout = value
    def getsockopt(self, *unused): return struct.pack('3i', self.pid, self.uid, self.uid)
    def recv(self, maximum):
        value, self.raw = self.raw[:maximum], self.raw[maximum:]
        return value
    def sendall(self, value): self.sent += value


class OwnerProcessTests(unittest.TestCase):
    def setUp(self):
        self.pid=432;self.uid=1004;self.release='a'*64
        self.script='/opt/xuanjun-control-releases/integration-'+self.release[:16]+'/stage1/owner_callback_server.py'
        self.python='/usr/libexec/platform-python3.6'
        self.argv=s._expected_argv(self.script)
        self.unit=('''[Unit]\nDescription=callback\n[Service]\nUser=xuanjun-callback\nGroup=xuanjun-control-db\nExecStart='''+' '.join(self.argv)+'\n').encode()
        self.policy=dict(schema=1,callback_uid=self.uid,release_sha256=self.release,
            python_exe=self.python,python_sha256=sha(b'python'),script=self.script,
            script_sha256=sha(b'script'),unit_file=s.CALLBACK_UNIT,unit_sha256=sha(self.unit),
            argv=list(self.argv),cgroup=s.CALLBACK_CGROUP)
        self.raw=json.dumps(self.policy,sort_keys=True).encode()
        self.identities={path:s.native._file_identity(info(st_ino=n)) for n,path in enumerate(
            (s.OWNER_BINDING_FILE,s.CALLBACK_UNIT,self.script,self.python),10)}
        self.files={self.python:sha(b'python'),self.script:sha(b'script'),s.CALLBACK_UNIT:sha(self.unit)}
        self.proc={'status':b'Name:\tpython3\nPPid:\t1\nUid:\t1004 1004 1004 1004\n',
            'cmdline':b'\0'.join(x.encode() for x in self.argv)+b'\0',
            'cgroup':('0::'+s.CALLBACK_CGROUP+'\n').encode(),
            'stat':self.stat_raw(100)}
        self.proc_reads=[];self.file_reads=[]
        self.exe_path=self.python;self.exe_hash=sha(b'python');self.exe_identity=self.identities[self.python]
        self.patches=[mock.patch.object(s,'_read_protected',side_effect=self.read_protected),
            mock.patch.object(s,'_root_file_digest',side_effect=self.file_digest),
            mock.patch.object(s,'_root_file_identity',side_effect=lambda p:self.identities[p]),
            mock.patch.object(s.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1004)),
            mock.patch.object(s.native,'_proc_bytes',side_effect=self.proc_bytes),
            mock.patch.object(s.native,'_proc_exe_sha256',side_effect=self.exe_digest),
            mock.patch.object(s.native,'_proc_exe_file_identity',side_effect=self.exe_file)]
        for patch in self.patches:patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):patch.stop()

    def stat_raw(self,start):
        return ('432 (callback (name)) '+' '.join(['S','1']+['0']*17+[str(start)])+'\n').encode()

    def write_policy(self):self.raw=json.dumps(self.policy,sort_keys=True).encode()

    def read_protected(self,path,maximum=65536):
        self.file_reads.append(path)
        if path==s.OWNER_BINDING_FILE:return self.raw,self.identities[path]
        if path==s.CALLBACK_UNIT:return self.unit,self.identities[path]
        raise AssertionError('unexpected protected read '+path)

    def file_digest(self,path):
        self.file_reads.append(path)
        return self.files[path],self.identities[path]

    def proc_bytes(self,root,pid,name,maximum=65536):
        self.assertEqual(root,'/fixture-proc');self.assertEqual(pid,self.pid)
        self.proc_reads.append(name)
        return self.proc[name]

    def exe_digest(self,root,pid,path,uid):
        self.assertEqual(uid,0);self.assertEqual(root,'/fixture-proc');self.assertEqual(pid,self.pid)
        if path!=self.exe_path:raise ValueError('wrong exe path')
        return self.exe_hash,self.exe_identity

    def exe_file(self,root,pid,path):
        if path!=self.exe_path:raise ValueError('wrong exe path')
        return self.exe_identity

    def load(self):return s.load_owner_process_verifier(self.release,proc_root='/fixture-proc')

    def server_fixture(self):
        import uk_owner_callback_core as core
        self.assertEqual(pathlib.Path(core.__file__).resolve(), ROOT / 'stage1/uk_owner_callback_core.py')
        active = dict(ledger_uuid='u', generation=1, epoch=8, instance='i')
        store, ledger = mock.Mock(), mock.Mock()
        store.read.side_effect = lambda **unused: dict(active)
        ledger.owner_decision.return_value = dict(accepted=True, state='PENDING', task_id='task', fence=3)
        request = dict(active, operation='OWNER_DECISION', event=dict(request_id='request',
            task_id='task', fence=3, owner_user_id='owner', owner_chat_id='chat',
            update_id=1, decision='APPROVE'))
        server = core.LedgerOwnerDecisionServer(store, ledger, self.uid,
                                               owner_process_verifier=self.load())
        return server, store, ledger, FakeConnection(self.pid, self.uid, request)

    def test_concrete_gate_integrates_with_projection_owner_mutation(self):
        server, store, ledger, connection = self.server_fixture()
        server.serve_connection(connection)
        ledger.owner_decision.assert_called_once_with('task', 3, 'APPROVE',
            'request', 1, 'owner', 'chat', 'owner-callback:1004', True)
        self.assertIs(json.loads(connection.sent.decode())['accepted'], True)

    def test_same_uid_dashboard_denied_before_activation_or_mutation_in_server(self):
        server, store, ledger, connection = self.server_fixture()
        self.proc['cgroup'] = b'0::/system.slice/xuanjun-uk-owner-dashboard.service\n'
        with self.assertRaises(PermissionError): server.serve_connection(connection)
        store.read.assert_not_called(); ledger.owner_decision.assert_not_called()
        self.assertEqual(connection.sent, b'')

    def test_changed_pins_deny_server_before_activation_or_mutation(self):
        server, store, ledger, connection = self.server_fixture()
        self.files[s.CALLBACK_UNIT] = '0' * 64
        with self.assertRaises(PermissionError): server.serve_connection(connection)
        store.read.assert_not_called(); ledger.owner_decision.assert_not_called()

    def test_valid_callback_returns_literal_true(self):
        verifier=self.load();self.assertIs(verifier(self.pid,self.uid),True)
        self.assertEqual(self.proc_reads.count('stat'),2)
        for field in ('status','cmdline','cgroup'):self.assertEqual(self.proc_reads.count(field),2)

    def test_same_uid_dashboard_cgroup_denied_even_with_callback_argv(self):
        verifier=self.load();self.proc['cgroup']=b'0::/system.slice/xuanjun-uk-owner-dashboard.service\n'
        self.assertIs(verifier(self.pid,self.uid),False)

    def test_dashboard_argv_denied_even_with_callback_cgroup(self):
        verifier=self.load();self.proc['cmdline']=self.proc['cmdline'].replace(b'owner_callback_server.py',b'owner_dashboard.py')
        self.assertFalse(verifier(self.pid,self.uid))

    def test_wrong_uid_invalid_pid_types_denied_without_proc_reads(self):
        v=self.load()
        for pid,uid in ((432,1003),(432,0),(True,1004),(0,1004),(-1,1004),('432',1004),(432,True)):
            self.assertIs(v(pid,uid),False)
        self.assertEqual(self.proc_reads,[])

    def test_all_four_uid_slots_required(self):
        v=self.load()
        for slot in range(4):
            values=[1004]*4;values[slot]=1003
            self.proc['status']=('PPid:\t1\nUid:\t'+' '.join(map(str,values))+'\n').encode()
            self.assertFalse(v(self.pid,self.uid))
        self.proc['status']=b'PPid:\t1\nUid:\t1004 1004 1004\n'
        self.assertFalse(v(self.pid,self.uid))

    def test_missing_or_invalid_parent_rejected(self):
        v=self.load()
        for parent in ('0','-1','x'):
            self.proc['status']=('PPid:\t'+parent+'\nUid:\t1004 1004 1004 1004\n').encode()
            self.assertFalse(v(self.pid,self.uid))

    def test_wrong_executable_path_or_hash_rejected(self):
        v=self.load();self.exe_path='/other/python';self.assertFalse(v(self.pid,self.uid))
        self.exe_path=self.python;self.exe_hash='0'*64;self.assertFalse(v(self.pid,self.uid))

    def test_exact_argv_and_config_paths_required(self):
        v=self.load();original=self.proc['cmdline']
        cases=(original+b'\0',original.rstrip(b'\0'),original+b'--extra\0',
               original.replace(b'/usr/bin/python3',self.python.encode()),
               original.replace(b'owner-callback-auth',b'owner-dashboard-token'),
               original.replace(b'18557',b'18556'))
        for raw in cases:self.proc['cmdline']=raw;self.assertFalse(v(self.pid,self.uid))

    def test_exact_cgroup_supports_v1_but_rejects_prefix_suffix(self):
        v=self.load();self.proc['cgroup']=('1:name=systemd:'+s.CALLBACK_CGROUP+'\n').encode()
        self.assertTrue(v(self.pid,self.uid))
        for suffix in ('-other','/child'):
            self.proc['cgroup']=('0::'+s.CALLBACK_CGROUP+suffix+'\n').encode()
            self.assertFalse(v(self.pid,self.uid))

    def test_unrelated_controller_cannot_spoof_callback_service_cgroup(self):
        v=self.load()
        self.proc['cgroup']=('2:memory:'+s.CALLBACK_CGROUP+'\n1:name=systemd:/system.slice/xuanjun-uk-owner-dashboard.service\n').encode()
        self.assertFalse(v(self.pid,self.uid))
        self.proc['cgroup']=('2:memory:'+s.CALLBACK_CGROUP+'\n').encode()
        self.assertFalse(v(self.pid,self.uid))

    def test_conflicting_hybrid_cgroup_or_malformed_lines_rejected(self):
        v=self.load()
        for raw in (('0::'+s.CALLBACK_CGROUP+'\n1:name=systemd:/other\n').encode(),b'malformed\n'):
            self.proc['cgroup']=raw;self.assertFalse(v(self.pid,self.uid))

    def test_script_or_unit_hash_change_rejected(self):
        v=self.load()
        for path in (self.script,s.CALLBACK_UNIT):
            saved=self.files[path];self.files[path]='0'*64;self.assertFalse(v(self.pid,self.uid));self.files[path]=saved

    def test_binding_bytes_or_inode_change_rejected(self):
        v=self.load();old=self.raw;self.raw+=b' ';self.assertFalse(v(self.pid,self.uid));self.raw=old
        self.identities[s.OWNER_BINDING_FILE]=s.native._file_identity(info(st_ino=99))
        self.assertFalse(v(self.pid,self.uid))

    def test_missing_proc_status_and_eacces_fail_closed(self):
        v=self.load()
        for name in tuple(self.proc):
            raw=self.proc.pop(name);self.assertFalse(v(self.pid,self.uid));self.proc[name]=raw
        with mock.patch.object(s.native,'_proc_bytes',side_effect=PermissionError('EACCES')):
            self.assertFalse(v(self.pid,self.uid))

    def test_executable_read_error_fails_closed(self):
        v=self.load()
        with mock.patch.object(s.native,'_proc_exe_sha256',side_effect=OSError('EIO')):
            self.assertFalse(v(self.pid,self.uid))

    def test_script_unit_or_binding_read_error_fails_closed(self):
        v=self.load()
        with mock.patch.object(s,'_root_file_digest',side_effect=PermissionError('EACCES')):
            self.assertFalse(v(self.pid,self.uid))
        with mock.patch.object(s,'_read_protected',side_effect=FileNotFoundError('missing')):
            self.assertFalse(v(self.pid,self.uid))

    def test_pid_reuse_rejected(self):
        v=self.load();calls=[]
        def proc(root,pid,name,maximum=65536):
            result=self.proc_bytes(root,pid,name,maximum)
            if name=='stat':
                calls.append(1)
                if len(calls)>1:return self.stat_raw(101)
            return result
        with mock.patch.object(s.native,'_proc_bytes',side_effect=proc):self.assertFalse(v(self.pid,self.uid))

    def test_uid_parent_argv_and_cgroup_change_rejected(self):
        v=self.load()
        for field,changed in (('status',b'PPid:\t2\nUid:\t1004 1004 1004 1004\n'),
            ('status',b'PPid:\t1\nUid:\t1004 1003 1004 1004\n'),('cmdline',b'changed'),('cgroup',b'0::/other\n')):
            calls=[]
            def proc(root,pid,name,maximum=65536):
                value=self.proc_bytes(root,pid,name,maximum)
                if name==field:
                    calls.append(1)
                    if len(calls)>1:return changed
                return value
            with mock.patch.object(s.native,'_proc_bytes',side_effect=proc):self.assertFalse(v(self.pid,self.uid))

    def test_executable_identity_change_rejected(self):
        v=self.load()
        with mock.patch.object(s.native,'_proc_exe_file_identity',return_value=('different',)):
            self.assertFalse(v(self.pid,self.uid))

    def test_root_file_identity_change_rejected(self):
        v=self.load()
        for target in (self.script,s.CALLBACK_UNIT,s.OWNER_BINDING_FILE):
            def file_id(path):return ('different',) if path==target else self.identities[path]
            with mock.patch.object(s,'_root_file_identity',side_effect=file_id):self.assertFalse(v(self.pid,self.uid))

    def test_no_callback_secret_contents_read(self):
        v=self.load();self.assertTrue(v(self.pid,self.uid))
        self.assertEqual(set(self.file_reads),{s.OWNER_BINDING_FILE,s.CALLBACK_UNIT,self.script,self.python})

    def test_missing_policy_has_no_fallback(self):
        with mock.patch.object(s,'_read_protected',side_effect=FileNotFoundError('pins missing')):
            with self.assertRaises(FileNotFoundError):self.load()

    def test_binding_exact_root_root_0644_single_inode_contract(self):
        for changes in ({'st_uid':1004},{'st_gid':1006},{'st_mode':stat.S_IFREG|0o640},{'st_nlink':2}):
            self.identities[s.OWNER_BINDING_FILE]=s.native._file_identity(info(**changes))
            with self.assertRaises(ValueError):self.load()

    def test_missing_extra_or_type_confused_schema_rejected(self):
        original=copy.deepcopy(self.policy)
        for key in tuple(original):
            self.policy=copy.deepcopy(original);del self.policy[key];self.write_policy()
            with self.assertRaises(ValueError):self.load()
        for updates in ({'extra':1},{'schema':True},{'callback_uid':True},{'callback_uid':1005},
                        {'unit_file':'/tmp/other'},{'cgroup':'/system.slice/other.service'}):
            self.policy=copy.deepcopy(original);self.policy.update(updates);self.write_policy()
            with self.assertRaises(ValueError):self.load()

    def test_duplicate_keys_nonfinite_or_invalid_json_rejected(self):
        for raw in (b'{"schema":1,"schema":1}',b'{"schema":NaN}',b'[]',b'not json',b'\xff'):
            self.raw=raw
            with self.assertRaises((ValueError,UnicodeError)):self.load()

    def test_invalid_digest_or_noncanonical_python_rejected(self):
        original=copy.deepcopy(self.policy)
        for field in ('release_sha256','python_sha256','script_sha256','unit_sha256'):
            self.policy=copy.deepcopy(original);self.policy[field]='X'*64;self.write_policy()
            with self.assertRaises(ValueError):self.load()
        for path in ('relative','/usr/../python','//usr/python','/usr/python\0x'):
            self.policy=copy.deepcopy(original);self.policy['python_exe']=path;self.write_policy()
            with self.assertRaises(ValueError):self.load()

    def test_script_must_match_full_release_prefix_and_fixed_filename(self):
        for path in (self.script.replace('a'*16,'b'*16),self.script.replace('owner_callback_server.py','owner_dashboard.py'),'/tmp/callback.py'):
            self.policy['script']=path;self.policy['argv']=s._expected_argv(path);self.write_policy()
            with self.assertRaises(ValueError):self.load()

    def test_exact_full_release_required_not_just_prefix(self):
        wrong='a'*16+'b'*48
        with self.assertRaises(ValueError):s.load_owner_process_verifier(wrong,proc_root='/fixture-proc')
        for value in (None,True,'a'):
            with self.assertRaises(ValueError):s.load_owner_process_verifier(value)

    def test_nss_identity_mismatch_rejected(self):
        with mock.patch.object(s.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1005)):
            with self.assertRaises(ValueError):self.load()

    def test_policy_wrong_argv_or_secret_path_rejected(self):
        original=copy.deepcopy(self.policy)
        for argv in (self.argv+['--extra'],self.argv[:-1],self.argv[1:],tuple(self.argv)):
            self.policy=copy.deepcopy(original);self.policy['argv']=argv
            # JSON normalizes tuple to list, so validate that case directly.
            if isinstance(argv,tuple):
                with self.assertRaises(ValueError):s._validate_policy(self.policy)
            else:
                self.write_policy()
                with self.assertRaises(ValueError):self.load()

    def test_startup_python_script_hash_mismatch_rejected(self):
        for path in (self.python,self.script):
            old=self.files[path];self.files[path]='0'*64
            with self.assertRaises(ValueError):self.load()
            self.files[path]=old

    def test_startup_unit_hash_mismatch_rejected(self):
        self.unit+=b'# drift\n'
        with self.assertRaises(ValueError):self.load()

    def test_unit_critical_invocation_mismatch_or_duplicates_rejected(self):
        original=self.unit
        for raw in (original.replace(b'User=xuanjun-callback',b'User=root'),
                    original.replace(b'Group=xuanjun-control-db',b'Group=root'),
                    original.replace(b'--max-workers 8',b'--max-workers 9'),
                    original+b'User=xuanjun-callback\n',original+b'ExecStart=/bin/true\n'):
            self.unit=raw;self.policy['unit_sha256']=sha(raw);self.write_policy()
            with self.assertRaises(ValueError):self.load()


class ProtectedFileTests(unittest.TestCase):
    def test_regular_root_file_read_is_bounded_and_closes_fd(self):
        with mock.patch.object(s,'_protected_chain'),mock.patch.object(s.os,'open',return_value=91) as opened, \
             mock.patch.object(s.os,'fstat',return_value=info()),mock.patch.object(s.os,'read',side_effect=[b'data',b'']) as read, \
             mock.patch.object(s.os,'close') as close:
            raw,identity=s._read_protected('/safe/policy',maximum=4)
        self.assertEqual(raw,b'data');self.assertEqual(identity,s.native._file_identity(info()))
        self.assertEqual(read.call_args_list,[mock.call(91,5),mock.call(91,1)])
        flags=opened.call_args[0][1];self.assertTrue(flags&os.O_NOFOLLOW);self.assertTrue(flags&os.O_NONBLOCK)
        close.assert_called_once_with(91)

    def test_wrong_owner_mode_type_or_size_rejected_and_closed(self):
        for changes in ({'st_uid':1004},{'st_mode':stat.S_IFREG|0o666},{'st_mode':stat.S_IFIFO|0o600},
                        {'st_size':65537},{'st_size':-1}):
            with mock.patch.object(s,'_protected_chain'),mock.patch.object(s.os,'open',return_value=91), \
                 mock.patch.object(s.os,'fstat',return_value=info(**changes)),mock.patch.object(s.os,'close') as close:
                with self.assertRaises(ValueError):s._read_protected('/safe/policy')
                close.assert_called_once_with(91)

    def test_short_read_and_changed_metadata_rejected(self):
        for reads,after in (([b'dat',b''],info()),([b'data',b''],info(st_ctime_ns=11))):
            with mock.patch.object(s,'_protected_chain'),mock.patch.object(s.os,'open',return_value=91), \
                 mock.patch.object(s.os,'fstat',side_effect=[info(),after]),mock.patch.object(s.os,'read',side_effect=reads), \
                 mock.patch.object(s.os,'close') as close:
                with self.assertRaises(ValueError):s._read_protected('/safe/policy')
                close.assert_called_once_with(91)

    def test_read_growth_or_error_rejected_and_closed(self):
        for result in (b'12345',OSError('read failure')):
            with mock.patch.object(s,'_protected_chain'),mock.patch.object(s.os,'open',return_value=91), \
                 mock.patch.object(s.os,'fstat',return_value=info()),mock.patch.object(s.os,'read',side_effect=[result]), \
                 mock.patch.object(s.os,'close') as close:
                with self.assertRaises((ValueError,OSError)):s._read_protected('/safe/policy',maximum=4)
                close.assert_called_once_with(91)

    def test_chain_requires_root_nonwritable_directories_and_canonical_path(self):
        directory=info(st_mode=stat.S_IFDIR|0o755)
        with mock.patch.object(s.os.path,'realpath',side_effect=lambda p:p),mock.patch.object(s.os,'stat',return_value=directory) as st:
            s._protected_chain('/safe/policy')
            self.assertEqual(st.call_args_list,[mock.call('/safe',follow_symlinks=False),mock.call('/',follow_symlinks=False)])
        for changed in (info(st_mode=stat.S_IFDIR|0o755,st_uid=1004),info(st_mode=stat.S_IFDIR|0o775),info()):
            with mock.patch.object(s.os.path,'realpath',side_effect=lambda p:p),mock.patch.object(s.os,'stat',return_value=changed):
                with self.assertRaises(ValueError):s._protected_chain('/safe/policy')
        with mock.patch.object(s.os.path,'realpath',return_value='/elsewhere'):
            with self.assertRaises(ValueError):s._protected_chain('/safe/policy')

    def test_root_digest_delegates_stable_descriptor_hash_and_closes_fd(self):
        with mock.patch.object(s,'_protected_chain'),mock.patch.object(s.os,'open',return_value=91), \
             mock.patch.object(s.native,'_owned_fd_sha256',return_value=('hash',('identity',))) as digest, \
             mock.patch.object(s.os,'close') as close:
            self.assertEqual(s._root_file_digest('/safe/file'),('hash',('identity',)))
        digest.assert_called_once_with(91,0,256*1024*1024);close.assert_called_once_with(91)


if __name__=='__main__':unittest.main(verbosity=2)
