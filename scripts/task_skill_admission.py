"""Version-bound read-back evidence on the original model_audit ledger.
No learned/comprehension assertion, credentials, hooks or new authorization.
"""
import hashlib
import json
from task_supervisor import canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def material(control, task_id, role_id, role_version):
    control.gateway.assert_task_context(control.context, task_id)
    task = control.gateway.supervisor._task(task_id)
    spec = control.db.execute('SELECT goal,deliverables_json,acceptance_json FROM task_work_specs WHERE tenant_id=? AND task_id=?', (control.tenant_id, task_id)).fetchone()
    if spec is None:
        raise ValueError('TASK_WORK_SPEC_REQUIRED')
    rows = list(control.db.execute('''SELECT b.skill_id,b.skill_version,b.review_sha256 AS binding_review,s.review_sha256,s.content_json,s.content_sha256,s.state FROM role_skill_bindings b LEFT JOIN approved_skills s ON s.tenant_id=b.tenant_id AND s.skill_id=b.skill_id AND s.skill_version=b.skill_version WHERE b.tenant_id=? AND b.role_id=? AND b.role_version=? AND b.status='APPROVED' ORDER BY b.skill_id,b.skill_version''', (control.tenant_id, role_id, role_version)))
    if not rows:
        raise ValueError('REQUIRED_SKILL_BINDINGS_MISSING')
    skills = []
    applicable = []
    for row in rows:
        if row['state'] != 'APPROVED' or row['binding_review'] != row['review_sha256']:
            raise ValueError('SKILL_VERSION_REVOKED_OR_UNAVAILABLE')
        content = json.loads(row['content_json'])
        if digest(content) != row['content_sha256']:
            raise ValueError('SKILL_SOURCE_SHA_MISMATCH')
        skills.append({'skill_id': row['skill_id'], 'version': row['skill_version'], 'source_sha256': row['content_sha256'], 'content': content})
        rules = content.get('task_rules')
        if isinstance(rules, dict) and rules.get('task_id') == task_id:
            applicable.append(rules)
    if len(applicable) != 1:
        raise ValueError('EXACT_TASK_MODULE_RULES_REQUIRED')
    rules = applicable[0]
    if rules.get('work_spec_sha256') != digest(dict(spec)) or rules.get('task_spec_sha256') != task['spec_sha256']:
        raise ValueError('TASK_RULES_STALE_VERSION')
    module = rules.get('module_id')
    if not isinstance(module, str) or not module:
        raise ValueError('TASK_MODULE_REQUIRED')
    refs = rules.get('references', {})
    required = ['module_rules', 'requirements', 'checkpoint']
    if type(rules.get('ui_required')) is not bool:
        raise ValueError('UI_APPLICABILITY_REQUIRED')
    if rules['ui_required']:
        required += ['confirmed_ui']
    for kind in required:
        ref = refs.get(kind)
        if not isinstance(ref, dict) or not isinstance(ref.get('content'), str) or not ref['content'] or not ref.get('source_ref'):
            raise ValueError('TASK_REFERENCE_MISSING:' + kind)
        if ref.get('module_id') != module:
            raise ValueError('TASK_REFERENCE_WRONG_MODULE:' + kind)
        if hashlib.sha256(ref['content'].encode('utf-8')).hexdigest() != ref.get('source_sha256'):
            raise ValueError('TASK_REFERENCE_SHA_MISMATCH:' + kind)
    # References are admin-approved source material, NOT proof of customer consent.
    return {'task_id': task_id, 'attempt_id': task['attempt_id'], 'role_id': role_id,
            'role_version': role_version, 'module_id': module, 'skills': skills,
            'work_spec_sha256': digest(dict(spec))}


def _detail(control, task_id, principal, action, fingerprint):
    rows = control.db.execute('SELECT detail_json FROM model_audit WHERE tenant_id=? AND target_id=? AND principal_id=? AND action=?', (control.tenant_id, task_id, principal, action))
    return any(json.loads(row['detail_json']).get('material_sha256') == fingerprint for row in rows)


def read_material(control, task_id, role_id, role_version):
    body = material(control, task_id, role_id, role_version)
    sha = digest(body)
    principal = control._principal()
    if not _detail(control, task_id, principal, 'TASK_RULES_READ', sha):
        control._audit(principal, 'TASK_RULES_READ', task_id, {'material_sha256': sha}, control.clock())
        control.db.commit()
    return {'material': body, 'material_sha256': sha, 'state': 'READ_RESPONSE_NOT_LEARNING_PROOF'}


def acknowledge(control, task_id, role_id, role_version, material_sha256):
    body = material(control, task_id, role_id, role_version)
    sha = digest(body)
    principal = control._principal()
    if sha != material_sha256 or not _detail(control, task_id, principal, 'TASK_RULES_READ', sha):
        raise ValueError('CURRENT_AUTHENTICATED_READ_BACK_REQUIRED')
    duplicate = _detail(control, task_id, principal, 'TASK_RULES_READ_BACK', sha)
    if not duplicate:
        control._audit(principal, 'TASK_RULES_READ_BACK', task_id, {'material_sha256': sha}, control.clock())
        control.db.commit()
    return {'state': 'READ_BACK_RECORDED_NOT_COMPREHENSION_PROOF', 'material_sha256': sha, 'duplicate': duplicate}


def require_read_back(control, task_id, role_id, role_version, principal):
    sha = digest(material(control, task_id, role_id, role_version))
    if not _detail(control, task_id, principal, 'TASK_RULES_READ_BACK', sha):
        raise ValueError('ASSIGNED_AI_CURRENT_READ_BACK_REQUIRED')
    return sha
