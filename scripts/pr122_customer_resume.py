"""Fixed V2 checkpoints inside the original customer apply transaction.
No CLI, command input, independent permit, alternate ledger or generic repair.
"""
import errno
from scripts import pr122_customer_profile as deployment
import os
import stat
import time
from pathlib import Path
from scripts.pr122_customer_core import Denied, canonical, digest, private_path
from scripts.pr122_customer_attempts import read_private as read_ledger
import json

def read_private(path):
    from scripts.pr122_customer_attempts import protected_directory
    protected_directory(Path(path).parent)
    fd=os.open(private_path(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        need(trusted(info) and stat.S_ISREG(info.st_mode) and info.st_nlink==1
             and stat.S_IMODE(info.st_mode)==0o600,'V2_RECEIPT_TRUST')
        raw=stream.read(2000001)
    need(len(raw)<=2000000,'V2_RECEIPT_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'V2_DUPLICATE_KEY');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:need(False,'V2_NONFINITE'))

POLICY = 'CONTROLLED_INSTALL_RESUME_V2'
ACTIONS = frozenset({'REPAIR_INCOMPLETE_OWNED_FILE', 'RETRY_TRANSIENT_READONLY_CHECK', 'RECONCILE_OWNED_CHECKPOINTS'})
SUCCESS = 'HTTPS_SMOKE_PASS_AWAIT_14_REAL_ACCEPTANCE'


def need(ok, code):
    if not ok: raise Denied('HOLD:' + code)


def trusted(info):
    return info.st_uid == 0 and info.st_gid == 0 and not info.st_mode & 0o022


def directory_identity(info):
    result=identity(info);result.pop('nlink');return result


def identity(info):
    return {'dev': info.st_dev, 'ino': info.st_ino, 'uid': info.st_uid,
            'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode), 'nlink': info.st_nlink}


def assert_lock(release):
    fd=release._v2_lock_fd
    need(identity(os.fstat(fd))==identity(os.lstat(release.LOCK)), 'V2_LOCK_REPLACED')


class Recoverable(Denied):
    def __init__(self, code, step, action, evidence):
        super().__init__('HOLD:' + code)
        self.failure = {'code': code, 'step': step, 'repair_action': action,
                        'evidence': evidence, 'at_unix': int(time.time())}


class Stopped(Denied):
    def __init__(self, report):
        super().__init__('HOLD:' + report['state'])
        self.report = report


def validate_policy(approval):
    actions = approval.get('recovery_actions')
    need(approval.get('attempt_policy') == POLICY and type(actions) is list
         and len(actions) == len(set(actions)) and bool(actions)
         and all(type(x) is str and x in ACTIONS for x in actions), 'V2_EXACT_RECOVERY_SCOPE')
    return frozenset(actions)


class Journal:
    def __init__(self, release, receipt, attempts, files, raw, workflow_lease=None):
        self.r, self.receipt, self.attempts = release, receipt, attempts
        self.txn = release.STATE / release.TXN
        self.path = self.txn / 'receipt.json'
        self.workflow_lease=workflow_lease
        if workflow_lease is None:self.actions=validate_policy(receipt['approval'])
        else:
            from scripts.pr122_customer_workflow import POLICY as WORKFLOW_POLICY
            workflow_lease.assert_fence()
            need(receipt['approval']==workflow_lease.approval and receipt['approval']['attempt_policy']==WORKFLOW_POLICY,
                 'V2_BORROWED_WORKFLOW_PERMISSION')
            actions=set(workflow_lease.stage_contract('CUSTOMER_APPLY')['recovery_actions'])
            if 'RECONCILE_CUSTOMER' in actions:actions.add('RECONCILE_OWNED_CHECKPOINTS')
            self.actions=frozenset(actions & ACTIONS)
        self.payloads = {str(release.CODE / p): b for p, b in files.items()}
        self.payloads[str(release.CODE / 'CUSTOMER_MANIFEST.json')] = raw
        self.payloads[str(release.SNIPPET)] = files['deploy/pr122-customer-center/locations.conf']
        for unit in deployment.units(receipt['plan'],release.UNITS):
            self.payloads[str(release.UNIT / unit)] = files['deploy/pr122-customer-center/' + unit]
        self.payloads[str(self.txn / 'https.before')] = receipt['_backup_bytes']
        self.modes = {p: 0o644 for p in self.payloads}
        self.modes[str(self.txn / 'https.before')] = 0o600
        # Only byte-identical approved content can ever be repaired.
        for p, b in self.payloads.items():
            need(receipt['expected_files'].get(p) == {'sha256': digest(b), 'size': len(b), 'mode': self.modes[p]}, 'V2_PAYLOAD_BINDING')

    def save(self):
        if self.workflow_lease is not None:self.workflow_lease.assert_active()
        self.assert_lock()
        if self.attempts is not None:self.attempts.assert_fence()
        # Backup bytes are transient and are never serialized in JSON.
        value = {k: v for k, v in self.receipt.items() if k != '_backup_bytes'}
        self.r.atomic_json(self.path, value)

    def _file_fd(self, path, flags):
        from scripts.pr122_customer_attempts import protected_directory
        protected_directory(Path(path).parent)
        private_path(path)
        fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if not (trusted(info) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
            os.close(fd); raise Denied('HOLD:V2_FILE_IDENTITY')
        return fd, info

    def verify_file(self, path, checkpoint, complete=True):
        fd, info = self._file_fd(path, os.O_RDONLY)
        try:
            expected = checkpoint['identity']
            need(identity(info) == expected, 'V2_OWNED_FILE_DRIFT')
            if complete:
                b = bytearray()
                while len(b) <= len(self.payloads[path]):
                    part = os.read(fd, min(65536, len(self.payloads[path]) + 1 - len(b)))
                    if not part: break
                    b.extend(part)
                need(bytes(b) == self.payloads[path], 'V2_COMPLETED_BYTES_DRIFT')
            after = os.fstat(fd); named = os.lstat(path)
            fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_gid','st_nlink')
            need(all(getattr(info,k) == getattr(after,k) == getattr(named,k) for k in fields), 'V2_FILE_READ_RACE')
        finally: os.close(fd)

    def reconcile(self):
        for path, expected in self.receipt['directories'].items():
            info = os.lstat(private_path(path))
            need(trusted(info) and stat.S_ISDIR(info.st_mode) and directory_identity(info) == expected, 'V2_DIRECTORY_DRIFT')
        for path, cp in self.receipt['files'].items():
            need(path in self.payloads and cp['status'] in ('COMPLETE','WRITING'), 'V2_CHECKPOINT_SCOPE')
            self.verify_file(path, cp, cp['status'] == 'COMPLETE')
            if cp['status'] == 'WRITING':
                need(not self.receipt['activation_started'] and 'REPAIR_INCOMPLETE_OWNED_FILE' in self.actions,
                     'V2_INCOMPLETE_FILE_NOT_RECOVERABLE')
        if self.r.CODE.exists():
            # A foreign file, symlink or unexpected directory is never adopted.
            known = set(self.receipt['files']) | set(self.receipt['directories'])
            for parent, dirs, files in os.walk(self.r.CODE, followlinks=False):
                need(len(dirs) + len(files) <= 10000, 'V2_LAYOUT_BOUND')
                for name in dirs + files:
                    path = str(Path(parent) / name)
                    need(path in known and not Path(path).is_symlink(), 'V2_FOREIGN_LAYOUT')
        intent = self.receipt['intent']
        # A durable create intent with an absent target proves there was no
        # lasting create effect. A present object without recorded ownership
        # remains unresolved; never adopt it from its name or contents alone.
        absent_create = (type(intent) is dict and intent.get('kind') in ('mkdir','file_create')
                         and type(intent.get('path')) is str and not os.path.lexists(intent['path']))
        if absent_create:
            path=Path(intent['path'])
            allowed = (str(path) in self.payloads if intent['kind']=='file_create' else
                       any(path==Path(p).parent or path in Path(p).parents for p in self.payloads))
            need(allowed,'V2_INTENT_SCOPE')
        need(intent is None or absent_create or (type(intent) is dict and intent.get('kind') == 'file_write'
             and intent.get('path') in self.receipt['files']
             and self.receipt['files'][intent['path']]['status'] == 'WRITING'), 'V2_UNRESOLVED_EFFECT')
        if absent_create:self.receipt['intent']=None

    def assert_lock(self):
        if self.workflow_lease is None:assert_lock(self.r)
        else:self.workflow_lease.assert_fence()

    def guard(self):
        self.assert_lock()
        need(self.attempts is not None, 'V2_NO_ACTIVE_LEASE')
        self.attempts.assert_active()

    def directory(self, path):
        self.guard()
        path = Path(path); key = str(path)
        if key in self.receipt['directories']:
            info = path.lstat();need(directory_identity(info) == self.receipt['directories'][key] and trusted(info), 'V2_DIRECTORY_DRIFT');return
        if os.path.lexists(path):
            # Existing parents outside owned code/snippet are not newly owned.
            need(not (path==self.r.CODE or self.r.CODE in path.parents or path==self.r.SNIPPET.parent), 'V2_FOREIGN_DIRECTORY')
            info = path.lstat();need(stat.S_ISDIR(info.st_mode) and trusted(info), 'V2_UNTRUSTED_PARENT');return
        self.directory(path.parent)
        self.receipt['intent'] = {'kind':'mkdir','path':key};self.save()
        os.mkdir(path,0o755)
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd);need(trusted(info),'V2_DIRECTORY_OWNER');os.fsync(fd)
        finally:os.close(fd)
        parent_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(parent_fd)
        finally:os.close(parent_fd)
        self.receipt['directories'][key]=directory_identity(info);self.receipt['intent']=None;self.save()

    def _write_bytes(self, fd, raw):
        view=memoryview(raw)
        while view:
            n=os.write(fd,view);need(n>0,'V2_SHORT_WRITE');view=view[n:]

    def file(self, path):
        self.guard()
        key=str(path);raw=self.payloads[key];mode=self.modes[key]
        cp=self.receipt['files'].get(key)
        if cp and cp['status']=='COMPLETE':self.verify_file(key,cp);return
        need(not self.receipt['activation_started'],'V2_NO_ACTIVE_CODE_REPAIR')
        repaired=cp is not None
        if repaired:
            need('REPAIR_INCOMPLETE_OWNED_FILE' in self.actions,'V2_REPAIR_NOT_PERMITTED')
            self.verify_file(key,cp,False)
            fd,info=self._file_fd(path,os.O_WRONLY)
            if identity(info)!=cp['identity']:
                os.close(fd);raise Denied('HOLD:V2_REPAIR_INODE_DRIFT')
        else:
            self.directory(Path(path).parent)
            need(not os.path.lexists(path),'V2_FOREIGN_FILE')
            self.receipt['intent']={'kind':'file_create','path':key};self.save()
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            info=os.fstat(fd)
            try:
                need(trusted(info) and stat.S_ISREG(info.st_mode) and info.st_nlink==1,'V2_NEW_FILE_OWNER')
                cp={'status':'WRITING','identity':identity(info)};self.receipt['files'][key]=cp
                if key != str(self.txn/'https.before'):self.receipt['owned'][key]=digest(raw)
                self.receipt['intent']={'kind':'file_write','path':key};self.save()
            except BaseException:os.close(fd);raise
        try:
            if repaired:
                # Capacity check before the sole fixed repair; never delete other data.
                fs=os.fstatvfs(fd);need(fs.f_bavail*fs.f_frsize >= len(raw)+65536,'V2_REPAIR_CAPACITY_UNVERIFIED')
                os.ftruncate(fd,0);os.lseek(fd,0,os.SEEK_SET)
            try:self._write_bytes(fd,raw)
            except OSError as error:
                if error.errno in (errno.EINTR,errno.ENOSPC) and 'REPAIR_INCOMPLETE_OWNED_FILE' in self.actions:
                    raise Recoverable('OWNED_FILE_WRITE_INTERRUPTED',key,'REPAIR_INCOMPLETE_OWNED_FILE',
                                      {'errno':error.errno,'owned_identity':cp['identity'],'expected_sha256':digest(raw)}) from None
                raise
            # fsync failures and post-write ambiguity are NOT classified safe.
            os.fsync(fd);os.fchmod(fd,mode);os.fsync(fd)
            cp.update(status='COMPLETE',identity=identity(os.fstat(fd)),sha256=digest(raw))
        finally:os.close(fd)
        parent_fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(parent_fd)
        finally:os.close(parent_fd)
        self.receipt['intent']=None
        if repaired:self.receipt['repairs'].append({'attempt':self.attempts.row['number'],'action':'REPAIR_INCOMPLETE_OWNED_FILE','path':key,'result_sha256':digest(raw),'validated':True})
        self.save();self.verify_file(key,cp)

    def effect(self,name,call):
        self.guard()
        if name in self.receipt['checkpoints']:return
        self.receipt['intent']={'kind':'effect','step':name};self.save()
        result=call()
        self.receipt['checkpoints'][name]={'attempt':self.attempts.row['number'],'completed_unix':int(time.time())}
        self.receipt['intent']=None;self.save();return result

    def readonly(self,name,call):
        self.guard()
        try:result=call()
        except Exception as error:
            transient = name=='HTTPS_SMOKE' and getattr(error,'returncode',None) in (7,28)
            transient = transient or (name in ('HTTPS_SMOKE','UNIT_VERIFY','NGINX_TEST') and getattr(error,'result_unknown',False))
            transient = transient or (name=='RUNTIME_CHECK' and str(error)=='HOLD:RUNTIME_PID')
            if transient and 'RETRY_TRANSIENT_READONLY_CHECK' in self.actions:
                raise Recoverable('TRANSIENT_READONLY_CHECK',name,'RETRY_TRANSIENT_READONLY_CHECK',
                                  {'exception':type(error).__name__,'returncode':getattr(error,'returncode',None),
                                   'stderr_sha256':getattr(error,'stderr_sha256',None)}) from None
            raise
        for repair in self.receipt['repairs']:
            if repair.get('step')==name and repair.get('state')=='REVALIDATION_PENDING':
                repair.update(state='VALIDATED',validated_attempt=self.attempts.row['number'])
        self.receipt['validations'].append({'attempt':self.attempts.row['number'],'step':name,'at_unix':int(time.time()),'passed':True})
        self.save();return result


def context(release,receipt):
    expected=dict(receipt['plan'])
    if 'NGINX_WRITE' in receipt['checkpoints']:
        expected['previous_https_sha256']=receipt['new_https_sha256']
        expected['nginx']={'master':expected['nginx']['master'],'files':dict(expected['nginx']['files'])}
        expected['nginx']['files'][str(release.HTTPS)]=receipt['new_https_sha256']
        expected['nginx']['files'][str(release.SNIPPET)]=receipt['expected_files'][str(release.SNIPPET)]['sha256']
    need(release.plan_without_absence(expected)==expected,'V2_PLAN_CONTEXT_DRIFT')
    plan=receipt['plan']
    if 'isolated_python' in plan:need(release.isolated_python_identity()==plan['isolated_python'],'V2_RUNTIME_IDENTITY_DRIFT')
    if 'publisher_config_sha256' in plan:need(digest((release.CONFIG/'publisher.json').read_bytes())==plan['publisher_config_sha256'],'V2_PUBLISHER_CONFIG_DRIFT')
    if 'isolated_python' in plan:
        account=release.pwd.getpwnam('xuanjun-customer')
        need(account.pw_uid==plan['account_uid'] and account.pw_gid==plan['account_gid'] and account.pw_uid>0
             and account.pw_shell in ('/sbin/nologin','/usr/sbin/nologin','/bin/false'),'V2_ACCOUNT_DRIFT')


def execute_steps(j,files):
    r=j.r;receipt=j.receipt
    context(r,receipt);j.reconcile()
    # Existing successful file checkpoints are verified and skipped, not rewritten.
    j.file(j.txn/'https.before')
    j.directory(r.CODE)
    for path in j.payloads:
        if path!=str(j.txn/'https.before'):j.file(Path(path))
    receipt['activation_started']=True;j.save()
    j.effect('DAEMON_RELOAD',lambda:r.run(['/usr/bin/systemctl','daemon-reload']))
    j.readonly('UNIT_VERIFY',lambda:r.run(['/usr/bin/systemd-analyze','verify',*[str(r.UNIT/u) for u in deployment.units(receipt['plan'],r.UNITS)]]))
    j.effect('START_RUNTIME',lambda:r.run(['/usr/bin/systemctl','start',r.UNITS[0]]))
    j.readonly('RUNTIME_CHECK',lambda:r.runtime_check(receipt['plan']['account_uid']))
    if not deployment.is_login(receipt['plan']):
        def publisher_identity():
            for prop,expected in (('FragmentPath',str(r.UNIT/r.UNITS[3])),('DropInPaths','')):
                need(r.run(['/usr/bin/systemctl','show',r.UNITS[3],'-p',prop,'--value']).decode().strip()==expected,'PUBLISHER_LOADED_UNIT_IDENTITY')
        j.readonly('PUBLISHER_IDENTITY',publisher_identity)
        j.effect('START_PUBLISHER',lambda:r.run(['/usr/bin/systemctl','start',r.UNITS[3]]))
        def publisher_result():need(r.run(['/usr/bin/systemctl','show',r.UNITS[3],'-p','Result','--value']).decode().strip()=='success','PUBLISHER_REAL_START_FAILED')
        j.readonly('PUBLISHER_RESULT',publisher_result)
    need(time.time()<receipt['approval']['expires_unix'],'APPROVAL_EXPIRED_BEFORE_NGINX');context(r,receipt)
    def nginx_write():
        old=receipt['_backup_bytes'];new=old.replace(r.ANCHOR,r.INCLUDE+r.ANCHOR)
        receipt['new_https_sha256']=digest(new);j.save()
        temporary=r.HTTPS.with_name('pr122-customer.temporary')
        r.secure_write(temporary,new);os.chmod(temporary,0o644);os.replace(temporary,r.HTTPS)
        fd=os.open(r.HTTPS.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    j.effect('NGINX_WRITE',nginx_write)
    j.readonly('NGINX_TEST',lambda:r.run(['/usr/sbin/nginx','-t']))
    j.effect('NGINX_RELOAD',lambda:r.run(['/usr/bin/systemctl','reload','nginx']))
    j.effect('TRIGGERS_ENABLE',lambda:r.run(['/usr/bin/systemctl','enable','--now',*deployment.triggers(receipt['plan'],r.UNITS)]))
    def smoke():
        data=r.run(['/usr/bin/curl','--noproxy','*','--resolve','wenwenwenyiyiyi.work:443:127.0.0.1','--fail','--silent','--show-error','--max-time','15','https://wenwenwenyiyiyi.work/customer/center/'])
        need(digest(data)==digest(files['deploy/pr122-customer-center/ui/index.html']),'REAL_HTTPS_HTML')
    j.readonly('HTTPS_SMOKE',smoke)
    receipt['completed']=['CODE_DIRECTORY','RUNTIME_STARTED','NGINX_INSTALLED','HTTPS_SMOKE']
    if not deployment.is_login(receipt['plan']):receipt['completed'].insert(2,'PUBLISHER_ROOT_TO_NONROOT_VERIFIED')


def report(receipt,state):
    return {'state':state,'transaction':receipt['plan']['transaction'],'attempts_used':receipt['attempt_number'],
            'max_attempts':receipt['approval']['max_executions'],'failures':receipt['failures'],
            'repairs':receipt['repairs'],'completed_steps':list(receipt['checkpoints']),
            'automatic_retry_allowed':False,'production_acceptance':'NOT_VERIFIED'}


def load_existing(release):
    try:value=read_private(release.STATE/release.TXN/'receipt.json')
    except Denied:raise Denied('HOLD:V2_TRANSACTION_SEALED_UNTRUSTED_RECEIPT') from None
    need(type(value) is dict and value.get('schema')==2 and value.get('policy')==POLICY,'V2_LEGACY_TRANSACTION_SEALED')
    need(value.get('state') in ('RECOVERABLE_FAILURE','INSTALLING','HOLD_UNKNOWN_OR_PARTIAL'), 'V2_TRANSACTION_NOT_RESUMABLE')
    need(type(value.get('failures')) is list and len(value['failures'])<=5
         and type(value.get('attempt_number')) is int and 1<=value['attempt_number']<=5,
         'V2_RECOVERY_CHECKPOINT_REQUIRED')
    return value


def backup_bytes(release,receipt):
    path=release.STATE/release.TXN/'https.before';cp=receipt['files'].get(str(path))
    if cp and cp['status']=='COMPLETE':
        fd=os.open(private_path(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd);need(trusted(info) and identity(info)==cp['identity'],'V2_BACKUP_IDENTITY')
            raw=os.read(fd,2000001);need(len(raw)<=2000000,'V2_BACKUP_SIZE')
        finally:os.close(fd)
    else:
        need(not receipt['activation_started'],'V2_MISSING_COMPLETED_BACKUP')
        raw=private_path(release.HTTPS).read_bytes()
    need(digest(raw)==receipt['plan']['previous_https_sha256'],'V2_BACKUP_HASH')
    return raw


def reconcile_interrupted(release,receipt,files,raw,comment):
    """Read-only proof before reopening a held V2 attempt under its original permit.
    Unknown service effects and unowned objects cannot be proven by this mechanism.
    """
    from scripts import pr122_customer_attempts as ledger
    assert_lock(release)
    path=release.STATE/(release.TXN+'.attempts.json')
    data=ledger.read_private(path)
    snapshot=canonical(data)
    binding={'transaction':release.TXN,'approval_comment':comment,
             'approval_sha256':digest(canonical(receipt['approval'])),
             'plan_sha256':digest(canonical(receipt['plan'])),
             'host':os.uname().nodename,'executor_uid':os.geteuid()}
    need(data.get('schema')==1 and data.get('binding')==binding,'V2_RECONCILE_BINDING')
    rows=data.get('attempts');need(type(rows) is list and 1<=len(rows)<=5,'V2_RECONCILE_HISTORY')
    previous=None
    for number,row in enumerate(rows,1):
        need(row.get('number')==number and row.get('previous_sha256')==previous,'V2_RECONCILE_CHAIN')
        previous=digest(canonical(row))
    last=rows[-1]
    need(receipt['attempt_number']==len(rows) and receipt['attempt_id']==last['attempt_id'], 'V2_RECONCILE_ATTEMPT')
    if receipt['state']=='RECOVERABLE_FAILURE' and last['state']=='RECOVERABLE_INSTALL_FAILURE':return
    need('RECONCILE_OWNED_CHECKPOINTS' in validate_policy(receipt['approval']), 'V2_RECONCILIATION_NOT_PERMITTED')
    need(last['state'] in ('STARTED_UNKNOWN','HOLD_UNKNOWN_OR_PARTIAL'), 'V2_RECONCILIATION_STATE')
    need(len(rows)<receipt['approval']['max_executions'], 'ATTEMPT_EXHAUSTED')
    receipt['_backup_bytes']=backup_bytes(release,receipt)
    journal=Journal(release,receipt,None,files,raw)
    context(release,receipt);journal.reconcile()
    failure={'attempt':last['number'],'attempt_id':last['attempt_id'],
             'code':'RECONCILED_OWNED_CHECKPOINTS','step':receipt['intent'],
             'repair_action':'RECONCILE_OWNED_CHECKPOINTS',
             'evidence':{'prior_attempt_sha256':previous,'checkpoints_sha256':digest(canonical(receipt['checkpoints'])),
                         'files_sha256':digest(canonical(receipt['files']))},'at_unix':int(time.time())}
    need(canonical(ledger.read_private(path))==snapshot,'ATTEMPT_FENCE_LOST')
    journal.assert_lock()
    need(release.gate(comment,receipt['plan'])==receipt['approval'],'V2_PERMISSION_DRIFT')
    # Preserve the original failure cause; add a separate proven recovery record.
    receipt['reconciliations']=receipt.get('reconciliations',[])+[failure]
    if receipt['failures'] and receipt['failures'][-1]['attempt']==last['number']:
        failure['prior_failure']=receipt['failures'][-1]
        receipt['failures'][-1]=failure
    else:receipt['failures'].append(failure)
    receipt['state']='RECOVERABLE_FAILURE';journal.save()
    last.update(state='RECOVERABLE_INSTALL_FAILURE',details=failure,ended_unix=int(time.time()))
    need(canonical(ledger.read_private(path))==snapshot,'ATTEMPT_FENCE_LOST')
    journal.assert_lock()
    release.atomic_json(path,data)


def apply_locked(release,folder,comment,initial_plan=None,initial_approval=None,lock_fd=None):
    """One invocation, one unchanged permit, at most its durable remaining budget.
    Caller holds the original shared lock across every attempt and repair.
    """
    from scripts.pr122_customer_attempts import Attempts
    need(type(lock_fd) is int,'V2_SHARED_LOCK_REQUIRED')
    release._v2_lock_fd=lock_fd
    assert_lock(release)
    txn=release.STATE/release.TXN
    existing=os.path.lexists(txn)
    if existing:
        receipt=load_existing(release);observed=receipt['plan']
        approval=release.gate(comment,observed)
        need(receipt['approval']==approval and receipt['approval_comment']==comment,'V2_PERMISSION_DRIFT')
    else:
        observed=initial_plan if initial_plan is not None else release.plan(folder)
        approval=initial_approval if initial_approval is not None else release.gate(comment,observed)
        receipt=None
    validate_policy(approval)
    manifest,raw,files=release.source(folder)
    need(digest(raw)==observed['manifest_sha256'] and manifest['source_commit']==observed['source_commit'],'V2_SOURCE_DRIFT')
    if receipt is not None:
        reconcile_interrupted(release,receipt,files,raw,comment)
    while True:
        # Repeat exact approval checks; no new permit is requested or fabricated.
        need(release.gate(comment,observed)==approval,'V2_PERMISSION_DRIFT')
        assert_lock(release)
        attempts=Attempts(release.STATE,release.TXN,approval,comment,observed,release.atomic_json,
                          release.CONFIG,resume_receipt=receipt)
        if receipt is None:
            txn.mkdir(mode=0o700)
            receipt={'schema':2,'policy':POLICY,'state':'INSTALLING','approval_comment':comment,
                     'approval':approval,'plan':observed,'owned':{},'completed':[], 'intent':None,
                     'directories':{},'files':{},'checkpoints':{},'failures':[], 'repairs':[],
                     'validations':[],'activation_started':False,'expected_files':{}}
            old=private_path(release.HTTPS).read_bytes()
            need(digest(old)==observed['previous_https_sha256'],'V2_BACKUP_SOURCE_DRIFT')
            payloads={str(release.CODE/p):b for p,b in files.items()}
            payloads[str(release.CODE/'CUSTOMER_MANIFEST.json')]=raw
            payloads[str(release.SNIPPET)]=files['deploy/pr122-customer-center/locations.conf']
            for unit in release.UNITS:payloads[str(release.UNIT/unit)]=files['deploy/pr122-customer-center/'+unit]
            payloads[str(txn/'https.before')]=old
            receipt['expected_files']={p:{'sha256':digest(b),'size':len(b),'mode':0o600 if p==str(txn/'https.before') else 0o644} for p,b in payloads.items()}
            receipt['_backup_bytes']=old
        else:
            receipt['_backup_bytes']=backup_bytes(release,receipt)
        receipt.update(state='INSTALLING',attempt_id=attempts.row['attempt_id'],attempt_number=attempts.row['number'])
        journal=Journal(release,receipt,attempts,files,raw)
        journal.save()
        try:
            execute_steps(journal,files)
            receipt['state']=SUCCESS;journal.save();attempts.finish(SUCCESS)
            return {k:v for k,v in receipt.items() if k!='_backup_bytes'}
        except Recoverable as error:
            attempts.assert_fence()
            failure=dict(error.failure,attempt=attempts.row['number'],attempt_id=attempts.row['attempt_id'])
            receipt['failures'].append(failure)
            exhausted=attempts.row['number']>=approval['max_executions']
            receipt['state']='ATTEMPTS_EXHAUSTED' if exhausted else 'RECOVERABLE_FAILURE'
            if not exhausted and failure['repair_action']=='RETRY_TRANSIENT_READONLY_CHECK':
                receipt['repairs'].append({'attempt':attempts.row['number'],'action':failure['repair_action'],
                                          'step':failure['step'],'state':'REVALIDATION_PENDING'})
            journal.save()
            attempts.finish('RECOVERABLE_INSTALL_FAILURE',details=failure)
            if exhausted:raise Stopped(report(receipt,'ATTEMPTS_EXHAUSTED')) from None
            # No generic repair and no retry after a mutating-command ambiguity.
            # The next iteration consumes the same ledger and reconstructs only
            # an explicitly allowed owned file or rechecks a transient read.
            need(failure['repair_action'] in journal.actions,'V2_REPAIR_NOT_PERMITTED')
            # A fixed bounded delay avoids a hot retry loop; expiry is rechecked.
            time.sleep(0.1)
        except BaseException as error:
            attempts.assert_fence()
            # Never expose exception bodies/subprocess stdout/credentials.
            receipt['failures'].append({'attempt':attempts.row['number'],'attempt_id':attempts.row['attempt_id'],
                                        'code':'UNKNOWN_OR_UNSAFE_EFFECT','exception':type(error).__name__,
                                        'step':receipt['intent'],'at_unix':int(time.time())})
            receipt['state']='ATTEMPTS_EXHAUSTED' if attempts.row['number']>=approval['max_executions'] else 'HOLD_UNKNOWN_OR_PARTIAL'
            journal.save();attempts.finish('HOLD_UNKNOWN_OR_PARTIAL',details=receipt['failures'][-1])
            raise Stopped(report(receipt,receipt['state'])) from None
