"""Read only discovery of already-authorized mini customer contexts.

Not an admin merchant directory. Never publishes onboarding materials or infers
industry classifications. Existing per-scene services remain the authority.
"""
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_merchant_store import profile
from scripts.community_mini_login import SCENE


def customer_contexts(gateway, token, params):
    if type(params) is not dict or set(params) not in (set(), {'after_scene'}):
        raise ValueError('INVALID_CUSTOMER_CONTEXT_FIELDS')
    after = params.get('after_scene', '')
    if type(after) is not str or after and not SCENE.fullmatch(after):
        raise ValueError('INVALID_CUSTOMER_CONTEXT_CURSOR')
    identity = gateway.identity
    if type(identity) is not CenterIdentity:
        raise PermissionError('ORIGINAL_CENTER_IDENTITY_REQUIRED')
    identity.applicant_context(token)  # original session/link and maintenance check
    # Paginate only after live authorization. Global scene keys/counts are not
    # public metadata and must never leak through a cursor or has_more flag.
    authorized = []
    for scene in sorted(identity.scenes):
        if scene <= after:
            continue
        try:
            _, _, principal = identity._resolve(token, scene)
        except PermissionError:
            continue  # no disclosure of inaccessible project or merchant
        if principal.role != 'CUSTOMER':
            continue
        authorized.append((scene, principal))
        if len(authorized) == 51:
            break
    contexts = []
    for scene, principal in authorized[:50]:
        scope = gateway.runtime.bindings[principal]
        merchant = None
        try:
            record = profile(gateway.runtime.demo.merchant_db, scope)
            merchant = {key: record[key] for key in ('name', 'description')}
        except ValueError as exc:
            if str(exc) != 'UNAVAILABLE_STOREFRONT':raise
        contexts.append(dict(scene=scene, merchant=merchant,
                             storefront_state='AVAILABLE' if merchant is not None else 'UNAVAILABLE',
                             category=None, storefront_photo=None,
                             public_assets_state='NOT_CONNECTED'))
    return dict(contexts=contexts, has_more=len(authorized)>50,
                next_cursor=authorized[49][0] if len(authorized)>50 else None,
                scope='CURRENT_CUSTOMER_AUTHORIZED_CONTEXTS',
                payment_enabled=False)
