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
if __name__ == '__main__':
    # Isolated Python entry loads only the adjacent protected installed module,
    # never a scripts package from CWD or PYTHONPATH.
    try:
        import importlib.util
        target=Path(__file__).absolute().parent/'p2_swas_receipt_validator.py'
        for node in (target,)+tuple(target.parents):
            meta=node.lstat()
            if meta.st_uid!=0 or stat.S_ISLNK(meta.st_mode) or meta.st_mode & 0o022:
                raise RuntimeError('UNPROTECTED_CODE')
            if node==target and not (stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and meta.st_size<=32768):
                raise RuntimeError('INVALID_CODE_FILE')
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
    parser.add_argument('action',choices=('run-once','query-existing'))
    args=parser.parse_args()
    try:raise SystemExit(supervise(args.action))
    except Exception:
        print('{"state":"HOLD","redispatch_allowed":false}',flush=True)
        raise SystemExit(2) from None
