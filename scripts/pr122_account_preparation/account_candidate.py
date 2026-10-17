"""Offline account-only design validator. NOT an account creation executable.
No OS/NSS/subprocess adapters, network, credential reads, or mutation operations.
All observations are supplied by a caller and remain UNTRUSTED design inputs.
"""
import json
import stat

HOST = 'iZvt5t8tlrm8oiZ'
ACCOUNT = 'xuanjun-customer'
SOURCE_COMMIT = 'a1d5a6dee3135df2d3332e96c722091e2f2fd9d9'
# Fixed candidate command; shadow -r suppresses home/mail/subid allocation.
PROPOSED_ARGV = ('/usr/sbin/useradd', '-r', '-U', '-M', '-d', '/nonexistent',
                 '-s', '/usr/sbin/nologin', '--password', '!', ACCOUNT)
DIRECTORIES = ('/', '/usr', '/usr/sbin', '/etc')
EXECUTABLES = ('/usr/sbin/useradd', '/usr/sbin/nologin')
ABSENT_PATHS = ('/nonexistent', '/home/xuanjun-customer',
                '/var/mail/xuanjun-customer', '/var/spool/mail/xuanjun-customer')
MISSING_INPUTS = (
    'EXACT_ACCOUNT_OPERATION_CANONICAL_TRANSACTION_BINDING',
    'ORIGINAL_ONE_SHOT_EVIDENCE_PATH_AND_CONSUMPTION_CONTRACT',
    'REVIEWED_STS_SWAS_WORKFLOW_IDENTITY_AND_EXACT_PAYLOAD_HASH',
    'TARGET_USERADD_PACKAGE_BINARY_IDENTITY_AND_SUPPORTED_FLAGS',
    'TARGET_PLATFORM_DEFAULTS_HOOKS_NSS_AND_SYSTEM_ID_RANGES',
    'TARGET_MAIL_SPOOL_AND_SUBID_SIDE_EFFECT_SUPPRESSION',
    'TARGET_PASSWORD_LOCK_DEFAULT_AND_PRIVATE_BOOLEAN_POSTCHECK',
    'FRESH_LOCKED_ABSENCE_ROOT_PATH_AND_PRIVILEGE_POLICY_CHECKS',
    'DURABLE_FAILURE_RECEIPT_AND_NO_RETRY_PROTOCOL',
)

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
    result = {'host': adapter.host, 'uid': adapter.uid, 'euid': adapter.euid,
              'account': absence(adapter.getpwnam),
              'group': absence(adapter.getgrnam), 'paths': {}}
    # Parent validation intentionally precedes child lstat; no symlink traversal.
    for path in DIRECTORIES + EXECUTABLES:
        parent = path.rsplit('/', 1)[0] or '/'
        if path != '/' and not safe(result['paths'].get(parent), directory=True):
            result['paths'][path] = {'state': 'UNKNOWN'}
            continue
        result['paths'][path] = metadata(adapter, path)
    # Nested absent-path checks require separately verified parent chains.
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
        return {'state': 'PRESENT', 'uid': row.st_uid, 'gid': row.st_gid,
                'mode': row.st_mode, 'nlink': row.st_nlink}
    except FileNotFoundError:
        return {'state': 'ABSENT'}
    except Exception:
        return {'state': 'UNKNOWN'}


def safe(row, directory=False):
    if not isinstance(row, dict) or row.get('state') != 'PRESENT':
        return False
    if any(type(row.get(k)) is not int for k in ('uid', 'gid', 'mode', 'nlink')):
        return False
    mode = row['mode']
    return (row['uid'] == row['gid'] == 0 and not mode & 0o022
            and not mode & 0o7000
            and (stat.S_ISDIR(mode) if directory else
                 stat.S_ISREG(mode) and row['nlink'] == 1 and bool(mode & 0o100)))


def plan(observed):
    """Returns a non-executable review plan even for wholly favorable fixtures."""
    errors = []
    if not isinstance(observed, dict):
        observed = {}
    if observed.get('host') != HOST:
        errors.append('FIXED_HOST_REQUIRED')
    if any(type(observed.get(k)) is not int or observed[k] != 0 for k in ('uid', 'euid')):
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
    return {'state': 'HOLD_PLAN_ONLY', 'execution_authorized': False,
            'production_changes': 0, 'host': HOST, 'account': ACCOUNT,
            'source_commit_context_only': SOURCE_COMMIT,
            'proposed_argv_NOT_EXECUTABLE': list(PROPOSED_ARGV),
            'precondition_failures': errors, 'missing_execution_inputs': list(MISSING_INPUTS),
            'required_postconditions': {
                'uid_gid': 'NONZERO_WITHIN_VERIFIED_SYSTEM_RANGES',
                'primary_group': ACCOUNT, 'supplementary_groups': [],
                'home_field': '/nonexistent', 'home_created': False,
                'shell': '/usr/sbin/nologin', 'password_locked': True,
                'sudo_grants': False, 'polkit_global_policy': 'NOT_AUDITED',
                'privilege_policy_changes': False,
                'mail_spool_created': False, 'subuid_subgid_allocated': False},
            'retry_allowed': False, 'automatic_repair_or_delete': False}


