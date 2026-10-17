# Standalone reviewed-candidate payload. No execution during preparation.
"""Offline account-only design validator. NOT an account creation executable.
No OS/NSS/subprocess adapters, network, credential reads, or mutation operations.
All observations are supplied by a caller and remain UNTRUSTED design inputs.
"""
import json
import stat
HOST = 'iZvt5t8tlrm8oiZ'
ACCOUNT = 'xuanjun-customer'
SOURCE_COMMIT = 'a1d5a6dee3135df2d3332e96c722091e2f2fd9d9'
PROPOSED_ARGV = ('/usr/sbin/useradd', '-r', '-U', '-M', '-d', '/nonexistent', '-s', '/usr/sbin/nologin', '--password', '!', ACCOUNT)
DIRECTORIES = ('/', '/usr', '/usr/sbin', '/etc')
EXECUTABLES = ('/usr/sbin/useradd', '/usr/sbin/nologin')
ABSENT_PATHS = ('/nonexistent', '/home/xuanjun-customer', '/var/mail/xuanjun-customer', '/var/spool/mail/xuanjun-customer')
MISSING_INPUTS = ('EXACT_ACCOUNT_OPERATION_CANONICAL_TRANSACTION_BINDING', 'ORIGINAL_ONE_SHOT_EVIDENCE_PATH_AND_CONSUMPTION_CONTRACT', 'REVIEWED_STS_SWAS_WORKFLOW_IDENTITY_AND_EXACT_PAYLOAD_HASH', 'TARGET_USERADD_PACKAGE_BINARY_IDENTITY_AND_SUPPORTED_FLAGS', 'TARGET_PLATFORM_DEFAULTS_HOOKS_NSS_AND_SYSTEM_ID_RANGES', 'TARGET_MAIL_SPOOL_AND_SUBID_SIDE_EFFECT_SUPPRESSION', 'TARGET_PASSWORD_LOCK_DEFAULT_AND_PRIVATE_BOOLEAN_POSTCHECK', 'FRESH_LOCKED_ABSENCE_ROOT_PATH_AND_PRIVILEGE_POLICY_CHECKS', 'DURABLE_FAILURE_RECEIPT_AND_NO_RETRY_PROTOCOL')

class Denied(RuntimeError):
    pass

def collect_fixture(adapter):
    """Only injected adapter; no default live implementation exists.

    Useful solely to exercise prospective read behavior with mocks. Exceptions
    are reduced to fixed labels; account/group rows (including passwords) are
    never exported. This is NOT proof of freshness, approval or NSS completeness.
    """

    def absence(call):
        try:
            call(ACCOUNT)
        except KeyError:
            return 'ABSENT'
        except Exception:
            return 'UNKNOWN'
        return 'PRESENT'
    result = {'host': adapter.host, 'uid': adapter.uid, 'euid': adapter.euid, 'account': absence(adapter.getpwnam), 'group': absence(adapter.getgrnam), 'paths': {}}
    for path in DIRECTORIES + EXECUTABLES:
        parent = path.rsplit('/', 1)[0] or '/'
        if path != '/' and (not safe(result['paths'].get(parent), directory=True)):
            result['paths'][path] = {'state': 'UNKNOWN'}
            continue
        result['paths'][path] = metadata(adapter, path)
    for path in ABSENT_PATHS:
        parts = path.strip('/').split('/')[:-1]
        parent = ''
        verified = safe(result['paths'].get('/'), directory=True)
        for part in parts:
            parent += '/' + part
            if not verified:
                break
            if parent not in result['paths']:
                result['paths'][parent] = metadata(adapter, parent)
            verified = safe(result['paths'][parent], directory=True)
        result['paths'][path] = metadata(adapter, path) if verified else {'state': 'UNKNOWN'}
    return result

def metadata(adapter, path):
    try:
        row = adapter.lstat(path)
        return {'state': 'PRESENT', 'uid': row.st_uid, 'gid': row.st_gid, 'mode': row.st_mode, 'nlink': row.st_nlink}
    except FileNotFoundError:
        return {'state': 'ABSENT'}
    except Exception:
        return {'state': 'UNKNOWN'}

def safe(row, directory=False):
    if not isinstance(row, dict) or row.get('state') != 'PRESENT':
        return False
    if any((type(row.get(k)) is not int for k in ('uid', 'gid', 'mode', 'nlink'))):
        return False
    mode = row['mode']
    return row['uid'] == row['gid'] == 0 and (not mode & 18) and (not mode & 3584) and (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode) and row['nlink'] == 1 and bool(mode & 64))

