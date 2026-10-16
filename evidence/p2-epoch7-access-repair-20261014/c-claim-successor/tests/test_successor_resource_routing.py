"""Portable D5 routing tests using a temporary frozen-baseline + local overlay.

All host boundaries are synthetic. The exact predecessor bytes are unavailable
locally, so the fixed original pin is asserted separately and must reject these
synthetic bytes. Reader tests copy generated views and substitute ONLY that
predecessor's content hash for an explicitly synthetic 1641-byte local file.
The real ResourceReader, all 17 checkpoints, all sections, all other specs and
all 16 frozen fixture phase mutations remain unchanged. This grants no authority.
"""
import ast
import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

CANDIDATE = Path(__file__).resolve().parent.parent
BASELINE = CANDIDATE / 'baseline'
OVERLAY = CANDIDATE / 'kit-overlay'
OLD_OUTER = 'epoch7-recovery-sequence.json'
OLD_INNER = 'epoch7-recovery-execution.json'
NEW_OUTER = 'epoch7-recovery-sequence-successor-a5602f7e70e22edba.json'
NEW_INNER = 'epoch7-recovery-execution-successor-a5602f7e70e22edba.json'
PREDECESSOR_SHA256 = 'a5602f7e70e22edbab683518f21ae8b851369fb61008e7683af1451f4b357055'


