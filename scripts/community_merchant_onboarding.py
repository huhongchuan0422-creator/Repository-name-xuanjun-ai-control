"""Merchant admission on existing Center identity, storage and onboarding tables.

Business review does not approve WeChat submerchant registration or enable funds.
An applicant needs an existing verified account, not a fictitious signed project.
"""
from scripts.community_admin_route_gate import community_route, community_project, resolve_admin_workspace, has_admin_templates
import base64
import hashlib
import json
import secrets
import shutil
import re
from pathlib import Path
from scripts.pr122_customer_core import Center,canonical,secure_write,private_path,safe_text
from scripts import community_onboarding_offline as workflow

class MaterialPreviewUnavailable(ValueError):
    """Safe static non-auth preview state; never carries private contents."""

MATERIALS={
    'business_license':'营业执照', 'identity_front':'经营者/法定代表人证件正面',
    'identity_back':'经营者/法定代表人证件反面', 'storefront_photo':'门店门头照片',
    'interior_photo':'门店经营场所照片', 'cashier_photo':'收银台照（选填补充）', 'bank_card':'银行卡照片', 'settlement_proof':'结算账户证明',
    'operator_authorization':'经办人授权书', 'operator_identity':'经办人证件正面',
    'industry_permit':'行业经营许可（按经营类目）',
    **{'industry_permit_'+str(i):'行业资质材料'+str(i) for i in range(2,6)},
    'mini_program_screenshot':'小程序商品或服务页面截图（微信进件按场景提供）',
    'operator_identity_back':'经办人证件反面',
    **{'ubo_'+str(i)+'_'+side:'受益人'+str(i)+('证件正面' if side=='front' else '证件反面') for i in range(1,5) for side in ('front','back')}}
INDUSTRY_MATERIAL_KINDS=('industry_permit',)+tuple('industry_permit_'+str(i) for i in range(2,6))
BASE=('business_license','identity_front','identity_back')
STORE_SCENE='SALES_SCENES_STORE'
MINI_SCENE='SALES_SCENES_MINI_PROGRAM'
REDEMPTION_PERCENT_OPTIONS=(0,10,20,25,30)


def checked_redemption_percent(value):
    if type(value) is not int or value not in REDEMPTION_PERCENT_OPTIONS:
        raise ValueError('INVALID_REDEMPTION_PERCENT')
    return value


def checked_split_choice(participates,value):
    if type(participates) is not bool or type(value) is not int or not 0<=value<=10000:
        raise ValueError('INVALID_SPLIT_PARTICIPATION')
    if participates != (value>0):
        raise ValueError('SPLIT_PARTICIPATION_RATIO_MISMATCH')
    return participates,value

def checked_scenes(value):
    if type(value) is not list or not value or len(value)>2 or any(type(s) is not str or s not in (STORE_SCENE,MINI_SCENE) for s in value) or len(set(value))!=len(value):
        raise ValueError('INVALID_ONBOARDING_SALES_SCENES')
    return list(value)


def checked_declarations(value,entity):
    # UI conditions only, in the existing encrypted application metadata.
    # These are not extra WeChat fields, account grants or business scope.
    if (type(value) is not dict or set(value)!={'scene','ubos'}
            or type(value['scene']) is not str or value['scene'] not in ('unknown','store','mini','both')
            or not (value['ubos']=='unknown' or type(value['ubos']) is int and 0<=value['ubos']<=4
                    or entity=='SOLE_PROPRIETOR' and value['ubos']=='not_applicable')):
        raise ValueError('INVALID_APPLICATION_DECLARATIONS')
    if entity=='ENTERPRISE' and value['ubos']=='not_applicable':raise ValueError('INVALID_APPLICATION_DECLARATIONS')
    return dict(value)


def require_confirmed_declarations(meta,profile=None):
    value=meta.get('declarations')
    if value is None:return  # Historical callers retain their original validation.
    value=checked_declarations(value,meta['entity_type'])
    if value['scene']=='unknown' or meta['entity_type']=='ENTERPRISE' and value['ubos']=='unknown':
        raise ValueError('APPLICATION_CONDITIONS_NOT_CONFIRMED')
    expected={'store':[STORE_SCENE],'mini':[MINI_SCENE],'both':[MINI_SCENE,STORE_SCENE]}[value['scene']]
    actual=profile_scenes(profile) if profile is not None else meta.get('sales_scenes_type')
    if actual is None or set(actual)!=set(expected):raise ValueError('APPLICATION_SCENE_DECLARATION_MISMATCH')
    if profile is not None and meta['entity_type']=='ENTERPRISE':
        ubos=profile.get('subject_info',{}).get('ubo_info_list',[])
        if type(ubos) is not list or len(ubos)!=value['ubos']:raise ValueError('APPLICATION_UBO_DECLARATION_MISMATCH')


def profile_scenes(profile):
    value=profile
    for key in ('business_info','sales_info'):
        if type(value) is not dict:return None
        value=value.get(key)
    if type(value) is not dict:return None
    scenes=value.get('sales_scenes_type')
    return None if scenes is None else checked_scenes(scenes)


