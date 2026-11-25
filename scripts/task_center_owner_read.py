"""One read-only HandoffHost action over a parent-owned inherited pipe.

Not a login issuer, grant store, HTTP server or general command runner. The
Gateway owner alone releases the result after rechecking its live authority.
The child rechecks the existing TC session, FORMAL profile and READ grant.
"""
import argparse,json,os,sqlite3,stat,sys,time
from urllib.parse import quote
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from task_center_handoff_host import FormalHandoffIdentityProvider,HandoffHost
from task_center_handoff_runtime import HostIdentityProvider,HostActionAdapter
from task_center_handoff_backend import CanonicalHandoffBackend
from task_center_handoff_launch import load_config
from task_center_mcp_dispatch_host import load_config as load_dispatch
from task_center_role_contract import RoleContractResolver
from task_center_session_auth import SessionStore

class OwnerReadSource(FormalHandoffIdentityProvider):
    """One parent-admitted disclosure, never persistent session provenance."""
    def __init__(self,binding):self.binding=binding
    def verify(self,*args):return None
    def is_formal_session(self,session):
        b=self.binding
        return (all(session.get(k)==b[k] for k in ('tenant_id','principal_id','session_hash'))
            and time.time()<b['expires_at'])

def read_receipt(db_path,config,dispatch,binding,request):
    if not config['enabled'] or binding['tenant_id']!=config['tenant_id']:
        raise ValueError('OWNER_READ_TENANT_REQUIRED')
    if set(request)!={'task_id','attempt_id','event_id'} or any(request[k]!=binding[k] for k in ('task_id','attempt_id')):
        raise ValueError('OWNER_READ_EXACT_BINDING_REQUIRED')
    def connect():
        db=sqlite3.connect('file:'+quote(os.path.realpath(db_path),safe='/')+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');return db
    db=connect()
    try:
        # Borrow existing SessionStore read semantics without its schema ctor.
        sessions=SessionStore.__new__(SessionStore)
        sessions.connection_factory=connect;sessions.tenant_id=config['tenant_id'];sessions.clock=time.time
        row=db.execute('SELECT * FROM task_center_sessions WHERE tenant_id=? AND session_hash=?',
            (binding['tenant_id'],binding['session_hash'])).fetchone()
        if row is None or row['revoked_at'] is not None:raise ValueError('OWNER_READ_CURRENT_SESSION_REQUIRED')
        session=dict(tenant_id=binding['tenant_id'],principal_id=row['principal_id'],
            roles=json.loads(row['roles_json']),session_hash=row['session_hash'],
            csrf_hash=row['csrf_hash'],expires_at=min(row['expires_at'],binding['expires_at']))
        backend=CanonicalHandoffBackend(sessions,OwnerReadSource(binding),config['issuer'],db)
        identity=HostIdentityProvider(config['tenant_id'],backend)
        if not identity.is_formal_session(session):raise ValueError('OWNER_READ_CURRENT_SESSION_REQUIRED')
        contract=RoleContractResolver(db,config['contracts'],config['intake_plans'])
        host=HandoffHost(db,config['tenant_id'],config['issuer'],HostActionAdapter(identity,config['issuer']),
            mcp_config=dispatch,role_contract=contract)
        return host.read_receipt(session,request['task_id'],request['attempt_id'],request['event_id'])
    finally:db.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True);parser.add_argument('--runtime-config',required=True)
    parser.add_argument('--dispatch-config',required=True)
    args=parser.parse_args()
    # fd3 is created by spawn, not a socket, token, path or public listener.
    if not stat.S_ISFIFO(os.fstat(3).st_mode) and not stat.S_ISSOCK(os.fstat(3).st_mode):
        raise ValueError('OWNER_READ_PARENT_PIPE_REQUIRED')
    with os.fdopen(3,'rb') as channel:raw=channel.read(32769)
    if len(raw)>32768:raise ValueError('OWNER_READ_BODY_LIMIT')
    value=json.loads(raw.decode('utf8'))
    if set(value)!={'binding','request','operation_id','request_digest'}:raise ValueError('OWNER_READ_PACKET_REQUIRED')
    result=read_receipt(args.db,load_config(args.runtime_config),load_dispatch(args.dispatch_config),value['binding'],value['request'])
    print(json.dumps(dict(operation_id=value['operation_id'],request_digest=value['request_digest'],receipt=result),sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception:
        # No database path, row, backend exception or credential in stderr.
        sys.stderr.write('OWNER_READ_REJECTED\n');raise SystemExit(69)
