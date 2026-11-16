"""Offline observation journal. Never dispatches or manages business authority."""
import json, os, re, tempfile, hashlib
from pathlib import Path
from datetime import datetime, timezone

ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
TIME = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$')
VALID = {'VERIFIED_NOW', 'HISTORICAL', 'UNKNOWN', 'STALE', 'UNAVAILABLE', 'DENIED'}
TYPES = {'task','role','host_service','permission_ref','source_artifact'}
PHASES = {'register','dispatch_request','send_accepted','actual_received','start','progress','block','result','review','accept','cancel','deploy','runtime','business_verify','correction','diagnostic','handoff_propose','handoff_nominate','handoff_send_accepted','handoff_received','handoff_aligned','handoff_gap','handoff_supervision_start','handoff_verified','handoff_rejected','handoff_incomplete'}
# Deliberately finite fields: input is structured metadata, never arbitrary payloads.
FIELDS = {'id','schema_version','source','occurred_at','observed_at','validity','kind','project_id','task_id','attempt_id','event_id','idempotency_key','producer','type','causation','evidence','result','data','namespace','target_event_id','state','goal','acceptance','instruction_ref','writer_role_id','blocker','next_action','dependencies','code_refs','deploy_refs','role_id','verified_session_ref','entry_ref','query_capability','send_capability','receipt_ref','service_class','host_ref','build_ref','running_ref','scope','expires_at','denial','manager_ref','repo_ref','branch','commit','tree','dirty_ref','manifest_ref','size','artifact_sha256','download_ref','test_ref','review_ref','rollback_ref','lease_ref','fence_ref','stage','status','message_ref','pending_operations','permission_boundary','source_refs','last_progress','reply_id','receipt_id','substantive','role_idle','unresolved_effects','permission_valid','owner_authorized','reason','version','events','objects','tasks','history','conflicts','snapshot','cursor','progress','diagnostic','eligible','reasons','data_ref','observations','original_entry_ref','dependency_lock_ref','build_id','release_status','business_verify_ref','runtime_source_ref','goal_acceptance_ref','handoff_id','handoff_version','snapshot_digest','snapshot_data','scope_included','scope_excluded','actor_ref','session_ref','identity_evidence_ref','permission_evidence_ref','permission_expires_at','actual_checks','unknown_items','proposal_event_id','received_event_id','alignment_event_id','supervision_start_event_id','target_ref','handoff_status','handoffs','outgoing','receiving','supervisor','required_fields','version_conflict','summary','snapshot_scope','verification_ref','scope_authorization_ref','sanitization','writer_verification'}
# Reject secret-looking content, paths and URLs with credentials/query. Values are not printed on failure.
BAD = re.compile(r'(?i)(?:password|passwd|secret|token|private[ _-]?key|authorization|bearer\s+|-----BEGIN|LTAI[A-Za-z0-9]|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|\bsk-[A-Za-z0-9]|/home/|/root/|/var/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://[^\s/@]+@|https?://\S*[?&])')
class LedgerError(Exception): pass
class Conflict(LedgerError): pass

# Conservative structured input: text is short, manually reviewed, and never a raw transcript.
TEXT_FIELDS={'goal','acceptance','blocker','next_action','reason'}
LIST_FIELDS={'dependencies','code_refs','deploy_refs','source_refs','pending_operations',
             'scope_included','scope_excluded','actual_checks','unknown_items'}
