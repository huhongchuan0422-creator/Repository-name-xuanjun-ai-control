"""Default-off original queue adapter for the frozen website baseline collector.

No arbitrary command/path, installation, credential or server enrollment API.
Host enrollment supplies the approved binding digest; requests cannot enroll it.
"""
import base64
import hashlib
import json
import shlex
import zlib

from .queue import Hold, SHA, TOKEN, canonical, decode, TARGETS
from .private_transfer import check, strict

COLLECTOR_SHA = 'c352c041ab62a1bf3c1c55afeea461ba935016e294975dfb515e19972365250f'
LABELS = {'CURRENT','RUNTIME_CURRENT','R2_RECEIPT','INSTALLED_PUBLISHER','RUNTIME_UNIT',
          'STATIC_LOCK','CANDIDATE_LEDGER'} | {'NGINX_%02d' % i for i in range(1,14)}
SEALED = 'conn-second-window-uk-20261021T162627Z'


class WebsiteBaselinePolicy:
    def __init__(self, source, raw_binding, approved_binding_sha):
        check(type(source) is bytes and hashlib.sha256(source).hexdigest() == COLLECTOR_SHA, 'COLLECTOR_SOURCE_PIN')
        check(type(raw_binding) is bytes and len(raw_binding) <= 16384
              and type(approved_binding_sha) is str and SHA.fullmatch(approved_binding_sha)
              and hashlib.sha256(raw_binding).hexdigest() == approved_binding_sha, 'HOST_ACTION_BINDING')
        b = strict(raw_binding)
        check(type(b) is dict and set(b) == {'schema','project','target','operation','source_commit',
              'collector_sha256','execution_identity','max_output_bytes','input_manifest_sha256',
              'plan_sha256','approval_ref','valid_from','valid_until'}, 'FIXED_ACTION_FIELDS')
        check(type(b['schema']) is int and b['schema'] == 1 and b['target'] == 'domestic'
              and b['operation'] == 'website_baseline_collect' and b['execution_identity'] == 'root'
              and b['collector_sha256'] == COLLECTOR_SHA and type(b['max_output_bytes']) is int
              and b['max_output_bytes'] == 32768, 'FIXED_ACTION_SCOPE')
        import re
        check(type(b['source_commit']) is str and re.fullmatch('[0-9a-f]{40}',b['source_commit']), 'ACTION_SOURCE_COMMIT')
        for key in ('project','approval_ref'):
            check(type(b[key]) is str and TOKEN.fullmatch(b[key]), 'ACTION_REFERENCE')
        for key in ('input_manifest_sha256','plan_sha256'):
            check(type(b[key]) is str and SHA.fullmatch(b[key]), 'ACTION_INPUT_PIN')
        check(type(b['valid_from']) is int and type(b['valid_until']) is int
              and 0 < b['valid_until']-b['valid_from'] <= 86400, 'ACTION_WINDOW')
        self.source, self.binding, self.sha = source, b, approved_binding_sha

    def validate(self, request, actor, now):
        b=self.binding
        check(actor == 332398908 and type(actor) is int and request['request_id'] != SEALED, 'ACTION_ACTOR_OR_SEALED')
        check(request['project'] == b['project'] and request['target'] == b['target']
              and request['operation'] == 'project_fixed_action'
              and request['arguments'] == {'binding_sha256':self.sha}, 'ACTION_REQUEST_SCOPE')
        check(b['valid_from'] <= now < b['valid_until'] and request['expires_unix'] <= b['valid_until'], 'ACTION_WINDOW')

    def command(self, request):
        # This code runs only the byte-pinned existing collector, with no caller
        # command, args, URL or filesystem path. No upload/install/cleanup.
        nonce=hashlib.sha256(canonical(request).encode()).hexdigest()
        code = ('import base64,subprocess,sys,json,os,hashlib,zlib\n'
                's=zlib.decompress(base64.b64decode(%r))\n'
                'assert len(s)==12809 and hashlib.sha256(s).hexdigest()==%r\n'
                'r=subprocess.run([sys.executable,"-I","-B","-S","-c",s.decode("utf-8")],'
                'stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=25)\n'
                'assert len(r.stdout)<=32768\n'
                'print(json.dumps(dict(hostname=os.uname().nodename,uid=os.geteuid(),nonce=%r,'
                'collector_exit=r.returncode,bytes=len(r.stdout),sha256=hashlib.sha256(r.stdout).hexdigest(),'
                'base64=base64.b64encode(r.stdout).decode())))\n') % (base64.b64encode(zlib.compress(self.source,9)).decode(),COLLECTOR_SHA,nonce)
        command='/usr/bin/python3 -I -B -S -c '+shlex.quote(code)
        check(len(base64.b64encode(command.encode())) <= 16384, 'SWAS_COMMAND_BOUND')
        return {'CommandContent':command,
                'Type':'RunShellScript','WorkingUser':'root','WorkingDir':'/',
                'Timeout':30,'Name':'xuanjun-fixed-website-baseline-readonly'}

    def result(self, request, invoke, response):
        from .worker import HOSTS
        row=response.get('InvocationResult',{})
        check(row.get('InvokeId') == invoke and row.get('InstanceId') == TARGETS[request['target']][2], 'RESULT_TARGET')
        state=row.get('InvocationStatus')
        if state in ('Pending','Running','Stopping'): return None,None
        if state != 'Success' or type(row.get('ExitCode')) is not int or row['ExitCode'] != 0:
            return {'state':'FAILED','invoke_id':invoke,'exit_code':row.get('ExitCode')},None
        raw=row.get('Output')
        check(type(raw) is str and len(raw) <= 131072, 'OUTPUT_BOUND')
        text=raw if raw.lstrip().startswith('{') else base64.b64decode(raw,validate=True).decode()
        v=strict(text.encode())
        check(v.get('hostname') == HOSTS[request['target']] and type(v.get('uid')) is int and v['uid'] == 0
              and v.get('nonce') == hashlib.sha256(canonical(request).encode()).hexdigest(), 'REMOTE_IDENTITY')
        data=base64.b64decode(v['base64'],validate=True)
        check(len(data) <= 32768 and type(v.get('bytes')) is int and v['bytes'] == len(data)
              and hashlib.sha256(data).hexdigest() == v.get('sha256'), 'FILE_DIGEST')
        observation=strict(data)
        check(type(observation) is dict and observation.get('scope') == 'STATIC_BASELINE_FIXED_READONLY_CANDIDATE', 'COLLECTOR_RESULT_SCOPE')
        success=v.get('collector_exit') == 0 and type(v.get('collector_exit')) is int and observation.get('state') == 'OBSERVATION_ONLY'
        if success:
            rows=observation.get('observations')
            check(type(rows) is list and len(rows) == 20
                  and {x.get('label') for x in rows if type(x) is dict} == LABELS, 'COLLECTOR_FIXED_TWENTY')
        return {'state':'SUCCESS' if success else 'FAILED','invoke_id':invoke,'target':request['target'],
                'action_binding_sha256':self.sha,'collector_sha256':COLLECTOR_SHA,
                'bytes':len(data),'sha256':v['sha256'],'business_acceptance':'NOT_GRANTED'},data


