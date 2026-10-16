#!/usr/bin/env python3
"""UNBOUND successor preparation delivery. No installation or approval operation."""
import argparse,ast,base64,zlib,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,time,types,urllib.request

PINS_BOUND=False
PUBLICATION_COMMIT=None
RAW_PREFIX='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/c-claim-successor/preparation/'
CAND='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
PREP_ROOT=CAND+'/epoch7-preparation-candidate-r7-claim-successor'
KIT_ROOT=CAND+'/epoch7-recovery-candidate-r7-resourcebind'
HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCES={'epoch7_prepare_successor.py': (None, None)}

COMPILER_ROOT=CAND+'/epoch7-recovery-candidate-r7-claim-successor'
ARCHIVE_COMMIT=None
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/c-claim-successor/artifact/epoch7-kit-claim-successor.tar.gz'
ARCHIVE_SHA=None
ARCHIVE_SIZE=None
COMPILER_MANIFEST_SHA=None
COMPILER_ENTRY_SHA=None
COMPILER_SOURCE=None
COMPILER_TREE=None
COMPILER_CACHE_COUNT=256
COMPILER_ENTRY_BYTES=None
EXTRACTOR_SHA='7de66b8c760de9f26de158fda95c80b8c8b3052025bb1c65bc0ecccd7a1afb03'
EXTRACTOR_SIZE=10222
EXTRACTOR_Z='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'

STAGE_SECONDS=60
STATUS_SECONDS=5
PHASE='INPUT_VALIDATION'
CODES=frozenset(('UNBOUND','PREPARER_BINDING','RUNTIME_SCOPE','ARGUMENTS','ROOT_HOST','ISOLATED','SOURCE_SET','SOURCE_PIN','RESPONSE','PROPOSAL_SIZE_BOUND',
 'REDIRECT','ENCODING','LENGTH','DEADLINE','EXISTING_TIMER','ANCESTRY','XATTR','PATH_RACE','PARENT_NAMES',
 'DIRECTORY','INVENTORY','PREPARATION_OUTPUT_SCOPE','PREPARATION_RESULT_SCOPE','REVIEW_INPUT','FILE_AUTHORITY','FILE_RACE','FILE_BYTES','SHORT_WRITE','COMPILER_BINDING','COMPILER_SOURCE','COMPILER_CACHE','COMPILER_STATE','COMPILER_RECHECK','EXTRACTOR_PIN','OWNED_PARENT','STATUS_BOUND','LABEL_SOURCE_BOUND'))

