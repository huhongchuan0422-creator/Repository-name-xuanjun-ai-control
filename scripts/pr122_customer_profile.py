"""Fixed deployment scopes. No permission, credential or execution machinery."""
from scripts.pr122_customer_core import Denied
FULL='FULL'
LOGIN_ONLY='OFFICIAL_LOGIN_ONLY_V1'
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
    need(profile(runtime)==value,'DEPLOYMENT_PROFILE_BINDING')
    if value==LOGIN_ONLY:
        for obj in (config,runtime):
            providers=obj.get('providers')
            need(type(providers) is dict and set(providers)=={'smtp'} and bool(providers['smtp']),
                 'LOGIN_SMTP_ONLY_REQUIRED')
    return value

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
