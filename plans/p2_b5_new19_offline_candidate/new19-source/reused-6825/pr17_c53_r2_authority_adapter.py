"""Default-closed authority bridge; no CLI, credentials or new trust root.

Original queue/custody/OAuth algorithms are bound only to frozen context.
Independent conflict and recovery facts remain fail-closed without provenance.
"""
import copy
import time
import pr17_c53_r2_review_transaction as c53
from pr17_c53_r2_local_adapter import prepare_local_adapter, single_thread
from pr17_b5_single_batch_witness import WitnessStore, ROOT as WITNESS_ROOT


def request_local_authorization_only():
    """Maintenance cannot borrow the analyst's later HTTP bearer context."""
    raise c53.Hold('ANALYST_HTTP_REQUEST_CONTEXT_REQUIRED')


class ExistingRequestAuthority:
    # These operations require the original enrolled UK queue, custody and
    # authenticated request interfaces. A Python method name is not evidence
    # that the corresponding original operation is enrolled.
    ORIGINAL_REQUIRED = (
        'verify_cross_project_old_policy_dependency',
        'verify_fixed_receiver_target_conflicts',
        'submit_original_intake_once',
        'verify_nineteen_original_success_receipts',
        'verify_original_archive_custody',
        'custody_once',
        'read_project_chunk_complete',
        'canonical_state_unknown',
        'prove_no_new_operations_canonically',
        'approve_precise_pre_start_restore',
        'approve_c53_b5_exposure_close',
    )

    def preflight_original_capabilities(self):
        """Check enrolled providers before reservation, without demanding success."""
        from pr17_b5_deployment_composition import OriginalComposition
        c53.require(type(getattr(self, 'original', None)) is OriginalComposition,
                    'ORIGINAL_DEPLOYMENT_COMPOSITION_UNAVAILABLE')
        c53.require(self.original.test_only is False,
                    'TEST_COMPOSITION_NOT_PRODUCTION_AUTHORITY')
        self._bound_original(active=False)
        self.original.preflight()
        # A is a live read-only observation, not an enrollment or mutation
        # permit. B must independently reclassify after stop and lock.
        c53.require(callable(getattr(self,'precheck_old_policy_reader',None)),
                    'OLD_POLICY_PRECHECK_READER_UNAVAILABLE')
        precheck=self.precheck_old_policy_reader(self.request_ids,c53.PROJ)
        c53.require(type(precheck) is dict and
                    precheck.get('phase')=='PRECHECK_OBSERVATION' and
                    precheck.get('dependent_active')==0 and
                    precheck.get('unresolved')==0 and
                    precheck.get('source')=='ORIGINAL_PROTECTED_OBSERVATION',
                    'OLD_POLICY_PRECHECK_UNKNOWN')
        self.verify_fixed_receiver_target_conflicts(
            '/var/lib/xuanjun-cloud-connection/b5-material-custody',
            self.request_ids)
        # Recovery and close require their own fresh, precisely scoped
        # provenance at the action; this preflight does not preapprove them.
        return True

    def __init__(self, *, authenticator, authorization_from_request, catalog_raw,
                 catalog_sha, request_ids, clock=time.time,
                 active_resource_reader=None, expected_resource_raw=None,
                 prepared_settings=None, witness_store=None,
                 batch_id=None, attempt_id=None, window_start=None,
                 original=None, runtime_attachment=None,
                 canonical_snapshot_reader=None, receiver_conflict_reader=None):
        if active_resource_reader is None:
            from production.cloud_connection.oauth_resource import Introspection
            c53.require(type(authenticator) is Introspection and authenticator.open_url is None,
                        'ORIGINAL_INTROSPECTION_REQUIRED')
        else:
            c53.require(authenticator is None and callable(active_resource_reader)
                        and type(expected_resource_raw) is bytes and type(prepared_settings) is dict,
                        'CURRENT_RESOURCE_SOURCE_REQUIRED')
        self.active_resource_reader = active_resource_reader
        self.expected_resource_raw = expected_resource_raw
        self.prepared_settings = copy.deepcopy(prepared_settings)
        self.authenticator = authenticator
        self.authorization_from_request = authorization_from_request
        self.catalog_raw = catalog_raw
        self.catalog_sha = catalog_sha
        self.request_ids = tuple(request_ids)
        self.clock = clock
        c53.require(witness_store is None or type(witness_store) is WitnessStore,
                    'WITNESS_STORE_TYPE')
        if witness_store is not None:
            c53.require(witness_store.root == WITNESS_ROOT and
                        witness_store.test_only is False,
                        'PRODUCTION_WITNESS_ROOT_REQUIRED')
        self.witness_store = witness_store
        self.original = original
        self.runtime_attachment = runtime_attachment
        self.canonical_snapshot_reader = canonical_snapshot_reader
        self.receiver_conflict_reader = receiver_conflict_reader
        self.batch_id, self.attempt_id, self.window_start = (
            batch_id, attempt_id, window_start)

    def _witness(self):
        c53.require(self.witness_store is not None,
                    'INDEPENDENT_WITNESS_NOT_ENROLLED')
        return self.witness_store.inspect(self._witness_binding())

    def _bound_original(self, active=True):
        from pr17_b5_deployment_composition import OriginalComposition
        c53.require(type(getattr(self, 'original', None)) is OriginalComposition,
                    'ORIGINAL_DEPLOYMENT_COMPOSITION_UNAVAILABLE')
        self.original.verify_binding(
            self.catalog_raw, self.catalog_sha, self.request_ids,
            c53.RECIP, c53.PROJ, active=active)
        c53.require(getattr(self,'authorization_from_request',None) is
                    self.original.authorization_from_request,
                    'ORIGINAL_REQUEST_AUTHORIZATION_CHANGED')
        return self.original

    def preflight_runtime_attachment(self):
        self._bound_original(active=False)
        c53.require(callable(self.runtime_attachment),
                    'ORIGINAL_RUNTIME_ATTACHMENT_UNAVAILABLE')
        return True

    def attach_original_after_worker_start(self):
        """Use the original bound Queue/OAuth pair after worker stabilization."""
        self.preflight_runtime_attachment()
        pair=self.runtime_attachment('observe')
        c53.require(type(pair) is tuple and len(pair)==2,
                    'ORIGINAL_RUNTIME_ATTACHMENT_RESULT')
        self.original.attach_after_worker_start(pair[0],pair[1])
        return self._bound_original(active=True)

    def _current_authenticator(self):
        if self.active_resource_reader is None:
            return self.authenticator
        # Invoked only by the post-activation gate. Never use generated future
        # settings as observed state; read protected current bytes again.
        raw = self.active_resource_reader()
        c53.require(type(raw) is bytes and raw == self.expected_resource_raw,
                    'AUTH_ACTIVATED_RESOURCE_CHANGED')
        resource = c53.strict_json(raw)
        c53.require(resource.get('schema') == 1 and type(resource['schema']) is int
                    and resource.get('enabled') is True and resource.get('hostname') == c53.HOST,
                    'AUTH_ACTIVATED_RESOURCE_BINDING')
        settings = copy.deepcopy(resource.get('settings'))
        c53.require(type(settings) is dict and set(settings) ==
                    {'issuer', 'endpoint', 'client_id', 'audience', 'subjects'},
                    'AUTH_ACTIVATED_SETTINGS')
        c53.require(all(settings[k] == self.prepared_settings[k] for k in
                    ('issuer', 'endpoint', 'client_id', 'audience')),
                    'AUTH_ORIGINAL_SETTINGS_CHANGED')
        mapping = settings['subjects'].get(c53.SUBJECT)
        c53.require(type(mapping) is dict and mapping.get('recipient') == c53.RECIP
                    and type(mapping.get('projects')) is list and c53.PROJ in mapping['projects'],
                    'AUTH_ACTIVATED_B5_MAPPING')
        entries = resource.get('catalogs')
        c53.require(type(entries) is list and len(entries) == 1
                    and entries[0].get('manifest_ref') == c53.binder.CATALOG
                    and entries[0].get('manifest_sha256') == self.catalog_sha
                    and resource.get('custodies') == {self.catalog_sha: [c53.binder.DEST, 0]},
                    'AUTH_ACTIVATED_CATALOG_BINDING')
        settings['subjects'] = {c53.SUBJECT: mapping}
        from production.cloud_connection.oauth_resource import Introspection
        from production.cloud_connection.oauth_entrypoint import private_bytes
        secret_ref = resource['client_secret_ref']
        def existing_secret():
            return private_bytes(secret_ref, 4096).decode().strip()
        return Introspection(secret_provider=existing_secret, **settings)

    def verify_existing_grant(self, subject, recipient, project, status_scope,
                              file_scope, catalog_sha):
        c53.require((subject, recipient, project, status_scope, file_scope) ==
                    (c53.SUBJECT, c53.RECIP, c53.PROJ,
                     'connection.status', 'project.files.read'), 'AUTH_FIXED_SCOPE')
        c53.require(catalog_sha == self.catalog_sha and
                    c53.sha(self.catalog_raw) == catalog_sha, 'AUTH_CATALOG_CHANGED')
        catalog = c53.strict_json(self.catalog_raw)
        c53.require(catalog.get('project') == project and
                    recipient in catalog.get('recipients', ()), 'AUTH_CATALOG_SCOPE')
        now = self.clock()
        c53.require(type(now) in (int, float) and
                    type(catalog.get('valid_from')) is int and
                    type(catalog.get('valid_until')) is int and
                    catalog['valid_from'] <= now < catalog['valid_until'],
                    'AUTH_CATALOG_EXPIRED')
        authenticator = self._current_authenticator()
        # Narrowed original registry makes returned recipient prove the exact
        # subject too: Introspection.authenticate otherwise returns no subject.
        c53.require(set(authenticator.subjects) == {subject},
                    'AUTH_SUBJECT_CONTEXT_AMBIGUOUS')
        c53.require(callable(self.authorization_from_request),
                    'ORIGINAL_REQUEST_AUTHORIZATION_NOT_CONNECTED')
        header = self.authorization_from_request()
        try:
            for scope in (status_scope, file_scope):
                actual = authenticator.authenticate(header, scope, project, int(now))
                c53.require(actual == recipient, 'AUTH_RECIPIENT_MISMATCH')
        finally:
            del header
        end = self.clock()
        c53.require(type(end) in (int, float) and now <= end < catalog['valid_until'],
                    'AUTH_WINDOW_CHANGED')
        # This digest covers non-sensitive verification context, never a token.
        evidence = dict(subject=subject, recipient=recipient, project=project,
                        scopes=[status_scope, file_scope], catalog_sha256=catalog_sha,
                        checked_at=end, grant_active=True)
        evidence['evidence_sha256'] = c53.sha(c53.canon(evidence))
        evidence.update(verified=True, source='ORIGINAL_AUTHENTICATED_CLIENT')
        return evidence

    def verify_owner_maintenance_scope(self, host, commit, job, request_ids):
        c53.require((host, commit, job, tuple(request_ids)) ==
                    (c53.HOST, c53.COMMIT,
                     '/opt/xuanjun-cloud-connection/l2-c53-recovery-once',
                     self.request_ids), 'MAINTENANCE_BINDING_MISMATCH')
        witnessed = self._witness()
        return {'verified': True, 'source': 'UK_OWNER_WITNESS_SINGLE_BATCH',
                'evidence_sha256': witnessed['owner_sha256'],
                'witness_pair_sha256': witnessed['pair_sha256'],
                'host': host, 'commit': commit, 'job': job, 'approved': True}

    def verify_b5_analyst_ack(self, subject, recipient, project, operation,
                            catalog_sha, request_ids):
        c53.require((subject, recipient, project, operation, catalog_sha,
                     tuple(request_ids)) ==
                    (c53.SUBJECT, c53.RECIP, c53.PROJ, 'fetch_approved_object',
                     self.catalog_sha, self.request_ids), 'B5_ACK_BINDING_MISMATCH')
        witnessed = self._witness()
        return {'verified': True, 'source': 'UK_OWNER_WITNESS_SINGLE_BATCH',
                'evidence_sha256': witnessed['analyst_sha256'],
                'witness_pair_sha256': witnessed['pair_sha256'],
                'analyst_ready': True, 'subject': subject,
                'recipient': recipient, 'project': project,
                'operation': operation, 'catalog_sha256': catalog_sha,
                'request_ids': list(request_ids)}

    def witness_pair_digest(self):
        return self._witness()['pair_sha256']

    def witness_action(self):
        c53.require(self.witness_store is not None,
                    'INDEPENDENT_WITNESS_NOT_ENROLLED')
        return self.witness_store.action(self._witness_binding())

    def consume_witness_once(self):
        self._witness()
        return self.witness_store.consume_once(self._witness_binding())

    def _witness_binding(self):
        c53.require(type(self.window_start) is int and
                    type(self.attempt_id) is str,
                    'WITNESS_BATCH_CONTEXT_MISSING')
        return {'batch': self.batch_id,
            'job': '/opt/xuanjun-cloud-connection/l2-c53-recovery-once',
            'attempt': self.attempt_id, 'ids': list(self.request_ids),
            'catalog_sha256': self.catalog_sha, 'recipient': c53.RECIP,
            'project': c53.PROJ, 'subject': c53.SUBJECT, 'commit': c53.COMMIT,
            'valid_from': self.window_start,
            'valid_until': self.window_start + 3600}

    def verify_nineteen_original_success_receipts(self, ids, catalog_sha):
        c53.require(tuple(ids) == self.request_ids and catalog_sha == self.catalog_sha,
                    'B5_SUCCESS_CONTEXT')
        invokes = self._bound_original().success()
        result = dict(success_count=len(invokes), invoke_bound_count=len(invokes),
                      sha_bound_count=len(invokes), catalog_sha256=catalog_sha)
        return self._original_receipt(result)

    def submit_original_intake_once(self, request, persist_intent, persist_sent):
        return self._bound_original().send_once(request, persist_intent, persist_sent)

    def observe_original_intake_ready(self, request):
        from production.cloud_connection.queue import Hold as QueueHold
        try:
            self._bound_original().ready(request)
        except QueueHold as exc:
            if str(exc) == 'B5_INTAKE_PENDING_OR_UNKNOWN_NO_REPOST':
                raise c53.Hold(str(exc)) from None
            raise
        return {'request_id': request['request_id'], 'state': 'ACCEPTED'}

    def observe_original_success_progress(self, ids, catalog_sha):
        c53.require(tuple(ids) == self.request_ids and catalog_sha == self.catalog_sha,
                    'B5_SUCCESS_CONTEXT')
        return self._bound_original().success_progress()

    def verify_original_archive_custody(self, size, digest):
        return self._original_receipt(self._bound_original().archive(size, digest))

    def custody_once(self, job, catalog_sha):
        c53.require(catalog_sha == self.catalog_sha and
                    job == '/opt/xuanjun-cloud-connection/l2-c53-recovery-once',
                    'B5_CUSTODY_CONTEXT')
        original=self._bound_original()
        if original.test_only is True:
            # Explicit offline fixture already owns its disposable writable DB.
            return self._original_receipt(original.custody())
        c53.require(original.runtime_phase=='observe' and
                    callable(self.runtime_attachment),
                    'B5_CUSTODY_PHASE_NOT_ADMITTED')
        pair=self.runtime_attachment('custody')
        c53.require(type(pair) is tuple and len(pair)==2,
                    'B5_CUSTODY_ATTACHMENT_RESULT')
        original.replace_runtime_phase(pair[0],pair[1],'observe','custody')
        try:
            return self._original_receipt(original.custody())
        finally:
            # An uncertain custody result stays UNKNOWN and is never repeated.
            # Reopening read-only is an observation, not an action replay.
            try:
                read_pair=self.runtime_attachment('observe')
                c53.require(type(read_pair) is tuple and len(read_pair)==2,
                            'B5_OBSERVE_ATTACHMENT_RESULT')
                original.replace_runtime_phase(read_pair[0],read_pair[1],
                                               'custody','observe')
            except BaseException:
                try:original.detach_runtime_unknown()
                except BaseException:
                    raise c53.Hold('B5_CUSTODY_CLOSE_UNKNOWN_NO_RETRY') from None
                raise c53.Hold('B5_CUSTODY_PHASE_UNKNOWN_NO_RETRY') from None

    def read_project_chunk_complete(self, request, catalog_sha, obj):
        c53.require(catalog_sha == self.catalog_sha, 'B5_BODY_CATALOG')
        return self._bound_original().body(request, obj)

    @staticmethod
    def _original_receipt(fields):
        result = dict(fields)
        result.update(verified=True, source='ORIGINAL_ALGORITHM_VERIFIED')
        result['evidence_sha256'] = c53.sha(c53.canon(fields))
        return result

    def verify_cross_project_old_policy_dependency(self, ids, project):
        c53.require(callable(getattr(self,'old_policy_reader',None)),
                    'OLD_POLICY_READER_UNAVAILABLE')
        return self.old_policy_reader(ids,project)

    def verify_fixed_receiver_target_conflicts(self, root, ids):
        c53.require(callable(self.receiver_conflict_reader),
                    'FIXED_RECEIVER_CONFLICT_SOURCE_UNKNOWN')
        return self.receiver_conflict_reader(root,ids)

    def canonical_state_unknown(self, job):
        if job!='/opt/xuanjun-cloud-connection/l2-c53-recovery-once':return True
        try:return self.canonical_snapshot_reader() is not True
        except BaseException:return True

    def prove_no_new_operations_canonically(self, job):
        if job!='/opt/xuanjun-cloud-connection/l2-c53-recovery-once':return False
        try:return self.canonical_snapshot_reader() is True
        except BaseException:return False

    def approve_precise_pre_start_restore(self, job):
        raise c53.Hold('PRE_START_RESTORE_APPROVAL_SOURCE_UNKNOWN')

    def approve_c53_b5_exposure_close(self, job):
        raise c53.Hold('C53_CLOSE_APPROVAL_SOURCE_UNKNOWN')


