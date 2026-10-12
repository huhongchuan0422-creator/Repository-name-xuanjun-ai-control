"""Fetch bounded code bytes for CODE_READY and return syntax-only receipts.

Runs from trusted control code. It never checks out or executes source code,
grants writer authority, uses models, or modifies canonical task state.
"""
import base64
import hashlib
import json
import os
import re
import urllib.request
import shutil
import subprocess
import sys

import native_syntax_gate

from native_syntax_gate import check_bytes


def _sha256_file(path):
    value=hashlib.sha256()
    with open(path,'rb') as stream:
        while True:
            chunk=stream.read(524288)
            if not chunk:break
            value.update(chunk)
    return value.hexdigest()


def _runtime(executable,args):
    path=os.path.realpath(executable)
    if not os.path.isabs(path) or not os.path.isfile(path):
        raise ValueError('CHECKER_EXECUTABLE_REQUIRED')
    proc=subprocess.run([path]+args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=5,check=False)
    lines=proc.stdout.decode('utf-8','replace').splitlines()
    if proc.returncode or not lines or len(lines[0])>160:
        raise ValueError('CHECKER_VERSION_REQUIRED')
    return {'path':path,'version':lines[0],'sha256':_sha256_file(path)}


def build_checker_identity():
    workspace=os.environ.get('GITHUB_WORKSPACE')
    module=os.environ.get('XJ_TYPESCRIPT_MODULE')
    if not workspace or os.path.realpath(workspace)!=workspace or not native_syntax_gate.trusted_typescript(module):
        raise ValueError('TRUSTED_CHECKER_CONTEXT_REQUIRED')
    proc=subprocess.run(['/usr/bin/git','-C',workspace,'rev-parse','HEAD'],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5,check=False)
    commit=proc.stdout.decode('ascii','strict').strip()
    if proc.returncode or not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('EXACT_CHECKOUT_COMMIT_REQUIRED')
    node=shutil.which('node')
    if not node:raise ValueError('NODE_CHECKER_REQUIRED')
    return {'gate_commit':commit,'python':_runtime(sys.executable,['--version']),
        'bash':_runtime('/usr/bin/bash',['--version']),'node':_runtime(node,['--version']),
        'intake_sha256':_sha256_file(__file__),'gate_sha256':_sha256_file(native_syntax_gate.__file__),
        'typescript_version':'5.7.3','typescript_sha256':_sha256_file(module)}


