#!/usr/bin/env python3
"""Fixed receipt-bound diagnostic continuation. No permission repair or UID test.

Only the completed exact r3 attempt can satisfy this route. A fresh full
observation still gates the separately reviewed finite probe. No resume.
"""
import argparse,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,types,urllib.request
HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
KIT=BASE+'/epoch7-recovery-candidate-r5'
OWNERS=((0,0),)
READY=True
SOURCE='9c40fc811947112df579b293fb4d54c61d9ce37b'
TREE='75dde36eb35524838fd2748ebe07fbba3d82da5e'
PUBLICATION='d5ed9f17ad9ef09d430aa6011f86449d227f0f1c'
REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
PREFIX='https://raw.githubusercontent.com/'+REPOSITORY+'/'
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-9c40fc81.tar.gz'
ARCHIVE_URL='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/d5ed9f17ad9ef09d430aa6011f86449d227f0f1c/evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-9c40fc81.tar.gz'
EXTRACTOR_URL='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/9c40fc811947112df579b293fb4d54c61d9ce37b/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'
ARCHIVE_SHA='e0fbc766d53a961f180a9ddfcdd1a40bdc6f8d809236f1b9bfb9cf4d3a929776'
EXTRACTOR_SHA='a5c283dfa297983617d5fca20c8453cd4766d765ba53ec9326e6c5645493202c'
ENTRY_SHA='1565e2f1e7e771f33e0895ffcaf8f38caddee9e02811a11b6a2318334af6075a'
MANIFEST_SHA='d8c36ad208994a3314f6b0c0598ad2e4ea8641c75f2610f9749784f834244d49'
ARCHIVE_SIZE=1028165
EXTRACTOR_SIZE=9582
KIT_SOURCE_FILES=249
PRIOR_ID='dbfe0a9a9cf8e074'
PRIOR_NONCE='a3542c827dec571ac52b30f9e86a0c80'
PRIOR_RECEIPT='epoch7-diagnostic-'+PRIOR_ID+'.private.json'
PRIOR_RECEIPT_SHA='4d85a064583ca92079f0df489838aa76cfb21f530a3725217689f33356fcbe91'
PRIOR_OBSERVATION='epoch7-observation-'+PRIOR_ID+'.private.json'
PRIOR_OBSERVATION_SHA='2192823493290c4829bfda8a4f6397e94d1ae053266075c1f0da9f63d319e0c9'
PRIOR_SOURCE='460a53e0f702fb416811e785a6ef8d6c39b2d003'
PRIOR_MANIFEST='e6618cf3012bc5edf8f3c9fb9982494dad7d916fbc7adcaeab39ebe0733cc3b8'
UK_CASE='test_epoch7_exact_access_uk.ActualFDTests.test_actual_fd_acl_changes_only_two_named_access_sets'
UK_TEST_SHA='8984cdc5a77411051fb9c2d9d81aefcd8c662e206c14f25dfa90c349f6512635'
HOME='/home/xuanjun_dev'
OPENCLAW=HOME+'/.openclaw'
TARGETS=(OPENCLAW+'/bin',OPENCLAW+'/tools',OPENCLAW+'/tools/node-v24.21.0')
FIELDS=('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns')
SHA=re.compile(r'^[0-9a-f]{64}$')
ALARM_CLEANUP_INTERVAL=1.0
class DiagnosticHold(ValueError):
    pass


class StageTimeout(KeyboardInterrupt):
    """Escape unittest's BaseException-to-error conversion."""
    pass


def need(value, code):
    if not value:
        raise DiagnosticHold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def host_boundary():
    need(os.geteuid() == 0 and os.getegid() == 0 and
         socket.gethostname().split('.')[0] == HOST, 'FIXED_ROOT_HOST_REQUIRED')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
         'ISOLATED_NO_SITE_NO_BYTECODE_REQUIRED')
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER_REFUSED')


