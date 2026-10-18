"""Read-only SWAS lookup + durable binding in ORIGINAL controller directory.

Does not dispatch, create a controller root, claim a Writer or authorize recovery.
The fd and binding callback must come from the admitted persistent controller.
No cloud credentials or raw command/output are persisted or returned.
"""
import base64
import fcntl
import hashlib
import json
import os
import re
import stat

REGION = 'cn-shanghai'
INSTANCE = '3a22c458934142eea89ec6e3bf481a57'
HOST = 'iZvt5t8tlrm8oiZ'
ENDPOINT = 'swas.cn-shanghai.aliyuncs.com'
SHA = re.compile(r'[0-9a-f]{64}')
ID = re.compile(r'[A-Za-z0-9_-]{1,180}')


class ReconciliationHold(RuntimeError):
    pass


def require(value, code):
    if not value: raise ReconciliationHold(code)


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def validate_intent(intent):
    require(type(intent) is dict and set(intent) == {'operation_id', 'source_sha256',
        'command_sha256', 'region', 'instance', 'host', 'action'}, 'ORIGINAL_INTENT_SCHEMA')
    require(all(type(intent[k]) is str and SHA.fullmatch(intent[k])
                for k in ('operation_id', 'source_sha256', 'command_sha256')), 'ORIGINAL_INTENT_DIGEST')
    require((intent['region'], intent['instance'], intent['host'], intent['action']) ==
        (REGION, INSTANCE, HOST, 'PR99_FINAL_DOMESTIC_START_V1'), 'ORIGINAL_INTENT_SCOPE')


def _content_matches(content, digest):
    if type(content) is not str or len(content) > 20000: return False
    if hashlib.sha256(content.encode()).hexdigest() == digest: return True
    try: raw = base64.b64decode(content, validate=True)
    except (ValueError, UnicodeError): return False
    return hashlib.sha256(raw).hexdigest() == digest


def locate_once(intent, rpc, credentials):
    """Find exactly one full-content-bound invocation; zero is NEVER no-effect.

    Aliyun documents that CommandName is ignored when InstanceId is supplied.
    Accordingly query the fixed instance and filter ALL bounded pages locally.
    A changed total or repeated InvokeId invalidates the whole observation.
    """
    validate_intent(intent)
    require(callable(rpc), 'EXPLICIT_READONLY_RPC_REQUIRED')
    expected_name = 'pr99-final-start-' + intent['operation_id'][:24]
    candidates = []
    total = None
    seen = set()
    for page in range(1, 21):
        try:
            response = rpc(ENDPOINT, '2020-06-01', 'DescribeCommandInvocations', credentials,
                RegionId=REGION, InstanceId=INSTANCE, PageNumber=page, PageSize=50)
        except Exception:
            raise ReconciliationHold('CLOUD_LOOKUP_UNKNOWN_NO_REPLAY') from None
        require(type(response) is dict and type(response.get('TotalCount')) is int
                and 0 <= response['TotalCount'] <= 1000, 'INVOCATION_LIST_BOUND')
        count = response['TotalCount']
        require(total is None or total == count, 'INVOCATION_LIST_CHANGED')
        total = count
        rows = response.get('CommandInvocations')
        require(type(rows) is list and len(rows) == min(50, max(0, count-(page-1)*50)), 'INVOCATION_PAGE_INCOMPLETE')
        for row in rows:
            require(type(row) is dict and type(row.get('InvokeId')) is str
                    and ID.fullmatch(row['InvokeId']) and row['InvokeId'] not in seen, 'INVOCATION_PAGE_IDENTITY')
            seen.add(row['InvokeId'])
            if row.get('CommandName') != expected_name: continue
            require(row.get('CommandType') == 'RunShellScript' and row.get('Username') == 'root'
                    and row.get('WorkingDir') == '/root' and row.get('Timeout') == 240,
                    'MATCHED_NAME_FOREIGN_COMMAND_SCOPE')
            require(_content_matches(row.get('CommandContent'), intent['command_sha256']),
                    'MATCHED_NAME_COMMAND_DIGEST_CONFLICT')
            peers = row.get('InvokeInstances')
            require(type(peers) is list and len(peers) == 1 and type(peers[0]) is dict
                    and peers[0].get('InstanceId') == INSTANCE, 'MATCHED_INVOCATION_TARGET')
            require(row.get('Parameters') in ('{}', '{}\n', {}), 'MATCHED_INVOCATION_PARAMETERS')
            candidates.append(row['InvokeId'])
        if page*50 >= count: break
    require(len(candidates) <= 1, 'AMBIGUOUS_INVOCATIONS_PRESERVE_NO_REPLAY')
    if not candidates:
        return {'status': 'UNKNOWN_NO_MATCH_NO_REPLAY', 'operation_id': intent['operation_id']}
    return {'status': 'EXACT_INVOKE_DISCOVERED_QUERY_RESULT_ONLY',
            'operation_id': intent['operation_id'], 'invoke_id': candidates[0]}


