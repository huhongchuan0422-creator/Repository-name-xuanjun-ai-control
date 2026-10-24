#!/bin/bash
# ROOT REVIEW CANDIDATE ONLY. Run once on the original UK host only after review.
# Complete embedded Python; no install, download, temporary file or dependency.
set -eu
if [ "$#" -ne 0 ]; then
  printf '%s\n' 'COMMUNITY_READONLY_ARGUMENTS_DENIED'
  exit 2
fi
community_readonly_exit=0
/usr/bin/python3 -I -B -S - <<'COMMUNITY_READONLY_PY' || community_readonly_exit=$?
"""Fixed UK community read-only observation candidate. Never a deploy/preview gate.

Python 3.6 stdlib. No CLI inputs, environment reads, secret/DB body reads or writes.
The accompanying shell embeds these exact bytes and only invokes this main.
"""
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
DOCKER = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']
CURRENT = 'xuanjun-community-preview'
ROLLBACK = 'xuanjun-community-preview-before-2330dd55'
ROOT = '/var/lib/xuanjun-community-preview'
RUN = '/run/xuanjun-community-preview'
STAGE = '/opt/xuanjun-community-preview/roles-upgrade-2330dd55'
URL = 'https://uk.wenwenwenyiyiyi.work/community-preview/community/health'
ROOT_ANCHOR = '/'
ROOT_UID = 0
PROJECT_UID = 10001
UNKNOWN = 'UNKNOWN'
SHA = re.compile(r'^[0-9a-f]{40}$')
IMAGE = re.compile(r'^sha256:[0-9a-f]{64}$')
CID = re.compile(r'^[0-9a-f]{64}$')
DIGEST = CID
META_PATHS = {'config_directory': ROOT+'/config', 'data_directory': ROOT+'/data',
              'runtime_directory': RUN, 'host_plan_reference': ROOT+'/config/host.json',
              'center_keys_reference': ROOT+'/config/center-keys.json',
              'wechat_secret_reference': ROOT+'/config/wechat.json'}
ROUTE_PATHS = {'community_route': '/etc/nginx/community-preview.inc',
               'shared_vhost_file_digest_only': '/etc/nginx/conf.d/xuanjun-p2-owner.conf'}
TRANSACTION_PATHS = {'attempt': STAGE+'/attempt.json',
                     'resume_receipt': STAGE+'/resume-01/receipt.json'}

class Hold(Exception):
    pass


class TotalDeadline(BaseException):
    pass


def owner_for(path):
    return PROJECT_UID if path in (ROOT+'/config', ROOT+'/data', RUN) else ROOT_UID


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)


def protected(s, uid, directory=False):
    if s.st_uid not in (uid if isinstance(uid, tuple) else (uid,)) or s.st_mode & 0o022:
        raise Hold('UNPROTECTED_PATH')
    if directory and not stat.S_ISDIR(s.st_mode):
        raise Hold('DIRECTORY_REQUIRED')


