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
HOSTS = (('domestic', CN, 'cn-shanghai', '3a22c458934142eea89ec6e3bf481a57', 'iZvt5t8tlrm8oiZ'), ('tokyo', CN, 'ap-northeast-1', '68985c531add4e90a131aef703a389e6', 'iZ6wee8q9z4t03hvqumwfhZ'))


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

HOST_PROGRAM = '"""Fixed PR99 process/descriptor observation. Metadata only, never a fence.\n\nOnly imported by the exact embedded read-only entry; no standalone dispatch.\nAll /proc reads are bounded. Runtime file contents and environment are not read.\n"""\nimport datetime\nimport hashlib\nimport json\nimport os\nimport stat\nimport subprocess\nimport time\nfrom pathlib import Path\n\nROOTS = (\n    (\'portal\', \'/opt/trading-system/runtime/secure-secrets-portal\'),\n    (\'operations\', \'/opt/trading-system/runtime/v8-domestic-operations\'),\n    (\'database\', \'/opt/trading-system/database/data\'),\n    (\'workspace\', \'/home/admin/.openclaw/workspace/xuanjun-agent-coordination\'),\n    (\'external_operations\', \'/home/openclaw_ops/v8-domestic-operations\'),\n)\nTAGS = (\n    \'scripts/secure_secrets_portal_server.py\',\n    \'ai_service.wecom_customer_contact_service\',\n    \'ai_service.wecom_customer_service\',\n    \'ai_service.internal_provider_neutral_bridge\',\n    \'production_start.py\', \'production_transport.py\',\n)\nUNITS = (\'secure-secrets-portal.service\',\n         \'xuanjun-wecom-customer-contact.service\',\n         \'xuanjun-wecom-customer-service.service\',\n         \'xuanjun-pr99-domestic-portal.service\',\n         \'xuanjun-pr99-domestic-contact.service\',\n         \'xuanjun-pr99-domestic-customer-service.service\')\n\n\ndef bounded(path, limit):\n    with Path(path).open(\'rb\') as stream:\n        raw = stream.read(limit + 1)\n    if len(raw) > limit:\n        raise RuntimeError(\'PROC_BOUND\')\n    return raw\n\n\ndef identity(path):\n    # The comm field can contain spaces or \')\'; all following fields are numeric.\n    raw = bounded(path / \'stat\', 4096)\n    values = raw[raw.rfind(b\')\') + 2:].split()\n    return int(values[1]), int(values[19])  # ppid, starttime, not pid alone\n\n\ndef classify(target, roots):\n    deleted = target.endswith(\' (deleted)\')\n    target = target[:-10] if deleted else target\n    labels = sorted({label for label, name in roots\n                     if target == name or target.startswith(name + \'/\')})\n    return labels, deleted\n\n\ndef writable_flags(raw):\n    flags = [line.partition(b\':\')[2].strip() for line in raw.splitlines()\n             if line.startswith(b\'flags:\')]\n    if len(flags) != 1:\n        raise RuntimeError(\'FD_FLAGS_UNKNOWN\')\n    return int(flags[0], 8) & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR)\n\n\ndef scan(roots, deadline, proc=Path(\'/proc\')):\n    counts = {\'processes\': 0, \'fds\': 0, \'vanished\': 0, \'unreadable\': 0,\n              \'pid_identity_changed\': 0}\n    matches = []\n    pids = sorted((p for p in proc.iterdir() if p.name.isdigit()), key=lambda p: int(p.name))\n    if len(pids) > 4096:\n        raise RuntimeError(\'PROCESS_BOUND\')\n    for p in pids:\n        if int(p.name) == os.getpid():\n            continue\n        if time.monotonic() > deadline:\n            raise RuntimeError(\'OBSERVATION_DEADLINE\')\n        counts[\'processes\'] += 1\n        try:\n            before = identity(p)\n            tags = [i for i, tag in enumerate(TAGS) if tag.encode() in bounded(p / \'cmdline\', 65536)]\n            handles = []\n            fds = sorted((p / \'fd\').iterdir(), key=lambda f: int(f.name))\n            if len(fds) > 4096:\n                raise RuntimeError(\'FD_BOUND\')\n            for fd in fds:\n                counts[\'fds\'] += 1\n                if counts[\'fds\'] > 65536:\n                    raise RuntimeError(\'TOTAL_FD_BOUND\')\n                try:\n                    labels, deleted = classify(os.readlink(fd), roots)\n                    if not labels:\n                        continue\n                    fs = fd.stat()\n                    # Never open the descriptor target (which could be a database).\n                    flags = writable_flags(bounded(p / \'fdinfo\' / fd.name, 4096))\n                    handles.append({\'fd\': int(fd.name), \'roots\': labels, \'writable\': flags,\n                                    \'deleted\': deleted, \'device\': fs.st_dev, \'inode\': fs.st_ino})\n                except FileNotFoundError:\n                    counts[\'vanished\'] += 1\n                except PermissionError:\n                    counts[\'unreadable\'] += 1\n            mapped = []\n            # Shared writable mappings can persist after the file descriptor closes.\n            for line in bounded(p / \'maps\', 2097152).decode(\'utf-8\', \'replace\').splitlines():\n                fields = line.split(None, 5)\n                if len(fields) != 6 or len(fields[1]) != 4 or fields[1][1] != \'w\' or fields[1][3] != \'s\':\n                    continue\n                labels, deleted = classify(fields[5], roots)\n                if labels:\n                    mapped.append({\'roots\': labels, \'deleted\': deleted})\n            if len(handles) > 256 or len(mapped) > 256:\n                raise RuntimeError(\'MATCH_BOUND\')\n            if before != identity(p):\n                counts[\'pid_identity_changed\'] += 1\n                continue\n            if tags or handles or mapped:\n                group = bounded(p / \'cgroup\', 16384)\n                matches.append({\'pid\': int(p.name), \'ppid\': before[0], \'start_ticks\': before[1],\n                                \'uid\': p.stat().st_uid, \'tags\': tags,\n                                \'cgroup_sha256\': hashlib.sha256(group).hexdigest(),\n                                \'handles\': handles, \'shared_writable_mappings\': mapped})\n            if len(matches) > 128:\n                raise RuntimeError(\'MATCH_PROCESS_BOUND\')\n        except (FileNotFoundError, ProcessLookupError):\n            counts[\'vanished\'] += 1\n        except PermissionError:\n            counts[\'unreadable\'] += 1\n    return {\'counts\': counts, \'processes\': matches}\n\n\ndef observe(expected, nonce):\n    assert os.geteuid() == 0 and os.uname().nodename == expected\n    deadline = time.monotonic() + 35\n    roots = []\n    metadata = []\n    for label, name in ROOTS:\n        try:\n            resolved = str(Path(name).resolve(strict=True))\n            s = Path(name).stat()\n            roots += [(label, name), (label, resolved)]\n            metadata.append({\'root\': label, \'present\': True, \'device\': s.st_dev, \'inode\': s.st_ino})\n        except FileNotFoundError:\n            metadata.append({\'root\': label, \'present\': False})\n    samples = [scan(roots, deadline)]\n    units = []\n    for name in UNITS:\n        r = subprocess.run([\'/usr/bin/systemctl\', \'show\', name,\n            \'--property=LoadState,ActiveState,MainPID,ControlGroup\', \'--no-pager\'],\n            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3,\n            universal_newlines=True, env={\'PATH\': \'/usr/sbin:/usr/bin:/sbin:/bin\', \'LANG\': \'C\'})\n        fields = dict(line.split(\'=\', 1) for line in r.stdout.splitlines() if \'=\' in line)\n        states = (\'loaded\', \'not-found\', \'masked\', \'error\', \'bad-setting\', \'active\',\n                  \'inactive\', \'failed\', \'activating\', \'deactivating\', \'reloading\')\n        units.append({\'unit\': name, \'returncode\': r.returncode,\n                      \'load\': fields.get(\'LoadState\') if fields.get(\'LoadState\') in states else \'UNKNOWN\',\n                      \'active\': fields.get(\'ActiveState\') if fields.get(\'ActiveState\') in states else \'UNKNOWN\',\n                      \'pid\': int(fields.get(\'MainPID\', \'0\')),\n                      \'cgroup_sha256\': hashlib.sha256(fields.get(\'ControlGroup\', \'\').encode()).hexdigest()})\n    # Metadata of scheduler entrypoints; their contents/commands are not read.\n    schedulers = []\n    for name in (\'/etc/crontab\', \'/etc/cron.d\', \'/var/spool/cron\', \'/var/spool/cron/crontabs\'):\n        try:\n            s = Path(name).lstat()\n            schedulers.append({\'slot\': len(schedulers), \'present\': True, \'mode\': stat.S_IMODE(s.st_mode),\n                               \'uid\': s.st_uid, \'size\': s.st_size, \'symlink\': stat.S_ISLNK(s.st_mode)})\n        except FileNotFoundError:\n            schedulers.append({\'slot\': len(schedulers), \'present\': False})\n    samples.append(scan(roots, deadline))\n    return {\'hostname\': expected, \'uid\': 0, \'nonce\': nonce,\n            \'observed_at\': datetime.datetime.utcnow().isoformat() + \'Z\',\n            \'scope\': \'PR99_OPEN_HANDLE_OBSERVATION_NOT_AUTHORITY_OR_FENCE\',\n            \'roots\': metadata, \'samples\': samples, \'units\': units, \'scheduler_metadata\': schedulers,\n            \'authoritative_writer\': \'UNKNOWN\', \'enforced_fence\': \'UNKNOWN\', \'inflight_drained\': False,\n            \'database_opened\': False, \'service_actions\': 0, \'business_requests\': 0,\n            \'limitations\': [\'IDLE_WRITERS_NOT_EXCLUDED\', \'SCHEDULER_CONTENTS_NOT_READ\',\n                            \'OTHER_MOUNT_NAMESPACES_NOT_PROVEN\', \'NO_STOP_OR_DRAIN_PERFORMED\']}\n\n\nif __name__ == \'__main__\':\n    # EXPECTED/NONCE are supplied only by the exact fixed-host transport bootstrap.\n    print(json.dumps(observe(EXPECTED, NONCE), sort_keys=True), flush=True)\n'
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
    shell="#!/bin/sh\nset -eu\n/usr/bin/python3 -I -B - <<'PR99_READONLY'\n"+bootstrap+"\nPR99_READONLY\n"
    if len(shell.encode())>6000:raise Hold('COMMAND_LENGTH')
    return shell


