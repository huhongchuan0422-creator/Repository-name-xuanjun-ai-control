"""Concrete bounded Linux unit/cgroup/process/DB-FD census, including ACTIVE.

No service start, socket connect, DB open, model call or notification. The exact
resource-section compiler is separate; this supplies actual census observations.
Unknown/missing/racing processes, mounts or permissions fail closed.
"""
import copy
import ctypes
import errno
import hashlib
import os
import re
import socket
import stat
import time

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
import reviewed_scanner as reviewed
from epoch7_command_runner import ExactCommandRunner
from epoch7_recovery_sequence import PHASES, BoundedDiagnostics
from epoch7_live_controls import UNIT_FIELDS, MAX_PROCESSES, MAX_FD_ROWS, MAX_CGROUP_FILES
from epoch7_host_phases import need, sha

PROC_MAX = 1048576
EXE_MAX = 268435456
TOTAL_EXE_MAX = 536870912
CGROUP_ROOT = '/sys/fs/cgroup/systemd/system.slice'
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os,'O_CLOEXEC',0)
D_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os,'O_CLOEXEC',0)
PF_KTHREAD = 0x00200000


class StableDirectory(object):
    """fdopendir/readdir avoids os.listdir(fd)'s transient duplicated own fd."""
    def __init__(self, fd):
        self.libc = ctypes.CDLL(None,use_errno=True)
        self.libc.fdopendir.argtypes=[ctypes.c_int]; self.libc.fdopendir.restype=ctypes.c_void_p
        self.libc.readdir.argtypes=[ctypes.c_void_p]; self.libc.readdir.restype=ctypes.c_void_p
        self.libc.rewinddir.argtypes=[ctypes.c_void_p]; self.libc.rewinddir.restype=None
        self.libc.closedir.argtypes=[ctypes.c_void_p]; self.libc.closedir.restype=ctypes.c_int
        self.fd=fd; self.stream=self.libc.fdopendir(fd)
        if not self.stream:
            error=ctypes.get_errno();os.close(fd);raise OSError(error,'FDOPENDIR_FAILED')
    def names(self, maximum):
        self.libc.rewinddir(self.stream);result=[]
        while True:
            ctypes.set_errno(0); pointer=self.libc.readdir(self.stream)
            if not pointer:
                error=ctypes.get_errno()
                if error:raise OSError(error,'READDIR_FAILED')
                break
            # Linux getdents64 dirent layout: inode8,offset8,reclen2,type1,name.
            length=ctypes.c_ushort.from_address(pointer+16).value
            need(20 <= length <= 4096,'DIRENT_RECORD_BOUND')
            raw=ctypes.string_at(pointer+19,length-19).split(b'\0',1)[0]
            need(raw and b'/' not in raw,'DIRENT_NAME')
            if raw in (b'.',b'..'):continue
            result.append(raw.decode('ascii','strict'));need(len(result)<=maximum,'DIRECTORY_ENTRY_BOUND')
        need(len(result)==len(set(result)),'DIRECTORY_DUPLICATE_ENTRY')
        return sorted(result)
    def close(self):
        if self.stream:
            stream,self.stream=self.stream,None
            need(self.libc.closedir(stream)==0,'DIRECTORY_CLOSE_UNKNOWN')


