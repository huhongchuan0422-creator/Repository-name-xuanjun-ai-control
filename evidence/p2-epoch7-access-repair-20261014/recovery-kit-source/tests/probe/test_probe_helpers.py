"""Pure/fake transport tests and temporary workspace file tests only."""
import copy
import errno
import json
import os
import pathlib
import socket
import stat
import struct
import tempfile
import types
import unittest
from unittest import mock
import probe_helpers as h
import probe_driver as d
from test_probe_driver import fixture


class BytesSocket(object):
    family=socket.AF_UNIX;type=socket.SOCK_STREAM
    def __init__(self,chunks,peer=(1,0,0)):self.chunks=list(chunks);self.peer=peer;self.sent=[];self.connected=[];self.closed=False
    def settimeout(self,unused):pass
    def recv(self,unused):return self.chunks.pop(0) if self.chunks else b''
    def sendall(self,raw):self.sent.append(raw)
    def connect(self,path):self.connected.append(path)
    def getsockopt(self,*unused):return struct.pack('3i',*self.peer)
    def close(self):self.closed=True


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.policy,self.raw,unused,unused2=fixture();self.ops=d.HostOps(self.policy,'1'*64)
        self.config=self.ops.helper_config('native',1);self.root=d.scope(self.policy)['root']
    def test_driver_config_matches_helper_exact_path(self):
        for case,role,kind in d.CASES:
            config=self.ops.helper_config(role,case)
            self.assertEqual(h.validate_config(config,self.root+'/helper-'+role+'-client.json'),self.root)
    def test_config_other_nonce_rejected(self):
        self.assertRaises(ValueError,h.validate_config,self.config,'/run/xj-p2-proof-'+'b'*32+'/helper-native-client.json')
    def test_config_ack_not_proof_but_required(self):
        self.config['operator_acknowledged']=False
        self.assertRaises(ValueError,h.validate_config,self.config,self.root+'/helper-native-client.json')
    def test_fragmented_single_frame(self):
        self.assertEqual(h.receive(BytesSocket([b'{"a":',b'1}\n']),10**15),{'a':1})
    def test_two_frames_rejected(self):self.assertRaises(ValueError,h.receive,BytesSocket([b'{}\n{}\n']),10**15)
    def test_frame_bound_rejected(self):self.assertRaises(ValueError,h.receive,BytesSocket([b'x'*4097]),10**15)
    def test_eof_rejected(self):self.assertRaises(ValueError,h.receive,BytesSocket([b'']),10**15)
    def test_proc_reader_scope_excludes_environ_memory_cmdline(self):
        with mock.patch.object(h.os,'open',side_effect=AssertionError('NO_PROC_OPEN')):
            for path in ('/proc/1/environ','/proc/1/mem','/proc/1/cmdline','/etc/passwd'):
                self.assertRaises(ValueError,h.read_proc,path,100)
    def client(self,peer=(1,0,0),case=1):
        config=self.ops.helper_config('native' if case==1 else 'broker',case)
        request={'schema':1,'nonce':config['nonce'],'case':case,'challenge':'PUBLIC_INERT_PROBE'}
        sock=BytesSocket([h.canonical(dict(request,reply='PUBLIC_INERT_REPLY'))+b'\n',b''],peer)
        with mock.patch.object(h.socket,'socket',return_value=sock),mock.patch.object(h,'endpoint',return_value={'ino':1}),\
             mock.patch.object(h,'process',return_value={'pid':1}),mock.patch.object(h.os.path,'lexists',return_value=False),\
             mock.patch.object(h,'readpaths',return_value=[]),mock.patch.object(h,'sdk_checks',return_value=[]),\
             mock.patch.object(h,'emit'):
            result=h.client(config,self.root)
        return sock,result
    def test_peer_verified_before_any_nonce_bytes(self):
        sock,result=self.client(peer=(900,0,0))
        self.assertEqual(sock.sent,[]);self.assertEqual(result['status'],'FAIL_OBSERVED')
    def test_exactly_one_connection_no_sdk_import_and_no_admission_claim(self):
        sock,result=self.client()
        self.assertEqual(len(sock.connected),1);self.assertEqual(len(sock.sent),1)
        self.assertTrue(sock.closed);self.assertEqual(result['production_verifier_admission'],'NOT_VERIFIED')
    def test_ptrace_target_cannot_be_manager(self):
        self.assertRaises(ValueError,h.peer_executable,self.config,self.root,(1,0,0),1)
    def test_actual_inherited_server_accepts_at_most_eight_fake_connections(self):
        config=self.ops.helper_config('ledger',1);connections=[]
        for case in range(1,9):
            frame={'schema':1,'nonce':config['nonce'],'case':case,'challenge':'PUBLIC_INERT_PROBE'}
            connections.append(BytesSocket([h.canonical(frame)+b'\n']))
        listener=BytesSocket([]);listener.getsockname=lambda:self.root+'/ledger.sock'
        listener.getsockopt=lambda level,option: {socket.SO_DOMAIN:socket.AF_UNIX,
            socket.SO_TYPE:socket.SOCK_STREAM,socket.SO_ACCEPTCONN:1}[option]
        pending=list(connections);listener.accept=lambda:(pending.pop(0),None)
        with mock.patch.object(h.socket,'socket',return_value=listener),mock.patch.dict(h.os.environ,{'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'1'}),\
             mock.patch.object(h,'endpoint',return_value={}),mock.patch.object(h,'process',return_value={}),\
             mock.patch.object(h,'connection_budget',return_value=0),mock.patch.object(h,'syscall_denials',return_value={'fixture':True}),mock.patch.object(h,'peer_executable',return_value={'fixture':True}),\
             mock.patch.object(h,'emit'):
            h.server(config,self.root)
        self.assertEqual(len(pending),0);self.assertTrue(listener.closed)
        self.assertEqual(sum(len(sock.sent) for sock in connections),8)
    def test_server_refuses_noninherited_listener_without_socket_construction(self):
        config=self.ops.helper_config('ledger',1)
        with mock.patch.dict(h.os.environ,{'LISTEN_FDS':'0'}),mock.patch.object(h.socket,'socket',side_effect=AssertionError('NO_SOCKET')):
            self.assertRaises(ValueError,h.server,config,self.root)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='epoch7-probe-fixture-')
        self.path=pathlib.Path(self.temp.name)/'file'
    def tearDown(self):self.temp.cleanup()
    def read(self,bound):return h.read_regular(str(self.path),bound,False,os.geteuid())
    def test_exact_sdk_8mib_accepted(self):
        self.path.write_bytes(b'x'*(8*1024*1024));raw,unused=self.read(h.SDK_MAX)
        self.assertEqual(len(raw),h.SDK_MAX)
    def test_sdk_8mib_plus_one_rejected(self):
        self.path.write_bytes(b'x'*(h.SDK_MAX+1));self.assertRaises(ValueError,self.read,h.SDK_MAX)
    def test_hardlink_rejected(self):
        self.path.write_bytes(b'x');os.link(str(self.path),str(self.path)+'.link');self.assertRaises(ValueError,self.read,100)
    def test_symlink_rejected(self):
        target=self.path.with_name('target');target.write_bytes(b'x');self.path.symlink_to(target)
        self.assertRaises((OSError,ValueError),self.read,100)
    def test_fifo_is_not_opened_blocking(self):
        os.mkfifo(str(self.path));self.assertRaises(ValueError,self.read,100)
    def test_group_writable_file_rejected(self):
        self.path.write_bytes(b'x');self.path.chmod(0o660);self.assertRaises(ValueError,self.read,100)
    def test_changed_inode_after_read_rejected(self):
        self.path.write_bytes(b'x');actual=h.os.lstat
        def changed(path):
            info=actual(path)
            values=list(info);values[1]+=1
            return os.stat_result(values)
        with mock.patch.object(h.os,'lstat',side_effect=[actual(str(self.path)),changed(str(self.path))]):
            self.assertRaises(ValueError,self.read,100)
    def test_syscall_denial_probe_only_targets_fake_owned_child(self):
        libc=types.SimpleNamespace()
        calls=[]
        def denied(*args):h.ctypes.set_errno(errno.EPERM);calls.append(args[0]);return -1
        libc.ptrace=denied;libc.process_vm_readv=denied;libc.process_vm_writev=denied
        selector=types.SimpleNamespace(register=lambda *args:None,select=lambda *args:[True],close=lambda:None)
        with mock.patch.object(h.ctypes,'CDLL',return_value=libc),mock.patch.object(h.os,'pipe',side_effect=[(10,11),(12,13)]),\
             mock.patch.object(h.os,'fork',return_value=34567),mock.patch.object(h.os,'close'),\
             mock.patch.object(h.os,'write',return_value=1),mock.patch.object(h.os,'read',return_value=b'NONSECRET_PROBE_MEMORY\0'),\
             mock.patch.object(h.os,'kill') as killed,mock.patch.object(h.os,'waitpid',return_value=(34567,0)),\
             mock.patch.object(h.os,'waitid',return_value=None),\
             mock.patch.object(h,'isolated_syscall',side_effect=lambda name,libc,pid,*args:{'syscall':name,'status':'PASS_OBSERVED','target':pid}),\
             mock.patch.object(h.selectors,'DefaultSelector',return_value=selector):
            result=h.syscall_denials()
        self.assertTrue(result['child_memory_unchanged']);self.assertEqual(len(result['results']),3)
        self.assertTrue(all(x['status']=='PASS_OBSERVED' for x in result['results']))
        self.assertTrue(all(x['target']==34567 for x in result['results']))
        killed.assert_called_once_with(34567,h.signal.SIGKILL)




class GlobalBudgetTests(unittest.TestCase):
    def setUp(self):
        policy,unused,unused2,unused3=fixture();self.config=d.HostOps(policy,'1'*64).helper_config('ledger',1)
        self.info=types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o600,st_uid=0,st_gid=0,
            st_nlink=1,st_size=100,st_mtime_ns=1,st_ctime_ns=1)
    def run_budget(self,count,claim):
        value={'schema':1,'nonce':self.config['nonce'],'accepted':count};written=[]
        def write(fd,raw):written.append(raw[:3]);return min(3,len(raw))
        with mock.patch.object(h.os,'fstat',return_value=self.info),mock.patch.object(h.fcntl,'flock'),\
             mock.patch.object(h.os,'lseek'),mock.patch.object(h.os,'read',return_value=h.canonical(value)+b'\n'),\
             mock.patch.object(h.os,'write',side_effect=write),mock.patch.object(h.os,'ftruncate'),mock.patch.object(h.os,'fsync'):
            result=h.connection_budget(self.config,claim)
        return result,b''.join(written)
    def test_persistent_budget_advances_with_full_write(self):
        count,raw=self.run_budget(7,True);self.assertEqual(count,8)
        self.assertEqual(h.parse(raw)['accepted'],8)
    def test_ninth_connection_rejected_across_invocations(self):
        self.assertRaises(ValueError,self.run_budget,8,True)
    def test_budget_read_does_not_reserve_before_accept(self):
        count,raw=self.run_budget(6,False);self.assertEqual(count,6);self.assertEqual(raw,b'')
    def test_budget_cannot_be_dispatcher_owned_mutable_path(self):
        self.info.st_uid=1003
        self.assertRaises(ValueError,self.run_budget,0,False)