def validate_mini_license_region(meta,profile):
    """Mini's retained license address only; Web's operating address is unchanged.

    This is not a draft-save or history-read gate. Platform submission calls it
    under its existing BEGIN IMMEDIATE lock; provider submission binds the
    checked profile to the existing expected_version and transactional compare.
    """
    profile=profile if type(profile) is dict else {}
    scenes=profile_scenes(profile) or meta.get('sales_scenes_type',[STORE_SCENE])
    if STORE_SCENE not in scenes:return
    def retained(*keys):
        value=profile
        for key in keys:
            if type(value) is not dict:return None
            value=value.get(key)
        return value
    from scripts.community_license_region import validate
    return validate(retained('subject_info','business_license_info','license_address'),
                    retained('business_info','sales_info','biz_store_info','biz_address_code'))


def shared_application_fields(profile,fields):
    """Project platform fields from this same application's WeChat profile.

    Old drafts without a sales selection retain their original stored fields;
    no default store/project is inferred and no second applicant form is added.
    """
    result=dict(fields)
    for key,path in {'legal_name':('subject_info','business_license_info','merchant_name'),
                     'contact':('contact_info','mobile_phone')}.items():
        value=profile
        for part in path:
            value=value.get(part) if type(value) is dict else None
        if value is not None:
            if type(value) is not str:raise ValueError('INVALID_SHARED_APPLICATION_FIELD')
            if value:safe_text(value,512)
            if key=='contact' and len(value)>120:raise ValueError('MERCHANT_PROFILE_FIELD_LIMIT')
            result[key]=value
    scenes=profile_scenes(profile)
    if scenes is not None:
        store='SALES_SCENES_STORE' in scenes
        sources={'store_name':('business_info','sales_info','biz_store_info','biz_store_name') if store else ('business_info','merchant_shortname'),
                 'address':('business_info','sales_info','biz_store_info','biz_store_address') if store else ('subject_info','business_license_info','license_address')}
        for key,path in sources.items():
            value=profile
            for part in path:value=value.get(part) if type(value) is dict else None
            if value is None:value=''
            if type(value) is not str:raise ValueError('INVALID_SHARED_APPLICATION_FIELD')
            if value:safe_text(value,512)
            if key=='store_name' and len(value)>120:raise ValueError('MERCHANT_PROFILE_FIELD_LIMIT')
            result[key]=value
    return result


def _failure_diagnostic(error,commit_attempted,rollback,object_write):
    # Internal fixed enums only; never expose paths, applicant/material IDs or errors.
    diagnostic=dict(database='ROLLED_BACK_BEFORE_COMMIT' if not commit_attempted and rollback=='COMPLETED' else 'UNKNOWN',
        commit_attempted=commit_attempted,rollback=rollback,object_write=object_write,
        filesystem_cleanup='NOT_ATTEMPTED')
    try:
        error.onboarding_failure=diagnostic
        error.add_note('MERCHANT_ONBOARDING_FAILURE='+json.dumps(diagnostic,sort_keys=True,separators=(',',':')))
    except BaseException:
        # A diagnostic sink must never replace the original business/storage error.
        pass