class LinuxProcessCensus(object):
    def __init__(self, context, authority, diagnostics, executable_check, database_identities,
                 manager_pin, retained_sidecar_pins, runner_factory=ExactCommandRunner):
        need(isinstance(diagnostics,BoundedDiagnostics) and callable(executable_check) and
             callable(runner_factory),'CENSUS_EXPLICIT_ADAPTERS')
        need(type(database_identities) is dict and set(database_identities)==set(snap.DATABASES),
             'CENSUS_EXACT_DATABASE_SET')
        for row in database_identities.values():
            need(type(row) is dict and set(row)=={'dev','ino'} and
                 type(row['dev']) is int and type(row['ino']) is int and row['ino']>0,'CENSUS_DATABASE_PINS')
        self.context,self.authority=copy.deepcopy(context),authority
        self.diagnostics,self.executable,self.factory=diagnostics,executable_check,runner_factory
        self.database_identities,self.manager_pin=copy.deepcopy(database_identities),copy.deepcopy(manager_pin)
        expected={p+s for p in snap.DATABASES if p!=d.DB for s in ('-wal','-shm','-journal')}
        need(type(retained_sidecar_pins) is dict and set(retained_sidecar_pins)==expected,'CENSUS_RETAINED_SIDECAR_PINS')
        self.retained_sidecars=copy.deepcopy(retained_sidecar_pins)
        self.deadline=None;self.guard_deadline=None;self.cache={};self.total_exe=0;self.phase=None
        self.scoped_units=set();self.process_meta={};self.last_executable={}

    def _check(self):
        self.authority.receipt()
        need(self.deadline is not None and time.monotonic()<self.deadline,'CENSUS_TOTAL_DEADLINE')

    def _start(self,context,phase):
        need(context==self.context and phase in PHASES,'CENSUS_EXACT_CONTEXT')
        need(os.geteuid()==0 and socket.gethostname().split('.')[0]==snap.HOST,'CENSUS_FIXED_HOST_ROOT')
        self.authority.receipt();self.deadline=min(time.monotonic()+30,self.guard_deadline if self.guard_deadline is not None else float('inf'));self.phase=phase
        self.cache={};self.total_exe=0;self.process_meta={};self.last_executable={}

    def _read(self,path,maximum):
        self._check();fd=os.open(path,FLAGS)
        try:
            before=os.fstat(fd);chunks=[];total=0
            need(stat.S_ISREG(before.st_mode),'CENSUS_REGULAR_FILE')
            while True:
                self._check();part=os.read(fd,min(65536,maximum+1-total))
                if not part:break
                total+=len(part);need(total<=maximum,'CENSUS_READ_BOUND');chunks.append(part)
            need(fs.stamp(os.fstat(fd))==fs.stamp(before),'CENSUS_READ_RACE')
            return b''.join(chunks)
        finally:os.close(fd)

    def verify_systemd_controller_mount(self):
        reviewed.validate_systemd_mountinfo(self._read('/proc/self/mountinfo',1048576))

    @staticmethod
    def bounded_file_inventory(*args,**kwargs):
        return reviewed.bounded_file_inventory(*args,**kwargs)

    @staticmethod
    def _parse_unit_blocks(output,units):
        need(type(output) is bytes and 0<len(output)<=65536,'CENSUS_UNIT_OUTPUT_BOUND')
        blocks=output.decode('utf-8','strict').strip().split('\n\n');result={}
        need(len(blocks)==len(units),'CENSUS_UNIT_BLOCK_COUNT')
        for block in blocks:
            rows={}
            for line in block.splitlines():
                need('=' in line,'CENSUS_UNIT_OUTPUT');key,value=line.split('=',1)
                need(key in UNIT_FIELDS and key not in rows,'CENSUS_UNIT_OUTPUT_KEYS');rows[key]=value
            unit=rows.get('Id');need(unit in units and unit not in result,'CENSUS_UNIT_OUTPUT_IDENTITY')
            for key in ('MainPID','ControlPID'):
                if key in rows:
                    need(re.fullmatch(r'0|[1-9][0-9]{0,9}',rows[key]),'CENSUS_UNIT_PID')
                    rows[key]=int(rows[key])
            required,optional=snap.unit_process_fields(unit)
            need((UNIT_FIELDS-snap.UNIT_PROCESS_FIELDS)|required <= set(rows) <= UNIT_FIELDS,
                 'CENSUS_EXACT_UNIT_PROPERTIES')
            snap.validate_unit_process_fields(unit,rows,pid_type=int)
            result[unit]=rows
        need(set(result)==set(units),'CENSUS_EXACT_UNIT_SET');return result

    def _show_units(self,units):
        self._check();need(type(units) in (tuple,list) and len(units)==len(set(units)) and
             set(units)<=snap.WRITER_UNITS and len(units)>0,'CENSUS_UNIT_SCOPE')
        need(self.executable('/usr/bin/systemctl') is True,'CENSUS_SYSTEMCTL_PIN')
        remaining=int(self.deadline-time.monotonic());need(remaining>=1,'CENSUS_QUERY_TIME')
        props=','.join(sorted(UNIT_FIELDS))
        spec={'phase':self.phase,'operation':'service_show',
            'argv':['/usr/bin/systemctl','show']+list(units)+['--property='+props],
            'cwd':'/','env':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},
            'timeout':min(5,remaining),'accepted_returncodes':[0]}
        output=self.factory({'show':spec},lambda:self._admitted(),self.diagnostics).run('show').stdout
        self._check();need(self.executable('/usr/bin/systemctl') is True,'CENSUS_SYSTEMCTL_AFTER_PIN')
        return self._parse_unit_blocks(output,units)

    def _unit_state(self,unit):return self._show_units((unit,))[unit]

    def _all_units(self):
        units=sorted(snap.WRITER_UNITS);before=self._show_units(units)
        first={unit:self._cgroups(unit) for unit in units};after=self._show_units(units)
        second={unit:self._cgroups(unit) for unit in units}
        need(before==after and first==second,'CENSUS_BATCH_UNIT_CGROUP_RACE')
        return {unit:{'before':before[unit],'after':after[unit],
            'cgroup_present':first[unit][0],'cgroups':first[unit][1]} for unit in units}

    def _admitted(self):self._check();return True

    def _cgroups(self,unit):
        self.verify_systemd_controller_mount()
        root=CGROUP_ROOT+'/'+unit;parts=root.strip('/').split('/');held=[];links=[]
        fd=os.open('/',D_FLAGS);held.append(fd)
        try:
            for index,part in enumerate(parts):
                self._check();info=os.fstat(fd)
                need(info.st_uid==0 and stat.S_ISDIR(info.st_mode),'CENSUS_CGROUP_ANCESTOR')
                try:child=os.open(part,D_FLAGS,dir_fd=fd)
                except FileNotFoundError:
                    need(index==len(parts)-1,'CENSUS_CGROUP_PARENT_MISSING')
                    names=os.listdir(fd);need(part not in names,'CENSUS_CGROUP_ABSENCE_RACE')
                    return False,{}
                before=os.stat(part,dir_fd=fd,follow_symlinks=False)
                need(fs.stamp(before)==fs.stamp(os.fstat(child)),'CENSUS_CGROUP_OPEN_RACE')
                links.append((fd,part,child,before));held.append(child);fd=child
            result={};count=[0]
            def walk(directory,path):
                self._check();before=os.fstat(directory);names=sorted(os.listdir(directory))
                need(before.st_uid==0 and not before.st_mode&0o022,'CENSUS_CGROUP_AUTHORITY')
                need('cgroup.procs' in names,'CENSUS_CGROUP_PROCS_REQUIRED')
                for name in names:
                    self._check();info=os.stat(name,dir_fd=directory,follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        child=os.open(name,D_FLAGS,dir_fd=directory)
                        try:walk(child,path+'/'+name)
                        finally:os.close(child)
                    elif name=='cgroup.procs':
                        count[0]+=1;need(count[0]<=MAX_CGROUP_FILES,'CENSUS_CGROUP_BOUND')
                        child=os.open(name,FLAGS,dir_fd=directory)
                        try:
                            raw=os.read(child,PROC_MAX+1);need(len(raw)<=PROC_MAX,'CENSUS_CGROUP_PID_BYTES')
                        finally:os.close(child)
                        lines=raw.decode('ascii').splitlines()
                        need(all(re.fullmatch(r'[1-9][0-9]{0,9}',v) for v in lines),'CENSUS_CGROUP_PIDS')
                        pids=[int(x) for x in lines];need(len(pids)==len(set(pids)),'CENSUS_CGROUP_DUPLICATE_PID')
                        result[path+'/cgroup.procs']=sorted(pids)
                    else:need(not stat.S_ISLNK(info.st_mode),'CENSUS_CGROUP_SYMLINK')
                need(sorted(os.listdir(directory))==names and fs.stamp(os.fstat(directory))==fs.stamp(before),
                     'CENSUS_CGROUP_TREE_RACE')
            walk(fd,root)
            for parent,name,child,before in links:
                need(fs.stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==fs.stamp(before) and
                     fs.stamp(os.fstat(child))==fs.stamp(before),'CENSUS_CGROUP_PATH_RACE')
            return True,result
        finally:
            for fd in reversed(held):os.close(fd)

    def _unit(self,unit):
        before=self._unit_state(unit);present,groups=self._cgroups(unit);after=self._unit_state(unit)
        # A second complete cgroup read catches additions/removals during show.
        second_present,second_groups=self._cgroups(unit)
        need(before==after and present==second_present and groups==second_groups,'CENSUS_UNIT_CGROUP_RACE')
        return {'before':before,'after':after,'cgroup_present':present,'cgroups':groups}

    def _executable(self,pid):
        path='/proc/%d/exe'%pid
        first=os.readlink(path);need(first.startswith('/') and not first.endswith(' (deleted)'),
                                     'CENSUS_EXECUTABLE_PATH')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_CLOEXEC',0))
        try:
            before=os.fstat(fd);key=fs.stamp(before)
            need(stat.S_ISREG(before.st_mode) and before.st_size<=EXE_MAX,'CENSUS_EXECUTABLE_BOUND')
            digest=self.cache.get(key)
            if digest is None:
                value=hashlib.sha256();count=0
                while True:
                    self._check();part=os.read(fd,65536)
                    if not part:break
                    count+=len(part);self.total_exe+=len(part)
                    need(count<=EXE_MAX and self.total_exe<=TOTAL_EXE_MAX,'CENSUS_EXECUTABLE_TOTAL_BOUND');value.update(part)
                need(count==before.st_size,'CENSUS_EXECUTABLE_SIZE');digest=value.hexdigest();self.cache[key]=digest
            need(fs.stamp(os.fstat(fd))==key and os.readlink(path)==first,'CENSUS_EXECUTABLE_RACE')
            self.last_executable[pid]=(before.st_dev,before.st_ino)
            return first,digest
        finally:os.close(fd)

    def _identity(self,pid,unit):
        base='/proc/%d/'%pid;raw=self._read(base+'stat',65536);end=raw.rfind(b')');fields=raw[end+2:].split()
        need(end>0 and len(fields)>=20,'CENSUS_PROC_STAT');start=int(fields[19]);flags=int(fields[6])
        scoped=unit in self.scoped_units
        parent=int(fields[1]);parent_before=None
        if scoped:
            need(parent>0,'CENSUS_SCOPED_PARENT_REQUIRED')
            parent_before=self._read('/proc/%d/stat'%parent,65536)
        status=self._read(base+'status',65536);values={}
        for line in status.splitlines():
            key,sep,value=line.partition(b':')
            if key in (b'Uid',b'Gid',b'Groups'):
                need(key not in values and sep and all(x.isdigit() for x in value.split()),'CENSUS_PROC_IDS')
                values[key]=[int(x) for x in value.split()]
        need(set(values)=={b'Uid',b'Gid',b'Groups'} and len(values[b'Uid'])==len(values[b'Gid'])==4,
             'CENSUS_PROC_ID_FIELDS')
        comm=self._read(base+'comm',256).rstrip(b'\n').decode('utf-8','strict')
        argv=self._read(base+'cmdline',1048576)
        kernel=bool(flags&PF_KTHREAD)
        if kernel:
            need(values[b'Uid']==[0]*4 and values[b'Gid']==[0]*4 and argv==b'', 'CENSUS_KERNEL_THREAD_IDENTITY')
            try:os.readlink(base+'exe')
            except FileNotFoundError:pass
            else:raise ValueError('EPOCH7_HOST_KERNEL_EXECUTABLE_UNEXPECTED')
            executable,digest=None,None
        else:executable,digest=self._executable(pid)
        after=self._read(base+'stat',65536);tail=after[after.rfind(b')')+2:].split()
        need(len(tail)>=20 and int(tail[19])==start and bool(int(tail[6])&PF_KTHREAD)==kernel,
             'CENSUS_PID_REUSE')
        if scoped:
            need(int(tail[1])==parent and len(argv)<=16384,'CENSUS_SCOPED_PARENT_OR_ARGV_RACE')
            parent_after=self._read('/proc/%d/stat'%parent,65536)
            first_parent=parent_before[parent_before.rfind(b')')+2:].split()
            last_parent=parent_after[parent_after.rfind(b')')+2:].split()
            need(len(first_parent)>=20 and len(last_parent)>=20 and first_parent[19]==last_parent[19],
                 'CENSUS_PARENT_REUSE')
            from epoch7_service_roles import normalized_title
            try:title=normalized_title(argv)
            except ValueError:title=None
            dev,ino=self.last_executable[pid]
            self.process_meta[pid]={'ppid':parent,'parent_starttime':int(first_parent[19]),
                'executable_dev':dev,'executable_ino':ino,'cmdline_title':title,'cmdline_size':len(argv)}
        return {'pid':pid,'starttime':start,'uids':values[b'Uid'],'gids':values[b'Gid'],
            'groups':sorted(values[b'Groups']),'comm':comm,'executable':executable,
            'executable_sha256':digest,'argv_sha256':sha(argv),'unit':unit,'kernel_thread':kernel}

    def _pids(self):
        self._check();names=os.listdir('/proc');pids=sorted(int(x) for x in names if x.isdigit())
        need(len(pids)<=MAX_PROCESSES,'CENSUS_PID_BOUND');return pids

    def _database_paths(self):
        files={};identities={}
        for path,pin in self.database_identities.items():
            for suffix in ('','-wal','-shm','-journal'):
                storage=path+suffix
                try:before=os.lstat(storage)
                except FileNotFoundError:
                    need(bool(suffix),'CENSUS_BASE_DATABASE_MISSING')
                    if path!=d.DB:need(self.retained_sidecars[storage] is None,'CENSUS_RETAINED_SIDECAR_MISSING')
                    files[storage]=None;continue
                need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'CENSUS_DATABASE_FILE_AUTHORITY')
                row={'kind':'REGULAR','dev':before.st_dev,'ino':before.st_ino,'uid':before.st_uid,
                     'gid':before.st_gid,'mode':stat.S_IMODE(before.st_mode),'nlink':before.st_nlink}
                if not suffix:
                    need({'dev':before.st_dev,'ino':before.st_ino}==pin,'CENSUS_DATABASE_IDENTITY_CHANGED')
                elif path!=d.DB:
                    raw=self._read(storage,1048576)
                    need(fs.stamp(before)==fs.stamp(os.lstat(storage)),'CENSUS_RETAINED_SIDECAR_READ_RACE')
                    row.update(size=before.st_size,mtime_ns=before.st_mtime_ns,ctime_ns=before.st_ctime_ns,sha256=sha(raw))
                    need(row==self.retained_sidecars[storage],'CENSUS_RETAINED_SIDECAR_CHANGED')
                else:
                    need((row['uid'],row['gid'],row['mode'])==(1003,1006,0o600),
                         'CENSUS_UNREVIEWED_DATABASE_SIDECAR')
                need((before.st_dev,before.st_ino) not in identities,'CENSUS_DATABASE_FILE_ALIAS')
                files[storage]=row;identities[(before.st_dev,before.st_ino)]=(path,storage)
        return files,identities

    def _fds_once(self,pid,identities,observed):
        self._check();base='/proc/%d/fd'%pid
        stream=StableDirectory(os.open(base,D_FLAGS));result=[]
        try:
            first=stream.names(MAX_FD_ROWS)
            for name in first:
                self._check();need(name.isdigit(),'CENSUS_FD_NAME')
                info=os.stat(name,dir_fd=stream.fd,follow_symlinks=True)
                matched=identities.get((info.st_dev,info.st_ino))
                try:target=os.readlink(name,dir_fd=stream.fd)
                except FileNotFoundError:
                    need(matched is None,'CENSUS_WATCHED_FD_DISAPPEARED')
                    raise
                known_paths={base+suffix for base in self.database_identities for suffix in ('','-wal','-shm','-journal')}
                linked=target[:-10] if target.endswith(' (deleted)') else target
                matched=identities.get((info.st_dev,info.st_ino))
                if linked in known_paths:
                    need(matched is not None and not target.endswith(' (deleted)') and matched[1]==linked,
                         'CENSUS_UNLINKED_OR_REPLACED_DATABASE_FD')
                if matched is not None:
                    path,storage=matched
                    def flags():
                        try:raw=self._read('/proc/%d/fdinfo/%s'%(pid,name),65536)
                        except FileNotFoundError:raise ValueError('EPOCH7_HOST_CENSUS_WATCHED_FD_DISAPPEARED') from None
                        rows=[line.split(b':',1)[1].strip() for line in raw.splitlines() if line.startswith(b'flags:')]
                        need(len(rows)==1 and re.fullmatch(br'[0-7]{1,16}',rows[0]),'CENSUS_FD_FLAGS')
                        return int(rows[0],8)
                    value=flags()
                    try:again=os.stat(name,dir_fd=stream.fd,follow_symlinks=True)
                    except FileNotFoundError:raise ValueError('EPOCH7_HOST_CENSUS_WATCHED_FD_DISAPPEARED') from None
                    need((again.st_dev,again.st_ino)==(info.st_dev,info.st_ino) and flags()==value,'CENSUS_FD_IDENTITY_RACE')
                    row={'pid':pid,'fd':int(name),'path':path,'storage_path':storage,'dev':info.st_dev,'ino':info.st_ino,'flags':value}
                    result.append(row);observed[d.digest(row)]=row
                    need(len(observed)<=MAX_FD_ROWS,'CENSUS_CUMULATIVE_DATABASE_FD_BOUND')
            need(stream.names(MAX_FD_ROWS)==first,'CENSUS_FD_LIST_RACE')
            return result,len(first)
        finally:stream.close()

    def _fds(self,pid,identities):
        observed={}
        first=self._read('/proc/%d/stat'%pid,65536)
        fields=first[first.rfind(b')')+2:].split()
        need(len(fields)>=20,'CENSUS_FD_PROCESS_START');started=int(fields[19])
        while True:
            self._check()
            try:
                rows,count=self._fds_once(pid,identities,observed)
                return list(observed.values()),count
            except FileNotFoundError:
                # Only retry a descriptor that closed while its SAME process
                # remains readable. Vanished/unreadable PID is never skipped.
                current=self._read('/proc/%d/stat'%pid,65536)
                tail=current[current.rfind(b')')+2:].split()
                need(len(tail)>=20 and int(tail[19])==started,'CENSUS_FD_PID_REUSE')
            except ValueError as error:
                if str(error)!='EPOCH7_HOST_CENSUS_FD_LIST_RACE':raise
                current=self._read('/proc/%d/stat'%pid,65536)
                tail=current[current.rfind(b')')+2:].split()
                need(len(tail)>=20 and int(tail[19])==started,'CENSUS_FD_PID_REUSE')

    def _manager(self):
        identity=self._identity(1,None)
        boot=self._read('/proc/sys/kernel/random/boot_id',128).decode('ascii').strip()
        channels={}
        for path in ('/run/systemd/private','/run/dbus/system_bus_socket'):
            info=os.lstat(path)
            need(stat.S_ISSOCK(info.st_mode) and (info.st_uid,info.st_gid)==(0,0),'CENSUS_MANAGER_CHANNEL')
            channels[path]=fs.metadata(info)
        result={'pid':1,'uids':identity['uids'],'starttime':identity['starttime'],'boot_id':boot,
                'executable':identity['executable'],'executable_sha256':identity['executable_sha256'],
                'channels_sha256':d.digest(channels)}
        need(result==self.manager_pin,'CENSUS_MANAGER_PIN_CHANGED')
        return result

    def processes(self,context,phase,boundary):
        self._start(context,phase);self.verify_systemd_controller_mount()
        manager=self._manager();units=self._all_units();memberships={}
        for unit,row in units.items():
            for pids in row['cgroups'].values():
                for pid in pids:
                    need(pid not in memberships,'CENSUS_MULTIPLE_CGROUP_UNITS');memberships[pid]=unit
        before=self._pids();db_files,db_before=self._database_paths();rows={};db_fds=[];count=0;scoped_meta={}
        for pid in before:
            first=self._identity(pid,memberships.get(pid));first_meta=copy.deepcopy(self.process_meta.get(pid))
            fds,total=self._fds(pid,db_before);count+=total;need(count<=MAX_FD_ROWS,'CENSUS_FD_TOTAL_BOUND')
            last=self._identity(pid,memberships.get(pid))
            if first_meta is not None:
                last_meta=copy.deepcopy(self.process_meta.get(pid));need(first_meta==last_meta,'CENSUS_ANCESTRY_RACE')
                scoped_meta[str(pid)]={'before':first_meta,'after':last_meta}
            need(first==last,'CENSUS_PROCESS_IDENTITY_RACE');rows[str(pid)]={'before':first,'after':last};db_fds.extend(fds)
        after=self._pids();need(before==after and self._database_paths()==(db_files,db_before),'CENSUS_PROCESS_OR_DATABASE_RACE')
        # Reobserve every unit/cgroup after the global /proc scan.
        need(self._all_units()==units,'CENSUS_MEMBERSHIP_AFTER_SCAN_CHANGED')
        manager_after=self._manager();self.verify_systemd_controller_mount();self._check()
        self.scoped_meta=scoped_meta
        return {'manager_before':manager,'manager_after':manager_after,'units':units,'pids_before':before,
                'pids_after':after,'processes':rows,'database_fds':db_fds,'database_files':db_files,'observer_pid':os.getpid()}

    def unit(self,context,operation,unit):
        need(operation in ('observe_stopped_before','observe_stopped_after'),'CENSUS_CLEANUP_OBSERVATION')
        self._start(context,'activate_new_services');return self._unit(unit)


