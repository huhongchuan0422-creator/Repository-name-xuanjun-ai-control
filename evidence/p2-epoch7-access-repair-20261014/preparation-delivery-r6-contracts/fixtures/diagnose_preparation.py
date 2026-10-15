#!/usr/bin/env python3
"""Bounded read-only diagnosis of the frozen r6 preparation proposal path."""
import ast,contextlib,hashlib,json,os,re,signal,socket,sys,time,types,urllib.request
DELIVERY_COMMIT='f21fc4f4efe1a2793740ebe45aa1e9f2ad88ba61'
DELIVERY_SHA256='9a87f740ee8d81fb95fe41e1644584c85b723fe5823f309ea0bf07796140cf9f'
DELIVERY_BYTES=14950
DELIVERY_URL='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'+DELIVERY_COMMIT+'/evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r6/epoch7_prepare_delivery.py'
PREPARATION_COMMIT='e8b9ebb3fb215fa5b1ef0a8dc0b31a77efd0ab67'
CAND='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
PREP_ROOT=CAND+'/epoch7-preparation-candidate-r6'
KIT_ROOT=CAND+'/epoch7-recovery-candidate-r6'
OBSERVATION_PATH=CAND+'/epoch7-observation-1311b9e9fa97cfd4.private.json'
OBSERVATION_SHA256='b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246'
HOST='iZd7oeikknn1z21sq6ji6zZ'
PHASES=frozenset(('INPUT_VALIDATION','AUTHENTICATE_DELIVERY','AUTHENTICATE_PREPARATION_SOURCES','VERIFY_EXISTING_STAGING','LOAD_FROZEN_PREPARER','PROPOSE_TOPOLOGY','VERIFY_EXISTING_STAGING_AFTER_PROPOSAL'))
CODES=frozenset(('ARGUMENTS','ROOT_HOST','ISOLATED','EXISTING_TIMER','DEADLINE','DELIVERY_RESPONSE','DELIVERY_ENCODING','DELIVERY_LENGTH','DELIVERY_PIN','REDIRECT','FROZEN_BINDING','LABEL_SOURCE_BOUND','STATUS_BOUND','SHORT_WRITE'))
ERROR_CLASSES=frozenset(('ValueError','KeyError','TypeError','OSError','FileNotFoundError','PermissionError','TimeoutError','InterruptedError','KeyboardInterrupt','SystemExit','Hold','DeadlineError','CleanupError','DiagnosticHold'))
PUBLIC_CODE_PATHS=frozenset(('epoch7_recovery_entry.py', 'helpers/epoch3_service_containment.py', 'helpers/epoch7_acceptance_rows.py', 'helpers/epoch7_additive_identity.py', 'helpers/epoch7_additive_server.py', 'helpers/epoch7_approval.py', 'helpers/epoch7_bindings.py', 'helpers/epoch7_bounded_stager.py', 'helpers/epoch7_command_runner.py', 'helpers/epoch7_complete_approval.py', 'helpers/epoch7_delta.py', 'helpers/epoch7_exact_access.py', 'helpers/epoch7_host_containment.py', 'helpers/epoch7_host_driver.py', 'helpers/epoch7_host_factory.py', 'helpers/epoch7_host_observer.py', 'helpers/epoch7_host_phases.py', 'helpers/epoch7_injected_recovery.py', 'helpers/epoch7_live_controls.py', 'helpers/epoch7_nginx_recipe.py', 'helpers/epoch7_openclaw_recipe.py', 'helpers/epoch7_owner_prerequisite.py', 'helpers/epoch7_pre_active_guards.py', 'helpers/epoch7_protected_fs.py', 'helpers/epoch7_python_identity.py', 'helpers/epoch7_quiet_startup.py', 'helpers/epoch7_recovery_sequence.py', 'helpers/epoch7_resource_observer.py', 'helpers/epoch7_resource_plan.py', 'helpers/epoch7_runtime_acceptance.py', 'helpers/epoch7_runtime_effects.py', 'helpers/epoch7_service_contract.py', 'helpers/epoch7_service_roles.py', 'helpers/epoch7_snapshot.py', 'helpers/epoch7_timer_tail.py', 'helpers/epoch7_unit_transitions.py', 'helpers/exact_access_plan.py', 'helpers/node_sqlite_probe.py', 'helpers/observe_epoch7.py', 'helpers/openclaw_metadata.py', 'helpers/probe_driver.py', 'helpers/probe_helpers.py', 'helpers/probe_metadata.py', 'helpers/protected_command_evidence.py', 'helpers/reviewed_database.py', 'helpers/reviewed_publisher.py', 'helpers/reviewed_scanner.py', 'helpers/snapshot_io.py', 'helpers/unit_metadata.py', 'xuanjun-p2-package/stage1/activation_control.py', 'xuanjun-p2-package/stage1/callback_schema_gate.py', 'xuanjun-p2-package/stage1/codex_app_server_worker.py', 'xuanjun-p2-package/stage1/codex_worker.py', 'xuanjun-p2-package/stage1/dependency_evidence_view.py', 'xuanjun-p2-package/stage1/development_loop.py', 'xuanjun-p2-package/stage1/development_pipeline.py', 'xuanjun-p2-package/stage1/development_service.py', 'xuanjun-p2-package/stage1/execution_ledger.py', 'xuanjun-p2-package/stage1/execution_supervision.py', 'xuanjun-p2-package/stage1/github_issue_consumer.py', 'xuanjun-p2-package/stage1/ledger_backup.py', 'xuanjun-p2-package/stage1/ledger_cutover_transaction.py', 'xuanjun-p2-package/stage1/ledger_install_stage.py', 'xuanjun-p2-package/stage1/ledger_read_client.py', 'xuanjun-p2-package/stage1/ledger_read_projection.py', 'xuanjun-p2-package/stage1/ledger_read_transport.py', 'xuanjun-p2-package/stage1/ledger_server_identity.py', 'xuanjun-p2-package/stage1/ledger_service.py', 'xuanjun-p2-package/stage1/legacy_host_adapter.py', 'xuanjun-p2-package/stage1/legacy_quiescence.py', 'xuanjun-p2-package/stage1/mechanical_wake.py', 'xuanjun-p2-package/stage1/mechanical_wake_service.py', 'xuanjun-p2-package/stage1/native_child_adapter.py', 'xuanjun-p2-package/stage1/native_gateway_controller.py', 'xuanjun-p2-package/stage1/native_github_notifier.py', 'xuanjun-p2-package/stage1/native_ledger_bridge.py', 'xuanjun-p2-package/stage1/native_ledger_operations.py', 'xuanjun-p2-package/stage1/native_peer_identity.py', 'xuanjun-p2-package/stage1/native_pipeline_runtime.py', 'xuanjun-p2-package/stage1/native_snapshot_access.py', 'xuanjun-p2-package/stage1/owner_approval_dispatch.py', 'xuanjun-p2-package/stage1/owner_callback_server.py', 'xuanjun-p2-package/stage1/owner_dashboard.py', 'xuanjun-p2-package/stage1/owner_feishu_bridge_cycle.py', 'xuanjun-p2-package/stage1/owner_feishu_claim_guard.py', 'xuanjun-p2-package/stage1/owner_feishu_history.py', 'xuanjun-p2-package/stage1/owner_feishu_https.py', 'xuanjun-p2-package/stage1/owner_feishu_ledger_endpoint.py', 'xuanjun-p2-package/stage1/owner_feishu_transport.py', 'xuanjun-p2-package/stage1/owner_notification_outbox.py', 'xuanjun-p2-package/stage1/owner_process_identity.py', 'xuanjun-p2-package/stage1/owner_update_router.py', 'xuanjun-p2-package/stage1/p2_auxiliary_isolation.py', 'xuanjun-p2-package/stage1/p2_bootstrap_files.py', 'xuanjun-p2-package/stage1/p2_fixed_host_runtime.py', 'xuanjun-p2-package/stage1/p2_gateway_relay.py', 'xuanjun-p2-package/stage1/p2_install_entrypoint.py', 'xuanjun-p2-package/stage1/p2_legacy_adoption.py', 'xuanjun-p2-package/stage1/p2_prerequisites.py', 'xuanjun-p2-package/stage1/p2_publisher_bootstrap.py', 'xuanjun-p2-package/stage1/p2_rpm_prerequisites.py', 'xuanjun-p2-package/stage1/p2_sandbox_profile.py', 'xuanjun-p2-package/stage1/p2_service_context_preflight.py', 'xuanjun-p2-package/stage1/p2_tls_lifecycle.py', 'xuanjun-p2-package/stage1/root_broker.py', 'xuanjun-p2-package/stage1/run_usage_projection.py', 'xuanjun-p2-package/stage1/task_cost_projection.py', 'xuanjun-p2-package/stage1/task_supervisor_inventory_adapter.py', 'xuanjun-p2-package/stage1/telegram_owner_transport.py', 'xuanjun-p2-package/stage1/uk_owner_callback_core.py', 'xuanjun-p2-package/stage1/uk_owner_notify_worker.py'))

