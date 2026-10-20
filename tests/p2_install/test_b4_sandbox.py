"""Real original consumer/policy tests. Constructed B3 inputs are fixtures, not UK proof."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[2]
APP=REPO/'evidence/p2-epoch7-access-repair-20261014/runtime/stage1'
sys.path.insert(0,str(REPO));sys.path.insert(0,str(APP))
from production.p2_install import b3_ledger as b3
from production.p2_install import b4_sandbox as b4
from activation_control import ActivationStore


def fixture(base):
    base=Path(base);root=base/'b3-initialize';root.mkdir(mode=0o700)
    (root/'activation').mkdir(mode=0o700)
    for name in ('data','run'):(root/name).mkdir(mode=0o700)
    (root/'.initialize.lock').write_bytes(b'');(root/'.initialize.lock').chmod(0o600)
    binary=Path(os.path.realpath(sys.executable));raw=binary.read_bytes()
    spec={'path':str(binary),'bytes':len(raw),'sha256':b3.sha(raw)}
    cfg={'installation_id':'p2-b4-fixture','initial_state':'PREPARED','initial_epoch':1,
      'release_manifest_sha256':'a'*64,'instance':'0891a51b-feea-520e-850a-c8fc7c840d94',
      'ledger_uuid':'093955da-4b7d-5c8d-b85e-3adaa304c675','generation':1,
      'db_path':str(root/'data/ledger.sqlite3'),'ledger_socket':str(root/'run/ledger.sock')}
    config=b3.encode(cfg);(root/'binding-config.json').write_bytes(config)
    activation=root/'activation'
    store=ActivationStore(str(activation/'active.json'),str(activation/'epochs.jsonl'),str(activation/'activation.lock'),owner_uid=os.geteuid())
    store.prepare(release_sha256='a'*64,config_sha256=b3.sha(config),binary_sha256=spec['sha256'],
       ledger_uuid=cfg['ledger_uuid'],generation=1,instance=cfg['instance'],db_path=cfg['db_path'],ledger_socket=cfg['ledger_socket'],expected_epoch=0)
    receipt={'schema':1,'scope':'ISOLATED_TEST_ONLY','origin':'ISOLATED_NEW','status':'COMMITTED',
      'installation_id':cfg['installation_id'],'config_sha256':b3.sha(config),'binary_sha256':spec['sha256'],
      'full_b3_complete':False,'descriptor_file_sha256':b3.sha((activation/'active.json').read_bytes()),
      'journal_sha256':b3.sha((activation/'epochs.jsonl').read_bytes())}
    (root/'commit-receipt.json').write_bytes(b3.encode(receipt))
    req={'schema':1,'scope':'ISOLATED_TEST_ONLY','root':str(root),'application':str(APP),'binary':spec,
      'sources':{n:b3.sha((APP/n).read_bytes()) for n in b3.NAMES},'operation_id':'fixture-b3',
      'cp03_receipt_sha256':b3.sha(b3.encode(receipt))}
    # Only fixture construction substitutes the already-accepted B3 CP08 record.
    # No test claims to reaccept CP08/UK. The CP10 consumer/OS checks are real.
    with mock.patch('production.p2_install.cp08_evidence.load',return_value={'status':'PASS','origin':'CONSTRUCTED_B3_INPUT_FIXTURE'}):
        prepared=b3.dispatch(req,'execute',b3.sha(b3.encode(req)))
    if prepared['status']!='PREPARATION_COMMITTED':raise AssertionError(prepared)
    target=base/'b4-sandbox';target.mkdir(mode=0o700)
    for name in ('workspace',)+b4.ROLES:(target/name).mkdir(mode=0o700)
    req={'schema':1,'scope':'ISOLATED_TEST_ONLY','b3_root':str(root),'root':str(target),'application':str(APP),
      'b3_receipt_sha256':prepared['receipt']['sha256'],'binary':spec,
      'installation_id':'p2-b4-fixture','attempt_id':'cp10-a1',
      'sources':{n:b3.sha((APP/n).read_bytes()) for n in b3.NAMES+('p2_sandbox_profile.py',)},
      'runtime_sha256':b4.RUNTIME_SHA}
    (base/'request.json').write_bytes(b3.encode(req));return req


def call(req,role,action='execute'):
    path=Path(req['root']).parent/'request.json'
    cmd=[sys.executable,'-B','-S','-m','production.p2_install.b4_sandbox',action,'--request',str(path),'--role',role]
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=str(REPO),timeout=20)
    if not result.stdout.strip():raise AssertionError(result.stderr.decode())
    return json.loads(result.stdout)


def prior(req):
    root=Path(req['b3_root'])
    return {str(p):(p.read_bytes(),p.stat().st_ino,p.stat().st_mode,p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='p2-b3-test-b4-',dir='/tmp');self.req=fixture(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_real_prepared_consumer_and_original_sandbox_policy(self):
        value=b4.handoff(self.req)
        self.assertEqual(value['real_consumer']['status'],'PREPARED_CONFIG_VALIDATED')
        self.assertEqual(value['policy']['agents']['entries']['developer']['sandbox']['workspaceAccess'],'rw')
        self.assertEqual(value['policy']['agents']['entries']['platform-engineer']['sandbox']['workspaceAccess'],'ro')
        self.assertFalse(value['real_consumer']['roles_verified_for_start'])
        self.assertEqual(value['real_consumer']['start_requirements'][0],'ACTIVE descriptor')
    def test_receipt_tamper_and_wrong_identity_rejected(self):
        req=copy.deepcopy(self.req);req['b3_receipt_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'B3_RECEIPT_SHA'):b4.handoff(req)
        req=copy.deepcopy(self.req);req['sources']['ledger_service.py']='f'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_SHA'):b4.handoff(req)
    def test_checkpoint_chain_tamper_rejected(self):
        path=Path(self.req['b3_root'])/'prepared/CP07-committed.json';row=json.loads(path.read_bytes());row['previous_receipt_sha256']='f'*64;path.chmod(0o600);path.write_bytes(b3.encode(row))
        with self.assertRaisesRegex(ValueError,'CHECKPOINT_CHAIN'):b4.handoff(self.req)
    def test_runtime_source_is_fixed_499bcc43(self):
        import production.p2_runtime as runtime
        self.assertEqual(b3.sha(Path(runtime.__file__).read_bytes()),b4.RUNTIME_SHA)
        value=b4.handoff(self.req);request=b4.runtime_request(self.req,'developer',value)
        self.assertEqual(request['inputs']['health']['type'],'unix_socket')
        self.assertIn('CP10_FINITE_READY',request['inputs']['health']['expect'])
        self.assertNotIn('PONG',request['inputs']['health']['expect'])
    def test_normal_ledger_start_guard_unchanged(self):
        import ledger_service
        with self.assertRaisesRegex(ValueError,'PREPARATION_PROFILE_CANNOT_START'):
            ledger_service.build({'profile':'ISOLATED_NEW_PREPARE_ONLY'})
    def test_inspect_unstarted_never_launches(self):
        with mock.patch.object(b4,'runtime_cli',side_effect=AssertionError('no process launch')):
            self.assertEqual(b4.dispatch(self.req,'developer','inspect')['status'],'NOT_EXECUTED')


def role_driver(req,role):
    before=prior(req);first=call(req,role)
    if first['status']!='CP10_FINITE_COMMITTED':raise AssertionError(first)
    for action in ('inspect','recover','execute'):
        result=call(req,role,action)
        if result!=first:raise AssertionError((action,result,first))
    assert before==prior(req)
    assert not Path(req['b3_root'],'data/ledger.sqlite3').exists()
    assert not Path(req['b3_root'],'run/ledger.sock').exists()
    print(json.dumps({'status':'CP10_REAL_ROLE_PASS','role':role,'result':first,'b3_unchanged':True}))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='fixture':fixture(sys.argv[2])
    elif len(sys.argv)>1 and sys.argv[1]=='role':role_driver(json.loads(Path(sys.argv[2]).read_bytes()),sys.argv[3])
    else:unittest.main()
