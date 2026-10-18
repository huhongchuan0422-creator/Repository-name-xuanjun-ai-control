"""Run original customer fixed checkpoints on the whole-workflow's SINGLE lease.
No nested Attempts construction, extra permit, alternate budget or retry loop.
"""
import errno
import os
from pathlib import Path
from scripts import pr122_customer_resume as resume
from scripts.pr122_customer_core import canonical,digest,private_path,Denied
from scripts.pr122_customer_workflow import POLICY,need

DYNAMIC_FIELDS=frozenset({'account_uid','account_gid','isolated_python'})


class BorrowedAttempt:
    def __init__(self,lease,transaction):
        self.lease=lease
        number=lease.active['number']
        self.row={'number':number,'attempt_id':transaction+'-%02d'%number}
    def assert_active(self):self.lease.assert_active()
    def assert_fence(self):self.lease.assert_fence()


def _bound(lease,release,folder):
    lease.assert_fence();lease.authority();lease.verify_inputs('CUSTOMER_APPLY')
    need(lease.approval.get('attempt_policy')==POLICY,'CUSTOMER_WHOLE_SCOPE_REQUIRED')
    need(digest(Path(release.__file__).read_bytes())==lease.stage_contract('CUSTOMER_APPLY')['implementation_sha256'],
         'CUSTOMER_IMPLEMENTATION_DRIFT')
    for stage in ('ACCOUNT','RUNTIME'):
        checkpoint=lease.data['checkpoints'].get(stage)
        need(type(checkpoint) is dict and lease.ops.verify(stage,checkpoint) is True,
             'CUSTOMER_PREREQUISITE_CHECKPOINT_UNPROVEN')
    lease.assert_fence()
    value=lease.ops.input('CUSTOMER_APPLY')
    need(type(value) is dict and set(value)=={'static_plan'} and type(value['static_plan']) is dict
         and not DYNAMIC_FIELDS.intersection(value['static_plan']),'CUSTOMER_STATIC_PLAN_CONTRACT')
    manifest,raw,files=release.source(folder)
    need(manifest['source_commit']==lease.plan['source_commit'] and digest(raw)==lease.plan['manifest_sha256'],
         'CUSTOMER_REVIEWED_SOURCE')
    return value['static_plan'],manifest,raw,files


def _load(lease,release,static):
    receipt=resume.read_private(release.STATE/release.TXN/'receipt.json')
    need(receipt.get('schema')==3 and receipt.get('policy')==POLICY and receipt.get('approval')==lease.approval,
         'CUSTOMER_CHILD_LEGACY_OR_PERMISSION')
    need({k:v for k,v in receipt['plan'].items() if k not in DYNAMIC_FIELDS}==static,'CUSTOMER_CHILD_PLAN_BINDING')
    receipt['_backup_bytes']=resume.backup_bytes(release,receipt)
    return receipt


def _checkpoint(lease,release,receipt):
    raw=(release.STATE/release.TXN/'receipt.json').read_bytes()
    return {'state':'COMPLETE','receipt_sha256':digest(raw),
            'effect_sha256':digest(canonical({'owned':receipt['owned'],'checkpoints':receipt['checkpoints'],
                                              'https_sha256':receipt.get('new_https_sha256')})),
            'source_commit':lease.plan['source_commit']}


def _recovery_action(lease,receipt):
    """Select only a permitted action supported by the reconciled child evidence."""
    permitted=lease.stage_contract('CUSTOMER_APPLY')['recovery_actions']
    failures=receipt.get('failures')
    failure=failures[-1] if type(failures) is list and failures else None
    if type(failure) is dict and failure.get('attempt')==receipt.get('attempt_number'):
        action=failure.get('repair_action')
        if action in permitted:
            if action=='REPAIR_INCOMPLETE_OWNED_FILE':
                path=failure.get('step');checkpoint=receipt['files'].get(path)
                evidence=failure.get('evidence');expected=receipt['expected_files'].get(path)
                if (failure.get('code')=='OWNED_FILE_WRITE_INTERRUPTED'
                    and receipt.get('activation_started') is False
                    and type(checkpoint) is dict and checkpoint.get('status')=='WRITING'
                    and type(evidence) is dict and type(expected) is dict
                    and evidence.get('errno') in (errno.EINTR,errno.ENOSPC)
                    and evidence.get('owned_identity')==checkpoint.get('identity')
                    and evidence.get('expected_sha256')==expected.get('sha256')):
                    return action
            elif action=='RETRY_TRANSIENT_READONLY_CHECK':
                if (failure.get('code')=='TRANSIENT_READONLY_CHECK'
                    and failure.get('step') in ('HTTPS_SMOKE','UNIT_VERIFY','NGINX_TEST','RUNTIME_CHECK')
                    and receipt.get('activation_started') is True and receipt.get('intent') is None
                    and all(cp.get('status')=='COMPLETE' for cp in receipt['files'].values())):
                    return action
    return 'RECONCILE_CUSTOMER' if 'RECONCILE_CUSTOMER' in permitted else None