PHASES=frozenset(('INPUT_VALIDATION','DOWNLOAD_ALL','LOAD_VERIFIED_PREPARER','STAGE_COMPILER','STAGE_EXACT','PREPARE_PRIVATE_PLAN','VERIFY_STAGING_AFTER_PREPARATION','DELIVER_STATUS'))
ERROR_CLASSES=frozenset(('ValueError','KeyError','TypeError','OSError','FileNotFoundError','PermissionError','TimeoutError','InterruptedError','KeyboardInterrupt','SystemExit','Hold','DeadlineError','CleanupError','DiagnosticHold','Deadline'))
PUBLIC_CODE_PATHS=frozenset(('epoch7_recovery_entry.py', 'helpers/epoch3_service_containment.py', 'helpers/epoch7_acceptance_rows.py', 'helpers/epoch7_additive_identity.py', 'helpers/epoch7_additive_server.py', 'helpers/epoch7_approval.py', 'helpers/epoch7_bindings.py', 'helpers/epoch7_bounded_stager.py', 'helpers/epoch7_command_runner.py', 'helpers/epoch7_complete_approval.py', 'helpers/epoch7_claim_successor.py', 'helpers/epoch7_delta.py', 'helpers/epoch7_exact_access.py', 'helpers/epoch7_host_containment.py', 'helpers/epoch7_host_driver.py', 'helpers/epoch7_host_factory.py', 'helpers/epoch7_host_observer.py', 'helpers/epoch7_host_phases.py', 'helpers/epoch7_injected_recovery.py', 'helpers/epoch7_live_controls.py', 'helpers/epoch7_nginx_recipe.py', 'helpers/epoch7_openclaw_recipe.py', 'helpers/epoch7_owner_prerequisite.py', 'helpers/epoch7_pre_active_guards.py', 'helpers/epoch7_protected_fs.py', 'helpers/epoch7_python_identity.py', 'helpers/epoch7_quiet_startup.py', 'helpers/epoch7_recovery_sequence.py', 'helpers/epoch7_resource_observer.py', 'helpers/epoch7_resource_plan.py', 'helpers/epoch7_runtime_acceptance.py', 'helpers/epoch7_runtime_effects.py', 'helpers/epoch7_service_contract.py', 'helpers/epoch7_service_roles.py', 'helpers/epoch7_snapshot.py', 'helpers/epoch7_timer_tail.py', 'helpers/epoch7_unit_transitions.py', 'helpers/exact_access_plan.py', 'helpers/node_sqlite_probe.py', 'helpers/observe_epoch7.py', 'helpers/openclaw_metadata.py', 'helpers/probe_driver.py', 'helpers/probe_helpers.py', 'helpers/probe_metadata.py', 'helpers/protected_command_evidence.py', 'helpers/reviewed_database.py', 'helpers/reviewed_publisher.py', 'helpers/reviewed_scanner.py', 'helpers/snapshot_io.py', 'helpers/unit_metadata.py', 'xuanjun-p2-package/stage1/activation_control.py', 'xuanjun-p2-package/stage1/callback_schema_gate.py', 'xuanjun-p2-package/stage1/codex_app_server_worker.py', 'xuanjun-p2-package/stage1/codex_worker.py', 'xuanjun-p2-package/stage1/dependency_evidence_view.py', 'xuanjun-p2-package/stage1/development_loop.py', 'xuanjun-p2-package/stage1/development_pipeline.py', 'xuanjun-p2-package/stage1/development_service.py', 'xuanjun-p2-package/stage1/execution_ledger.py', 'xuanjun-p2-package/stage1/execution_supervision.py', 'xuanjun-p2-package/stage1/github_issue_consumer.py', 'xuanjun-p2-package/stage1/ledger_backup.py', 'xuanjun-p2-package/stage1/ledger_cutover_transaction.py', 'xuanjun-p2-package/stage1/ledger_install_stage.py', 'xuanjun-p2-package/stage1/ledger_read_client.py', 'xuanjun-p2-package/stage1/ledger_read_projection.py', 'xuanjun-p2-package/stage1/ledger_read_transport.py', 'xuanjun-p2-package/stage1/ledger_server_identity.py', 'xuanjun-p2-package/stage1/ledger_service.py', 'xuanjun-p2-package/stage1/legacy_host_adapter.py', 'xuanjun-p2-package/stage1/legacy_quiescence.py', 'xuanjun-p2-package/stage1/mechanical_wake.py', 'xuanjun-p2-package/stage1/mechanical_wake_service.py', 'xuanjun-p2-package/stage1/native_child_adapter.py', 'xuanjun-p2-package/stage1/native_gateway_controller.py', 'xuanjun-p2-package/stage1/native_github_notifier.py', 'xuanjun-p2-package/stage1/native_ledger_bridge.py', 'xuanjun-p2-package/stage1/native_ledger_operations.py', 'xuanjun-p2-package/stage1/native_peer_identity.py', 'xuanjun-p2-package/stage1/native_pipeline_runtime.py', 'xuanjun-p2-package/stage1/native_snapshot_access.py', 'xuanjun-p2-package/stage1/owner_approval_dispatch.py', 'xuanjun-p2-package/stage1/owner_callback_server.py', 'xuanjun-p2-package/stage1/owner_dashboard.py', 'xuanjun-p2-package/stage1/owner_feishu_bridge_cycle.py', 'xuanjun-p2-package/stage1/owner_feishu_claim_guard.py', 'xuanjun-p2-package/stage1/owner_feishu_history.py', 'xuanjun-p2-package/stage1/owner_feishu_https.py', 'xuanjun-p2-package/stage1/owner_feishu_ledger_endpoint.py', 'xuanjun-p2-package/stage1/owner_feishu_transport.py', 'xuanjun-p2-package/stage1/owner_notification_outbox.py', 'xuanjun-p2-package/stage1/owner_process_identity.py', 'xuanjun-p2-package/stage1/owner_update_router.py', 'xuanjun-p2-package/stage1/p2_auxiliary_isolation.py', 'xuanjun-p2-package/stage1/p2_bootstrap_files.py', 'xuanjun-p2-package/stage1/p2_fixed_host_runtime.py', 'xuanjun-p2-package/stage1/p2_gateway_relay.py', 'xuanjun-p2-package/stage1/p2_install_entrypoint.py', 'xuanjun-p2-package/stage1/p2_legacy_adoption.py', 'xuanjun-p2-package/stage1/p2_prerequisites.py', 'xuanjun-p2-package/stage1/p2_publisher_bootstrap.py', 'xuanjun-p2-package/stage1/p2_rpm_prerequisites.py', 'xuanjun-p2-package/stage1/p2_sandbox_profile.py', 'xuanjun-p2-package/stage1/p2_service_context_preflight.py', 'xuanjun-p2-package/stage1/p2_tls_lifecycle.py', 'xuanjun-p2-package/stage1/root_broker.py', 'xuanjun-p2-package/stage1/run_usage_projection.py', 'xuanjun-p2-package/stage1/task_cost_projection.py', 'xuanjun-p2-package/stage1/task_supervisor_inventory_adapter.py', 'xuanjun-p2-package/stage1/telegram_owner_transport.py', 'xuanjun-p2-package/stage1/uk_owner_callback_core.py', 'xuanjun-p2-package/stage1/uk_owner_notify_worker.py'))

