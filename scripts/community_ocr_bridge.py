"""Community source callbacks for pinned OCR 90aca1cf plus explicit API schema successor.

Legacy scene permission admission remains closed. The separately protected
applicant opt-in admits only the verified mini account's own application, not
a merchant tenant or project grant. Test admission is not production authority.
"""
from scripts.community_mini_merchant import MiniMerchant

OCR_SOURCE_SHA = '90aca1cfca1ec2a354950c394a4b0c2689b37d13'
OCR_SOURCE_TREE = 'cdb3918520b176286af570101c75885bcf07cde4'
KINDS = {'business_license': 'business_license', 'id_front': 'identity_front', 'id_back': 'identity_back'}
CONFIRMED_KEYS = {
    'business_license': {'company_name','credit_code','legal_representative','registered_address','business_scope'},
    'id_front': {'id_name','id_number','registered_address'},
    'id_back': {'issuing_authority','valid_from','valid_to'},
}


def application_revision(value):
    # Original Center revisions are positive integers; OCR freezes their decimal
    # string form. Never accept booleans, floats, padded or caller-made revisions.
    if type(value) is not int or value < 1:
        raise PermissionError('OCR_APPLICATION_REVISION_INVALID')
    return str(value)


def on_owner(method):
    def invoke(self, *args, **kwargs):
        from scripts.community_ocr_host import current_diagnostic, _attach_failure, _CURRENT_DIAGNOSTIC
        context=current_diagnostic()
        stage={'authenticate':'AUTHENTICATION','authorize_application':'APPLICATION_AUTHORIZATION',
               'source':'SOURCE_BINDING','authorize_attachment':'SOURCE_BINDING','apply_confirmed':'WRITEBACK','recovery_view':'RESULT_READ','recovery_confirm':'CONFIRMATION','recovery_apply':'WRITEBACK'}.get(method.__name__,'ADMISSION')
        def execute():
            import threading
            if context:context.phase(stage)
            if threading.get_ident() != self.owner_thread:
                raise PermissionError('OCR_CENTER_OWNER_THREAD_REQUIRED')
            reset=_CURRENT_DIAGNOSTIC.set(context)
            try:return method(self, *args, **kwargs)
            except BaseException as error:
                _attach_failure(error,context,stage=stage);raise
            finally:
                if context:context.phase({'submit':'QUEUE','read':'RESULT_READ','confirm':'CONFIRMATION','apply_confirmed':'WRITEBACK','recover_view':'RESULT_READ','recover_confirm':'CONFIRMATION','recover_apply':'WRITEBACK'}.get(context.action,'ADMISSION'))
                _CURRENT_DIAGNOSTIC.reset(reset)
        execute.ocr_context=context;execute.ocr_stage=stage
        return self.owner_call(execute)
    return invoke