DICT_FIELDS={'data','snapshot_data'}
HASH_FIELDS={'snapshot_digest','artifact_sha256','commit','tree'}
TIME_FIELDS={'occurred_at','observed_at','expires_at','permission_expires_at'}
TEXT_RE=re.compile(r'^[\w\s\u3400-\u9fff，。；：、（）(),.：:;!?！？，/\-]{1,256}$')
OPAQUE=re.compile(r'(?<![A-Za-z0-9])[A-Za-z0-9]{25,}(?![A-Za-z0-9])')
def safe(value, key=None):
    if isinstance(value, dict):
        if key is not None and key not in DICT_FIELDS: raise LedgerError('invalid object type')
        if any(k not in FIELDS for k in value): raise LedgerError('field not allowed')
        for k,v in value.items(): safe(v,k)
    elif isinstance(value, list):
        if key not in LIST_FIELDS or len(value)>100: raise LedgerError('invalid list')
        for v in value:
            if not isinstance(v,str): raise LedgerError('invalid list item')
            safe(v,'list_item')
    elif isinstance(value, str):
        if key in DICT_FIELDS or key in LIST_FIELDS: raise LedgerError('invalid field type')
        if len(value)>256 or BAD.search(value) or any(ord(c)<32 for c in value): raise LedgerError('unsafe value')
        if key in TEXT_FIELDS:
            if not TEXT_RE.fullmatch(value) or OPAQUE.search(value): raise LedgerError('unsafe business text')
        elif key in HASH_FIELDS:
            if value!='UNKNOWN' and not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}',value): raise LedgerError('invalid digest')
        elif key in TIME_FIELDS:
            if value not in ('UNKNOWN','UNAVAILABLE'): parse_time(value)
        elif key in ('branch',):
            if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}',value) or '..' in value: raise LedgerError('invalid branch')
        elif not ID.fullmatch(value) or OPAQUE.search(value): raise LedgerError('invalid structured reference')
    elif isinstance(value,bool):
        if key not in ('substantive','role_idle','unresolved_effects','permission_valid','owner_authorized'): raise LedgerError('invalid boolean')
    elif isinstance(value,int):
        if key not in ('schema_version','version','handoff_version','size') or value<0: raise LedgerError('invalid number')
    else: raise LedgerError('invalid value')