def prepare_maintenance_candidate(*, authorization_from_request=None,
                                  witness_store=None, attempt_id=None,
                                  original=None, runtime_attachment=None, **inputs):
    """Actual local adapter -> transaction -> original OAuth factory linkage.

    Returns a prepared transaction only. Does not call execute or authenticate.
    A request-local Authorization accessor still must be supplied by the
    original authenticated caller, never CLI/chat/env/token-file input.
    """
    c53.require('authority' not in inputs, 'EXTERNAL_AUTHORITY_FORBIDDEN')
    if original is not None:
        from pr17_b5_deployment_composition import OriginalComposition
        c53.require(type(original) is OriginalComposition and
                    original.test_only is False,
                    'ORIGINAL_COMPOSITION_TYPE')
    c53.require(witness_store is None or type(witness_store) is WitnessStore,
                'WITNESS_STORE_TYPE')
    if witness_store is not None:
        c53.require(witness_store.root == WITNESS_ROOT and
                    witness_store.test_only is False,
                    'PRODUCTION_WITNESS_ROOT_REQUIRED')
    single_thread()
    if authorization_from_request is None:
        authorization_from_request=request_local_authorization_only
    transaction = prepare_local_adapter(authority=None, **inputs)
    backend = transaction.b
    if original is None and callable(authorization_from_request):
        original=build_original_for_prepared_bundle(
            transaction.bundle,authorization_from_request)
    # Use current protected bytes read by the adapter, not generated future
    # resource settings (which would add the B5 mapping before activation).
    resource = c53.strict_json(backend.frozen_baselines[c53.CONFIGS[1]])
    c53.require(resource.get('enabled') is True and resource.get('hostname') == c53.HOST
                and type(resource.get('schema')) is int and resource['schema'] == 1,
                'AUTH_CURRENT_RESOURCE_BINDING')
    settings = copy.deepcopy(resource['settings'])
    c53.require(set(settings) == {'issuer', 'endpoint', 'client_id', 'audience', 'subjects'},
                'AUTH_CURRENT_SETTINGS')
    mapping = settings['subjects'].get(c53.SUBJECT)
    c53.require(type(mapping) is dict and type(mapping.get('projects')) is list,
                'AUTH_CURRENT_SUBJECT_MISSING')
    # Activation preparation accepts the actual withdrawal state. Independent
    # maintenance approval and analyst ACK are still required before mutation.
    # No Introspection, secret read or grant check happens in this factory.
    backend.authority = ExistingRequestAuthority(
        authenticator=None, authorization_from_request=authorization_from_request,
        catalog_raw=transaction.bundle['files'][c53.binder.CATALOG],
        catalog_sha=transaction.bundle['catalog_sha'], request_ids=backend.expected_ids,
        active_resource_reader=backend.read_activated_resource_verified,
        expected_resource_raw=transaction.bundle['files'][c53.CONFIGS[1]],
        prepared_settings=settings, witness_store=witness_store,
        batch_id=transaction.bundle['batch_id'], attempt_id=attempt_id,
        window_start=transaction.bundle['window_start'], original=original,
        runtime_attachment=runtime_attachment,
        canonical_snapshot_reader=backend.canonical_prestart_no_new_operations,
        receiver_conflict_reader=backend.observe_fixed_receiver_target_readonly)
    backend.authority.old_policy_reader=backend.observe_cross_project_old_policy_dependency
    backend.authority.precheck_old_policy_reader=backend.observe_prestart_old_policy_dependency
    if original is not None:
        backend.authority._bound_original(active=False)
        if runtime_attachment is None:
            # Construct the production caller from this exact prepared
            # transaction. The closure still requires the next reviewed pin
            # and activated protected facts at invocation time.
            from pr17_b5_maintenance_runtime import attachment_for_prepared
            backend.authority.runtime_attachment=attachment_for_prepared(transaction)
    return transaction


