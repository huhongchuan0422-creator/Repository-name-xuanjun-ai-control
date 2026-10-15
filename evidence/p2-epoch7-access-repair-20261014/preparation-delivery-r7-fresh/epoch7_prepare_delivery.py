#!/usr/bin/env python3
"""Observation-bound r7-fresh preparation delivery. No installation or approval operation."""
import argparse,ast,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,time,types,urllib.request

PINS_BOUND=False
PUBLICATION_COMMIT=None
RAW_PREFIX='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-source-r7-fresh/'
CAND='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
PREP_ROOT=CAND+'/epoch7-preparation-candidate-r7-fresh'
KIT_ROOT=CAND+'/epoch7-recovery-candidate-r7'
OBSERVATION_PATH=CAND+'/epoch7-observation-8df3b22b3762070f.private.json'
OBSERVATION_SHA256='a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68'
HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCES={'epoch7_prepare.py': ('b95c5bb675219b831f4d715ba5a5702537f4e36841316237d05f5a92a6c95a6e', 48550), 'epoch7_prepare_data.py': ('71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 13888), 'epoch7_topology_projection.py': ('0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6', 36482)}
STAGE_SECONDS=60
STATUS_SECONDS=5
PHASE='INPUT_VALIDATION'
CODES=frozenset(('UNBOUND','OBSERVATION_BINDING','ARGUMENTS','ROOT_HOST','ISOLATED','SOURCE_SET','SOURCE_PIN','RESPONSE',
 'REDIRECT','ENCODING','LENGTH','DEADLINE','EXISTING_TIMER','ANCESTRY','XATTR','PATH_RACE','PARENT_NAMES',
 'DIRECTORY','INVENTORY','PREPARATION_OUTPUT_SCOPE','PREPARATION_RESULT_SCOPE','REVIEW_INPUT','FILE_AUTHORITY','FILE_RACE','FILE_BYTES','SHORT_WRITE','OWNED_PARENT','STATUS_BOUND','LABEL_SOURCE_BOUND'))

PHASES=frozenset(('INPUT_VALIDATION','DOWNLOAD_ALL','LOAD_VERIFIED_PREPARER','STAGE_EXACT','PREPARE_PRIVATE_PLAN','VERIFY_STAGING_AFTER_PREPARATION','DELIVER_STATUS'))
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
    need(PINS_BOUND is True and type(PUBLICATION_COMMIT) is str and re.fullmatch('[0-9a-f]{40}',PUBLICATION_COMMIT),'UNBOUND')

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
        need(authority(parent)==parent_before,'PATH_RACE');leaf='epoch7-preparation-candidate-r7-fresh'
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
                for prefix in ('EPOCH7_PREP_','TOPOLOGY_'):labels.add(prefix+value)
    return frozenset(labels)

def code_locations(error):
    rows=[];tb=error.__traceback__;count=0
    while tb is not None and count<64:
        count+=1;frame=tb.tb_frame;name=frame.f_code.co_filename;label=None
        if frame.f_globals is globals():label='delivery/epoch7_prepare_delivery.py'
        elif name=='<verified-preparation-delivery>':label='delivery/epoch7_prepare_delivery.py'
        elif name in tuple(PREP_ROOT+'/'+item for item in ('epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py')):
            label='preparation/'+name.rsplit('/',1)[1]
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
    staged=None;module=None;prepared=None;labels=frozenset(CODES)
    try:
        with budget(STAGE_SECONDS) as end:
            PHASE='DOWNLOAD_ALL';cache=fetch_sources(end);labels=public_labels(cache)
            PHASE='LOAD_VERIFIED_PREPARER';module=preparer(cache);check(end)
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
            PHASE='VERIFY_STAGING_AFTER_PREPARATION';stage(cache,end,allow_create=False)
        result={'schema':1,'state':'PREPARED_NOT_ADMITTED','staging':staged,'preparation':prepared,
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    except BaseException as error:
        error.delivery_preparer=module;error.delivery_labels=labels
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
        try:status.update(retained_outputs(error))
        except BaseException:status.update(completed_outputs=[],created_output_paths=[],preparation_output_evidence='UNKNOWN',cleanup_unknown=True)
        try:deliver_status(status)
        except StatusDeliveryError:pass
        return 2

if __name__=='__main__':sys.exit(entrypoint())