def run_isolated():
    """No imports, bytecode, fixtures, or edits enter the frozen baseline."""
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix='successor-resource-tests-') as temporary:
        merged = Path(temporary) / 'kit'
        shutil.copytree(str(BASELINE), str(merged))
        for source in OVERLAY.rglob('*'):
            if source.is_file():
                target = merged / source.relative_to(OVERLAY)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(source), str(target))
        (merged / 'helpers/fixtures').mkdir(exist_ok=True)
        runtime = merged / 'xuanjun-p2-package'
        sys.path[:0] = [str(merged / 'helpers'), str(runtime / 'scripts'),
                       str(runtime / 'stage1'), str(merged / 'tests/recovery'),
                       str(merged / 'tests/acceptance_rows')]
        import epoch7_claim_successor as successor
        import epoch7_resource_plan as p
        import epoch7_resource_observer as r
        import epoch7_host_phases as h
        import epoch7_host_containment as containment
        import epoch7_protected_fs as fs
        import epoch7_delta as d
        import epoch7_recovery_sequence as sequence

        def contract_fixture():
            return {'schema': 1, 'kind': 'EXACT_CLAIM_ONLY_SUCCESSOR',
                'predecessor': successor.predecessor_contract(),
                'implementation': {'source_commit': '1' * 40, 'source_tree': '2' * 40,
                                   'kit_manifest_sha256': '3' * 64},
                'admission_expires_at_utc': '2027-12-31T23:59:59Z',
                'authorized_successors': 1, 'automatic_retry': False,
                'effect_scope': 'UNCHANGED_107_PAYLOADS_16_PHASES',
                'measured_predecessor_sha256': '4' * 64}

        # Adapt only fixture inputs, never production globals or source. The
        # frozen test file on disk remains byte-for-byte unchanged.
        fixture_path = merged / 'tests/resource_plan/test_epoch7_resource_plan.py'
        fixture_source = fixture_path.read_text()
        old = "self.inner('epoch7-recovery-execution.json',{'stage':'ADMITTED'})"
        assert fixture_source.count(old) == 1
        fixture_source = fixture_source.replace(old,
            "self.inner(%r,{'stage':'ADMITTED'})" % NEW_INNER)
        old = 'publisher_journal_raw=self.publisher_raw,nss_projection=self.nss)'
        assert fixture_source.count(old) == 1
        fixture_source = fixture_source.replace(old, old[:-1] + ',claim_successor=self.claim_successor)')
        fixture_namespace = {'__file__': str(fixture_path), '__name__': '_frozen_resource_fixture'}
        exec(compile(fixture_source, str(fixture_path), 'exec'), fixture_namespace)
        Fixture = fixture_namespace['SeventeenCheckpointTests']
        original_namespace = {'__name__': '_original_resource_plan',
                              '__file__': str(BASELINE / 'helpers/epoch7_resource_plan.py')}
        exec(compile((BASELINE / 'helpers/epoch7_resource_plan.py').read_bytes(),
                     '<frozen-original-resource-plan>', 'exec'), original_namespace)

        class SuccessorResourceTests(Fixture):
            def setUp(self):
                self.claim_successor = contract_fixture()
                super().setUp()
                self.exact_views = copy.deepcopy(self.views)
                self.predecessor_path = fs.TRANSACTION + '/' + OLD_OUTER
                raw = h.packed({'fixture': 'SYNTHETIC_PREDECESSOR_NOT_ORIGINAL', 'padding': ''})
                self.synthetic_raw = h.packed({'fixture': 'SYNTHETIC_PREDECESSOR_NOT_ORIGINAL',
                                              'padding': '.' * (1641 - len(raw))})
                self.assertEqual(len(self.synthetic_raw), 1641)
                self.assertNotEqual(h.sha(self.synthetic_raw), PREDECESSOR_SHA256)
                self.synthetic_metadata = self.file(self.predecessor_path, self.synthetic_raw)
                for view in self.views:
                    row = next(row for row in view['historical'] if row['path'] == self.predecessor_path)
                    row['sha256'] = h.sha(self.synthetic_raw)

            def test_fixed_predecessor_and_old_absence_at_all17_checkpoints(self):
                self.assertEqual(len(self.exact_views), 17)
                wanted = {'path': self.predecessor_path, 'kind': 'FILE', 'uid': 0, 'gid': 0,
                          'mode': 0o600, 'access_acl': p.decode_acl(None, 0o600),
                          'sha256': PREDECESSOR_SHA256}
                for view in self.exact_views:
                    self.assertEqual(set(view), r.SECTIONS)
                    rows = {row['path']: row for row in view['historical']}
                    self.assertEqual(rows[self.predecessor_path], wanted)
                    self.assertEqual(rows[fs.TRANSACTION + '/' + OLD_INNER],
                                     p.absent(fs.TRANSACTION + '/' + OLD_INNER))
                    self.assertEqual(rows[fs.TRANSACTION + '/' + NEW_INNER],
                        p.projection(fs.TRANSACTION + '/' + NEW_INNER,
                                     [(('transaction_id',), d.TX)], binding='inner'))
                    self.assertNotIn(fs.TRANSACTION + '/' + NEW_OUTER, rows)

            def test_only_three_historical_rows_differ_from_original_views(self):
                before = copy.deepcopy((self.snapshot, self.support, self.claim_successor))
                original = original_namespace['build_resource_views'](
                    self.snapshot, self.support, self.compiled, self.additions, self.security,
                    self.manifest_raw, self.payloads, self.installer, self.native_after,
                    self.tls_before, self.profile_candidate, self.legacy,
                    release_parent=self.fresh_parent, executable_specs=self.exes,
                    policy=self.policy, publisher_journal_raw=self.publisher_raw,
                    nss_projection=self.nss)
                expected = copy.deepcopy(original)
                for view in expected:
                    rows = {row['path']: row for row in view['historical']}
                    current = rows.pop(fs.TRANSACTION + '/' + OLD_INNER)
                    current['path'] = fs.TRANSACTION + '/' + NEW_INNER
                    rows[current['path']] = current
                    rows[fs.TRANSACTION + '/' + OLD_INNER] = p.absent(fs.TRANSACTION + '/' + OLD_INNER)
                    rows[self.predecessor_path] = p.predecessor_resource_spec(self.claim_successor)
                    view['historical'] = [rows[path] for path in sorted(rows)]
                self.assertEqual(self.exact_views, expected)
                self.assertEqual((self.snapshot, self.support, self.claim_successor), before)
                self.assertEqual(p.build_resource_directories(self.policy, self.exact_views),
                                 p.build_resource_directories(self.policy, original))
                self.assertNotEqual(r.resource_views_digest(self.exact_views), r.resource_views_digest(original))

            def test_actual_reader_rejects_predecessor_change_at_every_checkpoint(self):
                for index in range(17):
                    with self.subTest(checkpoint=index):
                        if index:
                            self.mutate(sequence.PHASES[index - 1])
                        self.file(self.predecessor_path, b'!' + self.synthetic_raw[1:])
                        with self.assertRaisesRegex(AssertionError, 'RESOURCE_EXACT_SPEC_DRIFT'):
                            self.check_view(index)
                        self.file(self.predecessor_path, self.synthetic_raw)
                        self.check_view(index)

            def test_actual_reader_rejects_predecessor_mode_and_hardlink(self):
                os.chmod(self.root + self.predecessor_path, 0o644)
                with self.assertRaisesRegex(AssertionError, 'RESOURCE_EXACT_SPEC_DRIFT'):
                    self.check_view(0)
                os.chmod(self.root + self.predecessor_path, 0o600)
                os.link(self.root + self.predecessor_path, self.root + self.predecessor_path + '.extra-link')
                with self.assertRaisesRegex(AssertionError, 'RESOURCE_FILE_BOUND'):
                    self.check_view(0)

            def test_actual_reader_rejects_old_inner_presence(self):
                self.inner(OLD_INNER, {'stage': 'ADMITTED'})
                with self.assertRaisesRegex(AssertionError, 'RESOURCE_UNEXPECTED_PRESENT'):
                    self.check_view(0)

            def test_actual_reader_requires_new_inner_current_binding(self):
                path = fs.TRANSACTION + '/' + NEW_INNER
                good = h.decode(self.raw[path])
                for key, value in (('name', OLD_INNER), ('transaction_id', 'wrong'),
                                   ('binding', {'review_id': successor.OLD_REVIEW_ID}), ('schema', 2)):
                    with self.subTest(field=key):
                        bad = copy.deepcopy(good); bad[key] = value
                        self.file(path, h.packed(bad))
                        with self.assertRaisesRegex(AssertionError, 'RESOURCE_INNER_JOURNAL_BINDING'):
                            self.check_view(0)
                self.file(path, h.packed(good))
                self.check_view(0)

            def test_synthetic_bytes_cannot_authenticate_as_original(self):
                with self.assertRaisesRegex(ValueError, 'CLAIM_SUCCESSOR_PREDECESSOR_BYTES'):
                    successor.validate_predecessor_record(self.synthetic_raw, self.synthetic_metadata)
                self.views = self.exact_views
                with self.assertRaisesRegex(AssertionError, 'RESOURCE_EXACT_SPEC_DRIFT'):
                    self.check_view(0)

        class RoutingAndContractTests(unittest.TestCase):
            def test_predecessor_pin_and_all_names_are_fixed(self):
                self.assertEqual((successor.OLD_OUTER, successor.OLD_INNER, successor.NEW_OUTER,
                                  successor.NEW_INNER), (OLD_OUTER, OLD_INNER, NEW_OUTER, NEW_INNER))
                self.assertEqual(successor.PREDECESSOR_SIZE, 1641)
                self.assertEqual(successor.PREDECESSOR_SHA256, PREDECESSOR_SHA256)
                self.assertEqual(successor.predecessor_resource_identity(contract_fixture())['size'], 1641)
                for field, value in (('outer_name', NEW_OUTER), ('inner_name', NEW_INNER),
                    ('successor_outer_name', OLD_OUTER), ('successor_inner_name', OLD_INNER),
                    ('raw_size', 1640), ('raw_sha256', 'f' * 64)):
                    contract = contract_fixture(); contract['predecessor'][field] = value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        p.predecessor_resource_spec(contract)
                contract = contract_fixture(); contract['implementation']['source_commit'] = 'UNBOUND'
                with self.assertRaises(ValueError): p.predecessor_resource_spec(contract)
                with self.assertRaises(ValueError): p.predecessor_resource_spec(None)

            def test_old_names_are_not_writable_aliases(self):
                io = fs.ProtectedFilesystem.__new__(fs.ProtectedFilesystem)
                io.owner = 0; io.group = 0
                io._authorize = mock.Mock(side_effect=AssertionError('AUTHORITY_BOUNDARY'))
                for name in (OLD_INNER, OLD_OUTER):
                    self.assertNotIn(name, fs.NEW_JOURNALS)
                    with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_JOURNAL_ONLY'):
                        io.create_exclusive(name, b'{}\n', 0, 0, 0o600)
                    with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_JOURNAL_ONLY'):
                        io.replace_exact(name, {}, b'{}\n', 0, 0, 0o600)
                io._authorize.assert_not_called()
                self.assertIn(NEW_INNER, fs.NEW_JOURNALS)
                with self.assertRaisesRegex(AssertionError, 'AUTHORITY_BOUNDARY'):
                    io.create_exclusive(NEW_INNER, b'{}\n', 0, 0, 0o600)

            def test_all_four_intent_consumers_read_new_inner(self):
                io = fs.ProtectedFilesystem.__new__(fs.ProtectedFilesystem)
                io.owner = 0; io.group = 0
                io._authorize = lambda: None
                io._approved_effect = lambda *args: None
                io._require_intent = mock.Mock(side_effect=AssertionError('INTENT_BOUNDARY'))
                path = next(iter(d.TARGETS)); raw = b'synthetic'
                after = {'kind': 'FILE', 'uid': 0, 'gid': 0, 'mode': 0o644, 'sha256': h.sha(raw)}
                calls = [
                    (io.backup_target_exact, (path, {}, 'epoch7-target-before-' + h.sha(path.encode()) + '.private'), 'TARGET_DELTA_INTENT'),
                    (io.replace_target_exact, (path, {}, raw, after), 'TARGET_DELTA_INTENT'),
                    (io.publish_additive_exact, ({'path': fs.additive.PATH}, raw, after), 'ADDITIVE_PUBLICATION_INTENT'),
                    (io.chmod_generation_exact, ({'path': d.GENERATION, 'mode': 0o750},
                        {'path': d.GENERATION, 'mode': 0o700, 'access_acl': 'user::rwx\ngroup::---\nother::---\n'}), 'GENERATION_ACCESS_INTENT')]
                for method, args, stage in calls:
                    io._require_intent.reset_mock()
                    with self.subTest(method=method.__name__), self.assertRaisesRegex(AssertionError, 'INTENT_BOUNDARY'):
                        method(*args)
                    io._require_intent.assert_called_once_with(NEW_INNER, stage)

            def prepared_inner_boundary(self):
                root = tempfile.mkdtemp(prefix='prechecked-inner-', dir=str(merged / 'helpers/fixtures'))
                self.addCleanup(shutil.rmtree, root)
                os.chmod(root, 0o700)
                transaction = root + fs.TRANSACTION
                os.makedirs(transaction, mode=0o700)
                contract = contract_fixture()
                # Synthetic predecessor content boundary, with actual local
                # filesystem stamps for the fixture ancestry endpoints.
                def ancestors():
                    return {path: dict(fs.metadata(os.lstat(local)), kind='DIRECTORY')
                            for path, local in (('/', root), (fs.TRANSACTION, transaction))}
                proof = {'record': {'fixture': 'SYNTHETIC_MEASURED_PREDECESSOR'},
                         'ancestors': ancestors()}
                contract['measured_predecessor_sha256'] = successor.digest(proof)
                context = {'context_sha256': 'b' * 64, 'claim_successor': contract}
                lock = types.SimpleNamespace(held=lambda: True)
                verifier = types.SimpleNamespace(body_sha='c' * 64, checked_under_lock=True,
                    cached=b'SYNTHETIC_CACHED_REVIEW', _bound=mock.Mock(), verify_exact=mock.Mock(),
                    check_admission_expiry=mock.Mock(), seal_admission=mock.Mock())
                gate = types.SimpleNamespace(check=mock.Mock(), review_id=7000000001,
                                             verifier=verifier, expected={})
                io = fs.ProtectedFilesystem(gate, fixture_root=root)
                outer_io = types.SimpleNamespace(read_predecessor_proof=lambda: proof,
                    predecessor_record=lambda: proof['record'], predecessor_ancestors=ancestors,
                    predecessor_inner_absent=lambda: True, journal_exists=lambda name: False)
                inner = types.SimpleNamespace(_packed=lambda state: h.packed({'name': NEW_INNER,
                    'transaction_id': d.TX, 'state': state}))
                controls = types.SimpleNamespace(install_lock=lambda: lock,
                    observer=types.SimpleNamespace(guard_deadline=successor.time.monotonic() + 30),
                    preflight=lambda current: sequence.observation(current, 'preflight', 'd' * 64))
                driver = types.SimpleNamespace(context=context, gate=gate, inner=inner,
                    retained_io=io, journal_io=outer_io, controls=controls, check_binding=mock.Mock())
                prepared, unused = successor.prepare_successor(driver, contract)
                prepared.consume(driver)
                prepared.ready(proof, controls.observer.guard_deadline)
                journal = types.SimpleNamespace(io=outer_io, context=context, last=None,
                                                poisoned=False, _raw=h.packed)
                outer_io.read_journal = lambda name: copy.deepcopy(journal.last)
                outer_raw = prepared.begin_outer(journal, {'stage': 'CLAIM_INTENT'})
                prepared.authorize_outer_io(outer_io, NEW_OUTER, outer_raw)
                journal.last = {'data': outer_raw}; prepared.confirm_outer(journal, outer_raw)
                prepared.begin_inner(inner, prepared.inner_raw)
                return io, prepared, gate, root

            def test_prechecked_inner_uses_one_final_capability_and_no_full_gate(self):
                io, prepared, gate, root = self.prepared_inner_boundary()
                calls = []; gate.check.reset_mock()
                parent = io._journal_parent; authorize = prepared.authorize_inner_io
                exclusive = io._exclusive_at
                def get_parent():
                    calls.append('protected_parent'); return parent()
                def authorize_once(*args):
                    calls.append('capability'); return authorize(*args)
                def publish(*args):
                    calls.append('exclusive'); return exclusive(*args)
                with mock.patch.object(io, '_journal_parent', side_effect=get_parent), \
                     mock.patch.object(prepared, 'authorize_inner_io', side_effect=authorize_once), \
                     mock.patch.object(io, '_exclusive_at', side_effect=publish):
                    io.create_prechecked_inner(NEW_INNER, prepared.inner_raw, prepared)
                self.assertEqual(calls, ['protected_parent', 'capability', 'exclusive'])
                gate.check.assert_not_called()
                path = Path(root + fs.TRANSACTION + '/' + NEW_INNER)
                self.assertEqual(path.read_bytes(), prepared.inner_raw)
                self.assertEqual(path.stat().st_nlink, 1)
                self.assertEqual(path.stat().st_mode & 0o7777, 0o600)
                with self.assertRaisesRegex(ValueError, 'INNER_IO_CAPABILITY'):
                    io.create_prechecked_inner(NEW_INNER, prepared.inner_raw, prepared)
                self.assertEqual(path.read_bytes(), prepared.inner_raw)

            def test_prechecked_inner_write_failure_consumes_io_permission(self):
                io, prepared, gate, root = self.prepared_inner_boundary()
                gate.check.reset_mock()
                with mock.patch.object(io, '_exclusive_at', side_effect=OSError('SYNTHETIC_WRITE_FAILURE')) as write:
                    with self.assertRaisesRegex(OSError, 'SYNTHETIC_WRITE_FAILURE'):
                        io.create_prechecked_inner(NEW_INNER, prepared.inner_raw, prepared)
                    with self.assertRaisesRegex(ValueError, 'INNER_IO_CAPABILITY'):
                        io.create_prechecked_inner(NEW_INNER, prepared.inner_raw, prepared)
                    self.assertEqual(write.call_count, 1)
                self.assertTrue(prepared.io_used)
                self.assertFalse(os.path.exists(root + fs.TRANSACTION + '/' + NEW_INNER))
                gate.check.assert_not_called()

            def test_prechecked_inner_rejects_lookalike_capabilities(self):
                io = fs.ProtectedFilesystem.__new__(fs.ProtectedFilesystem)
                fake = types.SimpleNamespace(authorize_inner_io=mock.Mock())
                for token in (None, False, {}, fake):
                    with self.subTest(token=type(token).__name__), self.assertRaisesRegex(
                            ValueError, 'PRECHECKED_CAPABILITY_REQUIRED'):
                        io.create_prechecked_inner(NEW_INNER, b'{}\n', token)
                fake.authorize_inner_io.assert_not_called()
                for name in (OLD_INNER, OLD_OUTER, NEW_OUTER, 'caller-chosen.json'):
                    with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'PRECHECKED_INNER_NAME_ONLY'):
                        io.create_prechecked_inner(name, b'{}\n', fake)

            def test_containment_reads_only_current_successor_outer(self):
                holder = containment.HostContainment.__new__(containment.HostContainment)
                holder.context = {'context_sha256': 'a' * 64}; holder.attempted = set()
                reader = mock.Mock(side_effect=AssertionError('OUTER_BOUNDARY'))
                holder.io = types.SimpleNamespace(read_journal=reader,
                    authority=types.SimpleNamespace(receipt=lambda: None, validate_outer=lambda value: value))
                with self.assertRaisesRegex(AssertionError, 'OUTER_BOUNDARY'):
                    holder.run(holder.context, 'fence', None, None)
                reader.assert_called_once_with(NEW_OUTER)

            def test_owned_routing_edits_do_not_change_business_methods(self):
                for name, old, new in (('epoch7_protected_fs.py', OLD_INNER, NEW_INNER),
                                       ('epoch7_host_containment.py', OLD_OUTER, NEW_OUTER)):
                    original = (BASELINE / 'helpers' / name).read_text()
                    changed = (OVERLAY / 'helpers' / name).read_text()
                    expected = ast.parse(original.replace(old, new))
                    actual = ast.parse(changed)
                    if name == 'epoch7_protected_fs.py':
                        cls = next(node for node in actual.body if isinstance(node, ast.ClassDef)
                                   and node.name == 'ProtectedFilesystem')
                        added = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                                 and node.name == 'create_prechecked_inner']
                        self.assertEqual(len(added), 1)
                        cls.body.remove(added[0])
                    self.assertEqual(ast.dump(actual), ast.dump(expected))
                def phases(path):
                    tree = ast.parse(path.read_text())
                    build = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                                 and node.name == 'build_resource_views')
                    return next(node for node in build.body if isinstance(node, ast.For)
                                and isinstance(node.iter, ast.Name) and node.iter.id == 'PHASES')
                self.assertEqual(ast.dump(phases(BASELINE / 'helpers/epoch7_resource_plan.py')),
                                 ast.dump(phases(OVERLAY / 'helpers/epoch7_resource_plan.py')))

        suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorResourceTests),
                                   unittest.defaultTestLoader.loadTestsFromTestCase(RoutingAndContractTests)])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1


class PortableSuccessorResourceRoutingTests(unittest.TestCase):
    def test_merged_candidate_resource_routing(self):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        completed = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--isolated'],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env=environment, universal_newlines=True, timeout=240)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        print(completed.stdout)


if __name__ == '__main__':
    if '--isolated' in sys.argv:
        sys.exit(run_isolated())
    unittest.main()
