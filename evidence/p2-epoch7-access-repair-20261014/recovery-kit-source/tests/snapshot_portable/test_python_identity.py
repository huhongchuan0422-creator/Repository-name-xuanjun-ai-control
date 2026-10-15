"""Pure Python-pair regressions using the recorded metadata-only Owner result.

No host reads, package queries, interpreter execution, or authority bypasses.
Fixture stamps are the recorded report values; they are not a live observation.
"""
import ast
import copy
import hashlib
import inspect
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import epoch7_python_identity as p


def sample_fixture():
    row = {'kind': 'FILE', 'uid': 0, 'gid': 0, 'mode': 0o755, 'dev': 64771,
        'ino': 1060429, 'nlink': 2, 'size': 15352,
        'mtime_ns': 1733905245000000000, 'ctime_ns': 1751181288018979029,
        'sha256': p.RETAINED_SHA256, 'access_acl': False, 'default_acl': False,
        'capability': False, 'elf_header': True}
    directories = {}
    for path, inode, mode, links, mtime, ctime in (
            ('/', 2, 0o555, 18, 1791903687733891019, 1791903687733891019),
            ('/usr', 1046530, 0o755, 12, 1751181232646489376, 1751181232646489376),
            ('/usr/libexec', 1047702, 0o755, 32, 1791615135886159394, 1791615135886159394)):
        directories[path] = {'kind': 'DIRECTORY', 'uid': 0, 'gid': 0, 'mode': mode,
            'dev': 64771, 'ino': inode, 'nlink': links, 'size': 4096,
            'mtime_ns': mtime, 'ctime_ns': ctime,
            'access_acl': False, 'default_acl': False, 'capability': False}
    return {'files': {path: dict(row) for path in p.PYTHON_PATHS}, 'ancestors': directories}


def proof_fixture():
    sample = sample_fixture()
    return p.build_pair_proof(sample, copy.deepcopy(sample), p.package_claim())


