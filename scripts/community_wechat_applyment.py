"""Private official submerchant application drafts, media and signed submission.

Official schemas: partner/4012719997, 4012697168, 4012760490.
Internal approval and provider acceptance are independent states. Host must
explicitly admit real submissions; no payment merchant binding is auto-created.
"""
import base64
from scripts import community_submission_diagnostic as submission_diagnostic
import hashlib
import json
import re
import secrets
import syslog
import threading

# Serialize current same-material sends, not historical attempts.
_MINI_ACTIVE_MEDIA_LOCKS=tuple(threading.Lock() for _ in range(64))
from io import BytesIO
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.pr122_customer_core import canonical,private_path
from scripts.community_provider_transport import request

def provider_submission_profile(profile):
    # Only the outgoing copy is projected. Stored history and other scene data
    # remain intact, and every selected scene retains its original fields.
    result=json.loads(canonical(profile))
    sales=result.get('business_info',{}).get('sales_info',{})
    scenes=sales.get('sales_scenes_type',[])
    if 'SALES_SCENES_MINI_PROGRAM' not in scenes:sales.pop('mini_program_info',None)
    if 'SALES_SCENES_STORE' not in scenes:sales.pop('biz_store_info',None)
    # Official enum spelling, not a change of industry, rate or saved profile.
    # The existing catalog extracted spaces around HTML-separated slash tokens.
    # Exact legacy tuple only; no blanket whitespace normalization.
    settlement=result.get('settlement_info',{})
    if (result.get('subject_info',{}).get('subject_type')=='SUBJECT_TYPE_INDIVIDUAL'
            and settlement.get('settlement_id')=='746'
            and settlement.get('qualification_type')=='门户论坛 / 网络广告及推广 / 软件开发 / 其他互联网服务'):
        settlement['qualification_type']='门户论坛/网络广告及推广/软件开发/其他互联网服务'
    # Signed personal-bank catalog: canonical account_bank; saved details stay intact.
    bank=result.get('bank_account_info',{})
    if bank.get('bank_account_type')=='BANK_ACCOUNT_TYPE_PERSONAL' and bank.get('account_bank')=='中国邮政储蓄银行':
        bank['account_bank']='邮政储蓄银行'
    # Verified personal-bank catalog says no branch is required for this bank.
    if bank.get('bank_account_type')=='BANK_ACCOUNT_TYPE_PERSONAL' and bank.get('account_bank')=='邮政储蓄银行':
        bank.pop('bank_name',None)
        bank.pop('bank_branch_id',None)
    return result


class WechatMediaUnavailable(PermissionError):
    """Explicitly disabled provider capability, never an authentication result."""


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


def submission_evidence_class(record):
    """Display grouping only, never authorizes or schedules a provider request."""
    if record is None:return 'DRAFT'
    if type(record) is not dict:return 'UNVERIFIED'
    code=record.get('business_code');aid=record.get('applyment_id')
    receipts=record.get('submission_receipts',[])
    if type(receipts)is not list:return 'UNVERIFIED'
    receipts=list(receipts);recovery=record.get('submission_recovery_receipt')
    if recovery is not None:
        if type(recovery)is not dict:return 'UNVERIFIED'
        receipts.append(recovery)
    valid_identity=(type(code)is str and re.fullmatch('[A-Za-z0-9_-]{1,64}',code)
        and type(aid)is str and re.fullmatch('[1-9][0-9]{0,18}',aid) and int(aid)<2**63)
    if (record.get('state')!='SUBMISSION_UNKNOWN' and valid_identity
        and type(record.get('provider_sp_mchid'))is str and bool(record['provider_sp_mchid'])
        and any(type(x)is dict and x.get('business_code')==code and x.get('applyment_id')==aid
            and type(x.get('signed_at'))is int and x['signed_at']>=0 and re.fullmatch('[a-f0-9]{64}',str(x.get('signature_sha256',''))) for x in receipts)):
        return 'SUBMITTED'
    # Only a strict original local draft with zero submission/history traces is
    # hidden by default. Partial/unknown/history evidence stays visible to review.
    trace_keys={'business_code','applyment_id','replacement_submission','consumed_rejections','correction_receipt','parameter_rejection','parameter_rejection_history','explicit_retry_sequence'}
    traced=any((key in trace_keys or key.startswith('submission_') or key.startswith('provider_'))
        and key not in ('provider_state','provider_sync_error','provider_sync_error_at') and value not in (None,'',[],{}) for key,value in record.items())
    if record.get('state')=='DRAFT' and record.get('provider_state') in (None,'NOT_SUBMITTED') and not receipts and not traced:
        return 'DRAFT'
    return 'UNVERIFIED'


