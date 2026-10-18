"""Review request data and strict fixed-scope input checks. No host operations.
This module never grants permission, emits signatures, or emits execution commands.
"""
import copy
import json
import os
import stat
from pathlib import Path
from scripts.pr122_customer_core import canonical,digest,Denied
from scripts.pr122_customer_workflow import STAGES,RECOVERY,POLICY,hex64,need

MAX_JSON=8_000_000
IMPLEMENTATIONS={
 'PROBE':'scripts/pr122_account_admission/readonly_probe.py',
 'ACCOUNT':'scripts/pr122_account_admission/approved_account_prepare.py',
 'RUNTIME':'scripts/pr122_customer_runtime.py',
 'POLICY_RESTORE':'scripts/pr122_account_admission/domestic_bootstrap.py',
 'CHANNEL_REBIND':'scripts/pr122_customer_channel_upgrade.py',
 'CUSTOMER_APPLY':'scripts/pr122_customer_release.py',
}
STATIC_FIELDS={'publisher_config_sha256','source_tree','artifact_tar_sha256','scope_sha256',
 'review_trust_sha256','telegram_credential_evidence_sha256','state','transaction','manifest_sha256',
 'source_commit','main_current','previous_https_sha256','nginx','config_sha256',
 'runtime_config_sha256','target_acceptance_sha256','production_changes'}
ARTIFACT_FIELDS={'source_commit','source_tree','manifest_sha256','artifact_tar_sha256',
 'artifact_zip_sha256','artifact_id','ci_run_id'}
RUNTIME_FIELDS={'schema','host','source_commit','runtime_module_sha256','wheel_directory',
 'interpreter_sha256','stdlib_trees','native_files','abi','expected_venv_tree','account_uid','account_gid'}


def strict_json(raw):
    need(type(raw) is bytes and len(raw)<=MAX_JSON,'REQUEST_JSON_SIZE')
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out,'REQUEST_DUPLICATE_KEY');out[k]=v
        return out
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError):raise Denied('HOLD:REQUEST_JSON_INVALID') from None


def read_bytes(path,protected=False,code=False):
    """Bounded stable regular-file read; protected input also uses original root path rules."""
    path=Path(path)
    if protected:
        from scripts.pr122_customer_core import private_path
        from scripts.pr122_customer_attempts import protected_directory
        protected_directory(path.parent)
        private_path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=MAX_JSON,'REQUEST_FILE')
        if protected:
            need(before.st_uid==0 and (not before.st_mode&0o022 if code else stat.S_IMODE(before.st_mode)==0o600),
                 'REQUEST_PROTECTED_MODE')
        raw=stream.read(MAX_JSON+1);after=os.fstat(stream.fileno());named=os.lstat(path)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(identity(before)==identity(after)==identity(named),'REQUEST_FILE_CHANGED')
    return raw


def read_json(path,protected=False):
    return strict_json(read_bytes(path,protected=protected))


def source_index(manifest,raw):
    need(type(manifest) is dict and strict_json(raw)==manifest and type(manifest.get('files')) is list,'REQUEST_MANIFEST')
    files={}
    for row in manifest['files']:
        need(type(row) is dict and set(row)=={'path','size','sha256'} and type(row['path']) is str
             and row['path'] not in files and not Path(row['path']).is_absolute()
             and all(p not in ('','.','..') for p in row['path'].split('/'))
             and type(row['size']) is int and row['size']>=0 and hex64(row['sha256']),'REQUEST_MANIFEST_MEMBER')
        files[row['path']]=row
    need(all(p in files for p in IMPLEMENTATIONS.values()),'REQUEST_IMPLEMENTATION_CLOSURE')
    return files


