"""Concrete fixed adapters for the original website preparation/install chain.
Inputs are data, not authority: the original signed gate binds every stage hash.
No new privileged CLI, probe writer, ledger, permission enrollment or shell input.
"""
import copy
import json
import os
from pathlib import Path
from scripts.pr122_customer_core import canonical,digest,Denied
from scripts.pr122_customer_workflow import STAGES,need
from scripts import pr122_customer_resume as resume
from scripts import pr122_customer_preparation as preparation
from scripts import pr122_customer_runtime as runtime
from scripts import pr122_customer_runtime_stage as runtime_stage
from scripts import pr122_customer_channel_upgrade as channel
from scripts import pr122_customer_workflow_apply as customer
from scripts.pr122_account_admission import approved_account_prepare as account
from scripts.pr122_account_admission import domestic_bootstrap as bootstrap
from scripts.pr122_account_admission import readonly_probe as probe

PROBE_RECEIPT=Path('/var/lib/xuanjun-customer-channel/readonly-admission-20261017/result.json')


class OriginalOperations:
    def __init__(self,release,folder,plan,inputs):
        need(type(inputs) is dict and set(inputs)=={'schema','stages'} and inputs['schema']==1
             and type(inputs['stages']) is dict and set(inputs['stages'])==set(STAGES), 'WORKFLOW_PROTECTED_INPUTS')
        self.r,self.folder,self.plan=release,folder,copy.deepcopy(plan)
        self.inputs=copy.deepcopy(inputs['stages']);self.coordinator=None

    def attach(self,coordinator):
        need(self.coordinator is None,'WORKFLOW_ADAPTER_ALREADY_BOUND');self.coordinator=coordinator

    def input(self,stage):return copy.deepcopy(self.inputs[stage])

    def implementation(self,stage):
        module={'PROBE':probe,'ACCOUNT':account,'RUNTIME':runtime,'POLICY_RESTORE':bootstrap,
                'CHANNEL_REBIND':channel,'CUSTOMER_APPLY':self.r}[stage]
        return Path(module.__file__).read_bytes()

    def _record(self,stage,phase):
        rows=[row for row in self.coordinator.data['stage_records'] if row['stage']==stage and row['phase']==phase]
        need(bool(rows),'WORKFLOW_CHILD_SUCCESS_RECEIPT_REQUIRED')
        return copy.deepcopy(rows[-1])

    def _cp(self,receipt,effect,source=None):
        return {'state':'COMPLETE','receipt_sha256':digest(receipt),'effect_sha256':digest(canonical(effect)),
                'source_commit':source or self.plan['source_commit']}

    def account_identity(self):
        raw=account.read_public_config(Path(account.ACCOUNT_RECEIPT)/'ACCOUNT_CREATED_VERIFIED_NO_RETRY.json').encode()
        need(json.loads(raw)=={'state':'ACCOUNT_CREATED_VERIFIED_NO_RETRY','host':account.HOST,
                              'account':account.ACCOUNT,'retry_allowed':False},'ACCOUNT_SUCCESS_RECEIPT')
        ops=account.OS();platform=ops.platform_preconditions();post=ops.private_postcheck()
        value=self.input('ACCOUNT')
        need(digest(canonical(platform))==value['platform_sha256'],'ACCOUNT_PLATFORM_DRIFT')
        uid,gid=post.get('uid'),post.get('gid')
        need(type(uid) is int and type(gid) is int and platform['uid_min']<=uid<=platform['uid_max']
             and platform['gid_min']<=gid<=platform['gid_max'] and uid>0 and gid>0
             and post.get('name')==post.get('primary_group')==account.ACCOUNT and post.get('group_gid')==gid
             and post.get('home')=='/nonexistent' and post.get('shell')=='/usr/sbin/nologin'
             and post.get('supplementary_groups')==[] and all(post.get(k) is True for k in
                 ('password_locked','home_absent','mail_spool_absent','no_subids','no_sudo_grants')),
             'ACCOUNT_LIVE_POSTCONDITION')
        # If this series created the account, retain its exact UID/GID, not just
        # a newly valid account at the same name after drift.
        rows=[r for r in self.coordinator.data['stage_records'] if r['stage']=='ACCOUNT' and r['phase']=='ACCOUNT_VERIFIED']
        if rows:need((uid,gid)==(rows[-1]['metadata']['uid'],rows[-1]['metadata']['gid']),'ACCOUNT_CREATED_IDENTITY_DRIFT')
        return {'uid':uid,'gid':gid,'receipt_sha256':digest(raw)}

    def _observe(self,stage):
        if stage=='PROBE':
            value=resume.read_private(PROBE_RECEIPT);raw=PROBE_RECEIPT.read_bytes()
            need(set(self.input(stage))=={'receipt_sha256'} and digest(raw)==self.input(stage)['receipt_sha256'],
                 'PROBE_EXACT_EXISTING_RECEIPT')
            need(value.get('state')=='READONLY_OBSERVED_ACCOUNT_CREATION_HOLD' and value.get('hostname')==account.HOST
                 and value.get('account')==account.ACCOUNT and value.get('mutations')==0
                 and value.get('creation_authorized') is False,'PROBE_HISTORICAL_RESULT')
            return self._cp(raw,value)
        if stage=='ACCOUNT':
            identity=self.account_identity()
            raw=account.read_public_config(Path(account.ACCOUNT_RECEIPT)/'ACCOUNT_CREATED_VERIFIED_NO_RETRY.json').encode()
            return self._cp(raw,identity)
        if stage=='RUNTIME':
            record=self._record(stage,'RUNTIME_VERIFIED');report=record['metadata'];identity=self.account_identity()
            need((report['account_uid'],report['account_gid'])==(identity['uid'],identity['gid']),'RUNTIME_ACCOUNT_DRIFT')
            current=runtime._runtime_tree(runtime.PROTECTED_RUNTIME)
            need(digest(canonical(current))==report['runtime_closure_sha256'],'RUNTIME_COMPLETED_CLOSURE_DRIFT')
            info=os.lstat(runtime.PROTECTED_RUNTIME)
            need(report['runtime_root_identity']=={'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,
                 'gid':info.st_gid,'mode':__import__('stat').S_IMODE(info.st_mode)},'RUNTIME_ROOT_IDENTITY_DRIFT')
            contract=copy.deepcopy(self.input(stage)['runtime_template'])
            contract.update(account_uid=identity['uid'],account_gid=identity['gid'])
            need(runtime._source_identity(contract)==report['source_closure_sha256'],'RUNTIME_SOURCE_CLOSURE_DRIFT')
            return self._cp(canonical(record),report)
        if stage=='POLICY_RESTORE':
            raw=bootstrap.read(bootstrap.CONTROL/'ROLLED_BACK.json',0o400)
            need(raw==bootstrap.canonical({'state':'ROLLED_BACK'}),'POLICY_COMPLETION_RECEIPT')
            need(bootstrap.read(bootstrap.POLICY,0o440)==bootstrap.expected_policy()
                 and bootstrap.read(bootstrap.EXEC,0o755)==bootstrap.expected_wrapper(),'POLICY_COMPLETED_BYTES_DRIFT')
            value=self.input(stage)
            need(bootstrap.sha(bootstrap.read(bootstrap.CONTROL/'plan.json',0o400))==value['plan_sha256']
                 and bootstrap.sha(bootstrap.read(bootstrap.CONTROL/'old-wrapper',0o400))==value['old_wrapper_sha256']
                 and bootstrap.sha(bootstrap.read(bootstrap.CONTROL/'old-sudoers',0o400))==value['old_policy_sha256'],
                 'POLICY_BACKUP_DRIFT')
            return self._cp(raw,{'wrapper':value['old_wrapper_sha256'],'policy':value['old_policy_sha256']})
        if stage=='CHANNEL_REBIND':
            receipt=json.loads(channel.read(channel.CONTROL/'receipt.json'))
            need(receipt.get('state')=='BOUND' and receipt.get('phase')=='BOUND'
                 and receipt.get('step_status')=='DONE','CHANNEL_COMPLETION_REQUIRED')
            approved=receipt['approval']
            need(approved.get('workflow_approval_sha256')==digest(canonical(self.coordinator.approval))
                 and approved.get('rollback_approved') is False,'CHANNEL_SAME_WORKFLOW_PERMISSION')
            value,files,archive,code=channel.bundle(self.input(stage)['zip_sha256']);plan=receipt['plan']
            need(digest(channel.canonical(plan))==self.input(stage)['plan_sha256'] and value==plan['new'],'CHANNEL_PLAN_BINDING')
            need(channel.snapshot(channel.BASE/'candidate')=={n:{'sha256':channel.sha(b),'mode':0o400} for n,b in files.items()}
                 and channel.read(channel.BASE/'channel.py')==code and channel.read(channel.BASE/channel.ARCHIVE)==archive
                 and json.loads(channel.read(channel.BASE/'grant-state.json'))=={'state':'GRANTED'},'CHANNEL_COMPLETED_DRIFT')
            channel.verify_policy(plan);channel.backup_verify(plan)
            return self._cp(channel.read(channel.CONTROL/'receipt.json'),value)
        if stage=='CUSTOMER_APPLY':
            receipt=resume.read_private(self.r.STATE/self.r.TXN/'receipt.json')
            need(receipt.get('schema')==3 and receipt.get('policy')==self.coordinator.approval['attempt_policy']
                 and receipt.get('approval')==self.coordinator.approval and receipt.get('state')==resume.SUCCESS,
                 'CUSTOMER_COMPLETION_REQUIRED')
            value=self.input(stage)
            need(type(value) is dict and set(value)=={'static_plan'} and type(value['static_plan']) is dict
                 and not customer.DYNAMIC_FIELDS.intersection(value['static_plan'])
                 and {k:v for k,v in receipt['plan'].items() if k not in customer.DYNAMIC_FIELDS}==value['static_plan'],
                 'CUSTOMER_COMPLETED_PLAN_BINDING')
            receipt['_backup_bytes']=resume.backup_bytes(self.r,receipt)
            manifest,raw,files=self.r.source(self.folder)
            need(manifest['source_commit']==self.plan['source_commit'] and digest(raw)==self.plan['manifest_sha256'],
                 'CUSTOMER_COMPLETED_SOURCE_BINDING')
            # Read-only Journal verification does not require an active child
            # lease and never calls a mutation method.
            actions=self.coordinator.stage_contract(stage)['recovery_actions']
            class ProofContext:
                approval=self.coordinator.approval
                def assert_fence(inner):self.coordinator.assert_fence()
                def stage_contract(inner,name):
                    need(name==stage,'CUSTOMER_PROOF_SCOPE');return {'recovery_actions':actions}
            journal=resume.Journal(self.r,receipt,None,files,raw,workflow_lease=ProofContext())
            resume.context(self.r,receipt);journal.reconcile()
            return customer._checkpoint(self.coordinator,self.r,receipt)
        raise Denied('HOLD:UNSUPPORTED_FIXED_STAGE')

    def inherited(self,stage):return self._observe(stage)

    def verify(self,stage,checkpoint):
        actual=self._observe(stage)
        # The current approved verifier may inherit an explicitly pinned prior
        # source receipt; the coordinator separately validates that source pin.
        return all(actual[k]==checkpoint[k] for k in ('state','receipt_sha256','effect_sha256'))

    def execute(self,stage,lease):
        lease.assert_active()
        if stage=='PROBE':raise Denied('HOLD:EXISTING_SUCCESSFUL_PROBE_PIN_REQUIRED')
        if stage=='ACCOUNT':preparation.account_once(lease)
        elif stage=='RUNTIME':runtime_stage.rebuild_runtime(lease)
        elif stage=='POLICY_RESTORE':preparation.restore_policy(lease)
        elif stage=='CHANNEL_REBIND':channel.apply_for_workflow(lease)
        elif stage=='CUSTOMER_APPLY':return customer.execute(lease,self.r,self.folder)
        else:raise Denied('HOLD:UNSUPPORTED_FIXED_STAGE')
        lease.assert_active();return self._observe(stage)

    def reconcile(self,stage,intent,checkpoint,lease):
        lease.assert_fence();lease.authority()
        action={'PROBE':'REVALIDATE_READONLY','ACCOUNT':'RECONCILE_ACCOUNT','RUNTIME':'RECONCILE_RUNTIME',
                'POLICY_RESTORE':'RECONCILE_POLICY','CHANNEL_REBIND':'RECONCILE_CHANNEL','CUSTOMER_APPLY':'RECONCILE_CUSTOMER'}[stage]
        if stage=='CUSTOMER_APPLY':return customer.reconcile(lease,self.r,self.folder)
        try:
            observed=self._observe(stage)
            return {'status':'COMPLETE','action':action,'evidence_sha256':digest(canonical(observed)),'checkpoint':observed}
        except (Denied,OSError,ValueError,KeyError,RuntimeError):pass
        safe=False;evidence={}
        # Only prove no original writer has consumed its own transaction. Do
        # not delete/repair an unowned account or partial runtime/channel tree.
        if stage=='ACCOUNT' and not os.path.lexists(account.ACCOUNT_RECEIPT):
            ops=account.OS();seen=[]
            for getter in (ops.getpwnam,ops.getgrnam):
                try:getter(account.ACCOUNT);seen.append(True)
                except KeyError:seen.append(False)
            safe=seen==[False,False];evidence={'account_absent':safe,'original_receipt_absent':True}
        elif stage=='RUNTIME' and not os.path.lexists(runtime.PROTECTED_RUNTIME):
            safe=True;evidence={'fixed_runtime_absent':True}
        elif stage=='CHANNEL_REBIND' and not os.path.lexists(channel.CONTROL):
            current=channel.plan(expected_zip_sha256=self.input(stage)['zip_sha256']);safe=digest(channel.canonical(current))==self.input(stage)['plan_sha256']
            evidence={'original_rebind_transaction_absent':True,'plan_sha256':digest(channel.canonical(current))}
        elif stage=='POLICY_RESTORE':
            # Exact partial policy bytes are recoverable by the gated original
            # restoration entry on the next lease, never in this read-only proof.
            p,helper=bootstrap.transaction();value=self.input(stage)
            safe=(bootstrap.sha(bootstrap.read(bootstrap.CONTROL/'plan.json',0o400))==value['plan_sha256']
                  and bootstrap.read(bootstrap.POLICY,0o440) in (bootstrap.expected_policy(),bootstrap.new_policy())
                  and bootstrap.read(bootstrap.EXEC,0o755) in (bootstrap.expected_wrapper(),bootstrap.new_wrapper()))
            evidence={'plan_sha256':bootstrap.sha(bootstrap.canonical(p)),'exact_restore_states':safe}
        lease.assert_fence()
        return {'status':'SAFE_TO_RETRY' if safe else 'UNKNOWN','action':action,
                'evidence_sha256':digest(canonical(evidence)),'checkpoint':None}
