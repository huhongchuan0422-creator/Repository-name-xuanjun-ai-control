"""Owner-only temporary fixed-action bootstrap. Offline candidate, no trust enrollment.
Security changes require separate Owner approval of exact reviewed bytes before use.
No account creation, probe execution, cloud API or network operations occur here.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

HOST = 'iZvt5t8tlrm8oiZ'
BASE = Path('/var/lib/xuanjun-customer-channel')
EXEC = Path('/usr/local/libexec/xuanjun-customer-channel')
POLICY = Path('/etc/sudoers.d/xuanjun-customer-channel')
INPUT = Path('/root/pr122-readonly-admission-inputs')
CONTROL = BASE / 'readonly-bootstrap-20261017'
HELPER = BASE / 'readonly-admission.py'
OLD_CODE = '0804e33edac6ad07a711456c0c15708266b2ad8a75c4cb3bdc5964a9b79a96bd'
VISUDO = Path('/usr/sbin/visudo')

def need(ok, message):
    if not ok: raise RuntimeError('HOLD:' + message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
def owner():
    need(os.getuid() == 0 and os.geteuid() == 0 and os.uname().nodename == HOST and os.environ.get('SUDO_UID') != '1002', 'OWNER_HOST_REQUIRED')
def secure(path, directory=False):
    path = Path(path)
    need(path.is_absolute(), 'ABSOLUTE_PATH')
    for p in reversed((path, *path.parents)):
        s = p.lstat()
        need(s.st_uid == 0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode & 0o022, 'ROOT_PRIVATE_PATH')
        if p != path or directory: need(stat.S_ISDIR(s.st_mode), 'DIRECTORY')
        else: need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 2000000, 'REGULAR_BOUNDED_FILE')
    return path

def file_stat(s):
    need(s.st_uid == 0 and stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and not s.st_mode & 0o022, 'UNSAFE_FILE_DESCRIPTOR')

def read(path, mode=None):
    secure(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        a = os.fstat(f.fileno()); file_stat(a)
        raw = f.read(2000001); b = os.fstat(f.fileno()); file_stat(b)
        current = Path(path).lstat()
        need((b.st_dev, b.st_ino) == (current.st_dev, current.st_ino) and not stat.S_ISLNK(current.st_mode), 'PATH_INODE_DRIFT')
    need((a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns) == (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns) and len(raw) <= 2000000, 'FILE_DRIFT')
    need(mode is None or stat.S_IMODE(a.st_mode) == mode, 'MODE_DRIFT')
    return raw

def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)
def create(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), mode); f.write(raw); f.flush(); os.fsync(f.fileno())
    sync(path.parent)
def replace(path, raw, mode):
    # Fixed staging name: interruption is diagnostic; never overwrite unknown staging.
    stage = path.parent / ('.' + path.name + '.readonly-bootstrap-pending')
    create(stage, raw, mode)
    os.replace(stage, path); sync(path.parent)
def expected_wrapper():
    return ('#!/bin/sh\nset -eu\n[ "$#" -eq 1 ] || exit 2\nexec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C SUDO_UID="${SUDO_UID-}" /usr/bin/python3 -I -B ' + str(BASE / 'channel.py') + ' "$1"\n').encode()
def expected_policy():
    return ('githubrunner ALL=(root) NOPASSWD: ' + ', '.join(str(EXEC) + ' ' + x for x in ('inspect', 'plan', 'apply', 'rollback')) + '\n').encode()
def new_wrapper():
    old = expected_wrapper(); marker = b'exec /usr/bin/env'
    branch = ('if [ "$1" = "inspect-account-once" ]; then\n  exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C SUDO_UID="${SUDO_UID-}" /usr/bin/python3 -I -B ' + str(HELPER) + '\nfi\n').encode()
    return old.replace(marker, branch + marker, 1)
def new_policy(): return expected_policy().rstrip(b'\n') + (', ' + str(EXEC) + ' inspect-account-once\n').encode()

def bundle():
    secure(INPUT, True)
    need(stat.S_IMODE(INPUT.stat().st_mode) == 0o700, 'INPUT_MODE')
    manifest = json.loads(read(INPUT / 'domestic-bootstrap-manifest.json', 0o400))
    helper = read(INPUT / 'domestic-readonly-helper.py', 0o400)
    owner_tool = read(INPUT / 'domestic_owner.py', 0o400)
    need(set(manifest) == {'schema', 'scope', 'files'} and manifest['schema'] == 1 and manifest['scope'] == 'DOMESTIC_READONLY_BOOTSTRAP_20261017', 'MANIFEST_SCOPE')
    files = {'domestic-readonly-helper.py': helper, 'wrapper': new_wrapper(), 'sudoers': new_policy(), 'domestic_bootstrap.py': read(Path(__file__).absolute()), 'domestic_owner.py': owner_tool}
    need(manifest['files'] == {n: {'sha256': sha(v), 'size': len(v)} for n, v in files.items()}, 'MANIFEST_BINDING')
    compile(helper, 'fixed-reviewed-helper', 'exec')
    compile(owner_tool, 'reviewed-owner-tool', 'exec') # Validate syntax only; never execute.
    return helper, manifest

def interpreter_identity():
    need(sys.version_info >= (3, 8) and all(hasattr(os, name) for name in ('O_NOFOLLOW', 'O_DIRECTORY', 'fsync', 'replace')) and hasattr(fcntl, 'flock'), 'UNSUPPORTED_PYTHON_API')
    fixed = Path('/usr/bin/python3'); path = fixed; chain = []; seen = set()
    for _ in range(16):
        need(str(path) not in seen, 'PYTHON_SYMLINK_LOOP'); seen.add(str(path))
        secure(path.parent, True)
        info = path.lstat()
        need(info.st_uid == 0, 'PYTHON_PATH_OWNER')
        if not stat.S_ISLNK(info.st_mode): break
        target = os.readlink(path)
        chain.append({'path': str(path), 'target': target, 'device': info.st_dev, 'inode': info.st_ino})
        path = Path(os.path.normpath(str(path.parent / target))) if not os.path.isabs(target) else Path(os.path.normpath(target))
    else: raise RuntimeError('HOLD:PYTHON_SYMLINK_DEPTH')
    file_stat(info)
    need(Path(sys.executable).resolve(strict=True) == path.resolve(strict=True), 'ALTERNATE_PYTHON_EXECUTABLE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno()); file_stat(before)
        need(before.st_size <= 32000000, 'PYTHON_BINARY_BOUND')
        digest = hashlib.sha256(); total = 0
        while True:
            chunk = f.read(65536)
            if not chunk: break
            total += len(chunk); need(total <= 32000000, 'PYTHON_BINARY_BOUND'); digest.update(chunk)
        after = os.fstat(f.fileno())
    current = path.lstat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and (current.st_dev, current.st_ino) == (after.st_dev, after.st_ino) and not stat.S_ISLNK(current.st_mode), 'PYTHON_BINARY_DRIFT')
    return {'fixed': str(fixed), 'resolved': str(path), 'chain': chain, 'device': after.st_dev, 'inode': after.st_ino, 'mode': stat.S_IMODE(after.st_mode), 'size': total, 'sha256': digest.hexdigest(), 'version': list(sys.version_info[:3])}

def baseline():
    owner(); interpreter = interpreter_identity(); secure(BASE, True)
    need(stat.S_IMODE(BASE.stat().st_mode) == 0o700, 'BASE_MODE')
    need(sha(read(BASE / 'channel.py', 0o444)) == OLD_CODE, 'ORIGINAL_CODE')
    grant = json.loads(read(BASE / 'grant-state.json', 0o600))
    need(type(grant) is dict and grant.get('state') == 'GRANTED', 'GRANTED_REQUIRED')
    s = (BASE / 'channel.py').stat()
    return {'interpreter': interpreter, 'device': s.st_dev, 'inode': s.st_ino, 'code_sha256': OLD_CODE, 'grant_sha256': sha(read(BASE / 'grant-state.json'))}

@contextmanager
def owner_lock(create_allowed=False):
    owner()
    lock = BASE / '.upgrade-lock'
    if not os.path.lexists(lock):
        need(create_allowed, 'UPGRADE_LOCK_REQUIRED')
        try: create(lock, b'', 0o600)
        except FileExistsError: pass
    read(lock, 0o600)
    handles = []
    try:
        for path in (lock, BASE / 'channel.py'):
            secure(path)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            handles.append(fd)
            before = os.fstat(fd); file_stat(before)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            after = path.lstat()
            need((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) and not stat.S_ISLNK(after.st_mode), 'LOCK_INODE_DRIFT')
        yield
    finally:
        for fd in reversed(handles): os.close(fd)

def no_admission_state():
    need(not os.path.lexists(BASE / 'READONLY_ADMISSION_TRUST.json') and not os.path.lexists(BASE / 'readonly-admission-20261017'), 'PREEXISTING_ADMISSION_STATE')

def plan():
    no_admission_state()
    identity = baseline()
    need(not os.path.lexists(CONTROL) and not os.path.lexists(HELPER), 'TRANSACTION_OR_HELPER_EXISTS')
    need(read(EXEC, 0o755) == expected_wrapper() and read(POLICY, 0o440) == expected_policy(), 'ORIGINAL_WRAPPER_POLICY')
    if os.path.lexists(BASE / '.upgrade-lock'): read(BASE / '.upgrade-lock', 0o600)
    helper, manifest = bundle()
    return {'scope': manifest['scope'], 'baseline': identity, 'manifest': manifest, 'trust_enrolled': False, 'probe_executed': False}

def policy_check(path):
    secure(VISUDO)
    result = subprocess.run([str(VISUDO), '-c', '-f', str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
    need(result.returncode == 0, 'VISUDO_REJECTED')
def record(state):
    # Each phase is written once. No reset or forward retry.
    create(CONTROL / (state + '.json'), canonical({'state': state}), 0o400)

def install():
    p = plan()
    with owner_lock(create_allowed=True):
        need(plan() == p, 'PLAN_DRIFT')
        helper, _ = bundle()
        CONTROL.mkdir(mode=0o700); sync(BASE)
        create(CONTROL / 'plan.json', canonical(p), 0o400)
        create(CONTROL / 'old-wrapper', expected_wrapper(), 0o400)
        create(CONTROL / 'old-sudoers', expected_policy(), 0o400)
        create(CONTROL / 'new-helper', helper, 0o400)
        create(CONTROL / 'new-sudoers', new_policy(), 0o440)
        record('PREPARED')
        policy_check(CONTROL / 'new-sudoers')
        need(baseline() == p['baseline'], 'BASELINE_DRIFT')
        create(HELPER, helper, 0o400); record('HELPER_INSTALLED')
        replace(EXEC, new_wrapper(), 0o755); record('WRAPPER_INSTALLED')
        no_admission_state()
        replace(POLICY, new_policy(), 0o440); record('POLICY_INSTALLED')
        result = verify_locked(); record('VERIFIED')
        return result

def transaction():
    baseline(); secure(CONTROL, True)
    need(stat.S_IMODE(CONTROL.stat().st_mode) == 0o700, 'CONTROL_MODE')
    p = json.loads(read(CONTROL / 'plan.json', 0o400))
    need(baseline() == p['baseline'] and p['scope'] == 'DOMESTIC_READONLY_BOOTSTRAP_20261017', 'ORIGINAL_INODE_OR_STATE_DRIFT')
    need(read(CONTROL / 'old-wrapper', 0o400) == expected_wrapper() and read(CONTROL / 'old-sudoers', 0o400) == expected_policy(), 'BACKUP_DRIFT')
    helper = read(CONTROL / 'new-helper', 0o400)
    need(p['manifest']['files']['domestic-readonly-helper.py'] == {'sha256': sha(helper), 'size': len(helper)}, 'HELPER_BACKUP_DRIFT')
    return p, helper

def verify():
    with owner_lock(): return verify_locked()

def verify_locked():
    _, helper = transaction()
    need(read(EXEC, 0o755) == new_wrapper() and read(POLICY, 0o440) == new_policy() and read(HELPER, 0o400) == helper, 'INSTALL_PARTIAL_OR_DRIFT')
    need(not os.path.lexists(CONTROL / 'ROLLBACK_INTENT.json'), 'ROLLBACK_STARTED')
    pin_present = os.path.lexists(BASE / 'READONLY_ADMISSION_TRUST.json')
    receipt_present = os.path.lexists(BASE / 'readonly-admission-20261017')
    return {'state': 'INSTALLED_PIN_PRESENT_NOT_VALIDATED' if pin_present else 'INSTALLED_AWAITING_OWNER_PIN', 'trust_enrolled': pin_present, 'trust_validated': False, 'receipt_present': receipt_present, 'probe_executed': 'NOT_ESTABLISHED_BY_BOOTSTRAP'}

def rollback():
    owner()
    with owner_lock():
        p, helper = transaction()
        need(not os.path.lexists(CONTROL / 'ROLLBACK_INTENT.json'), 'ROLLBACK_ALREADY_STARTED_NO_RETRY')
        need(read(EXEC, 0o755) in (expected_wrapper(), new_wrapper()) and read(POLICY, 0o440) in (expected_policy(), new_policy()), 'UNKNOWN_WRAPPER_POLICY')
        if os.path.lexists(HELPER): need(read(HELPER, 0o400) == helper, 'UNKNOWN_HELPER')
        for path in (EXEC, POLICY):
            need(not os.path.lexists(path.parent / ('.' + path.name + '.readonly-bootstrap-pending')), 'PARTIAL_STAGING_REQUIRES_REVIEW')
        policy_check(CONTROL / 'old-sudoers')
        record('ROLLBACK_INTENT')
        # Withdraw privilege first, then wrapper; helper/evidence remain root-only.
        if read(POLICY) != expected_policy(): replace(POLICY, expected_policy(), 0o440)
        if read(EXEC) != expected_wrapper(): replace(EXEC, expected_wrapper(), 0o755)
        need(baseline() == p['baseline'] and read(POLICY, 0o440) == expected_policy() and read(EXEC, 0o755) == expected_wrapper(), 'RESTORE_VERIFY')
        record('ROLLED_BACK')
        return {'state': 'ROLLED_BACK', 'evidence_retained': True, 'helper_retained_if_installed': True}

def restore_for_workflow(coordinator):
    """Exact old policy restoration under a NEW explicit whole-workflow grant.

    Old CLI/rollback remains one-shot. Caller must enter from the protected Owner
    workflow, holding only its website lock, never from a channel-locked command.
    We acquire original upgrade then channel locks, both nonblocking, and retain
    every original receipt/helper. This is not business or application rollback.
    """
    def guard():
        from scripts.pr122_customer_workflow import POLICY as WORKFLOW_POLICY
        need(coordinator.approval.get('attempt_policy')==WORKFLOW_POLICY,'WHOLE_WORKFLOW_PERMISSION_REQUIRED')
        coordinator.authority();coordinator.assert_active();coordinator.verify_inputs('POLICY_RESTORE')
        need(coordinator.data['intent'] is not None and coordinator.data['intent']['stage']=='POLICY_RESTORE',
             'POLICY_STAGE_NOT_ACTIVE')
        need('RECONCILE_POLICY' in coordinator.stage_contract('POLICY_RESTORE')['recovery_actions'],
             'POLICY_RESTORATION_NOT_APPROVED')
    guard();owner()
    with owner_lock():
        guard();p,helper=transaction()
        inputs=coordinator.ops.input('POLICY_RESTORE')
        need(type(inputs) is dict and set(inputs)=={'transaction','plan_sha256','old_wrapper_sha256','old_policy_sha256'}
             and inputs['transaction']==CONTROL.name and inputs['plan_sha256']==sha(read(CONTROL/'plan.json',0o400))
             and inputs['old_wrapper_sha256']==sha(read(CONTROL/'old-wrapper',0o400))
             and inputs['old_policy_sha256']==sha(read(CONTROL/'old-sudoers',0o400)), 'POLICY_RESTORE_EXACT_BACKUPS')
        need(read(EXEC,0o755) in (expected_wrapper(),new_wrapper())
             and read(POLICY,0o440) in (expected_policy(),new_policy()), 'UNKNOWN_WRAPPER_POLICY')
        if os.path.lexists(HELPER):need(read(HELPER,0o400)==helper,'UNKNOWN_HELPER')
        for path in (EXEC,POLICY):
            need(not os.path.lexists(path.parent/('.'+path.name+'.readonly-bootstrap-pending')),
                 'PARTIAL_STAGING_REQUIRES_REVIEW')
        for phase in ('ROLLBACK_INTENT','ROLLED_BACK'):
            if os.path.lexists(CONTROL/(phase+'.json')):
                need(read(CONTROL/(phase+'.json'),0o400)==canonical({'state':phase}),'POLICY_RECEIPT_DRIFT')
        helper_present=os.path.lexists(HELPER)
        def recheck():
            current_plan,current_helper=transaction()
            need(current_plan==p and current_helper==helper,'RESTORE_BACKUP_CHANGED')
            need(os.path.lexists(HELPER)==helper_present,'RESTORE_HELPER_CHANGED')
            if helper_present:need(read(HELPER,0o400)==helper,'RESTORE_HELPER_CHANGED')
            need(sha(read(CONTROL/'plan.json',0o400))==inputs['plan_sha256'],'RESTORE_PLAN_CHANGED')
        complete=(read(POLICY,0o440)==expected_policy() and read(EXEC,0o755)==expected_wrapper())
        if os.path.lexists(CONTROL/'ROLLED_BACK.json'):
            need(complete and baseline()==p['baseline'],'COMPLETED_POLICY_DRIFT')
            return {'state':'ROLLED_BACK','already_complete':True,'evidence_retained':True}
        policy_check(CONTROL/'old-sudoers');guard()
        if not os.path.lexists(CONTROL/'ROLLBACK_INTENT.json'):record('ROLLBACK_INTENT')
        coordinator.record_stage('POLICY_RESTORE','POLICY_RESTORE_INTENT',{'plan_sha256':inputs['plan_sha256']})
        try:
            # Reconcile each exact owned byte sequence; successful writes skip.
            guard();recheck()
            current=read(POLICY,0o440);need(current in (expected_policy(),new_policy()),'POLICY_CHANGED_BEFORE_RESTORE')
            if current!=expected_policy():replace(POLICY,expected_policy(),0o440)
            guard();recheck()
            current=read(EXEC,0o755);need(current in (expected_wrapper(),new_wrapper()),'WRAPPER_CHANGED_BEFORE_RESTORE')
            if current!=expected_wrapper():replace(EXEC,expected_wrapper(),0o755)
            need(baseline()==p['baseline'] and read(POLICY,0o440)==expected_policy()
                 and read(EXEC,0o755)==expected_wrapper(),'RESTORE_VERIFY')
            guard();record('ROLLED_BACK')
            result={'state':'ROLLED_BACK','already_complete':False,'evidence_retained':True}
            coordinator.record_stage('POLICY_RESTORE','POLICY_RESTORE_VERIFIED',result)
            return result
        except BaseException:
            coordinator.record_stage('POLICY_RESTORE','POLICY_RESTORE_UNKNOWN',{'evidence_retained':True})
            raise


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=('plan', 'install', 'verify', 'rollback')); args = parser.parse_args()
    owner(); print(canonical(globals()[args.action]()).decode())
if __name__ == '__main__': main()
