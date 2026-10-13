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
        identity=self._db_identity(fd)
        self._assert_db_identity(fd,identity)
        try:
            # The SQLite connection is opened through the already pinned fd.
            # If pathname replacement makes that fd no longer reopenable for
            # SQLite/WAL, classify the observed identity drift before returning.
            uri='file:/proc/self/fd/%d?mode=rw' % fd
            conn=sqlite3.connect(uri,uri=True,timeout=10,isolation_level=None)
        except sqlite3.OperationalError:
            try:
                self._assert_db_identity(fd,identity)
            except LeaseLost:
                os.close(fd)
                raise
            os.close(fd)
            raise SchemaMismatch('existing authoritative database unavailable')
        conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            conn.execute('BEGIN IMMEDIATE')
            self._assert_activation();self._assert_db_identity(fd,identity)
            yield conn,identity
            self._assert_activation();self._assert_db_identity(fd,identity)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close();os.close(fd)

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
    inventory_method = (
        "\n"
        "    def record_inventory_notices(self,limit=100):\n"
        "        if self.activation_store is None or self.activation_binding is None:\n"
        "            raise LeaseLost('inventory notice requires active canonical generation')\n"
        "        if type(limit) is not int or not 1<=limit<=100:\n"
        "            raise ValueError('inventory notice limit')\n"
        "        from execution_supervision import ExecutionSupervisor\n"
        "        from task_supervisor_inventory_adapter import canonical_inventory_page\n"
        "        with self._pinned_transaction() as value:\n"
        "            conn,identity=value\n"
        "            required=('supervised_runs','supervision_events','supervision_delivery')\n"
        "            if any(not conn.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name=?\",(name,)).fetchone() for name in required):\n"
        "                raise SchemaMismatch('existing supervision schema required')\n"
        "            supervisor=ExecutionSupervisor.__new__(ExecutionSupervisor)\n"
        "            supervisor.db_path=self.db_path;supervisor.clock=self.clock\n"
        "            supervisor.activation_store=self.activation_store\n"
        "            supervisor.activation_binding=dict(self.activation_binding)\n"
        "            supervisor.max_delivery_attempts=3;supervisor.claim_ttl=30\n"
        "            receipts=[];observed=0;pages=0;after_id=None\n"
        "            while True:\n"
        "                pages+=1\n"
        "                if pages>64: raise ValueError('inventory pagination bound exceeded')\n"
        "                page=canonical_inventory_page(conn,self._now(),after_id=after_id,limit=limit,\n"
        "                    activation_binding=self.activation_binding,ledger_identity=identity)\n"
        "                observed+=len(page['tasks'])\n"
        "                for intent in page['tasks']:\n"
        "                    if intent['decision']=='HOLD_AND_NOTIFY_REQUIRES_ADMISSION':\n"
        "                        receipts.append(supervisor.record_inventory_notice(\n"
        "                            conn,intent,self.activation_binding,identity))\n"
        "                if page['complete']: break\n"
        "                cursor=page['next_cursor']\n"
        "                if not isinstance(cursor,str) or not cursor or (after_id is not None and cursor<=after_id):\n"
        "                    raise ValueError('inventory cursor did not advance')\n"
        "                after_id=cursor\n"
        "            return {'state':'INVENTORY_NOTICE_PASS','ledger_identity':identity,\n"
        "                    'observed':observed,'pages':pages,'notices':receipts,\n"
        "                    'dispatch_performed':False}\n"
    )
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

    manifest=deploy/'integration-manifest.json';value=json.loads(manifest.read_text());files=value['files']
    changed=[controller,stage1/'native_gateway_controller.py.json',relay,preflight,ledger,wake,fixed,entry,
             dispatcher,relay_template,relay_socket,relay_service]
    for item in changed:
        files[item.relative_to(source).as_posix()]=sha(item)
    manifest.write_text(json.dumps(value,sort_keys=True,indent=2,separators=(',', ': '))+'\n')
    print('P2_SERVICE_CONTEXT_TASK23_OVERLAY_APPLIED')

if __name__=='__main__':main()