def parse_time(value):
    if not isinstance(value,str) or not TIME.fullmatch(value): raise LedgerError('invalid timestamp')
    v=re.sub(r'([+-]\d\d):(\d\d)$',r'\1\2',value.replace('Z','+0000'))
    try: return datetime.strptime(v,'%Y-%m-%dT%H:%M:%S.%f%z' if '.' in v else '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone.utc)
    except ValueError: raise LedgerError('invalid timestamp')

def ident(x):
    if not isinstance(x,str) or not ID.fullmatch(x) or x in ('.','..'): raise LedgerError('invalid identifier')
    return x

def canonical(x): return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(data): return hashlib.sha256(data).hexdigest()
def load(path):
    try: return json.loads(Path(path).read_text(encoding='utf8'))
    except (OSError,ValueError) as e: raise LedgerError('input unavailable or invalid') from e

def validate(e):
    safe(e)
    required=('schema_version','namespace','event_id','task_id','attempt_id','idempotency_key','producer','type','occurred_at','observed_at','source','evidence','result','data','validity','causation','sanitization')
    if not isinstance(e,dict) or any(k not in e for k in required): raise LedgerError('missing event field')
    if any(not isinstance(e[k],str) or not e[k] for k in ('source','evidence','result','causation')): raise LedgerError('source and evidence references required')
    if e['sanitization'] != 'MANUAL_REDACTED': raise LedgerError('manual redaction declaration required')
    if e['schema_version'] != 1 or e['validity'] not in VALID or e['type'] not in PHASES: raise LedgerError('invalid schema or phase')
    for k in ('namespace','event_id','task_id','attempt_id','idempotency_key','producer'): ident(e[k])
    for k in ('occurred_at','observed_at'): parse_time(e[k])
    if not isinstance(e['data'],dict): raise LedgerError('invalid data')
    if e['type']=='register':
        d=e['data']
        if not all(k in d for k in ('kind','id','schema_version','source','occurred_at','observed_at','validity')) or d['kind'] not in TYPES or d['validity'] not in VALID or d['schema_version'] != 1: raise LedgerError('invalid registered object')
        ident(d['id'])
        required_by_kind={
            'task':('goal','acceptance','instruction_ref','writer_role_id','state','blocker','next_action','dependencies','code_refs','deploy_refs'),
            'role':('task_id','verified_session_ref','entry_ref','query_capability','send_capability','receipt_ref'),
            'host_service':('task_id','service_class','host_ref','source_refs','build_ref','running_ref'),
            'permission_ref':('task_id','scope','expires_at','denial','manager_ref'),
            'source_artifact':('task_id','repo_ref','branch','commit','tree','dirty_ref','manifest_ref','size','artifact_sha256','download_ref','test_ref','review_ref','deploy_refs','rollback_ref')}
        if any(k not in d for k in required_by_kind[d['kind']]): raise LedgerError('missing object field')
        if d['kind']=='host_service' and d['service_class'] not in ('business','admin','health','fixture','UNKNOWN'): raise LedgerError('invalid service class')
        if d['kind']=='task' and d['id'] != e['task_id']: raise LedgerError('task identity mismatch')
        for k in ('occurred_at','observed_at'): parse_time(d[k])
    if e['type'].startswith('handoff_'):
        from .handoffs import validate_handoff
        validate_handoff(e)
    if e['type']=='correction':
        ident(e['data'].get('target_event_id'))
        if not isinstance(e['data'].get('data'),dict): raise LedgerError('correction requires replacement object')
    return e

# The local marker is not an authentication system: enforce the same limited
# offline policy on new, replayed, and already-present event files.
def offline_policy(e, writer, namespace=None, filename=None):
    validate(e)
    if e['producer'] != writer: raise LedgerError('writer verification unavailable')
    if namespace is not None and e['namespace'] != namespace: raise LedgerError('namespace mismatch')
    if filename is not None and e['event_id'] != filename: raise LedgerError('event identity mismatch')
    if e['namespace'] != 'synthetic':
        if e['validity'] != 'HISTORICAL' or e['type'] != 'register' or e['data']['validity'] == 'VERIFIED_NOW':
            raise LedgerError('writer verification unavailable')
        if e['data'].get('artifact_sha256','UNKNOWN') != 'UNKNOWN': raise LedgerError('artifact provenance unavailable')

def causal_order(events):
    """Stable replay dependencies without altering original observation history."""
    phases={'start','progress','block','result','review','accept'}
    byid={e['event_id']:e for e in events}; visited=set(); active=[]; cycle=set(); ordered=[]
    def visit(e):
        key=e['event_id']
        if key in visited: return
        if key in active:
            cycle.update(active[active.index(key):]); return
        active.append(key)
        if e['type'] in phases:
            parent=byid.get(e['causation'])
            if parent and parent['type'] in phases.union({'actual_received'}): visit(parent)
        active.pop(); visited.add(key); ordered.append(e)
    for e in events: visit(e)
    return ordered,cycle

class Store:
    def __init__(self, root, writer):
        self.root=Path(root); self.writer=ident(writer)
        for p in ('events','outbox','views'): (self.root/p).mkdir(parents=True,exist_ok=True)
        self._append(self.root/'writer.id', (self.writer+'\n').encode())
    def enqueue(self,e):
        offline_policy(e,self.writer)
        p=self.root/'outbox'/e['namespace']/ (e['event_id']+'.json')
        return self._append(p,canonical(e))
    @staticmethod
    def _append(p,data):
        p.parent.mkdir(parents=True,exist_ok=True)
        # Write complete file before hard-link publication; no overwrite and no partial published event.
        fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=p.parent)
        try:
            with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            try: os.link(tmp,p); return 'APPENDED'
            except FileExistsError:
                if p.read_bytes()==data: return 'DUPLICATE'
                raise Conflict('event content conflict; original preserved')
        finally: os.unlink(tmp)
    def flush(self, namespace):
        ident(namespace); folder=self.root/'outbox'/namespace
        counts={'appended':0,'duplicate':0,'conflict':0}
        for p in sorted(folder.glob('*.json')):
            e=load(p); offline_policy(e,self.writer,namespace,p.stem)
            try:
                outcome=self._append(self.root/'events'/namespace/p.name,canonical(e))
                counts[outcome.lower()]+=1
            except Conflict:
                counts['conflict']+=1
                continue
            # Retain outbox receipt permanently; repeat is harmless and recoverable.
        return counts
    def events(self,namespace):
        ident(namespace); items=[]
        for p in (self.root/'events'/namespace).glob('*.json'):
            e=load(p); offline_policy(e,self.writer,namespace,p.stem)
            items.append(e)
        return sorted(items,key=lambda e:(parse_time(e['observed_at']),e['event_id']))
    def project(self,namespace):
        events=self.events(namespace); processing,cycles=causal_order(events); all_events={e['event_id']:e for e in events}
        seen={}; objects={}; tasks={}; conflicts=[]; pending=[]; registered={}; object_ids={}; phase_events={}; phase_rank={}; object_head={}
        for e in processing:
            key=(e['task_id'],e['attempt_id'],e['idempotency_key'])
            if key in seen:
                if seen[key] != e['event_id']: conflicts.append(e['event_id'])
                continue
            seen[key]=e['event_id']; task=tasks.setdefault(e['task_id'],{'task_id':e['task_id'],'state':'UNKNOWN','history':[]})
            task['history'].append(e)
            if e['type']=='register':
                objkey=e['data']['kind']+':'+e['data']['id']; old=object_ids.get(objkey)
                if old is None:
                    objects[objkey]=e['data']; object_ids[objkey]=e['data']; object_head[objkey]=e['event_id']; registered[e['event_id']]=(e['task_id'],e['data'])
                elif old!=e['data']: conflicts.append(e['event_id'])
            elif e['type']=='correction':
                entry=registered.get(e['data']['target_event_id']); replacement=e['data']['data']
                if entry and entry[0]==e['task_id'] and replacement.get('id')==entry[1]['id'] and replacement.get('kind')==entry[1]['kind'] and replacement.get('source')==entry[1]['source'] and object_head.get(entry[1]['kind']+':'+entry[1]['id'])==e['data']['target_event_id']:
                    candidate=dict(e); candidate['type']='register'; candidate['data']=replacement
                    try: validate(candidate)
                    except LedgerError: conflicts.append(e['event_id'])
                    else:
                        objects[entry[1]['kind']+':'+entry[1]['id']]=replacement
                        object_ids[entry[1]['kind']+':'+entry[1]['id']]=replacement
                        object_head[entry[1]['kind']+':'+entry[1]['id']]=e['event_id']; registered[e['event_id']]=(e['task_id'],replacement)
                else: conflicts.append(e['event_id'])
            elif e['type']=='cancel': task['state']='CANCELLED'
            elif e['type'] in ('start','progress','block','result','review','accept') and task['state']!='CANCELLED':
                ranks={'start':1,'progress':2,'block':2,'result':3,'review':4,'accept':5}
                predecessor=phase_events.get(e['causation']); scope=(e['task_id'],e['attempt_id'])
                allowed={'start':('actual_received',),'progress':('start','progress','block'),'block':('start','progress','block'),'result':('start','progress','block'),'review':('result',),'accept':('review',)}
                valid=bool(predecessor and (predecessor['task_id'],predecessor['attempt_id'])==scope and predecessor['type'] in allowed[e['type']] and parse_time(predecessor['occurred_at'])<=parse_time(e['occurred_at']) and ranks[e['type']]>=phase_rank.get(scope,0))
                if e['event_id'] in cycles: conflicts.append(e['event_id'])
                elif e['causation'] not in all_events or e['causation'] in pending: pending.append(e['event_id'])
                elif valid:
                    task['state']={'start':'STARTED','progress':'IN_PROGRESS','block':'BLOCKED','result':'RESULT','review':'REVIEW','accept':'ACCEPTED'}[e['type']]; phase_rank[scope]=ranks[e['type']]
                else: conflicts.append(e['event_id'])
            if e['type']=='actual_received' or (e['type'] in ('start','progress','block','result','review','accept') and e['event_id'] not in conflicts and e['event_id'] not in pending and task['state']!='CANCELLED'): phase_events[e['event_id']]=e
            # Corrections remain traceable and do not silently rewrite authority or historical events.
        # History is observation-ordered, independent of replay evaluation order.
        for task in tasks.values(): task['history'].sort(key=lambda e:(parse_time(e['observed_at']),e['event_id']))
        from .handoffs import project_handoffs
        return {'schema_version':1,'namespace':namespace,'objects':objects,'tasks':tasks,'conflicts':conflicts,'pending_dependencies':pending,'writer_verification':'UNKNOWN','handoffs':project_handoffs([event for task in tasks.values() for event in task['history']])}
    def handoff(self,namespace,task_id):
        return handoff(self,namespace,task_id)
    def publish_view(self,namespace,expected):
        ident(namespace); p=self.root/'views'/(namespace+'.json'); lock=self.root/'views'/(namespace+'.lock')
        # Local projection CAS only, not a business lease. Crash leaves lock for operator recovery.
        try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError as e: raise Conflict('view busy') from e
        try:
            os.close(fd); old=p.read_bytes() if p.exists() else b''
            if digest(old)!=expected: raise Conflict('view version conflict')
            data=canonical(self.project(namespace)); tmp=p.with_name(p.name+'.tmp')
            with open(tmp,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,p); return digest(data)
        finally: os.unlink(lock)

