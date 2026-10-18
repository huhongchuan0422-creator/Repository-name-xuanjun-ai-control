"""Versioned five-attempt authority; explicit Owner and independent modes.

The production path fetches directly over the inherited bounded/no-proxy HTTPS
worker. No caller-supplied transport, verified flag or public key can authenticate
its own five-attempt authority. Python 3.6; no credentials or UK host actions.
"""
import hashlib
from receipt_provider import canonical, digest, need

REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
MARKER='P2_ATTEMPT5_EXACT_VERSIONED_GRANT_V1\n'
DECISION='APPROVED_P2_ATTEMPT5_V1_EXACT_SCOPE'
OWNER_MARKER='P2_ATTEMPT5_OWNER_AUTHORIZATION_V1\n'
OWNER_DECISION='OWNER_AUTHORIZED_P2_ATTEMPT5_V1_EXACT_SCOPE'
OWNER_LOGIN='huhongchuan0422-creator'
OWNER_ID=332398908

def expected(grant,provider,cycle_policy=None,owner=False):
    from permit_cycle import policy
    body=dict(grant);body.pop('approval_body_sha256')
    key={'modulus_hex':format(provider.modulus,'x'),'exponent':provider.exponent}
    return {'schema':1,'decision':OWNER_DECISION if owner else DECISION,'grant':body,'issuer':provider.issuer,
            'provider_key_sha256':digest(key),'permit_cycle':policy(cycle_policy),
            'retry_policy':'INDEPENDENT_NO_WRITE_OR_NATIVE_CAS_SAFE_CHECKPOINT_ONLY_NO_REPLAY_V1',
            'effect_scope':'INHERITED_107_PAYLOADS_16_PHASES_NO_TLS_ISSUANCE'}

def validate(raw,review_id,grant,provider,cycle_policy=None):
    # The inherited parser rejects duplicate keys and NaN/Infinity.
    import epoch7_approval as old
    need(type(review_id) is int and review_id>0 and review_id not in old.CONSUMED,'NEW_REVIEW_ID')
    need(type(raw) is bytes and len(raw)<=65536,'APPROVAL_RESPONSE_BOUND')
    value=old.decode(raw.decode('utf-8'))
    need(type(value) is dict and type(value.get('id')) is int and value['id']==review_id and
         type(value.get('user')) is dict, 'APPROVAL_RESPONSE_IDENTITY')
    body=value.get('body')
    need(type(body) is str, 'APPROVAL_BODY_TYPE')
    # The authenticated HTTPS response selects a distinct versioned protocol.
    # A flag, root-owned config or caller-supplied key cannot select/forge it.
    owner=body.startswith(OWNER_MARKER)
    marker=OWNER_MARKER if owner else MARKER
    if owner:
        need(type(value['user'].get('id')) is int and value['user']['id']==OWNER_ID and
             value['user'].get('login')==OWNER_LOGIN, 'OWNER_APPROVAL_AUTHOR')
        issue=17
    else:
        need(value['user'].get('id')==95597695 and
             value['user'].get('login')=='18598789888','INDEPENDENT_APPROVAL_AUTHOR')
        issue=58
    need(value.get('issue_url')=='https://api.github.com/repos/'+REPO+'/issues/'+str(issue),
         'APPROVAL_DESTINATION')
    need(body.startswith(marker) and
         hashlib.sha256(body.encode('utf-8')).hexdigest()==grant['approval_body_sha256'], 'APPROVAL_BODY_SHA')
    if owner:
        from attempt_ledger import _valid_grant
        _valid_grant(grant)
    wanted=expected(grant,provider,cycle_policy,owner=owner)
    need(canonical(old.decode(body[len(marker):]))==canonical(wanted),'NEW_GRANT_AND_ISSUER_KEY_BINDING')
    return {'review_id':review_id,'approval_body_sha256':grant['approval_body_sha256'],
            'grant_sha256':digest(grant),'cycle_policy_sha256':digest(wanted['permit_cycle']),'provider_key_sha256':wanted['provider_key_sha256']}

def authenticate(review_id,grant,provider,cycle_policy=None):
    import epoch7_approval as old
    need(type(review_id) is int and review_id>0,'NEW_APPROVAL_NOT_ISSUED')
    url='https://api.github.com/repos/'+REPO+'/issues/comments/'+str(review_id)
    # Both protocols use the unchanged authenticated transport, never local JSON.
    # Reuse the unchanged original authenticated transport implementation and
    # its owned-session/response/timeout/cleanup bounds. No injectable fetcher.
    raw=old._run_worker([old.TRUSTED_PYTHON,'-I','-B','-S','-c',old._FETCH_WORKER,url])
    return validate(raw,review_id,grant,provider,cycle_policy)
