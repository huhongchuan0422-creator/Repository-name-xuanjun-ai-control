"""Preserve an existing authenticated ROOT inventory; never mint capabilities."""
import json
import hmac
import hashlib
from scripts.community_admin_authority import CHANNEL, ACCOUNT_INDEX, full_community_capabilities
from scripts.pr122_customer_core import Center, canonical, digest, Denied
from types import SimpleNamespace

# Original authenticated ROOT165 list, read back before this change.
# Pin the exact list across source/installed inventory versions; never a subset rule.
ORIGINAL_165_SHA256 = '56b84a13587493531726f54d05662565bcf4cd29027d8a63483e9817a3f34433'

def unchanged_capabilities(original, target):
    full = frozenset(full_community_capabilities())
    original_set, target_set = frozenset(original), frozenset(target)
    known_165 = len(original_set) == 165 and digest(canonical(sorted(original_set))) == ORIGINAL_165_SHA256
    if (len(original) != len(original_set) or len(target) != len(target_set)
            or not (original_set == full or known_165)):
        raise Denied('EXACT_KNOWN_ORIGINAL_CAPABILITY_INVENTORY_REQUIRED')
    if original_set != target_set:
        raise Denied('POLICY_CAPABILITY_CHANGE_NOT_IN_SCOPE')

def readonly_original_root(db, keys, project, tenant):
    """Authenticated DB rows only. Caller already checked original inode/realm.
    No Center constructor/DDL/transaction/session/account writes or request UID.
    """
    view = SimpleNamespace(keys=keys)
    decrypt = lambda payload, aad: Center.decrypt(view, payload, aad)
    roots = []
    for row in db.execute('SELECT * FROM links WHERE channel=? AND project=?', (CHANNEL, project)):
        value = json.loads(decrypt(row['payload'], CHANNEL+':'+row['subject_idx']+':'+project))
        if value.get('kind') == 'ROOT':
            roots.append((row, value))
    if len(roots) != 1 or roots[0][0]['active'] != 1:
        raise Denied('ONE_ACTIVE_ORIGINAL_ROOT_REQUIRED')
    row, value = roots[0]
    fields = {'uid','project','tenant','kind','revision','parent','parent_revision',
              'capabilities','workspace_scopes','scope_binding_sha','manifest_sha','request_id'}
    if (set(value) != fields or value['uid'] != row['subject_idx']
            or row['user_id'] != value['uid'] or value['project'] != project
            or value['tenant'] != tenant or value['parent'] is not None
            or value['parent_revision'] is not None or type(value['revision']) is not int
            or value['revision'] < 1 or type(value['capabilities']) is not list
            or type(value['workspace_scopes']) is not list
            or len(value['workspace_scopes']) != len(set(value['workspace_scopes']))):
        raise Denied('EXACT_ORIGINAL_ROOT_REQUIRED')
    expected = digest(canonical(dict(capabilities=sorted(value['capabilities']),
        workspace_scopes=sorted(value['workspace_scopes']),scope_binding_sha=value['scope_binding_sha'])))
    if value['manifest_sha'] != expected:
        raise Denied('COMMUNITY_ADMIN_BINDING_CHANGED')
    account = db.execute('SELECT * FROM accounts WHERE id=?', (value['uid'],)).fetchone()
    if account is None or account['verified'] != 1:
        raise Denied('ACTIVE_ORIGINAL_ACCOUNT_REQUIRED')
    address = decrypt(account['email_enc'], value['uid']).decode()
    index_key = db.execute("SELECT v FROM settings WHERE k='index_key'").fetchone()[0]
    owner_index = hmac.new(keys[index_key],(ACCOUNT_INDEX+address).encode(),hashlib.sha256).hexdigest()
    if account['email_idx'] == owner_index:
        proof = db.execute('SELECT payload,active FROM links WHERE channel=? AND subject_idx=? AND project=? AND user_id=?',
            (CHANNEL+'_IDENTITY',value['uid'],project,value['uid'])).fetchone()
        if proof is None or proof['active'] != 1:
            raise Denied('OWNER_PROVISIONED_IDENTITY_REVOKED')
        identity = json.loads(decrypt(proof['payload'],CHANNEL+'_IDENTITY:'+value['uid']+':'+project))
        binding = identity.get('owner_binding',{})
        if (identity.get('kind') != 'OWNER_PROVISIONED_ACCOUNT'
                or identity.get('mailbox_verified') is not False
                or (binding.get('email'),binding.get('project'),binding.get('tenant')) != (address,project,tenant)):
            raise Denied('OWNER_PROVISIONED_IDENTITY_CHANGED')
    return value
