"""Exact retained direct-entry profile; official bytes, synthetic host facts.

The Node link/stamps/probe are explicit public test fixtures. No installed
32nd-source match, fresh UK alias measurement or production admission is claimed.
"""
import base64
import copy
import json
import pathlib
import unittest
import epoch7_openclaw_recipe as oc
import epoch7_service_contract as sc
import epoch7_service_roles as sr
import epoch7_live_controls as live
import unit_metadata as um
import node_sqlite_probe as np
from test_epoch7_openclaw_recipe import complete_fixture
from test_node_sqlite_probe import fixture_attempt,fixture_proof,fixture_receipt
from test_probe_driver import fixture as probe_fixture
from test_epoch7_service_contract import runtime_fixture_root
import test_epoch7_openclaw_family as family
HERE=pathlib.Path(__file__).resolve().parent


def node_reference_fixture(node,target='node-v24.21.0'):
    attrs={'access_acl':False,'default_acl':False,'capability':False}
    link=dict(node['metadata'],kind='SYMLINK',ino=701,mode=0o777,size=len(target.encode()))
    ancestors={}
    for index,path in enumerate(um.NODE_REFERENCE_ANCESTORS):
        owner=0 if path in ('/','/home') else 1002
        ancestors[path]=dict(node['metadata'],kind='DIRECTORY',uid=owner,gid=owner,ino=800+index,
            mode=0o755,size=4096,nlink=2,**attrs)
    proof={'schema':1,'kind':'FIXED_NODE_DIRECTORY_ALIAS','reference_path':oc.DIRECT_NODE_REFERENCE,
        'link':{'path':um.NODE_ALIAS_PATH,'target':target,'metadata':link},
        'final':{'path':node['path'],'sha256':node['sha256'],
                 'metadata':dict(node['metadata'],kind='FILE',sha256=node['sha256'],elf_header=True,**attrs)},
        'ancestors':ancestors,'reread':'EXACT_PRE_POST'}
    return um.validate_node_reference(proof,node['path'],node['sha256'])


