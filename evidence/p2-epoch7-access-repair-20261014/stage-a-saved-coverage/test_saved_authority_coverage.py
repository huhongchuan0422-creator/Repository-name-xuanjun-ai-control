"""Focused reconstruction tests. No actual full private observation is available.

synthetic_full_observation is intentionally a mapper-only synthetic fixture,
NOT a genuine full-validator fixture. actual_public_subset_summary is a distinct
TEST-ONLY adapter and never calls or feeds summarize_saved_authority.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('saved_authority_coverage', str(HERE/'saved_authority_coverage.py'))
a = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(a)

ACTUAL_PACKET = pathlib.Path(os.environ.get('STAGE_A_ACTUAL_PACKET', str(
    HERE.parent/'baseline/evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7-actual-20261015/packet.json')))
ACTUAL_PACKET_SHA256 = '45b832dce9577b49e6ee718f1637862eebd775c6c10f87d9150ed0a87476fdf7'


def synthetic_meta(index, size=0, gid=0):
    return {'uid': 0, 'gid': gid, 'mode': 0o755, 'dev': 1, 'ino': index,
            'nlink': 2, 'size': size, 'mtime_ns': 1000, 'ctime_ns': 1000}


def rehash(value):
    value['unit_metadata_sha256'] = a._hash(value['unit_metadata'])
    value['policy_sha256'] = a._hash(value['policy'])
    return value


def synthetic_full_observation():
    """Fabricated mapper input. This never represents actual raw observation."""
    inventory = {}
    for unit in a.DROPIN_UNITS:
        inventory[unit] = {base+'/'+unit+'.d': {'present': False, 'files': {}}
                           for base in a.DROPIN_ROOTS}
    nginx = 'nginx.service'
    for base in (a.DROPIN_ROOTS[0], a.DROPIN_ROOTS[2]):
        inventory[nginx][base+'/'+nginx+'.d']['present'] = True
    gateway = 'xuanjun-uk-openclaw.service'
    root = a.DROPIN_ROOTS[0]+'/'+gateway+'.d'
    raw = b'[Service]\nSupplementaryGroups=synthetic\n'
    meta = synthetic_meta(99, len(raw))
    meta.update(mode=0o644, nlink=1, kind='FILE', sha256=a.digest(raw))
    inventory[gateway][root] = {'present': True, 'files': {
        root+'/20-synthetic.conf': {'sha256': a.digest(raw), 'metadata': meta,
        'public_service_fields': {'Type': [], 'User': [], 'Group': [],
                                  'SupplementaryGroups': ['synthetic']}}}}
    dispatcher = 'xuanjun-development-dispatcher.service'
    manager = {'synthetic_marker': 'NOT_ACTUAL_HOST_DATA'}
    tool_sha = a.digest(b'synthetic-systemctl')
    late = {'unit': dispatcher, 'collector_path_used': False,
        'resolution': {'command': 'git', 'path_environment': '/usr/bin', 'entries': [
            {'directory': '/usr/bin', 'uid': 0, 'gid': 0, 'mode': 0o755,
             'dev': 1, 'ino': 700, 'git': {'path': '/usr/bin/git',
                    'sha256': a.digest(b'synthetic-git'), 'dev': 1, 'ino': 701}}]},
        'provenance': {'source': 'SYSTEM_MANAGER_CHILD_ENVIRONMENT',
            'systemctl_sha256': tool_sha, 'manager_sha256': a._hash(manager),
            'upstream_version': '239', 'distro_matching_build': 'NOT_VERIFIED',
            'unit_sha256': a.digest(b'synthetic-unit'),
            'dropins_sha256': a._hash(inventory[dispatcher]),
            'public_unit_environment': {'environment_names': [],
                'path_overrides': 'PROVEN_ABSENT_IN_SUPPORTED_SYNTAX'}}}
    boot = {'units': sorted(a.BOOT_UNITS), 'roots': {}, 'unsupported_roots': [],
            'restored_enablement': 'NOT_INFERRED',
            'runtime_alias_semantics': 'REQUIRES_SYSTEMD239_REVIEW'}
    policy_dirs = {}
    for root_index, base in enumerate(a.DROPIN_ROOTS):
        dirs = {}
        for path in a._ancestors(base):
            policy_dirs[path] = {'uid': 0, 'gid': 0, 'mode': 0o755}
        dirs[base] = {'metadata': synthetic_meta(100+root_index), 'entry_count': 2,
                      'inventory_sha256': a.digest(b'synthetic-base-listing')}
        for unit in a.DROPIN_UNITS:
            path = base+'/'+unit+'.d'
            if inventory[unit][path]['present']:
                policy_dirs[path] = {'uid': 0, 'gid': 0, 'mode': 0o755}
                dirs[path] = {'metadata': synthetic_meta(200+root_index),
                    'entry_count': len(inventory[unit][path]['files']),
                    'inventory_sha256': a.digest(('synthetic-listing-'+path).encode())}
        boot['roots'][base] = {'present': True, 'directories': dirs, 'links': [],
            'selected_nonlinks': {}, 'scan_scope': 'BOUNDED_RECURSIVE_NOFOLLOW',
            'all_link_inventory_sha256': a.digest(b'synthetic-no-links')}
    for base in a.BOOT_ROOTS[3:]:
        boot['roots'][base] = {'present': False, 'directories': {}, 'links': []}
    sections = {name: {'state': 'MEASURED_UNREVIEWED', 'evidence': {}}
                for name in a.UNIT_SECTIONS}
    sections['dropins']['evidence'] = {'units': inventory, 'unsupported': [],
                                     'raw_unit_bytes_returned': False}
    sections['command_resolutions']['evidence'] = late
    sections['boot_links']['evidence'] = boot
    metadata = {'schema': 1, 'kind': 'PRIVATE_UNIT_FACTS_UNREVIEWED',
        'state': 'COMPLETE_UNREVIEWED', 'sections': sections, 'unsupported_sections': [],
        'independent_acceptance': 'PENDING', 'install_admission': 'NOT_GRANTED'}
    value = {'schema': 1, 'kind': 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
        'independent_acceptance': 'PENDING', 'install_admission': 'NOT_GRANTED',
        'unit_metadata': metadata, 'policy': {'directories': policy_dirs,
            'executables': {'systemctl': {'sha256': tool_sha}}},
        'evidence': {'writers': {'manager': manager}},
        'fixture_class': 'SYNTHETIC_MAPPER_ONLY_NOT_FULL_VALIDATOR_INPUT'}
    return rehash(value)


def actual_public_subset_summary(packet):
    """TEST ONLY. Validate actual public inventory, without inventing full input."""
    saved = packet['saved_unit_dropins']
    a._saved_dropin_section(saved['dropins_section'])
    inventory = saved['dropins_section']['evidence']['units']
    a._saved_latecheck_section(saved['latecheck_section'], inventory)
    rows = [item for unit in inventory.values() for item in unit.values()]
    return {'kind': 'ACTUAL_EXPORTED_SUBSET_ONLY', 'scope_count': len(rows),
            'present_count': sum(item['present'] is True for item in rows),
            'absent_count': sum(item['present'] is False for item in rows),
            'empty_present_count': sum(item['present'] and not item['files'] for item in rows),
            'file_count': sum(len(item['files']) for item in rows),
            'full_private_observation': 'NOT_AVAILABLE',
            'boot_directory_records': a.MISSING, 'policy_ancestor_records': a.MISSING,
            'source_chain_validation': 'NOT_ASSESSED', 'topology_approval': 'NOT_GRANTED'}


class SavedAuthorityCoverageTests(unittest.TestCase):
    def setUp(self):
        self.v = synthetic_full_observation()
        self.sections = self.v['unit_metadata']['sections']
        self.inventory = self.sections['dropins']['evidence']['units']
        self.boot = self.sections['boot_links']['evidence']
        self.policy = self.v['policy']['directories']
        self.base = a.DROPIN_ROOTS[0]
        self.unit = 'xuanjun-uk-openclaw.service'
        self.root = self.base+'/'+self.unit+'.d'
        self.file = next(iter(self.inventory[self.unit][self.root]['files'].values()))

    def result(self):
        return a.summarize_saved_authority(rehash(self.v))

    def reject(self, label=None):
        with self.assertRaises(ValueError) as caught:
            self.result()
        self.assertRegex(str(caught.exception), r'^SAVED_AUTHORITY_[A-Z0-9_]+$')
        if label:
            self.assertIn(label, str(caught.exception))

    def test_synthetic_exact_33_and_no_approval(self):
        result = self.result()
        self.assertEqual(result['counts'], {'unit_count': 11, 'root_count': 3,
            'scope_count': 33, 'present_count': 3, 'absent_count': 30,
            'empty_present_count': 2, 'nonempty_present_count': 1, 'file_count': 1})
        self.assertEqual(len(result['rows']), 33)
        self.assertEqual(result['status'], 'MAPPED_UNAPPROVED')
        for field in ('topology_approval',):
            self.assertEqual(result[field], 'NOT_GRANTED')
        self.assertEqual(result['source_chain_validation'], 'CALLER_REQUIRED')

    def test_input_unchanged(self):
        before = a.canonical(self.v)
        self.result()
        self.assertEqual(a.canonical(self.v), before)

    def test_deterministic(self):
        self.assertEqual(a.canonical(self.result()), a.canonical(self.result()))

    def test_fixed_public_bound(self):
        self.assertLessEqual(len(a.canonical(self.result())), 131072)

    def test_output_excludes_private_fields(self):
        text = a.canonical(self.result()).decode()
        for forbidden in ('/etc/', '/run/', '/usr/', '.service', '.socket', 'synthetic',
                          '"uid"', '"gid"', '"mode"', '"ino"', '"dev"',
                          '"mtime_ns"', '"ctime_ns"', 'SupplementaryGroups'):
            self.assertNotIn(forbidden, text)

    def test_private_canary_not_exported(self):
        self.v['private_buffers'] = ['SECRET_PRIVATE_CANARY/path/token']
        self.assertNotIn('SECRET_PRIVATE_CANARY', a.canonical(self.result()).decode())

    def test_source_guarantees_do_not_claim_saved_raw_values(self):
        layers = self.result()['evidence_layers']
        self.assertEqual(layers['fd_path_object_consistency'], a.SOURCE)
        self.assertEqual(layers['per_check_ancestor_fd_dev_ino_records'], a.MISSING)
        self.assertEqual(layers['dropin_to_boot_object_identity_join'], a.MISSING)

    def test_original_failure_preserved(self):
        self.assertEqual(self.result()['historical_failure'], 'PRESERVE_ORIGINAL_HOLD')
        self.assertEqual(self.result()['fresh_collection'], 'NOT_RUN')

    def test_outer_kind_alone_insufficient(self):
        with self.assertRaises(ValueError):
            a.summarize_saved_authority({'kind': 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED'})

    def test_public_subset_not_full_input(self):
        with self.assertRaises(ValueError):
            a.summarize_saved_authority({'saved_unit_dropins': self.sections['dropins']})

    def test_outer_hold_rejected(self):
        self.v['kind'] = 'EPOCH7_OBSERVATION_ONLY_HOLD'; self.reject()

    def test_metadata_incomplete(self):
        self.v['unit_metadata']['state'] = 'INCOMPLETE'; self.reject()

    def test_unknown_section_rejected(self):
        self.sections['unit_nss']['state'] = 'UNKNOWN'; self.reject()

    def test_missing_metadata_section(self):
        del self.sections['online_cpus']; self.reject()

    def test_extra_metadata_section(self):
        self.sections['PRIVATE_CANARY'] = {}; self.reject()

    def test_metadata_digest_mismatch(self):
        self.v['unit_metadata_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'UNIT_METADATA_DIGEST'):
            a.summarize_saved_authority(self.v)

    def test_policy_digest_mismatch(self):
        self.v['policy_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'POLICY_DIGEST'):
            a.summarize_saved_authority(self.v)

    def test_missing_unit(self):
        del self.inventory[self.unit]; self.reject()

    def test_extra_unit(self):
        self.inventory['SECRET.service'] = {}; self.reject()

    def test_missing_root_not_absence(self):
        del self.inventory[self.unit][self.root]; self.reject()

    def test_extra_root(self):
        self.inventory[self.unit]['/SECRET'] = {'present': False, 'files': {}}; self.reject()

    def test_unknown_presence(self):
        self.inventory[self.unit][self.root]['present'] = None; self.reject()

    def test_integer_presence(self):
        self.inventory[self.unit][self.root]['present'] = 1; self.reject()

    def test_absent_with_files(self):
        self.inventory[self.unit][self.root]['present'] = False; self.reject()

    def test_unknown_inventory_row(self):
        self.inventory[self.unit][self.root]['state'] = 'UNKNOWN'; self.reject()

    def test_socket_content_rejected(self):
        unit = a.SOCKET_UNITS[0]; root = self.base+'/'+unit+'.d'
        self.inventory[unit][root] = {'present': True, 'files': {
            root+'/20-synthetic.conf': copy.deepcopy(self.file)}}
        self.reject('SOCKET_CONTENT')

    def test_unknown_file_fields(self):
        self.file['reason'] = 'SECRET_PRIVATE_CANARY'; self.reject()

    def test_file_hash_mismatch(self):
        self.file['sha256'] = '0'*64; self.reject()

    def test_file_uid_rejected(self):
        self.file['metadata']['uid'] = 1; self.reject()

    def test_file_gid_rejected(self):
        self.file['metadata']['gid'] = 1; self.reject()

    def test_file_hardlink_rejected(self):
        self.file['metadata']['nlink'] = 2; self.reject()

    def test_file_writable_rejected(self):
        self.file['metadata']['mode'] = 0o666; self.reject()

    def test_file_special_mode_rejected(self):
        self.file['metadata']['mode'] = 0o4644; self.reject()

    def test_file_symlink_kind_rejected(self):
        self.file['metadata']['kind'] = 'LINK'; self.reject()

    def test_file_size_bound(self):
        self.file['metadata']['size'] = 65537; self.reject()

    def test_file_outside_root(self):
        self.inventory[self.unit][self.root]['files'] = {'/SECRET.conf': self.file}; self.reject()

    def test_file_nested_path(self):
        self.inventory[self.unit][self.root]['files'] = {self.root+'/nested/SECRET.conf': self.file}; self.reject()

    def test_latecheck_unknown(self):
        self.sections['command_resolutions']['state'] = 'UNKNOWN'; self.reject()

    def test_latecheck_hash_mismatch(self):
        self.sections['command_resolutions']['evidence']['provenance']['dropins_sha256'] = '0'*64
        self.reject('LATECHECK_DROPIN_BINDING')

    def test_latecheck_manager_mismatch(self):
        self.v['evidence']['writers']['manager']['changed'] = True; self.reject()

    def test_latecheck_tool_mismatch(self):
        self.v['policy']['executables']['systemctl']['sha256'] = '0'*64; self.reject()

    def test_latecheck_private_path_not_echoed(self):
        self.sections['command_resolutions']['evidence']['resolution']['path_environment'] = '/SECRET'
        self.reject()

    def test_missing_boot_root_explicit_not_retained(self):
        del self.boot['roots'][self.base]
        result = self.result()
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['base_roots'][0]['later_directory_record']['evidence'], a.MISSING)
        self.assertEqual(result['evidence_layers']['saved_policy_ancestor_authority'], a.SAVED)

    def test_boot_unknown_rejected(self):
        self.sections['boot_links']['state'] = 'UNKNOWN'; self.reject()

    def test_optional_boot_unknown_row_rejected(self):
        self.boot['roots'][a.BOOT_ROOTS[3]] = {'state': 'UNKNOWN', 'reason': 'SECRET'}
        self.reject()

    def test_optional_boot_absent_content_rejected(self):
        self.boot['roots'][a.BOOT_ROOTS[3]]['links'] = ['SECRET']; self.reject()

    def test_optional_boot_missing_explicit_not_retained(self):
        del self.boot['roots'][a.BOOT_ROOTS[3]]
        result = self.result()
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['scan_roots'][3]['evidence'], a.MISSING)

    def test_required_base_absent_rejected(self):
        self.boot['roots'][self.base] = {'present': False, 'directories': {}, 'links': []}
        self.reject()

    def test_missing_later_directory_is_hold(self):
        del self.boot['roots'][self.base]['directories'][self.root]
        result = self.result()
        self.assertEqual(result['status'], 'HOLD')
        row = next(r for r in result['rows'] if r['unit_index'] == sorted(a.DROPIN_UNITS).index(self.unit)
                   and r['root_index'] == 0)
        self.assertEqual(row['later_directory_record']['evidence'], a.MISSING)

    def test_missing_policy_ancestor_is_hold(self):
        del self.policy['/etc']
        result = self.result()
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['base_roots'][0]['policy_ancestors'][1]['evidence'], a.MISSING)
        self.assertEqual(result['evidence_layers']['saved_policy_ancestor_authority'], a.MISSING)

    def test_missing_policy_leaf_is_hold(self):
        del self.policy[self.root]
        self.assertEqual(self.result()['status'], 'HOLD')

    def test_boot_policy_uid_mismatch(self):
        self.boot['roots'][self.base]['directories'][self.root]['metadata']['uid'] = 1; self.reject()

    def test_boot_policy_gid_mismatch(self):
        self.boot['roots'][self.base]['directories'][self.root]['metadata']['gid'] = 17
        self.reject('BOOT_POLICY_AUTHORITY_MISMATCH')

    def test_boot_policy_mode_mismatch(self):
        self.boot['roots'][self.base]['directories'][self.root]['metadata']['mode'] = 0o750
        self.reject('BOOT_POLICY_AUTHORITY_MISMATCH')

    def test_nonzero_directory_gid_allowed_when_agrees(self):
        self.policy[self.root]['gid'] = 17
        self.boot['roots'][self.base]['directories'][self.root]['metadata']['gid'] = 17
        self.assertEqual(self.result()['status'], 'MAPPED_UNAPPROVED')

    def test_policy_writable_directory_rejected(self):
        self.policy[self.root]['mode'] = 0o777; self.reject()

    def test_policy_extra_field_rejected(self):
        self.policy[self.root]['private_key'] = 'SECRET'; self.reject()

    def test_boot_file_count_mismatch(self):
        self.boot['roots'][self.base]['directories'][self.root]['entry_count'] = 2; self.reject()

    def test_absent_inventory_with_present_boot_directory(self):
        unit = a.SOCKET_UNITS[0]; path = self.base+'/'+unit+'.d'
        self.boot['roots'][self.base]['directories'][path] = copy.deepcopy(
            self.boot['roots'][self.base]['directories'][self.root])
        self.reject('PRESENCE_MISMATCH')

    def test_directory_raw_type_not_claimed(self):
        row = self.result()['base_roots'][0]['later_directory_record']
        self.assertEqual(row['object_type_check'], a.SOURCE)

    def test_different_boot_inode_does_not_claim_join(self):
        self.boot['roots'][self.base]['directories'][self.root]['metadata']['ino'] = 999999
        result = self.result()
        self.assertEqual(result['evidence_layers']['dropin_to_boot_object_identity_join'], a.MISSING)
        self.assertEqual(result['status'], 'MAPPED_UNAPPROVED')

    def test_non_finite_value_rejected_without_echo(self):
        self.file['metadata']['size'] = float('nan')
        with self.assertRaises(ValueError) as caught:
            a.summarize_saved_authority(self.v)
        self.assertRegex(str(caught.exception), '^SAVED_AUTHORITY_[A-Z0-9_]+$')

    def test_output_cap_enforced(self):
        old = a.MAX_OUTPUT_BYTES
        try:
            a.MAX_OUTPUT_BYTES = 1
            self.reject('OUTPUT_BOUND')
        finally:
            a.MAX_OUTPUT_BYTES = old

    def test_pure_import_scope(self):
        tree = ast.parse((HERE/'saved_authority_coverage.py').read_text())
        imports = [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
        self.assertEqual(set(imports), {'hashlib', 'json', 're'})
        self.assertFalse(any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertFalse(names.intersection({'open', 'eval', 'exec', '__import__'}))

    def test_actual_subset_truthful_inventory(self):
        raw = ACTUAL_PACKET.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ACTUAL_PACKET_SHA256)
        packet = json.loads(raw.decode('utf-8'))
        result = actual_public_subset_summary(packet)
        self.assertEqual((result['scope_count'], result['absent_count'], result['present_count'],
                          result['empty_present_count'], result['file_count']), (33, 30, 3, 2, 1))
        self.assertEqual(result['full_private_observation'], 'NOT_AVAILABLE')
        self.assertEqual(result['boot_directory_records'], a.MISSING)
        self.assertEqual(result['policy_ancestor_records'], a.MISSING)
        self.assertEqual(result['topology_approval'], 'NOT_GRANTED')
        with self.assertRaises(ValueError):
            a.summarize_saved_authority(packet)

    def test_actual_subset_expected_nginx_openclaw_socket_shape(self):
        packet = json.loads(ACTUAL_PACKET.read_text())
        inventory = packet['saved_unit_dropins']['dropins_section']['evidence']['units']
        nginx = inventory['nginx.service']
        self.assertEqual([nginx[base+'/nginx.service.d']['present'] for base in a.DROPIN_ROOTS],
                         [True, False, True])
        self.assertTrue(all(not row['files'] for row in nginx.values()))
        gateway = inventory['xuanjun-uk-openclaw.service']
        self.assertEqual(sum(len(row['files']) for row in gateway.values()), 1)
        for unit in a.SOCKET_UNITS:
            self.assertTrue(all(not row['files'] for row in inventory[unit].values()))


if __name__ == '__main__':
    unittest.main()
