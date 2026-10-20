import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
APP=REPO/'evidence/p2-epoch7-access-repair-20261014/runtime/stage1'
sys.path.insert(0,str(REPO));sys.path.insert(0,str(APP))
from production.p2_install import b3_ledger as m
from activation_control import ActivationStore
import ledger_service


def snap(root):
    return {str(p):(p.read_bytes(),p.stat().st_ino,p.stat().st_mtime_ns,p.stat().st_mode)
            for p in root.rglob('*') if p.is_file()}


class LedgerPreparation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='p2-b3-test-',dir='/tmp')
        self.root=Path(self.temp.name)/'b3-initialize';self.root.mkdir(mode=0o700)
        activation=self.root/'activation';activation.mkdir(mode=0o700)
        (self.root/'.initialize.lock').write_bytes(b'');(self.root/'.initialize.lock').chmod(0o600)
        binary=Path(os.path.realpath(sys.executable));raw=binary.read_bytes()
        self.binary={'path':str(binary),'bytes':len(raw),'sha256':m.sha(raw)}
        cfg={'installation_id':'p2-test-isolated','initial_state':'PREPARED','initial_epoch':1,
             'release_manifest_sha256':'a'*64,'instance':'0891a51b-feea-520e-850a-c8fc7c840d94',
             'ledger_uuid':'093955da-4b7d-5c8d-b85e-3adaa304c675','generation':1,
             'db_path':str(self.root/'data/ledger.sqlite3'),'ledger_socket':str(self.root/'run/ledger.sock')}
        (self.root/'binding-config.json').write_bytes(m.encode(cfg));cfg_sha=m.sha(m.encode(cfg))
        store=ActivationStore(str(activation/'active.json'),str(activation/'epochs.jsonl'),
                              str(activation/'activation.lock'),owner_uid=os.geteuid())
        store.prepare(release_sha256='a'*64,config_sha256=cfg_sha,binary_sha256=self.binary['sha256'],
                      ledger_uuid=cfg['ledger_uuid'],generation=1,instance=cfg['instance'],
                      db_path=cfg['db_path'],ledger_socket=cfg['ledger_socket'],expected_epoch=0)
        receipt={'schema':1,'scope':'ISOLATED_TEST_ONLY','origin':'ISOLATED_NEW','status':'COMMITTED',
                 'installation_id':cfg['installation_id'],'config_sha256':cfg_sha,
                 'binary_sha256':self.binary['sha256'],'full_b3_complete':False,
                 'descriptor_file_sha256':m.sha((activation/'active.json').read_bytes()),
                 'journal_sha256':m.sha((activation/'epochs.jsonl').read_bytes())}
        (self.root/'commit-receipt.json').write_bytes(m.encode(receipt))
        self.req={'schema':1,'scope':'ISOLATED_TEST_ONLY','root':str(self.root),'application':str(APP),
                  'binary':self.binary,'sources':{n:m.sha((APP/n).read_bytes()) for n in m.NAMES},
                  'operation_id':'test-b3-ledger-prepare-a1',
                  'cp03_receipt_sha256':m.sha(m.encode(receipt))}
        self.original=snap(self.root)

    def tearDown(self):
        for p,identity in self.original.items():
            path=Path(p)
            self.assertEqual(identity,(path.read_bytes(),path.stat().st_ino,path.stat().st_mtime_ns,path.stat().st_mode))
        self.assertFalse((self.root/'data/ledger.sqlite3').exists())
        self.assertFalse((self.root/'run/ledger.sock').exists())
        self.temp.cleanup()

    def call(self,action='execute',req=None):
        req=req or self.req
        return m.dispatch(req,action,m.sha(m.encode(req)))

    def child(self,action='recover',crash=None):
        program='''import json,os,signal,sys
sys.path.insert(0,sys.argv[1])
from production.p2_install import b3_ledger as m
if sys.argv[3]!='none':
 def die(name):
  if name==sys.argv[3]:os.kill(os.getpid(),signal.SIGKILL)
 m._checkpoint=die
req=json.loads(sys.stdin.read())
print(json.dumps(m.dispatch(req,sys.argv[2],m.sha(m.encode(req)))))
'''
        return subprocess.run([sys.executable,'-B','-c',program,str(REPO),action,crash or 'none'],
                              input=m.encode(self.req),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)

    def test_real_consumer_without_build_listener_database(self):
        value=self.call()
        self.assertEqual(value['completed'][:4],['CP04','CP05','CP06','CP07'],value)
        self.assertIn(value['status'],('HOLD','PREPARATION_COMMITTED'))
        profile=json.loads((self.root/'prepared/profile.json').read_bytes())
        self.assertEqual(profile['roles']['callback_uid'],1004)
        self.assertEqual(profile['roles']['service_uid'],'UNKNOWN')
        self.assertNotEqual(profile['roles']['preparer_uid'],1004)

    def test_start_refuses_preparation_profile(self):
        with self.assertRaisesRegex(ValueError,'PREPARATION_PROFILE_CANNOT_START'):
            ledger_service.build({'profile':'ISOLATED_NEW_PREPARE_ONLY'})
        # The original socket activation guard is still effective.
        old=dict(os.environ)
        try:
            os.environ.pop('LISTEN_FDS',None);os.environ.pop('LISTEN_PID',None)
            with self.assertRaisesRegex(ValueError,'exactly one systemd socket'):
                ledger_service.listener()
        finally:
            os.environ.clear();os.environ.update(old)

    def test_full_sequence_or_accurate_independent_uid_hold(self):
        value=self.call()
        if os.environ.get('P2_REQUIRE_OS_DENIAL')=='1':
            self.assertEqual(value['status'],'PREPARATION_COMMITTED',value)
        if value['status']=='HOLD':
            self.assertEqual(value['stage'],'CP08',value)
            self.assertTrue(value['observations'],value)
            self.assertEqual(value['observations'][0]['denial']['status'],'UNAVAILABLE')
            self.assertFalse((self.root/'prepared/CP09-committed.json').exists())
            return
        self.assertEqual(value['completed'],list(m.STAGES))
        self.assertEqual(value['status'],'PREPARATION_COMMITTED')
        self.assertFalse(value['full_b3_complete'])

    def test_response_loss_after_terminal_returns_original_receipt(self):
        value=self.call()
        if value['status']!='PREPARATION_COMMITTED':
            self.skipTest('independent UID unavailable; terminal response loss not executed')
        before=snap(self.root/'prepared')
        result=self.child('recover','after_final')
        self.assertEqual(result.returncode,-signal.SIGKILL)
        recovered=self.child('recover')
        self.assertEqual(json.loads(recovered.stdout)['receipt'],value['receipt'])
        self.assertEqual(before,snap(self.root/'prepared'))

    def test_cross_process_duplicate_original_reference(self):
        first=self.call();result=self.child()
        self.assertEqual(result.returncode,0,result.stderr)
        second=json.loads(result.stdout)
        self.assertEqual(first,second)
        self.assertEqual(self.call('inspect'),first)

    def test_sigkill_after_configuration_publish_recovers_same_request(self):
        result=self.child('execute','after_ledger-config.json')
        self.assertEqual(result.returncode,-signal.SIGKILL,result.stderr)
        self.assertTrue((self.root/'prepared/CP04-committed.json').exists())
        self.assertFalse((self.root/'prepared/CP05-committed.json').exists())
        recovered=self.child()
        self.assertEqual(recovered.returncode,0,recovered.stderr)
        self.assertIn('CP05',json.loads(recovered.stdout)['completed'])

    def test_changed_contract_cannot_bypass_hold(self):
        self.call()
        req=copy.deepcopy(self.req);req['operation_id']='another-operation'
        value=self.call('recover',req)
        self.assertEqual(value['status'],'HOLD')
        self.assertIn('CONFLICT',value['error']['code'])

    def test_config_tampering_hold_not_tls_exemption(self):
        self.call();path=self.root/'prepared/ledger-config.json'
        path.chmod(0o600);value=json.loads(path.read_bytes());value['tls_required']=False
        path.write_bytes(m.encode(value));path.chmod(0o400)
        result=self.call('recover')
        self.assertEqual(result['status'],'HOLD')
        self.assertNotIn('CP09',result['completed'])

    def test_checkpoint_order_conflict(self):
        self.call();(self.root/'prepared/CP06-committed.json').unlink()
        result=self.call('recover')
        self.assertEqual(result['error']['code'],'CHECKPOINT_ORDER')

    def test_inspect_before_execution_no_output_directory(self):
        self.assertEqual(self.call('inspect')['status'],'NOT_EXECUTED')
        self.assertFalse((self.root/'prepared').exists())


if __name__=='__main__':
    # Toolcache binaries can be group-writable. Use identical executable bytes
    # in a private 0500 staging directory instead of weakening production checks.
    if not os.environ.get('P2_LEDGER_PRIVATE_PYTHON'):
        with tempfile.TemporaryDirectory(prefix='p2-ledger-python-') as d:
            binary=Path(d)/'python';shutil.copyfile(os.path.realpath(sys.executable),binary);binary.chmod(0o500)
            env=dict(os.environ,P2_LEDGER_PRIVATE_PYTHON='1',PYTHONHOME=sys.prefix,
                     LD_LIBRARY_PATH=str(Path(sys.prefix)/'lib'))
            result=subprocess.run([str(binary),'-B',__file__]+sys.argv[1:],env=env)
            sys.exit(result.returncode)
    unittest.main()
