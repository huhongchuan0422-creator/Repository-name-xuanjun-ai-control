import copy
import json
import pathlib
import unittest
import epoch7_bindings as m

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT/'p2-epoch5-repair/runtime-v4-extracted/xuanjun-p2-package'

def reconciliation_fixture(plan_raw):
    """Synthetic observation for pure tests, never a measured host pin."""
    plan=json.loads(plan_raw.decode());publisher=plan['runtime']['publisher']
    row=next(r for r in plan['runtime']['provisioning'] if r['target']==m.DISPATCHER)
    reference=m.sha(m.canonical(publisher))
    observed={'schema':1,'path':'/var/lib/xuanjun-development/control.git',
        'head_commit':publisher['source_commit'],'head_tree':publisher['source_tree'],
        'publisher_reference_sha256':reference,'publisher_journal_sha256':'1'*64,
        'publisher_fingerprint_sha256':'2'*64,'git_sha256':'3'*64}
    return {'schema':1,'purpose':'DISPATCHER_RETAINED_CONTROL_HEAD',
        'old_dispatcher_sha256':row['rendered_sha256'],
        'old_source_commit':row['replacements']['@@SOURCE_COMMIT@@'],
        'publisher_reference_sha256':reference,'observation_sha256':m.sha(m.canonical(observed)),
        'observation':observed}

class BindingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_raw=(BASE/'deploy/integration-manifest.json').read_bytes()
        cls.old=json.loads(cls.old_raw.decode())
        cls.payload={p:(BASE/p).read_bytes() for p in cls.old['files']}
        cls.plan=(ROOT/'p2-epoch5-repair/compiled-plan-v4.private.json').read_bytes()
    def setUp(self):
        self.new=copy.deepcopy(self.old);self.data=dict(self.payload)
        # Deliberately labeled local fixture, never production provenance.
        self.data['stage1/native_ledger_bridge.py'] += b'\n# LOCAL_BINDING_TEST_FIXTURE\n'
        self.data['deploy/p2-native-ledger-client.json.template'] = b'{"socket_path":"/run/xuanjun-development/ledger.sock","server_identity_policy":"/etc/xuanjun-development/p2-ledger-server-identity.json"}\n'
    def raw(self):
        self.new['files']={p:m.sha(v) for p,v in self.data.items()}
        return (json.dumps(self.new,sort_keys=True,indent=2)+'\n').encode()
    def call(self, raw=None):
        return m.compile_retained_bindings(self.plan,self.old_raw,self.payload,
            self.raw() if raw is None else raw,self.data,'1'*40,'2'*40,
            control_reconciliation=reconciliation_fixture(self.plan))
    def test_all24_reproduced_and_rebound(self):
        v=self.call();self.assertEqual(len(v['rendered_targets']),24)
        self.assertEqual(v['activation_proposal']['epoch'],8)
        self.assertFalse(v['install_admission'])
        self.assertEqual(v['source_provenance'],'REQUIRES_INDEPENDENT_READBACK')
        for row in v['runtime']['provisioning']:
            self.assertEqual(row['rendered_sha256'],m.sha(v['rendered_targets'][row['target']]))
    def test_native_client_and_bridge_updated_together(self):
        v=self.call();binding=json.loads(v['rendered_targets'][m.BINDING].decode())['ledger']
        self.assertEqual(binding['files'][m.CLIENT],m.sha(v['rendered_targets'][m.CLIENT]))
        self.assertEqual(binding['files'][binding['bridge']],m.sha(self.data['stage1/native_ledger_bridge.py']))
        self.assertNotIn(m.OLD_MANIFEST[:16],binding['bridge'])
    def test_three_plugin_pins(self):
        v=self.call();p=v['runtime']['plugin']
        for a,b in [('binding_file','binding_sha256'),('ledger_client_config','ledger_client_sha256'),('gateway_relay_config','gateway_relay_sha256')]:
            self.assertEqual(p[b],m.sha(v['rendered_targets'][p[a]]))
    def test_tls_retained_and_new_candidate_path(self):
        v=self.call();a=json.loads(v['old_rendered_targets'][m.TLS].decode());b=json.loads(v['rendered_targets'][m.TLS].decode())
        a.pop('release_sha256');b.pop('release_sha256');self.assertEqual(a,b)
        self.assertTrue(v['runtime']['tls_renewal']['path'].endswith('/epoch8-tls-renewal-candidate.json'))
        self.assertEqual(v['runtime']['tls_renewal']['sha256'],m.sha(v['tls_config_bytes']))
    def test_original_bytes_and_inputs_unchanged(self):
        before=copy.deepcopy(self.data);old=copy.deepcopy(self.payload);self.call()
        self.assertEqual(before,self.data);self.assertEqual(old,self.payload)
        self.assertEqual(m.sha(self.plan),m.OLD_PLAN)
    def test_additional_stage1_helper_allowed_not_added_target(self):
        self.data['stage1/fixture_helper.py']=b'# fixture only\n';v=self.call()
        self.assertEqual(len(v['rendered_targets']),24)
        self.assertIn('REQUIRES',v['additional_identity_targets'])
    def test_no_runtime_deletion(self):
        self.data.pop('stage1/native_ledger_bridge.py')
        with self.assertRaisesRegex(ValueError,'NO_DELETIONS'):self.call()
    def test_additional_nonhelper_denied(self):
        self.data['deploy/new.service']=b'# fixture\n'
        with self.assertRaisesRegex(ValueError,'ADDITIVE_HELPER'):self.call()
    def test_old_plan_drift_rejected(self):
        self.plan+=b' '
        with self.assertRaisesRegex(ValueError,'EXACT_V4_INPUTS'):self.call()
    def test_old_manifest_drift_rejected(self):
        self.old_raw+=b' '
        with self.assertRaisesRegex(ValueError,'EXACT_V4_INPUTS'):self.call()
    def test_new_payload_hash_drift(self):
        raw=self.raw();self.data['stage1/native_ledger_bridge.py']+=b'bad'
        with self.assertRaisesRegex(ValueError,'PAYLOAD_HASH'):self.call(raw)
    def test_renderer_changed_rejected(self):
        self.data[m.RENDERER_PATH]+=b'# changed\n'
        with self.assertRaisesRegex(ValueError,'PINNED_RENDERER'):self.call()
    def test_metadata_changed_rejected(self):
        self.new['source_parent']='3'*40
        with self.assertRaisesRegex(ValueError,'MANIFEST_CONTRACT'):self.call()
    def test_controller_binary_changed_rejected(self):
        self.data['stage1/native_gateway_controller.py']+=b'# changed\n'
        with self.assertRaisesRegex(ValueError,'CONTROLLER_BINARY'):self.call()
    def test_actual_reviewed_controller_transition_preserves_ledger_identity(self):
        package=ROOT/'p2-epoch7-repair/runtime-build-101b465c/xuanjun-p2-package'
        raw=(package/'deploy/integration-manifest.json').read_bytes();manifest=json.loads(raw.decode())
        payload={name:(package/name).read_bytes() for name in manifest['files']}
        value=m.compile_retained_bindings(self.plan,self.old_raw,self.payload,raw,payload,
            '101b465ca3554bf34fef2d53d6006b96d85c4a63','3ae50b40c38d9a807876c175818299e344d53134',
            reconciliation_fixture(self.plan))
        active=value['activation_proposal'];before=json.loads(self.plan.decode())['activation_proposal']
        self.assertEqual(active['release_sha256'],m.REVIEWED_CONTROLLER_MANIFEST)
        self.assertEqual(active['binary_sha256'],m.REVIEWED_CONTROLLER_BINARY)
        for key in ('schema','ledger_uuid','generation','instance','db_path','ledger_socket'):
            self.assertEqual(active[key],before[key])
    def test_known_new_controller_with_other_manifest_rejected(self):
        package=ROOT/'p2-epoch7-repair/runtime-build-101b465c/xuanjun-p2-package'
        self.data[m.CONTROLLER_PATH]=(package/m.CONTROLLER_PATH).read_bytes()
        with self.assertRaisesRegex(ValueError,'CONTROLLER_BINARY_CHANGED_UNREVIEWED_PAIR'):self.call()
    def test_original_activation_binary_must_match_original_manifest(self):
        from unittest.mock import patch
        plan=json.loads(self.plan.decode());plan['activation_proposal']['binary_sha256']='0'*64
        self.plan=json.dumps(plan,sort_keys=True).encode()
        with patch.object(m,'OLD_PLAN',m.sha(self.plan)):
            with self.assertRaisesRegex(ValueError,'ORIGINAL_CONTROLLER_MANIFEST_BINDING'):self.call()
    def test_exact_new_actual_controller_pair_and_immutable_ledger_ids(self):
        new_root=ROOT/'p2-epoch7-repair/runtime-build-101b465c/xuanjun-p2-package'
        raw=(new_root/'deploy/integration-manifest.json').read_bytes()
        new=json.loads(raw.decode());payload={path:(new_root/path).read_bytes() for path in new['files']}
        value=m.compile_retained_bindings(self.plan,self.old_raw,self.payload,raw,payload,
            '101b465ca3554bf34fef2d53d6006b96d85c4a63','3ae50b40c38d9a807876c175818299e344d53134',
            reconciliation_fixture(self.plan))
        active=value['activation_proposal'];old=json.loads(self.plan.decode())['activation_proposal']
        self.assertEqual((active['release_sha256'],active['binary_sha256']),
            (m.REVIEWED_CONTROLLER_MANIFEST,m.REVIEWED_CONTROLLER_BINARY))
        for key in ('schema','ledger_uuid','generation','instance','db_path','ledger_socket'):
            self.assertEqual(active[key],old[key])
        self.assertNotEqual(active['binary_sha256'],old['binary_sha256'])
    def test_controller_original_binding_and_pair_negatives(self):
        active=json.loads(self.plan.decode())['activation_proposal']
        new=copy.deepcopy(self.old);new['files'][m.CONTROLLER_PATH]=m.REVIEWED_CONTROLLER_BINARY
        bad=copy.deepcopy(active);bad['binary_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ORIGINAL_CONTROLLER_MANIFEST_BINDING'):
            m.bind_controller_binary(bad,self.old,new,m.REVIEWED_CONTROLLER_MANIFEST)
        for manifest,binary in (('1'*64,m.REVIEWED_CONTROLLER_BINARY),
                (m.REVIEWED_CONTROLLER_MANIFEST,'2'*64),
                (m.REVIEWED_CONTROLLER_MANIFEST,active['binary_sha256'])):
            new['files'][m.CONTROLLER_PATH]=binary
            with self.assertRaisesRegex(ValueError,'CONTROLLER_BINARY_CHANGED_UNREVIEWED_PAIR'):
                m.bind_controller_binary(active,self.old,new,manifest)
    def test_tls_scope_expansion_rejected(self):
        path=next(r['source'] for r in json.loads(self.plan.decode())['runtime']['provisioning'] if r['target']==m.TLS)
        self.data[path]=self.data[path].replace(b'"schema":1',b'"schema":2')
        with self.assertRaisesRegex(ValueError,'TLS_RETENTION_SCOPE'):self.call()
    def test_unknown_token_rejected(self):
        self.data['deploy/p2-native-ledger-client.json.template']+=b'@@UNKNOWN@@'
        with self.assertRaisesRegex(ValueError,'UNRESOLVED_TOKEN'):self.call()
    def test_stale_release_rejected(self):
        self.data['deploy/p2-native-ledger-client.json.template']+=m.OLD_MANIFEST.encode()
        with self.assertRaisesRegex(ValueError,'STALE_RELEASE'):self.call()
    def test_missing_source_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_IDENTIFIERS'):
            m.compile_retained_bindings(self.plan,self.old_raw,self.payload,self.raw(),self.data,None,'2'*40)
    def test_actual_retained_mismatch_requires_explicit_reconciliation(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_CONTROL_HEAD_RECONCILIATION_REQUIRED'):
            m.compile_retained_bindings(self.plan,self.old_raw,self.payload,self.raw(),self.data,'1'*40,'2'*40)
    def test_package_and_retained_task_source_are_distinct(self):
        value=self.call();source=json.loads(value['rendered_targets'][m.DISPATCHER].decode())['source_commit']
        self.assertEqual(source,value['runtime']['publisher']['source_commit'])
        self.assertNotEqual(source,value['source_commit'])
        self.assertEqual(value['source_commit'],'1'*40)
        self.assertEqual(value['runtime']['publisher'],json.loads(self.plan.decode())['runtime']['publisher'])
        self.assertEqual(value['control_repository_reconciliation'],reconciliation_fixture(self.plan))
    def test_reconciliation_wrong_old_dispatcher_hash_denied(self):
        proof=reconciliation_fixture(self.plan);proof['old_dispatcher_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CONTROL_OLD_BINDINGS'):
            m.compile_retained_bindings(self.plan,self.old_raw,self.payload,self.raw(),self.data,'1'*40,'2'*40,proof)
    def test_observed_nonpublisher_head_denied_even_with_rehashed_proof(self):
        proof=reconciliation_fixture(self.plan);proof['observation']['head_commit']='4'*40
        proof['observation_sha256']=m.sha(m.canonical(proof['observation']))
        with self.assertRaisesRegex(ValueError,'CONTROL_RETAINED_HEAD_MISMATCH'):
            m.compile_retained_bindings(self.plan,self.old_raw,self.payload,self.raw(),self.data,'1'*40,'2'*40,proof)
    def test_proof_hash_drift_denied(self):
        proof=reconciliation_fixture(self.plan);proof['observation']['git_sha256']='4'*64
        with self.assertRaisesRegex(ValueError,'CONTROL_OBSERVATION_DIGEST'):
            m.compile_retained_bindings(self.plan,self.old_raw,self.payload,self.raw(),self.data,'1'*40,'2'*40,proof)
    def test_matching_retained_baseline_is_preserved_without_correction(self):
        publisher=json.loads(self.plan.decode())['runtime']['publisher']
        raw=json.dumps({'source_commit':publisher['source_commit']}).encode()
        self.assertEqual(m.reconcile_control_source(raw,publisher,None),(publisher['source_commit'],None))
    def test_genuine_load_config_accepts_retained_head_after_explicit_correction(self):
        import importlib.util
        location=ROOT/'p2-epoch7-repair/isolated-probe-candidate/audit_installation_hazards.py'
        spec=importlib.util.spec_from_file_location('actual_config_loader_audit',str(location))
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        value=self.call();raw=value['rendered_targets'][m.DISPATCHER]
        retained=value['runtime']['publisher']['source_commit']
        self.assertEqual(audit.source_loader(raw,retained)[0],'ACCEPTED')
        wrong=json.loads(raw.decode());wrong['source_commit']=value['source_commit']
        self.assertEqual(audit.source_loader(json.dumps(wrong).encode(),retained)[0],
            'control source HEAD does not match approved commit')


class NativeSidefileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): BindingsTests.setUpClass.__func__(cls)
    setUp = BindingsTests.setUp
    raw = BindingsTests.raw
    call = BindingsTests.call
    def fixture(self):
        from unittest.mock import patch
        v=self.call();ledger=copy.deepcopy(json.loads(v['old_rendered_targets'][m.BINDING].decode())['ledger'])
        previous=ledger['bridge'];retained='/opt/xuanjun-control-releases/integration-'+m.RETAINED_NATIVE_RELEASE[:16]+'/stage1/native_ledger_bridge.py'
        ledger['bridge']=retained;ledger['files'][retained]=ledger['files'].pop(previous)
        raw=(json.dumps({'ledger':ledger,'gatewayIdentity':{'fixture':'PRIVATE_UNCHANGED'}},sort_keys=True)+'\n').encode()
        return v,raw,ledger['files'][retained],ledger['files'][m.CLIENT],patch.object(m,'RETAINED_NATIVE_SHA',m.sha(raw))
    def test_native_retained_gateway_identity_preserved(self):
        v,raw,b,c,p=self.fixture()
        with p: after=m.native_sidefile_delta(raw,v,b,c)
        a=json.loads(after.decode());self.assertEqual(a['gatewayIdentity'],{'fixture':'PRIVATE_UNCHANGED'})
        self.assertEqual(a['ledger'],json.loads(v['rendered_targets'][m.BINDING].decode())['ledger'])
    def test_native_wrong_before_hash_rejected(self):
        v,raw,b,c,p=self.fixture()
        with self.assertRaisesRegex(ValueError,'NATIVE_RETAINED_BYTES'):m.native_sidefile_delta(raw,v,b,c)
    def test_native_before_file_pin_drift_rejected(self):
        v,raw,b,c,p=self.fixture()
        with p:
            with self.assertRaisesRegex(ValueError,'NATIVE_OLD_FILE_PINS'):m.native_sidefile_delta(raw,v,'0'*64,c)
    def test_native_interpreter_change_rejected(self):
        v,raw,b,c,p=self.fixture();payload=json.loads(v['rendered_targets'][m.BINDING].decode());payload['ledger']['python']='/bin/other'
        v['rendered_targets'][m.BINDING]=json.dumps(payload).encode()
        with p:
            with self.assertRaisesRegex(ValueError,'NATIVE_COMPILED_TARGET_DRIFT'):m.native_sidefile_delta(raw,v,b,c)

if __name__=='__main__':unittest.main()
