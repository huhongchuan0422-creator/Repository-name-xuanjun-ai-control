"""One journaled P2 install entrypoint with fail-closed recovery.

The concrete release installer, fixed-host adapter, activation store, and
runtime provisioner are deliberately injected so tests can prove ordering
without touching a host.  Production wiring must provide all four; there is
no default, model fallback, credential copy, or implicit restart path.
"""
import hashlib
import json
import os
import re

from ledger_cutover_transaction import _atomic_receipt


SHA256 = re.compile(r'^[0-9a-f]{64}$')
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
PROOF_KEYS = frozenset(('identity_verified', 'coordinator_inactive',
                        'parent_unit_inactive', 'cgroups_empty',
                        'restart_inhibited'))
STAGES = ('VALIDATED', 'RELEASE_INSTALLED', 'RUNTIME_PROVISIONED',
          'ACTIVATION_PREPARED', 'LEGACY_QUIESCED', 'RUNTIME_ACTIVE',
          'COMPLETE', 'ROLLBACK_REQUESTED', 'ROLLED_BACK', 'HOLD')


def _canonical(value):
    return isinstance(value, str) and os.path.isabs(value) and os.path.realpath(value) == value


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def validate_plan(plan):
    required = {'schema', 'transaction_id', 'artifact', 'cutover', 'activation',
                'runtime', 'auth', 'tls'}
    if not isinstance(plan, dict) or set(plan) != required or plan.get('schema') != 1:
        raise ValueError('EXACT_P2_INSTALL_PLAN_REQUIRED')
    if not UUID.fullmatch(plan.get('transaction_id', '')):
        raise ValueError('CANONICAL_TRANSACTION_ID_REQUIRED')

    artifact = plan['artifact']
    artifact_keys = {'root', 'manifest', 'source_commit', 'source_tree',
                     'manifest_sha256', 'releases'}
    if (not isinstance(artifact, dict) or set(artifact) != artifact_keys
            or any(not _canonical(artifact[key])
                   for key in ('root', 'manifest', 'releases'))
            or not re.fullmatch(r'[0-9a-f]{40}', artifact['source_commit'])
            or not re.fullmatch(r'[0-9a-f]{40}', artifact['source_tree'])
            or not SHA256.fullmatch(artifact['manifest_sha256'])):
        raise ValueError('INVALID_FROZEN_ARTIFACT_BINDING')

    activation = plan['activation']
    activation_keys = {'release_sha256', 'config_sha256', 'binary_sha256',
                       'ledger_uuid', 'generation', 'instance', 'db_path',
                       'ledger_socket', 'expected_epoch'}
    if (not isinstance(activation, dict) or set(activation) != activation_keys
            or any(not SHA256.fullmatch(activation.get(key, ''))
                   for key in ('release_sha256', 'config_sha256', 'binary_sha256'))
            or any(not UUID.fullmatch(activation.get(key, ''))
                   for key in ('ledger_uuid', 'instance'))
            or type(activation.get('generation')) is not int
            or activation['generation'] < 1
            or type(activation.get('expected_epoch')) is not int
            or activation['expected_epoch'] < 0
            or any(not _canonical(activation[key])
                   for key in ('db_path', 'ledger_socket'))):
        raise ValueError('INVALID_ACTIVATION_BINDING')

    for name, expected_mode in (('auth', 'EXISTING_OAUTH_REFERENCE'),
                                ('tls', 'EXISTING_TLS_REFERENCE')):
        value = plan[name]
        if (not isinstance(value, dict)
                or set(value) != {'mode', 'references'}
                or value.get('mode') != expected_mode
                or not isinstance(value.get('references'), list)
                or not value['references']):
            raise ValueError('INVALID_' + name.upper() + '_REFERENCE_BINDING')
        seen = set()
        for reference in value['references']:
            if (not isinstance(reference, dict)
                    or set(reference) != {'path', 'sha256', 'owner_uid', 'mode'}
                    or not _canonical(reference.get('path'))
                    or reference['path'] in seen
                    or not SHA256.fullmatch(reference.get('sha256', ''))
                    or type(reference.get('owner_uid')) is not int
                    or type(reference.get('mode')) is not int
                    or reference['mode'] & 0o077):
                raise ValueError('INVALID_' + name.upper() + '_REFERENCE')
            seen.add(reference['path'])

    runtime = plan['runtime']
    if (not isinstance(runtime, dict)
            or set(runtime) != {'release_directory', 'provisioning', 'services'}
            or not re.fullmatch(r'integration-[0-9a-f]{16}',
                                runtime.get('release_directory', ''))
            or not isinstance(runtime.get('provisioning'), list)
            or not runtime['provisioning']
            or not isinstance(runtime.get('services'), list)
            or not runtime['services']):
        raise ValueError('INVALID_RUNTIME_BINDING')
    return True


