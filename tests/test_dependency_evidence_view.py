import copy
import unittest
from scripts.dependency_evidence_view import dependency_view


def nodes():
    return {'T': dict(dependencies=['A'], state='READY', evidence_sha256=None),
            'A': dict(dependencies=[], state='ACCEPTED', evidence_sha256='a' * 64)}


class DependencyTests(unittest.TestCase):
    def test_ready_never_grants(self):
        r = dependency_view('T', nodes())
        self.assertEqual(r['status'], 'DEPENDENCIES_EVIDENCED')
        self.assertFalse(r['execution_granted'])

    def test_missing_node(self):
        n = nodes(); del n['A']
        self.assertEqual(dependency_view('T', n)['status'], 'HOLD')

    def test_unknown_status_or_hash(self):
        for field, value in (('state', 'UNKNOWN'), ('evidence_sha256', None)):
            n = nodes(); n['A'][field] = value
            self.assertEqual(dependency_view('T', n)['status'], 'HOLD')

    def test_cycle(self):
        n = nodes(); n['A']['dependencies'] = ['T']
        self.assertIn('DEPENDENCY_CYCLE', dependency_view('T', n)['reasons'])

    def test_duplicate_dependency(self):
        n = nodes(); n['T']['dependencies'] = ['A', 'A']
        self.assertEqual(dependency_view('T', n)['status'], 'HOLD')

    def test_transitive_missing(self):
        n = nodes(); n['A']['dependencies'] = ['B']
        self.assertEqual(dependency_view('T', n)['status'], 'HOLD')

    def test_diamond(self):
        n = nodes(); n['B'] = copy.deepcopy(n['A']); n['T']['dependencies'].append('B')
        n['A']['dependencies'] = ['C']; n['B']['dependencies'] = ['C']
        n['C'] = dict(dependencies=[], state='ACCEPTED', evidence_sha256='c' * 64)
        self.assertEqual(dependency_view('T', n)['visited_count'], 4)

    def test_nonrecursive_large_chain(self):
        n = {str(i): dict(dependencies=[str(i + 1)] if i < 999 else [],
                         state='ACCEPTED', evidence_sha256='a' * 64) for i in range(1000)}
        self.assertEqual(dependency_view('0', n)['visited_count'], 1000)

    def test_no_mutation(self):
        n = nodes(); before = copy.deepcopy(n); dependency_view('T', n)
        self.assertEqual(n, before)

    def test_malformed_dependency(self):
        n = nodes(); n['A']['dependencies'] = [None]
        self.assertEqual(dependency_view('T', n)['status'], 'HOLD')

    def test_malformed_target_has_fixed_rejection(self):
        for target in ([], {}, None, True, '', '../bad', 'x' * 161):
            with self.assertRaisesRegex(ValueError, 'INVALID_DEPENDENCY_INPUT'):
                dependency_view(target, nodes())
