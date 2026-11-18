"""Three-party handoff observation projection, never grants execution authority.

Identity and permission validation must be supplied by a trusted existing system.
Without a verifier even complete-looking receipts remain incomplete.
"""
from datetime import datetime, timezone
import re
from .core import LedgerError, ident, canonical, digest, parse_time

SNAPSHOT_FIELDS=('goal_acceptance_ref','instruction_ref','repo_ref','branch','commit','tree','dirty_ref',
                 'manifest_ref','artifact_sha256','build_ref','deploy_refs','running_ref','runtime_source_ref','entry_ref',
                 'host_ref','verified_session_ref','permission_boundary','permission_evidence_ref','scope','expires_at','denial',
                 'writer_role_id','lease_ref','fence_ref','pending_operations','unresolved_effects','next_action')
CONTINUATION_FIELDS=('installed_version_ref','permission_request_ref','install_channel_ref',
                     'protected_config_ref','credential_ref','effects_receipt_ref','backup_ref',
                     'restore_ref','acceptance_entry_ref','acceptance_identity_ref',
                     'acceptance_actions_ref')
COMMON=('handoff_id','handoff_version','snapshot_digest','actor_ref','role_id',
        'session_ref','identity_evidence_ref','permission_evidence_ref','permission_expires_at')
UNKNOWN={'UNKNOWN','STALE','UNAVAILABLE','DENIED','NONE',''}

def known(value):
    if isinstance(value,str): return bool(value.strip()) and value not in UNKNOWN
    if isinstance(value,list): return bool(value) and all(isinstance(x,str) and known(x) for x in value)
    return False

def validate_handoff(e):
    d=e['data']
    if any(k not in d for k in COMMON): raise LedgerError('missing handoff field')
    ident(d['handoff_id'])
    if not isinstance(d['handoff_version'],int) or isinstance(d['handoff_version'],bool) or d['handoff_version']<1: raise LedgerError('invalid handoff version')
    if not isinstance(d['snapshot_digest'],str) or len(d['snapshot_digest'])!=64 or any(c not in '0123456789abcdef' for c in d['snapshot_digest']): raise LedgerError('invalid digest')
    for k in ('actor_ref','role_id','session_ref','identity_evidence_ref','permission_evidence_ref'): ident(d[k])
    if d['permission_expires_at'] not in UNKNOWN: parse_time(d['permission_expires_at'])
    if e['type']=='handoff_propose':
        if any(k not in d for k in ('snapshot_data','scope_included','scope_excluded','scope_authorization_ref')): raise LedgerError('missing snapshot')
        snap=d['snapshot_data']; included=d['scope_included']; excluded=d['scope_excluded']
        if not isinstance(snap,dict) or set(snap) not in (set(SNAPSHOT_FIELDS),set(SNAPSHOT_FIELDS+CONTINUATION_FIELDS)): raise LedgerError('incomplete snapshot structure')
        if not isinstance(included,list) or not isinstance(excluded,list) or not included or set(included)&set(excluded) or set(included)|set(excluded)!=set(snap) or len(set(included))!=len(included) or len(set(excluded))!=len(excluded): raise LedgerError('invalid handoff scope')
        if digest(canonical(snap))!=d['snapshot_digest']: raise LedgerError('snapshot digest mismatch')
    else:
        ident(d.get('proposal_event_id'))
    if e['type'] in ('handoff_aligned','handoff_gap','handoff_verified','handoff_rejected','handoff_incomplete'):
        if not isinstance(d.get('actual_checks'),list) or not isinstance(d.get('unknown_items'),list): raise LedgerError('missing actual checks')
    if e['type'] in ('handoff_aligned','handoff_gap'): ident(d.get('received_event_id'))
    if e['type'] in ('handoff_verified','handoff_rejected','handoff_incomplete'):
        ident(d.get('alignment_event_id')); ident(d.get('supervision_start_event_id'))

def _usable(e, verifier, now):
    d=e['data']
    if e['validity']!='VERIFIED_NOW' or not known(e['source']) or not known(e['evidence']): return False
    if not all(known(d.get(k)) for k in ('actor_ref','role_id','session_ref','identity_evidence_ref','permission_evidence_ref')): return False
    try:
        if parse_time(d['permission_expires_at'])<=now or parse_time(d['permission_expires_at'])<=parse_time(e['occurred_at']): return False
        return bool(verifier and verifier(e))
    except (ValueError, LedgerError, TypeError): return False

