"""Independent-process readback over exact-format synthetic R03 mirrors only."""
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
import unittest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'production/p2_install/rebind_readback.py'
spec = importlib.util.spec_from_file_location('readback', str(TOOL))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
a = importlib.util.spec_from_file_location('frozen', str(REPO / r.SOURCE))
frozen = importlib.util.module_from_spec(a)
a.loader.exec_module(frozen)


def write(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(mode)


def fixture(root, cut):
    paths = {k: Path(str(root) + v) for k, v in r.RESOURCES.items()}
    old = {'schema': 1, 'state': 'PREPARED', 'release_sha256': '1'*64,
        'config_sha256': '2'*64, 'binary_sha256': '3'*64,
        'ledger_uuid': '11111111-1111-1111-1111-111111111111',
        'generation': 1, 'epoch': 7, 'instance': '22222222-2222-2222-2222-222222222222',
        'db_path': '/isolated/db.sqlite3', 'ledger_socket': '/isolated/ledger.sock'}
    new = dict(old, epoch=8, release_sha256='4'*64)
    context = '5'*64
    binding = {'review_id': 'SYNTHETIC_TEST_ONLY', 'approval_body_sha256': 'a'*64,
        'authorization_sha256': 'b'*64, 'delta_sha256': 'c'*64, 'complete_delta_sha256': 'd'*64,
        'additive_targets_sha256': 'e'*64, 'snapshot_sha256': '6'*64}
    proof = {'controller_transition_sha256': '7'*64, 'approval_body_sha256': 'a'*64,
        'snapshot_sha256': '6'*64, 'recovery_plan_sha256': '8'*64,
        'old_descriptor_sha256': frozen.ActivationStore.head(old),
        'new_descriptor_sha256': frozen.ActivationStore.head(new),
        'all_writers_excluded': True, 'install_lock_held': True, 'retained_resources_verified': True}
    journal = b''
    previous = '0'*64
    # Existing durable activation schema/chain, epochs1..7; no production guard invoked.
    for epoch in range(1, 8):
        descriptor = dict(old, epoch=epoch)
        record = {'schema':1,'seq':epoch,'epoch':epoch,'state':'PREPARED',
            'previous_sha256':previous, 'descriptor_sha256':frozen.ActivationStore.head(descriptor),
            'descriptor':descriptor,'proof':{}}
        raw = r.encode(record)+b'\n';journal += raw;previous = r.sha(raw)
    before_journal = journal
    if cut != 'before':
        record = {'schema':1,'seq':8,'epoch':8,'state':'PREPARED','previous_sha256':previous,
            'descriptor_sha256':frozen.ActivationStore.head(new),'descriptor':new,
            'proof':dict(proof,recovery='EXACT_EPOCH7_RELEASE_REBIND',writer_admission=False,previous_epoch=7)}
        journal += r.encode(record)+b'\n'
    outer = {'schema':1,'name':'epoch7-recovery-sequence.json','transaction_id':r.TX,
        'context_sha256':context,'binding':binding,'state':{
            'stage':r.PHASE+'_INTENT','completed':r.PREFIX,'admission':'ADMITTED',
            'containment_status':'NOT_ATTEMPTED','containment':[],'automatic_retry':False}}
    inner = {'schema':1,'name':'epoch7-recovery-execution.json','transaction_id':r.TX,
             'binding':binding,'state':{'stage':'ADMITTED'}}
    outer_raw, inner_raw = r.encode(outer)+b'\n', r.encode(inner)+b'\n'
    for key,raw,mode in [('journal',journal,0o644),('descriptor',r.encode(old if cut in ('before','append') else new)+b'\n',0o644),
        ('lock',b'',0o644),('native',b'old native\n' if cut in ('before','append') else b'new native\n',0o644),
        ('outer',outer_raw,0o600),('inner',inner_raw,0o600)]:write(paths[key],raw,mode)
    if cut in ('native','complete'):write(paths['backup'],b'old native\n')
    if cut == 'complete':write(paths['tls'],b'tls candidate\n')
    refs = {k:{'ref':'fixture:'+k,'sha256':v} for k,v in {
        'context':context,'snapshot':'6'*64,'candidate':'9'*64,'plan':'8'*64,
        'outer':r.sha(outer_raw),'inner':r.sha(inner_raw)}.items()}
    return {'schema':1,'scope':'ISOLATED_TEST_ONLY','root':str(root),'phase':r.PHASE,'transaction_id':r.TX,
        'context_sha256':context,'binding':binding,'proof':proof,'source_refs':refs,
        'before':{'activation':old,'journal_sha256':r.sha(before_journal),'native_sha256':r.sha(b'old native\n')},
        'after':{'activation':new,'native_sha256':r.sha(b'new native\n'),'tls_sha256':r.sha(b'tls candidate\n')}}


def inventory(root):
    return {str(p.relative_to(root)):(r.sha(p.read_bytes()),r.stamp(p.stat())) for p in root.rglob('*') if p.is_file()}


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p2-b3-readback-')
        self.root = Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def invoke(self, value, pin=None):
        before = inventory(self.root)
        proc = subprocess.run([sys.executable,'-B','-S',str(TOOL),'--spec-sha256',pin or r.sha(r.encode(value))],
            input=r.encode(value),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(proc.stderr,b'')
        output=json.loads(proc.stdout)
        self.assertEqual(output['decision'],'HOLD');self.assertFalse(output['write_authority'])
        self.assertEqual(inventory(self.root),before)
        return output
    def crash_fixture(self, cut):
        # A separate fixture producer is killed; a new CLI inspects persisted bytes.
        p=subprocess.run([sys.executable,'-B',__file__,'--fixture-crash',str(self.root),cut],timeout=10)
        self.assertEqual(p.returncode,-signal.SIGKILL)
        return json.loads((self.root/'fixture-spec.json').read_bytes())
    def test_append_before_descriptor_after_sigkill(self):
        out=self.invoke(self.crash_fixture('append'))
        self.assertEqual(out['status'],'UNKNOWN');self.assertEqual(out['interruption'],'ACTIVATION_APPEND_BEFORE_DESCRIPTOR')
        self.assertEqual(out['effects']['activation_append'],'ALREADY_APPLIED')
    def test_native_before_tls_after_sigkill(self):
        out=self.invoke(self.crash_fixture('native'))
        self.assertEqual(out['status'],'UNKNOWN');self.assertEqual(out['interruption'],'NATIVE_REPLACED_BEFORE_TLS_CANDIDATE')
        self.assertEqual(out['effects']['native'],'ALREADY_APPLIED')
    def test_complete_new_process_repeated_readback(self):
        value=fixture(self.root,'complete')
        first=self.invoke(value);second=self.invoke(value)
        self.assertEqual(first['status'],'ALREADY_APPLIED');self.assertEqual(first,second)
    def test_proven_not_applied_requires_positive_prior_history(self):
        self.assertEqual(self.invoke(fixture(self.root,'before'))['status'],'PROVEN_NOT_APPLIED')
    def test_missing_journal_is_unknown(self):
        value=fixture(self.root,'before');Path(str(self.root)+r.RESOURCES['journal']).unlink()
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_missing_backup_is_unknown(self):
        value=fixture(self.root,'complete');Path(str(self.root)+r.RESOURCES['backup']).unlink()
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_changed_proof_is_unknown(self):
        value=fixture(self.root,'native');value['proof']['recovery_plan_sha256']='f'*64
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_changed_request_pin_is_unknown(self):
        self.assertEqual(self.invoke(fixture(self.root,'complete'),'0'*64)['status'],'UNKNOWN')
    def test_wrong_outer_identity_is_unknown(self):
        value=fixture(self.root,'complete');value['context_sha256']='0'*64
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_corrupt_history_is_unknown(self):
        value=fixture(self.root,'complete');p=Path(str(self.root)+r.RESOURCES['journal']);p.write_bytes(p.read_bytes()+b'{broken\n')
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_wrong_resource_mode_is_unknown(self):
        value=fixture(self.root,'complete');Path(str(self.root)+r.RESOURCES['backup']).chmod(0o644)
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_complete_record_conflicts_with_before_effects(self):
        value=fixture(self.root,'before');path=Path(str(self.root)+r.RESOURCES['outer'])
        outer=json.loads(path.read_bytes());outer['state'].update(stage=r.PHASE+'_COMPLETE',completed=r.PREFIX+[r.PHASE])
        raw=r.encode(outer)+b'\n';path.write_bytes(raw);value['source_refs']['outer']['sha256']=r.sha(raw)
        self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_existing_lock_busy_is_unknown(self):
        import fcntl
        value=fixture(self.root,'complete')
        with open(str(self.root)+r.RESOURCES['lock'],'rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.invoke(value)['status'],'UNKNOWN')
    def test_resource_symlink_rejected_without_following(self):
        value=fixture(self.root,'complete');p=Path(str(self.root)+r.RESOURCES['native']);p.unlink();p.symlink_to('/dev/null')
        # inventory intentionally excludes symlinks to avoid reading their target.
        proc=subprocess.run([sys.executable,'-B','-S',str(TOOL),'--spec-sha256',r.sha(r.encode(value))],input=r.encode(value),capture_output=True,timeout=10)
        self.assertEqual(json.loads(proc.stdout)['status'],'UNKNOWN');self.assertTrue(p.is_symlink())


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--fixture-crash':
        root=Path(sys.argv[2]);value=fixture(root,sys.argv[3]);write(root/'fixture-spec.json',r.encode(value))
        for p in root.rglob('*'):
            if p.is_file():
                with p.open('rb') as f:os.fsync(f.fileno())
        os.kill(os.getpid(),signal.SIGKILL)
    else:unittest.main()
