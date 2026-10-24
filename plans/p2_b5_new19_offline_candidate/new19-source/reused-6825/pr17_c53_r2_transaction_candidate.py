"""PR17 R2 c53 successor: reviewed OFFLINE transaction binder, never a live runner.

Safety: no os, subprocess, sqlite, networking, timers, locks, services or filesystem
mutations. Values for authorization/ACK, live source bytes, slot backups and runtime
observations must be independently supplied through separately approved channels.
This module cannot grant consent, authenticate evidence, enroll roots or invoke jobs.
"""
import hashlib
import json
import re

SPEC_SHA256 = '11aff4749d18ee6f4987d5f31934ce8bd535e6fd5ba13e2a07716773df4145b4'
ORIGINAL_R2_SHA256 = '64bf564b1178f2c2746254163fa361d2d7d788e1b7d5b82698301e870ff14843'
ORIGINAL_DRAFT_SHA256 = '0714fe90c385d6e66712a765843130cee393ad2590d00d47358582405ffd5ee9'
COMMIT = 'c53cefd986718ebcfa34296d70ad4e0defd1f8fb'
MANIFEST = 'e528eea2f8d5be5f6214ec85d914c3bcb9905be40669ce06b9a77d2b5736d76f'
CODEPIN = '53e8e0ba5a86b647e282a786f1330788fb88b5715a46d239982ec13963921043'
E78_PIN = 'f85fdb173b93729ee070ee4285d8ece4d85499b3dd8e4ac7c9894a9ce6058cee'
E78_MANIFEST = '10ff7a1ace9d81be347b98611f6e970c3b7f7529d0b88ec4b305bd64cc5b013c'
RESOURCE_SHA = '811fb18285087c1c281b0e4008de06281c5b57a39193f0b41f8bbbd3115918bc'
SOURCE_PRODUCER = '7c12b368b3586ba0b2d1f91498d8f9f4ed2d95b5'
ACTOR = 'github:332398908'
RECIPIENT = 'github-332398908'
PROJECT = 'p2-b5-material-analysis'
CERT = '/opt/xuanjun-cloud-oauth/venv/lib/python3.12/site-packages/certifi/cacert.pem'
HOST = 'iZd7oeikknn1z21sq6ji6zZ'
ETC = '/etc/xuanjun-cloud-executor'
BIND = ETC + '/approved-objects-binding.json'
CATALOG = ETC + '/b5-material-catalog.json'
CUSTODY = ETC + '/material-custody.json'
DEST = '/var/lib/xuanjun-cloud-connection/b5-material-custody'
MANIFEST_PATH = 'deployment/cloud-connection/oauth/SOURCE_MANIFEST.json'
SCOPE_SHA256 = '8a56b57cc58a06235b26ff5cbae94a785d872e719939bc4b8797f7e1894419b8'
ARCHIVE_ROOT = '/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002'
PACKAGE_ROOT = '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
ARCHIVE_PREFIX = 'home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/'
ARCHIVE_SHA = 'e6d3a3cef96ee996eb4b130fb0bd9305438489326b85678a263998602413e485'
ARCHIVE_IDENTITY = (64771,1845773,33152,1002,1002,1,559237632,1792487297836456594,1792487297836456594)
PIN_ORDER = ('queue.py','worker.py','runtime.py','private_transfer.py','credential_lifecycle.py','fixed_actions.py','pr122_baseline_collector.py','archive_reader.py','material_custody.py')
SHA = re.compile(r'[0-9a-f]{64}\Z')
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')

class Hold(ValueError):
    pass

def require(ok, code):
    if not ok: raise Hold(code)

def sha(raw):
    require(type(raw) is bytes, 'RAW_BYTES_REQUIRED')
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,'DUPLICATE_JSON_KEY')
        out[k]=v
    return out

def strict_json(raw, limit=262144):
    require(type(raw) is bytes and len(raw)<=limit,'JSON_SIZE')
    try:
        result=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Hold('NONFINITE_JSON')))
    except Hold: raise
    except (ValueError,UnicodeError,TypeError): raise Hold('JSON_FORMAT') from None
    require(type(result) is dict,'JSON_TOPLEVEL')
    return result