def build_original_for_prepared_bundle(bundle, authorization_from_request):
    """Construct the original providers from a frozen, unactivated bundle.

    This does not publish, read a bearer token, open a database, or authorize a
    batch.  The request-local accessor is supplied by the enrolled caller and
    cannot be synthesized from maintenance configuration.
    """
    from pr17_b5_deployment_composition import OriginalComposition
    from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
    from production.cloud_connection.worker import Github, Cloud, Network
    c53.require(type(bundle) is dict and callable(authorization_from_request),
                'ORIGINAL_REQUEST_CONTEXT_UNAVAILABLE')
    raw=bundle.get('files',{}).get(c53.binder.BIND)
    c53.require(type(raw) is bytes and
                type(bundle.get('requests')) in (list,tuple) and
                len(bundle['requests'])==19,
                'ORIGINAL_BUNDLE_INCOMPLETE')
    policy=ApprovedObjectsPolicy(raw,c53.sha(raw))
    network=Network()
    return OriginalComposition(
        queue=None,github=Github('/etc/xuanjun-development/github-intake-token',
                                  network,1003),
        cloud=Cloud('/etc/xuanjun-cloud-executor/credentials.json',network),
        policy=policy,resource=None,requests=bundle['requests'],
        archive_root_ref='b5-original-archive',
        destination_root=c53.binder.DEST,destination_owner=0,
        authorization_from_request=authorization_from_request,
        clock=time.time,test_only=False)