class Hold(ValueError):pass
class DeadlineError(Exception):pass
class CleanupError(Exception):pass
class StatusDeliveryError(Exception):pass

def need(value,code):
    if not value:raise Hold(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp(info):return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
def check(end):need(time.monotonic()<end,'DEADLINE')
def no_attributes(fd):
    for key in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,key)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'XATTR')
        else:raise Hold('XATTR')
def close_all(fds,primary=None):
    failed=False
    for fd in reversed(fds):
        try:os.close(fd)
        except BaseException:failed=True
    if failed:
        if primary is None:raise CleanupError()
        primary.delivery_cleanup_failed=True

@contextlib.contextmanager
def budget(seconds):
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'EXISTING_TIMER')
    old=signal.getsignal(signal.SIGALRM);end=time.monotonic()+seconds;primary=None
    def expired(unused_signum,unused_frame):raise DeadlineError()
    try:
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds,0)
        yield end;check(end)
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,old)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.delivery_cleanup_failed=True

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise Hold('REDIRECT')

def bound():
    """Publication and every dependency pin are mandatory before any effects."""
    need(PINS_BOUND is True and all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v)
         for v in (PUBLICATION_COMMIT,ARCHIVE_COMMIT,COMPILER_SOURCE,COMPILER_TREE)),'UNBOUND')
    need(all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v)
         for v in (ARCHIVE_SHA,COMPILER_MANIFEST_SHA,COMPILER_ENTRY_SHA)),'UNBOUND')
    need(type(ARCHIVE_SIZE) is int and 0<ARCHIVE_SIZE<=32*1024*1024 and
         type(COMPILER_ENTRY_BYTES) is int and 0<COMPILER_ENTRY_BYTES<=1024*1024,'UNBOUND')
    need(type(SOURCES) is dict and set(SOURCES)=={'epoch7_prepare_successor.py'},'UNBOUND')
    for pin in SOURCES.values():
        need(type(pin) is tuple and len(pin)==2 and type(pin[0]) is str and
             re.fullmatch('[0-9a-f]{64}',pin[0]) and type(pin[1]) is int and
             0<pin[1]<=1024*1024,'UNBOUND')


def validate_sources(cache):
    need(type(cache) is dict and set(cache)==set(SOURCES),'SOURCE_SET')
    for name,(digest,size) in SOURCES.items():
        need(type(cache[name]) is bytes and len(cache[name])==size and sha(cache[name])==digest,'SOURCE_PIN')
    return cache

def fetch_sources(end):
    bound();cache={}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    for name,(digest,size) in sorted(SOURCES.items()):
        check(end);url=RAW_PREFIX+PUBLICATION_COMMIT+'/'+PUBLIC_PREFIX+name
        request=urllib.request.Request(url,headers={'Accept-Encoding':'identity'})
        response=None;primary=None
        try:
            response=opener.open(request,timeout=min(10,max(.001,end-time.monotonic())))
            need(response.status==200 and response.geturl()==url,'RESPONSE')
            need(response.headers.get('Content-Encoding','identity')=='identity','ENCODING')
            length=response.headers.get('Content-Length');need(length is None or length==str(size),'LENGTH')
            raw=response.read(size+1);check(end)
            need(len(raw)==size and sha(raw)==digest,'SOURCE_PIN');cache[name]=raw
        except BaseException as error:primary=error;raise
        finally:
            if response is not None:
                try:response.close()
                except BaseException:
                    if primary is None:raise CleanupError()
                    primary.delivery_cleanup_failed=True
    check(end);return validate_sources(cache)

def fetch_archive(end):
    bound();url=RAW_PREFIX+ARCHIVE_COMMIT+'/'+ARCHIVE_PATH
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    response=None;primary=None
    try:
        response=opener.open(urllib.request.Request(url,headers={'Accept-Encoding':'identity'}),timeout=min(10,max(.001,end-time.monotonic())))
        need(response.status==200 and response.geturl()==url,'RESPONSE')
        need(response.headers.get('Content-Encoding','identity')=='identity','ENCODING')
        length=response.headers.get('Content-Length');need(length is None or length==str(ARCHIVE_SIZE),'LENGTH')
        raw=response.read(ARCHIVE_SIZE+1);check(end)
        need(len(raw)==ARCHIVE_SIZE and sha(raw)==ARCHIVE_SHA,'SOURCE_PIN');return raw
    except BaseException as error:primary=error;raise
    finally:
        if response is not None:
            try:response.close()
            except BaseException:
                if primary is None:raise CleanupError()
                primary.delivery_cleanup_failed=True

def safe_extractor_bytes():
    blob=zlib.decompressobj();code=blob.decompress(base64.b64decode(EXTRACTOR_Z,validate=True),EXTRACTOR_SIZE+1)
    need(blob.eof and not blob.unused_data and not blob.unconsumed_tail and len(code)==EXTRACTOR_SIZE and sha(code)==EXTRACTOR_SHA,'EXTRACTOR_PIN')
    return code