def execute(lease,release,folder):
    lease.assert_active();static,manifest,raw,files=_bound(lease,release,folder)
    txn=release.STATE/release.TXN
    if os.path.lexists(txn):
        receipt=_load(lease,release,static)
        need(receipt['state']!=resume.SUCCESS,'CUSTOMER_SUCCESS_MUST_BE_INHERITED')
    else:
        observed=release.plan(folder)
        need({k:v for k,v in observed.items() if k not in DYNAMIC_FIELDS}==static,'CUSTOMER_STATIC_CONTEXT_DRIFT')
        account=lease.ops.account_identity();account_cp=lease.data['checkpoints'].get('ACCOUNT')
        need(type(account_cp) is dict and account['receipt_sha256']==account_cp['receipt_sha256']
             and observed['account_uid']==account['uid'] and observed['account_gid']==account['gid'],
             'CUSTOMER_VERIFIED_ACCOUNT_BINDING')
        need('RUNTIME' in lease.data['checkpoints'],'CUSTOMER_VERIFIED_RUNTIME_REQUIRED')
        lease.assert_active();txn.mkdir(mode=0o700)
        fd=os.open(release.STATE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
        old=private_path(release.HTTPS).read_bytes()
        need(digest(old)==observed['previous_https_sha256'],'CUSTOMER_BACKUP_DRIFT')
        payloads={str(release.CODE/p):b for p,b in files.items()}
        payloads[str(release.CODE/'CUSTOMER_MANIFEST.json')]=raw
        payloads[str(release.SNIPPET)]=files['deploy/pr122-customer-center/locations.conf']
        for unit in release.UNITS:payloads[str(release.UNIT/unit)]=files['deploy/pr122-customer-center/'+unit]
        payloads[str(txn/'https.before')]=old
        receipt={'schema':3,'policy':POLICY,'state':'INSTALLING','approval':lease.approval,'plan':observed,
                 'owned':{},'completed':[],'intent':None,'directories':{},'files':{},'checkpoints':{},
                 'failures':[],'repairs':[],'validations':[],'activation_started':False,
                 'expected_files':{p:{'sha256':digest(b),'size':len(b),'mode':0o600 if p==str(txn/'https.before') else 0o644}
                                   for p,b in payloads.items()},'_backup_bytes':old}
    borrowed=BorrowedAttempt(lease,release.TXN)
    receipt.update(attempt_number=borrowed.row['number'],attempt_id=borrowed.row['attempt_id'],state='INSTALLING')
    journal=resume.Journal(release,receipt,borrowed,files,raw,workflow_lease=lease)
    journal.save()
    try:
        resume.execute_steps(journal,files)
        lease.authority();lease.assert_active()
        receipt['state']=resume.SUCCESS;journal.save()
        return _checkpoint(lease,release,receipt)
    except BaseException as error:
        borrowed.assert_active()
        failure=error.failure if isinstance(error,resume.Recoverable) else {'code':'UNKNOWN_OR_UNSAFE_EFFECT','exception':type(error).__name__}
        receipt['failures'].append(dict(failure,attempt=borrowed.row['number']))
        receipt['state']='HOLD_WHOLE_WORKFLOW';journal.save()
        raise


def reconcile(lease,release,folder):
    """Read-only reconciliation. Fixed repair occurs on a subsequent total lease."""
    static,manifest,raw,files=_bound(lease,release,folder)
    try:
        if not os.path.lexists(release.STATE/release.TXN):
            observed=release.plan(folder)
            need({k:v for k,v in observed.items() if k not in DYNAMIC_FIELDS}==static,'CUSTOMER_STATIC_CONTEXT_DRIFT')
            need('RECONCILE_CUSTOMER' in lease.stage_contract('CUSTOMER_APPLY')['recovery_actions'],
                 'CUSTOMER_GENERIC_RECONCILIATION_NOT_APPROVED')
            return {'status':'SAFE_TO_RETRY','action':'RECONCILE_CUSTOMER',
                    'evidence_sha256':digest(canonical(observed)),'checkpoint':None}
        receipt=_load(lease,release,static)
        borrowed=BorrowedAttempt(lease,release.TXN)
        journal=resume.Journal(release,receipt,borrowed,files,raw,workflow_lease=lease)
        resume.context(release,receipt);journal.reconcile()
        evidence=digest(canonical({k:v for k,v in receipt.items() if k!='_backup_bytes'}))
        if receipt['state']==resume.SUCCESS:
            need('RECONCILE_CUSTOMER' in lease.stage_contract('CUSTOMER_APPLY')['recovery_actions'],
                 'CUSTOMER_GENERIC_RECONCILIATION_NOT_APPROVED')
            return {'status':'COMPLETE','action':'RECONCILE_CUSTOMER','evidence_sha256':evidence,
                    'checkpoint':_checkpoint(lease,release,receipt)}
        action=_recovery_action(lease,receipt)
        need(action is not None,'CUSTOMER_RECONCILIATION_NOT_APPROVED')
        return {'status':'SAFE_TO_RETRY','action':action,'evidence_sha256':evidence,'checkpoint':None}
    except (Denied,OSError,KeyError,TypeError,ValueError):
        return {'status':'UNKNOWN','action':'RECONCILE_CUSTOMER','evidence_sha256':digest(b'UNPROVEN_CUSTOMER_CHECKPOINT'),
                'checkpoint':None}
