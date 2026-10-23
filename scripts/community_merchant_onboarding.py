"""Merchant admission on existing Center identity, storage and onboarding tables.

Business review does not approve WeChat submerchant registration or enable funds.
An applicant needs an existing verified account, not a fictitious signed project.
"""
import base64
import hashlib
import json
import secrets
import shutil
import re
from pathlib import Path
from scripts.pr122_customer_core import Center,canonical,secure_write,private_path,safe_text
from scripts import community_onboarding_offline as workflow

MATERIALS={
    'business_license':'营业执照', 'identity_front':'经营者/法定代表人证件正面',
    'identity_back':'经营者/法定代表人证件反面', 'storefront_photo':'门店门头照片',
    'interior_photo':'门店经营场所照片', 'cashier_photo':'收银台照（选填补充）', 'settlement_proof':'结算账户证明',
    'operator_authorization':'经办人授权书', 'operator_identity':'经办人身份证明',
    'industry_permit':'行业经营许可（按经营类目）',
    'mini_program_screenshot':'小程序商品或服务页面截图（微信进件按场景提供）',
    'operator_identity_back':'经办人证件反面',
    **{'ubo_'+str(i)+'_'+side:'受益人'+str(i)+('证件正面' if side=='front' else '证件反面') for i in range(1,5) for side in ('front','back')}}
BASE=('business_license','identity_front','identity_back')
STORE_SCENE='SALES_SCENES_STORE'
MINI_SCENE='SALES_SCENES_MINI_PROGRAM'

def checked_scenes(value):
    if type(value) is not list or not value or len(value)>2 or any(type(s) is not str or s not in (STORE_SCENE,MINI_SCENE) for s in value) or len(set(value))!=len(value):
        raise ValueError('INVALID_ONBOARDING_SALES_SCENES')
    return list(value)


def profile_scenes(profile):
    value=profile
    for key in ('business_info','sales_info'):
        if type(value) is not dict:return None
        value=value.get(key)
    if type(value) is not dict:return None
    scenes=value.get('sales_scenes_type')
    return None if scenes is None else checked_scenes(scenes)


