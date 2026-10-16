#!/usr/bin/env python3
"""Observation-bound r7-fresh preparation delivery. No installation or approval operation."""
import argparse,ast,base64,zlib,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,time,types,urllib.request

PINS_BOUND=True
PUBLICATION_COMMIT='170c3fd74eb612f2529d1062e07c83e4263f78b1'
RAW_PREFIX='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/'
CAND='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
PREP_ROOT=CAND+'/epoch7-preparation-candidate-r7-resourcebind'
KIT_ROOT=CAND+'/epoch7-recovery-candidate-r7'
OBSERVATION_PATH=CAND+'/epoch7-observation-8df3b22b3762070f.private.json'
OBSERVATION_SHA256='a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68'
HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCES={'epoch7_prepare.py': ('18d3c459bc14f4a3c00317c5a407d18178059209830763564dced41d9af945fd', 55833), 'epoch7_prepare_data.py': ('71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 13888), 'epoch7_topology_projection.py': ('0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6', 36482)}

COMPILER_ROOT=CAND+'/epoch7-recovery-candidate-r7-resourcebind'
ARCHIVE_COMMIT='170c3fd74eb612f2529d1062e07c83e4263f78b1'
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz'
ARCHIVE_SHA='6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e'
ARCHIVE_SIZE=1056853
COMPILER_MANIFEST_SHA='6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
COMPILER_ENTRY_SHA='071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5'
COMPILER_SOURCE='ef21ca95331769622c294c65bb60ec7ceed0c392'
COMPILER_TREE='5a70c5627afe75fcd475c20e71ee9bfb0b6a156d'
COMPILER_CACHE_COUNT=255
EXTRACTOR_SHA='be71e68b382b5826d44c760ffc8bdb96e71f28613f7b344928c96b95adf10dd9'
EXTRACTOR_SIZE=10192
EXTRACTOR_Z='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'

STAGE_SECONDS=60
STATUS_SECONDS=5
PHASE='INPUT_VALIDATION'
CODES=frozenset(('UNBOUND','OBSERVATION_BINDING','ARGUMENTS','ROOT_HOST','ISOLATED','SOURCE_SET','SOURCE_PIN','RESPONSE','PROPOSAL_SIZE_BOUND',
 'REDIRECT','ENCODING','LENGTH','DEADLINE','EXISTING_TIMER','ANCESTRY','XATTR','PATH_RACE','PARENT_NAMES',
 'DIRECTORY','INVENTORY','PREPARATION_OUTPUT_SCOPE','PREPARATION_RESULT_SCOPE','REVIEW_INPUT','FILE_AUTHORITY','FILE_RACE','FILE_BYTES','SHORT_WRITE','COMPILER_BINDING','COMPILER_SOURCE','COMPILER_CACHE','COMPILER_STATE','COMPILER_RECHECK','EXTRACTOR_PIN','OWNED_PARENT','STATUS_BOUND','LABEL_SOURCE_BOUND'))

PHASES=frozenset(('INPUT_VALIDATION','DOWNLOAD_ALL','LOAD_VERIFIED_PREPARER','STAGE_COMPILER','STAGE_EXACT','PREPARE_PRIVATE_PLAN','VERIFY_STAGING_AFTER_PREPARATION','DELIVER_STATUS'))
ERROR_CLASSES=frozenset(('ValueError','KeyError','TypeError','OSError','FileNotFoundError','PermissionError','TimeoutError','InterruptedError','KeyboardInterrupt','SystemExit','Hold','DeadlineError','CleanupError','DiagnosticHold'))
PUBLIC_CODE_PATHS=frozenset(('epoch7_recovery_entry.py', 'helpers/epoch3_service_containment.py', 'helpers/epoch7_acceptance_rows.py', 'helpers/epoch7_additive_identity.py', 'helpers/epoch7_additive_server.py', 'helpers/epoch7_approval.py', 'helpers/epoch7_bindings.py', 'helpers/epoch7_bounded_stager.py', 'helpers/epoch7_command_runner.py', 'helpers/epoch7_complete_approval.py', 'helpers/epoch7_delta.py', 'helpers/epoch7_exact_access.py', 'helpers/epoch7_host_containment.py', 'helpers/epoch7_host_driver.py', 'helpers/epoch7_host_factory.py', 'helpers/epoch7_host_observer.py', 'helpers/epoch7_host_phases.py', 'helpers/epoch7_injected_recovery.py', 'helpers/epoch7_live_controls.py', 'helpers/epoch7_nginx_recipe.py', 'helpers/epoch7_openclaw_recipe.py', 'helpers/epoch7_owner_prerequisite.py', 'helpers/epoch7_pre_active_guards.py', 'helpers/epoch7_protected_fs.py', 'helpers/epoch7_python_identity.py', 'helpers/epoch7_quiet_startup.py', 'helpers/epoch7_recovery_sequence.py', 'helpers/epoch7_resource_observer.py', 'helpers/epoch7_resource_plan.py', 'helpers/epoch7_runtime_acceptance.py', 'helpers/epoch7_runtime_effects.py', 'helpers/epoch7_service_contract.py', 'helpers/epoch7_service_roles.py', 'helpers/epoch7_snapshot.py', 'helpers/epoch7_timer_tail.py', 'helpers/epoch7_unit_transitions.py', 'helpers/exact_access_plan.py', 'helpers/node_sqlite_probe.py', 'helpers/observe_epoch7.py', 'helpers/openclaw_metadata.py', 'helpers/probe_driver.py', 'helpers/probe_helpers.py', 'helpers/probe_metadata.py', 'helpers/protected_command_evidence.py', 'helpers/reviewed_database.py', 'helpers/reviewed_publisher.py', 'helpers/reviewed_scanner.py', 'helpers/snapshot_io.py', 'helpers/unit_metadata.py', 'xuanjun-p2-package/stage1/activation_control.py', 'xuanjun-p2-package/stage1/callback_schema_gate.py', 'xuanjun-p2-package/stage1/codex_app_server_worker.py', 'xuanjun-p2-package/stage1/codex_worker.py', 'xuanjun-p2-package/stage1/dependency_evidence_view.py', 'xuanjun-p2-package/stage1/development_loop.py', 'xuanjun-p2-package/stage1/development_pipeline.py', 'xuanjun-p2-package/stage1/development_service.py', 'xuanjun-p2-package/stage1/execution_ledger.py', 'xuanjun-p2-package/stage1/execution_supervision.py', 'xuanjun-p2-package/stage1/github_issue_consumer.py', 'xuanjun-p2-package/stage1/ledger_backup.py', 'xuanjun-p2-package/stage1/ledger_cutover_transaction.py', 'xuanjun-p2-package/stage1/ledger_install_stage.py', 'xuanjun-p2-package/stage1/ledger_read_client.py', 'xuanjun-p2-package/stage1/ledger_read_projection.py', 'xuanjun-p2-package/stage1/ledger_read_transport.py', 'xuanjun-p2-package/stage1/ledger_server_identity.py', 'xuanjun-p2-package/stage1/ledger_service.py', 'xuanjun-p2-package/stage1/legacy_host_adapter.py', 'xuanjun-p2-package/stage1/legacy_quiescence.py', 'xuanjun-p2-package/stage1/mechanical_wake.py', 'xuanjun-p2-package/stage1/mechanical_wake_service.py', 'xuanjun-p2-package/stage1/native_child_adapter.py', 'xuanjun-p2-package/stage1/native_gateway_controller.py', 'xuanjun-p2-package/stage1/native_github_notifier.py', 'xuanjun-p2-package/stage1/native_ledger_bridge.py', 'xuanjun-p2-package/stage1/native_ledger_operations.py', 'xuanjun-p2-package/stage1/native_peer_identity.py', 'xuanjun-p2-package/stage1/native_pipeline_runtime.py', 'xuanjun-p2-package/stage1/native_snapshot_access.py', 'xuanjun-p2-package/stage1/owner_approval_dispatch.py', 'xuanjun-p2-package/stage1/owner_callback_server.py', 'xuanjun-p2-package/stage1/owner_dashboard.py', 'xuanjun-p2-package/stage1/owner_feishu_bridge_cycle.py', 'xuanjun-p2-package/stage1/owner_feishu_claim_guard.py', 'xuanjun-p2-package/stage1/owner_feishu_history.py', 'xuanjun-p2-package/stage1/owner_feishu_https.py', 'xuanjun-p2-package/stage1/owner_feishu_ledger_endpoint.py', 'xuanjun-p2-package/stage1/owner_feishu_transport.py', 'xuanjun-p2-package/stage1/owner_notification_outbox.py', 'xuanjun-p2-package/stage1/owner_process_identity.py', 'xuanjun-p2-package/stage1/owner_update_router.py', 'xuanjun-p2-package/stage1/p2_auxiliary_isolation.py', 'xuanjun-p2-package/stage1/p2_bootstrap_files.py', 'xuanjun-p2-package/stage1/p2_fixed_host_runtime.py', 'xuanjun-p2-package/stage1/p2_gateway_relay.py', 'xuanjun-p2-package/stage1/p2_install_entrypoint.py', 'xuanjun-p2-package/stage1/p2_legacy_adoption.py', 'xuanjun-p2-package/stage1/p2_prerequisites.py', 'xuanjun-p2-package/stage1/p2_publisher_bootstrap.py', 'xuanjun-p2-package/stage1/p2_rpm_prerequisites.py', 'xuanjun-p2-package/stage1/p2_sandbox_profile.py', 'xuanjun-p2-package/stage1/p2_service_context_preflight.py', 'xuanjun-p2-package/stage1/p2_tls_lifecycle.py', 'xuanjun-p2-package/stage1/root_broker.py', 'xuanjun-p2-package/stage1/run_usage_projection.py', 'xuanjun-p2-package/stage1/task_cost_projection.py', 'xuanjun-p2-package/stage1/task_supervisor_inventory_adapter.py', 'xuanjun-p2-package/stage1/telegram_owner_transport.py', 'xuanjun-p2-package/stage1/uk_owner_callback_core.py', 'xuanjun-p2-package/stage1/uk_owner_notify_worker.py'))

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
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds,.1)
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
    need(PINS_BOUND is True and all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (PUBLICATION_COMMIT,ARCHIVE_COMMIT)),'UNBOUND')

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
    need(extractor.ROOT_NAME=='epoch7-recovery-candidate-r7-resourcebind','COMPILER_BINDING')
    files,dirs=extractor.inspect_archive(raw,ARCHIVE_SHA,COMPILER_ENTRY_SHA,COMPILER_MANIFEST_SHA)
    need(len(files)==COMPILER_CACHE_COUNT+1,'COMPILER_CACHE')
    entry=types.ModuleType('verified_compiler_entry');entry.__file__=COMPILER_ROOT+'/epoch7_recovery_entry.py'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec'),entry.__dict__)
    manifest=entry.decode(files['recovery-kit-manifest.json']);entry.validate_manifest(manifest)
    need(manifest['kit_source_commit']==COMPILER_SOURCE and manifest['kit_source_tree']==COMPILER_TREE and len(manifest['files'])==COMPILER_CACHE_COUNT,'COMPILER_SOURCE')
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
            try:os.stat('epoch7-recovery-candidate-r7-resourcebind',dir_fd=tree.fd,follow_symlinks=False)
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
        need(authority(parent)==parent_before,'PATH_RACE');leaf='epoch7-preparation-candidate-r7-resourcebind'
        try:before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:
            need(allow_create is True,'DIRECTORY')
            check(end);os.mkdir(leaf,0o700,dir_fd=parent);created.append(PREP_ROOT);before=os.stat(leaf,dir_fd=parent,follow_symlinks=False);new=True
        else:new=False
        need(stat.S_ISDIR(before.st_mode),'DIRECTORY')
        directory=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(directory)
        start=authority(directory,0o700);need(stamp(before)==start,'PATH_RACE')
        need(names(directory,3)==(() if new else tuple(sorted(SOURCES))),'INVENTORY')
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
        expected_names=tuple(sorted(SOURCES));need(names(directory,3)==expected_names,'INVENTORY')
        observed={name:read_file(directory,name,cache[name],end) for name in sorted(SOURCES)}
        for name in sorted(SOURCES):need(stamp(os.stat(name,dir_fd=directory,follow_symlinks=False))==observed[name],'FILE_RACE')
        need(authority(directory,0o700)==current and names(directory,3)==expected_names and
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
    validate_sources(cache);module=types.ModuleType('verified_epoch7_preparer');module.__file__=PREP_ROOT+'/epoch7_prepare.py'
    exec(compile(cache['epoch7_prepare.py'],module.__file__,'exec'),module.__dict__);return module

def public_labels(cache):
    labels=set(CODES)
    for raw in cache.values():
        need(type(raw) is bytes and len(raw)<=1048576,'LABEL_SOURCE_BOUND')
        for node in ast.walk(ast.parse(raw.decode('utf-8'))):
            value=node.s if isinstance(node,ast.Str) else None
            if type(value) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,119}',value):
                labels.add(value)
                for prefix in ('EPOCH7_PREP_','TOPOLOGY_','EPOCH7_EXTRACT_','EPOCH7_HOST_'):labels.add(prefix+value)
    return frozenset(labels)

