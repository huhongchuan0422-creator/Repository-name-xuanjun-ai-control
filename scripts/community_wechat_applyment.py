"""Private official submerchant application drafts, media and signed submission.

Official schemas: partner/4012719997, 4012697168, 4012760490.
Internal approval and provider acceptance are independent states. Host must
explicitly admit real submissions; no payment merchant binding is auto-created.
"""
import base64
import hashlib
import json
import re
import secrets
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.pr122_customer_core import canonical,private_path
from scripts.community_provider_transport import request

SENSITIVE={'contact_name','contact_id_number','mobile_phone','contact_email','id_card_name','id_card_number','id_card_address','id_doc_name','id_doc_number','id_doc_address','account_name','account_number','ubo_id_doc_name','ubo_id_doc_number','ubo_id_doc_address','ubo_address'}


def provider_applyment_id(data):
    # The official query/submit contracts use a required JSON integer (int64),
    # not a decimal string or a JSON boolean. Keep the persisted representation.
    value=data.get('applyment_id')
    if type(value) is not int or not 0<value<2**63:
        raise ValueError('INVALID_OFFICIAL_APPLYMENT_ID')
    return str(value)


def signed_response_context(value):
    if (type(value) is not dict or type(value.get('signed_at')) is not int
            or value['signed_at']<0 or type(value.get('signature_sha256')) is not str
            or not re.fullmatch('[0-9a-f]{64}',value['signature_sha256'])):
        raise ValueError('VERIFIED_PROVIDER_RESPONSE_CONTEXT_REQUIRED')
    return value


def consumed_rejection_signatures(record):
    return {receipt['signature_sha256'] for receipt in record.get('consumed_rejections',[])}


def used_provider_signatures(record):
    return (consumed_rejection_signatures(record)
        |{receipt['signature_sha256'] for receipt in record.get('submission_receipts',[])}
        |set(record.get('provider_query_signatures',[]))
        |{record.get('provider_query_signature_sha256'),record.get('submission_response_signature_sha256')})


def known_applyment_ids(record):
    return set(record.get('provider_applyment_history',[]))|({record['applyment_id']} if record.get('applyment_id') else set())


def submission_boundary(record):
    # Compare provider-signed times with provider-signed times. The local wall
    # clock remains audit context, never proof of a provider business generation.
    return max(record.get('submission_response_signed_at',-1),
        record.get('submission_recovery_receipt',{}).get('signed_at',-1))


def provider_response_claims(record):
    """Read current and historical claims, including pre-domain legacy records."""
    if type(record) is not dict:raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
    ids=set();signatures=set()
    def identity(value):
        if value is None:return
        if type(value) is not str or not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>=2**63:
            raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        ids.add(value)
    def signature(value):
        if value is None:return
        if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):
            raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        signatures.add(value)
    identity(record.get('applyment_id'))
    for field,consume in (('provider_applyment_history',identity),('provider_query_signatures',signature)):
        values=record.get(field,[])
        if type(values) is not list:raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        for value in values:consume(value)
    for field in ('provider_query_signature_sha256','submission_response_signature_sha256'):
        signature(record.get(field))
    receipts=[]
    for field in ('submission_receipts','consumed_rejections'):
        values=record.get(field,[])
        if type(values) is not list:raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        receipts.extend(values)
    receipts.extend(record[field] for field in ('correction_receipt','submission_recovery_receipt') if field in record)
    for receipt in receipts:
        if type(receipt) is not dict:raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        if 'business_code' in receipt and receipt['business_code']!=record.get('business_code'):
            raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED')
        identity(receipt.get('applyment_id'));signature(receipt.get('signature_sha256'))
    return ids,signatures


def original_submission_intent(current,code,version):
    """Only persist the response for the exact already-reserved application intent."""
    return (type(current) is dict and current.get('business_code')==code
            and current.get('state')=='SUBMISSION_UNKNOWN'
            and type(version) is int and current.get('version')==version)


