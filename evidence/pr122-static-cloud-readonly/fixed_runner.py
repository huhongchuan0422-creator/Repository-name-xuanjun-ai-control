"""PR122 exact domestic staging observation; no install or arbitrary RPC interface.

CLI modes are workflow-internal fixed operations. Helpers, paths, hosts, commands,
and InvokeIds cannot be supplied through event inputs or command-line arguments.
Only mock tests should invoke functions locally before independent admission.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import time
import uuid
import zlib

from frozen_helper import HELPER_BYTES, HELPER_SHA256
from github_evidence import (GitHub, Hold, REPOSITORY, REPOSITORY_ID, BRANCH,
                             encoded, strict_json, require, live_admission)
from original_rpc import rpc as original_rpc

SCOPE = 'DOMESTIC_STAGING_READONLY'
REGION = 'cn-shanghai'
ROLE = 'acs:ram::1384884686754410:role/xuanjun-automation'
INSTANCE = '3a22c458934142eea89ec6e3bf481a57'
HOST = 'iZvt5t8tlrm8oiZ'
ENDPOINT = 'swas.cn-shanghai.aliyuncs.com'
STATE = Path('pr122-readonly-state')
SHA = re.compile(r'[0-9a-f]{64}')
SHA40 = re.compile(r'[0-9a-f]{40}')
INVOKE = re.compile(r'[A-Za-z0-9_-]{1,180}')
LABELS = ('ROOT_DISTRIBUTION_MANIFEST', 'ROOT_HOST_PINS', 'ROOT_STATIC_ARCHIVE',
          'ROOT_PREVIOUS_MANIFEST', 'ROOT_COMBINED_SOURCE', 'ROOT_PREFLIGHT_SOURCE',
          'ROOT_UNIFIED_SOURCE', 'RUNNER_APPROVED_ARCHIVE')
MAX_ENCODED_COMMAND = 16 * 1024
MAX_OUTPUT = 8192


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed_command(head, nonce):
    require(type(head) is str and SHA40.fullmatch(head)
            and type(nonce) is str and SHA.fullmatch(nonce), 'COMMAND_IDENTITY')
    require(type(HELPER_BYTES) is bytes and 0 < len(HELPER_BYTES) <= 100000
            and type(HELPER_SHA256) is str and SHA.fullmatch(HELPER_SHA256)
            and digest(HELPER_BYTES) == HELPER_SHA256, 'HELPER_NOT_FROZEN')
    payload = base64.b64encode(zlib.compress(HELPER_BYTES, 9)).decode()
    program = (
        'import base64,zlib,hashlib,json,os\n'
        'assert os.geteuid()==0 and os.uname().nodename==' + repr(HOST) + '\n'
        'b=zlib.decompress(base64.b64decode(' + repr(payload) + ',validate=True))\n'
        'assert len(b)==' + str(len(HELPER_BYTES)) + ' and hashlib.sha256(b).hexdigest()==' + repr(HELPER_SHA256) + '\n'
        "n={'__name__':'pr122_frozen_readonly'}\n"
        "exec(compile(b,'pr122_frozen_readonly.py','exec'),n)\n"
        "r=n['collect']()\n"
        "out={'schema':1,'scope':" + repr(SCOPE) + ",'head_sha':" + repr(head)
        + ",'nonce':" + repr(nonce) + ",'helper_sha256':" + repr(HELPER_SHA256)
        + ",'hostname':os.uname().nodename,'uid':os.geteuid(),'receipt':r}\n"
        "s=json.dumps(out,sort_keys=True,separators=(',',':'))\n"
        "assert len(s.encode())<=6000\nprint(s,flush=True)\n"
    )
    # No uncaught remote traceback or original exception may reach cloud logs.
    program = ('try:\n' + ''.join(' ' + line + '\n' for line in program.splitlines())
               + 'except BaseException:\n'
               + ' print(\'{"status":"HOLD_PRIVATE_DETAIL_WITHHELD"}\',flush=True)\n'
               + ' raise SystemExit(2)\n')
    shell = '#!/bin/sh\nset -eu\n/usr/bin/python3.11 -I -B -c ' + shlex.quote(program) + '\n'
    # SWAS command budget is checked on its base64 wire representation, not the
    # unencoded shell. CommandContent follows the original working raw signer.
    require(len(base64.b64encode(shell.encode())) <= MAX_ENCODED_COMMAND, 'COMMAND_WIRE_TOO_LARGE')
    return shell


def intent_for(admission, nonce):
    command = fixed_command(admission['head_sha'], nonce)
    return {'schema': 1, 'scope': SCOPE, 'repository': REPOSITORY,
            'repository_id': REPOSITORY_ID, 'branch': BRANCH,
            'head_sha': admission['head_sha'], 'run_id': admission['run_id'],
            'workflow_id': admission['workflow_id'], 'nonce': nonce,
            'helper_sha256': HELPER_SHA256, 'command_sha256': digest(command.encode()),
            'region': REGION, 'instance_id': INSTANCE, 'hostname': HOST,
            'working_user': 'root', 'action': 'RunCommand',
            'production_changes': 0, 'deployment_performed': False}


def validate_intent(intent, admission, source=False):
    source_run = admission['source_run_id'] if source else admission['run_id']
    expected = intent_for(dict(admission, run_id=source_run), intent.get('nonce'))
    require(type(intent) is dict and intent == expected, 'INTENT_BINDING_MISMATCH')
    return expected


def name(kind, head, run_id):
    require(kind in ('intent', 'dispatch'), 'ARTIFACT_KIND')
    return 'pr122-readonly-' + kind + '-' + head + '-' + str(run_id)


def local_write(filename, value, replace=False):
    require(filename in ('intent.json', 'dispatch.json', 'result.json'), 'LOCAL_RECORD_NAME')
    STATE.mkdir(mode=0o700, exist_ok=True)
    info = STATE.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'LOCAL_STATE_IDENTITY')
    target = STATE / filename
    temp = STATE / (filename + '.tmp') if replace else target
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(encoded(value)); stream.flush(); os.fsync(fd)
    finally:
        os.close(fd)
    if replace:
        os.replace(temp, target)
    fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def local_read(filename):
    path = STATE / filename
    info = STATE.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'LOCAL_STATE_IDENTITY')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_size <= 32768, 'LOCAL_RECORD_IDENTITY')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(32769)
    finally:
        os.close(fd)
    require(len(raw) <= 32768, 'LOCAL_RECORD_SIZE')
    value = strict_json(raw)
    require(encoded(value) == raw, 'LOCAL_RECORD_NONCANONICAL')
    return value


def verify_intent_artifact(api, admission, artifact_id=None, source=False):
    run_id = admission['source_run_id'] if source else admission['run_id']
    intent = api.read_artifact(run_id, name('intent', admission['head_sha'], run_id),
                               'intent.json', artifact_id=artifact_id)
    return validate_intent(intent, admission, source=source)


class FixedCloud:
    """No caller-selected endpoints, actions, hosts, commands, or credentials."""
    def __init__(self, master, rpc=original_rpc, mask=None):
        require(type(master) is tuple and len(master) == 3 and master[2] == ''
                and all(type(v) is str and v and '\n' not in v and '\r' not in v for v in master[:2]),
                'EXISTING_SECRETS_UNAVAILABLE')
        self._master = master
        self._rpc = rpc
        self._credentials = None
        self._mask = mask or (lambda _: None)

    def _assume(self):
        if self._credentials is not None:
            return
        try:
            response = self._rpc('sts.aliyuncs.com', '2015-04-01', 'AssumeRole', self._master,
                                 RoleArn=ROLE, RoleSessionName='pr122-staging-readonly', DurationSeconds=900)
            c = response['Credentials']
            credentials = tuple(c[k] for k in ('AccessKeyId', 'AccessKeySecret', 'SecurityToken'))
            require(all(type(v) is str and v and '\n' not in v and '\r' not in v for v in credentials),
                    'CREDENTIAL_RESPONSE_INVALID')
        except Exception:
            raise Hold('STS_UNAVAILABLE') from None
        for value in credentials:
            self._mask(value)
        self._credentials = credentials

    def dispatch(self, intent):
        self._assume()
        # No retry exists here or in the original signer.
        return self._rpc(ENDPOINT, '2020-06-01', 'RunCommand', self._credentials,
                         RegionId=REGION, InstanceId=INSTANCE, Type='RunShellScript',
                         WorkingUser='root', WorkingDir='/root', Timeout=120,
                         Name='pr122-domestic-staging-readonly',
                         CommandContent=fixed_command(intent['head_sha'], intent['nonce']))

    def query(self, invoke):
        require(type(invoke) is str and INVOKE.fullmatch(invoke), 'INVOKE_ID_SCHEMA')
        self._assume()
        return self._rpc(ENDPOINT, '2020-06-01', 'DescribeInvocationResult', self._credentials,
                         RegionId=REGION, InstanceId=INSTANCE, InvokeId=invoke)


def dispatch_once(api, event, env, cloud, artifact_id):
    admission = live_admission(api, event, env, 'dispatch')
    intent = verify_intent_artifact(api, admission, artifact_id)
    require(local_read('intent.json') == intent, 'LOCAL_INTENT_DRIFT')
    # Intent has been uploaded and independently re-downloaded before even STS.
    record = {'schema': 1, 'scope': SCOPE, 'intent_sha256': digest(encoded(intent)),
              'head_sha': intent['head_sha'], 'run_id': intent['run_id'],
              'instance_id': INSTANCE, 'command_sha256': intent['command_sha256'],
              'status': 'UNKNOWN_NO_INVOKE_NO_REPLAY', 'invoke_id': None}
    local_write('dispatch.json', record)
    try:
        response = cloud.dispatch(intent)
        invoke = response.get('InvokeId')
        require(type(invoke) is str and INVOKE.fullmatch(invoke), 'INVOKE_ID_SCHEMA')
        record.update(status='DISPATCHED_QUERY_ONLY', invoke_id=invoke)
        local_write('dispatch.json', record, replace=True)
        return record
    except Exception:
        # Never print exceptions: API code/body could contain private material.
        raise Hold('DISPATCH_UNKNOWN_NO_REPLAY') from None


def validate_dispatch(record, intent):
    expected = {'schema': 1, 'scope': SCOPE, 'intent_sha256': digest(encoded(intent)),
                'head_sha': intent['head_sha'], 'run_id': intent['run_id'],
                'instance_id': INSTANCE, 'command_sha256': intent['command_sha256'],
                'status': 'DISPATCHED_QUERY_ONLY', 'invoke_id': record.get('invoke_id')}
    require(type(record) is dict and record == expected
            and type(record['invoke_id']) is str and INVOKE.fullmatch(record['invoke_id']),
            'NO_TRUSTED_INVOKE_QUERY_ONLY_HOLD')
    return record['invoke_id']


def validate_receipt(value):
    require(type(value) is dict and set(value) == {'schema', 'scope', 'state', 'files',
            'production_changes', 'deployment_performed'} and type(value['schema']) is int
            and value['schema'] == 1 and value['scope'] == SCOPE
            and value['state'] in ('OBSERVATION_COMPLETE', 'HOLD')
            and type(value['production_changes']) is int and value['production_changes'] == 0
            and value['deployment_performed'] is False and type(value['files']) is list
            and len(value['files']) == len(LABELS), 'RECEIPT_SCHEMA')
    require(tuple(row.get('label') for row in value['files']) == LABELS, 'RECEIPT_FILE_SET')
    held = False
    for row in value['files']:
        require(type(row) is dict and row.get('state') in ('OBSERVED', 'ABSENT', 'HOLD', 'NOT_READ'), 'FILE_SCHEMA')
        if held:
            require(row == {'label': row['label'], 'state': 'NOT_READ'}, 'POST_HOLD_READ_REJECTED')
            continue
        require(row['state'] != 'NOT_READ', 'PREMATURE_NOT_READ')
        if row['state'] == 'OBSERVED':
            require(set(row) == {'label', 'state', 'size', 'sha256'} and type(row['size']) is int
                    and 0 <= row['size'] <= 64 * 1024 * 1024 and type(row['sha256']) is str
                    and SHA.fullmatch(row['sha256']), 'FILE_METADATA_SCHEMA')
        elif row['state'] == 'ABSENT':
            require(set(row) == {'label', 'state'}, 'FILE_ABSENT_SCHEMA')
        else:
            require(set(row) == {'label', 'state', 'reason'}
                    and row['reason'] in HELPER_HOLD_REASONS, 'FILE_REASON_SCHEMA')
            held = True
    require(value['state'] == ('HOLD' if any(r['state'] == 'HOLD' for r in value['files'])
                               else 'OBSERVATION_COMPLETE'), 'RECEIPT_STATE_MISMATCH')
    return value


# Updated from the frozen helper's finite reason set before release.
HELPER_HOLD_REASONS = frozenset(['DEADLINE', 'DIRECTORY_CHANGED', 'DIRECTORY_REPLACED', 'FILE_ACCESS', 'FILE_CHANGED', 'FILE_REPLACED', 'FILE_SIZE_LIMIT', 'FIXED_HOST_ROOT_REQUIRED', 'FIXED_PATH', 'NO_ARGUMENTS_ALLOWED', 'OUTPUT_LIMIT', 'OWNER_OR_MODE', 'PATH_APPEARED', 'PATH_DISAPPEARED', 'READ_SIZE_LIMIT', 'TOTAL_SIZE_LIMIT', 'UNSAFE_DIRECTORY', 'UNSAFE_FILE', 'UNSAFE_PATH'])


def validated_output(output, intent):
    require(type(output) is str and len(output.encode()) <= MAX_OUTPUT, 'OUTPUT_SIZE')
    try:
        value = strict_json(output)
    except Hold:
        try:
            raw = base64.b64decode(output, validate=True)
            require(len(raw) <= 6000, 'OUTPUT_SIZE')
            value = strict_json(raw)
        except Exception:
            raise Hold('OUTPUT_SCHEMA') from None
    require(type(value) is dict and set(value) == {'schema', 'scope', 'head_sha', 'nonce',
            'helper_sha256', 'hostname', 'uid', 'receipt'} and type(value['schema']) is int
            and value['schema'] == 1 and value['scope'] == SCOPE
            and value['head_sha'] == intent['head_sha'] and value['nonce'] == intent['nonce']
            and value['helper_sha256'] == intent['helper_sha256'] and value['hostname'] == HOST
            and type(value['uid']) is int and value['uid'] == 0, 'OUTPUT_BINDING')
    return validate_receipt(value['receipt'])


def query_only(cloud, intent, record, clock=time.monotonic, sleep=time.sleep):
    invoke = validate_dispatch(record, intent)
    end = clock() + 180
    while clock() < end:
        try:
            response = cloud.query(invoke)
            result = response.get('InvocationResult', {})
            require(result.get('InstanceId') == INSTANCE and result.get('InvokeId') == invoke,
                    'QUERY_IDENTITY')
            state = result.get('InvocationStatus')
            if state in ('Pending', 'Running', 'Stopping'):
                sleep(5)
                continue
            require(state == 'Success' and type(result.get('ExitCode')) is int
                    and result['ExitCode'] == 0, 'REMOTE_TERMINAL_NOT_SUCCESS')
            receipt = validated_output(result.get('Output'), intent)
            return {'schema': 1, 'scope': SCOPE, 'status': receipt['state'],
                    'head_sha': intent['head_sha'], 'invoke_id': invoke,
                    'command_sha256': intent['command_sha256'], 'receipt': receipt,
                    'retry_allowed': False, 'deployment_performed': False}
        except Exception:
            raise Hold('QUERY_UNVERIFIED_NO_REPLAY') from None
    raise Hold('QUERY_PENDING_PRESERVE_NO_REPLAY')


def workflow_main(mode, env=None):
    env = dict(os.environ if env is None else env)
    require(mode in ('prepare-dispatch', 'dispatch-once', 'query-current', 'query-previous'), 'CLI_MODE')
    raw = Path(env['GITHUB_EVENT_PATH']).read_bytes()
    require(len(raw) <= 1024 * 1024, 'EVENT_SIZE')
    event = strict_json(raw)
    api = GitHub(env.get('GH_TOKEN', ''))
    admission = live_admission(api, event, env, 'query' if mode == 'query-previous' else 'dispatch')
    if mode == 'prepare-dispatch':
        intent = intent_for(admission, uuid.uuid4().hex + uuid.uuid4().hex)
        local_write('intent.json', intent)
        return {'status': 'INTENT_READY_NOT_DISPATCHED'}
    artifact_id = None
    if mode == 'dispatch-once':
        raw_id = env.get('INTENT_ARTIFACT_ID', '')
        require(raw_id.isdecimal() and int(raw_id) > 0, 'INTENT_ARTIFACT_ID_REQUIRED')
        artifact_id = int(raw_id)
    # Constructing this object does not read a remote credential or call STS.
    cloud = FixedCloud((env.get('ALIYUN_ACCESS_KEY_ID', ''),
                        env.get('ALIYUN_ACCESS_KEY_SECRET', ''), ''),
                       mask=lambda value: print('::add-mask::' + value, flush=True))
    if mode == 'dispatch-once':
        return dispatch_once(api, event, env, cloud, artifact_id)
    source = mode == 'query-previous'
    intent = verify_intent_artifact(api, admission, source=source)
    run_id = intent['run_id']
    record = api.read_artifact(run_id, name('dispatch', intent['head_sha'], run_id), 'dispatch.json')
    result = query_only(cloud, intent, record)
    local_write('result.json', result)
    return result


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'CLI_MODE')
        outcome = workflow_main(sys.argv[1])
        print(json.dumps(outcome, sort_keys=True), flush=True)
        raise SystemExit(2 if outcome.get('status') == 'HOLD' else 0)
    except Exception:
        # Constant only, never raw service error, stdout, filename or credential.
        print('{"status":"HOLD_PRESERVE_NO_REPLAY","deployment_performed":false}', flush=True)
        raise SystemExit(2)
