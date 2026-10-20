"""Fixed domestic portal lifecycle actions for an admitted original controller.

No CLI, sudo policy, claim, epoch, source-fence generator or new journal. The
original controller supplies stage admission, durable evidence publication and
real final-data/business/loaded-route verification. Missing verifiers HOLD
before a mutation. Source services and the domestic CRM are never touched.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile

HOST = 'iZvt5t8tlrm8oiZ'
RELEASE = Path('/opt/xuanjun-migration-s07/releases/portal-manual-6tm7b08f')
PREPARATION = Path('/root/pr99-cutover-preparation-izmakdgr')
UNIT_NAME = 'xuanjun-pr99-domestic-portal.service'
UNIT_PATH = Path('/etc/systemd/system') / UNIT_NAME
ROUTE_PATH = Path('/etc/nginx/pr122-minimal-cutover/tokyo-proxy-settings.conf')
UNIT_SHA = 'efff80c930d29b978c073df8837b8fd6f59ac5c5e24cbbceef98596fb351119f'
LAUNCHER_SHA = '6c2548d7e5560046c00d795b3cb888411c4c22c852e1b5e749e5ed4d8ffa1242'
ROUTE_SHA = '23ec502aaf9c929582c3a92b078aeedbb0acab3cf6fd3f1ef9ed1b7b1c305f5c'


class LifecycleHold(RuntimeError):
    pass


class LifecycleUnknown(LifecycleHold):
    pass


def need(condition, code):
    if not condition:
        raise LifecycleHold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def root_read(path):
    path = Path(path)
    for ancestor in [path, *path.parents]:
        info = ancestor.lstat()
        need(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and
             not info.st_mode & 0o022, 'ROOT_PATH_IDENTITY')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_size <= 1000000, 'ROOT_FILE_IDENTITY')
        raw = os.read(descriptor, 1000001)
        after = os.fstat(descriptor)
        linked = path.lstat()
        fingerprint = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                     value.st_mtime_ns, value.st_ctime_ns)
        need(fingerprint(before) == fingerprint(after) == fingerprint(linked)
             and len(raw) == before.st_size, 'ROOT_FILE_DRIFT')
        return raw
    finally:
        os.close(descriptor)


def replace_route(expected, replacement):
    """Only the existing fixed route; durable rename, no deletion or wildcards."""
    need(root_read(ROUTE_PATH) == expected, 'ROUTE_COMPARE_FAILED')
    descriptor, temporary = tempfile.mkstemp(prefix='.pr99-route-', dir=ROUTE_PATH.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(replacement)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        need(root_read(ROUTE_PATH) == expected, 'ROUTE_COMPARE_FAILED')
        os.replace(temporary, ROUTE_PATH)
        parent = os.open(ROUTE_PATH.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


class PortalLifecycle:
    def __init__(self, admit, publish, verify_final, verify_business,
                 verify_loaded_route, runner=subprocess.run):
        # Refuse an incomplete adapter set before any systemctl/nginx call.
        need(all(callable(callback) for callback in (
            admit, publish, verify_final, verify_business, verify_loaded_route,
            runner)), 'REAL_LIFECYCLE_ADAPTERS_REQUIRED')
        self.admit = admit
        self.publish = publish
        self.final = verify_final
        self.business = verify_business
        self.loaded = verify_loaded_route
        self.runner = runner

    def bound(self, request):
        need(os.geteuid() == 0 and os.uname().nodename.split('.')[0] == HOST,
             'TARGET_HOST_ROOT_REQUIRED')
        need(self.admit(request) is True, 'ORIGINAL_STAGE_ADMISSION_REQUIRED')
        need(digest(root_read(UNIT_PATH)) == UNIT_SHA, 'ACCEPTED_UNIT_CHANGED')
        need(digest(root_read(RELEASE / 'migration_portal_launcher.py')) ==
             LAUNCHER_SHA, 'ACCEPTED_LAUNCHER_CHANGED')
        accepted = json.loads(root_read(RELEASE / 'wired-portal-check-receipt.json'))
        need(accepted.get('status') == 'PASS' and
             digest(root_read(RELEASE / 'migration_credential_store.py')) ==
             accepted.get('credential_component_sha256'), 'ACCEPTED_CREDENTIAL_COMPONENT_CHANGED')
        candidate = root_read(PREPARATION / 'candidate-domestic-proxy-settings.conf')
        need(digest(candidate) == ROUTE_SHA, 'ACCEPTED_ROUTE_CHANGED')
        return candidate

    def command(self, arguments):
        try:
            result = self.runner(arguments, capture_output=True, timeout=20,
                                 check=False, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
                                                  'LANG': 'C'})
        except (subprocess.TimeoutExpired, OSError):
            raise LifecycleUnknown('COMMAND_OUTCOME_UNKNOWN_NO_REPLAY') from None
        need(len(result.stdout) <= 262144 and len(result.stderr) <= 262144,
             'COMMAND_OUTPUT_LIMIT')
        return result

    def service(self):
        result = self.command(['/usr/bin/systemctl', 'show', UNIT_NAME,
                               '--property=ActiveState,MainPID,DropInPaths', '--no-pager'])
        need(result.returncode == 0, 'SERVICE_QUERY_FAILED')
        values = dict(line.split('=', 1) for line in
                      result.stdout.decode('utf-8', 'strict').splitlines() if '=' in line)
        need(values.get('DropInPaths') == '', 'UNBOUND_SERVICE_DROPINS')
        return values

    def receipt(self, request, evidence, query_only=False):
        need(type(evidence) is dict and evidence, 'REAL_EVIDENCE_REQUIRED')
        self.bound(request)
        # Original publisher must bind request and durably persist evidence.
        # Query cannot manufacture a missing result or a fresh timestamp.
        return self.publish(request, evidence, query_only=query_only)

    def start_owned(self, request):
        need(request.get('stage') == 'start_owned', 'EXACT_LIFECYCLE_STAGE_REQUIRED')
        self.bound(request)
        proof = self.final(request)
        need(type(proof) is dict and proof.get('status') == 'PASS' and
             proof.get('final_source_sync') is True and
             proof.get('source_writer_resumed') is False,
             'FINAL_DATA_AND_SOURCE_FENCE_NOT_VERIFIED')
        state = self.service()
        need(state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0',
             'SERVICE_NOT_STOPPED')
        # Marker content must be supplied and bound by final-data verifier.
        marker = root_read(RELEASE / 'cutover-ready.json')
        need(proof.get('cutover_marker_sha256') == digest(marker), 'CUTOVER_MARKER_NOT_BOUND')
        sock = socket.socket()
        try:
            sock.bind(('127.0.0.1', 18080))
        except OSError:
            raise LifecycleHold('PORT_ALREADY_OWNED') from None
        finally:
            sock.close()
        self.bound(request)
        result = self.command(['/usr/bin/systemctl', 'start', UNIT_NAME])
        if result.returncode:
            # A failed start may have spawned/restarted a process. Preserve the
            # original intent; never infer NO_EFFECT or auto-replay from exit.
            raise LifecycleUnknown('START_FAILED_QUERY_ONLY')
        state = self.service()
        need(state.get('ActiveState') == 'active' and int(state.get('MainPID', '0')) > 0,
             'START_SUPERVISION_NOT_CONFIRMED')
        return self.receipt(request, {'service': state, 'final_data': proof})

    def cutover_route(self, request):
        need(request.get('stage') == 'cutover_route', 'EXACT_LIFECYCLE_STAGE_REQUIRED')
        candidate = self.bound(request)
        original = root_read(PREPARATION / 'original-tokyo-proxy-settings.conf')
        need(root_read(ROUTE_PATH) == original, 'ROUTE_NOT_AT_ORIGINAL_SNAPSHOT')
        accepted = self.business(request)
        need(type(accepted) is dict and accepted.get('status') == 'PASS',
             'BUSINESS_ACCEPTANCE_NOT_VERIFIED')
        state = self.service()
        need(state.get('ActiveState') == 'active' and int(state.get('MainPID', '0')) > 0,
             'OWNED_SERVICE_NOT_ACTIVE')
        replace_route(original, candidate)
        try:
            tested = self.command(['/usr/sbin/nginx', '-t'])
        except LifecycleHold:
            # No reload was dispatched. Restore only our exact written bytes.
            replace_route(candidate, original)
            raise
        if tested.returncode:
            replace_route(candidate, original)
            raise LifecycleHold('CANDIDATE_NGINX_INVALID_ORIGINAL_RESTORED')
        self.bound(request)
        result = self.command(['/usr/bin/systemctl', 'reload', 'nginx.service'])
        if result.returncode:
            raise LifecycleUnknown('RELOAD_OUTCOME_UNKNOWN_QUERY_ONLY')
        proof = self.loaded(request)
        need(type(proof) is dict and proof.get('status') == 'PASS' and
             proof.get('upstream') == '127.0.0.1:18080' and
             proof.get('route_sha256') == digest(candidate),
             'LOADED_ROUTE_AND_HTTPS_NOT_PROVEN')
        return self.receipt(request, {'loaded_route': proof, 'business': accepted})

    def query_start(self, request):
        need(request.get('stage') == 'start_owned', 'EXACT_LIFECYCLE_STAGE_REQUIRED')
        self.bound(request)
        state = self.service()
        need(state.get('ActiveState') == 'active' and int(state.get('MainPID', '0')) > 0,
             'START_OUTCOME_STILL_UNKNOWN')
        proof = self.final(request)
        need(type(proof) is dict and proof.get('status') == 'PASS' and
             proof.get('final_source_sync') is True and
             proof.get('source_writer_resumed') is False,
             'FINAL_DATA_AND_SOURCE_FENCE_NOT_VERIFIED')
        need(proof.get('cutover_marker_sha256') ==
             digest(root_read(RELEASE / 'cutover-ready.json')), 'CUTOVER_MARKER_NOT_BOUND')
        return self.receipt(request, {'service': state, 'final_data': proof}, True)

    def query_route(self, request):
        need(request.get('stage') == 'cutover_route', 'EXACT_LIFECYCLE_STAGE_REQUIRED')
        candidate = self.bound(request)
        need(root_read(ROUTE_PATH) == candidate, 'ROUTE_OUTCOME_STILL_UNKNOWN')
        proof = self.loaded(request)
        need(type(proof) is dict and proof.get('status') == 'PASS' and
             proof.get('upstream') == '127.0.0.1:18080' and
             proof.get('route_sha256') == digest(candidate),
             'LOADED_ROUTE_AND_HTTPS_NOT_PROVEN')
        return self.receipt(request, {'loaded_route': proof}, True)
