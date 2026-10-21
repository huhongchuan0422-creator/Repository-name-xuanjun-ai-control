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
