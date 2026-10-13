from __future__ import print_function
import hashlib
import json
import os
import pathlib
import stat
import tempfile
import unittest
from unittest.mock import patch

SOURCE=pathlib.Path(os.environ['P2_SOURCE_ROOT'])
STAGE1=SOURCE/'stage1'
import sys
sys.path.insert(0,str(STAGE1))

from codex_worker import CodexWorker
from codex_app_server_worker import CodexAppServerWorker
from native_child_adapter import NativeContractError
from native_pipeline_runtime import load_reviewed_controller

class ReviewBlockerTests(unittest.TestCase):
    def test_legacy_codex_worker_denies_before_runner(self):
        calls=[]
        worker=CodexWorker('/bin/true','/tmp/work','/tmp/home','/tmp/codex','/usr/bin:/bin',
                           runner=lambda *a,**k:calls.append((a,k)))
        with self.assertRaisesRegex(RuntimeError,'delegated model dispatch prohibited'):
            worker.run('never dispatch',lease_check=lambda:True)
        self.assertEqual(calls,[])

    def test_legacy_app_server_denies_before_runner(self):
        calls=[]
        with tempfile.TemporaryDirectory() as root:
            work=os.path.join(root,'work');home=os.path.join(root,'home');codex=os.path.join(root,'codex')
            for path in (work,home,codex):os.mkdir(path)
            worker=CodexAppServerWorker('/bin/true',work,home,codex,'/usr/bin:/bin',
                                        runner=lambda *a,**k:calls.append((a,k)))
            with self.assertRaisesRegex(RuntimeError,'delegated model dispatch prohibited'):
                worker.run('never dispatch',lease_check=lambda:True)
        self.assertEqual(calls,[])

    def test_dispatcher_service_binds_exact_controller(self):
        controller=STAGE1/'native_gateway_controller.py'
        digest=hashlib.sha256(controller.read_bytes()).hexdigest()
        service=(SOURCE/'deploy/xuanjun-development-dispatcher.service').read_text()
        expected='/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/native_gateway_controller.py'
        for line in service.splitlines():
            if line.startswith(('ExecStartPre=','ExecStart=')):
                self.assertIn('--native-controller '+expected,line)
                self.assertIn('--native-controller-sha256 '+digest,line)
        transport=json.loads((STAGE1/'native_gateway_controller.py.json').read_text())
        self.assertEqual(transport,{'relay_socket':'/run/xuanjun-development/p2-gateway.sock',
                                    'server_user':'xuanjun_dev',
                                    'client_group':'xuanjun-dispatcher'})
        relay=json.loads((SOURCE/'deploy/p2-gateway-relay.json.template').read_text())
        self.assertEqual(relay['openclaw_bin'],'/home/xuanjun_dev/.openclaw/bin/openclaw')
        self.assertEqual(relay['openclaw_sha256'],
                         'b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2')

    def test_real_controller_loader_accepts_exact_and_rejects_missing_wrong_digest(self):
        controller=str(STAGE1/'native_gateway_controller.py')
        digest=hashlib.sha256(pathlib.Path(controller).read_bytes()).hexdigest()
        config={'gh_bin':'/usr/bin/true','service_home':'/tmp','path':'/usr/bin:/bin'}
        import os as real_os
        real_lstat=real_os.lstat;real_fstat=real_os.fstat
        def root_stat(value,directory=None):
            values=list(value)
            is_dir=stat.S_ISDIR(value.st_mode) if directory is None else directory
            values[0]=(stat.S_IFDIR|0o755) if is_dir else (stat.S_IFREG|0o644)
            values[4]=0;values[5]=0
            return os.stat_result(values)
        def fake_lstat(path):
            return root_stat(real_lstat(path))
        def fake_fstat(fd):
            return root_stat(real_fstat(fd),False)
        with patch('os.lstat',side_effect=fake_lstat),patch('os.fstat',side_effect=fake_fstat):
            runtime=load_reviewed_controller(controller,digest,config)
            self.assertEqual(runtime.binary_sha256,digest)
            with self.assertRaisesRegex(NativeContractError,'hash mismatch'):
                load_reviewed_controller(controller,'0'*64,config)
            with self.assertRaisesRegex(NativeContractError,'pinned canonical controller required'):
                load_reviewed_controller(None,None,config)

if __name__=='__main__':unittest.main(verbosity=2)
