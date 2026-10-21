"""Candidate orchestration only: no CLI, entropy default or production adapter.

Admission is a trusted injected boundary, NOT a user-supplied approval boolean.
Its claim(request_bytes, now) must authenticate exact Owner scope/custody evidence
and durably consume one attempt before returning a grant. check(request_bytes,
grant_bytes, now) must revalidate that same claim (including revocation), returning
the identical grant bytes. No such real adapter is supplied here. Test adapters
and shape-valid grants do not constitute actual permission.
"""
from __future__ import annotations

import json
import math

from tools import pr122_login_config_prepare as prepare


OPERATION = 'FIRST_LOGIN_ONLY_PREPARE_V1'
MAX_GRANT_SECONDS = 300


class _Refused(Exception):
    pass


def _need(value, code):
    if not value:
        raise _Refused(code)


def _clock(source):
    value = source()
    _need(type(value) in (int, float) and math.isfinite(value) and value >= 0,
          'CLOCK_INVALID')
    return value


def _grant(raw, request_sha256, now):
    _need(type(raw) is bytes and len(raw) <= prepare.MAX_FILE_BYTES, 'ADMISSION_DENIED')
    grant = prepare._json(raw)
    _need(type(grant) is dict and set(grant) == {
        'schema', 'decision', 'request_sha256', 'authority_ref',
        'issued_unix', 'expires_unix'}, 'ADMISSION_DENIED')
    _need(prepare.canonical(grant) == raw and type(grant['schema']) is int
          and grant['schema'] == 1 and grant['decision'] == 'ADMITTED'
          and grant['request_sha256'] == request_sha256
          and prepare._text(grant['authority_ref'], 1024), 'ADMISSION_DENIED')
    start, end = grant['issued_unix'], grant['expires_unix']
    _need(type(start) is int and type(end) is int
          and 0 <= start <= now < end and end - start <= MAX_GRANT_SECONDS,
          'ADMISSION_EXPIRED')


def _report(state, error=None):
    result = {'state': state, 'production': 'NOT_INSTALLABLE',
              'target_acceptance': 'NOT_VERIFIED', 'secret_values': 'NOT_DISPLAYED',
              'retry_allowed': False}
    if error:
        result['error'] = error
    return result


class InitialPreparation:
    """One invocation per instance; trusted adapter also owns durable consumption.

    All request inputs are snapshotted before calling dependencies. Caller,
    ownership proofs, two-key custody and output approval must be verified by
    admission against the exact request, not inferred from the assessment JSON.
    The public result contains no supplied references, secrets or exception text.
    """
    def __init__(self, *, admission=None, entropy_source=None, clock=None):
        self._admission = admission
        self._entropy = entropy_source
        self._clock = clock
        self._used = False

    def run(self, *, assessment, observation, manifest_sha256, key_id,
            backup_key_ref, smtp, output_path):
        if self._used:
            return _report('HOLD', 'ATTEMPT_ALREADY_USED')
        self._used = True
        write_started = False
        try:
            adapter = self._admission
            _need(adapter is not None and callable(getattr(adapter, 'claim', None))
                  and callable(getattr(adapter, 'check', None))
                  and callable(self._entropy) and callable(self._clock),
                  'ADAPTER_REQUIRED')
            # Freeze all caller-owned containers, including secret SMTP material.
            frozen = json.loads(prepare.canonical({
                'assessment': assessment, 'manifest_sha256': manifest_sha256,
                'key_id': key_id, 'backup_key_ref': backup_key_ref, 'smtp': smtp}))
            _need(type(observation) is bytes, 'INPUT_INVALID')
            now = _clock(self._clock)
            prepare._initial_assessment(frozen['assessment'], observation,
                                        frozen['manifest_sha256'], now)
            prepare.require(type(frozen['key_id']) is str
                            and prepare.ID.fullmatch(frozen['key_id']), 'DATA_KEYS')
            prepare.require(prepare._text(frozen['backup_key_ref'], 1024), 'BACKUP_REFERENCE')
            prepare._smtp(frozen['smtp'])
            output = prepare._path(output_path)
            request = prepare.canonical({
                'operation': OPERATION, 'target': prepare.INITIAL_TARGET,
                'profile': prepare.PROFILE, 'initialization_mode': prepare.INITIAL_LOGIN,
                'material_classes': ['data', 'backup'], 'authority_key': 'NOT_CREATED',
                'key_id': frozen['key_id'], 'backup_key_ref': frozen['backup_key_ref'],
                'data_material_location': str(output / 'config.json'),
                'output': str(output), 'inputs_sha256': prepare.digest(prepare.canonical(frozen)),
                'observation_sha256': prepare.digest(observation)})
            request_sha = prepare.digest(request)
            grant = adapter.claim(request, now)
            _grant(grant, request_sha, now)
            # Existing/unsafe output is refused before entropy or file creation.
            prepare._preflight_output(output)

            def recheck():
                nonlocal now
                fresh = _clock(self._clock)
                _need(fresh >= now, 'CLOCK_INVALID')
                now = fresh
                _grant(grant, request_sha, now)
                _need(adapter.check(request, grant, now) == grant,
                      'ADMISSION_DENIED')
                prepare._initial_assessment(frozen['assessment'], observation,
                                            frozen['manifest_sha256'], now)
                prepare._preflight_output(output)

            recheck()
            config, _ = prepare.prepare_initial_pair(
                frozen['assessment'], observation,
                manifest_sha256=frozen['manifest_sha256'], now=now,
                key_id=frozen['key_id'], backup_key_ref=frozen['backup_key_ref'],
                smtp=frozen['smtp'], entropy_source=self._entropy)
            recheck()
            write_started = True
            prepare.write_bundle(output, config)
            # Reuse the original bounded private-file/hash reader after publish.
            prepare.inspect_bundle(output)
            return _report('PREPARED_OFFLINE_SYNTHETIC_CANDIDATE')
        except _Refused as exc:
            return _report('UNKNOWN' if write_started else 'NOT_PREPARED', exc.args[0])
        except prepare.ConfigError as exc:
            return _report('UNKNOWN' if write_started else 'NOT_PREPARED', exc.code)
        except BaseException:
            # Includes cancellation, interrupted publication and adapter failures.
            # Preserve existing/staging files, never cleanup or automatically retry.
            return _report('UNKNOWN' if write_started else 'NOT_PREPARED', 'PREPARATION_FAILED')
