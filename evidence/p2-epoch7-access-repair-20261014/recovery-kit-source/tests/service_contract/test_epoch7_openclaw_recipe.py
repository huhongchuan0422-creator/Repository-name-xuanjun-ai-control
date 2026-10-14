"""Actual official source bytes with explicitly synthetic host/probe evidence.

No UK state, installed matching, package execution or production admission is
claimed. This proves the pure compiler can complete a fully populated contract.
"""
import base64
import copy
import json
import pathlib
import unittest
HERE=pathlib.Path(__file__).resolve().parent
import epoch7_service_roles as sr
import epoch7_service_contract as sc
import epoch7_openclaw_recipe as oc
import test_epoch7_service_contract as base_tests
from test_node_sqlite_probe import fixture_attempt
from test_probe_driver import fixture as probe_fixture
import node_sqlite_probe as np


def complete_fixture():
    basic=base_tests.NginxRecipeTests();basic.setUp();base_tests.CompilerTests.add_git_facts(basic)
    args,delta=basic.args,basic.delta;compiled,facts=args[0],args[4]
    runtime=base_tests.runtime_fixture_root()
    for name in ('stage1/native_gateway_controller.py','plugins/p2-native-controller/ledger.mjs'):
        facts['source_bytes'][name]=(runtime/name).read_bytes()
    manifest=json.loads(facts['runtime_manifest_bytes'].decode());release='/opt/xuanjun-control-releases/integration-'+compiled['manifest_sha256'][:16]
    def target(path,value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':'))
        compiled['rendered_targets'][path]=raw
        compiled['runtime']['provisioning'].append({'target':path,'owner_uid':0,'group_gid':0,'mode':420,'rendered_sha256':sc.sha(raw.encode())})
        after={'kind':'FILE','sha256':sc.sha(raw.encode()),'uid':0,'gid':0,'mode':420}
        delta['changes'].append({'path':path,'operation':'REPLACE_EXACT_FILE','before':dict(after,sha256='9'*64),'after':after})
    client='/etc/xuanjun-development/p2-native-ledger-client.json';target(client,{'fixture':'synthetic client only'})
    python=facts['executables']['/usr/bin/python3'];bridge=release+'/stage1/native_ledger_bridge.py'
    target(sc.CONTROLLER,{'ledger':{'python':python['path'],'pythonSha256':python['sha256'],
        'bridge':bridge,'config':client,'files':{bridge:manifest['files']['stage1/native_ledger_bridge.py'],
            client:sc.sha(compiled['rendered_targets'][client].encode())}}})
    wrapper=b'#!/bin/sh\nexec /fixture/node /fixture/openclaw.mjs "$@"\n';wrapper_sha=sc.sha(wrapper)
    relay={'openclaw_bin':oc.LAUNCHER,'openclaw_sha256':wrapper_sha,'openclaw_owner_uid':1002,
        'gateway_home':'/home/xuanjun_dev','gateway_path':'/usr/bin:/bin','dispatcher_user':'xuanjun-dispatcher'}
    target('/etc/xuanjun-development/p2-gateway-relay.json',relay)
    policy=probe_fixture(source_root=runtime)[0]
    attempt,original_policy,observed,original_policy_pin=fixture_attempt(original_policy=policy)
    validated_probe=np.validated_proof_from_attempt(attempt,original_policy,observed,original_policy_pin)
    binding=np.binding_from_observation(observed);node=binding['node']
    native=json.loads(args[2].decode());native['gatewayIdentity'].update(exe=node['path'],sha256=node['sha256'])
    args=list(args);args[2]=json.dumps(native).encode()
    root='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
    source=json.loads((HERE/'fixtures/openclaw-source-profile.json').read_text())
    assert source['fixture_scope']=='OFFICIAL_SOURCE_BYTES_ONLY_NOT_UK_EVIDENCE'
    assert set(source['files'])==set(oc.SOURCE_HASHES)
    files={}
    for index,(name,row) in enumerate(sorted(source['files'].items())):
        raw=base64.b64decode(row['content_base64'].encode(),validate=True)
        assert sc.sha(raw)==row['sha256']==oc.SOURCE_HASHES[name]
        files[name]={'sha256':row['sha256'],'metadata':{'kind':'FILE','dev':8,'ino':1000+index,
            'uid':1002,'gid':1002,'mode':420,'nlink':1,'size':len(raw),'mtime_ns':1,'ctime_ns':1}}
    facts['openclaw_recipe_evidence']={'schema':1,'package_root':root,'files':files,'node':node,
        'launcher':{'path':oc.LAUNCHER,'sha256':wrapper_sha,'entry_realpath':root+'/openclaw.mjs',
            'recipe':{'executable':node['path'],'entry_script':root+'/openclaw.mjs','forwards_unit_arguments':True,
                'shebang':'#!/bin/sh','environment_names':[],'source_execution':'NOT_PERFORMED'}},
        'node_probe':validated_probe,
        'quiet_bootstrap':{'schema':1,'selected_environment':dict({key:None for key in oc.ENV_KEYS},HOME='/home/xuanjun_dev'),
            'config_projection':{'env_shell_enabled':False,'proxy_enabled':False,'proxy_url_present':False,'include_present':False},
            'source_bindings':{sc.UNIT_ROOT+oc.GATEWAY:sc.sha(args[3]),oc.LAUNCHER:wrapper_sha,
                '/home/xuanjun_dev/.openclaw/openclaw.json':'a'*64},
            'manager_sha256':'c'*64,'package_absence':{name:'ABSENT' for name in oc.ABSENT},
            'node_exec_argv':[],'relay_environment':{'HOME':relay['gateway_home'],'PATH':relay['gateway_path'],'LANG':'C.UTF-8'}}}
    return tuple(args),delta


