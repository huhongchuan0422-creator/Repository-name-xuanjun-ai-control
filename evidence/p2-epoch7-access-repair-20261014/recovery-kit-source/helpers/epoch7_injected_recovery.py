"""Injectable retained-target/journal mechanics; no host entrypoint or CLI.

This module cannot touch a filesystem or authenticate a review by itself.
Verifier and guards must be supplied by the separately reviewed outer loader.
Tests use fake in-memory operations. Never substitute booleans for that loader.
All phase effects require the bound review, held install lock, current pins and
writer exclusion on every check. Uncertain writes retain INTENT and cannot resume.
"""
import copy
import hashlib
import json

import epoch7_delta as d
import epoch7_additive_identity as additive
import epoch7_additive_server as server_additive

ATTEMPT = 'epoch7-recovery-execution.json'
PROVISION = 'epoch8-runtime-provisioning.json'
JOURNALS = frozenset((ATTEMPT, PROVISION, 'epoch7-generation-access.json',
                     'epoch7-owner-identity-publication.json', 'epoch7-server-identity-publication.json'))
DECISION = 'APPROVED_ONE_EXACT_EPOCH7_RETAINED_RECOVERY'


def byte_digest(raw):
    d.need(isinstance(raw, bytes), 'BYTES_REQUIRED')
    return hashlib.sha256(raw).hexdigest()


def required_authorization(delta, kit_sha256, security_sha256, additions):
    d.hash_value(kit_sha256); d.hash_value(security_sha256)
    return {'schema': 1, 'decision': DECISION, 'transaction_id': d.TX,
        'expected_epoch': 7, 'proposed_prepared_epoch': 8, 'authorized_attempts': 1,
        'delta_sha256': d.digest(delta), 'snapshot_sha256': delta['snapshot_sha256'],
        'complete_delta_sha256': d.digest({'retained_delta': delta, 'additive_targets': additions}),
        'additive_targets_sha256': d.digest(additions),
        'additive_targets': [{'path': x['path'], 'uid': x['after']['uid'], 'gid': x['after']['gid'],
            'mode': x['after']['mode'], 'sha256': x['after']['sha256'],
            'provenance_sha256': d.digest(x['provenance'])} for x in additions],
        'retained_target_count': 24, 'total_target_count': 24 + len(additions),
        'candidate_sha256': delta['candidate_sha256'],
        'runtime_manifest_sha256': delta['runtime_manifest_sha256'],
        'kit_manifest_sha256': kit_sha256, 'security_delta_sha256': security_sha256,
        'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY', 'automatic_retry': False,
        'legacy_restart': False, 'historical_notification_replay': False,
        'tls_issuance_renewal_or_dry_run': False,
        'production_acceptance': 'PENDING'}


