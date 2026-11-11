"""PID1 ExecStopPost safety guard; consumes only an existing exact LIVE attempt.

Never authorizes a new start, refresh, network change or credential read. The
historical permit is verified for STOP scope after its start expiry, not renewed.
Systemd BindsTo already stops worker when controller dies; this independently
confirms both dedicated UIDs stopped and quarantines exact temporary identities.
Uncertain stop/partial quarantine stays HOLD, no automatic third stop attempt.
"""
import json
import os
import stat
import sys

from gate_common import canonical_bytes,require
from korea.phase_c import artifact,lifecycle as live
from korea.phase_c.entry import load_config
from korea.phase_c.install_controller import WORK as INSTALL_WORK,UNITS,atomic_receipt
from korea.phase_c.security import (digest,fsync_dir,read_file,rename_new,strict_json,
                                    trusted_directory,write_once)


def finalize(ctx=None):
    ctx=ctx or live.Context();ctx.check_identity()
    work=ctx.path(live.WORK)
    if not os.path.lexists(work):return {'status':'NO_CONSUMED_ATTEMPT_NO_ACTION','service_started':False}
    trusted_directory(work,exact_mode=0o700)
    original=read_file(work/'receipt.json',modes=(0o600,))
    receipt=strict_json(original)
    if receipt.get('start_attempted') is not True:
        return {'status':'NO_START_ATTEMPT_NO_STOP_ACTION','service_started':False}
    config=load_config(ctx.path(live.CONFIG))
    release=ctx.path('/opt/xuanjun-binance-phase-c/releases/'+config['runtime_manifest_sha256'])
    ctx.verify_loaded(release,config['runtime_manifest_sha256'])
    plan_raw=read_file(work/'plan.json',modes=(0o600,));plan=strict_json(plan_raw)
    installed=strict_json(read_file(ctx.path(INSTALL_WORK)/'receipt.json',modes=(0o600,)))
    ctx.verify_installed(installed,config)
    pin=strict_json(read_file(work/'consumed-approval.json',modes=(0o600,),limit=110000))
    body=pin['approval_body'];b='<!-- '+live.MARKER+'\n';e='\n'+live.MARKER+' -->'
    require(body.count(b)==body.count(e)==1,'C_STOP_GUARD_MARKER')
    historical=strict_json(body.split(b)[1].split(e)[0])
    require(type(historical['issued_at']) is int,'C_STOP_GUARD_HISTORICAL_TIME')
    allowed=live.approval(pin,dict(source_commit=installed['source_commit'],
        runtime_manifest_sha256=config['runtime_manifest_sha256'],plan_sha256=digest(plan_raw),
        controller_sha256=digest(read_file(release/(artifact.PREFIX+'lifecycle.py'),modes=(0o444,),limit=1048576))),
        historical['issued_at']) # STOP-only validation of an already consumed permission.
    require(receipt['action']==live.ACTION and receipt['approval_comment_id']==allowed['approval_comment_id'] and
            plan['signed_admission']['admission']['approval_comment_id']==allowed['approval_comment_id'],
            'C_STOP_GUARD_ATTEMPT_BINDING')
    if receipt.get('temporary_quarantined') is True:
        require(all(row['MainPID']=='0' and row['ActiveState'] in ('inactive','failed') for row in ctx.states().values()),
                'C_STOP_GUARD_PRIOR_STOP_DRIFT')
        ctx.quiescent(config)
        return {'status':'PRIOR_STOP_AND_QUARANTINE_CONFIRMED_NO_EXTRA_ACTION','service_started':False}
    marker=work/'stop-guard-attempt.json'
    require(not os.path.lexists(marker),'C_STOP_GUARD_PREVIOUS_ATTEMPT_UNKNOWN_NO_RETRY')
    objects=strict_json(read_file(work/'temporary-identities.json',modes=(0o600,)))
    require(type(objects) is dict and set(objects)=={config['credential_generation'],config['broker_private_key']} and
            all(type(v) is list and len(v)==2 and all(type(n) is int and n>=0 for n in v) for v in objects.values()),
            'C_STOP_GUARD_TEMPORARY_IDENTITIES')
    write_once(marker,canonical_bytes({'approval_comment_id':allowed['approval_comment_id'],'stop_attempts':1}))
    result=dict(schema_version=1,status='STOPPING',service_started=False,writer_enabled=False,retry_allowed=False,
                approval_comment_id=allowed['approval_comment_id'],temporary_quarantined=False)
    try:
        atomic_receipt(work/'stop-guard-receipt.json',result)
        r=ctx.run(['/usr/bin/systemctl','stop',UNITS['worker.service'],UNITS['broker.service'],UNITS['network-verified.target']])
        require(r.returncode==0,'C_STOP_GUARD_STOP_UNKNOWN')
        require(all(row['MainPID']=='0' and row['ActiveState'] in ('inactive','failed') and
                    row['SubState'] in ('dead','failed') for row in ctx.states().values()),'C_STOP_GUARD_PROCESS_REMAINS')
        ctx.quiescent(config)
        require({n:list(v) for n,v in ctx.temporary_objects(config).items()}==objects,'C_STOP_GUARD_TEMPORARY_DRIFT')
        quarantine=ctx.path(live.QUARANTINE)
        trusted_directory(quarantine.parent,exact_mode=0o700)
        require(not os.path.lexists(quarantine),'C_STOP_GUARD_PARTIAL_QUARANTINE_PRESERVE')
        quarantine.mkdir(mode=0o700);os.chmod(quarantine,0o700);fsync_dir(quarantine.parent)
        require(all(ctx.path(n).lstat().st_dev==quarantine.stat().st_dev for n in objects),
                'C_STOP_GUARD_CROSS_FILESYSTEM')
        for index,name in enumerate(objects):rename_new(ctx.path(name),quarantine/('temporary-%d'%index))
        admission=ctx.path(config['admission_path'])
        if os.path.lexists(admission):
            require(read_file(admission,modes=(0o444,))==canonical_bytes(plan['signed_admission']),
                    'C_STOP_GUARD_ADMISSION_DRIFT')
            rename_new(admission,admission.with_name('.live-admission-guarded-'+str(allowed['approval_comment_id'])+'.json'))
        write_once(work/'receipt.before-stop-guard.json',original)
        receipt.update(status='HOLD_PRESERVE_EVIDENCE',phase='systemd_stop_guard',temporary_quarantined=True,
                       supervisor_loss_handled=True,lock_released=False)
        atomic_receipt(work/'receipt.json',receipt)
        live.publish_summary(ctx,receipt)
        result.update(status='STOP_GUARD_STOPPED_AND_QUARANTINED',temporary_quarantined=True,dedicated_uids_quiescent=True)
        atomic_receipt(work/'stop-guard-receipt.json',result)
        return result
    except BaseException as error:
        result.update(status='HOLD_PRESERVE_EVIDENCE',error_type=type(error).__name__)
        atomic_receipt(work/'stop-guard-receipt.json',result)
        raise


def main():
    os.umask(0o077)
    try:print(json.dumps(finalize(),sort_keys=True));return 0
    except BaseException as error:
        print(json.dumps({'status':'HOLD_PRESERVE_EVIDENCE','error_type':type(error).__name__,'retry_allowed':False}));return 2


if __name__=='__main__':sys.exit(main())