def compiler_inputs(raw):
    need(type(raw) is bytes and len(raw)==ARCHIVE_SIZE and sha(raw)==ARCHIVE_SHA,'SOURCE_PIN')
    code=safe_extractor_bytes()
    extractor=types.ModuleType('verified_compiler_extractor');extractor.__file__='<verified-compiler-extractor>'
    exec(compile(code,extractor.__file__,'exec'),extractor.__dict__)
    need(extractor.ROOT_NAME=='epoch7-recovery-candidate-r7-claim-successor','COMPILER_BINDING')
    files,dirs=extractor.inspect_archive(raw,ARCHIVE_SHA,COMPILER_ENTRY_SHA,COMPILER_MANIFEST_SHA)
    need(len(files)==COMPILER_CACHE_COUNT+1 and len(files['epoch7_recovery_entry.py'])==COMPILER_ENTRY_BYTES,'COMPILER_CACHE')
    entry=types.ModuleType('verified_compiler_entry');entry.__file__=COMPILER_ROOT+'/epoch7_recovery_entry.py'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec'),entry.__dict__)
    manifest=entry.decode(files['recovery-kit-manifest.json']);entry.validate_manifest(manifest)
    need(manifest['kit_source_commit']==COMPILER_SOURCE and manifest['kit_source_tree']==COMPILER_TREE and
         manifest['production_resume']=='AUTHENTICATED_CLAIM_SUCCESSOR_APPROVAL_GATED_SINGLE_ATTEMPT' and
         manifest['status']=='CLAIM_SUCCESSOR_CANDIDATE_REQUIRES_NEW_EXACT_APPROVAL' and
         len(manifest['files'])==COMPILER_CACHE_COUNT,'COMPILER_SOURCE')
    runtime=entry.validate_runtime(manifest,files)
    need(type(runtime) is dict and type(runtime.get('files')) is dict and len(runtime['files'])==107,'RUNTIME_SCOPE')
    return extractor,entry,files

def compiler_summary(state):
    need(state in ('NOT_STAGED','EXTRACTION_ATTEMPTED_NOT_VERIFIED','VERIFY_EXISTING_FAILED','EXTRACTED_AND_VERIFIED','VERIFIED_EXISTING'),'COMPILER_STATE')
    return {'state':state,'path':COMPILER_ROOT,'archive_sha256':ARCHIVE_SHA,'kit_manifest_sha256':COMPILER_MANIFEST_SHA,
            'entry_sha256':COMPILER_ENTRY_SHA,'kit_source_commit':COMPILER_SOURCE,'kit_source_tree':COMPILER_TREE,
            'source_files':COMPILER_CACHE_COUNT,'runtime_effects':'NOT_EXECUTED'}

def verify_compiler(entry,files,end):
    check(end)
    try:kit=entry.verify_kit(COMPILER_ROOT,COMPILER_MANIFEST_SHA)
    except BaseException as error:
        # The frozen reader may fail during constructor/close; retain uncertainty.
        error.delivery_cleanup_failed=True;raise
    expected={name:raw for name,raw in files.items() if name!='recovery-kit-manifest.json'}
    need(kit.cache==expected and len(kit.cache)==COMPILER_CACHE_COUNT and
         kit.manifest['kit_source_commit']==COMPILER_SOURCE and kit.manifest['kit_source_tree']==COMPILER_TREE,'COMPILER_RECHECK')
    check(end);return kit

def stage_compiler(raw,extractor,entry,files,end):
    state='NOT_STAGED';entered=False
    try:
        entered=True
        with extractor.ProtectedDirectory(CAND,((0,0),)) as tree:
            try:os.stat('epoch7-recovery-candidate-r7-claim-successor',dir_fd=tree.fd,follow_symlinks=False)
            except FileNotFoundError:present=False
            else:present=True
            tree.check()
        entered=False;check(end)
        state='VERIFY_EXISTING_FAILED' if present else 'EXTRACTION_ATTEMPTED_NOT_VERIFIED'
        if not present:
            entered=True
            extractor.extract(raw,COMPILER_ROOT,ARCHIVE_SHA,COMPILER_ENTRY_SHA,COMPILER_MANIFEST_SHA)
            entered=False;check(end)
        verify_compiler(entry,files,end)
        return compiler_summary('VERIFIED_EXISTING' if present else 'EXTRACTED_AND_VERIFIED')
    except BaseException as error:
        if entered or state=='EXTRACTION_ATTEMPTED_NOT_VERIFIED':error.delivery_cleanup_failed=True
        error.compiler_staging=compiler_summary(state);raise


def authority(fd,mode=None):
    info=os.fstat(fd)
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and not info.st_mode&0o7022 and
         (mode is None or stat.S_IMODE(info.st_mode)==mode),'ANCESTRY')
    no_attributes(fd);return stamp(info)

def names(fd,maximum):
    row=os.listdir(fd);need(len(row)<=maximum and len(row)==len(set(row)) and all(type(v) is str and 0<len(v)<=255 and '/' not in v and '\x00' not in v for v in row),'PARENT_NAMES')
    return tuple(sorted(row))