@contextlib.contextmanager
def bounded_stage(seconds):
    """Only bootstrap/test phases; never leave an alarm around the probe."""
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER_REFUSED')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(unused_signum, unused_frame):
        raise StageTimeout()
    signal.signal(signal.SIGALRM, expired)
    primary = None
    try:
        # Repeated delivery remains armed during owned-context unwinding. A
        # slow Python cleanup cannot silently continue after the first expiry.
        signal.setitimer(signal.ITIMER_REAL, seconds, ALARM_CLEANUP_INTERVAL)
        yield
    except BaseException as error:
        primary = error
        raise
    finally:
        failed = False
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except BaseException:
            failed = True
        try:
            signal.signal(signal.SIGALRM, previous)
        except BaseException:
            failed = True
        if failed:
            if primary is not None:
                primary.diagnostic_timer_cleanup_failed = True
            else:
                raise DiagnosticHold('TIMER_CLEANUP_FAILED')


@contextlib.contextmanager
def preserve_cleanup(manager, label):
    """Preserve the primary outcome if a known context's cleanup also fails."""
    value = manager.__enter__()
    try:
        yield value
    except BaseException as primary:
        info = sys.exc_info()
        try:
            manager.__exit__(*info)
        except BaseException:
            setattr(primary, 'diagnostic_' + label + '_failed', True)
        raise
    else:
        manager.__exit__(None, None, None)


def bounded_reverify(entry):
    try:
        with bounded_stage(60):
            entry.verify_kit(KIT, MANIFEST_SHA)
    except BaseException as error:
        error.diagnostic_reverification_failed = True
        raise


@contextlib.contextmanager
def reverify_after(entry):
    try:
        yield
    except BaseException as primary:
        try:
            bounded_reverify(entry)
        except BaseException:
            primary.diagnostic_reverification_failed = True
        raise
    else:
        bounded_reverify(entry)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *unused, **unused_keywords):
        raise DiagnosticHold('DOWNLOAD_REDIRECT_REFUSED')


def download(url, size, digest):
    """Two fixed public HTTPS objects, no proxy, credentials, redirect or retry."""
    need((url, size, digest) in ((EXTRACTOR_URL, EXTRACTOR_SIZE, EXTRACTOR_SHA),
                                (ARCHIVE_URL, ARCHIVE_SIZE, ARCHIVE_SHA)), 'DOWNLOAD_SCOPE')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity'})
    with bounded_stage(30):
        with opener.open(request, timeout=10) as response:
            need(response.status == 200 and response.geturl() == url, 'DOWNLOAD_RESPONSE')
            need(response.headers.get('Content-Encoding', 'identity') == 'identity', 'DOWNLOAD_ENCODING')
            length = response.headers.get('Content-Length')
            need(length is None or length == str(size), 'DOWNLOAD_LENGTH')
            data = response.read(size + 1)
    need(type(data) is bytes and len(data) == size and sha(data) == digest, 'DOWNLOAD_HASH')
    return data


def authenticated_module(raw, digest, name, filename):
    need(type(raw) is bytes and sha(raw) == digest, 'BOOTSTRAP_HASH')
    module = types.ModuleType(name)
    module.__file__ = filename
    exec(compile(raw, filename, 'exec'), module.__dict__)
    return module


