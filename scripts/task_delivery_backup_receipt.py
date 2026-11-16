"""Display-only candidate for existing backup receipts; never scans or backs up.

No provider, scheduler, credential, destination or writer authority is installed.
A syntactically valid report is not verified source evidence.
"""
import re
from task_delivery_ledger.core import ident,parse_time,safe,LedgerError

EXCLUSIONS=frozenset(('secrets','environment','customer','business_database','raw_logs','cache'))
REQUIRED=frozenset(('schema_version','project_ref','receipt_id','source_ref','reported_status',
    'observed_at','base_ref','result_ref','manifest_ref','restore_ref','last_success_at',
    'content_changed','file_hashes','excluded','limitations'))
class BackupReceiptError(Exception):pass

def unavailable():
    return {'state':'UNAVAILABLE','provider_verification':'UNKNOWN','schedule_enabled':'UNKNOWN',
            'requested_interval_seconds':300,'last_success_at':'UNKNOWN','registered_projects':'UNKNOWN',
            'destination':'UNKNOWN','backup_started':False}

def map_report(record):
    """Return untrusted metadata only. Caller cannot supply a verification flag."""
    if not isinstance(record,dict) or set(record)!=REQUIRED or type(record['schema_version']) is not int or record['schema_version']!=1:raise BackupReceiptError('invalid metadata')
    for k in ('project_ref','receipt_id','source_ref','base_ref','result_ref','manifest_ref','restore_ref'):
        try:
            ident(record[k])
            if k not in ('base_ref','result_ref'):safe(record[k],'list_item')
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
