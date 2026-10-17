"""Provider identity adapter using the reviewed read-only client interfaces.

No clients are created automatically. A separately admitted private caller must
provide exact account anchors and approved clients. Tests inject fake clients;
this module has never been called with real credentials in this increment.
"""
from custody import Hold, digest, require
from pr122_oauth_candidate.tiktok import sanitize_user_info_response as sanitize_tiktok
from pr122_oauth_candidate.douyin import sanitize_user_info_response as sanitize_douyin


class PrivateIdentityVerifier:
    def __init__(self, account_ids, *, tiktok_client=None, douyin_client=None):
        self._accounts = dict(account_ids)
        self._clients = {'tiktok':tiktok_client, 'douyin':douyin_client}

    def __repr__(self):
        return '<PrivateIdentityVerifier private anchors redacted>'

    def __call__(self, provider, records):
        require(provider in self._clients and self._clients[provider] is not None,
                'PRIVATE_PROVIDER_CLIENT_NOT_ADMITTED')
        identity = self._accounts.get(provider)
        require(isinstance(identity,str) and bool(identity), 'PRIVATE_EXACT_ACCOUNT_ANCHOR_REQUIRED')
        try:
            token = records[provider.upper()+'_ACCESS_TOKEN']['value']
            require(isinstance(token,str) and bool(token), 'PRIVATE_ACCESS_TOKEN_REQUIRED')
            client = self._clients[provider]
            if provider == 'tiktok':
                raw = client.user_info(access_token=token)
                raw_identity = (raw.get('data') or {}).get('user', {}).get('open_id')
                account = sanitize_tiktok(raw)
            else:
                raw = client.user_info(access_token=token,open_id=identity)
                raw_identity = (raw.get('data') or {}).get('open_id')
                account = sanitize_douyin(raw)
            require(raw_identity == identity and account.get('status') == 'PASS', 'PRIVATE_ACCOUNT_VERIFICATION_MISMATCH')
            return {'raw_open_id':identity, 'access_token_sha256':digest(token), 'account':account}
        except Hold:
            raise
        except Exception:
            raise Hold('PRIVATE_IDENTITY_CHECK_UNKNOWN') from None