class RecoveryGate(object):
    """Require external provenance verification; no default verifier or guards.

    verifier.verify_exact(review_id, expected) must authenticate owner/reviewer,
    destination, exact raw body and current one-attempt authority externally.
    A dict equality check is not authentication. This class only binds that
    verified response to the immutable proposal and checks live adapter evidence.
    """
    def __init__(self, snapshot, candidate, snapshot_sha256, kit_sha256,
                 security_sha256, review_id, verifier, guards, prior_provision_bytes,
                 additive_delta=None, additive_deltas=None):
        d.need(type(review_id) is int and review_id > 0 and review_id not in d.CONSUMED,
               'FRESH_REVIEW_REQUIRED')
        d.need(verifier is not None and guards is not None, 'EXTERNAL_VERIFIER_AND_GUARDS_REQUIRED')
        self.snapshot = d.validate_snapshot(snapshot, snapshot_sha256)
        d.validate_provision_before(self.snapshot, prior_provision_bytes)
        self.candidate = copy.deepcopy(candidate)
        self.snapshot_sha256 = d.digest(self.snapshot)
        self.candidate_sha256 = d.digest(self.candidate)
        self.delta = d.build_delta(snapshot, snapshot_sha256, candidate)
        self.delta_sha256 = d.digest(self.delta)
        d.need(additive_delta is None or additive_deltas is None, 'ONE_ADDITIVE_INPUT_FORM')
        proposals = ([additive_delta] if additive_delta is not None else
                     ([] if additive_deltas is None else additive_deltas))
        d.need(isinstance(proposals, list) and len(proposals) <= 2, 'EXACT_TWO_ADDITIVE_SCOPE')
        self.additions = []
        paths = set()
        for proposal in proposals:
            d.need(isinstance(proposal, dict), 'EXPLICIT_ADDITIVE_PROPOSAL_REQUIRED')
            path = proposal.get('path')
            d.need(path not in paths and path in (additive.PATH, server_additive.PATH), 'EXACT_UNIQUE_ADDITIVE_PATH')
            compiler = additive if path == additive.PATH else server_additive
            value = compiler.validate_compiled(proposal, candidate['manifest_sha256'])
            if path == additive.PATH:
                d.need(candidate['targets'][additive.UNIT]['sha256'] ==
                       value['provenance']['rendered_unit_sha256'], 'ADDITIVE_OWNER_UNIT_CANDIDATE_BINDING')
            else:
                binding = {k: candidate['activation'][k] for k in server_additive.BINDING_KEYS}
                d.need(value['provenance']['activation_binding_sha256'] == d.digest(binding), 'SERVER_EXACT_CANDIDATE_BINDING')
                for source, sha in value['provenance']['source_files'].items():
                    if source in d.TARGETS:
                        d.need(candidate['targets'][source]['sha256'] == sha, 'SERVER_CANDIDATE_SOURCE_BINDING')
            self.additions.append(value); paths.add(path)
        self.additions.sort(key=lambda item: item['path'])
        self.additions_sha256 = d.digest(self.additions)
        self.expected = required_authorization(self.delta, kit_sha256, security_sha256, self.additions)
        self.expected_sha256 = d.digest(self.expected)
        self.review_id, self.verifier, self.guards = review_id, verifier, guards
        self.authorization = None
        self.current_targets = copy.deepcopy(snapshot['targets'])
        self.current_generation = copy.deepcopy(snapshot['generation'])
        self.current_additive_targets = {x["path"]: None for x in self.additions}
        self.preserved = copy.deepcopy(self.delta['preserve'])

    def check(self):
        d.need(d.digest(self.snapshot) == self.snapshot_sha256 and
               d.digest(self.candidate) == self.candidate_sha256 and
               d.same(self.preserved, self.delta["preserve"]) and
               d.digest(self.delta) == self.delta_sha256 and
               d.digest(self.expected) == self.expected_sha256 and
               d.digest(self.additions) == self.additions_sha256, 'GATE_BINDING_MUTATED')
        d.need(self.guards.install_lock_held() is True, 'INSTALL_LOCK_REQUIRED')
        review = self.verifier.verify_exact(self.review_id, copy.deepcopy(self.expected))
        d.keys(review, ('review_id', 'body_sha256', 'binding'), 'VERIFIED_REVIEW_SHAPE')
        d.need(type(review['review_id']) is int and review['review_id'] == self.review_id and
               d.same(review['binding'], self.expected), 'EXACT_NEW_REVIEW_BINDING')
        d.hash_value(review['body_sha256'])
        if self.authorization is not None:
            d.need(d.same(review, self.authorization), 'REVIEW_CHANGED_DURING_ATTEMPT')
        observed = self.guards.read_preserved_pins()
        d.need(d.same(observed, self.preserved), 'PRESERVED_STATE_DRIFT')
        activation = self.guards.read_activation_evidence()
        d.keys(activation, ('descriptor', 'preserved_epoch7_prefix_sha256'), 'ACTIVATION_EVIDENCE_KEYS')
        allowed = [self.snapshot['activation'], self.candidate['activation']]
        quiesced = copy.deepcopy(self.candidate['activation']); quiesced['state'] = 'QUIESCED'
        allowed.append(quiesced)
        d.need(any(d.same(activation['descriptor'], value) for value in allowed) and
               activation['preserved_epoch7_prefix_sha256'] == self.snapshot['epoch_journal_sha256'],
               'EXACT_NONACTIVE_EPOCH_REQUIRED')
        d.need(d.same(self.guards.read_generation(), self.current_generation) and
               d.same(self.guards.read_sandbox(), self.snapshot['sandbox']),
               'TARGET_PHASE_REQUIRES_ORIGINAL_GENERATION_AND_RESTORED_SANDBOX')
        d.need(d.same(self.guards.read_targets(), self.current_targets), 'CURRENT_TARGET_STATE_DRIFT')
        for addition in self.additions:
            path = addition['path']; current = self.current_additive_targets[path]
            if current is None:
                d.need(d.same(self.guards.read_additive_absence(path), addition['before']),
                       'ADDITIVE_CURRENT_ABSENCE_DRIFT')
            else:
                d.need(d.same(self.guards.read_additive_target(path), current), 'ADDITIVE_PUBLISHED_TARGET_DRIFT')
        exclusion = self.guards.read_writer_exclusion()
        d.keys(exclusion, self.snapshot['writer_exclusion'], 'LIVE_EXCLUSION_KEYS')
        for key, value in exclusion.items():
            if key == 'evidence_sha256':
                d.hash_value(value)
            else:
                d.need(value is True, 'LIVE_WRITER_EXCLUSION_REQUIRED')
        self.authorization = copy.deepcopy(review)
        return copy.deepcopy(review)

    def journal_binding(self):
        d.need(self.authorization is not None, 'VERIFIED_REVIEW_REQUIRED')
        return {'review_id': self.review_id,
            'approval_body_sha256': self.authorization['body_sha256'],
            'authorization_sha256': d.digest(self.expected),
            'delta_sha256': self.delta_sha256,
            'complete_delta_sha256': self.expected['complete_delta_sha256'],
            'additive_targets_sha256': self.additions_sha256,
            'snapshot_sha256': self.delta['snapshot_sha256']}