class ApprovedObjectsPolicy:
    """Default-off, bounded analysis objects; no catalog approval or root creation.

    A root-owned, hash-pinned host binding supplies every value. There is one
    immutable request ID per object; callers cannot choose paths or recipients.
    Only metadata leaves the cloud command. Bodies use the original transfer.
    """
    def __init__(self, raw_binding, approved_binding_sha):
        import os
        import re
        from .private_transfer import Catalog
        check(type(raw_binding) is bytes and len(raw_binding) <= 16384
              and type(approved_binding_sha) is str and SHA.fullmatch(approved_binding_sha)
              and hashlib.sha256(raw_binding).hexdigest() == approved_binding_sha,
              'APPROVED_OBJECT_HOST_BINDING')
        b = strict(raw_binding)
        fields = {'schema', 'catalog', 'catalog_sha256', 'policy', 'roots', 'recipient_id',
                  'requests', 'execution_user', 'execution_uid', 'reader_sha256'}
        check(type(b) is dict and (set(b) == fields or set(b) == fields | {'archives', 'archive_reader_sha256'}),
              'APPROVED_OBJECT_FIELDS')
        check(type(b['schema']) is int and b['schema'] == 1, 'APPROVED_OBJECT_SCHEMA')
        policy = b['policy']
        check(type(policy) is dict
              and type(policy.get('max_objects')) is int and 0 < policy['max_objects'] <= 19
              and type(policy.get('max_total_bytes')) is int and 0 < policy['max_total_bytes'] <= 93592
              and type(policy.get('max_object_bytes')) is int and 0 < policy['max_object_bytes'] <= 53969,
              'APPROVED_OBJECT_ANALYSIS_BUDGET')
        catalog = Catalog(canonical(b['catalog']).encode(), b['catalog_sha256'], policy)
        check(catalog.value['target'] == 'uk' and catalog.value['recipients'] == [b['recipient_id']]
              and policy['recipients'] == [b['recipient_id']], 'APPROVED_OBJECT_RECIPIENT')
        roots = b['roots']
        check(type(roots) is dict and set(roots) == set(policy['root_refs'])
              and set(roots) == {x['root_ref'] for x in catalog.objects.values()}, 'APPROVED_OBJECT_ROOTS')
        for root in roots.values():
            check(type(root) is list and len(root) == 2 and type(root[0]) is str
                  and root[0].startswith('/') and os.path.normpath(root[0]) == root[0]
                  and root[0] != '/' and type(root[1]) is int and root[1] >= 0,
                  'APPROVED_OBJECT_ROOT')
        check(type(b['execution_user']) is str and re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', b['execution_user'])
              and type(b['execution_uid']) is int and b['execution_uid'] >= 0, 'APPROVED_OBJECT_EXECUTION_IDENTITY')
        requests = b['requests']
        check(type(requests) is dict and set(requests) == set(catalog.objects)
              and all(type(v) is str and TOKEN.fullmatch(v) and v != SEALED for v in requests.values())
              and len(set(requests.values())) == len(requests), 'APPROVED_OBJECT_SINGLE_REQUEST')
        check(type(b['reader_sha256']) is str and SHA.fullmatch(b['reader_sha256']), 'APPROVED_OBJECT_READER_PIN')
        if 'archives' in b:
            from .archive_reader import validate_archive
            check(type(b['archives']) is dict and len(b['archives']) == 1
                  and set(b['archives']) <= set(roots)
                  and type(b['archive_reader_sha256']) is str and SHA.fullmatch(b['archive_reader_sha256']), 'APPROVED_ARCHIVES')
            check(sum(x['root_ref'] in b['archives'] for x in catalog.objects.values()) <= 5, 'APPROVED_ARCHIVE_MEMBER_COUNT')
            for ref, plan in b['archives'].items():
                validate_archive(plan)
                check(plan['identity'][3] == roots[ref][1], 'APPROVED_ARCHIVE_OWNER')
        self.binding, self.sha, self.catalog = b, approved_binding_sha, catalog

    def request_object(self, request):
        b, c = self.binding, self.catalog
        args = request.get('arguments')
        check(type(args) is dict and set(args) == {'manifest_sha256', 'object_ref', 'recipient_id'},
              'APPROVED_OBJECT_ARGUMENTS')
        ref = args['object_ref']
        check(type(ref) is str and ref in c.objects and args['manifest_sha256'] == c.sha
              and args['recipient_id'] == b['recipient_id']
              and request.get('request_id') == b['requests'][ref]
              and request.get('project') == c.value['project'] and request.get('target') == 'uk'
              and request.get('operation') == 'fetch_approved_object'
              and request.get('executor_sha256') == c.value['executor_sha256'], 'APPROVED_OBJECT_SCOPE')
        return c.objects[ref]

    def validate(self, request, actor, now):
        check(type(actor) is int and actor == 332398908, 'APPROVED_OBJECT_ACTOR')
        item = self.request_object(request)
        self.catalog.object(item['ref'], self.binding['recipient_id'], now)
        check(type(request['expires_unix']) is int and now < request['expires_unix'] <= self.catalog.value['valid_until'], 'APPROVED_OBJECT_EXPIRY')

    def reader_source(self, archive=False):
        import ast
        from pathlib import Path
        from . import private_transfer as transfer
        from . import archive_reader
        code = ''
        modules = [(transfer, 'reader_sha256', ('check', 'stamp', 'directory') if archive else ('check', 'stamp', 'directory', 'read_object'))]
        if archive:
            modules.append((archive_reader, 'archive_reader_sha256', ('validate_archive', 'ArchiveView', '_read_archive', 'read_archive_member_metadata')))
        for module, pin, names in modules:
            raw = Path(module.__file__).with_suffix('.py').read_bytes()
            check(hashlib.sha256(raw).hexdigest() == self.binding[pin], 'APPROVED_OBJECT_READER_PIN')
            text = raw.decode('utf-8'); nodes = ast.parse(text).body; lines = text.splitlines(True)
            for name in names:
                matches = [(i, n) for i, n in enumerate(nodes) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
                check(len(matches) == 1, 'APPROVED_OBJECT_READER_SOURCE')
                i, node = matches[0]
                end = nodes[i + 1].lineno - 1 if i + 1 < len(nodes) else len(lines)
                code += ''.join(lines[node.lineno - 1:end]) + '\n'
        return code

    def read_source(self, item):
        from .private_transfer import read_object
        from .archive_reader import read_archive_member
        check(item == self.catalog.objects.get(item.get('ref')), 'APPROVED_OBJECT_ITEM')
        plan = self.binding.get('archives', {}).get(item['root_ref'])
        self.reader_source(plan is not None)
        root, owner = self.binding['roots'][item['root_ref']]
        return read_archive_member(root, owner, item, plan) if plan is not None else read_object(root, owner, item)

    def read_archive_group(self, items):
        from .archive_reader import read_archive_members
        check(type(items) is list and 0 < len(items) <= 5, 'APPROVED_ARCHIVE_GROUP')
        ref = items[0]['root_ref']
        check(all(x == self.catalog.objects.get(x.get('ref')) and x['root_ref'] == ref for x in items), 'APPROVED_ARCHIVE_GROUP')
        plan = self.binding.get('archives', {}).get(ref)
        check(plan is not None, 'APPROVED_ARCHIVE_GROUP')
        self.reader_source(True)
        root, owner = self.binding['roots'][ref]
        return read_archive_members(root, owner, items, plan)

    def command(self, request):
        # Reuse the existing descriptor reader verbatim, rather than introduce
        # a second path walker. Its code is already included in runtime.code_pin.
        from .worker import HOSTS
        item = self.request_object(request)
        root, owner = self.binding['roots'][item['root_ref']]
        plan = self.binding.get('archives', {}).get(item['root_ref'])
        code = 'import os,stat,time,hashlib,json,tarfile\nclass Hold(Exception): pass\nCHUNK=65536\n'
        code += self.reader_source(plan is not None)
        read_call = ('read_archive_member_metadata(%r,%r,%r,%r)' % (root, owner, item, plan)
                     if plan is not None else 'read_object(%r,%r,%r)' % (root, owner, item))
        nonce = hashlib.sha256(canonical(request).encode()).hexdigest()
        body = ('check(os.uname().nodename==%r and os.geteuid()==%r,"REMOTE_IDENTITY")\n'
                 'check(%r<=int(time.time())<%r,"APPROVED_OBJECT_EXPIRED_BEFORE_READ")\n'
                 'data=%s\n'
                 'check(int(time.time())<%r,"APPROVED_OBJECT_EXPIRED_AFTER_READ")\n'
                 'print(json.dumps(dict(hostname=os.uname().nodename,uid=os.geteuid(),nonce=%r,'
                 'manifest_sha256=%r,object_ref=%r,recipient_id=%r,bytes=len(data),'
                 'sha256=hashlib.sha256(data).hexdigest())))\n') % (
                     HOSTS['uk'], self.binding['execution_uid'], self.catalog.value['valid_from'],
                     min(request['expires_unix'], self.catalog.value['valid_until']), read_call,
                     min(request['expires_unix'], self.catalog.value['valid_until']), nonce, self.catalog.sha, item['ref'], self.binding['recipient_id'])
        import textwrap
        code += 'try:\n' + textwrap.indent(body, '    ') + 'except BaseException:\n    raise SystemExit(2)\n'
        command = '/usr/bin/python3 -I -B -S -c ' + shlex.quote(code)
        check(len(base64.b64encode(command.encode())) <= 16384, 'SWAS_COMMAND_BOUND')
        return {'CommandContent': command, 'Type': 'RunShellScript',
                'WorkingUser': self.binding['execution_user'], 'WorkingDir': '/',
                'Timeout': 45, 'Name': 'xuanjun-approved-object-metadata'}

    def result(self, request, invoke, response):
        from .worker import HOSTS
        item = self.request_object(request)
        check(type(invoke) is str and TOKEN.fullmatch(invoke), 'APPROVED_OBJECT_INVOKE')
        check(type(response) is dict and type(response.get('InvocationResult')) is dict, 'RESULT_FORMAT')
        row = response['InvocationResult']
        check(row.get('InvokeId') == invoke and row.get('InstanceId') == TARGETS['uk'][2], 'RESULT_TARGET')
        status = row.get('InvocationStatus')
        if status in ('Pending', 'Running', 'Stopping'):
            return None, None
        exit_code = row.get('ExitCode')
        check(type(exit_code) is int and -2147483648 <= exit_code <= 2147483647, 'APPROVED_OBJECT_EXIT_CODE')
        if status != 'Success' or exit_code != 0:
            return {'state': 'FAILED', 'invoke_id': invoke, 'exit_code': exit_code}, None
        raw = row.get('Output')
        check(type(raw) is str and len(raw.encode()) <= 8192, 'APPROVED_OBJECT_OUTPUT_BOUND')
        try:
            text = raw if raw.lstrip().startswith('{') else base64.b64decode(raw, validate=True).decode('utf-8')
        except (ValueError, UnicodeError):
            raise Hold('APPROVED_OBJECT_OUTPUT_FORMAT') from None
        v = strict(text.encode())
        expected = {'hostname': HOSTS['uk'], 'uid': self.binding['execution_uid'],
                    'nonce': hashlib.sha256(canonical(request).encode()).hexdigest(),
                    'manifest_sha256': self.catalog.sha, 'object_ref': item['ref'],
                    'recipient_id': self.binding['recipient_id'], 'bytes': item['bytes'], 'sha256': item['sha256']}
        check(type(v) is dict and set(v) == set(expected)
              and type(v.get('uid')) is int and type(v.get('bytes')) is int
              and v == expected, 'APPROVED_OBJECT_RESULT_BINDING')
        # This is derived exclusively from an observed successful invocation;
        # no body or synthetic file_ref is inserted in the original queue.
        return {'state': 'SUCCESS', 'invoke_id': invoke, 'target': 'uk',
                'manifest_sha256': self.catalog.sha, 'object_ref': item['ref'],
                'recipient_id': self.binding['recipient_id'], 'bytes': item['bytes'],
                'sha256': item['sha256'], 'action_binding_sha256': self.sha}, None