def validate_inputs(plan,inputs,manifest,raw):
    """Pure schema/binding validation. Actual authority and live proof remain original gates."""
    from scripts.pr122_customer_release import TXN
    from scripts.pr122_account_admission import approved_account_prepare as account
    from scripts import pr122_customer_runtime as runtime
    need(type(plan) is dict and set(plan)==STATIC_FIELDS|{'workflow_contract'},'REQUEST_PLAN_SCHEMA')
    static={k:v for k,v in plan.items() if k!='workflow_contract'}
    need(plan['transaction']==TXN and plan['state']=='READONLY_PLAN'
         and type(plan['production_changes']) is int and plan['production_changes']==0,'REQUEST_FIXED_PLAN')
    for key in STATIC_FIELDS:
        if key.endswith('_sha256'):need(hex64(plan[key]),'REQUEST_PLAN_HASH')
    need(plan['source_commit']==manifest['source_commit'] and plan['source_tree']==manifest['source_tree']
         and digest(raw)==plan['manifest_sha256'] and digest(canonical(manifest['files']))==plan['scope_sha256'],
         'REQUEST_SOURCE_BINDING')
    for key in ('source_commit','source_tree'):
        need(type(plan[key]) is str and len(plan[key])==40 and all(c in '0123456789abcdef' for c in plan[key]),'REQUEST_GIT_ID')
    need(type(plan['main_current']) is str and plan['main_current'] and type(plan['nginx']) is dict
         and set(plan['nginx'])=={'master','files'} and type(plan['nginx']['files']) is dict
         and bool(plan['nginx']['files']) and all(type(p) is str and p.startswith('/') and hex64(v) for p,v in plan['nginx']['files'].items()),'REQUEST_LIVE_STATIC_PLAN')
    files=source_index(manifest,raw)
    need(type(inputs) is dict and set(inputs)=={'schema','stages'} and type(inputs['schema']) is int
         and inputs['schema']==1 and type(inputs['stages']) is dict and set(inputs['stages'])==set(STAGES),'REQUEST_INPUTS_SCHEMA')
    from scripts.pr122_customer_workflow import validate_contract
    validate_contract(plan,{'attempt_policy':POLICY,'workflow_contract_sha256':digest(canonical(plan['workflow_contract'])),'max_executions':5})
    for row in plan['workflow_contract']['stages']:
        name=row['stage'];value=inputs['stages'][name]
        need(type(value) is dict and digest(canonical(value))==row['input_sha256']
             and row['implementation_sha256']==files[IMPLEMENTATIONS[name]]['sha256'],'REQUEST_STAGE_BINDING')
    s=inputs['stages'];probe=s['PROBE']
    need(set(probe)=={'receipt_sha256'} and hex64(probe['receipt_sha256'])
         and plan['workflow_contract']['stages'][0]['adopt_receipt_sha256']==probe['receipt_sha256'],'REQUEST_EXISTING_PROBE_REQUIRED')
    a=s['ACCOUNT']
    need(set(a)=={'account','argv_sha256','platform_sha256'} and a['account']==account.ACCOUNT
         and a['argv_sha256']==digest(canonical(list(account.PROPOSED_ARGV))) and hex64(a['platform_sha256']),'REQUEST_FIXED_ACCOUNT')
    r=s['RUNTIME'];need(set(r)=={'runtime_template','account_binding'} and r['account_binding']=='VERIFIED_ACCOUNT_CHECKPOINT','REQUEST_RUNTIME_BINDING')
    t=r['runtime_template'];need(type(t) is dict and set(t)==RUNTIME_FIELDS and type(t['schema']) is int
         and t['schema']==1 and t['host']==runtime.FIXED_HOST and t['source_commit']==plan['source_commit']
         and t['runtime_module_sha256']==files[IMPLEMENTATIONS['RUNTIME']]['sha256']
         and t['account_uid'] is None and t['account_gid'] is None
         and t['interpreter_sha256']==runtime.INTERPRETER_SHA256
         and type(t['wheel_directory']) is str and t['wheel_directory'].startswith('/')
         and '..' not in Path(t['wheel_directory']).parts
         and t['abi']=={'python':'3.11','machine':'x86_64','glibc_min':'2.34'},'REQUEST_RUNTIME_TEMPLATE')
    for key in ('stdlib_trees','native_files','expected_venv_tree'):
        need(type(t[key]) is dict and bool(t[key]),'REQUEST_RUNTIME_CLOSURE_REQUIRED')
    need(all(type(v) is dict and bool(v) and all(hex64(h) for h in v.values()) for v in t['stdlib_trees'].values())
         and all(hex64(h) for h in t['native_files'].values()),'REQUEST_RUNTIME_CLOSURE_HASHES')
    need(set(t['stdlib_trees']) <= {'/usr/lib/python3.11','/usr/lib64/python3.11'},'REQUEST_STDLIB_ROOT')
    for members in t['stdlib_trees'].values():
        for name in members:runtime._relative_runtime_path(name)
    need(all(type(p) is str and '..' not in Path(p).parts and
             any(p.startswith(root) for root in ('/usr/lib/','/usr/lib64/','/lib/','/lib64/'))
             for p in t['native_files']),'REQUEST_NATIVE_PATH')
    aliases={'venv/bin/python3':'python','venv/bin/python3.11':'python','venv/lib64':'lib'}
    for name,member in t['expected_venv_tree'].items():
        runtime._relative_runtime_path(name)
        need(not name.startswith('venv/lib/python3.11/site-packages/') and not name.endswith('.pth')
             and Path(name).name not in ('sitecustomize.py','usercustomize.py'),'REQUEST_VENV_STARTUP_HOOK')
        need(type(member) is dict and member.get('kind') in ('file','directory','symlink'),'REQUEST_VENV_MEMBER')
        if member['kind']=='symlink':
            need(set(member)=={'kind','target'} and name in aliases and member['target']==aliases[name],'REQUEST_VENV_ALIAS')
        else:
            fields={'kind','mode','sha256'} if member['kind']=='file' else {'kind','mode'}
            need(set(member)==fields and type(member['mode']) is int and 0<=member['mode']<=0o777
                 and not member['mode']&0o022,'REQUEST_VENV_MODE')
            if member['kind']=='file':need(hex64(member['sha256']),'REQUEST_VENV_FILE_HASH')
    expected=t['expected_venv_tree']
    need(expected.get('venv/bin/python',{}).get('kind')=='file'
         and expected['venv/bin/python'].get('sha256')==runtime.INTERPRETER_SHA256
         and expected.get('venv/pyvenv.cfg',{}).get('kind')=='file','REQUEST_VENV_REQUIRED_FILES')
    p=s['POLICY_RESTORE']
    need(set(p)=={'transaction','plan_sha256','old_wrapper_sha256','old_policy_sha256'}
         and p['transaction']=='readonly-bootstrap-20261017'
         and all(hex64(p[k]) for k in ('plan_sha256','old_wrapper_sha256','old_policy_sha256')),'REQUEST_FIXED_RESTORE')
    c=s['CHANNEL_REBIND'];need(set(c)=={'plan_sha256','zip_sha256'} and all(hex64(v) for v in c.values()),'REQUEST_CHANNEL_INPUT')
    need(s['CUSTOMER_APPLY']=={'static_plan':static},'REQUEST_CUSTOMER_STATIC_PLAN')
    return True


