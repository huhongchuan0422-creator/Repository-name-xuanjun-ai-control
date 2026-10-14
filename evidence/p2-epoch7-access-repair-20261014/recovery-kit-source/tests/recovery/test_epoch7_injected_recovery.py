"""In-memory adapter tests. They do not authenticate reviews or touch UK files."""
import copy
import json
import unittest

import epoch7_delta as d
import epoch7_injected_recovery as r
from test_epoch7_delta import fixture, h


class FakeVerifier(object):
    def __init__(self):
        self.reject = False
        self.body = h('synthetic reviewer body')
        self.calls = 0
        self.binding_mutator = None

    def verify_exact(self, review_id, expected):
        self.calls += 1
        if self.reject:
            raise ValueError('FAKE_REVIEW_DENIED')
        binding = copy.deepcopy(expected)
        if self.binding_mutator:
            self.binding_mutator(binding)
        return {'review_id': review_id, 'body_sha256': self.body, 'binding': binding}


class FakeOps(object):
    def __init__(self, snapshot):
        self.snapshot = copy.deepcopy(snapshot)
        self.targets = copy.deepcopy(snapshot['targets'])
        self.preserved = None
        self.files = {p: ('old:' + p).encode() for p, v in self.targets.items() if v['kind'] == 'FILE'}
        self.journals = {}
        self.backups = {}
        self.events = []
        self.lock = True
        self.ino = 1000
        self.fail = None
        self.activation = copy.deepcopy(snapshot['activation'])
        self.exclusion = copy.deepcopy(snapshot['writer_exclusion'])
        self.before_replace = None

    def install_lock_held(self): return self.lock
    def read_preserved_pins(self): return copy.deepcopy(self.preserved)
    def read_activation_evidence(self):
        return {'descriptor': copy.deepcopy(self.activation),
                'preserved_epoch7_prefix_sha256': self.snapshot['epoch_journal_sha256']}
    def read_generation(self): return copy.deepcopy(self.snapshot['generation'])
    def read_sandbox(self): return copy.deepcopy(self.snapshot['sandbox'])
    def read_targets(self): return copy.deepcopy(self.targets)
    def read_writer_exclusion(self): return copy.deepcopy(self.exclusion)
    def journal_exists(self, name): return name in self.journals
    def read_journal(self, name): return copy.deepcopy(self.journals[name])

    def record(self, raw, uid=0, gid=0, mode=0o600):
        self.ino += 1
        return {'data': raw, 'uid': uid, 'gid': gid, 'mode': mode,
                'dev': 1, 'ino': self.ino, 'nlink': 1}

    def create_exclusive(self, name, raw, uid, gid, mode):
        self.events.append(('create', name))
        if name in self.journals: raise ValueError('FAKE_O_EXCL')
        self.journals[name] = self.record(raw, uid, gid, mode)
        if self.fail == 'create_uncertain': raise OSError('FAKE_FSYNC_UNCERTAIN')

    def replace_exact(self, name, expected, raw, uid, gid, mode):
        self.events.append(('journal_replace', name))
        if self.journals[name] != expected: raise ValueError('FAKE_JOURNAL_CAS')
        self.journals[name] = self.record(raw, uid, gid, mode)
        if self.fail == 'journal_uncertain': raise OSError('FAKE_REPLACE_UNCERTAIN')

    def backup_target_exact(self, path, expected, name):
        self.events.append(('backup', path))
        if self.targets[path] != expected: raise ValueError('FAKE_TARGET_CAS')
        if name in self.backups: raise ValueError('FAKE_BACKUP_O_EXCL')
        if self.fail == 'backup': raise OSError('FAKE_BACKUP_FAILURE')
        if expected['kind'] == 'FILE':
            raw = self.files[path]
            if r.byte_digest(raw) != expected['sha256']: raise ValueError('FAKE_OLD_BYTES_CHANGED')
            wanted = r.byte_digest(raw)
        else:
            raw = d.canonical(expected); wanted = d.digest(expected)
        self.backups[name] = self.record(raw)
        return {'name': name, 'sha256': wanted, 'kind': expected['kind']}

    def replace_target_exact(self, path, expected, raw, after):
        self.events.append(('target_replace', path))
        if self.before_replace: self.before_replace(self, path)
        if self.targets[path] != expected: raise ValueError('FAKE_TARGET_CAS')
        self.ino += 1
        self.targets[path] = dict(after, dev=1, ino=self.ino, nlink=1)
        self.files[path] = raw
        if self.fail == 'target_uncertain': raise OSError('FAKE_TARGET_RESULT_UNKNOWN')
        if self.fail == 'target_wrong_mode': self.targets[path]['mode'] = 0o666

    def read_target(self, path): return copy.deepcopy(self.targets[path])