def validate_checker_identity(value):
    fields={'gate_commit','python','bash','node','intake_sha256','gate_sha256','typescript_version','typescript_sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['typescript_version']!='5.7.3'
            or not isinstance(value['gate_commit'],str) or not re.fullmatch('[0-9a-f]{40}',value['gate_commit'])):
        raise ValueError('EXACT_CHECKER_IDENTITY_REQUIRED')
    for field in ('intake_sha256','gate_sha256','typescript_sha256'):
        if not isinstance(value[field],str) or not re.fullmatch('[0-9a-f]{64}',value[field]):
            raise ValueError('EXACT_CHECKER_DIGEST_REQUIRED')
    for field in ('python','bash','node'):
        runtime=value[field]
        if (not isinstance(runtime,dict) or set(runtime)!= {'path','version','sha256'}
                or not isinstance(runtime['path'],str) or not os.path.isabs(runtime['path'])
                or os.path.normpath(runtime['path'])!=runtime['path']
                or not isinstance(runtime['version'],str) or not runtime['version']
                or not isinstance(runtime['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',runtime['sha256'])):
            raise ValueError('EXACT_RUNTIME_IDENTITY_REQUIRED')


def github_json(url, token):
    request=urllib.request.Request(url,headers={
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'User-Agent':'xuanjun-syntax-intake'})
    with urllib.request.urlopen(request,timeout=15) as response:
        raw=response.read(2097153)
    if len(raw)>2097152:raise ValueError('BOUNDED_GITHUB_RESPONSE_REQUIRED')
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('DUPLICATE_API_JSON_KEY')
            value[key]=item
        return value
    value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_API_JSON')))
    if not isinstance(value,dict):raise ValueError('API_OBJECT_REQUIRED')
    return value


def syntax_receipt(value, control_repository, token, read=github_json, typescript_module=None,checker_identity=None):
    if value.get('event')!='CODE_READY':return None
    repo=value.get('target_repository')
    # Metadata receipt intake does not authorize other repositories.
    if repo!=control_repository or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',repo):
        return {'state':'HOLD_TARGET_REPOSITORY_ADMISSION_REQUIRED','authority_effect':'NONE'}
    if checker_identity is None:checker_identity=build_checker_identity()
    validate_checker_identity(checker_identity)
    base,head=value.get('target_base_sha'),value.get('code_commit')
    if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{40}',v) for v in (base,head)):
        raise ValueError('EXACT_COMMIT_BINDING_REQUIRED')
    prefix='https://api.github.com/repos/'+repo
    change=read(prefix+'/compare/'+base+'...'+head,token)
    if (change.get('status')!='ahead' or change.get('base_commit',{}).get('sha')!=base
            or change.get('merge_base_commit',{}).get('sha')!=base
            or not isinstance(change.get('commits'),list) or not change['commits']
            or change['commits'][-1].get('sha')!=head):
        raise ValueError('EXACT_ANCESTOR_REQUIRED')
    files=change.get('files')
    if not isinstance(files,list) or not files or len(files)>32:
        raise ValueError('BOUNDED_CHANGED_FILES_REQUIRED')
    tree=read(prefix+'/git/trees/'+head+'?recursive=1',token)
    if tree.get('truncated') is not False:
        raise ValueError('COMPLETE_TREE_REQUIRED')
    objects={item['path']:item for item in tree.get('tree',[])}
    checks=[];total=0;seen=set()
    for file in files:
        path=file.get('filename')
        if (not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',path)
                or any(p in ('','.','..') for p in path.split('/')) or path in seen):
            raise ValueError('SAFE_UNIQUE_PATH_REQUIRED')
        seen.add(path)
        previous=file.get('previous_filename')
        if file.get('status')=='renamed' and previous is None:
            raise ValueError('RENAME_SOURCE_REQUIRED')
        if previous is not None and (not isinstance(previous,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',previous) or any(p in ('','.','..') or p.startswith('.') for p in previous.split('/')) or re.search(r'(^|/)(auth|secret|credential|token)[^/]*$',previous,re.I)):
            raise ValueError('PROTECTED_RENAME_SOURCE')
        if any(p.startswith('.') for p in path.split('/')) or re.search(r'(^|/)(auth|secret|credential|token)[^/]*$',path,re.I):
            raise ValueError('PROTECTED_PATH_REQUIRES_SEPARATE_ADMISSION')
        if file.get('status')=='removed':
            if path in objects:raise ValueError('REMOVAL_TREE_MISMATCH')
            checks.append({'path':path,'state':'REMOVED_DATA_ONLY','code_executed':False})
            continue
        if file.get('status') not in ('added','modified','renamed'):
            raise ValueError('UNSUPPORTED_CHANGE_TYPE')
        obj=objects.get(path,{})
        if (obj.get('type')!='blob' or obj.get('mode') not in ('100644','100755')
                or obj.get('sha')!=file.get('sha') or type(obj.get('size')) is not int
                or obj['size']>131072):
            raise ValueError('REGULAR_BOUNDED_BLOB_REQUIRED')
        total+=obj['size']
        if total>524288:raise ValueError('BUNDLE_TOO_LARGE')
        blob=read(prefix+'/git/blobs/'+obj['sha'],token)
        if blob.get('encoding')!='base64':raise ValueError('BLOB_ENCODING_REQUIRED')
        raw=base64.b64decode(''.join(blob['content'].split()),validate=True)
        if len(raw)!=obj['size'] or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=obj['sha']:
            raise ValueError('BLOB_IDENTITY_MISMATCH')
        checks.append(check_bytes(path,raw,typescript_module))
    binding={key:value[key] for key in ('task_id','spec_sha256','checkpoint_sha256',
             'entry','target_repository','target_base_sha','code_commit')}
    binding['files']=sorted(checks,key=lambda c:c['path'])
    binding['checker']=checker_identity
    digest=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    passed=all(c['state'] in ('PASS_SYNTAX','REMOVED_DATA_ONLY') for c in checks)
    return {'state':'PASS_SYNTAX_NOT_ADMITTED' if passed else 'HOLD_SYNTAX_GATE',
            'binding':binding,'receipt_sha256':digest,'authority_effect':'NONE',
            'code_executed':False,'independent_review':'NOT_PERFORMED',
            'security_approved':False,'quota_attribution':'UNKNOWN'}