class CommunityOcrBridge:
    def __init__(self, merchant, scene, principal_type, owner_call, *, applicant_mode=False):
        if type(applicant_mode) is not bool or type(merchant) is not MiniMerchant or (scene!='' if applicant_mode else scene not in merchant.identity.scenes):
            raise PermissionError('ORIGINAL_OCR_SOURCE_REQUIRED')
        from pydantic import PrivateAttr
        class BoundPrincipal(principal_type):
            _community_token: str = PrivateAttr()
        self.merchant, self.scene, self.principal_type = merchant, scene, BoundPrincipal
        self.applicant_mode=applicant_mode
        import threading
        self.owner_call = owner_call
        self.owner_thread = threading.get_ident()

    @on_owner
    def authenticate(self, token):
        if self.applicant_mode:
            uid,_=self.merchant.identity.applicant_context(token)
            # Account-local OCR partition, not a merchant tenant or project grant.
            p=self.principal_type(subject=uid,tenant_id='community-applicant:'+uid,permissions={'ocr:use'})
        else:
            uid, project, csrf, principal = self.merchant.context(token, self.scene)
            origin = self.merchant._ocr_origin(self.scene, project, principal)
            p = self.principal_type(subject=uid, tenant_id=origin['scope']['tenant_id'], permissions=set())
        p._community_token = token
        # Legacy scene mode has no permission mapping; explicit applicant mode is owner-only.
        return p

    def _context(self, p):
        if type(p) is not self.principal_type:
            raise PermissionError('OCR_ORIGINAL_SESSION_REQUIRED')
        if self.applicant_mode:
            uid,_=self.merchant.identity.applicant_context(p._community_token)
            if p.subject!=uid or p.tenant_id!='community-applicant:'+uid:raise PermissionError('OCR_PRINCIPAL_CHANGED')
            return uid,None
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
            return data['status'] in ('DRAFT','CORRECTION_REQUIRED') if self.applicant_mode else meta.get('ocr_origin') == origin
        except (PermissionError, ValueError, KeyError):
            return False

    @on_owner
    def source(self, p, application, document_type):
        self._context(p)
        if document_type not in KINDS:
            raise PermissionError('OCR_DOCUMENT_NOT_SUPPORTED')
        reader = self.merchant.ocr_shared_source if self.merchant.onboarding.wechat_applyment is not None else self.merchant.ocr_source
        source = reader(p._community_token, self.scene, application, KINDS[document_type],applicant=self.applicant_mode)
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
            from scripts.community_ocr_host import current_diagnostic
            context=current_diagnostic()
            if context:context.fail(reason='APPLICATION_REVISION_CHANGED' if expected_revision is not None and
                (type(expected_revision) is not str or expected_revision != source['application_revision']) else 'ATTACHMENT_CHANGED',stage='SOURCE_BINDING')
            raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
        # Observe (do not bypass or change) the API's subsequent provider-version
        # comparison, so a swallowed callback error cannot erase its safe cause.
        from scripts.community_ocr_host import current_diagnostic
        context=current_diagnostic()
        if (context and context.has_expected_binding and context.expected_provider_version is not None
                and source.get('wechat_version') != context.expected_provider_version):
            context.fail(reason='PROVIDER_VERSION_CHANGED',stage='SOURCE_BINDING')
        result = {'authorized': True, 'content_sha256': source['document_sha256'],
                  'document_type': document_type, 'application_revision': source['application_revision']}
        if 'wechat_version' in source:
            result['provider_version'] = source['wechat_version']
        return result

    @on_owner
    def recovery_view(self, p, application, document_type, locator, recovery_key):
        """New explicitly authorized exact-material view; old jobs stay immutable."""
        if 'ocr:use' not in p.permissions or not self.authorize_application(p, application):
            raise PermissionError('OCR_APPLICATION_DENIED')
        self._context(p)
        if type(locator) is not dict or set(locator) not in ({'job_id'}, {'original_key'}):
            raise ValueError('OCR_RECOVERY_EXACT_LOCATOR_REQUIRED')
        job = self.store.resolve_recovery_job(p.tenant_id,p.subject,application,document_type,**locator)
        from scripts.community_ocr_host import current_diagnostic
        context=current_diagnostic()
        if context:context.durable_job_retained=True
        source = self.source(p, application, document_type)
        for field in ('subject','tenant_id','document_type','attachment_id','document_sha256'):
            if source.get(field) != job.get(field):
                raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
        if job['status'] not in ('needs_review','confirmed'):
            raise ValueError('OCR_RECOVERY_RESULT_NOT_READY')
        if (type(source.get('application_revision')) is not str or not __import__('re').fullmatch('[1-9][0-9]*',source['application_revision'])
                or source.get('wechat_version') is not None and (type(source['wechat_version']) is not int or source['wechat_version']<0)):
            raise PermissionError('OCR_RECOVERY_BINDING_INVALID')
        binding = dict(application_revision=source['application_revision'],
            provider_version=source.get('wechat_version'),document_type=document_type,
            attachment_id=source['attachment_id'],content_sha256=source['document_sha256'])
        payload = dict(application=application,document_type=document_type,locator=locator,binding=binding)
        view = dict(recovery_id=recovery_key,revision=1,job_id=job['job_id'],
            subject=p.subject,tenant_id=p.tenant_id,onboarding_application_id=application,
            original_application_revision=job['application_revision'],
            original_provider_version=job.get('provider_version'),binding=binding,
            fields={k:v for k,v in job.get('fields',{}).items() if k in CONFIRMED_KEYS[document_type]-{'business_scope'}},status='needs_review',confirmed=False,
            requires_human_confirmation=True,authenticity_verified=False)
        # Exact retries return the original snapshot, never a newly bound one.
        result=self.store.recovery_record(p.tenant_id,p.subject,'view',recovery_key,payload,view)
        self._recovery_current(p,application,result)
        return result

    def _recovery_current(self, p, application, view):
        self._context(p)
        if (not self.authorize_application(p,application) or
                view.get('subject') != p.subject or view.get('tenant_id') != p.tenant_id or
                view.get('onboarding_application_id') != application):
            raise PermissionError('OCR_APPLICATION_DENIED')
        binding=view['binding']
        job=self.store.resolve_recovery_job(p.tenant_id,p.subject,application,binding['document_type'],job_id=view['job_id'])
        from scripts.community_ocr_host import current_diagnostic
        context=current_diagnostic()
        if context:context.durable_job_retained=True
        source=self.source(p,application,binding['document_type'])
        current=dict(application_revision=source['application_revision'],provider_version=source.get('wechat_version'),
            document_type=source['document_type'],attachment_id=source['attachment_id'],content_sha256=source['document_sha256'])
        from scripts.community_ocr_host import current_diagnostic
        context=current_diagnostic()
        if context:context.durable_job_retained=True
        if (current != binding or any(type(current[k]) is not type(binding[k]) for k in current) or job['attachment_id'] != binding['attachment_id'] or
                job['document_sha256'] != binding['content_sha256']):
            reason=('APPLICATION_REVISION_CHANGED' if type(current['application_revision']) is not type(binding['application_revision']) or current['application_revision']!=binding['application_revision'] else
                    'PROVIDER_VERSION_CHANGED' if type(current['provider_version']) is not type(binding['provider_version']) or current['provider_version']!=binding['provider_version'] else 'ATTACHMENT_CHANGED')
            if context:context.fail(reason=reason,stage='SOURCE_BINDING')
            raise PermissionError('OCR_RECOVERY_SOURCE_CHANGED')
        return source

    @on_owner
    def recovery_confirm(self,p,application,recovery_id,revision,fields,confirmation_key):
        if 'ocr:use' not in p.permissions:raise PermissionError('OCR_PERMISSION_DENIED')
        view=self.store.recovery_receipt(p.tenant_id,p.subject,'view',recovery_id)
        if not view:raise PermissionError('OCR_RECOVERY_VIEW_NOT_FOUND')
        self._recovery_current(p,application,view)
        if type(revision) is not int or revision != view['revision']:
            raise ValueError('OCR_RECOVERY_VIEW_CHANGED')
        allowed=CONFIRMED_KEYS[view['binding']['document_type']]-{'business_scope'}
        if (type(fields) is not dict or not fields or not set(fields)<=allowed or
                any(type(v) is not str or not v.strip() or len(v)>4096 for v in fields.values())):
            raise ValueError('OCR_CONFIRMED_FIELDS_INVALID')
        payload=dict(recovery_id=recovery_id,revision=revision,fields=fields,binding=view['binding'])
        confirmation=dict(view,confirmation_id=confirmation_key,confirmation_revision=1,
            confirmed_fields=dict(fields),status='confirmed',confirmed=True)
        result=self.store.recovery_record(p.tenant_id,p.subject,'confirm',confirmation_key,payload,confirmation)
        self._recovery_current(p,application,view)
        return result

    @on_owner
    def recovery_apply(self,p,application,recovery_id,confirmation_id,confirmation_revision,writeback_key):
        """Explicit blank-only save, with durable receipt in the original draft tx."""
        import hashlib,json
        if 'ocr:use' not in p.permissions:raise PermissionError('OCR_PERMISSION_DENIED')
        self._context(p)
        if not self.authorize_application(p,application):raise PermissionError('OCR_APPLICATION_DENIED')
        confirmation=self.store.recovery_receipt(p.tenant_id,p.subject,'confirm',confirmation_id)
        if (not confirmation or confirmation.get('recovery_id') != recovery_id
                or type(confirmation_revision) is not int
                or confirmation.get('confirmation_revision') != confirmation_revision
                or confirmation.get('onboarding_application_id') != application
                or confirmation.get('subject') != p.subject or confirmation.get('tenant_id') != p.tenant_id):
            raise PermissionError('OCR_RECOVERY_CONFIRMATION_REQUIRED')
        binding=confirmation['binding'];doc=binding['document_type']
        service=self.merchant.onboarding.wechat_applyment
        if service is None:raise PermissionError('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED')
        if type(writeback_key) is not str or not writeback_key:raise ValueError('OCR_RECOVERY_OPERATION_INVALID')
        # Current-material checks are mandatory even for a committed-receipt replay.
        def material(source):
            if any(source.get(k)!=v for k,v in dict(subject=p.subject,tenant_id=p.tenant_id,
                    document_type=doc,attachment_id=binding['attachment_id'],document_sha256=binding['content_sha256']).items()):
                raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
        original=self.store.resolve_recovery_job(p.tenant_id,p.subject,application,doc,job_id=confirmation['job_id'])
        from scripts.community_ocr_host import current_diagnostic
        context=current_diagnostic()
        if context:context.durable_job_retained=True
        material(self.source(p,application,doc))
        if original['attachment_id']!=binding['attachment_id'] or original['document_sha256']!=binding['content_sha256']:
            raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
        fields=confirmation['confirmed_fields']
        allowed={'business_license':('company_name','credit_code','legal_representative','registered_address'),'id_front':('id_name','id_number','registered_address'),'id_back':('valid_from','valid_to')}[doc]
        selected={k:v for k,v in fields.items() if k in allowed and v.strip()}
        if not selected:
            self._recovery_current(p,application,confirmation)
            return dict(written=False,application_revision=int(binding['application_revision']),wechat_version=binding['provider_version'],applied=[],skipped=[])
        uid,_,csrf,_=self.merchant._ocr_context(p._community_token,self.scene,self.applicant_mode)
        frozen=json.dumps(confirmation,sort_keys=True)
        def check(application_version,provider_version):
            self._context(p)
            current=self.store.recovery_receipt(p.tenant_id,p.subject,'confirm',confirmation_id)
            if json.dumps(current,sort_keys=True)!=frozen:raise PermissionError('OCR_CONFIRMATION_SNAPSHOT_CHANGED')
            # Original transaction is already open: use its in-transaction reader.
            now=self.merchant.ocr_source(p._community_token,self.scene,application,KINDS[doc],applicant=self.applicant_mode)
            material(now)
            if now['application_revision']!=application_version:raise PermissionError('OCR_APPLICATION_REVISION_CHANGED')
            provider=service._read(application);version=0 if provider is None else provider['version']
            if type(version) is not int or version!=provider_version:raise PermissionError('OCR_PROVIDER_VERSION_CHANGED')
            self.store.resolve_recovery_job(p.tenant_id,p.subject,application,doc,job_id=confirmation['job_id'])
        identity=json.dumps([p.tenant_id,p.subject,application,writeback_key],separators=(',',':'))
        request=json.dumps([recovery_id,confirmation_id,confirmation_revision,binding,fields],sort_keys=True,separators=(',',':'))
        receipt=dict(id=self.store._index('recovery-writeback/'+identity),payload_hash=hashlib.sha256(request.encode()).hexdigest())
        return service._fill_confirmed_document_draft(p._community_token,csrf,application,document_type=doc,
            expected_application_revision=int(binding['application_revision']),expected_wechat_version=binding['provider_version'],
            confirmed_fields=selected,source_check=check,recovery_receipt=receipt,recovery_replay_check=check)

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
        allowed = CONFIRMED_KEYS.get(job['document_type'],set())
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
        if service is None and job.get('provider_version') is not None:
            raise PermissionError('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED')
        if service is not None:
            version = job.get('provider_version')
            if type(version) is not int or version < 0:
                raise PermissionError('OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED')
            if source['wechat_version'] != version:
                raise PermissionError('OCR_PROVIDER_VERSION_CHANGED')
            allowed_fill={'business_license':('company_name','registered_address'),'id_front':('id_name','id_number','registered_address'),'id_back':('valid_from','valid_to')}[job['document_type']]
            # The official provider schema has no issuing-authority field. It is
            # retained in the encrypted OCR confirmation, never sent as a made-up field.
            confirmed = {key:value for key,value in fields.items() if key in allowed_fill and value.strip()}
            if not confirmed:
                return {'written':False,'revision':int(revision)}
            uid,_,csrf,_ = self.merchant._ocr_context(p._community_token,self.scene,self.applicant_mode)
            def check(application_version,provider_version):
                # Original Center transaction is already held by the primitive.
                # Never call the independent-transaction shared reader here.
                self._context(p)
                current = self.store.get(job_id,p.tenant_id)
                import json
                if json.dumps(current,sort_keys=True) != json.dumps(job,sort_keys=True):
                    raise PermissionError('OCR_CONFIRMATION_SNAPSHOT_CHANGED')
                now = self.merchant.ocr_source(p._community_token,self.scene,job['onboarding_application_id'],KINDS[job['document_type']],applicant=self.applicant_mode)
                if (now['subject'] != p.subject or now['tenant_id'] != p.tenant_id
                        or now['document_type'] != job['document_type']
                        or now['attachment_id'] != job['attachment_id'] or now['document_sha256'] != job['document_sha256']
                        or now['application_revision'] != application_version):
                    raise PermissionError('OCR_ATTACHMENT_BINDING_CHANGED')
                provider = service._read(job['onboarding_application_id'])
                current_version = 0 if provider is None else provider['version']
                if type(current_version) is not int or current_version != provider_version:
                    raise PermissionError('OCR_PROVIDER_VERSION_CHANGED')
            fill={'business_license':service.fill_confirmed_license_draft,'id_front':service.fill_confirmed_identity_draft,'id_back':service.fill_confirmed_identity_back_draft}[job['document_type']]
            return fill(p._community_token,csrf,job['onboarding_application_id'],
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


def compose(merchant, scene, ocr_api, store, owner_call, infer=None, *, applicant_mode=False):
    """Explicit host composition; default scene admission still denies ocr:use.

    Caller provides the exactly pinned API successor and original encrypted store. No
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
    bridge = CommunityOcrBridge(merchant, scene, ocr_api.Principal, owner_call,applicant_mode=applicant_mode)
    bridge.store = store
    options = dict(authenticate=bridge.authenticate, store=store,
        authorize_application=bridge.authorize_application, authorize_attachment=bridge.authorize_attachment)
    def recovery(operation,p,body):
        methods={'view':bridge.recovery_view,'confirm':bridge.recovery_confirm,'apply':bridge.recovery_apply}
        return methods[operation](p,**body)
    options['recovery']=recovery
    if infer is not None:
        options['infer'] = infer
    return bridge, ocr_api.create_app(**options)