def direct_fixture():
    args,delta=complete_fixture();args=list(args);compiled,facts=args[0],args[4]
    recipe=facts['openclaw_recipe_evidence'];node=recipe['node'];node['path']=oc.DIRECT_NODE_PATH
    native=json.loads(args[2].decode());native['gatewayIdentity']['exe']=node['path'];args[2]=json.dumps(native).encode()
    source=json.loads((HERE/'fixtures/openclaw-direct-source-profile.json').read_text())
    assert source['fixture_scope']=='OFFICIAL_SOURCE_BYTES_ONLY_NOT_UK_EVIDENCE'
    for name,row in source['files'].items():
        raw=base64.b64decode(row['content_base64'].encode(),validate=True)
        assert sc.sha(raw)==row['sha256']==oc.DIRECT_SOURCE_HASHES[name]
        recipe['files'][name]={'sha256':row['sha256'],'metadata':dict(recipe['files']['openclaw.mjs']['metadata'],
            ino=2000,size=len(raw))}
    assert len(um.DIRECT_DIST_WRAPPER)==188 and sc.sha(um.DIRECT_DIST_WRAPPER)==oc.DIRECT_WRAPPER_SHA
    recipe['launcher']={'path':oc.LAUNCHER,'sha256':oc.DIRECT_WRAPPER_SHA,'entry_realpath':oc.DIRECT_ENTRY,
        'recipe':um.launcher_recipe(um.DIRECT_DIST_WRAPPER,node['path']),
        'node_reference':node_reference_fixture(node)}
    recipe['quiet_bootstrap']['source_bindings'][oc.LAUNCHER]=oc.DIRECT_WRAPPER_SHA
    path='/etc/xuanjun-development/p2-gateway-relay.json';relay=sc.decode(compiled['rendered_targets'][path])
    relay['openclaw_sha256']=oc.DIRECT_WRAPPER_SHA
    raw=json.dumps(relay,sort_keys=True,separators=(',',':'));compiled['rendered_targets'][path]=raw;pin=sc.sha(raw.encode())
    next(r for r in compiled['runtime']['provisioning'] if r['target']==path)['rendered_sha256']=pin
    next(r for r in delta['changes'] if r['path']==path)['after']['sha256']=pin
    # Rebuild the complete synthetic original observation/attempt binding. The
    # real full-chain validator, not a mocked PASS, verifies the changed Node.
    policy=probe_fixture(source_root=runtime_fixture_root())[0]
    attempt,policy,observed,policy_sha=fixture_attempt(original_policy=policy)
    retained=observed['evidence']['retained'];retained['native_components']['components']={
        node['path']:dict(node['metadata'],kind='FILE',sha256=node['sha256'])}
    observed['snapshot']['retained_resource_sha256']=np.digest(np.canonical(retained))
    observed['snapshot_sha256']=np.digest(np.canonical(observed['snapshot']))
    observed['evidence']['snapshot_sha256']=observed['snapshot_sha256']
    observed['unit_metadata']['sections']['native_gateway']['evidence']['gateway_identity'].update(
        exe=node['path'],sha256=node['sha256'])
    for name in ('evidence','unit_metadata'):observed[name+'_sha256']=np.digest(np.canonical(observed[name]))
    binding=np.binding_from_observation(observed)
    policy['node_sqlite']=copy.deepcopy(binding);policy_sha=np.digest(np.canonical(policy)+b'\n')
    attempt['policy']=copy.deepcopy(policy);attempt['policy_sha256']=policy_sha
    proof=fixture_proof(node,policy['nonce'],policy_sha,binding['probe_input_sha256'])
    attempt['result']['node_sqlite']=proof
    receipt=attempt['result']['created_receipt'];receipt['node_sqlite_event_sha256']=np.digest(np.canonical(proof))
    raw=fixture_receipt(attempt);receipt['sha256']=np.digest(raw);receipt['metadata']['size']=len(raw)
    recipe['node_probe']=np.validated_proof_from_attempt(attempt,policy,observed,policy_sha)
    return tuple(args),delta


