"""Fixed preparation-stage bridges to existing account and bootstrap writers.
No new CLI, account creator, policy writer, secret input, or independent ledger.
"""
from pathlib import Path
from scripts.pr122_customer_core import canonical,digest,Denied
from scripts.pr122_customer_workflow import POLICY,need
from scripts.pr122_account_admission import approved_account_prepare as account
from scripts.pr122_account_admission import domestic_bootstrap as bootstrap


def _guard(lease,stage,module,active=True):
    if active:lease.assert_active()
    else:lease.assert_fence()
    lease.authority();lease.verify_inputs(stage)
    need(lease.approval.get('attempt_policy')==POLICY,'PREPARATION_NEW_SCOPE_REQUIRED')
    need(digest(Path(module.__file__).read_bytes())==lease.stage_contract(stage)['implementation_sha256'],
         'PREPARATION_IMPLEMENTATION_DRIFT')
    if active:lease.assert_active()
    else:lease.assert_fence()


def account_once(lease):
    """Delegate to the one original account writer under its original lock."""
    _guard(lease,'ACCOUNT',account)
    inputs=lease.ops.input('ACCOUNT')
    need(type(inputs) is dict and set(inputs)=={'account','argv_sha256','platform_sha256'}
         and inputs['account']==account.ACCOUNT
         and inputs['argv_sha256']==digest(canonical(list(account.PROPOSED_ARGV))), 'ACCOUNT_FIXED_CONTRACT')
    original=account.OS()
    class LeaseCheckedAccount:
        def __getattr__(self,name):return getattr(original,name)
        def platform_preconditions(self):
            _guard(lease,'ACCOUNT',account)
            value=original.platform_preconditions()
            need(digest(canonical(value))==inputs['platform_sha256'],'ACCOUNT_PLATFORM_DRIFT')
            return value
        def reserve_original_evidence(self,path):
            _guard(lease,'ACCOUNT',account);return original.reserve_original_evidence(path)
        def record_original_evidence(self,path,state):
            _guard(lease,'ACCOUNT',account);return original.record_original_evidence(path,state)
        def run_fixed_useradd(self,argv):
            _guard(lease,'ACCOUNT',account);self.platform_preconditions()
            _guard(lease,'ACCOUNT',account)
            return original.run_fixed_useradd(argv)
    ops=LeaseCheckedAccount()
    need(digest(canonical(ops.platform_preconditions()))==inputs['platform_sha256'],'ACCOUNT_PLATFORM_DRIFT')
    _guard(lease,'ACCOUNT',account)
    lease.record_stage('ACCOUNT','ACCOUNT_CREATE_INTENT',{'platform_sha256':inputs['platform_sha256']})
    try:
        result=account.create_once(ops)
        need(result.get('state')=='ACCOUNT_CREATED_VERIFIED','ACCOUNT_RESULT_UNKNOWN')
        lease.record_stage('ACCOUNT','ACCOUNT_VERIFIED',result)
        return result
    except BaseException:
        lease.record_stage('ACCOUNT','ACCOUNT_UNKNOWN_PRESERVE',{'retry_allowed':False})
        raise


def restore_policy(lease):
    """Only the original bootstrap's exact old wrapper/sudoers restoration."""
    _guard(lease,'POLICY_RESTORE',bootstrap)
    return bootstrap.restore_for_workflow(lease)