class BoundedRetainedTLS(object):
    """Reuse collector TLS fingerprint/certificate checks with exact command IO."""
    def __init__(self,policy,authority,diagnostics,executable_check):
        from snapshot_io import LocalReadOnlyIO
        owner=self
        class TLSReadOnlyIO(LocalReadOnlyIO):
            def check_locks(self):
                owner.authority.receipt()
                need(owner.deadline is not None and time.monotonic()<owner.deadline,'TLS_SCAN_TOTAL_DEADLINE')
            def command(self,label,args):return owner.command(label,args)
        self.policy=copy.deepcopy(policy);self.authority=authority;self.diagnostics=diagnostics
        self.executable=executable_check;self.deadline=None;self.guard_deadline=None
        self.io=TLSReadOnlyIO(self.policy,{})

    def command(self,label,args):
        self.io.check_locks();need(label=='openssl','TLS_EXACT_QUERY_TOOL')
        domain='uk.wenwenwenyiyiyi.work'
        cert=os.path.realpath(snap.TLS+'/config/live/'+domain+'/fullchain.pem')
        key=os.path.realpath(snap.TLS+'/config/live/'+domain+'/privkey.pem')
        archive=snap.TLS+'/config/archive/'+domain+'/'
        need(cert.startswith(archive) and key.startswith(archive),'TLS_QUERY_LINEAGE')
        allowed=(['x509','-in',cert,'-noout','-checkhost',domain],
            ['x509','-in',cert,'-noout','-checkend','86400'],
            ['x509','-in',cert,'-pubkey','-noout'],['pkey','-in',key,'-pubout'],
            ['x509','-in',cert,'-outform','DER'])
        need(args in allowed,'TLS_PUBLIC_QUERY_ONLY')
        binary=self.policy['executables']['openssl']['path']
        need(self.executable(binary) is True,'TLS_OPENSSL_PIN')
        remaining=int(self.deadline-time.monotonic());need(remaining>=1,'TLS_QUERY_DEADLINE')
        scope=self.diagnostics.scope
        phase=scope[len('phase:'):] if type(scope) is str and scope.startswith('phase:') else 'activate_new_services'
        need(phase in PHASES,'TLS_DIAGNOSTIC_PHASE')
        contract={'tls':{'phase':phase,'operation':'tls_inspect',
            'argv':[binary]+list(args),'cwd':'/','env':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},
            'timeout':min(5,remaining),'accepted_returncodes':[0]}}
        def admitted():self.io.check_locks();return True
        result=ExactCommandRunner(contract,admitted,self.diagnostics).run('tls')
        need(self.executable(binary) is True,'TLS_OPENSSL_AFTER_PIN');return result.stdout

    def contents(self):
        self.deadline=min(time.monotonic()+30,self.guard_deadline if self.guard_deadline is not None else float('inf'))
        result=self.io.tls(self.policy)
        need(result['domain_verified'] is True and result['key_pair_verified'] is True and
             result['acme_calls']==0,'TLS_CERTIFICATE_OBSERVATION')
        return {key:result[key] for key in ('certificate_sha256','tree_fingerprint_sha256')}


