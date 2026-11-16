"""Read one coordinator-approved bounded observation snapshot, never authority.

The digest pins only the exact non-secret metadata bytes handed off by main; it
is not a signature, an issuer, identity verification, or a production trust
root. HTTP requests cannot supply a path or alter this allowlist.
"""
import hashlib,json,re,uuid

APPROVED_SNAPSHOTS={'main-bounded-sessions-20261116':'cefceddce48f4f810a26dc2c708aacd62ac1b26f16b5258df9eac7bd65537537',
                    'main-development-handoff-20261117':'cddee07f04affca65f5507b7f286cd0bb22f0a1a71cc8cc16ec166f11ee7cf40'}
SESSION=re.compile(r'^agent:[a-z0-9-]+:subagent:[a-f0-9-]{36}$')
NAME=re.compile(r'^[a-zA-Z][a-zA-Z0-9_.-]{0,63}$')
class ObservationUnavailable(Exception):pass

def fields(value,names):
    if not isinstance(value,dict) or set(value)!=set(names):raise ObservationUnavailable('invalid metadata structure')

def as_uuid(value):
    try:
        if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError()
    except (ValueError,AttributeError):raise ObservationUnavailable('invalid reference')
    return value

class ApprovedObservationReader(object):
    def __init__(self,path,collector_ref):
        if collector_ref not in APPROVED_SNAPSHOTS:raise ObservationUnavailable('unapproved collector')
        self.path=path;self.collector_ref=collector_ref
    def read(self):
        try:
            with open(self.path,'rb') as f:raw=f.read(65537)
            if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=APPROVED_SNAPSHOTS[self.collector_ref]:raise ObservationUnavailable('unapproved snapshot')
            document=json.loads(raw.decode('utf8'))
            if self.collector_ref=='main-development-handoff-20261117':
                return {'state':'OBSERVED_METADATA_ONLY','source_observation_verified':'MAIN_RELAYED_SNAPSHOT_BYTES_MATCH',
                        'verification_scope':'MAIN_RELAY_NOT_API_ISSUER_OR_IDENTITY',
                        'permission_verification':'UNKNOWN','handoff_completed':'UNKNOWN',
                        'development_handoff':document}
            result=normalize(document,self.collector_ref)
            result['state']='OBSERVED_METADATA_ONLY'
            result['source_observation_verified']='MAIN_APPROVED_SNAPSHOT_BYTES_MATCH'
            result['verification_scope']='COORDINATOR_HANDOFF_NOT_API_ISSUER_OR_IDENTITY'
            return result
        except (OSError,UnicodeError,ValueError,TypeError,KeyError):raise ObservationUnavailable('snapshot unavailable')

