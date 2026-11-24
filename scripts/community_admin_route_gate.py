"""Supplemental, fail-closed restrictions at ORIGINAL community route entries.

Exact community authority uses explicitly protected registered workspace
templates, never fabricated roles or another account identity. Native Principal,
ownership, financial and provider checks still run. Independent CRM projects
retain their original project membership checks.
The protected composition must attach its exact CommunityAdminAuthority as
center.community_admin_authority. Merely having a live legacy workspace must
never let a restricted/revoked community administrator evade its grant.
"""
from contextvars import ContextVar
from functools import wraps
from scripts.pr122_customer_core import Center, Denied
from scripts.community_admin_authority import CommunityAdminAuthority, CHANNEL

ROUTE_FAMILIES = (
    '/merchant/onboarding', '/community/operations', '/customer/saas-api',
    '/community/fulfillment', '/community/provider-actions',
    '/community/merchant-bills', '/community/directory',
    '/community/commerce', '/community/project-materials',
)


def enforce_admin_route(center, session, csrf, route, body):
    if type(center) is not Center or route not in ROUTE_FAMILIES:
        raise Denied('ORIGINAL_COMMUNITY_ROUTE_REQUIRED')
    # Original public catalog is not an administrative permission.
    if route == '/merchant/onboarding' and type(body) is dict and body.get('operation') == 'catalog' and body.get('params') == {}:
        return None
    # No feature installation: leave all original behavior, including public
    # onboarding catalog and its validation order, entirely untouched.
    if not center.db.execute('SELECT 1 FROM links WHERE channel=? LIMIT 1', (CHANNEL,)).fetchone():
        return None
    if not session:
        return None  # Original authenticated paths reject absent sessions.
    uid = center.session(session, csrf)
    records = list(center.db.execute('SELECT project FROM links WHERE channel=? AND subject_idx=?', (CHANNEL, uid)))
    if not records:
        return None  # Ordinary users keep their original authorization path.
    authority = getattr(center, 'community_admin_authority', None)
    if (type(authority) is not CommunityAdminAuthority or authority.c is not center
            or len(records) != 1 or records[0]['project'] != authority.project):
        raise Denied('EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED')
    if type(body) is not dict or type(body.get('operation')) is not str:
        raise Denied('EXACT_COMMUNITY_OPERATION_REQUIRED')
    # Includes inactive records: revocation cannot fall back to legacy grants.
    workspace = '__community_onboarding__' if route == '/merchant/onboarding' else body.get('workspace')
    if type(workspace) is not str or not workspace:
        raise Denied('EXACT_COMMUNITY_WORKSPACE_REQUIRED')
    return authority.authorize(session, csrf, route, body['operation'], workspace=workspace)


_CURRENT = ContextVar('original_community_admin_request', default=None)


def community_route(route):
    """Bind only a real original dispatch invocation; always clear on exit."""
    if route not in ROUTE_FAMILIES:
        raise ValueError('UNKNOWN_ORIGINAL_ROUTE')
    def decorate(method):
        @wraps(method)
        def dispatch(self, session, csrf, body, *args, **kwargs):
            admitted = enforce_admin_route(self.center, session, csrf, route, body)
            token = _CURRENT.set(None if admitted is None else
                (self.center, session, csrf, route, body['operation'], admitted,
                 '__community_onboarding__' if route == '/merchant/onboarding' else body['workspace']))
            try:
                return method(self, session, csrf, body, *args, **kwargs)
            finally:
                _CURRENT.reset(token)
        return dispatch
    return decorate


def community_project(center, uid, project, roles):
    """Community realm only, after ORIGINAL protected UID/workspace checks.

    Does not impersonate OWNER/REVIEWER membership. Returned marker is explicitly
    COMMUNITY_ADMIN and is used by original immutable context comparisons.
    CRM project workflow must continue calling original Center.project directly.
    """
    context = _CURRENT.get()
    if context is None or context[0] is not center or context[5]['uid'] != uid:
        return center.project(uid, project, roles)
    authority = getattr(center, 'community_admin_authority', None)
    if type(authority) is not CommunityAdminAuthority or authority.c is not center:
        raise Denied('EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED')
    live = authority.authorize(context[1], context[2], context[3], context[4], workspace=context[6])
    if live != context[5] or project != live['project']:
        raise Denied('COMMUNITY_ADMIN_SCOPE_OR_REVISION_CHANGED')
    record = authority._realm()
    if record['tenant'] != live['tenant']:
        raise Denied('COMMUNITY_ADMIN_TENANT_CHANGED')
    return record, 'COMMUNITY_ADMIN', None