def absent(tree, leaf):
    try:
        os.stat(leaf, dir_fd=tree.fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise DiagnosticHold('OUTPUT_OR_NONCE_ALREADY_EXISTS')


def check_outputs(extractor, identifier, nonce):
    with extractor.ProtectedDirectory(BASE, OWNERS) as tree:
        for name in ('epoch7-observation-' + identifier + '.private.json',
                     'epoch7-diagnostic-' + identifier + '.private.json'):
            absent(tree, name)
        tree.check()
    if nonce is not None:
        stem = 'xj-p2-proof-' + nonce
        with extractor.ProtectedDirectory('/run', OWNERS) as tree:
            absent(tree, stem)
            tree.check()
        with extractor.ProtectedDirectory('/run/systemd/system', OWNERS) as tree:
            for suffix in ('.socket', '.service', '-broker.service', '-dashboard.service',
                           '-callback.service', '-native.service'):
                absent(tree, stem + suffix)
            tree.check()


def stage_kit(extractor):
    with extractor.ProtectedDirectory(BASE, OWNERS) as tree:
        try:
            os.stat('epoch7-recovery-candidate-r5', dir_fd=tree.fd, follow_symlinks=False)
        except FileNotFoundError:
            present = False
        else:
            present = True
        tree.check()
    if not present:
        archive = download(ARCHIVE_URL, ARCHIVE_SIZE, ARCHIVE_SHA)
        with bounded_stage(60):
            extractor.extract(archive, KIT, ARCHIVE_SHA, ENTRY_SHA, MANIFEST_SHA)
    # Reuse the frozen anchored regular-file reader. A symlink, partial tree,
    # extra file or mismatched old candidate is rejected, never repaired.
    with bounded_stage(60):
        raw = extractor.read_archive(KIT + '/epoch7_recovery_entry.py', OWNERS)
        need(len(raw) <= 1024 * 1024, 'ENTRY_BOUND')
        entry = authenticated_module(raw, ENTRY_SHA, 'reviewed_epoch7_entry', KIT + '/epoch7_recovery_entry.py')
        kit = entry.verify_kit(KIT, MANIFEST_SHA)
    need(kit.manifest['kit_source_commit'] == SOURCE and kit.manifest['kit_source_tree'] == TREE and
         len(kit.cache) == KIT_SOURCE_FILES, 'EXACT_SOURCE_KIT_REQUIRED')
    return entry, kit, 'VERIFIED_EXISTING' if present else 'EXTRACTED_AND_VERIFIED'


def public_observation(value):
    """Allow only fixed status values/digests from the already bounded entry."""
    allowed = {'operation': ('observe-only', 'observe-and-probe'),
        'kind': ('EPOCH7_OBSERVATION_ONLY_UNREVIEWED', 'EPOCH7_OBSERVATION_ONLY_HOLD'),
        'probe_stage': ('NOT_REQUESTED', 'HOLD_NOT_EXECUTED', 'HOLD_AFTER_ATTEMPT', 'RESULT_RECORDED'),
        'independent_acceptance': ('PENDING',), 'install_admission': ('NOT_GRANTED',),
        'production_resume': ('NOT_EXECUTED',)}
    result = {}
    for key, choices in allowed.items():
        need(value.get(key) in choices, 'OBSERVATION_STATUS')
        result[key] = value[key]
    for key in ('private_file_sha256', 'snapshot_sha256', 'policy_sha256', 'kit_manifest_sha256'):
        data = value.get(key)
        need((data is None and key in ('snapshot_sha256', 'policy_sha256')) or
             (type(data) is str and SHA.fullmatch(data)), 'OBSERVATION_DIGEST')
        result[key] = data
    need(result['kit_manifest_sha256'] == MANIFEST_SHA, 'OBSERVATION_KIT')
    for key in ('success', 'probe_observations_complete'):
        need(type(value.get(key)) is bool, 'OBSERVATION_BOOLEAN')
        result[key] = value[key]
    return result


def write_receipt(extractor, entry, identifier, result):
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False) + '\n').encode('ascii')
    need(len(raw) <= 16384, 'DIAGNOSTIC_RECEIPT_BOUND')
    leaf = 'epoch7-diagnostic-' + identifier + '.private.json'
    with extractor.ProtectedDirectory(BASE, OWNERS) as tree:
        fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=tree.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                need(count > 0, 'DIAGNOSTIC_RECEIPT_SHORT_WRITE')
                offset += count
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(tree.fd)
        tree.check()
    with entry.DescriptorTree(BASE) as tree:
        need(tree.read(leaf, 16384, private=True) == raw, 'DIAGNOSTIC_RECEIPT_READBACK')
        tree.recheck()
    return sha(raw)


