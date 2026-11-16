"""Fixed deployment scopes. No permission, credential or execution machinery."""
from scripts.pr122_customer_core import Denied
import base64
import json
import math
from pathlib import PurePosixPath
import re
FULL='FULL'
LOGIN_ONLY='OFFICIAL_LOGIN_ONLY_V1'
INITIAL_LOGIN='FIRST_LOGIN_ONLY_V1'
INITIAL_TARGET='iZvt5t8tlrm8oiZ'
IDENTITY_SUBJECT='CANONICAL_IDENTITY_INVENTORY'
IDENTITY_DECISION='NO_EXISTING_AUTHORITATIVE_IDENTITY'
WINDOW_SECONDS=18000
LOGIN_ACCEPTANCE=('canonical_identity_mapping','key_backup_recovery',
                  'smtp_verified_account_recovery','login_session_security')

def need(ok,code):
    if not ok:raise Denied('HOLD:'+code)

def profile(config):
    need(type(config) is dict,'DEPLOYMENT_CONFIG')
    value=config.get('deployment_profile',FULL)
    need(type(value) is str and value in (FULL,LOGIN_ONLY),'DEPLOYMENT_PROFILE')
    return value

def validate_pair(config,runtime):
    value=profile(config)
    initialization_mode(config)
    need(profile(runtime)==value,'DEPLOYMENT_PROFILE_BINDING')
    if value==LOGIN_ONLY:
        for obj in (config,runtime):
            providers=obj.get('providers')
            need(type(providers) is dict and set(providers)=={'smtp'} and bool(providers['smtp']),
                 'LOGIN_SMTP_ONLY_REQUIRED')
    return value

def initialization_mode(config):
    """Admin provenance/scope only, never a statement that a live target is empty."""
    selected=profile(config)
    if 'initialization_mode' not in config:return None
    need(type(config['initialization_mode']) is str and config['initialization_mode']==INITIAL_LOGIN
         and selected==LOGIN_ONLY,'INITIALIZATION_MODE')
    need('authority_verify_key' not in config,'INITIAL_AUTHORITY_FORBIDDEN')
    return INITIAL_LOGIN

def validate_admin_keys(config):
    """No-authority shape is explicit; legacy/FULL key requirements are retained."""
    initial=initialization_mode(config)==INITIAL_LOGIN
    def key(value):
        try:
            need(type(value) is str and len(base64.b64decode(value,validate=True))==32,
                 'PROTECTED_KEYS_REQUIRED')
        except (ValueError,TypeError):raise Denied('HOLD:PROTECTED_KEYS_REQUIRED') from None
    keys=config.get('keys')
    need(type(keys) is dict and bool(keys) and type(config.get('active_key')) is str
         and config['active_key'] in keys,'DATA_KEY_MAPPING')
    for value in keys.values():key(value)
    key(config.get('backup_key'))
    need(bool(config.get('backup_key_ref')),'DATA_KEY_MAPPING')
    if initial:
        need(type(config['backup_key_ref']) is str and 0<len(config['backup_key_ref'])<=1024
             and not any(ord(c)<32 or ord(c)==127 for c in config['backup_key_ref']),
             'DATA_KEY_MAPPING')
        backup=base64.b64decode(config['backup_key'],validate=True)
        need(all(backup!=base64.b64decode(value,validate=True) for value in keys.values()),
             'INITIAL_KEY_SEPARATION')
    else:key(config.get('authority_verify_key'))
    return True

def first_evidence_path(value):
    """Lexical namespace check before the existing protected stable-file reader."""
    try:
        need(type(value) is str,'INITIAL_EVIDENCE_PATH')
        value.encode('utf-8',errors='strict')
    except UnicodeError:raise Denied('HOLD:INITIAL_EVIDENCE_PATH') from None
    need(type(value) is str and value.startswith('/var/lib/xuanjun-customer-preflight/')
         and '\\' not in value and not any(ord(c)<32 or ord(c)==127 for c in value)
         and all(part not in ('','.','..') for part in value.split('/')[1:])
         and str(PurePosixPath(value))==value,'INITIAL_EVIDENCE_PATH')
    return value