class DiagnosticHold(ValueError):pass
class CleanupError(Exception):pass
class StatusDeliveryError(Exception):pass

def need(ok,label):
    if not ok:raise DiagnosticHold(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()

@contextlib.contextmanager
def budget(seconds):
    need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'EXISTING_TIMER')
    old=signal.getsignal(signal.SIGALRM);primary=None;end=time.monotonic()+seconds
    def expired(a,b):raise DiagnosticHold('DEADLINE')
    try:
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds,.1)
        yield end;need(time.monotonic()<end,'DEADLINE')
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,old)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.diagnostic_cleanup_failed=True

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise DiagnosticHold('REDIRECT')

def download_delivery(end):
    response=None;primary=None
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        response=opener.open(urllib.request.Request(DELIVERY_URL,headers={'Accept-Encoding':'identity'}),timeout=10)
        need(response.status==200 and response.geturl()==DELIVERY_URL,'DELIVERY_RESPONSE')
        need(response.headers.get('Content-Encoding','identity')=='identity','DELIVERY_ENCODING')
        need(response.headers.get('Content-Length') in (None,str(DELIVERY_BYTES)),'DELIVERY_LENGTH')
        raw=response.read(DELIVERY_BYTES+1);need(time.monotonic()<end,'DEADLINE')
        need(type(raw) is bytes and len(raw)==DELIVERY_BYTES and sha(raw)==DELIVERY_SHA256,'DELIVERY_PIN')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        if response is not None:
            try:response.close()
            except BaseException:
                if primary is None:raise CleanupError()
                primary.diagnostic_cleanup_failed=True

