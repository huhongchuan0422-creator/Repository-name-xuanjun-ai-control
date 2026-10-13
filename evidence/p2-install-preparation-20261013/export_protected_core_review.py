"""Export exact non-secret proposal bytes after protected digest validation; no apply."""
import os,stat,socket,hashlib,json,base64
P='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/plan-p2pkg-38420216343-1/protected-core-install-plan.json'
SHA='6a7789a023d0cbb265663275ee7442fdd026eaaee0fc4ee4a0f237ec5a62e970'
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
assert os.path.realpath(P)==P
fd=os.open(P,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,'rb') as f:
 s=os.fstat(f.fileno());raw=f.read(262145)
 assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and len(raw)<=262144
assert hashlib.sha256(raw).hexdigest()==SHA
v=json.loads(raw.decode())
assert set(v)=={'schema','transaction_id','artifact','cutover','activation','runtime','auth','tls'}
assert v['artifact']['source_commit']=='62d2e64d34feea1f02bffa7e8b597484bb98307f'
assert v['artifact']['manifest_sha256']=='2b49066f37742dedd41657fb445c91f4204fd4a2a257f921dd9fd514e5b25f0e'
assert v['auth']['mode']=='EXISTING_OAUTH_REFERENCE' and v['tls']['mode']=='EXISTING_TLS_REFERENCE'
assert all(set(x)=={'path','sha256','owner_uid','mode'} for x in v['auth']['references']+v['tls']['references'])
# Replacement strings were checked against the pinned generator: IDs, hashes,
# paths, generation and UUIDs only; no callback/GitHub/OAuth/TLS secret values.
import re
for row in v['runtime']['provisioning']:
 for token,value in row['replacements'].items():
  assert re.fullmatch(r'@@[A-Z0-9_]+@@',token)
  assert isinstance(value,str) and len(value)<=4096
  assert not re.search(r'(?i)secret|password|access_token|private_key',token)
assert not re.search(br'github_pat_|gh[pousr]_[A-Za-z0-9]|-----BEGIN .*PRIVATE KEY-----|Bearer ',raw)
# The exact pinned generator includes only public metadata, paths and digests.
# No referenced protected file or credential is opened or exported.
print('FULL_PLAN_BYTES_BASE64='+base64.b64encode(raw).decode())
print('FULL_PLAN_SHA256='+SHA)
print('FULL_PLAN_BYTE_COUNT='+str(len(raw)))
print('REDACTIONS=NONE; REFERENCED_SECRET_CONTENT=NOT_READ; INSTALL=NO; SERVICES_CHANGED=NO')