def execute(*args, **kwargs):
    # Deliberately unconditional. No override, permit flag, shell, or callback.
    raise Denied('HOLD:UNKNOWN_CANONICAL_ACCOUNT_EXECUTION_BINDING_PLAN_ONLY')


if __name__ == '__main__':
    # No inputs, host introspection or filesystem accesses. Always a refusal.
    print(json.dumps(plan({}), sort_keys=True))
    raise SystemExit(2)

# Creation core for a separately reviewed one-shot caller. No live adapter is
# shipped. The caller must bind an exact account-only receipt to the original
# transaction; a string supplied by a workflow/user is not sufficient evidence.
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
        required = ('fixed_useradd_flags_supported', 'mail_spool_suppressed',
                    'no_subid_allocation', 'no_account_creation_hooks',
                    'locked_password_explicit', 'no_supplementary_group_defaults',
                    'no_privilege_policy_changes')
        if not isinstance(platform, dict) or any(platform.get(k) is not True for k in required):
            raise Denied('HOLD:UNKNOWN_PLATFORM_PRECONDITIONS')
        for key in ('uid_min', 'uid_max', 'gid_min', 'gid_max'):
            if type(platform.get(key)) is not int or platform[key] <= 0:
                raise Denied('HOLD:UNKNOWN_SYSTEM_ID_RANGE')
        if platform['uid_min'] > platform['uid_max'] or platform['gid_min'] > platform['gid_max']:
            raise Denied('HOLD:INVALID_SYSTEM_ID_RANGE')
        # This call must atomically reserve/fsync the reviewed ORIGINAL evidence
        # location, rejecting every existing/partial/unknown attempt. No retries.
        ops.reserve_original_evidence(ACCOUNT_RECEIPT)
        try:
            # Do not trust an earlier metadata run or even our first lookup.
            if plan(collect_fixture(ops))['precondition_failures']:
                raise Denied('HOLD:FRESH_ACCOUNT_PREFLIGHT')
            if ops.platform_preconditions() != platform:
                raise Denied('HOLD:PLATFORM_DRIFT')
            ops.record_original_evidence(ACCOUNT_RECEIPT, 'ACCOUNT_CREATE_INTENT_NO_RETRY')
            # Must use shell=False, fixed minimal environment, DEVNULL stdin,
            # bounded timeout and captured/discarded output; never print stderr.
            if ops.run_fixed_useradd(PROPOSED_ARGV) != 0:
                raise Denied('HOLD:USERADD_FAILED_NO_RETRY')
            post = ops.private_postcheck()
            if not isinstance(post, dict):
                raise Denied('HOLD:POSTCHECK_UNKNOWN_NO_RETRY')
            uid, gid = post.get('uid'), post.get('gid')
            valid = (type(uid) is int and type(gid) is int
                     and platform['uid_min'] <= uid <= platform['uid_max']
                     and platform['gid_min'] <= gid <= platform['gid_max']
                     and post.get('name') == post.get('primary_group') == ACCOUNT
                     and post.get('group_gid') == gid
                     and post.get('home') == '/nonexistent'
                     and post.get('shell') == '/usr/sbin/nologin'
                     and post.get('supplementary_groups') == []
                     and all(post.get(k) is True for k in
                             ('password_locked', 'home_absent', 'mail_spool_absent',
                              'no_subids', 'no_sudo_grants')))
            if not valid:
                raise Denied('HOLD:POSTCHECK_FAILED_NO_RETRY')
            ops.record_original_evidence(ACCOUNT_RECEIPT, 'ACCOUNT_CREATED_VERIFIED_NO_RETRY')
            return {'state': 'ACCOUNT_CREATED_VERIFIED', 'account': ACCOUNT,
                    'uid': uid, 'gid': gid, 'retry_allowed': False,
                    'sudo_privileges': 'DENIED', 'polkit_global_policy': 'NOT_AUDITED',
                    'privilege_policy_changes': False}
        except BaseException:
            # Preserve the consumed evidence on all errors, including timeouts.
            # No userdel/groupdel, repair, secondary mutation or blind retry.
            ops.record_original_evidence(ACCOUNT_RECEIPT, 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY')
            raise Denied('HOLD:ACCOUNT_RESULT_UNKNOWN_NO_RETRY') from None