def plan(observed):
    """Returns a non-executable review plan even for wholly favorable fixtures."""
    errors = []
    if not isinstance(observed, dict):
        observed = {}
    if observed.get('host') != HOST:
        errors.append('FIXED_HOST_REQUIRED')
    if any((type(observed.get(k)) is not int or observed[k] != 0 for k in ('uid', 'euid'))):
        errors.append('REAL_AND_EFFECTIVE_ROOT_REQUIRED')
    for key in ('account', 'group'):
        if observed.get(key) != 'ABSENT':
            errors.append(key.upper() + '_ABSENCE_REQUIRED_NO_REPAIR')
    paths = observed.get('paths', {})
    if not isinstance(paths, dict):
        paths = {}
    for path in DIRECTORIES + EXECUTABLES:
        if not safe(paths.get(path), directory=path in DIRECTORIES):
            errors.append('UNSAFE_OR_UNKNOWN_PATH:' + path)
    for path in ABSENT_PATHS:
        if not isinstance(paths.get(path), dict) or paths[path].get('state') != 'ABSENT':
            errors.append('ABSENCE_REQUIRED:' + path)
    return {'state': 'HOLD_PLAN_ONLY', 'execution_authorized': False, 'production_changes': 0, 'host': HOST, 'account': ACCOUNT, 'source_commit_context_only': SOURCE_COMMIT, 'proposed_argv_NOT_EXECUTABLE': list(PROPOSED_ARGV), 'precondition_failures': errors, 'missing_execution_inputs': list(MISSING_INPUTS), 'required_postconditions': {'uid_gid': 'NONZERO_WITHIN_VERIFIED_SYSTEM_RANGES', 'primary_group': ACCOUNT, 'supplementary_groups': [], 'home_field': '/nonexistent', 'home_created': False, 'shell': '/usr/sbin/nologin', 'password_locked': True, 'sudo_grants': False, 'polkit_global_policy': 'NOT_AUDITED', 'privilege_policy_changes': False, 'mail_spool_created': False, 'subuid_subgid_allocated': False}, 'retry_allowed': False, 'automatic_repair_or_delete': False}

def execute(*args, **kwargs):
    raise Denied('HOLD:UNKNOWN_CANONICAL_ACCOUNT_EXECUTION_BINDING_PLAN_ONLY')
ORIGINAL_LOCK = '/var/lib/xuanjun-customer-channel/channel.py'
ACCOUNT_RECEIPT = '/var/lib/xuanjun-customer-channel/account-preparation-20261017'