def provider_workflow_view(record):
    state=record.get('provider_state','NOT_SUBMITTED') if type(record) is dict else 'NOT_SUBMITTED'
    bucket=provider_workflow(state)
    evidence=submission_evidence_class(record)
    confirmed=record if evidence=='SUBMITTED' else {}
    observed_at=confirmed.get('provider_observed_at')
    observed_at=observed_at if type(observed_at) is int and 0<observed_at<10000000000 else None
    return dict(state=state,bucket=bucket,submission_class=evidence,completed=bucket=='COMPLETED',
                applyment_id=confirmed.get('applyment_id'),observed_at=observed_at,
        sign_action_available=(bucket=='PENDING_CONFIRMATION'
            and type(record) is dict
            and type(record.get('provider_sign_url')) is str
            and type(record.get('provider_sign_url_proof')) is dict),
        sync_error=(record.get('owner_recovery_error') or record.get('provider_sync_error')) if type(record) is dict else None,
        sync_error_at=(record.get('owner_recovery_error_at') if record.get('owner_recovery_error') else record.get('provider_sync_error_at')) if type(record) is dict else None)


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
    # The documented payment URL is an example, not the sole signing route.
    # A verified same-application response also returns the official MP binding
    # link. Keep exact origins, never a suffix/wildcard or arbitrary redirect.
    official_route=(parsed.netloc=='pay.weixin.qq.com'
        and parsed.path=='/public/apply4ec_sign/s') or (
        parsed.netloc=='mp.weixin.qq.com' and parsed.path.startswith('/')
        and not parsed.path.startswith('//'))
    if (parsed.scheme!='https' or not official_route
            or not parsed.query or parsed.fragment):
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
        self.observer=None
    def _read(self,application):
        row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND project=? AND active=1",(application,application)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0],'wechat-applyment:'+application))
    def local_presubmission_editable(self,application,owner,*,local_queue):
        # Read exact original links (including revoked rows): absence presented by
        # _read alone would otherwise treat revoked evidence as never submitted.
        db=self.center.db
        row=db.execute("""SELECT user_id,active FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT'
            AND subject_idx=? AND project=?""",(application,application)).fetchone()
        if row is None:
            if not local_queue:return False
        else:
            if row['user_id']!=owner or row['active']!=1:return False
            record=self._read(application)
            if type(record) is not dict:return False
            state=record.get('state')
            internal=state in ('PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED')
            if not local_queue and not internal:return False
            if state not in ('DRAFT','CORRECTION') and not internal:return False
            if type(record.get('version')) is not int or record['version']<1:return False
            # Internal review stages are local only. Normalize solely to classify
            # submission evidence; no provider row or associated history mutation.
            if (record.get('owner_submit_confirmation') not in (None,{})
                    or submission_evidence_class(dict(record,state='DRAFT'))!='DRAFT'):
                return False
        # Original submit reserves the attempt, provider record and audit in one
        # transaction. Also fail closed on same-application evidence if a
        # previously written provider record is missing or no longer readable.
        if db.execute("""SELECT 1 FROM links WHERE project=? AND
                channel IN ('COMMUNITY_WECHAT_OBSERVATION','COMMUNITY_WECHAT_PROVIDER_ERROR') LIMIT 1""",
                (application,)).fetchone() is not None:return False
        return db.execute("""SELECT 1 FROM audit WHERE project=? AND event IN
            ('WECHAT_APPLYMENT_SUBMISSION_ATTEMPT','WECHAT_APPLYMENT_SUBMITTED','WECHAT_APPLYMENT_QUERIED') LIMIT 1""",
            (application,)).fetchone() is None

    def _save(self,application,owner,record):
        self.center.db.execute("INSERT INTO links VALUES('COMMUNITY_WECHAT_APPLYMENT',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",(application,owner,application,self.center.encrypt(canonical(record),'wechat-applyment:'+application)))
    def _mini_feedback_read(self, record, owner, application, revision):
        if type(record) is not dict or record.get('state')!='CORRECTION' or record.get('applyment_id') or record.get('submission_receipts') or record.get('submission_recovery_receipt'):
            return None
        proof=record.get('owner_submit_confirmation'); mark=record.get('parameter_rejection')
        if type(proof) is not dict or type(mark) is not dict or proof.get('owner')!=owner or proof.get('application')!=application or type(revision) is not int or type(proof.get('platform_revision')) is not int or proof['platform_revision']!=revision:
            return None
        v=mark.get('profile_version'); seq=mark.get('retry_sequence'); token=mark.get('intent_token'); code=mark.get('business_code'); sha=mark.get('response_sha256')
        if type(v) is not int or type(record.get('version')) is not int or record['version']!=v+1 or proof.get('version')!=v or type(seq) is not int or seq!=record.get('explicit_retry_sequence',0) or type(code) is not str or code!=record.get('business_code'):
            return None
        if type(token) is not str or not re.fullmatch('[0-9a-f]{32}', token) or token!=proof.get('intent_token') or token!=record.get('submission_intent_token') or type(sha) is not str or not re.fullmatch('[0-9a-f]{64}',sha):
            return None
        try:
            c=self.center
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_PROVIDER_ERROR' AND subject_idx=? AND user_id=? AND project=? AND active=1", (application,owner,application)).fetchone()
            if row is None:return None
            raw=c.decrypt(row[0],'wechat-provider-error:'+application)
            if len(raw)>32768:return None
            receipt=json.loads(raw)
            if type(receipt) is not dict or any(receipt.get(k)!=mark.get(k) for k in ('business_code','profile_version','retry_sequence','intent_token')):return None
            err=receipt.get('provider_error')
            if type(err) is not dict or err.get('signature_verified') is not True or err.get('http_status')!=400 or err.get('code')!='PARAM_ERROR' or err.get('response_sha256')!=sha:return None
            answer=dict(source='VERIFIED_WECHAT',application=application,application_revision=revision,version=v+1,code='PARAM_ERROR')
            text=err.get('message')
            # Owner-only text. Exclude control characters and embedded data-bearing details.
            if type(text) is str and 0<len(text)<=256 and re.fullmatch(r'[㐀-鿿，。；：！？（）“”、《》　 ]+',text):answer['message']=text
            detail=err.get('detail')
            if type(detail) is dict:
                f=detail.get('field')
                if type(f) is str:
                    f=f.lstrip('/').replace('/','.')
                    if len(f)<=160 and re.fullmatch(r'(contact_info|subject_info|business_info|settlement_info|bank_account_info|addition_info)(\.[a-z][a-z0-9_]*)+', f):answer['field']=f
            return answer
        except Exception:
            return None

    def _retain_verified_provider_error(self,error,application,owner,code,version,*,retry_sequence=None,intent_token=None):
        # Preserve the original exception; only exact-call signed parameter rejection is correctable.
        saved=False
        try:
            detail=submission_diagnostic.take_verified_error_receipt(error)
            if detail is None:return
            diagnostic=submission_diagnostic.snapshot('FAILED') or {}
            receipt=dict(business_code=code,profile_version=version,at=self.center.now(),
                correlation_id=diagnostic.get('correlation_id'),provider_error=detail,
                retry_sequence=retry_sequence,intent_token=intent_token)
            encrypted=self.center.encrypt(canonical(receipt),'wechat-provider-error:'+application)
            with self.center.tx():
                self.center.db.execute("INSERT INTO links VALUES('COMMUNITY_WECHAT_PROVIDER_ERROR',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload",
                    (application,owner,application,encrypted))
                current=self._read(application)
                platform_row=self.center.db.execute('SELECT status,revision FROM onboarding WHERE tenant=? AND application=?',(owner,application)).fetchone()
                if (platform_row and (platform_row[0] in ('SUBMITTED','IN_REVIEW','APPROVED') or (platform_row[0]=='DRAFT' and self._owner_intent_matches(current,application,owner) and type(platform_row[1]) is int and type(current['owner_submit_confirmation'].get('platform_revision')) is int and current['owner_submit_confirmation']['platform_revision']==platform_row[1]))
                        and detail.get('http_status')==400 and detail.get('code')=='PARAM_ERROR'
                        and detail.get('signature_verified') is True
                        and type(intent_token) is str and re.fullmatch('[0-9a-f]{32}',intent_token)
                        and original_submission_intent(current,code,version)
                        and current.get('submission_intent_token')==intent_token
                        and current.get('explicit_retry_sequence',0)==retry_sequence
                        and not current.get('applyment_id') and not current.get('submission_receipts')
                        and not current.get('submission_recovery_receipt')):
                    current.update(state='CORRECTION',version=version+1,
                        parameter_rejection=dict(business_code=code,profile_version=version,
                            retry_sequence=retry_sequence,intent_token=intent_token,
                            response_sha256=detail['response_sha256']))
                    self._save(application,owner,current)
                    self.center.audit(application,owner,'WECHAT_PARAMETER_REJECTED',detail['response_sha256'])
            saved=True
        except Exception:
            pass
        finally:
            cached=getattr(error,'_community_error_diagnostic',None)
            if type(cached) is dict:cached['provider_error_receipt_saved']=saved


    def apply_current_ocr_review(self, session, csrf, application, *, revision, version, docs,
                                 receipt, verify):
        """Owner-only host compound save through the existing Center transaction."""
        from scripts import community_onboarding_offline as workflow
        from scripts.community_ocr_draft import MATERIAL, resolve_confirmed
        from scripts.pr122_customer_core import safe_text
        c=self.center
        if c.db.in_transaction or not callable(verify) or type(receipt) is not tuple or len(receipt)!=2:
            raise ValueError('CURRENT_OCR_REVIEW_INTERNAL_REQUIRED')
        if any(type(k) is not str or not re.fullmatch('[0-9a-f]{64}',k) for k in receipt):
            raise ValueError('CURRENT_OCR_REVIEW_RECEIPT_INVALID')
        if type(revision) is not int or revision<1 or type(version) is not int or version<0:
            raise ValueError('EXPLICIT_DUAL_VERSIONS_REQUIRED')
        paths={
            'business_license':{'company_name':('business_license_info','merchant_name'),
                'credit_code':('business_license_info','license_number'),
                'legal_representative':('business_license_info','legal_person'),
                'registered_address':('business_license_info','license_address')},
            'id_front':{'id_name':('identity_info','id_card_info','id_card_name'),
                'id_number':('identity_info','id_card_info','id_card_number'),
                'registered_address':('identity_info','id_card_info','id_card_address')},
            'id_back':{'valid_from':('identity_info','id_card_info','card_period_begin'),
                       'valid_to':('identity_info','id_card_info','card_period_end'),
                       'issuing_authority':None},
            'bank_card':{'account_number':('bank_account_info','account_number'),'account_bank':('bank_account_info','account_bank')}}
        if type(docs) is not dict or not docs or not set(docs)<=set(paths):
            raise ValueError('CURRENT_OCR_REVIEW_DOCUMENTS_INVALID')
        for kind,fields in docs.items():
            if type(fields) is not dict or not fields or not set(fields)<=set(paths[kind]):
                raise ValueError('CURRENT_OCR_REVIEW_FIELDS_INVALID')
            for value in fields.values():
                if type(value) is not str or not value.strip():raise ValueError('CURRENT_OCR_REVIEW_VALUE_INVALID')
                safe_text(value,512)
        event='SHARED_OCR_CURRENT_REVIEW_SAVED'
        key,checksum=receipt
        with c.tx():
            uid=c.session(session,csrf);owner,meta,platform=self.onboarding._load(application,uid)
            if uid!=owner or self.onboarding.wechat_applyment is not self:
                raise PermissionError('ORIGINAL_SHARED_DRAFT_REQUIRED')
            provider_row=c.db.execute("SELECT user_id,active FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND subject_idx=? AND project=?",(application,application)).fetchone()
            if provider_row is not None and (provider_row['user_id']!=owner or provider_row['active']!=1):
                raise PermissionError('SHARED_DRAFT_OWNER_REVOKED')
            seen=c.db.execute('SELECT object_id FROM audit WHERE project=? AND actor=? AND event=? AND object_id LIKE ?',
                (application,owner,event,key+':%')).fetchall()
            if seen:
                if len(seen)!=1 or seen[0]['object_id']!=key+':'+checksum:raise PermissionError('OCR_REVIEW_IDEMPOTENCY_CONFLICT')
                return {'saved':True}
            record=self._read(application)
            if platform['revision']!=revision or (record['version'] if record is not None else 0)!=version:
                raise PermissionError('SHARED_DRAFT_DUAL_VERSION_CONFLICT')
            local_edit=self.onboarding.local_presubmission_editable(application,owner,platform)
            if not local_edit and (platform['status'] not in ('DRAFT','CORRECTION_REQUIRED') or
                record is not None and record['state'] not in ('DRAFT','CORRECTION')):
                raise PermissionError('SHARED_DRAFT_EDIT_STATE_DENIED')
            verify(meta)
            result=json.loads(json.dumps(record)) if record is not None else {'provider_state':'NOT_SUBMITTED','profile':{}}
            profile=result['profile'];subject=profile.setdefault('subject_info',{})
            if type(subject) is not dict:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
            old_drafts=result.get('ocr_drafts',{});drafts=old_drafts
            # This is not an ordinary full-profile save. Only fields accepted
            # from this OCR review may project, via the original narrow mapping.
            current_fields=dict(platform['fields'])
            platform_ocr_paths={'company_name':'legal_name','registered_address':'address'}
            for kind,fields in docs.items():
                if kind in ('id_front','id_back') and (type(subject.get('identity_info')) is not dict or
                    subject['identity_info'].get('id_doc_type')!='IDENTIFICATION_TYPE_IDCARD'):
                    raise ValueError('ORIGINAL_IDCARD_TYPE_SELECTION_REQUIRED')
                for field,value in fields.items():
                    keys=paths[kind][field]
                    if keys is None:continue
                    current=profile if kind=='bank_card' else subject
                    for part in keys[:-1]:
                        current=current.setdefault(part,{})
                        if type(current) is not dict:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
                    existing=current.get(keys[-1],'')
                    if type(existing) is not str:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
                    if (existing.strip() if kind=='bank_card' else existing):continue
                    platform_key=platform_ocr_paths.get(field) if kind=='business_license' else None
                    original=current_fields.get(platform_key) if platform_key is not None else None
                    if original and original!=value:continue
                    current[keys[-1]]=value
                    if platform_key is not None and not original:
                        current_fields[platform_key]=value
                drafts=resolve_confirmed(drafts,kind,meta['materials'].get(MATERIAL.get(kind,kind),{}),fields)
            # Keep the original Mini legal-contact and store reuse only
            # for a reviewed value, never from conflicting manual evidence.
            identity=docs.get('id_front',{})
            contact=profile.get('contact_info')
            if identity.get('id_name') and type(contact) is dict and contact.get('contact_type')=='LEGAL':
                retained=subject['identity_info'].get('id_card_info',{}).get('id_card_name')
                existing_contact=contact.get('contact_name','')
                if retained==identity['id_name'] and type(existing_contact) is str and not existing_contact.strip():
                    contact['contact_name']=identity['id_name']
            license_fields=docs.get('business_license',{})
            business=profile.get('business_info')
            sales=business.get('sales_info') if type(business) is dict else None
            if license_fields and type(sales) is dict and type(sales.get('sales_scenes_type')) is list and 'SALES_SCENES_STORE' in sales['sales_scenes_type']:
                lic=subject.get('business_license_info',{})
                for field,source,target in (('company_name','merchant_name','biz_store_name'),('registered_address','license_address','biz_store_address')):
                    value=license_fields.get(field)
                    if not value or lic.get(source)!=value:continue
                    store=sales.setdefault('biz_store_info',{})
                    if type(store) is not dict:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
                    existing_store=store.get(target,'')
                    if type(existing_store) is str and not existing_store.strip():store[target]=value
            if 'ocr_drafts' in result or drafts!=old_drafts:result['ocr_drafts']=drafts
            if len(canonical(profile))>100000:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
            if profile==(record or {}).get('profile',{}) and drafts==old_drafts and current_fields==platform['fields']:
                c.audit(application,owner,event,key+':'+checksum)
                return {'saved':True}
            if local_edit:self.onboarding.resume_local_draft_for_write(application,owner,platform,revision)
            if current_fields!=platform['fields']:
                workflow.save_draft(c.db,owner,application,uid,dict(current_fields,license_ref='PRIVATE_ONBOARDING_MATERIALS'),revision,
                    encode=lambda value:self.onboarding._encode(value,'onboarding-fields:'+application),manage_transaction=False)
            if meta.get('reviews'):
                meta['reviews']={};self.onboarding._meta(application,owner,meta)
            result.update(version=version+1,state='DRAFT')
            self._save(application,owner,result)
            c.audit(application,owner,event,key+':'+checksum)
            return {'saved':True}

    def fill_confirmed_license_draft(self, session, csrf, application, *,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None, _mini_applicant=False):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='business_license',
            expected_application_revision=expected_application_revision,expected_wechat_version=expected_wechat_version,
            confirmed_fields=confirmed_fields,source_check=source_check,_mini_applicant=_mini_applicant)

    def fill_confirmed_identity_draft(self, session, csrf, application, *,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None, _mini_applicant=False):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='id_front',
            expected_application_revision=expected_application_revision,expected_wechat_version=expected_wechat_version,
            confirmed_fields=confirmed_fields,source_check=source_check,_mini_applicant=_mini_applicant)

    def fill_confirmed_identity_back_draft(self, session, csrf, application, *,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None, _mini_applicant=False):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='id_back',
            expected_application_revision=expected_application_revision,expected_wechat_version=expected_wechat_version,
            confirmed_fields=confirmed_fields,source_check=source_check,_mini_applicant=_mini_applicant)

    def fill_confirmed_bank_card_draft(self, session, csrf, application, **kwargs):
        return self._fill_confirmed_document_draft(session,csrf,application,document_type='bank_card',**kwargs)

    def _fill_confirmed_document_draft(self, session, csrf, application, *,document_type,
                                     expected_application_revision, expected_wechat_version,
                                     confirmed_fields, source_check=None, _mini_applicant=False):
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
        if (type(confirmed_fields) is not dict or not confirmed_fields
                or not set(confirmed_fields)<=allowed):
            raise ValueError('CONFIRMED_LICENSE_FIELDS_ONLY')
        for value in confirmed_fields.values():
            if type(value) is not str or not value.strip():raise ValueError('CONFIRMED_LICENSE_STRING_REQUIRED')
            safe_text(value,512)
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
            if platform['revision']!=expected_application_revision or version!=expected_wechat_version:
                raise ValueError('SHARED_DRAFT_DUAL_VERSION_CONFLICT')
            local_edit=(_mini_applicant is True and source_check is not None
                and self.onboarding.local_presubmission_editable(application,owner,platform))
            if (not local_edit and (platform['status'] not in ('DRAFT','CORRECTION_REQUIRED')
                    or record is not None and record.get('state') not in ('DRAFT','CORRECTION'))):
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
                    if any(value and value!=name for value in (fields['legal_name'],existing)):
                        skipped.append('company_name')
                    else:
                        changed=False
                        if not fields['legal_name']:fields['legal_name']=name;changed=True
                        if not existing:
                            profile.setdefault('subject_info',{}).setdefault('business_license_info',{})['merchant_name']=name
                            changed=True
                        if changed:applied.append('company_name')
                address=confirmed_fields.get('registered_address')
                if address is not None:
                    if fields['address']:skipped.append('registered_address')
                    else:fields['address']=address;applied.append('registered_address')
            elif document_type=='bank_card':
                bank=profile.get('bank_account_info',{})
                if type(bank) is not dict:raise ValueError('ORIGINAL_BANK_PROFILE_REQUIRED')
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
                    if existing:skipped.append(key)
                    else:card[target]=confirmed_fields[key];applied.append(key)
                if applied:identity['id_card_info']=card
            draft_changed=False
            if 'ocr_drafts' in result:
                from scripts.community_ocr_draft import resolve_confirmed, MATERIAL
                old_drafts=result['ocr_drafts']
                updated=resolve_confirmed(old_drafts,document_type,meta['materials'].get(MATERIAL.get(document_type,document_type),{}),confirmed_fields)
                draft_changed=updated!=old_drafts
                if draft_changed:result['ocr_drafts']=updated
            if not applied and not draft_changed:
                if source_check is not None:source_check(platform['revision'],version)
                return dict(written=False,application_revision=platform['revision'],wechat_version=version,applied=[],skipped=skipped)
            if len(canonical(profile))>100000:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
            # Recheck after decoding/validation and immediately before first write.
            if (c.session(session,csrf)!=uid or self.onboarding._load(application,uid)[2]!=platform
                    or provider()!=record):raise PermissionError('SHARED_DRAFT_SOURCE_CHANGED')
            if source_check is not None:source_check(platform['revision'],version)
            if local_edit:self.onboarding.resume_local_draft_for_write(application,owner,platform,expected_application_revision)
            revision=workflow.save_draft(c.db,owner,application,uid,fields,expected_application_revision,
                encode=lambda value:self.onboarding._encode(value,'onboarding-fields:'+application),manage_transaction=False)
            meta['reviews']={};self.onboarding._meta(application,owner,meta)
            if c.session(session,csrf)!=uid or provider()!=record:
                raise PermissionError('SHARED_DRAFT_SOURCE_CHANGED')
            result.update(version=version+1,state='DRAFT')
            self._save(application,owner,result)
            c.audit(application,uid,'SHARED_LICENSE_CONFIRMED_FILL' if document_type=='business_license' else 'SHARED_IDCARD_CONFIRMED_FILL',str(revision)+':'+str(result['version']))
            _,latest_meta,latest=self.onboarding._load(application,uid)
            if (c.session(session,csrf)!=uid or latest['revision']!=revision or latest['status']!='DRAFT'
                    or latest['fields']!=fields or latest_meta.get('reviews')!={}
                    or provider()!=result):raise PermissionError('SHARED_DRAFT_SOURCE_CHANGED')
            if source_check is not None:source_check(revision,result['version'])
            return dict(written=True,application_revision=revision,wechat_version=result['version'],applied=applied,skipped=skipped)

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
    def _owner_direct_wire_profile(self, profile):
        sections={'contact_info','subject_info','business_info','settlement_info','bank_account_info','addition_info'}
        if type(profile) is not dict or set(profile)-sections or any(type(value) is not dict for value in profile.values()):
            raise ValueError('INVALID_OFFICIAL_PROFILE_TRANSPORT_SHAPE')
        if len(canonical(profile))>100000:
            raise ValueError('APPLYMENT_PROFILE_TOO_LARGE')

        absent=object()
        def clean(value,key=''):
            media=key.endswith(('_copy','_copy_back','_pic','_pics')) or key in ('id_card_national','qualifications','business_authorization_letter','legal_person_commitment','addition_pics','activities_additions','web_authorisation')
            if key in SENSITIVE:
                if value is None or value=='':
                    return absent
                if type(value) is not str:
                    raise ValueError('INVALID_SENSITIVE_OFFICIAL_FIELD')
                return value
            if media and (value is None or value==''):
                return absent
            if type(value) is dict:
                if media:
                    raise PermissionError('CURRENT_ORIGINAL_APPLICATION_MEDIA_REQUIRED')
                return {name:entry for name,v in value.items() if (entry:=clean(v,name)) is not absent}
            if type(value) is list:
                return [entry for item in value if (entry:=clean(item,key)) is not absent]
            if media and type(value) is not str:
                raise PermissionError('CURRENT_ORIGINAL_APPLICATION_MEDIA_REQUIRED')
            return value

        # The original scene projection still owns provider data minimization.
        outgoing=provider_submission_profile(clean(profile))
        self.cashier_values(outgoing)
        return outgoing

    def _validate_media(self,profile,application,meta,*,_owner_direct_integrity=False):
        rows=self.center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND project=? AND active=1",(application,)).fetchall()
        admitted=set()
        by_media_id={}; referenced_kinds=set()
        for key,payload in rows:
            value=json.loads(self.center.decrypt(payload,'wechat-media:'+key))
            current=meta['materials'].get(value['kind'])
            if current and current['sha256']==value['sha256'] and (current['expires_at'] is None or current['expires_at']>self.center.now()):
                admitted.add(value['media_id'])
                if _owner_direct_integrity:by_media_id.setdefault(value['media_id'],set()).add(value['kind'])
        def walk(value,key=''):
            if type(value) is dict:
                for k,v in value.items():walk(v,k)
            elif type(value) is list:
                for v in value:walk(v,key)
            elif type(value) is str and (key.endswith(('_copy','_copy_back','_pic','_pics')) or key in ('id_card_national','qualifications','business_authorization_letter','legal_person_commitment','addition_pics','activities_additions','web_authorisation')):
                if value not in admitted:raise PermissionError('CURRENT_ORIGINAL_APPLICATION_MEDIA_REQUIRED')
                if _owner_direct_integrity:referenced_kinds.update(by_media_id[value])
        walk(profile)
        if _owner_direct_integrity:self.onboarding._check_materials(application,meta,_owner_direct_referenced=referenced_kinds)

    def status_dispatch(self,session,csrf,body,*,expected_project=None):
        # Separate owner-only entry; never invokes administrative route decorator.
        if (type(body)is not dict or set(body)!={'operation','params'}
                or body['operation'] not in ('wechat_status','wechat_owner_sign_qr')
                or type(body['params'])is not dict):
            raise ValueError('EXACT_OWNER_STATUS_REQUEST_REQUIRED')
        args=body['params']; action=body['operation']
        original=(action=='wechat_owner_sign_qr' and set(args)=={'application','qr_format'} and args['qr_format']=='WECHAT_OFFICIAL')
        if not original and set(args)!={'application'}:raise ValueError('EXACT_OWNER_STATUS_REQUEST_REQUIRED')
        if type(csrf)is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        if self.observer is None:raise PermissionError('BOUND_OBSERVER_NOT_CONFIGURED')
        if original:
            return _original_sign_image(self.observer,session,csrf,args['application'],expected_project)
        return self.observer.read(session,csrf,body['params']['application'],body['operation']=='wechat_owner_sign_qr',expected_project=expected_project)

    def display_record(self,application,record):
        result=self.observer.display_record(application,record) if self.observer is not None else record
        # Sealed host restore proof is never an HTTP response or client capability.
        if type(result)is dict and 'restore_provenance' in result:
            result=dict(result);result.pop('restore_provenance')
        return result

    def _commit_provider_query(self,application,owner,record,merchant,result,uid,reauthorize,*,owner_recovery=False,audit_actor=None):
        # Same verified query commit for original reviewer, explicit owner retry,
        # and the original host's narrowly bound automatic owner-intent recovery.
        c=self.center;data,digest,verified=result
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
            if reauthorize()!=uid:raise PermissionError('CURRENT_ORIGINAL_QUERY_OWNER_REQUIRED')
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
            if recovered_generation or (owner_recovery and record['state']=='SUBMISSION_UNKNOWN' and not record.get('replacement_submission',False) and record.get('applyment_id') is None):
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
            self._check_response_owner(application,record['business_code'],merchant,applyment_id,verified)
            current['provider_sp_mchid']=merchant
            current.pop('owner_recovery_error',None);current.pop('owner_recovery_error_at',None)
            self._save(application,owner,current);c.audit(application,audit_actor or uid,'WECHAT_APPLYMENT_QUERIED',digest)
        return current

    @staticmethod
    def _owner_intent_matches(record,application,owner):
        if type(record)is not dict or record.get('state')!='SUBMISSION_UNKNOWN':return False
        proof=record.get('owner_submit_confirmation')
        return (type(proof)is dict and proof.get('owner')==owner and proof.get('application')==application
            and proof.get('version')==record.get('version') and type(proof.get('confirmed_at'))is int
            and type(record.get('submission_intent_token'))is str and bool(record['submission_intent_token'])
            and proof.get('intent_token')==record['submission_intent_token'])

    @staticmethod
    def _draft_reply(record, *, owner_materials=None):
        if type(record) is not dict or 'ocr_drafts' not in record:return record
        output=dict(record)
        drafts=output.pop('ocr_drafts')
        if owner_materials is not None:
            from scripts.community_ocr_draft import current_drafts
            output['ocr_drafts']=current_drafts(drafts,owner_materials)
        return output

    def dispatch(self,session,csrf,body,*,_owner_submit=None,_owner_query=None,_mini_edit=None):
        if type(body) is not dict or set(body)!={'operation','params'} or type(body['params']) is not dict:raise ValueError('INVALID_WECHAT_APPLYMENT_REQUEST')
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf);op,p=body['operation'],body['params']
        fields={'wechat_read':{'application'},'wechat_review_read':{'application'},'wechat_save':{'application','expected_version','profile'},
            'wechat_submit_review':{'application','expected_version'},'wechat_review':{'application','expected_version','decision','opinion'},
            'wechat_media':{'application','kind'},'wechat_media_status':{'application','kind','expected_source_sha256'},'wechat_cashier_link':{'application','expected_version','media_id'},'wechat_execute':{'application','expected_version'},'wechat_query':{'application'},'wechat_sign_qr':{'application'}}
        if _owner_submit is not None and op=='wechat_submit_review':fields['wechat_submit_review']=fields['wechat_submit_review']|{'application_revision'}
        private_fields={'ocr_drafts','application_revision'}
        if (type(op) is not str or op not in fields or (set(p)!=fields[op] and not (op=='wechat_media' and set(p) in ({'application','kind','expected_source_sha256','application_revision','owner_confirmed_material_send'},{'application','kind','application_revision','owner_confirmed_material_send'}) and callable(_mini_edit)))
                and not (op=='wechat_save' and _mini_edit is not None and set(p)==fields[op]|private_fields)):
            raise ValueError('INVALID_WECHAT_APPLYMENT_FIELDS')
        if _owner_submit is not None and (not callable(_owner_submit) or op!='wechat_submit_review'):
            raise PermissionError('EXACT_MINI_OWNER_SUBMISSION_REQUIRED')
        if _owner_query is not None and (not callable(_owner_query) or op!='wechat_query' or _owner_submit is not None):
            raise PermissionError('EXACT_OWNER_RECOVERY_QUERY_REQUIRED')
        if _mini_edit is not None and (not callable(_mini_edit) or op not in ('wechat_save','wechat_cashier_link','wechat_media_status','wechat_read','wechat_media')):
            raise PermissionError('EXACT_MINI_DRAFT_EDIT_REQUIRED')
        reviewer=op in ('wechat_review_read','wechat_review','wechat_execute','wechat_query','wechat_sign_qr') and _owner_query is None
        owner,meta,platform=self.onboarding._load(p['application'],uid,reviewer)
        application=p['application']
        if _owner_submit is not None and (type(p['application_revision']) is not int or p['application_revision']!=platform['revision']):
            raise ValueError('CONFIRMED_APPLICATION_REVISION_CHANGED')
        if platform['status']=='WITHDRAWN' and op not in ('wechat_read','wechat_review_read','wechat_query'):
            raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        with c.tx():c.limit('wechat-applyment:'+uid,20,60)
        if op=='wechat_media_status':
            if not callable(_mini_edit):
                raise PermissionError('EXACT_MINI_OWNER_MEDIA_STATUS_REQUIRED')
            return self._mini_owner_media_status(uid,owner,application,p,_mini_edit)
        if op=='wechat_media':return self.media(uid,owner,application,meta,p['kind'],lambda:c.session(session,csrf),_mini_actor=_mini_edit,_start=p if set(p) in ({'application','kind','expected_source_sha256','application_revision','owner_confirmed_material_send'},{'application','kind','application_revision','owner_confirmed_material_send'}) else None)
        record=self._read(application)
        if op=='wechat_sign_qr':
            record=self.display_record(application,record)
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
            result=self.display_record(application,record) or dict(version=0,state='DRAFT',provider_state='NOT_SUBMITTED')
            if op=='wechat_read' and callable(_mini_edit) and uid==owner and _mini_edit()==uid:
                feedback=self._mini_feedback_read(record,owner,application,platform['revision'])
                if feedback is not None and result.get('version')==feedback['version']:
                    result=dict(result,provider_feedback=feedback)
            return self._draft_reply(result,owner_materials=meta['materials'] if op=='wechat_read' else None)
        if op=='wechat_query':
            if record is None or not record.get('business_code'):raise ValueError('PROVIDER_APPLICATION_NOT_SUBMITTED')
            if _owner_query is not None:
                if _owner_query()!=uid or owner!=uid or not self._owner_intent_matches(record,application,owner):
                    raise PermissionError('ORIGINAL_OWNER_SUBMISSION_INTENT_REQUIRED')
            merchant=self._provider_domain(record)
            data,digest,verified=request(self.reader,'GET','/v3/applyment4sub/applyment/business_code/'+record['business_code'],include_verification=True)
            def authorize_query():
                if c.session(session,csrf)!=uid or (_owner_query is not None and _owner_query()!=uid):raise PermissionError('CURRENT_ORIGINAL_QUERY_OWNER_REQUIRED')
                self.onboarding._load(application,uid,_owner_query is None)
                return uid
            current=self._commit_provider_query(application,owner,record,merchant,(data,digest,verified),uid,authorize_query,owner_recovery=_owner_query is not None)
            return self._draft_reply(current)
        version=record['version'] if record else 0
        if type(p['expected_version']) is not int or p['expected_version']!=version:raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
        if _owner_submit is not None and record is not None and record.get('state')=='SUBMISSION_UNKNOWN':
            return self.dispatch(session,csrf,{'operation':'wechat_query','params':{'application':application}},_owner_query=_owner_submit)
        if op=='wechat_execute' or _owner_submit is not None:
            if not self.enabled:raise PermissionError('REAL_MERCHANT_SUBMISSION_GATE_CLOSED')
            if _owner_submit is None:
                if record is None or record['state']!='INTERNAL_APPROVED' or platform['status']!='APPROVED':raise PermissionError('SEPARATE_INTERNAL_AND_PLATFORM_APPROVAL_REQUIRED')
            else:
                if _owner_submit()!=uid or owner!=uid:raise PermissionError('CURRENT_ORIGINAL_APPLICANT_REQUIRED')
                if record is None or record['state'] not in ('DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED'):
                    raise PermissionError('CURRENT_OWNER_SUBMISSION_VERSION_REQUIRED')
            merchant=self._provider_domain(record,submission=True)
            if _owner_submit is None:
                self.onboarding._check_materials(application,meta)
                self._validate(record['profile'],meta['entity_type'])
                if record['profile']['subject_info']['identity_info']['id_doc_type']!=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'):raise ValueError('PLATFORM_IDENTITY_TYPE_MISMATCH')
                if meta['category']=='FOOD' and not record['profile']['settlement_info'].get('qualifications'):raise ValueError('FOOD_QUALIFICATIONS_REQUIRED_BY_EXISTING_CATEGORY')
                self._validate_media(record['profile'],application,meta)
            else:
                outgoing=self._owner_direct_wire_profile(record['profile'])
                self._validate_media(outgoing,application,meta,_owner_direct_integrity=True)
            code=record.get('business_code') or 'ap'+hashlib.sha256(canonical([merchant,application,version])).hexdigest()[:30]
            correction=record.get('correction_receipt')
            parameter=record.get('parameter_rejection')
            parameter_retry=(type(parameter) is dict and parameter.get('business_code')==code
                and type(parameter.get('profile_version')) is int and parameter['profile_version']<version
                and parameter.get('intent_token')==record.get('submission_intent_token')
                and parameter.get('retry_sequence')==record.get('explicit_retry_sequence',0)
                and not record.get('applyment_id') and not record.get('submission_receipts')
                and not record.get('submission_recovery_receipt'))
            if not parameter_retry and record.get('business_code') and (record.get('provider_state')!='APPLYMENT_STATE_REJECTED'
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
            attempt=code if not (correction or parameter_retry) else code+':revision:'+str(version)
            retry_sequence=record.get('explicit_retry_sequence',0)
            intent_token=secrets.token_hex(16)
            payload=dict(self._encrypt(provider_submission_profile(record['profile']) if _owner_submit is None else outgoing),business_code=code)
            with c.tx():
                if c.session(session,csrf)!=uid or (_owner_submit is not None and _owner_submit()!=uid):raise PermissionError('CURRENT_ORIGINAL_SUBMITTER_REQUIRED')
                current_owner,current_meta,current_platform=self.onboarding._load(application,uid,_owner_submit is None)
                if (current_owner,current_meta,current_platform)!=(owner,meta,platform):raise ValueError('WECHAT_APPLYMENT_CHANGED')
                current=self._read(application)
                if current!=record:raise ValueError('WECHAT_APPLYMENT_CHANGED')
                if c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_APPLYMENT_ATTEMPT' AND event_id=?",(attempt,)).fetchone():raise PermissionError('QUERY_EXISTING_APPLICATION_ONLY')
                c.db.execute("INSERT INTO events VALUES('WECHAT_APPLYMENT_ATTEMPT',?,?)",(attempt,c.now()))
                current.update(state='SUBMISSION_UNKNOWN',business_code=code,submission_intent_token=intent_token,
                    replacement_submission=bool(correction),submission_started_at=c.now(),provider_sp_mchid=merchant)
                if _owner_submit is not None:
                    current['owner_submit_confirmation']=dict(owner=uid,application=application,
                        version=version,platform_revision=platform['revision'],confirmed_at=c.now(),intent_token=intent_token,
                        project=getattr(self.observer,'expected_project',None),
                        account_epoch=c.db.execute('SELECT epoch FROM accounts WHERE id=?',(uid,)).fetchone()[0])
                if correction:
                    current['consumed_rejections']=[*current.get('consumed_rejections',[]),
                        dict(correction,submission_version=version)]
                if parameter_retry:current['parameter_rejection_history']=[*current.get('parameter_rejection_history',[]),parameter]
                current.pop('parameter_rejection',None)
                current.pop('correction_receipt',None);self._save(application,owner,current)
                c.audit(application,uid,'WECHAT_APPLYMENT_SUBMISSION_ATTEMPT',code)
            try:
                data,digest,verified=request(self.reader,'POST','/v3/applyment4sub/applyment/',payload,include_verification=True)
            except Exception as error:
                self._retain_verified_provider_error(error,application,owner,code,version,retry_sequence=retry_sequence,intent_token=intent_token)
                if _owner_submit is not None and not isinstance(error,PermissionError) and self._owner_intent_matches(self._read(application),application,owner):
                    # One bounded read-only recovery, never a second POST. If it
                    # is still unknown, retain the original error and durable intent.
                    try:return self.dispatch(session,csrf,{'operation':'wechat_query','params':{'application':application}},_owner_query=_owner_submit)
                    except Exception:pass
                raise
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
                if c.session(session,csrf)!=uid or (_owner_submit is not None and _owner_submit()!=uid):raise PermissionError('CURRENT_ORIGINAL_SUBMITTER_REQUIRED')
                self.onboarding._load(application,uid,_owner_submit is None)
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
            return self._draft_reply(current)
        with c.tx():
            if c.session(session,csrf)!=uid:raise PermissionError('CURRENT_APPLYMENT_SESSION_REQUIRED')
            latest_platform=self.onboarding._load(application,uid,reviewer)[2]
            if latest_platform['status']=='WITHDRAWN':
                raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
            if self._read(application)!=record:raise ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT')
            local_edit=(_mini_edit is not None and latest_platform==platform
                and self.onboarding.local_presubmission_editable(application,owner,platform) and _mini_edit()==uid)
            if op=='wechat_cashier_link':
                if (not local_edit and (platform['status'] not in ('DRAFT','CORRECTION_REQUIRED')
                        or record is None or record['state'] not in ('DRAFT','CORRECTION'))) or record is None:
                    raise PermissionError('CASHIER_DRAFT_REQUIRED')
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
                if record and record['state'] not in ('DRAFT','CORRECTION') and not local_edit:raise PermissionError('PAYMENT_APPLICATION_EDIT_DENIED')
                if type(p['profile']) is not dict or len(canonical(p['profile']))>100000:raise ValueError('INVALID_OFFICIAL_PROFILE_DRAFT')
                private_drafts=None
                if 'ocr_drafts' in p:
                    from scripts.community_ocr_draft import merge_drafts, MATERIAL, FIELDS
                    current_owner,current_meta,current_platform=self.onboarding._load(application,uid)
                    if (_mini_edit() != uid or (current_owner,current_meta,current_platform)!=(owner,meta,platform)
                            or type(p['application_revision']) is not int or p['application_revision']!=platform['revision']):
                        raise ValueError('PRIVATE_OCR_DRAFT_APPLICATION_CHANGED')
                    if type(p['ocr_drafts']) is not dict or set(p['ocr_drafts'])-set(FIELDS):
                        raise ValueError('INVALID_PRIVATE_OCR_DRAFT')
                    updates={}
                    for kind,draft in p['ocr_drafts'].items():
                        material=meta['materials'].get(MATERIAL.get(kind,kind))
                        if not material or type(draft) is not dict or set(draft)!={'fields'}:
                            raise ValueError('INVALID_PRIVATE_OCR_DRAFT')
                        updates[kind]=dict(object_id=material['object_id'],sha256=material['sha256'],fields=draft['fields'])
                    private_drafts=merge_drafts((record or {}).get('ocr_drafts'),updates,meta['materials'])
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
                if private_drafts is not None:result['ocr_drafts']=private_drafts
                if not record:result['provider_state']='NOT_SUBMITTED'
            elif op=='wechat_submit_review':
                from scripts.community_merchant_onboarding import require_confirmed_declarations
                require_confirmed_declarations(meta,(record or {}).get('profile'))
                if record is None or record['state'] not in ('DRAFT','CORRECTION'):raise PermissionError('PAYMENT_DRAFT_REQUIRED')
                self._validate(record['profile'],meta['entity_type'])
                if record['profile']['subject_info']['identity_info']['id_doc_type']!=meta.get('identity_type','IDENTIFICATION_TYPE_IDCARD'):raise ValueError('PLATFORM_IDENTITY_TYPE_MISMATCH')
                result=dict(record,version=version+1,state='PENDING_INTERNAL_REVIEW')
            else:
                if uid==owner or record is None or record['state']!='PENDING_INTERNAL_REVIEW' or p['decision'] not in ('INTERNAL_APPROVED','CORRECTION') or type(p['opinion']) is not str or not 1<=len(p['opinion'])<=1000:raise PermissionError('INDEPENDENT_PAYMENT_APPLICATION_REVIEW_REQUIRED')
                result=dict(record,version=version+1,state=p['decision'],opinion=p['opinion'],reviewer=uid)
            self._save(application,owner,result);c.audit(application,uid,'WECHAT_'+op.upper(),str(result['version']))
        return self._draft_reply(result,owner_materials=meta['materials'] if op=='wechat_save' else None)
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
    def clear_cashier_media(self,application,owner,*,_mini_presubmission=False):
        c=self.center
        if not c.db.in_transaction:raise ValueError('ORIGINAL_ONBOARDING_TRANSACTION_REQUIRED')
        record=self._read(application)
        if record is None:return
        if (record['state'] not in ('DRAFT','CORRECTION')
                and not (_mini_presubmission is True and self.local_presubmission_editable(application,owner,local_queue=False))):
            raise PermissionError('CASHIER_DRAFT_REQUIRED')
        result=json.loads(json.dumps(record));values=self.cashier_values(result.get('profile',{}))
        previous=result.get('cashier_media_id');self.check_cashier_binding(application,values,previous)
        if previous:
            values.remove(previous)
            if values:result['profile']['addition_info']['business_addition_pics']=values
            else:result['profile']['addition_info'].pop('business_addition_pics',None)
            result.pop('cashier_media_id');result['version']+=1
            self._save(application,owner,result)
            c.audit(application,owner,'WECHAT_CASHIER_UNLINKED',str(result['version']))
    def _mini_owner_media_status(self, uid, owner, application, p, reauthorize):
        # Only the original Mini applicant context supplies this reauthorizer.
        if uid != owner or reauthorize() != uid:
            raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
        c = self.center
        _, meta, platform = self.onboarding._load(application, uid)
        if platform['status'] == 'WITHDRAWN':
            raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        kind = p['kind']
        if kind == 'bank_card':
            raise PermissionError('BANK_CARD_PRIVATE_PREVIEW_ONLY')
        if not self.enabled:
            raise WechatMediaUnavailable('REAL_MERCHANT_MEDIA_UPLOAD_GATE_CLOSED')
        if type(kind) is not str or kind not in meta['materials']:
            raise ValueError('ORIGINAL_PRIVATE_MATERIAL_REQUIRED')
        material = meta['materials'][kind]
        if material['expires_at'] is not None and material['expires_at'] <= c.now():
            raise ValueError('EXPIRED_PRIVATE_MATERIAL')
        source = material['sha256']
        want = p['expected_source_sha256']
        if (type(source) is not str or len(source) != 64
            or any(ch not in '0123456789abcdef' for ch in source)
            or want is not None and (type(want) is not str or source != want)):
            raise ValueError('MEDIA_RECEIPT_BINDING_MISMATCH')
        row = c.db.execute('SELECT project,sha,scan,mime FROM objects WHERE id=?',
                           (material['object_id'],)).fetchone()
        if row is None or tuple(row[:3]) != (application,source,'CLEAN'):
            raise PermissionError('SCANNED_ORIGINAL_MATERIAL_REQUIRED')
        if row[3] not in ('image/jpeg','image/png','application/pdf'):
            raise ValueError('UNSUPPORTED_PROVIDER_MEDIA')
        key = hashlib.sha256(canonical([self.reader._mchid,application,kind,source])).hexdigest()
        result = dict(application=application,kind=kind,source_sha256=source,state='PENDING_OR_UNKNOWN')
        # An old missing receipt is not proof that no upstream attempt occurred.
        row = c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' "
                           "AND subject_idx=? AND project=? AND user_id=? AND active=1",
                           (key,application,owner)).fetchone()
        if row is not None:
            evidence = c.db.execute("SELECT MIN(at) FROM audit WHERE project=? AND actor=? "
                                    "AND event='WECHAT_MEDIA_UPLOADED' AND object_id=?",
                                    (application,uid,key)).fetchone()
            at = evidence[0] if evidence is not None else None
            now = c.now()
            if type(at) is int and 0 <= now-at < 29*86400:
                saved = json.loads(c.decrypt(row[0], 'wechat-media:'+key))
                media_id = saved.get('media_id')
                response = saved.get('provider_response_sha256')
                if (saved.get('kind') != kind or saved.get('sha256') != source
                    or type(media_id) is not str or not 1 <= len(media_id) <= 1024
                    or type(response) is not str or len(response)!=64
                    or any(ch not in '0123456789abcdef' for ch in response)):
                    raise ValueError('MEDIA_RECEIPT_BINDING_MISMATCH')
                result.update(state='READY', media_id=media_id)
        if reauthorize() != uid:
            raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
        _, current, platform = self.onboarding._load(application, uid)
        if platform['status'] == 'WITHDRAWN' or current['materials'].get(kind) != material:
            raise PermissionError('MEDIA_RECEIPT_BINDING_MISMATCH')
        result['application_revision']=platform['revision']
        if (result['state']=='PENDING_OR_UNKNOWN' and row is None and platform['status'] in ('DRAFT','CORRECTION_REQUIRED')
            and not self._material_attempt_seen(c,application,uid,key)):
            result['state']='NOT_STARTED'
        return result

    @staticmethod
    def _material_attempt_seen(c,application,uid,key):
        return (c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_MEDIA_ATTEMPT' AND event_id=?",(key,)).fetchone() is not None
            or c.db.execute("SELECT 1 FROM audit WHERE project=? AND actor=? AND event IN ('WECHAT_MEDIA_UPLOAD_ATTEMPT','WECHAT_MEDIA_UPLOADED') AND object_id=?",(application,uid,key)).fetchone() is not None)

    def media(self,uid,owner,application,meta,kind,reauthorize,*,_mini_actor=None,_start=None):
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
        if self.onboarding._load(application,uid)[2]['status']=='WITHDRAWN':raise PermissionError('WITHDRAWN_APPLICATION_READ_ONLY')
        # Once sent, retain the original response evidence even if the applicant
        # later withdraws locally. Withdrawal never cancels a provider operation.
        _actor=_mini_actor if callable(_mini_actor) else reauthorize
        _key=hashlib.sha256(canonical([self.reader._mchid,application,kind,material['sha256']])).hexdigest()
        _direct=callable(_mini_actor) and _start is not None and 'expected_source_sha256' not in _start
        with _MINI_ACTIVE_MEDIA_LOCKS[int(_key[:2],16)%len(_MINI_ACTIVE_MEDIA_LOCKS)]:
            with c.tx():
                if reauthorize()!=uid or _actor()!=uid or owner!=uid:
                    raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
                _owner,_meta,_platform=self.onboarding._load(application,uid)
                if _owner!=uid or _meta['materials'].get(kind)!=material or _platform['status']=='WITHDRAWN':
                    raise PermissionError('ORIGINAL_MINI_MEDIA_CONTEXT_CHANGED')
                if _direct:
                    if callable(_mini_actor) and (_start is None or _start['owner_confirmed_material_send'] is not True or _start.get('expected_source_sha256',material['sha256'])!=material['sha256'] or type(_start['application_revision']) is not int or _start['application_revision']!=_platform['revision']):
                        raise ValueError('WECHAT_MEDIA_RESULT_UNKNOWN')
                    _stored=c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND subject_idx=? AND project=? AND user_id=? AND active=1",(_key,application,uid)).fetchone()
                    if _stored is not None:
                        _saved=self._mini_owner_media_status(uid,owner,application,dict(kind=kind,expected_source_sha256=material['sha256']),_actor)
                        if _saved['state']=='READY':return dict(media_id=_saved['media_id'],kind=kind,source_sha256=material['sha256'])
                    # Historical prepared markers do not gate a new deliberate click.
                else:
                    _status=self._mini_owner_media_status(uid,owner,application,dict(kind=kind,expected_source_sha256=material['sha256']),_actor)
                    if _status['state']=='READY':return dict(media_id=_status['media_id'],kind=kind,source_sha256=material['sha256'])
                    if callable(_mini_actor) and (_start is None or _start['owner_confirmed_material_send'] is not True or _start['expected_source_sha256']!=material['sha256'] or type(_start['application_revision']) is not int or _start['application_revision']!=_platform['revision'] or _status['state']!='NOT_STARTED'):
                        raise ValueError('WECHAT_MEDIA_RESULT_UNKNOWN')
                    if self._material_attempt_seen(c,application,uid,_key) or c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND subject_idx=? AND project=? AND user_id=? AND active=1",(_key,application,uid)).fetchone() is not None:
                        raise ValueError('WECHAT_MEDIA_RESULT_UNKNOWN')
                _reserved=c.db.execute("INSERT OR IGNORE INTO events VALUES('WECHAT_MEDIA_ATTEMPT',?,?)",(_key,c.now())).rowcount
                if _reserved!=1 and not _direct:raise ValueError('WECHAT_MEDIA_RESULT_UNKNOWN')
                c.audit(application,uid,'WECHAT_MEDIA_UPLOAD_ATTEMPT',_key)
            if reauthorize()!=uid or _actor()!=uid:
                raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
            _owner,_meta,_platform=self.onboarding._load(application,uid)
            if _owner!=uid or _meta['materials'].get(kind)!=material or _platform['status']=='WITHDRAWN' or (callable(_mini_actor) and _platform['revision']!=_start['application_revision']):
                raise PermissionError('ORIGINAL_MINI_MEDIA_CONTEXT_CHANGED')
            try:
                data,digest=request(self.reader,'POST','/v3/merchant/media/upload',raw=body,content_type='multipart/form-data; boundary='+boundary,signing_body=metadata)
            except Exception as error:
                try:
                    cls=type(error).__name__
                    cls=cls if cls in ('HTTPError','URLError','TimeoutError','ConnectionError','ConnectionResetError','SSLError','ValueError','PermissionError','InvalidSignature','OSError','RuntimeError','TypeError','AttributeError') else 'OtherError'
                    code=getattr(error,'code',None)
                    inner=getattr(error,'reason',None) if cls=='URLError' else error
                    inner_cls=type(inner).__name__
                    inner_cls=inner_cls if inner_cls in ('gaierror','TimeoutError','SSLError','SSLCertVerificationError','ConnectionRefusedError','ConnectionResetError','ConnectionAbortedError','BrokenPipeError','PermissionError','OSError','NoneType') else 'Other'
                    eno=getattr(inner,'errno',None)
                    verify=getattr(inner,'verify_code',None)
                    detail=' inner='+inner_cls+' errno='+str(eno if type(eno) is int and -4096<=eno<=4096 else 0)+' verify='+str(verify if type(verify) is int and 1<=verify<=1024 else 0)
                    syslog.syslog(syslog.LOG_WARNING,'XJ_MINI_MEDIA_PROVIDER_FAILURE class='+cls+' http='+str(code if type(code) is int and 100<=code<=599 else 0)+detail)
                except Exception:pass
                raise
            if type(data.get('media_id')) is not str or not 1<=len(data['media_id'])<=1024:raise ValueError('INVALID_PROVIDER_MEDIA_ID')
            with c.tx():
                key=hashlib.sha256(canonical([self.reader._mchid,application,kind,material['sha256']])).hexdigest()
                c.db.execute("INSERT OR IGNORE INTO links VALUES('COMMUNITY_WECHAT_MEDIA',?,?,?,?,1)",(key,owner,application,c.encrypt(canonical(dict(media_id=data['media_id'],kind=kind,sha256=material['sha256'],provider_response_sha256=digest)),'wechat-media:'+key)))
                c.audit(application,uid,'WECHAT_MEDIA_UPLOADED',key)
                # The winning persisted receipt is authoritative under concurrent uploads.
                saved=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA' AND subject_idx=? AND project=? AND user_id=? AND active=1",(key,application,owner)).fetchone()
                if saved is None:raise ValueError('MEDIA_RECEIPT_NOT_AVAILABLE')
                receipt=json.loads(c.decrypt(saved[0],'wechat-media:'+key))
                if receipt.get('kind')!=kind or receipt.get('sha256')!=material['sha256']:raise ValueError('MEDIA_RECEIPT_BINDING_MISMATCH')
            if reauthorize()!=uid:raise PermissionError('ORIGINAL_APPLICANT_SESSION_REQUIRED')
            self.onboarding._load(application,uid)
            return dict(media_id=receipt['media_id'],kind=kind,source_sha256=material['sha256'])


