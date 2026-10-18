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

HOST_PROGRAM='"""Fixed storage implementation inspection, with every business literal removed.\n\nRead source definitions only. No imports from the project, database opens,\nprocess injection, requests, service control or runtime-configuration claims.\n"""\nimport ast\nimport base64\nimport copy\nimport datetime\nimport hashlib\nimport json\nimport os\nimport re\nimport stat\nimport zlib\n\nTARGETS=(\n (\'database/repositories/__init__.py\', ()),\n (\'database/repositories/credential_repository.py\', (\'CredentialRepository\',)),\n (\'accounts/credential_store.py\', (\'CredentialStore\',)),\n (\'ai_service/secure_secrets_portal.py\', (\'OperationsSecretRefStore\',\'FileBackedSubmissionSessionRepository\',\'SecureSecretsPortalService\')),\n (\'ai_service/wecom_customer_service.py\', (\'WeComCustomerServiceIngress\',)),\n (\'ai_service/wecom_customer_contact_service.py\', (\'WeComCustomerContactIngress\',)),\n (\'ai_service/telegram_customer_service_canary.py\', (\'TelegramCustomerServiceCanary\',)),\n (\'database/connection.py\', ()),\n (\'douyin/open_api_foundation.py\', (\'DouyinOAuthStateStore\',\'DouyinTokenLifecycleStore\')),\n (\'tiktok/open_api_foundation.py\', (\'TikTokOAuthStateStore\',\'TikTokTokenLifecycleStore\')),\n (\'scripts/secure_secrets_portal_server.py\', (\'PortalHandler\',)),\n)\nPINS={\n \'ai_service/wecom_customer_service.py\':\'aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402\',\n \'ai_service/wecom_customer_contact_service.py\':\'c95ca9ec711d05d64489ed927cae770157954b46661411b5f762f193ba711571\',\n \'database/connection.py\':\'58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece\',\n \'scripts/secure_secrets_portal_server.py\':\'57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1\',\n}\nSAFE_CONSTANTS=(\'PRIVATE_LITERAL_WITHHELD\',)\n\ndef sha(raw):return hashlib.sha256(raw).hexdigest()\n\nclass RemoveLiterals(ast.NodeTransformer):\n    def generic_visit(self,node):\n        node=super().generic_visit(node)\n        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and not node.body:\n            node.body=[ast.Pass()]\n        return node\n    def visit_Expr(self,node):\n        if isinstance(node.value,ast.Constant):return None\n        return self.generic_visit(node)\n    def visit_Constant(self,node):\n        if node.value is None or type(node.value)is bool:return node\n        if type(node.value)is int and node.value in (0,1,2):return node\n        return ast.copy_location(ast.Constant(\'PRIVATE_LITERAL_WITHHELD\'),node)\n\ndef excerpt(raw,classes):\n    tree=ast.parse(raw)\n    selected=[];definitions=[];found=[]\n    for node in tree.body:\n        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):\n            definitions.append({\'name\':node.name,\'line\':node.lineno,\'kind\':type(node).__name__})\n        if isinstance(node,ast.ClassDef):\n            if node.name not in classes:continue\n            found.append(node.name)\n        elif not isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef,ast.AsyncFunctionDef)):\n            continue\n        selected.append(node)\n    clean=RemoveLiterals().visit(copy.deepcopy(ast.Module(body=selected,type_ignores=[])))\n    code=ast.unparse(ast.fix_missing_locations(clean))\n    # Removing docstrings can empty an otherwise valid class/function body.\n    # Parsing here catches such transformations before any evidence is emitted.\n    ast.parse(code)\n    if len(code.encode())>170000 or len(definitions)>160:raise RuntimeError(\'STORAGE_SOURCE_BOUND\')\n    return {\'definitions\':definitions,\'selected_classes\':found,\n      \'missing_classes\':sorted(set(classes)-set(found)),\'redacted_syntax\':code}\n\ndef read_source(root,path):\n    parent=os.dup(root)\n    try:\n        pieces=path.split(\'/\')\n        for piece in pieces[:-1]:\n            child=os.open(piece,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)\n            os.close(parent);parent=child\n        fd=os.open(pieces[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)\n        try:\n            a=os.fstat(fd)\n            if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_size>1048576:raise RuntimeError(\'SOURCE_TYPE_BOUND\')\n            raw=os.pread(fd,1048577,0);b=os.fstat(fd)\n            c=os.stat(pieces[-1],dir_fd=parent,follow_symlinks=False)\n            fp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)\n            if fp(a)!=fp(b) or fp(b)!=fp(c) or len(raw)!=a.st_size:raise RuntimeError(\'SOURCE_DRIFT\')\n            return raw\n        finally:os.close(fd)\n    finally:os.close(parent)\n\ndef observe(expected,nonce):\n    if os.geteuid()!=0 or os.uname().nodename!=expected or expected!=\'iZ6wee8q9z4t03hvqumwfhZ\':raise RuntimeError(\'FIXED_TOKYO_ROOT\')\n    root=os.open(\'/opt/trading-system\',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)\n    rows=[]\n    try:\n        for path,classes in TARGETS:\n            try:raw=read_source(root,path)\n            except FileNotFoundError:\n                rows.append({\'path\':path,\'source_state\':\'MISSING\',\'sha256\':None,\'definitions\':[],\n                  \'selected_classes\':[],\'missing_classes\':sorted(classes),\'redacted_syntax\':\'\'})\n                continue\n            pin=sha(raw)\n            if path in PINS and pin!=PINS[path]:raise RuntimeError(\'PINNED_SOURCE_DRIFT\')\n            rows.append({\'path\':path,\'source_state\':\'PRESENT\',\'sha256\':pin,**excerpt(raw,classes)})\n    finally:os.close(root)\n    return {\'scope\':\'PR99_STORAGE_IMPLEMENTATIONS_NOT_RUNTIME_ATTESTATION\',\'hostname\':expected,\'nonce\':nonce,\n      \'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\'sources\':rows,\n      \'raw_private_literals_disclosed\':False,\'environment_read\':False,\'database_opened\':False,\n      \'business_imports\':0,\'service_actions\':0,\'effective_runtime_configuration_proven\':False}\n\ndef wire(value):\n    raw=json.dumps(value,sort_keys=True,separators=(\',\',\':\')).encode()\n    if len(raw)>360000:raise RuntimeError(\'STORAGE_SEMANTICS_RAW_BOUND\')\n    value={\'encoding\':\'PR99_STORAGE_SEMANTICS_ZLIB_V1\',\'bytes\':len(raw),\'sha256\':sha(raw),\'payload\':base64.b64encode(zlib.compress(raw,9)).decode()}\n    out=json.dumps(value,separators=(\',\',\':\'))\n    if len(out.encode())>=23000:raise RuntimeError(\'STORAGE_SEMANTICS_WIRE_BOUND\')\n    return out\n\nif __name__==\'__main__\':\n    try:print(wire(observe(EXPECTED,NONCE)),flush=True)\n    except BaseException as error:\n        code=str(error)\n        print(json.dumps({\'status\':\'STORAGE_SEMANTICS_HOLD\',\'exception\':type(error).__name__,\n          \'code\':code if re.fullmatch(\'[A-Z0-9_]{1,100}\',code) else \'PRIVATE_DETAIL_WITHHELD\',\'retry_allowed\':False}),flush=True)\n        raise SystemExit(2)\n'
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
        if not ok:raise ValueError('REPOSITORY_SEMANTICS_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    n={'__name__':'semantics_contract'};exec(compile(HOST_PROGRAM,'fixed_semantics_definitions','exec'),n)
    fields(d,'scope hostname nonce observed_at sources raw_private_literals_disclosed environment_read database_opened business_imports service_actions effective_runtime_configuration_proven')
    need(d['scope']=='PR99_STORAGE_IMPLEMENTATIONS_NOT_RUNTIME_ATTESTATION' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for key in ('raw_private_literals_disclosed','environment_read','database_opened','effective_runtime_configuration_proven'):need(d[key]is False)
    for key in ('business_imports','service_actions'):need(type(d[key])is int and d[key]==0)
    need(type(d['sources'])is list and len(d['sources'])==len(n['TARGETS']))
    for row,(path,classes) in zip(d['sources'],n['TARGETS']):
        fields(row,'path source_state sha256 definitions selected_classes missing_classes redacted_syntax')
        need(row['path']==path and row['source_state']in('PRESENT','MISSING'))
        need(type(row['selected_classes'])is list and type(row['missing_classes'])is list)
        need(len(row['selected_classes'])==len(set(row['selected_classes'])) and
             len(row['missing_classes'])==len(set(row['missing_classes'])) and
             not set(row['selected_classes'])&set(row['missing_classes']) and
             set(row['selected_classes'])|set(row['missing_classes'])==set(classes))
        if row['source_state']=='MISSING':
            need(row['sha256']is None and row['selected_classes']==[] and row['definitions']==[] and row['redacted_syntax']=='')
            continue
        need(type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']))
        if path in n['PINS']:need(row['sha256']==n['PINS'][path])
        need(type(row['definitions'])is list and len(row['definitions'])<=160)
        for f in row['definitions']:
            fields(f,'name line kind')
            need(type(f['name'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,100}',f['name']))
            need(type(f['line'])is int and 0<f['line']<100000 and f['kind']in('ClassDef','FunctionDef','AsyncFunctionDef'))
        code=row['redacted_syntax'];need(type(code)is str and len(code.encode())<=170000)
        tree=ast.parse(code)
        need(set(x.name for x in tree.body if isinstance(x,ast.ClassDef))==set(row['selected_classes']))
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant):
                need((type(node.value)is str and node.value=='PRIVATE_LITERAL_WITHHELD') or node.value is None or type(node.value)is bool or (type(node.value)is int and node.value in (0,1,2)))
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=32768:raise ValueError()
        try:wire=json.loads(output)
        except ValueError:wire=json.loads(base64.b64decode(output,validate=True))
        assert type(wire)is dict and set(wire)=={'encoding','bytes','sha256','payload'}
        assert wire['encoding']=='PR99_STORAGE_SEMANTICS_ZLIB_V1' and type(wire['bytes'])is int and 0<wire['bytes']<=360000
        packed=base64.b64decode(wire['payload'],validate=True);decoder=zlib.decompressobj();raw=decoder.decompress(packed,360001)
        assert decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data
        assert len(raw)==wire['bytes'] and hashlib.sha256(raw).hexdigest()==wire['sha256']
        return validate_observation(json.loads(raw),expected,nonce)
    except Exception:raise Hold('REPOSITORY_SEMANTICS_OUTPUT_REJECTED') from None



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
        claim=Path('pr99-repository-semantics-r2-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-repository-semantics-r2-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_REPOSITORY_SEMANTICS_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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
            row['status']='STORAGE_IMPLEMENTATIONS_OBSERVED_NOT_RUNTIME_ATTESTATION'
            return row
        raise Hold('READONLY_RESULT_UNKNOWN_NO_RETRY')
    except Hold as e:row['error_code']=safe(str(e))
    except Exception:row['error_code']='UNEXPECTED_UNKNOWN_NO_RETRY'
    return row


def self_test():
    import ast
    import tempfile
    n={'__name__':'semantics_fixture'};exec(compile(HOST_PROGRAM,'fixed_semantics_source','exec'),n)
    raw='import missing_business_module\nPRIVATE="DO_NOT_DISCLOSE_TOKEN"\nclass CredentialStore:\n "PRIVATE_DOCSTRING"\n def empty(self):\n  "PRIVATE_DOCSTRING"\n def put(self,value):\n  return f"PRIVATE_TEMPLATE{value}"\ndef helper():\n return b"PRIVATE_BYTES"'
    clean=n['excerpt'](raw,('CredentialStore',))
    for private in ('DO_NOT_DISCLOSE_TOKEN','PRIVATE_DOCSTRING','PRIVATE_TEMPLATE','PRIVATE_BYTES'):
        assert private not in json.dumps(clean)
    assert 'class CredentialStore' in clean['redacted_syntax'] and 'pass' in clean['redacted_syntax']
    assert n['excerpt'](raw,('NotPresent',))['missing_classes']==['NotPresent']
    sources=[]
    for path,classes in n['TARGETS']:
        text='\n'.join('class '+x+':\n pass' for x in classes) or 'import missing_business_module'
        sources.append({'path':path,'source_state':'PRESENT','sha256':n['PINS'].get(path,'b'*64),**n['excerpt'](text,classes)})
    d={'scope':'PR99_STORAGE_IMPLEMENTATIONS_NOT_RUNTIME_ATTESTATION','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-19T00:00:00Z',
       'sources':sources,'raw_private_literals_disclosed':False,'environment_read':False,'database_opened':False,'business_imports':0,'service_actions':0,'effective_runtime_configuration_proven':False}
    assert decode_receipt(n['wire'](d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(n['wire'](d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    changes=(lambda x:x.update(effective_runtime_configuration_proven=True),lambda x:x.update(database_opened=True),
        lambda x:x.update(private='TOKEN'),lambda x:x['sources'][-1].update(sha256='0'*64),
        lambda x:x['sources'][0].update(redacted_syntax='token="PRIVATE_SECRET"'),
        lambda x:x.update(service_actions=True),lambda x:x['sources'][1].update(selected_classes=[]))
    for change in changes:
        bad=json.loads(json.dumps(d));change(bad)
        try:decode_receipt(n['wire'](bad),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('PRIVATE_OR_FALSE_STORAGE_PROOF_ACCEPTED')
    # Real descriptor reads reject links and parent-directory links, without
    # opening a business database or executing any of the inspected imports.
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'sub').mkdir();(root/'sub/a.py').write_text(raw)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            assert n['read_source'](fd,'sub/a.py')==raw.encode()
            (root/'sub/link.py').symlink_to('a.py')
            (root/'linked').symlink_to('sub',target_is_directory=True)
            for path in ('sub/link.py','linked/a.py'):
                try:n['read_source'](fd,path)
                except OSError:pass
                else:raise AssertionError('SOURCE_LINK_ACCEPTED')
        finally:os.close(fd)
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
    assert 'subprocess' not in HOST_PROGRAM and 'systemctl' not in HOST_PROGRAM
    print('PR99_REPOSITORY_SEMANTICS_REDACTION_REQUIRED_CLASSES_SAFE_READS_CONTRACT_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-repository-semantics-r2-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'STORAGE_IMPLEMENTATIONS_BATCH_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_REPOSITORY_SEMANTICS_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='STORAGE_IMPLEMENTATIONS_OBSERVED_NOT_RUNTIME_ATTESTATION' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_REPOSITORY_SEMANTICS_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