class IsolatedSyscallTests(unittest.TestCase):
    def attempt(self,status,raw=b'{"return":-1,"errno":1}',cleanup_errors=None):
        libc=types.SimpleNamespace(ptrace=lambda *unused:None)
        with mock.patch.object(h.os,'pipe',return_value=(10,11)),mock.patch.object(h.os,'fork',return_value=34568),\
             mock.patch.object(h.os,'close'),mock.patch.object(h.os,'read',return_value=raw),\
             mock.patch.object(h.os,'waitpid',return_value=(34568,status)),mock.patch.object(h.os,'kill') as killed,\
             mock.patch.object(h,'forbidden_call',side_effect=AssertionError('OBSERVER_MUST_NOT_CALL')),\
             mock.patch.object(h,'cleanup_fork_child',return_value=[] if cleanup_errors is None else cleanup_errors),\
             mock.patch.object(h,'emit'):
            result=h.isolated_syscall('ptrace',libc,34567,None,None,10**15)
        killed.assert_called_once_with(34567,h.signal.SIGCONT)
        return result
    def test_default_sigsys_is_observed_without_killing_server(self):
        result=self.attempt(h.signal.SIGSYS)
        self.assertEqual(result['status'],'PASS_OBSERVED');self.assertEqual(result['signal'],h.signal.SIGSYS)
    def test_explicit_eperm_is_observed(self):
        self.assertEqual(self.attempt(0)['status'],'PASS_OBSERVED')
    def test_successful_forbidden_syscall_fails(self):
        self.assertEqual(self.attempt(0,b'{"return":0,"errno":0}')['status'],'FAIL_OBSERVED')
    def test_unrelated_fatal_signal_is_not_denial_proof(self):
        self.assertEqual(self.attempt(h.signal.SIGKILL)['status'],'NOT_VERIFIED')
    def test_cleanup_unknown_cannot_return_pass(self):
        for status in (0,h.signal.SIGSYS):
            result=self.attempt(status,cleanup_errors=['FORK_REAP_UNCONFIRMED'])
            self.assertEqual(result['status'],'NOT_VERIFIED')
            self.assertEqual(result['cleanup_state'],'UNKNOWN')
            self.assertEqual(result['cleanup_errors'],['FORK_REAP_UNCONFIRMED'])
    def test_missing_libc_symbol_is_not_success(self):
        self.assertEqual(h.isolated_syscall('ptrace',object(),34567,None,None,10**15)['status'],'NOT_VERIFIED')