def create_once(ops):
    """Concrete one-command operation; mock-testable, never used by the CLI.

    Trusted adapter contract is specified in README.md. It owns fixed canonical
    lock/evidence paths and only boolean password/policy disclosure. No arbitrary
    command/path/username may be accepted from external input.
    """
    with ops.lock_existing(ORIGINAL_LOCK):
        observed = collect_fixture(ops)
        if plan(observed)['precondition_failures']:
            raise Denied('HOLD:ACCOUNT_PREFLIGHT')
        platform = ops.platform_preconditions()
        required = ('fixed_useradd_flags_supported', 'mail_spool_suppressed', 'no_subid_allocation', 'no_account_creation_hooks', 'locked_password_explicit', 'no_supplementary_group_defaults', 'no_privilege_policy_changes')
        if not isinstance(platform, dict) or any((platform.get(k) is not True for k in required)):
            raise Denied('HOLD:UNKNOWN_PLATFORM_PRECONDITIONS')
        for key in ('uid_min', 'uid_max', 'gid_min', 'gid_max'):
            if type(platform.get(key)) is not int or platform[key] <= 0:
                raise Denied('HOLD:UNKNOWN_SYSTEM_ID_RANGE')
        if platform['uid_min'] > platform['uid_max'] or platform['gid_min'] > platform['gid_max']:
            raise Denied('HOLD:INVALID_SYSTEM_ID_RANGE')
        ops.reserve_original_evidence(ACCOUNT_RECEIPT)
        try:
            if plan(collect_fixture(ops))['precondition_failures']:
                raise Denied('HOLD:FRESH_ACCOUNT_PREFLIGHT')
            if ops.platform_preconditions() != platform:
                raise Denied('HOLD:PLATFORM_DRIFT')
            ops.record_original_evidence(ACCOUNT_RECEIPT, 'ACCOUNT_CREATE_INTENT_NO_RETRY')
            if ops.run_fixed_useradd(PROPOSED_ARGV) != 0:
                raise Denied('HOLD:USERADD_FAILED_NO_RETRY')
            post = ops.private_postcheck()
            if not isinstance(post, dict):
                raise Denied('HOLD:POSTCHECK_UNKNOWN_NO_RETRY')
            uid, gid = (post.get('uid'), post.get('gid'))
            valid = type(uid) is int and type(gid) is int and (platform['uid_min'] <= uid <= platform['uid_max']) and (platform['gid_min'] <= gid <= platform['gid_max']) and (post.get('name') == post.get('primary_group') == ACCOUNT) and (post.get('group_gid') == gid) and (post.get('home') == '/nonexistent') and (post.get('shell') == '/usr/sbin/nologin') and (post.get('supplementary_groups') == []) and all((post.get(k) is True for k in ('password_locked', 'home_absent', 'mail_spool_absent', 'no_subids', 'no_sudo_grants')))
            if not valid:
                raise Denied('HOLD:POSTCHECK_FAILED_NO_RETRY')
            ops.record_original_evidence(ACCOUNT_RECEIPT, 'ACCOUNT_CREATED_VERIFIED_NO_RETRY')
            return {'state': 'ACCOUNT_CREATED_VERIFIED', 'account': ACCOUNT, 'uid': uid, 'gid': gid, 'retry_allowed': False, 'sudo_privileges': 'DENIED', 'polkit_global_policy': 'NOT_AUDITED', 'privilege_policy_changes': False}
        except BaseException:
            ops.record_original_evidence(ACCOUNT_RECEIPT, 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY')
            raise Denied('HOLD:ACCOUNT_RESULT_UNKNOWN_NO_RETRY') from None
'Fixed host OS adapter. Authoring/review only; never executed during preparation.'
import contextlib
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess

def need(ok):
    if not ok:
        raise Denied('HOLD:OS_PRECONDITION')

def secure(path, directory=False):
    path = Path(path)
    need(path.is_absolute())
    for item in reversed((path, *path.parents)):
        row = os.lstat(item)
        is_dir = item != path or directory
        need(safe({'state': 'PRESENT', 'uid': row.st_uid, 'gid': row.st_gid, 'mode': row.st_mode, 'nlink': row.st_nlink}, directory=is_dir) if is_dir else row.st_uid == row.st_gid == 0 and stat.S_ISREG(row.st_mode) and (row.st_nlink == 1) and (not row.st_mode & 3602))
    return path

def read_public_config(path):
    secure(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        need(info.st_size < 131072)
        return f.read(131072).decode('utf-8')

def secure_postcheck_tool(path):
    need(path in ('/usr/bin/sudo', '/usr/bin/passwd'))
    secure(Path(path).parent, directory=True)
    row = os.lstat(path)
    need(row.st_uid == row.st_gid == 0 and stat.S_ISREG(row.st_mode) and (row.st_nlink == 1) and (stat.S_IMODE(row.st_mode) in (493, 2541)))

class OS:

    def __init__(self):
        self.host = os.uname().nodename
        self.uid, self.euid = (os.getuid(), os.geteuid())
        need(self.host == HOST and self.uid == self.euid == 0)
        self.reserved = False
    getpwnam = staticmethod(pwd.getpwnam)
    getgrnam = staticmethod(grp.getgrnam)
    lstat = staticmethod(os.lstat)

    @contextlib.contextmanager
    def lock_existing(self, path):
        need(path == ORIGINAL_LOCK)
        secure(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before, opened = (os.lstat(path), os.fstat(fd))
            need((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def command(argv):
        if argv[0] in ('/usr/bin/sudo', '/usr/bin/passwd'):
            secure_postcheck_tool(argv[0])
        else:
            secure(argv[0])
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, shell=False, env={'PATH': '/usr/sbin:/usr/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        need(len(result.stdout) < 131072 and len(result.stderr) < 131072)
        return result

    def platform_preconditions(self):
        secure_postcheck_tool('/usr/bin/passwd')
        secure_postcheck_tool('/usr/bin/sudo')
        help_result = self.command(('/usr/sbin/useradd', '--help'))
        need(help_result.returncode == 0)
        help_text = help_result.stdout.decode('utf-8')
        flags = all((flag in help_text for flag in ('--system', '--user-group', '--no-create-home', '--home-dir', '--shell', '--password')))
        defaults = {}
        for line in read_public_config('/etc/login.defs').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                bits = line.split(None, 1)
                need(len(bits) == 2 and bits[0] not in defaults)
                defaults[bits[0]] = bits[1].strip()
        for path in ('/etc/shadow-maint/useradd-pre.d', '/etc/shadow-maint/useradd-post.d', '/etc/useradd.d'):
            if os.path.lexists(path):
                secure(path, directory=True)
                need(not list(Path(path).iterdir()))
        for key in ('USERADD_CMD', 'USERGROUPS_ENAB'):
            if key == 'USERADD_CMD':
                need(key not in defaults)
        user_defaults = read_public_config('/etc/default/useradd')
        parsed = {}
        for line in user_defaults.splitlines():
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            need('=' in line)
            key, value = line.split('=', 1)
            need(key not in parsed)
            parsed[key] = value.strip().strip('"').strip("'")
        need(not parsed.get('GROUPS'))
        return dict(fixed_useradd_flags_supported=flags, mail_spool_suppressed=True, no_subid_allocation=True, no_account_creation_hooks=True, locked_password_explicit=True, no_supplementary_group_defaults=not parsed.get('GROUPS'), no_privilege_policy_changes=True, uid_min=int(defaults['SYS_UID_MIN']), uid_max=int(defaults['SYS_UID_MAX']), gid_min=int(defaults['SYS_GID_MIN']), gid_max=int(defaults['SYS_GID_MAX']))

    @staticmethod
    def sync(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def reserve_original_evidence(self, path):
        need(path == ACCOUNT_RECEIPT and (not self.reserved))
        secure(Path(path).parent, directory=True)
        os.mkdir(path, 448)
        self.reserved = True
        self.sync(Path(path).parent)
        self.record_original_evidence(path, 'ACCOUNT_STARTED_NO_RETRY')

    def record_original_evidence(self, path, state):
        need(path == ACCOUNT_RECEIPT and self.reserved)
        need(state in ('ACCOUNT_STARTED_NO_RETRY', 'ACCOUNT_CREATE_INTENT_NO_RETRY', 'ACCOUNT_CREATED_VERIFIED_NO_RETRY', 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY'))
        secure(path, directory=True)
        file = Path(path) / (state + '.json')
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384)
        with os.fdopen(fd, 'w') as f:
            json.dump({'state': state, 'host': HOST, 'account': ACCOUNT, 'retry_allowed': False}, f)
            f.flush()
            os.fsync(f.fileno())
        self.sync(path)

    def run_fixed_useradd(self, argv):
        need(argv == PROPOSED_ARGV and self.reserved)
        return self.command(PROPOSED_ARGV).returncode

    def sudo_denied(self):
        result = self.command(('/usr/bin/sudo', '-n', '-l', '-U', ACCOUNT))
        if result.returncode == 0:
            return False
        if result.returncode != 1:
            return None
        import re
        text = (result.stdout + result.stderr).decode('utf-8').strip()
        expected = 'User ' + re.escape(ACCOUNT) + ' is not allowed to run sudo on ' + re.escape(HOST) + '\\.?'
        return True if re.fullmatch(expected, text) else None

    def private_postcheck(self):
        account, group = (pwd.getpwnam(ACCOUNT), grp.getgrnam(ACCOUNT))
        status = self.command(('/usr/bin/passwd', '-S', ACCOUNT))
        fields = status.stdout.decode('utf-8').split()
        locked = status.returncode == 0 and len(fields) >= 2 and (fields[0] == ACCOUNT) and (fields[1] == 'L')
        no_subids = True
        for path in ('/etc/subuid', '/etc/subgid'):
            if os.path.lexists(path):
                rows = read_public_config(path).splitlines()
                no_subids = no_subids and (not any((row.split(':', 1)[0] in (ACCOUNT, str(account.pw_uid)) for row in rows)))
        no_sudo = self.sudo_denied()
        return {'name': account.pw_name, 'uid': account.pw_uid, 'gid': account.pw_gid, 'primary_group': group.gr_name, 'group_gid': group.gr_gid, 'home': account.pw_dir, 'shell': account.pw_shell, 'supplementary_groups': [g.gr_gid for g in grp.getgrall() if ACCOUNT in g.gr_mem], 'password_locked': locked, 'home_absent': not os.path.lexists('/nonexistent') and (not os.path.lexists('/home/xuanjun-customer')), 'mail_spool_absent': not os.path.lexists('/var/mail/xuanjun-customer') and (not os.path.lexists('/var/spool/mail/xuanjun-customer')), 'no_subids': no_subids, 'no_sudo_grants': no_sudo}

def main(argv):
    need(argv == ['--apply'])
    return create_once(OS())
if __name__ == '__main__':
    import sys
    try:
        print(json.dumps(main(sys.argv[1:]), sort_keys=True))
    except BaseException:
        print('{"state":"HOLD","retry_allowed":false}')
        raise SystemExit(2) from None
