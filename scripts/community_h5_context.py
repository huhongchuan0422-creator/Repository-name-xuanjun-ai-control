"""Request-local bridge to the SAME Center account and live project authority.

Only the H5 composition enters this context after cookie+CSRF authentication.
No mini link, account, role, grant, credential or persistent policy is created.
Outside this request context all original mini admission rules are unchanged.
"""
import contextvars
from contextlib import contextmanager

_CURRENT = contextvars.ContextVar('community_h5_existing_center', default=None)

@contextmanager
def authorized(identity, token, csrf):
    from scripts.community_mini_center_identity import CenterIdentity
    if type(identity) is not CenterIdentity or type(csrf) is not str or not csrf:
        raise PermissionError('ORIGINAL_CENTER_CSRF_REQUIRED')
    uid = identity.center.session(token, csrf)
    reset = _CURRENT.set((identity, token, csrf, uid))
    try: yield
    finally: _CURRENT.reset(reset)

def current(identity, token):
    value = _CURRENT.get()
    if value is None: return None
    if value[0] is not identity or value[1] != token:
        raise PermissionError('H5_REQUEST_CONTEXT_MISMATCH')
    if identity.center.session(token, value[2]) != value[3]:
        raise PermissionError('H5_ACCOUNT_CHANGED')
    identity._time(identity.center.now())
    return value[3], value[2]

def resolve(identity, token, scene):
    value = current(identity, token)
    if value is None: return None
    binding = identity.scenes.get(scene)
    if binding is None: raise PermissionError('SCENE_NOT_REGISTERED')
    uid, csrf = value
    from scripts import community_wechat_registration as registration
    if registration.native(identity.center,uid) is not None:
        project = registration.project(identity,uid,scene)
    else:
        project,_,_ = identity.center.project(uid,binding['project'],('OWNER','EDITOR'))
    principal = binding['principal']
    if principal.role != 'CUSTOMER' or project['tenant'] != principal.tenant_id or principal not in identity.runtime.bindings:
        raise PermissionError('CURRENT_CUSTOMER_PROJECT_REQUIRED')
    return uid, binding['project'], principal
