"""Merchant admission on existing Center identity, storage and onboarding tables.

Business review does not approve WeChat submerchant registration or enable funds.
An applicant needs an existing verified account, not a fictitious signed project.
"""
import base64
import hashlib
import json
import secrets
import shutil
from pathlib import Path
from scripts.pr122_customer_core import Center,canonical,secure_write,private_path,safe_text
from scripts import community_onboarding_offline as workflow

MATERIALS={
    'business_license':'营业执照', 'identity_front':'经营者/法定代表人身份证人像面',
    'identity_back':'经营者/法定代表人身份证国徽面', 'storefront_photo':'门店门头照片',
    'interior_photo':'门店经营场所照片', 'settlement_proof':'结算账户证明',
    'operator_authorization':'经办人授权书', 'operator_identity':'经办人身份证明',
    'industry_permit':'行业经营许可（按经营类目）'}
BASE=('business_license','identity_front','identity_back','storefront_photo','interior_photo','settlement_proof')


class MerchantOnboarding:
    def __init__(self,center,reviewers):
        if type(center) is not Center or type(reviewers) is not dict or not reviewers:
            raise ValueError('EXISTING_CENTER_AND_PROTECTED_REVIEWERS_REQUIRED')
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest()!=\
                'f9a736fa954bcc3fbdf2eea317bb0b71559864126c940ac6738a4bc9e4a87bd4':
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        if any(type(k) is not str or not k or type(v) is not str or not v for k,v in reviewers.items()):
            raise ValueError('ORIGINAL_REVIEWER_PROJECT_BINDING_REQUIRED')
        if center.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        self.center=center;self.reviewers=dict(reviewers)
        # Reuse the already developed onboarding business tables in the original
        # Center backup domain. No second account store or review queue exists.
        workflow.initialize(center.db)
    @staticmethod
    def catalog():
        return {'entity_types':{'ENTERPRISE':'企业','SOLE_PROPRIETOR':'个体工商户'},
                'materials':[{'id':k,'title':v,'required':k in BASE} for k,v in MATERIALS.items()],
                'formats':['application/pdf','image/png','image/jpeg'],'max_file_bytes':5_000_000,
                'industry_permit_required_for':['FOOD'],'operator_materials_when_delegated':True,
                'scope':'平台业务入驻资料清单；微信进件由支付服务商独立核验',
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
        data=workflow.get_application(self.center.db,owner,application,
            decode=lambda value:self._decode(value,'onboarding-fields:'+application))
        if data['reviewer_note']:
            data['reviewer_note']=self._decode(data['reviewer_note'],'onboarding-note:'+application)['note']
        return owner,meta,data
    def _meta(self,application,owner,meta):
        self.center.db.execute("INSERT INTO links VALUES('COMMUNITY_ONBOARDING',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",
            (application,owner,application,self._encode(meta,'onboarding-meta:'+application)))
    def _required(self,meta):
        return BASE+(('operator_authorization','operator_identity') if meta['delegated'] else ())+(('industry_permit',) if meta['category']=='FOOD' else ())
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
        data=dict(data,fields={k:v for k,v in data['fields'].items() if k!='license_ref'})
        return dict(data,application=application,entity_type=meta['entity_type'],category=meta['category'],
            delegated=meta['delegated'],required_materials=list(self._required(meta)),
            materials={k:{'uploaded':True,'expires_at':v['expires_at'],
                'review':meta.get('reviews',{}).get(k,{}).get('decision','PENDING'),
                'review_note':meta.get('reviews',{}).get(k,{}).get('note','')} for k,v in meta['materials'].items()},
            opening_state='AWAITING_CRM_BINDING' if data['status']=='APPROVED' else 'NOT_APPROVED',
            wechat_submerchant_state='NOT_VERIFIED',payment_enabled=False)
    def dispatch(self,session,csrf,body):
        if type(body) is not dict or set(body)!={'operation','params'} or type(body['params']) is not dict:
            raise ValueError('INVALID_ONBOARDING_REQUEST')
        op,params=body['operation'],body['params'];c=self.center
        if op=='catalog' and params=={}:return self.catalog()
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        uid=c.session(session,csrf)
        schemas={'mine':set(),'save':{'application','revision','fields','entity_type','category','delegated'},
                 'upload':{'application','revision','kind','content_base64','expires_at'},
                 'submit':{'application','revision'},'review_list':set(),
                 'review_read':{'application'},'review':{'application','revision','action','note'},
                 'review_material':{'application','revision','kind','decision','note'},
                 'download':{'application','kind'}}
        if type(op) is not str or op not in schemas or set(params)!=schemas[op]:raise ValueError('INVALID_ONBOARDING_FIELDS')
        if c.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        if op in ('mine','review_list'):
            if op=='review_list':self._reviewer(uid)
            rows=c.db.execute("SELECT subject_idx FROM links WHERE channel='COMMUNITY_ONBOARDING' AND active=1"+
                (' AND user_id=?' if op=='mine' else '')+' ORDER BY subject_idx LIMIT 101',(uid,) if op=='mine' else ()).fetchall()
            if len(rows)>100:raise ValueError('APPLICATION_LIST_REQUIRES_PAGINATION')
            return {'applications':[self._view(row[0],*self._load(row[0],uid,op=='review_list')[1:]) for row in rows]}
        if op=='review_read':
            _,meta,data=self._load(params['application'],uid,True)
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
        c.db.execute('BEGIN IMMEDIATE')
        try:
            # Reload under the original DB write lock for stale-version safety.
            if data is not None:owner,meta,data=self._load(application,uid,op in ('review','review_material'))
            c.limit('merchant-onboarding:'+uid,60,3600)
            if op=='save':
                if params['entity_type'] not in ('ENTERPRISE','SOLE_PROPRIETOR') or params['category'] not in ('GENERAL','FOOD') or type(params['delegated']) is not bool:
                    raise ValueError('INVALID_BUSINESS_TYPE')
                fields=params['fields']
                if type(fields) is not dict or set(fields)!={'legal_name','store_name','address','contact'}:raise ValueError('INVALID_PROFILE_FIELDS')
                for value in fields.values():
                    if type(value) is not str:raise ValueError('INVALID_PROFILE_VALUE')
                    if value:safe_text(value,512)
                meta.update(entity_type=params['entity_type'],category=params['category'],delegated=params['delegated'])
                meta['reviews']={}
                revision=workflow.save_draft(c.db,uid,application,uid,dict(fields,license_ref='PRIVATE_ONBOARDING_MATERIALS'),params['revision'],
                    encode=lambda value:self._encode(value,'onboarding-fields:'+application),manage_transaction=False)
                self._meta(application,uid,meta)
            elif op=='upload':
                if data['status'] not in ('DRAFT','CORRECTION_REQUIRED') or data['revision']!=params['revision']:raise ValueError('STATE_OR_REVISION_CONFLICT')
                kind=params['kind'];expires=params['expires_at']
                if type(kind) is not str or kind not in MATERIALS or expires is not None and (type(expires) is not int or expires<=c.now()):raise ValueError('INVALID_MATERIAL')
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
                secure_write(c.objects/oid,c.encrypt(raw,'object:'+application+':'+oid))
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
                action='SUBMIT' if op=='submit' else params['action']
                if op=='review' and (action not in ('BEGIN_REVIEW','CORRECTION','REJECT','APPROVE') or owner==uid):raise PermissionError('INDEPENDENT_REVIEW_REQUIRED')
                if action in ('SUBMIT','APPROVE'):self._check_materials(application,meta)
                if action=='APPROVE':
                    account=c.db.execute('SELECT verified FROM accounts WHERE id=?',(owner,)).fetchone()
                    if account is None or account[0]!=1:raise PermissionError('VERIFIED_APPLICANT_REQUIRED')
                    for kind in self._required(meta):
                        review=meta.get('reviews',{}).get(kind,{})
                        if review.get('decision')!='ACCEPTED' or review.get('sha256')!=meta['materials'][kind]['sha256']:
                            raise ValueError('MATERIAL_REVIEW_REQUIRED:'+kind)
                note='' if op=='submit' else safe_text(params['note'],80)
                encoded_note=self._encode({'note':note},'onboarding-note:'+application) if note else ''
                revision=workflow.transition(c.db,owner,application,uid,'MERCHANT' if op=='submit' else 'REVIEWER',action,params['revision'],encoded_note,
                    decode=lambda value:self._decode(value,'onboarding-fields:'+application),manage_transaction=False)
            c.audit(application,uid,'MERCHANT_ONBOARDING_'+op.upper(),str(revision))
            c.db.commit()
        except BaseException:
            c.db.rollback();raise
        _,meta,data=self._load(application,uid,op in ('review','review_material'))
        return self._view(application,meta,data)
