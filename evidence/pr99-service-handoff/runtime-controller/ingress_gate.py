"""Application-side intake closure and drain; no migration Writer or issuer.

An admitted application routes ALL covered jobs through this gate. It borrows a
pre-held, one-use seal fd, never creates paths/locks/controllers or retries jobs.
The existing authority must verify origin coverage and startup reconciliation.
This is an integration component, not an installed endpoint or a durable queue.
A process restart after sealing remains UNKNOWN rather than inferring an empty
queue. Deploying/adapting the live applications is a separate, unfulfilled step.
"""
import hashlib
import json
import os
import queue
import re
import stat
import threading
import time
import uuid
import fcntl
import weakref

from catalogue_binding import encode, digest

_LIVE=weakref.WeakValueDictionary()
_LIVE_MUTEX=threading.RLock()


class IngressHold(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise IngressHold(code)


def runtime_identity():
    # Kernel process identity, not an issuer-supplied PID or a business import.
    with open('/proc/self/stat', 'rb') as stream:
        raw=stream.read(8193)
    need(len(raw)<=8192, 'PROCESS_IDENTITY_BOUND')
    fields=raw.rsplit(b') ',1)[1].split()
    with open('/proc/sys/kernel/random/boot_id','rb') as stream:
        boot=stream.read(129)
    need(len(boot)<=128 and len(fields)>19, 'PROCESS_IDENTITY')
    return {'host':os.uname().nodename, 'pid':os.getpid(), 'start_ticks':int(fields[19]),
            'boot_sha256':hashlib.sha256(boot).hexdigest()}


class ApplicationIngressGate:
    def __init__(self, binding, original_seal_fd, verify_original_binding,
                 check_original_fd, verify_bootstrap, bootstrap_sha256, capacity=1024):
        need(all(callable(x) for x in (verify_original_binding,check_original_fd,verify_bootstrap)),
             'ORIGINAL_INGRESS_BINDING_REQUIRED')
        need(type(capacity)is int and 0<capacity<=4096,'INGRESS_CAPACITY')
        self.binding=json.loads(encode(binding));self.binding_sha=digest(self.binding)
        self.process=runtime_identity()
        self.runtime={**self.process,'gate_id':uuid.uuid4().hex}
        self.fd=original_seal_fd;self.authorize=verify_original_binding;self.check_fd=check_original_fd
        self.bootstrap=verify_bootstrap;self.bootstrap_sha=bootstrap_sha256
        self.mutex=threading.Condition(threading.RLock());self.jobs=queue.Queue(capacity)
        self.tickets={};self.seen=set();self.capacity=capacity;self.sealed=False;self.broken=False
        self.record=None;self.prior_runtime=False
        self.identity=self._bound('query')
        # Only borrow the original one-use descriptor. No new lock file or
        # migration Writer is created. The owner retains and closes the fd.
        with _LIVE_MUTEX:
            need(_LIVE.get(self.identity) is None,'ORIGINAL_INGRESS_FD_ALREADY_BORROWED')
            try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise IngressHold('ORIGINAL_INGRESS_FD_BUSY') from None
            _LIVE[self.identity]=self
        self._refresh()

    def _bound(self, mode):
        need(runtime_identity()==self.process,'INGRESS_PROCESS_CHANGED_NO_INHERITED_GATE')
        b=self.binding
        need(digest(b)==self.binding_sha and type(b)is dict and set(b)=={
             'schema','source_host','transaction_id','plan_digest','inventory_sha256','epoch','origin','issued_at','expires_at'},
             'INGRESS_BINDING_SCHEMA')
        need(type(b['schema'])is int and b['schema']==1 and b['source_host']==self.runtime['host'] and
             type(b['epoch'])is int and b['epoch']>0 and
             all(type(b[k])is str and re.fullmatch('[0-9a-f]{64}',b[k]) for k in ('plan_digest','inventory_sha256')) and
             all(type(b[k])is str and re.fullmatch('[A-Za-z0-9_-]{1,80}',b[k]) for k in ('transaction_id','origin')) and
             type(b['issued_at']) is type(b['expires_at']) is int and
             b['issued_at']<=time.time()<b['expires_at']<=b['issued_at']+7200,
             'INGRESS_ORIGINAL_LEASE')
        need(type(self.bootstrap_sha)is str and re.fullmatch('[0-9a-f]{64}',self.bootstrap_sha), 'BOOTSTRAP_PROOF_REQUIRED')
        need(self.authorize(mode,b,self.runtime) is True and self.check_fd() is True, 'ORIGINAL_INGRESS_ADMISSION')
        need(type(self.fd)is int,'ORIGINAL_SEAL_FD_REQUIRED')
        fs=os.fstat(self.fd);flags=fcntl.fcntl(self.fd,fcntl.F_GETFL)
        identity=(fs.st_dev,fs.st_ino)
        need(stat.S_ISREG(fs.st_mode) and fs.st_nlink==1 and fs.st_uid==os.geteuid() and
             stat.S_IMODE(fs.st_mode)==0o600 and fs.st_size<=16384 and
             flags & os.O_ACCMODE==os.O_RDWR and not flags & os.O_APPEND and
             getattr(self,'identity',identity)==identity, 'ORIGINAL_SEAL_FD_BINDING')
        return identity

    def _refresh(self):
        self._bound('query')
        before=os.fstat(self.fd);raw=os.pread(self.fd,16385,0);after=os.fstat(self.fd)
        need((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
             (after.st_size,after.st_mtime_ns,after.st_ctime_ns) and len(raw)==before.st_size,
             'SEAL_RECORD_CHANGED')
        if not raw:
            need(self.record is None and not self.sealed, 'SEAL_RECORD_REMOVED_PRESERVE')
            return
        # Any bytes close intake, including a partial record. Never reset them.
        self.sealed=True
        try:
            record=json.loads(raw)
            need(type(record)is dict and set(record)=={'action','binding','runtime_identity','bootstrap_sha256','observed_at'} and
                 encode(record)==raw and record['action']=='PR99_APPLICATION_INTAKE_SEAL_V1' and
                 record['binding']==self.binding and record['bootstrap_sha256']==self.bootstrap_sha and
                 type(record['observed_at'])is int and self.binding['issued_at']<=record['observed_at']<=time.time(),
                 'FOREIGN_OR_PARTIAL_SEAL_PRESERVE')
            identity=record['runtime_identity']
            need(type(identity)is dict and set(identity)==set(self.runtime) and identity['host']==self.runtime['host'] and
                 type(identity['pid']) is type(identity['start_ticks']) is int and
                 identity['pid']>0 and identity['start_ticks']>=0 and type(identity['boot_sha256'])is str and
                 re.fullmatch('[0-9a-f]{64}',identity['boot_sha256']) and type(identity['gate_id'])is str and
                 re.fullmatch('[0-9a-f]{32}',identity['gate_id']), 'SEAL_PROCESS_IDENTITY')
            need(self.record is None or record==self.record, 'SEAL_RECORD_REPLACED_PRESERVE')
        except (ValueError,UnicodeError,IngressHold):
            self.broken=True
            raise IngressHold('FOREIGN_OR_PARTIAL_SEAL_PRESERVE') from None
        self.record=record;self.prior_runtime=identity!=self.runtime

    def _new(self, kind, token):
        self._bound('work');self._refresh()
        need(not self.sealed and not self.broken,'INTAKE_SEALED_NO_NEW_JOB')
        need(len(self.tickets)<self.capacity,'INGRESS_CAPACITY')
        need(type(token)is str and re.fullmatch('[A-Za-z0-9_-]{1,100}',token),'ORIGINAL_JOB_ID_REQUIRED')
        need(token not in self.seen,'ORIGINAL_JOB_ALREADY_ACCEPTED_NO_REPLAY')
        need(len(self.seen)<65536,'ORIGINAL_JOB_HISTORY_BOUND')
        self.tickets[token]=kind;self.seen.add(token)
        return token

    def submit(self, original_job_id, payload):
        """Accept before enqueue; no payloads or errors are written to evidence."""
        with self.mutex:
            token=self._new('QUEUED',original_job_id)
            try:self.jobs.put_nowait((token,payload))
            except queue.Full:
                del self.tickets[token];self.seen.remove(token);raise IngressHold('INGRESS_CAPACITY') from None
            except BaseException:
                self.tickets[token]='UNKNOWN';self.mutex.notify_all();raise
            return token

    def process_one(self, handler):
        """Run an accepted queued job once. An exception is UNKNOWN, never retry."""
        need(callable(handler),'JOB_HANDLER_REQUIRED')
        with self.mutex:
            self._bound('work')
            token,payload=self.jobs.get_nowait()
            need(self.tickets.get(token)=='QUEUED','QUEUE_MEMBERSHIP_UNKNOWN')
            self.tickets[token]='ACTIVE_QUEUED'
        try:result=handler(payload)
        except BaseException:
            with self.mutex:self.tickets[token]='UNKNOWN_QUEUED';self.mutex.notify_all()
            raise
        with self.mutex:
            try:
                self._bound('work');self.jobs.task_done();del self.tickets[token]
            except BaseException:
                self.tickets[token]='UNKNOWN_QUEUED';raise
            finally:self.mutex.notify_all()
        return result

    def run_sync(self, original_job_id, handler, *args, **kwargs):
        """Cover synchronous writes until the application's handler returns.

        The handler must return ONLY after its transaction is committed/rolled
        back and no detached writer remains. Authority must verify that wiring.
        """
        need(callable(handler),'JOB_HANDLER_REQUIRED')
        with self.mutex:token=self._new('ACTIVE_SYNC',original_job_id)
        try:result=handler(*args,**kwargs)
        except BaseException:
            with self.mutex:self.tickets[token]='UNKNOWN_SYNC';self.mutex.notify_all()
            raise
        with self.mutex:
            try:
                self._bound('work');del self.tickets[token]
            except BaseException:
                self.tickets[token]='UNKNOWN_SYNC';raise
            finally:self.mutex.notify_all()
        return result

    def seal(self):
        with self.mutex:
            self._bound('seal');self._refresh()
            if self.sealed:return self._status()
            need(self.bootstrap(self.binding,self.runtime,self.bootstrap_sha) is True,'STARTUP_RECONCILIATION_UNPROVEN')
            record={'action':'PR99_APPLICATION_INTAKE_SEAL_V1','binding':self.binding,
                    'runtime_identity':self.runtime,'bootstrap_sha256':self.bootstrap_sha,'observed_at':int(time.time())}
            raw=encode(record)
            # Closing admission and tracking accepted work share the same mutex.
            # Failure after this line stays closed; it cannot reopen or truncate.
            self.sealed=True
            try:
                need(os.fstat(self.fd).st_size==0 and len(raw)<=16384,'SEAL_OUTPUT_NOT_EMPTY')
                written=os.pwrite(self.fd,raw,0);os.fsync(self.fd)
                need(written==len(raw) and os.pread(self.fd,16385,0)==raw,'PARTIAL_SEAL_PRESERVE')
                self.record=record;self._refresh()
            except BaseException:
                self.broken=True;raise
            self.mutex.notify_all()
            return self._status()

    def _status(self):
        self._refresh()
        need(not self.broken,'PARTIAL_SEAL_UNKNOWN')
        queued=sum(v=='QUEUED' for v in self.tickets.values())
        queued_unfinished=sum(v in ('QUEUED','ACTIVE_QUEUED','UNKNOWN_QUEUED') for v in self.tickets.values())
        with self.jobs.mutex:
            items=list(self.jobs.queue)
            need(len(items)==queued and self.jobs.unfinished_tasks==queued_unfinished and
                 all(type(item)is tuple and len(item)==2 for item in items) and
                 {item[0] for item in items}=={token for token,state in self.tickets.items() if state=='QUEUED'},
                 'UNTRACKED_QUEUE_WORK')
        unknown=sum(v.startswith('UNKNOWN') for v in self.tickets.values())
        prior=self.prior_runtime
        status=('UNKNOWN_PRIOR_PROCESS' if prior else 'OPEN' if not self.sealed else
                'UNKNOWN' if unknown else 'WAITING' if self.tickets else 'DRAINED')
        if status=='DRAINED':
            need(self.bootstrap(self.binding,self.runtime,self.bootstrap_sha) is True,'STARTUP_RECONCILIATION_UNPROVEN')
        return {'origin':self.binding['origin'],'runtime_identity':dict(self.runtime),
                'admission_sealed':self.sealed,'pending':None if prior else len(self.tickets),
                'unknown':None if prior else unknown,'status':status,
                'seal_sha256':None if self.record is None else digest(self.record)}

    def query(self):
        with self.mutex:return self._status()

    def wait_drained(self, timeout):
        need(type(timeout)in (int,float) and 0<=timeout<=60,'DRAIN_WAIT_BOUND')
        deadline=time.monotonic()+timeout
        with self.mutex:
            while True:
                value=self._status()
                if value['status'] in ('DRAINED','UNKNOWN','UNKNOWN_PRIOR_PROCESS','OPEN'):return value
                left=deadline-time.monotonic()
                if left<=0:return value
                self.mutex.wait(min(left,1))

    def reconcile_unknown(self, token, verify_original_outcome):
        """Account a terminal original outcome; never invoke a handler again."""
        with self.mutex:
            self._bound('reconcile');self._refresh()
            state=self.tickets.get(token)
            need(type(state)is str and state.startswith('UNKNOWN') and callable(verify_original_outcome),
                 'UNKNOWN_ORIGINAL_JOB_REQUIRED')
            value=verify_original_outcome(self.binding,self.runtime,token)
            need(type(value)is dict and set(value)=={'outcome','proof_sha256'} and
                 value['outcome'] in ('COMMITTED','ABORTED_WITH_NO_EFFECT') and type(value['proof_sha256'])is str and
                 re.fullmatch('[0-9a-f]{64}',value['proof_sha256']), 'ORIGINAL_JOB_OUTCOME_UNPROVEN')
            need(state!='UNKNOWN','AMBIGUOUS_QUEUE_ADMISSION_PRESERVED')
            if state=='UNKNOWN_QUEUED':self.jobs.task_done()
            del self.tickets[token];self.mutex.notify_all()
            return self._status()
