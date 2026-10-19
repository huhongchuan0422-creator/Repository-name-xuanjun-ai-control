"""Production management bridge. Never invents isolation or signs host facts.

The management adapter is an explicitly SHA-pinned existing control-plane
program, not an arbitrary shell command. It must perform real isolation and
readback and return the independently signed protocol response. Missing input
fails closed. The separate reservation journal is NOT an AuthorityStore.
"""
import fcntl
import os
import selectors
import socket
import sqlite3
import stat
import struct
import subprocess
import sys
import time

r = None
e = None


class Reservations(object):
    def __init__(self, path):
        self.path = r.path(path)
        self.parent = r.directory(os.path.dirname(path))
        self.lock = None
        try:
            self.lock = os.open(os.path.basename(path)+'.lock', os.O_RDWR | os.O_CREAT |
                                os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.parent)
            info = os.fstat(self.lock)
            r.need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                   and stat.S_IMODE(info.st_mode) == 0o600, 'RESERVATION_LOCK')
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd = r.opened(path)
            self.identity = os.fstat(fd)
            os.close(fd)
            r.need(not any(os.path.lexists(path+x) for x in ('-journal','-wal','-shm')),
                   'RESERVATION_RECOVERY_REQUIRED')
            self.db = sqlite3.connect(path, timeout=1, isolation_level=None)
            r.need(self.db.execute('PRAGMA journal_mode').fetchone()==('delete',),
                   'RESERVATION_JOURNAL_MODE')
            self.db.execute('PRAGMA synchronous=FULL')
            r.need(self.db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'RESERVATION_INTEGRITY')
            r.need(self.db.execute('SELECT value FROM metadata WHERE name=?', ('kind',)).fetchone()
                   == ('P2_MANAGEMENT_RESERVATIONS_V1',), 'NOT_RESERVATION_JOURNAL')
        except BaseException:
            self.close()
            raise

    @staticmethod
    def initialize(path):
        # Explicit operator operation in a new protected management directory.
        # Never called by serve, recovery apply or any unknown-state retry.
        parent = r.directory(os.path.dirname(r.path(path)))
        try:
            r.need(not any(os.path.lexists(path+s) for s in ('', '-journal', '-wal', '-shm', '.lock')),
                   'RESERVATION_OUTPUT_EXISTS')
            fd = os.open(os.path.basename(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=parent)
            os.close(fd)
            db = sqlite3.connect(path)
            try:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
                db.execute('INSERT INTO metadata VALUES(?,?)', ('kind','P2_MANAGEMENT_RESERVATIONS_V1'))
                db.execute('CREATE TABLE reservations(old_id TEXT PRIMARY KEY,new_id TEXT UNIQUE NOT NULL,'
                    'database_path TEXT UNIQUE NOT NULL,writer_id TEXT UNIQUE NOT NULL,'
                    'request_sha TEXT UNIQUE NOT NULL,binding TEXT NOT NULL)')
                db.execute('CREATE TABLE audit(sequence INTEGER PRIMARY KEY,request_sha TEXT NOT NULL,'
                           'response_sha TEXT NOT NULL,operation TEXT NOT NULL)')
                db.commit()
            finally:
                db.close()
            fd = os.open(os.path.basename(path), os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try: os.fsync(fd)
            finally: os.close(fd)
            os.fsync(parent)
        finally:
            os.close(parent)

    def check(self, request, operation):
        info=os.stat(os.path.basename(self.path),dir_fd=self.parent,follow_symlinks=False)
        r.need((info.st_dev,info.st_ino)==(self.identity.st_dev,self.identity.st_ino),
               'RESERVATION_REPLACED')
        row=self.db.execute('SELECT request_sha FROM reservations WHERE old_id=?',
                            (request['old_authority_id'],)).fetchone()
        digest=r.sha(r.canonical(request))
        if row is None:
            r.need(operation=='recovery_apply','RESERVATION_NOT_COMMITTED')
            collisions=self.db.execute('SELECT 1 FROM reservations WHERE new_id=? OR database_path=? OR writer_id=?',
                (request['new_authority_id'],request['target_database'],request['writer_id'])).fetchone()
            r.need(collisions is None,'RESERVATION_CONFLICT')
        else:
            r.need(row==(digest,),'RESERVATION_CONFLICT')

    def commit(self, request, response, operation):
        info = os.stat(os.path.basename(self.path), dir_fd=self.parent, follow_symlinks=False)
        r.need((info.st_dev,info.st_ino)==(self.identity.st_dev,self.identity.st_ino),
               'RESERVATION_REPLACED')
        digest = r.sha(r.canonical(request))
        binding = r.canonical(response['body']['reservation']).decode('ascii')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT request_sha,binding FROM reservations WHERE old_id=?',
                                  (request['old_authority_id'],)).fetchone()
            if row is None:
                r.need(operation == 'recovery_apply', 'RESERVATION_NOT_COMMITTED')
                self.db.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',
                    (request['old_authority_id'],request['new_authority_id'],request['target_database'],
                     request['writer_id'],digest,binding))
            else:
                r.need(row == (digest,binding), 'RESERVATION_CONFLICT')
            self.db.execute('INSERT INTO audit(request_sha,response_sha,operation) VALUES(?,?,?)',
                            (digest,r.sha(r.canonical(response)),operation))
            self.db.commit()
            # No positive response is sent before both SQLite and directory durability.
            os.fsync(self.parent)
        except BaseException:
            if self.db.in_transaction: self.db.rollback()
            raise

    def close(self):
        if hasattr(self,'db'): self.db.close()
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if getattr(self,'parent',None) is not None:
            os.close(self.parent)
            self.parent = None


