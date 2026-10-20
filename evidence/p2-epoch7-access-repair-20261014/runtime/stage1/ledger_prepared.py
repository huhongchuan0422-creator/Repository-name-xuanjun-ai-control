"""Canonical ledger configuration consumption without building the service.

Only the explicit isolated preparation branch uses this format. Normal startup
keeps its ACTIVE, callback UID1004, native/Owner identity and fd3 guards.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from activation_control import ActivationStore

PROFILE = 'ISOLATED_NEW_PREPARE_ONLY'
CONFIG_KEYS = frozenset(('schema','scope','profile','installation_id',
    'activation_descriptor','activation_epoch_journal','activation_lock',
    'activation_config_sha256','release_sha256','binary_sha256','ledger_uuid',
    'generation','instance','db_path','ledger_socket','callback_user',
    'control_repository','source_commit','max_workers'))
PROFILE_KEYS = frozenset(('schema','scope','profile','preparation_uid',
    'config_sha256','sources','binary','operation_id','cp03_receipt_sha256','roles'))


def need(ok, code):
    if not ok: raise ValueError(code)


def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def digest(raw): return hashlib.sha256(raw).hexdigest()


def read(path, maximum=1048576):
    path=Path(path)
    need(path.is_absolute() and '..' not in path.parts,'PREPARED_ABSOLUTE_PATH')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=child
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            need(stat.S_ISREG(before.st_mode) and not before.st_mode & 0o022
                 and before.st_size<=maximum,'PREPARED_FILE_PROTECTION')
            raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
            fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_gid','st_nlink')
            need(all(getattr(before,k)==getattr(after,k) for k in fields)
                 and len(raw)==before.st_size,'PREPARED_FILE_CHANGED')
            return raw
    finally:os.close(parent)


def decode(raw):
    def pairs(rows):
        out={}
        for key,value in rows:
            need(key not in out,'PREPARED_DUPLICATE_FIELD');out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=pairs)


def check_prepared(config_path, profile_path, profile_sha256):
    need(profile_path is not None and profile_sha256 is not None,'PREPARED_PROFILE_REQUIRED')
    profile_raw=read(profile_path)
    need(digest(profile_raw)==profile_sha256,'PREPARED_PROFILE_SHA')
    profile=decode(profile_raw);cfg_raw=read(config_path);cfg=decode(cfg_raw)
    need(set(profile)==PROFILE_KEYS and set(cfg)==CONFIG_KEYS,'PREPARED_FIELDS')
    need(profile['schema']==cfg['schema']==1 and
         profile['scope']==cfg['scope']=='ISOLATED_TEST_ONLY' and
         profile['profile']==cfg['profile']==PROFILE,'PREPARED_SCOPE')
    need(type(profile['preparation_uid']) is int and
         profile['preparation_uid']==os.geteuid(),'PREPARED_SUBJECT')
    need(digest(cfg_raw)==profile['config_sha256'],'PREPARED_CONFIG_SHA')
    here=Path(__file__).resolve().parent
    need(set(profile['sources'])=={'ledger_service.py','ledger_prepared.py','activation_control.py'},
         'PREPARED_SOURCES')
    for name,pin in profile['sources'].items():
        need(digest(read(here/name))==pin,'PREPARED_SOURCE_SHA')
    binary=profile['binary'];need(set(binary)=={'path','bytes','sha256'},'PREPARED_BINARY_FIELDS')
    need(os.path.realpath(sys.executable)==binary['path'],'PREPARED_BINARY_PATH')
    raw=read(binary['path'],32*1024*1024)
    need(len(raw)==binary['bytes'] and digest(raw)==binary['sha256']==cfg['binary_sha256'],
         'PREPARED_BINARY_SHA')
    root=Path(cfg['activation_descriptor']).parent.parent
    production=str(root)=='/var/lib/xuanjun-p2-isolated-test/b3-initialize'
    fixture=str(root).startswith('/tmp/p2-b3-test-') and root.name=='b3-initialize'
    need(production or fixture,'PREPARED_ROOT_SCOPE')
    if production:need(profile['preparation_uid']==1002,'PREPARED_FIXED_SUBJECT')
    paths={'activation_descriptor':root/'activation/active.json',
           'activation_epoch_journal':root/'activation/epochs.jsonl',
           'activation_lock':root/'activation/activation.lock',
           'db_path':root/'data/ledger.sqlite3','ledger_socket':root/'run/ledger.sock'}
    need(all(cfg[k]==str(v) for k,v in paths.items()),'PREPARED_PATH_BINDING')
    receipt_raw=read(root/'commit-receipt.json')
    need(digest(receipt_raw)==profile['cp03_receipt_sha256'],'PREPARED_CP03_SHA')
    receipt=decode(receipt_raw)
    need(receipt['status']=='COMMITTED' and receipt['scope']=='ISOLATED_TEST_ONLY'
         and receipt['origin']=='ISOLATED_NEW' and receipt['full_b3_complete'] is False
         and receipt['installation_id']==cfg['installation_id'],'PREPARED_CP03_IDENTITY')
    need(digest(read(paths['activation_descriptor']))==receipt['descriptor_file_sha256']
         and digest(read(paths['activation_epoch_journal']))==receipt['journal_sha256']
         and cfg['activation_config_sha256']==receipt['config_sha256'],'PREPARED_CP03_BINDING')
    store=ActivationStore(cfg['activation_descriptor'],cfg['activation_epoch_journal'],
                          cfg['activation_lock'],owner_uid=profile['preparation_uid'])
    desc=store.read(require_active=False)
    need(desc['state']=='PREPARED' and desc['epoch']==1,'PREPARED_ACTIVATION_STATE')
    need(all(desc[k]==cfg[k] for k in ('release_sha256','binary_sha256','ledger_uuid',
            'generation','instance','db_path','ledger_socket')) and
         desc['config_sha256']==cfg['activation_config_sha256'],'PREPARED_ACTIVATION_BINDING')
    need(cfg['callback_user']=='xuanjun-callback' and cfg['max_workers']==1 and
         cfg['control_repository']=='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
         and len(cfg['source_commit'])==40,'PREPARED_CONSUMER_POLICY')
    roles={'preparer_uid':profile['preparation_uid'],'service_user':'xuanjun-dispatcher',
           'service_uid':'UNKNOWN','callback_user':'xuanjun-callback','callback_uid':1004,
           'activation_start_owner_uid':0,'socket_activation':'systemd-fd3'}
    need(profile['roles']==roles,'PREPARED_ROLE_SEPARATION')
    need(not os.path.lexists(cfg['db_path']) and not os.path.lexists(cfg['ledger_socket']),
         'PREPARED_UNEXPECTED_RUNTIME_EFFECT')
    # Exact schema contains only one local Unix endpoint and no outbound/TLS
    # configuration. This statement is scoped to this preparation consumer.
    return {'status':'PREPARED_CONFIG_VALIDATED','scope':'ISOLATED_TEST_ONLY',
            'config_sha256':digest(cfg_raw),'profile_sha256':profile_sha256,
            'operation_id':profile['operation_id'],'instance':desc['instance'],
            'activation_state':'PREPARED','service_started':False,
            'database_opened':False,'socket_bound':False,'roles_verified_for_start':False,
            'tls':{'status':'NOT_APPLICABLE','scope':'CANONICAL_LEDGER_UNIX_ENDPOINT_ONLY',
                   'socket':cfg['ledger_socket'],'config_sha256':digest(cfg_raw)},
            'start_requirements':['ACTIVE descriptor','root-owned trusted activation',
               'provisioned separate service/worker/callback identities',
               'native and Owner process verification','systemd fd3',
               'original unit capability and filesystem policy']}