def shared_application_fields(profile,fields):
    """Platform names/contacts reuse this application's provider draft only."""
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
        if type(center) is not Center or type(reviewers) is not dict or not reviewers:
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
                'default_sales_scenes':[MINI_SCENE],
                'optional_materials':['settlement_proof','operator_authorization','cashier_photo'],
                'scope':'同一申请资料按微信主体与经营场景复用，平台仅核原项目门店归属',
                'payment_enabled':False}
    def _encode(self,value,aad):return base64.b64encode(self.center.encrypt(canonical(value),aad)).decode()
    def _decode(self,value,aad):return json.loads(self.center.decrypt(base64.b64decode(value,validate=True),aad))
    def _reviewer(self,uid):
        project=self.reviewers.get(uid)
        if project is None:raise PermissionError('PLATFORM_REVIEWER_REQUIRED')
        self.center.project(uid,project,('REVIEWER',))
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
    def _required(self,meta):
        base=tuple(k for k in BASE if k!='identity_back' or meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD')!='IDENTIFICATION_TYPE_OVERSEA_PASSPORT')
        # Old records without a declaration retain conservative offline requirements.
        # New UI always submits its selected scenes; no history is rewritten.
        scenes=checked_scenes(meta.get('sales_scenes_type',[STORE_SCENE]))
        scene_materials=(('storefront_photo','interior_photo') if STORE_SCENE in scenes else ())+(('mini_program_screenshot',) if MINI_SCENE in scenes else ())
        operator=() if not meta['delegated'] else ('operator_identity',)+(('operator_identity_back',) if meta.get('operator_identity_type','IDENTIFICATION_TYPE_IDCARD')!='IDENTIFICATION_TYPE_OVERSEA_PASSPORT' else ())
        return base+scene_materials+operator+(('industry_permit',) if meta['category']=='FOOD' else ())
    def _check_materials(self,application,meta):
        for kind in self._required(meta):
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
        owner=self.center.db.execute("SELECT user_id FROM links WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=? AND project=?",(application,application)).fetchone()[0]
        workspaces=[] if self.operations is None else [name for name,g in self.operations.grants.items()
            if g['user_id']==owner and g['onboarding_required']]
        data=dict(data,fields={k:v for k,v in data['fields'].items() if k!='license_ref'})
        wechat_record=self.wechat_applyment._read(application) if self.wechat_applyment is not None else None
        if wechat_record is not None:data['fields']=shared_application_fields(wechat_record.get('profile',{}),data['fields'])
        return dict(data,application=application,entity_type=meta['entity_type'],identity_type=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'),category=meta['category'],
            delegated=meta['delegated'],sales_scenes_type=meta.get('sales_scenes_type',[STORE_SCENE]),required_materials=list(self._required(meta)),
            materials={k:{'uploaded':True,'expires_at':v['expires_at'],
                'review':meta.get('reviews',{}).get(k,{}).get('decision','PENDING'),
                'review_note':meta.get('reviews',{}).get(k,{}).get('note','')} for k,v in meta['materials'].items()},
            opening_state=opening_state(self,application) if data['status']=='APPROVED' else 'NOT_APPROVED',
            opening_workspaces=workspaces,
            wechat_submerchant_state=wechat_record.get('provider_state','NOT_VERIFIED') if wechat_record else 'NOT_VERIFIED',payment_enabled=False)
    def dispatch(self,session,csrf,body):
        if type(body) is not dict or set(body)!={'operation','params'} or type(body['params']) is not dict:
            raise ValueError('INVALID_ONBOARDING_REQUEST')
        op,params=body['operation'],body['params'];c=self.center
        if op=='catalog' and params=={}:return self.catalog()
        if type(op) is str and op.startswith('wechat_'):
            if self.wechat_applyment is None:raise PermissionError('OFFICIAL_APPLYMENT_NOT_CONFIGURED')
            return self.wechat_applyment.dispatch(session,csrf,body)
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        uid=c.session(session,csrf)
        schemas={'mine':set(),'save':{'application','revision','fields','entity_type','category','delegated'},
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
                (not set(params).issubset({'cursor','status'}) if listing else (not (schemas[op]<=set(params)<=schemas[op]|{'identity_type','sales_scenes_type'}) if op=='save' else set(params)!=schemas[op]))):
            raise ValueError('INVALID_ONBOARDING_FIELDS')
        if c.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
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
            meta={'entity_type':params['entity_type'],'category':params['category'],'delegated':params['delegated'],'materials':{}}
            data=None
        else:owner,meta,data=self._load(application,uid,op in ('review','review_material') or op=='download' and uid in self.reviewers)
        if op=='download':
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
                meta.update(entity_type=params['entity_type'],category=params['category'],delegated=params['delegated'])
                meta['reviews']={}
                revision=workflow.save_draft(c.db,uid,application,uid,dict(fields,license_ref='PRIVATE_ONBOARDING_MATERIALS'),params['revision'],
                    encode=lambda value:self._encode(value,'onboarding-fields:'+application),manage_transaction=False)
                self._meta(application,uid,meta)
            elif op=='upload':
                if data['status'] not in ('DRAFT','CORRECTION_REQUIRED') or data['revision']!=params['revision']:raise ValueError('STATE_OR_REVISION_CONFLICT')
                kind=params['kind'];expires=params['expires_at']
                if type(kind) is not str or kind not in MATERIALS or expires is not None and (type(expires) is not int or expires<=c.now()):raise ValueError('INVALID_MATERIAL')
                if kind=='cashier_photo' and self.wechat_applyment is not None:
                    self.wechat_applyment.clear_cashier_media(application,owner)
                value=params['content_base64']
                if type(value) is not str or len(value)>6_666_668:raise ValueError('FILE_LIMIT')
                raw=base64.b64decode(value,validate=True)
                if not 1<=len(raw)<=5_000_000:raise ValueError('FILE_LIMIT')
                mime='application/pdf' if raw.startswith(b'%PDF-') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
                if mime is None:raise ValueError('PDF_PNG_JPEG_ONLY')
                safe_text(raw.decode('latin1'),5_000_000)
                if c.scanner is None:raise RuntimeError('EXISTING_SCANNER_REQUIRED')
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
                action='SUBMIT' if op=='submit' else 'WITHDRAW' if op=='withdraw' else params['action']
                if op=='review' and (action not in ('BEGIN_REVIEW','CORRECTION','REJECT','REOPEN','APPROVE') or owner==uid):raise PermissionError('INDEPENDENT_REVIEW_REQUIRED')
                if action in ('SUBMIT','APPROVE'):self._check_materials(application,meta)
                if action=='APPROVE':
                    account=c.db.execute('SELECT verified FROM accounts WHERE id=?',(owner,)).fetchone()
                    if account is None or account[0]!=1:raise PermissionError('VERIFIED_APPLICANT_REQUIRED')
                    for kind in self._required(meta):
                        review=meta.get('reviews',{}).get(kind,{})
                        if review.get('decision')!='ACCEPTED' or review.get('sha256')!=meta['materials'][kind]['sha256']:
                            raise ValueError('MATERIAL_REVIEW_REQUIRED:'+kind)
                note='' if op in ('submit','withdraw') else safe_text(params['note'],80)
                encoded_note=self._encode({'note':note},'onboarding-note:'+application) if note else ''
                revision=workflow.transition(c.db,owner,application,uid,'MERCHANT' if op in ('submit','withdraw') else 'REVIEWER',action,params['revision'],encoded_note,
                    decode=lambda value:self._decode(value,'onboarding-fields:'+application),manage_transaction=False)
                if action=='REOPEN':
                    # Reopening a rejection authorizes correction, not approval.
                    # New material decisions are required; immutable history stays.
                    meta['reviews']={}
                    self._meta(application,owner,meta)
            c.audit(application,uid,'MERCHANT_ONBOARDING_'+op.upper(),str(revision))
            from scripts.community_onboarding_history import append
            append(self,application,owner,uid,op,params,data,meta,revision)
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
