"""Display-only candidate for existing backup receipts; never scans or backs up.

No provider, scheduler, credential, destination or writer authority is installed.
A syntactically valid report is not verified source evidence.
"""
import json, re
from datetime import datetime, timezone
from task_delivery_ledger.core import ident,parse_time,safe,LedgerError
from task_delivery_observation import ObservationUnavailable

EXCLUSIONS=frozenset(('secrets','environment','customer','business_database','raw_logs','cache'))
REQUIRED=frozenset(('schema_version','project_ref','receipt_id','source_ref','reported_status',
    'observed_at','base_ref','result_ref','manifest_ref','restore_ref','last_success_at',
    'content_changed','file_hashes','excluded','limitations'))
class BackupReceiptError(Exception):pass

class LocalBackupReceiptReader(object):
    """Read a caller-bound local report; neither authenticate it nor expose raw fields."""
    def __init__(self,path):
        self.path=path
    def read(self):
        try:
            with open(self.path,'rb') as f:raw=f.read(65537)
            if len(raw)>65536:raise ValueError('oversize')
            d=json.loads(raw.decode('utf8'))
            if not isinstance(d,dict) or d.get('status') not in ('ok','failed'):raise ValueError('status')
            parse_time(d['time_utc'])
            for k in ('files','excluded_count'):
                if k in d and (type(d[k]) is not int or d[k]<0):raise ValueError('count')
            for k in ('changed','remote_verified'):
                if k in d and type(d[k]) is not bool:raise ValueError('flag')
            if d['status']=='ok' and any(k not in d for k in ('files','excluded_count')):raise ValueError('missing count')
            return {'state':'OBSERVED_METADATA_ONLY','source_observation_verified':'LOCAL_RECEIPT_REPORTED_NOT_AUTHENTICATED',
                'provider_verification':'UNKNOWN','freshness':'local-receipt-not-live-scheduler',
                'backup_observation':{'observed_at':datetime.now(timezone.utc).isoformat(),
                    'backup_at':d['time_utc'],'backup_status':d['status'],
                    'files':d.get('files','UNKNOWN'),'excluded_count':d.get('excluded_count','UNKNOWN'),
                    'changed':d.get('changed','UNKNOWN'),'remote_verified_reported':d.get('remote_verified','UNKNOWN')}}
        except (OSError,UnicodeError,ValueError,TypeError,KeyError,LedgerError):raise ObservationUnavailable('local backup receipt unavailable')

def unavailable():
    return {'state':'UNAVAILABLE','provider_verification':'UNKNOWN','schedule_enabled':'UNKNOWN',
            'requested_interval_seconds':300,'last_success_at':'UNKNOWN','registered_projects':'UNKNOWN',
            'destination':'UNKNOWN','backup_started':False}

def map_report(record):
    """Return untrusted metadata only. Caller cannot supply a verification flag."""
    if not isinstance(record,dict) or set(record)!=REQUIRED or type(record['schema_version']) is not int or record['schema_version']!=1:raise BackupReceiptError('invalid metadata')
    for k in ('project_ref','receipt_id','source_ref','base_ref','result_ref','manifest_ref','restore_ref'):
        try:
            value=ident(record[k])
            if k in ('base_ref','result_ref') and re.fullmatch(r'[0-9a-fA-F]+',value):
                # A bare hexadecimal value claims object identity: accept only
                # full lowercase Git SHA-1 or SHA-256, never an ambiguous prefix.
                if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})',value):
                    raise LedgerError('invalid full object reference')
            else:
                safe(value,'list_item')
        except (LedgerError,TypeError):raise BackupReceiptError('invalid reference')
    try:
        observed=parse_time(record['observed_at'])
        if record['last_success_at']!='UNKNOWN' and parse_time(record['last_success_at'])>observed:raise BackupReceiptError('invalid last success')
    except (ValueError,TypeError,LedgerError):raise BackupReceiptError('invalid time')
    status=record['reported_status'];changed=record['content_changed']
    if status not in ('CHECK_NO_CHANGE','BACKUP_SUCCEEDED','BACKUP_FAILED') or type(changed) is not bool:raise BackupReceiptError('invalid state')
    if status=='CHECK_NO_CHANGE' and (changed or record['base_ref']!=record['result_ref'] or record['file_hashes']):raise BackupReceiptError('invalid no-change report')
    if status=='BACKUP_SUCCEEDED' and (not changed or record['manifest_ref']=='UNKNOWN' or record['restore_ref']=='UNKNOWN' or record['last_success_at']=='UNKNOWN' or not record['file_hashes']):raise BackupReceiptError('incomplete backup report')
    if not isinstance(record['file_hashes'],list) or len(record['file_hashes'])>256:raise BackupReceiptError('invalid hashes')
    seen=set()
    for item in record['file_hashes']:
        if not isinstance(item,dict) or set(item)!={'file_ref','sha256'}:raise BackupReceiptError('invalid file reference')
        try:
            ident(item['file_ref']);safe(item['file_ref'],'list_item')
        except (LedgerError,TypeError):raise BackupReceiptError('invalid file reference')
        if item['file_ref'] in seen or not isinstance(item['sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',item['sha256']):raise BackupReceiptError('invalid file hash')
        seen.add(item['file_ref'])
    if not isinstance(record['excluded'],list) or any(not isinstance(x,str) for x in record['excluded']) or not EXCLUSIONS.issubset(set(record['excluded'])):raise BackupReceiptError('incomplete exclusions')
    for item in record['excluded']:
        if item not in EXCLUSIONS:
            try:safe(item,'list_item')
            except (LedgerError,TypeError):raise BackupReceiptError('invalid exclusion reference')
    if not isinstance(record['limitations'],list) or not record['limitations']:raise BackupReceiptError('missing limitations')
    for item in record['limitations']:
        try:
            ident(item);safe(item,'list_item')
        except (LedgerError,TypeError):raise BackupReceiptError('invalid limitation reference')
    return {'state':'UNVERIFIED_REPORT','provider_verification':'UNKNOWN','receipt':dict(record),
            'reported_new_backup':False if status=='CHECK_NO_CHANGE' else 'UNKNOWN',
            'verified_last_success_at':'UNKNOWN','requested_interval_seconds':300,
            'schedule_enabled':'UNKNOWN','backup_started':False}