class BoundJournal(object):
    """Exact-name single-writer journal over an injected protected filesystem.

    io.read_journal(name) returns data,uid,gid,mode,dev,ino,nlink.
    io.create_exclusive and io.replace_exact must implement protected ancestry,
    no-follow opens, exact metadata/bytes CAS, write-all, file+parent fsync and
    atomic publication. See the separate protected filesystem candidate adapter.
    """
    def __init__(self, name, gate, io):
        d.need(name in JOURNALS and io is not None, 'EXACT_NEW_JOURNAL_ONLY')
        self.name, self.gate, self.io = name, gate, io
        self.last = None
        self.state = None
        self.poisoned = False

    @staticmethod
    def _validate_record(record):
        required = {'data', 'uid', 'gid', 'mode', 'dev', 'ino', 'nlink'}
        if isinstance(record, dict) and d.FILE_STAMP_KEYS & set(record): required |= d.FILE_STAMP_KEYS
        d.keys(record, required, 'JOURNAL_METADATA_KEYS')
        d.need(isinstance(record['data'], bytes) and len(record['data']) <= 1048576,
               'JOURNAL_BYTES_BOUND')
        for key in ('uid', 'gid', 'mode', 'dev', 'ino', 'nlink'):
            d.integer(record[key], 1 if key in ('ino', 'nlink') else 0)
        for key in d.FILE_STAMP_KEYS & set(record): d.integer(record[key])
        d.need((record['uid'], record['gid'], record['mode'], record['nlink']) ==
               (0, 0, 0o600, 1), 'PROTECTED_JOURNAL_REQUIRED')
        value = json.loads(record['data'].decode('utf-8'))
        d.need(d.canonical(value) + b'\n' == record['data'], 'CANONICAL_JOURNAL_REQUIRED')
        return value

    def _packed(self, state):
        d.need(isinstance(state, dict) and isinstance(state.get('stage'), str), 'JOURNAL_STAGE_REQUIRED')
        value = {'schema': 1, 'name': self.name, 'transaction_id': d.TX,
                 'binding': self.gate.journal_binding(), 'state': copy.deepcopy(state)}
        raw = d.canonical(value) + b'\n'
        d.need(len(raw) <= 1048576, 'JOURNAL_BYTES_BOUND')
        return raw

    def _after(self, raw, state):
        record = self.io.read_journal(self.name)
        self._validate_record(record)
        d.need(record['data'] == raw, 'JOURNAL_PUBLICATION_UNCONFIRMED')
        self.last = copy.deepcopy(record)
        self.state = copy.deepcopy(state)

    def create(self, state):
        d.need(not self.poisoned and self.last is None, 'JOURNAL_CANNOT_RESUME_OR_RESET')
        self.gate.check()
        d.need(self.io.journal_exists(self.name) is False, 'EXISTING_ATTEMPT_OR_JOURNAL_HOLD')
        raw = self._packed(state)
        try:
            self.io.create_exclusive(self.name, raw, 0, 0, 0o600)
            self._after(raw, state)
        except BaseException:
            self.poisoned = True
            raise

    def save(self, state):
        d.need(not self.poisoned and self.last is not None, 'UNCLAIMED_OR_UNCERTAIN_JOURNAL')
        self.gate.check()
        current = self.io.read_journal(self.name)
        self._validate_record(current)
        d.need(current == self.last, 'JOURNAL_CAS_DRIFT')
        raw = self._packed(state)
        try:
            self.io.replace_exact(self.name, copy.deepcopy(self.last), raw, 0, 0, 0o600)
            self._after(raw, state)
        except BaseException:
            self.poisoned = True
            raise