# Only previously verified exact applicant-bound sign_url; no local QR substitute.
def _original_sign_image(observer, session, csrf, application, project):
    out=observer.read(session,csrf,application,False,expected_project=project)
    if out.get('provider_state')!='APPLYMENT_STATE_TO_BE_SIGNED' or out.get('qr_available') is not True:
        raise ValueError('VERIFIED_PROVIDER_SIGN_URL_REQUIRED')
    uid=observer.center.session(session,csrf)
    def checked():
        obs=observer.snapshot(application); g=obs['grant']; saved=observer.stored(application)
        record=saved if observer._matching(saved,obs) else obs['record']; proof=record.get('provider_sign_url_proof')
        if (not g.get('active') or g.get('owner')!=uid or (project is not None and g.get('project')!=project)
            or record.get('provider_state')!='APPLYMENT_STATE_TO_BE_SIGNED' or g.get('applyment_id')!=out.get('applyment_id')
            or type(proof) is not dict or proof.get('applyment_id')!=out.get('applyment_id')
            or proof.get('signed_at')!=record.get('provider_query_signed_at')
            or proof.get('signature_sha256')!=record.get('provider_query_signature_sha256')):
            raise PermissionError('VERIFIED_PROVIDER_SIGN_URL_REQUIRED')
        return (g,proof,official_signing_url(record.get('provider_sign_url')))
    saved=checked()
    try:
        image=_read_wechat_sign_image(saved[2])
    except ValueError as e:
        import syslog
        detail=e.args[0] if len(e.args)==1 and e.args[0] in ('WX_OFFICIAL_QR_NO_REFERENCE','WX_OFFICIAL_QR_HTTP','WX_OFFICIAL_QR_NO_IMAGE','WX_OFFICIAL_QR_INVALID_IMAGE') else 'WX_OFFICIAL_QR_NO_IMAGE'
        syslog.syslog(syslog.LOG_WARNING,'XJ_OFFICIAL_SIGN_IMAGE '+detail)
        raise ValueError(detail) from None
    if observer.center.session(session,csrf)!=uid or checked()!=saved:
        raise PermissionError('VERIFIED_PROVIDER_SIGN_URL_REQUIRED')
    out.update(image)
    return out

