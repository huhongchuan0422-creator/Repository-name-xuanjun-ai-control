"""Startup-only applyment readers; no account/config/network/database writes.

The original commerce reader remains unchanged. Only protected host assembly
supplies additional readers; no HTTP provider hint is accepted here.
"""
import re
from types import MappingProxyType


class ApplymentReaders:
    def __init__(self, legacy, additional=None, submission_provider=None):
        configured = additional is not None
        if additional is not None and type(additional) is not dict:
            raise ValueError('EXACT_APPLYMENT_READER_MAP_REQUIRED')
        readers = {legacy._mchid: legacy}
        for merchant, reader in (additional or {}).items():
            if (type(merchant) is not str or not re.fullmatch('[0-9]{6,32}', merchant)
                    or merchant != reader._mchid or merchant in readers):
                raise ValueError('APPLYMENT_READER_IDENTITY_MISMATCH')
            readers[merchant] = reader
        if configured and submission_provider is None:
            raise ValueError('SUBMISSION_PROVIDER_READER_REQUIRED')
        default = legacy._mchid if submission_provider is None else submission_provider
        if type(default) is not str or default not in readers:
            raise ValueError('SUBMISSION_PROVIDER_READER_REQUIRED')
        self.readers = MappingProxyType(readers)
        self.submission_provider = default
        self.legacy = legacy
        self.configured = configured

    def for_record(self, record, *, submission=False):
        if type(record) is not dict:
            raise PermissionError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        merchant = record.get('provider_sp_mchid')
        if merchant is not None:
            if type(merchant) is not str or merchant not in self.readers:
                raise PermissionError('PROVIDER_APPLICATION_READER_UNAVAILABLE')
            return self.readers[merchant]
        traced = any(record.get(k) for k in (
            'business_code', 'applyment_id', 'submission_receipts',
            'submission_recovery_receipt', 'provider_applyment_history',
            'submission_started_at', 'submission_intent_token', 'provider_sign_url',
            'provider_sign_url_proof', 'provider_query_signature_sha256'))
        if self.configured and (record.get('state') not in (None,'DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED')
                or record.get('provider_state') not in (None,'NOT_SUBMITTED')):
            traced = True
        if traced and self.configured:
            # A legacy accepted/unknown record is not a new unbound draft.
            # Its provider cannot be inferred by trying either account.
            raise PermissionError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        if traced and submission and record.get('business_code'):
            raise PermissionError('PROVIDER_APPLICATION_DOMAIN_UNCONFIRMED_QUERY_REQUIRED')
        return self.readers[self.submission_provider] if not traced else self.legacy
