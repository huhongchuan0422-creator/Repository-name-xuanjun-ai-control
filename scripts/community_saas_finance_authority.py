"""Detached Finance confirmation verifier; no signer, ledger or payment mutation.

Trust keys and tenant scopes are protected deployment configuration belonging to
Finance. WeChat payment public keys are not Finance authorization keys. No key
is generated/discovered from a receipt, and test attestations are not accepted.
"""
import base64
import hashlib
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import rsa,padding,ed25519
from scripts.community_merchant_contract import valid_id
from scripts.pr122_customer_core import canonical
from scripts.community_saas_fulfillment import FinanceAuthority,FinanceConfirmation

AUDIENCE='xuanjun.community.saas.fulfillment.v1'


class SignedFinanceAuthority(FinanceAuthority):
    audience=AUDIENCE
    status='CONFIRMED'
    def __init__(self,trust):
        if type(trust) is not dict or not trust:raise ValueError('ADMITTED_FINANCE_TRUST_REQUIRED')
        self._keys={}
        for kid,record in trust.items():
            if (not valid_id(kid) or type(record) is not dict or set(record)!={'public_key_pem','tenants'}
                    or type(record['tenants']) not in (list,tuple) or not record['tenants']
                    or any(not valid_id(t) for t in record['tenants'])):raise ValueError('INVALID_FINANCE_TRUST')
            try:key=serialization.load_pem_public_key(record['public_key_pem'])
            except Exception:raise ValueError('FINANCE_PUBLIC_KEY_REQUIRED') from None
            if not isinstance(key,ed25519.Ed25519PublicKey) and not (isinstance(key,rsa.RSAPublicKey) and key.key_size>=2048):
                raise ValueError('SUPPORTED_FINANCE_SIGNING_KEY_REQUIRED')
            self._keys[kid]=(key,frozenset(record['tenants']))
    def __repr__(self):return '<SignedFinanceAuthority protected trust redacted>'
    def verify(self,claim,proof,now):
        if (type(now) is not int or not 0<=now<=253402300799 or type(claim) is not dict
                or type(proof) is not dict or set(proof)!={'key_id','payload','signature'}
                or type(proof['key_id']) is not str or proof['key_id'] not in self._keys
                or type(proof['payload']) is not dict or type(proof['signature']) is not str
                or len(proof['signature'])>2048):raise PermissionError('INVALID_FINANCE_CONFIRMATION')
        p=proof['payload'];key,tenants=self._keys[proof['key_id']]
        fields={'audience','tenant_id','order_id','quote_sha256','claim_sha256','proof_id','verified_at','expires_at','status'}
        if (set(p)!=fields or p['audience']!=self.audience or p['status']!=self.status
                or type(p['tenant_id']) is not str or p['tenant_id'] not in tenants
                or p['tenant_id']!=claim.get('tenant_id') or p['order_id']!=claim.get('order_id')
                or p['quote_sha256']!=claim.get('quote_sha256') or not valid_id(p['proof_id'])
                or p['claim_sha256']!=hashlib.sha256(canonical(claim)).hexdigest()
                or type(p['verified_at']) is not int or type(p['expires_at']) is not int
                or not 0<=p['verified_at']<=now<p['expires_at']<=p['verified_at']+900):
            raise PermissionError('FINANCE_CLAIM_OR_VALIDITY_MISMATCH')
        try:
            signature=base64.b64decode(proof['signature'],validate=True);message=canonical(p)
            if isinstance(key,rsa.RSAPublicKey):key.verify(signature,message,padding.PKCS1v15(),hashes.SHA256())
            else:key.verify(signature,message)
        except Exception:raise PermissionError('FINANCE_SIGNATURE_REJECTED') from None
        return FinanceConfirmation(p['proof_id'],p['claim_sha256'],p['verified_at'])


class SignedFinanceReversalAuthority(SignedFinanceAuthority):
    """Full original-claim reversal, with a distinct signed audience and status."""
    audience='xuanjun.community.saas.reversal.v1'
    status='REVERSED'