def code_locations(error):
    rows=[];tb=error.__traceback__;count=0
    while tb is not None and count<64:
        count+=1;frame=tb.tb_frame;name=frame.f_code.co_filename;label=None
        if frame.f_globals is globals():label='delivery/epoch7_prepare_delivery.py'
        elif name=='<verified-compiler-extractor>':label='delivery/extract_epoch7_compiler_kit.py'
        elif name=='<verified-preparation-delivery>':label='delivery/epoch7_prepare_delivery.py'
        elif name in tuple(PREP_ROOT+'/'+item for item in ('epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py')):
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
    inner=getattr(preparer,'CURRENT_PHASE',None)
    if preparer is None or type(inner) is not str or inner not in preparer.PHASES:inner='UNAVAILABLE'
    allowed=set(labels)|set(CODES)
    args=error.args if type(error.args) is tuple else ()
    label=args[0] if len(args)==1 and type(error) in (ValueError,Hold) else None
    if type(label) is not str or label not in allowed:label=None
    kind=type(error).__name__;kind=kind if kind in ERROR_CLASSES else 'DEPENDENCY_ERROR'
    cleanup=isinstance(error,CleanupError) or bool(getattr(error,'delivery_cleanup_failed',False)) or bool(getattr(error,'preparation_cleanup_failed',False))
    if preparer is not None:cleanup=cleanup or isinstance(error,preparer.CleanupError)
    return {'schema':1,'state':'HOLD','phase':outer if outer in PHASES else 'INPUT_VALIDATION',
        'preparation_phase':inner,'failure_code':kind,'failure_label':label,
        'code_locations':code_locations(error),'cleanup_unknown':cleanup,
        'observation_sha256':OBSERVATION_SHA256,'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}

def retained_staging(error):
    """Only the fixed public staging inventory may survive a failed projection."""
    allowed=set((PREP_ROOT,))|set(PREP_ROOT+'/'+name for name in SOURCES)
    value=getattr(error,'delivery_created_paths',[])
    paths=[item for item in value if type(item) is str and item in allowed] if type(value) is list and len(value)<=4 else []
    result={'created_paths':paths,'staging':None}
    value=getattr(error,'delivery_staging',None)
    if type(value) is dict and value.get('state') in ('STAGED_EXACT','REUSED_EXACT') and value.get('path')==PREP_ROOT:
        files={name:{'sha256':SOURCES[name][0],'bytes':SOURCES[name][1]} for name in sorted(SOURCES)}
        if value.get('files')==files and value.get('created_paths')==paths:
            result['staging']={'state':value['state'],'path':PREP_ROOT,'files':files,'created_paths':list(paths)}
    return result

def retained_outputs(error):
    """Keep only bounded fixed private-output path/hash/length metadata."""
    prefixes={'epoch7-approved-plan-':2*1024*1024,'epoch7-resume-inputs-':64*1024*1024,'epoch7-review-packet-':2*1024*1024}
    def path_scope(path):
        need(type(path) is str and os.path.dirname(path)==CAND,'PREPARATION_OUTPUT_SCOPE')
        name=os.path.basename(path)
        matches=[prefix for prefix in prefixes if re.fullmatch(re.escape(prefix)+'[0-9a-f]{16}\\.private\\.json',name)]
        need(len(matches)==1,'PREPARATION_OUTPUT_SCOPE');return matches[0]
    created=getattr(error,'preparation_created_paths',[]);rows=getattr(error,'preparation_outputs',[])
    need(type(created) is list and len(created)<=3 and len(set(created))==len(created),'PREPARATION_OUTPUT_SCOPE')
    for path in created:path_scope(path)
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

def run(argv=None):
    global PHASE
    PHASE='INPUT_VALIDATION'
    class Parser(argparse.ArgumentParser):
        def error(self,unused):raise Hold('ARGUMENTS')
    parser=Parser(add_help=False);parser.add_argument('--observation',required=True);parser.add_argument('--observation-sha256',required=True);parser.add_argument('--topology-review-id',type=int,required=True);parser.add_argument('--retained-renewal-timer',choices=('enable-after-reviewed-checks',),required=True);args=parser.parse_args(argv)
    bound()
    need(type(args.topology_review_id) is int and 0<args.topology_review_id<10**20 and args.retained_renewal_timer=='enable-after-reviewed-checks','REVIEW_INPUT')
    need(type(args.observation) is str and os.path.dirname(args.observation)==CAND and re.fullmatch('epoch7-observation-[0-9a-f]{16}\\.private\\.json',os.path.basename(args.observation)) and re.fullmatch('[0-9a-f]{64}',args.observation_sha256),'ARGUMENTS')
    need(args.observation==OBSERVATION_PATH and args.observation_sha256==OBSERVATION_SHA256,'OBSERVATION_BINDING')
    need(os.geteuid()==os.getegid()==0 and socket.gethostname()==HOST,'ROOT_HOST')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED')
    staged=None;compiler_staged=None;module=None;prepared=None;labels=frozenset(CODES)
    try:
        with budget(STAGE_SECONDS) as end:
            PHASE='DOWNLOAD_ALL';cache=fetch_sources(end);archive=fetch_archive(end);extractor,compiler_entry,compiler_files=compiler_inputs(archive);labels=public_labels(dict(cache,extractor_source=safe_extractor_bytes(),compiler_delta=compiler_files['helpers/epoch7_delta.py'],compiler_resources=compiler_files['helpers/epoch7_resource_observer.py'],compiler_factory=compiler_files['helpers/epoch7_host_factory.py']))
            PHASE='LOAD_VERIFIED_PREPARER';module=preparer(cache);check(end)
            PHASE='STAGE_COMPILER';compiler_staged=stage_compiler(archive,extractor,compiler_entry,compiler_files,end)
            PHASE='STAGE_EXACT';staged=stage(cache,end)
        PHASE='PREPARE_PRIVATE_PLAN'
        prepare_args=types.SimpleNamespace(operation='prepare',observation=args.observation,
            observation_sha256=args.observation_sha256,topology_review_id=args.topology_review_id,retained_renewal_timer=args.retained_renewal_timer)
        with module.budget() as end:
            prepared=module.run_preparation(prepare_args,end)
            need(type(prepared) is dict and prepared.get('state')=='PREPARED_NOT_ADMITTED' and prepared.get('install_admission')=='NOT_GRANTED' and prepared.get('production_resume')=='NOT_EXECUTED' and type(prepared.get('outputs')) is list and len(prepared['outputs'])==3,'PREPARATION_RESULT_SCOPE')
            retained_outputs(types.SimpleNamespace(preparation_outputs=prepared['outputs'],preparation_created_paths=[row.get('path') for row in prepared['outputs'] if type(row) is dict]))
            # The preparation summary is returned only while the fixed staging
            # inventory still equals the originally downloaded source bytes.
            PHASE='VERIFY_STAGING_AFTER_PREPARATION';stage(cache,end,allow_create=False);verify_compiler(compiler_entry,compiler_files,end)
        result={'schema':1,'state':'PREPARED_NOT_ADMITTED','staging':staged,'compiler_staging':compiler_staged,'preparation':prepared,
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