def _first_identity_header(record,manifest_sha256,now):
    fields={'schema','target','deployment_profile','initialization_mode','manifest_sha256',
            'target_state','identity_decision','observation_ref','observation_sha256','observed_unix'}
    hex64=lambda value:type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
    need(type(record) is dict and set(record)==fields,'INITIAL_IDENTITY_SCHEMA')
    try:json.dumps(record,ensure_ascii=False,allow_nan=False).encode('utf-8',errors='strict')
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError):
        raise Denied('HOLD:INITIAL_IDENTITY_SCHEMA') from None
    need(all(type(record[name]) is str for name in fields-{'schema','observed_unix'}),
         'INITIAL_IDENTITY_SCHEMA')
    need(type(record['schema']) is int and record['schema']==1
         and record['target']==INITIAL_TARGET and record['deployment_profile']==LOGIN_ONLY
         and record['initialization_mode']==INITIAL_LOGIN,'INITIAL_IDENTITY_SCOPE')
    need(record['target_state']=='ABSENT' and record['identity_decision']==IDENTITY_DECISION,
         'INITIAL_IDENTITY_NOT_FRESH')
    need(hex64(manifest_sha256) and record['manifest_sha256']==manifest_sha256
         and hex64(record['observation_sha256']),'INITIAL_IDENTITY_BINDING')
    first_evidence_path(record['observation_ref'])
    observed=record['observed_unix']
    need(type(observed) is int and observed>=0 and type(now) in (int,float)
         and (type(now) is int or math.isfinite(now)) and observed<=now
         and now-observed<=WINDOW_SECONDS,'INITIAL_OBSERVATION_AGE')
    return True

def validate_first_identity_record(record,observation,*,manifest_sha256,now):
    """Schema/scope/header binding only. Source authenticity needs the original gates.

    The protected caller separately verifies the source's exact raw-byte digest.
    OS account absence does not establish platform canonical-identity absence.
    """
    _first_identity_header(record,manifest_sha256,now)
    # strict_json rejects NaN literals; valid numeric spellings such as 1e999
    # can still overflow to infinity. Validate the entire retained source body.
    try:json.dumps(observation,ensure_ascii=False,allow_nan=False).encode('utf-8',errors='strict')
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError):
        raise Denied('HOLD:INITIAL_OBSERVATION_BINDING') from None
    need(type(observation) is dict and observation.get('subject')==IDENTITY_SUBJECT
         and observation.get('target')==record['target']
         and type(observation.get('observed_unix')) is int
         and observation['observed_unix']==record['observed_unix'],'INITIAL_OBSERVATION_BINDING')
    return True

def is_login(plan):return profile(plan)==LOGIN_ONLY

def units(plan,all_units):return all_units[:3] if is_login(plan) else all_units

def triggers(plan,all_units):return (all_units[2],) if is_login(plan) else (all_units[2],all_units[4],all_units[5])

def validate_window(approval,plan,now):
    issued,expires=approval.get('issued_unix'),approval.get('expires_unix')
    need(type(issued) is int and type(expires) is int and issued<=now<expires,'APPROVAL_EXPIRY')
    explicit='permit_window_seconds' in approval or 'permit_window_seconds' in plan
    if explicit:
        need(type(approval.get('permit_window_seconds')) is int
             and approval['permit_window_seconds']==plan.get('permit_window_seconds')==WINDOW_SECONDS
             and expires-issued==WINDOW_SECONDS,'EXACT_FIVE_HOUR_PERMISSION')
        need(approval.get('attempt_policy')=='CONTROLLED_WHOLE_WEBSITE_V3'
             and type(approval.get('max_executions')) is int and approval['max_executions']==5,
             'FIVE_HOUR_EXISTING_WHOLE_BUDGET_REQUIRED')
    else:need(0<expires-issued<=7200,'APPROVAL_EXPIRY')
    if is_login(plan):
        need(approval.get('deployment_profile')==LOGIN_ONLY and explicit,'LOGIN_EXPLICIT_PERMISSION')
    else:need('deployment_profile' not in approval or approval['deployment_profile']==FULL,'DEPLOYMENT_PERMISSION_SCOPE')
