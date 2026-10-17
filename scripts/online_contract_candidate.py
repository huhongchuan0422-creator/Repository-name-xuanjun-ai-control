"""Offline policy prototype, NOT an identity verifier or production contracting service."""
from datetime import datetime, timezone

def evaluate(dossier, now):
    """Consume trusted-adapter-shaped fixtures only; never declares legal validity."""
    def hold(reason): return {'status':'HOLD','reason':reason,'production_enabled':False}
    if not isinstance(dossier,dict) or not isinstance(now,datetime) or now.tzinfo is None:
        return hold('INVALID_INPUT')
    try:
        for key in ('identity_verified','regional_legal_review','material_terms_presented','customer_confirmed','provider_confirmed','downloadable_evidence'):
            if dossier.get(key) is not True: return hold(key.upper()+'_REQUIRED')
        for key in ('contract_id','version_hash','tenant_id','actor_id','region_policy_id'):
            if not isinstance(dossier.get(key),str) or not dossier[key].strip(): return hold('MISSING_BINDING')
        if dossier.get('confirmed_version_hash') != dossier['version_hash']:return hold('VERSION_MISMATCH')
        if dossier.get('customer_type') not in ('PERSON','BUSINESS'):return hold('INVALID_CUSTOMER_TYPE')
        if dossier['customer_type']=='BUSINESS':
            a=dossier.get('authority')
            if not isinstance(a,dict) or a.get('verified') is not True or a.get('revoked') is not False:return hold('AUTHORITY_REQUIRED')
            if a.get('tenant_id')!=dossier['tenant_id'] or a.get('actor_id')!=dossier['actor_id']:return hold('AUTHORITY_SCOPE')
            if a.get('contract_id')!=dossier['contract_id'] or a.get('action')!='ACCEPT_CONTRACT':return hold('AUTHORITY_SCOPE')
            start=datetime.fromisoformat(a['valid_from']);end=datetime.fromisoformat(a['valid_until'])
            if start.tzinfo is None or end.tzinfo is None or not start<=now<end:return hold('AUTHORITY_EXPIRED')
            amount=dossier.get('amount_minor');limit=a.get('limit_minor')
            if type(amount) is not int or type(limit) is not int or not 0<=amount<=limit:return hold('AUTHORITY_AMOUNT')
            if not dossier.get('currency') or a.get('currency')!=dossier['currency']:return hold('AUTHORITY_CURRENCY')
        return {'status':'OFFLINE_POLICY_READY','production_enabled':False,'legal_validity':'NOT_DETERMINED','chain_status':'NOT_SUBMITTED'}
    except (KeyError,ValueError,TypeError,OverflowError):return hold('MALFORMED_EVIDENCE')
