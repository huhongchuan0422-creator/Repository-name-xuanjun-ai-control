"""Fixed static profile over the original single durable Coordinator ledger.
No CLI, enrollment, signature creation or arbitrary request-defined stages.
Only an independently verified, exact new static permit can use this profile.
"""
from scripts.pr122_customer_core import canonical,digest
from scripts.pr122_customer_workflow import Coordinator,need,validate_contract

POLICY='CONTROLLED_STATIC_WEBSITE_V1'
PROFILE='OFFICIAL_STATIC_ONLY_V1'
STAGES=('BACKUP_VERIFIED','SEALED_BUNDLE','STATIC_PREPARED','NGINX_STAGED','NGINX_VALIDATED','ACTIVATION_DRIFT_CHECK','STATIC_ACTIVATED','NGINX_RELOADED','HTTPS_SMOKE','STATIC_CHECK')
RECOVERY={stage:frozenset({'RECONCILE_STATIC'}) for stage in STAGES}

def validate_permission(plan,approval):
    need(plan.get('deployment_profile')==approval.get('deployment_profile')==PROFILE,'STATIC_PROFILE')
    need(plan.get('permit_window_seconds')==approval.get('permit_window_seconds')==18000
         and type(approval.get('permit_window_seconds')) is int,'STATIC_FIVE_HOURS')
    need(type(approval.get('issued_unix')) is int and type(approval.get('expires_unix')) is int
         and approval['expires_unix']-approval['issued_unix']==18000,'STATIC_EXACT_WINDOW')
    need(type(approval.get('max_executions')) is int and approval['max_executions']==5,'STATIC_FIVE_ATTEMPTS')
    for name in ('static_baseline_sha256','host_pins_sha256'):
        value=plan.get(name)
        need(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
             and value==approval.get(name),'STATIC_BINDING:'+name)
    return validate_contract(plan,approval,stages=STAGES,recovery=RECOVERY,policy=POLICY)

class StaticCoordinator(Coordinator):
    STAGES=STAGES
    RECOVERY=RECOVERY
    POLICY=POLICY
    PHASES={}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        validate_permission(self.plan,self.approval)
    def authority(self):
        validate_permission(self.plan,self.approval)
        # release.gate must revalidate original Owner anchors + independent
        # Ed25519 review for this profile; super also checks source and lock.
        super().authority()