class MerchantOnboarding:
    def __init__(self,center,reviewers):
        if type(center) is not Center or type(reviewers) is not dict or (not reviewers and not has_admin_templates(center,'/merchant/onboarding')):
            raise ValueError('EXISTING_CENTER_AND_PROTECTED_REVIEWERS_REQUIRED')
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest()!=\
                'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0':
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        if any(type(k) is not str or not k or type(v) is not str or not v for k,v in reviewers.items()):
            raise ValueError('ORIGINAL_REVIEWER_PROJECT_BINDING_REQUIRED')
        if center.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        self.center=center;self.reviewers=dict(reviewers)
        self.operations=None
        self.wechat_applyment=None
        self.provider_actions=None
        # Reuse the already developed onboarding business tables in the original
        # Center backup domain. No second account store or review queue exists.
        workflow.initialize(center.db)
    @staticmethod
    def catalog():
        return {'entity_types':{'ENTERPRISE':'企业','SOLE_PROPRIETOR':'个体工商户'},
                'materials':[{'id':k,'title':v,'required':k in BASE} for k,v in MATERIALS.items()],
                'formats':['application/pdf','image/png','image/jpeg'],'max_file_bytes':5_000_000,
                'industry_permit_required_for':['FOOD'],'operator_materials_when_delegated':True,
                'sales_scenes':[MINI_SCENE,STORE_SCENE],
                'default_sales_scenes':[], 'sales_scene_confirmation_required':True,
                'optional_materials':['settlement_proof','operator_authorization','cashier_photo'],
                'scope':'同一申请资料按微信主体与经营场景复用，平台仅核原项目门店归属',
                'payment_enabled':False}
    def _encode(self,value,aad):return base64.b64encode(self.center.encrypt(canonical(value),aad)).decode()
    def _decode(self,value,aad):return json.loads(self.center.decrypt(base64.b64decode(value,validate=True),aad))
    def _reviewer(self,uid):
        template=resolve_admin_workspace(self.center,{},'__community_onboarding__',uid)
        project=template['project'] if template is not None and template['role']=='PLATFORM_REVIEWER' else self.reviewers.get(uid)
        if project is None:raise PermissionError('PLATFORM_REVIEWER_REQUIRED')
        community_project(self.center,uid,project,('REVIEWER',))
    def _load(self,application,uid,review=False):
        if type(application) is not str:raise ValueError('APPLICATION_REQUIRED')
        row=self.center.db.execute("SELECT user_id,payload FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
        if row is None:raise PermissionError('APPLICATION_ACCESS_DENIED')
        owner=row['user_id']
        if review:self._reviewer(uid)
        elif uid!=owner:raise PermissionError('APPLICATION_ACCESS_DENIED')
        meta=self._decode(row['payload'],'onboarding-meta:'+application)
        # Current original application draft is authoritative, never a client
        # success flag or a different merchant's provider result. No PII copies.
        if self.wechat_applyment is not None:
            record=self.wechat_applyment._read(application)
            scenes=profile_scenes((record or {}).get('profile',{}))
            if scenes is not None:meta['sales_scenes_type']=checked_scenes(scenes)
            profile=(record or {}).get('profile')
            contact=profile.get('contact_info') if type(profile) is dict else None
            if type(contact) is dict and contact.get('contact_type') in ('LEGAL','SUPER'):
                meta['delegated']=contact['contact_type']=='SUPER'
                meta['operator_identity_type']=contact.get('contact_id_doc_type','IDENTIFICATION_TYPE_IDCARD')
        data=workflow.get_application(self.center.db,owner,application,
            decode=lambda value:self._decode(value,'onboarding-fields:'+application))
        if data['reviewer_note']:
            data['reviewer_note']=self._decode(data['reviewer_note'],'onboarding-note:'+application)['note']
        return owner,meta,data
    def _meta(self,application,owner,meta):
        self.center.db.execute("INSERT INTO links VALUES('COMMUNITY_ONBOARDING',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",
            (application,owner,application,self._encode(meta,'onboarding-meta:'+application)))
    def _split_policy(self,meta,owner=None):
        origin=meta.get('ocr_origin')
        actions=self.provider_actions
        value=origin.get('scope') if type(origin) is dict else None
        if value is None and owner is not None and self.operations is not None:
            candidates=[g['scope'] for g in self.operations.grants.values() if g['user_id']==owner and g.get('onboarding_required')]
            if len(candidates)==1:value=candidates[0]
        if actions is None:return None
        if type(value) is not dict or set(value)!={'tenant_id','merchant_id','store_id'}:return None
        policy=actions.bindings.get(tuple(value[k] for k in ('tenant_id','merchant_id','store_id')))
        if policy is None:return None
        return policy['max_total_bps'] if policy['profit_sharing'] else 0
    def split_admission_for_application(self,application):
        row=self.center.db.execute("SELECT user_id,payload FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
        if row is None:raise PermissionError('MERCHANT_SPLIT_APPLICATION_REQUIRED')
        meta=self._decode(row['payload'],'onboarding-meta:'+application)
        requested=meta.get('requested_split_bps',0);participates=meta.get('split_participation',False)
        checked_split_choice(participates,requested)
        provider_max=self._split_policy(meta,row['user_id'])
        effective=meta.get('effective_split_bps',0)
        if not participates:return dict(participates=False,requested_bps=0,provider_max_bps=provider_max,effective_bps=0)
        if provider_max is None or type(effective) is not int or effective!=requested or not 0<effective<=provider_max:
            raise PermissionError('MERCHANT_SPLIT_NOT_APPROVED')
        return dict(participates=True,requested_bps=requested,provider_max_bps=provider_max,effective_bps=effective)
    def split_admission_for_scope(self,scope):
        key=hashlib.sha256(canonical(scope)).hexdigest()
        rows=self.center.db.execute("SELECT project,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING' AND subject_idx=? AND active=1",(key,)).fetchall()
        if len(rows)!=1:raise PermissionError('MERCHANT_SPLIT_OPENING_REQUIRED')
        application,payload=rows[0]
        opening=self._decode(payload,'community-opening:'+key+':'+application)
        if opening.get('state')!='OPENED' or opening.get('scope')!=scope:raise PermissionError('MERCHANT_SPLIT_OPENING_REQUIRED')
        return self.split_admission_for_application(application)
    def _required(self,meta,application=None):
        base=tuple(k for k in BASE if k!='identity_back' or meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD')!='IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
        # Old records without a declaration retain conservative offline requirements.
        # New UI always submits its selected scenes; no history is rewritten.
        scenes=checked_scenes(meta.get('sales_scenes_type',[STORE_SCENE]))
        scene_materials=(('storefront_photo','interior_photo') if STORE_SCENE in scenes else ())+(('mini_program_screenshot',) if MINI_SCENE in scenes else ())
        operator=() if not meta['delegated'] else ('operator_identity',)+(('operator_identity_back',) if meta.get('operator_identity_type','IDENTIFICATION_TYPE_IDCARD')!='IDENTIFICATION_TYPE_OVERSEA_PASSPORT' else ())
        selected=set()
        if application and self.wechat_applyment is not None:
            record=self.wechat_applyment._read(application) or {}
            values=record.get('profile',{}).get('settlement_info',{}).get('qualifications',[])
            selected={b['kind'] for b in record.get('industry_qualification_bindings',[]) if b.get('media_id') in values}
        industry=tuple(k for k in INDUSTRY_MATERIAL_KINDS if k in selected or k=='industry_permit' and meta['category']=='FOOD')
        return base+scene_materials+operator+industry
    def _check_materials(self,application,meta):
        for kind in self._required(meta,application):
            material=meta['materials'].get(kind)
            if not material or (material['expires_at'] is not None and material['expires_at']<=self.center.now()):
                raise ValueError('REQUIRED_MATERIAL_MISSING_OR_EXPIRED:'+kind)
            row=self.center.db.execute('SELECT project,sha,scan FROM objects WHERE id=?',(material['object_id'],)).fetchone()
            if row is None or tuple(row)!=(application,material['sha256'],'CLEAN'):
                raise PermissionError('PRIVATE_MATERIAL_BINDING_INVALID')
            raw=self.center.decrypt(private_path(self.center.objects/material['object_id']).read_bytes(),
                'object:'+application+':'+material['object_id'])
            if hashlib.sha256(raw).hexdigest()!=material['sha256']:raise PermissionError('PRIVATE_MATERIAL_INTEGRITY')
    def _view(self,application,meta,data):
        from scripts.community_merchant_opening import opening_state
        from scripts.community_wechat_applyment import provider_workflow_view
        owner=self.center.db.execute("SELECT user_id FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=?",(application,application)).fetchone()[0]
        workspaces=[] if self.operations is None else [name for name,g in self.operations.grants.items()
            if g['user_id']==owner and g['onboarding_required']]
        data=dict(data,fields={k:v for k,v in data['fields'].items() if k!='license_ref'})
        wechat_record=self.wechat_applyment._read(application) if self.wechat_applyment is not None else None
        if wechat_record is not None:data['fields']=shared_application_fields(wechat_record.get('profile',{}),data['fields'])
        return dict(data,application=application,entity_type=meta['entity_type'],identity_type=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'),category=meta['category'],
            delegated=meta['delegated'],declarations=meta.get('declarations'),sales_scenes_type=meta.get('sales_scenes_type',[STORE_SCENE]),required_materials=list(self._required(meta,application)),
            redemption_percent=meta.get('redemption_percent',0),approved_redemption_percent=meta.get('approved_redemption_percent'),
            split_participation=meta.get('split_participation',False),requested_split_bps=meta.get('requested_split_bps',0),
            provider_max_split_bps=self._split_policy(meta,owner),effective_split_bps=meta.get('effective_split_bps',0),
            materials={k:{'uploaded':True,'expires_at':v['expires_at'],
                'review':meta.get('reviews',{}).get(k,{}).get('decision','PENDING'),
                'review_note':meta.get('reviews',{}).get(k,{}).get('note','')} for k,v in meta['materials'].items()},
            opening_state=opening_state(self,application) if data['status']=='APPROVED' else 'NOT_APPROVED',
            opening_workspaces=workspaces,
            application_result=(wechat_record.get('provider_state') if wechat_record.get('provider_state') not in (None,'NOT_SUBMITTED','NOT_VERIFIED') else 'PROVIDER_ACCEPTED' if wechat_record.get('state')=='SUBMITTED_TO_PROVIDER' else 'SUBMISSION_UNKNOWN' if wechat_record.get('state')=='SUBMISSION_UNKNOWN' else 'DRAFT') if wechat_record and wechat_record.get('applicant_direct_submission') else None,
            wechat_submerchant_state=wechat_record.get('provider_state','NOT_VERIFIED') if wechat_record else 'NOT_VERIFIED',
            wechat_provider_workflow=provider_workflow_view(wechat_record),payment_enabled=False)
    def _material_preview(self,session,csrf,uid,params):
        """Current owner's exact retained image only; never the reviewer download path."""
        c=self.center
        kind=params['kind'];application=params['application'];revision=params['revision']
        if type(kind) is not str or kind not in ('business_license','identity_front','identity_back','bank_card','settlement_proof'):
            raise ValueError('MATERIAL_PREVIEW_KIND_DENIED')
        if type(revision) is not int or revision<0:raise ValueError('INVALID_REVISION')
        # The original generic settlement proof has no trusted bank-card type.
        # Do not treat arbitrary account documents as a previously retained card.
        def current():
            if c.session(session,csrf)!=uid:raise PermissionError('APPLICATION_ACCESS_DENIED')
            owner,meta,data=self._load(application,uid,False)
            if data['revision']!=revision:raise MaterialPreviewUnavailable('MATERIAL_PREVIEW_SOURCE_CHANGED')
            if kind=='settlement_proof':raise MaterialPreviewUnavailable('BANK_CARD_BINDING_UNAVAILABLE')
            material=meta['materials'].get(kind)
            if not material:raise MaterialPreviewUnavailable('MATERIAL_NOT_FOUND')
            if kind=='bank_card' and material.get('purpose')!='BANK_CARD':raise MaterialPreviewUnavailable('BANK_CARD_BINDING_UNAVAILABLE')
            expires=material.get('expires_at')
            if expires is not None and (type(expires) is not int or expires<=c.now()):raise MaterialPreviewUnavailable('MATERIAL_PREVIEW_EXPIRED')
            oid=material.get('object_id');digest=material.get('sha256')
            if type(oid) is not str or not re.fullmatch(r'o_[0-9a-f]{32}',oid) or type(digest) is not str or not re.fullmatch(r'[0-9a-f]{64}',digest):raise MaterialPreviewUnavailable('MATERIAL_INTEGRITY')
            row=c.db.execute('SELECT mime,sha,size,scan FROM objects WHERE id=? AND project=?',(oid,application)).fetchone()
            if row is None or row['scan']!='CLEAN' or row['sha']!=digest:raise MaterialPreviewUnavailable('MATERIAL_INTEGRITY')
            if row['mime'] not in ('image/jpeg','image/png'):raise MaterialPreviewUnavailable('MATERIAL_PREVIEW_IMAGE_REQUIRED')
            if type(row['size']) is not int or not 1<=row['size']<=5_000_000:raise MaterialPreviewUnavailable('MATERIAL_INTEGRITY')
            return (oid,digest,row['mime'],row['size'],expires)
        before=current()
        raw=c.decrypt(private_path(c.objects/before[0]).read_bytes(),'object:'+application+':'+before[0])
        if len(raw)!=before[3] or hashlib.sha256(raw).hexdigest()!=before[1]:raise MaterialPreviewUnavailable('MATERIAL_INTEGRITY')
        content_mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
        if content_mime!=before[2]:raise MaterialPreviewUnavailable('MATERIAL_INTEGRITY')
        if current()!=before:raise MaterialPreviewUnavailable('MATERIAL_PREVIEW_SOURCE_CHANGED')
        # Recheck immediately before return; no object contents enter logs/audit.
        return {'application':application,'revision':revision,'kind':kind,'object_id':before[0],
                'sha256':before[1],'mime':before[2],'size':before[3],
                'content_base64':base64.b64encode(raw).decode(),'cache':'PRIVATE_TEMPORARY_ONLY'}

    @community_route('/merchant/onboarding')
    def dispatch(self,session,csrf,body,*,source_origin=None,_mini_submission=False):
        if type(_mini_submission) is not bool:raise ValueError("INVALID_INTERNAL_MINI_SUBMISSION")
        if type(body) is not dict or set(body)!={'operation','params'} or type(body['params']) is not dict:
            raise ValueError('INVALID_ONBOARDING_REQUEST')
        op,params=body['operation'],body['params'];c=self.center
        if op=='catalog' and params=={}:return self.catalog()
        if type(op) is str and op.startswith('wechat_'):
            if self.wechat_applyment is None:raise PermissionError('OFFICIAL_APPLYMENT_NOT_CONFIGURED')
            return self.wechat_applyment.dispatch(session,csrf,body)
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        uid=c.session(session,csrf)
        schemas={'material_preview':{'application','revision','kind'},'mine':set(),'save':{'application','revision','fields','entity_type','category','delegated'},
                 'upload':{'application','revision','kind','content_base64','expires_at'},
                 'remove_material':{'application','revision','kind','expected_wechat_version'},
                 'submit':{'application','revision'},'withdraw':{'application','revision'},'review_list':set(),
                 'read':{'application'},'review_read':{'application'},
                 'history':{'application','after_revision'},'review_history':{'application','after_revision'},
                 'notices':{'application','after_id'},'notice_read':{'application','notice_id'},'review':{'application','revision','action','note'},
                 'review_material':{'application','revision','kind','decision','note'},
                 'open_workbench':{'application','revision','workspace'},
                 'download':{'application','kind'}}
        listing=type(op) is str and op in ('mine','review_list')
        if (type(op) is not str or op not in schemas or
                (not set(params).issubset({'cursor','status'}) if listing else (not (schemas[op]<=set(params)<=schemas[op]|{'identity_type','sales_scenes_type','declarations','redemption_percent','split_participation','requested_split_bps'}) if op=='save' else set(params)!=schemas[op]))):
            raise ValueError('INVALID_ONBOARDING_FIELDS')
        if c.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        if op=='material_preview':
            try:return self._material_preview(session,csrf,uid,params)
            except MaterialPreviewUnavailable as error:return {'status':'UNAVAILABLE','reason':str(error)}
        if op=='open_workbench':
            from scripts.community_merchant_opening import open_workbench
            open_workbench(self,self.operations,uid,params['application'],params['workspace'],params['revision'])
            _,meta,data=self._load(params['application'],uid,True)
            return self._view(params['application'],meta,data)
        if op in ('mine','review_list'):
            if op=='review_list':self._reviewer(uid)
            cursor=params.get('cursor');status=params.get('status','ALL')
            if cursor is not None and (type(cursor) is not str or not re.fullmatch('ma_[0-9a-f]{32}',cursor)):
                raise ValueError('INVALID_APPLICATION_CURSOR')
            if type(status) is not str or status not in workflow._ALLOWED|{'ALL'}:raise ValueError('INVALID_APPLICATION_STATUS')
            query="SELECT l.subject_idx FROM links l JOIN onboarding o ON o.tenant=l.user_id AND o.application=l.subject_idx WHERE l.channel='COMMUNITY_ONBOARDING' AND l.active=1 AND l.project=l.subject_idx"
            args=[]
            if op=='mine':query+=' AND l.user_id=?';args.append(uid)
            if cursor is not None:query+=' AND l.subject_idx>?';args.append(cursor)
            if status!='ALL':query+=' AND o.status=?';args.append(status)
            rows=c.db.execute(query+' ORDER BY l.subject_idx LIMIT 51',args).fetchall()
            page=rows[:50]
            return {'applications':[self._view(row[0],*self._load(row[0],uid,op=='review_list')[1:]) for row in page],
                    'next_cursor':page[-1][0] if len(rows)>50 else None}
        if op in ('notices','notice_read'):
            from scripts.community_onboarding_notices import dispatch
            return dispatch(self,session,csrf,op,params)
        if op in ('history','review_history'):
            from scripts.community_onboarding_history import read
            return read(self,session,csrf,params['application'],params['after_revision'],op=='review_history')
        if op in ('read','review_read'):
            _,meta,data=self._load(params['application'],uid,op=='review_read')
            return self._view(params['application'],meta,data)
        application=params['application']
        if op=='save' and application is None:
            application='ma_'+secrets.token_hex(16);owner=uid
            meta={'entity_type':params['entity_type'],'category':params['category'],'delegated':params['delegated'],'materials':{},
                  'redemption_percent':checked_redemption_percent(params.get('redemption_percent',0))}
            participates,requested=checked_split_choice(params.get('split_participation',False),params.get('requested_split_bps',0))
            meta.update(split_participation=participates,requested_split_bps=requested,effective_split_bps=0)
            # Trusted Python composition only; never a body-supplied scope.
            if source_origin is not None:
                if (type(source_origin) is not dict or set(source_origin)!={'project','scene','scope'}
                        or any(type(source_origin[k]) is not str or not source_origin[k] for k in ('project','scene'))):
                    raise ValueError('EXACT_APPLICATION_ORIGIN_REQUIRED')
                from scripts.community_merchant_contract import scope
                scope(source_origin['scope'])
                meta['ocr_origin']=json.loads(canonical(source_origin))
            data=None
        else:owner,meta,data=self._load(application,uid,op in ('review','review_material') or op=='download' and uid in self.reviewers)
        if op=='download':
            if params['kind']=='bank_card':raise PermissionError('BANK_CARD_PRIVATE_PREVIEW_ONLY')
            material=meta['materials'].get(params['kind'])
            if material is None:raise ValueError('MATERIAL_NOT_FOUND')
            row=c.db.execute('SELECT mime,sha,size,scan FROM objects WHERE id=? AND project=?',(material['object_id'],application)).fetchone()
            raw=c.decrypt(private_path(c.objects/material['object_id']).read_bytes(),'object:'+application+':'+material['object_id'])
            if row is None or row['scan']!='CLEAN' or hashlib.sha256(raw).hexdigest()!=row['sha'] or len(raw)!=row['size']:
                raise PermissionError('MATERIAL_INTEGRITY')
            with c.tx():c.audit(application,uid,'ONBOARDING_DOWNLOAD',material['object_id'])
            return {'content_base64':base64.b64encode(raw).decode(),'mime':row['mime']}
        if type(params['revision']) is not int or params['revision']<0:raise ValueError('INVALID_REVISION')
        commit_attempted=False;object_write='NOT_STARTED'
        c.db.execute('BEGIN IMMEDIATE')
        try:
            # Reload under the original DB write lock for stale-version safety.
            if data is not None:owner,meta,data=self._load(application,uid,op in ('review','review_material'))
            if op=='withdraw' and c.session(session,csrf)!=uid:raise PermissionError('CURRENT_APPLICANT_SESSION_REQUIRED')
            c.limit('merchant-onboarding:'+uid,60,3600)
            if op=='save':
                if params['entity_type'] not in ('ENTERPRISE','SOLE_PROPRIETOR') or params['category'] not in ('GENERAL','FOOD') or type(params['delegated']) is not bool:
                    raise ValueError('INVALID_BUSINESS_TYPE')
                fields=params['fields']
                if type(fields) is not dict or set(fields)!={'legal_name','store_name','address','contact'}:raise ValueError('INVALID_PROFILE_FIELDS')
                for value in fields.values():
                    if type(value) is not str:raise ValueError('INVALID_PROFILE_VALUE')
                    if value:safe_text(value,512)
                if len(fields['store_name'])>120 or len(fields['contact'])>120:raise ValueError('MERCHANT_PROFILE_FIELD_LIMIT')
                if self.wechat_applyment is not None:
                    record=self.wechat_applyment._read(application)
                    if record is not None:fields=shared_application_fields(record.get('profile',{}),fields)
                from scripts.community_applyment_conditions import DOCS
                identity_type=params.get('identity_type',meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'))
                if type(identity_type) is not str or identity_type not in DOCS:raise ValueError('INVALID_IDENTITY_TYPE')
                meta['identity_type']=identity_type
                if 'sales_scenes_type' in params:meta['sales_scenes_type']=checked_scenes(params['sales_scenes_type'])
                if 'declarations' in params:
                    declaration=checked_declarations(params['declarations'],params['entity_type'])
                    if declaration['scene']=='unknown':meta.pop('sales_scenes_type',None)
                    else:
                        expected={'store':[STORE_SCENE],'mini':[MINI_SCENE],'both':[MINI_SCENE,STORE_SCENE]}[declaration['scene']]
                        if set(meta.get('sales_scenes_type',[]))!=set(expected):raise ValueError('APPLICATION_SCENE_DECLARATION_MISMATCH')
                    meta['declarations']=declaration
                if 'redemption_percent' in params:
                    meta['redemption_percent']=checked_redemption_percent(params['redemption_percent'])
                if 'split_participation' in params or 'requested_split_bps' in params:
                    participates,requested=checked_split_choice(params.get('split_participation',meta.get('split_participation',False)),params.get('requested_split_bps',meta.get('requested_split_bps',0)))
                    # Only an explicit ratio choice is checked on draft edits. Old
                    # records are not migrated or changed by reads/unrelated saves.
                    provider_max=self._split_policy(meta,owner)
                    if participates and provider_max is not None and requested>provider_max:
                        raise ValueError('SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM')
                    meta.update(split_participation=participates,requested_split_bps=requested,effective_split_bps=0)
                meta.update(entity_type=params['entity_type'],category=params['category'],delegated=params['delegated'])
                meta['reviews']={}
                revision=workflow.save_draft(c.db,uid,application,uid,dict(fields,license_ref='PRIVATE_ONBOARDING_MATERIALS'),params['revision'],
                    encode=lambda value:self._encode(value,'onboarding-fields:'+application),manage_transaction=False)
                self._meta(application,uid,meta)
            elif op=='upload':
                if data['status'] not in ('DRAFT','CORRECTION_REQUIRED') or data['revision']!=params['revision']:raise ValueError('STATE_OR_REVISION_CONFLICT')
                kind=params['kind'];expires=params['expires_at']
                if type(kind) is not str or kind not in MATERIALS or expires is not None and (type(expires) is not int or expires<=c.now()):raise ValueError('INVALID_MATERIAL')
                if kind in INDUSTRY_MATERIAL_KINDS and self.wechat_applyment is not None:
                    self.wechat_applyment.clear_industry_material(application,owner,meta,kind)
                if kind=='cashier_photo' and self.wechat_applyment is not None:
                    self.wechat_applyment.clear_cashier_media(application,owner)
                value=params['content_base64']
                if type(value) is not str or len(value)>6_666_668:raise ValueError('FILE_LIMIT')
                raw=base64.b64decode(value,validate=True)
                if not 1<=len(raw)<=5_000_000:raise ValueError('FILE_LIMIT')
                mime='application/pdf' if raw.startswith(b'%PDF-') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
                if mime is None:raise ValueError('PDF_PNG_JPEG_ONLY')
                if kind=='bank_card' and mime not in ('image/png','image/jpeg'):raise ValueError('BANK_CARD_IMAGE_REQUIRED')
                safe_text(raw.decode('latin1'),5_000_000)
                if c.scanner is None:raise RuntimeError('EXISTING_SCANNER_REQUIRED')
                if hasattr(c.scanner,'sanitize'):
                    raw=c.scanner.sanitize(raw)
                    mime='image/jpeg'
                if c.scanner(raw) is not True:raise PermissionError('SCAN_NOT_CLEAN')
                count,size=c.db.execute('SELECT count(*),coalesce(sum(size),0) FROM objects WHERE project=?',(application,)).fetchone()
                if count>=100 or size+len(raw)>50_000_000 or shutil.disk_usage(c.root).free<max(50_000_000,3*len(raw)):raise RuntimeError('MATERIAL_STORAGE_LIMIT')
                oid='o_'+secrets.token_hex(16);version='v_'+secrets.token_hex(16)
                encrypted=c.encrypt(raw,'object:'+application+':'+oid)
                object_write='ATTEMPTED'
                secure_write(c.objects/oid,encrypted)
                object_write='RETURNED'
                seq=c.db.execute('SELECT coalesce(max(seq),0)+1 FROM versions WHERE project=? AND item=?',(application,kind)).fetchone()[0]
                c.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',(version,application,kind,seq,uid,'SAVE',c.encrypt(canonical({'object_id':oid,'category':'MATERIAL'}),version),expires,c.now()))
                sha=hashlib.sha256(raw).hexdigest()
                c.db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?,?,?)',(oid,version,application,mime,len(raw),sha,'CLEAN',c.key_id))
                meta['materials'][kind]={'object_id':oid,'sha256':sha,'expires_at':expires}
                if kind=='bank_card':meta['materials'][kind]['purpose']='BANK_CARD'
                meta.setdefault('reviews',{}).pop(kind,None)
                revision=data['revision']+1
                c.db.execute("UPDATE onboarding SET revision=?,status='DRAFT' WHERE tenant=? AND application=?",(revision,uid,application))
                workflow._append(c.db,uid,application,revision,uid,'UPLOAD',{'kind':kind,'sha256':sha})
                self._meta(application,uid,meta)
            elif op=='remove_material':
                # Only this new optional slot; never delete objects or immutable versions.
                if params['kind']!='cashier_photo':raise ValueError('CASHIER_MATERIAL_ONLY')
                if data['status'] not in ('DRAFT','CORRECTION_REQUIRED') or data['revision']!=params['revision']:raise ValueError('STATE_OR_REVISION_CONFLICT')
                if self.wechat_applyment is not None:
                    record=self.wechat_applyment._read(application)
                    version=record['version'] if record else 0
                    if type(params['expected_wechat_version']) is not int or params['expected_wechat_version']!=version:raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
                    self.wechat_applyment.clear_cashier_media(application,owner)
                elif type(params['expected_wechat_version']) is not int or params['expected_wechat_version']!=0:
                    raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
                if 'cashier_photo' not in meta['materials']:raise ValueError('MATERIAL_NOT_FOUND')
                meta['materials'].pop('cashier_photo');meta.setdefault('reviews',{}).pop('cashier_photo',None)
                revision=data['revision']+1
                c.db.execute("UPDATE onboarding SET revision=?,status='DRAFT' WHERE tenant=? AND application=?",(revision,uid,application))
                workflow._append(c.db,uid,application,revision,uid,'REMOVE_MATERIAL',{'kind':'cashier_photo'})
                self._meta(application,uid,meta)
            elif op=='review_material':
                kind=params['kind'];decision=params['decision'];note=safe_text(params['note'],80)
                if (owner==uid or data['status'] not in ('SUBMITTED','IN_REVIEW')
                        or data['revision']!=params['revision']):raise PermissionError('REVIEW_STATE_OR_REVISION_DENIED')
                if kind not in meta['materials'] or decision not in ('ACCEPTED','NEEDS_CORRECTION'):raise ValueError('INVALID_MATERIAL_REVIEW')
                meta.setdefault('reviews',{})[kind]={'sha256':meta['materials'][kind]['sha256'],'decision':decision,'note':note,'reviewer':uid}
                revision=data['revision']+1
                c.db.execute("UPDATE onboarding SET revision=?,status='IN_REVIEW' WHERE tenant=? AND application=?",(revision,owner,application))
                workflow._append(c.db,owner,application,revision,uid,'REVIEW_MATERIAL',{'kind':kind,'decision':decision,'note_sha256':hashlib.sha256(note.encode()).hexdigest()})
                self._meta(application,owner,meta)
            else:
                if op=='submit':
                    if _mini_submission:
                        validate_mini_license_region(meta,(self.wechat_applyment._read(application) or {}).get('profile') if self.wechat_applyment is not None else None)
                    participates,requested=checked_split_choice(meta.get('split_participation',False),meta.get('requested_split_bps',0))
                    provider_max=self._split_policy(meta,owner)
                    if participates and provider_max is not None and requested>provider_max:
                        raise ValueError('SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM')
                    # Unknown configuration may reach internal review; the original
                    # APPROVE check below still requires a verified configured cap.
                    require_confirmed_declarations(meta,(self.wechat_applyment._read(application) or {}).get('profile') if self.wechat_applyment is not None else None)
                action='SUBMIT' if op=='submit' else 'WITHDRAW' if op=='withdraw' else params['action']
                if op=='review' and (action not in ('BEGIN_REVIEW','CORRECTION','REJECT','REOPEN','APPROVE') or owner==uid):raise PermissionError('INDEPENDENT_REVIEW_REQUIRED')
                if action in ('SUBMIT','APPROVE'):self._check_materials(application,meta)
                if action=='APPROVE':
                    account=c.db.execute('SELECT verified FROM accounts WHERE id=?',(owner,)).fetchone()
                    if account is None or account[0]!=1:raise PermissionError('VERIFIED_APPLICANT_REQUIRED')
                    for kind in self._required(meta,application):
                        review=meta.get('reviews',{}).get(kind,{})
                        if review.get('decision')!='ACCEPTED' or review.get('sha256')!=meta['materials'][kind]['sha256']:
                            raise ValueError('MATERIAL_REVIEW_REQUIRED:'+kind)
                    meta['approved_redemption_percent']=checked_redemption_percent(meta.get('redemption_percent',0))
                    participates,requested=checked_split_choice(meta.get('split_participation',False),meta.get('requested_split_bps',0))
                    provider_max=self._split_policy(meta,owner)
                    if participates and (provider_max is None or requested>provider_max):
                        raise ValueError('SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM' if provider_max is not None else 'WECHAT_SPLIT_MAXIMUM_NOT_VERIFIED')
                    meta['effective_split_bps']=requested if participates else 0
                    self._meta(application,owner,meta)
                note='' if op in ('submit','withdraw') else safe_text(params['note'],80)
                encoded_note=self._encode({'note':note},'onboarding-note:'+application) if note else ''
                required_fields=workflow._FIELDS
                if action=='SUBMIT' and self.wechat_applyment is not None:
                    record=self.wechat_applyment._read(application)
                    if record is not None and profile_scenes(record.get('profile',{}))==['SALES_SCENES_MINI_PROGRAM']:
                        # Authoritative same-application draft only, never a body flag.
                        # License address is optional in WeChat's mini-only contract;
                        # names/contact/materials and the full provider validation remain.
                        required_fields=tuple(k for k in workflow._FIELDS if k!='address')
                revision=workflow.transition(c.db,owner,application,uid,'MERCHANT' if op in ('submit','withdraw') else 'REVIEWER',action,params['revision'],encoded_note,
                    decode=lambda value:self._decode(value,'onboarding-fields:'+application),manage_transaction=False,required_fields=required_fields)
                if action=='REOPEN':
                    # Reopening a rejection authorizes correction, not approval.
                    # New material decisions are required; immutable history stays.
                    meta['reviews']={}
                    self._meta(application,owner,meta)
            c.audit(application,uid,'MERCHANT_ONBOARDING_'+op.upper(),str(revision))
            from scripts.community_onboarding_history import append
            append(self,application,owner,uid,op,params,data,meta,revision)
            if op=='review' and params['action']=='APPROVE':
                from scripts.community_demo_directory import retire_on_approval
                retire_on_approval(self,application,owner,uid,revision,meta)
            if op=='review':
                from scripts.community_onboarding_notices import append as notify_result
                notify_result(self,application,owner,revision,params['action'])
            if op=='withdraw':
                if c.session(session,csrf)!=uid:raise PermissionError('CURRENT_APPLICANT_SESSION_REQUIRED')
                self._load(application,uid)
            commit_attempted=True
            c.db.commit()
        except BaseException as error:
            rollback='FAILED'
            try:
                was_active=c.db.in_transaction
                c.db.rollback()
                rollback='COMPLETED' if was_active and not c.db.in_transaction else 'UNCONFIRMED'
            except BaseException:
                pass
            _failure_diagnostic(error,commit_attempted,rollback,object_write)
            raise
        _,meta,data=self._load(application,uid,op in ('review','review_material'))
        if op=='review' and params['action']=='APPROVE' and self.operations is not None:
            targets=[name for name,g in self.operations.grants.items() if g['user_id']==owner and g['onboarding_required']]
            if len(targets)==1:
                from scripts.community_merchant_opening import open_workbench
                open_workbench(self,self.operations,uid,application,targets[0],data['revision'])
        return self._view(application,meta,data)