def publication_gate():
    need(READY is True, 'IMMUTABLE_R5_PUBLICATION_NOT_READY')
    for value in (SOURCE,TREE,PUBLICATION):
        need(type(value) is str and re.fullmatch(r'[0-9a-f]{40}',value), 'IMMUTABLE_GIT_PIN')
    for value in (ARCHIVE_SHA,EXTRACTOR_SHA,ENTRY_SHA,MANIFEST_SHA):
        need(type(value) is str and SHA.fullmatch(value), 'IMMUTABLE_SOURCE_PIN')
    need(type(ARCHIVE_PATH) is str and re.fullmatch(
        r'evidence/p2-epoch7-access-repair-20261014/artifacts/[A-Za-z0-9_.-]+\.tar\.gz',ARCHIVE_PATH), 'IMMUTABLE_ARCHIVE_PATH')
    need(ARCHIVE_URL == PREFIX+PUBLICATION+'/'+ARCHIVE_PATH and
         EXTRACTOR_URL == PREFIX+SOURCE+'/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py',
         'IMMUTABLE_DOWNLOAD_SCOPE')
    need(type(ARCHIVE_SIZE) is int and 0<ARCHIVE_SIZE<=32*1024*1024 and
         type(EXTRACTOR_SIZE) is int and 0<EXTRACTOR_SIZE<=1024*1024 and
         type(KIT_SOURCE_FILES) is int and 1<=KIT_SOURCE_FILES<=1024, 'IMMUTABLE_SIZE_PINS')


class ScopeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse otherwise repeats arbitrary unrecognized argument contents.
        raise DiagnosticHold('CLI_SCOPE')


def validate_prior(entry,receipt_raw,observation_raw):
    need(type(receipt_raw) is bytes and len(receipt_raw)<=16384 and sha(receipt_raw)==PRIOR_RECEIPT_SHA,
         'PRIOR_RECEIPT_HASH')
    need(type(observation_raw) is bytes and len(observation_raw)<=67108864 and sha(observation_raw)==PRIOR_OBSERVATION_SHA,
         'PRIOR_OBSERVATION_HASH')
    receipt=entry.decode(receipt_raw);observation=entry.decode(observation_raw)
    need(type(receipt) is dict and type(receipt.get('schema')) is int and receipt['schema']==1 and
         receipt.get('kind')=='OWNER_R3_PREREQUISITE_DIAGNOSTIC' and receipt.get('stage')=='HOLD_RECORDED' and
         receipt.get('kit_source_commit')==PRIOR_SOURCE and receipt.get('kit_manifest_sha256')==PRIOR_MANIFEST and
         receipt.get('production_resume')=='NOT_EXECUTED' and receipt.get('install_admission')=='NOT_GRANTED',
         'PRIOR_DIAGNOSTIC_BINDING')
    need(not any(key in receipt for key in ('failure_code','reverification','workspace_cleanup','import_cleanup','timer_cleanup')),
         'PRIOR_CLEANUP_UNCERTAINTY')
    acl=receipt.get('exact_uid_acl')
    need(type(acl) is dict and acl.get('case')==UK_CASE and acl.get('source_sha256')==UK_TEST_SHA and
         acl.get('success') is True and acl.get('state')=='PASS_OBSERVED_FIXTURE_ONLY' and
         acl.get('scope')=='TWO_DISPOSABLE_TARGET_ACLS_NOT_PRODUCTION_DAC_ACCEPTANCE' and
         all(type(acl.get(key)) is int and acl[key]==value for key,value in
             (('tests',1),('failures',0),('errors',0),('skipped',0))),'PRIOR_UID_PROOF')
    old=receipt.get('observation')
    need(type(old) is dict and old.get('private_file_sha256')==PRIOR_OBSERVATION_SHA and
         old.get('kit_manifest_sha256')==PRIOR_MANIFEST and old.get('kind')=='EPOCH7_OBSERVATION_ONLY_HOLD' and
         old.get('probe_stage')=='HOLD_NOT_EXECUTED' and old.get('probe_observations_complete') is False,
         'PRIOR_OBSERVATION_BINDING')
    need(type(observation) is dict and type(observation.get('schema')) is int and observation['schema']==1 and
         observation.get('kind')=='EPOCH7_OBSERVATION_ONLY_HOLD','PRIOR_OBSERVATION_KIND')
    attempt=observation.get('finite_probe')
    need(type(attempt) is dict and attempt.get('nonce')==PRIOR_NONCE and attempt.get('stage')=='HOLD_NOT_EXECUTED' and
         attempt.get('resume_authority') is False and 'policy' not in attempt and 'result' not in attempt,
         'PRIOR_PROBE_NOT_STARTED')
    prior=receipt.get('prerequisite')
    need(type(prior) is dict and prior.get('kind')=='EPOCH7_OWNER_PREREQUISITE' and
         prior.get('stage')=='COMPLETE_PREREQUISITES_ONLY' and prior.get('cleanup_failed') is False and
         prior.get('automatic_retry') is False and prior.get('permission_widening_rollback') is False and
         prior.get('production_admission')=='NOT_GRANTED' and
         all(type(prior.get(key)) is int and prior[key]==0 for key in ('service_actions','database_writes')) and
         all(prior.get(key)==list(TARGETS) for key in ('authorized_targets','attempted','completed')),
         'PRIOR_COMPLETED_PREREQUISITE_REQUIRED')
    for label in ('guard_before','guard_after'):
        guard=prior.get(label)
        need(type(guard) is dict and type(guard.get('epoch')) is int and guard['epoch']==7 and
             guard.get('state')=='PREPARED','PRIOR_PREPARED_EPOCH')
    before=prior.get('before');after=prior.get('after')
    need(type(before) is dict and set(before)==set(TARGETS) and type(after) is dict and set(after)==set(TARGETS),
         'PRIOR_EXACT_TARGET_ROWS')
    for path in TARGETS:
        a,b=before[path],after[path]
        need(type(a) is dict and type(b) is dict and set(a)==set(b)==set(FIELDS) and
             all(type(a[k]) is int and type(b[k]) is int for k in FIELDS) and
             (a['uid'],a['gid'],a['mode'])==(1002,1002,0o775) and
             (b['uid'],b['gid'],b['mode'])==(1002,1002,0o755) and
             all(a[k]==b[k] for k in FIELDS if k not in ('mode','ctime_ns')),
             'PRIOR_NARROWING_METADATA')
    return after