def verify_spec_bytes(raw):
    require(sha(raw)==SPEC_SHA256,'SPEC_SHA_CHANGED')
    s=strict_json(raw)
    require(s.get('schema')=='PR17_C53_R2_STATIC_TRANSACTION_V1','SPEC_SCHEMA')
    require(s['host']==HOST and s['source']['target_release']==COMMIT and s['source']['target_manifest_sha256']==MANIFEST and s['source']['target_code_pin']==CODEPIN,'TARGET_VERSION')
    require(s['provenance']=={'r2_bytes':62278,'r2_sha256':ORIGINAL_R2_SHA256,'draft_bytes':23124,'draft_sha256':ORIGINAL_DRAFT_SHA256},'ORIGINAL_SOURCE_BINDING')
    require(s['batch']['request_ids_reserved'] is False and s['batch']['remote_requests_created']==0 and s['batch']['window_started_at'] is None,'BATCH_NOT_UNRESERVED')
    require(s['actor']=={'subject':ACTOR,'recipient':RECIPIENT,'project':PROJECT,'operation':'fetch_approved_object'},'ACTOR_BINDING')
    require(len(s['objects'])==19 and len(s['batch']['draft_request_ids'])==19,'OBJECT_COUNT')
    require(len(set(s['batch']['draft_request_ids']))==19 and all(TOKEN.fullmatch(x) for x in s['batch']['draft_request_ids']),'REQUEST_IDS_INVALID')
    require(all(not x.startswith('l2-b5-b5-material-e78-20261023-') for x in s['batch']['draft_request_ids']),'SEALED_E78_REQUEST_REUSE')
    require(sum(x['bytes'] for x in s['objects'])==93592 and sum(x['bytes'] for x in s['objects'][:5])==59128 and sum(x['bytes'] for x in s['objects'][5:])==34464,'OBJECT_SIZE_SCOPE')
    require(len(s['source']['source_records'])==32,'SOURCE_RECORD_COUNT')
    records={x['path']:x for x in s['source']['source_records']}
    require(len(records)==32,'SOURCE_PATH_DUPLICATE')
    require(all(type(x['bytes']) is int and x['bytes']>0 and SHA.fullmatch(x['sha256']) and x['mode']=='0644' for x in records.values()),'SOURCE_RECORD_INVALID')
    pin=sha(canonical([[n,records['production/cloud_connection/'+n]['sha256']] for n in PIN_ORDER]))
    require(pin==CODEPIN,'SOURCE_CODE_PIN_MISMATCH')
    observed=s['observed_baseline']
    expected_slots={BIND:'10c15a68eafab6e7b46aa3e3e0a4dc1ec4050cd321572e917fbe84c0c858f70f',CUSTODY:'c9fd701097dece1d05994c8cb862bd480cd970a4a09015c3876fe6c8e23b05a7',CATALOG:'f40b9429d72a4f55428aef139617b4a071a61c172e5395fb3d93e610539456e4'}
    require(all(observed['files'][p]['sha256']==digest for p,digest in expected_slots.items()),'SLOTS_BASELINE_NOT_PRESENT')
    require(observed['receiver']['contents_unknown'] is True and observed['db']['queue_conflicts']=='UNKNOWN','UNKNOWN_PROTECTION')
    require(s['preconditions']['current_grant']=='UNKNOWN' and s['preconditions']['analyst_ack']=='UNKNOWN','AUTHORITY_CANNOT_PREAPPROVE')
    require(s['paths_reserved'] is False,'PATH_RESERVATION_FABRICATED')
    require(s['closeout']['current_received_count']==0 and s['closeout']['p2_installation'] is False,'RECEIPT_INSTALL_FABRICATION')
    return s

