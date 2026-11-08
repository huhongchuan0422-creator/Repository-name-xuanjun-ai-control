"""Formal first-registration identity adapter and preparation verifier."""
import argparse, hashlib, json, time
from development_authority import canonical_bytes, load_public_key
from secure_file_input import read_owned_secret_file

def verify_registration(bundle, owner_key, now=None):
    required={'contract','owner_grant','developer_identity'}
    if not isinstance(bundle,dict) or set(bundle)!=required: raise ValueError('EXACT_REGISTRATION_BUNDLE_REQUIRED')
    contract=bundle['contract']; grant=bundle['owner_grant']; developer=bundle['developer_identity']
    now=time.time() if now is None else now
    contract_sha=hashlib.sha256(canonical_bytes(contract)).hexdigest()
    fields={'issuer','subject','developer','contract_sha256','valid_until','signature'}
    if (not isinstance(grant,dict) or set(grant)!=fields or grant['issuer']!='owner-auth'
        or grant['contract_sha256']!=contract_sha or grant['developer']!=developer
        or developer!=contract.get('developer') or not isinstance(grant['valid_until'],(int,float))
        or now>=grant['valid_until']): raise ValueError('AUTHENTICATED_OWNER_GRANT_REQUIRED')
    signed={k:grant[k] for k in fields-{'signature'}}
    import base64
    try: owner_key.verify(base64.b64decode(grant['signature'],validate=True),canonical_bytes(signed))
    except Exception: raise ValueError('OWNER_GRANT_SIGNATURE_INVALID')
    return {'task_id':contract.get('task_id'),'contract_sha256':contract_sha,
      'owner':{'issuer':'owner-auth','subject':grant['subject']},'developer':developer}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--bundle-file',required=True)
    p.add_argument('--owner-public-key-file',required=True); a=p.parse_args(argv)
    try:
        bundle=json.loads(read_owned_secret_file(a.bundle_file,'REGISTRATION_BUNDLE'))
        key=load_public_key(read_owned_secret_file(a.owner_public_key_file,'OWNER_PUBLIC_KEY').encode('ascii'))
        print(json.dumps(verify_registration(bundle,key),sort_keys=True)); return 0
    except Exception as exc:
        print(json.dumps({'verified':False,'error':str(exc)},sort_keys=True)); return 69

if __name__=='__main__': raise SystemExit(main())