def parent_walk(held,end):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd)
    rows=[(fd,None,None,'/',authority(fd))];path=''
    for name in CAND[1:].split('/'):
        check(end);parent=fd;path+='/'+name
        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(fd)
        row=authority(fd);need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==row,'PATH_RACE')
        rows.append((fd,parent,name,path,row))
    return rows

def recheck_parents(rows,parent_after):
    for fd,parent,name,path,before in rows:
        actual=authority(fd);wanted=parent_after if path==CAND else before
        need(actual==wanted,'PATH_RACE')
        if parent is not None:need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==actual,'PATH_RACE')

def read_file(directory,name,raw,end):
    check(end);before=os.stat(name,dir_fd=directory,follow_symlinks=False);fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory);primary=None
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink,info.st_size)==(0,0,0o600,1,len(raw)),'FILE_AUTHORITY')
        need(stamp(before)==stamp(info),'FILE_RACE');no_attributes(fd);parts=[];count=0
        while True:
            check(end);part=os.read(fd,min(16384,len(raw)+1-count))
            if not part:break
            count+=len(part);need(count<=len(raw),'FILE_BYTES');parts.append(part)
        need(b''.join(parts)==raw,'FILE_BYTES');no_attributes(fd)
        need(stamp(os.fstat(fd))==stamp(info)==stamp(os.stat(name,dir_fd=directory,follow_symlinks=False)),'FILE_RACE')
        check(end);return stamp(info)
    except BaseException as error:primary=error;raise
    finally:close_all([fd],primary)

def stage(cache,end,allow_create=True):
    """Exclusive fixed directory; a partial attempt is retained and reported."""
    validate_sources(cache);need(os.geteuid()==os.getegid()==0,'ROOT_HOST')
    held=[];created=[];primary=None;result=None
    try:
        rows=parent_walk(held,end);parent=rows[-1][0];parent_before=rows[-1][4];before_names=names(parent,1024)
        need(authority(parent)==parent_before,'PATH_RACE');leaf='epoch7-preparation-candidate-r7-claim-successor'
        try:before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:
            need(allow_create is True,'DIRECTORY')
            check(end);os.mkdir(leaf,0o700,dir_fd=parent);created.append(PREP_ROOT);before=os.stat(leaf,dir_fd=parent,follow_symlinks=False);new=True
        else:new=False
        need(stat.S_ISDIR(before.st_mode),'DIRECTORY')
        directory=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(directory)
        start=authority(directory,0o700);need(stamp(before)==start,'PATH_RACE')
        need(names(directory,1)==(() if new else tuple(sorted(SOURCES))),'INVENTORY')
        if new:
            for name in sorted(SOURCES):
                check(end);raw=cache[name];fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory);created.append(PREP_ROOT+'/'+name);file_primary=None
                try:
                    info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),'FILE_AUTHORITY');no_attributes(fd)
                    offset=0
                    while offset<len(raw):
                        check(end);count=os.write(fd,raw[offset:offset+16384]);need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=count
                    os.fsync(fd);check(end)
                except BaseException as error:file_primary=error;raise
                finally:close_all([fd],file_primary)
            os.fsync(directory);os.fsync(parent);check(end)
        current=authority(directory,0o700)
        need(current[:6]==start[:6] and (new or current==start),'DIRECTORY')
        expected_names=tuple(sorted(SOURCES));need(names(directory,1)==expected_names,'INVENTORY')
        observed={name:read_file(directory,name,cache[name],end) for name in sorted(SOURCES)}
        for name in sorted(SOURCES):need(stamp(os.stat(name,dir_fd=directory,follow_symlinks=False))==observed[name],'FILE_RACE')
        need(authority(directory,0o700)==current and names(directory,1)==expected_names and
             stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==current,'PATH_RACE')
        parent_after=authority(parent)
        if new:
            need(parent_after[:5]==parent_before[:5] and parent_after[5]==parent_before[5]+1 and names(parent,1024)==tuple(sorted(before_names+(leaf,))),'OWNED_PARENT')
        else:need(parent_after==parent_before and names(parent,1024)==before_names,'OWNED_PARENT')
        recheck_parents(rows,parent_after);check(end)
        result={'state':'STAGED_EXACT' if new else 'REUSED_EXACT','path':PREP_ROOT,
                'files':{name:{'sha256':SOURCES[name][0],'bytes':SOURCES[name][1]} for name in sorted(SOURCES)},'created_paths':list(created)}
        return result
    except BaseException as error:primary=error;error.delivery_created_paths=list(created);raise
    finally:
        try:close_all(held,primary)
        except BaseException as error:error.delivery_created_paths=list(created);raise

