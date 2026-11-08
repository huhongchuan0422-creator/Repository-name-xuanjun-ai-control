"""Fixed wrapper pin/compressor and strict metadata-only receipt reducer."""
import base64, hashlib, json, zlib
from pathlib import Path
WRAPPER_NAME='p2_uk_stage_a_admission_readonly.sh'
WRAPPER_BYTES=16975
WRAPPER_SHA256='c7e89857aa94edd6afa02a3f0d361155a293e4a8c124044e02e7783363649a8d'
MAX_COMMAND_CONTENT=16384
MAX_OUTPUT_BYTES=16384
TOP_FIELDS={'scope','host_matches','euid','egid','sudo_uid_1000','writes','network','product_imports','stage_a_executed','db_rows_read','worker','config','binding','frozen_root','queue','state','read_bytes'}
HOLD_STATES={'DEADLINE_HOLD','HOST_OR_SUDO_IDENTITY_HOLD','SAFE_ERROR_HOLD','OUTPUT_BOUND_HOLD'}
class AdmissionHold(ValueError): pass
def need(ok,reason='ADMISSION_RECEIPT_REJECTED'):
    if not ok: raise AdmissionHold(reason)
def unique_pairs(pairs):
    out={}
    for k,v in pairs:
        need(k not in out,'DUPLICATE_JSON_KEY'); out[k]=v
    return out
def wrapper_bytes(base_dir):
    raw=(Path(base_dir)/WRAPPER_NAME).read_bytes()
    need(len(raw)==WRAPPER_BYTES and hashlib.sha256(raw).hexdigest()==WRAPPER_SHA256,'ADMISSION_WRAPPER_PIN_MISMATCH')
    return raw
def command_content(base_dir):
    raw=wrapper_bytes(base_dir)
    encoded=base64.b64encode(zlib.compress(raw,9)).decode('ascii')
    command="#!/bin/sh\nset -eu\nprintf '%s' '"+encoded+"' | /usr/bin/base64 -d | /usr/bin/python3 -I -B -c 'import sys,zlib;sys.stdout.buffer.write(zlib.decompress(sys.stdin.buffer.read()))' | /bin/bash\n"
    need(len(command.encode())<=MAX_COMMAND_CONTENT,'COMMAND_CONTENT_BOUND')
    return command
def validate_action_contract(action, request, binding):
    contracts={'b5-admission':('B5_STAGE_A_ADMISSION_METADATA_ONLY','B5_ADMISSION_METADATA_ONLY'),'b5-admission-query':('B5_STAGE_A_ADMISSION_METADATA_ONLY','B5_ADMISSION_QUERY')}
    need(action in contracts,'B5_ACTION_NOT_ALLOWED')
    purpose,operation=contracts[action]
    need(type(request) is dict and request.get('purpose')==purpose,'B5_PURPOSE_MISMATCH')
    need(type(binding) is dict and binding.get('operation')==operation and binding.get('attempt')==request.get('attempt'),'B5_BINDING_MISMATCH')
    return True
def _identity(v): return type(v) is list and len(v)==9 and all(type(n) is int and n>=0 for n in v)
OBS_STATES={'OBSERVED','ABSENT','PRESENT','CURRENT_UNSAFE','CURRENT_CHANGED',
 'NOT_OBSERVED_PERMISSION','NOT_OBSERVED_SAFE_ERROR','UNKNOWN_RELEASE_NOT_READ',
 'ROOT_UNSAFE','ROOT_CHANGED','FILE_UNSAFE','PARENT_UNSAFE','READ_BUDGET',
 'NOATIME_UNAVAILABLE','IDENTITY_CHANGED','JSON_DUPLICATE','JSON_NONFINITE',
 'JSON_SHAPE','OUTPUT_BOUND_HOLD','FILE_UNSAFE','NOATIME_UNAVAILABLE'}
RELEASES={'e78bd7749414d1637012f57b65d2019955282fc3','f0fe0d3978b72a11e4fa4cfb9928424d60124940'}
def _sha(v): return type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v)
def _nullable_sha(v): return v is None or _sha(v)
def _bool(v): return type(v) is bool
def _nonnegative(v): return type(v) is int and v>=0
def _obs(v):
    need(type(v) is dict and type(v.get('state')) is str and v['state'] in OBS_STATES,'OBSERVATION_STATE')
    return v