class PythonIdentityTests(unittest.TestCase):
    def setUp(self):
        self.sample = sample_fixture()

    def both(self, key, value):
        for row in self.sample['files'].values(): row[key] = value

    def test_recorded_report_projection_and_stable_reread(self):
        proof = p.build_pair_proof(self.sample, copy.deepcopy(self.sample), p.package_claim())
        self.assertEqual(set(proof), set(p.PROOF_FIELDS))
        self.assertEqual(p.validate_pair_proof(proof), proof)
        self.assertEqual(p.validate_pair_reread(proof, self.sample, copy.deepcopy(self.sample)), proof)
        self.assertEqual(proof['package_signature_authenticity'], 'NOT_VERIFIED')

    def test_owner_report_and_package_claim_pins_are_exact(self):
        self.assertEqual(p.OWNER_REPORT_SHA256,
            '88cc60f8c3bc465c4025eeda297f98a0b00d5ca5e0a80d3266e52e00f997e2f3')
        raw = json.dumps(p.package_claim(), sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), p.PACKAGE_CLAIM_SHA256)
        self.assertEqual(p.package_claim()['package']['file_digest_algorithm'], 8)

    def test_package_tags_are_not_live_inode_numbers(self):
        self.assertNotEqual(p.package_claim()['selected']['package_inode'], self.sample['files'][p.PYTHON_PATHS[0]]['ino'])
        self.assertNotEqual(p.package_claim()['selected']['package_device'], self.sample['files'][p.PYTHON_PATHS[0]]['dev'])
        proof_fixture()

    def test_integer_nanosecond_precision_survives_json_roundtrip(self):
        restored = json.loads(json.dumps(self.sample))
        self.assertEqual(restored, self.sample)
        self.assertEqual(restored['files'][p.PYTHON_PATHS[0]]['ctime_ns'], 1751181288018979029)
        proof = proof_fixture()
        rounded = copy.deepcopy(self.sample)
        for row in rounded['files'].values():
            row['ctime_ns'] = int(float(row['ctime_ns']))
        self.assertNotEqual(rounded, self.sample)
        with self.assertRaisesRegex(ValueError, 'PINNED_PRE_POST_CHANGED'):
            p.validate_pair_reread(proof, rounded, copy.deepcopy(rounded))

    def test_fixed_path_set_only(self):
        for bad in ('/usr/bin/python3', '/usr/libexec/platform-python',
                    '/usr/libexec/../libexec/platform-python3.6', '/tmp/python'):
            value = copy.deepcopy(self.sample)
            value['files'][bad] = value['files'].pop(p.PYTHON_PATHS[1])
            with self.assertRaisesRegex(ValueError, 'EXACT_TWO_FIXED_PATHS'): p.validate_pair_sample(value)

    def test_third_alias_or_missing_member_refused(self):
        for extra in (True, False):
            value = copy.deepcopy(self.sample)
            if extra: value['files']['/usr/libexec/python-third'] = dict(value['files'][p.PYTHON_PATHS[0]])
            else: del value['files'][p.PYTHON_PATHS[1]]
            with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_all_other_link_counts_refused(self):
        for bad in (0, 1, 3, 4, True, 2.0, '2'):
            self.both('nlink', bad)
            with self.assertRaises(ValueError): p.validate_pair_sample(self.sample)

    def test_pair_requires_complete_stamp_identity(self):
        for key in p.METADATA_FIELDS:
            value = copy.deepcopy(self.sample)
            value['files'][p.PYTHON_PATHS[1]][key] += 1
            with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_every_integer_stamp_rejects_bool_negative_float_and_missing(self):
        for key in p.METADATA_FIELDS:
            for bad in (True, -1, 1.0, '1', 2**64):
                value = copy.deepcopy(self.sample)
                for row in value['files'].values(): row[key] = bad
                with self.assertRaises(ValueError): p.validate_pair_sample(value)
            value = copy.deepcopy(self.sample)
            del value['files'][p.PYTHON_PATHS[0]][key]
            with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_file_owner_group_modes_size_and_kind_are_fixed(self):
        for key, values in (('uid', (1000, 1002)), ('gid', (1002, 1006)),
                ('mode', (0o644, 0o775, 0o4755, 0o2755, 0o100755)),
                ('size', (0, 15351, 15353)), ('kind', ('LINK', 'DIRECTORY'))):
            for bad in values:
                value = copy.deepcopy(self.sample)
                for row in value['files'].values(): row[key] = bad
                with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_exact_retained_hash_and_elf_required(self):
        for key, bad in (('sha256', '0'*64), ('sha256', p.RETAINED_SHA256.upper()),
                         ('elf_header', False), ('elf_header', 1), ('elf_header', None)):
            value = copy.deepcopy(self.sample)
            for row in value['files'].values(): row[key] = bad
            with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_file_acl_capabilities_and_unknown_refused(self):
        for key in p.XATTR_FIELDS:
            for bad in (True, None, 0, '', 'NOT_VERIFIED'):
                value = copy.deepcopy(self.sample)
                for row in value['files'].values(): row[key] = bad
                with self.assertRaisesRegex(ValueError, 'ACL_OR_CAPABILITY'): p.validate_pair_sample(value)

    def test_exact_ancestor_set_and_directory_type(self):
        for path in p.ANCESTOR_PATHS:
            value = copy.deepcopy(self.sample); del value['ancestors'][path]
            with self.assertRaises(ValueError): p.validate_pair_sample(value)
            value = copy.deepcopy(self.sample); value['ancestors'][path]['kind'] = 'SYMLINK'
            with self.assertRaises(ValueError): p.validate_pair_sample(value)
        value = copy.deepcopy(self.sample); value['ancestors']['/usr/bin'] = value['ancestors']['/usr']
        with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_root_owned_searchable_protected_ancestors(self):
        for path in p.ANCESTOR_PATHS:
            for key, bad in (('uid', 1002), ('gid', 1002), ('mode', 0o775), ('mode', 0o700),
                             ('access_acl', True), ('default_acl', True), ('capability', True),
                             ('access_acl', None), ('capability', None)):
                value = copy.deepcopy(self.sample); value['ancestors'][path][key] = bad
                with self.assertRaises(ValueError): p.validate_pair_sample(value)

    def test_repeated_directory_identity_refused(self):
        self.sample['ancestors']['/usr/libexec'] = dict(self.sample['ancestors']['/usr'])
        with self.assertRaisesRegex(ValueError, 'DISTINCT_ANCESTOR'): p.validate_pair_sample(self.sample)

    def test_pre_post_file_full_stamp_changes_refused(self):
        for key in ('ino', 'dev', 'mtime_ns', 'ctime_ns'):
            after = copy.deepcopy(self.sample)
            for row in after['files'].values(): row[key] += 1
            with self.assertRaisesRegex(ValueError, 'PRE_POST_CHANGED'):
                p.build_pair_proof(self.sample, after, p.package_claim())

    def test_pre_post_directory_full_stamp_changes_refused(self):
        for path in p.ANCESTOR_PATHS:
            for key in ('ino', 'dev', 'nlink', 'size', 'mtime_ns', 'ctime_ns'):
                after = copy.deepcopy(self.sample); after['ancestors'][path][key] += 1
                with self.assertRaises(ValueError): p.build_pair_proof(self.sample, after, p.package_claim())

    def test_live_replacement_needs_new_proof_and_cannot_reuse_old(self):
        proof = proof_fixture()
        fresh = copy.deepcopy(self.sample)
        for row in fresh['files'].values(): row['ino'] += 100
        self.assertNotEqual(p.build_pair_proof(fresh, copy.deepcopy(fresh), p.package_claim()), proof)
        with self.assertRaisesRegex(ValueError, 'PINNED_PRE_POST_CHANGED'):
            p.validate_pair_reread(proof, fresh, copy.deepcopy(fresh))

    def test_package_mutation_and_signature_upgrade_refused(self):
        for key, bad in (('inventory_count', 19), ('response_sha256', '0'*64),
                         ('schema', True), ('authority', 'VENDOR_VERIFIED')):
            claim = p.package_claim(); claim[key] = bad
            with self.assertRaises(ValueError): p.build_pair_proof(self.sample, self.sample, claim)
        claim = p.package_claim(); claim['package']['epoch'] = False
        with self.assertRaises(ValueError): p.build_pair_proof(self.sample, self.sample, claim)
        proof = proof_fixture(); proof['package_signature_authenticity'] = 'VERIFIED'
        with self.assertRaises(ValueError): p.validate_pair_proof(proof)

    def test_proof_fields_source_pins_and_reread_binding(self):
        proof = proof_fixture()
        for key in p.PROOF_FIELDS:
            value = copy.deepcopy(proof); del value[key]
            with self.assertRaises(ValueError): p.validate_pair_proof(value)
        for key, bad in (('schema', True), ('kind', 'OTHER'), ('owner_report_sha256', '0'*64),
                ('package_claim_sha256', '0'*64), ('retained_sha256', '0'*64), ('reread', 'NOT_RUN')):
            value = copy.deepcopy(proof); value[key] = bad
            with self.assertRaises(ValueError): p.validate_pair_proof(value)

    def test_all_outputs_are_independent_copies(self):
        proof = proof_fixture(); result = p.validate_pair_reread(proof, self.sample, self.sample)
        result['sample']['files'][p.PYTHON_PATHS[0]]['ino'] = 123
        self.assertEqual(proof['sample'], self.sample)
        result = p.validate_pair_sample(self.sample); result['ancestors']['/']['ino'] = 123
        self.assertEqual(self.sample, sample_fixture())

    def test_unknown_fields_or_recursive_proof_are_not_accepted(self):
        for target in ('sample', 'file', 'directory', 'proof'):
            value = proof_fixture() if target == 'proof' else copy.deepcopy(self.sample)
            row = value if target in ('sample', 'proof') else (value['files'][p.PYTHON_PATHS[0]]
                if target == 'file' else value['ancestors']['/'])
            row['python_identity'] = proof_fixture()
            with self.assertRaises(ValueError):
                (p.validate_pair_proof if target == 'proof' else p.validate_pair_sample)(value)

    def test_helper_has_no_filesystem_process_or_network_interface(self):
        tree = ast.parse(inspect.getsource(p))
        imports = {a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names}
        self.assertEqual(imports, {'copy', 'hashlib', 'json'})
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('open', 'exec', 'eval', '__import__', 'compile'))


if __name__ == '__main__': unittest.main()