class DirectRecipeTests(unittest.TestCase):
    def setUp(self):self.args,self.delta=direct_fixture();self.recipe=self.args[4]['openclaw_recipe_evidence']
    def compile(self):return sc.compile_service_contract(*self.args,candidate_delta=self.delta)
    def test_complete_exact_direct_profile_has_one_node_one_bridge(self):
        result=self.compile();self.assertEqual(result['state'],'COMPLETE');self.assertFalse(result['install_admission'])
        self.assertEqual(result['production_acceptance'],'NOT_VERIFIED')
        roles=result['service_role_contract']['units'][oc.GATEWAY]['roles']
        self.assertEqual([r['name'] for r in roles],['main','bridge_main'])
        self.assertEqual([r['maximum'] for r in roles],[1,1])
        derived=result['derivations'][oc.GATEWAY]['startup_recipe']
        self.assertEqual(derived['gateway_argv'][:2],[oc.DIRECT_NODE_REFERENCE,oc.DIRECT_ENTRY])
        self.assertEqual(roles[0]['identity']['executable'],oc.DIRECT_NODE_PATH)
        self.assertIsNone(derived['cache_child_argv'])
        self.assertEqual(derived['node_reference'],self.recipe['launcher']['node_reference'])
        self.assertEqual(len(derived['source_profile']['source_hashes']),32)
        self.assertEqual(derived['relay_cli_argv'][:2],[oc.DIRECT_NODE_REFERENCE,oc.DIRECT_ENTRY])
        self.assertEqual(derived['relay_respawn_argv'][:3],
            [oc.DIRECT_NODE_PATH,'--disable-warning=ExperimentalWarning',oc.DIRECT_ENTRY])
    def test_old_root_profile_remains31_and_cache_child(self):
        args,delta=complete_fixture();result=sc.compile_service_contract(*args,candidate_delta=delta)
        derived=result['derivations'][oc.GATEWAY]['startup_recipe']
        self.assertEqual(len(derived['source_profile']['source_hashes']),31)
        self.assertEqual(derived['cache_child_argv'],derived['gateway_argv']);self.assertNotIn('node_reference',derived)
    def test_source32_is_mandatory_only_for_exact_direct_wrapper(self):
        self.recipe['files'].pop('dist/is-main-DYSvvM1W.mjs')
        with self.assertRaisesRegex(ValueError,'REVIEWED_FILE_SET'):self.compile()
    def test_source32_changed_bytes_reject(self):
        self.recipe['files']['dist/is-main-DYSvvM1W.mjs']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_MATCH'):self.compile()
    def test_missing_node_reference_rejects(self):
        self.recipe['launcher'].pop('node_reference')
        with self.assertRaisesRegex(ValueError,'FIXED_LAUNCHER'):self.compile()
    def test_generic_or_parent_traversal_alias_rejects(self):
        for target in ('node-v24.22.0','../node-v24.21.0','/tmp/node-v24.21.0'):
            self.recipe['launcher']['node_reference']['link']['target']=target
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'NODE_REFERENCE'):self.compile()
    def test_wrong_native_hash_is_not_reference_self_equality(self):
        proof=self.recipe['launcher']['node_reference'];proof['final']['sha256']='0'*64
        proof['final']['metadata']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'RETAINED_HASH'):self.compile()
    def test_wrong_reference_inode_is_not_node_descriptor(self):
        self.recipe['launcher']['node_reference']['final']['metadata']['ino']+=1
        with self.assertRaisesRegex(ValueError,'DESCRIPTOR_BINDING'):self.compile()
    def test_wrapper_pin_does_not_grant_alternate_entry(self):
        self.recipe['launcher']['recipe']['entry_script']=self.recipe['package_root']+'/openclaw.mjs'
        with self.assertRaisesRegex(ValueError,'FIXED_EXEC_RECIPE'):self.compile()
    def test_canonical_argv_is_not_the_retained_lexical_argv(self):
        self.recipe['launcher']['recipe']['executable']=oc.DIRECT_NODE_PATH
        with self.assertRaisesRegex(ValueError,'DIRECT_ENTRY_RECIPE'):self.compile()
    def test_root_profile_cannot_carry_alias_proof(self):
        args,delta=complete_fixture();args[4]['openclaw_recipe_evidence']['launcher']['node_reference']=self.recipe['launcher']['node_reference']
        with self.assertRaisesRegex(ValueError,'FIXED_LAUNCHER'):sc.compile_service_contract(*args,candidate_delta=delta)
    def test_absolute_fixed_alias_target_allowed_with_exact_size(self):
        self.recipe['launcher']['node_reference']=node_reference_fixture(self.recipe['node'],um.NODE_VERSION_DIRECTORY)
        self.assertEqual(self.compile()['state'],'COMPLETE')
    def test_cache_or_second_bridge_role_cannot_be_added(self):
        result=self.compile();contract=result['service_role_contract']
        root_args,root_delta=complete_fixture();root=sc.compile_service_contract(*root_args,candidate_delta=root_delta)
        for name in ('compile_cache_child','bridge_child'):
            changed=copy.deepcopy(contract);roles=changed['units'][oc.GATEWAY]['roles']
            extra=copy.deepcopy(next(r for r in root['service_role_contract']['units'][oc.GATEWAY]['roles'] if r['name']==name))
            extra['identity']=copy.deepcopy(roles[0 if name=='compile_cache_child' else 1]['identity'])
            roles.append(extra)
            with self.subTest(name=name),self.assertRaises(ValueError):
                sr.validate_contract(changed,live.digest,live._path,live._role)
    def test_direct_topology_cannot_be_relabelled_root_cache(self):
        contract=self.compile()['service_role_contract'];contract['units'][oc.GATEWAY]['topology_source_sha256']=oc.SOURCE_HASHES['openclaw.mjs']
        with self.assertRaisesRegex(ValueError,'DIRECT_ENTRY_ROLE_SET'):sr.validate_contract(contract,live.digest,live._path,live._role)
    def test_quiet_or_probe_unknown_still_refused(self):
        self.recipe['quiet_bootstrap']['selected_environment']['NODE_OPTIONS']='--require=other'
        with self.assertRaisesRegex(ValueError,'QUIET_ENVIRONMENT'):self.compile()
        self.recipe['quiet_bootstrap']['selected_environment']['NODE_OPTIONS']=None
        self.recipe['node_probe']['proof']['cleanup_state']='UNKNOWN'
        with self.assertRaisesRegex(ValueError,'PROOF_NOT_VERIFIED'):self.compile()
    def test_actual_pinned_source_branches_back_direct_topology(self):
        sources=json.loads((HERE/'fixtures/openclaw-source-profile.json').read_text())['files']
        sources.update(json.loads((HERE/'fixtures/openclaw-direct-source-profile.json').read_text())['files'])
        def text(name):
            row=sources[name];raw=base64.b64decode(row['content_base64'].encode(),validate=True)
            self.assertEqual(sc.sha(raw),oc.DIRECT_SOURCE_HASHES[name]);return raw.decode()
        entry=text('dist/entry.js');respawn=text('dist/entry.respawn-3dMNRLSy.mjs');main=text('dist/is-main-DYSvvM1W.mjs')
        self.assertIn('if (platform !== \"win32\" && isForegroundGatewayRunArgv(argv)) return;',entry)
        self.assertIn('if (!isSourceCheckoutInstallRoot(params.installRoot)) return;',entry)
        self.assertIn('if (shouldSkipStartupEnvironmentRespawnForArgv(normalizedArgv, platform) || isTruthyEnvValue(env.OPENCLAW_NO_RESPAWN)) return null;',respawn)
        self.assertIn('invocation.primary === \"gateway\" && isForegroundGatewayRunArgv(argv)',respawn)
        self.assertIn('const execPath = params.execPath ?? process.execPath;',respawn)
        self.assertIn('childExecArgv.unshift(EXPERIMENTAL_WARNING_FLAG)',respawn)
        self.assertIn('argv: [...childExecArgv, ...argv.slice(1)]',respawn)
        self.assertIn('childEnv[OPENCLAW_NODE_OPTIONS_READY] = \"1\"',respawn)
        self.assertIn('detachForProcessTree: !isTerminalInteractiveRespawnArgv(argv)',respawn)
        self.assertIn('return fs.realpathSync.native(resolved);',main)
        self.assertIn('if (normalizedCurrent && normalizedArgv1 && normalizedCurrent === normalizedArgv1) return true;',main)


