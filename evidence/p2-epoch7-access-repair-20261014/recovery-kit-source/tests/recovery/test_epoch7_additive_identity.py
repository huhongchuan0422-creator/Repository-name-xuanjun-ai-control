"""Synthetic additive config tests; real content/interpreter pins remain pending."""
import copy
import json
from pathlib import Path
import activation_control
import unittest

import epoch7_additive_identity as a
import epoch7_delta as d
import epoch7_injected_recovery as r
from test_epoch7_delta import h
from test_epoch7_injected_recovery import prepared


def additive_fixture():
    # Actual public source identity; interpreter/absence facts remain explicit
    # synthetic fixtures and never represent measured host pins.
    root=Path(activation_control.__file__).resolve().parent.parent
    manifest=(root/'deploy/integration-manifest.json').read_bytes()
    script_sha=json.loads(manifest.decode())['files'][a.SCRIPT_REL]
    assert a.raw_sha((root/a.SCRIPT_REL).read_bytes())==script_sha
    manifest_sha = a.raw_sha(manifest)
    script = '/opt/xuanjun-control-releases/integration-' + manifest_sha[:16] + '/' + a.SCRIPT_REL
    argv = a.expected_argv(script)
    unit = ('[Service]\nUser=xuanjun-callback\nGroup=xuanjun-control-db\nExecStart=' + ' '.join(argv) + '\n').encode()
    config = {'schema': 1, 'callback_uid': 1004, 'release_sha256': manifest_sha,
        'python_exe': '/usr/libexec/platform-python3.6', 'python_sha256': h('synthetic interpreter'),
        'script': script, 'script_sha256': script_sha,
        'unit_file': a.UNIT, 'unit_sha256': a.raw_sha(unit), 'argv': argv, 'cgroup': a.CGROUP}
    interpreter = {'path': config['python_exe'], 'kind': 'FILE', 'sha256': config['python_sha256'],
        'uid': 0, 'gid': 0, 'mode': 0o755, 'dev': 1, 'ino': 1, 'nlink': 1}
    absence = {'path': a.PATH, 'kind': 'ABSENT', 'parent': {'path': a.PARENT,
        'kind': 'DIRECTORY', 'uid': 0, 'gid': 0, 'mode': 0o755, 'dev': 1, 'ino': 2,
        'acl_sha256': h('synthetic parent ACL')}}
    return config, manifest, unit, interpreter, absence


