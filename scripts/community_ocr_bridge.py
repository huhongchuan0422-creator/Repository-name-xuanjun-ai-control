"""Community source callbacks for pinned OCR 2dc5eeb; no network or new grant.

Production permission admission remains closed until an existing ocr:use
mapping is independently evidenced. Test admission is not production authority.
"""
from scripts.community_mini_merchant import MiniMerchant

OCR_SOURCE_SHA = '2dc5eeb1d0d1ffb037314a8edcf5c2e16d645a40'
OCR_SOURCE_TREE = '2984f51d3ed29b2cc67646b8d885c00a04c12881'
KINDS = {'business_license': 'business_license', 'id_front': 'identity_front'}


def application_revision(value):
    # Original Center revisions are positive integers; OCR freezes their decimal
    # string form. Never accept booleans, floats, padded or caller-made revisions.
    if type(value) is not int or value < 1:
        raise PermissionError('OCR_APPLICATION_REVISION_INVALID')
    return str(value)


def on_owner(method):
    def invoke(self, *args, **kwargs):
        def execute():
            import threading
            if threading.get_ident() != self.owner_thread:
                raise PermissionError('OCR_CENTER_OWNER_THREAD_REQUIRED')
            return method(self, *args, **kwargs)
        return self.owner_call(execute)
    return invoke


class CommunityOcrBridge:
    def __init__(self, merchant, scene, principal_type, owner_call):
        if type(merchant) is not MiniMerchant or scene not in merchant.identity.scenes:
            raise PermissionError('ORIGINAL_OCR_SOURCE_REQUIRED')
        from pydantic import PrivateAttr
        class BoundPrincipal(principal_type):
            _community_token: str = PrivateAttr()
        self.merchant, self.scene, self.principal_type = merchant, scene, BoundPrincipal
        import threading
        self.owner_call = owner_call
        self.owner_thread = threading.get_ident()

    @on_owner
    def authenticate(self, token):
        uid, project, csrf, principal = self.merchant.context(token, self.scene)
        origin = self.merchant._ocr_origin(self.scene, project, principal)
        p = self.principal_type(subject=uid, tenant_id=origin['scope']['tenant_id'], permissions=set())
        p._community_token = token
        # No evidenced existing ocr:use mapping: the actual OCR HTTP gate rejects.
        return p

    def _context(self, p):
        if type(p) is not self.principal_type:
            raise PermissionError('OCR_ORIGINAL_SESSION_REQUIRED')
        uid, project, csrf, principal = self.merchant.context(p._community_token, self.scene)
        origin = self.merchant._ocr_origin(self.scene, project, principal)
        if p.subject != uid or p.tenant_id != origin['scope']['tenant_id']:
            raise PermissionError('OCR_PRINCIPAL_CHANGED')
        return uid, origin

    @on_owner
    def authorize_application(self, p, application):
        try:
            uid, origin = self._context(p)
            _, meta, data = self.merchant.onboarding._load(application, uid)
            return meta.get('ocr_origin') == origin
        except (PermissionError, ValueError, KeyError):
            return False

    @on_owner
    def source(self, p, application, document_type):
        self._context(p)
        if document_type not in KINDS:
            raise PermissionError('OCR_DOCUMENT_NOT_SUPPORTED')
        source = self.merchant.ocr_source(p._community_token, self.scene, application, KINDS[document_type])
        if source['subject'] != p.subject or source['tenant_id'] != p.tenant_id:
            raise PermissionError('OCR_PRINCIPAL_CHANGED')
        source['application_revision'] = application_revision(source['application_revision'])
        return source

    @on_owner
    def authorize_attachment(self, p, application, attachment, digest, document_type, expected_revision=None):
        source = self.source(p, application, document_type)
        if (source['attachment_id'] != attachment or source['document_sha256'] != digest
                or source['document_type'] != document_type
                or expected_revision is not None and (type(expected_revision) is not str
                    or expected_revision != source['application_revision'])):
            raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
        return {'authorized': True, 'content_sha256': source['document_sha256'],
                'document_type': document_type, 'application_revision': source['application_revision']}

    @on_owner
    def apply_confirmed(self, p, job_id):
        """Protected host-only writeback from configured encrypted OCR store.

        No HTTP body can supply fields/authority. Recheck the source and original
        revision before original onboarding's locked CAS; fill only empty fields.
        """
        if 'ocr:use' not in p.permissions:
            raise PermissionError('OCR_PERMISSION_DENIED')
        self._context(p)
        job = self.store.get(job_id, p.tenant_id)
        if not job or job['subject'] != p.subject or job['status'] != 'confirmed':
            raise PermissionError('OCR_CONFIRMED_JOB_REQUIRED')
        self.authorize_attachment(p, job['onboarding_application_id'], job['attachment_id'],
            job['document_sha256'], job['document_type'], job.get('application_revision'))
        _, meta, current = self.merchant.onboarding._load(job['onboarding_application_id'], p.subject)
        if application_revision(current['revision']) != job.get('application_revision'):
            raise PermissionError('OCR_APPLICATION_REVISION_CHANGED')
        fields = {key:current['fields'][key] for key in ('legal_name','store_name','address','contact')}
        mapping = {'company_name': 'legal_name', 'registered_address': 'address'} if job['document_type'] == 'business_license' else {}
        for key, target in mapping.items():
            value = job.get('confirmed_fields', {}).get(key)
            if not fields[target] and type(value) is str and value.strip():
                fields[target] = value
        if all(value == current['fields'][key] for key,value in fields.items()):
            return {'written': False, 'revision': current['revision']}
        # source() performs one more byte/scan/session read immediately before
        # dispatch. Original save then reloads under BEGIN IMMEDIATE + revision CAS.
        self.authorize_attachment(p, job['onboarding_application_id'], job['attachment_id'],
            job['document_sha256'], job['document_type'], job['application_revision'])
        result = self.merchant.dispatch(p._community_token, self.scene, {'operation':'onboarding','params':{
            'operation':'save','params':dict(application=job['onboarding_application_id'], revision=current['revision'],
                entity_type=meta['entity_type'], category=meta['category'], delegated=meta['delegated'], fields=fields)}})
        return {'written': True, 'revision': result['revision']}


def compose(merchant, scene, ocr_api, store, owner_call, infer=None):
    """Explicit host composition; default admission still denies ocr:use.

    Caller provides the pinned, unmodified OCR module and encrypted store. No
    importing a second engine tree from request data, no engine source writes.
    """
    import hashlib
    import json
    from pathlib import Path
    lock = json.loads(Path(__file__).with_name('community_ocr_dependency.json').read_text())
    root = Path(ocr_api.__file__).resolve().parent
    for name, digest in lock['files'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise PermissionError('OCR_PINNED_DEPENDENCY_REQUIRED')
    if type(store) is not ocr_api.SecureSQLiteJobStore:
        raise PermissionError('OCR_ENCRYPTED_STORE_REQUIRED')
    bridge = CommunityOcrBridge(merchant, scene, ocr_api.Principal, owner_call)
    bridge.store = store
    options = dict(authenticate=bridge.authenticate, store=store,
        authorize_application=bridge.authorize_application, authorize_attachment=bridge.authorize_attachment)
    if infer is not None:
        options['infer'] = infer
    return bridge, ocr_api.create_app(**options)