def prior_files(entry):
    with entry.DescriptorTree(BASE) as tree:
        receipt_raw=tree.read(PRIOR_RECEIPT,16384,private=True)
        observation_raw=tree.read(PRIOR_OBSERVATION,67108864,private=True)
        tree.recheck()
    return validate_prior(entry,receipt_raw,observation_raw)


def metadata(info):
    value={key:getattr(info,'st_'+key) for key in FIELDS};value['mode']=stat.S_IMODE(info.st_mode);return value


def no_attributes(fd):
    for key in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,key)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'COMPLETED_DIRECTORY_ATTRIBUTE_READ')
        else:need(False,'COMPLETED_DIRECTORY_ATTRIBUTE')


class CompletedDirectories(object):
    """Exact0755 postconditions only. This class contains no mutation method."""
    def __init__(self,expected,_root='/',_owner=(1002,1002),_root_owner=(0,0),_root_mode=0o555):
        self.expected=expected;self.root=_root;self.owner=_owner;self.root_owner=_root_owner;self.root_mode=_root_mode
        self.held=[];self.rows=[]
    def authority(self,fd,path):
        info=os.fstat(fd)
        if path=='/':wanted=self.root_owner+(self.root_mode,)
        elif path=='/home':wanted=self.root_owner+(0o755,)
        else:wanted=self.owner+((0o755 if path in TARGETS else 0o700),)
        need(stat.S_ISDIR(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==wanted,
             'COMPLETED_DIRECTORY_AUTHORITY')
        no_attributes(fd)
        if path in TARGETS:need(metadata(info)==self.expected[path],'COMPLETED_DIRECTORY_PRIOR_POSTCONDITION')
        return metadata(info)
    def open(self,path,parent=None,name=None):
        fd=os.open(self.root if parent is None else name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),
                   **({} if parent is None else {'dir_fd':parent}))
        self.held.append(fd);pin=self.authority(fd,path)
        self.rows.append((fd,parent,name,path,pin));return fd
    def __enter__(self):
        try:
            need(type(self.expected) is dict and set(self.expected)==set(TARGETS),'COMPLETED_DIRECTORY_SCOPE')
            root=self.open('/');home=self.open('/home',root,'home');user=self.open(HOME,home,'xuanjun_dev')
            base=self.open(OPENCLAW,user,'.openclaw');self.open(TARGETS[0],base,'bin')
            tools=self.open(TARGETS[1],base,'tools');self.open(TARGETS[2],tools,'node-v24.21.0')
            self.check();return self
        except BaseException as error:
            try:self.close()
            except BaseException:error.diagnostic_directory_cleanup_failed=True
            raise
    def check(self):
        result={}
        for fd,parent,name,path,pin in self.rows:
            live=os.lstat(self.root) if parent is None else os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISDIR(live.st_mode) and self.authority(fd,path)==metadata(live)==pin,'COMPLETED_DIRECTORY_CHANGED')
            if path in TARGETS:result[path]=pin
        return result
    def close(self):
        pending,self.held=self.held,[];failure=None
        for fd in reversed(pending):
            try:os.close(fd)
            except BaseException as error:
                if failure is None:failure=error
        if failure is not None:
            failure.diagnostic_directory_cleanup_failed=True;raise failure
    def __exit__(self,kind,error,tb):
        try:
            with bounded_stage(60):self.close()
        except BaseException as failure:
            # If timer setup itself refused before close, still attempt each
            # remaining owned descriptor once. Ambiguously closed FDs are gone
            # from self.held and are never retried.
            if self.held:
                try:self.close()
                except BaseException:pass
            if error is not None:error.diagnostic_directory_cleanup_failed=True
            else:
                failure.diagnostic_directory_cleanup_failed=True;raise
        return False