def _read_wechat_sign_image(initial,fetch=None):
    from io import BytesIO
    import base64, hashlib, urllib.request as req, urllib.error as err
    from urllib.parse import urljoin,urlsplit,parse_qsl
    from html.parser import HTMLParser
    from PIL import Image
    import syslog
    def kind(url):
        if type(url) is not str or not 1<=len(url)<=2048 or any(ord(c)<33 or ord(c)>126 for c in url) or chr(92) in url or '#' in url: return ''
        u=urlsplit(url)
        if u.scheme!='https' or not u.query: return ''
        if (u.netloc,u.path)==('mp.weixin.qq.com','/cgi-bin/showqrcode'):
            fields=parse_qsl(u.query,keep_blank_values=True,max_num_fields=2)
            return 'image' if len(fields)==1 and fields[0][0]=='ticket' and 1<=len(fields[0][1])<=1024 else ''
        return {('pay.weixin.qq.com','/public/apply4ec_sign/s'):'page',('mp.weixin.qq.com','/showqrcode'):'image'}.get((u.netloc,u.path),'')
    class NoRedirect(req.HTTPRedirectHandler):
        def redirect_request(self,*args,**kw): return None
    def network(url):
        lim=192000 if kind(url)=='image' else 256000
        try:
            op=req.build_opener(req.ProxyHandler({}),NoRedirect())
            with op.open(req.Request(url,headers={'Accept':'image/png,image/jpeg' if kind(url)=='image' else 'text/html'}),timeout=3) as r:
                return r.status,r.headers.get_content_type(),r.read(lim+1)
        except err.HTTPError as e:
            with e:
                if e.code in (301,302,303,307,308): return e.code,'',e.headers.get('Location')
                raise ValueError('WX_OFFICIAL_QR_HTTP') from None
        except (OSError,err.URLError): raise ValueError('WX_OFFICIAL_QR_HTTP') from None
    class Img(HTMLParser):
        def handle_starttag(self,tag,attrs):
            if tag!='img': return
            for key,ref in attrs:
                if key in ('src','data-src') and ref:
                    target=urljoin(current,ref)
                    if kind(target)=='image': links.add(target)
    current=initial; seen=set()
    for _ in range(4):
        role=kind(current)
        if not role or current in seen:
            if fetch is None:
                shape=urlsplit(current); net='wxmp' if shape.netloc=='mp.weixin.qq.com' else 'wxpay' if shape.netloc=='pay.weixin.qq.com' else 'other'
                path={'/cgi-bin/showqrcode':'cgi','/showqrcode':'image','/public/apply4ec_sign/s':'sign_page'}.get(shape.path,'other')
                syslog.syslog(syslog.LOG_INFO,'XJ_OFFICIAL_SIGN_IMAGE_SHAPE blocked host='+net+' path='+path)
            break
        seen.add(current); code,mime,body=(fetch or network)(current)
        if fetch is None:
            typ=mime if mime in ('image/png','image/jpeg','image/jpg','image/gif','image/webp','image/x-png','application/octet-stream','text/html','application/json','') else 'other'
            size=str(len(body)) if type(body) is bytes else '0'
            syslog.syslog(syslog.LOG_INFO,'XJ_OFFICIAL_SIGN_IMAGE_SHAPE role='+role+' http='+str(code)+' type='+typ+' bytes='+size)
        if code in (301,302,303,307,308) and type(body) is str:
            current=urljoin(current,body); continue
        if code!=200 or type(body) is not bytes: break
        if role=='page' and mime=='text/html' and len(body)<=256000:
            links=set(); Img().feed(body.decode('utf-8','replace'))
            if len(links)!=1: raise ValueError('WX_OFFICIAL_QR_NO_REFERENCE')
            current,=links; continue
        if role=='image' and len(body)<=192000:
            try:
                with Image.open(BytesIO(body)) as pic:
                    if pic.format not in ('PNG','JPEG','GIF','WEBP') or pic.width!=pic.height or not 80<=pic.width<=1500 or getattr(pic,'n_frames',1)!=1: break
                    if pic.format=='PNG': pic.verify()
                    else:
                        buf=BytesIO(); pic.convert('RGB').save(buf,format='PNG'); body=buf.getvalue()
            except (OSError,ValueError): raise ValueError('WX_OFFICIAL_QR_INVALID_IMAGE') from None
            if len(body)<=192000:
                return {'qr_source':'WECHAT_OFFICIAL','qr_available':True,'png_data':'data:image/png;base64,'+base64.b64encode(body).decode('ascii'),'url_sha256':hashlib.sha256(initial.encode()).hexdigest()}
        break
    raise ValueError('WX_OFFICIAL_QR_NO_IMAGE')
