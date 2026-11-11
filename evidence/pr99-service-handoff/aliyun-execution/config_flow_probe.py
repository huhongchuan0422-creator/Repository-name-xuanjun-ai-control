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

HOST_PROGRAM='"""Read four exact source files to resolve the missing startup loader/order.\n\nOutput is redacted syntax, never executable business imports, raw literals,\nenvironment values, database bytes or an in-memory/effective-config attestation.\n"""\nimport ast\nimport base64\nimport copy\nimport datetime\nimport hashlib\nimport json\nimport os\nimport re\nimport stat\nimport zlib\n\nPINS=(\n (\'scripts/secure_secrets_portal_server.py\',\'57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1\'),\n (\'ai_service/wecom_customer_contact_service.py\',\'c95ca9ec711d05d64489ed927cae770157954b46661411b5f762f193ba711571\'),\n (\'ai_service/wecom_customer_service.py\',\'aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402\'),\n (\'database/connection.py\',\'58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece\'))\nLITERALS=frozenset((\'__main__\',\'__name__\',\'PRIVATE_LITERAL_WITHHELD\',\'TRADING_DATABASE_URL\',\n \'DATABASE_URL\',\'credential-store.env\',\'utf-8\',\'utf8\',\'=\', \'#\',\'\',\':\',\'\\n\',\n \'--host\',\'--port\',\'--runtime-dir\',\'--env-file\',\'--database-url\',\'--db-url\',\'--config\',\'--credential-env-file\',\n \'/opt/trading-system/runtime/secure-secrets-portal\',\n \'/opt/trading-system/runtime/v8-domestic-operations\',\n \'/opt/trading-system/runtime/v8-domestic-operations/operations-secretref-store\',\n \'/opt/trading-system/runtime/v8-domestic-operations/wecom-customer-service\',\n \'/opt/trading-system/runtime/v8-domestic-operations/wecom-customer-contact\',\n \'serve\',\'store_true\',\'dest\',\'default\',\'required\',\'type\'))\n\n\ndef sha(raw):return hashlib.sha256(raw).hexdigest()\n\n\nclass Redact(ast.NodeTransformer):\n    def visit_Constant(self,node):\n        if type(node.value)is str and node.value in LITERALS:return node\n        if node.value is None or type(node.value)is bool:return node\n        if type(node.value)is int and node.value in (0,1,2):return node\n        return ast.copy_location(ast.Constant(\'PRIVATE_LITERAL_WITHHELD\'),node)\n\n\ndef excerpt(raw):\n    tree=ast.parse(raw)\n    selected=[];functions=[]\n    for node in tree.body:\n        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):\n            functions.append({\'name\':node.name,\'line\':node.lineno})\n            if re.search(r\'main$|^serve$|env|config|^build_|^create_|^parser\',node.name,re.I):\n                selected.append(node)\n        elif isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign)):\n            selected.append(node)\n    clean=Redact().visit(copy.deepcopy(ast.Module(body=selected,type_ignores=[])))\n    code=ast.unparse(ast.fix_missing_locations(clean))\n    if len(code.encode())>55000 or len(functions)>120:raise RuntimeError(\'CONFIG_FLOW_BOUND\')\n    return {\'functions\':functions,\'redacted_syntax\':code}\n\n\ndef read_source(root,path):\n    parts=path.split(\'/\');parent=os.dup(root)\n    try:\n        for name in parts[:-1]:\n            nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)\n            os.close(parent);parent=nxt\n        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)\n        try:\n            before=os.fstat(fd)\n            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>1048576:raise RuntimeError(\'SOURCE_TYPE_BOUND\')\n            raw=os.pread(fd,1048577,0);after=os.fstat(fd);linked=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)\n            fingerprint=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)\n            if fingerprint(before)!=fingerprint(after) or fingerprint(after)!=fingerprint(linked) or len(raw)!=before.st_size:raise RuntimeError(\'SOURCE_DRIFT\')\n            return raw\n        finally:os.close(fd)\n    finally:os.close(parent)\n\n\ndef observe(expected,nonce):\n    if os.geteuid()!=0 or os.uname().nodename!=expected or expected!=\'iZ6wee8q9z4t03hvqumwfhZ\':raise RuntimeError(\'FIXED_TOKYO_ROOT\')\n    root=os.open(\'/opt/trading-system\',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)\n    rows=[]\n    try:\n        for path,pin in PINS:\n            raw=read_source(root,path)\n            if sha(raw)!=pin:raise RuntimeError(\'PINNED_CONFIG_SOURCE_CHANGED\')\n            rows.append({\'path\':path,\'sha256\':pin,**excerpt(raw)})\n    finally:os.close(root)\n    return {\'scope\':\'PR99_REDACTED_STARTUP_CONFIGURATION_FLOW_NOT_RUNTIME_ATTESTATION\',\n      \'hostname\':expected,\'nonce\':nonce,\'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\'sources\':rows,\n      \'raw_private_literals_disclosed\':False,\'environment_read\':False,\'database_opened\':False,\n      \'business_imports\':0,\'service_actions\':0,\'effective_runtime_configuration_proven\':False}\n\n\ndef wire(value):\n    raw=json.dumps(value,sort_keys=True,separators=(\',\',\':\')).encode()\n    if len(raw)>180000:raise RuntimeError(\'CONFIG_FLOW_OUTPUT_BOUND\')\n    result={\'encoding\':\'PR99_CONFIG_FLOW_ZLIB_V1\',\'bytes\':len(raw),\'sha256\':sha(raw),\n            \'payload\':base64.b64encode(zlib.compress(raw,9)).decode()}\n    out=json.dumps(result,separators=(\',\',\':\'))\n    if len(out.encode())>=23000:raise RuntimeError(\'CONFIG_FLOW_WIRE_BOUND\')\n    return out\n\n\nif __name__==\'__main__\':print(wire(observe(EXPECTED,NONCE)),flush=True)\n'
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
    import ast
    def need(ok):
        if not ok:raise ValueError('CONFIG_FLOW_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    context={'__name__':'config_syntax_contract'};exec(compile(HOST_PROGRAM,'fixed_config_definitions','exec'),context)
    fields(d,'scope hostname nonce observed_at sources raw_private_literals_disclosed environment_read database_opened business_imports service_actions effective_runtime_configuration_proven')
    need(d['scope']=='PR99_REDACTED_STARTUP_CONFIGURATION_FLOW_NOT_RUNTIME_ATTESTATION' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for key in ('raw_private_literals_disclosed','environment_read','database_opened','effective_runtime_configuration_proven'):need(d[key]is False)
    for key in ('business_imports','service_actions'):need(type(d[key])is int and d[key]==0)
    need(type(d['sources'])is list and len(d['sources'])==4)
    for row,(path,pin) in zip(d['sources'],context['PINS']):
        fields(row,'path sha256 functions redacted_syntax');need(row['path']==path and row['sha256']==pin)
        need(type(row['functions'])is list and len(row['functions'])<=120)
        for f in row['functions']:
            fields(f,'name line');need(type(f['name'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,100}',f['name']))
            need(type(f['line'])is int and 0<f['line']<100000)
        code=row['redacted_syntax'];need(type(code)is str and len(code.encode())<=55000)
        tree=ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant):
                need((type(node.value)is str and node.value in context['LITERALS']) or node.value is None or type(node.value)is bool or (type(node.value)is int and node.value in (0,1,2)))
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=32768:raise ValueError()
        try:wire=json.loads(output)
        except ValueError:wire=json.loads(base64.b64decode(output,validate=True))
        assert type(wire)is dict and set(wire)=={'encoding','bytes','sha256','payload'}
        assert wire['encoding']=='PR99_CONFIG_FLOW_ZLIB_V1' and type(wire['bytes'])is int and 0<wire['bytes']<=180000
        packed=base64.b64decode(wire['payload'],validate=True);decoder=zlib.decompressobj();raw=decoder.decompress(packed,180001)
        assert decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data
        assert len(raw)==wire['bytes'] and hashlib.sha256(raw).hexdigest()==wire['sha256']
        return validate_observation(json.loads(raw),expected,nonce)
    except Exception:raise Hold('CONFIG_FLOW_OUTPUT_REJECTED') from None


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
        claim=Path('pr99-config-flow-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-config-flow-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_CONFIG_FLOW_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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
                raise Hold('READONLY_COMMAND_FAILED_NO_RETRY')
            row['receipt']=decode_receipt(detail.get('Output'),expected,nonce)
            row['host_commands']=1
            row['status']='CONFIG_FLOW_OBSERVED_NOT_EFFECTIVE_ATTESTATION'
            return row
        raise Hold('READONLY_RESULT_UNKNOWN_NO_RETRY')
    except Hold as e:row['error_code']=safe(str(e))
    except Exception:row['error_code']='UNEXPECTED_UNKNOWN_NO_RETRY'
    return row


def self_test():
    n={'__name__':'config_fixture'};exec(compile(HOST_PROGRAM,'fixed_config_source','exec'),n)
    raw='import missing_business_module\nPRIVATE="DO_NOT_DISCLOSE_TOKEN"\ndef load_env(path):\n token="DO_NOT_DISCLOSE_TOKEN"\n return os.environ.get("TRADING_DATABASE_URL")\ndef irrelevant():\n return "PRIVATE_OTHER"'
    clean=n['excerpt'](raw)
    assert 'DO_NOT_DISCLOSE_TOKEN' not in json.dumps(clean) and 'PRIVATE_OTHER' not in json.dumps(clean)
    assert 'TRADING_DATABASE_URL' in clean['redacted_syntax'] and 'return os.environ' in clean['redacted_syntax']
    assert len(clean['functions'])==2 and 'def irrelevant' not in clean['redacted_syntax']
    d={'scope':'PR99_REDACTED_STARTUP_CONFIGURATION_FLOW_NOT_RUNTIME_ATTESTATION','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-18T15:40:00Z',
       'sources':[{'path':p,'sha256':h,**clean} for p,h in n['PINS']],'raw_private_literals_disclosed':False,'environment_read':False,'database_opened':False,'business_imports':0,'service_actions':0,'effective_runtime_configuration_proven':False}
    assert decode_receipt(n['wire'](d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(n['wire'](d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    changes=(lambda x:x.update(effective_runtime_configuration_proven=True),lambda x:x.update(environment_read=True),
        lambda x:x.update(private='TOKEN'),lambda x:x['sources'][0].update(sha256='0'*64),
        lambda x:x['sources'][0].update(redacted_syntax='token="PRIVATE_SECRET"'),
        lambda x:x.update(service_actions=True),lambda x:x['sources'][0]['functions'][0].update(name='X=PRIVATE'),
        lambda x:x['sources'][0].update(redacted_syntax='X=123456789'))
    for change in changes:
        v=json.loads(json.dumps(d));change(v)
        try:decode_receipt(n['wire'](v),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('PRIVATE_OR_FALSE_CONFIG_PROOF_ACCEPTED')
    for raw in ('X=b"SECRET"','X=987654321','X="secret"','X=f"PRIVATE_SECRET{variable}"'):
        assert 'SECRET' not in n['excerpt'](raw)['redacted_syntax']
    shell=shell_for(HOSTS[0][4],'a'*32)
    assert 'systemctl' not in HOST_PROGRAM and 'sqlite3' not in HOST_PROGRAM and 'subprocess' not in HOST_PROGRAM
    print('PR99_CONFIG_FLOW_8_REJECTIONS_REDACTION_WIRE_AND_ONE_SHOT_BOUNDARIES_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-config-flow-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'CONFIG_FLOW_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_CONFIG_FLOW_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='CONFIG_FLOW_OBSERVED_NOT_EFFECTIVE_ATTESTATION' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_CONFIG_FLOW_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
