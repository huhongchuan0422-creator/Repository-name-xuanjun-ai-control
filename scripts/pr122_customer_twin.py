"""Read-only task projection hosted by the original customer App.
No task ledger, write operation, model call, credential, or production source is created here.
The host must inject an already-authorized project-scoped snapshot provider.
"""
from scripts.pr122_customer_core import Denied,Unavailable

ROLES=('OWNER','EDITOR','VIEWER','REVIEWER')
TASK_FIELDS=('task_id','project_id','node_id','attempt_id','module_id','state','runtime_status',
             'task_responsible_party','responsible_party','blocker','next_action','authority_state',
             'epoch','checkpoint_sha256','writer_identity','received_at','started_at',
             'last_real_progress_at','last_event_at','authority_valid_until')
CP_FIELDS=('attempt_id','checkpoint_id','effects_state','created_at')
DEP_FIELDS=('producer_task_id','required_version','required_evidence_ref','state','event_attempt_id','event_id')
EV_FIELDS=('task_id','attempt_id','event_id','kind','observed_at','evidence_kind','evidence_ref')

def _scalar(value):
    if value is None:return None
    if type(value) in (str,int,float) and not isinstance(value,bool):return value
    raise ValueError('TWIN_FIELD_TYPE')

def _projected(row,fields):
    if type(row) is not dict:raise ValueError('TWIN_ROW')
    return {k:_scalar(row[k]) for k in fields if k in row}

def sanitize(snapshot,pid,role):
    if type(snapshot) is not dict or snapshot.get('schema')!=3 or snapshot.get('mode')!='TEST_ONLY' or snapshot.get('production_status')!='NOT_IMPLEMENTED':
        raise Unavailable('TWIN_SOURCE_CONTRACT_UNVERIFIED')
    tasks=snapshot.get('tasks');timeline=snapshot.get('timeline')
    if type(tasks) is not list or type(timeline) is not list or len(tasks)>1000 or len(timeline)>5000:raise ValueError('TWIN_SIZE')
    out_tasks=[]
    for raw in tasks:
        row=_projected(raw,TASK_FIELDS)
        if row.get('project_id')!=pid:raise Denied('TWIN_PROJECT_SCOPE')
        cps=raw.get('checkpoints',[]);deps=raw.get('dependencies',[])
        if type(cps) is not list or type(deps) is not list or len(cps)>1000 or len(deps)>1000:raise ValueError('TWIN_SIZE')
        row['checkpoints']=[_projected(x,CP_FIELDS) for x in cps]
        row['dependencies']=[_projected(x,DEP_FIELDS) for x in deps]
        if role not in ('OWNER','REVIEWER'):
            for key in ('writer_identity','checkpoint_sha256','authority_state','epoch'):row.pop(key,None)
        out_tasks.append(row)
    out_events=[]
    visible={x.get('task_id') for x in out_tasks}
    for raw in timeline:
        row=_projected(raw,EV_FIELDS)
        if row.get('task_id') not in visible:continue
        out_events.append(row)
    return {'schema':3,'mode':'TEST_ONLY','production_status':'NOT_IMPLEMENTED',
            'observed_at':snapshot.get('observed_at') if type(snapshot.get('observed_at')) in (int,float) and not isinstance(snapshot.get('observed_at'),bool) else None,
            'tasks':out_tasks,'timeline':out_events,
            'scope':'ORIGINAL_PROJECT_READONLY_PROJECTION','write_allowed':False,
            'dispatch_receipt':'UNKNOWN','ack':'UNKNOWN','acceptance':'UNKNOWN'}

class TwinProjectionHTTP:
    def __init__(self,snapshot_provider):self.snapshot_provider=snapshot_provider
    def handle(self,center,uid,method,operation,body):
        parts=operation.split('/')
        if len(parts)!=3 or parts[:2]!=['twin','projection']:return 404,{'error':'NOT_FOUND'}
        if method!='GET':return 405,{'error':'METHOD_NOT_ALLOWED'}
        pid=parts[2]
        with center.tx():
            project,role,_=center.project(uid,pid)
            if role not in ROLES:raise Denied('PROJECT_ROLE_NOT_ALLOWED')
            snapshot=self.snapshot_provider(project['tenant'],pid)
            if snapshot is None:raise Unavailable('TWIN_SOURCE_NOT_CONFIGURED')
            return 200,sanitize(snapshot,pid,role)
