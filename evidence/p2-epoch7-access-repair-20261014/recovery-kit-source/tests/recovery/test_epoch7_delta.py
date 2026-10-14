"""Synthetic metadata tests only; no UK observation or production admission."""
import ast
import copy
import pathlib
import unittest

import epoch7_delta as d


def h(label):
    return d.digest(label)


def fixture():
    targets = {}
    for n, path in enumerate(sorted(d.TARGETS)):
        if path in d.OWNER_MASKS:
            targets[path] = {'kind': 'MASK', 'link': '/dev/null', 'dev': 1,
                             'ino': 100 + n, 'uid': 0, 'gid': 0}
        else:
            targets[path] = {'kind': 'FILE', 'sha256': h(path), 'uid': 0,
                'gid': 0, 'mode': 0o644, 'dev': 1, 'ino': 100 + n, 'nlink': 1}
    activation = {'schema': 1, 'state': 'PREPARED', 'epoch': 7, 'generation': 1,
        'release_sha256': d.OLD_MANIFEST, 'binary_sha256': d.OLD_BINARY,
        'config_sha256': targets['/etc/xuanjun-development/dispatcher.json']['sha256'],
        'ledger_uuid': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        'instance': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        'db_path': d.DB, 'ledger_socket': d.SOCKET}
    receipts = {name: h(name) for name in d.PRESERVED_RECEIPTS}
    s = {'schema': 1, 'transaction_id': d.TX, 'activation': activation,
        'epoch_journal_sha256': h('epoch7 journal'),
        'attempt': {'name': 'epoch5-recovery-execution.json',
            'sha256': receipts['epoch5-recovery-execution.json'], 'state': 'HOLD',
            'approval_id': 6170703284, 'consumed': True},
        'targets': targets, 'receipts': receipts,
        'tls': {'state': 'READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED',
            'journal_sha256': h('ready journal'), 'certificate_sha256': h('certificate'),
            'tree_fingerprint_sha256': h('tls tree'), 'config_identity_sha256': h('tls identity'),
            'release_sha256': d.OLD_MANIFEST},
        'cache_inventories': {
            '/opt/xuanjun-control-releases/integration-1111111111111111': h('original inventory'),
            '/opt/xuanjun-control-releases/integration-338e488c4203e23d': h('epoch3 inventory'),
            '/opt/xuanjun-control-releases/integration-' + d.OLD_MANIFEST[:16]: h('v4 inventory')},
        'retained_resource_sha256': h('all retained resources'),
        'generation': {'path': d.GENERATION, 'kind': 'DIRECTORY', 'uid': 1003,
            'gid': 1006, 'mode': 0o750, 'dev': 1, 'ino': 300,
            'access_acl': 'user::rwx\ngroup::r-x\nother::---\n', 'default_acl': ''},
        'database': {'path': d.DB, 'sha256': h('db bytes'), 'logical_manifest_sha256': h('db logical'),
            'dev': 1, 'ino': 301, 'uid': 0, 'gid': 0, 'mode': 0o600, 'nlink': 1, 'sidecars': []},
        'sandbox': {'state': 'RESTORED', 'journal_sha256': receipts['sandbox-profile.json'],
            'profile_sha256': h('original profile')},
        'plugin_state': 'VERIFIED_ABSENT', 'new_attempt_present': False,
        'absent_paths': {name: True for name in d.ABSENT_EFFECT_PATHS},
        'writer_exclusion': dict((key, True) for key in (
            'all_stopped', 'cgroups_empty', 'legacy_masks_preserved',
            'scheduler_excluded', 'runner_excluded', 'database_fds_excluded'))}
    s['writer_exclusion']['evidence_sha256'] = h('live exclusion')
    new_targets = {}
    for path, old in targets.items():
        new_targets[path] = {k: old[k] for k in ('kind', 'sha256', 'uid', 'gid', 'mode')} if old['kind'] == 'FILE' else {
            'kind': 'FILE', 'sha256': h('new ' + path), 'uid': 0, 'gid': 0, 'mode': 0o644}
    new_targets['/etc/xuanjun-development/dispatcher.json']['sha256'] = h('new dispatcher')
    new_activation = copy.deepcopy(activation)
    new_activation.update(epoch=8, release_sha256=d.NEW_MANIFEST, binary_sha256=d.NEW_BINARY,
                          config_sha256=h('new dispatcher'))
    c = {'manifest_sha256': d.NEW_MANIFEST, 'activation': new_activation,
         'targets': new_targets, 'tls_config_identity_sha256': h('tls identity')}
    return s, c


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.s, self.c = fixture()

    def build(self):
        return d.build_delta(self.s, d.digest(self.s), self.c)

    def bad_snapshot(self, mutate, reason=None):
        mutate(self.s)
        with self.assertRaisesRegex(ValueError, reason or '.'):
            self.build()

    def test_valid_proposal_has_no_admission_or_effects(self):
        x = self.build()
        self.assertEqual((x['effects'], x['authorized_attempts']), (0, 0))
        self.assertEqual(x['install_admission'], 'NOT_GRANTED')
        self.assertEqual((x['expected_epoch'], x['proposed_epoch']), (7, 8))
        self.assertEqual(len(x['changes']), 24)

    def test_inputs_are_not_modified(self):
        before = d.canonical([self.s, self.c]); self.build()
        self.assertEqual(before, d.canonical([self.s, self.c]))

    def test_exact_controller_transition_is_explicit_and_preserves_ledger_identity(self):
        transition = self.build()['controller_transition']
        self.assertEqual(transition, d.controller_transition(self.s['activation'], self.c['activation']))
        self.assertEqual(d.validate_controller_transition(transition), transition)
        self.assertEqual(transition['before']['binary_sha256'], d.OLD_BINARY)
        self.assertEqual(transition['after']['binary_sha256'], d.NEW_BINARY)
        self.assertEqual(transition['after']['release_sha256'], d.NEW_MANIFEST)
        self.assertEqual(transition['preserved_identity'],
                         {key:self.s['activation'][key] for key in d.CANONICAL_IDENTITY})

    def test_unknown_or_swapped_candidate_controller_release_pairs_rejected(self):
        for manifest, binary in ((d.NEW_MANIFEST, d.OLD_BINARY),
                (d.NEW_MANIFEST, h('unknown binary')), (d.OLD_MANIFEST, d.NEW_BINARY),
                (h('unknown manifest'), d.NEW_BINARY), (h('unknown manifest'), d.OLD_BINARY)):
            s, c = fixture(); c['manifest_sha256'] = manifest
            c['activation'].update(release_sha256=manifest, binary_sha256=binary)
            with self.assertRaises(ValueError): d.build_delta(s, d.digest(s), c)

    def test_old_snapshot_controller_release_state_are_not_rewritten(self):
        for update in ({'binary_sha256': d.NEW_BINARY}, {'binary_sha256': h('unknown')},
                {'release_sha256': d.NEW_MANIFEST}, {'state': 'ACTIVE'}, {'epoch': 8}):
            s, c = fixture(); s['activation'].update(update)
            with self.assertRaises(ValueError): d.build_delta(s, d.digest(s), c)

    def test_transition_evidence_cannot_forge_preserved_identity_or_schema(self):
        original = self.build()['controller_transition']
        for mutation in (lambda value:value.update(operation='RETAIN'),
                lambda value:value['preserved_identity'].update(instance='forged'),
                lambda value:value['after'].update(instance='cccccccc-cccc-4ccc-8ccc-cccccccccccc'),
                lambda value:value.update(extra=True)):
            value = copy.deepcopy(original); mutation(value)
            with self.assertRaises(ValueError): d.validate_controller_transition(value)

    def test_retained_resources_and_receipts_are_exact(self):
        x = self.build()
        self.assertEqual(x['preserve']['receipts'], self.s['receipts'])
        self.assertEqual(x['preserve']['database'], self.s['database'])
        self.assertEqual(x['preserve']['caches'], self.s['cache_inventories'])
        self.assertEqual(x['new_attempt_name'], 'epoch7-recovery-execution.json')

    def test_only_observed_two_masks_may_be_unmasked(self):
        rows = self.build()['changes']
        self.assertEqual({r['path'] for r in rows if r['operation'] == 'REPLACE_EXACT_OWNER_MASK'}, d.OWNER_MASKS)
        self.assertEqual(sum(r['operation'] == 'REPLACE_EXACT_FILE' for r in rows), 1)
        self.assertEqual(sum(r['operation'] == 'RETAIN' for r in rows), 21)

    def test_generation_change_is_only_mode_and_base_group_acl(self):
        x = self.build()['generation_change']
        changed = {k for k in x['before'] if x['before'][k] != x['after'][k]}
        self.assertEqual(changed, {'mode', 'access_acl'})
        self.assertEqual(x['after']['mode'], 0o700)
        self.assertFalse(x['recursive'])

    def test_tls_is_metadata_only_and_keeps_ready_state(self):
        x = self.build()['tls_change']
        self.assertEqual(x['retained_state'], self.s['tls']['state'])
        self.assertEqual(x['certificate_sha256'], self.s['tls']['certificate_sha256'])
        self.assertEqual((x['issuance_calls'], x['renewal_calls'], x['dry_run_calls']), (0, 0, 0))
        self.assertEqual(x['archive_name'], 'epoch7-prior-tls-lifecycle.json')

    def test_restored_sandbox_uses_new_journal(self):
        x = self.build()['sandbox_change']
        self.assertEqual(x['new_journal_name'], 'epoch7-sandbox-profile.json')
        self.assertEqual(x['preserve_journal_sha256'], self.s['receipts']['sandbox-profile.json'])

    def test_snapshot_digest_is_bound(self):
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_DIGEST'):
            d.build_delta(self.s, h('stale'), self.c)

    def test_old_epoch_cannot_be_blindly_reused(self):
        self.bad_snapshot(lambda s: s['activation'].update(epoch=5), 'EXACT_PREPARED')

    def test_active_state_cannot_be_treated_as_hold(self):
        self.bad_snapshot(lambda s: s['activation'].update(state='ACTIVE'), 'EXACT_PREPARED')

    def test_bool_epoch_schema_generation_rejected(self):
        for key in ('epoch', 'schema', 'generation'):
            s, c = fixture(); s['activation'][key] = True
            with self.assertRaises(ValueError): d.build_delta(s, d.digest(s), c)

    def test_consumed_attempt_cannot_disappear_or_reset(self):
        for change in ({'state': 'ADMITTED'}, {'consumed': False}, {'approval_id': 6167552232}):
            s, c = fixture(); s['attempt'].update(change)
            with self.assertRaisesRegex(ValueError, 'CONSUMED_ATTEMPT'):
                d.build_delta(s, d.digest(s), c)

    def test_existing_new_attempt_blocks_proposal(self):
        self.bad_snapshot(lambda s: s.update(new_attempt_present=True), 'UNCLASSIFIED_PRIOR_EFFECT')

    def test_unreached_or_new_journal_presence_is_not_reset(self):
        for name in d.ABSENT_EFFECT_PATHS:
            s, c = fixture(); s['absent_paths'][name] = False
            with self.assertRaisesRegex(ValueError, 'UNCLASSIFIED_EFFECT'):
                d.build_delta(s, d.digest(s), c)

    def test_absence_inventory_cannot_omit_a_path(self):
        self.bad_snapshot(lambda s: s['absent_paths'].pop('ledger-access.json'), 'ABSENCE_INVENTORY')

    def test_missing_old_receipt_blocks(self):
        self.bad_snapshot(lambda s: s['receipts'].pop('epoch6-runtime-provisioning.json'), 'PRESERVED_RECEIPT_SET')

    def test_attempt_hash_must_match_preserved_receipt(self):
        self.bad_snapshot(lambda s: s['attempt'].update(sha256=h('other')), 'ATTEMPT_RECEIPT_BINDING')

    def test_sandbox_journal_not_an_arbitrary_hash(self):
        self.bad_snapshot(lambda s: s['sandbox'].update(journal_sha256=h('other')), 'SANDBOX_RECEIPT_BINDING')

    def test_missing_target_blocks(self):
        self.bad_snapshot(lambda s: s['targets'].pop('/etc/systemd/system/nginx.service'), 'EXACT_24')

    def test_arbitrary_extra_target_blocks(self):
        self.bad_snapshot(lambda s: s['targets'].update({'/etc/shadow': {}}), 'EXACT_24')

    def test_nonowner_mask_rejected(self):
        self.bad_snapshot(lambda s: s['targets']['/etc/systemd/system/nginx.service'].update(kind='MASK'), 'REGULAR_FILE')

    def test_unknown_owner_mask_target_rejected(self):
        self.bad_snapshot(lambda s: s['targets'][sorted(d.OWNER_MASKS)[0]].update(link='/tmp/other'), 'EXACT_OWNER_MASK')

    def test_hardlinked_target_rejected(self):
        self.bad_snapshot(lambda s: s['targets']['/etc/systemd/system/nginx.service'].update(nlink=2), 'SINGLE_LINK')

    def test_existing_target_permissions_cannot_expand(self):
        self.c['targets']['/etc/systemd/system/nginx.service']['mode'] = 0o640
        with self.assertRaisesRegex(ValueError, 'PERMISSION_DELTA'): self.build()

    def test_candidate_config_must_match_activation(self):
        self.c['activation']['config_sha256'] = h('wrong')
        with self.assertRaisesRegex(ValueError, 'CANDIDATE_DISPATCHER'): self.build()

    def test_observed_config_must_match_activation(self):
        self.bad_snapshot(lambda s: s['activation'].update(config_sha256=h('wrong')), 'OBSERVED_DISPATCHER')

    def test_canonical_db_and_queue_identity_cannot_change(self):
        for key, value in (('ledger_uuid', 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'),
            ('instance', 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'), ('db_path', '/tmp/other.sqlite'),
            ('ledger_socket', '/tmp/other.sock'), ('binary_sha256', h('other binary'))):
            s, c = fixture(); c['activation'][key] = value
            with self.assertRaises(ValueError): d.build_delta(s, d.digest(s), c)

    def test_wrong_next_epoch_rejected(self):
        self.c['activation']['epoch'] = 9
        with self.assertRaisesRegex(ValueError, 'EXACT_PREPARED'): self.build()

    def test_same_release_not_a_new_candidate(self):
        self.c['manifest_sha256'] = d.OLD_MANIFEST
        with self.assertRaisesRegex(ValueError, 'NEW_MANIFEST'): self.build()

    def test_tls_hold_cannot_reenter_first_dryrun(self):
        self.bad_snapshot(lambda s: s['tls'].update(state='HOLD'), 'RETAIN_READY_TLS')

    def test_tls_identity_cannot_change(self):
        self.c['tls_config_identity_sha256'] = h('other account')
        with self.assertRaisesRegex(ValueError, 'TLS_OPERATIONAL'): self.build()

    def test_database_wal_or_ownership_drift_blocks(self):
        for change in ({'sidecars': ['-wal']}, {'uid': 1003}, {'mode': 0o640}, {'nlink': 2}):
            s, c = fixture(); s['database'].update(change)
            with self.assertRaises(ValueError): d.build_delta(s, d.digest(s), c)

    def test_generation_extended_acl_requires_separate_review(self):
        self.bad_snapshot(lambda s: s['generation'].update(access_acl=s['generation']['access_acl'] + 'user:1002:r-x\n'), 'EXTENDED_ACL')

    def test_generation_default_acl_requires_separate_review(self):
        self.bad_snapshot(lambda s: s['generation'].update(default_acl='default:user::rwx\n'), 'EXTENDED_ACL')

    def test_generation_already_0700_is_not_blindly_accepted(self):
        self.bad_snapshot(lambda s: s['generation'].update(mode=0o700), 'OWNER_MODE')

    def test_generation_owner_drift_blocks(self):
        self.bad_snapshot(lambda s: s['generation'].update(uid=0), 'OWNER_MODE')

    def test_fresh_plugin_effect_journal_is_mandatory(self):
        self.assertIn('epoch7-plugin-effects.json',d.ABSENT_EFFECT_PATHS)
        self.bad_snapshot(lambda s:s['absent_paths'].pop('epoch7-plugin-effects.json'),'ABSENCE_INVENTORY')

    def test_plugin_unknown_not_assumed_absent(self):
        self.bad_snapshot(lambda s: s.update(plugin_state='UNKNOWN'), 'UNCLASSIFIED_PRIOR_EFFECT')

    def test_sandbox_partial_or_applied_not_restored(self):
        self.bad_snapshot(lambda s: s['sandbox'].update(state='APPLIED'), 'RESTORED_SANDBOX')

    def test_unverified_exclusion_flags_block(self):
        for key in set(self.s['writer_exclusion']) - {'evidence_sha256'}:
            s, c = fixture(); s['writer_exclusion'][key] = 1
            with self.assertRaisesRegex(ValueError, 'EXCLUSION_UNPROVEN'):
                d.build_delta(s, d.digest(s), c)

    def test_v4_cache_inventory_cannot_be_omitted(self):
        self.bad_snapshot(lambda s: s['cache_inventories'].pop('/opt/xuanjun-control-releases/integration-' + d.OLD_MANIFEST[:16]), 'CACHE_INVENTORIES')

    def test_all_consumed_approval_ids_rejected(self):
        x = self.build()
        for review in d.CONSUMED | {True}:
            with self.assertRaisesRegex(ValueError, 'UNCONSUMED'):
                d.expected_review_binding(x, review, h('kit'), h('security'))

    def test_review_template_cannot_grant_permission(self):
        r = d.expected_review_binding(self.build(), 7000000000, h('kit'), h('security'))
        self.assertFalse(r['authorization_verified'])
        self.assertEqual(r['install_admission'], 'NOT_GRANTED')

    def test_generation_receipt_requires_same_inode_and_exact_binding(self):
        delta = self.build(); x = delta['generation_change']
        receipt = {'state': 'DONE', 'delta_sha256': d.digest(delta),
            'snapshot_sha256': delta['snapshot_sha256'], 'approval_body_sha256': h('approval'),
            'before_sha256': d.digest(x['before']), 'after_sha256': d.digest(x['after'])}
        result = d.validate_generation_receipt(delta, x['before'], x['after'], receipt)
        self.assertTrue(result['postcondition_consistent'])
        self.assertFalse(result['authorization_verified'])
        for key, value in (('ino', 999), ('uid', 0), ('mode', 0o750)):
            bad = copy.deepcopy(x['after']); bad[key] = value
            with self.assertRaisesRegex(ValueError, 'GENERATION_METADATA_DRIFT'):
                d.validate_generation_receipt(delta, x['before'], bad, receipt)
        receipt['state'] = 'INTENT'
        with self.assertRaisesRegex(ValueError, 'RECEIPT_BINDING'):
            d.validate_generation_receipt(delta, x['before'], x['after'], receipt)


class TlsAndPurityTests(unittest.TestCase):
    def test_release_only_tls_rebind(self):
        before = {'release_sha256': d.OLD_MANIFEST, 'domain': 'fixture.invalid',
                  'accept_acme_terms': True, 'root': '/fixture'}
        after = dict(before, release_sha256=h('new'))
        out = d.tls_config_rebind(before, after)
        self.assertFalse(out['action_applied'])
        self.assertEqual((out['issuance_calls'], out['renewal_calls'], out['dry_run_calls']), (0, 0, 0))

    def test_tls_operational_and_type_change_rejected(self):
        before = {'release_sha256': d.OLD_MANIFEST, 'accept_acme_terms': True}
        for value in (False, 1):
            after = dict(before, release_sha256=h('new'), accept_acme_terms=value)
            with self.assertRaisesRegex(ValueError, 'OPERATIONAL_IDENTITY'):
                d.tls_config_rebind(before, after)

    def test_module_has_only_pure_stdlib_imports_and_no_io_calls(self):
        source = pathlib.Path(d.__file__).read_text()
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {'copy', 'hashlib', 'json', 're', 'uuid'})
        self.assertFalse(any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)))
        forbidden = {'open', 'exec', 'eval', 'compile', '__import__', 'input'}
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse(forbidden & calls)


if __name__ == '__main__':
    unittest.main()
