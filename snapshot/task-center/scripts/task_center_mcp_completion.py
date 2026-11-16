"""Opt-in lifecycle tools over original ModelControl, never model-text execution.

Existing host-run checklists are consumed, not created via MCP. Development
contracts must use their controlled signed review/execution path instead.
"""
import json
import re
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

class CandidateLifecycleMCP:
    def __init__(self,control,binding,lock_dir):
        self.control=control;self.binding=dict(binding);self.lock_dir=lock_dir
        self.supervisor=control.gateway.supervisor
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
        if name=='task_submit_candidate':
            return c.submit_candidate(args['task_id'],args['artifact_sha256'],args['checklist_sha256'],actor,_host_binding=b)
        if name=='task_review_candidate':
            return c.review_candidate(args['candidate_id'],actor,args['findings'],args['passed'],b['review_kind'],_host_binding=b)
        if name=='task_candidate_status':
            c.db.execute('BEGIN')
            try:
                task=c.assert_host_lifecycle(b)
                row=c.db.execute('SELECT state,artifact_sha256,checklist_sha256,accepted_by FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?',
                    (c.tenant_id,args['candidate_id'])).fetchone()
                released=False
                if task['state']=='SUCCESS' and task['authority_state']=='REVOKED':
                    try:c.require_host_resource_release(dict(task_id=args['task_id'],attempt_id=args['attempt_id']));released=True
                    except ValueError:pass
                audited=c.db.execute("SELECT 1 FROM model_audit WHERE tenant_id=? AND principal_id=? AND action='CANDIDATE_ACCEPTED' AND target_id=?",
                    (c.tenant_id,row['accepted_by'],args['candidate_id'])).fetchone() is not None
                return {'candidate_id':args['candidate_id'],'candidate_state':row['state'],
                    'canonical_task_state':task['state'],'authority_state':task['authority_state'],
                    'artifact_sha256':row['artifact_sha256'],'checklist_sha256':row['checklist_sha256'],
                    'observation_only':True,'model_invoked':False,
                    'completion_state':('ACCEPTED' if row['state']=='ACCEPTED' and released and audited
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
            return c.validate_accept_candidate(args['candidate_id'],actor)
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
        result=c.accept_candidate(args['candidate_id'],actor,_host_binding=b)
        result.update(canonical_task_state='SUCCESS',model_invoked=False)
        return result
    def rpc(self,value):
        if not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or value.get('method')!='tools/call':
            raise ValueError('EXACT_LIFECYCLE_RPC_REQUIRED')
        p=value.get('params')
        if not isinstance(p,dict) or set(p)!={'name','arguments'}:raise ValueError('EXACT_LIFECYCLE_PARAMS_REQUIRED')
        result=self.call(p['name'],p['arguments'])
        return {'jsonrpc':'2.0','id':value.get('id'),'result':{'content':[{'type':'text','text':json.dumps(result,sort_keys=True)}],'isError':False}}
