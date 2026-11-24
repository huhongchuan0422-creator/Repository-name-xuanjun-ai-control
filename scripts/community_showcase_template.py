"""Protected showcase template only; no grant, identity or policy writes."""
from scripts.pr122_customer_core import Denied, identifier
ROLE = 'PLATFORM_SHOWCASE_ROOT'
ROUTE = '/community/operations'
OPS = frozenset(('community.item', 'community.merchant_settings'))
FIELDS = {'project', 'tenant', 'role', 'operator_uid', 'operations'}

def validate(key, template, project, tenant):
    if (type(template) is not dict or set(template) != FIELDS
            or template['role'] != ROLE or template['project'] != project
            or template['tenant'] != tenant or type(key) is not str
            or not key.startswith(ROUTE+'#') or key.count('#') != 1
            or type(template['operations']) is not list
            or len(template['operations']) != 2 or set(template['operations']) != OPS):
        raise Denied('EXACT_SHOWCASE_TEMPLATE_REQUIRED')
    identifier(key.split('#')[1]); identifier(template['operator_uid'])

def authorize(center, authority, proof, route, operation, workspace):
    key = route+'#'+workspace
    template = getattr(center, 'community_admin_workspace_bindings', {}).get(key)
    if template is None or template.get('role') != ROLE:
        return proof
    from scripts.community_admin_route_gate import template_digest
    if getattr(center, 'community_admin_template_pins', {}).get(key) != template_digest(template):
        raise Denied('COMMUNITY_ADMIN_TEMPLATE_CHANGED')
    # Runtime tuples are immutable projections of the protected list.
    raw = dict(template, operations=list(template['operations']))
    validate(key, raw, authority.project, authority.tenant)
    if (operation not in OPS or proof['uid'] != template['operator_uid']
            or authority.authority(proof['uid'])['kind'] != 'ROOT'):
        raise Denied('EXACT_SHOWCASE_ROOT_OPERATION_REQUIRED')
    return proof
