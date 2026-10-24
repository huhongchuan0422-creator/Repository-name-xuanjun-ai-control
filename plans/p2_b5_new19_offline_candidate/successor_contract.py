"""Exact, offline successor contract for the staged B5 transaction.

This module only checks supplied bytes. It cannot approve a maintenance action,
register a batch, submit an intake, or fetch a body. The old c53 transaction is
deliberately not accepted as a successor by changing its constants in memory.
"""
import hashlib
import json
import copy


class Hold(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def sha(raw):
    require(type(raw) is bytes, 'BYTES_REQUIRED')
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def decode(raw):
    require(type(raw) is bytes and len(raw) <= 262144, 'JSON_SIZE')
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'DUPLICATE_KEY')
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold('NONFINITE')))
    except Hold:
        raise
    except (ValueError, UnicodeError, TypeError):
        raise Hold('JSON_FORMAT') from None
    require(type(value) is dict, 'JSON_TOPLEVEL')
    return value


PHASES = ('FREEZE_LOCAL', 'AUTHENTICATE_EXISTING', 'ANALYST_ACK',
          'STOP_EXISTING_WORKER', 'ORIGINAL_LOCK_ADMISSION', 'BACKUP_EXISTING',
          'PUBLISH_SUCCESSOR', 'ACTIVATE_SUCCESSOR', 'RESOURCE_READINESS',
          'RELEASE_LOCK', 'START_ATTEMPT_CHECKPOINT', 'START_WORKER',
          'WINDOW_ENABLE', 'INTAKE_19', 'ONE_CUSTODY',
          'B5_HTTP_RECEIVE_AND_VERIFY', 'CLOSE_EXPOSURE')
ORIGINAL_SHA256 = '11aff4749d18ee6f4987d5f31934ce8bd535e6fd5ba13e2a07716773df4145b4'


def derive(original_raw, binder_raw, manifest_raw=None):
    """Prepare a separate draft; never mutate the historical c53 spec."""
    require(sha(original_raw) == ORIGINAL_SHA256, 'ORIGINAL_REVIEWED_BYTES_CHANGED')
    old, binding = decode(original_raw), decode(binder_raw)
    release = binding.get('release_commit')
    require(type(release) is str and len(release) == 40 and
            all(c in '0123456789abcdef' for c in release), 'RELEASE_COMMIT')
    paths = copy.deepcopy(old['fixed_paths'])
    job = '/opt/xuanjun-cloud-connection/l2-b5-staged-' + release[:12]
    old_job = paths['job_proposed']
    paths['job_proposed'] = job
    paths['backups_proposed'] = {
        key: [x.replace(old_job, job) for x in value] if type(value) is list
             else value.replace(old_job, job)
        for key, value in paths['backups_proposed'].items()}
    paths['target_release'] = [base + '/releases/' + release for base in
        ('/opt/xuanjun-cloud-connection', '/opt/xuanjun-cloud-oauth')]
    paths['stage_proposed'] = [base + '/releases/.l2-b5-staged-' + release[:12]
                               for base in ('/opt/xuanjun-cloud-connection',
                                            '/opt/xuanjun-cloud-oauth')]
    result = copy.deepcopy(old)
    result.update(schema='PR17_B5_STAGED_SUCCESSOR_V1',
                  state='DRAFT_NO_LIVE_PERMISSION',
                  original_spec_sha256=ORIGINAL_SHA256,
                  release=binding, fixed_paths=paths,
                  phases=list(PHASES),
                  protected_baseline=copy.deepcopy(old['observed_baseline']),
                  gates={
                'maintenance': ['original_owner_exact_approval', 'b5_same_batch_ack',
                                'authenticated_uk_maintenance_provider', 'original_lock',
                                'six_slot_backup_and_cas', 'two_current_identity'],
                'restore': ['precise_original_pre_start_restore_approval'],
                'close': ['precise_original_b5_exposure_close_approval'],
                'body': ['b5_request_local_project.files.read_each_call',
                 'received_bytes_and_sha_each_of_19']},
                  body_boundary='ORIGINAL_AUTHENTICATED_HTTP_ONLY',
                  maintenance_body_read=False)
    result['source']['target_release'] = release
    result['source']['target_manifest_sha256'] = binding['runtime_manifest_sha256']
    result['source']['target_code_pin'] = binding['code_pin_sha256']
    if manifest_raw is not None:
        manifest = decode(manifest_raw)
        result['source']['source_records'] = [dict(path=x['path'], bytes=x['bytes'],
                                                   sha256=x['sha256'], mode='0644')
                                             for x in manifest['files']]
    for row, phase in zip(result['phase_sequence'], PHASES):
        row['phase'] = phase
        if phase == 'PUBLISH_SUCCESSOR':
            row['step'] = 7
            row['required_result'] = ('Verify all 42 fixed runtime source bytes, '
                                      'the runtime manifest and code pin before '
                                      'bounded publication of the two exact '
                                      'successor releases; present target HOLD.')
        elif phase == 'ACTIVATE_SUCCESSOR':
            row['step'] = 8
            row['required_result'] = ('Switch the two current links and six '
                                      'protected config/slot bytes by the original '
                                      'lock and CAS, bound to this successor release.')
        elif phase == 'WINDOW_ENABLE':
            row['step'] = 13
            row['required_result'] = ('Only after actual scoped grant, same-batch '
                                      'analyst ACK, successor activation, conflict '
                                      'clearance and window approval begin the '
                                      'single 60-minute window.')
        if phase == 'B5_HTTP_RECEIVE_AND_VERIFY':
            row['step'] = 16
            row['required_result'] = ('Nineteen bound bytes/SHA/InvokeId proofs '
                                      'from B5 request-local authenticated cloud '
                                      'reads, linked to exact custody and close '
                                      'scope; no maintenance bearer or body grant.')
        elif phase == 'CLOSE_EXPOSURE':
            row['step'] = 17
            row['required_result'] = ('Close this successor B5 exposure under '
                                      'independent precise close approval; retain '
                                      'queue/history and never infer OAuth grant '
                                      'revocation from catalog expiry.')
    return result


