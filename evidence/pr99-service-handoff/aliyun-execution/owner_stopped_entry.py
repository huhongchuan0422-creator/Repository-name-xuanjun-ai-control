"""Normal Owner-direct entry for the published stopped/quarantine installer.

Owner removed the independent-review/permit wait. This explicit entry uses the
same original STATE, lock, unit bytes, copied acceptance and rollback ownership.
It never invents an independent approval or touches the restricted M99 repair.
Only install-stopped is supported; no start, enable, data or route operations.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def fixed_systemctl(*args):
    need(args==('daemon-reload',) or (len(args)==4 and args[0]=='show' and
         args[1] in ('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service',
         'xuanjun-wecom-customer-service.service','provider-neutral-domestic-bridge.service',
         'winctl.service','windows-interaction-http.service','nginx.service',
         'xuanjun-pr99-domestic-portal.service','xuanjun-pr99-domestic-contact.service',
         'xuanjun-pr99-domestic-customer-service.service') and args[2] in
         ('--property=LoadState,ActiveState,SubState,MainPID,FragmentPath','--property=ActiveState,MainPID') and
         args[3]=='--no-pager'),'FIXED_SERVICE_OPERATION')
    p=subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,timeout=20,
                     env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
    need(len(p.stdout)<=8192,'UNIT_OUTPUT_BOUND')
    value=p.stdout.decode('utf-8','strict')
    if args==('daemon-reload',):need(p.returncode==0,'DAEMON_RELOAD_FAILED_PRESERVE')
    else:
        fields=dict(line.split('=',1) for line in value.splitlines() if '=' in line)
        expected=set(args[2].split('=',1)[1].split(','))
        need(set(fields)==expected and fields.get('MainPID','').isdigit(),'UNIT_STATE_UNKNOWN')
        # systemctl show returns 1 for a missing unit; accept only its complete,
        # inactive zero-PID result. All other native failures remain failures.
        need(p.returncode==0 or (p.returncode==1 and fields.get('ActiveState')=='inactive' and
             fields.get('MainPID')=='0' and fields.get('LoadState','not-found')=='not-found'),
             'SYSTEMCTL_SHOW_FAILED')
    return value


def need(ok,code):
    if not ok:raise RuntimeError(code)


def frozen_library():
    raw=FROZEN_SOURCE.encode()
    need(hashlib.sha256(raw).hexdigest()=='99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315','PUBLISHED_INSTALLER_SOURCE_DRIFT')
    ns={'__name__':'published_stopped_functions','__file__':'<hash-pinned-published-stopped-functions>'}
    exec(compile(raw,'published_stopped_functions','exec'),ns)
    # Correct the protected Windows unit name using already verified live data.
    ns['PROTECTED']=tuple(sorted(set(ns['PROTECTED'])|{'windows-interaction-http.service'}))
    ns['systemctl']=fixed_systemctl
    return ns


def owner_install(ns,nonce):
    state=Path(ns['STATE']);units=Path('/etc/systemd/system')
    # No new transaction root or Writer: reuse the original exact state/lock.
    # An earlier partial/unknown attempt is preserved and cannot be replayed.
    for p in reversed(state.parents):
        s=p.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'ORIGINAL_STATE_PARENT')
    exists=os.path.lexists(state)
    if exists:
        s=state.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'ORIGINAL_STATE_IDENTITY')
        need((state/'receipt.json').is_file() and not (state/'receipt.json').is_symlink(),'ORIGINAL_INSTALL_STATE_PENDING_NO_REPLAY')
        lock=os.open(state/'lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    else:
        # All read-only eligibility checks precede creating the original claim.
        before=ns['snapshot']()
        need(all('LoadState=not-found' in before[u] for u in ns['ORIGINAL']),'ORIGINAL_UNIT_PRESENT')
        need(all(not os.path.lexists(units/u) and ns['stopped'](u) for u in ns['NAMES']),'TARGET_UNIT_PRESENT_OR_RUNNING')
        receipt=json.loads(ns['read_regular'](Path(ns['RELEASE'])/'callback-restart-acceptance-v1/receipt.json',private=True))
        need(receipt.get('status')=='R2_CALLBACK_REJECTION_RESTART_CLEANUP_PASS_NOT_PRODUCTION' and
             receipt.get('application_processes_stopped') is True,'COPY_ACCEPTANCE_MISSING')
        state.mkdir(mode=0o700)
        lock=os.open(state/'lock',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        s=os.fstat(lock);need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'ORIGINAL_LOCK_IDENTITY')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not exists:
            # This records Owner authorization, not a fabricated reviewer permit.
            owner={'mode':'OWNER_DIRECT','owner_instruction':'2026-10-19T00:29:13+08:00',
              'action':'INSTALL_STOPPED_QUARANTINE_ONLY','invocation_nonce':nonce,
              'published_installer_sha256':hashlib.sha256(FROZEN_SOURCE.encode()).hexdigest(),
              'manifest':ns['manifest']()}
            ns['write_exclusive'](state/'owner-direct.authorization.json',ns['encode'](owner))
            ns['install'](units,state,{'nonce':nonce},ns['digest'](ns['encode'](owner)))
        saved=json.loads(ns['read_regular'](state/'receipt.json',private=True))
        need(saved.get('status')=='QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION' and
             saved.get('manifest')==ns['manifest']() and saved.get('starts')==0 and saved.get('enables')==0,
             'ORIGINAL_INSTALL_RECEIPT_BINDING')
        for name,data in ns['unit_bytes']().items():
            need(ns['read_regular'](units/name)==data and ns['stopped'](name),'INSTALLED_UNIT_DRIFT_OR_RUNNING')
            marker=json.loads(ns['read_regular'](state/(name+'.created'),private=True))
            need(marker.get('sha256')==ns['digest'](data),'INSTALLED_UNIT_ORIGINAL_OWNERSHIP')
        return {'status':'QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION','installed_units':len(ns['NAMES']),
                'created_this_invocation':not exists,'original_state_reused':True,
                'starts':0,'enables':0,'data_restored':False,'route_changed':False,
                'unit_sha256':{n:ns['digest'](b) for n,b in ns['unit_bytes']().items()}}
    finally:os.close(lock)


def observe(expected,nonce):
    need(os.geteuid()==0 and os.uname().nodename==expected=='iZvt5t8tlrm8oiZ','FIXED_DOMESTIC_ROOT')
    ns=frozen_library();before=ns['snapshot']()
    result=owner_install(ns,nonce)
    after=ns['snapshot']()
    need(before==after,'PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')
    return {'scope':'PR99_OWNER_ORIGINAL_STOPPED_INSTALL_ONLY','hostname':expected,'nonce':nonce,
            'observed_at':datetime.datetime.utcnow().isoformat()+'Z','installation':result,
            'protected_state_unchanged':True,'production_started':False,'migration_complete':False}


if __name__=='__main__':
    try:print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
    except BaseException as error:
        import re
        code=str(error)
        print(json.dumps({'status':'OWNER_STOPPED_INSTALL_HOLD','error_type':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,160}',code) else 'PRIVATE_DETAIL_WITHHELD','retry_allowed':False}),flush=True)
        raise SystemExit(2)