def preparer(cache):
    validate_sources(cache)
    module=types.ModuleType('verified_epoch7_successor_preparer')
    module.__file__=PREP_ROOT+'/epoch7_prepare_successor.py'
    exec(compile(cache['epoch7_prepare_successor.py'],module.__file__,'exec'),module.__dict__)
    module.require_binding()
    need(module.CAND==CAND and module.HOST==HOST and module.OLD_ROOT==KIT_ROOT and
         module.NEW_ROOT==COMPILER_ROOT and module.NEW_KIT_SHA==COMPILER_MANIFEST_SHA and
         module.NEW_ENTRY_SHA==COMPILER_ENTRY_SHA and module.NEW_ENTRY_BYTES==COMPILER_ENTRY_BYTES and
         module.NEW_SOURCE==COMPILER_SOURCE and module.NEW_TREE==COMPILER_TREE and
         type(module.SECONDS) is int and module.SECONDS==120 and
         all(callable(getattr(module,name,None)) for name in ('prepare','budget','cleanup_unknown')),'PREPARER_BINDING')
    return module


def public_labels(cache):
    labels=set(CODES)
    for raw in cache.values():
        need(type(raw) is bytes and len(raw)<=1048576,'LABEL_SOURCE_BOUND')
        for node in ast.walk(ast.parse(raw.decode('utf-8'))):
            value=node.s if isinstance(node,ast.Str) else None
            if type(value) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,119}',value):
                labels.add(value)
                for prefix in ('EPOCH7_PREP_','EPOCH7_KIT_','EPOCH7_EXTRACT_','EPOCH7_HOST_','CLAIM_SUCCESSOR_'):labels.add(prefix+value)
    return frozenset(labels)

def code_locations(error):
    rows=[];tb=error.__traceback__;count=0
    while tb is not None and count<64:
        count+=1;frame=tb.tb_frame;name=frame.f_code.co_filename;label=None
        if frame.f_globals is globals():label='delivery/epoch7_prepare_successor_delivery.py'
        elif name=='<verified-compiler-extractor>':label='delivery/extract_epoch7_successor_kit.py'
        elif name=='<verified-preparation-delivery>':label='delivery/epoch7_prepare_successor_delivery.py'
        elif name in tuple(PREP_ROOT+'/'+item for item in ('epoch7_prepare_successor.py',)):
            label='preparation/'+name.rsplit('/',1)[1]
        elif name.startswith(COMPILER_ROOT+'/') and name[len(COMPILER_ROOT)+1:] in PUBLIC_CODE_PATHS:
            label='compiler-kit/'+name[len(COMPILER_ROOT)+1:]
        elif name.startswith(KIT_ROOT+'/') and name[len(KIT_ROOT)+1:] in PUBLIC_CODE_PATHS:
            label='kit/'+name[len(KIT_ROOT)+1:]
        elif name in ('<hash-pinned-build_epoch5_runtime>','<hash-pinned-inspect_epoch3>',
                      '<hash-pinned-prepare_epoch5_bindings>','<hash-pinned-epoch5_plan>',
                      '<hash-pinned-identity-renderer>'):
            label='historical/'+name[1:-1]
        if label is not None and type(tb.tb_lineno) is int and 0<tb.tb_lineno<=100000:
            rows.append({'source':label,'line':tb.tb_lineno})
        tb=tb.tb_next
    return rows[-8:]

