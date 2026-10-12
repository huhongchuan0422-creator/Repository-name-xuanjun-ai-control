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

from native_syntax_gate import check_bytes


def github_json(url, token):
    request=urllib.request.Request(url,headers={
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'User-Agent':'xuanjun-syntax-intake'})
    with urllib.request.urlopen(request,timeout=15) as response:
        raw=response.read(2097153)
    if len(raw)>2097152:raise ValueError('BOUNDED_GITHUB_RESPONSE_REQUIRED')
    return json.loads(raw.decode('utf-8'))


def syntax_receipt(value, control_repository, token, read=github_json, typescript_module=None):
    if value.get('event')!='CODE_READY':return None
    repo=value.get('target_repository')
    # Metadata receipt intake does not authorize other repositories.
    if repo!=control_repository or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',repo):
        return {'state':'HOLD_TARGET_REPOSITORY_ADMISSION_REQUIRED','authority_effect':'NONE'}
    base,head=value.get('target_base_sha'),value.get('code_commit')
    if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{40}',v) for v in (base,head)):
        raise ValueError('EXACT_COMMIT_BINDING_REQUIRED')
    prefix='https://api.github.com/repos/'+repo
    change=read(prefix+'/compare/'+base+'...'+head,token)
    if (change.get('status')!='ahead' or change.get('base_commit',{}).get('sha')!=base
            or change.get('merge_base_commit',{}).get('sha')!=base):
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
    binding['files']=checks
    digest=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    passed=all(c['state'] in ('PASS_SYNTAX','REMOVED_DATA_ONLY') for c in checks)
    return {'state':'PASS_SYNTAX_NOT_ADMITTED' if passed else 'HOLD_SYNTAX_GATE',
            'binding':binding,'receipt_sha256':digest,'authority_effect':'NONE',
            'code_executed':False,'independent_review':'NOT_PERFORMED',
            'security_approved':False,'quota_attribution':'UNKNOWN'}
