"""Offline package qualification only: no registry, payment, auth or release writes.
Caller must supply authoritative snapshots; untrusted manifest never grants authority.
"""
import hashlib
import json
import re

BASES = ('identity', 'crm', 'tenant', 'rbac', 'model_router')
GATES = ('technical', 'security', 'operational', 'documentation',
         'customer_prerequisites', 'reuse_rights', 'pricing', 'finance_margin', 'support')
ID = re.compile(r'[a-z][a-z0-9_.-]{0,95}\Z')
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
REFERENCE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/@#?=&%+~-]{0,511}\Z')


def valid_reference(value):
    return isinstance(value, str) and bool(REFERENCE.fullmatch(value))


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def assess(manifest, artifact, context, receipts):
    """Return local qualification, never actual publication or tenant entitlement.

    context/receipts are trusted-adapter inputs, not request-body booleans. Receipt
    authority authenticity is deliberately outside this offline implementation.
    Exact dependency pins only. No resolving, fetching or installing dependencies.
    """
    errors = []
    def require(ok, code):
        if not ok:
            errors.append(code)
    if not all(isinstance(v, dict) for v in (manifest, context, receipts)):
        return result(['INVALID_INPUT'])
    for field in ('installed_versions', 'foundation_refs', 'trusted_authorities'):
        if not isinstance(context.get(field, {}), dict):
            return result(['INVALID_CONTEXT:' + field])
    for field in ('allowed_tenant_ids', 'allowed_permissions', 'approved_offer_refs'):
        values = context.get(field, [])
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            return result(['INVALID_CONTEXT:' + field])
    if not all(isinstance(v, list) and all(valid_reference(x) for x in v)
               for v in context.get('trusted_authorities', {}).values()):
        return result(['INVALID_AUTHORITIES'])
    allowed = {'schema_version', 'module_id', 'version', 'name', 'capabilities',
               'dependencies', 'foundation_refs', 'tenant_ids', 'required_permissions',
               'artifact_sha256', 'source_ref', 'owner_ref', 'release_state', 'offer_refs'}
    require(set(manifest) == allowed, 'MANIFEST_FIELDS')
    require(manifest.get('schema_version') == '1', 'SCHEMA_VERSION')
    require(isinstance(manifest.get('module_id'), str) and bool(ID.fullmatch(manifest['module_id'])), 'MODULE_ID')
    require(isinstance(manifest.get('version'), str) and bool(VERSION.fullmatch(manifest['version'])), 'EXACT_VERSION')
    require(isinstance(manifest.get('name'), str) and bool(manifest['name'].strip()), 'NAME')
    for field in ('source_ref', 'owner_ref'):
        require(valid_reference(manifest.get(field)), field.upper())
    require(manifest.get('release_state') == 'CANDIDATE', 'STATE_NOT_CANDIDATE')
    for field in ('capabilities', 'tenant_ids', 'required_permissions', 'offer_refs'):
        values = manifest.get(field)
        require(isinstance(values, list) and len(values) > 0 and
                all(isinstance(v, str) and bool(ID.fullmatch(v)) for v in values) and
                len(set(values)) == len(values), field.upper())
    deps = manifest.get('dependencies')
    require(isinstance(deps, dict), 'DEPENDENCIES')
    if isinstance(deps, dict):
        for key, value in deps.items():
            require(isinstance(key, str) and bool(ID.fullmatch(key)) and
                    key != manifest.get('module_id') and isinstance(value, str) and
                    bool(VERSION.fullmatch(value)), 'DEPENDENCY_PIN')
            require(context.get('installed_versions', {}).get(key) == value, 'DEPENDENCY_UNAVAILABLE:' + str(key))
    foundations = manifest.get('foundation_refs')
    require(isinstance(foundations, dict) and set(foundations) == set(BASES), 'FOUNDATION_REUSE')
    if isinstance(foundations, dict):
        for key in BASES:
            value = foundations.get(key)
            require(valid_reference(value) and
                    context.get('foundation_refs', {}).get(key) == value, 'FOUNDATION_BINDING:' + key)
    sha = manifest.get('artifact_sha256')
    require(isinstance(sha, str) and bool(HEX.fullmatch(sha)), 'ARTIFACT_DIGEST')
    require(isinstance(artifact, bytes) and hashlib.sha256(artifact if isinstance(artifact, bytes) else b'').hexdigest() == sha, 'ARTIFACT_MISMATCH')
    require(context.get('writer_owner_ref') == manifest.get('owner_ref') and
            valid_reference(context.get('writer_owner_ref')), 'WRITER_UNCONFIRMED')
    if errors:
        return result(errors)
    for tenant in manifest['tenant_ids']:
        require(tenant in context.get('allowed_tenant_ids', []), 'TENANT_DENIED:' + tenant)
    require(set(manifest['required_permissions']).issubset(set(context.get('allowed_permissions', []))), 'PERMISSION_DENIED')
    require(set(manifest['offer_refs']).issubset(set(context.get('approved_offer_refs', []))), 'OFFER_NOT_APPROVED')
    digest = manifest_digest(manifest)
    now = context.get('now')
    require(type(now) is int and now >= 0, 'TRUSTED_TIME_REQUIRED')
    for gate in GATES:
        receipt = receipts.get(gate)
        valid = isinstance(receipt, dict) and receipt.get('decision') == 'PASS' and receipt.get('manifest_sha256') == digest and receipt.get('artifact_sha256') == sha and receipt.get('module_id') == manifest['module_id'] and receipt.get('version') == manifest['version'] and valid_reference(receipt.get('authority_ref')) and receipt.get('authority_ref') in context.get('trusted_authorities', {}).get(gate, []) and valid_reference(receipt.get('evidence_ref')) and type(receipt.get('issued_at')) is int and type(receipt.get('expires_at')) is int and type(now) is int and receipt['issued_at'] <= now < receipt['expires_at']
        require(valid, 'EVIDENCE_MISSING_OR_INVALID:' + gate)
    return result(errors, digest)


def result(errors, digest=None):
    return {'local_qualification': 'BLOCKED' if errors else 'PENDING_LISTING_REVIEW',
            'manifest_sha256': digest, 'reasons': sorted(set(errors)),
            'published': False, 'production_ready': False, 'entitlement_granted': False,
            'scope': 'OFFLINE_CANDIDATE_ONLY',
            'tenant_authorization': 'NOT_VERIFIED',
            'permission_authorization': 'NOT_VERIFIED',
            'dependency_closure': 'UNKNOWN',
            'receipt_authenticity': 'NOT_VERIFIED',
            'integration_readiness': 'BLOCKED_PENDING_AUTHORITATIVE_ADAPTERS'}
