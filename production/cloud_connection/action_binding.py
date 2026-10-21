"""Bind fixed project actions to ORIGINAL queue/gates; never execute a command.

The host-enrolled binding digest is authority input, not a client-supplied
approval. Preparing references neither creates a job nor grants installation.
"""
import hashlib
import re

from .queue import SHA, TOKEN
from .private_transfer import strict, check

OPERATIONS = ('b5_collect', 'website_baseline_collect', 'project_install',
              'project_update', 'project_backup', 'project_recover')
SEALED_REQUEST = 'conn-second-window-uk-20261021T162627Z'


def prepare(db, raw_binding, enrolled_sha, request_id, authenticated_actor_id, now):
    check(type(raw_binding) is bytes and len(raw_binding) <= 131072 and type(enrolled_sha) is str and SHA.fullmatch(enrolled_sha)
          and hashlib.sha256(raw_binding).hexdigest() == enrolled_sha, 'ACTION_ENROLLMENT_BINDING')
    check(type(now) is int and type(authenticated_actor_id) is int and authenticated_actor_id == 332398908, 'AUTHENTICATED_ACTION_ACTOR')
    check(type(request_id) is str and TOKEN.fullmatch(request_id) and request_id != SEALED_REQUEST, 'SEALED_OR_INVALID_REQUEST')
    b = strict(raw_binding)
    fields = {'schema', 'action_ref', 'project', 'target', 'operation', 'source_commit',
              'adapter_path', 'adapter_sha256', 'input_manifest_sha256', 'plan_sha256',
              'approval_ref', 'execution_identity', 'valid_from', 'valid_until'}
    check(type(b) is dict and set(b) == fields and type(b['schema']) is int and b['schema'] == 1, 'ACTION_BINDING_FIELDS')
    for k in ('action_ref', 'project', 'approval_ref'):
        check(type(b[k]) is str and TOKEN.fullmatch(b[k]), 'ACTION_REFERENCE')
    check(b['operation'] in OPERATIONS and b['target'] in ('uk', 'korea', 'domestic'), 'ACTION_NOT_ENROLLED')
    check(b['execution_identity'] in ('admin', 'root'), 'ACTION_IDENTITY')
    check(type(b['source_commit']) is str and re.fullmatch(r'[0-9a-f]{40}', b['source_commit']), 'ACTION_SOURCE')
    path = b['adapter_path']
    check(type(path) is str and not path.startswith('/') and len(path) <= 512
          and all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', p) and p not in ('.', '..') for p in path.split('/')), 'ACTION_ADAPTER_PATH')
    for k in ('adapter_sha256', 'input_manifest_sha256', 'plan_sha256'):
        check(type(b[k]) is str and SHA.fullmatch(b[k]), 'ACTION_ARTIFACT_PIN')
    check(type(b['valid_from']) is int and type(b['valid_until']) is int
          and 0 < b['valid_until'] - b['valid_from'] <= 86400
          and b['valid_from'] <= now < b['valid_until'], 'ACTION_WINDOW')
    # No bool flags, command, URL, unpinned args, retry count or replacement
    # ledger are accepted. This is a read of the original job, never an INSERT.
    row = db.execute('SELECT project,request_json,actor_id,state,invoke_id FROM connection_jobs WHERE request_id=?', (request_id,)).fetchone()
    check(row is not None, 'ORIGINAL_QUEUE_JOB_REQUIRED')
    check(type(row[1]) is str, 'ORIGINAL_ACTION_CORRUPT')
    r = strict(row[1].encode())
    check(type(r) is dict and row[2] == authenticated_actor_id and row[0] == b['project']
          and r.get('request_id') == request_id and r.get('project') == b['project']
          and r.get('target') == b['target'] and r.get('operation') == 'project_fixed_action'
          and r.get('arguments') == {'binding_sha256': enrolled_sha}, 'ORIGINAL_ACTION_SCOPE')
    state, invoke = row[3:]
    if state == 'SUCCESS':
        next_step = 'DONE_NO_REPLAY'
    elif state in ('DISPATCHING', 'UNKNOWN'):
        next_step = 'QUERY_ORIGINAL_INVOKE_ONLY' if invoke else 'HOLD_ORIGINAL_TRANSACTION_RECONCILIATION'
    elif state == 'READY':
        next_step = 'ORIGINAL_ADAPTER_AND_GATE_REQUIRED'
    else:
        next_step = 'HOLD_ORIGINAL_RECOVERY_POLICY'
    return {'state': 'BOUND_NOT_EXECUTED', 'request_id': request_id, 'project': b['project'],
            'target': b['target'], 'operation': b['operation'], 'binding_sha256': enrolled_sha,
            'source_commit': b['source_commit'], 'adapter_path': path,
            'adapter_sha256': b['adapter_sha256'], 'input_manifest_sha256': b['input_manifest_sha256'],
            'plan_sha256': b['plan_sha256'], 'execution_identity': b['execution_identity'],
            'invoke_id': invoke, 'next': next_step, 'dispatch_permitted': False,
            'writer_fence_and_transaction': 'VERIFY_IN_ORIGINAL_ADAPTER',
            'installation_permission': 'NOT_ISSUED'}
