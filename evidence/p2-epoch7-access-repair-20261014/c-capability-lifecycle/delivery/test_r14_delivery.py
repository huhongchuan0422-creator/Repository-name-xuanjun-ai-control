"""R1-R4 integration with real HTTP, pinned real archives and real prepare.

Only host identity, fixed paths and unavailable private historical observations
are test fixtures. Real download/hash/extractor/kit loader/directory staging,
preparer orchestration, pure compiler and exclusive private publication run.
No production host, command, service, claim or approval is exercised.
"""
import contextlib
import copy
import hashlib
import http.server
import importlib
import importlib.util
import json
import os
import pathlib
import socketserver
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parent
CANDIDATE=HERE.parent
sys.path.insert(0,str(CANDIDATE/'preparation'))
import test_prepare_successor as history

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed=history.complete_historical_fixture()
        cls.private=history.private_wire(cls.seed)
        cls.measured=history.measurement_fixture(cls.private)
        cls.archive=(CANDIDATE/'published-v2/epoch7-kit-claim-lifecycle-0bd83e6f.tar.gz').read_bytes()
        cls.native_raws=history.fixture.native_pins.__globals__['native_fixture_raws'](cls.seed)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='r14-case-',dir='/');self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)/'candidate';self.root.mkdir(mode=0o700)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        raw=(HERE/'epoch7_prepare_successor_delivery.py').read_bytes()
        self.m=types.ModuleType('r14_in_memory_delivery');self.m.__file__='<verified-preparation-delivery>'
        exec(compile(raw,self.m.__file__,'exec'),self.m.__dict__)
        m=self.m
        m.CAND=str(self.root);m.PREP_ROOT=m.CAND+'/'+m.PREP_LEAF
        m.COMPILER_PARENT=m.CAND+'/'+m.COMPILER_PARENT_LEAF
        m.COMPILER_ROOT=m.COMPILER_PARENT+'/'+m.COMPILER_LEAF
        m.KIT_ROOT=m.CAND+'/epoch7-recovery-candidate-r7-resourcebind'
        # Verify the immutable actual v2 archive and every one of its 257 files.
        self.extractor,self.entry,self.files=m.compiler_inputs(self.archive)
        self.assertEqual(len(self.files),257)
        baseline=CANDIDATE/'baseline'
        for path in baseline.rglob('*'):
            if not path.is_file():continue
            dest=pathlib.Path(m.KIT_ROOT)/path.relative_to(baseline)
            dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with open(str(dest),'xb') as stream:stream.write(path.read_bytes())
            dest.chmod(0o444)
        # Existing legacy lifecycle siblings are immutable markers, not adopted.
        self.markers=[]
        for leaf in ('epoch7-recovery-candidate-r7-claim-lifecycle','epoch7-preparation-candidate-r7-claim-lifecycle'):
            dest=self.root/leaf;dest.mkdir(mode=0o700)
            marker=dest/'frozen';marker.write_bytes(b'original frozen bytes');marker.chmod(0o444)
            self.markers.append((marker,self.identity(marker)))
        self.originals={role:history.p.packed({'fixture':role}) for role in ('seed','plan','packet')}
        self.original_files=tuple((role,'fixture-'+role+'.private.json',len(raw),sha(raw))
                                 for role,raw in sorted(self.originals.items()))
        for role,leaf,size,pin in self.original_files:
            path=self.root/leaf;path.write_bytes(self.originals[role]);path.chmod(0o600)
        # Only CAND is relocated in the complete public preparer source.
        source=(CANDIDATE/'preparation/epoch7_prepare_successor.py').read_text()
        source=source.replace("CAND = BASE + '/complete-install-candidate-38503014520'",'CAND = '+repr(m.CAND))
        self.source=source.encode('ascii');m.SOURCES={'epoch7_prepare_successor.py':(sha(self.source),len(self.source))}
        m.PINS_BOUND=True;m.PUBLICATION_COMMIT='1'*40
        self.responses={m.PUBLICATION_COMMIT+'/'+m.PUBLIC_PREFIX+'epoch7_prepare_successor.py':self.source,
                        m.ARCHIVE_COMMIT+'/'+m.ARCHIVE_PATH:self.archive}
        self.requests=[]
        case=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                case.requests.append(self.path)
                body=case.responses.get(self.path[1:])
                if body is None:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                self.wfile.write(body)
            def log_message(self,*args):pass
        class Server(socketserver.TCPServer):allow_reuse_address=True
        self.server=Server(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.daemon=True;self.thread.start()
        self.addCleanup(self.close_server)
        m.RAW_PREFIX='http://127.0.0.1:%d/'%self.server.server_address[1]
        self.status=[];self.prep=None;self.prepare_calls=0;self.measure_calls=0
        self.stack.enter_context(mock.patch.object(m.socket,'gethostname',return_value=m.HOST))
        self.stack.enter_context(mock.patch.object(m,'deliver_status',side_effect=lambda row:self.status.append(row)))
        original=m.preparer
        def preparer(cache):
            p=original(cache);self.prep=p;p.FILES=self.original_files
            real_prepare=p.prepare
            def counted(*args):self.prepare_calls+=1;return real_prepare(*args)
            p.prepare=counted
            def original_private(loader,kit,raws):
                self.assertEqual(raws,self.originals)
                return copy.deepcopy(self.private)
            p.validate_original=original_private
            def measured(*args):
                self.measure_calls+=1
                return copy.deepcopy(self.measured)
            p.measure_predecessor=measured
            imports=p.authenticated_imports
            @contextlib.contextmanager
            def private_fixture_pins(kit):
                # Discard fixture-builder imports while the actual verified kit
                # owns its namespace, then restore those fixture definitions.
                previous={name:sys.modules.pop(name) for name in kit.manifest['modules'] if name in sys.modules}
                try:
                    with imports(kit):
                        snapshot=importlib.import_module('epoch7_snapshot')
                        current,prior,old,attempt=self.native_raws
                        with mock.patch.multiple(snapshot,NATIVE_CURRENT_SHA=sha(current),RETAINED_NATIVE_SHA=sha(prior),
                                NATIVE_ORIGINAL_SHA=sha(old),NATIVE_ATTEMPT_SHA=sha(attempt)):
                            yield
                finally:sys.modules.update(previous)
            p.authenticated_imports=private_fixture_pins
            if self.preparer_hook:self.preparer_hook(p)
            return p
        self.preparer_hook=None
        self.stack.enter_context(mock.patch.object(m,'preparer',side_effect=preparer))

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())
    def identity(self,path):
        info=path.lstat();return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,
                                info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    def invoke(self):
        # Fixture builders import UUID; the real CLI starts in a cold interpreter.
        # Exercise the actual cold parser rather than disabling its guard.
        previous=sys.modules.pop('uuid',None)
        try:result=self.m.entrypoint(['--operation','prepare','--admission-expires-at-utc','2099-01-01T00:00:00Z'])
        finally:
            sys.modules.pop('uuid',None)
            if previous is not None:sys.modules['uuid']=previous
        for path,before in self.markers:
            self.assertEqual(path.read_bytes(),b'original frozen bytes');self.assertEqual(self.identity(path),before)
        return result,self.status[-1]
    def assert_hold(self,result):
        code,row=result;self.assertEqual(code,2,row);self.assertEqual(row['state'],'HOLD')
        self.assertEqual(row['install_admission'],'NOT_GRANTED');self.assertEqual(row['production_resume'],'NOT_EXECUTED')
        return row

    def test_real_download_unpack_bootstrap_compile_prepare_and_recheck(self):
        code,row=self.invoke();self.assertEqual(code,0,row)
        self.assertEqual(self.prepare_calls,1);self.assertEqual(self.measure_calls,3)
        self.assertEqual(len(self.requests),2);self.assertEqual(row['state'],'PREPARED_NOT_ADMITTED')
        self.assertEqual(sorted(pathlib.Path(self.m.PREP_ROOT).iterdir()),
                         [pathlib.Path(self.m.PREP_ROOT)/'epoch7_prepare_successor.py'])
        self.assertEqual(len(row['preparation']['outputs']),3)
        for output in row['preparation']['outputs']:
            path=pathlib.Path(output['path']);self.assertEqual(sha(path.read_bytes()),output['sha256'])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        self.assertEqual(row['install_admission'],'NOT_GRANTED')

    def test_wrong_source_version_stops_before_any_new_directory(self):
        self.responses[self.m.PUBLICATION_COMMIT+'/'+self.m.PUBLIC_PREFIX+'epoch7_prepare_successor.py']=self.source+b'\n'
        row=self.assert_hold(self.invoke());self.assertEqual(row['phase'],'DOWNLOAD_ALL')
        self.assertFalse(pathlib.Path(self.m.COMPILER_PARENT).exists());self.assertEqual(self.prepare_calls,0)

    def test_wrong_archive_hash_stops_before_any_new_directory(self):
        self.responses[self.m.ARCHIVE_COMMIT+'/'+self.m.ARCHIVE_PATH]=self.archive[:-1]
        row=self.assert_hold(self.invoke());self.assertEqual(row['phase'],'DOWNLOAD_ALL')
        self.assertFalse(pathlib.Path(self.m.COMPILER_PARENT).exists());self.assertEqual(self.prepare_calls,0)

    def test_wrong_kit_source_identity_stops_before_any_new_directory(self):
        self.m.COMPILER_SOURCE='e'*40
        self.assert_hold(self.invoke());self.assertFalse(pathlib.Path(self.m.COMPILER_PARENT).exists())

    def test_retained_empty_version_parent_is_never_repaired(self):
        parent=pathlib.Path(self.m.COMPILER_PARENT);parent.mkdir(mode=0o700)
        self.assert_hold(self.invoke());self.assertEqual(list(parent.iterdir()),[]);self.assertEqual(self.prepare_calls,0)

    def test_version_parent_symlink_is_rejected(self):
        target=self.root/'target';target.mkdir(mode=0o700)
        pathlib.Path(self.m.COMPILER_PARENT).symlink_to(target,target_is_directory=True)
        self.assert_hold(self.invoke());self.assertEqual(list(target.iterdir()),[])

    def test_partial_kit_is_retained_without_repair(self):
        target=pathlib.Path(self.m.COMPILER_ROOT);target.mkdir(mode=0o700,parents=True)
        marker=target/'partial';marker.write_bytes(b'retain')
        self.assert_hold(self.invoke());self.assertEqual(marker.read_bytes(),b'retain')
        self.assertEqual(list(target.iterdir()),[marker]);self.assertEqual(self.prepare_calls,0)

    def test_mid_extraction_disk_failure_retains_partial_kit(self):
        original=self.m.compiler_inputs
        def inputs(raw):
            extractor,entry,files=original(raw)
            proxy=types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
            count=[0]
            def write(fd,data):
                count[0]+=1
                if count[0]==3:raise OSError('synthetic extraction disk full')
                return os.write(fd,data)
            proxy.write=write;extractor.os=proxy
            return extractor,entry,files
        with mock.patch.object(self.m,'compiler_inputs',side_effect=inputs):row=self.assert_hold(self.invoke())
        target=pathlib.Path(self.m.COMPILER_ROOT)
        self.assertTrue(target.is_dir());self.assertTrue(any(p.is_file() for p in target.rglob('*')))
        self.assertEqual(row['compiler_staging']['state'],'EXTRACTION_ATTEMPTED_NOT_VERIFIED')
        self.assertEqual(self.prepare_calls,0)

    def test_compiler_leaf_symlink_is_rejected(self):
        parent=pathlib.Path(self.m.COMPILER_PARENT);parent.mkdir(mode=0o700)
        target=self.root/'other-kit';target.mkdir(mode=0o700)
        pathlib.Path(self.m.COMPILER_ROOT).symlink_to(target,target_is_directory=True)
        self.assert_hold(self.invoke());self.assertEqual(list(target.iterdir()),[])

    def test_unsafe_version_parent_mode_is_rejected(self):
        parent=pathlib.Path(self.m.COMPILER_PARENT);parent.mkdir(mode=0o777);parent.chmod(0o777)
        self.assert_hold(self.invoke());self.assertEqual(list(parent.iterdir()),[])

    def test_preparer_extra_inventory_stops_before_prepare(self):
        parent=pathlib.Path(self.m.PREP_ROOT);parent.mkdir(mode=0o700)
        marker=parent/'delivery.py';marker.write_bytes(b'frozen wrong startup')
        self.assert_hold(self.invoke());self.assertEqual(self.prepare_calls,0)
        self.assertEqual(marker.read_bytes(),b'frozen wrong startup')

    def test_preparer_symlink_is_rejected(self):
        target=self.root/'empty-prep-target';target.mkdir(mode=0o700)
        pathlib.Path(self.m.PREP_ROOT).symlink_to(target,target_is_directory=True)
        self.assert_hold(self.invoke());self.assertEqual(list(target.iterdir()),[])

    def test_preparer_source_symlink_is_rejected(self):
        parent=pathlib.Path(self.m.PREP_ROOT);parent.mkdir(mode=0o700)
        target=self.root/'immutable-preparer';target.write_bytes(self.source);target.chmod(0o600)
        (parent/'epoch7_prepare_successor.py').symlink_to(target)
        self.assert_hold(self.invoke());self.assertEqual(target.read_bytes(),self.source);self.assertEqual(self.prepare_calls,0)

    def test_repeated_delivery_cannot_overwrite_existing_private_outputs(self):
        code,row=self.invoke();self.assertEqual(code,0,row)
        before={item['path']:(pathlib.Path(item['path']).read_bytes(),self.identity(pathlib.Path(item['path'])))
                for item in row['preparation']['outputs']}
        self.assert_hold(self.invoke())
        for path,(raw,identity) in before.items():
            self.assertEqual(pathlib.Path(path).read_bytes(),raw);self.assertEqual(self.identity(pathlib.Path(path)),identity)

    def test_second_private_create_permission_failure_retains_first_output(self):
        def hook(p):
            proxy=types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
            count=[0]
            def opening(path,flags,*args,**kwargs):
                if flags&os.O_CREAT:
                    self.assertTrue(flags&os.O_EXCL);self.assertTrue(flags&os.O_NOFOLLOW)
                    count[0]+=1
                    if count[0]==2:raise PermissionError('synthetic private output denial')
                return os.open(path,flags,*args,**kwargs)
            proxy.open=opening;p.os=proxy
        self.preparer_hook=hook
        row=self.assert_hold(self.invoke());self.assertEqual(self.prepare_calls,1)
        self.assertEqual(len(row['completed_outputs']),1);self.assertEqual(len(row['created_output_paths']),1)
        output=row['completed_outputs'][0];self.assertEqual(sha(pathlib.Path(output['path']).read_bytes()),output['sha256'])
        self.assertNotIn('synthetic private output denial',json.dumps(row))

    def test_partial_source_write_is_retained_and_not_repaired(self):
        proxy=types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
        def fail_write(fd,raw):raise OSError('synthetic disk full')
        proxy.write=fail_write
        with mock.patch.object(self.m,'os',proxy):row=self.assert_hold(self.invoke())
        file=pathlib.Path(self.m.PREP_ROOT)/'epoch7_prepare_successor.py'
        self.assertTrue(file.exists());self.assertEqual(file.read_bytes(),b'')
        self.assert_hold(self.invoke());self.assertEqual(file.read_bytes(),b'');self.assertEqual(self.prepare_calls,0)

