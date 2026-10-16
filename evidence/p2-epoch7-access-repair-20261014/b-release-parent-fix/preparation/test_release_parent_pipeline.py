"""New B collector-to-private-output integration over real frozen compilers.

Only host facts, native private-byte pins and reviewer receipt are synthetic.
The historical collect_inputs/v4 boundary is explicitly not reproduced here.
The new FD collector, seed hydration, both identity-policy compilers, whole107
factory, plan compiler, serialization and exclusive output writer are real.
"""
import ast
import copy
import errno
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
STAGE=ROOT.parent
KIT=pathlib.Path(os.environ.get('EPOCH7_PREP_TEST_KIT_ROOT',str(STAGE/'kit/epoch7-recovery-candidate-r7')))
PIN='7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
# Authenticate every original source before any factory fixture import.
raw=(KIT/'recovery-kit-manifest.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==PIN
manifest=json.loads(raw.decode())
for name,pin in manifest['files'].items():assert hashlib.sha256((KIT/name).read_bytes()).hexdigest()==pin
os.environ['EPOCH7_PREP_TEST_KIT_ROOT']=str(KIT)

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path));module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module

consumer=load(ROOT/'tests/test_fresh_release_parent.py','fresh_parent_consumer_fixture')
p=load(HERE/'epoch7_prepare.py','epoch7_prepare')
data=load(HERE/'epoch7_prepare_data.py','epoch7_prepare_data')
topology=load(HERE/'epoch7_topology_projection.py','epoch7_topology_projection')
collector_fixture=load(HERE/'test_fresh_release_parent.py','fresh_parent_collector_fixture')
sys.path.insert(0,str(STAGE/'fixtures/r7-saved-preparation-candidate'))
import test_epoch7_topology_projection as topology_fixture
import epoch7_additive_identity as owner
import epoch7_additive_server as server
from test_epoch7_full_factory_fixture import directory,meta,packed,native_pins
from test_node_sqlite_probe import fixture_proof