def _read(fd):
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid()
            and stat.S_IMODE(before.st_mode) == 0o600 and before.st_size <= 100000, 'ORIGINAL_RECORD_IDENTITY')
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []; size = 0
    while True:
        raw = os.read(fd, 16384)
        if not raw: break
        chunks.append(raw); size += len(raw)
        require(size <= 100000, 'ORIGINAL_RECORD_BOUND')
    raw = b''.join(chunks); after = os.fstat(fd)
    fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(fingerprint(before) == fingerprint(after) and len(raw) == before.st_size, 'ORIGINAL_RECORD_DRIFT')
    try: value = json.loads(raw)
    except (ValueError, UnicodeError): raise ReconciliationHold('ORIGINAL_RECORD_CORRUPT') from None
    require(raw == encode(value), 'ORIGINAL_RECORD_ENCODING')
    return value


def bind_missing_invoke(directory_fd, assert_directory_binding, rpc, credentials):
    """Extend original cloud-start.invocation.json; no second controller ledger.

    Retained dirfd is mandatory. The caller's original PathGuard/admission must
    verify that its name still refers to that fd; this module cannot grant that
    trust. A discovered ID is not a successful/failed operation receipt.
    Existing/partial/conflicting records are preserved, never overwritten.
    """
    require(type(directory_fd) is int and callable(assert_directory_binding), 'ADMITTED_DIRECTORY_FD_REQUIRED')
    st = os.fstat(directory_fd)
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid() and
            stat.S_IMODE(st.st_mode) == 0o700, 'ORIGINAL_CONTROLLER_DIRECTORY')
    assert_directory_binding()
    fd = os.open('cloud-start.intent.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        intent = _read(fd); validate_intent(intent)
        def current_binding():
            assert_directory_binding()
            s = os.stat('cloud-start.intent.json', dir_fd=directory_fd, follow_symlinks=False)
            own = os.fstat(fd)
            require((s.st_dev, s.st_ino) == (own.st_dev, own.st_ino) and _read(fd) == intent,
                    'ORIGINAL_INTENT_NAME_DRIFT')
        current_binding()
        def existing():
            try: f = os.open('cloud-start.invocation.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            except FileNotFoundError: return None
            try: r = _read(f)
            finally: os.close(f)
            invoke = r.get('invoke_id') if type(r) is dict else None
            require(type(invoke) is str and ID.fullmatch(invoke) and r == dict(intent, invoke_id=invoke),
                    'EXISTING_INVOCATION_CONFLICT')
            return r
        bound = existing()
        if bound:
            return {'status': 'EXISTING_INVOKE_QUERY_RESULT_ONLY',
                    'operation_id': intent['operation_id'], 'invoke_id': bound['invoke_id']}
        found = locate_once(intent, rpc, credentials)
        current_binding()
        if found['status'] == 'UNKNOWN_NO_MATCH_NO_REPLAY': return found
        record = dict(intent, invoke_id=found['invoke_id'])
        try:
            output = os.open('cloud-start.invocation.json',
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            require(existing() == record, 'CONCURRENT_INVOCATION_CONFLICT')
        else:
            try:
                raw = encode(record); pos = 0
                while pos < len(raw):
                    count = os.write(output, raw[pos:])
                    require(count > 0, 'INVOCATION_PERSIST_UNKNOWN')
                    pos += count
                os.fsync(output)
            finally: os.close(output)
            os.fsync(directory_fd)
        current_binding()
        require(existing() == record, 'RECOVERED_INVOCATION_POSTCHECK')
        return found
    finally: os.close(fd)


if __name__ == '__main__':
    raise SystemExit('NO_DISPATCH_OR_PRODUCTION_ENTRY')
