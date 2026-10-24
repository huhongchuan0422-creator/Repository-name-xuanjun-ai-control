import copy
import json
import unittest
from pathlib import Path

import successor_contract as contract

ROOT = Path(__file__).resolve().parent


def inputs():
    original = (ROOT / 'ORIGINAL_REVIEWED_SPEC.json').read_bytes()
    external = (ROOT / 'EXTERNAL_RELEASE_BINDER.json').read_bytes()
    manifest = (ROOT / 'RUNTIME_SOURCE_MANIFEST.json').read_bytes()
    listing = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_bytes())
    bodies = {row['release_path']: (ROOT / row['bundle_path']).read_bytes()
              for row in listing['files'] if row['release_path'] is not None}
    return original, external, manifest, bodies


class SuccessorContractTests(unittest.TestCase):
    def setUp(self):
        self.original, self.external, self.manifest, self.bodies = inputs()
        self.spec = contract.derive(self.original, self.external, self.manifest)

    def check(self, spec=None, external=None, manifest=None, bodies=None):
        return contract.validate(contract.canonical(self.spec if spec is None else spec),
                                 self.original, self.external if external is None else external,
                                 self.manifest if manifest is None else manifest,
                                 self.bodies if bodies is None else bodies)

    def test_exact_42_and_old_order(self):
        result = self.check()
        self.assertEqual((result['source_count'], result['object_count']), (42, 19))
        self.assertEqual(self.spec['fixed_paths']['configs'],
                         json.loads(self.original)['fixed_paths']['configs'])

    def test_successor_phase_descriptions_bound_to_42_and_separate_body(self):
        rows = self.spec['phase_sequence']
        self.assertEqual([r['step'] for r in rows], list(range(1, 18)))
        for number in (7, 8, 13, 16, 17):
            self.assertNotIn('c53', rows[number - 1]['required_result'])
        self.assertIn('42 fixed runtime source bytes', rows[6]['required_result'])
        self.assertIn('request-local authenticated cloud', rows[15]['required_result'])
        changed = copy.deepcopy(self.spec)
        changed['phase_sequence'][6]['required_result'] = 'old c53/32 release'
        with self.assertRaisesRegex(contract.Hold, 'SUCCESSOR_SPEC_UNEXPECTED_FIELDS'):
            self.check(spec=changed)

    def test_old_c53_spec_cannot_stand_in(self):
        with self.assertRaises(contract.Hold):
            contract.validate(self.original, self.original, self.external,
                              self.manifest, self.bodies)

    def test_changed_one_byte_or_lf_rejected(self):
        bodies = dict(self.bodies)
        name = sorted(bodies)[0]
        bodies[name] += b'\n'
        with self.assertRaisesRegex(contract.Hold, 'RELEASE_SOURCE_BYTES'):
            self.check(bodies=bodies)

    def test_old_release_or_32_only_rejected(self):
        with self.assertRaisesRegex(contract.Hold, 'RELEASE_PATHS'):
            self.check(bodies=dict(list(self.bodies.items())[:32]))
        changed = copy.deepcopy(self.spec)
        changed['fixed_paths']['target_release'] = json.loads(self.original)['fixed_paths']['target_release']
        with self.assertRaisesRegex(contract.Hold, 'SUCCESSOR_RELEASE_PATHS'):
            self.check(spec=changed)

    def test_role_gate_or_stage_reordering_rejected(self):
        changed = copy.deepcopy(self.spec)
        changed['gates']['close'] = changed['gates']['maintenance']
        with self.assertRaisesRegex(contract.Hold, 'STAGED_GATES'):
            self.check(spec=changed)
        changed = copy.deepcopy(self.spec)
        changed['phases'][14], changed['phases'][15] = changed['phases'][15], changed['phases'][14]
        with self.assertRaisesRegex(contract.Hold, 'SUCCESSOR_PHASE_ORDER'):
            self.check(spec=changed)

    def test_no_extra_approval_or_mixed_binder(self):
        changed = copy.deepcopy(self.spec)
        changed['approval_verified'] = True
        with self.assertRaisesRegex(contract.Hold, 'SUCCESSOR_SPEC_UNEXPECTED_FIELDS'):
            self.check(spec=changed)
        external = copy.deepcopy(json.loads(self.external))
        external['release_commit'] = json.loads(self.original)['source']['target_release']
        with self.assertRaisesRegex(contract.Hold, 'RELEASE_COMMIT'):
            self.check(external=contract.canonical(external))


if __name__ == '__main__':
    unittest.main()
