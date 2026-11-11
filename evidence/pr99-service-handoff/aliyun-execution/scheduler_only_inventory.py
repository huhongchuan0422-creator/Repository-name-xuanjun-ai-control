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

HOST_PROGRAM = "import ast\nimport datetime\nimport hashlib\nimport json\nimport os\nimport re\nimport stat\nimport time\nMARKERS = (b'/opt/trading-system', b'xuanjun', b'wecom', b'binance', b'finance')\nSAFE = re.compile('[A-Za-z0-9_./-]{1,240}')\n\ndef sha(raw):\n    return hashlib.sha256(raw).hexdigest()\n\ndef read_at(directory, name, limit):\n    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)\n    try:\n        before = os.fstat(fd)\n        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:\n            raise RuntimeError('SOURCE_TYPE_OR_SIZE')\n        raw = b''\n        while len(raw) <= limit:\n            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not chunk:\n                break\n            raw += chunk\n        after = os.fstat(fd)\n        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)\n        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)\n        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:\n            raise RuntimeError('SOURCE_DRIFT')\n        return raw\n    finally:\n        os.close(fd)\n\ndef scheduler_inventory(deadline):\n    rows = []\n    scanned = 0\n    matched = set()\n    total = 0\n    links = 0\n    roots = ('/etc/systemd/system', '/usr/lib/systemd/system', '/etc/cron.d', '/var/spool/cron')\n    for slot, root in enumerate(roots):\n        try:\n            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)\n        except FileNotFoundError:\n            continue\n        try:\n            for name in sorted(os.listdir(fd)):\n                if time.monotonic() > deadline:\n                    raise RuntimeError('SCHEDULER_DEADLINE')\n                if not re.fullmatch(r'[A-Za-z0-9_.:@\\\\-]{1,240}',name) or '/' in name:\n                    raise RuntimeError('SCHEDULER_NAME_BOUND')\n                s = os.stat(name, dir_fd=fd, follow_symlinks=False)\n                if stat.S_ISLNK(s.st_mode):\n                    links += 1\n                    continue\n                if not stat.S_ISREG(s.st_mode):\n                    continue\n                if slot < 2 and (not name.endswith(('.service', '.timer', '.path', '.socket'))):\n                    continue\n                raw = read_at(fd, name, 131072)\n                scanned += 1\n                total += len(raw)\n                if scanned > 2048 or total > 8388608:\n                    raise RuntimeError('SCHEDULER_TOTAL_BOUND')\n                lower = raw.lower()\n                if not any((m in lower or m in name.lower().encode() for m in MARKERS)):\n                    continue\n                if len(rows) >= 128:\n                    raise RuntimeError('SCHEDULER_MATCH_BOUND')\n                key = (slot, name)\n                matched.add(key)\n                rows.append({'root_slot': slot, 'name': name, 'sha256': sha(raw), 'bytes': len(raw), 'matching_lines': sum((any((m in line.lower() for m in MARKERS)) for line in raw.splitlines()))})\n        finally:\n            os.close(fd)\n    fd = os.open('/etc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)\n    try:\n        try:\n            raw = read_at(fd, 'crontab', 131072)\n        except FileNotFoundError:\n            raw = None\n        if raw is not None:\n            scanned += 1\n            if any((m in raw.lower() for m in MARKERS)):\n                rows.append({'root_slot': 4, 'name': 'crontab', 'sha256': sha(raw), 'bytes': len(raw), 'matching_lines': sum((any((m in line.lower() for m in MARKERS)) for line in raw.splitlines()))})\n    finally:\n        os.close(fd)\n    return {'regular_fragments_read': scanned, 'excluded_symlinks': links, 'candidates': rows}\n\ndef observe(expected,nonce):\n    assert os.geteuid()==0 and os.uname().nodename==expected=='iZ6wee8q9z4t03hvqumwfhZ'\n    return {'hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z',\n        'scope':'PR99_SCHEDULER_DEFINITIONS_ONLY_NOT_AUTHORITY',\n        'schedulers':scheduler_inventory(time.monotonic()+25),\n        'source_inventory':'PREVIOUS_FAILED_RESULT_NOT_RETURNED_NOT_REPLAYED',\n        'business_source_imports':0,'database_opened':False,'service_actions':0,'business_requests':0,\n        'canonical_data_assigned':False,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN',\n        'limitations':['IMMEDIATE_REGULAR_FRAGMENTS_ONLY_NOT_EFFECTIVE_UNIT_CONFIGURATION',\n                       'EXCLUDED_LINKS_DROPINS_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED']}\n\nif __name__=='__main__':\n    print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)\n"
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
def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('SCHEDULER_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    fields(d,'hostname nonce observed_at scope schedulers source_inventory business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations')
    need(d['hostname']==expected and d['nonce']==nonce)
    need(d['scope']=='PR99_SCHEDULER_DEFINITIONS_ONLY_NOT_AUTHORITY')
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    need(d['source_inventory']=='PREVIOUS_FAILED_RESULT_NOT_RETURNED_NOT_REPLAYED')
    for k in ('business_source_imports','service_actions','business_requests'):need(type(d[k])is int and d[k]==0)
    need(d['database_opened']is False and d['canonical_data_assigned']is False)
    need(d['authoritative_writer']==d['enforced_fence']=='UNKNOWN')
    need(d['limitations']==['IMMEDIATE_REGULAR_FRAGMENTS_ONLY_NOT_EFFECTIVE_UNIT_CONFIGURATION',
                           'EXCLUDED_LINKS_DROPINS_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED'])
    s=d['schedulers'];fields(s,'regular_fragments_read excluded_symlinks candidates')
    for k in ('regular_fragments_read','excluded_symlinks'):need(type(s[k])is int and 0<=s[k]<100001)
    need(type(s['candidates'])is list and len(s['candidates'])<=129)
    seen=set()
    for row in s['candidates']:
        fields(row,'root_slot name sha256 bytes matching_lines')
        need(type(row['root_slot'])is int and 0<=row['root_slot']<5)
        need(type(row['name'])is str and re.fullmatch(r'[A-Za-z0-9_.:@\\-]{1,240}',row['name']))
        need(row['name']not in ('.','..') and (row['root_slot'],row['name'])not in seen)
        seen.add((row['root_slot'],row['name']))
        need(type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']))
        for k in ('bytes','matching_lines'):need(type(row[k])is int and 0<=row[k]<=131072)
    return d

def decode_receipt(output, expected, nonce):
    if type(output) is not str or len(output) > 120000:
        raise Hold('WRITER_OUTPUT_BOUND')
    try:
        try: data = json.loads(output)
        except ValueError: data = json.loads(base64.b64decode(output, validate=True))
        return validate_observation(data, expected, nonce)
    except Exception:
        raise Hold('WRITER_OUTPUT_CONTRACT_REJECTED') from None


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
        claim=Path('pr99-scheduler-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-scheduler-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_SCHEDULER_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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
    valid={'hostname': 'test', 'nonce': 'nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn', 'observed_at': '2026-10-18T13:00:00Z', 'scope': 'PR99_SCHEDULER_DEFINITIONS_ONLY_NOT_AUTHORITY', 'schedulers': {'regular_fragments_read': 1, 'excluded_symlinks': 0, 'candidates': [{'root_slot': 0, 'name': 'xuanjun-worker@.service', 'sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'bytes': 10, 'matching_lines': 1}]}, 'source_inventory': 'PREVIOUS_FAILED_RESULT_NOT_RETURNED_NOT_REPLAYED', 'business_source_imports': 0, 'database_opened': False, 'service_actions': 0, 'business_requests': 0, 'canonical_data_assigned': False, 'authoritative_writer': 'UNKNOWN', 'enforced_fence': 'UNKNOWN', 'limitations': ['IMMEDIATE_REGULAR_FRAGMENTS_ONLY_NOT_EFFECTIVE_UNIT_CONFIGURATION', 'EXCLUDED_LINKS_DROPINS_OTHER_NAMESPACES_NOT_COVERED', 'NO_DRAIN_OR_FENCE_PERFORMED']}
    assert decode_receipt(json.dumps(valid),'test','n'*32)==valid
    for name in ('xuanjun-worker@.service','systemd-fsck@dev.service','xuanjun-service.timer'):
        x=json.loads(json.dumps(valid));x['schedulers']['candidates'][0]['name']=name
        assert decode_receipt(json.dumps(x),'test','n'*32)==x
    mutations=(lambda x:x.update(canonical_data_assigned=True),lambda x:x.update(command='SECRET'),
        lambda x:x.update(service_actions=True),lambda x:x['schedulers']['candidates'][0].update(name='../../SECRET'),
        lambda x:x['schedulers']['candidates'][0].update(command='SECRET'),
        lambda x:x['schedulers']['candidates'][0].update(name='SECRET=value'),
        lambda x:x['schedulers']['candidates'][0].update(bytes=True))
    for mutate in mutations:
        x=json.loads(json.dumps(valid));mutate(x)
        try:decode_receipt(json.dumps(x),'test','n'*32)
        except Hold:pass
        else:raise AssertionError('SCHEDULER_SECRET_OR_FALSE_AUTHORITY_ACCEPTED')
    assert 'code_inventory' not in HOST_PROGRAM
    for h in HOSTS:shell_for(h[4],'f'*32)
    print('PR99_SCHEDULER_TEMPLATE_NAMES_AND_SEVEN_REJECTIONS_PASS_NO_CLOUD',flush=True)


def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-scheduler-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'WRITER_METADATA_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_SCHEDULER_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_SCHEDULER_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