def make_request(manifest,raw,observations):
    """Always a non-executable review document. Missing facts stay explicitly UNKNOWN."""
    need(type(observations) is dict and set(observations)<= {'static_plan','inputs','artifact','adopt_receipts','recovery_actions'},'REQUEST_OBSERVATION_SCHEMA')
    files=source_index(manifest,raw);missing=[]
    for name in ('static_plan','inputs','artifact','adopt_receipts','recovery_actions'):
        if observations.get(name) is None:missing.append(name)
    def unknown(value,path):
        # Null adopted receipts mean "do not adopt"; null UID/GID explicitly
        # select the future verified ACCOUNT checkpoint, never guessed IDs.
        exempt=path.startswith('adopt_receipts.') or path.endswith(('.account_uid','.account_gid'))
        if not exempt and (value is None or value=='UNKNOWN'):
            if path not in missing:missing.append(path)
        elif type(value) is dict:
            for key,item in value.items():unknown(item,path+'.'+key)
    for key,value in observations.items():unknown(value,key)
    stage_values=observations.get('inputs',{}).get('stages',{}) if type(observations.get('inputs')) is dict else {}
    template=stage_values.get('RUNTIME',{}) if type(stage_values) is dict else {}
    template=template.get('runtime_template',{}) if type(template) is dict else {}
    if type(template) is dict and template:
        for key in ('stdlib_trees','native_files','expected_venv_tree'):
            if not template.get(key):missing.append('inputs.stages.RUNTIME.runtime_template.'+key)
    result={'schema':1,'state':'NOT_EXECUTABLE','permission':'NOT_GRANTED','max_actual_attempts_requested':5,
            'source_commit':manifest['source_commit'],'manifest_sha256':digest(raw),
            'missing_inputs':missing,'plan_candidate':None,'inputs_candidate':None,
            'workflow_contract_sha256':None,'artifact_candidate':None,
            'required_external_acceptance':['INDEPENDENT_CUSTODY_AND_SIGNED_WHOLE_SCOPE','OWNER_EXACT_INSTALL_APPROVAL',
                'PROTECTED_BOOTSTRAP_PYTHON_AND_CRYPTOGRAPHY_IDENTITY',
                'FRESH_TRUSTED_PROBE_RECEIPT','TARGET_RUNTIME_SOURCE_AND_VENV_CLOSURE',
                'PROTECTED_CONFIG_RUNTIME_PUBLISHER_AND_12_ACCEPTANCE_RECORDS','LIVE_POLICY_CHANNEL_STATIC_PLAN'],
            'successful_history':'N1_AND_E1_RETAINED_NOT_REEXECUTED'}
    if missing:return result
    static=copy.deepcopy(observations['static_plan']);inputs=copy.deepcopy(observations['inputs'])
    adoption=observations['adopt_receipts'];actions=observations['recovery_actions'];artifact=observations['artifact']
    need(type(adoption) is dict and set(adoption)==set(STAGES) and type(actions) is dict and set(actions)==set(STAGES),'REQUEST_STAGE_OPTIONS')
    need(type(inputs) is dict and type(inputs.get('stages')) is dict and set(inputs['stages'])==set(STAGES),'REQUEST_STAGE_INPUTS')
    for name in STAGES:
        if inputs['stages'][name] is None:missing.append('inputs.stages.'+name)
    if missing:return result
    need(type(static) is dict and set(static)==STATIC_FIELDS,'REQUEST_STATIC_PLAN_FIELDS')
    contract={'schema':1,'stages':[{'stage':name,'input_sha256':digest(canonical(inputs['stages'][name])),
              'implementation_sha256':files[IMPLEMENTATIONS[name]]['sha256'],
              'adopt_receipt_sha256':adoption[name],'recovery_actions':copy.deepcopy(actions[name])} for name in STAGES]}
    plan={**static,'workflow_contract':contract}
    validate_inputs(plan,inputs,manifest,raw)
    need(type(artifact) is dict and set(artifact)==ARTIFACT_FIELDS,'REQUEST_ARTIFACT_SCHEMA')
    need(all(artifact[k]==plan[k] for k in ('source_commit','source_tree','manifest_sha256','artifact_tar_sha256'))
         and hex64(artifact['artifact_zip_sha256']) and artifact['artifact_zip_sha256']==inputs['stages']['CHANNEL_REBIND']['zip_sha256']
         and all(type(artifact[k]) is int and artifact[k]>0 for k in ('artifact_id','ci_run_id')),'REQUEST_ARTIFACT_BINDING')
    result.update(plan_candidate=plan,inputs_candidate=inputs,workflow_contract_sha256=digest(canonical(contract)),
                  artifact_candidate=copy.deepcopy(artifact))
    return result


def read_review_source(folder):
    """Offline byte validation only. Never imports or executes candidate files."""
    folder=Path(folder)
    need(folder.is_dir() and not folder.is_symlink(),'REQUEST_SOURCE_DIRECTORY')
    def read(name):
        p=folder/name
        need(not p.is_symlink() and p.is_file(),'REQUEST_SOURCE_FILE')
        for parent in p.parents:
            if parent==folder:break
            need(not parent.is_symlink(),'REQUEST_SOURCE_PARENT')
        with os.fdopen(os.open(p,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
            info=os.fstat(stream.fileno());need(stat.S_ISREG(info.st_mode) and info.st_size<=MAX_JSON,'REQUEST_SOURCE_SIZE')
            raw=stream.read(MAX_JSON+1);need(len(raw)<=MAX_JSON,'REQUEST_SOURCE_SIZE');return raw
    raw=read('CUSTOMER_MANIFEST.json');manifest=strict_json(raw);index=source_index(manifest,raw)
    for name,row in index.items():
        body=read(name);need(len(body)==row['size'] and digest(body)==row['sha256'],'REQUEST_SOURCE_HASH')
    return manifest,raw