class LauncherTests(unittest.TestCase):
    def test_render_pins_entire_delivery_and_uses_no_bootstrap_file(self):
        launcher=load(HERE/'render_memory_launcher.py','memory_launcher')
        raw=b'def entrypoint(args):\n    return 0\n'
        command=launcher.render('a'*40,'2099-01-01T00:00:00Z',raw)
        body=command.decode('ascii').split('\n',1)[1].rsplit('P2_VERIFIED_MEMORY_DELIVERY\n',1)[0]
        response=mock.MagicMock();response.__enter__.return_value=response
        response.status=200;response.headers={}
        url='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'+'a'*40+'/evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/epoch7_prepare_successor_delivery.py'
        response.geturl.return_value=url;response.read.return_value=raw
        import urllib.request
        with mock.patch.object(urllib.request,'build_opener') as opener,mock.patch.object(os,'open',side_effect=AssertionError('bootstrap file')):
            opener.return_value.open.return_value=response
            with self.assertRaises(SystemExit) as exit:exec(compile(body,'<rendered-memory-command>','exec'),{})
            self.assertEqual(exit.exception.code,0)
            response.read.assert_called_once_with(len(raw)+1)
        response.read.return_value=raw+b'wrong'
        with mock.patch.object(urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=response
            with self.assertRaisesRegex(ValueError,'DELIVERY_PIN'):exec(compile(body,'<rendered-memory-command>','exec'),{})

if __name__=='__main__':unittest.main()
