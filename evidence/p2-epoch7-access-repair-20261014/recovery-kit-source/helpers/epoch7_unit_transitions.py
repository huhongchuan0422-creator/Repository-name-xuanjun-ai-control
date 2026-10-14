"""Finite cached-unit state acceptance after the owned exact target CAS.

The concrete observer supplies proof only from the bound gate's current targets,
its protected provisioning receipt and this attempt's successful command map.
This pure verifier does not authenticate caller-provided files or grant authority.
"""
import copy
import os.path

import epoch7_injected_recovery as retained
from epoch7_service_roles import _receipt

META=frozenset(('kind','sha256','uid','gid','mode','dev','ino','nlink','size','mtime_ns','ctime_ns'))
MUTABLE=frozenset(('LoadState','UnitFileState','NeedDaemonReload'))
REPLACED_CHECKPOINT=5
RELOADED_CHECKPOINT=15
ROOT='/etc/systemd/system/'
GATEWAY='xuanjun-uk-openclaw.service'


def need(value,label):
    if not value:raise ValueError('EPOCH7_UNIT_TRANSITION_'+label)


def affected_unit(path):
    need(type(path) is str and path.startswith(ROOT) and os.path.normpath(path)==path,'TARGET_PATH')
    tail=path[len(ROOT):]
    if '/' in tail:
        base,name=tail.split('/',1)
        need(base.endswith('.d') and '/' not in name and name.endswith('.conf') and name not in ('.conf','..conf'),'DROPIN_PATH')
        tail=base[:-2]
    need(tail.endswith(('.service','.socket','.timer')),'UNIT_SUFFIX')
    return tail


def validate_contract(value,static_fields,unit_set,hash_value):
    need(type(value) is dict and set(value) in ({'schema','targets','units'},
         {'schema','targets','units','gateway_restoration'}) and
         type(value['schema']) is int and value['schema']==1,'CONTRACT_SCHEMA')
    targets=value['targets'];units=value['units']
    need(type(targets) is dict and type(units) is dict and len(targets)<=32 and
         set(units)=={affected_unit(p) for p in targets} and set(units)<=unit_set,'EXACT_AFFECTED_UNITS')
    for path,row in targets.items():
        need(type(row) is dict and set(row)=={'sha256','uid','gid','mode'},'TARGET_PIN_SCHEMA')
        hash_value(row['sha256'])
        need(type(row['uid']) is int and row['uid']==0 and type(row['gid']) is int and row['gid']==0 and
             type(row['mode']) is int and row['mode'] in (0o644,0o600),'TARGET_AUTHORITY')
    for unit,row in units.items():
        need(type(row) is dict and set(row)=={'before','reloaded'},'UNIT_STATE_SCHEMA')
        for name,props in row.items():
            need(type(props) is dict and set(props)==static_fields and props['Id']==unit and
                 all(type(x) is str for x in props.values()) and props['ActiveState'] in ('inactive','failed') and
                 props['LoadState'] in ('loaded','masked') and props['NeedDaemonReload']=='no','STOPPED_STATE')
        need(all(row['before'][key]==row['reloaded'][key] for key in static_fields-MUTABLE),
             'ONLY_CACHE_PROPERTIES_DIFFER')
        need(row['reloaded']['LoadState']=='loaded' and
             row['reloaded']['UnitFileState'] in ('enabled','disabled','static'),'RELOADED_STATE')
    gateway=value.get('gateway_restoration')
    if gateway is not None:
        need(type(gateway) is dict and set(gateway)=={'path','sha256','uid','gid','mode',
             'legacy_receipt_sha256','boot_before','before'} and gateway['path']==ROOT+GATEWAY and
             type(gateway['uid']) is int and gateway['uid']==0 and type(gateway['gid']) is int and
             gateway['gid']==0 and type(gateway['mode']) is int and gateway['mode'] in (0o600,0o644) and
             gateway['boot_before'] in ('enabled','disabled'),'GATEWAY_RESTORE_CONTRACT')
        hash_value(gateway['sha256']);hash_value(gateway['legacy_receipt_sha256'])
        before=gateway['before']
        need(type(before) is dict and set(before)==static_fields and before['Id']==GATEWAY and
             before['LoadState']=='masked' and before['UnitFileState']=='masked' and
             before['ActiveState'] in ('inactive','failed') and before['NeedDaemonReload']=='no' and
             all(type(x) is str for x in before.values()),'GATEWAY_RESTORE_BASELINE')
    return copy.deepcopy(value)


