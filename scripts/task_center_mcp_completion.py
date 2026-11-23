"""Opt-in lifecycle tools over original ModelControl, never model-text execution.

Existing host-run checklists are consumed, not created via MCP. Development
contracts must use their controlled signed review/execution path instead.
"""
import json
import re
import hashlib
import math
import os
from task_writer_fence import Fence
from reusable_task_gateway import TestOnlyExecutor

ACTIONS={'task_submit_candidate':'EXECUTOR','task_review_candidate':'REVIEWER',
         'task_accept_candidate':'ACCEPTOR','task_candidate_status':None}
WRITE_TOOLS=frozenset(set(ACTIONS)-{'task_candidate_status'})
FIELDS={'task_submit_candidate':('artifact_sha256','checklist_sha256'),
        'task_review_candidate':('candidate_id','findings','passed'),
        'task_accept_candidate':('candidate_id',),
        'task_candidate_status':('candidate_id',)}

def tools():
    result=[]
    for name,extra in FIELDS.items():
        props={k:{'type':'string','minLength':1,'maxLength':128} for k in ('task_id','attempt_id')+extra}
        if name=='task_review_candidate':
            props['passed']={'type':'boolean'}
            props['findings']={'type':'array','maxItems':32,'items':{'type':'object'}}
        result.append({'name':name,'description':'Existing host-authorized candidate lifecycle; no model call, no code execution, no task creation.',
          'inputSchema':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}})
    return result

