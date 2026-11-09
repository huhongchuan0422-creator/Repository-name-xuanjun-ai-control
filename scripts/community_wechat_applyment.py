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
from io import BytesIO
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.pr122_customer_core import canonical,private_path
from scripts.community_provider_transport import request

class WechatMediaUnavailable(PermissionError):
    """Explicitly disabled provider capability, never an authentication result."""


class WechatMediaPending(PermissionError):
    """A durable provider attempt lacks a verified receipt; never blindly resend."""


SENSITIVE={'contact_name','contact_id_number','mobile_phone','contact_email','id_card_name','id_card_number','id_card_address','id_doc_name','id_doc_number','id_doc_address','account_name','account_number','ubo_id_doc_name','ubo_id_doc_number','ubo_id_doc_address','ubo_address'}

PROVIDER_WORKFLOW={
    'APPLYMENT_STATE_AUDITING':'PENDING_REVIEW',
    'APPLYMENT_STATE_TO_BE_CONFIRMED':'PENDING_CONFIRMATION',
    'APPLYMENT_STATE_TO_BE_SIGNED':'PENDING_CONFIRMATION',
    'APPLYMENT_STATE_SIGNING':'OPENING',
    'APPLYMENT_STATE_EDITTING':'CORRECTION_OR_REJECTION',
    'APPLYMENT_STATE_REJECTED':'CORRECTION_OR_REJECTION',
    'APPLYMENT_STATE_CANCELED':'EXCEPTION',
    'APPLYMENT_STATE_FINISHED':'COMPLETED',
}


def provider_workflow(state):
    """Stable operator queue bucket; unknown values stay visible as exceptions."""
    if state in ('NOT_SUBMITTED','NOT_VERIFIED',None):return 'PENDING_SUBMISSION'
    return PROVIDER_WORKFLOW.get(state,'EXCEPTION')


def provider_workflow_view(record):
    state=record.get('provider_state','NOT_SUBMITTED') if type(record) is dict else 'NOT_SUBMITTED'
    bucket=provider_workflow(state)
    return dict(state=state,bucket=bucket,completed=bucket=='COMPLETED',
        sign_action_available=(bucket=='PENDING_CONFIRMATION'
            and type(record) is dict
            and type(record.get('provider_sign_url')) is str
            and type(record.get('provider_sign_url_proof')) is dict),
        sync_error=record.get('provider_sync_error') if type(record) is dict else None,
        sync_error_at=record.get('provider_sync_error_at') if type(record) is dict else None)


def provider_applyment_id(data):
    # The official query/submit contracts use a required JSON integer (int64),
    # not a decimal string or a JSON boolean. Keep the persisted representation.
    value=data.get('applyment_id')
    if type(value) is not int or not 0<value<2**63:
        raise ValueError('INVALID_OFFICIAL_APPLYMENT_ID')
    return str(value)