def failure(error,outer,preparer,labels):
    inner='PREPARE_SUCCESSOR' if outer=='PREPARE_PRIVATE_PLAN' and preparer is not None else 'UNAVAILABLE'
    allowed=set(labels)|set(CODES)
    args=error.args if type(error.args) is tuple else ()
    label=args[0] if len(args)==1 and (type(error) in (ValueError,Hold) or (preparer is not None and type(error) is preparer.Hold)) else None
    if type(label) is not str or label not in allowed:label=None
    kind=type(error).__name__;kind=kind if kind in ERROR_CLASSES else 'DEPENDENCY_ERROR'
    cleanup=isinstance(error,CleanupError) or bool(getattr(error,'delivery_cleanup_failed',False)) or bool(getattr(error,'preparation_cleanup_failed',False)) or bool(getattr(error,'cleanup_unknown',False))
    if preparer is not None:cleanup=cleanup or preparer.cleanup_unknown(error)
    return {'schema':1,'state':'HOLD','phase':outer if outer in PHASES else 'INPUT_VALIDATION',
        'preparation_phase':inner,'failure_code':kind,'failure_label':label,
        'code_locations':code_locations(error),'cleanup_unknown':cleanup,
        'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}

def retained_staging(error):
    """Only the fixed public staging inventory may survive a failed projection."""
    allowed=set((PREP_ROOT,))|set(PREP_ROOT+'/'+name for name in SOURCES)
    value=getattr(error,'delivery_created_paths',[])
    paths=[item for item in value if type(item) is str and item in allowed] if type(value) is list and len(value)<=2 else []
    result={'created_paths':paths,'staging':None}
    value=getattr(error,'delivery_staging',None)
    if type(value) is dict and value.get('state') in ('STAGED_EXACT','REUSED_EXACT') and value.get('path')==PREP_ROOT:
        files={name:{'sha256':SOURCES[name][0],'bytes':SOURCES[name][1]} for name in sorted(SOURCES)}
        if value.get('files')==files and value.get('created_paths')==paths:
            result['staging']={'state':value['state'],'path':PREP_ROOT,'files':files,'created_paths':list(paths)}
    return result

def retained_outputs(error):
    """Keep only bounded fixed private-output path/hash/length metadata."""
    prefixes={'epoch7-successor-approved-plan-':2*1024*1024,'epoch7-successor-resume-inputs-':64*1024*1024,'epoch7-successor-review-packet-':2*1024*1024}
    def path_scope(path):
        need(type(path) is str and os.path.dirname(path)==CAND,'PREPARATION_OUTPUT_SCOPE')
        name=os.path.basename(path)
        matches=[prefix for prefix in prefixes if re.fullmatch(re.escape(prefix)+'[0-9a-f]{16}\\.private\\.json',name)]
        need(len(matches)==1,'PREPARATION_OUTPUT_SCOPE');return matches[0]
    created=getattr(error,'preparation_created_paths',[]);rows=getattr(error,'preparation_outputs',[])
    need(type(created) is list and len(created)<=3 and len(set(created))==len(created),'PREPARATION_OUTPUT_SCOPE')
    need(len({path_scope(path) for path in created})==len(created),'PREPARATION_OUTPUT_SCOPE')
    need(type(rows) is list and len(rows)<=3,'PREPARATION_OUTPUT_SCOPE');safe=[];seen=set()
    for row in rows:
        need(type(row) is dict and set(row)=={'path','sha256','bytes'},'PREPARATION_OUTPUT_SCOPE')
        prefix=path_scope(row['path']);pin=row['sha256'];size=row['bytes']
        need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and type(size) is int and 0<size<=prefixes[prefix], 'PREPARATION_OUTPUT_SCOPE')
        need(row['path']==CAND+'/'+prefix+pin[:16]+'.private.json' and row['path'] in created and row['path'] not in seen,'PREPARATION_OUTPUT_SCOPE')
        seen.add(row['path']);safe.append(dict(row))
    return {'completed_outputs':safe,'created_output_paths':list(created),'preparation_output_evidence':'RETAINED_BOUNDED_METADATA'}


def deliver_status(value):
    try:
        with budget(STATUS_SECONDS) as end:
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
            need(len(raw)<=131072,'STATUS_BOUND');offset=0
            while offset<len(raw):
                check(end);count=os.write(1,raw[offset:offset+16384]);need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=count
            check(end)
    except BaseException:raise StatusDeliveryError() from None

