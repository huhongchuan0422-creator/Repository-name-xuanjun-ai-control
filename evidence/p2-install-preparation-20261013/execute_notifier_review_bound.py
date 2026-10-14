"""Caller guard for the single accepted notifier operation; no arbitrary inputs."""
import hashlib
import json
import os
import stat
import subprocess
import sys
import urllib.request

APPROVAL = 6158080472
APPROVAL_BODY_SHA = 'cfd4c7a42e6797cd97b95e2a7770dee290591cc66457cbd388c01ffe4b5be05a'
SCRIPT_SHA = '967204b970c39191eb3eff5e71a61fa0adab3be898dbf8f1fdb61131dfabb11e'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notifier_isolation_candidate.py')

ROOT_LOADER = r'''
import hashlib,json,os,stat,sys
path=sys.argv[1]
expected='967204b970c39191eb3eff5e71a61fa0adab3be898dbf8f1fdb61131dfabb11e'
if os.geteuid()!=0:raise ValueError('ROOT_REQUIRED')
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,'rb') as f:
 info=os.fstat(f.fileno());raw=f.read(65537)
 if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or len(raw)>65536:raise ValueError('SOURCE_BOUND')
if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('ROOT_SOURCE_SHA_MISMATCH')
# Execute the exact verified in-memory bytes, never reopen a mutable source path.
sys.argv=[path,'--candidate-acceptance','PR58:6158080472']
namespace={'__name__':'__main__','__file__':path}
failed=None
try:
 exec(compile(raw,path,'exec'),namespace)
except BaseException as error:
 failed=type(error).__name__
finally:
 base='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5/notifier'
 result={'schema':1,'acceptance':'PR58:6158080472','script_sha256':expected,'execution_error_type':failed,'root_journal_present':os.path.lexists(base+'/notifier-isolation-receipt.json')}
 if result['root_journal_present']:
  digests={}
  for name in ['notifier-isolation-receipt.json','xj-uk-owner-notify.timer.backup','xj-uk-owner-notify.service.backup']:
   p=base+'/'+name
   if os.path.realpath(p)!=p:raise ValueError('RECEIPT_ALIAS')
   fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
   with os.fdopen(fd,'rb') as f:
    i=os.fstat(f.fileno());b=f.read(1048577)
    if not stat.S_ISREG(i.st_mode) or i.st_uid!=0 or i.st_gid!=0 or stat.S_IMODE(i.st_mode)!=0o600 or i.st_nlink!=1 or len(b)>1048576:raise ValueError('RECEIPT_IDENTITY')
   digests[name]=hashlib.sha256(b).hexdigest()
   if name=='notifier-isolation-receipt.json':result['actual_receipt']=json.loads(b.decode('utf-8'))
  result['root_private_file_digests']=digests
 print('NOTIFIER_REVIEW_BOUND_EXECUTION_RESULT='+json.dumps(result,sort_keys=True))
if failed is not None:sys.exit(1)
'''


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('APPROVAL_REDIRECT_REJECTED')


def enforce_approval(comment, raw):
    if (comment.get('id') != APPROVAL
            or comment.get('user', {}).get('login') != 'huhongchuan0422-creator'
            or hashlib.sha256(comment.get('body', '').encode()).hexdigest() != APPROVAL_BODY_SHA
            or hashlib.sha256(raw).hexdigest() != SCRIPT_SHA):
        raise ValueError('EXACT_REVIEW_SOURCE_BINDING_FAILED')


def main():
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise ValueError('APPROVAL_READ_AUTH_REQUIRED')
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/issues/comments/' + str(APPROVAL),
                                     headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw_comment = response.read(16385)
    if len(raw_comment) > 16384:
        raise ValueError('APPROVAL_BOUND_EXCEEDED')
    comment = json.loads(raw_comment.decode())
    fd = os.open(SCRIPT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        raw = stream.read(65537)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or len(raw) > 65536:
        raise ValueError('EXACT_REVIEWED_SCRIPT_BOUND')
    enforce_approval(comment, raw)
    print('EXACT_REVIEW_CALLER_BINDING=PASS; APPROVAL=6158080472; SCRIPT_SHA256=' + SCRIPT_SHA, flush=True)
    # Credentials do not enter root environment or argv.
    minimal = {'PATH': '/usr/bin:/bin', 'LANG': 'C'}
    result = subprocess.run(['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I', '-B', '-c', ROOT_LOADER, SCRIPT], env=minimal)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
