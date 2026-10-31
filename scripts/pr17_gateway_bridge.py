"""PR17 protected inbox and result publisher for the existing Gateway.

This module creates no task registry and grants no writer authority.  It moves
one already validated XJ_DEV_ENTRY envelope into a protected local inbox,
binds it through the existing canonical Gateway admission, and publishes the
result from a durable outbox with a GitHub comment marker used for recovery.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import urllib.request

from development_entry_intake import bind_from_controlled_environment, validate_event


RESULT_MARKER = '<!-- XJ_PR17_GATEWAY_RESULT %s -->'
SAFE_NAME = re.compile(r'^[0-9a-f]{64}\.json$')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('ascii')).hexdigest()


def _protected_directory(path):
    if (not isinstance(path, str) or not os.path.isabs(path)
            or os.path.realpath(path) != path):
        raise ValueError('ABSOLUTE_PROTECTED_DIRECTORY_REQUIRED')
    info = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o022):
        raise ValueError('PROTECTED_DIRECTORY_CUSTODY_REQUIRED')
    return path


def _atomic_json(directory, name, value):
    directory = _protected_directory(directory)
    if not SAFE_NAME.fullmatch(name):
        raise ValueError('CONTENT_ADDRESSED_FILENAME_REQUIRED')
    final = os.path.join(directory, name)
    raw = (canonical(value) + '\n').encode('ascii')
    if os.path.exists(final):
        with open(final, 'rb') as handle:
            if handle.read() != raw:
                raise ValueError('CONTENT_ADDRESSED_RECORD_CONFLICT')
        return final, True
    temporary = os.path.join(directory, '.' + name + '.tmp-%d' % os.getpid())
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, final)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return final, False


def intake_event(event, repository, owner, inbox_directory):
    receipt = validate_event(event, repository, owner)
    envelope = {
        'schema': 1,
        'kind': 'PR17_PROTECTED_GATEWAY_INBOX',
        'repository': repository,
        'pr': 17,
        'source_comment_id': receipt['source_comment_id'],
        'receipt': receipt,
        'authority_effect': 'NONE',
    }
    envelope_id = digest(envelope)
    path, duplicate = _atomic_json(inbox_directory, envelope_id + '.json', envelope)
    return {'state': 'PROTECTED_INBOX_RECEIVED', 'envelope_id': envelope_id,
            'path': path, 'duplicate': duplicate, 'authority_effect': 'NONE'}


def _read_record(path, expected_kind):
    if (not isinstance(path, str) or not os.path.isabs(path)
            or os.path.realpath(path) != path
            or not SAFE_NAME.fullmatch(os.path.basename(path))):
        raise ValueError('PROTECTED_RECORD_PATH_REQUIRED')
    directory = _protected_directory(os.path.dirname(path))
    info = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError('PROTECTED_RECORD_CUSTODY_REQUIRED')
    with open(path, 'rb') as handle:
        raw = handle.read()
    if len(raw) > 65536:
        raise ValueError('BOUNDED_PROTECTED_RECORD_REQUIRED')
    value = json.loads(raw.decode('ascii'))
    if value.get('schema') != 1 or value.get('kind') != expected_kind:
        raise ValueError('PROTECTED_RECORD_SCHEMA_REQUIRED')
    expected = os.path.basename(path)[:-5]
    if digest(value) != expected:
        raise ValueError('PROTECTED_RECORD_DIGEST_MISMATCH')
    return value, directory


def consume_inbox(path, outbox_directory, binder=bind_from_controlled_environment):
    envelope, _ = _read_record(path, 'PR17_PROTECTED_GATEWAY_INBOX')
    gate = binder(envelope['receipt'])
    result = {
        'schema': 1,
        'kind': 'PR17_GATEWAY_RESULT_OUTBOX',
        'repository': envelope['repository'],
        'pr': 17,
        'envelope_id': os.path.basename(path)[:-5],
        'source_comment_id': envelope['source_comment_id'],
        'task_id': envelope['receipt']['task_id'],
        'attempt_id': envelope['receipt']['attempt_id'],
        'spec_sha256': envelope['receipt']['spec_sha256'],
        'checkpoint_sha256': envelope['receipt']['checkpoint_sha256'],
        'gateway_result': gate,
        'authority_effect': 'NONE',
    }
    result_id = digest(result)
    output, duplicate = _atomic_json(outbox_directory, result_id + '.json', result)
    return {'state': 'GATEWAY_RESULT_DURABLE', 'result_id': result_id,
            'path': output, 'duplicate': duplicate, 'authority_effect': 'NONE'}


def _github_request(token, repository, suffix, method='GET', body=None):
    headers = {'Authorization': 'Bearer ' + token,
               'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'xuanjun-pr17-gateway-publisher'}
    data = None if body is None else json.dumps(body).encode('utf-8')
    if data is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(
        'https://api.github.com/repos/' + repository + suffix,
        data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def github_publish(token, repository, marker, body):
    for page in range(1, 11):
        rows = _github_request(token, repository,
                               '/issues/17/comments?per_page=100&page=%d' % page)
        if not isinstance(rows, list):
            raise ValueError('INVALID_GITHUB_COMMENTS_RESPONSE')
        for row in rows:
            if marker in (row.get('body') or ''):
                return {'comment_id': row['id'], 'duplicate': True}
        if len(rows) < 100:
            break
    row = _github_request(token, repository, '/issues/17/comments', 'POST',
                          {'body': marker + '\n::SKIP_COMPLETION::\n' + body})
    if type(row.get('id')) is not int:
        raise ValueError('GITHUB_COMMENT_RECEIPT_REQUIRED')
    return {'comment_id': row['id'], 'duplicate': False}


def publish_result(path, sent_directory, token, poster=github_publish):
    result, _ = _read_record(path, 'PR17_GATEWAY_RESULT_OUTBOX')
    result_id = os.path.basename(path)[:-5]
    marker = RESULT_MARKER % result_id
    body = canonical(result)
    published = poster(token, result['repository'], marker, body)
    sent = dict(result, result_id=result_id, publication={
        'state': 'PR17_COMMENT_PUBLISHED',
        'comment_id': published['comment_id'],
    })
    sent_id = digest(sent)
    sent_path, duplicate = _atomic_json(sent_directory, sent_id + '.json', sent)
    return {'state': 'PR17_RESULT_PUBLISHED', 'result_id': result_id,
            'sent_id': sent_id, 'sent_path': sent_path,
            'comment_id': published['comment_id'], 'duplicate': duplicate,
            'recovered_existing_comment': published.get('duplicate', False)}


def _next_record(directory, completed_directory=None, relation=None):
    directory = _protected_directory(directory)
    completed = []
    if completed_directory is not None:
        completed_directory = _protected_directory(completed_directory)
        for name in sorted(os.listdir(completed_directory)):
            if SAFE_NAME.fullmatch(name):
                try:
                    with open(os.path.join(completed_directory, name), 'rb') as handle:
                        completed.append(json.loads(handle.read().decode('ascii')))
                except (OSError, ValueError, TypeError):
                    raise ValueError('INVALID_COMPLETION_RECORD')
    for name in sorted(os.listdir(directory)):
        if not SAFE_NAME.fullmatch(name):
            continue
        path = os.path.join(directory, name)
        if relation is None:
            return path
        value, _ = _read_record(path, relation[0])
        source_value = (os.path.basename(path)[:-5] if relation[2] is None
                        else value.get(relation[2]))
        if not any(done.get(relation[1]) == source_value
                   for done in completed):
            return path
    return None


def _credential_token():
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    path = os.environ.get('GITHUB_TOKEN_FILE')
    if not path or not os.path.isabs(path):
        raise ValueError('GITHUB_TOKEN_CREDENTIAL_REQUIRED')
    with open(path, 'r', encoding='ascii') as handle:
        token = handle.read().strip()
    if not token:
        raise ValueError('GITHUB_TOKEN_CREDENTIAL_REQUIRED')
    return token


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('intake', 'consume', 'publish'))
    parser.add_argument('--path')
    args = parser.parse_args(argv)
    if args.action == 'intake':
        with open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8') as handle:
            event = json.load(handle)
        repo = os.environ['GITHUB_REPOSITORY']
        value = intake_event(event, repo, repo.split('/')[0],
                             os.environ['XJ_PR17_INBOX'])
    elif args.action == 'consume':
        path = args.path or _next_record(
            os.environ['XJ_PR17_INBOX'], os.environ['XJ_PR17_OUTBOX'],
            ('PR17_PROTECTED_GATEWAY_INBOX', 'envelope_id', None))
        if path is None:
            value = {'state': 'NO_PENDING_INBOX'}
        else:
            value = consume_inbox(path, os.environ['XJ_PR17_OUTBOX'])
    else:
        path = args.path or _next_record(
            os.environ['XJ_PR17_OUTBOX'], os.environ['XJ_PR17_SENT'],
            ('PR17_GATEWAY_RESULT_OUTBOX', 'result_id', None))
        if path is None:
            value = {'state': 'NO_PENDING_OUTBOX'}
        else:
            value = publish_result(path, os.environ['XJ_PR17_SENT'],
                                   _credential_token())
    print(canonical(value))


if __name__ == '__main__':
    main()