class RetainedTargetDelta(object):
    """Apply only exact 24 reviewed target replacements through injected ops.

    Requires an already-created fresh attempt. No TLS lifecycle, prerequisite,
    plugin, service, DB, activation or security permission operation is called.
    This phase runs BEFORE generation chmod, sandbox application and TLS journal
    rebinding; it can run while epoch7 PREPARED or approved epoch8 nonactive.
    io.backup_target_exact must preserve file bytes privately or the exact mask
    metadata before replacement; all backups and old receipts remain on failure.
    """
    def __init__(self, gate, attempt, io):
        d.need(attempt.name == ATTEMPT and attempt.gate is gate and io is not None,
               'EXACT_ATTEMPT_CONTEXT')
        self.gate, self.attempt, self.io = gate, attempt, io
        self.journal = BoundJournal(PROVISION, gate, io)
        self.started = False

    def apply(self, payloads):
        d.need(not self.started and self.attempt.last is not None and
               not self.attempt.poisoned, 'FRESH_ADMITTED_ATTEMPT_REQUIRED')
        d.need(self.attempt.state == {'stage': 'ADMITTED'}, 'EXACT_ADMITTED_PHASE_REQUIRED')
        self.gate.check()
        changes = [copy.deepcopy(row) for row in self.gate.delta['changes']
                   if row['operation'] != 'RETAIN']
        d.keys(payloads, {row['path'] for row in changes}, 'EXACT_CHANGED_PAYLOAD_SET')
        for row in changes:
            raw = payloads[row['path']]
            d.need(isinstance(raw, bytes) and len(raw) <= 1048576 and
                   byte_digest(raw) == row['after']['sha256'], 'RENDERED_PAYLOAD_HASH_OR_BOUND')
        d.need(self.io.journal_exists(PROVISION) is False, 'EXISTING_PROVISION_JOURNAL_HOLD')
        self.started = True
        self.attempt.save({'stage': 'TARGET_DELTA_INTENT'})
        state = {'stage': 'TARGET_DELTA_INTENT', 'targets': [dict(row, state='PENDING') for row in changes]}
        self.journal.create(state)
        for row in state['targets']:
            self.gate.check()
            path, before, after = row['path'], row['before'], row['after']
            row['state'] = 'BACKUP_INTENT'; self.journal.save(state)
            backup_name = 'epoch7-target-before-' + hashlib.sha256(path.encode('utf-8')).hexdigest() + '.private'
            backup = self.io.backup_target_exact(path, copy.deepcopy(before), backup_name)
            d.keys(backup, ('name', 'sha256', 'kind'), 'BACKUP_RECEIPT_KEYS')
            expected_hash = before['sha256'] if before['kind'] == 'FILE' else d.digest(before)
            d.need(backup == {'name': backup_name, 'sha256': expected_hash, 'kind': before['kind']},
                   'EXACT_PRIVATE_BACKUP_REQUIRED')
            row['backup'] = copy.deepcopy(backup)
            row['state'] = 'REPLACE_INTENT'; self.journal.save(state)
            self.io.replace_target_exact(path, copy.deepcopy(before), payloads[path], copy.deepcopy(after))
            observed = self.io.read_target(path)
            d.validate_file(observed)
            d.need(all(d.same(observed[k], v) for k, v in after.items()), 'TARGET_PUBLICATION_UNCONFIRMED')
            self.gate.current_targets[path] = copy.deepcopy(observed)
            row['observed_after'] = copy.deepcopy(observed)
            row['state'] = 'DONE'; self.journal.save(state)
        state['stage'] = 'TARGET_DELTA_COMPLETE'; self.journal.save(state)
        self.attempt.save({'stage': 'TARGET_DELTA_COMPLETE',
            'provision_receipt_sha256': byte_digest(self.journal.last['data'])})
        return {'target_delta_complete': True, 'changed_targets': len(changes),
            'retained_targets': 24 - len(changes), 'tls_calls': 0,
            'prior_receipts_rewritten': False, 'legacy_restart': False,
            'production_acceptance': 'PENDING'}


