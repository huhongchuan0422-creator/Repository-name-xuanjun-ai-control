"""Owner-root installs two fixed capabilities after exact independent grant approval.

No candidate install, root handoff, nft, credential, DB or service action occurs.
The private admission recorded here authorizes the channel only, not Phase-C.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import time
import urllib.request

HOST = 'iZmj7a5kwr75qc1tul4kf9Z'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}
DISPATCHER_SHA = 'a40371227b95a5fe78631b7c9e49c9b089dfeff8cf82175b9e8ca3f04c0c6497'
PROGRAM = '/usr/local/libexec/xuanjun-pr99-phase-c-channel.py'
WRAPPER = '/usr/local/sbin/xuanjun-pr99-phase-c'
POLICY = '/etc/sudoers.d/xuanjun-pr99-phase-c-channel'
WORK = '/var/lib/xuanjun-pr99-phase-c-channel-grant-v1'
MARKER = 'PR99_PHASE_C_CHANNEL_GRANT_APPROVAL_V1'
ACTION = 'PR99_KOREA_FIXED_PHASE_C_CHANNEL_GRANT_V1'
WRAPPER_BYTES = ("#!/bin/sh\nexec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C "
                 "/usr/bin/python3.11 -I -B " + PROGRAM + ' "$@"\n').encode()
POLICY_BYTES = ('githubrunner ALL=(root) NOPASSWD:NOSETENV: ' + WRAPPER + ' inspect\n' +
                'githubrunner ALL=(root) NOPASSWD:NOSETENV: ' + WRAPPER + ' install\n').encode()


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(rows):
        out = {}
        for k, v in rows:
            require(k not in out, 'DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def check_directory(path):
    path = Path(path)
    for p in list(reversed(path.parents)) + [path]:
        s = p.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
                'DIRECTORY_IDENTITY')


def read_once(path, limit):
    # Bootstrap input can be Owner-admin held, but is read once via O_NOFOLLOW
    # and compared to an independently approved exact digest before any use.
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= limit,
                'SOURCE_FILE_IDENTITY')
        data = bytearray()
        while True:
            block = os.read(fd, min(65536, limit + 1 - len(data)))
            if not block:
                break
            data.extend(block)
            require(len(data) <= limit, 'SOURCE_SIZE')
        after = os.fstat(fd)
        require((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'SOURCE_CHANGED')
        return bytes(data)
    finally:
        os.close(fd)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            fd = -1
            f.write(raw)
            f.flush()
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())
        fsync_dir(Path(path).parent)
    finally:
        if fd != -1:
            os.close(fd)


def approval_record(comment_id):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = ('https://api.github.com/repos/huhongchuan0422-creator/'
           'Repository-name-xuanjun-ai-control/issues/comments/' + str(comment_id))
    with opener.open(url, timeout=20) as r:
        raw = r.read(120001)
    require(len(raw) <= 120000, 'APPROVAL_SIZE')
    return parse(raw)


def verify(record, comment_id, body_sha, installer_raw, now):
    body = record['body']
    require(record['id'] == comment_id and sha(body.encode()) == body_sha, 'APPROVAL_BODY_PIN')
    require(record['issue_url'] == 'https://api.github.com/repos/huhongchuan0422-creator/'
            'Repository-name-xuanjun-ai-control/issues/99', 'APPROVAL_PR99_REQUIRED')
    begin, end = '<!-- ' + MARKER + '\n', '\n' + MARKER + ' -->'
    require(body.count(begin) == 1 and body.count(end) == 1, 'APPROVAL_MARKER')
    a = parse(body.split(begin)[1].split(end)[0])
    expected = dict(schema_version=1, decision='APPROVED_WITH_EXACT_PRECONDITIONS',
        action=ACTION, host=HOST, max_attempts=1, approval_comment_id=comment_id,
        dispatcher_sha256=DISPATCHER_SHA, installer_sha256=sha(installer_raw),
        wrapper_sha256=sha(WRAPPER_BYTES), sudoers_sha256=sha(POLICY_BYTES),
        runner='githubrunner', runner_uid=1001, arbitrary_root_commands_allowed=False,
        phase_c_install_allowed=False, service_actions_allowed=False,
        network_changes_allowed=False, credentials_allowed=False,
        database_export_allowed=False, writer_allowed=False)
    require(set(a) == set(expected) | {'issued_at', 'expires_at', 'source_commit'}, 'APPROVAL_FIELDS')
    for k, v in expected.items():
        require(type(a[k]) is type(v) and a[k] == v, 'APPROVAL_BINDING:' + k)
    require(re.fullmatch('[0-9a-f]{40}', a['source_commit']) is not None, 'SOURCE_COMMIT')
    require(type(a['issued_at']) is int and type(a['expires_at']) is int and
            a['issued_at'] <= now < a['expires_at'] and
            0 < a['expires_at'] - a['issued_at'] <= 43200, 'APPROVAL_EXPIRED')
    return a


class Context:
    def path(self, value):
        return Path(value)

    def now(self):
        return time.time()

    def identity(self):
        require(os.geteuid() == 0 and os.uname().nodename == HOST, 'ROOT_HOST_REQUIRED')
        allowed = dict(ENV)
        if os.environ.get('LC_CTYPE') == 'C.UTF-8':
            allowed['LC_CTYPE'] = 'C.UTF-8'
        require(dict(os.environ) == allowed and sys.version_info[:2] == (3, 11), 'CLEAN_PYTHON_ENV')
        user = pwd.getpwnam('githubrunner')
        require(user.pw_uid == 1001, 'RUNNER_IDENTITY')

    def current(self, comment_id):
        return approval_record(comment_id)

    def visudo(self, path=None):
        args = ['/usr/sbin/visudo', '-c'] if path is None else ['/usr/sbin/visudo', '-cf', str(path)]
        s = os.lstat(args[0])
        require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
                'VISUDO_IDENTITY')
        r = subprocess.run(args, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=15)
        require(r.returncode == 0, 'SUDOERS_VALIDATION')


def grant(dispatcher, comment_id, body_sha, installer_raw, ctx=None):
    ctx = ctx or Context()
    ctx.identity()
    require(type(comment_id) is int and comment_id > 0 and
            re.fullmatch('[0-9a-f]{64}', body_sha) is not None, 'APPROVAL_ARGUMENTS')
    data = read_once(dispatcher, 65536)
    require(sha(data) == DISPATCHER_SHA, 'DISPATCHER_BYTES')
    compile(data, 'approved_fixed_channel', 'exec')  # Never import input code.
    record = ctx.current(comment_id)
    a = verify(record, comment_id, body_sha, installer_raw, ctx.now())
    targets = (PROGRAM, WRAPPER, POLICY, WORK)
    for raw in targets:
        p = ctx.path(raw)
        check_directory(p.parent)
        require(not os.path.lexists(p), 'EXISTING_CHANNEL_OBJECT')
    ctx.visudo()
    # Revalidate current exact authority immediately before a permanent claim.
    verify(ctx.current(comment_id), comment_id, body_sha, installer_raw, ctx.now())
    work = ctx.path(WORK)
    work.mkdir(mode=0o700)
    work.chmod(0o700)
    fsync_dir(work.parent)
    write_new(work / 'consumed-approval.json',
              json.dumps(dict(approval_comment_id=comment_id, approval_body_sha256=body_sha,
                              approval_body=record['body']), sort_keys=True).encode(), 0o600)
    status = dict(status='INSTALLING_CHANNEL', approval_comment_id=comment_id,
                  phase_c_install_called=False, service_actions=0, retry_allowed=False)
    try:
        candidate = work / 'sudoers.candidate'
        write_new(candidate, POLICY_BYTES, 0o400)
        ctx.visudo(candidate)
        require(ctx.now() < a['expires_at'], 'APPROVAL_EXPIRED_BEFORE_WRITE')
        for raw, content, mode in ((PROGRAM, data, 0o444), (WRAPPER, WRAPPER_BYTES, 0o755),
                                   (POLICY, POLICY_BYTES, 0o440)):
            write_new(ctx.path(raw), content, mode)
        ctx.visudo()
        for raw, content, mode in ((PROGRAM, data, 0o444), (WRAPPER, WRAPPER_BYTES, 0o755),
                                   (POLICY, POLICY_BYTES, 0o440)):
            p = ctx.path(raw)
            s = p.lstat()
            require(p.read_bytes() == content and s.st_uid == 0 and s.st_nlink == 1 and
                    stat.S_IMODE(s.st_mode) == mode, 'INSTALLED_CHANNEL_CHANGED')
        status['status'] = 'FIXED_CHANNEL_READY_NO_PHASE_C_EXECUTION'
        write_new(work / 'receipt.json', json.dumps(status, sort_keys=True).encode(), 0o600)
        return status
    except BaseException as error:
        status.update(status='HOLD_PRESERVE_EVIDENCE', error_type=type(error).__name__)
        write_new(work / 'failure.json', json.dumps(status, sort_keys=True).encode(), 0o600)
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dispatcher', required=True)
    p.add_argument('--approval-id', type=int, required=True)
    p.add_argument('--approval-sha256', required=True)
    a = p.parse_args()
    os.umask(0o077)
    return grant(a.dispatcher, a.approval_id, a.approval_sha256,
                 read_once(__file__, 65536))


if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except BaseException as error:
        print(json.dumps(dict(status='HOLD_CHANNEL_GRANT', error_type=type(error).__name__,
                              retry_allowed=False)), file=sys.stderr)
        sys.exit(2)
