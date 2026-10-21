"""Candidate outbound-only connection worker; enrollment is not performed here.

Only fixed read-only operations are enrolled. This is not a P2 replacement,
installation writer, SDK launcher or arbitrary-command GitHub bot.
"""
import argparse
import base64
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .queue import Hold, Queue, TARGETS, canonical, decode, unique


REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
HOSTS = {'uk': 'iZd7oeikknn1z21sq6ji6zZ', 'korea': 'iZmj7a5kwr75qc1tul4kf9Z',
         'domestic': 'iZvt5t8tlrm8oiZ'}
ROLES = {'uk': 'xuanjun-ai-esc', 'korea': 'xuanjun-automation', 'domestic': 'xuanjun-automation'}
PREFIX = 'XJ_CLOUD_TASK_V1\n'


def protected_read(path, limit, owners=(0,)):
    path = Path(path)
    if not path.is_absolute():
        raise Hold('ABSOLUTE_PATH_REQUIRED')
    for parent in path.parents:
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise Hold('UNPROTECTED_PARENT')
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        s = os.fstat(stream.fileno())
        if (not stat.S_ISREG(s.st_mode) or s.st_uid not in owners
                or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1 or s.st_size > limit):
            raise Hold('UNPROTECTED_FILE')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise Hold('FILE_BOUND')
    return raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Network:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def json(self, request):
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(1048577)
            if len(raw) > 1048576:
                raise Hold('NETWORK_BOUND')
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise Hold('HTTP_' + str(exc.code)) from None
        except (OSError, ValueError):
            raise Hold('NETWORK_UNKNOWN_QUERY_EXISTING') from None


