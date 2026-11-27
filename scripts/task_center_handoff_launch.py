"""Original app launcher with protected selectors and in-process authority.

No provider plugin loader or auth replacement. Disabled configuration delegates
unchanged to app.main; enabled configuration requires the custodied backend.
"""
import argparse
import json
import os
import sqlite3
import sys
from urllib.parse import quote
from secure_file_input import read_owned_secret_file
import task_center_handoff_runtime as runtime
from task_center_role_contract import RoleContractResolver
from task_center_session_auth import SessionStore


def load_config(path):
    def unique(pairs):
        value={}
        for k,v in pairs:
            if k in value:raise ValueError('HANDOFF_RUNTIME_DUPLICATE_CONFIG_KEY')
            value[k]=v
        return value
    try:config=json.loads(read_owned_secret_file(path,'HANDOFF_RUNTIME_CONFIG'),object_pairs_hook=unique)
    except (OSError,ValueError,TypeError):
        raise ValueError('HANDOFF_RUNTIME_CONFIG_UNAVAILABLE_OR_INVALID') from None
    base={'schema_version','enabled'}
    if (not isinstance(config,dict) or type(config.get('schema_version')) is not int
            or config['schema_version']!=1 or type(config.get('enabled')) is not bool):
        raise ValueError('HANDOFF_RUNTIME_CONFIG_INVALID')
    if not config['enabled']:
        if set(config)!=base:raise ValueError('DISABLED_HANDOFF_CONFIG_MUST_BE_EMPTY')
        return config
    fields={'tenant_id','issuer','lifecycle_root','ledger_root','namespace','writer','contracts','intake_plans'}
    required=base|fields
    optional={'handoff_binding_projection_enabled'}
    if not (required <= set(config) <= (required|optional)):
        raise ValueError('HANDOFF_RUNTIME_CONFIG_INVALID')
    if type(config.get('handoff_binding_projection_enabled',False)) is not bool:
        raise ValueError('HANDOFF_BINDING_PROJECTION_BOOLEAN_REQUIRED')
    for key in ('tenant_id','issuer','namespace','writer'):
        if not isinstance(config[key],str) or not config[key]:raise ValueError('HANDOFF_RUNTIME_CONFIG_INVALID')
    for key in ('lifecycle_root','ledger_root'):
        if not isinstance(config[key],str) or not os.path.isabs(config[key]):raise ValueError('HANDOFF_RUNTIME_ROOT_REQUIRED')
    if not isinstance(config['contracts'],list) or not isinstance(config['intake_plans'],list):
        raise ValueError('HANDOFF_RUNTIME_CONTRACTS_REQUIRED')
    return config


def main(argv=None, *, identity_backend=None,evidence=None,gateway_runtime=None,
         mcp_claim_host=None,mcp_development_host=None,execution_provider=None,
         provenance_source=None,principal_mapper=None,native_runner=None,native_runner_factory=None,
         native_test_plan_sha256=None):
    """Trusted host imports main with existing authority/evidence objects.

    CLI only supplies protected selectors. It cannot create/import an identity
    backend. Missing authority is checked before DB open or SessionStore init.
    """
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--handoff-runtime-config-file',required=True)
    launch,app_argv=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    config=load_config(launch.handoff_runtime_config_file)
    guarded=provenance_source is not None or principal_mapper is not None
    native=any(value is not None for value in (native_runner,native_runner_factory,native_test_plan_sha256))
    if not config['enabled'] and (guarded or native):
        raise ValueError('TRUSTED_FORMAL_ADAPTERS_REQUIRE_ENABLED_RUNTIME')
    if guarded:
        if identity_backend is not None:
            raise ValueError('SINGLE_IDENTITY_SOURCE_REQUIRED')
        from task_center_provenance_consumer import GuardedProvenanceConsumer
        GuardedProvenanceConsumer.validate_source(provenance_source,principal_mapper)
    elif config['enabled']:
        runtime.HostIdentityProvider.validate_backend(config['tenant_id'],identity_backend)
    passthrough=dict(mcp_claim_host=mcp_claim_host,mcp_development_host=mcp_development_host,execution_provider=execution_provider)
    if not config['enabled']:
        from task_center_app import main as app_main
        return app_main(app_argv,gateway_runtime,**passthrough)
    selectors=argparse.ArgumentParser(add_help=False)
    selectors.add_argument('--db',required=True);selectors.add_argument('--tenant',required=True)
    selectors.add_argument('--mcp-dispatch-config-file');selectors.add_argument('--test-identity-file')
    selectors.add_argument('--admin-token-file');selectors.add_argument('--actor-token-file')
    selectors.add_argument('--mcp-development-config-file');selectors.add_argument('--enable-mcp',action='store_true')
    selectors.add_argument('--session-ttl-seconds',type=int,default=1800)
    args,_=selectors.parse_known_args(app_argv)
    if args.tenant!=config['tenant_id']:raise ValueError('HANDOFF_RUNTIME_TENANT_MISMATCH')
    if args.test_identity_file or args.admin_token_file or args.actor_token_file:
        raise ValueError('SINGLE_AUTH_MODE_REQUIRED')
    if not os.path.isdir(os.path.join(config['lifecycle_root'],'artifacts')):
        raise ValueError('EXISTING_CANDIDATE_LIFECYCLE_ROOT_REQUIRED')
    if not os.path.isdir(config['ledger_root']):raise ValueError('EXISTING_HANDOFF_LEDGER_ROOT_REQUIRED')
    if any(not isinstance(c,dict) or c.get('tenant_id')!=args.tenant for c in config['contracts']):
        raise ValueError('HANDOFF_RUNTIME_CONTRACT_TENANT_MISMATCH')
    if native:
        if not args.enable_mcp or not args.mcp_development_config_file or mcp_development_host is not None:
            raise ValueError('NATIVE_RUNNER_REQUIRES_EXISTING_MCP_DEVELOPMENT_SELECTOR')
        from native_development_executor import NativeDevelopmentExecutor
        if native_runner_factory is not None:
            if (native_runner is not None or not callable(native_runner_factory)
                    or not NativeDevelopmentExecutor.valid_plan(native_test_plan_sha256)):
                raise ValueError('EXACT_NATIVE_RUNNER_FACTORY_AND_PLAN_REQUIRED')
            native_runner=native_runner_factory()
        executor=NativeDevelopmentExecutor(native_runner,native_test_plan_sha256)
        from task_center_mcp_development import load_host
        development=load_host(args.mcp_development_config_file,execution_provider=execution_provider,
                              native_executor=executor)
        if development is None:
            raise ValueError('EXISTING_MCP_DEVELOPMENT_HOST_REQUIRED')
        passthrough['mcp_development_host']=development
    def connect():
        # Existing canonical DB only: no create, migration or profile minting.
        db=sqlite3.connect('file:%s?mode=rw'%quote(os.path.realpath(args.db),safe='/'),uri=True,timeout=5)
        db.row_factory=sqlite3.Row;return db
    db=connect()
    try:
        from task_center_mcp_dispatch_host import load_config as dispatch_config
        config_mcp=dispatch_config(args.mcp_dispatch_config_file) if args.mcp_dispatch_config_file else None
        contract=RoleContractResolver(db,config['contracts'],config['intake_plans'])
        store=runtime.FormalSessionStore if guarded else SessionStore
        sessions=store(connect,args.tenant,args.session_ttl_seconds)
        return runtime.main(app_argv,db=db,tenant_id=args.tenant,issuer=config['issuer'],identity_backend=identity_backend,
            session_store=sessions,evidence=evidence,role_contract=contract,mcp_config=config_mcp,
            lifecycle_root=config['lifecycle_root'],ledger_root=config['ledger_root'],namespace=config['namespace'],
            writer=config['writer'],gateway_runtime=gateway_runtime,provenance_source=provenance_source,
            principal_mapper=principal_mapper,
            handoff_binding_projection_enabled=config.get('handoff_binding_projection_enabled',False),**passthrough)
    finally:db.close()