class DirectFamilyTests(family.SourceFamilyTests):
    # Reuse the complete census builder, not a validator mock. Remove inherited
    # root-only cases: their absence is itself checked by direct contract tests.
    fixture=staticmethod(direct_fixture)
    test_cache_child_serves_and_is_the_only_native_bridge_parent=None
    test_cache_waiting_parent_cannot_also_have_serving_title=None
    test_both_native_bridge_parents_are_refused=None
    def test_initial_raw_argv_uses_lexical_node_not_canonical(self):
        for when in ('before','after'):
            self.view['processes'][str(self.gw)][when]['argv_sha256']=sr.argv_hash(
                [oc.DIRECT_NODE_PATH,oc.DIRECT_ENTRY,'gateway','--port','18789'])
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()
    def test_extra_node_even_same_bytes_is_not_a_gateway_role(self):
        self.assign(self.gw+20000,oc.GATEWAY,'main',1,title='openclaw-gateway')
        with self.assertRaises(ValueError):self.check()
    def test_wrong_canonical_elf_identity_is_rejected(self):
        for when in ('before','after'):self.view['processes'][str(self.gw)][when]['executable']=oc.DIRECT_NODE_REFERENCE
        with self.assertRaisesRegex(ValueError,'PROCESS_ROLE'):self.check()


if __name__=='__main__':unittest.main()
