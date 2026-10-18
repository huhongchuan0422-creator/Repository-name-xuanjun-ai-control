"""New PR58 five-attempt authority, separate from every legacy single-use permit.

The production path fetches directly over the inherited bounded/no-proxy HTTPS
worker. No caller-supplied transport, verified flag or public key can authenticate
its own five-attempt authority. Python 3.6; no credentials or UK host actions.
"""
import hashlib
from receipt_provider import canonical, digest, need

REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
MARKER='P2_ATTEMPT5_EXACT_VERSIONED_GRANT_V1\n'
DECISION='APPROVED_P2_ATTEMPT5_V1_EXACT_SCOPE'

def expected(grant,provider):
    body=dict(grant);body.pop('approval_body_sha256')
    key={'modulus_hex':format(provider.modulus,'x'),'exponent':provider.exponent}
    return {'schema':1,'decision':DECISION,'grant':body,'issuer':provider.issuer,
            'provider_key_sha256':digest(key)}

def validate(raw,review_id,grant,provider):
    # The inherited parser rejects duplicate keys and NaN/Infinity.
    import epoch7_approval as old
    need(type(review_id) is int and review_id>0 and review_id not in old.CONSUMED,'NEW_REVIEW_ID')
    need(type(raw) is bytes and len(raw)<=65536,'APPROVAL_RESPONSE_BOUND')
    value=old.decode(raw.decode('utf-8'))
    need(type(value) is dict and type(value.get('id')) is int and value['id']==review_id and
         type(value.get('user')) is dict and value['user'].get('id')==95597695 and
         value['user'].get('login')=='18598789888','INDEPENDENT_APPROVAL_AUTHOR')
    need(value.get('issue_url')=='https://api.github.com/repos/'+REPO+'/issues/58','APPROVAL_DESTINATION')
    body=value.get('body')
    need(type(body) is str and body.startswith(MARKER) and
         hashlib.sha256(body.encode('utf-8')).hexdigest()==grant['approval_body_sha256'], 'APPROVAL_BODY_SHA')
    wanted=expected(grant,provider)
    need(canonical(old.decode(body[len(MARKER):]))==canonical(wanted),'NEW_GRANT_AND_ISSUER_KEY_BINDING')
    return {'review_id':review_id,'approval_body_sha256':grant['approval_body_sha256'],
            'grant_sha256':digest(grant),'provider_key_sha256':wanted['provider_key_sha256']}

def authenticate(review_id,grant,provider):
    import epoch7_approval as old
    need(type(review_id) is int and review_id>0,'NEW_APPROVAL_NOT_ISSUED')
    url='https://api.github.com/repos/'+REPO+'/issues/comments/'+str(review_id)
    # Reuse the unchanged original authenticated transport implementation and
    # its owned-session/response/timeout/cleanup bounds. No injectable fetcher.
    raw=old._run_worker([old.TRUSTED_PYTHON,'-I','-B','-S','-c',old._FETCH_WORKER,url])
    return validate(raw,review_id,grant,provider)
