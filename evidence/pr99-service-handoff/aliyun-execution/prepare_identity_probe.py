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
HOSTS=(('domestic',CN,'cn-shanghai','3a22c458934142eea89ec6e3bf481a57','iZvt5t8tlrm8oiZ'),)


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

HOST_PROGRAM='"""Owner-authorized fixed domestic installation prerequisite, never activation.\n\nOnly possible mutation: native useradd for the absent dedicated xuanjun-s07\nsystem identity. No user modification/removal, service mutation, database or\nenvironment reads, data restore, route change, shell login or cloud credential.\n"""\nimport datetime\nimport grp\nimport json\nimport os\nfrom pathlib import Path\nimport pwd\nimport stat\nimport subprocess\n\nHOST=\'iZvt5t8tlrm8oiZ\'\nACCOUNT=\'xuanjun-s07\'\nCOMMAND=[\'/usr/sbin/useradd\',\'--system\',\'--no-create-home\',\'--home-dir\',\'/nonexistent\',\n         \'--shell\',\'/usr/sbin/nologin\',\'--user-group\',ACCOUNT]\nPROTECTED=(\'provider-neutral-domestic-bridge.service\',\'windows-interaction-http.service\',\'nginx.service\')\nTARGETS=tuple(\'xuanjun-pr99-domestic-\'+r+\'.service\' for r in (\'portal\',\'contact\',\'customer-service\'))\nRELEASES=(\'/opt/xuanjun-migration-s07/releases/domestic-r2\',\n          \'/opt/xuanjun-migration-s07/releases/domestic-r2/rootfs\',\n          \'/opt/xuanjun-migration-s07/releases/domestic-final-v1\',\n          \'/opt/xuanjun-migration-s07/releases/domestic-final-v1/rootfs\')\n\n\ndef need(ok,code):\n    if not ok:raise RuntimeError(code)\n\n\ndef identity(getuser,getgroup,users,groups):\n    try:user=getuser(ACCOUNT)\n    except KeyError:user=None\n    try:group=getgroup(ACCOUNT)\n    except KeyError:group=None\n    if user is group is None:return None\n    need(user is not None and group is not None,\'DEDICATED_NAME_PARTIAL_CONFLICT\')\n    need(user.pw_name==group.gr_name==ACCOUNT and user.pw_uid not in (0,65534,1000,1001) and\n         user.pw_gid==group.gr_gid and group.gr_gid not in (0,65534,1000,1001) and\n         user.pw_shell in (\'/usr/sbin/nologin\',\'/sbin/nologin\') and user.pw_dir==\'/nonexistent\' and not group.gr_mem,\n         \'DEDICATED_IDENTITY_CONFLICT\')\n    need(sum(u.pw_uid==user.pw_uid for u in users())==1 and\n         not any(u.pw_gid==group.gr_gid and u.pw_name!=ACCOUNT for u in users()) and\n         sum(g.gr_gid==group.gr_gid for g in groups())==1 and\n         not any(g.gr_gid!=group.gr_gid and ACCOUNT in g.gr_mem for g in groups()),\'DEDICATED_IDENTITY_ALIAS\')\n    return {\'name\':ACCOUNT,\'uid\':user.pw_uid,\'gid\':group.gr_gid,\'login_shell_disabled\':True,\n            \'home_created\':False,\'shared_primary_identity\':False}\n\n\ndef prepare_identity(getuser=None,getgroup=None,users=None,groups=None,run=None):\n    getuser=getuser or pwd.getpwnam;getgroup=getgroup or grp.getgrnam\n    users=users or pwd.getpwall;groups=groups or grp.getgrall;run=run or subprocess.run\n    before=identity(getuser,getgroup,users,groups)\n    if before is not None:return {\'created\':False,\'creation_attempted\':False,**before}\n    # Exactly one native call. On failure/timeout never retry or delete partial\n    # account/group state. A later action may only query the original outcome.\n    result=run(COMMAND,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,\n               env={\'PATH\':\'/usr/sbin:/usr/bin:/sbin:/bin\',\'LANG\':\'C\'})\n    need(result.returncode==0,\'USERADD_RESULT_UNKNOWN_PRESERVE_NO_RETRY\')\n    after=identity(getuser,getgroup,users,groups)\n    need(after is not None,\'USERADD_IDENTITY_NOT_OBSERVED\')\n    return {\'created\':True,\'creation_attempted\':True,**after}\n\n\ndef unit_states(names):\n    result={}\n    for name in names:\n        args=[\'/usr/bin/systemctl\',\'show\',name,\'--property=LoadState,ActiveState,SubState,MainPID\',\'--no-pager\']\n        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,\n                         env={\'PATH\':\'/usr/sbin:/usr/bin:/sbin:/bin\',\'LANG\':\'C\'})\n        need(len(p.stdout)<=8192,\'UNIT_STATE_BOUND\')\n        values=dict(l.split(\'=\',1) for l in p.stdout.decode(\'utf-8\',\'strict\').splitlines() if \'=\' in l)\n        need(set(values)=={\'LoadState\',\'ActiveState\',\'SubState\',\'MainPID\'} and\n             values[\'MainPID\'].isdigit(),\'UNIT_STATE_UNKNOWN\')\n        result[name]={**{k:values[k] for k in (\'LoadState\',\'ActiveState\',\'SubState\')},\'MainPID\':int(values[\'MainPID\'])}\n    return result\n\n\ndef metadata(path):\n    p=Path(path)\n    try:s=p.lstat()\n    except FileNotFoundError:return {\'path\':path,\'exists\':False}\n    need(not stat.S_ISLNK(s.st_mode),\'RELEASE_LINK_NOT_ADOPTED\')\n    return {\'path\':path,\'exists\':True,\'directory\':stat.S_ISDIR(s.st_mode),\'uid\':s.st_uid,\n            \'gid\':s.st_gid,\'mode\':stat.S_IMODE(s.st_mode),\'device\':s.st_dev,\'inode\':s.st_ino}\n\n\ndef prepare(expected,nonce):\n    need(os.geteuid()==0 and os.uname().nodename==expected==HOST,\'FIXED_DOMESTIC_ROOT\')\n    for path in (\'/usr/sbin/useradd\',\'/usr/sbin/nologin\'):\n        s=Path(path).stat()\n        need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and s.st_mode&0o111,\'FIXED_NATIVE_TOOL_IDENTITY\')\n    before=unit_states(PROTECTED)\n    releases=[metadata(p) for p in RELEASES]\n    target_states=unit_states(TARGETS)\n    account=prepare_identity()\n    after=unit_states(PROTECTED)\n    return {\'scope\':\'PR99_OWNER_DOMESTIC_IDENTITY_PREPARATION_ONLY\',\'hostname\':HOST,\'nonce\':nonce,\n            \'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\'identity\':account,\n            \'protected_before\':before,\'protected_after\':after,\'protected_state_unchanged\':before==after,\n            \'target_units\':target_states,\'releases\':releases,\'service_actions\':0,\'database_opened\':False,\n            \'route_changed\':False,\'migration_started\':False,\'production_started\':False}\n\n\nif __name__==\'__main__\':\n    try:print(json.dumps(prepare(EXPECTED,NONCE),sort_keys=True),flush=True)\n    except BaseException as error:\n        code=str(error)\n        import re\n        print(json.dumps({\'status\':\'PREPARATION_HOLD\',\'error_type\':type(error).__name__,\n          \'code\':code if re.fullmatch(\'[A-Z0-9_]{1,160}\',code) else \'PRIVATE_DETAIL_WITHHELD\',\n          \'retry_allowed\':False}),flush=True)\n        raise SystemExit(2)\n'
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
        if not ok:raise ValueError('IDENTITY_PREPARATION_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    fields(d,'scope hostname nonce observed_at identity protected_before protected_after protected_state_unchanged target_units releases service_actions database_opened route_changed migration_started production_started')
    need(d['scope']=='PR99_OWNER_DOMESTIC_IDENTITY_PREPARATION_ONLY' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    a=d['identity'];fields(a,'created creation_attempted name uid gid login_shell_disabled home_created shared_primary_identity')
    need(a['name']=='xuanjun-s07' and type(a['created']) is type(a['creation_attempted']) is bool and a['created']==a['creation_attempted'])
    for k in ('uid','gid'):need(type(a[k])is int and 0<a[k]<65534 and a[k]not in (1000,1001))
    need(a['login_shell_disabled']is True and a['home_created']is False and a['shared_primary_identity']is False)
    protected={'provider-neutral-domestic-bridge.service','windows-interaction-http.service','nginx.service'}
    targets={'xuanjun-pr99-domestic-'+r+'.service' for r in ('portal','contact','customer-service')}
    for key,names in (('protected_before',protected),('protected_after',protected),('target_units',targets)):
        need(type(d[key])is dict and set(d[key])==names)
        for row in d[key].values():
            fields(row,'LoadState ActiveState SubState MainPID')
            need(all(type(row[k])is str and re.fullmatch('[A-Za-z0-9_-]{1,80}',row[k]) for k in ('LoadState','ActiveState','SubState')))
            need(type(row['MainPID'])is int and 0<=row['MainPID']<2**31)
    need(type(d['protected_state_unchanged'])is bool and d['protected_state_unchanged']==(d['protected_before']==d['protected_after']))
    paths=['/opt/xuanjun-migration-s07/releases/domestic-r2','/opt/xuanjun-migration-s07/releases/domestic-r2/rootfs','/opt/xuanjun-migration-s07/releases/domestic-final-v1','/opt/xuanjun-migration-s07/releases/domestic-final-v1/rootfs']
    need(type(d['releases'])is list and len(d['releases'])==4)
    for row,path in zip(d['releases'],paths):
        need(type(row)is dict and row.get('path')==path and type(row.get('exists'))is bool)
        fields(row,'path exists directory uid gid mode device inode' if row['exists'] else 'path exists')
        if row['exists']:
            need(type(row['directory'])is bool)
            need(all(type(row[k])is int and 0<=row[k]<2**64 for k in ('uid','gid','mode','device','inode')))
    need(type(d['service_actions'])is int and d['service_actions']==0)
    for k in ('database_opened','route_changed','migration_started','production_started'):need(d[k]is False)
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
        claim=Path('pr99-prepare-identity-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'DEDICATED_ACCOUNT_PREPARATION_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-prepare-identity-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_IDENTITY_PREP_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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
                raise Hold('IDENTITY_PREPARATION_FAILED_NO_RETRY')
            row['receipt']=decode_receipt(detail.get('Output'),expected,nonce)
            if row['receipt']['protected_state_unchanged'] is not True:raise Hold('PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')
            row['host_commands']=1
            row['status']='DOMESTIC_IDENTITY_PREPARED_NOT_PRODUCTION_STARTED'
            return row
        raise Hold('IDENTITY_PREPARATION_RESULT_UNKNOWN_NO_RETRY')
    except Hold as e:row['error_code']=safe(str(e))
    except Exception:row['error_code']='UNEXPECTED_UNKNOWN_NO_RETRY'
    return row


def self_test():
    from types import SimpleNamespace as NS
    n={'__name__':'identity_fixture'};exec(compile(HOST_PROGRAM,'fixed_identity_program','exec'),n)
    state={};calls=[]
    u=NS(pw_name='xuanjun-s07',pw_uid=987,pw_gid=986,pw_shell='/usr/sbin/nologin',pw_dir='/nonexistent')
    g=NS(gr_name='xuanjun-s07',gr_gid=986,gr_mem=[])
    def getuser(name):
        if not state.get('user'):raise KeyError()
        return u
    def getgroup(name):
        if not state.get('group'):raise KeyError()
        return g
    def run(args,**kwargs):calls.append(args);state.update(user=True,group=True);return NS(returncode=0)
    def call(r=run):return n['prepare_identity'](getuser,getgroup,lambda:[u] if state.get('user') else [],lambda:[g] if state.get('group') else [],r)
    a=call();assert a['created']is True and calls==[n['COMMAND']]
    assert call()['created']is False and len(calls)==1
    for key in ('user','group'):
        state.clear();state[key]=True
        try:call()
        except RuntimeError:pass
        else:raise AssertionError('PARTIAL_ACCOUNT_ADOPTED')
    state.update(user=True,group=True);u.pw_uid=0
    try:call()
    except RuntimeError:pass
    else:raise AssertionError('ROOT_IDENTITY_ADOPTED')
    u.pw_uid=987;u.pw_shell='/bin/bash'
    try:call()
    except RuntimeError:pass
    else:raise AssertionError('LOGIN_ACCOUNT_ADOPTED')
    u.pw_shell='/usr/sbin/nologin';state.clear()
    def fail(args,**kwargs):calls.append(args);return NS(returncode=1)
    try:call(fail)
    except RuntimeError:pass
    else:raise AssertionError('NATIVE_FAILURE_ACCEPTED')
    assert len(calls)==2
    unit={'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','MainPID':0}
    protected={k:unit for k in n['PROTECTED']};targets={k:unit for k in n['TARGETS']}
    d={'scope':'PR99_OWNER_DOMESTIC_IDENTITY_PREPARATION_ONLY','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-19T00:00:00Z',
      'identity':a,'protected_before':protected,'protected_after':protected,'protected_state_unchanged':True,
      'target_units':targets,'releases':[{'path':p,'exists':False} for p in n['RELEASES']],
      'service_actions':0,'database_opened':False,'route_changed':False,'migration_started':False,'production_started':False}
    assert decode_receipt(json.dumps(d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(json.dumps(d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    for change in (lambda x:x.update(production_started=True),lambda x:x.update(private='TOKEN'),lambda x:x['identity'].update(uid=0),lambda x:x.update(service_actions=1)):
        bad=json.loads(json.dumps(d));change(bad)
        try:decode_receipt(json.dumps(bad),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('OVERSCOPE_OR_PRIVATE_OUTPUT_ACCEPTED')
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
    assert n['COMMAND']==['/usr/sbin/useradd','--system','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin','--user-group','xuanjun-s07']
    print('PR99_OWNER_IDENTITY_NATIVE_ONCE_CONFLICT_PRIVACY_NO_ACTIVATION_TESTS_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-prepare-identity-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'OWNER_IDENTITY_PREPARATION_BATCH_NOT_PRODUCTION_START','hosts':rows,
        'production_service_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_IDENTITY_PREP_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='DOMESTIC_IDENTITY_PREPARED_NOT_PRODUCTION_STARTED' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_IDENTITY_PREP_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
