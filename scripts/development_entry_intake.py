"""Three native entrants share existing GitHub task; no ledger or model effects."""
import hashlib
import json
import os
import re
import stat
import subprocess
import urllib.request

from native_syntax_intake import syntax_receipt

MARKER = re.compile(r'<!-- XJ_DEV_ENTRY (\{[^\n]*\}) -->')
ENTRIES = {'WORK': 'WORK_NATIVE', 'CHATGPT': 'CHATGPT_NATIVE', 'DOTS': 'DOTS_NATIVE'}
FIELDS = {'schema', 'entry', 'execution_path', 'task_id', 'spec_sha256',
          'checkpoint_sha256', 'target_repository', 'target_base_sha',
          'code_commit', 'event', 'attempt_id', 'lease_id', 'fence', 'epoch',
          'caller_id', 'run_id', 'session_id', 'gateway_id',
          'lock_provider_id'}
EVENTS = {'RECEIVED', 'CODE_READY', 'STOPPED', 'HANDOFF', 'HOLD'}
TASK = 'XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1'


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def validate_event(event, control_repository, trusted_owner):
    # Actor and destination come from the GitHub event, never the message.
    issue = event.get('issue', {})
    comment = event.get('comment', {})
    if (event.get('repository', {}).get('full_name') != control_repository
            or issue.get('number') != 17 or 'pull_request' not in issue
            or event.get('sender', {}).get('login') != trusted_owner
            or comment.get('user', {}).get('login') != trusted_owner
            or event.get('action') != 'created'):
        raise ValueError('UNTRUSTED_EVENT_OR_TASK_DESTINATION')
    body = comment.get('body', '')
    if not isinstance(body, str) or len(body.encode('utf-8')) > 16384:
        raise ValueError('BOUNDED_ENTRY_MESSAGE_REQUIRED')
    matches = MARKER.findall(body)
    if len(matches) != 1:
        raise ValueError('EXACT_SINGLE_ENTRY_MARKER_REQUIRED')
    value = json.loads(matches[0], object_pairs_hook=_unique)
    if set(value) != FIELDS or type(value.get('schema')) is not int or value['schema'] != 1:
        raise ValueError('EXACT_ENTRY_SCHEMA_REQUIRED')
    if value.get('entry') not in ENTRIES or value.get('execution_path') != ENTRIES[value['entry']]:
        raise ValueError('NATIVE_ENTRY_REQUIRED_NO_HIDDEN_CODEX')
    if value.get('task_id') != TASK or value.get('event') not in EVENTS:
        raise ValueError('EXISTING_TASK_AND_EVENT_REQUIRED')
    # Receipt intake accepts explicit destinations, but never authorizes them.
    if not isinstance(value.get('target_repository'), str) or not re.fullmatch(
            r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', value['target_repository']):
        raise ValueError('EXPLICIT_TARGET_REPOSITORY_REQUIRED')
    for key, length in [('spec_sha256', 64), ('checkpoint_sha256', 64),
                        ('target_base_sha', 40), ('code_commit', 40)]:
        if not isinstance(value.get(key), str) or not re.fullmatch('[0-9a-f]{%d}' % length, value[key]):
            raise ValueError('EXACT_HASH_BINDING_REQUIRED')
    if (not isinstance(value.get('attempt_id'), str) or not value['attempt_id']
            or not isinstance(value.get('lease_id'), str) or not value['lease_id']
            or type(value.get('fence')) is not int or value['fence'] < 1
            or type(value.get('epoch')) is not int or value['epoch'] < 1
            or any(not isinstance(value.get(name), str) or not value[name]
                   for name in ('caller_id','run_id','session_id','gateway_id',
                                'lock_provider_id'))):
        raise ValueError('EXACT_WRITER_BINDING_REQUIRED')
    if type(comment.get('id')) is not int or comment['id'] < 1:
        raise ValueError('GITHUB_COMMENT_ID_REQUIRED')
    return dict(value, source_comment_id=comment['id'],
                status='RECEIPT_VALIDATED_NOT_ADMITTED',
                native_identity='CLAIMED_NOT_VERIFIED', quota_attribution='UNKNOWN',
                authority_effect='NONE',
                required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE')


def bind_validated_receipt(supervisor, receipt, files=None):
    """Bind one validated intake receipt to current canonical task state.

    This does not create authority. CODE_READY additionally persists an exact
    candidate manifest under the already-valid canonical writer generation.
    """
    if (not isinstance(receipt, dict)
            or receipt.get('status') != 'RECEIPT_VALIDATED_NOT_ADMITTED'
            or receipt.get('authority_effect') != 'NONE'):
        raise ValueError('VALIDATED_ENTRY_RECEIPT_REQUIRED')
    task = supervisor._task(receipt.get('task_id'))
    contract = supervisor.development_contract(task['task_id'])
    expected = {
        'task_id': task['task_id'],
        'spec_sha256': task['spec_sha256'],
        'checkpoint_sha256': task['checkpoint_sha256'],
        'target_repository': contract['target_repository'],
        'target_base_sha': contract['target_base_sha'],
        'entry': task['entry'],
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError('CANONICAL_INTAKE_BINDING_MISMATCH')
    if receipt.get('event') != 'CODE_READY':
        return {'state': 'CANONICAL_MATCH_NOT_ADMITTED',
                'authority_effect': 'NONE'}
    if (receipt.get('attempt_id') != task['attempt_id']
            or receipt.get('lease_id') != task['lease_id']
            or receipt.get('fence') != task['fence']
            or receipt.get('epoch') != task['epoch']):
        raise ValueError('CURRENT_ATTEMPT_BINDING_REQUIRED')
    if not isinstance(files, dict) or not files:
        raise ValueError('CODE_READY_FILES_REQUIRED')
    manifest = {}
    for path, raw in files.items():
        if (not isinstance(path, str)
                or not re.fullmatch(r'[A-Za-z0-9_./-]+', path)
                or any(part in ('', '.', '..') for part in path.split('/'))
                or type(raw) is not bytes):
            raise ValueError('CANONICAL_CODE_READY_FILE_REQUIRED')
        manifest[path] = hashlib.sha256(raw).hexdigest()
    return supervisor.bind_development_candidate(receipt, manifest)


def _git_remote_repository(root):
    raw = subprocess.check_output(
        ['git','-C',root,'remote','get-url','origin'],
        stderr=subprocess.DEVNULL).decode('utf-8','strict').strip()
    patterns = (
        r'https://github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+?)(?:\.git)?    with open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8') as stream:
        event = json.load(stream)
    body = event.get('comment', {}).get('body', '')
    if 'XJ_DEV_ENTRY ' not in body:
        return
    repo = os.environ['GITHUB_REPOSITORY']
    owner = repo.split('/')[0]
    # Ignore untrusted sources without posting or replying to arbitrary issues.
    if (event.get('sender', {}).get('login') != owner
            or event.get('comment', {}).get('user', {}).get('login') != owner
            or event.get('issue', {}).get('number') != 17
            or 'pull_request' not in event.get('issue', {})):
        return
    try:
        receipt = validate_event(event, repo, owner)
        if receipt['event'] == 'CODE_READY':
            try:
                receipt['syntax_gate'] = syntax_receipt(receipt, repo,
                    os.environ['GITHUB_TOKEN'],
                    typescript_module=os.environ.get('XJ_TYPESCRIPT_MODULE'))
            except Exception:
                # Do not emit server errors, credential values or source snippets.
                receipt['syntax_gate'] = {'state': 'HOLD_SYNTAX_INTAKE_ERROR',
                    'authority_effect': 'NONE', 'code_executed': False}
            try:
                receipt['canonical_gate'] = bind_from_controlled_environment(receipt)
            except Exception:
                receipt['canonical_gate'] = {
                    'state': 'HOLD_CANONICAL_SOURCE_BINDING_ERROR',
                    'authority_effect': 'NONE'}
    except (ValueError, TypeError, KeyError):
        receipt = dict(status='REJECTED_INVALID_ENTRY_ENVELOPE',
                       source_comment_id=event['comment']['id'], authority_effect='NONE')
    marker = '<!-- XJ_DEV_ENTRY_RECEIPT %s -->' % json.dumps(receipt, sort_keys=True)
    request = urllib.request.Request(
        'https://api.github.com/repos/' + repo + '/issues/17/comments',
        data=json.dumps({'body': marker + '\n::SKIP_COMPLETION::\n'
             'Mechanical entry receipt only. No writer, stop, handoff, code execution or quota verification.'}).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json', 'User-Agent': 'xuanjun-entry-intake'},
        method='POST')
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 201:
            raise RuntimeError('RECEIPT_WRITE_FAILED')
    print(receipt['status'])


if __name__ == '__main__':
    main()

,
        r'git@github\.com:([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+?)(?:\.git)?    with open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8') as stream:
        event = json.load(stream)
    body = event.get('comment', {}).get('body', '')
    if 'XJ_DEV_ENTRY ' not in body:
        return
    repo = os.environ['GITHUB_REPOSITORY']
    owner = repo.split('/')[0]
    # Ignore untrusted sources without posting or replying to arbitrary issues.
    if (event.get('sender', {}).get('login') != owner
            or event.get('comment', {}).get('user', {}).get('login') != owner
            or event.get('issue', {}).get('number') != 17
            or 'pull_request' not in event.get('issue', {})):
        return
    try:
        receipt = validate_event(event, repo, owner)
        if receipt['event'] == 'CODE_READY':
            try:
                receipt['syntax_gate'] = syntax_receipt(receipt, repo,
                    os.environ['GITHUB_TOKEN'],
                    typescript_module=os.environ.get('XJ_TYPESCRIPT_MODULE'))
            except Exception:
                # Do not emit server errors, credential values or source snippets.
                receipt['syntax_gate'] = {'state': 'HOLD_SYNTAX_INTAKE_ERROR',
                    'authority_effect': 'NONE', 'code_executed': False}
    except (ValueError, TypeError, KeyError):
        receipt = dict(status='REJECTED_INVALID_ENTRY_ENVELOPE',
                       source_comment_id=event['comment']['id'], authority_effect='NONE')
    marker = '<!-- XJ_DEV_ENTRY_RECEIPT %s -->' % json.dumps(receipt, sort_keys=True)
    request = urllib.request.Request(
        'https://api.github.com/repos/' + repo + '/issues/17/comments',
        data=json.dumps({'body': marker + '\n::SKIP_COMPLETION::\n'
             'Mechanical entry receipt only. No writer, stop, handoff, code execution or quota verification.'}).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json', 'User-Agent': 'xuanjun-entry-intake'},
        method='POST')
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 201:
            raise RuntimeError('RECEIPT_WRITE_FAILED')
    print(receipt['status'])


if __name__ == '__main__':
    main()

,
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, raw)
        if match:
            return match.group(1)
    raise ValueError('CANONICAL_GIT_REMOTE_REQUIRED')


def _controlled_candidate_files(supervisor, receipt, root):
    if (not isinstance(root, str) or not root
            or not os.path.isdir(root)
            or os.path.realpath(root) != os.path.abspath(root)):
        raise ValueError('CANONICAL_CANDIDATE_ROOT_REQUIRED')
    observed_repo = _git_remote_repository(root)
    observed_head = subprocess.check_output(
        ['git','-C',root,'rev-parse','HEAD'],
        stderr=subprocess.DEVNULL).decode('ascii','strict').strip()
    if (observed_repo != receipt['target_repository']
            or observed_head != receipt['code_commit']):
        raise ValueError('CANDIDATE_CHECKOUT_IDENTITY_MISMATCH')
    contract = supervisor.development_contract(receipt['task_id'])
    result = {}
    root_real = os.path.realpath(root)
    for path in contract['allowed_files']:
        full = os.path.join(root, path)
        real = os.path.realpath(full)
        if not real.startswith(root_real + os.sep):
            raise ValueError('CANDIDATE_FILE_ESCAPES_ROOT')
        info = os.lstat(full)
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError('CANDIDATE_FILE_NOT_REGULAR')
        with open(full, 'rb') as stream:
            result[path] = stream.read()
    return result


def bind_from_controlled_environment(receipt):
    """Actual source-controlled intake call point.

    No ledger is created here. If an existing canonical DB and exact local Git
    checkout are not explicitly supplied, the caller receives HOLD with no
    authority effect.
    """
    ledger = os.environ.get('XJ_CANONICAL_LEDGER_PATH')
    root = os.environ.get('XJ_CANDIDATE_ROOT')
    if not ledger or not root:
        return {'state': 'HOLD_CANONICAL_SOURCE_INPUT_UNAVAILABLE',
                'authority_effect': 'NONE'}
    if not os.path.isfile(ledger):
        return {'state': 'HOLD_CANONICAL_LEDGER_UNAVAILABLE',
                'authority_effect': 'NONE'}
    from task_supervisor import Supervisor
    supervisor = Supervisor(ledger)
    try:
        files = _controlled_candidate_files(supervisor, receipt, root)
        bound = bind_validated_receipt(supervisor, receipt, files)
        return {'state': 'CANONICAL_SOURCE_BOUND',
                'authority_effect': 'NONE',
                'candidate_event_id': bound.get('candidate_event_id'),
                'candidate_sha256': bound.get('candidate_sha256'),
                'duplicate': bound.get('duplicate', False)}
    finally:
        supervisor.close()


def main():
    with open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8') as stream:
        event = json.load(stream)
    body = event.get('comment', {}).get('body', '')
    if 'XJ_DEV_ENTRY ' not in body:
        return
    repo = os.environ['GITHUB_REPOSITORY']
    owner = repo.split('/')[0]
    # Ignore untrusted sources without posting or replying to arbitrary issues.
    if (event.get('sender', {}).get('login') != owner
            or event.get('comment', {}).get('user', {}).get('login') != owner
            or event.get('issue', {}).get('number') != 17
            or 'pull_request' not in event.get('issue', {})):
        return
    try:
        receipt = validate_event(event, repo, owner)
        if receipt['event'] == 'CODE_READY':
            try:
                receipt['syntax_gate'] = syntax_receipt(receipt, repo,
                    os.environ['GITHUB_TOKEN'],
                    typescript_module=os.environ.get('XJ_TYPESCRIPT_MODULE'))
            except Exception:
                # Do not emit server errors, credential values or source snippets.
                receipt['syntax_gate'] = {'state': 'HOLD_SYNTAX_INTAKE_ERROR',
                    'authority_effect': 'NONE', 'code_executed': False}
    except (ValueError, TypeError, KeyError):
        receipt = dict(status='REJECTED_INVALID_ENTRY_ENVELOPE',
                       source_comment_id=event['comment']['id'], authority_effect='NONE')
    marker = '<!-- XJ_DEV_ENTRY_RECEIPT %s -->' % json.dumps(receipt, sort_keys=True)
    request = urllib.request.Request(
        'https://api.github.com/repos/' + repo + '/issues/17/comments',
        data=json.dumps({'body': marker + '\n::SKIP_COMPLETION::\n'
             'Mechanical entry receipt only. No writer, stop, handoff, code execution or quota verification.'}).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json', 'User-Agent': 'xuanjun-entry-intake'},
        method='POST')
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 201:
            raise RuntimeError('RECEIPT_WRITE_FAILED')
    print(receipt['status'])


if __name__ == '__main__':
    main()