def handoff(store,namespace,task_id=None):
    # A caller-supplied mutable projection is never an authority or export source.
    # Store.project rebuilds from the configured store and checks each event's
    # producer against store.writer via events()/offline_policy().
    if not isinstance(store,Store) or task_id is None: raise LedgerError('store context required')
    ident(namespace); ident(task_id)
    view=store.project(namespace)
    task=view['tasks'].get(task_id)
    if task is None: raise LedgerError('unknown task')
    objs={k:v for k,v in view['objects'].items() if v.get('task_id')==task_id or (v.get('kind')=='task' and v.get('id')==task_id)}
    for obj in objs.values(): safe(obj,'data')
    return {'schema_version':1,'namespace':namespace,'task_id':task_id,'snapshot':task,'objects':objs,'handoffs':{k:v for k,v in view.get('handoffs',{}).items() if v['task_id']==task_id}}

def stall(replies,receipts, state, role_idle=False, unresolved_effects=True, permission_valid=False, owner_authorized=False, prior_diagnostics=None, incident_id=None):
    # Inputs are already-observed, deduplicated reply/receipt IDs; no network or action.
    progress=max([i for i,r in enumerate(replies) if r.get('substantive')],default=-1)
    since=replies[progress+1:]; ids=[r.get('reply_id') for r in since if r.get('reply_id')]
    no_reply_progress=len(set(ids))>=3
    no_receipts=len(receipts)>=2 and receipts[-1]==receipts[-2]
    stale=no_reply_progress or no_receipts
    excluded=state in ('PAUSED','CANCELLED','DENIED','EXTERNAL_DEPENDENCY','UNKNOWN','STALE','UNAVAILABLE')
    eligible=bool(stale and not excluded and role_idle and not unresolved_effects and permission_valid and owner_authorized)
    key=digest(canonical({'incident_id':incident_id,'progress_id':replies[progress].get('reply_id') if progress>=0 else None})) if stale and incident_id else ''
    return {'diagnostic':bool(stale and key and key not in (prior_diagnostics or [])),'eligible':eligible,'reason':'observation only; no dispatch','diagnostic_id':key}