class GenerationAccessStep(object):
    """One bound chmod phase; no chown, recursion, rollback or retry."""
    def __init__(self, gate, attempt, io):
        d.need(attempt.gate is gate and attempt.name == ATTEMPT, 'EXACT_ATTEMPT_CONTEXT')
        self.gate, self.attempt, self.io = gate, attempt, io
        self.journal = BoundJournal('epoch7-generation-access.json', gate, io)
        self.started = False

    def apply(self):
        d.need(not self.started and self.attempt.last is not None and not self.attempt.poisoned and
               self.attempt.state.get('stage') in ('TARGET_DELTA_COMPLETE', 'IDENTITY_PUBLISHED', 'OWNER_IDENTITY_PUBLISHED'),
               'GENERATION_EXACT_PHASE_REQUIRED')
        self.gate.check()
        d.need(self.io.journal_exists(self.journal.name) is False, 'GENERATION_ALREADY_ATTEMPTED')
        change = copy.deepcopy(self.gate.delta['generation_change'])
        d.need(d.same(self.gate.current_generation, change['before']), 'GENERATION_BEFORE_STATE_REQUIRED')
        self.started = True
        attempt_state = dict(self.attempt.state, stage='GENERATION_ACCESS_INTENT')
        self.attempt.save(attempt_state)
        state = {'stage': 'GENERATION_ACCESS_INTENT', 'before': change['before'], 'after': change['after']}
        self.journal.create(state)
        observed = self.io.chmod_generation_exact(change['before'], change['after'])
        receipt = {'state': 'DONE', 'delta_sha256': self.gate.delta_sha256,
            'snapshot_sha256': self.gate.delta['snapshot_sha256'],
            'approval_body_sha256': self.gate.authorization['body_sha256'],
            'before_sha256': d.digest(change['before']), 'after_sha256': d.digest(observed)}
        d.validate_generation_receipt(self.gate.delta, change['before'], observed, receipt)
        self.gate.current_generation = copy.deepcopy(observed)
        state.update(stage='GENERATION_ACCESS_DONE', observed_after=copy.deepcopy(observed), receipt=receipt)
        self.journal.save(state)
        attempt_state.update(stage='GENERATION_ACCESS_COMPLETE',
            generation_receipt_sha256=byte_digest(self.journal.last['data']))
        self.attempt.save(attempt_state)
        return {'generation_mode': 0o700, 'same_inode_owner': True,
                'database_changed': False, 'production_acceptance': 'PENDING'}


