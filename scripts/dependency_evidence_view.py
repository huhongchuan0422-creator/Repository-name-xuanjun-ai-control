"""Pure DAG evidence view over caller-authenticated canonical nodes."""
import re


def dependency_view(target, nodes):
    if (not isinstance(target, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', target)
            or not isinstance(nodes, dict) or len(nodes) > 1000 or target not in nodes):
        raise ValueError('INVALID_DEPENDENCY_INPUT')
    reasons = set(); visited = set(); active = set(); stack = [(target, False)]
    while stack:
        name, leaving = stack.pop()
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', name):
            raise ValueError('INVALID_NODE_ID')
        if leaving:
            active.remove(name); visited.add(name); continue
        if name in active:
            reasons.add('DEPENDENCY_CYCLE'); continue
        if name in visited:
            continue
        node = nodes.get(name)
        if not isinstance(node, dict) or set(node) != {'dependencies', 'state', 'evidence_sha256'}:
            reasons.add('MISSING_OR_MALFORMED_NODE'); visited.add(name); continue
        deps = node['dependencies']
        if (not isinstance(deps, list) or len(deps) > 100
                or any(not isinstance(d, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', d) for d in deps)
                or len(set(deps)) != len(deps)):
            reasons.add('INVALID_DEPENDENCY_LIST'); visited.add(name); continue
        # Target is being evaluated for readiness; only ancestors must be done.
        if name != target and (node['state'] != 'ACCEPTED'
                or not isinstance(node['evidence_sha256'], str)
                or not re.fullmatch('[a-f0-9]{64}', node['evidence_sha256'])):
            reasons.add('DEPENDENCY_NOT_ACCEPTED_WITH_EVIDENCE')
        active.add(name); stack.append((name, True))
        stack.extend((dep, False) for dep in reversed(deps))
    return {'schema': 'DEPENDENCY_EVIDENCE_VIEW_V1',
            'status': 'HOLD' if reasons else 'DEPENDENCIES_EVIDENCED',
            'reasons': sorted(reasons), 'visited_count': len(visited),
            'execution_granted': False, 'authenticity': 'CALLER_REQUIRED'}