def _metadata(kind,v):
    _obs(v)
    state=v['state']
    if kind=='worker' and state=='UNKNOWN_RELEASE_NOT_READ':
        need(set(v)=={'state','current_identity','target_sha256'} and _identity(v['current_identity']) and _sha(v['target_sha256']),'WORKER_UNKNOWN_RELEASE_FIELDS')
    elif state!='OBSERVED':
        need(set(v)=={'state'},'OBSERVATION_EXTRA_FIELDS')
    elif kind=='worker':
        keys={'state','current_identity','release','source_files_read','nine_file_pin','candidate_twelve_file_pin','active_process'}
        need(set(v)==keys and _identity(v['current_identity']) and v['release'] in RELEASES
             and type(v['source_files_read']) is int and 0<=v['source_files_read']<=12
             and _nullable_sha(v['nine_file_pin']) and _nullable_sha(v['candidate_twelve_file_pin'])
             and v['active_process']=='UNKNOWN_NOT_QUERIED','WORKER_METADATA_FIELDS')
    elif kind=='config':
        keys={'state','identity','sha256','executor_sha256','actor_matches','state_root_matches','github_owner_matches','b5_hook_present','website_hook_present','b5_hook_reference_matches','b5_hook_sha256'}
        need(set(v)==keys and _identity(v['identity']) and _sha(v['sha256']) and _nullable_sha(v['executor_sha256']) and _nullable_sha(v['b5_hook_sha256'])
             and all(_bool(v[k]) for k in ('actor_matches','state_root_matches','github_owner_matches','b5_hook_present','website_hook_present','b5_hook_reference_matches')),'CONFIG_METADATA_FIELDS')
    elif kind=='binding':
        keys={'state','identity','sha256','project_matches','target_matches','operation_matches','execution_identity_matches','v3_sha_matches','request_id_present','valid_from','valid_until','single_consumption'}
        need(set(v)==keys and _identity(v['identity']) and _sha(v['sha256'])
             and all(_bool(v[k]) for k in ('project_matches','target_matches','operation_matches','execution_identity_matches','v3_sha_matches','request_id_present'))
             and all(v[k] is None or type(v[k]) is int for k in ('valid_from','valid_until'))
             and v['single_consumption']=='UNKNOWN_NOT_QUERIED','BINDING_METADATA_FIELDS')
    elif kind=='frozen_root':
        keys={'state','root_identity','expected','matched','missing','mismatched','unobserved','all_3_metadata_14_controller_42_runtime_match'}
        need(set(v)==keys and _identity(v['root_identity']) and type(v['expected']) is int and v['expected']==59
             and all(_nonnegative(v[k]) for k in ('matched','missing','mismatched','unobserved'))
             and sum(v[k] for k in ('matched','missing','mismatched','unobserved'))==59
             and _bool(v['all_3_metadata_14_controller_42_runtime_match'])
             and v['all_3_metadata_14_controller_42_runtime_match']==(v['matched']==59),'FROZEN_ROOT_METADATA_FIELDS')
    else: raise AdmissionHold('UNKNOWN_METADATA_KIND')
    return dict(v)

def _base(v):
    base={'scope','host_matches','euid','egid','sudo_uid_1000','writes','network','product_imports','stage_a_executed','db_rows_read','state','read_bytes'}
    need(base.issubset(v) and v['scope']=='UK_STAGE_A_ADMISSION_METADATA_ONLY'
         and all(_bool(v[k]) for k in ('host_matches','sudo_uid_1000','writes','network','product_imports','stage_a_executed'))
         and type(v['euid']) is int and type(v['egid']) is int
         and v['writes'] is False and v['network'] is False and v['product_imports'] is False
         and v['stage_a_executed'] is False and type(v['db_rows_read']) is int and v['db_rows_read']==0
         and type(v['read_bytes']) is int and 0<=v['read_bytes']<=2097152,'BASE_METADATA_FIELDS')
    return base
def _queue(v):
    need(type(v) is dict and set(v)=={'state','sqlite_connected','conflicts','rows_read','main','wal','shm','journal'},'QUEUE_FIELDS')
    need(v['state']=='METADATA_ONLY' and v['sqlite_connected'] is False and v['conflicts']=='UNKNOWN_DB_NOT_OPENED' and type(v['rows_read']) is int and v['rows_read']==0,'QUEUE_NOT_METADATA_ONLY')
    for k in ('main','wal','shm','journal'):
        item=_obs(v[k])
        if item['state']=='PRESENT':
            need(set(item)=={'state','identity','regular','historical_db_identity_matches'} and _identity(item['identity']) and type(item['regular']) is bool and (item['historical_db_identity_matches'] is None or type(item['historical_db_identity_matches']) is bool) and (k=='main' or item['historical_db_identity_matches'] is None),'QUEUE_FILE_METADATA')
        else: need(set(item)=={'state'},'QUEUE_ABSENT_FIELDS')
