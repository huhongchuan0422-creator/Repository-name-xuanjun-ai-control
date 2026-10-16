"""Focused large-resource B -> C closure; no host/network/install effects.

Run only this new suite on Python 3.12. The disposable public fixture maps the
existing four unavailable historical private-byte pins, never compiler results.
"""
import copy
import hashlib
import json
import os
import pathlib
import tempfile
import time
import types
import unittest
from unittest import mock

import resource_aggregate_fixture as x
import epoch7_host_observer as host_observer
import epoch7_quiet_startup as quiet


class NoEffectReader(x.observer.ResourceReader):
    """Read-only fake boundary; actual CheckpointResources methods remain real."""
    def __init__(self, directories):
        self.directories = copy.deepcopy(directories)
        self.started, self.observed = 0, []
    def start(self): self.started += 1
    def observe(self, spec):
        self.observed.append(spec['path'])
        return copy.deepcopy(spec)


def small_views():
    return [{name: [{'path': '/fixture/' + name, 'kind': 'ABSENT'}]
             for name in x.observer.SECTIONS} for unused in range(17)]


def small_directories():
    return {'/': [{'uid': 0, 'gid': 0, 'mode': 0o755,
                  'access_acl': 'user::rwx\ngroup::r-x\nother::r-x\n', 'default_acl': ''}]}


def bind_host(plan, resources):
    """Real C bind_plan/_bound, with only unavailable host components inert."""
    instance = object.__new__(host_observer.Epoch7HostObserver)
    instance.bound_plan, instance.live_contract = None, None
    instance.resource_reader = resources
    instance.policy_sha = plan['resource_observer']['snapshot_policy_sha256']
    live = plan['live_controls']
    instance.census = types.SimpleNamespace(manager_pin=copy.deepcopy(live['manager']),
        database_identities=copy.deepcopy(live['database_identities']),
        retained_sidecars=copy.deepcopy(live['retained_sidecar_pins']))
    instance.quiet = object.__new__(quiet.BoundedQuietStartup)
    instance.quiet.relay_metadata = None
    instance.bind_plan(plan)
    instance._bound()
    return instance


