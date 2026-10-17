"""Template for one fixed domestic observation. Never installs or enrolls trust."""
import base64
import contextlib
import datetime
import hashlib
import json
import os
import re
import stat
import sys
import urllib.request

PAYLOAD_B64 = '__PAYLOAD_B64__'
PROBE_B64 = '__PROBE_B64__'
HOST = 'iZvt5t8tlrm8oiZ'
BASE = '/var/lib/xuanjun-customer-channel'
CHANNEL = BASE + '/channel.py'
HELPER = BASE + '/readonly-admission.py'
WRAPPER = '/usr/local/libexec/xuanjun-customer-channel'
POLICY = '/etc/sudoers.d/xuanjun-customer-channel'
TRUST = BASE + '/READONLY_ADMISSION_TRUST.json'
RECEIPT = BASE + '/readonly-admission-20261017'
CHANNEL_SHA = '0804e33edac6ad07a711456c0c15708266b2ad8a75c4cb3bdc5964a9b79a96bd'
PAYLOAD_SHA = '885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818'
PROBE_SHA = '118e3e972fd94a34647c1a289f449caf4eef40dbb444611d99f53d155cd148ba'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
PREFIX = 'XUANJUN_DOMESTIC_READONLY_ADMISSION\n'
SCOPE = 'domestic-runner-uid1002-fixed-inspect-account-once'
HASH_FIELDS = ('helper_sha256', 'wrapper_sha256', 'policy_sha256')
PIN_FIELDS = {'schema', 'comment_id', 'body_sha256', 'source_writer_principal',
              'reviewer_principal', 'owner_principal', 'custody_evidence_sha256',
              'nonce', 'issued_at', 'expires_at', 'review_source', 'github_author_id', 'github_app_id', *HASH_FIELDS}
PERMIT_FIELDS = PIN_FIELDS - {'comment_id', 'body_sha256'} | {
    'scope', 'host', 'runner_uid', 'max_executions', 'channel_sha256',
    'payload_sha256', 'probe_sha256', 'creation_authorized'}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            need(k not in out, 'DUPLICATE_KEY')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON_CONSTANT')))


def secure_parents(path):
    parent = os.path.dirname(path)
    while True:
        s = os.lstat(parent)
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             'UNSAFE_PARENT')
        if parent == '/':
            return
        parent = os.path.dirname(parent)


def secure_read(path, mode, limit=2097152):
    secure_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
             before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == mode and
             before.st_size <= limit, 'UNSAFE_FILE')
        raw = b''
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
            need(len(raw) <= limit, 'SIZE')
        after, named = os.fstat(fd), os.lstat(path)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink',
                'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(all(getattr(before, k) == getattr(after, k) == getattr(named, k)
                 for k in keys), 'FILE_DRIFT')
        return raw, (before.st_dev, before.st_ino)
    finally:
        os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('REDIRECT')


def fetch_comment(comment_id):
    url = 'https://api.github.com/repos/' + REPO + '/issues/comments/' + str(comment_id)
    # No environment proxy, authentication, cookies, or arbitrary endpoint.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                               'User-Agent': 'xuanjun-fixed-readonly-admission'})
    with opener.open(req, timeout=15) as response:
        need(response.status == 200 and response.geturl() == url, 'COMMENT_ENDPOINT')
        raw = response.read(131073)
    need(len(raw) <= 131072, 'COMMENT_SIZE')
    return strict_json(raw)


def timestamp(value):
    need(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value), 'TIME_FORMAT')
    return datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp()


def check_time(pin, now):
    start, end = timestamp(pin['issued_at']), timestamp(pin['expires_at'])
    need(0 < end - start <= 1800 and start <= now < end, 'EXPIRED_OR_FUTURE')