def effective_policies(evidence,contract,checkpoint,index,context_sha,units,hash_value,allow_pending=False):
    """Check authenticated-observer proof and choose finite measured properties."""
    need(type(index) is int and 0<=index<=16,'CHECKPOINT_INDEX_REQUIRED')
    need(type(allow_pending) is bool,'PENDING_SCOPE_BOOLEAN')
    gateway=contract.get('gateway_restoration')
    if not contract['targets'] and gateway is None:
        need(evidence is None,'EMPTY_SCOPE_EVIDENCE');return checkpoint['units']
    if index<REPLACED_CHECKPOINT:
        need(evidence is None,'PREMATURE_TARGET_PROOF');return checkpoint['units']
    hash_value(context_sha)
    keys={'context_sha256','target_receipt','reload'}|({'gateway_restoration'} if gateway is not None else set())
    need(type(evidence) is dict and set(evidence)==keys and
         evidence['context_sha256']==context_sha,'CURRENT_CONTEXT_TARGET_PROOF')
    proof=evidence['target_receipt']
    if contract['targets']:
        need(type(proof) is dict and set(proof)=={'path','sha256','targets'} and
             proof['path']==retained.PROVISION,'EXACT_OWN_PROVISIONING_RECEIPT')
        hash_value(proof['sha256'])
        need(type(proof['targets']) is dict and set(proof['targets'])==set(contract['targets']),'EXACT_TARGET_PROOF_SET')
    else:need(proof is None,'EMPTY_TARGET_PROOF')
    for path,wanted in contract['targets'].items():
        actual=proof['targets'][path]
        need(type(actual) is dict and set(actual)==META and actual['kind']=='FILE' and
             actual['nlink']==1 and type(actual['nlink']) is int and
             all(type(actual[key]) is int and 0<=actual[key]<2**63 for key in META-{'kind','sha256'}) and
             actual['ino']>0 and actual['size']<=1048576 and all(actual[k]==v for k,v in wanted.items()),
             'EXACT_OWN_TARGET_CAS_METADATA')
    reload=evidence['reload']
    if reload is not None:
        need(index>=14,'PREMATURE_RELOAD_RECEIPT')
        _receipt(reload,context_sha,'daemon_reload')
    need(index<RELOADED_CHECKPOINT or reload is not None,'RELOAD_RECEIPT_REQUIRED')
    result=copy.deepcopy(checkpoint['units'])
    for unit,policy in contract['units'].items():
        if unit==GATEWAY and gateway is not None:continue
        actual=units[unit]['before'];old=policy['before'];new=policy['reloaded']
        expected=result[unit]['properties']
        if reload is None:
            need(actual['ActiveState'] in ('inactive','failed') and actual['MainPID']==0 and
                 actual['ControlPID']==0,'CACHED_UNIT_MUST_STAY_STOPPED')
            need(actual['LoadState'] in (old['LoadState'],new['LoadState']) and
                 actual['UnitFileState'] in (old['UnitFileState'],new['UnitFileState']) and
                 actual['NeedDaemonReload'] in ('yes','no'),'FINITE_CACHED_PROPERTIES')
        else:
            files={expected['UnitFileState']} if index>=RELOADED_CHECKPOINT else {new['UnitFileState']}
            if index==14 and new['UnitFileState'] in ('enabled','disabled'):files.add('enabled')
            need(actual['LoadState']==new['LoadState'] and actual['NeedDaemonReload']=='no' and
                 actual['UnitFileState'] in files,'EXACT_POST_RELOAD_PROPERTIES')
        # State/conditions remain checked by the selected phase's existing
        # inactive/active pair. Only cache fields get this explicit exception.
        for key in MUTABLE:result[unit]['properties'][key]=actual[key]
    if gateway is not None:
        restore=evidence['gateway_restoration'];actual=units[GATEWAY]['before']
        old=gateway['before'];expected=result[GATEWAY]['properties']
        if restore is None:
            need(index<15,'GATEWAY_RESTORE_RECEIPT_REQUIRED')
            need(all(actual[key]==old[key] for key in ('LoadState','UnitFileState')) and
                 actual['NeedDaemonReload'] in (('yes','no') if GATEWAY in contract['units'] else ('no',)),
                 'GATEWAY_NOT_OWN_RESTORED')
            need(actual['ActiveState'] in ('inactive','failed') and actual['MainPID']==actual['ControlPID']==0,
                 'GATEWAY_UNRESTORED_MUST_STOP')
        else:
            need(index>=14 and type(restore) is dict and set(restore)=={'context_sha256',
                 'legacy_receipt_sha256','observed_after','reload','persistence'} and
                 restore['context_sha256']==context_sha and
                 restore['legacy_receipt_sha256']==gateway['legacy_receipt_sha256'],'GATEWAY_OWN_RESTORE_CONTEXT')
            need(restore['persistence'] in ('PERSISTED','OWN_CAPTURE_PENDING_PUBLICATION') and
                 (allow_pending or restore['persistence']=='PERSISTED'),'GATEWAY_PERSISTED_RESTORE_REQUIRED')
            meta=restore['observed_after']
            need(type(meta) is dict and set(meta)==META and meta['kind']=='FILE' and
                 all(type(meta[key]) is int and 0<=meta[key]<2**63 for key in META-{'kind','sha256'}) and
                 meta['ino']>0 and meta['nlink']==1 and meta['size']<=65536 and
                 all(meta[key]==gateway[key] for key in ('sha256','uid','gid','mode')),'GATEWAY_EXACT_RESTORED_FILE')
            restored_reload=restore['reload']
            if restored_reload is None:
                need(index==14 and actual['ActiveState'] in ('inactive','failed') and
                     actual['MainPID']==actual['ControlPID']==0 and
                     actual['LoadState'] in ('masked','loaded') and
                     actual['UnitFileState'] in ('masked',gateway['boot_before']) and
                     actual['NeedDaemonReload'] in ('yes','no'),'GATEWAY_FINITE_PRE_RELOAD')
            else:
                _receipt(restored_reload,context_sha,'daemon_reload')
                if reload is not None:
                    need(restored_reload['sequence']<reload['sequence'],'RESTORE_BEFORE_RUNTIME_RELOAD')
                files={expected['UnitFileState']} if index>=15 else {gateway['boot_before'],'enabled'}
                need(actual['LoadState']=='loaded' and actual['UnitFileState'] in files and
                     actual['NeedDaemonReload']=='no','GATEWAY_EXACT_POST_RELOAD')
        for key in MUTABLE:result[GATEWAY]['properties'][key]=actual[key]
    return result
