"""Default-disabled, one-batch human witness record for PR17 B5.

This is an OS custody boundary, not cryptographic authentication of the two
people. The trusted UK registrar must inspect both original messages in the
authenticated Workbench before invoking ``register``. Deployment/enrollment is
separate. No CLI accepts a path, approval flag, or receipt supplied by a job.
"""
import fcntl
import contextlib
import errno
import hashlib
import json
import math
import os
import re
import stat
import threading
import time

ROOT = '/var/lib/xuanjun-cloud-connection/b5-new19-witness-staged-f0fe0d3978b7'
HOST = 'iZd7oeikknn1z21sq6ji6zZ'
JOB = '/opt/xuanjun-cloud-connection/l2-b5-staged-f0fe0d3978b7'
COMMIT = 'f0fe0d3978b72a11e4fa4cfb9928424d60124940'
PROJECT = 'p2-b5-material-analysis'
RECIPIENT = 'github-332398908'
SUBJECT = 'github:332398908'
HEX = re.compile(r'[0-9a-f]{64}\Z')
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
LOCK_WAIT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.02


class Hold(RuntimeError):
    pass


def check(ok, code):
    if not ok:
        raise Hold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def decode(raw):
    check(type(raw) is bytes and len(raw) <= 16384, 'WITNESS_RECORD_BOUND')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            check(key not in result, 'WITNESS_DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(Hold('WITNESS_NONFINITE')))
    except (ValueError, UnicodeError, TypeError):
        raise Hold('WITNESS_JSON') from None
    check(type(value) is dict and canonical(value) + b'\n' == raw,
          'WITNESS_CANONICAL')
    return value


def _regular(fd, mode, uid=0, gid=0):
    s = os.fstat(fd)
    check(stat.S_ISREG(s.st_mode) and s.st_uid == uid and s.st_gid == gid and
          s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == mode,
          'WITNESS_FILE_PROTECTION')
    return s


class WitnessStore:
    def __init__(self, root=ROOT, *, enabled=False, test_only=False, clock=time.time):
        check(enabled is True, 'WITNESS_DEFAULT_DISABLED')
        check(root == ROOT or test_only is True, 'WITNESS_FIXED_ROOT')
        self.root, self.clock, self.test_only = root, clock, test_only
        self._last_clock = None
        self._lease = threading.local()

    def _now(self):
        value = self.clock()
        check(type(value) in (int, float) and math.isfinite(value),
              'WITNESS_CLOCK_INVALID')
        check(self._last_clock is None or value >= self._last_clock,
              'WITNESS_CLOCK_ROLLBACK')
        self._last_clock = value
        return value

    def _admit_time(self, binding):
        now = self._now()
        check(binding['valid_from'] <= now < binding['valid_until'],
              'WITNESS_EXPIRED')
        return now

    def _expected_owner(self):
        return (os.geteuid(), os.getegid()) if self.test_only else (0, 0)

    def _lock_bounded(self, fd, mode, binding=None, revoke=False):
        """Acquire only with LOCK_NB, bounded by monotonic time and T1.

        A failed revocation is expressly NOT_COMPLETED; no holder is killed
        and no revocation record is published by the failed caller.
        """
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        timeout_code = ('REVOCATION_NOT_COMPLETED' if revoke else
                        'WITNESS_LOCK_TIMEOUT')
        while True:
            check(time.monotonic() < deadline, timeout_code)
            if binding is not None:
                self._admit_time(binding)
            try:
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Hold(timeout_code)
                time.sleep(min(LOCK_POLL_SECONDS, remaining))
            else:
                check(time.monotonic() < deadline, timeout_code)
                if binding is not None:
                    self._admit_time(binding)
                return

    def _open(self):
        if not self.test_only:
            check(os.geteuid() == os.getegid() == 0 and
                  os.environ.get('SUDO_UID') == '1000' and
                  os.uname().nodename == HOST, 'WITNESS_REGISTRAR_IDENTITY')
        check(os.path.isabs(self.root), 'WITNESS_ROOT_PATH')
        if not self.test_only:
            current = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
            try:
                for component in self.root.strip('/').split('/')[:-1]:
                    following = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                                        os.O_NOFOLLOW, dir_fd=current)
                    s = os.fstat(following)
                    if not (s.st_uid == 0 and not s.st_mode & 0o022):
                        os.close(following)
                        raise Hold('WITNESS_PARENT_PROTECTION')
                    os.close(current)
                    current = following
            finally:
                os.close(current)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        s = os.fstat(fd)
        uid, gid = self._expected_owner()
        if not (stat.S_ISDIR(s.st_mode) and s.st_uid == uid and s.st_gid == gid
                and stat.S_IMODE(s.st_mode) == 0o700):
            os.close(fd)
            raise Hold('WITNESS_ROOT_PROTECTION')
        return fd

    def _read(self, fd, name):
        f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=fd)
        try:
            before = _regular(f, 0o600, *self._expected_owner())
            check(before.st_size <= 16384, 'WITNESS_FILE_SIZE')
            raw = os.read(f, before.st_size + 1)
            after = os.fstat(f)
            named = os.stat(name, dir_fd=fd, follow_symlinks=False)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid,
                                   s.st_gid, s.st_nlink, s.st_size,
                                   s.st_mtime_ns, s.st_ctime_ns)
            check(len(raw) == before.st_size and
                  identity(before) == identity(after) == identity(named),
                  'WITNESS_READ_DRIFT')
            return decode(raw), digest(raw)
        finally:
            os.close(f)

    def _publish(self, fd, name, value, before_link=None):
        raw = canonical(value) + b'\n'
        check(len(raw) <= 16384, 'WITNESS_FILE_SIZE')
        try:
            os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(name)
        # Write a private temporary inode, then publish a non-overwriting hard
        # link. A crash leaves a pending name and must remain UNKNOWN.
        pending = '.' + name + '.pending'
        f = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=fd)
        try:
            _regular(f, 0o600, *self._expected_owner())
            written = 0
            while written < len(raw):
                written += os.write(f, raw[written:])
            os.fsync(f)
        finally:
            os.close(f)
        if before_link is not None:
            before_link()
        os.link(pending, name, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
        os.unlink(pending, dir_fd=fd)
        os.fsync(fd)
        return digest(raw)

    @staticmethod
    def _binding(binding):
        check(type(binding) is dict and set(binding) == {
            'batch', 'job', 'attempt', 'ids', 'catalog_sha256', 'recipient',
            'project', 'subject', 'commit', 'valid_from', 'valid_until'},
            'WITNESS_BINDING_FIELDS')
        check(binding['job'] == JOB and binding['commit'] == COMMIT and
              binding['recipient'] == RECIPIENT and
              binding['project'] == PROJECT and binding['subject'] == SUBJECT,
              'WITNESS_FIXED_IDENTITY')
        check(type(binding['batch']) is str and TOKEN.fullmatch(binding['batch'])
              and type(binding['attempt']) is str and TOKEN.fullmatch(binding['attempt'])
              and type(binding['catalog_sha256']) is str and
              HEX.fullmatch(binding['catalog_sha256']), 'WITNESS_BINDING_SYNTAX')
        ids = binding['ids']
        check(type(ids) is list and len(ids) == 19 and len(set(ids)) == 19 and
              all(type(x) is str and TOKEN.fullmatch(x) for x in ids),
              'WITNESS_IDS')
        check(type(binding['valid_from']) is int and
              type(binding['valid_until']) is int and
              binding['valid_until'] - binding['valid_from'] == 3600,
              'WITNESS_WINDOW')
        return digest(canonical(binding))

    @staticmethod
    def _record(role, binding_sha, source_id, source_raw, witness, observed_at):
        check(role in ('owner', 'analyst') and type(source_id) is str and
              TOKEN.fullmatch(source_id) and type(source_raw) is bytes and
              0 < len(source_raw) <= 16384 and type(witness) is str and
              TOKEN.fullmatch(witness) and type(observed_at) is int,
              'WITNESS_SOURCE_INPUT')
        # The source digest is custody evidence. It does not authenticate B5.
        return {'schema': 1, 'role': role, 'binding_sha256': binding_sha,
                'source_id': source_id, 'source_sha256': digest(source_raw),
                'witness_identity': witness, 'observed_at': observed_at,
                'witness_method': 'AUTHENTICATED_UK_WORKBENCH_AND_SUDO',
                'statement': 'ORIGINAL_SOURCE_CONTENT_MANUALLY_VERIFIED'}

    def register(self, binding, *, owner_source_id, owner_source_raw,
                 analyst_source_id, analyst_source_raw, witness_identity):
        """Trusted registrar only. Caller must inspect both distinct originals."""
        pin = self._binding(binding)
        check(owner_source_id != analyst_source_id and
              owner_source_raw != analyst_source_raw,
              'WITNESS_TWO_DISTINCT_ORIGINALS_REQUIRED')
        self._admit_time(binding)
        fd = self._open()
        try:
            lock = os.open('register.lock', os.O_RDWR | os.O_NOFOLLOW, dir_fd=fd)
            try:
                _regular(lock, 0o600, *self._expected_owner())
                self._lock_bounded(lock, fcntl.LOCK_EX, binding)
                # Preexisting or partial state is never overwritten/replayed.
                check(os.listdir(fd) == ['register.lock'],
                      'WITNESS_EXISTING_OR_PARTIAL_HOLD')
                now = self._admit_time(binding)
                owner = self._record('owner', pin, owner_source_id,
                                     owner_source_raw, witness_identity, int(now))
                analyst = self._record('analyst', pin, analyst_source_id,
                                       analyst_source_raw, witness_identity, int(now))
                a = self._publish(fd, 'owner.json', owner,
                                  before_link=lambda:self._admit_time(binding))
                b = self._publish(fd, 'analyst.json', analyst,
                                  before_link=lambda:self._admit_time(binding))
                return {'state': 'REGISTERED_NOT_CONSUMED',
                        'owner_sha256': a, 'analyst_sha256': b}
            finally:
                os.close(lock)
        finally:
            os.close(fd)

    def inspect(self, binding):
        pin = self._binding(binding)
        leased = getattr(self._lease, 'current', None)
        if leased is not None:
            check(leased[1] == pin, 'WITNESS_NESTED_BINDING')
            return self._inspect_locked(leased[0], binding, pin)
        fd = self._open()
        try:
            lock = os.open('register.lock', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            _regular(lock, 0o600, *self._expected_owner())
            self._lock_bounded(lock, fcntl.LOCK_SH, binding)
            return self._inspect_locked(fd, binding, pin)
        finally:
            if 'lock' in locals():
                os.close(lock)
            os.close(fd)

    def _inspect_locked(self, fd, binding, pin):
        names = set(os.listdir(fd))
        check(names <= {'register.lock','owner.json',
                'analyst.json','intent.json','revoked.json'} and
              {'owner.json','analyst.json'} <= names,
              'WITNESS_PARTIAL_OR_UNKNOWN_FILES')
        owner, a = self._read(fd, 'owner.json')
        analyst, b = self._read(fd, 'analyst.json')
        for role, row in (('owner', owner), ('analyst', analyst)):
            check(set(row) == {'schema','role','binding_sha256','source_id',
                  'source_sha256','witness_identity','observed_at',
                  'witness_method','statement'} and type(row['schema']) is int and
                  row['schema'] == 1 and
                  row['role'] == role and row['binding_sha256'] == pin and
                  row['witness_method'] == 'AUTHENTICATED_UK_WORKBENCH_AND_SUDO' and
                  row['statement'] == 'ORIGINAL_SOURCE_CONTENT_MANUALLY_VERIFIED' and
                  type(row['source_id']) is str and TOKEN.fullmatch(row['source_id']) and
                  type(row['source_sha256']) is str and HEX.fullmatch(row['source_sha256']) and
                  type(row['witness_identity']) is str and TOKEN.fullmatch(row['witness_identity']),
                  'WITNESS_RECORD_BINDING')
            check(type(row['observed_at']) is int and
                  binding['valid_from'] <= row['observed_at'] < binding['valid_until'],
                  'WITNESS_OBSERVATION_TIME')
        check(owner['source_id'] != analyst['source_id'] and
              owner['source_sha256'] != analyst['source_sha256'] and
              owner['witness_identity'] == analyst['witness_identity'],
              'WITNESS_DISTINCT_SOURCES')
        now = self._admit_time(binding)
        check(now >= max(owner['observed_at'], analyst['observed_at']),
              'WITNESS_CLOCK_ROLLBACK')
        # Revocation is immutable and checked at every admission call.
        try:
            revoked, _ = self._read(fd, 'revoked.json')
        except FileNotFoundError:
            revoked = None
        check(revoked is None, 'WITNESS_REVOKED')
        try:
            intent, _ = self._read(fd, 'intent.json')
        except FileNotFoundError:
            intent = None
        if intent is not None:
            check(type(intent.get('schema')) is int and
                  intent == {'schema': 1, 'binding_sha256': pin,
                             'pair_sha256': digest((a+b).encode()),
                             'job': JOB, 'attempt': binding['attempt']},
                  'WITNESS_INTENT_UNKNOWN')
        return {'binding_sha256': pin, 'owner_sha256': a,
                'analyst_sha256': b, 'pair_sha256': digest((a+b).encode()),
                'witness_identity': owner['witness_identity'],
                'owner_source_id': owner['source_id'],
                'analyst_source_id': analyst['source_id']}

    def consume_once(self, binding):
        """Durable intent before creating the job. A partial state is HOLD."""
        proof = self.inspect(binding)
        fd = self._open()
        try:
            lock = os.open('register.lock', os.O_RDWR | os.O_NOFOLLOW, dir_fd=fd)
            _regular(lock, 0o600, *self._expected_owner())
            self._lock_bounded(lock, fcntl.LOCK_EX, binding)
            # The earlier shared-lock observation is only a hint. Admission
            # is repeated under the exclusive lock immediately before intent.
            fresh = self._inspect_locked(fd, binding, self._binding(binding))
            check(fresh == proof, 'WITNESS_CONSUME_DRIFT')
            a = self._read(fd, 'owner.json')[1]
            b = self._read(fd, 'analyst.json')[1]
            check((a,b) == (proof['owner_sha256'],proof['analyst_sha256']),
                  'WITNESS_CONSUME_DRIFT')
            try:
                self._read(fd, 'revoked.json')
            except FileNotFoundError:
                pass
            else:
                raise Hold('WITNESS_REVOKED')
            self._admit_time(binding)
            self._publish(fd, 'intent.json', {
                'schema': 1, 'binding_sha256': proof['binding_sha256'],
                'pair_sha256': proof['pair_sha256'], 'job': JOB,
                'attempt': binding['attempt']},
                before_link=lambda:self._admit_time(binding))
            return proof['pair_sha256']
        finally:
            if 'lock' in locals():
                os.close(lock)
            os.close(fd)

    @contextlib.contextmanager
    def action(self, binding):
        """Serialize one bounded action with revocation's exclusive publish.

        A started action may finish; revoke returns only after its lease ends.
        No new action starts after a completed revoke. Backend timeouts bound
        the action; an unbounded backend can delay revocation and remains HOLD.
        """
        self._binding(binding)
        fd = self._open()
        lock = None
        try:
            lock = os.open('register.lock', os.O_RDONLY | os.O_NOFOLLOW,
                           dir_fd=fd)
            _regular(lock, 0o600, *self._expected_owner())
            self._lock_bounded(lock, fcntl.LOCK_SH, binding)
            self._inspect_locked(fd, binding, self._binding(binding))
            self._admit_time(binding)
            check(getattr(self._lease, 'current', None) is None,
                  'WITNESS_NESTED_ACTION')
            self._lease.current = (fd, self._binding(binding))
            try:
                yield
            finally:
                del self._lease.current
        finally:
            if lock is not None:
                os.close(lock)
            os.close(fd)

    def revoke(self, binding, reason_id):
        self._binding(binding)
        check(type(reason_id) is str and TOKEN.fullmatch(reason_id),
              'WITNESS_REVOCATION_REASON')
        fd = self._open()
        try:
            lock = os.open('register.lock', os.O_RDWR | os.O_NOFOLLOW, dir_fd=fd)
            _regular(lock, 0o600, *self._expected_owner())
            self._lock_bounded(lock, fcntl.LOCK_EX, revoke=True)
            self._read(fd, 'owner.json')
            self._read(fd, 'analyst.json')
            self._publish(fd, 'revoked.json', {'schema': 1,
                'binding_sha256': digest(canonical(binding)),
                'reason_id': reason_id, 'revoked_at': int(self._now())})
        finally:
            if 'lock' in locals():
                os.close(lock)
            os.close(fd)