def validate_pin(pin, now):
    need(type(pin) is dict and set(pin) == PIN_FIELDS and type(pin['schema']) is int and pin['schema'] == 1, 'PIN_SCHEMA')
    need(type(pin['comment_id']) is int and pin['comment_id'] > 0, 'COMMENT_ID')
    for key in (*HASH_FIELDS, 'body_sha256', 'custody_evidence_sha256'):
        need(type(pin[key]) is str and re.fullmatch('[0-9a-f]{64}', pin[key]), 'HASH_SCHEMA')
    for key in ('source_writer_principal', 'reviewer_principal', 'owner_principal'):
        need(type(pin[key]) is str and re.fullmatch(r'[A-Za-z0-9@._:+/-]{3,128}', pin[key]), 'PRINCIPAL')
    need(pin['source_writer_principal'] != pin['reviewer_principal'], 'INDEPENDENCE')
    need(pin['owner_principal'] != pin['source_writer_principal'], 'OWNER_CUSTODY')
    need(type(pin['nonce']) is str and re.fullmatch('[0-9a-f]{64}', pin['nonce']), 'NONCE')
    need(pin['review_source'] == 'original-task5-pr122', 'REVIEW_SOURCE')
    for key in ('github_author_id', 'github_app_id'):
        need(type(pin[key]) is int and pin[key] > 0, 'PROVENANCE')
    check_time(pin, now)


def validate_comment(pin, comment):
    cid = pin['comment_id']
    need(type(comment) is dict and type(comment.get('id')) is int and comment['id'] == cid, 'COMMENT_ID')
    need(comment.get('url') == f'https://api.github.com/repos/{REPO}/issues/comments/{cid}' and
         comment.get('issue_url') == f'https://api.github.com/repos/{REPO}/issues/122' and
         comment.get('html_url') == f'https://github.com/{REPO}/pull/122#issuecomment-{cid}', 'COMMENT_LOCATION')
    need(comment.get('user', {}).get('id') == pin['github_author_id'], 'COMMENT_AUTHOR')
    need(comment.get('performed_via_github_app', {}).get('id') == pin['github_app_id'], 'COMMENT_APP')
    body = comment.get('body')
    need(type(body) is str and digest(body.encode('utf-8')) == pin['body_sha256'] and body.startswith(PREFIX), 'BODY_PIN')
    permit = strict_json(body[len(PREFIX):])
    need(type(permit) is dict and set(permit) == PERMIT_FIELDS, 'PERMIT_SCHEMA')
    for key in PIN_FIELDS - {'comment_id', 'body_sha256'}:
        need(type(permit[key]) is type(pin[key]) and permit[key] == pin[key], 'PERMIT_PIN')
    need(permit['scope'] == SCOPE and permit['host'] == HOST and type(permit['runner_uid']) is int and
         permit['runner_uid'] == 1002 and type(permit['max_executions']) is int and permit['max_executions'] == 1 and
         permit['creation_authorized'] is False and permit['channel_sha256'] == CHANNEL_SHA and
         permit['payload_sha256'] == PAYLOAD_SHA and permit['probe_sha256'] == PROBE_SHA, 'PERMIT_SCOPE')
    return permit


def now():
    return datetime.datetime.now(datetime.timezone.utc).timestamp()


