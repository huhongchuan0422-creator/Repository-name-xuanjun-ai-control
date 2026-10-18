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
HOSTS = (('tokyo', CN, 'ap-northeast-1', '68985c531add4e90a131aef703a389e6', 'iZ6wee8q9z4t03hvqumwfhZ'),)


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

HOST_PROGRAM = 'import ast\nimport datetime\nimport hashlib\nimport json\nimport os\nimport re\nimport stat\nimport time\nROOT = \'/opt/trading-system\'\nSKIP = frozenset((\'.git\', \'.venv\', \'venv\', \'__pycache__\', \'node_modules\', \'runtime\', \'tests\', \'test\', \'docs\', \'evidence\', \'backup\', \'backups\'))\nSAFE = re.compile(\'[A-Za-z0-9_./-]{1,240}\')\nENV = re.compile(\'[A-Z][A-Z0-9_]{1,100}\')\nKINDS = (\'DB_FACTORY\', \'FILE_WRITE\', \'MUTATION_CALL\')\n\ndef sha(raw):\n    return hashlib.sha256(raw).hexdigest()\n\ndef read_at(directory, name, limit):\n    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)\n    try:\n        before = os.fstat(fd)\n        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:\n            raise RuntimeError(\'SOURCE_TYPE_OR_SIZE\')\n        raw = b\'\'\n        while len(raw) <= limit:\n            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not chunk:\n                break\n            raw += chunk\n        after = os.fstat(fd)\n        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)\n        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)\n        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:\n            raise RuntimeError(\'SOURCE_DRIFT\')\n        return raw\n    finally:\n        os.close(fd)\n\ndef analyze(raw):\n    """Only fixed categories, counts and environment variable NAMES leave AST."""\n    tree = ast.parse(raw)\n    counts = {name: 0 for name in KINDS}\n    env = set()\n    for node in ast.walk(tree):\n        if not isinstance(node, ast.Call):\n            continue\n        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else \'\'\n        if name in (\'connect\', \'create_engine\', \'sessionmaker\'):\n            counts[\'DB_FACTORY\'] += 1\n        elif name in (\'write_text\', \'write_bytes\', \'dump\', \'dumps\', \'mkdir\', \'makedirs\', \'replace\', \'rename\', \'unlink\'):\n            if name != \'dumps\':\n                counts[\'FILE_WRITE\'] += 1\n        elif name in (\'commit\', \'add\', \'add_all\', \'delete\', \'execute\', \'executemany\'):\n            counts[\'MUTATION_CALL\'] += 1\n        if name in (\'getenv\', \'get\') and node.args and isinstance(node.args[0], ast.Constant):\n            value = node.args[0].value\n            if type(value) is str and ENV.fullmatch(value):\n                env.add(value)\n        if name == \'open\':\n            modes = [node.args[1]] if len(node.args) > 1 else []\n            modes += [x.value for x in node.keywords if x.arg == \'mode\']\n            if any((isinstance(x, ast.Constant) and type(x.value) is str and any((c in x.value for c in \'wax+\')) for x in modes)):\n                counts[\'FILE_WRITE\'] += 1\n    return (counts, sorted(env))\n\ndef code_inventory(deadline):\n    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)\n    try:\n        root_identity = os.fstat(fd)\n        manifest = []\n        rows = []\n        errors = []\n        total = 0\n        excluded_links = 0\n        for relative, dirs, files, directory in os.fwalk(\'.\', topdown=True, follow_symlinks=False, dir_fd=fd):\n            if time.monotonic() > deadline:\n                raise RuntimeError(\'SOURCE_DEADLINE\')\n            keep = []\n            for name in sorted(dirs):\n                if name in SKIP or name.startswith(\'.\'):\n                    continue\n                s = os.stat(name, dir_fd=directory, follow_symlinks=False)\n                if stat.S_ISLNK(s.st_mode):\n                    excluded_links += 1\n                elif stat.S_ISDIR(s.st_mode):\n                    keep.append(name)\n            dirs[:] = keep\n            for name in sorted(files):\n                if not name.endswith(\'.py\') or name.startswith(\'test_\'):\n                    continue\n                path = (relative + \'/\' + name).removeprefix(\'./\')\n                if not SAFE.fullmatch(path):\n                    raise RuntimeError(\'SOURCE_NAME_BOUND\')\n                s = os.stat(name, dir_fd=directory, follow_symlinks=False)\n                if stat.S_ISLNK(s.st_mode):\n                    excluded_links += 1\n                    continue\n                raw = read_at(directory, name, 1048576)\n                total += len(raw)\n                if total > 67108864 or len(manifest) >= 2048:\n                    raise RuntimeError(\'SOURCE_TOTAL_BOUND\')\n                manifest.append([path, sha(raw)])\n                try:\n                    counts, env = analyze(raw)\n                except (SyntaxError, UnicodeError):\n                    if len(errors) >= 32:\n                        raise RuntimeError(\'SOURCE_PARSE_BOUND\')\n                    errors.append(path)\n                    continue\n                if any(counts.values()):\n                    rows.append({\'path\': path, \'sha256\': sha(raw), \'calls\': counts, \'environment_keys\': env[:12], \'environment_keys_total\': len(env)})\n        named = os.stat(ROOT, follow_symlinks=False)\n        if (named.st_dev, named.st_ino) != (root_identity.st_dev, root_identity.st_ino):\n            raise RuntimeError(\'SOURCE_ROOT_DRIFT\')\n        required = {\'scripts/secure_secrets_portal_server.py\', \'ai_service/wecom_customer_contact_service.py\', \'ai_service/wecom_customer_service.py\'}\n        if not required <= {item[0] for item in manifest}:\n            raise RuntimeError(\'SOURCE_ROLE_ENTRIES_MISSING\')\n        rows.sort(key=lambda row: (-row[\'calls\'][\'DB_FACTORY\'], -row[\'calls\'][\'MUTATION_CALL\'], row[\'path\']))\n        return {\'files\': len(manifest), \'bytes\': total, \'manifest_sha256\': sha(json.dumps(sorted(manifest), separators=(\',\', \':\')).encode()), \'candidate_files_total\': len(rows), \'omitted_candidate_files\': max(0, len(rows) - 128), \'candidates\': rows[:128], \'parse_errors\': errors, \'excluded_links\': excluded_links}\n    finally:\n        os.close(fd)\n\ndef observe(expected,nonce):\n    assert os.geteuid()==0 and os.uname().nodename==expected==\'iZ6wee8q9z4t03hvqumwfhZ\'\n    return {\'hostname\':expected,\'nonce\':nonce,\'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\n        \'scope\':\'PR99_SOURCE_ONLY_STATIC_CANDIDATES_NOT_AUTHORITY\',\n        \'source\':code_inventory(time.monotonic()+35),\n        \'scheduler_evidence\':\'INHERIT_T_JPN70EXLHV86XA8_NO_RESCAN\',\n        \'business_source_imports\':0,\'database_opened\':False,\'service_actions\':0,\'business_requests\':0,\n        \'canonical_data_assigned\':False,\'authoritative_writer\':\'UNKNOWN\',\'enforced_fence\':\'UNKNOWN\',\n        \'limitations\':[\'STATIC_CANDIDATES_NOT_PROVEN_WRITERS\',\'DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED\',\n                       \'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED\',\'NO_DRAIN_OR_FENCE_PERFORMED\']}\n\nif __name__==\'__main__\':\n    import base64,zlib\n    raw=json.dumps(observe(EXPECTED,NONCE),sort_keys=True,separators=(\',\',\':\')).encode()\n    assert len(raw)<=110000\n    wire={\'encoding\':\'PR99_ZLIB_BASE64_V1\',\'bytes\':len(raw),\'sha256\':sha(raw),\'payload\':base64.b64encode(zlib.compress(raw,9)).decode()}\n    assert len(wire[\'payload\'])<22000,\'SOURCE_RECEIPT_PAYLOAD_BOUND\'\n    text=json.dumps(wire,separators=(\',\',\':\'))\n    assert len(text.encode())<23000,\'SOURCE_RECEIPT_WIRE_BOUND\'\n    print(text,flush=True)\n'
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
    if len(shell.encode())>6000:raise Hold('COMMAND_LENGTH')
    return shell