def prepared():
    s, c = fixture()
    payloads = {}
    for path, row in s['targets'].items():
        if row['kind'] == 'FILE':
            row['sha256'] = r.byte_digest(('old:' + path).encode())
            c['targets'][path]['sha256'] = row['sha256']
        if path in d.OWNER_MASKS or path.endswith('/dispatcher.json'):
            raw = ('new:' + path).encode(); payloads[path] = raw
            c['targets'][path]['sha256'] = r.byte_digest(raw)
    s['activation']['config_sha256'] = s['targets']['/etc/xuanjun-development/dispatcher.json']['sha256']
    c['activation']['config_sha256'] = c['targets']['/etc/xuanjun-development/dispatcher.json']['sha256']
    prior_rows = []
    for path, row in sorted(s['targets'].items()):
        prior_rows.append({'target': path,
            'rendered_sha256': row.get('sha256', h('prior rendered ' + path)),
            'uid': 0, 'gid': 0, 'mode': 0o644,
            'previous': {'masked': True} if path in d.OWNER_MASKS else None})
    prior = d.canonical({'schema': 1, 'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY',
        'rollback_complete': False, 'targets': prior_rows}) + b'\n'
    s['receipts']['epoch6-runtime-provisioning.json'] = r.byte_digest(prior)
    ops = FakeOps(s); verifier = FakeVerifier()
    gate = r.RecoveryGate(s, c, d.digest(s), h('kit'), h('security'), 7000000000, verifier, ops, prior)
    ops.prior_provision_bytes = prior
    ops.preserved = copy.deepcopy(gate.preserved)
    return s, c, ops, verifier, gate, payloads