def parent_fd(path):
    if not isinstance(path, str) or not path.startswith('/') or any(p in ('', '.', '..') for p in path.split('/')[1:]):
        raise Hold('FIXED_ABSOLUTE_PATH_REQUIRED')
    fd = os.open(ROOT_ANCHOR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        protected(os.fstat(fd), ROOT_UID, True)
        parts = path.split('/')[1:]
        current = ''
        for part in parts[:-1]:
            current += '/'+part
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                protected(os.fstat(child), owner_for(current), True)
            except BaseException:
                os.close(child)
                raise
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def safe_file(path, body=False, limit=65536):
    """Dir-fd traversal; metadata only for secret/data references.

    Content reads are reserved to two route files and two transaction receipts.
    """
    if body and path not in set(ROUTE_PATHS.values()) | set(TRANSACTION_PATHS.values()):
        raise Hold('BODY_READ_OUT_OF_SCOPE')
    parent, name = parent_fd(path)
    fd = None
    try:
        parent_before = identity(os.fstat(parent))
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        allowed = (ROOT_UID, PROJECT_UID) if path in META_PATHS.values() and path.startswith(ROOT+'/config/') else owner_for(path)
        protected(before, allowed, stat.S_ISDIR(before.st_mode))
        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):
            raise Hold('REGULAR_FILE_OR_DIRECTORY_REQUIRED')
        expected_directory = path in (ROOT+'/config', ROOT+'/data', RUN)
        if (path in META_PATHS.values() and stat.S_ISDIR(before.st_mode) != expected_directory) or (path == '/usr/bin/docker' and not stat.S_ISREG(before.st_mode)):
            raise Hold('EXPECTED_REFERENCE_TYPE')
        result = {'status': 'OBSERVED', 'type': 'DIRECTORY' if stat.S_ISDIR(before.st_mode) else 'REGULAR_FILE',
                  'uid': before.st_uid, 'gid': before.st_gid, 'mode': format(stat.S_IMODE(before.st_mode), '04o'),
                  'device': before.st_dev, 'inode': before.st_ino, 'nlink': before.st_nlink, 'size': before.st_size,
                  'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns}
        if body:
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise Hold('BODY_FILE_BOUNDARY')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            if identity(os.fstat(fd)) != identity(before):
                raise Hold('FILE_CHANGED')
            pieces = []
            used = 0
            while used <= limit:
                chunk = os.read(fd, min(4096, limit+1-used))
                if not chunk:
                    break
                pieces.append(chunk)
                used += len(chunk)
            raw = b''.join(pieces)
            if used > limit or len(raw) != before.st_size or identity(os.fstat(fd)) != identity(before):
                raise Hold('FILE_CHANGED_OR_OVERSIZED')
            result['sha256'] = hashlib.sha256(raw).hexdigest()
            result['bytes'] = used
        if identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity(before):
            raise Hold('PATH_REPLACED')
        current_parent, current_name = parent_fd(path)
        try:
            if (current_name != name or identity(os.fstat(parent)) != parent_before
                    or identity(os.fstat(current_parent)) != parent_before
                    or identity(os.stat(current_name, dir_fd=current_parent, follow_symlinks=False)) != identity(before)):
                raise Hold('PARENT_OR_PATH_CHANGED')
        finally:
            os.close(current_parent)
        return (result, raw) if body else result
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def capture(args, timeout=8, budget=65536):
    """Bound both pipes; kill the process group and reap on every exit path."""
    poller = selectors.DefaultSelector()
    p = None
    reaped = False
    try:
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                                                         'DOCKER_CONFIG': '/proc/self/fd/-1'})
        poller.register(p.stdout, selectors.EVENT_READ, 'out')
        poller.register(p.stderr, selectors.EVENT_READ, 'err')
        end = time.monotonic()+timeout
        out = []
        total = 0
        while poller.get_map():
            left = end-time.monotonic()
            if left <= 0:
                raise Hold('COMMAND_TIMEOUT')
            for key, _ in poller.select(min(left, 0.1)):
                data = os.read(key.fileobj.fileno(), 4096)
                if not data:
                    poller.unregister(key.fileobj)
                    continue
                total += len(data)
                if total > budget:
                    raise Hold('COMMAND_OUTPUT_LIMIT')
                if key.data == 'out':
                    out.append(data)
        left = end-time.monotonic()
        if left <= 0:
            raise Hold('COMMAND_TIMEOUT')
        return_code = p.wait(timeout=left)
        reaped = True
        if return_code != 0:
            raise Hold('COMMAND_REJECTED')
        return b''.join(out).decode('utf-8')
    except subprocess.TimeoutExpired:
        raise Hold('COMMAND_TIMEOUT')
    finally:
        # A child could leave descendants holding pipes, even after its own exit.
        if p is not None and not reaped:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        poller.close()
        if p is not None:
            p.stdout.close()
            p.stderr.close()
            if not reaped:
                p.wait(timeout=2)