def check_files(pin):
    control = BASE + '/readonly-bootstrap-20261017'
    need(not os.path.lexists(control + '/ROLLBACK_INTENT.json') and
         not os.path.lexists(control + '/ROLLED_BACK.json'), 'ROLLBACK_STARTED')
    need(strict_json(secure_read(control + '/VERIFIED.json', 0o400, 16384)[0]) == {'state':'VERIFIED'}, 'BOOTSTRAP_NOT_VERIFIED')
    plan = strict_json(secure_read(control + '/plan.json', 0o400)[0])
    need(plan.get('scope') == 'DOMESTIC_READONLY_BOOTSTRAP_20261017', 'BOOTSTRAP_SCOPE')
    channel, inode = secure_read(CHANNEL, 0o444)
    grant = secure_read(BASE + '/grant-state.json', 0o600, 16384)[0]
    need(digest(channel) == CHANNEL_SHA, 'CHANNEL_HASH')
    need(strict_json(grant).get('state') == 'GRANTED', 'CHANNEL_NOT_GRANTED')
    baseline = plan.get('baseline')
    required = {'device':inode[0], 'inode':inode[1], 'code_sha256':CHANNEL_SHA, 'grant_sha256':digest(grant)}
    need(type(baseline) is dict and set(baseline) == set(required) | {'interpreter'} and
         type(baseline.get('interpreter')) is dict, 'BASELINE_SCHEMA')
    # Interpreter identity is enrolled and verified by bootstrap; this direct
    # helper guard verifies canonical channel inode, code and grant continuity.
    need({key:baseline[key] for key in required} == required, 'ORIGINAL_INODE_OR_GRANT_DRIFT')
    for path, mode, field in ((HELPER, 0o400, 'helper_sha256'), (WRAPPER, 0o755, 'wrapper_sha256'), (POLICY, 0o440, 'policy_sha256')):
        need(digest(secure_read(path, mode)[0]) == pin[field], 'DEPLOYED_HASH')


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_receipt(name, value):
    # Only fixed internal names, never runner-controlled paths.
    need(name in ('started.json', 'result.json'), 'RECEIPT_NAME')
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd = os.open(RECEIPT + '/' + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(RECEIPT)


class Admission:
    def __init__(self):
        self.pin = None
        self.trust_raw = None
        self.consumed = False
        self.lock_inode = None

    def admit(self):
        self.trust_raw, _ = secure_read(TRUST, 0o600, 16384)
        self.pin = strict_json(self.trust_raw)
        validate_pin(self.pin, now())
        check_files(self.pin)
        self.lock_inode = secure_read(CHANNEL, 0o444)[1]
        validate_comment(self.pin, fetch_comment(self.pin['comment_id']))
        self.verify_current_comment()
        # A partial directory permanently consumes this single operation too.
        secure_parents(RECEIPT)
        os.mkdir(RECEIPT, 0o700)
        self.consumed = True
        sync_dir(BASE)
        write_receipt('started.json', {'state': 'CONSUMED_BEFORE_OBSERVATION', 'pin': self.pin,
                                     'scope': SCOPE, 'retry_allowed': False,
                                     'github_job_identity': 'NOT_ATTESTED'})
        self.revalidate()

    def verify_current_comment(self):
        validate_comment(self.pin, fetch_comment(self.pin['comment_id']))
        self.revalidate()  # Includes expiry after the bounded network read.

    def revalidate(self):
        check_time(self.pin, now())
        need(secure_read(TRUST, 0o600, 16384)[0] == self.trust_raw, 'TRUST_DRIFT')
        check_files(self.pin)
        need(secure_read(CHANNEL, 0o444)[1] == self.lock_inode, 'LOCK_INODE_DRIFT')


def run():
    need(len(sys.argv) == 1, 'NO_ARGUMENTS')
    need(os.uname().nodename == HOST and os.getuid() == os.geteuid() == 0 and os.environ.get('SUDO_UID') == '1002', 'EXECUTOR')
    payload, probe = base64.b64decode(PAYLOAD_B64, validate=True), base64.b64decode(PROBE_B64, validate=True)
    need(digest(payload) == PAYLOAD_SHA and digest(probe) == PROBE_SHA, 'EMBEDDED_HASH')
    pns = {'__name__': 'fixed_readonly_probe'}
    exec(compile(probe, 'fixed-readonly-probe', 'exec'), pns)
    ns = pns['load_approved'](payload)
    gate = Admission()
    original_os = ns['OS']

    class GatedOS(original_os):
        @contextlib.contextmanager
        def lock_existing(self, path):
            need(path == CHANNEL, 'LOCK_PATH')
            inode = secure_read(CHANNEL, 0o444)[1]
            with super().lock_existing(path):
                need(secure_read(CHANNEL, 0o444)[1] == inode, 'LOCK_INODE_DRIFT')
                gate.admit()
                need(gate.lock_inode == inode, 'LOCK_INODE_DRIFT')
                yield
                gate.revalidate()

    ns['OS'] = GatedOS
    try:
        result = pns['run'](ns)
        gate.verify_current_comment()
        result['admission'] = {'scope': SCOPE, 'comment_id': gate.pin['comment_id'],
                               'nonce': gate.pin['nonce'], 'github_job_identity': 'NOT_ATTESTED',
                               'audit_receipt_writes': True, 'retry_allowed': False}
        write_receipt('result.json', result)
        return result
    except Exception:
        if gate.consumed:
            try:
                write_receipt('result.json', {'state': 'UNKNOWN_CONSUMED_NO_RETRY', 'retry_allowed': False})
            except Exception:
                pass
        raise


if __name__ == '__main__':
    try:
        print(json.dumps(run(), sort_keys=True))
    except Exception:
        print('{"state":"HOLD_OR_UNKNOWN","retry_allowed":false}')
        sys.exit(1)