def safe_receipt(output, outer_exit_code):
    """Outer shell can exit zero after printing EXIT_CODE; validate both layers."""
    need(type(outer_exit_code) is int and outer_exit_code==0,'OUTER_EXIT_CODE')
    need(type(output) is str and len(output.encode('utf-8'))<=MAX_OUTPUT_BYTES and '\r' not in output and '\x00' not in output,'OUTPUT_BOUND')
    # The pinned wrapper emits JSON, one blank line, then EXIT_CODE=N.
    # Accept only that exact three-line envelope; no stderr or extra output.
    lines=output.splitlines()
    need(len(lines)==3 and lines[1]=='' and lines[2] in ('EXIT_CODE=0','EXIT_CODE=2'),'OUTPUT_ENVELOPE')
    try: v=json.loads(lines[0],object_pairs_hook=unique_pairs,parse_constant=lambda _:(_ for _ in ()).throw(AdmissionHold('NONFINITE_JSON')))
    except Exception: raise AdmissionHold('OUTPUT_JSON') from None
    need(type(v) is dict,'TOP_FIELDS')
    inner=int(lines[2].split('=',1)[1])
    if inner==2:
        # HOLD paths intentionally emit only a minimal state object on output-bound
        # failure; other holds retain the complete metadata envelope.
        if v.get('state')=='OUTPUT_BOUND_HOLD':
            need(set(v)=={'state'},'HOLD_ENVELOPE_MISMATCH')
        else:
            hold_fields=_base(v)
            need(v['state'] in HOLD_STATES,'HOLD_STATE')
            order=('worker','config','binding','frozen_root','queue')
            present=tuple(k for k in order if k in v)
            need(set(v)==hold_fields|set(present) and present==order[:len(present)],'HOLD_ENVELOPE_MISMATCH')
            if v['state']=='HOST_OR_SUDO_IDENTITY_HOLD':
                need(not present,'HOST_HOLD_PREFIX')
            for k in present:
                if k=='queue':_queue(v[k])
                else:_metadata(k,v[k])
        return {'state':'B5_ADMISSION_HOLD','inner_exit_code':2,'hold_reason':v['state'],'redispatch_allowed':False,'install_authorized':False,'stage_a_pass':False,'output_sha256':hashlib.sha256(output.encode()).hexdigest()}
    need(set(v)==TOP_FIELDS,'TOP_FIELDS')
    _base(v)
    need(v['state']=='OBSERVED_REVIEW_REQUIRED','SUCCESS_STATE')
    need(v['scope']=='UK_STAGE_A_ADMISSION_METADATA_ONLY' and v['host_matches'] is True
         and type(v['euid']) is int and v['euid']==0 and type(v['egid']) is int and v['egid']==0
         and v['sudo_uid_1000'] is True and v['writes'] is False and v['network'] is False
         and v['product_imports'] is False and v['stage_a_executed'] is False
         and type(v['db_rows_read']) is int and v['db_rows_read']==0
         and type(v['read_bytes']) is int and 0<=v['read_bytes']<=2097152,'IDENTITY_OR_SCOPE')
    for k in ('worker','config','binding','frozen_root'): _metadata(k,v[k])
    _queue(v['queue'])
    # This is a metadata observation requiring human review, not a Stage-A pass.
    return {'state':'OBSERVED_REVIEW_REQUIRED','inner_exit_code':0,'host_matches':True,'euid':0,'egid':0,'sudo_uid_1000':True,'writes':False,'network':False,'product_imports':False,'stage_a_executed':False,'db_rows_read':0,'read_bytes':v['read_bytes'],'worker_state':v['worker']['state'],'config_state':v['config']['state'],'binding_state':v['binding']['state'],'frozen_root_state':v['frozen_root']['state'],'queue_state':v['queue']['state'],'sqlite_connected':False,'queue_metadata':v['queue'],'worker_metadata':_metadata('worker',v['worker']),'config_metadata':_metadata('config',v['config']),'binding_metadata':_metadata('binding',v['binding']),'frozen_root_metadata':_metadata('frozen_root',v['frozen_root']),'redispatch_allowed':False,'stage_a_pass':False,'install_authorized':False,'output_sha256':hashlib.sha256(output.encode()).hexdigest()}