def immutable_snapshot(snapshot):
    """Only a transient exclusion-proof digest is omitted, never its policy."""
    value = copy.deepcopy(snapshot)
    d.validate_snapshot(value, d.digest(value))
    value['writer_exclusion'].pop('evidence_sha256')
    return value


class Epoch7HostObserver(object):
    """Concrete composition for FiniteLiveControls' complete observation API."""
    def __init__(self,context,policy,policy_sha256,install_lock,activation_store,
                 authority,resources,census,tls,reviewed_snapshot):
        from epoch7_host_phases import ExistingInstallLock,BoundedActivationStore
        from epoch7_resource_observer import CheckpointResources
        need(isinstance(install_lock,ExistingInstallLock) and isinstance(activation_store,BoundedActivationStore)
             and isinstance(resources,CheckpointResources) and isinstance(census,LinuxProcessCensus)
             and isinstance(tls,BoundedRetainedTLS),'HOST_OBSERVER_CONCRETE_COMPONENTS')
        snap.validate_policy(policy);d.hash_value(policy_sha256)
        need(d.digest(policy)==policy_sha256,'HOST_OBSERVER_POLICY_HASH')
        self.context,self.policy=copy.deepcopy(context),copy.deepcopy(policy)
        self.lock,self.activation,self.authority=install_lock,activation_store,authority
        self.resource_reader,self.census,self.tls=resources,census,tls
        self.reviewed_snapshot=d.validate_snapshot(reviewed_snapshot,context['snapshot_sha256'])
        self.policy_sha=policy_sha256;self.bound_plan=None;self.live_contract=None;self.guard_deadline=None
        self.driver_gate=None;self.runtime=None;self.outer_io=None
        from epoch7_quiet_startup import BoundedQuietStartup
        self.quiet=BoundedQuietStartup(policy,authority,census)

    def bind_plan(self,plan):
        need(self.bound_plan is None and type(plan) is dict and 'resource_observer' in plan and
             'live_controls' in plan,'HOST_OBSERVER_REVIEWED_PLAN_REQUIRED')
        wanted={'views_sha256':self.resource_reader.digest,
                'directories_sha256':d.digest(self.resource_reader.reader.directories),
                'snapshot_policy_sha256':self.policy_sha}
        need(d.same(plan['resource_observer'],wanted),'HOST_OBSERVER_EXACT_PLAN_BINDING')
        contract=plan['live_controls']
        need(contract['manager']==self.census.manager_pin and contract['database_identities']==self.census.database_identities and
             contract['retained_sidecar_pins']==self.census.retained_sidecars,
             'HOST_OBSERVER_PROCESS_PIN_BINDING')
        for index,view in enumerate(self.resource_reader.views):
            need({name:d.digest(rows) for name,rows in view.items()}==contract['checkpoints'][index]['resources'],
                 'HOST_OBSERVER_CHECKPOINT_VIEW_BINDING')
        if any('quiet_startup' in block for block in contract.get('service_role_contract',{}).get('units',{}).values()):
            self.quiet.bind_resource_views(self.resource_reader.views)
        self.census.scoped_units=set(contract.get('service_role_contract',{}).get('units',{}))
        self.live_contract=copy.deepcopy(contract);self.bound_plan=d.digest({'observer':wanted,'live':contract})
        return True

    def begin_guard(self,deadline):
        need(self.bound_plan is not None,'HOST_OBSERVER_PLAN_NOT_BOUND')
        need(type(deadline) in (int,float) and time.monotonic()<deadline<=time.monotonic()+30.1,
             'HOST_OBSERVER_FINITE_GUARD_DEADLINE')
        self.guard_deadline=deadline
        self.census.guard_deadline=self.guard_deadline
        self.resource_reader.reader.guard_deadline=self.guard_deadline
        self.tls.guard_deadline=self.guard_deadline

    def _bound(self):
        wanted={'views_sha256':self.resource_reader.digest,
                'directories_sha256':d.digest(self.resource_reader.reader.directories),
                'snapshot_policy_sha256':self.policy_sha}
        need(self.bound_plan is not None and d.digest({'observer':wanted,'live':self.live_contract})==self.bound_plan,
             'HOST_OBSERVER_PLAN_MUTATED')

    def _preflight_command(self,io,label,args):
        io.check_locks();self.authority.receipt()
        if label == 'openssl':
            self.tls.deadline = self.guard_deadline
            return self.tls.command(label,args)
        if label == 'git':
            from snapshot_io import CONTROL_GIT_ARGS,CONTROL_GIT_ENV
            need(args==CONTROL_GIT_ARGS,'PREFLIGHT_EXACT_GIT_QUERY')
            operation='stage_source_verify'
        elif label == 'rpm':
            packages = snap.decode(io.read(snap.TRANSACTION+'/rpm-prerequisites.json')[0])['packages']
            need(type(args) is list and len(args)==4 and args[:3]==
                 ['-q','--qf','%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}'] and
                 args[3] in {row['name'] for row in packages}, 'PREFLIGHT_EXACT_RPM_QUERY')
            operation='retained_rpm_query'
        else:
            props=('Id','LoadState','ActiveState','SubState','MainPID','ControlPID','ControlGroup',
                   'UnitFileState','ConditionResult','FragmentPath','DropInPaths','NeedDaemonReload')
            need(label=='systemctl' and (args==['list-unit-files','--no-legend','--no-pager'] or
                 type(args) is list and len(args)==3 and args[0]=='show' and args[1] in snap.WRITER_UNITS and
                 args[2]=='--property='+','.join(props)), 'PREFLIGHT_EXACT_SYSTEMCTL_QUERY')
            operation='service_show'
        binary=self.policy['executables'][label]['path']
        need(self.census.executable(binary) is True,'PREFLIGHT_BINARY_PIN')
        remaining=int(self.guard_deadline-time.monotonic());need(remaining>=1,'PREFLIGHT_COMMAND_DEADLINE')
        spec={'phase':'stage_exact_release','operation':operation,'argv':[binary]+args,'cwd':'/',
              'env':(dict(CONTROL_GIT_ENV) if label=='git' else {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}),'timeout':min(5,remaining),
              'accepted_returncodes':[0]}
        def admitted():io.check_locks();self.authority.receipt();return True
        result=ExactCommandRunner({'preflight':spec},admitted,self.census.diagnostics).run('preflight')
        need(self.census.executable(binary) is True,'PREFLIGHT_BINARY_AFTER_PIN')
        return result.stdout

    def preflight(self,context):
        from snapshot_io import LocalReadOnlyIO,stamp
        self._bound()
        need(context==self.context and self.lock.held() is True and d.digest(self.policy)==self.policy_sha,
             'HOST_PREFLIGHT_CONTEXT_AND_LOCK')
        activation_fd=self.activation._locked()
        try:
            locks={snap.INSTALL_LOCK:(self.lock.fd,stamp(os.fstat(self.lock.fd))),
                   snap.ACTIVATION_LOCK:(activation_fd,stamp(os.fstat(activation_fd)))}
            owner=self
            class AdmissionReadOnlyIO(LocalReadOnlyIO):
                def command(self,label,args):return owner._preflight_command(self,label,args)
            io=AdmissionReadOnlyIO(self.policy,locks)
            need(self.guard_deadline is not None,'HOST_PREFLIGHT_GUARD_BUDGET')
            io.deadline=min(io.deadline,self.guard_deadline)
            snapshot,evidence=snap.collect(self.policy,io)
            snap.validate_writer_comparison(evidence.get('writer_observation_comparison'),evidence['writers'])
            need(d.digest(evidence['writers'])==snapshot['writer_exclusion']['evidence_sha256'],
                 'HOST_PREFLIGHT_WRITER_SNAPSHOT_BINDING')
            need(d.same(immutable_snapshot(snapshot),immutable_snapshot(self.reviewed_snapshot)),
                 'HOST_PREFLIGHT_IMMUTABLE_SNAPSHOT_DRIFT')
            # Provenance stays the approved snapshot. The fresh proof is kept in
            # full, and checked against the actual approved role/unit contract.
            measured=self.processes(context,'stage_exact_release','preflight')
            from epoch7_live_controls import validate_process_view
            validate_process_view(measured,self.live_contract,self.live_contract['checkpoints'][0],os.getpid(),
                                  context_sha256=self.context['context_sha256'],checkpoint_index=0)
            fresh_digest=d.digest(snapshot)
            evidence=dict(evidence, kind='PRIVATE_EPOCH7_ADMISSION_SPLIT_EVIDENCE', snapshot_sha256=context['snapshot_sha256'],
                          fresh_snapshot_sha256=fresh_digest, fresh_writer_exclusion=copy.deepcopy(snapshot['writer_exclusion']),
                          fresh_process_proof=measured)
            prefix=io.read(snap.EPOCHS)[0]
            need(sha(prefix)==snapshot['epoch_journal_sha256'],'HOST_PREFLIGHT_EPOCH_PREFIX')
            self.fresh_snapshot=copy.deepcopy(self.reviewed_snapshot);self.fresh_evidence=copy.deepcopy(evidence)
            self.epoch7_prefix=prefix
            return copy.deepcopy(self.reviewed_snapshot),evidence
        finally:os.close(activation_fd)

    def resources(self,*args):self._bound();return self.resource_reader.resources(*args)
    def bind_effects(self,gate,runtime,outer_io):
        from epoch7_injected_recovery import RecoveryGate
        from epoch7_timer_tail import DeferredRenewalRuntime
        from epoch7_host_phases import HostPhaseFilesystem
        need(self.driver_gate is None and isinstance(gate,RecoveryGate) and
             isinstance(runtime,DeferredRenewalRuntime) and isinstance(outer_io,HostPhaseFilesystem) and
             runtime.context==self.context and outer_io.authority is self.authority,'HOST_OBSERVER_OWNED_EFFECTS')
        self.driver_gate,self.runtime,self.outer_io=gate,runtime,outer_io

    def _service_sources(self,unit):
        wanted=self.live_contract['service_role_contract']['units'][unit]['sources'];result={}
        self.resource_reader.reader.start()
        for path,pin in wanted.items():
            matches=[row for view in self.resource_reader.views for rows in view.values() for row in rows
                     if row['path']==path and row['kind']=='FILE' and row['sha256']==pin]
            need(matches,'HOST_SERVICE_SOURCE_COVERAGE_REQUIRED')
            self.resource_reader.reader.observe(matches[-1]);result[path]=pin
        return result

    def _service_receipts(self,unit):
        need(self.runtime is not None and self.outer_io is not None,'HOST_SERVICE_OWN_RUNTIME_REQUIRED')
        captured=self.runtime.successful_commands
        need('daemon_reload' in captured and unit in captured,'HOST_SERVICE_OWN_SUCCESS_REQUIRED')
        parent,leaf=self.outer_io._parent(fs.TRANSACTION+'/runtime-boot.json')
        try:meta,raw=self.outer_io._read_at(parent,leaf)
        finally:os.close(parent)
        need((meta['uid'],meta['gid'],meta['mode'],meta['nlink'])==(0,0,0o600,1), 'HOST_SERVICE_PRIVATE_BOOT_RECEIPT')
        value=snap.decode(raw)
        need(value.get('context_sha256')==self.context['context_sha256'] and
             type(value.get('successful_commands')) is dict,'HOST_SERVICE_BOOT_CONTEXT')
        stored=value['successful_commands']
        need(all(k in captured and captured[k]==v for k,v in stored.items()),'HOST_SERVICE_RECEIPT_DRIFT')
        persisted=all(stored.get(k)==captured[k] for k in ('daemon_reload',unit))
        return {'reload':copy.deepcopy(captured['daemon_reload']),'start':copy.deepcopy(captured[unit]),
                'persistence':'PERSISTED' if persisted else 'OWN_CAPTURE_PENDING_PUBLICATION'}

    def _gateway_restoration(self):
        need(self.runtime is not None and self.runtime.legacy is not None and
             self.outer_io is self.runtime.legacy.io,'HOST_GATEWAY_CONCRETE_OWN_RESTORE')
        captured=self.runtime.legacy.restoration_evidence()
        if captured is None:return None
        parent,leaf=self.outer_io._parent(fs.TRANSACTION+'/runtime-boot.json')
        try:
            try:meta,raw=self.outer_io._read_at(parent,leaf)
            except FileNotFoundError:return dict(captured,persistence='OWN_CAPTURE_PENDING_PUBLICATION')
        finally:os.close(parent)
        need((meta['uid'],meta['gid'],meta['mode'],meta['nlink'])==(0,0,0o600,1),
             'HOST_GATEWAY_PRIVATE_BOOT_RECEIPT')
        value=snap.decode(raw)
        need(value.get('context_sha256')==self.context['context_sha256'] and
             value.get('gateway_restoration')==captured,'HOST_GATEWAY_PERSISTED_RESTORATION_CHANGED')
        return dict(captured,persistence='PERSISTED')

    def _target_transition(self,phase,boundary):
        from epoch7_injected_recovery import PROVISION
        from epoch7_recovery_sequence import PHASES
        contract=self.live_contract['unit_transition_contract']
        if boundary in ('cleanup','inner') or not contract['targets'] and 'gateway_restoration' not in contract:return None
        if boundary=='preflight':
            need(phase=='stage_exact_release','HOST_TARGET_PREFLIGHT_PHASE');return None
        need(phase in PHASES and boundary in ('before','after','effect'),'HOST_TARGET_PROOF_BOUNDARY')
        index=PHASES.index(phase)+(1 if boundary=='after' else 0)
        if index<5:return None
        need(self.driver_gate is not None and self.runtime is not None and self.outer_io is not None,
             'HOST_TARGET_OWN_EFFECTS_REQUIRED')
        self.authority.receipt()
        if not contract['targets']:
            return {'context_sha256':self.context['context_sha256'],'target_receipt':None,
                'reload':copy.deepcopy(self.runtime.successful_commands.get('daemon_reload')),
                'gateway_restoration':self._gateway_restoration()}
        parent,leaf=self.outer_io._parent(fs.TRANSACTION+'/'+PROVISION)
        try:meta,raw=self.outer_io._read_at(parent,leaf)
        finally:os.close(parent)
        need((meta['uid'],meta['gid'],meta['mode'],meta['nlink'])==(0,0,0o600,1),
             'HOST_TARGET_PRIVATE_RECEIPT')
        value=snap.decode(raw)
        need(d.canonical(value)+b'\n'==raw and set(value)=={'schema','name','transaction_id','binding','state'} and
             value['schema']==1 and value['name']==PROVISION and value['transaction_id']==d.TX and
             d.same(value['binding'],self.authority.binding) and
             d.same(value['binding'],self.driver_gate.journal_binding()),'HOST_TARGET_RECEIPT_BINDING')
        state=value['state'];need(type(state) is dict and set(state)=={'stage','targets'} and
             state['stage']=='TARGET_DELTA_COMPLETE' and type(state['targets']) is list,
             'HOST_TARGET_COMPLETE_RECEIPT_REQUIRED')
        changes={row['path']:row for row in self.driver_gate.delta['changes'] if row['operation']!='RETAIN'}
        rows={row['path']:row for row in state['targets']}
        need(len(rows)==len(state['targets']) and set(rows)==set(changes),'HOST_TARGET_RECEIPT_SCOPE')
        for path,row in rows.items():
            need(row['state']=='DONE' and all(d.same(row[key],expected) for key,expected in changes[path].items()) and
                 d.same(row['observed_after'],self.driver_gate.current_targets[path]),'HOST_TARGET_OWN_CAS_BINDING')
        result={}
        for path,wanted in contract['targets'].items():
            need(path in rows,'HOST_TARGET_NO_UNOWNED_REPLACEMENT')
            observed=rows[path]['observed_after'];d.validate_file(observed)
            need(all(d.same(observed[k],v) for k,v in wanted.items()),'HOST_TARGET_REVIEWED_PROPOSAL')
            # An unchanged cached Python record is insufficient: re-read the
            # exact installed inode and stamps without reusing pre-active gate.
            actual=self.outer_io.read_target(path)
            need(d.same(actual,observed),'HOST_TARGET_PUBLISHED_INODE_DRIFT')
            result[path]=copy.deepcopy(actual)
        reload=copy.deepcopy(self.runtime.successful_commands.get('daemon_reload'))
        proof={'context_sha256':self.context['context_sha256'],
               'target_receipt':{'path':PROVISION,'sha256':sha(raw),'targets':result},'reload':reload}
        if 'gateway_restoration' in contract:proof['gateway_restoration']=self._gateway_restoration()
        return proof

    def processes(self,*args):
        self._bound();value=self.census.processes(*args)
        if self.live_contract.get('schema')==2:
            blocks=self.live_contract['service_role_contract']['units']
            selected={unit:block for unit,block in blocks.items() if 'quiet_startup' in block}
            quiet=self.quiet.observe(selected,args[1],self.guard_deadline) if selected and args[2] not in ('cleanup','inner') else None
            active={u for u in self.census.scoped_units if value['units'][u]['before']['ActiveState']=='active'}
            units={}
            for unit in active:
                units[unit]=dict(self._service_receipts(unit),sources=self._service_sources(unit))
                if 'quiet_startup' in blocks[unit]:
                    need(quiet is not None,'HOST_FRESH_QUIET_PROJECTION_REQUIRED')
                    units[unit]['quiet_startup']=copy.deepcopy(quiet)
            value['service_role_evidence']={'context_sha256':self.context['context_sha256'] if active else None,
                'units':units,'processes':copy.deepcopy(self.census.scoped_meta)}
            need(len(args)==3 and args[0]==self.context,'HOST_PROCESS_PROOF_CONTEXT')
            value['unit_transition_evidence']=self._target_transition(args[1],args[2])
        return value
    def unit(self,*args):self._bound();return self.census.unit(*args)
    def tls_contents(self,context=None):
        self._bound();need(context is None or context==self.context,'HOST_TLS_CONTEXT')
        return self.tls.contents()

    def legacy_exclusion(self):
        from epoch7_live_controls import validate_cleanup_process_view
        self._bound();self.begin_guard(time.monotonic()+30)
        result=self.processes(self.context,'activate_new_services','cleanup')
        validate_cleanup_process_view(result,self.live_contract,os.getpid())
        return {'all_units_stopped_and_cgroups_empty':True,'database_fds_excluded':True,
                'process_census_sha256':d.digest(result)}