class AdditiveTests(unittest.TestCase):
    def setUp(self): self.config, self.manifest, self.unit, self.interpreter, self.absence = additive_fixture()

    def compile(self):
        raw = d.canonical(self.config) + b'\n'
        return a.compile_addition(raw, a.raw_sha(raw), self.manifest, a.raw_sha(self.manifest),
                                  self.unit, self.interpreter, self.absence)

    def test_exact_nonsecret_target_and_metadata_with_provenance(self):
        x = self.compile()
        self.assertEqual(x['path'], a.PATH)
        self.assertEqual((x['after']['uid'], x['after']['gid'], x['after']['mode']), (0, 0, 0o644))
        self.assertEqual(x['provenance']['runtime_manifest_sha256'], a.raw_sha(self.manifest))
        self.assertFalse(x['actual_host_pins_verified']); self.assertFalse(x['permission_applied'])
        self.assertEqual(x['install_admission'], 'NOT_GRANTED')

    def test_missing_config_hash_cannot_generate_inferred_pins(self):
        raw = d.canonical(self.config)
        with self.assertRaisesRegex(ValueError, 'HASH_REQUIRED'):
            a.compile_addition(raw, None, self.manifest, a.raw_sha(self.manifest), self.unit,
                               self.interpreter, self.absence)

    def test_secret_or_unknown_config_key_rejected(self):
        self.config['token'] = 'synthetic'
        with self.assertRaisesRegex(ValueError, 'CONFIG_SCHEMA'): self.compile()

    def test_bool_schema_or_uid_rejected(self):
        self.config['schema'] = True
        with self.assertRaisesRegex(ValueError, 'CALLBACK_IDENTITY'): self.compile()

    def test_other_target_or_preexisting_file_not_allowed(self):
        self.absence['path'] = '/etc/other.json'
        with self.assertRaisesRegex(ValueError, 'EXACT_ABSENCE'): self.compile()
        self.absence['path'] = a.PATH; self.absence['kind'] = 'FILE'
        with self.assertRaisesRegex(ValueError, 'EXACT_ABSENCE'): self.compile()

    def test_wrong_script_release_path_rejected(self):
        self.config['script'] = '/tmp/owner_callback_server.py'
        with self.assertRaisesRegex(ValueError, 'EXACT_SCRIPT_PATH'): self.compile()

    def test_script_hash_must_be_in_candidate_manifest(self):
        self.config['script_sha256'] = h('other script')
        with self.assertRaisesRegex(ValueError, 'SCRIPT_SOURCE_BINDING'): self.compile()

    def test_unit_hash_binds_exact_rendered_bytes(self):
        self.unit += b'# changed\n'
        with self.assertRaisesRegex(ValueError, 'RENDERED_UNIT_HASH'): self.compile()

    def test_argv_must_be_full_rendered_execstart(self):
        self.config['argv'] = self.config['argv'][:-2]
        with self.assertRaisesRegex(ValueError, 'ARGV_BINDING'): self.compile()

    def test_systemd_expansion_not_interpreted_by_compiler(self):
        self.unit = self.unit.replace(b'--port', b'--port=%i')
        self.config['unit_sha256'] = a.raw_sha(self.unit)
        with self.assertRaisesRegex(ValueError, 'LITERAL_EXECSTART'): self.compile()

    def test_multiple_execstart_lines_rejected(self):
        self.unit += b'ExecStart=/bin/true\n'; self.config['unit_sha256'] = a.raw_sha(self.unit)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_UNIT_DIRECTIVE'): self.compile()

    def test_unit_user_mismatch_rejected_even_with_updated_hash(self):
        self.unit = self.unit.replace(b'User=xuanjun-callback', b'User=root')
        self.config['unit_sha256'] = a.raw_sha(self.unit)
        with self.assertRaisesRegex(ValueError, 'UNIT_IDENTITY'): self.compile()

    def test_shortened_argv_and_matching_unit_still_rejected(self):
        self.config['argv'] = self.config['argv'][:2]
        self.unit = ('[Service]\nUser=xuanjun-callback\nGroup=xuanjun-control-db\nExecStart=' +
                     ' '.join(self.config['argv']) + '\n').encode()
        self.config['unit_sha256'] = a.raw_sha(self.unit)
        with self.assertRaisesRegex(ValueError, 'ARGV_BINDING'): self.compile()

    def test_wrong_interpreter_owner_or_kind_rejected(self):
        self.interpreter['uid'] = 1004
        with self.assertRaisesRegex(ValueError, 'INTERPRETER_BINDING'): self.compile()
        self.interpreter['uid'] = 0; self.interpreter['kind'] = 'DIRECTORY'
        with self.assertRaisesRegex(ValueError, 'INTERPRETER_BINDING'): self.compile()

    def test_wrong_interpreter_bytes_rejected(self):
        self.interpreter['sha256'] = h('unmeasured')
        with self.assertRaisesRegex(ValueError, 'INTERPRETER_BINDING'): self.compile()

    def test_writable_parent_rejected(self):
        self.absence['parent']['mode'] = 0o777
        with self.assertRaisesRegex(ValueError, 'PROTECTED_EXISTING_PARENT'): self.compile()

    def test_wrong_cgroup_rejected(self):
        self.config['cgroup'] = '/system.slice/other.service'
        with self.assertRaisesRegex(ValueError, 'RELEASE_UNIT_CGROUP'): self.compile()

    def test_compiled_metadata_cannot_be_relaxed(self):
        x = self.compile(); x['after']['mode'] = 0o640
        with self.assertRaisesRegex(ValueError, 'EXACT_METADATA'):
            a.validate_compiled(x, self.config['release_sha256'])

    def test_compiled_parent_must_still_match(self):
        x = self.compile(); x['before']['parent']['uid'] = 1004
        with self.assertRaisesRegex(ValueError, 'PROTECTED_EXISTING_PARENT'):
            a.validate_compiled(x, self.config['release_sha256'])

    def test_complete_review_keeps_24_retained_plus_explicit_25th(self):
        addition = self.compile()
        s, c, ops, verifier, unused, payloads = prepared()
        c['manifest_sha256'] = self.config['release_sha256']
        c['activation']['release_sha256'] = self.config['release_sha256']
        c['targets'][a.UNIT]['sha256'] = self.config['unit_sha256']
        ops.read_additive_absence = lambda path: copy.deepcopy(self.absence)
        gate = r.RecoveryGate(s, c, d.digest(s), h('kit'), h('security'), 7000000000,
                             verifier, ops, ops.prior_provision_bytes, additive_delta=addition)
        ops.preserved = copy.deepcopy(gate.preserved)
        gate.check()
        self.assertEqual(gate.expected['retained_target_count'], 24)
        self.assertEqual(gate.expected['total_target_count'], 25)
        self.assertEqual(len(gate.delta['changes']), 24)
        self.assertEqual(gate.expected['additive_targets'][0]['path'], a.PATH)
        self.assertNotIn(a.PATH, d.TARGETS)
        self.absence['kind'] = 'FILE'
        with self.assertRaisesRegex(ValueError, 'ADDITIVE_CURRENT_ABSENCE_DRIFT'): gate.check()

    def test_additive_unit_pin_must_match_reviewed_replacement(self):
        addition = self.compile(); s, c, ops, verifier, unused, payloads = prepared()
        c['manifest_sha256'] = self.config['release_sha256']
        c['activation']['release_sha256'] = self.config['release_sha256']
        with self.assertRaisesRegex(ValueError, 'OWNER_UNIT_CANDIDATE_BINDING'):
            r.RecoveryGate(s, c, d.digest(s), h('kit'), h('security'), 7000000000,
                verifier, ops, ops.prior_provision_bytes, additive_delta=addition)


if __name__ == '__main__': unittest.main()