def resolve_admin_workspace(center, legacy_grants, workspace, uid):
    """Resolve an explicitly protected template, never another user's grant."""
    context = _CURRENT.get()
    if context is None or context[0] is not center or context[5]['uid'] != uid:
        return legacy_grants.get(workspace)
    authority = getattr(center, 'community_admin_authority', None)
    admitted = authority.authorize(context[1], context[2], context[3], context[4], workspace=workspace)
    if admitted != context[5]:
        raise Denied('COMMUNITY_ADMIN_REVISION_CHANGED')
    templates = getattr(center, 'community_admin_workspace_bindings', {})
    template = templates.get(context[3]+'#'+workspace)
    if template is None:
        # Explicit legacy grant for this same UID remains usable; no fallback
        # to another user's workspace is ever permitted by native authorizers.
        return legacy_grants.get(workspace)
    pins = getattr(center, 'community_admin_template_pins', None)
    if pins is not None and pins.get(context[3]+'#'+workspace) != template_digest(template):
        raise Denied('COMMUNITY_ADMIN_TEMPLATE_CHANGED')
    if template['project'] != authority.project:
        raise Denied('COMMUNITY_ADMIN_TEMPLATE_PROJECT_CHANGED')
    from copy import deepcopy
    grant = {k: (v if k == 'principal' else deepcopy(v)) for k,v in template.items()}
    grant['user_id'] = uid
    return grant


def configure_admin_routes(center, runtime, principals, config):
    """Read-only composition from the ORIGINAL protected host plan.

    No accounts/members/Principals are created and no provider policy is changed.
    Templates are explicit server policy, not inferred from existing users.
    """
    from scripts.community_saas_phase2 import Principal
    from scripts.community_stage_runtime import StageRuntime
    from scripts.pr122_customer_core import identifier, digest, canonical
    from copy import deepcopy
    expected = {'project','tenant','capabilities','workspace_scopes','workspace_bindings','manifest_sha'}
    if (type(center) is not Center or type(runtime) is not StageRuntime
            or type(config) is not dict or set(config) != expected
            or type(principals) is not dict or type(config['capabilities']) is not list
            or type(config['workspace_scopes']) is not list or type(config['workspace_bindings']) is not dict):
        raise Denied('EXACT_PROTECTED_ADMIN_CONFIGURATION_REQUIRED')
    authority = CommunityAdminAuthority(center, config['project'], config['tenant'],
        tuple(config['capabilities']), tuple(config['workspace_scopes']),
        binding_digest(config['workspace_bindings'], runtime, principals))
    if config['manifest_sha'] != authority.manifest_sha:
        raise Denied('ADMIN_MANIFEST_PIN_CHANGED')
    authority._realm()
    templates = {}
    for key, raw in config['workspace_bindings'].items():
        if key not in authority.workspace_scopes or type(raw) is not dict or 'user_id' in raw:
            raise Denied('EXPLICIT_NONIMPERSONATING_ADMIN_TEMPLATE_REQUIRED')
        route, workspace = key.split('#')
        identifier(workspace)
        grant = deepcopy(raw)
        if grant.get('project') != authority.project:
            raise Denied('ADMIN_TEMPLATE_REALM_REQUIRED')
        if 'principal' in grant:
            if (set(grant) != {'project','project_roles','principal','onboarding_required'}
                    or grant['principal'] not in principals
                    or type(grant['project_roles']) is not list or not grant['project_roles']
                    or any(r not in ('OWNER','EDITOR','REVIEWER') for r in grant['project_roles'])
                    or type(grant['onboarding_required']) is not bool):
                raise Denied('EXACT_REGISTERED_ADMIN_TEMPLATE_REQUIRED')
            p = principals[grant['principal']]
            if type(p) is not Principal or p not in runtime.bindings or p.tenant_id != authority.tenant:
                raise Denied('ORIGINAL_REGISTERED_ADMIN_PRINCIPAL_REQUIRED')
            permitted = {
                '/community/operations': ('MERCHANT_ADMIN','STORE_STAFF','PLATFORM_REVIEWER','FINANCE_APPROVER','PLATFORM_OWNER'),
                '/customer/saas-api': ('CUSTOMER','PLATFORM_OWNER'),
                '/community/fulfillment': ('PLATFORM_OWNER',),
                '/community/provider-actions': ('FINANCE_APPROVER','PLATFORM_OWNER'),
                '/community/merchant-bills': ('FINANCE_APPROVER','PLATFORM_OWNER'),
                '/community/commerce': ('MERCHANT_ADMIN','PLATFORM_OWNER'),
                '/community/directory': ('FINANCE_APPROVER','PLATFORM_OWNER'),
            }
            if p.role not in permitted.get(route, ()) or grant['onboarding_required'] and p.role != 'MERCHANT_ADMIN':
                raise Denied('ORIGINAL_ROUTE_PRINCIPAL_ROLE_REQUIRED')
            grant.update(principal=p, role=p.role, tenant=p.tenant_id,
                scope=dict(runtime.bindings[p]), project_roles=tuple(grant['project_roles']))
        elif 'finance_workspace' in grant:
            from scripts.community_merchant_bills import MerchantBills
            MerchantBills._validate(workspace, dict(grant, user_id='template_validation'))
            if route != '/community/merchant-bills' or grant['tenant_id'] != authority.tenant:
                raise Denied('EXACT_MERCHANT_BILL_TEMPLATE_REQUIRED')
        elif set(grant) == {'project','tenant','role'}:
            if grant['tenant'] != authority.tenant or grant['role'] not in ('COMMUNITY_ADMIN','MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER'):
                raise Denied('EXACT_DIRECTORY_ADMIN_TEMPLATE_REQUIRED')
            if route == '/merchant/onboarding' and (workspace != '__community_onboarding__' or grant['role'] != 'PLATFORM_REVIEWER'):
                raise Denied('EXACT_ONBOARDING_REVIEWER_TEMPLATE_REQUIRED')
            if route not in ('/community/directory','/merchant/onboarding'):
                raise Denied('DIRECTORY_TEMPLATE_ROUTE_MISMATCH')
        else:
            raise Denied('UNKNOWN_ADMIN_TEMPLATE_SHAPE')
        templates[key] = grant
    center.community_admin_template_pins = {key:template_digest(value) for key,value in templates.items()}
    center.community_admin_workspace_bindings = templates
    center.community_admin_authority = authority
    return authority


