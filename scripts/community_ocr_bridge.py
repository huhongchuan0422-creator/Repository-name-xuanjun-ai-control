"""Community source callbacks for pinned OCR 90aca1cf; no network or new grant.

Production permission admission remains closed until an existing ocr:use
mapping is independently evidenced. Test admission is not production authority.
"""
from scripts.community_mini_merchant import MiniMerchant

OCR_SOURCE_SHA = '90aca1cfca1ec2a354950c394a4b0c2689b37d13'
OCR_SOURCE_TREE = 'cdb3918520b176286af570101c75885bcf07cde4'
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
        reader = self.merchant.ocr_shared_source if self.merchant.onboarding.wechat_applyment is not None else self.merchant.ocr_source
        source = reader(p._community_token, self.scene, application, KINDS[document_type])
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
        result = {'authorized': True, 'content_sha256': source['document_sha256'],
                  'document_type': document_type, 'application_revision': source['application_revision']}
        if 'wechat_version' in source:
            result['provider_version'] = source['wechat_version']
        return result

    @on_owner
    def apply_confirmed(self, p, job_id, *, expected_confirmation_revision):
        """Protected host-only writeback from configured encrypted OCR store.

        No HTTP body can supply fields/authority. Recheck the source and original
        revision before original onboarding's locked CAS; fill only empty fields.
        """
        if 'ocr:use' not in p.permissions:
            raise PermissionError('OCR_PERMISSION_DENIED')
        self._context(p)
        job = self.store.get(job_id, p.tenant_id)
        if (not job or job['subject'] != p.subject or job['tenant_id'] != p.tenant_id
                or job['job_id'] != job_id or job['status'] != 'confirmed'):
            raise PermissionError('OCR_CONFIRMED_JOB_REQUIRED')
        if (type(expected_confirmation_revision) is not int or expected_confirmation_revision < 1
                or type(job.get('confirmation_revision')) is not int
                or job['confirmation_revision'] != expected_confirmation_revision):
            raise PermissionError('OCR_CONFIRMATION_SNAPSHOT_CHANGED')
        binding = job.get('confirmed_binding')
        if type(binding) is not dict:
            raise PermissionError('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED')
        revision = job.get('application_revision')
        if (type(revision) is not str or not __import__('re').fullmatch('[1-9][0-9]*', revision)):
            raise PermissionError('OCR_APPLICATION_REVISION_INVALID')
        fields = job.get('confirmed_fields')
        allowed = ({'company_name','credit_code','legal_representative','registered_address','business_scope'}
                   if job['document_type'] == 'business_license' else {'id_name','id_number','registered_address'})
        if (type(fields) is not dict or not fields or not set(fields)<=allowed
                or any(type(value) is not str for value in fields.values())):
            raise PermissionError('OCR_CONFIRMED_FIELDS_INVALID')
        expected = dict(application_revision=revision, provider_version=job.get('provider_version'),
            document_type=job['document_type'], attachment_id=job['attachment_id'], content_sha256=job['document_sha256'])
        if (binding != expected or set(binding)!=set(expected)
                or type(binding['application_revision']) is not str
                or type(binding['provider_version']) is not type(job.get('provider_version'))):
            raise PermissionError('OCR_CONFIRMED_BINDING_CHANGED')
        source = self.source(p,job['onboarding_application_id'],job['document_type'])
        if (source['attachment_id'] != job['attachment_id'] or source['document_sha256'] != job['document_sha256']
                or source['application_revision'] != revision):
            raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
        service = self.merchant.onboarding.wechat_applyment
        if service is not None:
            version = job.get('provider_version')
            if type(version) is not int or version < 0:
                raise PermissionError('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED')
            if source['wechat_version'] != version:
                raise PermissionError('OCR_PROVIDER_VERSION_CHANGED')
            if job['document_type'] != 'business_license':
                return {'written':False,'revision':int(revision),'reason':'OCR_IDCARD_TARGET_UNDEFINED'}
            confirmed = {key:value for key,value in fields.items()
                         if key in ('company_name','registered_address') and value.strip()}
            if not confirmed:
                return {'written':False,'revision':int(revision)}
            uid,_,csrf,_ = self.merchant.context(p._community_token,self.scene)
            def check(application_version,provider_version):
                # Original Center transaction is already held by the primitive.
                # Never call the independent-transaction shared reader here.
                self._context(p)
                current = self.store.get(job_id,p.tenant_id)
                import json
                if json.dumps(current,sort_keys=True) != json.dumps(job,sort_keys=True):
                    raise PermissionError('OCR_CONFIRMATION_SNAPSHOT_CHANGED')
                now = self.merchant.ocr_source(p._community_token,self.scene,job['onboarding_application_id'],KINDS[job['document_type']])
                if (now['subject'] != p.subject or now['tenant_id'] != p.tenant_id
                        or now['document_type'] != job['document_type']
                        or now['attachment_id'] != job['attachment_id'] or now['document_sha256'] != job['document_sha256']
                        or now['application_revision'] != application_version):
                    raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
                provider = service._read(job['onboarding_application_id'])
                current_version = 0 if provider is None else provider['version']
                if type(current_version) is not int or current_version != provider_version:
                    raise PermissionError('OCR_PROVIDER_VERSION_CHANGED')
            return service.fill_confirmed_license_draft(p._community_token,csrf,job['onboarding_application_id'],
                expected_application_revision=int(revision),expected_wechat_version=version,
                confirmed_fields=confirmed,source_check=check)
        self.authorize_attachment(p, job['onboarding_application_id'], job['attachment_id'],
            job['document_sha256'], job['document_type'], revision)
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