class SegmentedBindingTests(unittest.TestCase):
    def test_plain_canonical_boundary_is_still_exactly_two_mib(self):
        self.assertEqual(len(x.d.canonical('a' * (x.LIMIT - 2))), x.LIMIT)
        for value in ('a' * (x.LIMIT - 1), {'value': 'a' * x.LIMIT}):
            with self.subTest(kind=type(value).__name__), self.assertRaisesRegex(ValueError, 'PROPOSAL_SIZE_BOUND'):
                x.d.canonical(value)

    def test_digest_and_comparison_are_deterministic_order_sensitive_and_nonmutating(self):
        views = small_views()
        views[-1]['historical'].append({'path': '/fixture/late', 'kind': 'FILE', 'uid': 0})
        before = copy.deepcopy(views)
        pin = x.observer.resource_views_digest(views)
        self.assertRegex(pin, '^[0-9a-f]{64}$')
        self.assertEqual(pin, x.observer.resource_views_digest(copy.deepcopy(views)))
        self.assertTrue(x.observer.same_resource_views(views, copy.deepcopy(views)))
        self.assertEqual(views, before)
        changed = copy.deepcopy(views)
        changed[-1]['historical'].reverse()
        self.assertFalse(x.observer.same_resource_views(views, changed))
        self.assertNotEqual(pin, x.observer.resource_views_digest(changed))

    def test_exact_segment_envelopes_bind_every_checkpoint_section_and_path(self):
        views = small_views()
        segments = [[index, [[name, len(view[name]), x.d.digest(view[name])]
                     for name in sorted(x.observer.SECTIONS)]] for index, view in enumerate(views)]
        expected = x.d.digest(['EPOCH7_RESOURCE_VIEWS_SEGMENTED_V1', 17, segments])
        self.assertEqual(x.observer.resource_views_digest(views), expected)
        dirs = small_directories()
        leaves = [x.d.digest(['EPOCH7_RESOURCE_DIRECTORY_LEAF_V1', path, dirs[path]]) for path in sorted(dirs)]
        expected = x.d.digest(['EPOCH7_RESOURCE_DIRECTORIES_SEGMENTED_V1', len(leaves), leaves])
        self.assertEqual(x.observer.resource_directories_digest(dirs), expected)

    def test_late_checkpoint_section_row_and_bool_int_mutations_are_bound(self):
        original = small_views()
        original[-1]['historical'][0]['uid'] = 0
        original[-1]['historical'].append({'path': '/fixture/last', 'kind': 'FILE', 'uid': 0})
        pin = x.observer.resource_views_digest(original)
        mutations = [
            lambda value: value[-1]['historical'][-1].update(uid=1),
            lambda value: value[-1]['historical'][-1].update(uid=False),
            lambda value: value[-1]['historical'][-1].update(path='/fixture/different'),
            lambda value: value[-1]['historical'].pop(),
            lambda value: value[-1].update(boot=copy.deepcopy(value[-1]['historical'])),
            lambda value: value.reverse(),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.subTest(mutation=mutate):
                self.assertNotEqual(pin, x.observer.resource_views_digest(changed))
                self.assertFalse(x.observer.same_resource_views(original, changed))

    def test_malformed_checkpoint_section_row_and_path_structures_refuse(self):
        cases = [None, {}, tuple(small_views()), small_views()[:-1], small_views() + [small_views()[0]]]
        for edit in (
            lambda value: value.__setitem__(-1, []),
            lambda value: value[-1].pop('historical'),
            lambda value: value[-1].update(extra=[]),
            lambda value: value[-1].update(historical=[]),
            lambda value: value[-1].update(historical=tuple(value[-1]['historical'])),
            lambda value: value[-1]['historical'].append(copy.deepcopy(value[-1]['historical'][0])),
            lambda value: value[-1].update(historical=[None]),
            lambda value: value[-1].update(historical=[{}]),
        ):
            value = small_views(); edit(value); cases.append(value)
        for path in (None, True, 1, 'relative', '/a/../b', '/a\x00b', '/' + 'a' * 4096):
            value = small_views(); value[-1]['historical'][0]['path'] = path; cases.append(value)
        for index, value in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(ValueError): x.observer.resource_views_digest(value)
                with self.assertRaises(ValueError): x.observer.same_resource_views(small_views(), value)

    def test_section_row_count_accepts_8192_and_rejects_8193(self):
        views = small_views()
        views[-1]['historical'] = [{'path': '/f/%d' % i, 'kind': 'ABSENT'} for i in range(8192)]
        x.observer.resource_views_digest(views)
        views[-1]['historical'].append({'path': '/f/8192', 'kind': 'ABSENT'})
        with self.assertRaisesRegex(ValueError, 'RESOURCE_FINITE_PATHS'):
            x.observer.resource_views_digest(views)

    def test_single_section_over_two_mib_and_nonfinite_leaf_still_refuse(self):
        for leaf in ('a' * x.LIMIT, float('nan'), float('inf')):
            views = small_views(); views[-1]['historical'][0]['extra'] = leaf
            with self.subTest(leaf_type=type(leaf).__name__), self.assertRaises(ValueError):
                x.observer.resource_views_digest(views)
        views = small_views(); views[-1]['historical'][0]['extra'] = 'a' * x.LIMIT
        with self.assertRaisesRegex(ValueError, 'PROPOSAL_SIZE_BOUND'):
            x.observer.same_resource_views(views, copy.deepcopy(views))

    def test_old_flat_views_digest_is_not_accepted_by_actual_checkpoint_consumer(self):
        views = small_views()
        old = x.d.digest(views)
        self.assertNotEqual(old, x.observer.resource_views_digest(views))
        with self.assertRaisesRegex(ValueError, 'RESOURCE_VIEW_HASH'):
            x.observer.CheckpointResources({}, NoEffectReader(small_directories()), views, old)

    def test_directory_keys_state_order_types_and_late_values_are_bound(self):
        original = small_directories()
        original['/last'] = [dict(original['/'][0], uid=1), dict(original['/'][0], uid=2)]
        pin = x.observer.resource_directories_digest(original)
        self.assertTrue(x.observer.same_resource_directories(original, copy.deepcopy(original)))
        self.assertEqual(pin, x.observer.resource_directories_digest(dict(reversed(list(original.items())))))
        for change in ('uid', 'type', 'path', 'order'):
            value = copy.deepcopy(original)
            if change == 'uid': value['/last'][-1]['uid'] = 3
            elif change == 'type': value['/'][0]['uid'] = False
            elif change == 'path': value['/other'] = value.pop('/last')
            else: value['/last'].reverse()
            with self.subTest(change=change):
                self.assertNotEqual(pin, x.observer.resource_directories_digest(value))
                self.assertFalse(x.observer.same_resource_directories(original, value))

    def test_directory_structural_limits_and_leaf_size_refuse(self):
        cases = [None, [], {}, {'/other': small_directories()['/']}]
        for rows in ([], (), [None], [{}], small_directories()['/'] * 4):
            cases.append({'/': rows})
        for path in ('relative', '/a/../b', '/a\x00b', '/' + 'a' * 4096):
            value = small_directories(); value[path] = copy.deepcopy(value['/']); cases.append(value)
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                x.observer.resource_directories_digest(value)
        value = small_directories(); value['/'][0]['access_acl'] = 'a' * x.LIMIT
        with self.assertRaisesRegex(ValueError, 'PROPOSAL_SIZE_BOUND'):
            x.observer.resource_directories_digest(value)
        value = small_directories()
        value.update({'/d/%d' % i: copy.deepcopy(value['/']) for i in range(8192)})
        with self.assertRaisesRegex(ValueError, 'RESOURCE_DIRECTORY_POLICY'):
            x.observer.resource_directories_digest(value)

    def test_8192_directory_bound_with_8191_maximum_length_paths_hashes_only_bounded_leaves(self):
        value = small_directories()
        value.update({'/' + ('%04x' % i) + 'a' * (4096 - 5): copy.deepcopy(value['/'])
                      for i in range(8191)})
        self.assertEqual(len(value), 8192)
        self.assertTrue(all(len(path) == 4096 for path in value if path != '/'))
        calls = []
        real = x.d.canonical
        def measured(item):
            raw = real(item); calls.append(len(raw)); return raw
        with mock.patch.object(x.d, 'canonical', side_effect=measured):
            pin = x.observer.resource_directories_digest(value)
        self.assertRegex(pin, '^[0-9a-f]{64}$')
        self.assertEqual(len(calls), 8193)
        self.assertLess(max(calls), x.LIMIT)
        self.assertLess(calls[-1], 600000)
        with self.assertRaisesRegex(ValueError, 'PROPOSAL_SIZE_BOUND'): x.d.canonical(value)


class LargeFactoryAndConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = x.large_seed()
        cls.seed_before = copy.deepcopy(cls.seed)
        with x.native_pins(cls.seed):
            cls.prepared = x.factory.prepare_host_inputs(cls.seed)
            cls.inputs = cls.prepared['inputs']
            cls.plan = x.factory.compile_host_contract(cls.inputs)

    def resources(self):
        reader = NoEffectReader(self.inputs['resource_directories'])
        context = {'fixture': 'NO_HOST_AUTHORITY'}
        resources = x.observer.CheckpointResources(context, reader, self.inputs['resource_views'],
                    self.plan['resource_observer']['views_sha256'])
        return context, reader, resources

    def test_genuine_107_factory_with_three_102_file_histories_exceeds_only_aggregate_bound(self):
        self.assertEqual(self.seed, self.seed_before)
        self.assertEqual(len(self.seed['source_payloads']), 107)
        histories = self.seed['observation']['evidence']['retained']['release_evidence']
        self.assertEqual(len(histories), 3)
        for root, history in histories.items():
            self.assertEqual(len(history['files']), 102)
            stamps = [(row['dev'], row['ino']) for row in history['directories'].values()]
            self.assertEqual(len(stamps), len(set(stamps)))
            components = self.seed['observation']['evidence']['retained']['native_components']['components']
            for name, row in history['files'].items():
                if root + '/' + name in components:
                    self.assertEqual(row, components[root + '/' + name])
            self.assertEqual(len(history['caches']), 48)
            for name, cache in history['caches'].items():
                source = 'stage1/' + pathlib.PurePosixPath(name).name[:-len('.cpython-36.pyc')] + '.py'
                self.assertEqual(cache['source_sha256'], history['files'][source]['sha256'])
        views = self.inputs['resource_views']
        self.assertEqual((len(views), len(views[0])), (17, 15))
        self.assertGreater(len(x.json_bytes(views)), x.LIMIT)
        self.assertTrue(all(len(x.d.canonical(rows)) <= x.LIMIT for view in views for rows in view.values()))
        with self.assertRaisesRegex(ValueError, 'PROPOSAL_SIZE_BOUND'): x.d.same(views, views)
        with self.assertRaisesRegex(ValueError, 'PROPOSAL_SIZE_BOUND'): x.d.digest(views)
        self.assertEqual(self.prepared['state'], 'COMPILED_NOT_ADMITTED')
        self.assertEqual(self.prepared['unresolved'], [])
        self.assertIs(self.prepared['install_admission'], False)
        self.assertEqual(self.plan['host_contract']['production_acceptance'], 'PENDING')
        print('RESOURCE_AGGREGATE_MEASUREMENTS ' + json.dumps({
            'scope': 'SYNTHETIC_HOST_FACTS_REAL107_COMPILERS_NO_HOST_AUTHORITY',
            'historical_release_file_counts': [len(v['files']) for v in histories.values()],
            'historical_release_cache_counts': [len(v['caches']) for v in histories.values()],
            'views_bytes': len(x.json_bytes(views)),
            'largest_section_bytes': max(len(x.d.canonical(rows)) for view in views for rows in view.values()),
            'plan_bytes': len(x.packed(self.plan))}, sort_keys=True))

    def test_factory_recomputes_exact_large_plan_and_source_derived_views(self):
        with x.native_pins(self.seed):
            self.assertEqual(self.plan, x.factory.compile_host_contract(copy.deepcopy(self.inputs)))
            bad = copy.deepcopy(self.inputs)
            bad['resource_views'][-1]['historical'][-1]['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'SOURCE_DERIVED_COMPLETE_RESOURCE_VIEWS|UNREVIEWED_CROSS_PHASE_MUTATION'):
                x.factory.compile_host_contract(bad)

    def test_real_checkpoint_reads_last_view_without_any_host_reader_call(self):
        context, reader, resources = self.resources()
        result = resources.resources(context, x.observer.PHASES[-1], 'after', sorted(x.observer.SECTIONS))
        self.assertEqual(result, self.inputs['resource_views'][-1])
        self.assertEqual(reader.started, 1)
        self.assertEqual(len(reader.observed), sum(map(len, result.values())))

    def test_checkpoint_internal_late_mutation_refuses_before_read(self):
        context, reader, resources = self.resources()
        resources.views[-1]['historical'][-1]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'RESOURCE_CONTEXT_OR_MUTATION'):
            resources.resources(context, x.observer.PHASES[0], 'before', ['historical'])
        self.assertEqual((reader.started, reader.observed), (0, []))

    def test_checkpoint_constructor_defensive_copy_and_context_scope(self):
        views = copy.deepcopy(self.inputs['resource_views'])
        reader = NoEffectReader(self.inputs['resource_directories'])
        context = {'fixture': 1}
        resources = x.observer.CheckpointResources(context, reader, views,
                    self.plan['resource_observer']['views_sha256'])
        views[-1]['historical'][0]['kind'] = 'CHANGED_OUTSIDE_COPY'
        context['fixture'] = 2
        self.assertNotEqual(views, resources.views)
        with self.assertRaisesRegex(ValueError, 'RESOURCE_CONTEXT_OR_MUTATION'):
            resources.resources(context, x.observer.PHASES[0], 'before', ['historical'])
        self.assertEqual(reader.started, 0)

    def test_actual_host_observer_bind_plan_and_bound_accept_large_resources(self):
        unused_context, reader, resources = self.resources()
        instance = bind_host(self.plan, resources)
        self.assertIsNotNone(instance.bound_plan)
        self.assertEqual(instance.quiet.relay_metadata['uid'], 0)
        self.assertEqual(reader.started, 0)
        instance._bound()

    def test_actual_host_observer_bind_plan_rejects_late_checkpoint_hash_drift(self):
        unused_context, reader, resources = self.resources()
        changed = copy.deepcopy(self.plan)
        changed['live_controls']['checkpoints'][-1]['resources']['historical'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'HOST_OBSERVER_CHECKPOINT_VIEW_BINDING'):
            bind_host(changed, resources)
        self.assertEqual(reader.started, 0)

    def test_factory_rejects_late_derived_directory_mutation(self):
        changed = copy.deepcopy(self.inputs)
        directories = changed['resource_directories']
        directories[sorted(directories)[-1]][-1]['uid'] += 1
        with x.native_pins(self.seed), self.assertRaisesRegex(ValueError, 'SOURCE_DERIVED_COMPLETE_RESOURCE_VIEWS'):
            x.factory.compile_host_contract(changed)

    def test_actual_host_observer_rejects_old_directory_digest(self):
        unused_context, unused_reader, resources = self.resources()
        changed = copy.deepcopy(self.plan)
        changed['resource_observer']['directories_sha256'] = x.d.digest(self.inputs['resource_directories'])
        with self.assertRaisesRegex(ValueError, 'HOST_OBSERVER_EXACT_PLAN_BINDING'):
            bind_host(changed, resources)

    def test_actual_host_observer_bound_rechecks_mutated_directory_and_live_plan(self):
        for target in ('directory', 'contract'):
            unused_context, reader, resources = self.resources()
            instance = bind_host(self.plan, resources)
            if target == 'directory': reader.directories[sorted(reader.directories)[-1]][-1]['uid'] += 1
            else: instance.live_contract['checkpoints'][-1]['resources']['historical'] = '0' * 64
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'HOST_OBSERVER_PLAN_MUTATED'):
                instance._bound()
            self.assertEqual(reader.started, 0)


class WrapperRoundtripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.data, cls.topology, cls.entry = x.wrapper_modules()
        cls.seed, tools = x.wrapper_seed()
        inventory, cls.proposal, cls.review = x.synthetic_topology(cls.topology)
        cls.collected = {'observation': cls.seed['observation'], 'compiled': cls.seed['compiled'],
            'buffers': {key: cls.seed[key] for key in cls.data.RAW_PATHS},
            'manifest_raw': cls.seed['source_manifest_raw'], 'source_payloads': cls.seed['source_payloads'],
            'tool_sources': tools, 'socket_dropins': inventory,
            'fresh_unit_authority': {'schema': 1, 'kind': 'FRESH_R7_UNIT_DROPIN_AUTHORITY',
                'saved_unit_dropins_sha256': cls.data.sha(cls.data.canonical(inventory)),
                'units': {}, 'reread': 'EXACT_PRE_POST_AND_FINAL'},
            'fresh_release_parent': copy.deepcopy(cls.seed['fresh_release_parent'])}
        cache = {'xuanjun-p2-package/' + name: raw for name, raw in cls.seed['source_payloads'].items()}
        cache['xuanjun-p2-package/deploy/integration-manifest.json'] = cls.seed['source_manifest_raw']
        # Exact future target root is selected by the new entry's fixed constant.
        # Digest is labeled synthetic: wrapper publication pins are not rebased.
        cls.kit = cls.entry.VerifiedKit(cls.entry.CANDIDATE_PARENT + '/epoch7-recovery-candidate-r7-resourcebind',
            {'runtime_source_commit': x.factory.SOURCE, 'runtime_source_tree': x.factory.SOURCE_TREE,
             'runtime_manifest_sha256': x.factory.MANIFEST}, cache,
            x.d.digest('SYNTHETIC_TARGET_KIT_IDENTITY_NOT_PUBLISHED_AUTHORITY'))
        with x.native_pins(cls.seed):
            cls.bundle = cls.p.compile_private_bundle(cls.kit, cls.collected, cls.proposal['topology_raw'],
                cls.review, True, cls.data)

    def test_actual_wrapper_seed_serializer_same_target_hydration_and_C_contract(self):
        wire = json.loads(self.bundle['seed_raw'].decode('utf-8'))
        self.assertEqual(set(wire), {'schema', 'seed'})
        self.assertEqual(set(wire['seed']), self.entry.PRIVATE_SEED_FIELDS)
        hydrated = self.kit._hydrate_seed(wire['seed'], x.factory)
        self.assertEqual(hydrated['kit_manifest_sha256'], self.kit.digest)
        self.assertEqual(hydrated['artifact']['root'], self.kit.root + '/xuanjun-p2-package')
        self.assertEqual(hydrated['observation'], self.seed['observation'])
        with x.native_pins(self.seed):
            prepared = x.factory.prepare_host_inputs(hydrated)
            plan = x.factory.compile_host_contract(prepared['inputs'])
        self.assertEqual(x.packed(plan), self.bundle['plan_raw'])
        self.assertEqual(self.data.seed_wire(hydrated), self.bundle['seed_raw'])
        reader = NoEffectReader(prepared['inputs']['resource_directories'])
        resources = x.observer.CheckpointResources({}, reader, prepared['inputs']['resource_views'],
                    plan['resource_observer']['views_sha256'])
        bind_host(plan, resources)._bound()
        self.assertFalse(prepared['install_admission'])
        self.assertEqual(reader.started, 0)

    def test_actual_wrapper_publishes_and_rechecks_three_bounded_private_files(self):
        entry, proxy = x.local_publication_entry(self.entry)
        with tempfile.TemporaryDirectory(prefix='aggregate-private-', dir=str(x.HERE)) as directory:
            with mock.patch.object(self.p, 'os', proxy), mock.patch.object(self.p, 'CAND', directory):
                publication = self.p.publish_bundle(entry, self.bundle, self.proposal,
                    {'schema': 1, 'fixture_only': 'SYNTHETIC_SOURCE_MANIFEST_NOT_PUBLICATION'}, time.monotonic() + 60)
                self.p.verify_publication(entry, publication, time.monotonic() + 60)
                self.assertEqual(len(publication), 3)
                sizes = {}
                for row in publication:
                    raw = pathlib.Path(row['path']).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                    self.assertEqual(os.stat(row['path']).st_mode & 0o777, 0o600)
                    self.assertLessEqual(len(raw), publication.bounds[row['path']])
                    kind = 'seed' if 'resume-inputs' in row['path'] else ('packet' if 'review-packet' in row['path'] else 'plan')
                    sizes[kind + '_bytes'] = len(raw)
                self.assertLessEqual(sizes['plan_bytes'], x.LIMIT)
                self.assertLessEqual(sizes['seed_bytes'], 64 * 1024 * 1024)
                self.assertLessEqual(sizes['packet_bytes'], x.LIMIT)
                with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                    self.p.publish_bundle(entry, self.bundle, self.proposal, {}, time.monotonic() + 60)
                self.assertEqual(len(os.listdir(directory)), 3)
                print('WRAPPER_PUBLICATION_MEASUREMENTS ' + json.dumps(sizes, sort_keys=True))

    def test_same_private_seed_cannot_reuse_plan_on_a_different_target_kit_root(self):
        wire = json.loads(self.bundle['seed_raw'].decode('utf-8'))['seed']
        other = self.entry.VerifiedKit(self.kit.root + '-other', self.kit.manifest,
                                      self.kit.cache, self.kit.digest)
        hydrated = other._hydrate_seed(wire, x.factory)
        with x.native_pins(self.seed):
            prepared = x.factory.prepare_host_inputs(hydrated)
            plan = x.factory.compile_host_contract(prepared['inputs'])
        self.assertNotEqual(x.packed(plan), self.bundle['plan_raw'])
        self.assertEqual(plan['resource_observer'], json.loads(self.bundle['plan_raw'])['resource_observer'])

    def test_hydrated_late_historical_mutation_cannot_reuse_same_plan(self):
        wire = json.loads(self.bundle['seed_raw'].decode('utf-8'))['seed']
        history = wire['observation']['evidence']['retained']['release_evidence']
        history[sorted(history)[-1]]['files'][sorted(history[sorted(history)[-1]]['files'])[-1]]['sha256'] = '0' * 64
        hydrated = self.kit._hydrate_seed(wire, x.factory)
        with x.native_pins(self.seed), self.assertRaises(ValueError):
            x.factory.prepare_host_inputs(hydrated)


if __name__ == '__main__':
    unittest.main(verbosity=2)