def admin_workspace_catalog(center, legacy_grants):
    """Only current principal's explicitly delegated workspace templates."""
    context = _CURRENT.get()
    if context is None or context[0] is not center:
        return legacy_grants
    result = {}
    authority = center.community_admin_authority
    current = authority.authority(context[5]['uid'])
    prefix = context[3]+'#'
    for key in current['workspace_scopes']:
        if key.startswith(prefix):
            workspace=key[len(prefix):]
            grant=resolve_admin_workspace(center,legacy_grants,workspace,current['uid'])
            if grant is not None:result[workspace]=grant
    return result



def binding_digest(workspace_bindings, runtime, principals):
    """Pin both named templates AND their actual registered role/store target."""
    from scripts.pr122_customer_core import canonical, digest
    from scripts.community_saas_phase2 import Principal
    if type(workspace_bindings) is not dict:
        raise Denied('EXACT_ADMIN_BINDING_CATALOG_REQUIRED')
    registered = {}
    for key, template in workspace_bindings.items():
        if type(template) is not dict:
            raise Denied('EXACT_ADMIN_BINDING_TEMPLATE_REQUIRED')
        if 'principal' not in template:
            continue
        name = template['principal']
        if type(name) is not str or name not in principals:
            raise Denied('NAMED_REGISTERED_ADMIN_PRINCIPAL_REQUIRED')
        p = principals[name]
        if type(p) is not Principal or p not in runtime.bindings:
            raise Denied('ORIGINAL_REGISTERED_ADMIN_PRINCIPAL_REQUIRED')
        registered[name] = dict(tenant_id=p.tenant_id,role=p.role,scope=dict(runtime.bindings[p]))
    return digest(canonical(dict(workspace_bindings=workspace_bindings,registered=registered)))



def template_digest(template):
    from scripts.pr122_customer_core import digest, canonical
    return digest(canonical({k: (dict(instance=id(v),tenant=v.tenant_id,role=v.role) if k=='principal' else v)
        for k,v in template.items()}))



def admin_request_active(center):
    context = _CURRENT.get()
    return context is not None and context[0] is center


def has_admin_templates(center, route):
    return type(getattr(center,'community_admin_authority',None)) is CommunityAdminAuthority and any(
        key.startswith(route+'#') for key in getattr(center,'community_admin_workspace_bindings',{}))
