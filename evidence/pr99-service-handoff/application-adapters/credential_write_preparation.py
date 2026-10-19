"""Prepare native encryption without writing the original repository.

The result is PRIVATE encrypted record material. It must be committed with its
binding by the original durable write controller; this module does not install
an application hook or authorize a production write.
"""
from credential_key_binding import CredentialBindingHold, fingerprint
from datetime import datetime


class _CaptureRepository:
    def __init__(self):
        self.record = None
        self.calls = 0

    def save(self, record):
        self.calls += 1
        if self.calls != 1 or not isinstance(record, dict):
            raise CredentialBindingHold('NATIVE_SAVE_CONTRACT_CHANGED')
        self.record = dict(record)
        self.record.setdefault('legacy_migration_required', 0)
        # SQLite BOOLEAN columns return integers. Normalize new envelopes only;
        # historical binding fingerprints remain unchanged.
        if self.record['legacy_migration_required'] in (False, 0):
            self.record['legacy_migration_required'] = 0
        # Native save returns the repository's complete record. This staging
        # repository deliberately does not fabricate timestamps or IDs.
        return dict(self.record)

    def get(self, credential_id):
        if self.record is None or self.record.get('credential_id') != credential_id:
            return None
        return dict(self.record)

    def update_status(self, credential_id, status, verification_state=None,
                      permission_state=None, last_verified_time=None, metadata=None):
        if self.record is None or self.record['credential_id'] != credential_id:
            raise CredentialBindingHold('VERIFICATION_RECORD_MISMATCH')
        self.record['status'] = status
        for name, value in (('verification_state', verification_state),
                            ('permission_state', permission_state),
                            ('last_verified_time', last_verified_time), ('metadata', metadata)):
            if value is not None:
                if name == 'last_verified_time':
                    if not isinstance(value, datetime):
                        raise CredentialBindingHold('VERIFICATION_TIME_REQUIRED')
                    value = value.isoformat(sep=' ')
                self.record[name] = value
        return dict(self.record)


def prepare_native_save(native_store_factory, key_ref, key_input, **arguments):
    """Use verified native save AND load methods against a private capture only.

    No real repository is accepted. Caller must supply an explicit credential
    ID so a lost result never becomes permission to generate another write.
    Plaintext arguments/results are never included in the returned envelope.
    """
    return _prepare(native_store_factory, key_ref, key_input, None, arguments)


def prepare_native_verified_save(native_store_factory, key_ref, key_input,
                                 verification, **arguments):
    """Stage original save + mark_verified on the SAME private capture.

    Caller supplies already obtained validation results and stable time/ID.
    No validator, exchange, live repository or session save is invoked here.
    """
    required = {'status', 'verification_state', 'permission_state', 'verified_time', 'metadata'}
    if not isinstance(verification, dict) or set(verification) != required:
        raise CredentialBindingHold('VERIFICATION_INPUTS_REQUIRED')
    return _prepare(native_store_factory, key_ref, key_input, verification, arguments)


def _prepare(native_store_factory, key_ref, key_input, verification, arguments):
    try:
        credential_id = arguments.get('credential_id')
        if (not isinstance(credential_id, str) or not credential_id or
                not isinstance(key_ref, str) or not key_ref or
                not isinstance(key_input, str) or not key_input):
            raise CredentialBindingHold('EXPLICIT_WRITE_INPUTS_REQUIRED')
        capture = _CaptureRepository()
        store = native_store_factory(repository=capture, master_key=key_input)
        store.save_credential(**arguments)
        if capture.calls != 1 or capture.record is None:
            raise CredentialBindingHold('NATIVE_SAVE_CONTRACT_CHANGED')
        if verification is not None:
            store.mark_verified(credential_id, **verification)
        record = dict(capture.record)
        if record.get('credential_id') != credential_id:
            raise CredentialBindingHold('CREDENTIAL_ID_CHANGED')
        digest = fingerprint(record)
        restored = store.load_credential(credential_id)
        try:
            if (restored['api_key'] != arguments['api_key'] or
                    restored['api_secret'] != arguments['api_secret']):
                raise CredentialBindingHold('NATIVE_ROUNDTRIP_MISMATCH')
        finally:
            del restored
        return {'record': record,
                'binding': {'record_sha256': digest, 'key_ref': key_ref},
                'state': 'PREPARED_NOT_COMMITTED'}
    except CredentialBindingHold:
        raise
    except Exception:
        raise CredentialBindingHold('NATIVE_WRITE_PREPARATION_FAILED') from None