def normalize(doc,collector_ref):
    fields(doc,('schema_version','source','observation_time_basis','scope','purpose','limitations','observations'))
    if doc['schema_version']!='1.0' or doc['source']!='main official agents_list and bounded sessions_history calls':raise ObservationUnavailable('source mismatch')
    if not all(isinstance(doc[k],str) and 0<len(doc[k])<=256 for k in ('scope','purpose','observation_time_basis')):raise ObservationUnavailable('invalid metadata')
    if not isinstance(doc['limitations'],list) or not all(isinstance(x,str) and len(x)<=256 for x in doc['limitations']):raise ObservationUnavailable('invalid limitations')
    if not isinstance(doc['observations'],list) or len(doc['observations'])>20:raise ObservationUnavailable('invalid observations')
    output=[];seen={};sessions={};session_roles={};runs={};run_sessions={};messages={}
    for item in doc['observations']:
        fields(item,('role_ref','source_api','query','pending_count','truncated','content_truncated','records'))
        role=item['role_ref']
        if role not in ('ledger-author','ledger-reviewer') or item['source_api']!='sessions_history':raise ObservationUnavailable('unsupported scope')
        fields(item['query'],('session_ref','limit','includeTools'))
        query=item['query'];session=query['session_ref']
        if not isinstance(session,str) or not SESSION.fullmatch(session) or type(query['limit']) is not int or query['limit']!=2 or query['includeTools'] is not True:raise ObservationUnavailable('invalid query metadata')
        if type(item['pending_count']) is not int or item['pending_count']<0 or type(item['truncated']) is not bool or type(item['content_truncated']) is not bool or not isinstance(item['records'],list) or len(item['records'])>2:raise ObservationUnavailable('invalid bounded history')
        if session in session_roles and session_roles[session]!=role:raise ObservationUnavailable('role session mismatch')
        session_roles[session]=role
        if session not in sessions:sessions[session]='local-session-%d'%(len(sessions)+1)
        for rec in item['records']:
            fields(rec,('role','tool_name','is_error','observed_timestamp_ms','message_ref','run_ref','stop_reason','tool_calls'))
            msg=as_uuid(rec['message_ref']);run=as_uuid(rec['run_ref']);ts=rec['observed_timestamp_ms']
            if type(ts) is not int or ts<=0 or ts>9999999999999 or rec['tool_calls']!=[]:raise ObservationUnavailable('invalid record metadata')
            if rec['role']=='toolResult':
                if not isinstance(rec['tool_name'],str) or not NAME.fullmatch(rec['tool_name']) or type(rec['is_error']) is not bool or rec['stop_reason'] is not None:raise ObservationUnavailable('invalid tool receipt')
                kind='TOOL_RESULT_OBSERVED'
            elif rec['role']=='assistant':
                if rec['tool_name'] is not None or rec['is_error'] is not None or rec['stop_reason']!='stop':raise ObservationUnavailable('invalid result receipt')
                kind='ROLE_RESULT_OBSERVED'
            else:raise ObservationUnavailable('unsupported record role')
            if run in run_sessions and run_sessions[run]!=session:raise ObservationUnavailable('run session mismatch')
            run_sessions[run]=session
            fingerprint=session+'|'+role+'|'+json.dumps(rec,sort_keys=True,separators=(',',':'))
            if msg in seen:
                if seen[msg]!=fingerprint:raise ObservationUnavailable('conflicting receipt')
                continue
            seen[msg]=fingerprint
            if run not in runs:runs[run]='local-run-%d'%(len(runs)+1)
            if msg not in messages:messages[msg]='local-message-%d'%(len(messages)+1)
            output.append({'role_label':role,'role_identity_verification':'UNKNOWN','source_api':'sessions_history',
                'source_ref':collector_ref,'session_ref':sessions[session],'run_ref':runs[run],
                'message_ref':messages[msg],'record_timestamp_ms':ts,'occurred_at':'UNKNOWN',
                'timestamp_semantics':'API_RECORD_TIME_NOT_EXECUTION_TIME','observation_kind':kind,
                'tool_name':rec['tool_name'] if kind=='TOOL_RESULT_OBSERVED' else 'UNKNOWN',
                'tool_reported_error':rec['is_error'] if kind=='TOOL_RESULT_OBSERVED' else 'UNKNOWN',
                'history_truncated':item['truncated'],'content_truncated':item['content_truncated'],
                'freshness':'STALE','pending':'UNKNOWN','actual_received':'UNKNOWN','worker_started':'UNKNOWN',
                'business_result':'UNKNOWN','writer_authority':'UNKNOWN','permission':'UNKNOWN',
                'unresolved_effects':'UNKNOWN'})
    return {'state':'UNTRUSTED_METADATA_ONLY','scope':'LEDGER_IMPLEMENTATION_AND_REVIEW_ONLY',
      'collector_ref':collector_ref,'source_observation_verified':'UNAVAILABLE',
      'verification_scope':'UNVERIFIED_NORMALIZER_OUTPUT',
      'official_api_issuer_verification':'UNAVAILABLE','freshness':'STALE','global_idle':'UNKNOWN',
      'writer_verification':'UNKNOWN','permission_verification':'UNKNOWN','business_acceptance':'UNKNOWN',
      'handoff_completed':'UNKNOWN','dispatch_performed':False,'records':output}
