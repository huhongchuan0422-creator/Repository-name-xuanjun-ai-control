"""Exact source data fence provider for an already admitted original controller.

No CLI, discovery, permit, lock or alternate PathGuard. The original admitted
material guard, complete catalogue and independently verified drain record are
mandatory. Runtime masks plus kernel immutable flags are checked, not inferred
from an empty fd sample. No unmask, flag clearing, rollback or retry is offered.
"""
from array import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time

from catalogue_binding import bind_catalogue, digest

IMMUTABLE = 0x10
GETFLAGS = (2 << 30) | (struct.calcsize('l') << 16) | (ord('f') << 8) | 1
SETFLAGS = (1 << 30) | (struct.calcsize('l') << 16) | (ord('f') << 8) | 2
RETAINED = re.compile(r'finance|billing|weekly|owner-commercial-ledger|provider-neutral|windows-interaction|morelogin|novel|yibi', re.I)


class FenceHold(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise FenceHold(code)


class LinuxFenceBackend:
    """Actual fixed systemd operations and FS_IOC_* on original guarded fds.

    Instantiation is inert. No live invocation is bundled. cgroup_bindings map
    exact original unit names to admitted existing cgroup directory fds. A missing
    cgroup is not silently replaced by a different directory or process scan.
    """
    def __init__(self, original_guard, cgroup_bindings, binding_check):
        need(sys.platform == 'linux' and callable(binding_check) and
             all(callable(getattr(original_guard,n,None)) for n in ('check','file_fd','directory_fd')),
             'ADMITTED_ORIGINAL_GUARD_REQUIRED')
        self.guard = original_guard
        self.cgroups = cgroup_bindings
        self.bound = binding_check

    def _bound(self):
        need(self.bound() is True and self.guard.check() is True, 'ORIGINAL_FENCE_BINDING_REQUIRED')

    def _ctl(self, action, unit):
        self._bound()
        need(type(unit) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,179}\.(service|timer|socket|path)',unit)
             and not RETAINED.search(unit), 'RETAINED_OR_INVALID_UNIT')
        arguments = {'mask':['mask','--runtime','--',unit], 'stop':['stop','--',unit],
                     'show':['show',unit,'--property=ActiveState,MainPID,ControlPID,ControlGroup,UnitFileState','--no-pager']}
        need(action in arguments, 'SYSTEMD_ACTION')
        result = subprocess.run(['/usr/bin/systemctl']+arguments[action],stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=20,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
        need(result.returncode == 0 and len(result.stdout) <= 32768, 'SYSTEMD_EFFECT_OR_STATE_UNKNOWN')
        self._bound()
        return result.stdout.decode('utf-8','strict')

    def mask(self, unit):
        self._ctl('mask',unit)

    def stop(self, unit):
        self._ctl('stop',unit)

    def stopped_and_masked(self, unit):
        values = dict(line.split('=',1) for line in self._ctl('show',unit).splitlines() if '=' in line)
        if values.get('MainPID') != '0' or values.get('ControlPID') != '0' or values.get('ActiveState') not in ('inactive','failed') or values.get('UnitFileState') not in ('masked','masked-runtime'):
            return False
        scope = self.cgroups.get(unit)
        need(type(scope) is dict and set(scope) == {'control_group','fds'} and type(scope['fds']) is list and (scope['fds'] or values.get('ControlGroup') == ''),
             'ADMITTED_CGROUP_BINDING_REQUIRED')
        current = values.get('ControlGroup')
        need(current in ('',scope['control_group']), 'UNIT_CGROUP_DRIFT')
        for descriptor in scope['fds']:
            need(type(descriptor) is int and stat.S_ISDIR(os.fstat(descriptor).st_mode), 'CGROUP_DESCRIPTOR')
            try:
                fd = os.open('cgroup.procs',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=descriptor)
            except FileNotFoundError:
                # A removed cgroup is accepted only after PID1 reports no group.
                need(current == '', 'CGROUP_REMOVAL_UNPROVEN')
                continue
            try:
                raw = os.read(fd,65537)
                need(len(raw) <= 65536, 'CGROUP_PROCESS_BOUND')
                if raw.strip():
                    return False
            finally:
                os.close(fd)
        self._bound()
        return True

    def object_fd(self, obj):
        self._bound()
        fd = os.dup(self.guard.directory_fd(Path(obj['path']))) if obj['kind'] == 'DIRECTORY' else self.guard.file_fd(Path(obj['path']))
        try:
            fs = os.fstat(fd)
            need((fs.st_dev,fs.st_ino,fs.st_uid) == (obj['device'],obj['inode'],obj['uid']) and
                 (stat.S_ISDIR(fs.st_mode) if obj['kind']=='DIRECTORY' else stat.S_ISREG(fs.st_mode) and fs.st_nlink==1),
                 'SOURCE_OBJECT_IDENTITY')
            self._bound()
            return fd
        except BaseException:
            os.close(fd)
            raise

    def get_flags(self, obj):
        fd = self.object_fd(obj)
        try:
            flags = array('l',[0]); fcntl.ioctl(fd,GETFLAGS,flags,True)
            return flags[0]
        finally:
            os.close(fd)

    def freeze(self, obj):
        fd = self.object_fd(obj)
        try:
            before = array('l',[0]); fcntl.ioctl(fd,GETFLAGS,before,True)
            need(before[0] == obj['original_flags'], 'SOURCE_FLAGS_DRIFT')
            flags = array('l',[before[0] | IMMUTABLE])
            fcntl.ioctl(fd,SETFLAGS,flags,False)
            os.fsync(fd)
            after = array('l',[0]); fcntl.ioctl(fd,GETFLAGS,after,True)
            need(after[0] == flags[0], 'KERNEL_FENCE_NOT_ESTABLISHED')
            self._bound()
        finally:
            os.close(fd)

    def exact_directory(self, obj, children):
        fd = self.object_fd(obj)
        try:
            actual = sorted(os.listdir(fd))
            expected = sorted(Path(child['path']).name for child in children)
            self._bound()
            return actual == expected
        finally:
            os.close(fd)


class SourceFence:
    def __init__(self, controller, catalogue, catalogue_digest, verify_catalogue,
                 backend, verify_drain, publish_original_proof):
        controller._bound('query')
        self.catalogue = bind_catalogue(catalogue,catalogue_digest,verify_catalogue)
        need(catalogue_digest == controller.binding['writer_inventory_sha256'] and callable(verify_drain) and callable(publish_original_proof),
             'FENCE_CATALOGUE_BINDING')
        self.controller = controller; self.backend = backend; self.drain = verify_drain
        self.inventory = catalogue_digest
        self.publish = publish_original_proof
        self.objects = [o for o in self.catalogue['objects'] if o['classification']=='COPY_FENCED']
        writers = {w for obj in self.objects for w in obj['writers']}
        self.units = sorted({o['unit'] for o in self.catalogue['origins'] if o['id'] in writers and o['unit'] is not None})
        need(self.units and all(not RETAINED.search(unit) for unit in self.units), 'RETAINED_WRITER_CONFLICT')

    def _drained(self):
        self.controller._bound('query')
        proof = self.drain(self.inventory,self.controller.binding['epoch'])
        need(type(proof) is dict and set(proof)=={'inventory_sha256','epoch','pending','unknown','proof_sha256'} and
             proof['inventory_sha256']==self.inventory and proof['epoch']==self.controller.binding['epoch'] and
             type(proof['pending']) is type(proof['unknown']) is int and proof['pending']==proof['unknown']==0 and
             type(proof['proof_sha256']) is str and re.fullmatch('[0-9a-f]{64}',proof['proof_sha256']),
             'TRUSTED_DRAIN_NOT_PROVEN')
        return proof['proof_sha256']

    def _complete(self):
        self.controller._bound('query')
        if not all(self.backend.stopped_and_masked(unit) for unit in self.units):
            return False
        by_id = {obj['id']:obj for obj in self.catalogue['objects']}
        for obj in self.objects:
            if self.backend.get_flags(obj) != obj['original_flags'] | IMMUTABLE:
                return False
            if obj['kind']=='DIRECTORY' and not self.backend.exact_directory(obj,[by_id[name] for name in obj['children']]):
                return False
        self._drained()
        return True

    def dispatch(self, request):
        need(request.get('stage')=='fence_source', 'EXACT_FENCE_STAGE')
        self.controller._bound('dispatch')
        # Trusted ingress/queue drain is a separate real input. An empty fd scan
        # cannot substitute for it. No stop is attempted if it is unknown.
        self._drained()
        for unit in self.units:
            self.backend.mask(unit)
        for unit in self.units:
            self.backend.stop(unit)
        need(all(self.backend.stopped_and_masked(unit) for unit in self.units), 'SOURCE_CONTROL_GROUP_NOT_EMPTY')
        by_id = {obj['id']:obj for obj in self.catalogue['objects']}
        # Validate complete membership before mutating any source data flags.
        for obj in self.objects:
            if obj['kind']=='DIRECTORY':
                need(self.backend.exact_directory(obj,[by_id[n] for n in obj['children']]),'SOURCE_MEMBERSHIP_DRIFT')
        for obj in sorted(self.objects,key=lambda o:(o['kind']=='DIRECTORY',-len(Path(o['path']).parts))):
            self.controller._bound('dispatch')
            self.backend.freeze(obj)
        need(self._complete(), 'SOURCE_FENCE_UNPROVEN_PRESERVE')
        return self._receipt(request)

    def _receipt(self, request, query_only=False):
        # A stage result binds evidence; it is not a free-standing signed final
        # proof. The original independent receipt publisher must persist/sign it.
        proof = {'action':'PR99_SOURCE_WRITER_FENCE_V1','source_host':self.catalogue['host'],
            'writer_inventory_sha256':self.inventory,'writer_epoch':self.controller.binding['epoch'],
            'writers_stopped':True,'inflight_drained':True,'unresolved_shared_writers':[],
            'kernel_fence':'IMMUTABLE_EVERY_COMPLETE_DATA_OBJECT','observed_at':int(time.time()),
            'drain_proof_sha256':self._drained()}
        self.controller._bound('query' if query_only else 'record')
        # The original publisher returns the durable proof (possibly already
        # present). Query never invents a missing proof or changes its timestamp.
        stored = self.publish(proof,query_only=query_only)
        need(type(stored)is dict and set(stored)==set(proof) and all(stored[k]==proof[k] for k in proof if k!='observed_at') and
             type(stored['observed_at'])is int and 0<stored['observed_at']<=proof['observed_at'],
             'ORIGINAL_DURABLE_FENCE_PROOF_REQUIRED')
        return {'request_digest':self.controller.m.digest(request),'operation_id':request['operation_id'],
                'stage':'fence_source','status':'SUCCEEDED','evidence':digest(stored)}

    def query(self, request):
        need(request.get('stage')=='fence_source', 'EXACT_FENCE_STAGE')
        need(self._complete(), 'PARTIAL_FENCE_UNKNOWN_NO_REPLAY')
        return self._receipt(request,query_only=True)