def validate(raw, original_raw, binder_raw, manifest_raw, source_blobs):
    """Bind all 42 release bytes and the immutable old reviewed contract.

    The external binder is an input, never evidence of grant or site admission.
    The separate final B5 HTTP step must retain the same 19 catalog objects.
    """
    spec, old, binding, manifest = map(decode, (raw, original_raw, binder_raw, manifest_raw))
    require(spec.get('schema') == 'PR17_B5_STAGED_SUCCESSOR_V1', 'SUCCESSOR_SCHEMA')
    require(spec.get('state') == 'DRAFT_NO_LIVE_PERMISSION', 'SUCCESSOR_STATE')
    require(sha(original_raw) == ORIGINAL_SHA256 and
            spec.get('original_spec_sha256') == ORIGINAL_SHA256, 'ORIGINAL_SPEC_PIN')
    require(old.get('schema') == 'PR17_C53_R2_STATIC_TRANSACTION_V1' and
            old.get('state') == 'REVIEW_ONLY_HOLD_NO_LIVE_EXECUTION', 'ORIGINAL_SPEC_KIND')
    require(tuple(x.get('phase') for x in old['phase_sequence']) ==
            tuple('PUBLISH_C53' if p == 'PUBLISH_SUCCESSOR' else
                  'ACTIVATE_C53' if p == 'ACTIVATE_SUCCESSOR' else
                  'RECEIVE_AND_VERIFY' if p == 'B5_HTTP_RECEIVE_AND_VERIFY' else p
                  for p in PHASES), 'ORIGINAL_PHASE_ORDER')
    require(spec.get('phases') == list(PHASES), 'SUCCESSOR_PHASE_ORDER')
    require(spec.get('objects') == old['objects'] and len(spec['objects']) == 19 and
            sum(x['bytes'] for x in spec['objects']) == 93592, 'OBJECT_SCOPE')
    require(spec.get('batch') == old['batch'] and
            old['batch']['remote_requests_created'] == 0 and
            old['batch']['request_ids_reserved'] is False, 'OLD_BATCH_REPLAY')
    require(spec.get('actor') == old['actor'], 'ACTOR_CHANGED')
    require(spec.get('protected_baseline') == old['observed_baseline'], 'BASELINE_CHANGED')
    require(binding.get('schema') == 'B5_EXTERNAL_RELEASE_BINDER_V1' and
            binding.get('status') == 'SOURCE_IDENTITY_ONLY_NOT_INSTALL_ADMISSION',
            'EXTERNAL_BINDER_KIND')
    release = binding.get('release_commit')
    require(type(release) is str and len(release) == 40 and
            all(c in '0123456789abcdef' for c in release) and
            release != old['source']['target_release'], 'RELEASE_COMMIT')
    require(spec.get('release') == binding, 'EXTERNAL_BINDER_NOT_CONSUMED')
    require(sha(manifest_raw) == binding['runtime_manifest_sha256'] and
            manifest.get('schema') == 'B5_RUNTIME_SOURCE_V1' and
            manifest.get('code_pin_sha256') == binding['code_pin_sha256'] and
            manifest.get('source_manifest_sha256') == binding['source_manifest_sha256'],
            'RELEASE_MANIFEST_BINDING')
    files = manifest.get('files')
    require(type(files) is list and len(files) == 42 and type(source_blobs) is dict,
            'RELEASE_42_REQUIRED')
    paths = [x.get('path') for x in files]
    require(len(set(paths)) == 42 and set(paths) == set(source_blobs) and
            all(type(p) is str and not p.startswith('/') and '..' not in p.split('/')
                for p in paths), 'RELEASE_PATHS')
    for item in files:
        data = source_blobs[item['path']]
        require(type(data) is bytes and type(item.get('bytes')) is int and
                len(data) == item['bytes'] and sha(data) == item['sha256'],
                'RELEASE_SOURCE_BYTES')
    paths = spec.get('fixed_paths')
    require(type(paths) is dict and
            paths.get('target_release') == [base + '/releases/' + release for base in
                  ('/opt/xuanjun-cloud-connection', '/opt/xuanjun-cloud-oauth')],
            'SUCCESSOR_RELEASE_PATHS')
    require(paths.get('configs') == old['fixed_paths']['configs'] and
            paths.get('protected_slots') == old['fixed_paths']['protected_slots'] and
            paths.get('current') == old['fixed_paths']['current'] and
            paths.get('receiver_root') == old['fixed_paths']['receiver_root'] and
            paths.get('job_proposed') != old['fixed_paths']['job_proposed'] and
            paths.get('stage_proposed') != old['fixed_paths']['stage_proposed'],
            'SUCCESSOR_PROTECTED_PATHS')
    gates = spec.get('gates')
    require(gates == {
        'maintenance': ['original_owner_exact_approval', 'b5_same_batch_ack',
                        'authenticated_uk_maintenance_provider', 'original_lock',
                        'six_slot_backup_and_cas', 'two_current_identity'],
        'restore': ['precise_original_pre_start_restore_approval'],
        'close': ['precise_original_b5_exposure_close_approval'],
        'body': ['b5_request_local_project.files.read_each_call',
                 'received_bytes_and_sha_each_of_19']}, 'STAGED_GATES')
    require(spec.get('body_boundary') == 'ORIGINAL_AUTHENTICATED_HTTP_ONLY' and
            spec.get('maintenance_body_read') is False, 'BODY_ROLE_SEPARATION')
    require(spec == derive(original_raw, binder_raw, manifest_raw),
            'SUCCESSOR_SPEC_UNEXPECTED_FIELDS')
    return {'state': 'SOURCE_AND_CONTRACT_VERIFIED_NOT_ADMITTED',
            'release': release, 'source_count': 42, 'object_count': 19,
            'runtime_manifest_sha256': sha(manifest_raw)}
