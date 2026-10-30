"""Delivery schema through actual controlled_apply, gate and durable Coordinator.

All 23 controller modules are copied byte-for-byte into an isolated interpreter.
Only GitHub responses, sandbox custody and the final host-effect adapter are
fixtures. No permission verifier, source verifier or Coordinator is mocked.
This is not a server installation or live authorization receipt.
"""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from scripts import pr122_static_source_package as package
from scripts.pr122_customer_core import canonical, digest
from tests.test_pr122_static_public_transport import _PublicFixture, COMMENTS, NOW, REAL_SUBPROCESS_RUN

PROGRAM = r'''
import sys,json,fcntl,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from scripts import pr122_static_workflow as s, pr122_static_github_approval as d
from scripts import pr122_site_hub_unified_release as original
from scripts import pr122_customer_release as r, pr122_customer_attempts as a
from scripts import pr122_customer_workflow as w, pr122_static_operations as operations
from scripts.pr122_customer_core import Denied
value=json.loads(sys.stdin.read());seen=[];effects=[]
original.PINS=root/'HOST_PINS.json';original.c.CONTROL=root/'control'
original.c.CONTROL.mkdir(mode=0o700)
original.c.read=lambda path:Path(path).read_bytes()
original.c.trusted=lambda *args:None
transaction=original.Transaction.__new__(original.Transaction)
transaction.id=value['plan']['transaction'];transaction.pins=json.loads(original.PINS.read_bytes())
lock=original.c.CONTROL/'transaction.lock';lock.touch(mode=0o600)
class Response:
    status=200
    def __init__(self,raw):self.raw=raw;self.headers={'X-RateLimit-Remaining':str(60-len(seen)),'X-RateLimit-Reset':'1792339200'}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw[:n]
def opened(request,timeout):
    path=request.full_url.split('/'+d.REPOSITORY+'/',1)[1];seen.append(path)
    assert not any(k.lower()=='authorization' for k,v in request.header_items())
    return Response(json.dumps(value['responses'][path]).encode())
def private(path):
    if Path(path).name=='STATIC_GITHUB_DUAL_APPROVAL.json':return value['trust']
    return json.loads(Path(path).read_bytes())
class HostEffectFixture:
    def input(self,stage):return {'stage':stage}
    def implementation(self,stage):return stage.encode()
    def inherited(self,stage):return value['receipts'][stage]
    def verify(self,stage,checkpoint):return checkpoint==value['receipts'][stage]
    def execute(self,stage,lease):
        lease.assert_active();lease.authority();lease.verify_inputs(stage)
        effects.append(stage)
        if value['case']=='unknown':raise KeyboardInterrupt()
        return value['receipts'][stage]
    def reconcile(self,stage,intent,checkpoint,lease):
        lease.assert_fence()
        return {'status':'UNKNOWN','action':'RECONCILE_STATIC','evidence_sha256':'b'*64,'checkpoint':None}
if value['case']=='source_drift':
    path=root/'scripts/pr122_static_workflow.py';path.write_bytes(path.read_bytes()+b'\n# changed after admission\n')
fd=os.open(lock,os.O_RDWR)
try:
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with patch.object(a,'read_private',side_effect=private),patch.object(w,'read_private',side_effect=private),patch.object(w,'protected_directory',lambda p:None),patch.object(r,'github',side_effect=AssertionError('No credential/legacy fallback')),patch.object(d.urllib.request,'build_opener',return_value=SimpleNamespace(open=opened)),patch.object(d.time,'time',return_value=value['now']),patch.object(operations,'OriginalStaticOperations',return_value=HostEffectFixture()):
        try:
            result=s.controlled_apply(transaction,root,4,value['plan'],fd)
            status=result['state']
        except KeyboardInterrupt:status='UNKNOWN_INTERRUPTED'
        except (Denied,RuntimeError) as error:status=str(error)
        if value['case']=='unknown':
            ledger=root/'control/transactions'/(transaction.id+'.attempts.json')
            before=ledger.read_bytes();count=len(effects)
            try:s.controlled_apply(transaction,root,4,value['plan'],fd)
            except (Denied,RuntimeError):pass
            assert len(effects)==count and ledger.read_bytes()==before
    ledger=root/'control/transactions'/(transaction.id+'.attempts.json')
    data=json.loads(ledger.read_bytes()) if ledger.exists() else None
    print(json.dumps({'status':status,'effects':effects,'requests':len(seen),'ledger':data}))
finally:os.close(fd)
'''