class InheritedSocketCompatibilityTests(unittest.TestCase):
    def test_actual_unix_descriptor_uses_explicit_family_on_both_pythons(self):
        left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        real_socket=socket.socket;opened=[]
        def construct(*args,**kwargs):
            self.assertEqual(args,(socket.AF_UNIX,socket.SOCK_STREAM))
            self.assertEqual(kwargs,{'fileno':3})
            result=real_socket(*args,fileno=os.dup(left.fileno()));opened.append(result)
            self.assertEqual(result.family,socket.AF_UNIX)
            self.assertEqual(result.getsockopt(socket.SOL_SOCKET,socket.SO_DOMAIN),socket.AF_UNIX)
            self.assertEqual(result.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE),socket.SOCK_STREAM)
            return result
        try:
            with mock.patch.object(h.socket,'socket',side_effect=construct):
                self.assertRaisesRegex(ValueError,'EXACT_INHERITED_LISTENER',h.inherited_listener,'/fixed')
            self.assertEqual(len(opened),1);self.assertEqual(opened[0].fileno(),-1)
        finally:left.close();right.close()
    def test_real_regular_file_fd_is_not_a_listener(self):
        real_socket=socket.socket
        with tempfile.TemporaryFile() as file:
            duplicate=os.dup(file.fileno())
            def construct(*args,**kwargs):
                self.assertEqual(args,(socket.AF_UNIX,socket.SOCK_STREAM))
                self.assertEqual(kwargs,{'fileno':3})
                return real_socket(*args,fileno=duplicate)
            try:
                with mock.patch.object(h.socket,'socket',side_effect=construct):
                    with self.assertRaises(OSError) as caught:h.inherited_listener('/fixed')
                self.assertEqual(caught.exception.errno,errno.ENOTSOCK)
            finally:
                try:os.close(duplicate)
                except OSError as error:
                    if error.errno!=errno.EBADF:raise
    def listener(self,domain=socket.AF_UNIX,kind=socket.SOCK_STREAM,listening=1,name='/fixed/ledger.sock'):
        result=mock.Mock();result.getsockname.return_value=name
        result.getsockopt.side_effect=lambda level,option:{socket.SO_DOMAIN:domain,
            socket.SO_TYPE:kind,socket.SO_ACCEPTCONN:listening}[option]
        return result
    def test_actual_kernel_domain_cannot_be_supplied_by_constructor_flags(self):
        listener=self.listener(domain=socket.AF_INET)
        with mock.patch.object(h.socket,'socket',return_value=listener):
            self.assertRaisesRegex(ValueError,'EXACT_INHERITED_LISTENER',h.inherited_listener,'/fixed')
        listener.close.assert_called_once_with()
    def test_datagram_kernel_type_rejected(self):
        listener=self.listener(kind=socket.SOCK_DGRAM)
        with mock.patch.object(h.socket,'socket',return_value=listener):
            self.assertRaisesRegex(ValueError,'EXACT_INHERITED_LISTENER',h.inherited_listener,'/fixed')
        listener.close.assert_called_once_with()
    def test_nonlistener_rejected(self):
        listener=self.listener(listening=0)
        with mock.patch.object(h.socket,'socket',return_value=listener):
            self.assertRaisesRegex(ValueError,'EXACT_INHERITED_LISTENER',h.inherited_listener,'/fixed')
    def test_other_nonce_name_rejected(self):
        listener=self.listener(name='/other/ledger.sock')
        with mock.patch.object(h.socket,'socket',return_value=listener):
            self.assertRaisesRegex(ValueError,'EXACT_INHERITED_LISTENER',h.inherited_listener,'/fixed')
    def test_socket_validation_primary_survives_close_failure(self):
        listener=self.listener(listening=0);listener.close.side_effect=KeyboardInterrupt()
        with mock.patch.object(h.socket,'socket',return_value=listener):
            self.assertRaisesRegex(ValueError,'EXACT_INHERITED_LISTENER',h.inherited_listener,'/fixed')
    def test_real_listener_and_unnamed_client_runtime_current_flow(self):
        # Mandatory Hosted regression; this local executor may disallow socket()
        # despite allowing socketpair(). That environmental skip is explicit.
        try:listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        except PermissionError:
            if os.environ.get('GITHUB_ACTIONS')=='true':raise
            self.skipTest('LOCAL_AF_UNIX_CREATION_DENIED_HOSTED_MUST_RUN')
        real_socket=socket.socket
        try:
            with tempfile.TemporaryDirectory(prefix='p2-unix-') as root:
                listener.bind(root+'/ledger.sock');listener.listen(1);listener.settimeout(1)
                for mode in ('fixed_helper','runtime107_implicit_listener'):
                    client=None;wrapped=None;connection=None
                    try:
                        if mode=='fixed_helper':
                            def construct(*args,**kwargs):
                                self.assertEqual(args,(socket.AF_UNIX,socket.SOCK_STREAM))
                                self.assertEqual(kwargs,{'fileno':3})
                                return real_socket(*args,fileno=os.dup(listener.fileno()))
                            with mock.patch.object(h.socket,'socket',side_effect=construct):wrapped=h.inherited_listener(root)
                        else:
                            # Exact runtime107 pattern: implicit listening FD,
                            # accepted address discarded, no family assertion.
                            wrapped=real_socket(fileno=os.dup(listener.fileno()))
                        wrapped.settimeout(1)
                        client=real_socket(socket.AF_UNIX,socket.SOCK_STREAM);client.settimeout(1)
                        client.connect(root+'/ledger.sock');connection,unused=wrapped.accept()
                        connection.settimeout(1)
                        self.assertEqual(struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)),
                                         (os.getpid(),os.getuid(),os.getgid()))
                        client.sendall(b'PUBLIC\n');self.assertEqual(connection.recv(16),b'PUBLIC\n')
                        connection.sendall(b'REPLY\n');self.assertEqual(client.recv(16),b'REPLY\n')
                    finally:
                        for item in (connection,client,wrapped):
                            if item is not None:item.close()
        finally:listener.close()


if __name__=='__main__':unittest.main()