def delivery_module(raw):
    need(type(raw) is bytes and len(raw)==DELIVERY_BYTES and sha(raw)==DELIVERY_SHA256,'DELIVERY_PIN')
    module=types.ModuleType('verified_readonly_preparation_delivery');module.__file__='<verified-preparation-delivery>'
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    need(module.PINS_BOUND is True and module.PUBLICATION_COMMIT==PREPARATION_COMMIT and
         module.PREP_ROOT==PREP_ROOT and module.CAND==CAND and
         module.OBSERVATION_PATH==OBSERVATION_PATH and module.OBSERVATION_SHA256==OBSERVATION_SHA256,'FROZEN_BINDING')
    return module

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
        if frame.f_globals is globals():label='diagnostic'
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

def failure(error,outer,preparer,delivery,labels):
    inner=getattr(preparer,'CURRENT_PHASE',None)
    if preparer is None or type(inner) is not str or inner not in preparer.PHASES:inner='UNAVAILABLE'
    allowed=set(labels)|set(CODES)
    if delivery is not None:allowed.update(delivery.CODES)
    args=error.args if type(error.args) is tuple else ()
    label=args[0] if len(args)==1 and (type(error) in (ValueError,DiagnosticHold) or (delivery is not None and type(error) is delivery.Hold)) else None
    if type(label) is not str or label not in allowed:label=None
    kind=type(error).__name__;kind=kind if kind in ERROR_CLASSES else 'DEPENDENCY_ERROR'
    cleanup=isinstance(error,CleanupError) or bool(getattr(error,'diagnostic_cleanup_failed',False)) or bool(getattr(error,'delivery_cleanup_failed',False)) or bool(getattr(error,'preparation_cleanup_failed',False))
    if preparer is not None:cleanup=cleanup or isinstance(error,preparer.CleanupError)
    if delivery is not None:cleanup=cleanup or isinstance(error,delivery.CleanupError)
    return {'schema':1,'state':'HOLD','outer_phase':outer if outer in PHASES else 'INPUT_VALIDATION',
        'preparation_phase':inner,'failure_code':kind,'failure_label':label,
        'code_locations':code_locations(error),'cleanup_unknown':cleanup,
        'staging_mode':'VERIFY_EXISTING_ONLY','created_paths':[],
        'observation_sha256':OBSERVATION_SHA256,'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}

def output(value):
    try:
        with budget(5) as end:
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
            need(len(raw)<=131072,'STATUS_BOUND');offset=0
            while offset<len(raw):
                need(time.monotonic()<end,'DEADLINE');n=os.write(1,raw[offset:offset+16384])
                need(type(n) is int and 0<n<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=n
            need(time.monotonic()<end,'DEADLINE')
    except BaseException:raise StatusDeliveryError() from None

def main(argv=None):
    outer='INPUT_VALIDATION';delivery=None;preparer=None;labels=frozenset(CODES)
    try:
        need((sys.argv[1:] if argv is None else argv)==[],'ARGUMENTS')
        need(os.geteuid()==os.getegid()==0 and socket.gethostname()==HOST,'ROOT_HOST')
        need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED')
        outer='AUTHENTICATE_DELIVERY'
        with budget(30) as end:delivery=delivery_module(download_delivery(end))
        with delivery.budget(60) as end:
            outer='AUTHENTICATE_PREPARATION_SOURCES';cache=delivery.fetch_sources(end);labels=public_labels(cache)
            outer='VERIFY_EXISTING_STAGING';delivery.stage(cache,end,allow_create=False)
            outer='LOAD_FROZEN_PREPARER';preparer=delivery.preparer(cache)
            need(preparer.PREP_ROOT==PREP_ROOT and preparer.KIT_ROOT==KIT_ROOT,'FROZEN_BINDING')
        outer='PROPOSE_TOPOLOGY'
        args=types.SimpleNamespace(operation='propose-topology',observation=OBSERVATION_PATH,
            observation_sha256=OBSERVATION_SHA256,topology_review_id=None,retained_renewal_timer=None)
        with preparer.budget() as end:
            proposal=preparer.run_preparation(args,end)
            outer='VERIFY_EXISTING_STAGING_AFTER_PROPOSAL';delivery.stage(cache,end,allow_create=False)
        value={'schema':1,'state':'TOPOLOGY_REVIEW_REQUIRED','output_scope':'UNSIGNED_PROPOSAL_AND_HOST_VALIDATED_EVIDENCE_BINDINGS',
            'proposal':proposal,'staging_mode':'VERIFY_EXISTING_ONLY','created_paths':[],
            'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'};code=0
    except BaseException as error:
        code=2
        try:value=failure(error,outer,preparer,delivery,labels)
        except BaseException:
            value={'schema':1,'state':'HOLD','outer_phase':outer if outer in PHASES else 'INPUT_VALIDATION',
                'preparation_phase':'UNAVAILABLE','failure_code':'DIAGNOSTIC_PROJECTION_FAILED',
                'failure_label':None,'code_locations':[],'cleanup_unknown':True,
                'staging_mode':'VERIFY_EXISTING_ONLY','created_paths':[],
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    try:output(value)
    except StatusDeliveryError:return 2
    return code

if __name__=='__main__':sys.exit(main())