class P2InstallEntrypoint(object):
    """Compose release, provisioning, cutover, activation and exact rollback."""

    def __init__(self, receipt_path, release_installer, cutover, activation,
                 runtime):
        if not _canonical(receipt_path):
            raise ValueError('CANONICAL_INSTALL_RECEIPT_REQUIRED')
        self.receipt_path = receipt_path
        self.release_installer = release_installer
        self.cutover = cutover
        self.activation = activation
        self.runtime = runtime

    def _write(self, receipt, stage, **details):
        if stage not in STAGES:
            raise ValueError('INVALID_INSTALL_STAGE')
        receipt.update(details)
        receipt['stage'] = stage
        _atomic_receipt(self.receipt_path, receipt)

    def _cutover_may_have_effect(self, transaction_id):
        """Read the cutover boundary after an exception without guessing.

        STOP_REQUESTED is durable before the adapter touches systemd.  HOLD
        carries the stage at which the failure occurred.  Either proves that
        direct legacy files may require restoration; absence/corruption holds
        recovery closed instead of claiming a clean preflight.
        """
        path = getattr(self.cutover, 'receipt_path', None)
        if not _canonical(path) or not os.path.lexists(path):
            return False
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            info = os.fstat(fd)
            if info.st_size > 1024 * 1024:
                raise ValueError('UNSAFE_CUTOVER_RECEIPT')
            with os.fdopen(fd) as stream:
                value = json.load(stream)
                fd = -1
        finally:
            if fd >= 0: os.close(fd)
        if (not isinstance(value, dict)
                or value.get('transaction_id') != transaction_id):
            raise ValueError('CUTOVER_RECEIPT_IDENTITY_MISMATCH')
        stage = value.get('failed_stage') if value.get('stage') == 'HOLD' else value.get('stage')
        return stage in ('STOP_REQUESTED', 'QUIESCED', 'STAGE_REQUESTED', 'STAGED')

    def execute(self, plan):
        validate_plan(plan)
        if os.path.lexists(self.receipt_path):
            raise ValueError('HOLD_EXISTING_INSTALL_RECONCILIATION_REQUIRED')
        plan_sha = _digest(plan)
        receipt = {'schema': 1, 'transaction_id': plan['transaction_id'],
                   'plan_sha256': plan_sha, 'stage': 'VALIDATED',
                   'legacy_writer_restarted': False,
                   'oauth_copied': False, 'new_paid_api_usage': 'NONE'}
        _atomic_receipt(self.receipt_path, receipt)
        release = None
        provision = None
        legacy_effect = False
        prepared = None
        try:
            # Read-only references are verified before the first install effect.
            self.runtime.preflight(plan['runtime'], plan['auth'], plan['tls'])
            release = self.release_installer(plan['artifact'])
            expected_release = os.path.join(plan['artifact']['releases'],
                                            plan['runtime']['release_directory'])
            if release != expected_release:
                raise ValueError('RELEASE_IDENTITY_MISMATCH')
            self._write(receipt, 'RELEASE_INSTALLED', release=release)

            provision = self.runtime.provision(release, plan['runtime'])
            if (not isinstance(provision, dict)
                    or set(provision) != {'schema', 'receipt_sha256',
                                          'rollback_complete'}
                    or provision['schema'] != 1
                    or not SHA256.fullmatch(provision['receipt_sha256'])
                    or provision['rollback_complete'] is not True):
                raise ValueError('INCOMPLETE_RUNTIME_PROVISIONING_RECEIPT')
            self._write(receipt, 'RUNTIME_PROVISIONED',
                        provisioning_receipt_sha256=provision['receipt_sha256'])

            value = plan['activation']
            prepared = self.activation.prepare(
                value['release_sha256'], value['config_sha256'],
                value['binary_sha256'], value['ledger_uuid'],
                value['generation'], value['instance'], value['db_path'],
                value['ledger_socket'], expected_epoch=value['expected_epoch'])
            self._write(receipt, 'ACTIVATION_PREPARED', epoch=prepared['epoch'])

            # The cutover journal writes STOP_REQUESTED before the first stop.
            cutover = self.cutover.execute(plan['cutover'])
            legacy_effect = cutover.get('stage') in ('QUIESCED', 'STAGED')
            if cutover.get('stage') != 'STAGED':
                raise ValueError('LEDGER_CUTOVER_NOT_STAGED')
            proof = cutover.get('quiescence', {}).get('proof')
            if (not isinstance(proof, dict) or set(proof) != PROOF_KEYS
                    or any(proof[key] is not True for key in PROOF_KEYS)):
                raise ValueError('LEGACY_QUIESCENCE_PROOF_INCOMPLETE')
            quiesced = self.activation.transition('PREPARED', 'QUIESCED',
                                                   prepared['epoch'],
                                                   prepared['instance'], proof)
            self._write(receipt, 'LEGACY_QUIESCED', epoch=quiesced['epoch'],
                        cutover_receipt_sha256=_digest(cutover))

            runtime_proof = self.runtime.activate(plan['runtime'], quiesced)
            if (not isinstance(runtime_proof, dict)
                    or set(runtime_proof) != {'database_reopened',
                                              'services_active'}
                    or runtime_proof['database_reopened'] is not True
                    or runtime_proof['services_active'] is not True):
                raise ValueError('RUNTIME_ACTIVATION_PROOF_INCOMPLETE')
            active = self.activation.transition('QUIESCED', 'ACTIVE',
                                                 quiesced['epoch'],
                                                 quiesced['instance'],
                                                 {'database_reopened': True})
            self._write(receipt, 'RUNTIME_ACTIVE', epoch=active['epoch'])
            self._write(receipt, 'COMPLETE', status='P2_INSTALL_TRANSACTION_COMPLETE')
            return dict(receipt)
        except Exception as error:
            failed_stage = receipt['stage']
            if not legacy_effect:
                legacy_effect = self._cutover_may_have_effect(plan['transaction_id'])
            self._write(receipt, 'ROLLBACK_REQUESTED', failed_stage=failed_stage,
                        error_type=type(error).__name__)
            rollback = []
            try:
                self.runtime.stop_new(plan['runtime'])
                rollback.append('NEW_RUNTIME_STOPPED')
                if provision is not None:
                    self.runtime.restore(provision)
                    rollback.append('PROVISIONING_RESTORED')
                if legacy_effect:
                    self.cutover.adapter.restore_legacy_files()
                    rollback.append('LEGACY_FILES_RESTORED_NOT_RESTARTED')
                self._write(receipt, 'ROLLED_BACK', rollback=rollback,
                            recovery='RECONCILE_DATABASE_AND_EPOCH_BEFORE_ANY_RESTART')
            except Exception as rollback_error:
                self._write(receipt, 'HOLD', rollback=rollback,
                            rollback_error_type=type(rollback_error).__name__,
                            recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
            raise
