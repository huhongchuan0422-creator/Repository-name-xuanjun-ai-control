"""Candidate adapter over original catalog; no new storage/service or authority."""
from copy import deepcopy
from scripts.saas_module_package_gate import assess, manifest_digest


def dependency_closure(catalog, module_id, manifests):
    """Inspect full reachable graph and exact pins, not installed/live readiness."""
    rows = {row['id']: row for row in catalog}
    errors, ordered, active, done = [], [], set(), set()
    def visit(mid):
        if mid in active:
            errors.append('CYCLE:' + mid); return
        if mid in done: return
        if mid not in rows:
            errors.append('MISSING_MODULE:' + mid); return
        manifest = manifests.get(mid)
        if not isinstance(manifest, dict):
            errors.append('MISSING_PACKAGE:' + mid); return
        if manifest.get('module_id') != mid:
            errors.append('PACKAGE_IDENTITY_MISMATCH:' + mid)
        deps = manifest.get('dependencies')
        if not isinstance(deps, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in deps.items()):
            errors.append('INVALID_DEPENDENCIES:' + mid); return
        if set(deps) != set(rows[mid]['dependencies']):
            errors.append('CATALOG_DEPENDENCY_MISMATCH:' + mid)
        active.add(mid)
        for dep, version in sorted(deps.items()):
            child = manifests.get(dep)
            if not isinstance(child, dict) or child.get('version') != version:
                errors.append('PIN_MISMATCH:' + mid + ':' + dep)
            visit(dep)
        active.remove(mid); done.add(mid); ordered.append(mid)
    visit(module_id)
    return {'state':'UNKNOWN' if errors else 'SYNTHETIC_GRAPH_VALIDATED',
            'errors':sorted(set(errors)), 'order':ordered, 'live_dependencies_verified':False}


class EcosystemAdapter:
    """Reads original catalog/list_offers. Input snapshots are not a second registry."""
    def __init__(self, modules, offers, db):
        self.modules, self.offers, self.db = modules, offers, db

    def propose_registration(self, manifest, artifact, context, receipts):
        qualification = assess(manifest, artifact, context, receipts)
        rows = {r['id']:r for r in self.modules.catalog()}
        mid = manifest.get('module_id') if isinstance(manifest, dict) else None
        row = rows.get(mid) if isinstance(mid,str) else None
        reasons = list(qualification['reasons'])
        if row is None: reasons.append('UNKNOWN_CANONICAL_MODULE')
        elif not reasons and set(manifest['capabilities']) != set(row['capabilities']):
            reasons.append('CANONICAL_CAPABILITY_MISMATCH')
        if row is not None and not reasons and set(manifest['dependencies']) != set(row['dependencies']):
            reasons.append('CANONICAL_DEPENDENCY_MISMATCH')
        return {'kind':'MODULE_PACKAGE_REGISTRATION_PROPOSAL', 'module_id':mid,
                'manifest':deepcopy(manifest), 'qualification':qualification,
                'proposal_id':None if reasons else 'sha256:' + manifest_digest(manifest),
                'reasons':sorted(set(reasons)), 'persisted':False, 'writer_lease':'UNKNOWN',
                'registration_state':'BLOCKED' if reasons else 'LOCAL_PROPOSAL_ONLY',
                'publish_allowed':False}

    def listing(self, manifests, artifacts, contexts, receipts, tenant_id):
        rows = self.modules.catalog()
        result = []
        qualifications = {row['id']: self.propose_registration(manifests[row['id']],
            artifacts.get(row['id'], b''), contexts.get(row['id'], {}),
            receipts.get(row['id'], {})) for row in rows if row['id'] in manifests}
        for row in rows:
            mid = row['id']; manifest = manifests.get(mid)
            offer_rows = self.offers.list_offers(self.db, mid, tenant_id)
            # Only offer identity, never internal cost/approval/customer material.
            offer_refs = [{'offer_id':o['offer_id'], 'offer_version':o['version'],
                           'kind':o['kind']} for o in offer_rows]
            if manifest is None:
                status, evidence, graph, version = 'UNPACKAGED', None, {'state':'UNKNOWN'}, None
            else:
                evidence = qualifications[mid]
                graph = dependency_closure(rows, mid, manifests)
                version = manifest.get('version') if isinstance(manifest,dict) else None
                blocked_dependencies = {dep: qualifications[dep]['reasons']
                    for dep in graph['order'] if dep != mid and dep in qualifications
                    and qualifications[dep]['reasons']}
                graph['qualification_state'] = ('SYNTHETIC_CLOSURE_REVIEW_ONLY'
                    if graph['state'] == 'SYNTHETIC_GRAPH_VALIDATED' and
                    not blocked_dependencies and not evidence['reasons'] else 'BLOCKED')
                graph['blocked_dependencies'] = blocked_dependencies
                status = ('LOCAL_REVIEW_ONLY' if graph['qualification_state'] ==
                          'SYNTHETIC_CLOSURE_REVIEW_ONLY' else 'BLOCKED')
            result.append({'module_id':mid,'title':row['title'],'capabilities':list(row['capabilities']),
                'package_version':version, 'dependencies':list(row['dependencies']),
                'dependency_graph':graph, 'offer_refs':offer_refs,
                'evidence':None if evidence is None else {'qualification':evidence['qualification'],
                    'registration_state':evidence['registration_state'], 'reasons':evidence['reasons']},
                'listing_state':status, 'published':False,
                'tenant_authorization':'UNKNOWN', 'permission_authorization':'UNKNOWN',
                'production_verified':False})
        return {'schema':'ecosystem-read-model-v1','source':'EXISTING_CATALOG_ADAPTER',
                'scope':'SYNTHETIC_INTEGRATION_ONLY','rows':result,
                'writer_lease':'UNKNOWN','http_wired':False,'publish_allowed':False}