class Cloud:
    def __init__(self, credentials_ref, network):
        self.credentials_ref = credentials_ref
        self.network = network

    def rpc(self, credentials, endpoint, action, version, params):
        key, secret, token = credentials
        values = dict(params, Action=action, Version=version, Format='JSON',
                      AccessKeyId=key, SignatureMethod='HMAC-SHA1', SignatureVersion='1.0',
                      SignatureNonce=uuid.uuid4().hex,
                      Timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        if token:
            values['SecurityToken'] = token
        quote = lambda v: urllib.parse.quote(str(v), safe='~')
        encoded = '&'.join(quote(k) + '=' + quote(v) for k, v in sorted(values.items()))
        values['Signature'] = base64.b64encode(hmac.new((secret + '&').encode(),
            ('POST&%2F&' + quote(encoded)).encode(), hashlib.sha1).digest()).decode()
        req = urllib.request.Request('https://' + endpoint + '/',
                                     data=urllib.parse.urlencode(values).encode())
        value = self.network.json(req)
        if type(value) is not dict or 'Code' in value:
            raise Hold('CLOUD_RESPONSE')
        return value

    def session(self, target):
        # Always obtains a new STS session; no cached expired token is reused.
        account, region, instance = TARGETS[target]
        c = decode(protected_read(self.credentials_ref, 4096).decode())
        master = (c['access_key_id'], c['access_key_secret'], '')
        v = self.rpc(master, 'sts.aliyuncs.com', 'AssumeRole', '2015-04-01', {
            'RoleArn': 'acs:ram::' + account + ':role/' + ROLES[target],
            'RoleSessionName': 'xuanjun-connection-worker', 'DurationSeconds': 900})
        c = v['Credentials']
        return (c['AccessKeyId'], c['AccessKeySecret'], c['SecurityToken'])

    def call(self, target, action, extra):
        if action not in ('RunCommand', 'DescribeInvocationResult'):
            raise Hold('CLOUD_ACTION')
        account, region, instance = TARGETS[target]
        params = dict(extra, RegionId=region, InstanceId=instance)
        return self.rpc(self.session(target), 'swas.' + region + '.aliyuncs.com',
                        action, '2020-06-01', params)


def fixed_command(request):
    # Candidate project jobs must never fall through to the old probe builder.
    if request.get('operation') not in ('probe', 'fetch_os_release'):
        raise Hold('FIXED_OPERATION_NOT_ENROLLED')
    nonce = hashlib.sha256(canonical(request).encode()).hexdigest()
    read_file = request['operation'] == 'fetch_os_release'
    code = ("import os,json,hashlib,base64,stat\n"
            "v={'hostname':os.uname().nodename,'uid':os.getuid(),'nonce':" + repr(nonce) + "}\n")
    if read_file:
        code += ("f=os.open('/etc/os-release',os.O_RDONLY|os.O_NOFOLLOW)\n"
                 "with os.fdopen(f,'rb') as z:\n"
                 " s=os.fstat(z.fileno());assert stat.S_ISREG(s.st_mode) and s.st_size<=65536\n"
                 " b=z.read(65537);assert len(b)<=65536\n"
                 "v.update({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),"
                 "'base64':base64.b64encode(b).decode()})\n")
    code += 'print(json.dumps(v))\n'
    return "#!/bin/sh\nset -eu\nexec /usr/bin/python3 -I -B -c '" + code.replace("'", "'\\''") + "'\n"


def validate_result(request, invoke, response):
    result = response.get('InvocationResult', {})
    if (result.get('InvokeId') != invoke
            or result.get('InstanceId') != TARGETS[request['target']][2]):
        raise Hold('RESULT_TARGET')
    status = result.get('InvocationStatus')
    if status in ('Pending', 'Running', 'Stopping'):
        return None, None
    if status != 'Success' or type(result.get('ExitCode')) is not int or result['ExitCode'] != 0:
        return {'state': 'FAILED', 'invoke_id': invoke, 'exit_code': result.get('ExitCode')}, None
    raw = result.get('Output')
    if not isinstance(raw, str) or len(raw) > 131072:
        raise Hold('OUTPUT_BOUND')
    try:
        text = raw if raw.lstrip().startswith('{') else base64.b64decode(raw, validate=True).decode()
        body = json.loads(text, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise Hold('OUTPUT_FORMAT') from None
    if (body.get('hostname') != HOSTS[request['target']] or type(body.get('uid')) is not int
            or body['uid'] != 1000
            or body.get('nonce') != hashlib.sha256(canonical(request).encode()).hexdigest()):
        raise Hold('REMOTE_IDENTITY')
    receipt = {'state': 'SUCCESS', 'invoke_id': invoke, 'hostname': body['hostname'], 'uid': body['uid']}
    data = None
    if request['operation'] == 'fetch_os_release':
        data = base64.b64decode(body['base64'], validate=True)
        if (len(data) > 65536 or type(body['bytes']) is not int or len(data) != body['bytes']
                or hashlib.sha256(data).hexdigest() != body['sha256']):
            raise Hold('FILE_DIGEST')
        receipt.update(bytes=len(data), sha256=body['sha256'])
    return receipt, data


class Github:
    def __init__(self, token_ref, network, token_owner):
        self.token_ref, self.network, self.token_owner = token_ref, network, token_owner

    def call(self, suffix, data=None):
        token = protected_read(self.token_ref, 8192, (self.token_owner,)).decode().strip()
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                   'User-Agent': 'xuanjun-cloud-connection'}
        req = urllib.request.Request('https://api.github.com/repos/' + REPO + suffix,
                                     data=canonical(data).encode() if data is not None else None,
                                     headers=headers)
        return self.network.json(req)

    def comments(self, since):
        comments = []
        for page in range(1, 21):
            rows = self.call('/issues/17/comments?' + urllib.parse.urlencode({
                'since': since, 'per_page': 100, 'page': page}))
            if type(rows) is not list:
                raise Hold('COMMENT_RESPONSE')
            comments.extend(rows)
            if len(rows) < 100:
                return comments
        raise Hold('COMMENT_BOUND_NO_CURSOR_ADVANCE')


def receive(github, queue, since, now):
    outcomes = []
    for c in github.comments(since):
        body = c.get('body', '')
        if not body.startswith(PREFIX):
            continue
        actor = c.get('user', {}).get('id')
        if type(actor) is not int or actor not in queue.allowed_actors:
            outcomes.append({'comment_id': c.get('id'), 'state': 'REJECTED_ACTOR'})
            continue
        # Edited tasks are rejected rather than silently changing queued work.
        if c.get('created_at') != c.get('updated_at'):
            outcomes.append({'comment_id': c.get('id'), 'state': 'REJECTED_EDIT'})
            continue
        try:
            status = queue.submit(body[len(PREFIX):], actor, now)
            outcomes.append(dict(status, comment_id=c.get('id')))
        except (Hold, ValueError, TypeError):
            outcomes.append({'comment_id': c.get('id'), 'state': 'REJECTED_REQUEST'})
    return outcomes


def execute_ready(queue, cloud, request_id, now):
    request = queue.begin_dispatch(request_id, now)
    try:
        # The database dispatch intent commits BEFORE this network side effect.
        v = cloud.call(request['target'], 'RunCommand', {
            'CommandContent': fixed_command(request), 'Type': 'RunShellScript',
            'WorkingUser': 'admin', 'WorkingDir': '/home/admin', 'Timeout': 30,
            'Name': 'xuanjun-enrolled-readonly-task'})
        queue.record_invoke(request_id, v['InvokeId'])
    except BaseException:
        queue.unknown(request_id)
        raise


def query_existing(queue, cloud, request_id, file_sink):
    row = queue.db.execute('SELECT request_json FROM connection_jobs WHERE request_id=?',
                           (request_id,)).fetchone()
    request = decode(row[0]) if row else None
    status = queue.inspect(request_id)
    if status['state'] in ('SUCCESS', 'FAILED'):
        return status
    if not status['invoke_id']:
        queue.unknown(request_id)
        raise Hold('NO_INVOKE_UNKNOWN_NO_DISPATCH')
    response = cloud.call(request['target'], 'DescribeInvocationResult', {'InvokeId': status['invoke_id']})
    receipt, data = validate_result(request, status['invoke_id'], response)
    if receipt is not None:
        if data is not None:
            # Private authenticated transfer adapter is REQUIRED; never fall
            # back to public GitHub comment bodies, base64 or public Artifacts.
            receipt['file_ref'] = file_sink(request_id, data, receipt['sha256'])
        queue.terminal(request_id, status['invoke_id'], receipt)
    return queue.inspect(request_id)


def main():
    # Deliberately no default daemon enrollment or unsafe public file fallback.
    raise SystemExit('NOT_ENROLLED: reviewed host config and private file sink required')


if __name__ == '__main__':
    main()


class ExistingProjectFiles:
    """Source-only bridge to existing SUCCESS jobs, never dispatch/enrollment.

    recipient_provider is a trusted transport dependency, NOT a tool argument.
    No such authenticated provider exists in the installed stdio transport;
    leaving it absent always refuses. Tests may supply an offline fixture.
    """
    def __init__(self, db, catalogs=None, recipient_provider=None, enabled=False):
        self.db = db
        self.catalogs = catalogs
        self.recipient_provider = recipient_provider
        self.enabled = enabled

    def read(self, arguments, now):
        if self.enabled is not True:
            raise Hold('PROJECT_TRANSFER_DISABLED')
        if self.recipient_provider is None:
            raise Hold('AUTHENTICATED_RECIPIENT_SOURCE_MISSING')
        # Deliberately no request/metadata passed to the provider.
        recipient = self.recipient_provider()
        if type(recipient) is not str or not recipient:
            raise Hold('AUTHENTICATED_RECIPIENT_REQUIRED')
        if (type(arguments) is not dict or set(arguments) !=
                {'manifest_sha256', 'request_id', 'object_ref', 'offset'}):
            raise Hold('FIXED_OBJECT_ARGUMENTS')
        sha = arguments['manifest_sha256']
        if type(sha) is not str or self.catalogs is None or sha not in self.catalogs:
            raise Hold('APPROVED_PROJECT_CATALOG_REQUIRED')
        catalog, roots = self.catalogs[sha]
        if catalog.sha != sha:
            raise Hold('PROJECT_CATALOG_BINDING')
        from .private_transfer import export_chunk
        return export_chunk(self.db, catalog, roots, arguments['request_id'],
                            arguments['object_ref'], recipient, arguments['offset'], now)
