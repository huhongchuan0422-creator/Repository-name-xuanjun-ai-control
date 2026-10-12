"""Three native entrants share existing GitHub task; no ledger or model effects."""
import json
import os
import re
import urllib.request

MARKER = re.compile(r'<!-- XJ_DEV_ENTRY (\{[^\n]*\}) -->')
ENTRIES = {'WORK': 'WORK_NATIVE', 'CHATGPT': 'CHATGPT_NATIVE', 'DOTS': 'DOTS_NATIVE'}
FIELDS = {'schema', 'entry', 'execution_path', 'task_id', 'spec_sha256',
          'checkpoint_sha256', 'target_repository', 'target_base_sha',
          'code_commit', 'event'}
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
    if type(comment.get('id')) is not int or comment['id'] < 1:
        raise ValueError('GITHUB_COMMENT_ID_REQUIRED')
    return dict(value, source_comment_id=comment['id'],
                status='RECEIPT_VALIDATED_NOT_ADMITTED',
                native_identity='CLAIMED_NOT_VERIFIED', quota_attribution='UNKNOWN',
                authority_effect='NONE',
                required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE')


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