def adapter_query(ref, payload):
    r.reference(ref)
    fd = r.opened(ref['path'])
    process = None
    try:
        raw = os.read(fd,1048577)
        r.need(len(raw)<=1048576 and r.sha(raw)==ref['sha256'], 'MANAGEMENT_ADAPTER_SHA')
        # Execute verified bytes rather than reopening a changeable source path.
        program = "import sys; source=sys.stdin.buffer.read(1048577); exec(compile(source," + repr(ref['path']) + ", 'exec'), {'__name__':'__main__','P2_MANAGEMENT_REQUEST':" + repr(payload) + "})"
        process = subprocess.Popen([sys.executable,'-I','-B','-S','-c',program],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            cwd='/',env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
        # Feed bounded verified source concurrently; selector bounds output/time.
        import threading
        def feed():
            try: process.stdin.write(raw); process.stdin.close()
            except (OSError,ValueError): pass
        writer = threading.Thread(target=feed); writer.daemon=True; writer.start()
        output = b''
        deadline=time.monotonic()+4
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while True:
                remaining=deadline-time.monotonic()
                r.need(remaining>0,'MANAGEMENT_ADAPTER_TIMEOUT')
                r.need(bool(selector.select(remaining)),'MANAGEMENT_ADAPTER_TIMEOUT')
                chunk=os.read(process.stdout.fileno(),min(65536,r.MAX+1-len(output)))
                if not chunk: break
                output+=chunk
                r.need(len(output)<=r.MAX,'MANAGEMENT_ADAPTER_BOUND')
        r.need(process.wait(timeout=max(.01,deadline-time.monotonic()))==0,'MANAGEMENT_ADAPTER_FAILED')
        return r.decode(output)
    finally:
        os.close(fd)
        if process is not None:
            if process.poll() is None: process.kill()
            process.wait()
            process.stdout.close()
            if not process.stdin.closed: process.stdin.close()


class Backend(object):
    def __init__(self, request, keys, plan_ref, restoration, journal, adapter, control=None):
        r.validate_request(request)
        r.reference(plan_ref)
        if control is None:r.reference(adapter)
        self.request,self.keys,self.plan_ref,self.restoration=request,keys,plan_ref,restoration
        self.journal,self.adapter=journal,adapter
        self.control=control

    def handle(self, probe):
        r.fields(probe,'schema operation request_sha256 challenge')
        r.need(type(probe['schema']) is int and probe['schema']==1 and
               probe['operation'] in ('recovery_apply','execution_gate') and
               probe['request_sha256']==r.sha(r.canonical(self.request)) and
               type(probe['challenge']) is str and len(probe['challenge'])==32 and
               all(x in '0123456789abcdef' for x in probe['challenge']), 'PROVIDER_PROBE')
        self.journal.check(self.request,probe['operation'])
        if self.control is not None:
            return self.control.respond(probe)
        response=adapter_query(self.adapter, {'probe':probe,'request':self.request,
            'plan':self.plan_ref,'restoration':self.restoration})
        e.validate_response(self.request,probe,response,self.keys,self.plan_ref,self.restoration)
        self.journal.commit(self.request,response,probe['operation'])
        return response


def serve(path, backend):
    parent=r.directory(os.path.dirname(r.path(path)))
    name=os.path.basename(path)
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        # Existing socket is retained on restart: no blind unlink or takeover.
        r.need(not os.path.lexists(path),'PROVIDER_SOCKET_EXISTS_RECONCILE')
        prior=os.umask(0o177)
        try: listener.bind('/proc/self/fd/'+str(parent)+'/'+name)
        finally: os.umask(prior)
        listener.listen(8)
        while True:
            conn,unused=listener.accept()
            with conn:
                conn.settimeout(5)
                unused_pid,uid,unused_gid=struct.unpack('3i',conn.getsockopt(
                    socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
                if uid!=0: continue
                try:
                    def exact(n):
                        result=b''
                        while len(result)<n:
                            chunk=conn.recv(n-len(result));r.need(bool(chunk),'PROVIDER_EOF')
                            result+=chunk
                        return result
                    size=struct.unpack('!I',exact(4))[0]
                    r.need(0<size<=4096,'PROVIDER_PROBE_BOUND')
                    response=backend.handle(r.decode(exact(size)))
                    raw=r.canonical(response)
                    r.need(len(raw)<=r.MAX,'PROVIDER_RESPONSE_BOUND')
                    conn.sendall(struct.pack('!I',len(raw))+raw)
                except (OSError,ValueError,RuntimeError,sqlite3.Error,subprocess.SubprocessError):
                    # No unsigned error packet and no raw configuration in logs.
                    continue
    finally:
        listener.close()
        os.close(parent)


def main():
    import argparse
    import hashlib
    import types
    global r, e
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('initialize-reservations','register-control','serve'))
    parser.add_argument('--journal',required=True)
    for name in ('bootstrap-sha256','recovery-code-sha256','executor-sha256'):
        parser.add_argument('--'+name,required=True)
    for name in ('request','request-sha256','trust','trust-sha256','plan','plan-sha256',
                 'evidence','evidence-sha256','adapter','adapter-sha256'):
        parser.add_argument('--'+name)
    for name in ('control-config','control-config-sha256','control-code-sha256','control-approval','control-approval-sha256'):
        parser.add_argument('--'+name)
    args=parser.parse_args()
    if (os.getuid()!=0 or os.geteuid()!=0 or not sys.flags.isolated or
            not sys.flags.no_site or not sys.dont_write_bytecode or
            os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ'):
        raise RuntimeError('ISOLATED_UK_ROOT_REQUIRED')
    # Read the small sibling bootstrap without trusting sys.path or following
    # writable/symlink ancestry. Its exact SHA is supplied by the Owner command.
    here = os.path.dirname(os.path.abspath(__file__))
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in here.strip('/').split('/'):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('BOOTSTRAP_PARENT')
        fd = os.open('bootstrap.py', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o022:
            raise RuntimeError('BOOTSTRAP_FILE')
        raw = os.read(fd, 1048577)
    finally:
        os.close(fd)
    if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != args.bootstrap_sha256:
        raise RuntimeError('BOOTSTRAP_SHA')
    bootstrap = types.ModuleType('_p2_recovery_bootstrap')
    exec(compile(raw, here + '/bootstrap.py', 'exec'), bootstrap.__dict__)
    r = bootstrap.load(here + '/recovery.py', args.recovery_code_sha256)
    executor = bootstrap.load(here + '/executor.py', args.executor_sha256)
    executor.r = r
    e=executor
    if args.operation=='initialize-reservations':
        Reservations.initialize(args.journal)
        print('{"management_reservations":"INITIALIZED","authority_initialized":false}')
        return
    r.need(all(getattr(args,name) is not None for name in
        ('request','request_sha256','trust','trust_sha256','plan','plan_sha256',
         'evidence','evidence_sha256')), 'PROVIDER_CONFIG_REQUIRED')
    r.need(args.control_config is not None or
           (args.adapter is not None and args.adapter_sha256 is not None),'MANAGEMENT_ADAPTER_REQUIRED')
    request=r.decode(r.read(args.request,args.request_sha256))
    keys=r.load_trust(args.trust,args.trust_sha256)
    packet=r.decode(r.read(args.evidence,args.evidence_sha256))
    e.historical_recipe(request,packet,keys)
    ref={'path':args.plan,'sha256':args.plan_sha256}
    plan=e.signed_plan(request,packet,ref)
    journal=Reservations(args.journal)
    try:
        control=None
        if args.control_config is not None:
            r.need(args.control_config_sha256 is not None and args.control_code_sha256 is not None,'CONTROL_PINS_REQUIRED')
            module=bootstrap.load(here+'/control_plane.py',args.control_code_sha256)
            module.r=r;module.e=e
            control=module.ControlPlane(journal,request,keys,ref,packet['body']['restoration'],
                {'path':args.control_config,'sha256':args.control_config_sha256})
        if args.operation=='register-control':
            r.need(control is not None and args.control_approval is not None and
                   args.control_approval_sha256 is not None,'CONTROL_APPROVAL_REQUIRED')
            control.register({'path':args.control_approval,'sha256':args.control_approval_sha256})
            print('{"control_config":"REGISTERED_NOT_ACTIVATED","authority_initialized":false}')
            return
        backend=Backend(request,keys,ref,packet['body']['restoration'],journal,
                        ({'path':args.adapter,'sha256':args.adapter_sha256} if control is None else None),control)
        serve(plan['provider_socket'],backend)
    finally: journal.close()


if __name__=='__main__':
    try: main()
    except Exception:
        print('{"state":"HOLD_RETAIN_OUTPUT","reason":"PROVIDER_FAILED_RECONCILE"}')
        sys.exit(2)
