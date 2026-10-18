"""Two-host PR99 writer-descriptor observation. No command input or automatic dispatch retry."""
import base64
import concurrent.futures
import datetime
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

UK = 'acs:ram::1107191612880779:role/xuanjun-ai-esc'
KR = 'acs:ram::1691189778575891:role/xuanjun-automation'
CN = 'acs:ram::1384884686754410:role/xuanjun-automation'
HOSTS=(('tokyo',CN,'ap-northeast-1','68985c531add4e90a131aef703a389e6','iZ6wee8q9z4t03hvqumwfhZ'),)


class Hold(Exception):
    pass


def safe(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}', value) else 'DETAIL_WITHHELD'


def quote(value):
    return urllib.parse.quote(str(value), safe='~')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def rpc(endpoint, version, action, credentials, **params):
    # Endpoint and action are fixed by this program, never accepted from a task.
    if endpoint not in {'sts.aliyuncs.com'} | {'swas.' + h[2] + '.aliyuncs.com' for h in HOSTS}:
        raise Hold('ENDPOINT_REJECTED')
    key, secret, token = credentials
    values = dict(params, Action=action, Version=version, Format='JSON',
                  AccessKeyId=key, SignatureMethod='HMAC-SHA1', SignatureVersion='1.0',
                  SignatureNonce=uuid.uuid4().hex,
                  Timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    if token:
        values['SecurityToken'] = token
    canonical = '&'.join(quote(k) + '=' + quote(v) for k, v in sorted(values.items()))
    signature = hmac.new((secret + '&').encode(), ('POST&%2F&' + quote(canonical)).encode(), hashlib.sha1).digest()
    values['Signature'] = base64.b64encode(signature).decode()
    request = urllib.request.Request('https://' + endpoint + '/',
        data=urllib.parse.urlencode(values).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(262145)
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read(262145))
            code = safe(data.get('Code'))
        except Exception:
            code = 'HTTP_' + str(error.code)
        raise Hold(code) from None
    except Exception:
        # Never print a URL/body, key, temporary token, or raw exception.
        raise Hold('TRANSPORT_RESULT_UNKNOWN') from None
    if len(raw) > 262144:
        raise Hold('RESPONSE_TOO_LARGE')
    try:
        data = json.loads(raw)
    except Exception:
        raise Hold('INVALID_API_RESPONSE') from None
    if not isinstance(data, dict):
        raise Hold('INVALID_API_RESPONSE')
    if 'Code' in data:
        raise Hold(safe(data['Code']))
    return data


# This recovery does not import, publish or run the M99-R1 repair candidate.
# Only this exact new read-only scope is authorized. Historical attempts are never replayed.
import zlib

HOST_PROGRAM='"""Bounded real kernel immutable/recovery capability, never a production fence."""\nfrom array import array\nimport datetime\nimport errno\nimport fcntl\nimport hashlib\nimport json\nimport os\nfrom pathlib import Path\nimport shutil\nimport stat\nimport struct\nimport tempfile\n\nHOST=\'iZ6wee8q9z4t03hvqumwfhZ\'\nIMMUTABLE=0x10\nGETFLAGS=(2<<30)|(struct.calcsize(\'l\')<<16)|(ord(\'f\')<<8)|1\nSETFLAGS=(1<<30)|(struct.calcsize(\'l\')<<16)|(ord(\'f\')<<8)|2\nPAYLOAD=b\'PR99 inert kernel fence capability fixture v1\\n\'\n\ndef need(ok,code):\n    if not ok:raise RuntimeError(code)\n\ndef get_flags(fd):\n    value=array(\'l\',[0]);fcntl.ioctl(fd,GETFLAGS,value,True);return value[0]\n\ndef set_flags(fd,value):\n    fcntl.ioctl(fd,SETFLAGS,array(\'l\',[value]),False)\n    need(get_flags(fd)==value,\'FLAG_RESULT_UNKNOWN\')\n\ndef identity(fd):\n    s=os.fstat(fd);return s.st_dev,s.st_ino,s.st_uid\n\ndef rejected(call):\n    try:call()\n    except OSError as error:\n        need(error.errno==errno.EPERM,\'EXPECTED_KERNEL_EPERM\');return True\n    raise RuntimeError(\'KERNEL_WRITE_NOT_BLOCKED\')\n\ndef capability(directory,filesystem_device,read_flags=get_flags,write_flags=set_flags):\n    directory=Path(directory);ds=directory.lstat()\n    need(stat.S_ISDIR(ds.st_mode) and ds.st_uid==os.geteuid() and stat.S_IMODE(ds.st_mode)==0o700 and ds.st_dev==filesystem_device,\'PRIVATE_SAME_FILESYSTEM_REQUIRED\')\n    dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)\n    fd=None;file_flags=directory_flags=None;restored=False\n    try:\n        fd=os.open(\'held-write.fixture\',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=dfd)\n        need(os.write(fd,PAYLOAD)==len(PAYLOAD),\'FIXTURE_WRITE\');os.fsync(fd)\n        original=identity(fd);directory_identity=identity(dfd)\n        file_flags=read_flags(fd);directory_flags=read_flags(dfd)\n        need(not(file_flags|directory_flags)&IMMUTABLE,\'NEW_FIXTURE_ALREADY_IMMUTABLE\')\n        write_flags(fd,file_flags|IMMUTABLE)\n        held_write_blocked=rejected(lambda:os.pwrite(fd,b\'X\',0))\n        unlink_blocked=rejected(lambda:os.unlink(\'held-write.fixture\',dir_fd=dfd))\n        need(os.pread(fd,len(PAYLOAD)+1,0)==PAYLOAD,\'FROZEN_FIXTURE_DRIFT\')\n        write_flags(dfd,directory_flags|IMMUTABLE)\n        def create_child():\n            child=os.open(\'unexpected-child.fixture\',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=dfd)\n            os.close(child)\n        create_blocked=rejected(create_child)\n        need(identity(fd)==original and identity(dfd)==directory_identity,\'FIXTURE_IDENTITY_DRIFT\')\n        write_flags(dfd,directory_flags);write_flags(fd,file_flags)\n        need(os.pwrite(fd,PAYLOAD[:1],0)==1,\'RESTORED_WRITE_FAILED\');os.fsync(fd)\n        need(os.pread(fd,len(PAYLOAD)+1,0)==PAYLOAD,\'RESTORED_BYTES_DRIFT\')\n        restored=True\n        return {\'held_writable_fd_write_blocked\':held_write_blocked,\'file_unlink_blocked\':unlink_blocked,\n          \'directory_create_blocked\':create_blocked,\'original_flags_restored\':True,\'write_after_restore_pass\':True,\n          \'same_filesystem_as_project_root\':True,\'fixture_bytes\':len(PAYLOAD),\'filesystem_device\':filesystem_device}\n    finally:\n        # Compensation only for these exact owned test descriptors; never touch\n        # application flags or paths. Failed restoration retains the fixture.\n        if not restored:\n            if directory_flags is not None:write_flags(dfd,directory_flags)\n            if fd is not None and file_flags is not None:write_flags(fd,file_flags)\n        if fd is not None:os.close(fd)\n        os.close(dfd)\n\ndef observe(expected,nonce):\n    need(os.geteuid()==0 and os.uname().nodename==expected==HOST,\'FIXED_TOKYO_ROOT\')\n    device=os.stat(\'/opt/trading-system\').st_dev\n    need(os.stat(\'/var/lib\').st_dev==device,\'TEST_FILESYSTEM_DIFFERENT_NO_MUTATION\')\n    directory=Path(tempfile.mkdtemp(prefix=\'pr99-native-fence-capability-\',dir=\'/var/lib\'))\n    completed=False\n    try:\n        result=capability(directory,device)\n        need(set(os.listdir(directory))=={\'held-write.fixture\'},\'FIXTURE_CLEANUP_MEMBERSHIP\')\n        s=directory.lstat();need(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,\'FIXTURE_CLEANUP_IDENTITY\')\n        (directory/\'held-write.fixture\').unlink();directory.rmdir();completed=True\n        return {\'scope\':\'PR99_NATIVE_FENCE_CAPABILITY_ONLY_NOT_SOURCE_FENCED\',\'hostname\':expected,\'nonce\':nonce,\n          \'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\'result\':result,\'fixture_cleaned\':True,\n          \'source_data_selected\':False,\'source_writer_stopped\':False,\'production_fence_enforced\':False,\n          \'database_opened\':False,\'service_actions\':0,\'writer_acquired\':False,\'route_changed\':False}\n    finally:\n        # No recursive deletion or retry on failure. Only success cleans exact fixtures.\n        if not completed:pass\n\nif __name__==\'__main__\':\n    try:print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)\n    except BaseException as error:\n        code=str(error)\n        import re\n        print(json.dumps({\'status\':\'NATIVE_FENCE_CAPABILITY_HOLD\',\'exception\':type(error).__name__,\n          \'code\':code if re.fullmatch(\'[A-Z0-9_]{1,160}\',code) else \'PRIVATE_DETAIL_WITHHELD\',\n          \'errno\':getattr(error,\'errno\',None),\'retry_allowed\':False}),flush=True)\n        raise SystemExit(2)\n'
ACTIVE = ('Pending','Running','Stopping')
TERMINAL = frozenset(('Invalid','Aborted','Success','Failed','Error','Timeout','Cancelled','Terminated'))
ID = re.compile(r'[A-Za-z0-9_-]{1,180}')
ALLOWED_ACTIONS = {'AssumeRole','DescribeCommandInvocations','RunCommand','DescribeInvocationResult'}
original_rpc = rpc


def bounded_rpc(endpoint, version, action, credentials, **params):
    if action not in ALLOWED_ACTIONS:
        raise Hold('RPC_ACTION_REJECTED')
    return original_rpc(endpoint, version, action, credentials, **params)


def project_invocations(data, instance, status):
    if type(data) is not dict or type(data.get('TotalCount')) is not int or data['TotalCount'] < 0:
        raise Hold('INVOCATION_LIST_SCHEMA')
    entries = data.get('CommandInvocations')
    if type(entries) is not list or len(entries) > 50:
        raise Hold('INVOCATION_LIST_SCHEMA')
    projected=[]
    for item in entries:
        if type(item) is not dict or type(item.get('InvokeId')) is not str or not ID.fullmatch(item['InvokeId']):
            raise Hold('INVOCATION_ID_REJECTED')
        peers=item.get('InvokeInstances')
        if type(peers) is not list:
            raise Hold('INVOCATION_PEERS_SCHEMA')
        selected=[p for p in peers if type(p) is dict and p.get('InstanceId') == instance]
        if len(selected)!=1:
            raise Hold('INVOCATION_TARGET_NOT_PROVEN')
        actual=selected[0].get('InvocationStatus')
        if actual not in ACTIVE and actual not in TERMINAL:
            raise Hold('INVOCATION_STATUS_UNKNOWN')
        # Never retain CommandContent, Output, ErrorInfo, Parameters or any other raw fields.
        projected.append({'invoke_id':item['InvokeId'],'status':actual})
    return data['TotalCount'],projected


def active_invocations(host, credentials, call=bounded_rpc):
    name,role,region,instance,expected=host
    endpoint='swas.'+region+'.aliyuncs.com'
    rows=[]
    for status in ACTIVE:
        expected_total=None
        for page in range(1,6):
            response=call(endpoint,'2020-06-01','DescribeCommandInvocations',credentials,
                RegionId=region,InstanceId=instance,InvocationStatus=status,
                PageNumber=page,PageSize=50)
            total,items=project_invocations(response,instance,status)
            if expected_total is not None and total!=expected_total:
                raise Hold('INVOCATION_LIST_CHANGED_RECHECK_REQUIRED')
            expected_total=total
            rows.extend(items)
            if page*50>=total:break
            if not items:raise Hold('INVOCATION_PAGINATION_INCOMPLETE')
        else:
            raise Hold('INVOCATION_PAGINATION_BOUND_HOLD')
    # This is an observed API list, not a fence or exclusive Writer assignment.
    return sorted({r['invoke_id']:r for r in rows}.values(),key=lambda x:x['invoke_id'])


def shell_for(expected,nonce):
    program='EXPECTED='+repr(expected)+'\nNONCE='+repr(nonce)+'\n'+HOST_PROGRAM
    payload=base64.b64encode(zlib.compress(program.encode(),9)).decode()
    digest=hashlib.sha256(program.encode()).hexdigest()
    bootstrap="import base64,zlib,hashlib; b=zlib.decompress(base64.b64decode("+repr(payload)+")); assert hashlib.sha256(b).hexdigest()=="+repr(digest)+"; exec(compile(b,'<pr99-readonly-recovery>','exec'))"
    shell="#!/bin/sh\nset -eu\n/usr/bin/python3.11 -I -B - <<'PR99_READONLY'\n"+bootstrap+"\nPR99_READONLY\n"
    if len(shell.encode())>11000:raise Hold('COMMAND_LENGTH')
    return shell


"""Strict public metadata boundary for the fixed observer, not an admission."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('NATIVE_FENCE_CAPABILITY_CONTRACT')
    need(type(d)is dict and set(d)==set('scope hostname nonce observed_at result fixture_cleaned source_data_selected source_writer_stopped production_fence_enforced database_opened service_actions writer_acquired route_changed'.split()))
    need(d['scope']=='PR99_NATIVE_FENCE_CAPABILITY_ONLY_NOT_SOURCE_FENCED' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    x=d['result'];need(type(x)is dict and set(x)==set('held_writable_fd_write_blocked file_unlink_blocked directory_create_blocked original_flags_restored write_after_restore_pass same_filesystem_as_project_root fixture_bytes filesystem_device'.split()))
    for key in set(x)-{'fixture_bytes','filesystem_device'}:need(x[key]is True)
    need(type(x['filesystem_device'])is int and 0<x['filesystem_device']<2**64 and x['fixture_bytes']==46)
    need(d['fixture_cleaned']is True and type(d['service_actions'])is int and d['service_actions']==0)
    for key in ('source_data_selected','source_writer_stopped','production_fence_enforced','database_opened','writer_acquired','route_changed'):need(d[key]is False)
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=16000:raise ValueError()
        try:d=json.loads(output)
        except ValueError:d=json.loads(base64.b64decode(output,validate=True))
        return validate_observation(d,expected,nonce)
    except Exception:raise Hold('IDENTITY_PREPARATION_OUTPUT_REJECTED') from None



def probe_current(host,master):
    name,role,region,instance,expected=host
    row={'host':name,'instance_id':instance,'status':'HOLD','host_commands':0,'run_command_attempted':False,'service_actions':0,
         'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN'}
    try:
        c=bounded_rpc('sts.aliyuncs.com','2015-04-01','AssumeRole',master,
            RoleArn=role,RoleSessionName='pr99-resume-'+uuid.uuid4().hex[:16],DurationSeconds=900)['Credentials']
        credentials=(c['AccessKeyId'],c['AccessKeySecret'],c['SecurityToken'])
        if not all(type(v) is str and v and '\r' not in v and '\n' not in v for v in credentials):
            raise Hold('CREDENTIAL_RESPONSE_INVALID')
        for value in credentials:print('::add-mask::'+value,flush=True)
        row['sts']='PASS_CURRENT'
        row['nonterminal_invocations']=active_invocations(host,credentials)
        row['cloud_query']='PASS_CURRENT_OBSERVATION_NOT_FENCE'
        if any(x['status'] in ACTIVE for x in row['nonterminal_invocations']):
            raise Hold('EXISTING_INFLIGHT_PRESERVED_NO_NEW_HOST_COMMAND')
        nonce=uuid.uuid4().hex
        shell=shell_for(expected,nonce)
        # Local job claim stops repeat dispatch in this process; no production state is created.
        # A lost InvokeId remains UNKNOWN. Workflow reruns are rejected before credentials.
        claim=Path('pr99-native-fence-capability-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'NATIVE_FENCE_CAPABILITY_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-native-fence-capability-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_NATIVE_FENCE_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            response=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','DescribeInvocationResult',credentials,
                RegionId=region,InstanceId=instance,InvokeId=invoke)
            detail=response.get('InvocationResult')
            if type(detail) is not dict or detail.get('InstanceId')!=instance or detail.get('InvokeId')!=invoke:
                raise Hold('RESULT_IDENTITY_UNKNOWN_NO_RETRY')
            state=detail.get('InvocationStatus')
            if state in ACTIVE:time.sleep(5);continue
            row['invocation_status']=safe(state)
            if state!='Success' or detail.get('ExitCode')!=0:
                output=detail.get('Output','')
                try:
                    try:failure=json.loads(output)
                    except ValueError:failure=json.loads(base64.b64decode(output,validate=True))
                    if type(failure)is dict and set(failure)=={'status','exception','code','errno','retry_allowed'}:
                        row['host_error_type']=safe(failure['exception']);row['host_error_code']=safe(failure['code'])
                        if type(failure['errno'])is int:row['host_errno']=failure['errno']
                except Exception:pass
                row['exit_code']=detail.get('ExitCode')
                raise Hold('NATIVE_FENCE_CAPABILITY_FAILED_NO_RETRY')
            row['receipt']=decode_receipt(detail.get('Output'),expected,nonce)
            if row['receipt']['fixture_cleaned'] is not True:raise Hold('FIXTURE_NOT_CLEANED')
            row['host_commands']=1
            row['status']='KERNEL_CAPABILITY_VERIFIED_NOT_PRODUCTION_FENCE'
            return row
        raise Hold('IDENTITY_PREPARATION_RESULT_UNKNOWN_NO_RETRY')
    except Hold as e:row['error_code']=safe(str(e))
    except Exception:row['error_code']='UNEXPECTED_UNKNOWN_NO_RETRY'
    return row


def self_test():
    n={'__name__':'capability_definitions'};exec(compile(HOST_PROGRAM,'capability','exec'),n)
    assert len(n['PAYLOAD'])==46
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
    d={'scope':'PR99_NATIVE_FENCE_CAPABILITY_ONLY_NOT_SOURCE_FENCED','hostname':HOSTS[0][4],'nonce':'a'*32,
       'observed_at':'2026-10-19T00:00:00Z','result':{k:True for k in ('held_writable_fd_write_blocked','file_unlink_blocked','directory_create_blocked','original_flags_restored','write_after_restore_pass','same_filesystem_as_project_root')},
       'fixture_cleaned':True,'source_data_selected':False,'source_writer_stopped':False,'production_fence_enforced':False,
       'database_opened':False,'service_actions':0,'writer_acquired':False,'route_changed':False}
    d['result'].update(fixture_bytes=46,filesystem_device=64771)
    assert decode_receipt(json.dumps(d),HOSTS[0][4],'a'*32)==d
    for key in ('source_writer_stopped','production_fence_enforced','writer_acquired'):
        x=json.loads(json.dumps(d));x[key]=True
        try:decode_receipt(json.dumps(x),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('FALSE_PRODUCTION_EVIDENCE_ACCEPTED')
    for key in ('held_writable_fd_write_blocked','original_flags_restored'):
        x=json.loads(json.dumps(d));x['result'][key]=False
        try:decode_receipt(json.dumps(x),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('FAILED_CAPABILITY_ACCEPTED')
    print('PR99_NATIVE_FENCE_CAPABILITY_SCOPE_AND_SCHEMA_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-native-fence-capability-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'NATIVE_FENCE_CAPABILITY_NOT_PRODUCTION_FENCE','hosts':rows,
        'production_service_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_NATIVE_FENCE_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='KERNEL_CAPABILITY_VERIFIED_NOT_PRODUCTION_FENCE' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_NATIVE_FENCE_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