def project_handoffs(events, verifier=None, now=None):
    """Verifier(e) must verify identity, role, instance, scope, source and permission.
    No default verifier: user-supplied receipt text is not evidence of authority.
    """
    now=now or datetime.now(timezone.utc)
    groups={}
    for e in events:
        if e['type'].startswith('handoff_'):
            d=e['data']; groups.setdefault((e['task_id'],d['handoff_id']),[]).append(e)
    result={}
    for (task_id,hid), es in groups.items():
        proposals=[e for e in es if e['type']=='handoff_propose']
        if not proposals:
            result[task_id+':'+hid]={'task_id':task_id,'handoff_id':hid,'version':max(x['data']['handoff_version'] for x in es),'snapshot_digest':'UNKNOWN','handoff_status':'待交出','scope_included':[],'scope_excluded':[],'unknown_items':['proposal'],'version_conflict':False,'outgoing':'UNKNOWN','receiving':'UNKNOWN','supervisor':'UNAVAILABLE','summary':{'reason':'尚未收到交出快照'},'history':es}
            continue
        version=max(e['data']['handoff_version'] for e in proposals)
        ps=[e for e in proposals if e['data']['handoff_version']==version]
        p=ps[0]; d=p['data']; snap=d['snapshot_data']; inc=d['scope_included']; exc=d['scope_excluded']
        version_conflict=len(ps)!=1
        same=[e for e in es if e['attempt_id']==p['attempt_id'] and e['data']['handoff_version']==version and e['data']['snapshot_digest']==d['snapshot_digest'] and (e is p or e['data'].get('proposal_event_id')==p['event_id'])]
        # Resolve exact causal events, not latest conversational summaries.
        byid={e['event_id']:e for e in same}
        def last(kind):
            a=[e for e in same if e['type']==kind]; return a[-1] if a else None
        nom=last('handoff_nominate'); r=last('handoff_received'); a=last('handoff_aligned'); gap=last('handoff_gap'); start=last('handoff_supervision_start'); v=last('handoff_verified'); reject=last('handoff_rejected'); incomplete=last('handoff_incomplete')
        unknown=[k for k in inc if not known(snap[k]) or (k in ('deploy_refs','pending_operations') and not isinstance(snap[k],list)) or (k not in ('deploy_refs','pending_operations') and not isinstance(snap[k],str))]
        if exc and not known(d['scope_authorization_ref']): unknown.append('scope_authorization_ref')
        for x in (a,gap,v,reject,incomplete):
            if x: unknown.extend(x['data']['unknown_items'])
        unknown=list(dict.fromkeys(unknown))
        state='待接收核对'; outgoing=p['event_id']; receiving=r['event_id'] if r else 'UNKNOWN'; supervisor=start['event_id'] if start else 'UNAVAILABLE'
        if r: state='待独立核验' if a else '待接收核对'
        if gap or reject or incomplete or unknown or version_conflict: state='有缺项'
        chain=bool(nom and r and a and start and v and r['causation']==p['event_id'] and a['data']['received_event_id']==r['event_id'] and a['causation']==r['event_id'] and nom['causation']==p['event_id'] and nom['data'].get('target_ref')==start['data']['role_id'] and start['causation']==nom['event_id'] and v['causation']==start['event_id'] and v['data']['alignment_event_id']==a['event_id'] and v['data']['supervision_start_event_id']==start['event_id'])
        if chain:
            if verifier is None: unknown.append('identity_permission_verifier_UNAVAILABLE')
            party=[p,r,start]; verdicts=[p,nom,r,a,start,v]
            identity_unique=all(len(set(x['data'][key] for x in party))==3 for key in ('actor_ref','session_ref','role_id'))
            same_nominator=all(nom['data'][key]==p['data'][key] for key in ('actor_ref','session_ref','role_id','identity_evidence_ref'))
            same_receiver=all(a['data'][key]==r['data'][key] for key in ('actor_ref','session_ref','role_id'))
            same_supervisor=all(v['data'][key]==start['data'][key] for key in ('actor_ref','session_ref','role_id'))
            checks=all(set(inc).issubset(set(x['data']['actual_checks'])) and not x['data']['unknown_items'] for x in (a,v))
            try:
                times_ok=(parse_time(p['occurred_at'])<=parse_time(r['occurred_at'])<=parse_time(a['occurred_at'])<=parse_time(v['occurred_at'])<=now and parse_time(p['occurred_at'])<=parse_time(nom['occurred_at'])<=parse_time(start['occurred_at'])<=parse_time(v['occurred_at']))
            except LedgerError: times_ok=False
            # Negative receipts supersede optimistic receipts for this version, even if arriving late.
            if not version_conflict and not (gap or reject or incomplete or unknown) and identity_unique and same_nominator and same_receiver and same_supervisor and checks and times_ok and all(_usable(x,verifier,now) for x in verdicts): state='交接完成(范围)'
            elif state!='有缺项': state='有缺项'
        key=task_id+':'+hid
        continuation={k:snap.get(k,'UNKNOWN') if k in inc else 'UNKNOWN' for k in CONTINUATION_FIELDS}
        continuation['snapshot_refs']={k:snap.get(k,'UNKNOWN') if k in inc else 'UNKNOWN' for k in SNAPSHOT_FIELDS}
        continuation['missing']=[k for k in CONTINUATION_FIELDS if not known(continuation[k])]
        continuation['status']='MISSING_REFERENCES' if continuation['missing'] else 'REFERENCES_UNVERIFIED'
        continuation['installed_version_check']='UNKNOWN'
        continuation['permission_expiry_revocation_check']='UNKNOWN'
        from task_delivery_backup_receipt import coverage_handoff_reference
        continuation['backup_observation']=coverage_handoff_reference(continuation['backup_ref'])
        continuation['instruction']='接手者须经原权限入口重新取得当次授权；先对账未决效果，勿继承令牌、租约或签据。版本、权限、恢复和验收须现场核实。'
        result[key]={'task_id':task_id,'handoff_id':hid,'version':version,'snapshot_digest':d['snapshot_digest'],'handoff_status':state,'scope_included':inc,'scope_excluded':exc,'unknown_items':unknown,'version_conflict':version_conflict,'outgoing':outgoing,'receiving':receiving,'supervisor':supervisor,'continuation':continuation,'summary':{'received_event_id':receiving,'alignment_event_id':a['event_id'] if a else 'UNKNOWN','supervision_start_event_id':supervisor,'verification_ref':v['event_id'] if v else 'UNKNOWN','reason':'接收事实不代表执行权；来源身份须独立验证'},'history':es}
    return result