def official_signing_url(value):
    """Official 4012697168 link, from this application's verified query only."""
    from urllib.parse import urlsplit
    if (type(value) is not str or not 1<=len(value)<=256
            or any(ord(c)<33 or ord(c)>126 for c in value) or '\\' in value):
        raise ValueError('INVALID_OFFICIAL_SIGNING_URL')
    parsed=urlsplit(value)
    if (parsed.scheme!='https' or parsed.netloc!='pay.weixin.qq.com'
            or parsed.path!='/public/apply4ec_sign/s' or not parsed.query or parsed.fragment):
        raise ValueError('INVALID_OFFICIAL_SIGNING_URL')
    return value


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
    def fill_confirmed_license_draft(self, session, csrf, application, *,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='business_license',
            expected_application_revision=expected_application_revision,expected_wechat_version=expected_wechat_version,
            confirmed_fields=confirmed_fields,source_check=source_check)

    def fill_confirmed_identity_draft(self, session, csrf, application, *,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='id_front',
            expected_application_revision=expected_application_revision,expected_wechat_version=expected_wechat_version,
            confirmed_fields=confirmed_fields,source_check=source_check)

    def fill_confirmed_identity_back_draft(self, session, csrf, application, *,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='id_back',
            expected_application_revision=expected_application_revision,expected_wechat_version=expected_wechat_version,
            confirmed_fields=confirmed_fields,source_check=source_check)

    def fill_confirmed_bank_card_draft(self, session, csrf, application, **kwargs):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='bank_card',**kwargs)

    def _fill_confirmed_document_draft(self, session, csrf, application, *,document_type,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None, recovery_receipt=None, recovery_replay_check=None):
        """Host-only empty-field fill, original Center transaction + two CAS.

        Caller must supply both versions from an independently bound human
        confirmation snapshot. The protected bridge can supply a source_check
        that revalidates the persisted confirmation and original attachment
        inside this transaction. No HTTP writeback entry or OCR grant exists.
        """
        from scripts import community_onboarding_offline as workflow
        from scripts.pr122_customer_core import safe_text
        c=self.center
        if source_check is not None and not callable(source_check):raise ValueError('HOST_SOURCE_CHECK_REQUIRED')
        if self.onboarding.center is not c or self.onboarding.wechat_applyment is not self:
            raise PermissionError('ORIGINAL_SHARED_DRAFT_REQUIRED')
        if c.db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        if (type(expected_application_revision) is not int or expected_application_revision<1
                or type(expected_wechat_version) is not int or expected_wechat_version<0):
            raise ValueError('EXPLICIT_DUAL_VERSIONS_REQUIRED')
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        if document_type not in ('business_license','id_front','id_back','bank_card'):raise ValueError('CONFIRMED_DOCUMENT_TYPE_REQUIRED')
        allowed={'business_license':{'company_name','registered_address'},'id_front':{'id_name','id_number','registered_address'},'id_back':{'valid_from','valid_to'},'bank_card':{'account_number','account_bank'}}[document_type]
        if recovery_receipt is not None and document_type=='business_license':
            allowed=allowed|{'credit_code','legal_representative'}
        if (type(confirmed_fields) is not dict or not confirmed_fields
                or not set(confirmed_fields)<=allowed):
            raise ValueError('CONFIRMED_LICENSE_FIELDS_ONLY')
        for value in confirmed_fields.values():
            if type(value) is not str or not value.strip():raise ValueError('CONFIRMED_LICENSE_STRING_REQUIRED')
            safe_text(value,512)
        if recovery_receipt is not None:
            if (type(recovery_receipt) is not dict or set(recovery_receipt)!={'id','payload_hash'}
                    or any(type(v) is not str or not re.fullmatch('[a-f0-9]{64}',v) for v in recovery_receipt.values())
                    or not callable(recovery_replay_check)):
                raise ValueError('OCR_RECOVERY_RECEIPT_INVALID')
        def retain_receipt(owner, outcome):
            if recovery_receipt is not None:
                key=recovery_receipt['id']
                payload=dict(payload_hash=recovery_receipt['payload_hash'],outcome=outcome)
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_OCR_RECOVERY_WRITEBACK',?,?,?,?,1)",
                    (key,owner,application,c.encrypt(canonical(payload),'ocr-recovery-writeback:'+key)))
            return outcome
        with c.tx():  # Original BEGIN IMMEDIATE; owns both writes and audit.
            uid=c.session(session,csrf)
            owner,meta,platform=self.onboarding._load(application,uid)
            def provider():
                row=c.db.execute("SELECT user_id,active FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND project=?",(application,application)).fetchone()
                if row is not None and (row['user_id']!=owner or row['active']!=1):
                    raise PermissionError('SHARED_DRAFT_OWNER_REVOKED')
                return self._read(application)
            record=provider();version=record['version'] if record is not None else 0
            if type(version) is not int or version<(1 if record is not None else 0):raise ValueError('PROVIDER_VERSION_INVALID')
            if recovery_receipt is not None:
                key=recovery_receipt['id']
                prior=c.db.execute("SELECT user_id,active,payload FROM links WHERE channel='COMMUNITY_OCR_RECOVERY_WRITEBACK' AND subject_idx=? AND project=?",(key,application)).fetchone()
                if prior is not None:
                    if prior['user_id']!=owner or prior['active']!=1:raise PermissionError('OCR_RECOVERY_RECEIPT_OWNER_CHANGED')
                    saved=json.loads(c.decrypt(prior['payload'],'ocr-recovery-writeback:'+key))
                    if saved.get('payload_hash')!=recovery_receipt['payload_hash']:raise ValueError('OCR_RECOVERY_IDEMPOTENCY_CONFLICT')
                    outcome=saved['outcome']
                    if (platform['revision']!=outcome['application_revision'] or version!=outcome['wechat_version']
                            or platform['status'] not in ('DRAFT','CORRECTION_REQUIRED')
                            or record is not None and record.get('state') not in ('DRAFT','CORRECTION')):
                        raise ValueError('SHARED_DRAFT_DUAL_VERSION_CONFLICT')
                    recovery_replay_check(platform['revision'],version)
                    return outcome
            if platform['revision']!=expected_application_revision or version!=expected_wechat_version:
                raise ValueError('SHARED_DRAFT_DUAL_VERSION_CONFLICT')
            if (platform['status'] not in ('DRAFT','CORRECTION_REQUIRED')
                    or record is not None and record.get('state') not in ('DRAFT','CORRECTION')):
                raise PermissionError('SHARED_DRAFT_EDIT_STATE_DENIED')
            fields=dict(platform['fields'])
            if any(type(fields.get(k)) is not str for k in ('legal_name','address')):
                raise ValueError('ORIGINAL_PROFILE_FIELDS_REQUIRED')
            result=json.loads(json.dumps(record)) if record is not None else dict(provider_state='NOT_SUBMITTED',profile={})
            profile=result.get('profile')
            if type(profile) is not dict:raise ValueError('SHARED_LICENSE_PROFILE_INVALID')
            subject=profile.get('subject_info',{})
            if type(subject) is not dict:raise ValueError('SHARED_LICENSE_PROFILE_INVALID')
            applied=[];skipped=[]
            if document_type=='business_license':
                license_info=subject.get('business_license_info',{})
                if type(license_info) is not dict or type(license_info.get('merchant_name','')) is not str:
                    raise ValueError('SHARED_LICENSE_PROFILE_INVALID')
                name=confirmed_fields.get('company_name');existing=license_info.get('merchant_name','')
                if name is not None:
                    # Provider names project into platform views. A different manual
                    # value on either side prevents filling the other side with a
                    # conflicting suggestion (even without changing its raw column).
                    if any((value.strip() if recovery_receipt is not None else value) and value!=name for value in (fields['legal_name'],existing)):
                        skipped.append('company_name')
                    else:
                        changed=False
                        if not (fields['legal_name'].strip() if recovery_receipt is not None else fields['legal_name']):fields['legal_name']=name;changed=True
                        if not (existing.strip() if recovery_receipt is not None else existing):
                            profile.setdefault('subject_info',{}).setdefault('business_license_info',{})['merchant_name']=name
                            changed=True
                        if changed:applied.append('company_name')
                if recovery_receipt is not None:
                    for key,target in (('credit_code','license_number'),('legal_representative','legal_person')):
                        if key not in confirmed_fields:continue
                        existing=license_info.get(target,'')
                        if type(existing) is not str:raise ValueError('SHARED_LICENSE_PROFILE_INVALID')
                        if existing.strip():skipped.append(key)
                        else:
                            profile.setdefault('subject_info',{}).setdefault('business_license_info',{})[target]=confirmed_fields[key]
                            applied.append(key)
                address=confirmed_fields.get('registered_address')
                if address is not None:
                    if recovery_receipt is not None:
                        existing=license_info.get('license_address','')
                        if type(existing) is not str:raise ValueError('SHARED_LICENSE_PROFILE_INVALID')
                        if any(v.strip() and v!=address for v in (fields['address'],existing)):
                            skipped.append('registered_address')
                        else:
                            changed=False
                            if not fields['address'].strip():fields['address']=address;changed=True
                            if not existing.strip():
                                profile.setdefault('subject_info',{}).setdefault('business_license_info',{})['license_address']=address;changed=True
                            if changed:applied.append('registered_address')
                    elif fields['address']:skipped.append('registered_address')
                    else:fields['address']=address;applied.append('registered_address')
            elif document_type=='bank_card':
                bank=profile.get('bank_account_info',{})
                if type(bank) is not dict:raise ValueError('ORIGINAL_BANK_PROFILE_REQUIRED')
                # Only human-confirmed printed fields; never infer ownership,
                # account type, branch, or bank verification from OCR.
                for key in ('account_number','account_bank'):
                    if key not in confirmed_fields:continue
                    existing=bank.get(key,'')
                    if type(existing) is not str:raise ValueError('ORIGINAL_BANK_PROFILE_REQUIRED')
                    if existing.strip():skipped.append(key)
                    else:bank[key]=confirmed_fields[key];applied.append(key)
                if applied:profile['bank_account_info']=bank
            else:
                # Identity type belongs to the applicant's original provider
                # draft. Never silently switch a passport/other document to ID.
                identity=subject.get('identity_info')
                if type(identity) is not dict or identity.get('id_doc_type')!='IDENTIFICATION_TYPE_IDCARD':
                    raise ValueError('ORIGINAL_IDCARD_TYPE_SELECTION_REQUIRED')
                card=identity.get('id_card_info',{})
                if type(card) is not dict:raise ValueError('ORIGINAL_IDCARD_PROFILE_REQUIRED')
                mapping=({'id_name':'id_card_name','id_number':'id_card_number','registered_address':'id_card_address'}
                         if document_type=='id_front' else {'valid_from':'card_period_begin','valid_to':'card_period_end'})
                for key,target in mapping.items():
                    if key not in confirmed_fields:continue
                    existing=card.get(target,'')
                    if type(existing) is not str:raise ValueError('ORIGINAL_IDCARD_PROFILE_REQUIRED')
                    if (existing.strip() if recovery_receipt is not None else existing):skipped.append(key)
                    else:card[target]=confirmed_fields[key];applied.append(key)
                if applied:identity['id_card_info']=card
            if not applied:
                if source_check is not None:source_check(platform['revision'],version)
                return retain_receipt(owner,dict(written=False,application_revision=platform['revision'],wechat_version=version,applied=[],skipped=skipped))
            if len(canonical(profile))>100000:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
            # Recheck after decoding/validation and immediately before first write.
            if (c.session(session,csrf)!=uid or self.onboarding._load(application,uid)[2]!=platform
                    or provider()!=record):raise PermissionError('SHARED_DRAFT_SOURCE_CHANGED')
            if source_check is not None:source_check(platform['revision'],version)
            revision=workflow.save_draft(c.db,owner,application,uid,fields,expected_application_revision,
                encode=lambda value:self.onboarding._encode(value,'onboarding-fields:'+application),manage_transaction=False)
            meta['reviews']={};self.onboarding._meta(application,owner,meta)
            if c.session(session,csrf)!=uid or provider()!=record:
                raise PermissionError('SHARED_DRAFT_SOURCE_CHANGED')
            result.update(version=version+1,state='DRAFT')
            self._save(application,owner,result)
            c.audit(application,uid,'SHARED_LICENSE_CONFIRMED_FILL' if document_type=='business_license' else 'SHARED_BANK_CARD_CONFIRMED_FILL' if document_type=='bank_card' else 'SHARED_IDCARD_CONFIRMED_FILL',str(revision)+':'+str(result['version']))
            _,latest_meta,latest=self.onboarding._load(application,uid)
            if (c.session(session,csrf)!=uid or latest['revision']!=revision or latest['status']!='DRAFT'
                    or latest['fields']!=fields or latest_meta.get('reviews')!={}
                    or provider()!=result):raise PermissionError('SHARED_DRAFT_SOURCE_CHANGED')
            if source_check is not None:source_check(revision,result['version'])
            return retain_receipt(owner,dict(written=True,application_revision=revision,wechat_version=result['version'],applied=applied,skipped=skipped))

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
        self.cashier_values(profile)
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
    def industry_media_receipts(self, application, meta):
        """Only current, scanned same-application industry slots and signed receipts."""
        from scripts.community_merchant_onboarding import INDUSTRY_MATERIAL_KINDS
        admitted={}
        rows=self.center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND project=? AND active=1",(application,)).fetchall()
        for key,payload in rows:
            value=json.loads(self.center.decrypt(payload,'wechat-media:'+key))
            kind=value.get('kind')
            if kind not in INDUSTRY_MATERIAL_KINDS:continue
            material=meta['materials'].get(kind)
            if not material or material['sha256']!=value.get('sha256') or material['expires_at'] is not None and material['expires_at']<=self.center.now():continue
            expected=hashlib.sha256(canonical([self.reader._mchid,application,kind,material['sha256']])).hexdigest()
            if key!=expected or type(value.get('provider_response_sha256')) is not str or not re.fullmatch('[0-9a-f]{64}',value['provider_response_sha256']):continue
            row=self.center.db.execute('SELECT project,sha,scan FROM objects WHERE id=?',(material['object_id'],)).fetchone()
            if row is None or tuple(row)!=(application,material['sha256'],'CLEAN'):continue
            raw=self.center.decrypt(private_path(self.center.objects/material['object_id']).read_bytes(),'object:'+application+':'+material['object_id'])
            if hashlib.sha256(raw).hexdigest()!=material['sha256']:raise PermissionError('PRIVATE_INDUSTRY_MATERIAL_INTEGRITY')
            media=value.get('media_id')
            if type(media) is not str or not 1<=len(media)<=1024:continue
            if media in admitted and admitted[media]['kind']!=kind:raise PermissionError('AMBIGUOUS_INDUSTRY_MEDIA_BINDING')
            admitted[media]=dict(kind=kind,sha256=material['sha256'],media_id=media)
        return admitted

    def validate_industry_materials(self, profile, application, meta):
        settlement=profile.get('settlement_info',{})
        values=settlement.get('qualifications')
        if values is None:
            if meta['category']=='FOOD':raise ValueError('FOOD_QUALIFICATIONS_REQUIRED_BY_EXISTING_CATEGORY')
            return []
        from scripts.community_applyment_conditions import images
        images(values,'settlement_info.qualifications')  # Original official max 5.
        receipts=self.industry_media_receipts(application,meta)
        if len(set(values))!=len(values) or any(v not in receipts for v in values):raise PermissionError('CURRENT_INDUSTRY_SLOT_RECEIPT_REQUIRED')
        bindings=[receipts[v] for v in values]
        if len({v['kind'] for v in bindings})!=len(bindings):raise PermissionError('DUPLICATE_INDUSTRY_SLOT')
        return bindings

    def industry_review_plan(self, profile, application, meta):
        from scripts.community_industry_rules import validate_selection
        bindings=self.validate_industry_materials(profile,application,meta)
        plan=validate_selection(profile,meta['entity_type'],meta['category'],bindings)
        # Bind applicable subject/category as well as owner profile. A platform
        # workflow-only revision is not a content change.
        plan['profile_sha256']=hashlib.sha256(canonical(dict(profile=profile,entity_type=meta['entity_type'],category=meta['category']))).hexdigest()
        return plan

    def check_industry_review(self, record, application, owner, meta, platform):
        from scripts.community_industry_rules import validate_review_evidence
        plan=self.industry_review_plan(record['profile'],application,meta)
        if plan['requires_explicit_review']:
            reviewer=record.get('reviewer')
            if type(reviewer) is not str or reviewer==owner:
                raise PermissionError('CURRENT_INDEPENDENT_INDUSTRY_REVIEW_REQUIRED')
            # Stored actor is not an authority token. Recheck original protected
            # reviewer/project access; no new role or permission is introduced.
            self.onboarding._load(application,reviewer,True)
            evidence=record.get('industry_review_evidence')
            reviewed_revision=evidence.get('application_revision') if type(evidence) is dict else None
            if type(reviewed_revision) is not int or reviewed_revision>platform['revision'] or reviewed_revision<0:
                raise PermissionError('CURRENT_INDEPENDENT_INDUSTRY_REVIEW_REQUIRED')
            # Approval/status progression may increase the platform revision.
            # Exact rule, subject/category, profile and selected media hashes
            # still must match the independently reviewed content.
            validate_review_evidence(plan,evidence,
                application=application,application_revision=reviewed_revision,
                profile_version=record['version'],owner_id=owner,authorized_reviewer_id=reviewer)
        return plan

    def clear_industry_material(self, application, owner, meta, kind):
        """Called inside original upload transaction; only remove replaced slot."""
        record=self._read(application)
        if record is None:return
        values=record.get('profile',{}).get('settlement_info',{}).get('qualifications')
        if not values:return
        # Retire this slot's prior receipt even when expired; it is not being
        # admitted for new use. Otherwise replacing an expired selected file
        # would strand its old media ID in qualifications forever.
        removed=set();material=meta['materials'].get(kind)
        if material:
            key=hashlib.sha256(canonical([self.reader._mchid,application,kind,material['sha256']])).hexdigest()
            row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND subject_idx=? AND project=? AND active=1",(key,application)).fetchone()
            if row:
                receipt=json.loads(self.center.decrypt(row[0],'wechat-media:'+key))
                if receipt.get('kind')==kind and receipt.get('sha256')==material['sha256']:removed.add(receipt['media_id'])
        if not removed.intersection(values):return
        if record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('INDUSTRY_REVIEW_SNAPSHOT_IMMUTABLE')
        result=json.loads(canonical(record));remaining=[v for v in values if v not in removed]
        if remaining:result['profile']['settlement_info']['qualifications']=remaining
        else:result['profile']['settlement_info'].pop('qualifications',None)
        result['industry_qualification_bindings']=[r for r in result.get('industry_qualification_bindings',[]) if r['kind']!=kind]
        result['version']+=1;result['state']='DRAFT';self._save(application,owner,result)

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
        fields={'wechat_qualifications_select':{'application','expected_version','application_revision','kind','media_id','selected'},'wechat_read':{'application'},'wechat_review_read':{'application'},'wechat_save':{'application','expected_version','profile'},
            'wechat_apply':{'application','expected_version'},'wechat_status':{'application'},'wechat_submit_review':{'application','expected_version'},'wechat_review':{'application','expected_version','decision','opinion'},
            'wechat_media':{'application','kind'},'wechat_cashier_link':{'application','expected_version','media_id'},'wechat_execute':{'application','expected_version'},'wechat_query':{'application'},'wechat_sign_qr':{'application'}}
        allowed=fields.get(op) if type(op) is str else None
        if allowed is None or set(p)!=allowed and not (op=='wechat_review' and set(p)==allowed|{'industry_branch_assessments'}):raise ValueError('INVALID_WECHAT_APPLYMENT_FIELDS')
        applicant_action=op in ('wechat_apply','wechat_status')
        reviewer=op in ('wechat_review_read','wechat_review','wechat_execute','wechat_query','wechat_sign_qr')
        owner,meta,platform=self.onboarding._load(p['application'],uid,reviewer)
        application=p['application']
        if applicant_action:
            if uid!=owner:raise PermissionError('ORIGINAL_APPLICANT_REQUIRED')
            op='wechat_execute' if op=='wechat_apply' else 'wechat_query'
        if platform['status']=='WITHDRAWN' and op not in ('wechat_read','wechat_review_read','wechat_query'):
            raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        with c.tx():c.limit('wechat-applyment:'+uid,20,60)
        if op=='wechat_media':return self.media(uid,owner,application,meta,p['kind'],lambda:c.session(session,csrf))
        record=self._read(application)
        if op=='wechat_sign_qr':
            proof=record.get('provider_sign_url_proof') if type(record) is dict else None
            if (record is None or record.get('provider_state') not in ('APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED')
                    or type(record.get('provider_sign_url')) is not str or type(proof) is not dict
                    or proof.get('applyment_id')!=record.get('applyment_id')
                    or proof.get('signed_at')!=record.get('provider_query_signed_at')
                    or proof.get('signature_sha256')!=record.get('provider_query_signature_sha256')):raise PermissionError('VERIFIED_PROVIDER_SIGN_URL_REQUIRED')
            official_signing_url(record['provider_sign_url'])
            import qrcode
            from qrcode.image.svg import SvgPathImage
            image=qrcode.make(record['provider_sign_url'],image_factory=SvgPathImage,box_size=8,border=4);output=BytesIO();image.save(output)
            svg=output.getvalue();return dict(application=application,applyment_id=record.get('applyment_id'),url_sha256=hashlib.sha256(record['provider_sign_url'].encode()).hexdigest(),svg_data='data:image/svg+xml;base64,'+base64.b64encode(svg).decode())
        if op in ('wechat_read','wechat_review_read'):
            result=json.loads(canonical(record or dict(version=0,state='DRAFT',provider_state='NOT_SUBMITTED')))
            if op=='wechat_review_read':
                try:
                    plan=self.industry_review_plan((record or {}).get('profile',{}),application,meta)
                    result['industry_review']=dict(status='READY',plan=plan,application_revision=platform['revision'])
                except (ValueError,PermissionError):
                    # Incomplete drafts remain readable; never invent a valid plan.
                    result['industry_review']=dict(status='INCOMPLETE',error_code='INDUSTRY_SELECTION_OR_CURRENT_MATERIALS_INCOMPLETE',application_revision=platform['revision'])
            return result
        if op=='wechat_query':
            if record is None or not record.get('business_code'):raise ValueError('PROVIDER_APPLICATION_NOT_SUBMITTED')
            merchant=self._provider_domain(record)
            data,digest,verified=request(self.reader,'GET','/v3/applyment4sub/applyment/business_code/'+record['business_code'],include_verification=True)
            verified=signed_response_context(verified)
            if data.get('business_code')!=record['business_code'] or type(data.get('applyment_state')) is not str:raise ValueError('PROVIDER_APPLYMENT_BINDING_MISMATCH')
            applyment_id=provider_applyment_id(data)
            recovered_initial=(applicant_action and record['state']=='SUBMISSION_UNKNOWN'
                and not record.get('replacement_submission',False) and record.get('applyment_id') is None)
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
                _,_,live_platform=self.onboarding._load(application,uid,reviewer)
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
                if recovered_generation or recovered_initial:
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
                current.pop('provider_sign_url',None)
                current.pop('provider_sign_url_proof',None)
                if data.get('sign_url') is not None and data['applyment_state'] not in ('APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED'):
                    current['provider_sign_url']=official_signing_url(data['sign_url'])
                    current['provider_sign_url_proof']=dict(applyment_id=applyment_id,**verified)
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
                if (current.get('applicant_direct_submission') and current['state']=='CORRECTION'
                        and live_platform['status'] in ('SUBMITTED','IN_REVIEW')):
                    from scripts import community_onboarding_offline as workflow
                    revision=live_platform['revision']+1
                    c.db.execute("UPDATE onboarding SET status='CORRECTION_REQUIRED',revision=? WHERE tenant=? AND application=?",(revision,owner,application))
                    workflow._append(c.db,owner,application,revision,uid,'WECHAT_OFFICIAL_CORRECTION',{'response_sha256':digest})
                self._check_response_owner(application,record['business_code'],merchant,applyment_id,verified)
                current['provider_sp_mchid']=merchant
                self._save(application,owner,current);c.audit(application,uid,'WECHAT_APPLYMENT_QUERIED',digest)
            return current
        version=record['version'] if record else 0
        if type(p['expected_version']) is not int or p['expected_version']!=version:raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
        if op=='wechat_execute':
            if not self.enabled:raise PermissionError('REAL_MERCHANT_SUBMISSION_GATE_CLOSED')
            if applicant_action:
                from scripts.community_merchant_onboarding import require_confirmed_declarations
                require_confirmed_declarations(meta,(record or {}).get('profile'))
                if record is None or record['state'] not in ('DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED'):raise PermissionError('QUERY_EXISTING_APPLICATION_ONLY')
            elif record is None or record['state']!='INTERNAL_APPROVED' or platform['status']!='APPROVED':raise PermissionError('SEPARATE_INTERNAL_AND_PLATFORM_APPROVAL_REQUIRED')
            merchant=self._provider_domain(record,submission=True)
            self.onboarding._check_materials(application,meta)
            self._validate(record['profile'],meta['entity_type'])
            if record['profile']['subject_info']['identity_info']['id_doc_type']!=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'):raise ValueError('PLATFORM_IDENTITY_TYPE_MISMATCH')
            if meta['category']=='FOOD' and not record['profile']['settlement_info'].get('qualifications'):raise ValueError('FOOD_QUALIFICATIONS_REQUIRED_BY_EXISTING_CATEGORY')
            if applicant_action:self.industry_review_plan(record['profile'],application,meta)
            else:self.check_industry_review(record,application,owner,meta,platform)
            self._validate_media(record['profile'],application,meta)
            if applicant_action and platform['status'] in ('DRAFT','CORRECTION_REQUIRED'):
                # Freeze this submitted snapshot through the original owner action.
                # This is not platform approval and grants no operational access.
                self.onboarding.dispatch(session,csrf,{'operation':'submit','params':{'application':application,'revision':platform['revision']}})
                owner,meta,platform=self.onboarding._load(application,uid)
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
                current_owner,current_meta,current_platform=self.onboarding._load(application,uid,reviewer)
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
                if applicant_action:current['applicant_direct_submission']=True
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
                self.onboarding._load(application,uid,reviewer)
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
            if op in ('wechat_review','wechat_submit_review') and self.onboarding._load(application,uid,reviewer)!=(owner,meta,platform):raise ValueError('WECHAT_APPLYMENT_CHANGED')
            if op=='wechat_qualifications_select':
                from scripts.community_merchant_onboarding import INDUSTRY_MATERIAL_KINDS
                _,meta,current_platform=self.onboarding._load(application,uid)
                if uid!=owner or current_platform['status'] not in ('DRAFT','CORRECTION_REQUIRED') or record is None or record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('OWNER_INDUSTRY_DRAFT_REQUIRED')
                if type(p['application_revision']) is not int or p['application_revision']!=current_platform['revision']:raise ValueError('INDUSTRY_APPLICATION_REVISION_CONFLICT')
                if type(p['kind']) is not str or p['kind'] not in INDUSTRY_MATERIAL_KINDS or type(p['selected']) is not bool:raise ValueError('INVALID_INDUSTRY_SELECTION')
                receipts=self.industry_media_receipts(application,meta)
                values=record.get('profile',{}).get('settlement_info',{}).get('qualifications',[])
                if type(values) is not list:raise PermissionError('CURRENT_INDUSTRY_SLOT_RECEIPT_REQUIRED')
                # Removing a known retained slot is not admitting expired media.
                # Bind the removal to the protected server record, never client SHA.
                if not p['selected']:
                    if p['media_id'] is not None:raise ValueError('DESELECT_WITHOUT_MEDIA_REQUIRED')
                    removed={b['media_id'] for b in record.get('industry_qualification_bindings',[])
                             if b.get('kind')==p['kind']}
                    if 'industry_qualification_bindings' not in record:
                        # Legacy single-slot profiles predate persisted bindings.
                        # A protected historical receipt may prove removal only;
                        # it is never added to the current admission set.
                        material=meta['materials'].get(p['kind'])
                        if material:
                            key=hashlib.sha256(canonical([self.reader._mchid,application,p['kind'],material['sha256']])).hexdigest()
                            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND subject_idx=? AND project=?",(key,application)).fetchone()
                            if row:
                                historical=json.loads(c.decrypt(row[0],'wechat-media:'+key))
                                media=historical.get('media_id')
                                if (historical.get('kind')==p['kind'] and historical.get('sha256')==material['sha256']
                                        and type(media) is str and media in values
                                        and type(historical.get('provider_response_sha256')) is str
                                        and re.fullmatch('[0-9a-f]{64}',historical['provider_response_sha256'])):
                                    removed.add(media)
                    values=[v for v in values if v not in removed]
                available=receipts
                if not p['selected']:
                    # Retain other known (possibly expired) selections without
                    # certifying them. They must still pass review/execute checks.
                    retained={b['media_id']:b for b in record.get('industry_qualification_bindings',[])
                              if b.get('kind') in INDUSTRY_MATERIAL_KINDS}
                    available=dict(retained,**receipts)
                if any(v not in available for v in values):raise PermissionError('CURRENT_INDUSTRY_SLOT_RECEIPT_REQUIRED')
                chosen={available[v]['kind']:available[v] for v in values}
                if p['selected']:
                    if type(p['media_id']) is not str:raise ValueError('INVALID_INDUSTRY_MEDIA_ID')
                    receipt=receipts.get(p['media_id'])
                    if receipt is None or receipt['kind']!=p['kind']:raise PermissionError('EXACT_INDUSTRY_SLOT_RECEIPT_REQUIRED')
                    chosen[p['kind']]=receipt
                else:
                    if p['media_id'] is not None:raise ValueError('DESELECT_WITHOUT_MEDIA_REQUIRED')
                    chosen.pop(p['kind'],None)
                bindings=[chosen[k] for k in INDUSTRY_MATERIAL_KINDS if k in chosen]
                result=json.loads(canonical(record));settlement=result['profile'].setdefault('settlement_info',{})
                if bindings:settlement['qualifications']=[v['media_id'] for v in bindings]
                else:settlement.pop('qualifications',None)
                result.update(industry_qualification_bindings=bindings,version=version+1,state='DRAFT')
            elif op=='wechat_cashier_link':
                if platform['status'] not in ('DRAFT','CORRECTION_REQUIRED') or record is None or record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('CASHIER_DRAFT_REQUIRED')
                material=meta['materials'].get('cashier_photo')
                media=p['media_id']
                if (type(media) is not str or not media or not material
                        or material['expires_at'] is not None and material['expires_at']<=c.now()
                        or media not in self.cashier_media_ids(application,material['sha256'])):
                    raise PermissionError('CURRENT_CASHIER_MEDIA_REQUIRED')
                result=json.loads(json.dumps(record))
                values=self.cashier_values(result['profile'])
                previous=result.get('cashier_media_id')
                self.check_cashier_binding(application,values,previous)
                if previous:values.remove(previous)
                if media in values:raise ValueError('CASHIER_MEDIA_BINDING_UNKNOWN')
                if len(values)>=5:raise ValueError('BUSINESS_ADDITION_PICS_LIMIT')
                values.append(media)
                result['profile'].setdefault('addition_info',{})['business_addition_pics']=values
                result.update(cashier_media_id=media,version=version+1,state='DRAFT')
            elif op=='wechat_save':
                if record and record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('PAYMENT_APPLICATION_EDIT_DENIED')
                if type(p['profile']) is not dict or len(canonical(p['profile']))>100000:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
                values=self.cashier_values(p['profile'])
                self.check_cashier_binding(application,values,(record or {}).get('cashier_media_id'))
                from scripts.community_merchant_onboarding import profile_scenes
                profile_scenes(p['profile'])  # Validate any declared scenes before storing this draft.
                from scripts.community_merchant_onboarding import shared_application_fields
                shared=shared_application_fields(p['profile'],platform['fields'])
                # Preserve submitted/approved historical review snapshots. Current
                # platform views project this same original provider draft.
                if shared!=platform['fields'] and platform['status'] in ('DRAFT','CORRECTION_REQUIRED'):
                    from scripts import community_onboarding_offline as workflow
                    workflow.save_draft(c.db,owner,application,uid,dict(shared,license_ref='PRIVATE_ONBOARDING_MATERIALS'),platform['revision'],
                        encode=lambda value:self.onboarding._encode(value,'onboarding-fields:'+application),manage_transaction=False)
                result=dict(record or {},version=version+1,state='DRAFT',profile=p['profile'])
                if not record:result['provider_state']='NOT_SUBMITTED'
            elif op=='wechat_submit_review':
                from scripts.community_merchant_onboarding import require_confirmed_declarations
                require_confirmed_declarations(meta,(record or {}).get('profile'))
                if record is None or record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('PAYMENT_DRAFT_REQUIRED')
                self._validate(record['profile'],meta['entity_type'])
                self.industry_review_plan(record['profile'],application,meta)
                if record['profile']['subject_info']['identity_info']['id_doc_type']!=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'):raise ValueError('PLATFORM_IDENTITY_TYPE_MISMATCH')
                result=dict(record,version=version+1,state='PENDING_INTERNAL_REVIEW')
            else:
                if uid==owner or record is None or record['state']!='PENDING_INTERNAL_REVIEW' or p['decision'] not in ('INTERNAL_APPROVED','CORRECTION') or type(p['opinion']) is not str or not 1<=len(p['opinion'])<=1000:raise PermissionError('INDEPENDENT_PAYMENT_APPLICATION_REVIEW_REQUIRED')
                result=dict(record,version=version+1,state=p['decision'],opinion=p['opinion'],reviewer=uid)
                result.pop('industry_review_evidence',None)
                if p['decision']=='INTERNAL_APPROVED':
                    from scripts.community_industry_rules import validate_review_evidence
                    plan=self.industry_review_plan(record['profile'],application,meta)
                    if plan['requires_explicit_review']:
                        evidence=dict(application=application,application_revision=platform['revision'],
                            profile_version=result['version'],reviewer_id=uid,decision='CONDITIONS_CONFIRMED',
                            branch_assessments=p.get('industry_branch_assessments'),
                            **{key:plan[key] for key in ('rule_sha256','materials_sha256','profile_sha256')})
                        validate_review_evidence(plan,evidence,application=application,
                            application_revision=platform['revision'],profile_version=result['version'],
                            owner_id=owner,authorized_reviewer_id=uid)
                        result['industry_review_evidence']=evidence

            self._save(application,owner,result);c.audit(application,uid,'WECHAT_'+op.upper(),str(result['version']))
        return result
    @staticmethod
    def cashier_values(profile):
        addition=profile.get('addition_info',{})
        if type(addition) is not dict:raise ValueError('INVALID_ADDITION_INFO')
        values=addition.get('business_addition_pics',[])
        if (type(values) is not list or len(values)>5
                or any(type(v) is not str or not 1<=len(v)<=1024 for v in values)
                or len(set(values))!=len(values)):
            raise ValueError('INVALID_BUSINESS_ADDITION_PICS')
        return list(values)
    def cashier_media_ids(self,application,sha=None):
        values=set();c=self.center
        for key,payload in c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND project=? AND active=1",(application,)):
            value=json.loads(c.decrypt(payload,'wechat-media:'+key))
            if value.get('kind')=='cashier_photo' and (sha is None or value.get('sha256')==sha):values.add(value['media_id'])
        return values
    def check_cashier_binding(self,application,values,previous):
        # Unknown legacy entries are retained; known cashier entries may only
        # be changed via the managed operation, never a wholesale profile save.
        if (previous is not None and (type(previous) is not str or values.count(previous)!=1)
                or set(values)&self.cashier_media_ids(application)-({previous} if previous else set())):
            raise ValueError('CASHIER_MEDIA_BINDING_UNKNOWN')
    def clear_cashier_media(self,application,owner):
        c=self.center
        if not c.db.in_transaction:raise ValueError('ORIGINAL_ONBOARDING_TRANSACTION_REQUIRED')
        record=self._read(application)
        if record is None:return
        if record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('CASHIER_DRAFT_REQUIRED')
        result=json.loads(json.dumps(record));values=self.cashier_values(result.get('profile',{}))
        previous=result.get('cashier_media_id');self.check_cashier_binding(application,values,previous)
        if previous:
            values.remove(previous)
            if values:result['profile']['addition_info']['business_addition_pics']=values
            else:result['profile']['addition_info'].pop('business_addition_pics',None)
            result.pop('cashier_media_id');result['version']+=1
            self._save(application,owner,result)
            c.audit(application,owner,'WECHAT_CASHIER_UNLINKED',str(result['version']))
    def media(self,uid,owner,application,meta,kind,reauthorize):
        if kind=='bank_card':raise PermissionError('BANK_CARD_PRIVATE_PREVIEW_ONLY')
        if not self.enabled:raise WechatMediaUnavailable('REAL_MERCHANT_MEDIA_UPLOAD_GATE_CLOSED')
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
        _,fresh_meta,fresh_platform=self.onboarding._load(application,uid)
        if fresh_platform['status']=='WITHDRAWN':raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        if fresh_meta['materials'].get(kind)!=material:raise ValueError('ORIGINAL_PRIVATE_MATERIAL_CHANGED')
        key=hashlib.sha256(canonical([self.reader._mchid,application,kind,material['sha256']])).hexdigest()
        # The source/session checks above apply to reuse as well as first transmission.
        with c.tx():
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND subject_idx=? AND user_id=? AND project=? AND active=1",(key,owner,application)).fetchone()
            if row is not None:
                receipt=json.loads(c.decrypt(row['payload'],'wechat-media:'+key))
                if (receipt.get('kind')!=kind or receipt.get('sha256')!=material['sha256']
                        or type(receipt.get('media_id')) is not str or not 1<=len(receipt['media_id'])<=1024):
                    raise ValueError('INVALID_SAVED_PROVIDER_MEDIA_RECEIPT')
                return dict(media_id=receipt['media_id'],kind=kind,source_sha256=material['sha256'])
            if c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_MEDIA_ATTEMPT' AND event_id=?",(key,)).fetchone():
                raise WechatMediaPending('WECHAT_MEDIA_RESULT_UNKNOWN')
            c.db.execute("INSERT INTO events VALUES('WECHAT_MEDIA_ATTEMPT',?,?)",(key,c.now()))
            c.audit(application,uid,'WECHAT_MEDIA_UPLOAD_ATTEMPT',key)
        try:
            data,digest=request(self.reader,'POST','/v3/merchant/media/upload',raw=body,content_type='multipart/form-data; boundary='+boundary,signing_body=metadata)
            if type(data.get('media_id')) is not str or not 1<=len(data['media_id'])<=1024:raise ValueError('INVALID_PROVIDER_MEDIA_ID')
        except Exception as error:
            raise WechatMediaPending('WECHAT_MEDIA_RESULT_UNKNOWN') from error
        # Persist an authentic response even if identity/source changes during the request.
        # A later call must still pass current source/session checks before reuse.
        with c.tx():
            c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_WECHAT_MEDIA',?,?,?,?,1)",(key,owner,application,c.encrypt(canonical(dict(media_id=data['media_id'],kind=kind,sha256=material['sha256'],provider_response_sha256=digest)),'wechat-media:'+key)))
            c.audit(application,uid,'WECHAT_MEDIA_UPLOADED',key)
        if reauthorize()!=uid:raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
        _,current_meta,current_platform=self.onboarding._load(application,uid)
        if current_meta['materials'].get(kind)!=material:raise ValueError('ORIGINAL_PRIVATE_MATERIAL_CHANGED')
        return dict(media_id=data['media_id'],kind=kind,source_sha256=material['sha256'])