def check_continuation(entry,expected,directories,result):
    with bounded_stage(60):
        after=prior_files(entry)
        need(after==expected,'PRIOR_FILES_RECHECK')
        current=directories.check()
        need(current==expected,'COMPLETED_DIRECTORY_RECHECK')
        result['continuation']['after']=current


@contextlib.contextmanager
def continuation_recheck(entry,expected,directories,result):
    try:yield
    except BaseException as primary:
        try:check_continuation(entry,expected,directories,result)
        except BaseException:primary.diagnostic_continuation_reverification_failed=True
        raise
    else:check_continuation(entry,expected,directories,result)


def cleanup_failures(result,error):
    for label in ('reverification','timer_cleanup','directory_cleanup','continuation_reverification'):
        if getattr(error,'diagnostic_'+label+'_failed',False) is True:result[label]='FAILED_OR_INTERRUPTED'
    seen=set();current=error
    for unused in range(8):
        if current is None or id(current) in seen:break
        seen.add(id(current))
        if type(current) is ValueError and current.args in (
                ('EXISTING_LOCKS_CLEANUP_UNKNOWN',),('NODE_REFERENCE_CLEANUP_UNKNOWN',),
                ('READER_PARENT_CLEANUP_UNKNOWN',)):
            result['cleanup_uncertainty']=True;break
        current=current.__cause__