class IdentityPublication(object):
    """Publish one explicitly reviewed fixed-path identity pin, once, without overwrite."""
    def __init__(self, gate, attempt, io, path):
        d.need(attempt.gate is gate and attempt.name == ATTEMPT, 'EXACT_ATTEMPT_CONTEXT')
        d.need(path in (additive.PATH, server_additive.PATH), 'EXACT_IDENTITY_PUBLICATION_PATH')
        self.path = path
        self.gate, self.attempt, self.io = gate, attempt, io
        name = ('epoch7-owner-identity-publication.json' if path == additive.PATH else
                'epoch7-server-identity-publication.json')
        self.journal = BoundJournal(name, gate, io)
        self.started = False

    def apply(self, raw):
        d.need(not self.started and self.attempt.last is not None and not self.attempt.poisoned and
               self.attempt.state.get('stage') in ('TARGET_DELTA_COMPLETE', 'GENERATION_ACCESS_COMPLETE', 'IDENTITY_PUBLISHED', 'OWNER_IDENTITY_PUBLISHED'),
               'ADDITIVE_EXACT_PHASE_REQUIRED')
        matched = [x for x in self.gate.additions if x['path'] == self.path]
        d.need(len(matched) == 1, 'EXPLICIT_IDENTITY_ADDITIVE_REVIEW_REQUIRED')
        addition = matched[0]
        d.need(self.gate.current_additive_targets[self.path] is None, 'ADDITIVE_ALREADY_PUBLISHED')
        d.need(isinstance(raw, bytes) and len(raw) <= 65536 and
               byte_digest(raw) == addition['after']['sha256'], 'ADDITIVE_EXACT_APPROVED_BYTES')
        self.gate.check()
        d.need(self.io.journal_exists(self.journal.name) is False, 'ADDITIVE_ALREADY_ATTEMPTED')
        self.started = True
        attempt_state = dict(self.attempt.state, stage='ADDITIVE_PUBLICATION_INTENT')
        self.attempt.save(attempt_state)
        state = {'stage': 'ADDITIVE_PUBLICATION_INTENT', 'before': copy.deepcopy(addition['before']),
                 'after': copy.deepcopy(addition['after']), 'additive_delta_sha256': d.digest(addition)}
        self.journal.create(state)
        observed = self.io.publish_additive_exact(state['before'], raw, state['after'])
        d.validate_file(observed)
        d.need(all(d.same(observed[k], v) for k, v in state['after'].items()),
               'ADDITIVE_PUBLICATION_UNCONFIRMED')
        self.gate.current_additive_targets[self.path] = copy.deepcopy(observed)
        state.update(stage='ADDITIVE_PUBLICATION_DONE', observed_after=copy.deepcopy(observed))
        self.journal.save(state)
        receipts = dict(attempt_state.get('identity_receipts', {}))
        receipts[self.path] = byte_digest(self.journal.last['data'])
        attempt_state.update(stage='IDENTITY_PUBLISHED', identity_receipts=receipts)
        self.attempt.save(attempt_state)
        return {'identity_published': self.path, 'single_link': True,
                'credentials_created': False, 'production_acceptance': 'PENDING'}


class OwnerIdentityPublication(IdentityPublication):
    def __init__(self, gate, attempt, io):
        IdentityPublication.__init__(self, gate, attempt, io, additive.PATH)
