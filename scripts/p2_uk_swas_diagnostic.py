"""UK-only transport candidates. Live execution requires external enrollment.
Cloud credentials stay Actions; the installed UK receiver consumes only pinned
identity requests and existing authenticated activation/ledger observation.
No Seed/Plan/Packet, worker launch or activation change is permitted.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
if __name__ == '__main__':
    # Isolated Python entry loads only the adjacent protected installed module,
    # never a scripts package from CWD or PYTHONPATH.
    try:
        import importlib.util
        target=Path(__file__).absolute().parent/'p2_swas_receipt_validator.py'
        actions_mode=len(sys.argv)>1 and sys.argv[1] in ('remote-run','cloud-query','a5-preflight','a5-query')
        if actions_mode:
            if (os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
                    or os.environ.get('P2_SPLIT_ENABLED')!='true'):
                raise RuntimeError('MANUAL_EVENT_REQUIRED')
            raw_policy=os.environ.get('P2_SPLIT_POLICY','')
            if len(raw_policy.encode())>32768:raise RuntimeError('POLICY_BOUND')
            def exact_pairs(items):
                result={}
                for k,v in items:
                    if k in result:raise RuntimeError('DUPLICATE_POLICY_KEY')
                    result[k]=v
                return result
            policy=json.loads(raw_policy,object_pairs_hook=exact_pairs)
            pins=policy['binding']['code_sha256']
        for code in (target,Path(__file__).absolute()):
            for node in (code,)+tuple(code.parents):
                meta=node.lstat()
                owners=(0,os.geteuid()) if actions_mode else (0,)
                if meta.st_uid not in owners or stat.S_ISLNK(meta.st_mode) or meta.st_mode & 0o022:
                    raise RuntimeError('UNPROTECTED_CODE')
                limit=32768 if code==target else 1048576
                if node==code and not (stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and meta.st_size<=limit):
                    raise RuntimeError('INVALID_CODE_FILE')
        if actions_mode:
            if (hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=pins['transport']
                    or hashlib.sha256(target.read_bytes()).hexdigest()!=pins['receipt']):
                raise RuntimeError('SOURCE_PINS_MISMATCH')
        spec=importlib.util.spec_from_file_location('p2_fixed_receipt',str(target))
        receipt=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(receipt)
    except BaseException:
        print('{"state":"HOLD","redispatch_allowed":false}',flush=True)
        raise SystemExit(2) from None
else:
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


def recovery_snapshot(ledger):
    """Read a stable durable checkpoint. Never dispatch, repair, or acquire keys.
    Caller must hold the same exclusive lock used for dispatch. Even an empty
    ledger is not a fresh approval. Corruption/partial writes remain HOLD.
    """
    names=('dispatch-intent.json','invoke.json','verified.json','rejected.json')
    def capture():
        values={}
        for name in names:
            try: values[name]=ledger.read(name)
            except FileNotFoundError: pass
        return values
    data=capture()
    need(data==capture())
    result={'redispatch_allowed':False,'p2_accepted':False,
            'requires_fresh_permission':True}
    if not data:
        result['state']='NO_DISPATCH_RECORD_NO_AUTHORITY'
        return result
    intent=data.get('dispatch-intent.json')
    need(type(intent) is dict and set(intent)=={
        'state','attempt','nonce','script_sha256','instance_id','region'})
    need(intent['state']=='DISPATCH_INTENT' and receipt.token(intent['attempt'])
         and receipt.token(intent['nonce']) and intent['instance_id']==receipt.INSTANCE
         and intent['region']==receipt.REGION and intent['script_sha256']==
         hashlib.sha256(command(intent['nonce']).encode()).hexdigest())
    invoke=data.get('invoke.json')
    if invoke is None:
        need(set(data)=={'dispatch-intent.json'})
        result['state']='DISPATCH_UNKNOWN_NO_INVOKE_NO_RETRY'
        return result
    need(type(invoke) is dict and set(invoke)=={'invoke_id'}
         and receipt.token(invoke['invoke_id']))
    result['invoke_id']=invoke['invoke_id']
    verified=data.get('verified.json'); rejected=data.get('rejected.json')
    need(not (verified is not None and rejected is not None))
    if verified is not None:
        # Revalidate stored public bytes through the original strict validator.
        need(type(verified) is dict)
        body={'hostname':verified.get('hostname'),'uid':verified.get('uid'),
              'python':verified.get('python'),'nonce':intent['nonce'],
              'private_inputs_read':verified.get('private_inputs_read')}
        expected=receipt.validate({'InvokeId':invoke['invoke_id'],
            'InstanceId':receipt.INSTANCE,'InvocationStatus':'Success',
            'ExitCode':0,'Output':json.dumps(body)},invoke['invoke_id'],intent['nonce'])
        need(verified==expected)
        result['state']='TERMINAL_VERIFIED_NO_REPLAY'
    elif rejected is not None:
        need(rejected=={'state':'TERMINAL_REJECTED','invoke_id':invoke['invoke_id']})
        result['state']='TERMINAL_REJECTED_NO_REPLAY'
    else:
        result['state']='QUERY_SAVED_INVOKE_ONLY'
    return result


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
            raise RuntimeError('QUERY_HOLD_REQUERY_SAVED_INVOKE_ONLY') from None
        except Exception:
            raise RuntimeError('QUERY_UNKNOWN_REQUERY_SAVED_INVOKE_ONLY') from None
    return {'state': 'QUERY_LIMIT_UNKNOWN', 'invoke_id': invoke, 'redispatch_allowed': False}


class AuthenticatedRPC:
    """Fixed UK RPC adapter. No retries, redirects, proxies or raw errors.
    master credentials are provided by the protected caller, never source/CLI.
    """
    def __init__(self, key, secret, opener=None, clock=None):
        import time
        import urllib.request
        self.clock = clock or time.monotonic
        self.deadline = self.clock() + 180
        self.credentials = (key, secret, '')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())

    def remaining(self):
        remaining = self.deadline - self.clock()
        need(remaining > 0)
        return min(20, remaining)

    def request(self, endpoint, action, **params):
        import base64
        import datetime
        import hmac
        import urllib.parse
        import urllib.request
        import uuid
        need((endpoint == 'sts.aliyuncs.com' and action == 'AssumeRole')
             or (endpoint == ENDPOINT and action in ('RunCommand', 'DescribeInvocationResult')))
        key, secret, session = self.credentials
        need(all(type(v) is str and v and '\n' not in v and '\r' not in v for v in (key, secret)))
        version = '2015-04-01' if action == 'AssumeRole' else '2020-06-01'
        values = dict(params, Action=action, Version=version, Format='JSON', AccessKeyId=key,
                      SignatureMethod='HMAC-SHA1', SignatureVersion='1.0',
                      SignatureNonce=uuid.uuid4().hex,
                      Timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        if session:
            values['SecurityToken'] = session
        quote = lambda x: urllib.parse.quote(str(x), safe='~')
        encoded = '&'.join(quote(k)+'='+quote(v) for k,v in sorted(values.items()))
        values['Signature'] = base64.b64encode(hmac.new(
            (secret+'&').encode(), ('POST&%2F&'+quote(encoded)).encode(), hashlib.sha1).digest()).decode()
        req = urllib.request.Request('https://'+endpoint+'/',
            data=urllib.parse.urlencode(values).encode(),
            headers={'Content-Type':'application/x-www-form-urlencoded'}, method='POST')
        try:
            with self.opener.open(req, timeout=self.remaining()) as response:
                raw = response.read(262145)
            need(len(raw) <= 262144)
            value = json.loads(raw, object_pairs_hook=receipt.unique)
            need(type(value) is dict and 'Code' not in value)
            return value
        except Exception:
            raise RuntimeError('AUTHENTICATED_RPC_UNKNOWN_NO_RETRY') from None

    def assume(self):
        value = self.request('sts.aliyuncs.com','AssumeRole', RoleArn=ROLE,
                             RoleSessionName='p2-uk-reviewed-transport',DurationSeconds=900)
        try:
            c=value['Credentials']
            values=(c['AccessKeyId'],c['AccessKeySecret'],c['SecurityToken'])
            need(all(type(v) is str and v and '\r' not in v and '\n' not in v for v in values))
            self.credentials=values
        except Exception:
            raise RuntimeError('STS_CREDENTIAL_RESPONSE_REJECTED') from None

    def __call__(self, endpoint, action, **params):
        need(endpoint == ENDPOINT and params.get('RegionId') == receipt.REGION
             and params.get('InstanceId') == receipt.INSTANCE)
        need(bool(self.credentials[2]))
        return self.request(endpoint, action, **params)



def consume_remote_identity(ledger, request, expected, activation, broker,
                            check_approval, now):
    """UK half of a split caller. No cloud keys, DB writes or worker start.

    activation/broker are the existing ActivationStore/BrokerObservationClient;
    expected and check_approval come from the protected installed entry, never
    the Actions payload. This API is not itself an installed/authorized entry.
    The durable directory is provisioned separately; no mkdir or enrollment.
    """
    import fcntl
    import math
    import sys
    need(type(request) is dict and type(expected) is dict and request==expected)
    keys={'schema','operation','attempt','nonce','task_id','lease_owner',
          'fence','activation','expires_unix','approval_sha256'}
    need(set(request)==keys and type(request['schema']) is int and request['schema']==1
         and request['operation']=='UK_READONLY_IDENTITY'
         and all(receipt.token(request[k]) for k in ('attempt','nonce'))
         and type(request['task_id']) is str and 1<=len(request['task_id'])<=256
         and '\x00' not in request['task_id']
         and type(request['lease_owner']) is str and bool(request['lease_owner'])
         and type(request['fence']) is int and request['fence']>=0
         and type(request['approval_sha256']) is str
         and re.fullmatch('[0-9a-f]{64}',request['approval_sha256']) is not None
         and type(request['expires_unix']) in (int,float)
         and math.isfinite(request['expires_unix']))
    active=request['activation']
    active_keys={'ledger_uuid','generation','epoch','instance','db_path','ledger_socket'}
    need(type(active) is dict and set(active)==active_keys)
    digest=hashlib.sha256(canonical(request)).hexdigest()
    fd=os.open('remote.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=ledger.fd)
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink==1
             and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def gate():
            clock=now()
            need(type(clock) in (int,float) and math.isfinite(clock)
                 and clock<request['expires_unix'])
            # Approval checker must bind the full exact request, source and scope.
            need(check_approval(request,digest) is True)
            before=activation.read(require_active=True)
            need(before.get('state')=='ACTIVE'
                 and all(type(before.get(k)) is type(active[k]) and before[k]==active[k]
                         for k in active_keys))
            observation=broker.observation(request['task_id'])
            need(type(observation) is dict and observation.get('task_id')==request['task_id']
                 and observation.get('lease_owner')==request['lease_owner']
                 and type(observation.get('fence')) is int
                 and observation['fence']==request['fence']
                 and observation.get('state')=='RUNNING')
            expiry=observation.get('lease_until')
            need(type(expiry) in (int,float) and math.isfinite(expiry) and expiry>clock)
            for k in ('ledger_uuid','generation','epoch','instance','db_path'):
                need(type(observation.get(k)) is type(active[k]) and observation[k]==active[k])
            after=activation.read(require_active=True)
            need(before==after)
            finished=now()
            need(type(finished) in (int,float) and math.isfinite(finished)
                 and finished<request['expires_unix'] and finished<expiry)
            return finished
        gate()
        # Never return a cached success under stale/revoked authority.
        try: consumed=ledger.read('remote-intent.json')
        except FileNotFoundError: consumed=None
        if consumed is not None:
            need(consumed=={'request_sha256':digest,'state':'REMOTE_IDENTITY_INTENT'})
            try: result=ledger.read('remote-result.json')
            except FileNotFoundError:
                return {'state':'REMOTE_EXECUTION_UNKNOWN','redispatch_allowed':False}
            need(type(result) is dict and set(result)=={'request_sha256','receipt'}
                 and result['request_sha256']==digest)
            detail={'InvokeId':'local_identity','InstanceId':receipt.INSTANCE,
                    'InvocationStatus':'Success','ExitCode':0,
                    'Output':json.dumps(result['receipt'])}
            receipt.validate(detail,'local_identity',request['nonce'])
            gate()
            return {'state':'REMOTE_RESULT_REPLAY','request_sha256':digest,
                    'receipt':result['receipt'],'redispatch_allowed':False}
        ledger.create('remote-intent.json',{'request_sha256':digest,
                      'state':'REMOTE_IDENTITY_INTENT'})
        gate()
        body={'hostname':os.uname().nodename,'uid':os.geteuid(),
              'python':list(sys.version_info[:3]),'nonce':request['nonce'],
              'private_inputs_read':False}
        receipt.validate({'InvokeId':'local_identity','InstanceId':receipt.INSTANCE,
            'InvocationStatus':'Success','ExitCode':0,'Output':json.dumps(body)},
            'local_identity',request['nonce'])
        gate()
        ledger.create('remote-result.json',{'request_sha256':digest,'receipt':body})
        return {'state':'REMOTE_IDENTITY_COMPLETE','request_sha256':digest,
                'receipt':body,'redispatch_allowed':False}
    finally:
        os.close(fd)


# Split transport v1: public data travels through SWAS; credentials stay Actions.
REMOTE_ENTRY = '/usr/local/libexec/xuanjun-p2-swas/transport.py'
RUNTIME_MODULES = ('activation_control', 'ledger_read_projection',
                   'ledger_read_transport', 'ledger_read_client', 'ledger_server_identity')


def split_authorize(policy, binding, body, now):
    import math
    need(type(now) in (int,float) and math.isfinite(now))
    need(policy['enabled'] is True and policy['revoked'] is False
         and all(type(policy[k]) is str and 1<=len(policy[k])<=256
                 for k in ('reviewer_principal','source_writer_principal'))
         and policy['reviewer_principal'] != policy['source_writer_principal']
         and all(type(policy[k]) is str and re.fullmatch('[0-9a-f]{64}',policy[k])
                 for k in ('custody_evidence_sha256','approval_body_sha256'))
         and type(body) is str and len(body.encode())<=16384
         and hashlib.sha256(body.encode()).hexdigest()==policy['approval_body_sha256'])
    need(body.startswith('P2_UK_SPLIT_ONCE\n'))
    permit=json.loads(body.split('\n',1)[1],object_pairs_hook=receipt.unique)
    need(set(permit)=={'decision','binding','issued_unix','expires_unix',
                      'max_executions','install_allowed','private_inputs_allowed'})
    need(permit['decision']==('A5_PREFLIGHT_APPROVED' if binding.get('operation') in ('A5_PREFLIGHT','A5_QUERY') else 'UK_SPLIT_APPROVED') and permit['binding']==binding
         and type(permit['max_executions']) is int and permit['max_executions']==1
         and permit['install_allowed'] is False and permit['private_inputs_allowed'] is False
         and type(permit['issued_unix']) is int and type(permit['expires_unix']) is int
         and permit['issued_unix']<=now<permit['expires_unix']
         and 0<permit['expires_unix']-permit['issued_unix']<=7200)
    return True


A5_SCRIPT = '/usr/local/libexec/xuanjun-p2-site/P2_SITE_ENTRY.py'
A5_SHA = '92413e219578fe3fd55a72c00ce8236817354216cc45b4af40577a27104a84e0'

def a5_command(request):
    need(request.get('purpose')=='A5_METADATA_PREFLIGHT_ONLY' and
         receipt.token(request.get('attempt')) and receipt.token(request.get('nonce')))
    # The externally custodied script must already be present, exact and immutable.
    return ("#!/bin/sh\nset -eu\n"
            "printf '%s  %s\n' '"+A5_SHA+"' '"+A5_SCRIPT+"' | sha256sum -c - >/dev/null\n"
            "exec /usr/bin/python3 -I -B "+A5_SCRIPT+" preflight\n")

def a5_validate(detail, invoke):
    need(detail.get('InvokeId')==invoke and detail.get('InstanceId')==receipt.INSTANCE
         and detail.get('InvocationStatus')=='Success' and type(detail.get('ExitCode')) is int
         and detail['ExitCode']==0)
    raw=detail.get('Output')
    need(type(raw) is str and len(raw.encode())<=8192)
    o=json.loads(raw,object_pairs_hook=receipt.unique)
    need(type(o) is dict and set(o)=={'schema','hostname','uid','python','paths','state',
         'mutations','activation','unique_writer','private_materials_read','install_authorized'}
         and type(o['schema']) is int and o['schema']==1
         and o['hostname']==receipt.HOST and type(o['uid']) is int and o['uid']==0
         and type(o['python']) is list and len(o['python'])==3
         and all(type(v) is int for v in o['python']) and o['python'][:2]==[3,6]
         and type(o['paths']) is dict and len(o['paths'])<=32
         and o['state']=='METADATA_ONLY_NOT_WRITER_OR_TRUST_VERIFICATION'
         and type(o['mutations']) is int and o['mutations']==0
         and o['activation']=='NOT_OBSERVED' and o['unique_writer']=='UNKNOWN'
         and o['private_materials_read'] is False and o['install_authorized'] is False)
    return {'state':'A5_METADATA_PREFLIGHT_VERIFIED','invoke_id':invoke,
            'redispatch_allowed':False,'private_inputs_read':False,
            'writer_verified':False,'install_authorized':False}

def remote_command(request):
    import base64
    raw=canonical(request)
    need(len(raw)<=8192)
    encoded=base64.b64encode(raw).decode('ascii')
    # No caller-controlled shell words, path or Python code. stdin is JSON data.
    return ("#!/bin/sh\nset -eu\nprintf '%s' '"+encoded+"' | base64 -d | "
            '/usr/bin/python3 -I -B '+REMOTE_ENTRY+' receive-identity\n')


def protected_code(path, digest):
    path=Path(path)
    need(path.is_absolute() and type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest))
    for node in (path,)+tuple(path.parents):
        s=node.lstat()
        need(s.st_uid==0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode & 0o022)
        if node!=path:need(stat.S_ISDIR(s.st_mode))
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=1048576)
        raw=stream.read(1048577);after=os.fstat(stream.fileno())
        need((before.st_dev,before.st_ino,before.st_mtime_ns,before.st_size)==
             (after.st_dev,after.st_ino,after.st_mtime_ns,after.st_size))
    need(hashlib.sha256(raw).hexdigest()==digest)
    return raw


def remote_factory(policy):
    """Load only five pinned existing read/activation modules, no broker start."""
    import importlib.util
    import sys
    pins=policy['runtime_files']
    need(type(pins) is dict and set(pins)==set(RUNTIME_MODULES))
    data={}
    for name in RUNTIME_MODULES:
        need(set(pins[name])=={'path','sha256'})
        data[name]=protected_code(pins[name]['path'],pins[name]['sha256'])
    # Fail if a preloaded module could bypass the pinned closure.
    need(not any(name in sys.modules for name in RUNTIME_MODULES))
    for name in RUNTIME_MODULES:
        module=importlib.util.module_from_spec(importlib.util.spec_from_loader(name,loader=None))
        module.__file__=pins[name]['path']
        sys.modules[name]=module
        try:exec(compile(data[name],pins[name]['path'],'exec'),module.__dict__)
        except BaseException:
            sys.modules.pop(name,None)
            raise
    cfg=policy['activation_paths']
    need(set(cfg)=={'descriptor','epoch_journal','lock'})
    activation=sys.modules['activation_control'].ActivationStore(
        cfg['descriptor'],cfg['epoch_journal'],cfg['lock'])
    # Do not load/activate socket units or create an ACTIVE descriptor.
    activation.read(require_active=True)
    verifier=sys.modules['ledger_server_identity'].load_server_verifier(activation=activation)
    transport=sys.modules['ledger_read_transport'].AuthenticatedLedgerReadTransport(verifier)
    broker=sys.modules['ledger_read_client'].BrokerObservationClient(activation,transport)
    return activation,broker


def receive_identity(request, policy_path=None):
    """Installed UK entry. Caller cannot supply paths, policy, keys or code."""
    import time
    need(os.getuid()==os.geteuid()==0 and os.uname().nodename==receipt.HOST)
    path=Path(policy_path) if policy_path is not None else CONTROL/'REMOTE_POLICY.json'
    policy,policy_sha=protected_json(path)
    need(type(request) is dict and request==policy['request'])
    need(set(policy['target_code'])=={'transport','receipt'})
    for name,module in (('transport',Path(__file__).absolute()),('receipt',Path(receipt.__file__).absolute())):
        item=policy['target_code'][name]
        need(item['path']==str(module) and
             item['sha256']==policy['binding']['code_sha256'][name])
        protected_code(module,item['sha256'])
    binding=policy['binding']
    target_config={k:policy[k] for k in ('request','target_code','runtime_files','activation_paths','ledger_path')}
    need(binding['target_config_sha256']==hashlib.sha256(canonical(target_config)).hexdigest())
    need(binding['operation']=='REMOTE_RUN'
         and binding['request_sha256']==hashlib.sha256(canonical(request)).hexdigest()
         and binding['command_sha256']==hashlib.sha256(remote_command(request).encode()).hexdigest())
    def check(req,digest):
        need(req==policy['request'] and digest==binding['request_sha256'])
        need(protected_json(path)[1]==policy_sha)
        body=fetch_approval(policy['approval_comment_id'])
        split_authorize(policy,binding,body,time.time())
        need(protected_json(path)[1]==policy_sha)
        # Revalidate executed bytes and runtime closure immediately before effects.
        for item in list(policy['target_code'].values())+list(policy['runtime_files'].values()):
            protected_code(item['path'],item['sha256'])
        return True
    check(request,binding['request_sha256'])
    activation,broker=remote_factory(policy)
    folder=Path(policy['ledger_path'])
    need(folder.is_absolute())
    for node in (folder,)+tuple(folder.parents):
        s=node.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not stat.S_ISLNK(s.st_mode)
             and not s.st_mode & 0o022)
    ledger=Ledger(folder)
    try:
        actual=folder.stat();held=os.fstat(ledger.fd)
        need((actual.st_dev,actual.st_ino)==(held.st_dev,held.st_ino))
        return consume_remote_identity(ledger,request,policy['request'],activation,broker,check,time.time)
    finally:ledger.close()


class GitJournal:
    """Transport metadata only on dedicated refs, not a second task registry.

    POST ref is the atomic one-use claim. Force=false plus one-parent commits
    makes concurrent appends reject non-fast-forward, never silently overwrite.
    Admin deletion/history rewriting is outside the trust model; target's
    protected durable intent is a separate barrier. No secret/request body stored.
    """
    def __init__(self,token,attempt,opener=None):
        import urllib.request
        need(receipt.token(attempt) and type(token) is str and bool(token))
        self.token=token;self.ref='heads/p2-transport-journal/'+attempt
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a,**k):return None
        self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def api(self,method,path,value=None,missing=False):
        import urllib.request
        import urllib.error
        need(path.startswith('/git/'))
        req=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+path,
            data=None if value is None else canonical(value),method=method,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                     'Content-Type':'application/json','User-Agent':'P2-Split-Journal'})
        try:
            with self.opener.open(req,timeout=15) as response:raw=response.read(65537)
            need(len(raw)<=65536)
            return json.loads(raw,object_pairs_hook=receipt.unique)
        except urllib.error.HTTPError as e:
            if missing and e.code==404:return None
            raise RuntimeError('JOURNAL_API_UNKNOWN_NO_RETRY') from None
        except Exception:raise RuntimeError('JOURNAL_API_UNKNOWN_NO_RETRY') from None

    def read(self):
        ref=self.api('GET','/git/ref/'+self.ref,missing=True)
        if ref is None:return None
        sha=ref['object']['sha']
        commit=self.api('GET','/git/commits/'+sha)
        tree=self.api('GET','/git/trees/'+commit['tree']['sha'])
        need(len(tree['tree'])==1 and tree['tree'][0]['path']=='state.json'
             and tree['tree'][0]['mode']=='100644' and tree['tree'][0]['type']=='blob')
        blob=self.api('GET','/git/blobs/'+tree['tree'][0]['sha'])
        import base64
        need(blob['encoding']=='base64' and blob['size']<=8192)
        value=json.loads(base64.b64decode(blob['content']),object_pairs_hook=receipt.unique)
        return sha,value

    def write(self,value,prior=None):
        need(len(canonical(value))<=8192)
        tree=self.api('POST','/git/trees',{'tree':[{'path':'state.json','mode':'100644',
             'type':'blob','content':canonical(value).decode()}]})
        commit=self.api('POST','/git/commits',{'message':'P2 transport metadata checkpoint',
             'tree':tree['sha'],'parents':[] if prior is None else [prior]})
        if prior is None:
            self.api('POST','/git/refs',{'ref':'refs/'+self.ref,'sha':commit['sha']})
        else:
            self.api('PATCH','/git/refs/'+self.ref,{'sha':commit['sha'],'force':False})
        saved=self.read()
        need(saved==(commit['sha'],value))
        return commit['sha']


def validate_split_output(detail,invoke,request):
    need(detail.get('InvokeId')==invoke and detail.get('InstanceId')==receipt.INSTANCE
         and detail.get('InvocationStatus')=='Success' and type(detail.get('ExitCode')) is int
         and detail['ExitCode']==0)
    raw=detail.get('Output')
    need(type(raw) is str and len(raw.encode())<=8192)
    data=json.loads(raw,object_pairs_hook=receipt.unique)
    if data=={'state':'REMOTE_EXECUTION_UNKNOWN','redispatch_allowed':False}:
        return {'state':'TARGET_EXECUTION_UNKNOWN','redispatch_allowed':False}
    need(type(data) is dict and set(data)=={'state','request_sha256','receipt','redispatch_allowed'}
         and data['state'] in ('REMOTE_IDENTITY_COMPLETE','REMOTE_RESULT_REPLAY')
         and data['redispatch_allowed'] is False
         and data['request_sha256']==hashlib.sha256(canonical(request)).hexdigest())
    public=receipt.validate({'InvokeId':invoke,'InstanceId':receipt.INSTANCE,
        'InvocationStatus':'Success','ExitCode':0,'Output':json.dumps(data['receipt'])},
        invoke,request['nonce'])
    return {'state':'SPLIT_TRANSPORT_VERIFIED','receipt':public,'redispatch_allowed':False}


def split_cloud(policy,journal,rpc_factory,read_approval,now,action,invoke_id=''):
    """Explicit one-shot RUN or fresh-permit QUERY, backed by durable Git ref."""
    need(action in ('remote-run','cloud-query','a5-preflight','a5-query'))
    request=policy['request'];binding=policy['binding']
    a5=action.startswith('a5-')
    if a5:need(request.get('purpose')=='A5_METADATA_PREFLIGHT_ONLY')
    else:need(request.get('purpose')!='A5_METADATA_PREFLIGHT_ONLY')
    need(type(request['expires_unix']) in (int,float))
    if action in ('remote-run','a5-preflight'):need(now()<request['expires_unix'])
    script=a5_command(request) if a5 else remote_command(request)
    need(binding['host']==receipt.HOST and binding['instance_id']==receipt.INSTANCE
         and binding['region']==receipt.REGION and binding['role']==ROLE
         and type(binding['target_config_sha256']) is str
         and re.fullmatch('[0-9a-f]{64}',binding['target_config_sha256']))
    need(binding['operation']==({'remote-run':'REMOTE_RUN','cloud-query':'CLOUD_QUERY','a5-preflight':'A5_PREFLIGHT','a5-query':'A5_QUERY'}[action])
         and binding['attempt']==request['attempt']
         and binding['request_sha256']==hashlib.sha256(canonical(request)).hexdigest()
         and binding['command_sha256']==hashlib.sha256(script.encode()).hexdigest()
         and binding['invoke_id']==invoke_id)
    def gate():
        return split_authorize(policy,binding,read_approval(policy['approval_comment_id']),now())
    gate()
    saved=journal.read()
    public={'attempt':request['attempt'],'request_sha256':binding['request_sha256'],
            'command_sha256':binding['command_sha256'],'source_commit':binding['source_commit'],
            'target_config_sha256':binding['target_config_sha256']}
    if action in ('remote-run','a5-preflight'):
        need(saved is None and not invoke_id)
        row=dict(public,state='CLOUD_DISPATCH_INTENT',invoke_id='')
        head=journal.write(row)
        # Any later failure permanently consumes RUN, even before STS.
    else:
        need(saved is not None and receipt.token(invoke_id))
        head,row=saved
        need(all(row.get(k)==v for k,v in public.items()) and row.get('invoke_id')==invoke_id
             and row.get('state') in ('CLOUD_DISPATCHED','CLOUD_QUERY_UNKNOWN'))
        ident=policy['approval_comment_id']
        used=row.get('query_permits',[])
        need(type(used) is list and ident not in used and len(used)<32)
        import uuid
        # Distinct trees prevent identical concurrent query commits from both
        # succeeding as an idempotent update of the same Git ref head.
        row=dict(row,query_permits=used+[ident],query_claim_nonce=uuid.uuid4().hex,
                 state='CLOUD_QUERY_UNKNOWN')
        head=journal.write(row,head)
    gate();rpc=rpc_factory();rpc.assume();gate()
    if action in ('remote-run','a5-preflight'):
        try:
            response=rpc(ENDPOINT,'RunCommand',RegionId=receipt.REGION,InstanceId=receipt.INSTANCE,
                CommandContent=script,Type='RunShellScript',WorkingUser='root',WorkingDir='/root',
                Timeout=60,Name='p2-uk-reviewed-split-identity')
            invoke_id=response.get('InvokeId');need(receipt.token(invoke_id))
            row=dict(row,state='CLOUD_DISPATCHED',invoke_id=invoke_id)
            head=journal.write(row,head)
        except BaseException:
            # INTENT may be the last durable state. No missing-ID reconstruction.
            raise RuntimeError('CLOUD_DISPATCH_UNKNOWN_NO_RETRY') from None
        return {'state':'CLOUD_DISPATCHED_AWAIT_SEPARATE_QUERY','invoke_id':invoke_id,
                'redispatch_allowed':False}
    try:
        gate()
        response=rpc(ENDPOINT,'DescribeInvocationResult',RegionId=receipt.REGION,
                     InstanceId=receipt.INSTANCE,InvokeId=invoke_id)
        detail=response.get('InvocationResult',{})
        need(detail.get('InvokeId')==invoke_id and detail.get('InstanceId')==receipt.INSTANCE)
        if detail.get('InvocationStatus') in ('Pending','Running','Stopping'):
            return {'state':'CLOUD_QUERY_UNKNOWN','invoke_id':invoke_id,'redispatch_allowed':False}
        if detail.get('InvocationStatus')!='Success' or detail.get('ExitCode')!=0:
            result={'state':'TARGET_REJECTED_OR_FAILED','redispatch_allowed':False}
        else:result=a5_validate(detail,invoke_id) if a5 else validate_split_output(detail,invoke_id,request)
        gate()
        journal.write(dict(row,state=result['state']),head)
        return result
    except BaseException:
        raise RuntimeError('CLOUD_QUERY_UNKNOWN_QUERY_SAVED_ID_ONLY') from None


def actions_entry(action,attempt,invoke_id=''):
    """Real manual Actions adapter; protected environment registration external."""
    import time
    need(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch'
         and os.environ.get('P2_SPLIT_ENABLED')=='true'
         and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY
         and os.environ.get('GITHUB_RUN_ATTEMPT')=='1'
         and os.environ.get('GITHUB_ACTOR_ID')==str(OWNER_ID))
    raw=os.environ.get('P2_SPLIT_POLICY','')
    need(len(raw.encode())<=32768)
    policy=json.loads(raw,object_pairs_hook=receipt.unique)
    binding=policy['binding']
    need(binding['source_commit']==os.environ.get('GITHUB_SHA')
         and re.fullmatch('[0-9a-f]{40}',binding['source_commit'])
         and policy['request']['attempt']==attempt and receipt.token(attempt)
         and os.environ.get('GITHUB_REF')==policy['workflow_ref'])
    for name,path in (('transport',__file__),('receipt',receipt.__file__)):
        need(hashlib.sha256(Path(path).read_bytes()).hexdigest()==binding['code_sha256'][name])
    workflow=Path('.github/workflows/p2-uk-swas-diagnostic.yml')
    need(hashlib.sha256(workflow.read_bytes()).hexdigest()==binding['workflow_sha256'])
    # Approval and exact source pins checked before reading the cloud key values.
    split_authorize(policy,binding,fetch_approval(policy['approval_comment_id']),time.time())
    journal=GitJournal(os.environ.get('P2_JOURNAL_TOKEN',''),attempt)
    def acquire():
        return AuthenticatedRPC(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),
                                os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''))
    return split_cloud(policy,journal,acquire,fetch_approval,time.time,action,invoke_id)


def protected_json(path):
    """Read pre-enrolled Root policy; never register or modify a trust anchor."""
    path=Path(path)
    need(path.is_absolute())
    for node in (path,)+tuple(path.parents):
        s=node.lstat()
        need(s.st_uid==0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode & 0o022)
        if node != path:need(stat.S_ISDIR(s.st_mode))
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_gid==0 and before.st_nlink==1
             and stat.S_IMODE(before.st_mode)==0o400 and before.st_size<=32768)
        raw=stream.read(32769);after=os.fstat(stream.fileno())
        need((before.st_ino,before.st_mtime_ns,before.st_size)==(after.st_ino,after.st_mtime_ns,after.st_size))
    need(len(raw)<=32768)
    return json.loads(raw,object_pairs_hook=receipt.unique),hashlib.sha256(raw).hexdigest()


def authorize(body, trust, binding, now):
    """Exact independently anchored comment; registration provenance is external.
    No self-reported reviewer role, source declaration or old permit suffices.
    """
    need(type(body) is str and len(body.encode())<=16384)
    need(trust['enabled'] is True and trust['revoked'] is False
         and trust['reviewer_principal'] != trust['source_writer_principal']
         and re.fullmatch('[0-9a-f]{64}',trust['custody_evidence_sha256']) is not None
         and hashlib.sha256(body.encode()).hexdigest()==trust['approval_body_sha256'])
    need(body.startswith('P2_UK_TRANSPORT_ONCE\n'))
    p=json.loads(body.split('\n',1)[1],object_pairs_hook=receipt.unique)
    need(set(p)=={'decision','binding','issued_unix','expires_unix','max_attempts','private_inputs_allowed','install_allowed'})
    need(p['decision']=='UK_TRANSPORT_APPROVED' and p['binding']==binding
         and type(p['max_attempts']) is int and p['max_attempts']==1
         and p['private_inputs_allowed'] is False and p['install_allowed'] is False
         and type(p['issued_unix']) is int and type(p['expires_unix']) is int
         and p['issued_unix']<=now<p['expires_unix']
         and 0<p['expires_unix']-p['issued_unix']<=7200)
    return hashlib.sha256(body.encode()).hexdigest()


def authorized_dispatch(ledger, attempt, nonce, trust_path, get_comment,
                        acquire_rpc, writer_epoch_path, query_only=False):
    """Gated caller candidate; get_comment and acquire_rpc are trusted adapters.
    A pre-existing Root policy supplies the only allowed files/epoch/approval.
    No GitHub trigger, enrollment or global writer transfer is performed here.
    """
    import fcntl
    import time
    fd=os.open('caller.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=ledger.fd)
    try:
        s=os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and s.st_nlink==1
             and stat.S_IMODE(s.st_mode)==0o600)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        trust,trust_sha=protected_json(trust_path)
        epoch,epoch_sha=protected_json(writer_epoch_path)
        folder=Path(trust['ledger_path'])
        for node in (folder,)+tuple(folder.parents):
            meta=node.lstat()
            need(meta.st_uid==0 and stat.S_ISDIR(meta.st_mode) and not stat.S_ISLNK(meta.st_mode) and not meta.st_mode & 0o022)
        actual=os.stat(str(folder));held=os.fstat(ledger.fd)
        need((actual.st_dev,actual.st_ino)==(held.st_dev,held.st_ino))
        need(trust['writer_epoch_sha256']==epoch_sha and epoch['state']=='EXCLUSIVE'
             and epoch['writer']==trust['source_writer_principal'])
        hashes={}
        for name,path in trust['code_paths'].items():
            need(name in ('transport','receipt'))
            node=Path(path)
            for parent in (node,)+tuple(node.parents):
                info=parent.lstat()
                need(info.st_uid==0 and not stat.S_ISLNK(info.st_mode) and not info.st_mode & 0o022)
            need(node.is_file())
            hashes[name]=hashlib.sha256(node.read_bytes()).hexdigest()
        need(set(hashes)=={'transport','receipt'}
             and Path(trust['code_paths']['transport'])==Path(__file__).absolute()
             and Path(trust['code_paths']['receipt'])==Path(receipt.__file__).absolute())
        need(type(query_only) is bool)
        binding={'operation':'QUERY_EXISTING' if query_only else 'RUN_COMMAND',
                 'attempt':attempt,'nonce':nonce,'host':receipt.HOST,
                 'instance_id':receipt.INSTANCE,'region':receipt.REGION,'role':ROLE,
                 'script_sha256':hashlib.sha256(command(nonce).encode()).hexdigest(),
                 'code_sha256':hashes,'writer_epoch_sha256':epoch_sha}
        need(trust['binding']==binding)
        body=get_comment(trust['approval_comment_id'])
        authorize(body,trust,binding,time.time())
        # Recheck policy, global epoch and comment under the same held lock.
        need(protected_json(trust_path)[1]==trust_sha
             and protected_json(writer_epoch_path)[1]==epoch_sha
             and get_comment(trust['approval_comment_id'])==body)
        authorize(body,trust,binding,time.time())
        # Recovery classification runs under the held lock, before credentials.
        checkpoint=recovery_snapshot(ledger)
        need(checkpoint['state']==('QUERY_SAVED_INVOKE_ONLY' if query_only
                                  else 'NO_DISPATCH_RECORD_NO_AUTHORITY'))
        # No credential access before gates; no RunCommand outside durable intent.
        if query_only:
            prior=ledger.read('dispatch-intent.json')
            need(prior['attempt']==attempt and prior['nonce']==nonce)
            need(receipt.token(ledger.read('invoke.json')['invoke_id']))
            ident=trust['approval_comment_id']
            need(type(ident) is int and ident>0)
            ledger.create('query-permit-'+str(ident)+'.json',{'state':'QUERY_PERMIT_CONSUMED'})
        else:
            try:
                ledger.read('dispatch-intent.json')
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('ATTEMPT_ALREADY_CONSUMED')
        rpc=acquire_rpc()
        rpc.assume()
        need(protected_json(trust_path)[1]==trust_sha
             and protected_json(writer_epoch_path)[1]==epoch_sha
             and get_comment(trust['approval_comment_id'])==body)
        authorize(body,trust,binding,time.time())
        if query_only:
            return poll_existing(ledger,rpc)
        return dispatch_once(ledger,attempt,nonce,binding['script_sha256'],rpc)
    except Exception:
        raise RuntimeError('AUTHORIZED_CALLER_HOLD_NO_BLIND_RETRY') from None
    finally:
        os.close(fd)


CONTROL = Path('/etc/xuanjun-p2-swas')
REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
OWNER_LOGIN = 'huhongchuan0422-creator'
OWNER_ID = 332398908


def fetch_approval(ident, opener=None):
    """Public approval GET with fixed origin/repository/PR and author identity.
    Independent authority still comes from the separately protected body hash.
    """
    import urllib.request
    need(type(ident) is int and ident > 0)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    client=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+
                                  '/issues/comments/'+str(ident),
                                  headers={'Accept':'application/vnd.github+json','User-Agent':'P2-UK-Protected-Caller'})
    try:
        with client.open(request,timeout=10) as response:raw=response.read(32769)
        need(len(raw)<=32768)
        data=json.loads(raw,object_pairs_hook=receipt.unique)
        need(data['id']==ident and data['user']['id']==OWNER_ID
             and data['user']['login']==OWNER_LOGIN
             and data['issue_url']=='https://api.github.com/repos/'+REPOSITORY+'/issues/58')
        body=data['body'];need(type(body) is str and len(body.encode())<=16384)
        return body
    except Exception:
        raise RuntimeError('APPROVAL_PROVENANCE_HOLD') from None


def protected_entry(action):
    """Root-installed fixed entry: no arbitrary file, command or host arguments.
    It never creates trust, epoch, credentials or the attempt directory.
    """
    need(os.getuid()==os.geteuid()==0 and action in ('run-once','query-existing'))
    trust_path=CONTROL/'TRUST.json'
    epoch_path=CONTROL/'WRITER_EPOCH.json'
    trust,unused=protected_json(trust_path)
    binding=trust['binding']
    need(binding['operation']==('RUN_COMMAND' if action=='run-once' else 'QUERY_EXISTING'))
    folder=Path(trust['ledger_path'])
    need(folder.is_absolute())
    def acquire():
        values,unused=protected_json(CONTROL/'CREDENTIALS.json')
        need(set(values)=={'AccessKeyId','AccessKeySecret'})
        return AuthenticatedRPC(values['AccessKeyId'],values['AccessKeySecret'])
    ledger=Ledger(folder)
    try:
        return authorized_dispatch(ledger,binding['attempt'],binding['nonce'],
                                   trust_path,fetch_approval,acquire,epoch_path,
                                   query_only=action=='query-existing')
    finally:ledger.close()


def supervise(action, seconds=240, operation=protected_entry):
    """Linux process deadline; interruption never authorizes a resubmission.
    Child emits at most one whitelisted receipt or generic failure. Private
    response bodies, policy and credentials are never printed.
    """
    import signal
    import time
    need(action in ('run-once','query-existing') and type(seconds) is int
         and 1<=seconds<=240)
    pid=os.fork()
    if pid==0:
        try:
            os.setsid()
            result=operation(action)
            print(json.dumps(result,sort_keys=True),flush=True)
            os._exit(0)
        except BaseException:
            print('{"state":"HOLD","redispatch_allowed":false}',flush=True)
            os._exit(2)
    deadline=time.monotonic()+seconds
    try:
        while True:
            done,status=os.waitpid(pid,os.WNOHANG)
            if done:
                return 0 if os.WIFEXITED(status) and os.WEXITSTATUS(status)==0 else 2
            if time.monotonic()>=deadline:
                # Kill the exact child even if it has not completed setsid yet.
                try:os.killpg(pid,signal.SIGKILL)
                except ProcessLookupError:pass
                try:os.kill(pid,signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(pid,0)
                print('{"state":"SUPERVISOR_TIMEOUT_UNKNOWN","redispatch_allowed":false}',flush=True)
                return 2
            time.sleep(0.05)
    except BaseException:
        try:os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        try:os.waitpid(pid,0)
        except ChildProcessError:pass
        raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('run-once','query-existing','receive-identity','remote-run','cloud-query','a5-preflight','a5-query'))
    parser.add_argument('--attempt',default='')
    parser.add_argument('--invoke-id',default='')
    args=parser.parse_args()
    try:
        if args.action=='receive-identity':
            import sys
            raw=sys.stdin.buffer.read(8193)
            need(len(raw)<=8192)
            request=json.loads(raw,object_pairs_hook=receipt.unique)
            raise SystemExit(supervise('run-once',operation=lambda unused:receive_identity(request)))
        elif args.action in ('remote-run','cloud-query','a5-preflight','a5-query'):
            raise SystemExit(supervise('run-once',operation=lambda unused:
                actions_entry(args.action,args.attempt,args.invoke_id)))
        else:raise SystemExit(supervise(args.action))
        print(json.dumps(result,sort_keys=True),flush=True)
    except Exception:
        print('{"state":"HOLD","redispatch_allowed":false}',flush=True)
        raise SystemExit(2) from None