def exact_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Hold('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(Hold('NONFINITE_JSON')))


def base_template():
    return '\n'.join('{{json '+s+'}}' for s in ('.Id', '.Image', '.State.Running', '.Config.User'))


def current_template():
    entry = json.dumps(json.dumps(['python', '-B', '-m', 'scripts.community_platform_host'], separators=(',', ':')))
    cmd = json.dumps(json.dumps(['--plan', ROOT+'/config/host.json', '--center-keys', ROOT+'/config/center-keys.json',
                               '--wechat-secret', ROOT+'/config/wechat.json'], separators=(',', ':')))
    template = base_template()+'\n{{json (eq (json .Config.Entrypoint) '+entry+')}}\n'
    template += '{{json (eq (json .Config.Cmd) '+cmd+')}}\n{{len .Mounts}}\n{{range .Mounts}}'
    for i, (path, rw, token) in enumerate(((ROOT+'/config', False, 'CONFIG_RO'), (ROOT+'/data', True, 'DATA_RW'), (RUN, True, 'RUNTIME_RW'))):
        template += '{{'+('if' if i == 0 else 'else if')+' and (eq .Type "bind") (eq .Source '+json.dumps(path)+') (eq .Destination '+json.dumps(path)+') (eq .RW '+str(rw).lower()+')}}'+json.dumps(token)+'\n'
    return template+'{{else}}"UNKNOWN"\n{{end}}{{end}}'


def project_container(raw, current=False):
    lines = raw.splitlines()
    if len(lines) < 4:
        raise Hold('CONTAINER_SHAPE')
    values = [exact_json(line) for line in lines]
    cid, image, running, user = values[:4]
    if type(cid) is not str or CID.fullmatch(cid) is None or type(image) is not str or IMAGE.fullmatch(image) is None or type(running) is not bool:
        raise Hold('CONTAINER_TYPES')
    result = {'status': 'OBSERVED', 'container_id': cid, 'image_id': image, 'running': running,
              'original_nonroot_user': 'MATCH' if user == '10001:1008' else UNKNOWN}
    if current:
        if len(values) < 7 or type(values[4]) is not bool or type(values[5]) is not bool or type(values[6]) is not int:
            raise Hold('BINDING_TYPES')
        mounts = values[7:]
        if len(mounts) != values[6] or any(type(v) is not str or v not in ('CONFIG_RO', 'DATA_RW', 'RUNTIME_RW', UNKNOWN) for v in mounts):
            raise Hold('MOUNT_SHAPE')
        result.update(entrypoint_match=values[4], command_reference_match=values[5],
                      original_mounts_match=len(mounts) == 3 and set(mounts) == {'CONFIG_RO', 'DATA_RW', 'RUNTIME_RW'})
    elif len(values) != 4:
        raise Hold('ROLLBACK_SHAPE')
    return result


def project_image(raw, expected):
    values = [exact_json(line) for line in raw.splitlines()]
    if len(values) != 4 or values[0] != expected:
        raise Hold('IMAGE_BINDING')
    refs = values[1]
    if refs is None:
        refs = []
    if type(refs) is not list or len(refs) > 16:
        raise Hold('REPO_DIGEST_SHAPE')
    digests = []
    for ref in refs:
        if type(ref) is not str or re.fullmatch(r'[A-Za-z0-9./:_-]{1,200}@sha256:[0-9a-f]{64}', ref) is None:
            raise Hold('REPO_DIGEST_TYPE')
        digests.append(ref.rsplit('@', 1)[1])
    revision = values[2]
    return {'status': 'OBSERVED', 'image_id': expected, 'repository_digest_state': 'PRESENT' if refs else 'EMPTY',
            'repository_digest_hashes': sorted(set(digests)),
            'oci_revision': revision if type(revision) is str and SHA.fullmatch(revision) else UNKNOWN,
            'original_nonroot_user': 'MATCH' if values[3] == '10001:1008' else UNKNOWN}


def project_transaction(value):
    if type(value) is not dict:
        raise Hold('TRANSACTION_OBJECT_REQUIRED')
    result = {}
    states = {'PREPARED', 'PUBLIC_ORIGINAL_ROLE_ASSETS_READY_AUTH_ACCEPTANCE_PENDING',
              'PUBLIC_READY_AUTH_ACCEPTANCE_PENDING', 'KNOWN_FAILURE', 'ROLLED_BACK'}
    for key, pattern in (('source_sha', SHA), ('image_id', IMAGE), ('container_id', CID),
                         ('old_id', CID), ('new_image', IMAGE), ('owner_vhost_sha256', DIGEST)):
        v = value.get(key)
        result[key] = v if type(v) is str and pattern.fullmatch(v) else UNKNOWN
    result['phase'] = 'PREPARED' if value.get('phase') == 'PREPARED' else UNKNOWN
    result['state'] = value.get('state') if type(value.get('state')) is str and value['state'] in states else UNKNOWN
    result['rollback_container'] = ROLLBACK if value.get('rollback_container') == ROLLBACK else UNKNOWN
    result['private_inputs_and_data'] = 'REUSED_UNCHANGED' if value.get('private_inputs_and_data') == 'REUSED_UNCHANGED' else UNKNOWN
    for key in ('payments', 'role_acceptance', 'wechat_login_verified'):
        result[key] = value[key] if type(value.get(key)) is bool else UNKNOWN
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def health(open_url=None, now=None):
    opener = open_url or build_opener(ProxyHandler({}), NoRedirect()).open
    try:
        response = opener(Request(URL, headers={'Accept': 'application/json'}), timeout=10)
    except HTTPError as error:
        if error.code != 503:
            raise Hold('HEALTH_HTTP')
        response = error
    with response:
        http_status = getattr(response, 'status', getattr(response, 'code', None))
        if http_status not in (200, 503) or response.geturl() != URL or response.headers.get_content_type() != 'application/json':
            raise Hold('HEALTH_RESPONSE')
        raw = response.read(4097)
        if len(raw) > 4096:
            raise Hold('HEALTH_SIZE')
        value = exact_json(raw.decode('utf-8'))
    if type(value) is not dict:
        raise Hold('HEALTH_OBJECT')
    observed = int(time.time()) if now is None else now
    if type(observed) is not int or observed < 0:
        raise Hold('LOCAL_TIME')
    remote = value.get('observed_at')
    valid_time = type(remote) is int and 0 <= remote <= 9007199254740991
    freshness = UNKNOWN if not valid_time else ('FUTURE' if remote > observed+30 else 'STALE' if observed-remote > 600 else 'FRESH')
    sha = value.get('runtime_source_sha')
    return {'status': 'OBSERVED', 'http_status': http_status, 'observed_at': observed,
            'backend_status': value.get('status') if type(value.get('status')) is str and value['status'] in ('READY', 'MAINTENANCE', 'UNAVAILABLE') else UNKNOWN,
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY' if value.get('scope') == 'PROCESS_AND_DATABASE_CONNECTIVITY' else UNKNOWN,
            'production_acceptance': False if value.get('production_acceptance') is False else UNKNOWN,
            'runtime_source_sha': sha if type(sha) is str and SHA.fullmatch(sha) else UNKNOWN,
            'version_source': 'IMAGE_BUILD_STAMP' if value.get('version_source') == 'IMAGE_BUILD_STAMP' else UNKNOWN,
            'backend_observed_at': remote if valid_time else UNKNOWN, 'freshness': freshness}


def observe(command=capture):
    report = {'candidate': 'ISSUE76_UK_READONLY_VERSION_OBSERVATION', 'executable': False,
              'preview_version_acceptance': 'NOT_EVALUATED_EXACT_SOURCE_MATCH_STILL_REQUIRED',
              'scope': 'COMMUNITY_ONLY_SHARED_VHOST_FILE_DIGEST_NO_P2_RUNTIME_OR_DATA', 'snapshot_atomic': False, 'sections': {}}
    sections = report['sections']
    for key in ('current_container', 'current_image', 'rollback_container', 'current_container_recheck'):
        sections[key] = {'status': 'NOT_OBSERVED'}
    def collect(key, call):
        try:
            sections[key] = call()
        except FileNotFoundError:
            sections[key] = {'status': 'MISSING'}
        except Exception:
            sections[key] = {'status': 'HOLD_UNKNOWN'}
        return sections[key]
    collect('docker_binary', lambda: safe_file('/usr/bin/docker'))
    if sections['docker_binary'].get('type') == 'REGULAR_FILE':
        current = collect('current_container', lambda: project_container(command(DOCKER+['container', 'inspect', '--format', current_template(), CURRENT]), True))
        if current.get('status') == 'OBSERVED':
            fmt = '\n'.join(('{{json .Id}}', '{{json .RepoDigests}}', '{{json (index .Config.Labels "org.opencontainers.image.revision")}}', '{{json .Config.User}}'))
            collect('current_image', lambda: project_image(command(DOCKER+['image', 'inspect', '--format', fmt, current['image_id']]), current['image_id']))
        collect('rollback_container', lambda: project_container(command(DOCKER+['container', 'inspect', '--format', base_template(), ROLLBACK])))
    for key, path in sorted(META_PATHS.items()):
        collect(key, lambda p=path: safe_file(p))
    for key, path in sorted(ROUTE_PATHS.items()):
        collect(key, lambda p=path: safe_file(p, True)[0])
    for key, path in sorted(TRANSACTION_PATHS.items()):
        def transaction(p=path):
            meta, raw = safe_file(p, True)
            return {'status': 'OBSERVED', 'metadata': meta, 'projection': project_transaction(exact_json(raw.decode('utf-8')))}
        collect(key, transaction)
    health_report = collect('runtime_health', health)
    initial = sections.get('current_container', {})
    if initial.get('status') == 'OBSERVED':
        def recheck():
            last = project_container(command(DOCKER+['container', 'inspect', '--format', base_template(), CURRENT]))
            if any(last[key] != initial[key] for key in ('container_id', 'image_id', 'running', 'original_nonroot_user')):
                raise Hold('CURRENT_CONTAINER_CHANGED')
            return {'status': 'OBSERVED', 'identity_image_state_recheck': 'MATCH'}
        collect('current_container_recheck', recheck)
    image = sections.get('current_image', {})
    runtime = health_report.get('runtime_source_sha', UNKNOWN)
    revision = image.get('oci_revision', UNKNOWN)
    report['runtime_image_revision_relation'] = UNKNOWN if UNKNOWN in (runtime, revision) else 'MATCH' if runtime == revision else 'DIFFERENT'
    report['state'] = 'OBSERVED_NOT_ACCEPTANCE' if all(s.get('status') == 'OBSERVED' for s in sections.values()) else 'HOLD_PARTIAL_OBSERVATION'
    return report


def main():
    if os.getuid() != 0 or os.geteuid() != 0 or os.uname().nodename.split('.')[0] != HOST:
        print('{"candidate":"ISSUE76_UK_READONLY_VERSION_OBSERVATION","executable":false,"state":"HOLD_HOST_OR_IDENTITY"}')
        return 2
    def deadline(*args):
        raise TotalDeadline('TOTAL_TIMEOUT')
    previous = signal.signal(signal.SIGALRM, deadline)
    signal.alarm(60)
    try:
        report = observe()
        raw = json.dumps(report, sort_keys=True, allow_nan=False)
        if len(raw.encode('utf-8')) > 16384:
            raise Hold('REPORT_SIZE')
        print(raw)
        return 0 if report['state'] == 'OBSERVED_NOT_ACCEPTANCE' else 2
    except (Exception, TotalDeadline):
        print('{"candidate":"ISSUE76_UK_READONLY_VERSION_OBSERVATION","executable":false,"state":"HOLD_BOUNDED_OBSERVATION"}')
        return 2
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    raise SystemExit(main())
COMMUNITY_READONLY_PY
printf 'COMMUNITY_READONLY_EXIT_CODE=%s\n' "$community_readonly_exit"
exit "$community_readonly_exit"
