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

    auth = plan['auth']
    if (not isinstance(auth, dict)
            or set(auth) != {'mode', 'references'}
            or auth.get('mode') != 'EXISTING_OAUTH_REFERENCE'
            or not isinstance(auth.get('references'), list)
            or not auth['references']):
        raise ValueError('INVALID_AUTH_REFERENCE_BINDING')
    seen = set()
    for reference in auth['references']:
        if (not isinstance(reference, dict)
                or set(reference) != {'path', 'sha256', 'owner_uid', 'mode'}
                or not _canonical(reference.get('path'))
                or reference['path'] in seen
                or not SHA256.fullmatch(reference.get('sha256', ''))
                or type(reference.get('owner_uid')) is not int
                or type(reference.get('mode')) is not int
                or reference['mode'] & 0o077):
            raise ValueError('INVALID_AUTH_REFERENCE')
        seen.add(reference['path'])

    runtime = plan['runtime']
    if (not isinstance(runtime, dict)
            or set(runtime)-{'legacy_cutover','auxiliary_isolation','tls_renewal'} not in ({'release_directory','provisioning','services','prerequisites','plugin'},
                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap'},
                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher'},
                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher','sandbox_policy'},
                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher','sandbox_policy','rpm'})
            or not isinstance(runtime.get('prerequisites'), dict)
            or not re.fullmatch(r'integration-[0-9a-f]{16}',
                                runtime.get('release_directory', ''))
            or not isinstance(runtime.get('provisioning'), list)
            or not runtime['provisioning']
            or not isinstance(runtime.get('services'), list)
            or not runtime['services']):
        raise ValueError('INVALID_RUNTIME_BINDING')
    if 'legacy_cutover' in runtime:
        value=runtime['legacy_cutover']
        if not isinstance(value,dict) or value!=plan['cutover'] or 'legacy_isolation' not in value:
            raise ValueError('ADOPTED_RUNTIME_CUTOVER_BINDING')
    if 'legacy_cutover' in runtime and 'auxiliary_isolation' not in runtime:
        raise ValueError('AUXILIARY_ISOLATION_REQUIRED')
    if 'auxiliary_isolation' in runtime:
        ref=runtime['auxiliary_isolation']
        if not isinstance(ref,dict) or set(ref)!={'path','sha256','transaction_id'} or ref['transaction_id']!=plan['transaction_id']:
            raise ValueError('AUXILIARY_TRANSACTION_BINDING')
    if 'tls_renewal' in runtime:
        ref=runtime['tls_renewal']
        if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not _canonical(ref['path']) or not SHA256.fullmatch(ref['sha256']):raise ValueError('TLS_RENEWAL_REFERENCE')
    if 'bootstrap' in runtime:
        value=runtime['bootstrap']
        if (not isinstance(value,dict) or set(value)!={'path','sha256'}
                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')
                or not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None):
            raise ValueError('INVALID_BOOTSTRAP_REFERENCE')
    if 'publisher' in runtime:
        value=runtime['publisher']
        if (not isinstance(value,dict) or set(value)!={'path','sha256','source_commit','source_tree'}
                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')
                or not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None
                or value['source_commit']!=plan['artifact']['source_commit']
                or value['source_tree']!=plan['artifact']['source_tree']):
            raise ValueError('INVALID_PUBLISHER_REFERENCE')
    if 'sandbox_policy' in runtime:
        value=runtime['sandbox_policy']
        if (not isinstance(value,dict) or set(value)!={'path','sha256','original_sha256'}
                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')
                or any(not isinstance(value[k],str) or re.fullmatch(r'[0-9a-f]{64}',value[k]) is None for k in ('sha256','original_sha256'))):
            raise ValueError('INVALID_SANDBOX_POLICY_REFERENCE')
    if 'rpm' in runtime:
        value=runtime['rpm']
        if (not isinstance(value,dict) or set(value)!={'path','sha256'}
                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')
                or not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None):
            raise ValueError('INVALID_RPM_REFERENCE')
    plugin=runtime['plugin']
    plugin_keys={'id','source','binding_file','binding_sha256','ledger_client_config',
                 'ledger_client_sha256','gateway_service','openclaw_bin','service_user',
                 'docker_dropin','gateway_relay_config','gateway_relay_sha256','gateway_relay_socket'}
    if (not isinstance(plugin,dict) or set(plugin)!=plugin_keys
            or plugin.get('id')!='xuanjun-p2-native-controller'
            or plugin.get('source')!='plugins/p2-native-controller'
            or plugin.get('binding_file')!='/etc/xuanjun-development/p2-native-controller.binding.json'
            or not SHA256.fullmatch(plugin.get('binding_sha256',''))
            or plugin.get('ledger_client_config')!='/etc/xuanjun-development/p2-native-ledger-client.json'
            or not SHA256.fullmatch(plugin.get('ledger_client_sha256',''))
            or plugin.get('gateway_service')!='xuanjun-uk-openclaw.service'
            or plugin.get('openclaw_bin')!='/home/xuanjun_dev/.openclaw/bin/openclaw'
            or plugin.get('service_user')!='xuanjun_dev'
            or plugin.get('docker_dropin')!='/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'
            or plugin.get('gateway_relay_config')!='/etc/xuanjun-development/p2-gateway-relay.json'
            or not SHA256.fullmatch(plugin.get('gateway_relay_sha256',''))
            or plugin.get('gateway_relay_socket')!='/run/xuanjun-development/p2-gateway.sock'):
        raise ValueError('INVALID_P2_PLUGIN_BINDING')
    tls=plan['tls']
    nginx_required=any(isinstance(x,dict)
                       and isinstance(x.get('target'),str)
                       and x['target'].startswith('/etc/nginx/')
                       for x in runtime['provisioning'])
    expected_tls_mode='EXISTING_TLS_REFERENCE' if nginx_required else 'NOT_APPLICABLE_NO_NGINX'
    if (not isinstance(tls,dict) or set(tls)!={'mode','references'}
            or tls.get('mode')!=expected_tls_mode
            or not isinstance(tls.get('references'),list)
            or (nginx_required and not tls['references'])
            or (not nginx_required and tls['references'])):
        raise ValueError('INVALID_TLS_REFERENCE_BINDING')
    seen=set()
    for reference in tls['references']:
        if (not isinstance(reference,dict)
                or set(reference)!={'path','sha256','owner_uid','mode'}
                or not _canonical(reference.get('path'))
                or reference['path'] in seen
                or not SHA256.fullmatch(reference.get('sha256',''))
                or type(reference.get('owner_uid')) is not int
                or type(reference.get('mode')) is not int
                or reference['mode'] & 0o077):
            raise ValueError('INVALID_TLS_REFERENCE')
        seen.add(reference['path'])
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

    def _complete_receipt(self, plan):
        if not os.path.lexists(self.receipt_path):
            raise ValueError('COMPLETE_INSTALL_RECEIPT_REQUIRED')
        fd = os.open(self.receipt_path, os.O_RDONLY |
                     getattr(os, 'O_NOFOLLOW', 0))
        try:
            info = os.fstat(fd)
            if (not os.path.isfile(self.receipt_path)
                    or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > 1024 * 1024):
                raise ValueError('PROTECTED_COMPLETE_INSTALL_RECEIPT_REQUIRED')
            with os.fdopen(fd) as stream:
                receipt = json.load(stream)
                fd = -1
        finally:
            if fd >= 0:
                os.close(fd)
        required = {'schema', 'transaction_id', 'plan_sha256', 'stage',
                    'legacy_writer_restarted', 'oauth_copied',
                    'new_paid_api_usage', 'release',
                    'provisioning_receipt_sha256', 'epoch',
                    'cutover_receipt_sha256', 'status'}
        if (not isinstance(receipt, dict) or set(receipt) != required
                or receipt.get('schema') != 1
                or receipt.get('transaction_id') != plan['transaction_id']
                or receipt.get('plan_sha256') != _digest(plan)
                or receipt.get('stage') != 'COMPLETE'
                or receipt.get('status') != 'P2_INSTALL_TRANSACTION_COMPLETE'
                or receipt.get('legacy_writer_restarted') is not False
                or receipt.get('oauth_copied') is not False
                or receipt.get('new_paid_api_usage') != 'NONE'
                or not SHA256.fullmatch(
                    receipt.get('provisioning_receipt_sha256', ''))):
            raise ValueError('EXACT_COMPLETE_INSTALL_RECEIPT_REQUIRED')
        return receipt

    def rollback(self, plan):
        """Rollback one exact COMPLETE install without restarting any writer."""
        validate_plan(plan)
        receipt = self._complete_receipt(plan)
        current = self.activation.read(require_active=True)
        activation = plan['activation']
        expected = {
            'state': 'ACTIVE',
            'release_sha256': activation['release_sha256'],
            'config_sha256': activation['config_sha256'],
            'binary_sha256': activation['binary_sha256'],
            'ledger_uuid': activation['ledger_uuid'],
            'generation': activation['generation'],
            'epoch': receipt['epoch'],
            'instance': activation['instance'],
            'db_path': activation['db_path'],
            'ledger_socket': activation['ledger_socket'],
        }
        if any(current.get(key) != value for key, value in expected.items()):
            raise ValueError('ACTIVE_INSTALL_IDENTITY_MISMATCH')
        provision = {'schema': 1,
                     'receipt_sha256':
                         receipt['provisioning_receipt_sha256'],
                     'rollback_complete': True}
        rollback = []
        self._write(receipt, 'ROLLBACK_REQUESTED',
                    rollback_from='COMPLETE',
                    rollback_step='FENCE_PENDING')
        try:
            fenced = self.activation.fence(current['epoch'],
                                           current['instance'])
            rollback.append('ACTIVATION_FENCED_EPOCH_' +
                            str(fenced['epoch']))
            self._write(receipt, 'ROLLBACK_REQUESTED',
                        rollback=rollback,
                        rollback_step='STOP_NEW_PENDING')
            self.runtime.stop_new(plan['runtime'])
            rollback.append('NEW_RUNTIME_STOPPED')
            self._write(receipt, 'ROLLBACK_REQUESTED',
                        rollback=rollback,
                        rollback_step='PROVISIONING_RESTORE_PENDING')
            self.runtime.restore(provision)
            rollback.append('PROVISIONING_RESTORED')
            self._write(receipt, 'ROLLBACK_REQUESTED',
                        rollback=rollback,
                        rollback_step='LEGACY_FILE_RESTORE_PENDING')
            (self.cutover.adapter.restore_legacy_files(preserve_mask=True)
             if 'legacy_isolation' in plan['cutover'] else self.cutover.adapter.restore_legacy_files())
            rollback.append('LEGACY_FILES_RESTORED_NOT_RESTARTED')
            self._write(
                receipt, 'ROLLED_BACK', rollback=rollback,
                rollback_step='COMPLETE',
                recovery='RECONCILE_DATABASE_AND_EPOCH_BEFORE_ANY_RESTART')
            return dict(receipt)
        except Exception as error:
            self._write(
                receipt, 'HOLD', rollback=rollback,
                rollback_step=receipt.get('rollback_step', 'UNKNOWN'),
                rollback_error_type=type(error).__name__,
                recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
            raise

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
        runtime_activation_requested = False
        runtime_stop_requested = False
        prepared = None
        prerequisites_requested = False
        try:
            # Read-only references are verified before the first install effect.
            self.runtime.preflight(plan['runtime'], plan['auth'], plan['tls'])
            release = self.release_installer(plan['artifact'])
            expected_release = os.path.join(plan['artifact']['releases'],
                                            plan['runtime']['release_directory'])
            if release != expected_release:
                raise ValueError('RELEASE_IDENTITY_MISMATCH')
            self._write(receipt, 'RELEASE_INSTALLED', release=release)

            prerequisites_requested = True
            self.runtime.prepare_prerequisites(plan['runtime'])

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

            # Services require ACTIVE; prove the staged DB is readable first.
            reopen = self.runtime.reopen_database(quiesced)
            if reopen != {'database_reopened': True}:
                raise ValueError('DATABASE_REOPEN_PROOF_INCOMPLETE')
            active = self.activation.transition('QUIESCED', 'ACTIVE',
                                                 quiesced['epoch'],
                                                 quiesced['instance'], reopen)
            # Mark before starting: a failed start may leave a live prefix.
            runtime_activation_requested = True
            # Cutover masks the old parent as well as the coordinator. Reuse
            # only its exact backed-up Gateway unit after the new epoch is ACTIVE;
            # the old coordinator remains masked and no service starts here.
            gateway_restore=self.cutover.adapter.restore_legacy_files(gateway_only=True)
            if gateway_restore!={'unit_files_restored':True,'services_restarted':False}:
                raise ValueError('GATEWAY_REUSE_RESTORE_UNPROVEN')
            runtime_proof = self.runtime.activate(plan['runtime'], active)
            if runtime_proof != {'services_active': True}:
                raise ValueError('RUNTIME_ACTIVATION_PROOF_INCOMPLETE')
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
                if prepared is not None:
                    fenced = self.activation.fence(prepared['epoch'], prepared['instance'])
                    rollback.append('ACTIVATION_FENCED_EPOCH_' + str(fenced['epoch']))
                if runtime_activation_requested:
                    runtime_stop_requested = True
                    self.runtime.stop_new(plan['runtime'])
                    rollback.append('NEW_RUNTIME_STOPPED')
                if provision is not None:
                    self.runtime.restore(provision)
                    rollback.append('PROVISIONING_RESTORED')
                elif prerequisites_requested:
                    self.runtime.restore_prerequisites(plan['runtime'])
                    rollback.append('PREREQUISITES_RESTORED')
                if legacy_effect:
                    (self.cutover.adapter.restore_legacy_files(preserve_mask=True)
             if 'legacy_isolation' in plan['cutover'] else self.cutover.adapter.restore_legacy_files())
                    rollback.append('LEGACY_FILES_RESTORED_NOT_RESTARTED')
                self._write(receipt, 'ROLLED_BACK', rollback=rollback,
                            recovery='RECONCILE_DATABASE_AND_EPOCH_BEFORE_ANY_RESTART')
            except Exception as rollback_error:
                # Fencing failure forbids restoration, but still contain any
                # service prefix already started. Never blindly retry a stop.
                if runtime_activation_requested and not runtime_stop_requested:
                    runtime_stop_requested = True
                    try:
                        self.runtime.stop_new(plan['runtime'])
                        rollback.append('NEW_RUNTIME_STOPPED_WITH_FENCE_HOLD')
                    except Exception:
                        rollback.append('NEW_RUNTIME_STOP_FAILED_HOLD')
                self._write(receipt, 'HOLD', rollback=rollback,
                            rollback_error_type=type(rollback_error).__name__,
                            recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
            raise