class WechatApplyment:
    def __init__(self,onboarding,reader,*,submission_enabled=False):
        from scripts.community_merchant_onboarding import MerchantOnboarding
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        if type(onboarding) is not MerchantOnboarding or not isinstance(reader,PartnerOrderReader) or type(submission_enabled) is not bool:raise ValueError('ORIGINAL_ONBOARDING_AND_PROVIDER_REQUIRED')
        self.onboarding,self.center,self.reader=onboarding,onboarding.center,reader
        self.enabled=submission_enabled
    def _read(self,application):
        row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0],'wechat-applyment:'+application))
    def _save(self,application,owner,record):
        self.center.db.execute("INSERT INTO links VALUES('COMMUNITY_WECHAT_APPLYMENT',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",(application,owner,application,self.center.encrypt(canonical(record),'wechat-applyment:'+application)))
    def _provider_domain(self,record,*,submission=False):
        merchant=self.reader._mchid
        if type(merchant) is not str or not re.fullmatch('[0-9]{6,32}',merchant):
            raise ValueError('PROTECTED_PROVIDER_MERCHANT_REQUIRED')
        bound=record.get('provider_sp_mchid')
        if bound is not None and bound!=merchant:
            raise PermissionError('PROVIDER_APPLICATION_SERVICE_MERCHANT_CHANGED')
        if submission and record.get('business_code') and bound is None:
            raise PermissionError('PROVIDER_APPLICATION_DOMAIN_UNCONFIRMED_QUERY_REQUIRED')
        return merchant
    def _check_response_owner(self,application,code,merchant,applyment_id,verified):
        # BEGIN IMMEDIATE serializes the check and the following original-record
        # save across all applications/connections. No separate account or ledger.
        c=self.center
        if not c.db.in_transaction:raise ValueError('ORIGINAL_CENTER_TRANSACTION_REQUIRED')
        if self.reader._mchid!=merchant:
            raise PermissionError('PROVIDER_APPLICATION_SERVICE_MERCHANT_CHANGED')
        rows=c.db.execute("SELECT subject_idx,project,payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT'")
        for row in rows:
            try:
                if row['subject_idx']!=row['project']:raise ValueError()
                other=json.loads(c.decrypt(row['payload'],'wechat-applyment:'+row['subject_idx']))
                ids,signatures=provider_response_claims(other)
                domain=other.get('provider_sp_mchid')
                if domain is not None and (type(domain) is not str or not re.fullmatch('[0-9]{6,32}',domain)):
                    raise ValueError()
                other_code=other.get('business_code')
                if (ids or signatures) and (type(other_code) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',other_code)):
                    raise ValueError()
            except Exception:
                # Do not leak another application's identity or ciphertext.
                raise ValueError('PROVIDER_APPLICATION_OWNERSHIP_UNCONFIRMED') from None
            # A known raw signed response cannot migrate even across providers.
            # IDs are scoped to the merchant; an unknown legacy domain is never
            # treated as proof that a matching ID belongs to another merchant.
            collision=(verified['signature_sha256'] in signatures
                or domain in (None,merchant) and applyment_id in ids)
            if collision and (row['subject_idx']!=application or other_code!=code):
                raise ValueError('PROVIDER_APPLYMENT_OWNERSHIP_CONFLICT')
    def _validate(self,profile,entity):
        required={'contact_info','subject_info','business_info','settlement_info','bank_account_info'}
        if type(profile) is not dict or not required.issubset(profile) or set(profile)-required-{'addition_info'} or any(type(profile[k]) is not dict for k in profile):raise ValueError('OFFICIAL_APPLYMENT_SECTIONS_REQUIRED')
        if len(canonical(profile))>100000:raise ValueError('APPLYMENT_PROFILE_TOO_LARGE')
        subject=profile['subject_info']
        expected='SUBJECT_TYPE_ENTERPRISE' if entity=='ENTERPRISE' else 'SUBJECT_TYPE_INDIVIDUAL'
        if subject.get('subject_type')!=expected:raise ValueError('OFFICIAL_SUBJECT_TYPE_MISMATCH')
        mandatory={'contact_info':('contact_name','mobile_phone','contact_email'),
            'subject_info':('business_license_info','identity_info'),
            'business_info':('merchant_shortname','service_phone','sales_info'),
            'settlement_info':('settlement_id','qualification_type'),
            'bank_account_info':('bank_account_type','account_name','account_bank','account_number')}
        missing=[section+'.'+field for section,fields in mandatory.items() for field in fields if not profile[section].get(field)]
        if missing:raise ValueError('MISSING_OFFICIAL_FIELDS:'+','.join(missing))
        bank=profile['bank_account_info']
        if bank['bank_account_type'] not in ('BANK_ACCOUNT_TYPE_CORPORATE','BANK_ACCOUNT_TYPE_PERSONAL') or entity=='ENTERPRISE' and bank['bank_account_type']!='BANK_ACCOUNT_TYPE_CORPORATE':raise ValueError('OFFICIAL_BANK_ACCOUNT_TYPE_MISMATCH')
        license=subject['business_license_info'];identity=subject['identity_info']
        if type(license) is not dict or type(identity) is not dict:raise ValueError('OFFICIAL_LICENSE_AND_IDENTITY_OBJECTS_REQUIRED')
        missing=['subject_info.business_license_info.'+k for k in ('license_copy','license_number','merchant_name','legal_person') if not license.get(k)]
        if identity.get('id_doc_type')=='IDENTIFICATION_TYPE_IDCARD':
            card=identity.get('id_card_info')
            if type(card) is not dict:raise ValueError('OFFICIAL_ID_CARD_INFO_REQUIRED')
            missing+=['subject_info.identity_info.id_card_info.'+k for k in ('id_card_copy','id_card_national','id_card_name','id_card_number','card_period_begin','card_period_end') if not card.get(k)]
            if entity=='ENTERPRISE' and not card.get('id_card_address'):missing.append('subject_info.identity_info.id_card_info.id_card_address')
            account_name=license['merchant_name'] if bank['bank_account_type']=='BANK_ACCOUNT_TYPE_CORPORATE' else card.get('id_card_name')
            if bank['account_name']!=account_name:raise ValueError('OFFICIAL_ACCOUNT_HOLDER_NAME_MISMATCH')
        sales=profile['business_info']['sales_info']
        if type(sales) is not dict or type(sales.get('sales_scenes_type')) is not list or not sales['sales_scenes_type']:missing.append('business_info.sales_info.sales_scenes_type')
        elif 'SALES_SCENES_MINI_PROGRAM' in sales['sales_scenes_type']:
            mini=sales.get('mini_program_info',{})
            if type(mini) is not dict or not (mini.get('mini_program_appid') or mini.get('mini_program_sub_appid')):missing.append('business_info.sales_info.mini_program_info.appid')
        if missing:raise ValueError('MISSING_OFFICIAL_FIELDS:'+','.join(missing))
        from scripts.community_applyment_conditions import validate
        validate(profile,entity,self.center.now())
        # Current official industry/bank catalogs and provider review remain authoritative.
    def _encrypt(self,value,key=None):
        if type(value) is dict:return {k:self._encrypt(v,k) for k,v in value.items()}
        if type(value) is list:return [self._encrypt(v,key) for v in value]
        if key in SENSITIVE:
            if type(value) is not str or not value or len(value.encode())>serialization.load_pem_public_key(self.reader._public).key_size//8-42:raise ValueError('INVALID_SENSITIVE_OFFICIAL_FIELD')
            public=serialization.load_pem_public_key(self.reader._public)
            return base64.b64encode(public.encrypt(value.encode(),padding.OAEP(mgf=padding.MGF1(hashes.SHA1()),algorithm=hashes.SHA1(),label=None))).decode()
        return value
    def _validate_media(self,profile,application,meta):
        rows=self.center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND project=? AND active=1",(application,)).fetchall()
        admitted=set()
        for key,payload in rows:
            value=json.loads(self.center.decrypt(payload,'wechat-media:'+key))
            current=meta['materials'].get(value['kind'])
            if current and current['sha256']==value['sha256'] and (current['expires_at'] is None or current['expires_at']>self.center.now()):admitted.add(value['media_id'])
        def walk(value,key=''):
            if type(value) is dict:
                for k,v in value.items():walk(v,k)
            elif type(value) is list:
                for v in value:walk(v,key)
            elif type(value) is str and (key.endswith(('_copy','_copy_back','_pic','_pics')) or key in ('id_card_national','qualifications','business_authorization_letter','legal_person_commitment','addition_pics','activities_additions','web_authorisation')):
                if value not in admitted:raise PermissionError('CURRENT_ORIGINAL_APPLICATION_MEDIA_REQUIRED')
        walk(profile)

    def dispatch(self,session,csrf,body):
        if type(body) is not dict or set(body)!={'operation','params'} or type(body['params']) is not dict:raise ValueError('INVALID_WECHAT_APPLYMENT_REQUEST')
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf);op,p=body['operation'],body['params']
        fields={'wechat_read':{'application'},'wechat_review_read':{'application'},'wechat_save':{'application','expected_version','profile'},
            'wechat_submit_review':{'application','expected_version'},'wechat_review':{'application','expected_version','decision','opinion'},
            'wechat_media':{'application','kind'},'wechat_execute':{'application','expected_version'},'wechat_query':{'application'}}
        if type(op) is not str or op not in fields or set(p)!=fields[op]:raise ValueError('INVALID_WECHAT_APPLYMENT_FIELDS')
        reviewer=op in ('wechat_review_read','wechat_review','wechat_execute','wechat_query')
        owner,meta,platform=self.onboarding._load(p['application'],uid,reviewer)
        application=p['application']
        if platform['status']=='WITHDRAWN' and op not in ('wechat_read','wechat_review_read','wechat_query'):
            raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        with c.tx():c.limit('wechat-applyment:'+uid,20,60)
        if op=='wechat_media':return self.media(uid,owner,application,meta,p['kind'],lambda:c.session(session,csrf))
        record=self._read(application)
        if op in ('wechat_read','wechat_review_read'):return record or dict(version=0,state='DRAFT',provider_state='NOT_SUBMITTED')
        if op=='wechat_query':
            if record is None or not record.get('business_code'):raise ValueError('PROVIDER_APPLICATION_NOT_SUBMITTED')
            merchant=self._provider_domain(record)
            data,digest,verified=request(self.reader,'GET','/v3/applyment4sub/applyment/business_code/'+record['business_code'],include_verification=True)
            verified=signed_response_context(verified)
            if data.get('business_code')!=record['business_code'] or type(data.get('applyment_state')) is not str:raise ValueError('PROVIDER_APPLYMENT_BINDING_MISMATCH')
            applyment_id=provider_applyment_id(data)
            recovered_generation=(record['state']=='SUBMISSION_UNKNOWN'
                and record.get('replacement_submission',False)
                and record.get('applyment_id') is not None
                and applyment_id not in known_applyment_ids(record))
            if record.get('applyment_id') not in (None,applyment_id):
                if not recovered_generation:raise ValueError('PROVIDER_APPLYMENT_ID_MISMATCH')
            allowed=('APPLYMENT_STATE_EDITTING','APPLYMENT_STATE_AUDITING','APPLYMENT_STATE_REJECTED','APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED','APPLYMENT_STATE_SIGNING','APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED')
            if data['applyment_state'] not in allowed:raise ValueError('UNKNOWN_PROVIDER_APPLICATION_STATE')
            with c.tx():
                if c.session(session,csrf)!=uid:raise PermissionError('CURRENT_REVIEWER_SESSION_REQUIRED')
                self.onboarding._load(application,uid,True)
                current=self._read(application)
                if current!=record:raise ValueError('APPLYMENT_CHANGED')
                if (current.get('provider_state') in ('APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED')
                        and current['provider_state']!=data['applyment_state']):
                    raise ValueError('TERMINAL_PROVIDER_APPLYMENT_STATE_CONFLICT')
                # Same business_code (and often the same applyment_id) survives
                # correction. A pre-submission signed rejection is not evidence
                # about the new revision, even inside the signature time window.
                boundary=submission_boundary(current)
                prior=current.get('provider_query_signed_at')
                if ((verified['signed_at']<=boundary)
                        or (prior is not None and verified['signed_at']<prior)
                        or (prior==verified['signed_at'] and current.get('provider_state')!=data['applyment_state'])
                        or verified['signature_sha256'] in consumed_rejection_signatures(current)):
                    raise ValueError('STALE_PROVIDER_APPLYMENT_RESPONSE')
                current.update(applyment_id=applyment_id,provider_state=data['applyment_state'],provider_response_sha256=digest,provider_observed_at=c.now())
                current['provider_applyment_history']=sorted(known_applyment_ids(record)|{applyment_id})
                current.update(provider_query_signed_at=verified['signed_at'],
                    provider_query_signature_sha256=verified['signature_sha256'])
                current['provider_query_signatures']=sorted(
                    set(current.get('provider_query_signatures',[]))|{verified['signature_sha256']})
                if recovered_generation:
                    # A previously unseen provider identity, explicitly returned
                    # for this business_code, distinguishes the new application.
                    # Same-ID status changes alone cannot recover an unknown POST.
                    current.update(state='SUBMITTED_TO_PROVIDER',submission_recovery_receipt=dict(
                        business_code=record['business_code'],applyment_id=applyment_id,
                        response_sha256=digest,**verified))
                if data.get('sub_mchid') is not None:
                    if type(data['sub_mchid']) is not str or not re.fullmatch('[0-9]{6,32}',data['sub_mchid']):raise ValueError('INVALID_PROVIDER_SUBMERCHANT')
                    if current.get('provider_sub_mchid') not in (None,data['sub_mchid']):
                        raise ValueError('IMMUTABLE_PROVIDER_SUBMERCHANT_CONFLICT')
                    current['provider_sub_mchid']=data['sub_mchid']
                current['audit_detail']=data.get('audit_detail',[])
                # Official 4012697168: a rejected application is corrected using
                # the SAME business_code. Only a current signed query opens this
                # path. A timed-out replacement may still expose the preceding
                # rejection, so that observation cannot authorize another POST.
                submitted_with_boundary=(current['state']=='SUBMITTED_TO_PROVIDER'
                    and (not current.get('replacement_submission',False)
                         or submission_boundary(current)>=0))
                if (data['applyment_state']=='APPLYMENT_STATE_REJECTED'
                        and (submitted_with_boundary
                             or current['state']=='SUBMISSION_UNKNOWN'
                             and not current.get('replacement_submission',False))):
                    current.update(state='CORRECTION',version=current['version']+1,
                        correction_receipt=dict(business_code=record['business_code'],
                            applyment_id=applyment_id,
                            signature_sha256=verified['signature_sha256'],signed_at=verified['signed_at'],
                            response_sha256=digest,observed_at=c.now()))
                self._check_response_owner(application,record['business_code'],merchant,applyment_id,verified)
                current['provider_sp_mchid']=merchant
                self._save(application,owner,current);c.audit(application,uid,'WECHAT_APPLYMENT_QUERIED',digest)
            return current
        version=record['version'] if record else 0
        if type(p['expected_version']) is not int or p['expected_version']!=version:raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
        if op=='wechat_execute':
            if not self.enabled:raise PermissionError('REAL_MERCHANT_SUBMISSION_GATE_CLOSED')
            if record is None or record['state']!='INTERNAL_APPROVED' or platform['status']!='APPROVED':raise PermissionError('SEPARATE_INTERNAL_AND_PLATFORM_APPROVAL_REQUIRED')
            merchant=self._provider_domain(record,submission=True)
            self.onboarding._check_materials(application,meta)
            self._validate(record['profile'],meta['entity_type'])
            if record['profile']['subject_info']['identity_info']['id_doc_type']!=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'):raise ValueError('PLATFORM_IDENTITY_TYPE_MISMATCH')
            if meta['category']=='FOOD' and not record['profile']['settlement_info'].get('qualifications'):raise ValueError('FOOD_QUALIFICATIONS_REQUIRED_BY_EXISTING_CATEGORY')
            self._validate_media(record['profile'],application,meta)
            code=record.get('business_code') or 'ap'+hashlib.sha256(canonical([merchant,application,version])).hexdigest()[:30]
            correction=record.get('correction_receipt')
            if record.get('business_code') and (record.get('provider_state')!='APPLYMENT_STATE_REJECTED'
                    or type(correction) is not dict
                    or correction.get('business_code')!=code
                    or correction.get('applyment_id')!=record.get('applyment_id')
                    or type(correction.get('signed_at')) is not int
                    or not re.fullmatch('[0-9a-f]{64}',str(correction.get('signature_sha256','')))
                    or correction.get('signature_sha256') in consumed_rejection_signatures(record)
                    or not re.fullmatch('[0-9a-f]{64}',str(correction.get('response_sha256','')))):
                raise PermissionError('SIGNED_PROVIDER_REJECTION_REQUIRED')
            # Initial legacy attempts keep their original key; corrected revisions
            # have their own consumed intent, retaining the original provider ID.
            attempt=code if not correction else code+':revision:'+str(version)
            payload=dict(self._encrypt(record['profile']),business_code=code)
            with c.tx():
                if c.session(session,csrf)!=uid:raise PermissionError('CURRENT_REVIEWER_SESSION_REQUIRED')
                current_owner,current_meta,current_platform=self.onboarding._load(application,uid,True)
                if (current_owner,current_meta,current_platform)!=(owner,meta,platform):raise ValueError('WECHAT_APPLYMENT_CHANGED')
                current=self._read(application)
                if current!=record:raise ValueError('WECHAT_APPLYMENT_CHANGED')
                if c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_APPLYMENT_ATTEMPT' AND event_id=?",(attempt,)).fetchone():raise PermissionError('QUERY_EXISTING_APPLICATION_ONLY')
                c.db.execute("INSERT INTO events VALUES('WECHAT_APPLYMENT_ATTEMPT',?,?)",(attempt,c.now()))
                current.update(state='SUBMISSION_UNKNOWN',business_code=code,
                    replacement_submission=bool(correction),submission_started_at=c.now(),provider_sp_mchid=merchant)
                if correction:
                    current['consumed_rejections']=[*current.get('consumed_rejections',[]),
                        dict(correction,submission_version=version)]
                current.pop('correction_receipt',None);self._save(application,owner,current)
                c.audit(application,uid,'WECHAT_APPLYMENT_SUBMISSION_ATTEMPT',code)
            data,digest,verified=request(self.reader,'POST','/v3/applyment4sub/applyment/',payload,include_verification=True)
            verified=signed_response_context(verified)
            # The submit response contains only applyment_id. A signed GET
            # response or error is not a submission ACK, even though it may also
            # carry that field. Verify response semantics as well as signatures.
            if set(data)!={'applyment_id'}:
                raise ValueError('INVALID_OFFICIAL_APPLYMENT_SUBMISSION_RESPONSE')
            applyment_id=provider_applyment_id(data)
            previous_signatures=used_provider_signatures(record)
            if correction:previous_signatures.add(correction['signature_sha256'])
            if (verified['signed_at']<max(correction['signed_at'] if correction else -1,
                    submission_boundary(record)) or verified['signature_sha256'] in previous_signatures):
                raise ValueError('STALE_PROVIDER_APPLYMENT_SUBMISSION_RESPONSE')
            if applyment_id!=record.get('applyment_id') and applyment_id in known_applyment_ids(record):
                raise ValueError('PROVIDER_APPLYMENT_ID_MISMATCH')
            with c.tx():
                if c.session(session,csrf)!=uid:raise PermissionError('CURRENT_REVIEWER_SESSION_REQUIRED')
                self.onboarding._load(application,uid,True)
                current=self._read(application)
                if not original_submission_intent(current,code,version):
                    raise ValueError('APPLYMENT_SUBMISSION_RACE_QUERY_EXISTING_ONLY')
                if verified['signature_sha256'] in used_provider_signatures(current):
                    raise ValueError('STALE_PROVIDER_APPLYMENT_SUBMISSION_RESPONSE')
                if current.get('applyment_id') not in (None,record.get('applyment_id'),applyment_id):
                    raise ValueError('PROVIDER_APPLYMENT_ID_MISMATCH')
                self._check_response_owner(application,code,merchant,applyment_id,verified)
                current.update(state='SUBMITTED_TO_PROVIDER',applyment_id=applyment_id,provider_response_sha256=digest,
                    submission_response_signed_at=verified['signed_at'],
                    submission_response_signature_sha256=verified['signature_sha256'])
                current['provider_applyment_history']=sorted(known_applyment_ids(current)|known_applyment_ids(record))
                current['submission_receipts']=[*current.get('submission_receipts',[]),
                    dict(business_code=code,applyment_id=applyment_id,response_sha256=digest,
                         submission_version=version,**verified)]
                self._save(application,owner,current);c.audit(application,uid,'WECHAT_APPLYMENT_SUBMITTED',code)
            return current
        with c.tx():
            if c.session(session,csrf)!=uid:raise PermissionError('CURRENT_APPLYMENT_SESSION_REQUIRED')
            if self.onboarding._load(application,uid,reviewer)[2]['status']=='WITHDRAWN':
                raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
            if self._read(application)!=record:raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
            if op=='wechat_save':
                if record and record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('PAYMENT_APPLICATION_EDIT_DENIED')
                if type(p['profile']) is not dict or len(canonical(p['profile']))>100000:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
                result=dict(record or {},version=version+1,state='DRAFT',profile=p['profile'])
                if not record:result['provider_state']='NOT_SUBMITTED'
            elif op=='wechat_submit_review':
                if record is None or record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('PAYMENT_DRAFT_REQUIRED')
                self._validate(record['profile'],meta['entity_type'])
                if record['profile']['subject_info']['identity_info']['id_doc_type']!=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'):raise ValueError('PLATFORM_IDENTITY_TYPE_MISMATCH')
                result=dict(record,version=version+1,state='PENDING_INTERNAL_REVIEW')
            else:
                if uid==owner or record is None or record['state']!='PENDING_INTERNAL_REVIEW' or p['decision'] not in ('INTERNAL_APPROVED','CORRECTION') or type(p['opinion']) is not str or not 1<=len(p['opinion'])<=1000:raise PermissionError('INDEPENDENT_PAYMENT_APPLICATION_REVIEW_REQUIRED')
                result=dict(record,version=version+1,state=p['decision'],opinion=p['opinion'],reviewer=uid)
            self._save(application,owner,result);c.audit(application,uid,'WECHAT_'+op.upper(),str(result['version']))
        return result
    def media(self,uid,owner,application,meta,kind,reauthorize):
        if not self.enabled:raise PermissionError('REAL_MERCHANT_MEDIA_UPLOAD_GATE_CLOSED')
        if type(kind) is not str or kind not in meta['materials']:raise ValueError('ORIGINAL_PRIVATE_MATERIAL_REQUIRED')
        material=meta['materials'][kind];c=self.center
        if material['expires_at'] is not None and material['expires_at']<=c.now():raise ValueError('EXPIRED_PRIVATE_MATERIAL')
        row=c.db.execute('SELECT project,sha,scan,mime FROM objects WHERE id=?',(material['object_id'],)).fetchone()
        if row is None or tuple(row[:3])!=(application,material['sha256'],'CLEAN'):raise PermissionError('SCANNED_ORIGINAL_MATERIAL_REQUIRED')
        extensions={'image/jpeg':'jpg','image/png':'png','application/pdf':'pdf'}
        if row[3] not in extensions:raise ValueError('UNSUPPORTED_PROVIDER_MEDIA')
        raw=c.decrypt(private_path(c.objects/material['object_id']).read_bytes(),'object:'+application+':'+material['object_id'])
        if hashlib.sha256(raw).hexdigest()!=material['sha256'] or len(raw)>5000000:raise PermissionError('PRIVATE_MEDIA_INTEGRITY_OR_SIZE')
        filename='material.'+extensions[row[3]];metadata=canonical(dict(filename=filename,sha256=material['sha256']))
        boundary='xj'+secrets.token_hex(24)
        body=('--'+boundary+'\r\nContent-Disposition: form-data; name="meta"\r\nContent-Type: application/json\r\n\r\n').encode()+metadata+('\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+filename+'"\r\nContent-Type: '+row[3]+'\r\n\r\n').encode()+raw+('\r\n--'+boundary+'--\r\n').encode()
        if reauthorize()!=uid:raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
        if self.onboarding._load(application,uid)[2]['status']=='WITHDRAWN':raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        # Once sent, retain the original response evidence even if the applicant
        # later withdraws locally. Withdrawal never cancels a provider operation.
        data,digest=request(self.reader,'POST','/v3/merchant/media/upload',raw=body,content_type='multipart/form-data; boundary='+boundary,signing_body=metadata)
        if type(data.get('media_id')) is not str or not 1<=len(data['media_id'])<=1024:raise ValueError('INVALID_PROVIDER_MEDIA_ID')
        with c.tx():
            if reauthorize()!=uid:raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
            self.onboarding._load(application,uid)
            key=hashlib.sha256(canonical([self.reader._mchid,application,kind,material['sha256']])).hexdigest()
            c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_WECHAT_MEDIA',?,?,?,?,1)",(key,owner,application,c.encrypt(canonical(dict(media_id=data['media_id'],kind=kind,sha256=material['sha256'],provider_response_sha256=digest)),'wechat-media:'+key)))
            c.audit(application,uid,'WECHAT_MEDIA_UPLOADED',key)
        return dict(media_id=data['media_id'],kind=kind,source_sha256=material['sha256'])
