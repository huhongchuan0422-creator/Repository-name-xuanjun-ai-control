#!/usr/bin/python3
"""Owner-only protected input; no runtime install, service or ledger changes."""
import os, socket, stat, getpass, re, json, urllib.request, urllib.error, hashlib
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
ROOT='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
s=os.lstat(ROOT)
assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700 and os.path.realpath(ROOT)==ROOT
path=ROOT+'/github-intake-token.input'
assert not os.path.lexists(path)
token=getpass.getpass('Repository-scoped GitHub token (hidden; never paste into chat): ')
if not re.fullmatch(r'github_pat_[A-Za-z0-9_]{20,250}',token):
    raise SystemExit('HOLD_FINE_GRAINED_TOKEN_FORMAT')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None
req=urllib.request.Request('https://api.github.com/repos/'+REPO,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'xuanjun-owner-protected-input'})
try:
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as f:raw=f.read(1048577)
    if len(raw)>1048576 or json.loads(raw.decode()).get('full_name')!=REPO:
        raise ValueError('REPOSITORY_IDENTITY')
except Exception:
    raise SystemExit('HOLD_REPOSITORY_READ_AUTH_NOT_VERIFIED')
raw=(token+'\n').encode()
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
del token
receipt={'schema':1,'state':'PROTECTED_GITHUB_INPUT_STORED_READ_ACCESS_VERIFIED','path':path,'sha256':hashlib.sha256(raw).hexdigest(),'owner_uid':0,'mode':0o600,'repository':REPO,'write_permission':'NOT_TESTED','runtime_install':False}
fd=os.open(ROOT+'/github-input-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as f:json.dump(receipt,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
print('PROTECTED_GITHUB_INPUT=STORED; REPOSITORY_READ=VERIFIED; WRITE_PERMISSION=NOT_TESTED; INSTALL=NO')
