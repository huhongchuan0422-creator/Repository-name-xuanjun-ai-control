"""UK-only transport library: no CLI/credentials/dispatch workflow is enabled.
A future separately approved caller supplies rpc and a durable protected ledger.
The fixed command never reads Seed/Plan/Packet or imports a P2 application.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from scripts import p2_swas_receipt_validator as receipt

ROLE = 'acs:ram::1107191612880779:role/xuanjun-ai-esc'
ENDPOINT = 'swas.eu-west-1.aliyuncs.com'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def need(ok):
    if not ok:
        raise RuntimeError('TRANSPORT_HOLD_NO_REDISPATCH')


def command(nonce):
    need(receipt.token(nonce))
    code = ('import json,os,sys; print(json.dumps({'
            '"hostname":os.uname().nodename,"uid":os.geteuid(),'
            '"python":list(sys.version_info[:3]),"nonce":' + repr(nonce)
            + ',"private_inputs_read":False}))')
    return ('#!/bin/sh\nset -eu\nPYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -I -B -c '
            + "'" + code.replace("'", "'\\''") + "'\n")


class Ledger:
    """A held directory fd and exclusive immutable records; caller owns custody.
    The ledger directory must pre-exist on a persistent protected filesystem.
    No permission grant or private material is stored in public results.
    """
    def __init__(self, folder):
        self.fd = os.open(str(folder), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        if not (stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700):
            os.close(self.fd)
            raise RuntimeError('LEDGER_NOT_PRIVATE')

    def close(self):
        os.close(self.fd)

    def read(self, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                 and info.st_size <= 8192)
            raw = stream.read(8193)
            need(len(raw) <= 8192)
            return json.loads(raw, object_pairs_hook=receipt.unique)

    def create(self, name, value):
        raw = canonical(value)
        need(len(raw) <= 8192)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self.fd)


def dispatch_once(ledger, attempt, nonce, script_sha256, rpc):
    """Exactly one RunCommand attempt; receipt is NOT a P2 approval.
    rpc is a trusted authenticated adapter, never a URL from the remote response.
    This library does not obtain or assert a business execution permission.
    """
    need(receipt.token(attempt) and receipt.token(nonce))
    script = command(nonce)
    need(hashlib.sha256(script.encode()).hexdigest() == script_sha256)
    # Consume durably before the network call, including before unknown outcomes.
    ledger.create('dispatch-intent.json', {'state': 'DISPATCH_INTENT',
                  'attempt': attempt, 'nonce': nonce, 'script_sha256': script_sha256,
                  'instance_id': receipt.INSTANCE, 'region': receipt.REGION})
    try:
        result = rpc(ENDPOINT, 'RunCommand', RegionId=receipt.REGION,
                     InstanceId=receipt.INSTANCE, CommandContent=script,
                     Type='RunShellScript', WorkingUser='root', WorkingDir='/root',
                     Timeout=30, Name='p2-uk-transport-identity-only')
        invoke = result.get('InvokeId')
        need(receipt.token(invoke))
        ledger.create('invoke.json', {'invoke_id': invoke})
        return {'state': 'DISPATCHED', 'invoke_id': invoke}
    except BaseException:
        # Even an interrupted/failed write leaves intent consumed. Never resend.
        raise RuntimeError('DISPATCH_UNKNOWN_PRESERVE_NO_RETRY') from None


def poll_existing(ledger, rpc, max_queries=12):
    """Re-query an exact saved InvokeId only; never dispatch from this method."""
    need(type(max_queries) is int and 1 <= max_queries <= 36)
    # Refuse re-poll after an accepted or rejected terminal result.
    for name in ('verified.json', 'rejected.json'):
        try:
            ledger.read(name)
        except FileNotFoundError:
            continue
        raise RuntimeError('TERMINAL_RECEIPT_EXISTS')
    intent = ledger.read('dispatch-intent.json')
    invoke = ledger.read('invoke.json')['invoke_id']
    need(intent['instance_id'] == receipt.INSTANCE and intent['region'] == receipt.REGION
         and receipt.token(invoke) and receipt.token(intent['nonce'])
         and intent['script_sha256'] == hashlib.sha256(command(intent['nonce']).encode()).hexdigest())
    for unused in range(max_queries):
        try:
            result = rpc(ENDPOINT, 'DescribeInvocationResult', RegionId=receipt.REGION,
                         InstanceId=receipt.INSTANCE, InvokeId=invoke)
            detail = result.get('InvocationResult', {})
            need(detail.get('InvokeId') == invoke and detail.get('InstanceId') == receipt.INSTANCE)
            if detail.get('InvocationStatus') in ('Pending', 'Running', 'Stopping'):
                continue
            try:
                public = receipt.validate(detail, invoke, intent['nonce'])
            except receipt.Hold:
                ledger.create('rejected.json', {'state': 'TERMINAL_REJECTED', 'invoke_id': invoke})
                raise RuntimeError('REMOTE_RESULT_REJECTED') from None
            ledger.create('verified.json', public)
            return public
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError('QUERY_UNKNOWN_REQUERY_SAVED_INVOKE_ONLY') from None
    return {'state': 'QUERY_LIMIT_UNKNOWN', 'invoke_id': invoke, 'redispatch_allowed': False}
