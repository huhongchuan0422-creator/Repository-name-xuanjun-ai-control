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
from task_center_handoff_runtime import HostIdentityProvider,HostActionAdapter
from task_center_handoff_host import HandoffHost
from task_center_handoff_ledger import HandoffLedgerBridge
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
    if set(config)!=base|fields:raise ValueError('HANDOFF_RUNTIME_CONFIG_INVALID')
    for key in ('tenant_id','issuer','namespace','writer'):
        if not isinstance(config[key],str) or not config[key]:raise ValueError('HANDOFF_RUNTIME_CONFIG_INVALID')
    for key in ('lifecycle_root','ledger_root'):
        if not isinstance(config[key],str) or not os.path.isabs(config[key]):raise ValueError('HANDOFF_RUNTIME_ROOT_REQUIRED')
    if not isinstance(config['contracts'],list) or not isinstance(config['intake_plans'],list):
        raise ValueError('HANDOFF_RUNTIME_CONTRACTS_REQUIRED')
    return config


def main(argv=None, *, identity_backend=None,evidence=None,gateway_runtime=None,
         mcp_claim_host=None,mcp_development_host=None,execution_provider=None):
    """Trusted host imports main with existing authority/evidence objects.

    CLI only supplies protected selectors. It cannot create/import an identity
    backend. Missing authority is checked before DB open or SessionStore init.
    """
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--handoff-runtime-config-file',required=True)
    launch,app_argv=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    config=load_config(launch.handoff_runtime_config_file)
    from task_center_app import main as app_main
    passthrough=dict(mcp_claim_host=mcp_claim_host,mcp_development_host=mcp_development_host,execution_provider=execution_provider)
    if not config['enabled']:
        return app_main(app_argv,gateway_runtime,**passthrough)
    identity=HostIdentityProvider(config['tenant_id'],identity_backend)
    selectors=argparse.ArgumentParser(add_help=False)
    selectors.add_argument('--db',required=True);selectors.add_argument('--tenant',required=True)
    selectors.add_argument('--mcp-dispatch-config-file');selectors.add_argument('--test-identity-file')
    selectors.add_argument('--session-ttl-seconds',type=int,default=1800)
    args,_=selectors.parse_known_args(app_argv)
    if args.tenant!=config['tenant_id']:raise ValueError('HANDOFF_RUNTIME_TENANT_MISMATCH')
    if args.test_identity_file:raise ValueError('SINGLE_AUTH_MODE_REQUIRED')
    if not os.path.isdir(os.path.join(config['lifecycle_root'],'artifacts')):
        raise ValueError('EXISTING_CANDIDATE_LIFECYCLE_ROOT_REQUIRED')
    if not os.path.isdir(config['ledger_root']):raise ValueError('EXISTING_HANDOFF_LEDGER_ROOT_REQUIRED')
    if any(not isinstance(c,dict) or c.get('tenant_id')!=args.tenant for c in config['contracts']):
        raise ValueError('HANDOFF_RUNTIME_CONTRACT_TENANT_MISMATCH')
    def connect():
        # Existing canonical DB only: no create, migration or profile minting.
        db=sqlite3.connect('file:%s?mode=rw'%quote(os.path.realpath(args.db),safe='/'),uri=True,timeout=5)
        db.row_factory=sqlite3.Row;return db
    db=connect()
    try:
        from task_center_mcp_dispatch_host import load_config as dispatch_config
        config_mcp=dispatch_config(args.mcp_dispatch_config_file) if args.mcp_dispatch_config_file else None
        contract=RoleContractResolver(db,config['contracts'],config['intake_plans'])
        host=HandoffHost(db,args.tenant,config['issuer'],HostActionAdapter(identity,config['issuer'],evidence),
            mcp_config=config_mcp,role_contract=contract,candidate_lifecycle_root=config['lifecycle_root'])
        bridge=HandoffLedgerBridge(host,config['ledger_root'],config['namespace'],config['writer'])
        sessions=SessionStore(connect,args.tenant,args.session_ttl_seconds)
        return app_main(app_argv,gateway_runtime,identity_provider=identity,session_store=sessions,
            handoff_host=host,ledger_bridge=bridge,**passthrough)
    finally:db.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except ValueError as exc:
        # Only fixed local error codes, never backend/config/secret bodies.
        message=str(exc)
        if not message or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in message):
            message='HANDOFF_RUNTIME_STARTUP_REJECTED'
        sys.stderr.write(message+'\n');raise SystemExit(69)