def public_fixture_functions():
    path=ROOT/'reference-tests/test_epoch7_prepare.py';raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='556187e54fa38a2901ca5dd3703a9c3afe54b0685a25eac565ce12c1dd5f43ae'
    text=raw.decode();parsed=ast.parse(text);lines=text.splitlines(True)
    names={'seed_fixture','mapped_info','fixture_owners','local_entry'}
    scope={'make_seed':consumer.seed_fixture,'owner':owner,'server':server,'directory':directory,
        'meta':meta,'packed':packed,'data':data,'d':consumer.d,'factory':consumer.factory,'node':consumer.node_probe,
        'fixture_proof':fixture_proof,'p':p,'os':os,'types':types,'pathlib':pathlib,
        '__file__':str(path),'fixture_kit':lambda:KIT}
    for index,node in enumerate(parsed.body):
        if isinstance(node,ast.FunctionDef) and node.name in names:
            end=parsed.body[index+1].lineno-1 if index+1<len(parsed.body) else len(lines)
            exec(compile(''.join(lines[node.lineno-1:end]),str(path),'exec'),scope)
    assert names<=set(scope)
    return scope


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.functions=public_fixture_functions()
        self.seed,self.tools=self.functions['seed_fixture']()
        self.collector=collector_fixture.ParentFixture('runTest');self.collector.setUp()
        self.addCleanup(self.collector.tearDown)
        self.before=copy.deepcopy(self.seed['observation'])
        self.parent=self.collector.gather.release_parent(self.seed['observation'])
        self.seed['fresh_release_parent']=self.parent
        self.top_fixture=topology_fixture.fixture();self.proposal=topology_fixture.project(self.top_fixture)
        self.review={'review_id':7000000001,'approval_body_sha256':'3'*64,
                     'evidence_sha256':self.proposal['topology_sha256']}
        self.collected={'observation':self.seed['observation'],'compiled':self.seed['compiled'],
            'buffers':{key:self.seed[key] for key in data.RAW_PATHS},
            'manifest_raw':self.seed['source_manifest_raw'],'source_payloads':self.seed['source_payloads'],
            'tool_sources':self.tools,'socket_dropins':self.top_fixture['dropins'],
            'fresh_unit_authority':{'schema':1,'kind':'FRESH_R7_UNIT_DROPIN_AUTHORITY',
                'saved_unit_dropins_sha256':data.sha(data.canonical(self.top_fixture['dropins'])),
                'units':{},'reread':'EXACT_PRE_POST_AND_FINAL'},'fresh_release_parent':self.parent}
        entry=load(ROOT/'kit-overlay/epoch7_recovery_entry.py','pipeline_target_entry')
        cache={'xuanjun-p2-package/'+name:raw for name,raw in self.seed['source_payloads'].items()}
        cache['xuanjun-p2-package/deploy/integration-manifest.json']=self.seed['source_manifest_raw']
        self.kit=entry.VerifiedKit(p.COMPILER_KIT_ROOT,{'runtime_source_commit':consumer.factory.SOURCE,
            'runtime_source_tree':consumer.factory.SOURCE_TREE,'runtime_manifest_sha256':consumer.factory.MANIFEST},
            cache,data.sha(b'SYNTHETIC_DISTINCT_TARGET_COMPILER_KIT_NOT_PUBLICATION'))
        self.temp=tempfile.TemporaryDirectory(prefix='pipeline-private-',dir=str(HERE));self.addCleanup(self.temp.cleanup)
        self.output_root=self.temp.name

    def compile(self):
        with native_pins(self.seed):
            return p.compile_private_bundle(self.kit,self.collected,self.proposal['topology_raw'],self.review,True,data)

    def publish(self,bundle):
        entry,proxy=self.functions['local_entry']()
        with mock.patch.object(p,'os',proxy),mock.patch.object(p,'CAND',self.output_root):
            rows=p.publish_bundle(entry,bundle,self.proposal,{'schema':1,'files':{}},time.monotonic()+60)
            p.verify_publication(entry,rows,time.monotonic()+60)
            return rows

    def test_real_new_chain_produces_exact_three_private_files(self):
        bundle=self.compile();self.collector.gather.recheck()
        self.assertEqual(self.seed['observation'],self.before)
        self.assertNotIn(p.RELEASE_PARENT,self.before['evidence']['retained']['prerequisites']['directories'])
        self.assertEqual(len(self.seed['source_payloads']),107)
        self.assertEqual(bundle['summary']['resource_checkpoints'],17)
        self.assertEqual(bundle['unsigned_approval']['recovery_plan_sha256'],data.sha(bundle['plan_raw']))
        wire=json.loads(bundle['seed_raw'].decode())['seed']
        self.assertEqual(len(wire),12)
        self.assertEqual(wire['fresh_release_parent'],self.parent)
        self.assertEqual(wire['observation'],self.before)
        self.assertEqual(bundle['summary']['snapshot_sha256'],self.before['snapshot_sha256'])
        rows=self.publish(bundle);self.collector.gather.recheck()
        self.assertEqual(len(rows),3)
        for row in rows:
            content=pathlib.Path(row['path']).read_bytes()
            self.assertEqual(data.sha(content),row['sha256'])
            self.assertEqual(os.stat(row['path']).st_mode&0o777,0o600)
        packet=next(json.loads(pathlib.Path(row['path']).read_text()) for row in rows if 'review-packet-' in row['path'])
        self.assertEqual(packet['fresh_release_parent'],self.parent)
        self.assertEqual(packet['saved_projection_source_manifest_sha256'],p.SAVED_PROJECTION_MANIFEST_SHA)
        self.assertIsNone(packet['final_review_id'])
        self.assertEqual(self.seed['observation'],self.before)

    def test_parent_identity_drift_after_real_compile_prevents_outputs(self):
        self.compile()
        target=self.collector.root/'opt/xuanjun-control-releases'
        target.rename(target.with_name('old-release-parent'));target.mkdir(mode=0o750)
        with self.assertRaises(ValueError):self.collector.gather.recheck()
        self.assertEqual(os.listdir(self.output_root),[])

    def test_parent_drift_after_publication_is_not_final_success(self):
        bundle=self.compile();rows=self.publish(bundle)
        os.chmod(str(self.collector.root/'opt/xuanjun-control-releases'),0o700)
        with self.assertRaises(ValueError):self.collector.gather.recheck()
        self.assertEqual(len(rows),3)
        self.assertTrue(all(pathlib.Path(row['path']).is_file() for row in rows))
        self.assertEqual(bundle['fresh_release_parent']['recheck'],'PRECOMPILE_MATCHED_FINAL_RECHECK_REQUIRED')
        self.assertNotIn('fresh_release_parent_final_recheck',bundle['summary'])

    def test_private_seed_roundtrip_recomputes_same_future_consumer_plan(self):
        bundle=self.compile();wire=json.loads(bundle['seed_raw'].decode())['seed']
        hydrated=self.kit._hydrate_seed(wire,consumer.factory)
        with native_pins(self.seed):
            prepared=consumer.factory.prepare_host_inputs(hydrated)
            recomputed=consumer.factory.compile_host_contract(prepared['inputs'])
        self.assertEqual(p.packed(recomputed),bundle['plan_raw'])
        self.assertEqual(hydrated['observation'],self.before)
        self.assertEqual(hydrated['fresh_release_parent'],self.parent)
        self.assertEqual(hydrated['kit_manifest_sha256'],self.kit.digest)
        self.assertNotEqual(self.kit.digest,p.KIT_SHA)
        self.assertNotEqual(self.kit.digest,self.seed['kit_manifest_sha256'])
        self.assertEqual(self.kit.root,p.CAND+'/epoch7-recovery-candidate-r7-parentfix')
        self.assertEqual(hydrated['artifact']['root'],self.kit.root+'/xuanjun-p2-package')
        self.assertFalse(prepared['install_admission'])
        self.assertEqual(os.listdir(self.output_root),[])

    def test_existing_output_collision_preserves_all_exact_files(self):
        bundle=self.compile();rows=self.publish(bundle)
        before={row['path']:pathlib.Path(row['path']).read_bytes() for row in rows}
        with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):self.publish(bundle)
        self.assertEqual({path:pathlib.Path(path).read_bytes() for path in before},before)
        self.assertEqual(len(os.listdir(self.output_root)),3)

    def test_partial_second_file_failure_retains_safe_created_path_report(self):
        bundle=self.compile();entry,proxy=self.functions['local_entry']()
        original_open,original_write=proxy.open,proxy.write
        created=[];failed_fd=[None]
        def opening(path,flags,*args,**kwargs):
            fd=original_open(path,flags,*args,**kwargs)
            if flags&os.O_CREAT:
                created.append(path)
                if len(created)==2:failed_fd[0]=fd
            return fd
        def writing(fd,raw):
            if fd==failed_fd[0]:raise OSError(errno.ENOSPC,'synthetic private error')
            return original_write(fd,raw)
        proxy.open=opening;proxy.write=writing
        with mock.patch.object(p,'os',proxy),mock.patch.object(p,'CAND',self.output_root):
            with self.assertRaises(OSError) as caught:
                p.publish_bundle(entry,bundle,self.proposal,{},time.monotonic()+60)
        error=caught.exception
        self.assertEqual(len(error.preparation_created_paths),2)
        self.assertEqual(len(error.preparation_outputs),1)
        self.assertEqual(set(error.preparation_created_paths),{self.output_root+'/'+x for x in created})
        for path in error.preparation_created_paths:self.assertEqual(os.stat(path).st_mode&0o777,0o600)
        self.assertNotIn('fresh_release_parent_final_recheck',bundle['summary'])

    def test_target_hydration_and_whole_factory_reject_modified_parent(self):
        self.collected['fresh_release_parent']['metadata']['gid']=123
        with self.assertRaises(ValueError):self.compile()
        self.assertEqual(os.listdir(self.output_root),[])


if __name__=='__main__':unittest.main(verbosity=2)