class GateTests(unittest.TestCase):
    def setUp(self): self.s, self.c, self.ops, self.verifier, self.gate, self.payloads = prepared()

    def test_exact_new_review_bound_to_all_proposal_hashes(self):
        result = self.gate.check()
        self.assertEqual(result['binding']['snapshot_sha256'], d.digest(self.s))
        self.assertEqual(result['binding']['delta_sha256'], d.digest(self.gate.delta))
        self.assertEqual(result['binding']['authorized_attempts'], 1)
        self.assertFalse(result['binding']['tls_issuance_renewal_or_dry_run'])

    def test_no_default_verifier_or_guards(self):
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_VERIFIER'):
            r.RecoveryGate(self.s, self.c, d.digest(self.s), h('kit'), h('security'), 7000000000, None, self.ops, self.ops.prior_provision_bytes)

    def test_consumed_review_cannot_create_gate(self):
        with self.assertRaisesRegex(ValueError, 'FRESH_REVIEW'):
            r.RecoveryGate(self.s, self.c, d.digest(self.s), h('kit'), h('security'), 6170703284, self.verifier, self.ops, self.ops.prior_provision_bytes)

    def test_lock_must_be_true_not_truthy(self):
        self.ops.lock = 1
        with self.assertRaisesRegex(ValueError, 'INSTALL_LOCK'): self.gate.check()

    def test_verifier_denial_blocks(self):
        self.verifier.reject = True
        with self.assertRaisesRegex(ValueError, 'REVIEW_DENIED'): self.gate.check()

    def test_boolean_or_changed_exact_binding_denied(self):
        self.verifier.binding_mutator = lambda b: b.update(authorized_attempts=True)
        with self.assertRaisesRegex(ValueError, 'EXACT_NEW_REVIEW'): self.gate.check()

    def test_review_body_change_after_verification_denied(self):
        self.gate.check(); self.verifier.body = h('changed')
        with self.assertRaisesRegex(ValueError, 'REVIEW_CHANGED'): self.gate.check()

    def test_any_preserved_receipt_change_denied(self):
        self.ops.preserved['receipts']['epoch5-recovery-execution.json'] = h('reset')
        with self.assertRaisesRegex(ValueError, 'PRESERVED_STATE_DRIFT'): self.gate.check()

    def test_tls_tree_or_certificate_change_denied(self):
        self.ops.preserved['tls']['certificate_sha256'] = h('new certificate')
        with self.assertRaisesRegex(ValueError, 'PRESERVED_STATE_DRIFT'): self.gate.check()

    def test_active_or_unreviewed_epoch_denied(self):
        self.ops.activation['state'] = 'ACTIVE'
        with self.assertRaisesRegex(ValueError, 'NONACTIVE_EPOCH'): self.gate.check()
        self.ops.activation = dict(self.c['activation'], epoch=9)
        with self.assertRaisesRegex(ValueError, 'NONACTIVE_EPOCH'): self.gate.check()

    def test_reviewed_epoch8_prepared_and_quiesced_are_supported(self):
        for state in ('PREPARED', 'QUIESCED'):
            self.ops.activation = dict(self.c['activation'], state=state)
            self.gate.check()

    def test_generation_or_sandbox_changed_phase_denied(self):
        self.ops.snapshot['generation']['mode'] = 0o700
        with self.assertRaisesRegex(ValueError, 'TARGET_PHASE'): self.gate.check()

    def test_writer_or_fd_exclusion_false_denied(self):
        self.ops.exclusion['database_fds_excluded'] = False
        with self.assertRaisesRegex(ValueError, 'LIVE_WRITER_EXCLUSION'): self.gate.check()

    def test_before_state_inode_drift_denied(self):
        self.ops.targets['/etc/systemd/system/nginx.service']['ino'] += 1
        with self.assertRaisesRegex(ValueError, 'CURRENT_TARGET_STATE_DRIFT'): self.gate.check()

    def test_internal_preserved_mutation_denied(self):
        self.gate.preserved['tls']['certificate_sha256'] = h('changed')
        self.ops.preserved = copy.deepcopy(self.gate.preserved)
        with self.assertRaisesRegex(ValueError, 'GATE_BINDING_MUTATED'): self.gate.check()

    def test_internal_candidate_mutation_cannot_allow_active(self):
        self.gate.candidate['activation']['state'] = 'ACTIVE'
        self.ops.activation = copy.deepcopy(self.gate.candidate['activation'])
        with self.assertRaisesRegex(ValueError, 'GATE_BINDING_MUTATED'): self.gate.check()

    def test_internal_snapshot_mutation_denied(self):
        self.gate.snapshot['epoch_journal_sha256'] = h('other journal')
        with self.assertRaisesRegex(ValueError, 'GATE_BINDING_MUTATED'): self.gate.check()

    def test_internal_delta_mutation_denied(self):
        self.gate.delta['automatic_retry'] = True
        with self.assertRaisesRegex(ValueError, 'GATE_BINDING_MUTATED'): self.gate.check()


