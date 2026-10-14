#!/usr/bin/python3
from __future__ import print_function
import argparse,json,os,pwd,socket,stat,struct,sys
from native_gateway_controller import GatewayController,strict_json

MAXIMUM=1048576
ALLOWED=('preflight','admit','launch','inspect','report','stop','owner_cycle')

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
    if op=='owner_cycle': return controller.owner_cycle()
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
