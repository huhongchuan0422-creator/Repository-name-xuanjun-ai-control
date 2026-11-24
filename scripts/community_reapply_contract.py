"""Internal candidate planner only. No HTTP, SQL, provider IO or credential handling.
Not an authentication boundary or deployed endpoint. Inputs must be re-read by
original trusted onboarding composition inside its existing transaction.
"""
from dataclasses import dataclass
import hashlib,json,re

class ReapplyBlocked(ValueError):pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def need(ok,code):
    if not ok:raise ReapplyBlocked(code)

@dataclass(frozen=True)
class Target:
    alias:str
    owner_ref:str
    application_ref:str
    scope:tuple
    old_provider_ref:str

@dataclass(frozen=True)
class Policy:
    targets:tuple
    new_provider_ref:str
    dots_effect_ref:str
    enabled:bool=False

@dataclass(frozen=True)
class Snapshot:
    owner_ref:str
    application_ref:str
    scope:tuple
    old_provider_ref:str
    current_provider_ref:str
    version:int
    generation:int
    old_state:str
    verified_observation_ref:str
    old_sub_ref:str
    unknown_submission:bool
    reconciliation_ref:str
    financial_clear:bool
    account_epoch:int
    login_identity_ref:str
    history_digest:str


def validate_policy(policy):
    need(type(policy) is Policy and policy.enabled is True,'PROTECTED_TEST_POLICY_DISABLED')
    need(len(policy.targets)==2 and all(type(t) is Target for t in policy.targets),'EXACT_TWO_TEST_TARGETS_REQUIRED')
    need({t.alias for t in policy.targets}=={'test1','test2'},'EXACT_TWO_TEST_ALIASES_REQUIRED')
    need(len({t.owner_ref for t in policy.targets})==2 and len({t.application_ref for t in policy.targets})==2,'EXACT_DISTINCT_TEST_OBJECTS_REQUIRED')
    need(bool(policy.dots_effect_ref) and bool(policy.new_provider_ref),'DOTS_ACTUAL_VERSION_EFFECT_REQUIRED')
    for t in policy.targets:
        need(all(type(x) is str and bool(x) for x in (t.owner_ref,t.application_ref,t.old_provider_ref)) and len(t.scope)==3 and all(type(x) is str and x for x in t.scope),'EXACT_PROTECTED_TARGET_REQUIRED')
        need(t.old_provider_ref!=policy.new_provider_ref,'DISTINCT_NEW_PROVIDER_REQUIRED')


def plan_release(policy,snapshot,*,alias,expected_version,idempotency_key,prior_receipt=None):
    """Plan ONLY a current-business cursor release; preserve old immutable rows.
    prior_receipt is an original transaction's trusted receipt, NEVER HTTP input.
    No signed success or submission capability is created by this plan.
    """
    validate_policy(policy)
    need(type(snapshot) is Snapshot,'TRUSTED_ORIGINAL_SNAPSHOT_REQUIRED')
    target=next((t for t in policy.targets if t.alias==alias),None)
    need(target is not None,'TEST_ALIAS_NOT_AUTHORIZED')
    need((snapshot.owner_ref,snapshot.application_ref,snapshot.scope,snapshot.old_provider_ref)==(target.owner_ref,target.application_ref,target.scope,target.old_provider_ref),'EXACT_TEST_OWNER_APPLICATION_STORE_PROVIDER_REQUIRED')
    need(type(expected_version) is int and expected_version>=1,'EXPECTED_VERSION_REQUIRED')
    need(type(idempotency_key) is str and re.fullmatch('[A-Za-z0-9_-]{16,80}',idempotency_key) is not None,'IDEMPOTENCY_KEY_REQUIRED')
    request=dict(alias=alias,owner=target.owner_ref,application=target.application_ref,scope=target.scope,old_provider=target.old_provider_ref,new_provider=policy.new_provider_ref,expected_version=expected_version,idempotency_key=idempotency_key,dots_effect=policy.dots_effect_ref)
    fingerprint=digest(request)
    need(snapshot.current_provider_ref==policy.new_provider_ref,'DOTS_CURRENT_PROVIDER_EFFECT_MISMATCH')
    need(not snapshot.unknown_submission,'UNKNOWN_SUBMISSION_RECONCILIATION_REQUIRED')
    need(snapshot.financial_clear is True and bool(snapshot.reconciliation_ref),'REAL_ORDERS_BALANCE_RECONCILIATION_REQUIRED')
    need(snapshot.old_state=='APPLYMENT_STATE_FINISHED' and bool(snapshot.verified_observation_ref) and bool(snapshot.old_sub_ref),'EXACT_OLD_FINISHED_PROOF_REQUIRED')
    need(type(snapshot.generation) is int and snapshot.generation>=1 and type(snapshot.account_epoch) is int and snapshot.account_epoch>=0 and bool(snapshot.login_identity_ref) and bool(snapshot.history_digest),'ORIGINAL_LOGIN_HISTORY_GENERATION_REQUIRED')
    if prior_receipt is not None:
        need(type(prior_receipt) is dict and prior_receipt.get('request_digest')==fingerprint and prior_receipt.get('released_version')==expected_version+1 and snapshot.version==expected_version+1 and prior_receipt.get('generation')==snapshot.generation and prior_receipt.get('history_digest')==snapshot.history_digest,'REPLAY_RECEIPT_OR_CURRENT_STATE_CONFLICT')
        return dict(prior_receipt,replay=True)
    need(snapshot.version==expected_version,'CURRENT_BINDING_VERSION_CONFLICT')
    return dict(schema=1,action='RELEASE_CURRENT_PAYMENT_APPLICATION_CURSOR_ONLY',request_digest=fingerprint,released_version=expected_version+1,generation=snapshot.generation,previous_application_ref=target.application_ref,previous_provider_ref=target.old_provider_ref,next_provider_ref=policy.new_provider_ref,next_generation=snapshot.generation+1,next_application_ref=None,history_digest=snapshot.history_digest,account_epoch=snapshot.account_epoch,login_identity_ref=snapshot.login_identity_ref,preserve_channels=('COMMUNITY_ONBOARDING','COMMUNITY_WECHAT_APPLYMENT','COMMUNITY_WECHAT_OBSERVATION','COMMUNITY_MERCHANT_OPENING','WECHAT_MINI'),preserve_orders=True,preserve_callbacks=True,provider_io=False,auto_submit=False,payment_enabled=False,replay=False)


def accept_new_generation_result(plan,*,provider_ref,generation,application_ref,response_application_ref):
    """Old provider/query can never be rendered as a new generation result."""
    return (type(plan) is dict and provider_ref==plan.get('next_provider_ref') and generation==plan.get('next_generation') and type(application_ref) is str and bool(application_ref) and application_ref!=plan.get('previous_application_ref') and application_ref==response_application_ref)


def rollback_allowed(plan,*,current_version,next_application_ref,submission_evidence_present,provider_effect_present):
    """Never roll back across any new application, unknown submit or provider IO."""
    return (type(plan) is dict and current_version==plan.get('released_version') and next_application_ref is None and submission_evidence_present is False and provider_effect_present is False)
