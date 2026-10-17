"""Fixed host OS adapter. Authoring/review only; never executed during preparation."""
import contextlib
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import account_candidate as c


def need(ok):
    if not ok:
        raise c.Denied('HOLD:OS_PRECONDITION')


def secure(path, directory=False):
    path = Path(path)
    need(path.is_absolute())
    for item in reversed((path, *path.parents)):
        row = os.lstat(item)
        is_dir = item != path or directory
        need(c.safe({'state': 'PRESENT', 'uid': row.st_uid, 'gid': row.st_gid,
                     'mode': row.st_mode, 'nlink': row.st_nlink}, directory=is_dir)
             if is_dir else row.st_uid == row.st_gid == 0
             and stat.S_ISREG(row.st_mode) and row.st_nlink == 1
             and not row.st_mode & 0o7022)
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
    need(row.st_uid == row.st_gid == 0 and stat.S_ISREG(row.st_mode)
         and row.st_nlink == 1 and stat.S_IMODE(row.st_mode) in (0o755, 0o4755))


class OS:
    def __init__(self):
        self.host = os.uname().nodename
        self.uid, self.euid = os.getuid(), os.geteuid()
        need(self.host == c.HOST and self.uid == self.euid == 0)
        self.reserved = False

    getpwnam = staticmethod(pwd.getpwnam)
    getgrnam = staticmethod(grp.getgrnam)
    lstat = staticmethod(os.lstat)

    @contextlib.contextmanager
    def lock_existing(self, path):
        need(path == c.ORIGINAL_LOCK)
        secure(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before, opened = os.lstat(path), os.fstat(fd)
            need((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def command(argv):
        # Only caller-defined constant commands below; no CLI command input.
        if argv[0] in ('/usr/bin/sudo', '/usr/bin/passwd'):
            secure_postcheck_tool(argv[0])
        else:
            secure(argv[0])
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30, shell=False,
                                env={'PATH': '/usr/sbin:/usr/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        need(len(result.stdout) < 131072 and len(result.stderr) < 131072)
        return result

    def platform_preconditions(self):
        # Shadow-utils flags and account defaults only. Fresh named NSS
        # lookups are performed by the core; no global NSS policy restriction.
        # Check both required postcheck tools before reserving/creating anything.
        # Rechecked again by command() immediately before each later use.
        secure_postcheck_tool('/usr/bin/passwd')
        secure_postcheck_tool('/usr/bin/sudo')
        help_result = self.command(('/usr/sbin/useradd', '--help'))
        need(help_result.returncode == 0)
        help_text = help_result.stdout.decode('utf-8')
        flags = all(flag in help_text for flag in ('--system', '--user-group',
                    '--no-create-home', '--home-dir', '--shell', '--password'))
        defaults = {}
        for line in read_public_config('/etc/login.defs').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                bits = line.split(None, 1)
                need(len(bits) == 2 and bits[0] not in defaults)
                defaults[bits[0]] = bits[1].strip()
        # Reject custom hooks entirely rather than run or inspect their contents.
        for path in ('/etc/shadow-maint/useradd-pre.d', '/etc/shadow-maint/useradd-post.d',
                     '/etc/useradd.d'):
            if os.path.lexists(path):
                secure(path, directory=True)
                need(not list(Path(path).iterdir()))
        for key in ('USERADD_CMD', 'USERGROUPS_ENAB'):
            if key == 'USERADD_CMD': need(key not in defaults)
        user_defaults = read_public_config('/etc/default/useradd')
        parsed = {}
        for line in user_defaults.splitlines():
            line = line.split('#', 1)[0].strip()
            if not line: continue
            need('=' in line)
            key, value = line.split('=', 1)
            need(key not in parsed)
            parsed[key] = value.strip().strip('"').strip("'")
        need(not parsed.get('GROUPS'))
        # Official shadow useradd documentation: -r without -F does not
        # allocate subordinate IDs. Support for -F itself is not a blocker.
        # Explicit password '!' is a disabled marker, not a secret credential.
        return dict(fixed_useradd_flags_supported=flags, mail_spool_suppressed=True,
                    no_subid_allocation=True, no_account_creation_hooks=True,
                    locked_password_explicit=True, no_supplementary_group_defaults=not parsed.get('GROUPS'),
                    no_privilege_policy_changes=True,
                    uid_min=int(defaults['SYS_UID_MIN']), uid_max=int(defaults['SYS_UID_MAX']),
                    gid_min=int(defaults['SYS_GID_MIN']), gid_max=int(defaults['SYS_GID_MAX']))

    @staticmethod
    def sync(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)

    def reserve_original_evidence(self, path):
        need(path == c.ACCOUNT_RECEIPT and not self.reserved)
        secure(Path(path).parent, directory=True)
        os.mkdir(path, 0o700)  # EEXIST, including partial result, is never retried.
        self.reserved = True
        self.sync(Path(path).parent)
        self.record_original_evidence(path, 'ACCOUNT_STARTED_NO_RETRY')

    def record_original_evidence(self, path, state):
        need(path == c.ACCOUNT_RECEIPT and self.reserved)
        need(state in ('ACCOUNT_STARTED_NO_RETRY', 'ACCOUNT_CREATE_INTENT_NO_RETRY',
                       'ACCOUNT_CREATED_VERIFIED_NO_RETRY', 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY'))
        secure(path, directory=True)
        file = Path(path) / (state + '.json')
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'state': state, 'host': c.HOST, 'account': c.ACCOUNT, 'retry_allowed': False}, f)
            f.flush(); os.fsync(f.fileno())
        self.sync(path)

    def run_fixed_useradd(self, argv):
        need(argv == c.PROPOSED_ARGV and self.reserved)
        return self.command(c.PROPOSED_ARGV).returncode

    def sudo_denied(self):
        # No arbitrary commands are submitted to sudo. -l only evaluates policy
        # for the fixed account. Any allowed command, error, or unrecognized
        # denial is a HOLD; raw output is never printed or retained in receipts.
        result = self.command(('/usr/bin/sudo', '-n', '-l', '-U', c.ACCOUNT))
        if result.returncode == 0:
            return False
        if result.returncode != 1:
            return None
        import re
        text = (result.stdout + result.stderr).decode('utf-8').strip()
        expected = r'User ' + re.escape(c.ACCOUNT) + r' is not allowed to run sudo on ' + re.escape(c.HOST) + r'\.?'
        return True if re.fullmatch(expected, text) else None

    def private_postcheck(self):
        account, group = pwd.getpwnam(c.ACCOUNT), grp.getgrnam(c.ACCOUNT)
        status = self.command(('/usr/bin/passwd', '-S', c.ACCOUNT))
        fields = status.stdout.decode('utf-8').split()
        locked = status.returncode == 0 and len(fields) >= 2 and fields[0] == c.ACCOUNT and fields[1] == 'L'
        no_subids = True
        for path in ('/etc/subuid', '/etc/subgid'):
            if os.path.lexists(path):
                rows = read_public_config(path).splitlines()
                no_subids = no_subids and not any(row.split(':', 1)[0] in
                          (c.ACCOUNT, str(account.pw_uid)) for row in rows)
        no_sudo = self.sudo_denied()
        return {'name': account.pw_name, 'uid': account.pw_uid, 'gid': account.pw_gid,
                'primary_group': group.gr_name, 'group_gid': group.gr_gid,
                'home': account.pw_dir, 'shell': account.pw_shell,
                'supplementary_groups': [g.gr_gid for g in grp.getgrall() if c.ACCOUNT in g.gr_mem],
                'password_locked': locked, 'home_absent': not os.path.lexists('/nonexistent')
                  and not os.path.lexists('/home/xuanjun-customer'),
                'mail_spool_absent': not os.path.lexists('/var/mail/xuanjun-customer')
                  and not os.path.lexists('/var/spool/mail/xuanjun-customer'),
                'no_subids': no_subids, 'no_sudo_grants': no_sudo}


def main(argv):
    need(argv == ['--apply'])
    # Instantiate only after exact explicit mode; OS constructor guards fixed host.
    return c.create_once(OS())


if __name__ == '__main__':
    import sys
    try:
        print(json.dumps(main(sys.argv[1:]), sort_keys=True))
    except BaseException:
        print('{"state":"HOLD","retry_allowed":false}')
        raise SystemExit(2) from None
