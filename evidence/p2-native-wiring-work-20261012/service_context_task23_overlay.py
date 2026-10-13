"""Close service-context and task23 production-caller review blockers.

Runs after the prior P2 overlays on the pinned reconstructed package.
Python 3.6 compatible; no second DB/queue and no model dispatch.
"""
from __future__ import print_function
import hashlib
import json
import pathlib
import sys

def replace_once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:
        raise ValueError('SERVICE_CONTEXT_SOURCE_DRIFT:'+path.name+':'+old[:48])
    path.write_text(text.replace(old,new))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source=pathlib.Path(sys.argv[1]).resolve()
    stage1=source/'stage1';deploy=source/'deploy'

    controller=stage1/'native_gateway_controller.py'
    replace_once(controller,
"""import os
import stat
import subprocess
""",
"""import grp
import os
import pwd
import socket
import stat
import struct
import subprocess
""")
    replace_once(controller,
"""def create_controller(config):
    # The installed transport config is part of the same release manifest.
    # Dispatcher config keeps its existing strict schema.
    config_path = __file__ + '.json'
""",
"""class RelayController(object):
    def __init__(self, config):
        self.socket_path=config['relay_socket']
        self.server_user=config['server_user']
        self.client_group=config['client_group']

    def _call(self, operation, value=None, **params):
        server_uid=pwd.getpwnam(self.server_user).pw_uid
        client_gid=grp.getgrnam(self.client_group).gr_gid
        parent=os.path.dirname(self.socket_path)
        parent_info=os.lstat(parent)
        socket_info=os.lstat(self.socket_path)
        if (os.path.realpath(self.socket_path)!=self.socket_path
                or not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid!=0
                or parent_info.st_mode&0o022
                or not stat.S_ISSOCK(socket_info.st_mode)
                or socket_info.st_uid!=server_uid or socket_info.st_gid!=client_gid
                or stat.S_IMODE(socket_info.st_mode)!=0o660):
            raise NativeContractError('Gateway relay socket identity rejected')
        request={'operation':operation}
        request.update(params)
        if value is not None: request['value']=value
        raw=(json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False)+'\\n').encode('utf-8')
        if len(raw)>1048576: raise NativeContractError('relay request limit')
        client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        client.settimeout(30)
        try:
            client.connect(self.socket_path)
            client.sendall(raw)
            response=bytearray()
            while b'\\n' not in response:
                chunk=client.recv(min(65536,1048577-len(response)))
                if not chunk: raise NativeContractError('Gateway relay truncated')
                response.extend(chunk)
                if len(response)>1048576: raise NativeContractError('Gateway relay response limit')
            result=strict_json(bytes(response).split(b'\\n',1)[0].decode('utf-8'))
            if not isinstance(result,dict) or set(result)!={'ok','result','error'}:
                raise NativeContractError('Gateway relay response shape')
            if result['ok'] is not True:
                raise NativeContractError('Gateway relay rejected: '+str(result.get('error')))
            return result['result']
        finally:
            client.close()

    def preflight(self, config): return self._call('preflight')
    def admit(self, request, key):
        raw=json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False)
        if hashlib.sha256(raw.encode('utf-8')).hexdigest()!=key:
            raise NativeContractError('admission request hash mismatch')
        return self._call('admit',request_json=raw,idempotency_key=key)
    def launch(self, admission): return self._call('launch',admission)
    def inspect(self, receipt): return self._call('inspect',receipt)
    def report(self, receipt): return self._call('report',receipt)
    def stop(self, receipt): return self._call('stop',receipt)


def create_controller(config):
    # Dispatcher receives only a peer-authenticated local relay socket.
    config_path = __file__ + '.json'
""")
    replace_once(controller,
"""    required = {'openclaw_bin', 'openclaw_sha256', 'openclaw_owner_uid',
                'gateway_home', 'gateway_path'}
    if not isinstance(transport, dict) or set(transport) != required:
        raise NativeContractError('transport config keys mismatch')
    return GatewayController(transport)
""",
"""    required={'relay_socket','server_user','client_group'}
    if (not isinstance(transport,dict) or set(transport)!=required
            or transport.get('relay_socket')!='/run/xuanjun-development/p2-gateway.sock'
            or transport.get('server_user')!='xuanjun_dev'
            or transport.get('client_group')!='xuanjun-dispatcher'):
        raise NativeContractError('transport config keys mismatch')
    return RelayController(transport)
""")
    (stage1/'native_gateway_controller.py.json').write_text(
        json.dumps({'relay_socket':'/run/xuanjun-development/p2-gateway.sock',
                    'server_user':'xuanjun_dev','client_group':'xuanjun-dispatcher'},
                   sort_keys=True,separators=(',',':'))+'\n')

    relay=stage1/'p2_gateway_relay.py'
    relay.write_text(r'''#!/usr/bin/python3
from __future__ import print_function
import argparse,json,os,pwd,socket,stat,struct,sys
from native_gateway_controller import GatewayController,strict_json

MAXIMUM=1048576
ALLOWED=('preflight','admit','launch','inspect','report','stop')

def load_config(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022
                or info.st_size>65536): raise ValueError('unsafe relay config')
        raw=os.read(fd,65537)
    finally: os.close(fd)
    value=strict_json(raw.decode('utf-8'))
    required={'openclaw_bin','openclaw_sha256','openclaw_owner_uid',
              'gateway_home','gateway_path','dispatcher_user'}
    if not isinstance(value,dict) or set(value)!=required:
        raise ValueError('relay config keys mismatch')
    return value

def read_request(connection):
    data=bytearray()
    while b'\n' not in data:
        chunk=connection.recv(min(65536,MAXIMUM+1-len(data)))
        if not chunk: raise ValueError('truncated relay request')
        data.extend(chunk)
        if len(data)>MAXIMUM: raise ValueError('relay request limit')
    return strict_json(bytes(data).split(b'\n',1)[0].decode('utf-8'))

def execute(controller,request):
    if not isinstance(request,dict) or request.get('operation') not in ALLOWED:
        raise ValueError('relay operation denied')
    op=request['operation']
    allowed={'operation'}
    if op=='admit': allowed.update(('request_json','idempotency_key'))
    elif op in ('launch','inspect','report','stop'): allowed.add('value')
    if set(request)!=allowed: raise ValueError('relay request keys mismatch')
    if op=='preflight': return controller.preflight({})
    if op=='admit':
        obj=strict_json(request['request_json'])
        return controller.admit(obj,request['idempotency_key'])
    return getattr(controller,op)(request['value'])

def serve_connection(connection,controller,dispatcher_uid):
    connection.settimeout(5)
    try:
        credentials=connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i'))
        unused_pid,uid,unused_gid=struct.unpack('3i',credentials)
        if uid!=dispatcher_uid: raise PermissionError('relay caller rejected')
        result=execute(controller,read_request(connection))
        answer={'ok':True,'result':result,'error':None}
    except Exception as error:
        answer={'ok':False,'result':None,'error':type(error).__name__}
    try:
        connection.sendall((json.dumps(answer,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    except Exception:
        pass
    return answer

def listener(path):
    if int(os.environ.get('LISTEN_FDS','0') or '0')==1 and int(os.environ.get('LISTEN_PID','0') or '0')==os.getpid():
        return socket.socket(fileno=3)
    raise ValueError('systemd socket activation required')

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    args=parser.parse_args(argv)
    config=load_config(args.config)
    if os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:
        raise SystemExit('HOLD_GATEWAY_RELAY_UID')
    dispatcher_uid=pwd.getpwnam(config['dispatcher_user']).pw_uid
    controller=GatewayController(config)
    server=listener('/run/xuanjun-development/p2-gateway.sock')
    while True:
        connection,_=server.accept()
        with connection:
            serve_connection(connection,controller,dispatcher_uid)

if __name__=='__main__': raise SystemExit(main())
''')

    preflight=stage1/'p2_service_context_preflight.py'
    preflight.write_text(r'''#!/usr/bin/python3
from __future__ import print_function
import argparse,json,os,pwd,sys
from development_service import load_config
from native_pipeline_runtime import load_reviewed_controller

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--native-controller',required=True)
    parser.add_argument('--native-controller-sha256',required=True)
    args=parser.parse_args(argv)
    expected=pwd.getpwnam('xuanjun-dispatcher').pw_uid
    if os.geteuid()!=expected: raise SystemExit('HOLD_DISPATCHER_UID')
    config=load_config(args.config)
    runtime=load_reviewed_controller(args.native_controller,args.native_controller_sha256,config)
    result=runtime.preflight(config)
    if not isinstance(result,dict) or result.get('ready') is not True:
        raise SystemExit('HOLD_PLUGIN_PREFLIGHT')
    print(json.dumps({'state':'P2_SERVICE_CONTEXT_PREFLIGHT_PASS','model_calls':0,
                      'launch_performed':False,'dispatcher_uid':expected},
                     sort_keys=True,separators=(',',':')))
    return 0
if __name__=='__main__': raise SystemExit(main())
''')

    relay_template=deploy/'p2-gateway-relay.json.template'
    relay_template.write_text("""{"dispatcher_user":"xuanjun-dispatcher","gateway_home":"/home/xuanjun_dev","gateway_path":"/home/xuanjun_dev/.openclaw/bin:/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin:/usr/bin:/bin","openclaw_bin":"/home/xuanjun_dev/.openclaw/bin/openclaw","openclaw_owner_uid":1002,"openclaw_sha256":"b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2"}
""")
    relay_socket=deploy/'xuanjun-p2-gateway-relay.socket'
    relay_socket.write_text("""[Unit]
Description=Xuanjun P2 authenticated Gateway relay socket
After=xuanjun-uk-openclaw.service

[Socket]
ListenStream=/run/xuanjun-development/p2-gateway.sock
SocketUser=xuanjun_dev
SocketGroup=xuanjun-dispatcher
SocketMode=0660
DirectoryMode=0750
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
""")
    relay_service=deploy/'xuanjun-p2-gateway-relay.service'
    relay_service.write_text("""[Unit]
Description=Xuanjun P2 authenticated Gateway relay
Requires=xuanjun-p2-gateway-relay.socket
After=xuanjun-p2-gateway-relay.socket xuanjun-uk-openclaw.service

[Service]
Type=simple
User=xuanjun_dev
Group=xuanjun_dev
RuntimeDirectory=xuanjun-p2-gateway-relay
RuntimeDirectoryMode=0700
WorkingDirectory=/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1
ExecStart=/usr/bin/python3 /opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/p2_gateway_relay.py --config /etc/xuanjun-development/p2-gateway-relay.json
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
ReadOnlyPaths=/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@ /etc/xuanjun-development
ReadWritePaths=/run/xuanjun-development /run/xuanjun-p2-gateway-relay
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UMask=0077

[Install]
WantedBy=multi-user.target
""")

    dispatcher=deploy/'xuanjun-development-dispatcher.service'
    controller_sha=sha(controller)
    controller_path='/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/native_gateway_controller.py'
    replace_once(dispatcher,
"""After=network-online.target
Wants=network-online.target
""",
"""After=network-online.target xuanjun-p2-gateway-relay.socket
Wants=network-online.target
Requires=xuanjun-p2-gateway-relay.socket
""")
    old_pre='ExecStartPre=/usr/bin/python3 /opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/development_service.py --config /etc/xuanjun-development/dispatcher.json --check-config --native-controller '+controller_path+' --native-controller-sha256 6ed190136acb0bb83d116b70724bc11b24ed721a530204bd2f360e63d96c0618'
    new_pre='ExecStartPre=/usr/bin/python3 /opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/development_service.py --config /etc/xuanjun-development/dispatcher.json --check-config --native-controller '+controller_path+' --native-controller-sha256 '+controller_sha+'\nExecStartPre=/usr/bin/python3 /opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/p2_service_context_preflight.py --config /etc/xuanjun-development/dispatcher.json --native-controller '+controller_path+' --native-controller-sha256 '+controller_sha
    replace_once(dispatcher,old_pre,new_pre)
    replace_once(dispatcher,
'ExecStart=/usr/bin/python3 /opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/development_service.py --config /etc/xuanjun-development/dispatcher.json --native-controller '+controller_path+' --native-controller-sha256 6ed190136acb0bb83d116b70724bc11b24ed721a530204bd2f360e63d96c0618',
'ExecStart=/usr/bin/python3 /opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/stage1/development_service.py --config /etc/xuanjun-development/dispatcher.json --native-controller '+controller_path+' --native-controller-sha256 '+controller_sha)

    ledger=stage1/'execution_ledger.py'
    replace_once(ledger,
"""    @contextlib.contextmanager
    def _transaction(self):
        self._assert_activation()
        try:
            uri = Path(self.db_path).resolve().as_uri() + '?mode=rw'
            conn = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
        except sqlite3.OperationalError:
            raise SchemaMismatch('existing authoritative database unavailable')
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            conn.execute('BEGIN IMMEDIATE')
            self._assert_activation()
            yield conn
            self._assert_activation()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
""",
"""    @staticmethod
    def _db_identity(fd):
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise SchemaMismatch('canonical database inode unsafe')
        return '%d:%d' % (info.st_dev,info.st_ino)

    def _assert_db_identity(self,fd,identity):
        try:
            current_identity=self._db_identity(fd)
        except SchemaMismatch:
            raise LeaseLost('canonical database fd changed')
        if current_identity!=identity:
            raise LeaseLost('canonical database fd changed')
        current=os.lstat(self.db_path)
        observed='%d:%d' % (current.st_dev,current.st_ino)
        if not stat.S_ISREG(current.st_mode) or observed!=identity:
            raise LeaseLost('canonical database path changed')
        return True

    @contextlib.contextmanager
    def _pinned_transaction(self):
        self._assert_activation()
        fd=os.open(self.db_path,os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        conn=None
        try:
            identity=self._db_identity(fd)
            self._assert_db_identity(fd,identity)
            try:
                uri='file:/proc/self/fd/%d?mode=rw' % fd
                conn=sqlite3.connect(uri,uri=True,timeout=10,isolation_level=None)
            except sqlite3.OperationalError:
                self._assert_db_identity(fd,identity)
                raise SchemaMismatch('existing authoritative database unavailable')
            conn.row_factory=sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            try:
                conn.execute('BEGIN IMMEDIATE')
                self._assert_activation();self._assert_db_identity(fd,identity)
                yield conn,identity
                self._assert_activation();self._assert_db_identity(fd,identity)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        finally:
            try:
                if conn is not None:
                    conn.close()
            finally:
                os.close(fd)

    @contextlib.contextmanager
    def _transaction(self):
        with self._pinned_transaction() as value:
            yield value[0]
""")
    supervisor_tail = (
        "        return ExecutionSupervisor(self.db_path, clock or self.clock,\n"
        "                                   max_delivery_attempts=max_delivery_attempts,\n"
        "                                   claim_ttl=claim_ttl,\n"
        "                                   activation_store=self.activation_store)\n"
    )
    inventory_method = """
    def record_inventory_notices(self,limit=100):
        if self.activation_store is None or self.activation_binding is None:
            raise LeaseLost('inventory notice requires active canonical generation')
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('inventory notice limit')
        from execution_supervision import ExecutionSupervisor
        from task_supervisor_inventory_adapter import canonical_inventory_page
        with self._pinned_transaction() as value:
            conn,identity=value
            required=('supervised_runs','supervision_events','supervision_delivery')
            if any(not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() for name in required):
                raise SchemaMismatch('existing supervision schema required')
            # Reuse canonical events as a durable, activation-bound scan checkpoint.
            # No task/checkpoint/lease is fabricated or overwritten.
            event='INVENTORY_SCAN_CHECKPOINT_V1'
            previous=conn.execute('SELECT details FROM events WHERE event=? ORDER BY id DESC LIMIT 1',
                                  (event,)).fetchone()
            after_id=None;sweep_end=None
            if previous is not None:
                raw=previous['details']
                if not isinstance(raw,str) or len(raw)>65536:
                    raise SchemaMismatch('inventory scan checkpoint invalid')
                try:
                    checkpoint=json.loads(raw)
                except (ValueError,TypeError):
                    raise SchemaMismatch('inventory scan checkpoint invalid')
                if not isinstance(checkpoint,dict) or set(checkpoint)!={'schema','binding','ledger_identity','after_id','sweep_end'} or type(checkpoint['schema']) is not int or checkpoint['schema']!=1:
                    raise SchemaMismatch('inventory scan checkpoint invalid')
                if checkpoint['binding']==self.activation_binding and checkpoint['ledger_identity']==identity:
                    after_id=checkpoint['after_id'];sweep_end=checkpoint['sweep_end']
                    if (after_id is None)!=(sweep_end is None) or (after_id is not None and
                            (not isinstance(after_id,str) or not after_id or len(after_id)>8192
                             or not isinstance(sweep_end,str) or not sweep_end or len(sweep_end)>8192
                             or after_id>=sweep_end)):
                        raise SchemaMismatch('inventory scan cursor invalid')
            # A finite high-water mark makes each sweep finish despite new tasks.
            # IDs inserted behind the cursor are covered by the next sweep.
            if sweep_end is None:
                sweep_end=conn.execute('SELECT MAX(id) FROM tasks').fetchone()[0]
                if sweep_end is not None and (not isinstance(sweep_end,str) or not sweep_end or len(sweep_end)>8192):
                    raise SchemaMismatch('inventory scan high-water mark invalid')
            supervisor=ExecutionSupervisor.__new__(ExecutionSupervisor)
            supervisor.db_path=self.db_path;supervisor.clock=self.clock
            supervisor.activation_store=self.activation_store
            supervisor.activation_binding=dict(self.activation_binding)
            supervisor.max_delivery_attempts=3;supervisor.claim_ttl=30
            receipts=[];observed=0;pages=0;complete=sweep_end is None
            while not complete and pages<64:
                pages+=1
                page=canonical_inventory_page(conn,self._now(),after_id=after_id,limit=limit,
                    activation_binding=self.activation_binding,ledger_identity=identity)
                last=after_id
                for intent in page['tasks']:
                    task_id=intent['id']
                    if task_id>sweep_end:
                        complete=True;break
                    observed+=1;last=task_id
                    if intent['decision']=='HOLD_AND_NOTIFY_REQUIRES_ADMISSION':
                        receipts.append(supervisor.record_inventory_notice(
                            conn,intent,self.activation_binding,identity))
                complete=complete or page['complete'] or (last is not None and last>=sweep_end)
                if complete:
                    break
                cursor=page['next_cursor']
                if not isinstance(cursor,str) or not cursor or len(cursor)>8192 or (after_id is not None and cursor<=after_id) or cursor!=last:
                    raise ValueError('inventory cursor did not advance')
                after_id=cursor
            checkpoint={'schema':1,'binding':dict(self.activation_binding),
                        'ledger_identity':identity,'after_id':None if complete else after_id,
                        'sweep_end':None if complete else sweep_end}
            self._event(conn,None,event,self._now(),checkpoint)
            return {'state':'INVENTORY_NOTICE_PASS' if complete else 'INVENTORY_NOTICE_BOUNDED_PROGRESS',
                    'ledger_identity':identity,'observed':observed,'pages':pages,
                    'notices':receipts,'sweep_complete':complete,'scan_pending':not complete,
                    'dispatch_performed':False}

"""
    replace_once(ledger,supervisor_tail,supervisor_tail+inventory_method)
    # execution_ledger needs stat for inode checks.
    replace_once(ledger,"import sqlite3\nimport time","import sqlite3\nimport stat\nimport time")

    wake=stage1/'mechanical_wake_service.py'
    replace_once(wake,
"""from activation_control import ActivationStore
from mechanical_wake import MechanicalWakeController
""",
"""from activation_control import ActivationStore
from execution_ledger import ExecutionLedger
from mechanical_wake import MechanicalWakeController
""")
    replace_once(wake,
"""LOCK = '/var/lib/xuanjun-development/activation/activation.lock'
""",
"""LOCK = '/var/lib/xuanjun-development/activation/activation.lock'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
""")
    replace_once(wake,
"""    active = activation.read(require_active=True)
    db = sqlite3.connect(Path(active['db_path']).resolve().as_uri() + '?mode=ro',
""",
"""    active = activation.read(require_active=True)
    ledger=ExecutionLedger(active['db_path'],[REPO],activation_store=activation)
    inventory=ledger.record_inventory_notices()
    db = sqlite3.connect(Path(active['db_path']).resolve().as_uri() + '?mode=ro',
""")
    replace_once(wake,
"""                      'native_resume_api': 'UNAVAILABLE',
                      'model_calls': 0, 'results': results},
""",
"""                      'native_resume_api': 'UNAVAILABLE',
                      'inventory': inventory,
                      'model_calls': 0, 'results': results},
""")

    fixed=stage1/'p2_fixed_host_runtime.py'
    replace_once(fixed,
"""    'xuanjun-development-dispatcher.service',
    'xuanjun-github-intake.timer',
)""",
"""    'xuanjun-p2-gateway-relay.socket',
    'xuanjun-p2-gateway-relay.service',
    'xuanjun-development-dispatcher.service',
    'xuanjun-github-intake.timer',
)""")
    replace_once(fixed,
"""    'xuanjun-github-intake.service',
    'xuanjun-development-dispatcher.service',
""",
"""    'xuanjun-github-intake.service',
    'xuanjun-development-dispatcher.service',
    'xuanjun-p2-gateway-relay.service',
    'xuanjun-p2-gateway-relay.socket',
""")

    entry=stage1/'p2_install_entrypoint.py'
    replace_once(entry,
"""    plugin_keys={'id','source','binding_file','binding_sha256','ledger_client_config',
                 'ledger_client_sha256','gateway_service','openclaw_bin','service_user',
                 'docker_dropin'}
""",
"""    plugin_keys={'id','source','binding_file','binding_sha256','ledger_client_config',
                 'ledger_client_sha256','gateway_service','openclaw_bin','service_user',
                 'docker_dropin','gateway_relay_config','gateway_relay_sha256','gateway_relay_socket'}
""")
    replace_once(entry,
"""            or plugin.get('docker_dropin')!='/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'):
""",
"""            or plugin.get('docker_dropin')!='/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'
            or plugin.get('gateway_relay_config')!='/etc/xuanjun-development/p2-gateway-relay.json'
            or not SHA256.fullmatch(plugin.get('gateway_relay_sha256',''))
            or plugin.get('gateway_relay_socket')!='/run/xuanjun-development/p2-gateway.sock'):
""")
    replace_once(fixed,
"""        dropins=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['docker_dropin']]
        if (len(matches)!=1 or matches[0].get('rendered_sha256')!=plugin['binding_sha256']
                or len(clients)!=1 or clients[0].get('rendered_sha256')!=plugin['ledger_client_sha256']
                or len(dropins)!=1):
""",
"""        dropins=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['docker_dropin']]
        relays=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['gateway_relay_config']]
        if (len(matches)!=1 or matches[0].get('rendered_sha256')!=plugin['binding_sha256']
                or len(clients)!=1 or clients[0].get('rendered_sha256')!=plugin['ledger_client_sha256']
                or len(relays)!=1 or relays[0].get('rendered_sha256')!=plugin['gateway_relay_sha256']
                or len(dropins)!=1):
""")


    # Complete the reviewed Gateway reuse boundary and bounded reference reads.
    replace_once(source/'stage1/p2_fixed_host_runtime.py',
"        data, info = _read_regular(value['path'])\n",
"        # Existing OAuth stores may be several MiB; still bounded and read-only.\n        data, info = _read_regular(value['path'], limit=16*1024*1024)\n")
    replace_once(source/'stage1/legacy_host_adapter.py',
'    def restore_legacy_files(self):\n        state = self._state()\n',
"    def restore_legacy_files(self, gateway_only=False):\n        if type(gateway_only) is not bool:\n            raise ValueError('INVALID_LEGACY_RESTORE_SELECTION')\n        state = self._state()\n        gateway='xuanjun-uk-openclaw.service'\n        coordinator='/etc/systemd/system/xuanjun-uk-stage1-minimal.service'\n        if gateway_only and (not os.path.islink(coordinator) or os.readlink(coordinator)!='/dev/null'):\n            raise ValueError('OLD_COORDINATOR_MUST_REMAIN_MASKED')\n")
    replace_once(source/'stage1/legacy_host_adapter.py',
"        for unit, data in payloads.items():\n            value = state['units'][unit]\n            path = value['path']\n            if (not os.path.islink(path) or os.readlink(path) != '/dev/null'):\n                # Allow an interrupted restore only when exact original bytes\n",
"        for unit, data in payloads.items():\n            if gateway_only and unit!=gateway:\n                continue\n            value = state['units'][unit]\n            path = value['path']\n            if (not os.path.islink(path) or os.readlink(path) != '/dev/null'):\n                # Allow an interrupted restore only when exact original bytes\n")
    replace_once(source/'stage1/legacy_host_adapter.py',
"        self._command('daemon-reload')\n        # Restoring files is not permission to restart old/new writers. Caller\n",
"        if gateway_only and (not os.path.islink(coordinator) or os.readlink(coordinator)!='/dev/null'):\n            raise ValueError('OLD_COORDINATOR_MASK_CHANGED')\n        self._command('daemon-reload')\n        # Restoring files is not permission to restart old/new writers. Caller\n")
    replace_once(source/'stage1/p2_install_entrypoint.py',
"            runtime_activation_requested = True\n            runtime_proof = self.runtime.activate(plan['runtime'], active)\n",
"            runtime_activation_requested = True\n            # Cutover masks the old parent as well as the coordinator. Reuse\n            # only its exact backed-up Gateway unit after the new epoch is ACTIVE;\n            # the old coordinator remains masked and no service starts here.\n            gateway_restore=self.cutover.adapter.restore_legacy_files(gateway_only=True)\n            if gateway_restore!={'unit_files_restored':True,'services_restarted':False}:\n                raise ValueError('GATEWAY_REUSE_RESTORE_UNPROVEN')\n            runtime_proof = self.runtime.activate(plan['runtime'], active)\n")
    replace_once(source/'stage1/p2_fixed_host_runtime.py',
"        for service in ALLOWED_SERVICES:\n            self._command(['/usr/bin/systemctl', 'start', service])\n",
"        # The caller restored only the Gateway unit after cutover. Start that\n        # admitted parent before relay/dispatcher preflight, never the old coordinator.\n        self._start_gateway()\n        for service in ALLOWED_SERVICES:\n            self._command(['/usr/bin/systemctl', 'start', service])\n")

    replace_once(fixed,
'    def activate(self, runtime, descriptor):\n',
"    def _unit_enable_state(self, unit):\n        result=self.run(['/usr/bin/systemctl','is-enabled',unit],\n                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,\n                        timeout=15,check=False,env={'PATH':'/usr/bin:/bin','LANG':'C'})\n        value=result.stdout.decode('ascii').strip()\n        if ((value=='enabled' and result.returncode==0)\n                or (value=='disabled' and result.returncode==1)):\n            return value\n        raise ValueError('HOLD_UNSUPPORTED_UNIT_ENABLE_STATE')\n\n    def _boot_binding(self):\n        raw,info=_read_regular(self.receipt_path)\n        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:\n            raise ValueError('UNSAFE_BOOT_PROVISION_RECEIPT')\n        return _digest_bytes(raw)\n\n    def _boot_read(self, binding):\n        path=os.path.join(self.directory,'runtime-boot.json')\n        raw,info=_read_regular(path)\n        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:\n            raise ValueError('UNSAFE_BOOT_JOURNAL')\n        value=json.loads(raw.decode('utf-8'))\n        if (not isinstance(value,dict)\n                or set(value)!={'schema','provision_sha256','state','previous'}\n                or type(value['schema']) is not int or value['schema']!=1\n                or value['provision_sha256']!=binding\n                or value['state'] not in ('ENABLE_REQUESTED','ENABLED','RESTORED')\n                or not isinstance(value['previous'],dict)\n                or set(value['previous'])!=set(ALLOWED_SERVICES+(GATEWAY_SERVICE,))\n                or any(v not in ('enabled','disabled') for v in value['previous'].values())):\n            raise ValueError('BOOT_JOURNAL_BINDING_MISMATCH')\n        return value\n\n    def _enable_boot(self):\n        binding=self._boot_binding()\n        path=os.path.join(self.directory,'runtime-boot.json')\n        if os.path.lexists(path):\n            value=self._boot_read(binding)\n            if value['state']=='RESTORED':raise ValueError('BOOT_TRANSACTION_ALREADY_RESTORED')\n        else:\n            previous={unit:self._unit_enable_state(unit)\n                      for unit in ALLOWED_SERVICES+(GATEWAY_SERVICE,)}\n            value={'schema':1,'provision_sha256':binding,\n                   'state':'ENABLE_REQUESTED','previous':previous}\n            # Durable intent and all original states precede the first enable.\n            _atomic_receipt(path,value)\n        for unit in ALLOWED_SERVICES+(GATEWAY_SERVICE,):\n            self._command(['/usr/bin/systemctl','enable',unit])\n            if self._unit_enable_state(unit)!='enabled':\n                raise ValueError('BOOT_ENABLE_UNPROVEN')\n        value['state']='ENABLED';_atomic_receipt(path,value)\n\n    def _restore_boot(self):\n        path=os.path.join(self.directory,'runtime-boot.json')\n        if not os.path.lexists(path):return\n        value=self._boot_read(self._boot_binding())\n        # Validate every observed state before any rollback effect. Only the\n        # reviewed persistent enabled/disabled states are supported.\n        for unit in ALLOWED_SERVICES+(GATEWAY_SERVICE,):\n            self._unit_enable_state(unit)\n        for unit in reversed(ALLOWED_SERVICES+(GATEWAY_SERVICE,)):\n            previous=value['previous'][unit]\n            if self._unit_enable_state(unit)!=previous:\n                self._command(['/usr/bin/systemctl',\n                               'enable' if previous=='enabled' else 'disable',unit])\n            if self._unit_enable_state(unit)!=previous:\n                raise ValueError('BOOT_ROLLBACK_UNPROVEN')\n        value['state']='RESTORED';_atomic_receipt(path,value)\n\n    def activate(self, runtime, descriptor):\n")
    replace_once(fixed,
'        # The caller restored only the Gateway unit after cutover.',
'        self._enable_boot()\n        # The caller restored only the Gateway unit after cutover.')
    replace_once(fixed,
'        # All receipt, backup, target and service-drop-in evidence has passed.',
'        self._restore_boot()\n        # All receipt, backup, target and service-drop-in evidence has passed.')

    manifest=deploy/'integration-manifest.json';value=json.loads(manifest.read_text());files=value['files']
    changed=[controller,stage1/'native_gateway_controller.py.json',relay,preflight,ledger,wake,fixed,entry,
             dispatcher,relay_template,relay_socket,relay_service,stage1/'legacy_host_adapter.py']
    for item in changed:
        files[item.relative_to(source).as_posix()]=sha(item)

    # Bind approved informational projections into the authenticated dashboard.
    (stage1/'task_cost_projection.py').write_text('"""Pure cost evidence projection; caller authenticates canonical input."""\nimport re\n\nMAX_AMOUNT = 2 ** 63 - 1\n\n\ndef _id(value):\n    return isinstance(value, str) and re.fullmatch(r\'[A-Za-z0-9_.:-]{1,160}\', value)\n\n\ndef project_costs(task_id, records):\n    """Separate actual/estimated micro-unit totals; never infer absent costs.\n\n    Each complete record represents one unique cost component. Missing actual\n    evidence poisons that currency\'s actual total; estimates remain separate.\n    No conversion, payment, revenue, margin or commission is computed.\n    """\n    if not _id(task_id) or not isinstance(records, list) or len(records) > 10000:\n        raise ValueError(\'INVALID_COST_INPUT\')\n    groups = {}; seen = {}; warnings = set()\n    for record in records:\n        if not isinstance(record, dict) or set(record) != {\n                \'task_id\', \'component_id\', \'currency\', \'kind\', \'amount_micros\',\n                \'evidence_sha256\'}:\n            raise ValueError(\'INVALID_COST_RECORD\')\n        currency = record[\'currency\']; amount = record[\'amount_micros\']\n        evidence = record[\'evidence_sha256\']; kind = record[\'kind\']\n        if (record[\'task_id\'] != task_id or not _id(record[\'component_id\'])\n                or not isinstance(currency, str) or not re.fullmatch(\'[A-Z]{3}\', currency)\n                or kind not in (\'ACTUAL\', \'ESTIMATE\', \'UNKNOWN\')\n                or (amount is not None and (type(amount) is not int\n                    or not 0 <= amount <= MAX_AMOUNT))\n                or (evidence is not None and (not isinstance(evidence, str)\n                    or not re.fullmatch(\'[a-f0-9]{64}\', evidence)))\n                or (kind == \'UNKNOWN\' and (amount is not None or evidence is not None))):\n            raise ValueError(\'INVALID_COST_RECORD\')\n        # One record per component+kind; contradictory duplicates are rejected.\n        key = (record[\'component_id\'], kind)\n        if key in seen:\n            if seen[key] != record:\n                raise ValueError(\'CONFLICTING_COST_RECORD\')\n            continue\n        seen[key] = dict(record)\n        group = groups.setdefault(currency, {\'actual_micros\': 0,\n            \'estimate_micros\': 0, \'actual_complete\': True,\n            \'estimate_complete\': True, \'record_count\': 0, \'has_actual\': False,\n            \'has_estimate\': False})\n        group[\'record_count\'] += 1\n        if kind == \'UNKNOWN\':\n            group[\'actual_complete\'] = False\n            warnings.add(\'UNKNOWN_ACTUAL_COST\')\n        else:\n            prefix = \'actual\' if kind == \'ACTUAL\' else \'estimate\'\n            group[\'has_\' + prefix] = True\n            if amount is None or evidence is None:\n                group[prefix + \'_complete\'] = False\n                warnings.add(\'MISSING_\' + kind + \'_EVIDENCE\')\n            else:\n                group[prefix + \'_micros\'] += amount\n                if group[prefix + \'_micros\'] > MAX_AMOUNT:\n                    raise ValueError(\'COST_TOTAL_OVERFLOW\')\n    for group in groups.values():\n        for prefix in (\'actual\', \'estimate\'):\n            if not group.pop(\'has_\' + prefix) or not group[prefix + \'_complete\']:\n                group[prefix + \'_micros\'] = None\n                group[prefix + \'_complete\'] = False\n    if not groups:\n        warnings.add(\'NO_COST_EVIDENCE\')\n    if any(not g[\'actual_complete\'] for g in groups.values()):\n        warnings.add(\'ACTUAL_TOTAL_INCOMPLETE\')\n    return {\'schema\': \'TASK_COST_PROJECTION_V1\', \'currencies\': groups,\n            \'warnings\': sorted(warnings), \'status\': \'HOLD\' if warnings else \'VIEW_READY\',\n            \'financial_completeness\': \'CALLER_COMPONENT_INVENTORY_REQUIRED\',\n            \'source_authenticity\': \'CALLER_REQUIRED\', \'payment_granted\': False}\n')
    (stage1/'run_usage_projection.py').write_text('"""Aggregate one complete cumulative sample per run; no model polling."""\nimport re\n\nCOUNTERS = (\'model_calls\', \'input_tokens\', \'output_tokens\', \'cpu_seconds\', \'memory_mib\')\n\n\ndef usage_projection(samples):\n    if not isinstance(samples, list) or len(samples) > 10000:\n        raise ValueError(\'INVALID_USAGE_INPUT\')\n    seen = {}; reasons = set(); totals = dict.fromkeys(COUNTERS, 0)\n    for sample in samples:\n        if not isinstance(sample, dict) or set(sample) != {\'run_id\', \'provider\', \'counters\', \'evidence_sha256\'}:\n            raise ValueError(\'INVALID_USAGE_SAMPLE\')\n        run = sample[\'run_id\']; provider = sample[\'provider\']; evidence = sample[\'evidence_sha256\']\n        if (not isinstance(run, str) or not re.fullmatch(r\'[A-Za-z0-9_.:-]{1,160}\', run)\n                or provider not in (\'XUANJUN\', \'TENANT\', \'DEDICATED_CUSTOMER\', \'INTERNAL\', \'UNKNOWN\')):\n            raise ValueError(\'INVALID_USAGE_IDENTITY\')\n        if run in seen:\n            if seen[run] != sample:\n                raise ValueError(\'CONFLICTING_RUN_SAMPLE\')\n            continue\n        seen[run] = dict(sample)\n        if provider == \'UNKNOWN\': reasons.add(\'UNKNOWN_PROVIDER\')\n        valid_evidence = isinstance(evidence, str) and re.fullmatch(\'[a-f0-9]{64}\', evidence)\n        if not valid_evidence: reasons.add(\'MISSING_USAGE_EVIDENCE\')\n        counters = sample[\'counters\']\n        if not isinstance(counters, dict) or set(counters) != set(COUNTERS):\n            raise ValueError(\'INVALID_COUNTER_SCHEMA\')\n        for key in COUNTERS:\n            value = counters[key]\n            if value is not None and (type(value) is not int or not 0 <= value <= 2 ** 63 - 1):\n                raise ValueError(\'INVALID_COUNTER\')\n            if value is None or not valid_evidence:\n                totals[key] = None; reasons.add(\'UNKNOWN_\' + key.upper())\n            elif totals[key] is not None:\n                # Memory is summed per-run peak, a conservative bound, not concurrent usage.\n                totals[key] += value\n                if totals[key] > 2 ** 63 - 1: raise ValueError(\'COUNTER_OVERFLOW\')\n    if not samples:\n        totals = dict.fromkeys(COUNTERS, None); reasons.add(\'NO_USAGE_EVIDENCE\')\n    return {\'schema\': \'RUN_USAGE_PROJECTION_V1\', \'totals\': totals,\n            \'run_count\': len(seen), \'reasons\': sorted(reasons),\n            \'status\': \'HOLD\' if reasons else \'SUPPLIED_USAGE_EVIDENCED\',\n            \'quota_remaining\': None, \'amount\': None, \'execution_granted\': False,\n            \'completeness\': \'CALLER_RUN_INVENTORY_REQUIRED\',\n            \'memory_semantics\': \'SUM_OF_RUN_PEAKS_NOT_CONCURRENT\',\n            \'native_chat_quota_attribution\': \'UNKNOWN\'}\n')
    replace_once(stage1/'owner_dashboard.py', 'def snapshot(path, now=None, limit=200, activation=None):', 'from task_cost_projection import project_costs\nfrom run_usage_projection import usage_projection\n\ndef snapshot(path, now=None, limit=200, activation=None):')
    replace_once(stage1/'owner_dashboard.py', "'counts': counts, 'tasks': tasks,", "'foundation_views': {'usage': usage_projection([]), 'costs': [project_costs(t['id'], []) for t in tasks], 'evidence_status': 'HOLD_NO_CANONICAL_COST_USAGE_PRODUCER'},\n                'counts': counts, 'tasks': tasks,")
    for name in ('task_cost_projection.py','run_usage_projection.py','owner_dashboard.py'):
        files['stage1/'+name]=sha(stage1/name)
    (stage1/'dependency_evidence_view.py').write_text('"""Pure DAG evidence view over caller-authenticated canonical nodes."""\nimport re\n\n\ndef dependency_view(target, nodes):\n    if (not isinstance(target, str) or not re.fullmatch(r\'[A-Za-z0-9_.:-]{1,160}\', target)\n            or not isinstance(nodes, dict) or len(nodes) > 1000 or target not in nodes):\n        raise ValueError(\'INVALID_DEPENDENCY_INPUT\')\n    reasons = set(); visited = set(); active = set(); stack = [(target, False)]\n    while stack:\n        name, leaving = stack.pop()\n        if not isinstance(name, str) or not re.fullmatch(r\'[A-Za-z0-9_.:-]{1,160}\', name):\n            raise ValueError(\'INVALID_NODE_ID\')\n        if leaving:\n            active.remove(name); visited.add(name); continue\n        if name in active:\n            reasons.add(\'DEPENDENCY_CYCLE\'); continue\n        if name in visited:\n            continue\n        node = nodes.get(name)\n        if not isinstance(node, dict) or set(node) != {\'dependencies\', \'state\', \'evidence_sha256\'}:\n            reasons.add(\'MISSING_OR_MALFORMED_NODE\'); visited.add(name); continue\n        deps = node[\'dependencies\']\n        if (not isinstance(deps, list) or len(deps) > 100\n                or any(not isinstance(d, str) or not re.fullmatch(r\'[A-Za-z0-9_.:-]{1,160}\', d) for d in deps)\n                or len(set(deps)) != len(deps)):\n            reasons.add(\'INVALID_DEPENDENCY_LIST\'); visited.add(name); continue\n        # Target is being evaluated for readiness; only ancestors must be done.\n        if name != target and (node[\'state\'] != \'ACCEPTED\'\n                or not isinstance(node[\'evidence_sha256\'], str)\n                or not re.fullmatch(\'[a-f0-9]{64}\', node[\'evidence_sha256\'])):\n            reasons.add(\'DEPENDENCY_NOT_ACCEPTED_WITH_EVIDENCE\')\n        active.add(name); stack.append((name, True))\n        stack.extend((dep, False) for dep in reversed(deps))\n    return {\'schema\': \'DEPENDENCY_EVIDENCE_VIEW_V1\',\n            \'status\': \'HOLD\' if reasons else \'DEPENDENCIES_EVIDENCED\',\n            \'reasons\': sorted(reasons), \'visited_count\': len(visited),\n            \'execution_granted\': False, \'authenticity\': \'CALLER_REQUIRED\'}\n')
    replace_once(stage1/'owner_dashboard.py', 'def snapshot(path, now=None, limit=200, activation=None):', "from dependency_evidence_view import dependency_view\n\ndef _foundation_dependencies(db, task_id, columns):\n    if 'depends' not in columns:\n        return {'status':'HOLD','reasons':['CANONICAL_DEPENDENCY_SCHEMA_MISSING'],'execution_granted':False}\n    rows=db.execute('SELECT id,state,depends FROM tasks LIMIT 1001').fetchall()\n    if len(rows)>1000:\n        return {'status':'HOLD','reasons':['COMPLETE_DEPENDENCY_GRAPH_BOUND'],'execution_granted':False}\n    nodes={}\n    for identity,state,raw in rows:\n        try:depends=json.loads(raw)\n        except (ValueError,TypeError):depends=None\n        # State is observed verbatim; DONE is never promoted to independently\n        # ACCEPTED. No acceptance digest is available from this producer.\n        nodes[identity]={'dependencies':depends,'state':state,'evidence_sha256':None}\n    try:return dependency_view(task_id,nodes)\n    except ValueError:\n        return {'status':'HOLD','reasons':['INVALID_CANONICAL_DEPENDENCY_INPUT'],'execution_granted':False}\n\ndef snapshot(path, now=None, limit=200, activation=None):")
    replace_once(stage1/'owner_dashboard.py', "'foundation_views': {'usage':", "'foundation_views': {'dependencies': {t['id']:_foundation_dependencies(db,t['id'],columns) for t in tasks}, 'usage':")
    files['stage1/dependency_evidence_view.py']=sha(stage1/'dependency_evidence_view.py')
    files['stage1/owner_dashboard.py']=sha(stage1/'owner_dashboard.py')
    manifest.write_text(json.dumps(value,sort_keys=True,indent=2,separators=(',', ': '))+'\n')
    print('P2_SERVICE_CONTEXT_TASK23_OVERLAY_APPLIED')

if __name__=='__main__':main()