def check_candidate_authority(transaction):
    """Verification-only caller; never reserve/stop/lock/execute on failure."""
    single_thread()
    transaction.b.verify_activation_admission(transaction.bundle, transaction.spec)
    transaction.b.verify_analyst_ack(transaction.bundle, transaction.spec)
    # No success capability or execute wrapper is provided by this candidate.


def reconstruct_recovery_candidate(*, spec_raw, source_root, legacy_io,
                                   authorization_from_request=None,
                                   runtime_attachment=None, witness_store=None):
    """Fresh-process reconstruction from exact protected backup and source bytes.

    This does not execute the transaction. The caller must attach original
    runtime objects and obtain fresh authority before any custody/body action.
    The protected reservation fixes the prior attempt; it is never replaced.
    """
    from pr17_c53_r2_local_pinned_source_loader import read_fixed_local_source
    from pr17_c53_r2_host_backend_candidate import R2HostBackend
    from pr17_b5_deployment_composition import OriginalComposition
    from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
    from production.cloud_connection.worker import Github, Cloud, Network
    single_thread()
    spec=c53.binder.verify_spec_bytes(spec_raw)
    job=spec['fixed_paths']['job_proposed']
    c53.require(job=='/opt/xuanjun-cloud-connection/l2-c53-recovery-once',
                'RECOVERY_JOB_SCOPE')
    try:raw,_=legacy_io.read(job+'/reservation.json')
    except FileNotFoundError:raise c53.Hold('RECOVERY_RESERVATION_ABSENT') from None
    c53.require(type(raw) is bytes and len(raw)<=4096,'RECOVERY_RESERVATION_LENGTH')
    reservation=c53.strict_json(raw)
    c53.require(reservation.get('state')=='RESERVED_NOT_SUBMITTED' and
                type(reservation.get('batch')) is str and
                type(reservation.get('approval_ref')) is str and
                type(reservation.get('attempt_id')) is str and
                type(reservation.get('window_start')) is int and
                type(reservation.get('window_end')) is int and
                reservation['window_end']==reservation['window_start']+3600,
                'RECOVERY_RESERVATION_FORMAT')
    backups=spec['fixed_paths']['backups_proposed']
    paths=c53.CONFIGS+c53.SLOTS
    saved=backups['configs']+backups['protected_slots']
    c53.require(len(saved)==6,'RECOVERY_BACKUP_SCOPE')
    baselines={}
    for path,backup in zip(paths,saved):
        c53.require(backup.startswith(job+'/'),'RECOVERY_BACKUP_PATH')
        try:content,_=legacy_io.read(backup)
        except FileNotFoundError:raise c53.Hold('RECOVERY_BACKUP_ABSENT') from None
        c53.require(type(content) is bytes and len(content)<=16384,
                    'RECOVERY_BACKUP_LENGTH')
        baselines[path]=content
    c53.verify_observed_bytes(spec,baselines)
    sources=read_fixed_local_source(spec,source_root)
    bundle=c53.make_bundle(spec,baselines,sources,
        batch_id=reservation['batch'],approval_ref=reservation['approval_ref'],
        window_start=reservation['window_start'])
    c53.validate_bundle(spec,bundle,verified_baselines=baselines,
                        verified_source_blobs=sources)
    c53.require(reservation.get('generation_seal')==bundle['generation_seal'] and
                reservation.get('catalog_sha256')==bundle['catalog_sha'] and
                reservation.get('ids')==[x['request_id'] for x in bundle['requests']] and
                reservation.get('request_set_sha256')==c53.sha(c53.canon(bundle['requests'])),
                'RECOVERY_REGENERATED_BUNDLE_MISMATCH')
    backend=R2HostBackend(legacy_io=legacy_io,spec=spec,source_blobs=sources,
                          observed_bytes=baselines)
    c53.require(tuple(x['request_id'] for x in bundle['requests'])==backend.expected_ids,
                'RECOVERY_REQUEST_SET_NOT_ORIGINAL_BATCH')
    # Closeout reads the original resource/env bytes, never the now-active
    # generated versions. Old inode identities are intentionally not inferred
    # from backup copies, so pre-start rollback stays unavailable here.
    backend.before={p:(raw,None) for p,raw in baselines.items()}
    if authorization_from_request is None:
        authorization_from_request=request_local_authorization_only
    original=build_original_for_prepared_bundle(bundle,authorization_from_request)
    old=c53.strict_json(baselines[c53.CONFIGS[1]])
    settings=copy.deepcopy(old['settings'])
    backend.authority=ExistingRequestAuthority(
        authenticator=None,authorization_from_request=authorization_from_request,
        catalog_raw=bundle['files'][c53.binder.CATALOG],
        catalog_sha=bundle['catalog_sha'],request_ids=backend.expected_ids,
        active_resource_reader=backend.read_activated_resource_verified,
        expected_resource_raw=bundle['files'][c53.CONFIGS[1]],
        prepared_settings=settings,witness_store=witness_store,
        batch_id=bundle['batch_id'],attempt_id=reservation['attempt_id'],
        window_start=bundle['window_start'],original=original,
        runtime_attachment=runtime_attachment,
        canonical_snapshot_reader=backend.canonical_prestart_no_new_operations,
        receiver_conflict_reader=backend.observe_fixed_receiver_target_readonly)
    backend.restore_activation_identity_readonly(bundle)
    transaction=c53.Transaction(spec,bundle,backend)
    if runtime_attachment is None:
        from pr17_b5_maintenance_runtime import attachment_for_prepared
        backend.authority.runtime_attachment=attachment_for_prepared(transaction)
    return transaction


def inspect_recovered_candidate_readonly(transaction):
    """Attach the original authenticated runtime, then inspect; never POST."""
    from pr17_c53_r2_host_backend_candidate import R2HostBackend
    c53.require(type(transaction) is c53.Transaction and
                type(transaction.b) is R2HostBackend and
                getattr(transaction.b,'recovered_from_protected',False) is True,
                'RECOVERY_FACTORY_REQUIRED')
    transaction.b.authority.attach_original_after_worker_start()
    return transaction.b.observe_poststart_canonical_readonly(transaction.bundle)