def verify_supplied_source(s, blobs):
    """Only when all 32 source bodies + c53 manifest are separately supplied.

    Does NOT retrieve source, read archive, generate a grant or perform IO.
    """
    require(type(blobs) is dict,'SOURCE_INPUT_TYPE')
    records={x['path']:x for x in s['source']['source_records']}
    require(set(blobs)==set(records)|{MANIFEST_PATH},'SOURCE_32_PLUS_MANIFEST_REQUIRED')
    manifest=strict_json(blobs[MANIFEST_PATH])
    require(sha(blobs[MANIFEST_PATH])==MANIFEST,'SOURCE_MANIFEST_SHA')
    require(type(manifest.get('files')) is list and len(manifest['files'])==32,'SOURCE_MANIFEST_COUNT')
    for entry in manifest['files']:
        require(type(entry) is dict,'SOURCE_ENTRY_SHAPE')
        path=entry.get('path')
        require(path in records,'SOURCE_ENTRY_PATH')
        expected=records[path]
        require(all(entry.get(k)==expected[k] for k in ('path','bytes','sha256','mode')),'SOURCE_ENTRY_MISMATCH')
    for path,entry in records.items():
        require(type(blobs[path]) is bytes and len(blobs[path])==entry['bytes'] and sha(blobs[path])==entry['sha256'],'SOURCE_BYTES_CHANGED')
    rows=[[n,sha(blobs['production/cloud_connection/'+n])]for n in PIN_ORDER]
    require(sha(canonical(rows))==CODEPIN,'SOURCE_CODE_PIN_FAILED')
    return {'state':'SOURCE_VERIFIED_FROM_SUPPLIED_BYTES_ONLY','raw_source_count':33,'manifest_sha256':MANIFEST,'code_pin':CODEPIN}

def eligible_for_live_transaction(s, evidence):
    """Conservative static admission: external proof is necessary, not sufficient.

    The input data cannot authenticate actual OAuth consent, analyst signatures,
    worker/lock state, backup consistency or grant ownership. Even all True
    cannot be elevated to live permission by this function.
    """
    require(type(evidence) is dict,'EVIDENCE_TYPE')
    unresolved=[]
    for key in ('grant_actual','recipient_authenticated','analyst_ack_signed',
                'batch_id_reserved','nineteen_ids_absent_under_original_lock',
                'worker_stop_confirmed','same_original_lock_held',
                'queue_and_outbox_conflicts_cleared','old_policy_nonterminal_cleared',
                'fixed_target_conflicts_cleared','three_slots_backed_up_exact',
                'connection_resource_env_backed_up_exact','current_links_backed_up_exact',
                'full_c53_source_bytes_verified','new_worker_attempt_checkpoint_durable'):
        if evidence.get(key) is not True: unresolved.append(key)
    return {'state':'HOLD_INDEPENDENT_LIVE_ADMISSION','unresolved':unresolved,
            'not_live_execution_permission':True,
            'note':'These assertions are unauthenticated offline inputs; require independent channel and per-stage real verification.'}

def fixed_phase_names(s):
    return [step['phase'] for step in s['phase_sequence']]

def rollback_classification(*, worker_start_attempted, state_unknown, no_new_operations_proven):
    """Pure boundary decision; never actually rolls back an OS object."""
    if not (worker_start_attempted is False and state_unknown is False and no_new_operations_proven is True):
        return {'state':'HOLD_C53_FAIL_CLOSED','allow_e78_rollback':False,'allow_database_rollback':False,
                'action':'PRESERVE_HISTORY_CLOSE_B5_EXPOSURE_BOUNDED_STOP_NO_OLD_WORKER'}
    return {'state':'PRE_WORKER_RESTORE_MAY_BE_REVIEWED','allow_e78_rollback':True,
            'allow_database_rollback':False,'action':'EXACT_SAME_TRANSACTION_BACKUPS_ONLY_AFTER_VERIFIED_NO_NEW_OPERATIONS'}

def report(spec_raw):
    s=verify_spec_bytes(spec_raw)
    return {'state':'REVIEW_ONLY_HOLD','source_commit':COMMIT,'source_manifest':MANIFEST,
            'code_pin':CODEPIN,'host':HOST,'object_count':len(s['objects']),
            'source_records':len(s['source']['source_records']),
            'batch_ids_frozen_draft_only':len(s['batch']['draft_request_ids']),
            'batch_ids_reserved':False,'actual_grant':'UNKNOWN','analyst_ack':'UNKNOWN',
            'original_queue_lock':'NOT_ACQUIRED','c53_source_raw':'NOT_SUPPLIED',
            'worker_start':'NOT_ATTEMPTED','new_requests':0,'received':0,'installation':'NOT_EXECUTED',
            'phases':fixed_phase_names(s)}

if __name__=='__main__':
    # Intentionally no command-line entry point, no implicit local file access.
    raise SystemExit('REVIEW_ONLY_NOT_A_LIVE_TRANSACTION')