def development_main(argv=None, *, issuer,provenance_source,principal_mapper,
                     native_runner=None,native_test_plan_sha256=None,
                     gateway_runtime=None,execution_provider=None):
    """MCP development bootstrap, independent of HandoffHost evidence assembly.

    In-process injection only; same real source/mapper and canonical sessions.
    No issuer, SSO, cross-runtime bridge or CLI source loader is created here.
    """
    from task_center_provenance_consumer import GuardedProvenanceConsumer
    GuardedProvenanceConsumer.validate_source(provenance_source,principal_mapper)
    selectors=argparse.ArgumentParser(add_help=False)
    selectors.add_argument('--db',required=True)
    selectors.add_argument('--tenant',required=True)
    selectors.add_argument('--enable-mcp',action='store_true')
    selectors.add_argument('--mcp-development-config-file',required=True)
    selectors.add_argument('--session-ttl-seconds',type=int,default=1800)
    selectors.add_argument('--test-identity-file')
    selectors.add_argument('--admin-token-file')
    selectors.add_argument('--actor-token-file')
    app_argv=list(sys.argv[1:] if argv is None else argv)
    args,_=selectors.parse_known_args(app_argv)
    if not args.enable_mcp:
        raise ValueError('DEVELOPMENT_ENTRY_REQUIRES_MCP')
    if args.test_identity_file or args.admin_token_file or args.actor_token_file:
        raise ValueError('SINGLE_AUTH_MODE_REQUIRED')
    executor=None
    if native_runner is not None or native_test_plan_sha256 is not None:
        from native_development_executor import NativeDevelopmentExecutor
        executor=NativeDevelopmentExecutor(native_runner,native_test_plan_sha256)
    from task_center_mcp_development import load_host
    development=load_host(args.mcp_development_config_file,
        execution_provider=execution_provider,native_executor=executor)
    if development is None:
        raise ValueError('EXISTING_MCP_DEVELOPMENT_HOST_REQUIRED')
    def connect():
        db=sqlite3.connect('file:%s?mode=rw'%quote(os.path.realpath(args.db),safe='/'),uri=True,timeout=5)
        db.row_factory=sqlite3.Row
        return db
    db=connect()
    try:
        from task_center_handoff_backend import CanonicalHandoffBackend
        sessions=runtime.FormalSessionStore(connect,args.tenant,args.session_ttl_seconds)
        consumer=GuardedProvenanceConsumer(sessions,provenance_source,principal_mapper)
        backend=CanonicalHandoffBackend(sessions,consumer,issuer,db)
        identity=runtime.HostIdentityProvider(args.tenant,backend)
        sessions.bind_identity(identity)
        from task_center_app import main as app_main
        return app_main(app_argv,gateway_runtime,identity_provider=identity,
            session_store=sessions,mcp_development_host=development,
            mcp_claim_host=getattr(development,'claim_host',None),
            execution_provider=execution_provider)
    finally:
        db.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except ValueError as exc:
        # Only fixed local error codes, never backend/config/secret bodies.
        message=str(exc)
        if not message or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in message):
            message='HANDOFF_RUNTIME_STARTUP_REJECTED'
        sys.stderr.write(message+'\n');raise SystemExit(69)