class StaticAuthority:
    """Internal authority adapter. Paths are fixed by original static control.
    Never accepts a fetcher, operations object, command, stage list or key from
    JSON. The protected Owner trust remains the existing customer trust store.
    """
    def __init__(self,transaction,folder):
        from scripts import pr122_site_hub_unified_release as original
        from scripts import pr122_customer_release as customer
        import re
        need(type(transaction) is original.Transaction,'STATIC_ORIGINAL_TRANSACTION')
        need(re.fullmatch(r'pr122-[a-z0-9-]{1,90}',transaction.id) is not None,'STATIC_TRANSACTION_ID')
        self.tx=transaction;self.folder=folder
        self.STATE=original.c.CONTROL/'transactions'
        self.TXN=transaction.id
        self.LOCK=original.c.CONTROL/'transaction.lock'
        self.atomic_json=customer.atomic_json
    def source(self,folder):
        from scripts.pr122_customer_core import private_path
        import json
        from pathlib import Path
        need(Path(folder)==Path(self.folder),'STATIC_SOURCE_FOLDER')
        root=private_path(folder);raw=private_path(root/'STATIC_SOURCE_MANIFEST.json').read_bytes()
        m=json.loads(raw);files={}
        from scripts import pr122_site_hub_unified_release as original
        original.verify_static_source_before_import(root,self.tx.pins)
        for row in m['files']:
            n=row['path'];need(type(n) is str and n and not n.startswith('/') and '\\' not in n and all(x not in ('','.','..') for x in n.split('/')),'STATIC_SOURCE_PATH')
            b=private_path(root/n).read_bytes();need(len(b)==row['size'] and digest(b)==row['sha256'],'STATIC_SOURCE_HASH');files[n]=b
        required={'scripts/pr122_customer_workflow.py','scripts/pr122_static_workflow.py','scripts/pr122_static_operations.py','scripts/pr122_customer_review.py','scripts/pr122_site_hub_unified_release.py','scripts/pr122_site_hub_combined.py','scripts/pr122_site_hub_host_preflight.py'}
        need(len(files)==len(m['files']) and required<=set(files),'STATIC_SOURCE_CLOSURE')
        # Imported trusted implementation must be the exact source being signed.
        for name in required:
            local=Path(__file__).resolve().parents[1]/name
            need(local.read_bytes()==files[name],'STATIC_LOADED_IMPLEMENTATION')
        import sys
        for module_name,module in tuple(sys.modules.items()):
            if module_name.startswith('scripts.') and getattr(module,'__file__',None):
                loaded=Path(module.__file__).resolve()
                need(loaded.is_relative_to(root.resolve()),'STATIC_IMPORT_OUTSIDE_CLOSURE')
                name=loaded.relative_to(root.resolve()).as_posix()
                need(name in files and loaded.read_bytes()==files[name],'STATIC_IMPORTED_CLOSURE')
        return m,raw,files
    def gate(self,comment_id,plan):
        import json,time
        from scripts import pr122_customer_release as customer
        from scripts.pr122_customer_review import verify,trust_digest
        from scripts import pr122_site_hub_unified_release as original
        pins_raw=original.c.read(original.PINS)
        need(digest(pins_raw)==plan['host_pins_sha256'] and json.loads(pins_raw)==self.tx.pins,'STATIC_HOST_PINS_DRIFT')
        need(self.tx.pins.get('package_schema')=='FULL_STATIC_REVIEW_V1' and self.tx.pins['static_artifact_sha256']==plan['artifact_tar_sha256'],'STATIC_ARTIFACT_PLAN_BINDING')
        baseline={name:self.tx.pins[name] for name in ('previous_release','previous_receipt_sha256','previous_manifest_sha256','nginx')}
        need(digest(canonical(baseline))==plan['static_baseline_sha256'],'STATIC_BASELINE_PLAN_BINDING')
        c=customer.github('issues/comments/'+str(comment_id))
        need(c['id']==comment_id and c['user']['login']==customer.OWNER and c['issue_url'].endswith('/issues/122') and c['body'].startswith('XUANJUN_STATIC_INSTALL_V1\n'),'STATIC_APPROVAL_ORIGIN')
        a=json.loads(c['body'].split('\n',1)[1]);validate_permission(plan,a)
        need(a.get('decision')=='INSTALL_APPROVED' and a.get('transaction')==self.TXN and a.get('plan_sha256')==digest(canonical(plan)) and a.get('rollback_approved') is True,'STATIC_APPROVAL_BINDING')
        need(a['issued_unix']<=time.time()<a['expires_unix'],'STATIC_EXPIRED')
        trust=customer.private_config(customer.CONFIG/'INDEPENDENT_REVIEW_TRUST.json')
        need(trust_digest(trust)==plan['review_trust_sha256'],'STATIC_TRUST_DRIFT')
        r=customer.github('issues/comments/'+str(a['review_comment_id']))
        need(r['id']!=comment_id and r['issue_url'].endswith('/issues/122'),'STATIC_REVIEW_ORIGIN')
        verify(r,c,a,plan,trust,customer.github)
        ci=customer.github('actions/runs/'+str(a['ci_run_id']))
        need(ci['conclusion']=='success' and ci['head_sha']==a['source_commit'] and ci['path']=='.github/workflows/pr122-unified-release-review.yml' and ci['event'] in ('push','workflow_dispatch'),'STATIC_EXACT_CI')
        return a

def controlled_apply(transaction,folder,comment,plan,lock_fd):
    """Internal source-fixed entry under the existing caller-held exclusive lock.
    No CLI is enabled here; protected caller admission remains independently gated.
    """
    from scripts.pr122_static_operations import OriginalStaticOperations
    authority=StaticAuthority(transaction,folder)
    approval=authority.gate(comment,plan)
    operations=OriginalStaticOperations(transaction,plan,plan['static_inputs'])
    coordinator=StaticCoordinator(authority,folder,comment,plan,approval,operations,lock_fd)
    return coordinator.run()