class CandidateAcceptanceEvidence:
    """Recheck original host-produced handoff, backup and bundle evidence."""
    def __init__(self,control,host,backup_assessor=None):
        self.control=control;self.host=host;self.backup_assessor=backup_assessor

    def check(self,binding,prepare_only=False):
        from task_center_handoff_host import HandoffHost, ID
        from task_center_role_contract import RoleContractResolver
        c=self.control;db=c.db;host=self.host
        if not prepare_only and not db.in_transaction:raise ValueError('CANDIDATE_EVIDENCE_TRANSACTION_REQUIRED')
        if prepare_only and db.in_transaction:raise ValueError('CANDIDATE_PREFLIGHT_TRANSACTION_FORBIDDEN')
        if type(host) is not HandoffHost or host.tenant_id!=c.tenant_id or type(host.role_contract) is not RoleContractResolver:
            raise ValueError('CANDIDATE_TRUSTED_HOST_REQUIRED')
        databases=[r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main']
        if host.db_path is None or len(databases)!=1 or not databases[0] or os.path.realpath(databases[0])!=host.db_path:
            raise ValueError('CANDIDATE_TRUSTED_HOST_REQUIRED')
        row=db.execute("SELECT * FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?",(c.tenant_id,binding['candidate_id'])).fetchone()
        if row is None or (row['task_id'],row['attempt_id'])!=(binding['task_id'],binding['attempt_id']):
            raise ValueError('EXACT_HOST_CANDIDATE_REQUIRED')
        snapshot=c._require_candidate_snapshot(row)
        snapshot_row=db.execute("SELECT snapshot_json FROM candidate_snapshots WHERE tenant_id=? AND candidate_id=?",(c.tenant_id,row['candidate_id'])).fetchone()
        if snapshot_row is None or hashlib.sha256(snapshot_row['snapshot_json'].encode('utf-8')).hexdigest()!=snapshot:
            raise ValueError('CANDIDATE_SNAPSHOT_DIGEST_REQUIRED')
        c._require_candidate_review_receipts(row)
        task=c.gateway.supervisor._task(row['task_id'])
        if db.execute("SELECT 1 FROM writer_operations WHERE task_id=? AND state IN ('PREPARED','DISPATCHING','UNKNOWN') LIMIT 1",(row['task_id'],)).fetchone():
            raise ValueError('UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED')
        actors=db.execute('''SELECT a.role_id,a.role_version,a.provider_id FROM model_assignments a
          JOIN role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
          WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.principal_id=?
          AND a.state='ASSIGNED' AND r.enabled=1 AND r.phase='EXECUTOR' ''',
          (c.tenant_id,row['task_id'],row['attempt_id'],row['submitted_by'])).fetchall()
        if len(actors)!=1:raise ValueError('CANDIDATE_EXECUTOR_CONTRACT_REQUIRED')
        actor=actors[0]
        resolver=RoleContractResolver(db,host.role_contract.contracts,host.role_contract.intake_plans)
        contract=resolver.resolve_planned(c.tenant_id,row['task_id'],row['attempt_id'],actor['role_id'],actor['role_version'],actor['provider_id'])
        acceptor=db.execute('''SELECT role_id,role_version,provider_id,state FROM model_assignments
          WHERE tenant_id=? AND task_id=? AND attempt_id=? AND role_id=? AND principal_id=?''',
          (c.tenant_id,row['task_id'],row['attempt_id'],binding['role_id'],binding['principal_id'])).fetchone()
        if acceptor is None or acceptor['state']!='ASSIGNED' or acceptor['role_version']!=binding['role_version']:
            raise ValueError('CANDIDATE_ACCEPTOR_CONTRACT_REQUIRED')
        acceptor_contract=resolver.resolve_planned(c.tenant_id,row['task_id'],row['attempt_id'],
          acceptor['role_id'],acceptor['role_version'],acceptor['provider_id'])
        request={'tenant_id':c.tenant_id,'project_id':binding['project_id'],'task_id':row['task_id'],
          'attempt_id':row['attempt_id'],'candidate_id':row['candidate_id'],'artifact_sha256':row['artifact_sha256'],
          'snapshot_sha256':snapshot,'provider_ref':actor['provider_id'],'contract_id':contract['contract_id'],
          'contract_version':contract['contract_version'],'contract_sha256':contract['contract_sha256']}
        try:bundle=host.assess_candidate_bundle(dict(request))
        except Exception:bundle=None
        common={'candidate_id','artifact_sha256','snapshot_sha256','read_location_ref'}
        if (not isinstance(bundle,dict) or set(bundle) not in (common|{'handoff_event_id'},common|{'handoff_event_ids'}) or
          any(bundle.get(k)!=request[k] for k in ('candidate_id','artifact_sha256','snapshot_sha256')) or
          not isinstance(bundle.get('read_location_ref'),str) or ID.fullmatch(bundle['read_location_ref']) is None):
            raise ValueError('CANDIDATE_BUNDLE_READBACK_REQUIRED')
        event_ids=([bundle['handoff_event_id']] if 'handoff_event_id' in bundle else bundle['handoff_event_ids'])
        if not isinstance(event_ids,list) or not event_ids or any(not isinstance(x,str) or ID.fullmatch(x) is None for x in event_ids):
            raise ValueError('CANDIDATE_BUNDLE_READBACK_REQUIRED')
        def phase(event_id,kind):
            if not isinstance(event_id,str) or ID.fullmatch(event_id) is None:
                raise ValueError('CANDIDATE_HANDOFF_RECEIPTS_REQUIRED')
            event=db.execute("SELECT kind,evidence_ref,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?",(row['task_id'],row['attempt_id'],'handoff-host:'+event_id)).fetchone()
            marker=db.execute("SELECT evidence_ref,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='HANDOFF_CONTRACT_BOUND'",(row['task_id'],row['attempt_id'],'handoff-contract:'+event_id)).fetchone()
            reference=db.execute("SELECT evidence_ref,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='HANDOFF_REFERENCE_ISSUED'",(row['task_id'],row['attempt_id'],'handoff-reference:'+event_id)).fetchone()
            if event is None or marker is None or reference is None or event['kind']!='AUTHENTICATED_HANDOFF_'+kind or event['evidence_ref']!='HOST_AUTHENTICATED' or marker['evidence_ref']!='HOST_AUTHENTICATED' or reference['evidence_ref']!='HOST_GENERATED':
                raise ValueError('CANDIDATE_HANDOFF_RECEIPTS_REQUIRED')
            try:payload=json.loads(event['payload_json']);bound=json.loads(marker['payload_json']);ref=json.loads(reference['payload_json'])
            except (TypeError,ValueError):raise ValueError('CANDIDATE_HANDOFF_RECEIPTS_REQUIRED')
            if not all(isinstance(x,dict) for x in (payload,bound,ref)):
                raise ValueError('CANDIDATE_HANDOFF_RECEIPTS_REQUIRED')
            fields=('tenant_id','task_id','attempt_id','handoff_id','handoff_version','backup_cycle_id','snapshot_digest','backup_manifest_sha256','provider_ref','contract_id','contract_version','contract_sha256')
            if (payload.get('issuer')!=host.issuer or bound.get('issuer')!=host.issuer or bound.get('event_id')!=event_id or
                payload.get('event_id')!=event_id or payload.get('action')!=kind or
                payload.get('scope')!='handoff:'+kind or
                any(not isinstance(payload.get(k),str) or ID.fullmatch(payload[k]) is None for k in ('handoff_id','backup_cycle_id','principal_id','session_id','role_id','provider_ref','contract_id')) or
                type(payload.get('handoff_version')) is not int or payload['handoff_version']<1 or
                any(not isinstance(payload.get(k),str) or re.fullmatch('[0-9a-f]{64}',payload[k]) is None for k in ('snapshot_digest','backup_manifest_sha256','contract_sha256')) or
                any(payload.get(k)!=bound.get(k) for k in fields) or
                any(ref.get(k)!=payload.get(k) for k in ('tenant_id','task_id','attempt_id','event_id','handoff_id','handoff_version','backup_cycle_id','fence','epoch','issuer','principal_id','session_id','role_id'))):
                raise ValueError('CANDIDATE_HANDOFF_RECEIPTS_REQUIRED')
            return payload
        def check_cycle(event_id):
            verified=phase(event_id,'VERIFIED')
            start=phase(verified.get('causation'),'SUPERVISION_START')
            nomination=phase(start.get('causation'),'NOMINATE')
            proposal=phase(nomination.get('causation'),'PROPOSE')
            aligned=phase(verified.get('alignment_ref'),'ALIGNED')
            received=phase(aligned.get('causation'),'RECEIVE')
            shared=('tenant_id','task_id','attempt_id','handoff_id','handoff_version','backup_cycle_id',
              'snapshot_digest','backup_manifest_sha256','backup_cycle_at','backup_state','provider_ref',
              'fence','epoch','contract_id','contract_version','contract_sha256','checked')
            if (proposal.get('causation')!='NONE' or received.get('causation')!=proposal.get('event_id') or nomination.get('target_ref')!=start.get('role_id') or
                any(any(p.get(k)!=verified.get(k) for k in shared) for p in (start,nomination,proposal,aligned,received)) or
                any(len({proposal.get(k),received.get(k),start.get(k)})!=3 for k in ('principal_id','session_id','role_id')) or
                any(proposal.get(k)!=nomination.get(k) or received.get(k)!=aligned.get(k) or start.get(k)!=verified.get(k)
                    for k in ('principal_id','session_id','role_id')) or
                verified.get('tenant_id')!=c.tenant_id or verified.get('task_id')!=row['task_id'] or
                verified.get('attempt_id')!=row['attempt_id'] or verified.get('snapshot_digest')!=snapshot or
                verified.get('provider_ref')!=actor['provider_id'] or verified.get('fence')!=task['fence'] or verified.get('epoch')!=task['epoch'] or
                verified.get('backup_state')!='COMPLETE' or verified.get('checked')!=contract['required_checks'] or
                any(verified.get(k)!=contract[k] for k in ('contract_id','contract_version','contract_sha256'))):
                raise ValueError('CANDIDATE_HANDOFF_RECEIPTS_REQUIRED')
            backup_binding={k:verified.get(k) for k in ('task_id','attempt_id','handoff_id','handoff_version','snapshot_digest','backup_cycle_id','backup_manifest_sha256','provider_ref','checked','contract_id','contract_version','contract_sha256')}
            backup_binding['applicability']={k:contract[k] for k in ('role_id','role_version','role_scope','required_categories','not_applicable','required_checks')}
            if prepare_only:return {'verified':verified,'backup_binding':backup_binding}
            try:
                backup=self.backup_assessor(backup_binding) if self.backup_assessor is not None else None
                if self.backup_assessor is not None:
                    resolver=getattr(getattr(self.backup_assessor,'component',None),'host',None)
                    if resolver is not None:
                        from task_center_backup_v1_migration import _ConfigRecheckedContract
                        if type(resolver) is _ConfigRecheckedContract:resolver.assert_current()
            except Exception:backup=None
            now=c.clock()
            if (not isinstance(backup,dict) or set(backup)!={'state','missing','cycle_at'} or backup['state']!='COMPLETE' or
                backup['missing']!=[] or type(backup['cycle_at']) not in (int,float) or not math.isfinite(backup['cycle_at']) or
                backup['cycle_at']!=verified.get('backup_cycle_at') or backup['cycle_at']>now or now-backup['cycle_at']>300):
                raise ValueError('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        # Each candidate is independently validated by the original causal,
        # contract and current host backup checks. IDs merely provide stable
        # iteration; no timestamp or recency is treated as authority.
        error=None
        for event_id in sorted(set(event_ids)):
            try:
                prepared=check_cycle(event_id)
                break
            except ValueError as exc:
                error=exc
        else:
            raise error
        if prepare_only:return prepared
        return {'task_id':row['task_id'],'attempt_id':row['attempt_id'],'candidate_id':row['candidate_id'],
          'artifact_sha256':row['artifact_sha256'],'snapshot_sha256':snapshot,
          'read_location_ref_sha256':hashlib.sha256(bundle['read_location_ref'].encode()).hexdigest(),
          'handoff_event_id':event_id,'contract_sha256':contract['contract_sha256'],
          'acceptor_contract_sha256':acceptor_contract['contract_sha256']}

class CandidateLifecycleMCP:
    def __init__(self,control,binding,lock_dir,acceptance_host=None,enforce_acceptance=False):
        self.control=control;self.binding=dict(binding);self.lock_dir=lock_dir
        self.acceptance_host=acceptance_host;self.enforce_acceptance=enforce_acceptance
        self.supervisor=control.gateway.supervisor
        self._backup_attempted=False;self._backup_assessor=None
    def _evidence_bound(self,row,actor):
        c=self.control
        audits=c.db.execute("SELECT detail_json FROM model_audit WHERE tenant_id=? AND principal_id=? AND action='CANDIDATE_EVIDENCE_BOUND' AND target_id=?",(c.tenant_id,actor,row['candidate_id'])).fetchall()
        if len(audits)!=1:return False
        try:
            detail=json.loads(audits[0]['detail_json'])
            snapshot=c._require_candidate_snapshot(row)
            snapshot_row=c.db.execute("SELECT snapshot_json FROM candidate_snapshots WHERE tenant_id=? AND candidate_id=?",(c.tenant_id,row['candidate_id'])).fetchone()
            if snapshot_row is None or hashlib.sha256(snapshot_row['snapshot_json'].encode('utf-8')).hexdigest()!=snapshot:return False
            fields={'task_id','attempt_id','candidate_id','artifact_sha256','snapshot_sha256',
                    'read_location_ref_sha256','handoff_event_id','contract_sha256','acceptor_contract_sha256'}
            if not isinstance(detail,dict) or set(detail)!=fields:return False
            if any(detail[k]!=row[k] for k in ('task_id','attempt_id','candidate_id','artifact_sha256')) or detail['snapshot_sha256']!=snapshot:return False
            if any(not isinstance(detail[k],str) or re.fullmatch('[0-9a-f]{64}',detail[k]) is None for k in ('read_location_ref_sha256','contract_sha256','acceptor_contract_sha256')):return False
            if not isinstance(detail['handoff_event_id'],str) or not detail['handoff_event_id']:return False
            from task_center_handoff_host import HandoffHost
            from task_center_role_contract import RoleContractResolver
            host=self.acceptance_host
            if type(host) is not HandoffHost or host.tenant_id!=c.tenant_id or type(host.role_contract) is not RoleContractResolver:return False
            databases=[r[2] for r in c.db.execute('PRAGMA database_list') if r[1]=='main']
            if host.db_path is None or len(databases)!=1 or not databases[0] or os.path.realpath(databases[0])!=host.db_path:return False
            resolver=RoleContractResolver(c.db,host.role_contract.contracts,host.role_contract.intake_plans)
            def role_contract(principal,phase):
                roles=c.db.execute('''SELECT a.role_id,a.role_version,a.provider_id FROM model_assignments a JOIN role_templates r
                  ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
                  WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.principal_id=?
                    AND a.state='ASSIGNED' AND r.phase=? AND r.enabled=1''',
                  (c.tenant_id,row['task_id'],row['attempt_id'],principal,phase)).fetchall()
                if len(roles)!=1:raise ValueError('TASK_CONTRACT_UNKNOWN')
                a=roles[0]
                return resolver.resolve_planned(c.tenant_id,row['task_id'],row['attempt_id'],a['role_id'],a['role_version'],a['provider_id'])['contract_sha256']
            if role_contract(row['submitted_by'],'EXECUTOR')!=detail['contract_sha256'] or role_contract(actor,'ACCEPTOR')!=detail['acceptor_contract_sha256']:return False
            return c.db.execute("SELECT 1 FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='AUTHENTICATED_HANDOFF_VERIFIED'",(row['task_id'],row['attempt_id'],'handoff-host:'+detail['handoff_event_id'])).fetchone() is not None
        except (ValueError,TypeError,KeyError):return False

    def call(self,name,args):
        if name not in ACTIONS or name not in self.binding['actions']:
            raise ValueError('HOST_LIFECYCLE_ACTION_REQUIRED')
        if not isinstance(args,dict) or set(args)!=set(('task_id','attempt_id')+FIELDS[name]):
            raise ValueError('EXACT_LIFECYCLE_ARGUMENTS_REQUIRED')
        for k,v in args.items():
            if k in ('findings','passed'):continue
            if not isinstance(v,str) or not 0<len(v)<=128 or any(ord(c)<33 or ord(c)>126 for c in v):
                raise ValueError('BOUNDED_LIFECYCLE_ID_REQUIRED')
            if k.endswith('sha256') or k=='candidate_id':
                if re.fullmatch('[0-9a-f]{64}',v) is None:raise ValueError('EXACT_LIFECYCLE_SHA_REQUIRED')
        if name=='task_review_candidate' and (type(args['passed']) is not bool or
                not isinstance(args['findings'],list) or len(args['findings'])>32 or
                any(not isinstance(x,dict) for x in args['findings']) or
                len(json.dumps(args['findings']).encode())>8192):
            raise ValueError('BOUNDED_REVIEW_DECISION_REQUIRED')
        b={k:self.binding[k] for k in ('project_id','principal_id','role_id','role_version','phase','review_kind')}
        b.update(task_id=args['task_id'],attempt_id=args['attempt_id'])
        if 'candidate_id' in args:b['candidate_id']=args['candidate_id']
        if ACTIONS[name] and ACTIONS[name]!=b['phase']:raise ValueError('HOST_LIFECYCLE_PHASE_REQUIRED')
        c=self.control;actor=b['principal_id']
        if name=='task_accept_candidate' and self.enforce_acceptance and not self._backup_attempted:
            return self._accept_with_prepared_backup(name,args,b)
        if name=='task_submit_candidate':
            return c.submit_candidate(args['task_id'],args['artifact_sha256'],args['checklist_sha256'],actor,_host_binding=b)
        if name=='task_review_candidate':
            return c.review_candidate(args['candidate_id'],actor,args['findings'],args['passed'],b['review_kind'],_host_binding=b)
        if name=='task_candidate_status':
            c.db.execute('BEGIN')
            try:
                task=c.assert_host_lifecycle(b)
                row=c.db.execute('SELECT * FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?',
                    (c.tenant_id,args['candidate_id'])).fetchone()
                released=False
                if task['state']=='SUCCESS' and task['authority_state']=='REVOKED':
                    try:c.require_host_resource_release(dict(task_id=args['task_id'],attempt_id=args['attempt_id']));released=True
                    except ValueError:pass
                audited=c.db.execute("SELECT 1 FROM model_audit WHERE tenant_id=? AND principal_id=? AND action='CANDIDATE_ACCEPTED' AND target_id=?",
                    (c.tenant_id,row['accepted_by'],args['candidate_id'])).fetchone() is not None
                evidence_bound=self._evidence_bound(row,row['accepted_by']) if row['state']=='ACCEPTED' and self.enforce_acceptance else False
                return {'candidate_id':args['candidate_id'],'candidate_state':row['state'],
                    'canonical_task_state':task['state'],'authority_state':task['authority_state'],
                    'artifact_sha256':row['artifact_sha256'],'checklist_sha256':row['checklist_sha256'],
                    'observation_only':True,'model_invoked':False,
                    'completion_state':('ACCEPTED' if row['state']=='ACCEPTED' and released and audited and (not self.enforce_acceptance or evidence_bound)
                        else 'HOLD_HANDOFF_EVIDENCE_RECONCILIATION' if row['state']=='ACCEPTED' and self.enforce_acceptance and not evidence_bound
                        else 'HOLD_REVOCATION_RECONCILIATION' if task['state']=='SUCCESS' and task['authority_state']!='REVOKED'
                        else 'HOLD_RESOURCE_RELEASE_RECONCILIATION' if task['state']=='SUCCESS' and not released
                        else 'HOLD_ACCEPTANCE_AUDIT_RECONCILIATION' if row['state']=='ACCEPTED' and not audited
                        else 'PENDING_ACCEPTANCE')}
            finally:c.db.rollback()
        # Repeat host/attempt/snapshot check at canonical terminal serialization,
        # not merely in this outer adapter. Original Fence owns drain/release.
        provider_id=[None]
        def admission():
            current=c.assert_host_lifecycle(b)
            if provider_id[0] is not None and current['authority_lock_provider_id']!=provider_id[0]:
                raise ValueError('EXISTING_WRITER_LOCK_PROVIDER_REQUIRED')
            candidate=c.validate_accept_candidate(args['candidate_id'],actor)
            if self.enforce_acceptance:CandidateAcceptanceEvidence(c,self.acceptance_host,self._backup_assessor).check(b)
            return candidate
        c.db.execute('BEGIN IMMEDIATE')
        try:
            c.assert_host_lifecycle(b)
            row=c.db.execute('SELECT * FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?',
                (c.tenant_id,args['candidate_id'])).fetchone()
            if row['state']=='ACCEPTED':
                c._require_candidate_snapshot(row);c._require_terminal_artifact(row);c.require_host_resource_release(row)
                if c.db.execute("SELECT 1 FROM model_audit WHERE tenant_id=? AND principal_id=? AND action='CANDIDATE_ACCEPTED' AND target_id=?",
                    (c.tenant_id,actor,args['candidate_id'])).fetchone() is None:
                    raise ValueError('HOLD_ACCEPTANCE_AUDIT_RECONCILIATION')
                if self.enforce_acceptance:
                    c._require_candidate_review_receipts(row)
                    if not self._evidence_bound(row,actor):
                        raise ValueError('CANDIDATE_EVIDENCE_RECONCILIATION_REQUIRED')
                task=self.supervisor._task(args['task_id'])
                if task['state']!='SUCCESS' or task['authority_state']!='REVOKED' or row['accepted_by']!=actor:
                    raise ValueError('EXACT_ACCEPTED_TERMINAL_REQUIRED')
                return {'candidate_id':args['candidate_id'],'state':'ACCEPTED','canonical_task_state':'SUCCESS','duplicate':True}
            candidate=admission()
            task=self.supervisor._task(args['task_id'])
        finally:c.db.rollback()
        if not (task['state']=='SUCCESS' and task['authority_state']=='REVOKED'):
            fence=Fence(self.supervisor,self.lock_dir)
            try:
                provider_id[0]=fence.locks.provider_id
                if task['authority_lock_provider_id']!=provider_id[0]:
                    raise ValueError('EXISTING_WRITER_LOCK_PROVIDER_REQUIRED')
                TestOnlyExecutor(c.gateway,fence,c.context).complete_success(
                    args['task_id'],args['attempt_id'],candidate['artifact_sha256'],
                    json.loads(task['completion_json']),terminal_admission_check=admission)
            finally:fence.close()
        accept_check=(lambda:CandidateAcceptanceEvidence(c,self.acceptance_host,self._backup_assessor).check(b)) if self.enforce_acceptance else None
        result=c.accept_candidate(args['candidate_id'],actor,_host_binding=b,_host_acceptance_check=accept_check)
        result.update(canonical_task_state='SUCCESS',model_invoked=False)
        return result
    def _accept_with_prepared_backup(self,name,args,binding):
        """Run the original producer outside the terminal DB transaction."""
        from task_center_handoff_host import HandoffHost
        from task_center_role_contract import RoleContractResolver
        c=self.control;host=self.acceptance_host
        # Authenticate and check candidate before any remote readback.
        c.db.execute('BEGIN')
        try:
            c.assert_host_lifecycle(binding)
            row=c.db.execute('SELECT state FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?',(c.tenant_id,args['candidate_id'])).fetchone()
            if row is None:raise ValueError('EXACT_HOST_CANDIDATE_REQUIRED')
            duplicate=row['state']=='ACCEPTED'
            if not duplicate:c.validate_accept_candidate(args['candidate_id'],binding['principal_id'])
        finally:c.db.rollback()
        if duplicate:
            self._backup_attempted=True
            try:return self.call(name,args)
            finally:self._backup_attempted=False
        databases=[r[2] for r in c.db.execute('PRAGMA database_list') if r[1]=='main']
        if (type(host) is not HandoffHost or type(host.role_contract) is not RoleContractResolver or
            host.tenant_id!=c.tenant_id or host.db_path is None or len(databases)!=1 or not databases[0] or os.path.realpath(databases[0])!=host.db_path):
            raise ValueError('CANDIDATE_TRUSTED_HOST_REQUIRED')
        roles=RoleContractResolver(c.db,host.role_contract.contracts,host.role_contract.intake_plans)
        readback=host._lifecycle_candidate_readback
        root=os.path.dirname(readback.artifacts) if readback is not None else None
        local=HandoffHost(c.db,host.tenant_id,host.issuer,host.adapter,clock=host.clock,mcp_config=host.mcp_config,role_contract=roles,candidate_lifecycle_root=root)
        # This host is private to backup assessment, not an authority for any
        # handoff write. After the original fence has released the task, resolve
        # its historical reservation only against the original terminal,
        # reconciled checkpoint and complete resource-release receipt.
        live_current=local._current_task
        def assessment_task(task_id,attempt_id,now):
            task=c.gateway.supervisor._task(task_id)
            if task['authority_state']!='REVOKED':
                return live_current(task_id,attempt_id,now)
            if (task_id!=binding['task_id'] or attempt_id!=binding['attempt_id'] or
                task['attempt_id']!=attempt_id or task['state']!='SUCCESS' or
                task['fence'] is None or task['epoch'] is None or
                type(now) not in (int,float) or not math.isfinite(now)):
                raise ValueError('CANDIDATE_RELEASED_RESERVATION_REQUIRED')
            c.assert_host_lifecycle(binding)
            candidate=c.validate_accept_candidate(binding['candidate_id'],binding['principal_id'])
            c.require_host_resource_release(candidate)
            c._require_terminal_artifact(candidate)
            resources=json.loads(task['resource_scope_json'])
            if (not isinstance(resources,list) or not resources or resources!=sorted(set(resources)) or
                hashlib.sha256(json.dumps(resources,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=task['resource_scope_digest']):
                raise ValueError('CANDIDATE_RELEASED_RESERVATION_REQUIRED')
            placeholders=','.join('?' for _ in resources)
            if c.db.execute('SELECT 1 FROM resource_claims WHERE resource_key IN (%s) LIMIT 1'%placeholders,resources).fetchone():
                raise ValueError('CANDIDATE_RELEASED_RESERVATION_REQUIRED')
            return task
        local._current_task=assessment_task
        plan=CandidateAcceptanceEvidence(c,local).check(binding,prepare_only=True)
        try:prepared=local.adapter.prepare_backup_assessment(local)
        except Exception:prepared=None
        if prepared is None:
            self._backup_attempted=True
            try:return self.call(name,args)
            finally:self._backup_attempted=False
        try:
            from task_center_backup_bridge_v2 import PreparedBackupAssessment
            if type(prepared) is not PreparedBackupAssessment or prepared.db is not c.db:raise ValueError('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        except ImportError:raise ValueError('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        # A known-busy bridge has not started this call; record a hold rather
        # than retrying an invocation with potentially unknown effects.
        if prepared._guard.locked():raise ValueError('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        owner=self
        class AcceptanceHost:
            def __init__(self):self.db=c.db
            def _reference(self,*a):return local._reference(*a)
            def _current_task(self,*a):return local._current_task(*a)
            def record(self,_session,_value):
                owner._backup_attempted=True;owner._backup_assessor=prepared
                try:return owner.call(name,args)
                finally:owner._backup_assessor=None;owner._backup_attempted=False
        return prepared.execute(AcceptanceHost(),binding['principal_id'],plan['verified'],plan['backup_binding'])

    def rpc(self,value):
        if not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or value.get('method')!='tools/call':
            raise ValueError('EXACT_LIFECYCLE_RPC_REQUIRED')
        p=value.get('params')
        if not isinstance(p,dict) or set(p)!={'name','arguments'}:raise ValueError('EXACT_LIFECYCLE_PARAMS_REQUIRED')
        try:result=self.call(p['name'],p['arguments'])
        except ValueError as exc:
            if p['name']=='task_accept_candidate' and self.enforce_acceptance:
                self._alert_missing(p['arguments'],str(exc))
            raise
        return {'jsonrpc':'2.0','id':value.get('id'),'result':{'content':[{'type':'text','text':json.dumps(result,sort_keys=True)}],'isError':False}}

    def _alert_missing(self,args,reason):
        from task_supervisor import canonical
        allowed={'CANDIDATE_TRUSTED_HOST_REQUIRED','CANDIDATE_BUNDLE_READBACK_REQUIRED',
          'CANDIDATE_HANDOFF_RECEIPTS_REQUIRED','CANDIDATE_BACKUP_COMPLETE_REQUIRED',
          'CANDIDATE_EXECUTOR_CONTRACT_REQUIRED','CANDIDATE_ACCEPTOR_CONTRACT_REQUIRED',
          'CANDIDATE_SNAPSHOT_DIGEST_REQUIRED','TASK_CONTRACT_UNKNOWN',
          'INDEPENDENT_REVIEW_RECEIPTS_REQUIRED','REVIEW_PASS_REQUIRED','UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED','MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'}
        if reason not in allowed or not isinstance(args,dict):return
        if any(not isinstance(args.get(k),str) for k in ('task_id','attempt_id','candidate_id')):return
        c=self.control;b={k:self.binding[k] for k in ('project_id','principal_id','role_id','role_version','phase','review_kind')}
        b.update(task_id=args['task_id'],attempt_id=args['attempt_id'],candidate_id=args['candidate_id'])
        c.db.execute('BEGIN IMMEDIATE')
        try:
            if reason=='MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED':
                c.assert_host_lifecycle(b,_allow_unsettled_supervision=True)
                assignment=c.db.execute('''SELECT state FROM model_assignments WHERE tenant_id=? AND task_id=? AND attempt_id=? AND role_id=? AND principal_id=? AND role_version=?''',
                    (c.tenant_id,args['task_id'],args['attempt_id'],b['role_id'],b['principal_id'],b['role_version'])).fetchone()
                if assignment is None or assignment['state']!='ASSIGNED':raise ValueError('CURRENT_HOST_LIFECYCLE_ROLE_REQUIRED')
                # A hold is not authority to take over. Recheck the original
                # same-DB host's live writer and all resource claims under lock.
                from task_center_handoff_host import HandoffHost
                from task_center_role_contract import RoleContractResolver
                host=self.acceptance_host
                paths=[r[2] for r in c.db.execute('PRAGMA database_list') if r[1]=='main']
                if (type(host) is not HandoffHost or type(host.role_contract) is not RoleContractResolver or
                    host.tenant_id!=c.tenant_id or host.db_path is None or len(paths)!=1 or not paths[0] or os.path.realpath(paths[0])!=host.db_path):
                    raise ValueError('CANDIDATE_TRUSTED_HOST_REQUIRED')
                roles=RoleContractResolver(c.db,host.role_contract.contracts,host.role_contract.intake_plans)
                local=HandoffHost(c.db,host.tenant_id,host.issuer,host.adapter,clock=host.clock,mcp_config=host.mcp_config,role_contract=roles)
                local._current_task(args['task_id'],args['attempt_id'],c.clock())
            else:c.assert_host_lifecycle(b)
            seed={'candidate_id':args['candidate_id'],'reason':reason}
            if reason=='MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED':
                # Deduplicate the same unsettled attempts, not a later distinct
                # unresolved model effect after an intervening reconciliation.
                pending=c.db.execute('''SELECT request_id,state,attempts FROM model_requests
                  WHERE tenant_id=? AND task_id=? AND attempt_id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED')
                  ORDER BY request_id LIMIT 2049''',(c.tenant_id,args['task_id'],args['attempt_id'])).fetchall()
                if not pending or len(pending)>2048:raise ValueError('MODEL_SUPERVISION_SCOPE_REQUIRED')
                seed['unsettled']=[list(row) for row in pending]
            encoded_seed=(canonical(seed) if reason=='MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'
                          else args['candidate_id']+':'+reason)
            event='candidate-evidence-hold-'+hashlib.sha256(encoded_seed.encode()).hexdigest()
            payload={'state':'HOLD','action':'RECONCILE_BEFORE_CONTROLLED_REASSIGN',
              'candidate_id':args['candidate_id'],'reason':reason,'requires_effect_reconciliation':True,'takeover_allowed':False}
            from task_supervisor import canonical
            now=c.clock()
            c.db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)',
              (args['task_id'],args['attempt_id'],event,'SUPERVISION_ACTION',now,'PHASE_EXECUTION','CANDIDATE_ACCEPTANCE_EVIDENCE_HOLD',canonical(payload)))
            self.supervisor._enqueue(args['task_id'],args['attempt_id'],event,payload,now)
            c.db.commit()
        except Exception:
            c.db.rollback()
            # Never turn an unverified requester or stale attempt into an alert.