"""Strict public metadata boundary for the fixed observer, not an admission."""
def validate_observation(data, expected, nonce):
    def need(value):
        if not value:
            raise ValueError('WRITER_OBSERVATION_SCHEMA')
    def fields(value, keys):
        need(type(value) is dict and set(value) == set(keys.split()))
    def integer(value, limit=2**64):
        need(type(value) is int and 0 <= value < limit)
    def boolean(value):
        need(type(value) is bool)
    def digest(value):
        need(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value))
    def rootnames(value):
        need(type(value) is list and 0 < len(value) <= 5 and value == sorted(set(value)))
        need(all(x in ('portal', 'operations', 'database', 'workspace', 'external_operations') for x in value))
    fields(data, 'hostname uid nonce observed_at scope roots samples units scheduler_metadata authoritative_writer enforced_fence inflight_drained database_opened service_actions business_requests limitations')
    need(data['hostname'] == expected and data['nonce'] == nonce)
    need(type(data['uid']) is int and data['uid'] == 0)
    need(type(data['observed_at']) is str and 19 <= len(data['observed_at']) <= 40
         and all(c in '0123456789T:.Z-' for c in data['observed_at']))
    need(data['scope'] == 'PR99_OPEN_HANDLE_OBSERVATION_NOT_AUTHORITY_OR_FENCE')
    need(data['authoritative_writer'] == data['enforced_fence'] == 'UNKNOWN')
    need(data['inflight_drained'] is False and data['database_opened'] is False)
    need(type(data['service_actions']) is int and data['service_actions'] == 0)
    need(type(data['business_requests']) is int and data['business_requests'] == 0)
    need(data['limitations'] == ['IDLE_WRITERS_NOT_EXCLUDED', 'SCHEDULER_CONTENTS_NOT_READ',
                                'OTHER_MOUNT_NAMESPACES_NOT_PROVEN', 'NO_STOP_OR_DRAIN_PERFORMED'])
    need(type(data['roots']) is list and len(data['roots']) == 5)
    for row, name in zip(data['roots'], ('portal', 'operations', 'database', 'workspace', 'external_operations')):
        fields(row, 'root present device inode' if row.get('present') is True else 'root present')
        need(row['root'] == name)
        boolean(row['present'])
        if row['present']:
            integer(row['device']); integer(row['inode'])
    need(type(data['samples']) is list and len(data['samples']) == 2)
    for sample in data['samples']:
        fields(sample, 'counts processes')
        fields(sample['counts'], 'processes fds vanished unreadable pid_identity_changed')
        for value in sample['counts'].values():
            integer(value, 131072)
        need(type(sample['processes']) is list and len(sample['processes']) <= 128)
        pids = set()
        for row in sample['processes']:
            fields(row, 'pid ppid start_ticks uid tags cgroup_sha256 handles shared_writable_mappings')
            for key in ('pid', 'ppid', 'start_ticks', 'uid'):
                integer(row[key])
            need(row['pid'] > 0 and row['pid'] not in pids)
            pids.add(row['pid'])
            digest(row['cgroup_sha256'])
            need(type(row['tags']) is list and len(row['tags']) <= 6)
            need(all(type(x) is int and 0 <= x < 6 for x in row['tags']))
            need(row['tags'] == sorted(set(row['tags'])))
            need(type(row['handles']) is list and len(row['handles']) <= 256)
            need(type(row['shared_writable_mappings']) is list and len(row['shared_writable_mappings']) <= 256)
            for handle in row['handles']:
                fields(handle, 'fd roots writable deleted device inode')
                for key in ('fd', 'device', 'inode'):
                    integer(handle[key])
                rootnames(handle['roots']); boolean(handle['writable']); boolean(handle['deleted'])
            for mapping in row['shared_writable_mappings']:
                fields(mapping, 'roots deleted')
                rootnames(mapping['roots']); boolean(mapping['deleted'])
    units = ('secure-secrets-portal.service', 'xuanjun-wecom-customer-contact.service',
             'xuanjun-wecom-customer-service.service', 'xuanjun-pr99-domestic-portal.service',
             'xuanjun-pr99-domestic-contact.service', 'xuanjun-pr99-domestic-customer-service.service')
    need(type(data['units']) is list and len(data['units']) == len(units))
    for row, name in zip(data['units'], units):
        fields(row, 'unit returncode load active pid cgroup_sha256')
        need(row['unit'] == name)
        need(type(row['returncode']) is int and -128 <= row['returncode'] <= 255)
        need(row['load'] in ('loaded', 'not-found', 'masked', 'error', 'bad-setting', 'UNKNOWN'))
        need(row['active'] in ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading', 'UNKNOWN'))
        integer(row['pid']); digest(row['cgroup_sha256'])
    need(type(data['scheduler_metadata']) is list and len(data['scheduler_metadata']) == 4)
    for index, row in enumerate(data['scheduler_metadata']):
        fields(row, 'slot present mode uid size symlink' if row.get('present') is True else 'slot present')
        integer(row['slot']); need(row['slot'] == index); boolean(row['present'])
        if row['present']:
            for key in ('mode', 'uid', 'size'):
                integer(row[key])
            boolean(row['symlink'])
    return data

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
        claim=Path('pr99-writer-observation-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-writer-observation-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_WRITER_OBSERVATION_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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
    valid = {'hostname': 'test', 'uid': 0, 'nonce': 'nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn', 'observed_at': '2026-10-18T12:00:00Z', 'scope': 'PR99_OPEN_HANDLE_OBSERVATION_NOT_AUTHORITY_OR_FENCE', 'roots': [{'root': 'portal', 'present': False}, {'root': 'operations', 'present': False}, {'root': 'database', 'present': False}, {'root': 'workspace', 'present': False}, {'root': 'external_operations', 'present': False}], 'samples': [{'counts': {'processes': 1, 'fds': 2, 'vanished': 0, 'unreadable': 0, 'pid_identity_changed': 0}, 'processes': [{'pid': 123, 'ppid': 1, 'start_ticks': 1234, 'uid': 1000, 'tags': [0], 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'handles': [{'fd': 3, 'roots': ['portal'], 'writable': True, 'deleted': False, 'device': 1, 'inode': 2}], 'shared_writable_mappings': [{'roots': ['operations'], 'deleted': True}]}]}, {'counts': {'processes': 1, 'fds': 2, 'vanished': 0, 'unreadable': 0, 'pid_identity_changed': 0}, 'processes': [{'pid': 123, 'ppid': 1, 'start_ticks': 1234, 'uid': 1000, 'tags': [0], 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'handles': [{'fd': 3, 'roots': ['portal'], 'writable': True, 'deleted': False, 'device': 1, 'inode': 2}], 'shared_writable_mappings': [{'roots': ['operations'], 'deleted': True}]}]}], 'units': [{'unit': 'secure-secrets-portal.service', 'returncode': 0, 'load': 'loaded', 'active': 'active', 'pid': 123, 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}, {'unit': 'xuanjun-wecom-customer-contact.service', 'returncode': 0, 'load': 'loaded', 'active': 'active', 'pid': 123, 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}, {'unit': 'xuanjun-wecom-customer-service.service', 'returncode': 0, 'load': 'loaded', 'active': 'active', 'pid': 123, 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}, {'unit': 'xuanjun-pr99-domestic-portal.service', 'returncode': 0, 'load': 'loaded', 'active': 'active', 'pid': 123, 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}, {'unit': 'xuanjun-pr99-domestic-contact.service', 'returncode': 0, 'load': 'loaded', 'active': 'active', 'pid': 123, 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}, {'unit': 'xuanjun-pr99-domestic-customer-service.service', 'returncode': 0, 'load': 'loaded', 'active': 'active', 'pid': 123, 'cgroup_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}], 'scheduler_metadata': [{'slot': 0, 'present': False}, {'slot': 1, 'present': False}, {'slot': 2, 'present': False}, {'slot': 3, 'present': False}], 'authoritative_writer': 'UNKNOWN', 'enforced_fence': 'UNKNOWN', 'inflight_drained': False, 'database_opened': False, 'service_actions': 0, 'business_requests': 0, 'limitations': ['IDLE_WRITERS_NOT_EXCLUDED', 'SCHEDULER_CONTENTS_NOT_READ', 'OTHER_MOUNT_NAMESPACES_NOT_PROVEN', 'NO_STOP_OR_DRAIN_PERFORMED']}
    assert decode_receipt(json.dumps(valid), 'test', 'n'*32) == valid
    mutations = [
        lambda x: x.update(private='SECRET'),
        lambda x: x.update(uid=False),
        lambda x: x.update(inflight_drained=True),
        lambda x: x.update(enforced_fence='PASS'),
        lambda x: x['samples'][0]['processes'][0].update(cmdline='SECRET'),
        lambda x: x['samples'][0]['processes'][0]['handles'][0].update(path='SECRET'),
        lambda x: x['samples'][0]['processes'][0]['handles'][0].update(writable=1),
        lambda x: x['samples'][0]['processes'][0]['handles'][0].update(roots=['SECRET']),
        lambda x: x['samples'][0]['processes'][0]['tags'].append('SECRET'),
        lambda x: x['samples'][0]['counts'].update(unreadable=False),
        lambda x: x['units'][0].update(unit='SECRET'),
        lambda x: x['scheduler_metadata'][0].update(contents='SECRET'),
        lambda x: x['roots'][0].update(root='SECRET'),
    ]
    for mutation in mutations:
        bad = json.loads(json.dumps(valid)); mutation(bad)
        try: decode_receipt(json.dumps(bad), 'test', 'n'*32)
        except Hold: pass
        else: raise AssertionError('PRIVATE_OR_FALSE_EVIDENCE_ACCEPTED')
    n = {'__name__': 'host_contract_tests'}
    exec(compile(HOST_PROGRAM, 'host_contract', 'exec'), n)
    roots = [('portal', '/a/runtime')]
    assert n['classify']('/a/runtime-other/file', roots) == ([], False)
    assert n['classify']('/a/runtime/db (deleted)', roots) == (['portal'], True)
    for flag, expected in [('0100000', False), ('0100001', True), ('0100002', True)]:
        assert n['writable_flags'](('flags:\t'+flag+'\n').encode()) is expected
    try: n['writable_flags'](b'pos: 0\n')
    except RuntimeError: pass
    else: raise AssertionError('UNKNOWN_FD_FLAGS_ACCEPTED')
    # stat comm may contain whitespace and ')'; starttime must remain field22.
    n['bounded'] = lambda *a: b'123 (odd ) name) S 7 ' + b'0 '*17 + b'987 0'
    assert n['identity'](Path('/fixture')) == (7, 987)
    for host in HOSTS: shell_for(host[4], 'f'*32)
    assert len(HOSTS) == 2 and {h[0] for h in HOSTS} == {'tokyo', 'domestic'}
    assert not any(x in HOST_PROGRAM for x in ('sqlite3', '.write_bytes(', '.write_text(', 'os.kill(', "'stop'", "'start'"))
    print('PR99_WRITER_OBSERVATION_CONTRACTS_PASS_13_REJECTIONS_NO_CLOUD', flush=True)


def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-writer-observe-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'WRITER_METADATA_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_WRITER_OBSERVATION_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_WRITER_OBSERVATION_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)
