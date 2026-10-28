"""Same-app merchant transport over original Center services, no new authority.

Applicant operations are owner-only. Merchant reads still require original,
live workspace grants and matching scene/store; consumers never inherit them.
"""
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_merchant_onboarding import MerchantOnboarding

APPLICANT={'catalog','mine','read','save','upload','remove_material','submit','withdraw','history',
           'notices','notice_read','wechat_read','wechat_save','wechat_submit_review','wechat_media','wechat_cashier_link'}
WRITES={'community.profile','community.item'}
READS={'community.orders','community.summary','community.orders_page',
       'community.order_detail','community.merchant_settings','community.ads',
       'community.ads_page','community.refund_preview','community.reconciliation'}

class MiniMerchant:
    def __init__(self,identity,onboarding,operations=None,collection_codes=None,ocr=None):
        if (type(identity) is not CenterIdentity or type(onboarding) is not MerchantOnboarding
                or identity.center is not onboarding.center
                or operations is not None and (operations.center is not identity.center or operations.runtime is not identity.runtime)):
            raise PermissionError('ORIGINAL_MINI_MERCHANT_SERVICES_REQUIRED')
        self.identity,self.onboarding,self.operations=identity,onboarding,operations
        self.collection_codes=collection_codes
        self.ocr=ocr
    def context(self,token,scene):
        return self.identity.merchant_context(token,scene)
    def _grant(self,token,scene,workspace):
        uid,pid,csrf,principal=self.context(token,scene)
        if self.operations is None:raise PermissionError('MERCHANT_OPERATIONS_NOT_CONFIGURED')
        from scripts.community_staff import Staff
        g=self.operations.grants.get(workspace)
        if g is None:g=Staff(self.operations).resolve(workspace,uid)
        if (g is None or g['user_id']!=uid or g['project']!=pid
                or g['role'] not in ('MERCHANT_ADMIN','STORE_STAFF')
                or g['scope']!=self.identity.runtime.bindings[principal]):
            raise PermissionError('MERCHANT_SCENE_GRANT_REQUIRED')
        return g,csrf
    def dispatch(self,token,scene,body):
        if (type(body) is not dict or set(body)!={'operation','params'}
                or type(body['operation']) is not str or type(body['params']) is not dict):
            raise ValueError('INVALID_MINI_MERCHANT_REQUEST')
        op,p=body['operation'],body['params']
        if scene == '':
            # Missing store context is allowed ONLY for this owner's application.
            # A supplied invalid/revoked scene never falls back to this branch.
            _,csrf=self.identity.applicant_context(token)
            if (op!='onboarding' or set(p)!={'operation','params'}
                    or type(p['operation']) is not str or p['operation'] not in APPLICANT):
                raise PermissionError('APPLICANT_OPERATION_REQUIRED')
            return self.onboarding.dispatch(token,csrf,p,source_origin=None)
        uid,pid,csrf,principal=self.context(token,scene)
        if op=='ocr':
            from scripts.community_ocr_host import HostOcr, OcrPublicError
            if type(self.ocr) is not HostOcr or self.ocr.merchant.identity is not self.identity or self.ocr.merchant.onboarding is not self.onboarding:
                raise OcrPublicError('OCR_UNAVAILABLE')
            try:return self.ocr.dispatch(token,scene,p)
            except PermissionError as error:
                from scripts.community_ocr_host import OcrPublicError
                code=str(error)
                if any(v in code for v in ('REVOKED','CHANGED','EXPIRED','REVISION','BINDING')):public='OCR_SOURCE_CHANGED'
                elif any(v in code for v in ('AUTH','SESSION','PERMISSION','PRINCIPAL')):public='OCR_AUTH_DENIED'
                else:public='OCR_UNAVAILABLE'
                raise OcrPublicError(public) from None
        if op=='collection_code':
            if set(p)!={'workspace'} or type(p['workspace']) is not str:raise ValueError('EXACT_COLLECTION_WORKSPACE_REQUIRED')
            from scripts.community_collection_code import CollectionCodes
            if type(self.collection_codes) is not CollectionCodes or self.collection_codes.gateway.identity is not self.identity:
                raise PermissionError('OFFICIAL_COLLECTION_CODE_NOT_CONFIGURED')
            return self.collection_codes.read(token,scene,p['workspace'])
        if op=='workspaces' and p=={}:
            names=[];permissions={}
            candidates=set(self.operations.grants if self.operations is not None else {})
            if self.operations is not None:
                candidates.update(row[0] for row in self.identity.center.db.execute(
                    "SELECT subject_idx FROM links WHERE channel='COMMUNITY_STAFF_GRANT' AND user_id=? AND active=1",(uid,)))
            for name in sorted(candidates):
                try:
                    grant,_=self._grant(token,scene,name)
                    self.operations.dispatch(token,csrf,{'workspace':name,'operation':'community.summary','params':{}})
                except PermissionError:continue
                names.append(name);permissions[name]={'profile_edit':grant['role']=='MERCHANT_ADMIN'}
            return {'workspaces':names,'permissions':permissions}
        if op=='onboarding':
            if set(p)!={'operation','params'} or type(p['operation']) is not str or p['operation'] not in APPLICANT:
                raise PermissionError('APPLICANT_OPERATION_REQUIRED')
            return self.onboarding.dispatch(token,csrf,p,source_origin=self._ocr_origin(scene,pid,principal))
        if op in ('read','write'):
            if set(p)!={'workspace','operation','params'} or type(p['operation']) is not str or p['operation'] not in (READS if op=='read' else WRITES) or type(p['workspace']) is not str:
                raise PermissionError('MERCHANT_READ_OPERATION_REQUIRED')
            grant,csrf=self._grant(token,scene,p['workspace'])
            if op=='write' and grant['role']!='MERCHANT_ADMIN':raise PermissionError('MERCHANT_ADMIN_REQUIRED')
            return self.operations.dispatch(token,csrf,p)
        raise PermissionError('MINI_MERCHANT_OPERATION_DENIED')

    def _ocr_origin(self,scene,project,principal):
        return {'project':project,'scene':scene,'scope':dict(self.identity.runtime.bindings[principal])}

    def ocr_shared_source(self,token,scene,application,kind):
        """Host-only source preparation, NOT an OCR resolver/API contract.

        Both original draft versions and current attachment bytes are observed
        under the same Center lock. Integers stay integers here; the approved
        OCR contract must define their wire representation and trusted binding.
        No confirmation authority, permission or writeback is created.
        """
        from scripts.community_wechat_applyment import WechatApplyment
        service=self.onboarding.wechat_applyment
        c=self.identity.center
        if (type(service) is not WechatApplyment or service.center is not c
                or service.onboarding is not self.onboarding):
            raise PermissionError('ORIGINAL_SHARED_DRAFT_REQUIRED')
        if c.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        with c.tx():
            uid,_,_,_=self.context(token,scene)
            owner,_,platform=self.onboarding._load(application,uid)
            def row():
                return c.db.execute("SELECT user_id,active,payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND project=?",
                                    (application,application)).fetchone()
            initial=row()
            if initial is not None and (initial['user_id']!=owner or initial['active']!=1):
                raise PermissionError('SHARED_DRAFT_OWNER_REVOKED')
            record=service._read(application)
            version=record['version'] if record is not None else 0
            if (type(version) is not int or version<(1 if record is not None else 0)
                    or type(platform['revision']) is not int or platform['revision']<1):
                raise PermissionError('OCR_SHARED_VERSIONS_INVALID')
            if (platform['status'] not in ('DRAFT','CORRECTION_REQUIRED')
                    or record is not None and record.get('state') not in ('DRAFT','CORRECTION')):
                raise PermissionError('SHARED_DRAFT_EDIT_STATE_DENIED')
            source=self.ocr_source(token,scene,application,kind)
            # _read decrypts private metadata. Bind its result to the exact row
            # read before decryption; never substitute the latest provider version.
            current=row()
            if ((tuple(initial) if initial is not None else None)
                    !=(tuple(current) if current is not None else None)
                    or source['subject']!=owner
                    or source['application_revision']!=platform['revision']):
                raise PermissionError('OCR_SHARED_SOURCE_CHANGED')
            # Original source performs final session/origin/object/expiry checks.
            # This second read also catches mutations during provider decryption.
            final=self.ocr_source(token,scene,application,kind)
            _,_,latest_platform=self.onboarding._load(application,uid)
            current=row()
            if (final!=source or latest_platform!=platform or (tuple(initial) if initial is not None else None)
                    !=(tuple(current) if current is not None else None)):
                raise PermissionError('OCR_SHARED_SOURCE_CHANGED')
            return dict(source,wechat_version=version)

    def ocr_source(self,token,scene,application,kind):
        """Protected Python-only preparation; no OCR/network call or HTTP exposure.

        Original mini identity + current applicant ownership + immutable origin
        + current scanned object + decrypted bytes are all rechecked. Legacy
        applications without origin require separate authoritative admission.
        """
        import hashlib
        from scripts.pr122_customer_core import private_path
        uid,pid,csrf,principal=self.context(token,scene)
        origin=self._ocr_origin(scene,pid,principal)
        owner,meta,data=self.onboarding._load(application,uid)
        if meta.get('ocr_origin')!=origin:
            raise PermissionError('OCR_APPLICATION_ORIGIN_UNVERIFIED')
        hints={'business_license':'business_license','identity_front':'id_front'}
        if kind not in hints or (kind=='identity_front' and meta.get('identity_type')!='IDENTIFICATION_TYPE_IDCARD'):
            raise PermissionError('OCR_DOCUMENT_NOT_SUPPORTED')
        material=meta['materials'].get(kind)
        if material is None:raise PermissionError('OCR_ATTACHMENT_REQUIRED')
        if material['expires_at'] is not None and material['expires_at']<=self.identity.center.now():
            raise PermissionError('OCR_ATTACHMENT_EXPIRED')
        c=self.identity.center
        row=c.db.execute('SELECT id,version,project,mime,size,sha,scan,key_id FROM objects WHERE id=? AND project=?',
                         (material['object_id'],application)).fetchone()
        if row is None or row['scan']!='CLEAN' or row['sha']!=material['sha256']:
            raise PermissionError('OCR_ATTACHMENT_INTEGRITY')
        raw=c.decrypt(private_path(c.objects/material['object_id']).read_bytes(),
                      'object:'+application+':'+material['object_id'])
        if not 1<=len(raw)<=5_000_000 or len(raw)!=row['size'] or hashlib.sha256(raw).hexdigest()!=row['sha']:
            raise PermissionError('OCR_ATTACHMENT_INTEGRITY')
        if row['mime'] not in ('image/png','image/jpeg'):
            raise PermissionError('OCR_IMAGE_REQUIRED')
        # Do not return bytes after a session/scope/application replacement.
        current=self.context(token,scene)
        _,latest,version=self.onboarding._load(application,uid)
        if (current!=(uid,pid,csrf,principal) or self._ocr_origin(scene,pid,principal)!=origin
                or latest!=meta or version['revision']!=data['revision']):
            raise PermissionError('OCR_SOURCE_CHANGED')
        # Re-read the authoritative object after decrypt and all identity/draft
        # callbacks. The first row is only a read-start snapshot, not a permit.
        current_object=c.db.execute(
            'SELECT id,version,project,mime,size,sha,scan,key_id FROM objects WHERE id=? AND project=?',
            (material['object_id'],application)).fetchone()
        if (current_object is None or tuple(current_object)!=tuple(row)
                or current_object['scan']!='CLEAN'
                or current_object['mime'] not in ('image/png','image/jpeg')
                or current_object['size']!=len(raw)
                or current_object['sha']!=material['sha256']
                or current_object['sha']!=hashlib.sha256(raw).hexdigest()):
            raise PermissionError('OCR_ATTACHMENT_INTEGRITY')
        # Clock can advance while decrypting/authorizing; use time at release.
        if material['expires_at'] is not None and material['expires_at']<=c.now():
            raise PermissionError('OCR_ATTACHMENT_EXPIRED')
        return {'subject':owner,'tenant_id':origin['scope']['tenant_id'],
                'project':pid,'scene':scene,'scope':origin['scope'],
                'onboarding_application_id':application,'application_revision':data['revision'],
                'attachment_id':material['object_id'],'document_sha256':row['sha'],
                'document_type':hints[kind],'mime':row['mime'],'data':raw}
