"""Synthetic v2 pins; these never constitute measured UK proof or approval."""
import copy
import json
from pathlib import Path
import activation_control
import unittest
import epoch7_additive_identity as a
import epoch7_additive_server as server
import epoch7_delta as d
import epoch7_injected_recovery as r
from test_epoch7_additive_identity import additive_fixture
from test_epoch7_injected_recovery import prepared
from test_epoch7_delta import h


RUNTIME=Path(activation_control.__file__).resolve().parent.parent


def server_fixture():
    s, c, ops, verifier, unused, payloads = prepared()
    manifest=(RUNTIME/'deploy/integration-manifest.json').read_bytes()
    sha = a.raw_sha(manifest); c['manifest_sha256'] = sha; c['activation']['release_sha256'] = sha
    release = '/opt/xuanjun-control-releases/integration-' + sha[:16] + '/stage1'
    creator = {'pid': 1, 'uid': 0, 'gid': 0, 'exe': '/usr/lib/systemd/systemd',
        'cgroup_sha256': h('synthetic manager cgroup'), 'pid_namespace_role': 'SYSTEM_INIT_SHARED_WITH_CLIENTS'}
    endpoint = {'path': d.SOCKET, 'uid': 1003, 'gid': 1007, 'mode': 0o660}
    proof = {'schema': 1, 'purpose': 'ROOT_MANAGER_SHARED_INIT_PROOF', 'creator': creator,
        'endpoint_identity': {k: endpoint[k] for k in ('uid','gid','mode')},
        'clients': {p: {'same_pid_namespace': True, 'same_proc_namespace': True, 'readpaths_verified': True}
                    for p in server.PROFILES}, 'exclusive_delivery_reviewed': True, 'systemd_version': 239,
        'evidence_records_sha256': h('synthetic bounded proof records')}
    raw_proof = d.canonical(proof)
    units = {}
    for unit in server.UNIT_PROPERTIES:
        units[unit] = {'Id': unit, 'LoadState': 'loaded', 'NeedDaemonReload': 'no',
                       'FragmentPath': '/etc/systemd/system/' + unit, 'DropInPaths': ''}
    units[server.SOCKET_UNIT].update(Listen=d.SOCKET+' (Stream)', Accept='no', Triggers=server.SERVICE_UNIT,
        SocketUser='xuanjun-dispatcher', SocketGroup='xuanjun-ledger-client', SocketMode='0660',
        DirectoryMode='0711', RemoveOnStop='yes')
    units[server.SERVICE_UNIT].update(User='xuanjun-dispatcher', Group='xuanjun-control-db',
        ExecStart=server.expected_exec_start(release), WorkingDirectory=release, TriggeredBy=server.SOCKET_UNIT)
    sources = {creator['exe']: b'manager image', '/usr/bin/systemctl': b'systemctl image',
               release + '/ledger_service.py': (RUNTIME/'stage1/ledger_service.py').read_bytes()}
    namespace={};exec(compile((RUNTIME/'scripts/uk-integration-install.py').read_bytes(),'<pure-renderer>','exec'),namespace)
    manifest_value=json.loads(manifest.decode())
    for unit in units:
        relative='deploy/'+unit
        sources['/etc/systemd/system/'+unit]=namespace['render_identity_bytes'](relative,(RUNTIME/relative).read_bytes(),sha,manifest_value)
    config = {'schema': 2, 'trust_model': 'ROOT_MANAGER_DELIVERY_V1', 'exclusive_delivery_reviewed': True,
        'activation_binding': {k: c['activation'][k] for k in server.BINDING_KEYS},
        'creator': dict(creator, topology_evidence_sha256=a.raw_sha(raw_proof)), 'endpoint': endpoint,
        'files': {p: a.raw_sha(raw) for p, raw in sources.items()}, 'units': units}
    for path, raw in sources.items():
        if path in d.TARGETS: c['targets'][path]['sha256'] = a.raw_sha(raw); payloads[path] = raw
    review = {'review_id': 7000000001, 'approval_body_sha256': h('independent isolated review'),
              'evidence_sha256': a.raw_sha(raw_proof)}
    unused, unused2, unused3, unused4, absence = additive_fixture(); absence['path'] = server.PATH
    return config, manifest, sources, raw_proof, review, absence, (s,c,ops,verifier,payloads)


class ServerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config,self.manifest,self.sources,self.proof,self.review,self.absence,self.context = server_fixture()
    def compile(self):
        raw = d.canonical(self.config)
        return server.compile_addition(raw, a.raw_sha(raw), self.manifest, a.raw_sha(self.manifest),
            self.sources, self.proof, self.review, self.absence)

    def test_exact_v2_source_proof_and_absence_binding(self):
        value = self.compile(); server.validate_compiled(value, a.raw_sha(self.manifest))
        self.assertEqual(value['provenance']['config_schema'], 2)
        self.assertFalse(value['actual_host_pins_verified'])
        self.assertEqual(value['install_admission'], 'NOT_GRANTED')
        self.assertNotIn('boot_id', self.config)
        self.assertNotIn('config_sha256', self.config['activation_binding'])
        self.assertNotIn(server.CONFIG_PATH, self.config['files'])

    def test_actual107_source_manifest_and_runtime_validator_contract(self):
        import ledger_server_identity as runtime
        value=json.loads(self.manifest.decode())
        self.assertEqual(a.raw_sha(self.manifest),d.NEW_MANIFEST);self.assertEqual(len(value['files']),107)
        for relative,expected in value['files'].items():
            self.assertEqual(a.raw_sha((RUNTIME/relative).read_bytes()),expected)
        self.assertEqual(value['files']['stage1/ledger_server_identity.py'],server.VALIDATOR_CONTRACT_SHA256)
        self.assertEqual(runtime.validate_policy(self.config),server.validate_policy(self.config))
        result=self.compile();self.assertFalse(result['actual_host_pins_verified'])
        self.assertFalse(result['permission_applied'])
    def test_superseded_validator_pin_rejected(self):
        from unittest.mock import patch
        with patch.object(server,'VALIDATOR_CONTRACT_SHA256','19d60f4d567a0bad477b616fc427f3ba7acf38b8ee959786f20047b092ac4971'):
            with self.assertRaisesRegex(ValueError,'REVIEWED_VALIDATOR_CONTRACT'):self.compile()
    def test_compiled_validator_source_cannot_change(self):
        value=self.compile(); value['provenance']['validator_source_sha256']=h('other source')
        with self.assertRaisesRegex(ValueError,'PROVENANCE_BINDING'):
            server.validate_compiled(value,a.raw_sha(self.manifest))

    def test_old_static_schema_is_rejected(self):
        self.config['schema'] = 1
        with self.assertRaisesRegex(ValueError, 'EXACT_POLICY_REQUIRED'): self.compile()
    def test_arbitrary_root_process_is_rejected(self):
        self.config['creator']['pid'] = 200
        with self.assertRaisesRegex(ValueError, 'MEASURED_INIT'): self.compile()
    def test_missing_topology_cannot_infer_pid1(self):
        self.config['creator'].pop('topology_evidence_sha256')
        with self.assertRaisesRegex(ValueError, 'CREATOR_FIELDS'): self.compile()
    def test_private_dispatcher_bytes_not_allowed(self):
        self.config['files'][server.CONFIG_PATH] = h('private bytes')
        with self.assertRaisesRegex(ValueError, 'EXACT_FILE_PINS'): self.compile()
    def test_boot_or_inode_static_fields_rejected(self):
        self.config['endpoint']['inode'] = 99
        with self.assertRaisesRegex(ValueError, 'ENDPOINT_FIELDS'): self.compile()
    def test_unsupported_systemd_property_rejected(self):
        self.config['units'][server.SOCKET_UNIT].pop('Triggers')
        with self.assertRaisesRegex(ValueError, 'UNIT_PROPERTIES'): self.compile()
    def test_source_hash_drift_rejected(self):
        self.sources['/usr/bin/systemctl'] = b'other'
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH'): self.compile()
    def test_missing_client_proof_rejected(self):
        import json
        proof=json.loads(self.proof.decode()); proof['clients']['native']['readpaths_verified']=False
        self.proof=d.canonical(proof)
        self.config['creator']['topology_evidence_sha256']=a.raw_sha(self.proof)
        self.review['evidence_sha256']=a.raw_sha(self.proof)
        with self.assertRaisesRegex(ValueError, 'CONTEXT_UNVERIFIED'): self.compile()
    def test_unrelated_topology_review_rejected(self):
        self.review['evidence_sha256']=h('other proof')
        with self.assertRaisesRegex(ValueError, 'INDEPENDENT_TOPOLOGY_REVIEW'): self.compile()
    def test_consumed_review_not_accepted(self):
        self.review['review_id']=6170703284
        with self.assertRaisesRegex(ValueError, 'INDEPENDENT_TOPOLOGY_REVIEW'): self.compile()
    def test_other_additive_absence_rejected(self):
        self.absence['path']=a.PATH
        with self.assertRaisesRegex(ValueError, 'EXACT_ABSENCE'): self.compile()

    def test_server_target_binds_candidate_sources_and_25_total(self):
        addition=self.compile(); s,c,ops,verifier,payloads=self.context
        ops.read_additive_absence=lambda path: copy.deepcopy(self.absence)
        gate=r.RecoveryGate(s,c,d.digest(s),h('kit'),h('security'),7000000000,verifier,ops,
                           ops.prior_provision_bytes, additive_deltas=[addition])
        ops.preserved=copy.deepcopy(gate.preserved); gate.check()
        self.assertEqual(gate.expected['retained_target_count'],24)
        self.assertEqual(gate.expected['total_target_count'],25)

    def test_two_explicit_pins_make_26_without_changing_retained24(self):
        addition=self.compile(); s,c,ops,verifier,payloads=self.context
        config, unused, unit, interpreter, absence=additive_fixture()
        sha=a.raw_sha(self.manifest); config['release_sha256']=sha
        config['script_sha256']=json.loads(self.manifest.decode())['files'][a.SCRIPT_REL]
        config['script']='/opt/xuanjun-control-releases/integration-'+sha[:16]+'/'+a.SCRIPT_REL
        config['argv']=a.expected_argv(config['script'])
        unit=('[Service]\nUser=xuanjun-callback\nGroup=xuanjun-control-db\nExecStart='+' '.join(config['argv'])+'\n').encode()
        config['unit_sha256']=a.raw_sha(unit); c['targets'][a.UNIT]['sha256']=a.raw_sha(unit)
        raw=d.canonical(config)
        owner=a.compile_addition(raw,a.raw_sha(raw),self.manifest,sha,unit,interpreter,absence)
        absences={server.PATH:self.absence,a.PATH:absence}
        ops.read_additive_absence=lambda path: copy.deepcopy(absences[path])
        gate=r.RecoveryGate(s,c,d.digest(s),h('kit'),h('security'),7000000000,verifier,ops,
                           ops.prior_provision_bytes, additive_deltas=[addition,owner])
        ops.preserved=copy.deepcopy(gate.preserved);gate.check()
        self.assertEqual((gate.expected['retained_target_count'],gate.expected['total_target_count']),(24,26))
        self.assertEqual(len(gate.delta['changes']),24)

    def test_mismatched_candidate_unit_rejected(self):
        addition=self.compile(); s,c,ops,verifier,payloads=self.context
        c['targets']['/etc/systemd/system/'+server.SOCKET_UNIT]['sha256']=h('other unit')
        with self.assertRaisesRegex(ValueError,'SOURCE_BINDING'):
            r.RecoveryGate(s,c,d.digest(s),h('kit'),h('security'),7000000000,verifier,ops,
                          ops.prior_provision_bytes,additive_deltas=[addition])
