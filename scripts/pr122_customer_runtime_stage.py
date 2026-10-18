"""Bind protected runtime rebuilding to the original whole-workflow StageLease.
The approved template selects the already verified account checkpoint, never a
new account or guessed UID. No standalone execution or authority enrollment.
"""
import copy
from pathlib import Path
from scripts.pr122_customer_core import canonical,digest
from scripts.pr122_customer_workflow import POLICY,need
from scripts import pr122_customer_runtime as runtime


class RuntimeStage:
    def __init__(self,lease):
        self.lease=lease
        self.input=copy.deepcopy(lease.ops.input('RUNTIME'))
        need(type(self.input) is dict and set(self.input)=={'runtime_template','account_binding'}
             and self.input['account_binding']=='VERIFIED_ACCOUNT_CHECKPOINT','RUNTIME_STAGE_INPUT')
        template=self.input['runtime_template']
        need(type(template) is dict and 'account_uid' in template and 'account_gid' in template and template.get('account_uid') is None and template.get('account_gid') is None,
             'RUNTIME_DERIVED_ACCOUNT_TEMPLATE')
        self.contract=copy.deepcopy(template)
        identity=lease.ops.account_identity()
        account=lease.data['checkpoints'].get('ACCOUNT')
        need(type(identity) is dict and set(identity)=={'uid','gid','receipt_sha256'}
             and type(identity['uid']) is int and identity['uid']>0
             and type(identity['gid']) is int and identity['gid']>0
             and type(account) is dict and account['receipt_sha256']==identity['receipt_sha256'],
             'RUNTIME_VERIFIED_ACCOUNT_RECEIPT')
        self.identity=copy.deepcopy(identity)
        self.contract.update(account_uid=identity['uid'],account_gid=identity['gid'])
        self.authorize_runtime(self.contract)

    def authorize_runtime(self,contract):
        lease=self.lease;lease.assert_active();lease.authority();lease.verify_inputs('RUNTIME')
        need(lease.approval.get('attempt_policy')==POLICY,'RUNTIME_WHOLE_SCOPE_REQUIRED')
        need(lease.ops.input('RUNTIME')==self.input and contract==self.contract
             and lease.ops.account_identity()==self.identity,'RUNTIME_BOUND_INPUT_DRIFT')
        actual=digest(Path(runtime.__file__).read_bytes())
        need(actual==lease.stage_contract('RUNTIME')['implementation_sha256']
             and contract.get('runtime_module_sha256')==actual,'RUNTIME_IMPLEMENTATION_BINDING')
        need(contract.get('source_commit')==lease.plan['source_commit'],'RUNTIME_SOURCE_BINDING')
        lease.assert_active()

    def assert_locked(self):
        self.lease.assert_active()

    def record_runtime(self,phase,metadata):
        self.lease.record_stage('RUNTIME',phase,metadata)

    def run(self):
        self.authorize_runtime(self.contract)
        return runtime.protected_rebuild(copy.deepcopy(self.contract),self)


def rebuild_runtime(lease):
    return RuntimeStage(lease).run()
