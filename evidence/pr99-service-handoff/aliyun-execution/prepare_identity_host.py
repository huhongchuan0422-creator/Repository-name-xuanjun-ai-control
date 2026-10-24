"""Owner-authorized fixed domestic installation prerequisite, never activation.

Only possible mutation: native useradd for the absent dedicated xuanjun-s07
system identity. No user modification/removal, service mutation, database or
environment reads, data restore, route change, shell login or cloud credential.
"""
import datetime
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess

HOST='iZvt5t8tlrm8oiZ'
ACCOUNT='xuanjun-s07'
COMMAND=['/usr/sbin/useradd','--system','--no-create-home','--home-dir','/nonexistent',
         '--shell','/usr/sbin/nologin','--user-group',ACCOUNT]
PROTECTED=('provider-neutral-domestic-bridge.service','windows-interaction-http.service','nginx.service')
TARGETS=tuple('xuanjun-pr99-domestic-'+r+'.service' for r in ('portal','contact','customer-service'))
RELEASES=('/opt/xuanjun-migration-s07/releases/domestic-r2',
          '/opt/xuanjun-migration-s07/releases/domestic-r2/rootfs',
          '/opt/xuanjun-migration-s07/releases/domestic-final-v1',
          '/opt/xuanjun-migration-s07/releases/domestic-final-v1/rootfs')


def need(ok,code):
    if not ok:raise RuntimeError(code)


def identity(getuser,getgroup,users,groups):
    try:user=getuser(ACCOUNT)
    except KeyError:user=None
    try:group=getgroup(ACCOUNT)
    except KeyError:group=None
    if user is group is None:return None
    need(user is not None and group is not None,'DEDICATED_NAME_PARTIAL_CONFLICT')
    need(user.pw_name==group.gr_name==ACCOUNT and user.pw_uid not in (0,65534,1000,1001) and
         user.pw_gid==group.gr_gid and group.gr_gid not in (0,65534,1000,1001) and
         user.pw_shell in ('/usr/sbin/nologin','/sbin/nologin') and user.pw_dir=='/nonexistent' and not group.gr_mem,
         'DEDICATED_IDENTITY_CONFLICT')
    need(sum(u.pw_uid==user.pw_uid for u in users())==1 and
         not any(u.pw_gid==group.gr_gid and u.pw_name!=ACCOUNT for u in users()) and
         sum(g.gr_gid==group.gr_gid for g in groups())==1 and
         not any(g.gr_gid!=group.gr_gid and ACCOUNT in g.gr_mem for g in groups()),'DEDICATED_IDENTITY_ALIAS')
    return {'name':ACCOUNT,'uid':user.pw_uid,'gid':group.gr_gid,'login_shell_disabled':True,
            'home_created':False,'shared_primary_identity':False}


def prepare_identity(getuser=None,getgroup=None,users=None,groups=None,run=None):
    getuser=getuser or pwd.getpwnam;getgroup=getgroup or grp.getgrnam
    users=users or pwd.getpwall;groups=groups or grp.getgrall;run=run or subprocess.run
    before=identity(getuser,getgroup,users,groups)
    if before is not None:return {'created':False,'creation_attempted':False,**before}
    # Exactly one native call. On failure/timeout never retry or delete partial
    # account/group state. A later action may only query the original outcome.
    result=run(COMMAND,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,
               env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
    need(result.returncode==0,'USERADD_RESULT_UNKNOWN_PRESERVE_NO_RETRY')
    after=identity(getuser,getgroup,users,groups)
    need(after is not None,'USERADD_IDENTITY_NOT_OBSERVED')
    return {'created':True,'creation_attempted':True,**after}


def unit_states(names):
    result={}
    for name in names:
        args=['/usr/bin/systemctl','show',name,'--property=LoadState,ActiveState,SubState,MainPID','--no-pager']
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,
                         env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
        need(len(p.stdout)<=8192,'UNIT_STATE_BOUND')
        values=dict(l.split('=',1) for l in p.stdout.decode('utf-8','strict').splitlines() if '=' in l)
        need(set(values)=={'LoadState','ActiveState','SubState','MainPID'} and
             values['MainPID'].isdigit(),'UNIT_STATE_UNKNOWN')
        result[name]={**{k:values[k] for k in ('LoadState','ActiveState','SubState')},'MainPID':int(values['MainPID'])}
    return result


def metadata(path):
    p=Path(path)
    try:s=p.lstat()
    except FileNotFoundError:return {'path':path,'exists':False}
    need(not stat.S_ISLNK(s.st_mode),'RELEASE_LINK_NOT_ADOPTED')
    return {'path':path,'exists':True,'directory':stat.S_ISDIR(s.st_mode),'uid':s.st_uid,
            'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'device':s.st_dev,'inode':s.st_ino}


def prepare(expected,nonce):
    need(os.geteuid()==0 and os.uname().nodename==expected==HOST,'FIXED_DOMESTIC_ROOT')
    for path in ('/usr/sbin/useradd','/usr/sbin/nologin'):
        s=Path(path).stat()
        need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and s.st_mode&0o111,'FIXED_NATIVE_TOOL_IDENTITY')
    before=unit_states(PROTECTED)
    releases=[metadata(p) for p in RELEASES]
    target_states=unit_states(TARGETS)
    account=prepare_identity()
    after=unit_states(PROTECTED)
    return {'scope':'PR99_OWNER_DOMESTIC_IDENTITY_PREPARATION_ONLY','hostname':HOST,'nonce':nonce,
            'observed_at':datetime.datetime.utcnow().isoformat()+'Z','identity':account,
            'protected_before':before,'protected_after':after,'protected_state_unchanged':before==after,
            'target_units':target_states,'releases':releases,'service_actions':0,'database_opened':False,
            'route_changed':False,'migration_started':False,'production_started':False}


if __name__=='__main__':
    try:print(json.dumps(prepare(EXPECTED,NONCE),sort_keys=True),flush=True)
    except BaseException as error:
        code=str(error)
        import re
        print(json.dumps({'status':'PREPARATION_HOLD','error_type':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,160}',code) else 'PRIVATE_DETAIL_WITHHELD',
          'retry_allowed':False}),flush=True)
        raise SystemExit(2)