class DeliveryControlledApplyTests(_PublicFixture, unittest.TestCase):
    def exercise(self, case='valid'):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            raw,report=package.build(Path(__file__).resolve().parents[1],self.plan['source_commit'])
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
                for member in archive:
                    target=root/member.name.removeprefix('pr122-static-controlled/')
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(member).read())
            manifest_raw=(root/'STATIC_SOURCE_MANIFEST.json').read_bytes();manifest=json.loads(manifest_raw)
            # Keep the reviewed public content exact; controller source is a new closure.
            self.plan['static_inputs']={'fixture':'NO_HOST_ACTIONS'}
            self.plan['artifact_tar_sha256']='4881d1e30da4815969cb44fd82411e0bef179cafa3444bf03f58e0ad8aabed80'
            pins={'package_schema':'FULL_STATIC_DELIVERY_REVIEW_V1','static_artifact_sha256':self.plan['artifact_tar_sha256'],
                  'previous_release':str(root/'previous'),'previous_receipt_sha256':'1'*64,
                  'previous_manifest_sha256':'2'*64,'nginx':{},'static_source_manifest_sha256':digest(manifest_raw)}
            if case=='wrong_schema':pins['package_schema']='FULL_STATIC_DELIVERY_REVIEW_V2'
            pins_raw=canonical(pins);(root/'HOST_PINS.json').write_bytes(pins_raw)
            baseline={k:pins[k] for k in ('previous_release','previous_receipt_sha256','previous_manifest_sha256','nginx')}
            bindings={'artifact_tar_sha256':self.plan['artifact_tar_sha256'],'manifest_sha256':digest(manifest_raw),
                      'scope_sha256':digest(canonical(manifest['files'])),'host_pins_sha256':digest(pins_raw),
                      'static_baseline_sha256':digest(canonical(baseline))}
            if case=='wrong_manifest':bindings['manifest_sha256']='f'*64
            self.plan.update(bindings)
            if case=='wrong_artifact':self.plan['artifact_tar_sha256']='f'*64
            if case=='wrong_commit':self.plan['source_commit']='c'*40
            for obj in (self.approval,self.review):obj.update(bindings)
            self.review['findings']['R3']['evidence_sha256']=[bindings['static_baseline_sha256']]
            self.bind_public()
            if case=='wrong_permit':
                self.approval['max_executions']=6;self.prepare()
            if case=='wrong_scope':self.plan['scope_sha256']='e'*64
            if case=='wrong_pins':(root/'HOST_PINS.json').write_bytes(pins_raw+b' ')
            payload={'trust':self.trust,'plan':self.plan,'case':case,'now':NOW+18000 if case=='expired' else NOW,
                     'receipts':self.ops.receipts,'responses':{**self.responses,COMMENTS:list(self.comments.values())}}
            result=REAL_SUBPROCESS_RUN([sys.executable,'-I','-S','-B','-c',PROGRAM,str(root)],input=canonical(payload),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=False)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            receipt=json.loads(result.stdout)
            if os.environ.get('PR122_DELIVERY_TEST_RECEIPTS'):
                output=Path(os.environ['PR122_DELIVERY_TEST_RECEIPTS']);output.mkdir(parents=True,exist_ok=True)
                (output/(case+'.json')).write_bytes(canonical({'scope':'ISOLATED_FIXTURE_NOT_INSTALLATION','case':case,**receipt}))
            return receipt

    def test_exact_delivery_binding_completes_all_controlled_stages(self):
        result=self.exercise();self.assertEqual(result['status'],'SUCCESS')
        self.assertEqual(result['effects'],list(__import__('scripts.pr122_static_workflow',fromlist=['STAGES']).STAGES))
        self.assertEqual(result['ledger']['attempts'][0]['state'],'SUCCESS')
        self.assertEqual(len(result['ledger']['checkpoints']),10)
    def test_wrong_schema_rejected_before_effect_or_ledger(self):self.check_reject('wrong_schema','STATIC_ARTIFACT_PLAN_BINDING')
    def test_wrong_artifact_rejected_before_effect_or_ledger(self):self.check_reject('wrong_artifact','STATIC_ARTIFACT_PLAN_BINDING')
    def test_source_bytes_drift_rejected_before_effect_or_ledger(self):self.check_reject('source_drift','STATIC_SOURCE_BYTES')
    def test_wrong_manifest_rejected_before_effect_or_ledger(self):self.check_reject('wrong_manifest','WORKFLOW_SOURCE_DRIFT')
    def test_wrong_permit_rejected_before_effect_or_ledger(self):self.check_reject('wrong_permit')
    def test_wrong_scope_rejected_before_effect_or_ledger(self):self.check_reject('wrong_scope')
    def test_wrong_source_commit_rejected_before_effect_or_ledger(self):self.check_reject('wrong_commit')
    def test_host_pins_drift_rejected_before_effect_or_ledger(self):self.check_reject('wrong_pins','STATIC_HOST_PINS_DRIFT')
    def test_expired_permit_rejected_before_effect_or_ledger(self):self.check_reject('expired')
    def test_unknown_stops_and_preserves_single_attempt(self):
        result=self.exercise('unknown');self.assertEqual(result['status'],'UNKNOWN_INTERRUPTED')
        self.assertEqual(len(result['effects']),1);self.assertEqual(len(result['ledger']['attempts']),1)
        self.assertIsNotNone(result['ledger']['intent'])
    def check_reject(self,case,code=None):
        result=self.exercise(case)
        if code:self.assertIn(code,result['status'])
        else:self.assertIn('HOLD:',result['status'])
        self.assertEqual(result['effects'],[]);self.assertIsNone(result['ledger'])