class CompleteRecipeTests(unittest.TestCase):
    def setUp(self):self.args,self.delta=complete_fixture();self.facts=self.args[4]['openclaw_recipe_evidence']
    def compile(self):return sc.compile_service_contract(*self.args,candidate_delta=self.delta)
    def test_actual_official_sources_and_synthetic_host_facts_compile_complete(self):
        result=self.compile();self.assertEqual(result['state'],'COMPLETE');self.assertEqual(result['unresolved'],[])
        self.assertFalse(result['install_admission']);self.assertEqual(result['production_acceptance'],'NOT_VERIFIED')
        contract=sc.require_complete_service_contract(result)
        self.assertEqual(set(contract['service_role_contract']['units']),
            {oc.GATEWAY,oc.RELAY,'nginx.service','xuanjun-development-dispatcher.service'})
        recipe=result['derivations'][oc.GATEWAY]['startup_recipe']
        self.assertEqual(recipe['cache_child_argv'],recipe['gateway_argv'])
        self.assertEqual(recipe['relay_respawn_argv'][1],'--disable-warning=ExperimentalWarning')
        gateway=contract['service_role_contract']['units'][oc.GATEWAY]
        relay=contract['service_role_contract']['units'][oc.RELAY]
        self.assertIn(991,gateway['roles'][0]['identity']['groups']);self.assertNotIn(991,relay['roles'][1]['identity']['groups'])
        self.assertEqual(len(gateway['sources']),40)
    def test_missing_profile_cannot_leave_hold(self):
        self.args[4].pop('openclaw_recipe_evidence');self.assertEqual(self.compile()['state'],'HOLD')
    def test_concrete_observation_probe_adapter_feeds_complete_compiler(self):
        import openclaw_metadata
        policy=probe_fixture(source_root=base_tests.runtime_fixture_root())[0]
        attempt,unused,observation,unused_pin=fixture_attempt(original_policy=policy)
        # This is a partial synthetic observation for this adapter, not a full
        # host snapshot or an independently authenticated approval artifact.
        manager={'fixture':'explicit synthetic manager evidence'}
        observation['evidence']['writers']={'manager':manager}
        observation['evidence_sha256']=sc.d.digest(observation['evidence'])
        recipe=copy.deepcopy(self.facts);recipe.pop('node_probe')
        recipe['quiet_bootstrap']['manager_sha256']=sc.d.digest(manager)
        profile={'schema':1,'state':'COMPLETE_UNREVIEWED','missing_fields':[],
            'sections':{'fixture':{'state':'MEASURED_UNREVIEWED'}},'recipe_evidence':recipe}
        observation.update(openclaw_profile=profile,openclaw_profile_sha256=sc.d.digest(profile),finite_probe=attempt)
        self.args[4]['openclaw_recipe_evidence']=openclaw_metadata.recipe_from_observation(observation)
        self.assertEqual(self.compile()['state'],'COMPLETE')
        observation['finite_probe']['result']['cleanup'][0]['status']='UNKNOWN'
        with self.assertRaises(ValueError):openclaw_metadata.recipe_from_observation(observation)
    def test_installed_source_drift_is_rejected(self):
        self.facts['files']['openclaw.mjs']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_MATCH'):self.compile()
    def test_unreviewed_source_owner_or_fifo_shape_is_rejected(self):
        self.facts['files']['openclaw.mjs']['metadata']['kind']='FIFO'
        with self.assertRaisesRegex(ValueError,'SOURCE_FILE_AUTHORITY'):self.compile()
    def test_source_checkout_or_pending_package_lifecycle_is_refused(self):
        for name in oc.ABSENT:
            self.facts['quiet_bootstrap']['package_absence'][name]='PRESENT'
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'ABSENCE'):self.compile()
            self.facts['quiet_bootstrap']['package_absence'][name]='ABSENT'
    def test_preloads_and_service_mode_side_paths_are_refused(self):
        for key in ('NODE_OPTIONS','BUN_OPTIONS','OPENCLAW_SERVICE_MARKER','OPENCLAW_CONTAINER'):
            self.facts['quiet_bootstrap']['selected_environment'][key]='present'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'QUIET_ENVIRONMENT'):self.compile()
            self.facts['quiet_bootstrap']['selected_environment'][key]=None
    def test_shell_or_proxy_config_requires_other_recipe(self):
        for key in ('env_shell_enabled','proxy_enabled'):
            self.facts['quiet_bootstrap']['config_projection'][key]=True
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'QUIET_CONFIG'):self.compile()
            self.facts['quiet_bootstrap']['config_projection'][key]=False
    def test_wrapper_cache_export_breaks_clean_relay_proof(self):
        self.facts['launcher']['recipe']['environment_names']=['NODE_COMPILE_CACHE']
        with self.assertRaisesRegex(ValueError,'WRAPPER_NO_EXTRA'):self.compile()
    def test_clean_relay_has_no_additional_compile_cache_generation(self):
        # Review the pinned source without importing or executing JavaScript.
        source=json.loads((HERE/'fixtures/openclaw-source-profile.json').read_text())['files']
        def text(name):
            raw=base64.b64decode(source[name]['content_base64'].encode(),validate=True)
            self.assertEqual(sc.sha(raw),oc.SOURCE_HASHES[name]);return raw.decode()
        launcher=text('openclaw.mjs');entry=text('dist/entry.js')
        respawn=text('dist/entry.respawn-3dMNRLSy.mjs')
        self.assertIn('const currentDirectory = module.getCompileCacheDir?.();\n  if (!currentDirectory) {\n    return false;',launcher)
        self.assertIn('path.resolve(currentDirectory) === desired',launcher)
        self.assertIn('path.dirname(path.resolve(currentDirectory)) === desired',launcher)
        self.assertLess(launcher.index('respawnWithPackagedCompileCacheIfNeeded()));'),
                        launcher.index('const result = module.enableCompileCache(directory);'))
        self.assertIn('if (!isSourceCheckoutInstallRoot(params.installRoot)) return;',entry)
        self.assertIn('const startupEnv = { ...process.env };',entry)
        self.assertIn('buildCliRespawnPlan({ env: startupEnv })',entry)
        self.assertIn('childExecArgv.unshift(EXPERIMENTAL_WARNING_FLAG);',respawn)
        self.assertIn('childEnv[OPENCLAW_NODE_OPTIONS_READY] = "1";',respawn)
        # A fresh clean-env Node has no inherited cache setting. The warning
        # child either starts with none, or a scoped base/leaf already equal to
        # the desired namespace; none requires another packaged-cache child.
        env=self.facts['quiet_bootstrap']['relay_environment']
        self.assertEqual(set(env),{'HOME','PATH','LANG'})
        self.assertEqual(self.facts['quiet_bootstrap']['node_exec_argv'],[])
        def cache_respawn(current,desired,inherited):
            return bool(current) and current!=desired and not (inherited==desired and current.rsplit('/',1)[0]==desired)
        for current,inherited in ((None,None),('/cache/openclaw/version/build',None),
                                  ('/cache/openclaw/version/build/node-leaf','/cache/openclaw/version/build')):
            self.assertFalse(cache_respawn(current,'/cache/openclaw/version/build',inherited))
        roles=self.compile()['service_role_contract']['units'][oc.RELAY]['roles']
        self.assertEqual([(x['name'],x['maximum']) for x in roles],
                         [('main',1),('cli',1),('cli_respawn',1)])
    def test_effective_config_or_home_redirect_is_refused(self):
        for key in ('HOME','OPENCLAW_HOME','OPENCLAW_STATE_DIR','OPENCLAW_CONFIG_PATH'):
            old=self.facts['quiet_bootstrap']['selected_environment'][key]
            self.facts['quiet_bootstrap']['selected_environment'][key]='/other/path'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'CONFIG_PATH_SELECTION'):self.compile()
            self.facts['quiet_bootstrap']['selected_environment'][key]=old
    def test_proxy_url_without_enabled_flag_is_still_refused(self):
        config=self.facts['quiet_bootstrap']['config_projection'];config['proxy_enabled']=None;config['proxy_url_present']=True
        with self.assertRaisesRegex(ValueError,'QUIET_CONFIG'):self.compile()
        config['proxy_url_present']=False;self.facts['quiet_bootstrap']['selected_environment']['OPENCLAW_PROXY_URL']='present'
        with self.assertRaisesRegex(ValueError,'QUIET_ENVIRONMENT'):self.compile()
    def test_config_include_cannot_bypass_default_projection(self):
        self.facts['quiet_bootstrap']['config_projection']['include_present']=True
        with self.assertRaisesRegex(ValueError,'QUIET_CONFIG'):self.compile()
    def test_node_probe_unknown_or_wrong_proposal_is_not_accepted(self):
        proof=self.facts['node_probe']['proof'];proof['cleanup_state']='UNKNOWN'
        with self.assertRaisesRegex(ValueError,'PROOF_NOT_VERIFIED'):self.compile()
        proof['cleanup_state']='OBSERVED';proof['policy_sha256']='0'*64
        with self.assertRaises(ValueError):self.compile()
    def test_unsupported_node_or_nul_failure_refuses_recovery_branch(self):
        result=self.facts['node_probe']['proof']['result'];result['node_version']='22.0.0'
        with self.assertRaisesRegex(ValueError,'SUPPORTED_NODE'):self.compile()
        result['node_version']='24.21.0';result['sqlite']['text']=False
        with self.assertRaisesRegex(ValueError,'NUL_ROUNDTRIP'):self.compile()
    def test_unbound_relay_environment_is_refused(self):
        self.facts['quiet_bootstrap']['relay_environment']['NODE_OPTIONS']='--require=evil'
        with self.assertRaisesRegex(ValueError,'CLEAN_RELAY'):self.compile()
    def test_bridge_binding_drift_rejected(self):
        self.args[4]['executables']['/usr/bin/python3']['sha256']='0'*64
        with self.assertRaises(ValueError):self.compile()


if __name__=='__main__':unittest.main()