def run(identifier,nonce=None,execute_reviewed_diagnostic=False,execute_reviewed_probe=False):
    result={'schema':1,'kind':'OWNER_R5_RECEIPT_BOUND_CONTINUATION','stage':'PRECONDITIONS','success':False,
        'kit_source_commit':SOURCE,'kit_manifest_sha256':MANIFEST_SHA,'install_admission':'NOT_GRANTED',
        'production_resume':'NOT_EXECUTED','independent_acceptance':'PENDING','permission_repairs':'NOT_EXECUTED',
        'uid_fixture':'PRIOR_HASH_BOUND_RESULT_ONLY','approval_obtained_by_wrapper':False}
    extractor=entry=None
    try:
        publication_gate()
        need(execute_reviewed_diagnostic is True,'EXPLICIT_DIAGNOSTIC_ACK_REQUIRED')
        need(type(identifier) is str and re.fullmatch(r'[0-9a-f]{16}',identifier) and identifier!=PRIOR_ID,'FRESH_OBSERVATION_ID')
        need(type(execute_reviewed_probe) is bool and ((nonce is None and not execute_reviewed_probe) or
             (type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}',nonce) and nonce!=PRIOR_NONCE and execute_reviewed_probe)),
             'FRESH_EXPLICIT_PROBE_SCOPE')
        host_boundary();result['stage']='BOOTSTRAP_SOURCE'
        extractor=authenticated_module(download(EXTRACTOR_URL,EXTRACTOR_SIZE,EXTRACTOR_SHA),
            EXTRACTOR_SHA,'reviewed_epoch7_extractor','<authenticated-epoch7-extractor>')
        check_outputs(extractor,identifier,nonce);result['stage']='KIT_STAGE'
        entry,kit,state=stage_kit(extractor);result['kit_staging']=state
        result['stage']='PRIOR_COMPLETION_AUTHENTICATION'
        with bounded_stage(60):expected=prior_files(entry)
        result['continuation']={'prior_diagnostic_sha256':PRIOR_RECEIPT_SHA,'prior_observation_sha256':PRIOR_OBSERVATION_SHA,
            'prior_uid_fixture':'PASS_OBSERVED_FIXTURE_ONLY','prior_permission_narrowing':'COMPLETE_PREREQUISITES_ONLY',
            'fresh_postcondition':'NOT_VERIFIED','permission_repairs':'NOT_EXECUTED'}
        with reverify_after(entry):
            with preserve_cleanup(contextlib.ExitStack(), 'directory_cleanup') as stack:
                with bounded_stage(60):directories=stack.enter_context(CompletedDirectories(expected))
                with bounded_stage(60):result['continuation']['before']=directories.check()
                result['continuation']['fresh_postcondition']='EXACT_PRIOR_0755_POSTCONDITIONS'
                with continuation_recheck(entry,expected,directories,result):
                    result['stage']='OBSERVATION_AND_OPTIONAL_PROBE';result['probe_requested']=execute_reviewed_probe
                    output=BASE+'/epoch7-observation-'+identifier+'.private.json'
                    observed=kit.observe(output,nonce if execute_reviewed_probe else None,execute_reviewed_probe)
                    result['observation']=public_observation(observed)
        result['success']=result['observation']['success']
        result['stage']='DIAGNOSTIC_RECORDED' if result['success'] else 'HOLD_RECORDED'
    except (KeyboardInterrupt,SystemExit) as error:
        result.update(success=False,failure_code='STAGE_DEADLINE' if isinstance(error,StageTimeout) else 'INTERRUPTED',
            outcome='POTENTIALLY_PARTIAL_NO_AUTOMATIC_RETRY');cleanup_failures(result,error)
    except Exception as error:
        code=error.args[0] if type(error) is DiagnosticHold and len(error.args)==1 else 'BOUNDARY_OR_DEPENDENCY_FAILED'
        if type(code) is not str or not re.fullmatch(r'[A-Z0-9_]{1,96}',code):code='BOUNDARY_OR_DEPENDENCY_FAILED'
        result.update(success=False,failure_code=code,outcome='POTENTIALLY_PARTIAL_NO_AUTOMATIC_RETRY');cleanup_failures(result,error)
    if entry is not None:
        try:
            with bounded_stage(30):result['diagnostic_receipt_sha256']=write_receipt(extractor,entry,identifier,result)
        except BaseException:result['success']=False;result['diagnostic_receipt']='FAILED_OR_INTERRUPTED'
    return result


def main(argv=None):
    parser=ScopeParser(description=__doc__)
    parser.add_argument('--observation-id',required=True);parser.add_argument('--nonce')
    parser.add_argument('--execute-reviewed-diagnostic',action='store_true')
    parser.add_argument('--execute-reviewed-probe',action='store_true')
    try:args=parser.parse_args(argv)
    except DiagnosticHold:
        result={'schema':1,'kind':'OWNER_R5_RECEIPT_BOUND_CONTINUATION','stage':'CLI','failure_code':'CLI_SCOPE',
                'success':False,'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    else:result=run(args.observation_id,args.nonce,args.execute_reviewed_diagnostic,args.execute_reviewed_probe)
    print(json.dumps(result,sort_keys=True));return 0 if result['success'] else 2


if __name__=='__main__':sys.exit(main())
