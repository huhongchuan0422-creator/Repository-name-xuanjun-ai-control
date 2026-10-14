"""Export exact non-secret proposal bytes after protected digest validation; no apply."""
import os,stat,socket,hashlib,json,base64
P='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/prerequisite-plan-38426073390/protected-prerequisite-install-proposal.json'
SHA='09970be3ffb35fc266385b9798fd95ed797044078b9d9de9b9a6842aef502cec'
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
assert os.path.realpath(P)==P
fd=os.open(P,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,'rb') as f:
 s=os.fstat(f.fileno());raw=f.read(262145)
 assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600 and len(raw)<=262144
assert hashlib.sha256(raw).hexdigest()==SHA
v=json.loads(raw.decode())
assert set(v)=={'schema','state','reviewed_runtime','references','proposed_nginx_identity','rpm_install_command','rpm_rollback_command','excluded_host_flag','unit_autopreset_allowed','old_units_observed','existing_payload_conflicts','payload_paths_checked','required_before_apply','install_admission','apply_entrypoint_integrated','production_rollback_verified','model_calls'}
assert v['install_admission'] is False and v['reviewed_runtime']['source']=='62d2e64d34feea1f02bffa7e8b597484bb98307f'
assert v['rpm_install_command'][:4]==['/bin/rpm','-U','--noscripts','--notriggers']
assert v['rpm_rollback_command'][:4]==['/bin/rpm','-e','--noscripts','--notriggers']
assert set(v['references'])=={'core_plan','owner_readback','rpm_baseline','rpm_effects','rpm_rehearsal'}
assert all(set(x)=={'path','sha256'} for x in v['references'].values())
# The exact pinned generator includes only public metadata, paths and digests.
# No referenced protected file or credential is opened or exported.
print('FULL_PLAN_BYTES_BASE64='+base64.b64encode(raw).decode())
print('FULL_PLAN_SHA256='+SHA)
print('FULL_PLAN_BYTE_COUNT='+str(len(raw)))
print('REDACTIONS=NONE; REFERENCED_SECRET_CONTENT=NOT_READ; INSTALL=NO; SERVICES_CHANGED=NO')