def input_contract():
    return {'schema':1,'state':'UNBOUND_NOT_AUTHORIZED' if not PINS_BOUND else 'BOUND_REQUIRES_SEPARATE_AUTHORIZATION',
        'preparation_root':PREP_ROOT,'successor_kit_root':COMPILER_ROOT,'original_kit_root':KIT_ROOT,
        'publication_commit':PUBLICATION_COMMIT,'archive_commit':ARCHIVE_COMMIT,
        'archive_path':ARCHIVE_PATH,'archive_sha256':ARCHIVE_SHA,'archive_bytes':ARCHIVE_SIZE,
        'kit_manifest_sha256':COMPILER_MANIFEST_SHA,'entry_sha256':COMPILER_ENTRY_SHA,
        'entry_bytes':COMPILER_ENTRY_BYTES,'source_commit':COMPILER_SOURCE,'source_tree':COMPILER_TREE,
        'preparation_sources':{name:{'sha256':pin[0],'bytes':pin[1]} for name,pin in SOURCES.items()},
        'source_files':COMPILER_CACHE_COUNT,'archive_files':COMPILER_CACHE_COUNT+1,
        'runtime_payloads':107,'business_phases':16,
        'required_prepare_argument':'--admission-expires-at-utc',
        'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}


def run(argv=None):
    global PHASE
    PHASE='INPUT_VALIDATION'
    class Parser(argparse.ArgumentParser):
        def error(self,unused):raise Hold('ARGUMENTS')
    parser=Parser(add_help=False)
    parser.add_argument('--operation',choices=('input-contract','prepare'),required=True)
    parser.add_argument('--admission-expires-at-utc')
    args=parser.parse_args(argv)
    if args.operation=='input-contract':
        need(args.admission_expires_at_utc is None,'ARGUMENTS')
        deliver_status(input_contract());return 0
    bound()
    need(type(args.admission_expires_at_utc) is str and
         re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',args.admission_expires_at_utc),'ARGUMENTS')
    need(os.geteuid()==os.getegid()==0 and socket.gethostname()==HOST,'ROOT_HOST')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED')
    staged=None;compiler_staged=None;module=None;prepared=None;labels=frozenset(CODES)
    try:
        # Complete exact-size/hash download and archive inspection precede all
        # destination creation. No partial/existing root is ever repaired.
        with budget(STAGE_SECONDS) as end:
            PHASE='DOWNLOAD_ALL'
            cache=fetch_sources(end);archive=fetch_archive(end)
            extractor,compiler_entry,compiler_files=compiler_inputs(archive)
            label_sources=dict(cache,extractor_source=safe_extractor_bytes())
            # Existing finite diagnostics use only authenticated in-memory bytes
            # at the already fixed public-source allowlist; no filesystem scan.
            label_sources.update({name:compiler_files[name] for name in PUBLIC_CODE_PATHS if name in compiler_files})
            labels=public_labels(label_sources)
            PHASE='LOAD_VERIFIED_PREPARER';module=preparer(cache);check(end)
            PHASE='STAGE_COMPILER';compiler_staged=stage_compiler(archive,extractor,compiler_entry,compiler_files,end)
            PHASE='STAGE_EXACT';staged=stage(cache,end)
        PHASE='PREPARE_PRIVATE_PLAN'
        # The original preparer's 120 seconds are separate from staging's 60.
        with module.budget(module.SECONDS):
            end=time.monotonic()+module.SECONDS
            prepared=module.prepare(args.admission_expires_at_utc,end)
            need(type(prepared) is dict and set(prepared)=={'schema','state','outputs','kit_manifest_sha256',
                 'measured_predecessor_sha256','admission_expires_at_utc','final_review','install_admission','production_resume'} and
                 type(prepared['schema']) is int and prepared['schema']==1 and
                 type(prepared['measured_predecessor_sha256']) is str and
                 re.fullmatch('[0-9a-f]{64}',prepared['measured_predecessor_sha256']) and
                 prepared.get('state')=='PREPARED_NOT_ADMITTED' and
                 prepared.get('install_admission')=='NOT_GRANTED' and
                 prepared.get('production_resume')=='NOT_EXECUTED' and
                 prepared.get('kit_manifest_sha256')==COMPILER_MANIFEST_SHA and
                 prepared.get('admission_expires_at_utc')==args.admission_expires_at_utc and
                 prepared.get('final_review')=='NEW_EXACT_APPROVAL_REQUIRED' and
                 type(prepared.get('outputs')) is list and len(prepared['outputs'])==3,'PREPARATION_RESULT_SCOPE')
            retained_outputs(types.SimpleNamespace(preparation_outputs=prepared['outputs'],preparation_created_paths=[row.get('path') for row in prepared['outputs'] if type(row) is dict]))
            PHASE='VERIFY_STAGING_AFTER_PREPARATION'
            stage(cache,end,allow_create=False);verify_compiler(compiler_entry,compiler_files,end)
        result={'schema':1,'state':'PREPARED_NOT_ADMITTED','staging':staged,
                'compiler_staging':compiler_staged,'preparation':prepared,
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    except BaseException as error:
        error.delivery_preparer=module;error.delivery_labels=labels
        if compiler_staged is not None:error.compiler_staging=compiler_staged
        if type(prepared) is dict and type(prepared.get('outputs')) is list:
            error.preparation_outputs=prepared['outputs']
            error.preparation_created_paths=[row.get('path') for row in prepared['outputs'] if type(row) is dict]
        if module is not None and isinstance(error,module.CleanupError):error.delivery_cleanup_failed=True
        if staged is not None:error.delivery_created_paths=staged['created_paths'];error.delivery_staging=staged
        raise
    PHASE='DELIVER_STATUS';deliver_status(result);return 0


def entrypoint(argv=None):
    try:return run(argv)
    except StatusDeliveryError:return 2
    except BaseException as error:
        retained={'created_paths':[],'staging':None}
        try:retained=retained_staging(error)
        except BaseException:pass
        try:
            status=failure(error,PHASE,getattr(error,'delivery_preparer',None),getattr(error,'delivery_labels',frozenset(CODES)))
        except BaseException:
            status={'schema':1,'state':'HOLD','phase':PHASE if PHASE in PHASES else 'INPUT_VALIDATION',
                'preparation_phase':'UNAVAILABLE','failure_code':'DIAGNOSTIC_PROJECTION_FAILED',
                'failure_label':None,'code_locations':[],'cleanup_unknown':True,
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        status.update(retained)
        status['compiler_staging']=None
        try:
            current=getattr(error,'compiler_staging',None)
            if type(current) is dict and current.get('state') in ('NOT_STAGED','EXTRACTION_ATTEMPTED_NOT_VERIFIED','VERIFY_EXISTING_FAILED','EXTRACTED_AND_VERIFIED','VERIFIED_EXISTING') and current==compiler_summary(current['state']):status['compiler_staging']=dict(current)
        except BaseException:status['cleanup_unknown']=True
        try:status.update(retained_outputs(error))
        except BaseException:status.update(completed_outputs=[],created_output_paths=[],preparation_output_evidence='UNKNOWN',cleanup_unknown=True)
        try:deliver_status(status)
        except StatusDeliveryError:pass
        return 2

if __name__=='__main__':sys.exit(entrypoint())