"""Strict public metadata boundary for the fixed observer, not an admission."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
def validate_original_shape(d, expected, nonce):
    import re
    def need(ok):
        if not ok: raise ValueError('DATA_INVENTORY_CONTRACT')
    def fields(x, keys):need(type(x) is dict and set(x)==set(keys.split()))
    def integer(x, maximum=2**64):need(type(x) is int and 0<=x<maximum)
    def digest(x):need(type(x) is str and re.fullmatch('[0-9a-f]{64}',x))
    def filename(x):need(type(x) is str and re.fullmatch('[A-Za-z0-9_./-]{1,240}',x) and '..' not in x.split('/'))
    fields(d,'hostname nonce observed_at scope source schedulers business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations')
    need(d['hostname']==expected and d['nonce']==nonce)
    need(d['scope']=='PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY')
    need(type(d['observed_at']) is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for name in ('business_source_imports','service_actions','business_requests'):
        need(type(d[name]) is int and d[name]==0)
    need(d['database_opened'] is False and d['canonical_data_assigned'] is False)
    need(d['authoritative_writer']==d['enforced_fence']=='UNKNOWN')
    need(d['limitations']==['STATIC_CANDIDATES_NOT_PROVEN_WRITERS','DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED',
         'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED'])
    s=d['source'];fields(s,'files bytes manifest_sha256 candidate_files_total omitted_candidate_files candidates parse_errors excluded_links')
    integer(s['files'],2049);integer(s['bytes'],67108865);digest(s['manifest_sha256'])
    for key in ('candidate_files_total','omitted_candidate_files','excluded_links'):integer(s[key],4097)
    need(s['candidate_files_total']<=s['files'] and s['omitted_candidate_files']==max(0,s['candidate_files_total']-128))
    need(type(s['candidates']) is list and len(s['candidates'])==min(128,s['candidate_files_total']))
    seen=set()
    for row in s['candidates']:
        fields(row,'path sha256 calls environment_keys environment_keys_total')
        filename(row['path']);need(row['path'].endswith('.py') and row['path'] not in seen);seen.add(row['path'])
        digest(row['sha256']);fields(row['calls'],'DB_FACTORY FILE_WRITE MUTATION_CALL')
        for count in row['calls'].values():integer(count,100001)
        need(sum(row['calls'].values())>0)
        integer(row['environment_keys_total'],100001)
        need(type(row['environment_keys']) is list and len(row['environment_keys'])==min(12,row['environment_keys_total']))
        need(row['environment_keys']==sorted(set(row['environment_keys'])))
        for key in row['environment_keys']:need(type(key) is str and re.fullmatch('[A-Z][A-Z0-9_]{1,100}',key))
    need(type(s['parse_errors']) is list and len(s['parse_errors'])<=32)
    for path in s['parse_errors']:filename(path)
    r=d['schedulers'];fields(r,'regular_fragments_read excluded_symlinks candidates')
    integer(r['regular_fragments_read'],2050);integer(r['excluded_symlinks'],100001)
    need(type(r['candidates']) is list and len(r['candidates'])<=129)
    seen=set()
    for row in r['candidates']:
        fields(row,'root_slot name sha256 bytes matching_lines')
        integer(row['root_slot'],5);filename(row['name']);need('/' not in row['name'])
        need((row['root_slot'],row['name']) not in seen);seen.add((row['root_slot'],row['name']))
        digest(row['sha256']);integer(row['bytes'],131073);integer(row['matching_lines'],131073)
    return d

def validate_observation(d,expected,nonce):
    assert type(d)is dict and set(d)==set('hostname nonce observed_at scope source scheduler_evidence business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations'.split())
    assert d['scope']=='PR99_SOURCE_COMPACT_STATIC_CANDIDATES_NOT_AUTHORITY'
    assert d['scheduler_evidence']=='INHERIT_T_JPN70EXLHV86XA8_NO_RESCAN'
    x=dict(d);del x['scheduler_evidence']
    x['scope']='PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY'
    x['schedulers']={'regular_fragments_read':0,'excluded_symlinks':0,'candidates':[]}
    validate_original_shape(x,expected,nonce)
    return d

def decode_receipt(output,expected,nonce):
    if type(output)is not str or len(output.encode())>=32768:raise Hold('SOURCE_WIRE_BOUND')
    try:
        try:envelope=output.encode();env=json.loads(envelope)
        except ValueError:
            envelope=base64.b64decode(output,validate=True);env=json.loads(envelope)
        assert len(envelope)<23000
        assert type(env)is dict and set(env)=={'encoding','bytes','sha256','payload'}
        assert env['encoding']=='PR99_ZLIB_BASE64_V1'
        assert type(env['bytes'])is int and 0<env['bytes']<=110000
        assert type(env['sha256'])is str and re.fullmatch('[0-9a-f]{64}',env['sha256'])
        assert type(env['payload'])is str and len(env['payload'])<22000
        packed=base64.b64decode(env['payload'],validate=True)
        decoder=zlib.decompressobj()
        raw=decoder.decompress(packed,110001)
        assert decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data
        assert len(raw)==env['bytes'] and hashlib.sha256(raw).hexdigest()==env['sha256']
        return validate_observation(json.loads(raw),expected,nonce)
    except Exception:raise Hold('SOURCE_COMPACT_CONTRACT_REJECTED') from None


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
        claim=Path('pr99-source-compact-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-source-compact-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_SOURCE_COMPACT_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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
            row['status']='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN'
            return row
        raise Hold('READONLY_RESULT_UNKNOWN_NO_RETRY')
    except Hold as e:row['error_code']=safe(str(e))
    except Exception:row['error_code']='UNEXPECTED_UNKNOWN_NO_RETRY'
    return row


def self_test():
    def wire(value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
        return json.dumps({'encoding':'PR99_ZLIB_BASE64_V1','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':base64.b64encode(zlib.compress(raw,9)).decode()})
    valid={'hostname': 'test', 'nonce': 'nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn', 'observed_at': '2026-10-18T12:00:00Z', 'scope': 'PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY', 'source': {'files': 3, 'bytes': 10, 'manifest_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'candidate_files_total': 1, 'omitted_candidate_files': 0, 'candidates': [{'path': 'database/session.py', 'sha256': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'calls': {'DB_FACTORY': 1, 'FILE_WRITE': 0, 'MUTATION_CALL': 0}, 'environment_keys': ['DATABASE_URL'], 'environment_keys_total': 1}], 'parse_errors': [], 'excluded_links': 0}, 'schedulers': {'regular_fragments_read': 5, 'excluded_symlinks': 2, 'candidates': [{'root_slot': 0, 'name': 'xuanjun-example.service', 'sha256': 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'bytes': 30, 'matching_lines': 1}]}, 'business_source_imports': 0, 'database_opened': False, 'service_actions': 0, 'business_requests': 0, 'canonical_data_assigned': False, 'authoritative_writer': 'UNKNOWN', 'enforced_fence': 'UNKNOWN', 'limitations': ['STATIC_CANDIDATES_NOT_PROVEN_WRITERS', 'DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED', 'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED', 'NO_DRAIN_OR_FENCE_PERFORMED']}
    valid.pop('schedulers');valid['scope']='PR99_SOURCE_COMPACT_STATIC_CANDIDATES_NOT_AUTHORITY'
    valid['scheduler_evidence']='INHERIT_T_JPN70EXLHV86XA8_NO_RESCAN'
    assert decode_receipt(wire(valid),'test','n'*32)==valid
    assert decode_receipt(base64.b64encode(wire(valid).encode()).decode(),'test','n'*32)==valid
    mutations=(
        lambda x:x.update(enforced_fence='PASS'),
        lambda x:x.update(canonical_data_assigned=True),
        lambda x:x.update(private='SECRET'),
        lambda x:x.update(service_actions=True),
        lambda x:x['source'].update(bytes=True),
        lambda x:x['source'].update(omitted_candidate_files=99),
        lambda x:x['source']['candidates'][0].update(source_text='SECRET'),
        lambda x:x['source']['candidates'][0].update(path='../SECRET.py'),
        lambda x:x['source']['candidates'][0].update(environment_keys=['SECRET=value']),
        lambda x:x['source']['candidates'][0]['calls'].update(DB_FACTORY=True),
        lambda x:x.update(schedulers={'command':'SECRET'}),
        lambda x:x.update(scheduler_evidence='FALSE_RECEIPT'),
        lambda x:x.update(database_opened=True),
    )
    for mutate in mutations:
        bad=json.loads(json.dumps(valid));mutate(bad)
        try:decode_receipt(wire(bad),'test','n'*32)
        except Hold:pass
        else:raise AssertionError('INVALID_DATA_INVENTORY_ACCEPTED')
    n={'__name__':'source_ast_only'};exec(compile(HOST_PROGRAM,'fixed-source-data','exec'),n)
    raw=b"import os\nSECRET='DO_NOT_DISCLOSE'\ne=create_engine(os.getenv('DATABASE_URL','PRIVATE_DEFAULT'))\np.write_text('PRIVATE_DATA')\ns.commit()\nopen('PRIVATE_PATH','ab')\n"
    counts,keys=n['analyze'](raw)
    assert counts=={'DB_FACTORY':1,'FILE_WRITE':2,'MUTATION_CALL':1} and keys==['DATABASE_URL']
    assert 'PRIVATE' not in json.dumps([counts,keys]) and 'DO_NOT_DISCLOSE' not in json.dumps([counts,keys])
    assert n['analyze'](b"raise RuntimeError('MUST_NOT_EXECUTE')")[0]==dict.fromkeys(n['KINDS'],0)
    for h in HOSTS:shell_for(h[4],'f'*32)
    assert len(HOSTS)==1 and HOSTS[0][0]=='tokyo'
    print('PR99_SOURCE_COMPACT_13_REJECTIONS_AND_AST_REDACTION_PASS_NO_CLOUD',flush=True)
    for change in (lambda x:x.update(bytes=True),lambda x:x.update(bytes=1),lambda x:x.update(sha256='0'*64),
                   lambda x:x.update(payload=x['payload']+'A'),lambda x:x.update(private='SECRET')):
        bad=json.loads(wire(valid));change(bad)
        try:decode_receipt(json.dumps(bad),'test','n'*32)
        except Hold:pass
        else:raise AssertionError('BAD_COMPRESSED_ENVELOPE_ACCEPTED')
    # All payloads that could exceed SWAS output capacity HOLD before acceptance.
    try:decode_receipt('x'*24576,'test','n'*32)
    except Hold:pass
    else:raise AssertionError('OVERSIZE_WIRE_ACCEPTED')
    print('PR99_SOURCE_COMPACT_SIX_ENVELOPE_REJECTIONS_PASS_NO_CLOUD',flush=True)


def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-source-compact-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'WRITER_METADATA_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_SOURCE_COMPACT_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_SOURCE_COMPACT_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