class ProvisionBindingTests(unittest.TestCase):
    def setUp(self):
        self.s, self.c, self.ops, self.verifier, self.gate, self.payloads = prepared()
        self.raw = self.ops.prior_provision_bytes

    def changed_receipt(self, mutate):
        value = json.loads(self.raw.decode()); mutate(value)
        raw = d.canonical(value) + b'\n'
        self.s['receipts']['epoch6-runtime-provisioning.json'] = r.byte_digest(raw)
        return raw

    def test_current_target_set_bound_to_exact_provision_receipt(self):
        result = d.validate_provision_before(self.s, self.raw)
        self.assertEqual((result['retained_regular_files'], result['restored_owner_masks']), (22, 2))
        self.assertFalse(result['host_provenance_verified'])

    def test_wrong_receipt_raw_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, 'RAW_HASH'):
            d.validate_provision_before(self.s, self.raw + b' ')

    def test_rehashed_receipt_cannot_disguise_target_drift(self):
        raw = self.changed_receipt(lambda v: v['targets'][0].update(rendered_sha256=h('drift')))
        with self.assertRaisesRegex(ValueError, 'DIFFERS_FROM_V4_RECEIPT'):
            d.validate_provision_before(self.s, raw)

    def test_two_masks_must_have_prior_mask_origin(self):
        def mutate(v):
            row = next(x for x in v['targets'] if x['target'] in d.OWNER_MASKS)
            row['previous'] = None
        raw = self.changed_receipt(mutate)
        with self.assertRaisesRegex(ValueError, 'OWNER_MASK_ORIGIN'):
            d.validate_provision_before(self.s, raw)

    def test_duplicate_target_path_rejected(self):
        raw = self.changed_receipt(lambda v: v['targets'].__setitem__(1, copy.deepcopy(v['targets'][0])))
        with self.assertRaisesRegex(ValueError, 'TARGET_SET'):
            d.validate_provision_before(self.s, raw)

    def test_duplicate_json_key_rejected_even_with_matching_hash(self):
        raw = self.raw.replace(b'"schema":1', b'"schema":1,"schema":1', 1)
        self.s['receipts']['epoch6-runtime-provisioning.json'] = r.byte_digest(raw)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_KEY'):
            d.validate_provision_before(self.s, raw)

    def test_old_generic_rollback_receipt_not_accepted(self):
        raw = self.changed_receipt(lambda v: v.update(rollback_complete=True))
        with self.assertRaisesRegex(ValueError, 'RETAIN_POLICY'):
            d.validate_provision_before(self.s, raw)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.s, self.c, self.ops, self.verifier, self.gate, self.payloads = prepared()
        self.j = r.BoundJournal(r.ATTEMPT, self.gate, self.ops)

    def test_create_and_save_protected_bound_journal(self):
        self.j.create({'stage': 'ADMITTED'}); self.j.save({'stage': 'TEST_INTENT'})
        value = json.loads(self.ops.journals[r.ATTEMPT]['data'].decode())
        self.assertEqual(value['binding']['delta_sha256'], self.gate.delta_sha256)
        self.assertEqual(value['state']['stage'], 'TEST_INTENT')
        self.assertEqual(self.ops.journals[r.ATTEMPT]['mode'], 0o600)

    def test_old_attempt_name_never_accepted(self):
        with self.assertRaisesRegex(ValueError, 'EXACT_NEW_JOURNAL'):
            r.BoundJournal('epoch5-recovery-execution.json', self.gate, self.ops)

    def test_existing_attempt_blocks_without_overwriting(self):
        self.ops.journals[r.ATTEMPT] = self.ops.record(b'old uncertain attempt')
        prior = copy.deepcopy(self.ops.journals)
        with self.assertRaisesRegex(ValueError, 'EXISTING_ATTEMPT'): self.j.create({'stage': 'ADMITTED'})
        self.assertEqual(prior, self.ops.journals)
        self.assertEqual(self.ops.events, [])

    def test_save_before_create_denied(self):
        with self.assertRaisesRegex(ValueError, 'UNCLAIMED'): self.j.save({'stage': 'HOLD'})

    def test_create_uncertain_is_poisoned_no_retry(self):
        self.ops.fail = 'create_uncertain'
        with self.assertRaises(OSError): self.j.create({'stage': 'ADMITTED'})
        self.assertTrue(self.j.poisoned); self.assertIn(r.ATTEMPT, self.ops.journals)
        self.ops.fail = None
        with self.assertRaisesRegex(ValueError, 'CANNOT_RESUME'): self.j.create({'stage': 'ADMITTED'})

    def test_save_uncertain_is_poisoned_no_retry(self):
        self.j.create({'stage': 'ADMITTED'}); self.ops.fail = 'journal_uncertain'
        with self.assertRaises(OSError): self.j.save({'stage': 'HOLD'})
        self.assertTrue(self.j.poisoned)
        with self.assertRaisesRegex(ValueError, 'UNCLAIMED_OR_UNCERTAIN'): self.j.save({'stage': 'HOLD'})

    def test_journal_inode_drift_denied(self):
        self.j.create({'stage': 'ADMITTED'}); self.ops.journals[r.ATTEMPT]['ino'] += 1
        with self.assertRaisesRegex(ValueError, 'JOURNAL_CAS_DRIFT'): self.j.save({'stage': 'NEXT'})

    def test_journal_hardlink_denied(self):
        self.j.create({'stage': 'ADMITTED'}); self.ops.journals[r.ATTEMPT]['nlink'] = 2
        with self.assertRaisesRegex(ValueError, 'PROTECTED_JOURNAL'): self.j.save({'stage': 'NEXT'})

    def test_readback_corruption_is_not_success(self):
        original = self.ops.create_exclusive
        def corrupt(*args):
            original(*args); self.ops.journals[r.ATTEMPT]['data'] = b'{"bogus":1}\n'
        self.ops.create_exclusive = corrupt
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_UNCONFIRMED'): self.j.create({'stage': 'ADMITTED'})
        self.assertTrue(self.j.poisoned)

    def test_lost_lock_stops_further_journal_writes(self):
        self.j.create({'stage': 'ADMITTED'}); self.ops.lock = False
        count = len(self.ops.events)
        with self.assertRaisesRegex(ValueError, 'INSTALL_LOCK'): self.j.save({'stage': 'NEXT'})
        self.assertEqual(len(self.ops.events), count)


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.s, self.c, self.ops, self.verifier, self.gate, self.payloads = prepared()
        self.attempt = r.BoundJournal(r.ATTEMPT, self.gate, self.ops)
        self.applier = r.RetainedTargetDelta(self.gate, self.attempt, self.ops)

    def admitted(self): self.attempt.create({'stage': 'ADMITTED'})

    def test_no_target_effect_without_consumed_new_attempt(self):
        with self.assertRaisesRegex(ValueError, 'FRESH_ADMITTED'): self.applier.apply(self.payloads)
        self.assertEqual(self.ops.events, [])

    def test_exact_changed_set_only_keeps_21_other_inodes(self):
        self.admitted(); before = copy.deepcopy(self.ops.targets)
        preserved = copy.deepcopy(self.ops.preserved)
        result = self.applier.apply(self.payloads)
        self.assertEqual((result['changed_targets'], result['retained_targets']), (3, 21))
        self.assertEqual(result['tls_calls'], 0)
        self.assertFalse(result['prior_receipts_rewritten']); self.assertFalse(result['legacy_restart'])
        for path in d.TARGETS - set(self.payloads): self.assertEqual(before[path], self.ops.targets[path])
        self.assertEqual(preserved, self.ops.preserved)
        self.assertEqual(len(self.ops.backups), 3)
        self.assertEqual(self.attempt.state['stage'], 'TARGET_DELTA_COMPLETE')

    def test_every_effect_has_durable_attempt_and_target_intent(self):
        self.admitted()
        def inspect(ops, path):
            a = json.loads(ops.journals[r.ATTEMPT]['data'].decode())
            p = json.loads(ops.journals[r.PROVISION]['data'].decode())
            self.assertEqual(a['state']['stage'], 'TARGET_DELTA_INTENT')
            row = [x for x in p['state']['targets'] if x['path'] == path][0]
            self.assertEqual(row['state'], 'REPLACE_INTENT')
            self.assertIn(row['backup']['name'], ops.backups)
        self.ops.before_replace = inspect
        self.applier.apply(self.payloads)

    def test_wrong_payload_hash_before_any_phase_effect(self):
        self.admitted(); before = list(self.ops.events)
        self.payloads[sorted(self.payloads)[-1]] = b'changed'
        with self.assertRaisesRegex(ValueError, 'PAYLOAD_HASH'): self.applier.apply(self.payloads)
        self.assertEqual(before, self.ops.events)

    def test_extra_or_missing_payload_denied(self):
        self.admitted(); self.payloads['/tmp/arbitrary'] = b'bad'
        with self.assertRaisesRegex(ValueError, 'PAYLOAD_SET'): self.applier.apply(self.payloads)
        self.assertNotIn(r.PROVISION, self.ops.journals)

    def test_existing_provision_journal_not_reset(self):
        self.admitted(); self.ops.journals[r.PROVISION] = self.ops.record(b'old')
        with self.assertRaisesRegex(ValueError, 'EXISTING_PROVISION'): self.applier.apply(self.payloads)
        self.assertEqual(self.ops.journals[r.PROVISION]['data'], b'old')

    def test_backup_failure_retains_intent_no_target_replacement(self):
        self.admitted(); self.ops.fail = 'backup'
        with self.assertRaises(OSError): self.applier.apply(self.payloads)
        self.assertFalse(any(x[0] == 'target_replace' for x in self.ops.events))
        state = json.loads(self.ops.journals[r.PROVISION]['data'].decode())['state']
        self.assertEqual(state['targets'][0]['state'], 'BACKUP_INTENT')
        with self.assertRaisesRegex(ValueError, 'FRESH_ADMITTED'): self.applier.apply(self.payloads)

    def test_target_result_unknown_retains_replace_intent_no_retry(self):
        self.admitted(); self.ops.fail = 'target_uncertain'
        with self.assertRaises(OSError): self.applier.apply(self.payloads)
        state = json.loads(self.ops.journals[r.PROVISION]['data'].decode())['state']
        self.assertEqual(state['targets'][0]['state'], 'REPLACE_INTENT')
        self.assertEqual(sum(x[0] == 'target_replace' for x in self.ops.events), 1)
        self.assertEqual(len(self.ops.backups), 1)
        with self.assertRaisesRegex(ValueError, 'FRESH_ADMITTED'): self.applier.apply(self.payloads)

    def test_target_cas_race_rejected(self):
        self.admitted()
        self.ops.before_replace = lambda ops, path: ops.targets[path].update(ino=9999)
        with self.assertRaisesRegex(ValueError, 'TARGET_CAS'): self.applier.apply(self.payloads)

    def test_wrong_post_mode_is_not_done(self):
        self.admitted(); self.ops.fail = 'target_wrong_mode'
        with self.assertRaisesRegex(ValueError, 'ROOT_PROTECTED_TARGET'): self.applier.apply(self.payloads)
        state = json.loads(self.ops.journals[r.PROVISION]['data'].decode())['state']
        self.assertEqual(state['targets'][0]['state'], 'REPLACE_INTENT')

    def test_lost_authorization_mid_phase_stops_next_effect(self):
        self.admitted()
        def revoke(ops, path): self.verifier.reject = True
        self.ops.before_replace = revoke
        with self.assertRaisesRegex(ValueError, 'REVIEW_DENIED'): self.applier.apply(self.payloads)
        self.assertEqual(sum(x[0] == 'target_replace' for x in self.ops.events), 1)

    def test_complete_phase_cannot_be_run_twice(self):
        self.admitted(); self.applier.apply(self.payloads)
        with self.assertRaisesRegex(ValueError, 'FRESH_ADMITTED'): self.applier.apply(self.payloads)

    def test_old_snapshot_target_drift_stops_before_effects(self):
        self.admitted(); self.ops.targets['/etc/systemd/system/nginx.service']['sha256'] = h('drift')
        before = list(self.ops.events)
        with self.assertRaisesRegex(ValueError, 'TARGET_STATE_DRIFT'): self.applier.apply(self.payloads)
        self.assertEqual(before, self.ops.events)


if __name__ == '__main__': unittest.main()
