"""Local fresh-B interface regression, using frozen producers and real compilers.

All directory facts are explicitly synthetic. No host collection or authority.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
if (HERE.parent.parent/'epoch7_recovery_entry.py').is_file():
    KIT=HERE.parent.parent;CODE_ROOT=KIT
else:
    KIT=ROOT.parent/'kit'/'epoch7-recovery-candidate-r7';CODE_ROOT=ROOT/'kit-overlay'
PATHS=[CODE_ROOT/'helpers',KIT/'helpers',KIT/'xuanjun-p2-package'/'stage1',
       KIT/'xuanjun-p2-package'/'scripts']
PATHS += [KIT/'tests'/x for x in ('host_factory','service_contract','acceptance_rows','recovery','snapshot','probe','sequence','plan','live_controls','host_filesystem')]
sys.path[:0]=[str(x) for x in PATHS]
import epoch7_resource_plan as resource
import epoch7_host_factory as factory
import epoch7_delta as d
import snapshot_io
from test_epoch7_full_factory_fixture import make_seed,native_pins,directory
from test_node_sqlite_probe import fixture_proof,fixture_receipt
import node_sqlite_probe as node_probe

# Exact historical pure function, retained only to reproduce the original defect.
FROZEN_OLD_ACCESS_SOURCE="def build_access_rows(support,compiled):\n    from exact_access_plan import propose\n    parent=support['retained']['prerequisites']['directories']['/opt/xuanjun-control-releases']\n    rows=[]\n    before={k:parent[k] for k in ('uid','gid','mode','dev','ino','access_acl','default_acl')}\n    before.update(kind='DIRECTORY',sha256=None,state_source='stage_exact_release_observed')\n    rows.append({'path':'/opt/xuanjun-control-releases','before_binding':before,\n                 'proposal':propose(before['access_acl'],'release_traversal',[1002,1003,1004])})\n    target=next(row for row in compiled['runtime']['provisioning'] if row['target']==CLIENT)\n    before={'kind':'FILE','uid':target['owner_uid'],'gid':target['group_gid'],'mode':target['mode'],\n            'sha256':sha(compiled['rendered_targets'][CLIENT]),'access_acl':decode_acl(None,target['mode']),\n            'default_acl':'','state_source':'inner_provision_observed_after'}\n    rows.append({'path':CLIENT,'before_binding':before,\n                 'proposal':propose(before['access_acl'],'ledger_client_binding_read',[1003])})\n    return rows\n"
FROZEN_OLD_ACCESS_SHA256='d77ffeee29c482e10d351b123d771b1f73540934ac5b423d85f193a257d0728b'
FROZEN_OLD_RESOURCE_FILE_SHA256='a1d5455da9acbfd08e446eda68e6eb82637d93000e82f0d5c58b364ad9dde79a'


def producer_directories():
    """The original prerequisite producer, not a hand-written directory map."""
    plan={'groups':{},'users':{},'directories':[
        {'path':'/etc/xuanjun-development','uid':0,'gid':0,'mode':0o755}], 'binaries':[]}
    packages=[{'name':'p'+str(i),'candidate':['p'+str(i),'0','1','1','x86_64']} for i in range(16)]
    calls=[]
    class Reader:
        def directory(self,path):
            calls.append(path);return dict(directory(),path=path)
        def command(self,tool,args):
            return ' '.join(next(r['candidate'] for r in packages if r['name']==args[-1])).encode()
    result=snapshot_io.LocalReadOnlyIO.prerequisites(Reader(),plan,
        {'schema':1,'plan_sha256':d.digest(plan),'actions':[]},
        {'state':'INSTALLED','packages':packages})
    return result['directories'],calls


def seed_fixture():
    seed=make_seed();obs=seed['observation'];retained=obs['evidence']['retained']
    # Replace the old test's fabricated extra row with the genuine producer scope.
    retained['prerequisites']['directories'],unused=producer_directories()
    obs['snapshot']['retained_resource_sha256']=d.digest(retained)
    obs['snapshot_sha256']=d.digest(obs['snapshot'])
    obs['evidence']['snapshot_sha256']=obs['snapshot_sha256']
    obs['evidence_sha256']=d.digest(obs['evidence'])
    # This synthetic fixture's probe must bind its corrected synthetic producer
    # output. No host observation or existing proof is edited by production.
    attempt=obs['finite_probe'];policy=attempt['policy']
    policy['node_sqlite']=node_probe.binding_from_observation(obs)
    pin=node_probe.digest(node_probe.canonical(policy)+b'\n')
    proof=fixture_proof(policy['node_sqlite']['node'],policy['nonce'],pin,
        policy['node_sqlite']['probe_input_sha256'])
    attempt['policy_sha256']=pin;attempt['result']['node_sqlite']=proof
    receipt=fixture_receipt(attempt);reported=attempt['result']['created_receipt']
    reported.update(sha256=node_probe.digest(receipt),node_sqlite_event_sha256=d.digest(proof))
    reported['metadata']['size']=len(receipt)
    def meta(path,ino):
        pin=obs['policy']['directories'][path]
        return directory(uid=pin['uid'],gid=pin['gid'],mode=pin['mode'],ino=ino)
    seed['fresh_release_parent']={
        'schema':1,'kind':'FRESH_B_RELEASE_PARENT_AUTHORITY','path':resource.RELEASE_PARENT,
        'observation_sha256':d.digest(obs),'policy_sha256':obs['policy_sha256'],
        'metadata':meta(resource.RELEASE_PARENT,900),
        'ancestors':{'/':meta('/',1),'/opt':meta('/opt',899)},
        'recheck':'PRECOMPILE_MATCHED_FINAL_RECHECK_REQUIRED'}
    return seed


class FreshParentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=seed_fixture()
    def setUp(self):self.seed=copy.deepcopy(self.base)
    def validate(self):
        return resource.validated_fresh_release_parent(self.seed['fresh_release_parent'],self.seed['observation'])
    def prepare(self):
        with native_pins(self.seed):return factory.prepare_host_inputs(self.seed)
    def test_actual_producer_omits_unlisted_parent(self):
        rows,calls=producer_directories()
        self.assertEqual(calls,['/etc/xuanjun-development'])
        self.assertNotIn(resource.RELEASE_PARENT,rows)
    def test_original_consumer_reproduces_missing_key(self):
        self.assertEqual(hashlib.sha256(FROZEN_OLD_ACCESS_SOURCE.encode()).hexdigest(),FROZEN_OLD_ACCESS_SHA256)
        namespace={};exec(compile(FROZEN_OLD_ACCESS_SOURCE,'<unchanged-frozen-consumer>','exec'),namespace)
        with self.assertRaises(KeyError) as error:
            namespace['build_access_rows'](self.seed['observation']['evidence'],self.seed['compiled'])
        self.assertEqual(error.exception.args,(resource.RELEASE_PARENT,))
    def test_typed_exact_valid_proof_and_no_input_mutation(self):
        before=copy.deepcopy(self.seed);row=self.validate()
        self.assertEqual(row,self.seed['fresh_release_parent']['metadata'])
        row['ino']=999;self.assertEqual(self.seed,before)
    def test_required_field_missing_or_extra(self):
        for key in resource.FRESH_PARENT_FIELDS:
            with self.subTest(key=key):
                self.seed=copy.deepcopy(self.base);del self.seed['fresh_release_parent'][key]
                with self.assertRaises(ValueError):self.validate()
        self.seed=copy.deepcopy(self.base);self.seed['fresh_release_parent']['extra']=True
        with self.assertRaises(ValueError):self.validate()
    def test_wrong_schema_kind_path_or_premature_final(self):
        for key,value in [('schema',True),('schema',2),('kind','OLD_RETAINED'),
                          ('path','/opt/other'),('recheck','FINAL_COMPLETED')]:
            with self.subTest(key=key,value=value):
                self.seed=copy.deepcopy(self.base);self.seed['fresh_release_parent'][key]=value
                with self.assertRaises(ValueError):self.validate()
    def test_observation_and_policy_binding(self):
        for key in ('observation_sha256','policy_sha256'):
            self.seed=copy.deepcopy(self.base);self.seed['fresh_release_parent'][key]='0'*64
            with self.assertRaisesRegex(ValueError,'OBSERVATION_BINDING'):self.validate()
    def test_missing_extra_or_unknown_ancestor(self):
        for names in (('/',),('/','/opt','/tmp'),('/','/other')):
            self.seed=copy.deepcopy(self.base)
            self.seed['fresh_release_parent']['ancestors']={x:directory() for x in names}
            with self.assertRaisesRegex(ValueError,'ANCESTORS'):self.validate()
    def test_all_metadata_missing_and_extra_refused(self):
        for section in ('metadata','root','opt'):
            for key in resource.DIRECTORY_FIELDS:
                self.seed=copy.deepcopy(self.base);proof=self.seed['fresh_release_parent']
                row=proof['metadata'] if section=='metadata' else proof['ancestors']['/' if section=='root' else '/opt']
                del row[key]
                with self.subTest(section=section,key=key),self.assertRaises(ValueError):self.validate()
            self.seed=copy.deepcopy(self.base);self.seed['fresh_release_parent']['metadata']['extra']=1
            with self.assertRaises(ValueError):self.validate()
    def test_bool_negative_and_oversized_numeric_metadata_refused(self):
        for key in ('uid','gid','mode','dev','ino','nlink','size','mtime_ns','ctime_ns'):
            for value in (True,-1,2**64):
                self.seed=copy.deepcopy(self.base);self.seed['fresh_release_parent']['metadata'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.validate()
    def test_wrong_owner_mode_type_or_acl_refused(self):
        for key,value in [('uid',1002),('gid',1002),('mode',0o777),('kind','LINK'),
                          ('access_acl','user:1002:rwx\n'),('default_acl','default:user::rwx\n'),('ino',0),('nlink',0)]:
            self.seed=copy.deepcopy(self.base);self.seed['fresh_release_parent']['metadata'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate()
    def test_policy_missing_drift_or_bool_refused(self):
        for path in ('/','/opt',resource.RELEASE_PARENT):
            for mode in ('missing','drift','bool'):
                self.seed=copy.deepcopy(self.base);obs=self.seed['observation'];pins=obs['policy']['directories']
                if mode=='missing':del pins[path]
                elif mode=='drift':pins[path]['mode']=0o700
                else:pins[path]['uid']=False
                obs['policy_sha256']=d.digest(obs['policy'])
                self.seed['fresh_release_parent'].update(observation_sha256=d.digest(obs),policy_sha256=obs['policy_sha256'])
                with self.subTest(path=path,mode=mode),self.assertRaises(ValueError):self.validate()
    def test_original_saved_evidence_has_no_new_row_after_validation(self):
        before=d.digest(self.seed['observation']);self.validate()
        self.assertEqual(d.digest(self.seed['observation']),before)
        self.assertNotIn(resource.RELEASE_PARENT,self.seed['observation']['evidence']['retained']['prerequisites']['directories'])
    def test_ancestor_gid_must_match_exact_saved_policy_not_assumed_zero(self):
        obs=self.seed['observation'];obs['policy']['directories']['/opt']['gid']=123
        obs['policy_sha256']=d.digest(obs['policy'])
        proof=self.seed['fresh_release_parent'];proof['ancestors']['/opt']['gid']=123
        proof.update(observation_sha256=d.digest(obs),policy_sha256=obs['policy_sha256'])
        self.validate()
        proof['ancestors']['/opt']['gid']=124
        with self.assertRaisesRegex(ValueError,'SAVED_POLICY'):self.validate()
    def test_parent_gid_zero_remains_required_even_with_matching_policy(self):
        obs=self.seed['observation'];obs['policy']['directories'][resource.RELEASE_PARENT]['gid']=123
        obs['policy_sha256']=d.digest(obs['policy']);proof=self.seed['fresh_release_parent']
        proof['metadata']['gid']=123
        proof.update(observation_sha256=d.digest(obs),policy_sha256=obs['policy_sha256'])
        with self.assertRaisesRegex(ValueError,'EXACT_MODE'):self.validate()
    def test_genuine_whole_factory_with_real_producer_scope(self):
        before=copy.deepcopy(self.seed);result=self.prepare()
        self.assertEqual(result['state'],'COMPILED_NOT_ADMITTED');self.assertEqual(result['unresolved'],[])
        self.assertFalse(result['install_admission']);self.assertEqual(self.seed,before)
        inputs=result['inputs'];self.assertEqual(len(inputs['resource_views']),17)
        self.assertEqual(inputs['observation'],before['observation'])
        parent=next(x for x in inputs['access_rows'] if x['path']==resource.RELEASE_PARENT)
        self.assertEqual(parent['before_binding']['ino'],900)
        for view in inputs['resource_views']:
            row=next(x for x in view['release'] if x['path']==resource.RELEASE_PARENT)
            self.assertEqual(row['ino'],900)
        with native_pins(self.seed):self.assertEqual(factory.compile_host_contract(inputs),factory.compile_host_contract(copy.deepcopy(inputs)))
    def test_missing_fresh_input_refuses_before_factory_effects(self):
        del self.seed['fresh_release_parent']
        with mock.patch.object(factory,'ExistingInstallLock') as effect:
            with self.assertRaisesRegex(ValueError,'COMPLETE_MEASURED_SEED'):factory.prepare_host_inputs(self.seed)
            effect.assert_not_called()
    def test_final_compile_rechecks_fresh_proof_and_derived_rows(self):
        result=self.prepare();inputs=result['inputs'];inputs['fresh_release_parent']['metadata']['ino']+=1
        with native_pins(self.seed),self.assertRaisesRegex(ValueError,'SOURCE_DERIVED_ACCESS_ROWS'):
            factory.compile_host_contract(inputs)
    def test_old_retained_row_cannot_override_fresh(self):
        obs=self.seed['observation'];obs['evidence']['retained']['prerequisites']['directories'][resource.RELEASE_PARENT]=directory(ino=777)
        # Changed old evidence is not made legitimate by a new B proof.
        self.seed['fresh_release_parent']['observation_sha256']=d.digest(obs)
        with native_pins(self.seed),self.assertRaises(ValueError):factory.prepare_host_inputs(self.seed)
    def test_entry_interface_explicitly_transports_fresh_field(self):
        spec=importlib.util.spec_from_file_location('fresh_entry_fixture',str(CODE_ROOT/'epoch7_recovery_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        self.assertIn('fresh_release_parent',entry.PRIVATE_SEED_FIELDS)
        self.assertEqual(entry.PRIVATE_SEED_FIELDS|entry.CACHE_SEED_FIELDS,factory.INPUTS-factory.DERIVED_INPUTS)
    def entry(self):
        spec=importlib.util.spec_from_file_location('fresh_entry_resume_fixture',str(CODE_ROOT/'epoch7_recovery_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry);return entry
    def test_resume_refuses_old_root_before_private_reads(self):
        entry=self.entry();kit=object.__new__(entry.VerifiedKit)
        kit.root=entry.CANDIDATE_PARENT+'/epoch7-recovery-candidate-r7'
        kit.manifest={'production_resume':entry.RESUME_COMPOSED}
        with mock.patch.object(entry.os,'geteuid',return_value=0),mock.patch.object(entry.os,'uname',return_value=types.SimpleNamespace(nodename=entry.FIXED_HOST)),mock.patch.object(kit,'_private_resume_inputs') as read:
            with self.assertRaisesRegex(ValueError,'RESUME_FIXED_HOST_ROOT'):
                kit.resume('plan','a'*64,'seed','b'*64,1,'c'*64)
            read.assert_not_called()
    def test_new_resume_root_still_requires_fresh_complete_review_arguments(self):
        entry=self.entry();kit=object.__new__(entry.VerifiedKit)
        kit.root=entry.CANDIDATE_PARENT+'/epoch7-recovery-candidate-r7-resourcebind'
        kit.manifest={'production_resume':entry.RESUME_COMPOSED}
        with mock.patch.object(entry.os,'geteuid',return_value=0),mock.patch.object(entry.os,'uname',return_value=types.SimpleNamespace(nodename=entry.FIXED_HOST)),mock.patch.object(kit,'_private_resume_inputs') as read:
            for review in (None,True,0,-1):
                with self.subTest(review=review),self.assertRaisesRegex(ValueError,'FRESH_REVIEW_ARGUMENTS_REQUIRED'):
                    kit.resume('plan','a'*64,'seed','b'*64,review,'c'*64)
            read.assert_not_called()
    def test_new_resume_root_reaches_protected_inputs_without_authorizing_effects(self):
        entry=self.entry();kit=object.__new__(entry.VerifiedKit)
        kit.root=entry.CANDIDATE_PARENT+'/epoch7-recovery-candidate-r7-resourcebind'
        kit.manifest={'production_resume':entry.RESUME_COMPOSED};kit.digest='d'*64
        with mock.patch.object(entry.os,'geteuid',return_value=0),mock.patch.object(entry.os,'uname',return_value=types.SimpleNamespace(nodename=entry.FIXED_HOST)),mock.patch.object(kit,'_private_resume_inputs',side_effect=ValueError('SYNTHETIC_PROTECTED_INPUT_STOP')) as read:
            result=kit.resume('plan','a'*64,'seed','b'*64,1,'c'*64)
            self.assertFalse(result['success']);self.assertEqual(result['install_admission'],'NOT_GRANTED')
            self.assertEqual(result['production_resume'],'NOT_EXECUTED');read.assert_called_once()
    def test_input_digest_binds_all_fresh_metadata(self):
        original=factory.input_digest(self.seed);self.seed['fresh_release_parent']['metadata']['ctime_ns']+=1
        self.assertNotEqual(factory.input_digest(self.seed),original)


if __name__=='__main__':unittest.main(verbosity=2)
