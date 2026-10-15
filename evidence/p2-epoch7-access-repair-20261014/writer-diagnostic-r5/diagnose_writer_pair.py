"""Capture exactly one frozen collector attempt and at most two writer samples."""
import ast,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,types
HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
KIT=BASE+'/epoch7-recovery-candidate-r5'
ENTRY_SHA='1565e2f1e7e771f33e0895ffcaf8f38caddee9e02811a11b6a2318334af6075a'
MANIFEST_SHA='d8c36ad208994a3314f6b0c0598ad2e4ea8641c75f2610f9749784f834244d49'
FILE='epoch7-observation-4965e4769e7bc085.private.json'
OBS_SHA='53c578a2eaa872d24dc06cf1bbaacd1f0dbc4746b36f73802d01bc8f334d16a0'
RECEIPT='epoch7-diagnostic-4965e4769e7bc085.private.json'
RECEIPT_SHA='a12d0b5107e78748239a1002667db14a354fd07e031e248c9486ff9d7dceb99c'
SOURCE='9c40fc811947112df579b293fb4d54c61d9ce37b'
def need(value):
    if not value:raise ValueError('DIAGNOSTIC_BOUNDARY')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def stamp(i):return tuple(getattr(i,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))


class Deadline(KeyboardInterrupt):pass


@contextlib.contextmanager
def bounded(seconds=600):
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0));previous=signal.getsignal(signal.SIGALRM)
    def expired(*unused):raise Deadline()
    signal.signal(signal.SIGALRM,expired);primary=None
    try:
        signal.setitimer(signal.ITIMER_REAL,seconds,1);yield
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,previous)
        except BaseException:failed=True
        if failed:
            if primary is not None:primary.diagnostic_cleanup_failed=True
            else:
                failure=ValueError('DIAGNOSTIC_BOUNDARY');failure.diagnostic_cleanup_failed=True;raise failure


def authority(fd,directory):
    i=os.fstat(fd)
    need((stat.S_ISDIR(i.st_mode) if directory else stat.S_ISREG(i.st_mode)) and i.st_uid==i.st_gid==0 and not i.st_mode&0o7022 and (directory or i.st_nlink==1))
    for name in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,name)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP))
        else:need(False)
    return i


def entry_bytes():
    held=[];rows=[];primary=None
    try:
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);held.append(fd);rows.append((fd,None,None,stamp(authority(fd,True))))
        for name in KIT[1:].split('/'):
            parent=fd;fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);held.append(fd)
            pin=stamp(authority(fd,True));need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==pin);rows.append((fd,parent,name,pin))
        parent=fd;name='epoch7_recovery_entry.py';fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);held.append(fd)
        before=authority(fd,False);need(0<before.st_size<=1048576);chunks=[];count=0
        while True:
            part=os.read(fd,min(65536,1048577-count))
            if not part:break
            count+=len(part);need(count<=1048576);chunks.append(part)
        raw=b''.join(chunks);need(count==before.st_size and sha(raw)==ENTRY_SHA and stamp(before)==stamp(authority(fd,False))==stamp(os.stat(name,dir_fd=parent,follow_symlinks=False)))
        for fd,parent,name,pin in rows:
            need(stamp(authority(fd,True))==pin)
            if parent is not None:need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==pin)
        return raw
    except BaseException as error:primary=error;raise
    finally:
        failure=None
        for fd in reversed(held):
            try:os.close(fd)
            except BaseException as error:
                if failure is None:failure=error
        if failure is not None:
            if primary is not None:primary.diagnostic_cleanup_failed=True
            else:
                failure.diagnostic_cleanup_failed=True;raise failure


def read_pair(entry):
    with entry.DescriptorTree(BASE) as tree:
        raw=tree.read(FILE,64*1024*1024,private=True)
        receipt_raw=tree.read(RECEIPT,16384,private=True)
        tree.recheck()
    need(sha(raw)==OBS_SHA and sha(receipt_raw)==RECEIPT_SHA)
    value=entry.decode(raw);receipt=entry.decode(receipt_raw)
    need(type(value) is dict and value.get('schema')==1 and type(receipt) is dict and receipt.get('schema')==1)
    need(receipt.get('kind')=='OWNER_R5_RECEIPT_BOUND_CONTINUATION' and receipt.get('kit_source_commit')==SOURCE and receipt.get('kit_manifest_sha256')==MANIFEST_SHA)
    observed=receipt.get('observation');need(type(observed) is dict and observed.get('private_file_sha256')==OBS_SHA and observed.get('kit_manifest_sha256')==MANIFEST_SHA)
    return value,receipt

MAX_SAMPLE=4*1024*1024
MAX_OUTPUT=65536
SECTIONS=('manager','units','masks','scheduler_sha256','control_files','processes')
META=('uid','gid','mode','dev','ino','nlink','size','mtime_ns','ctime_ns','kind','link','sha256')
MANAGER=('uids','gids','groups','boot_id','pid','starttime','binary_sha256','binary_path','binary_identity','channels')
CHANNELS=('/run/systemd/private','/run/dbus/system_bus_socket')
PROPS=('Id','LoadState','ActiveState','SubState','MainPID','ControlPID','ControlGroup','UnitFileState','ConditionResult','FragmentPath','DropInPaths','NeedDaemonReload')
CLEANUP=frozenset(('READ_ONLY_COMMAND_CLEANUP_UNKNOWN','EXISTING_LOCKS_CLEANUP_UNKNOWN','NODE_REFERENCE_CLEANUP_UNKNOWN','READER_PARENT_CLEANUP_UNKNOWN'))
LOCAL_CODES=frozenset(('DIAGNOSTIC_BOUNDARY','WRITER_CAPTURE_CALL_BOUND','WRITER_CAPTURE_SIZE_BOUND','WRITER_OBSERVATION_CHANGED'))


def canonical(value, maximum=MAX_SAMPLE):
    chunks=[];size=0
    encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    for chunk in encoder.iterencode(value):
        raw=chunk.encode('ascii');size+=len(raw)
        if size>maximum:raise ValueError('WRITER_CAPTURE_SIZE_BOUND')
        chunks.append(raw)
    return b''.join(chunks)


def digest(value):return sha(canonical(value))


def same(left,right):return canonical(left)==canonical(right)


def public_codes(cache):
    result=set(LOCAL_CODES)|set(CLEANUP)|set(PROCESS_CODES)
    for path,raw in cache.items():
        if path.endswith('.py'):
            for node in ast.walk(ast.parse(raw)):
                if isinstance(node,ast.Str) and type(node.s) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}',node.s):result.add(node.s)
    return frozenset(result)


def error_info(error,codes):
    code=error.args[0] if isinstance(error,ValueError) and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in codes else 'BOUNDARY_OR_DEPENDENCY_FAILED'
    if isinstance(error,Deadline):code='DIAGNOSTIC_DEADLINE'
    elif isinstance(error,KeyboardInterrupt):code='INTERRUPTED'
    elif isinstance(error,SystemExit):code='SYSTEM_EXIT'
    cleanup=False;seen=set();current=error
    for unused in range(8):
        if current is None or id(current) in seen:break
        seen.add(id(current));args=getattr(current,'args',())
        cleanup=cleanup or getattr(current,'diagnostic_cleanup_failed',False) is True or getattr(current,'prerequisite_cleanup_failed',False) is True or (len(args)==1 and type(args[0]) is str and args[0] in CLEANUP)
        current=current.__cause__
    return {'failure_code':code,'cleanup_unknown':cleanup,'errno':error.errno if isinstance(error,OSError) and type(error.errno) is int else None}


MAX_CENSUS=2*1024*1024
MAX_PROC_CAPTURE=32*1024*1024
MAX_CHANGED_PIDS=64
PROCESS_CODES=frozenset(('PROCESS_CAPTURE_CALL_BOUND','PROCESS_CAPTURE_PROFILE_PRESENT',
    'PROCESS_CAPTURE_PROFILE_CHANGED','PROCESS_CAPTURE_PROFILE_CLEANUP_UNKNOWN',
    'PROCESS_CAPTURE_RETURN_BINDING','PROCESS_CAPTURE_MAP_SCHEMA','PROCESS_CAPTURE_MAP_BOUND',
    'PROCESS_CAPTURE_DIGEST_BINDING','PROCESS_CAPTURE_FD_BINDING','PROCESS_CAPTURE_NESTED_CODE',
    'PROCESS_CAPTURE_DETAIL_BOUND','PROCESS_CAPTURE_DETAIL_SCHEMA','PROCESS_CAPTURE_STAT_BINDING'))
COMM_LABELS={b'systemd':'SYSTEMD_COMM',b'sshd':'SSHD_COMM',b'ssh':'SSH_COMM',
    b'crond':'CROND_COMM',b'cron':'CRON_COMM',b'dbus-daemon':'DBUS_DAEMON_COMM',
    b'rsyslogd':'RSYSLOGD_COMM',b'auditd':'AUDITD_COMM',b'agetty':'AGETTY_COMM',
    b'sudo':'SUDO_COMM',b'bash':'BASH_COMM',b'sh':'SH_COMM',
    b'python3':'PYTHON3_COMM',b'python3.6':'PYTHON36_COMM'}


def process_need(value,code):
    if not value:raise ValueError(code)


def stat_class(raw,pid,started):
    process_need(type(raw) is bytes and 0<len(raw)<=65536,'PROCESS_CAPTURE_DETAIL_SCHEMA')
    end=raw.rfind(b')');fields=raw[end+2:].split()
    process_need(raw.startswith((pid+' (').encode('ascii')) and end>0 and len(fields)>=20 and
        fields[6].isdigit() and fields[19].isdigit() and int(fields[19])==started,'PROCESS_CAPTURE_STAT_BINDING')
    return bool(int(fields[6])&0x00200000)


class ProcessCapture(object):
    """Observe authenticated return values; no second /proc census or writes."""
    def __init__(self):self.records=[];self.calls=0
    def call(self,owner,code,operation,original_digest):
        process_need(self.calls<2,'PROCESS_CAPTURE_CALL_BOUND');self.calls+=1
        record={'state':'UNKNOWN','reason':'ORIGINAL_PROCESS_SCAN_DID_NOT_RETURN'}
        self.records.append(record)
        process_need(sys.getprofile() is None and sys.gettrace() is None,'PROCESS_CAPTURE_PROFILE_PRESENT')
        nested=[item for item in code.co_consts if isinstance(item,types.CodeType) and item.co_name=='procfile']
        process_need(len(nested)==1,'PROCESS_CAPTURE_NESTED_CODE');nested=nested[0]
        captured=[];events=[0];details={};charged=[0];detail_failure=[None];scan_frame_id=[None];primary=None
        def returned(frame,event,value):
            # Retain bounded original stat/comm bytes temporarily and scalar
            # counts, then clear them after validation. No frame, status,
            # argv/environment/FD names or extra I/O is retained.
            if event!='return':return
            if frame.f_code is code and frame.f_locals.get('self') is owner:
                events[0]+=1
                if events[0]==1:
                    if scan_frame_id[0] is not None and scan_frame_id[0]!=id(frame):detail_failure[0]='PROCESS_CAPTURE_DETAIL_SCHEMA'
                    captured.append((frame.f_locals.get('result'),frame.f_locals.get('fd_count'),value))
            elif frame.f_code is nested and detail_failure[0] is None:
                parent=frame.f_back
                if parent is None or parent.f_code is not code or parent.f_locals.get('self') is not owner:return
                if scan_frame_id[0] is None:scan_frame_id[0]=id(parent)
                if scan_frame_id[0]!=id(parent):
                    detail_failure[0]='PROCESS_CAPTURE_DETAIL_SCHEMA';return
                name=frame.f_locals.get('name')
                if name not in ('stat','comm'):return
                pid=parent.f_locals.get('pid')
                if type(pid) is not str or len(pid)>10 or type(value) is not bytes or len(value)>(65536 if name=='stat' else 256):
                    detail_failure[0]='PROCESS_CAPTURE_DETAIL_SCHEMA';return
                charged[0]+=len(value)
                if charged[0]>MAX_PROC_CAPTURE or (pid not in details and len(details)>=65536):
                    detail_failure[0]='PROCESS_CAPTURE_DETAIL_BOUND';return
                row=details.setdefault(pid,{'stat':[],'comm':[]})
                if len(row[name])>=(2 if name=='stat' else 1):
                    detail_failure[0]='PROCESS_CAPTURE_DETAIL_SCHEMA';return
                row[name].append(value)
                if name=='stat' and len(row[name])==2:
                    names=parent.f_locals.get('fd_names')
                    row['fd_count']=len(names) if type(names) is list else None
        try:
            sys.setprofile(returned)
            value=operation()
            process_need(sys.getprofile() is returned and sys.gettrace() is None,'PROCESS_CAPTURE_PROFILE_CHANGED')
        except BaseException as error:
            primary=error;raise
        finally:
            failed=False
            try:sys.setprofile(None)
            except BaseException:failed=True
            try:failed=failed or sys.getprofile() is not None
            except BaseException:failed=True
            if primary is not None:captured[:]=[];details.clear()
            if failed:
                record['reason']='PROCESS_CAPTURE_PROFILE_CLEANUP_UNKNOWN'
                captured[:]=[];details.clear()
                if primary is not None:primary.diagnostic_cleanup_failed=True
                else:
                    failure=ValueError('PROCESS_CAPTURE_PROFILE_CLEANUP_UNKNOWN')
                    failure.diagnostic_cleanup_failed=True;raise failure
        try:
            process_need(events[0]==1 and len(captured)==1 and captured[0][2] is value,'PROCESS_CAPTURE_RETURN_BINDING')
            sample,count,unused=captured[0]
            process_need(type(sample) is dict and len(sample)<=65536,'PROCESS_CAPTURE_MAP_SCHEMA')
            for pid,row in sample.items():
                process_need(type(pid) is str and re.fullmatch('[1-9][0-9]{0,9}',pid) is not None and int(pid)<2**31 and
                    type(row) is dict and set(row)=={'starttime','uids'} and type(row['starttime']) is int and 0<=row['starttime']<2**64 and
                    type(row['uids']) is list and len(row['uids'])==4 and all(type(uid) is int and 0<=uid<2**32 for uid in row['uids']),
                    'PROCESS_CAPTURE_MAP_SCHEMA')
            raw=canonical(sample,MAX_CENSUS)
            process_need(len(raw)<=MAX_CENSUS,'PROCESS_CAPTURE_MAP_BOUND')
            process_need(type(value) is dict and original_digest(sample)==value.get('process_identity_sha256'),'PROCESS_CAPTURE_DIGEST_BINDING')
            process_need(type(count) is int and 0<=count<=1000000 and count==value.get('fd_count'),'PROCESS_CAPTURE_FD_BINDING')
            record.update(state='CAPTURED_FROM_ORIGINAL_RETURN',sample=json.loads(raw.decode('ascii')),
                          process_identity_sha256=value['process_identity_sha256'],fd_count=count,
                          details_state='UNKNOWN',details_reason=detail_failure[0])
            record.pop('reason',None)
            process_need(detail_failure[0] is None,detail_failure[0] or 'PROCESS_CAPTURE_DETAIL_SCHEMA')
            process_need(set(details)==set(sample),'PROCESS_CAPTURE_DETAIL_SCHEMA')
            typed={}
            for pid,row in sample.items():
                part=details[pid]
                process_need(len(part['stat'])==2 and len(part['comm'])==1 and type(part.get('fd_count')) is int and
                    0<=part['fd_count']<=1000000,'PROCESS_CAPTURE_DETAIL_SCHEMA')
                first=stat_class(part['stat'][0],pid,row['starttime']);last=stat_class(part['stat'][1],pid,row['starttime'])
                process_need(first==last,'PROCESS_CAPTURE_STAT_BINDING')
                comm=part['comm'][0].strip()
                typed[pid]={'kernel_thread':first,'comm_sha256':sha(comm),'comm_label':COMM_LABELS.get(comm,'UNLISTED_COMM_HASH_ONLY'),
                    'fd_count':part['fd_count']}
            process_need(sum(row['fd_count'] for row in typed.values())==count,'PROCESS_CAPTURE_FD_BINDING')
            record.update(details_state='EXACT_ORIGINAL_STAT_COMM_FD_BOUND',details=typed);record.pop('details_reason',None)
        except Exception as error:
            code=error.args[0] if isinstance(error,ValueError) and len(error.args)==1 else None
            reason=code if code in PROCESS_CODES else 'PROCESS_CAPTURE_VALIDATION_FAILED'
            if record['state']=='CAPTURED_FROM_ORIGINAL_RETURN':record['details_reason']=reason
            else:record['reason']=reason
        finally:
            captured[:]=[];details.clear()
        return value


def project_process_capture(capture):
    result={'state':'UNKNOWN_NOT_REACHED','attempted_scan_count':capture.processes.calls,
        'captured_scan_count':sum(r['state']=='CAPTURED_FROM_ORIGINAL_RETURN' for r in capture.processes.records),
        'sample_states':[{'state':r['state'],'reason':r.get('reason'),'details_state':r.get('details_state'),'details_reason':r.get('details_reason')} for r in capture.processes.records],
        'source':'EXACT_ORIGINAL_SCAN_RETURN_LOCALS','additional_proc_reads':0,
        'security_classification':'NOT_GRANTED','executable_cgroup_fd_targets':'NOT_CAPTURED',
        'comm_labels':'NAME_ONLY_NOT_EXECUTABLE_IDENTITY'}
    if len(capture.samples)!=2 or len(capture.processes.records)!=2:return result
    first,last=capture.processes.records
    if any(r['state']!='CAPTURED_FROM_ORIGINAL_RETURN' for r in (first,last)):return result
    for sample,row in zip(capture.samples,(first,last)):
        if row['process_identity_sha256']!=sample['processes']['process_identity_sha256'] or row['fd_count']!=sample['processes']['fd_count']:
            result.update(state='UNKNOWN_WRITER_SAMPLE_BINDING');return result
    before,after=first['sample'],last['sample']
    added=set(after)-set(before);removed=set(before)-set(after)
    changed={pid for pid in set(before)&set(after) if not same(before[pid],after[pid])}
    classified=all(row.get('details_state')=='EXACT_ORIGINAL_STAT_COMM_FD_BOUND' for row in (first,last))
    detail_changed={pid for pid in set(before)&set(after) if not same(first['details'][pid],last['details'][pid])} if classified else set()
    ordered=sorted(added|removed|changed|detail_changed,key=int);shown=ordered[:MAX_CHANGED_PIDS]
    def row_at(record,pid):
        if pid not in record['sample']:return None
        value=dict(record['sample'][pid])
        value['class_metadata']=dict(record['details'][pid]) if record.get('details_state')=='EXACT_ORIGINAL_STAT_COMM_FD_BOUND' else {'state':'UNKNOWN'}
        return value
    result.update(state='EXACT_ORIGINAL_SAMPLES_BOUND',class_metadata_state='EXACT_ORIGINAL_SAMPLES_BOUND' if classified else 'UNKNOWN',
        before_process_count=len(before),after_process_count=len(after),
        before_process_identity_sha256=first['process_identity_sha256'],after_process_identity_sha256=last['process_identity_sha256'],
        before_fd_count=first['fd_count'],after_fd_count=last['fd_count'],added_count=len(added),removed_count=len(removed),
        changed_identity_count=len(changed),changed_class_or_fd_count=len(detail_changed),omitted_changed_pid_count=max(0,len(ordered)-len(shown)),truncated=len(ordered)>len(shown),
        all_changed_pid_set_sha256=digest(ordered),
        changed_pid_rows=[{'pid':int(pid),'change':'ADDED' if pid in added else ('REMOVED' if pid in removed else ('IDENTITY_CHANGED' if pid in changed else 'CLASS_OR_FD_CHANGED')),
            'before':row_at(first,pid),'after':row_at(last,pid)} for pid in shown])
    return result


class Capture(object):
    def __init__(self):self.samples=[];self.calls=0;self.validations=0;self.processes=ProcessCapture()
    def call(self,operation,validate):
        if self.calls>=2:raise ValueError('WRITER_CAPTURE_CALL_BOUND')
        self.calls+=1
        value=operation()
        raw=canonical(value)
        validate(value)
        self.validations+=1
        self.samples.append(json.loads(raw.decode('ascii')))
        return value


def recording_io(base,validate,capture,original_digest=None):
    class RecordingIO(base):
        def writers(self,policy,paths):
            return capture.call(lambda:super(RecordingIO,self).writers(policy,paths),validate)
    if original_digest is not None:
        code=base._process_scan.__code__
        def process_scan(self,database_paths):
            return capture.processes.call(self,code,lambda:super(RecordingIO,self)._process_scan(database_paths),original_digest)
        RecordingIO._process_scan=process_scan
    return RecordingIO


def diff(before,after):
    return {'changed':not same(before,after),'before_sha256':digest(before),'after_sha256':digest(after)}


def fields(before,after,allowed):
    changed=[key for key in allowed if (key in before)!=(key in after) or not same(before.get(key),after.get(key))]
    extra_a={k:v for k,v in before.items() if k not in allowed};extra_b={k:v for k,v in after.items() if k not in allowed}
    return {'changed_fields':changed,'unlisted_field_count_before':len(extra_a),'unlisted_field_count_after':len(extra_b),
            'unlisted_fields':diff(extra_a,extra_b)}


def project(capture,units,masks):
    result={'successful_validated_samples':len(capture.samples),'attempted_call_count':capture.calls,
        'pair_state':'UNKNOWN_NOT_REACHED','global_process_churn_cause':'NOT_ATTRIBUTED'}
    if len(capture.samples)!=2:
        result['process_attribution']=project_process_capture(capture)
        return result
    before,after=capture.samples
    need(set(before)==set(after)==set(SECTIONS))
    result.update(pair_state='EQUAL' if same(before,after) else 'DIFFERENT',exact_pair_equal=same(before,after),
        before_sha256=digest(before),after_sha256=digest(after),changed_sections=[k for k in SECTIONS if not same(before[k],after[k])])
    details={key:diff(before[key],after[key]) for key in SECTIONS}
    details['manager'].update(fields(before['manager'],after['manager'],MANAGER))
    channels={}
    for name in CHANNELS:
        a=before['manager'].get('channels',{}).get(name,{});b=after['manager'].get('channels',{}).get(name,{})
        channels[name]=dict(diff(a,b),**fields(a,b,META))
    details['manager']['channels']=channels
    unit_rows={}
    for name in units:
        a=before['units'][name];b=after['units'][name]
        unit_rows[name]={'state':dict(diff(a['state'],b['state']),**fields(a['state'],b['state'],PROPS)),
            'cgroup_entries':dict(diff(a['cgroup_entries'],b['cgroup_entries']),before_count=len(a['cgroup_entries']),after_count=len(b['cgroup_entries']))}
    details['units']['rows']=unit_rows
    details['masks']['rows']={name:dict(diff(before['masks'][name],after['masks'][name]),**fields(before['masks'][name],after['masks'][name],META)) for name in masks}
    a=before['control_files'];b=after['control_files']
    details['control_files'].update(before_count=len(a),after_count=len(b),changed_entry_count=sum(1 for key in set(a)|set(b) if (key in a)!=(key in b) or not same(a.get(key),b.get(key))))
    a=before['processes'];b=after['processes']
    details['processes'].update(process_identity_sha256_changed=a['process_identity_sha256']!=b['process_identity_sha256'],
        fd_count_before=a['fd_count'],fd_count_after=b['fd_count'],
        background_processes=dict(diff(a['background_processes'],b['background_processes']),before_count=len(a['background_processes']),after_count=len(b['background_processes'])),
        background_processes_sha256_changed=a['background_processes_sha256']!=b['background_processes_sha256'])
    result['sections']=details
    result['process_attribution']=project_process_capture(capture)
    return result


def collect_once(observer,concrete,core,capture,result):
    reader=observer.ObservationReader({});pins={}
    for name,mode in ((core.INSTALL_LOCK,0o600),(core.ACTIVATION_LOCK,0o644)):
        unused,info=reader.read(name)
        core.need((info['uid'],info['gid'],info['mode'])==(0,0,mode),'OBSERVATION_EXISTING_LOCK_AUTHORITY')
        pins[name]={key:info[key] for key in ('sha256','uid','gid','mode')}
    with concrete.existing_locks(reader,{'files':pins}) as locks:
        backend=recording_io(observer.ObservationIO,core.validate_writers,capture,core.d.digest)(reader.pins,locks)
        result['collector_started']=True
        value=observer.observe_with_io(backend)
        # Never return the private policy, snapshot or evidence body.
        result['collector_returned']=True
        result['collector_result_digests']={key:value.get(key) for key in ('policy_sha256','snapshot_sha256','evidence_sha256')}


def run(entry,kit,result,capture,scope):
    with kit.imports():
        import observe_epoch7 as observer
        import snapshot_io as concrete
        import epoch7_snapshot as core
        scope['units']=tuple(sorted(core.WRITER_UNITS));scope['masks']=tuple(sorted(core.LEGACY_MASKS))
        collect_once(observer,concrete,core,capture,result)


def new_result():
    return {'schema':1,'kind':'FROZEN_R5_WRITER_PAIR_DIAGNOSTIC','kit_manifest_sha256':MANIFEST_SHA,
        'kit_source_commit':SOURCE,'prior_observation_sha256':OBS_SHA,'prior_receipt_sha256':RECEIPT_SHA,
        'collector_started':False,'collector_returned':False,'final_authentication':'NOT_RUN',
        'collector_attempts':0,'install_admission':'NOT_GRANTED','probe':'NOT_RUN','production_resume':'NOT_EXECUTED',
        'permission_changes':0,'service_actions':0,'private_evidence_values':'NOT_OUTPUT',
        'ancillary_probe_unit_source_openclaw_reports':'NOT_RUN',
        'query_side_effects':'DISPOSABLE_SQLITE_COPIES_AND_RPM_BOOKKEEPING_POSSIBLE'}


def finish(result,capture,scope,primary,codes):
    if primary is not None:result['primary_failure']=error_info(primary,codes)
    try:result['writer_pair']=project(capture,scope.get('units',()),scope.get('masks',()))
    except BaseException as error:result['projection_failure']=error_info(error,codes)
    code=result.get('primary_failure',{}).get('failure_code')
    result['tail_checks']='NOT_REACHED_AFTER_WRITER_MISMATCH' if code=='WRITER_OBSERVATION_CHANGED' else ('COMPLETED_BY_ORIGINAL_COLLECTOR' if result['collector_returned'] else 'NOT_RUN_OR_UNKNOWN_AFTER_FIRST_FAILURE')
    result['cleanup_unknown']=any(result.get(key,{}).get('cleanup_unknown') for key in ('primary_failure','final_authentication_failure','projection_failure'))
    result['process_attribution_complete']=result.get('writer_pair',{}).get('process_attribution',{}).get('class_metadata_state')=='EXACT_ORIGINAL_SAMPLES_BOUND'
    result['diagnostic_complete']=len(capture.samples)==2 and result['final_authentication']=='VERIFIED' and not result['cleanup_unknown'] and 'projection_failure' not in result
    result['success']=primary is None and result['final_authentication']=='VERIFIED' and 'projection_failure' not in result
    try:raw=canonical(result,MAX_OUTPUT)
    except BaseException:
        raw=canonical({'kind':result['kind'],'success':False,'failure_code':'OUTPUT_BOUND_OR_ENCODING','cleanup_unknown':result['cleanup_unknown'],
            'successful_validated_samples':len(capture.samples),'final_authentication':result['final_authentication'],'production_resume':'NOT_EXECUTED'},MAX_OUTPUT)
        return raw.decode('ascii'),2
    return raw.decode('ascii'),0 if result['success'] else 2


def main():
    result=new_result();capture=Capture();scope={};entry=None;authenticated=False;primary=None;codes=LOCAL_CODES|CLEANUP
    try:
        need(os.geteuid()==os.getegid()==0 and socket.gethostname().split('.')[0]==HOST)
        need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
        with bounded():
            raw=entry_bytes();entry=types.ModuleType('verified_writer_diagnostic_entry');entry.__file__=KIT+'/epoch7_recovery_entry.py'
            exec(compile(raw,entry.__file__,'exec',dont_inherit=True),entry.__dict__)
            kit=entry.verify_kit(KIT,MANIFEST_SHA);codes=public_codes(kit.cache)
            prior,unused=read_pair(entry)
            need(prior.get('kind')=='EPOCH7_OBSERVATION_ONLY_HOLD' and prior.get('failure_code')=='WRITER_OBSERVATION_CHANGED')
            authenticated=True;result['collector_attempts']=1
            run(entry,kit,result,capture,scope)
    except BaseException as error:primary=error
    if authenticated:
        try:
            with bounded(60):
                entry_bytes();entry.verify_kit(KIT,MANIFEST_SHA);read_pair(entry)
                result['final_authentication']='VERIFIED'
        except BaseException as error:
            result['final_authentication']='FAILED';result['final_authentication_failure']=error_info(error,codes)
    try:
        with bounded(10):text,status=finish(result,capture,scope,primary,codes)
    except BaseException as error:
        text=json.dumps({'kind':result['kind'],'success':False,'failure_code':'OUTPUT_FINALIZATION_FAILED','primary_failure':error_info(primary,codes) if primary is not None else None,'final_authentication':result['final_authentication'],'final_authentication_failure':result.get('final_authentication_failure'),'output_failure':error_info(error,codes),'cleanup_unknown':result.get('final_authentication_failure',{}).get('cleanup_unknown',False) or error_info(error,codes)['cleanup_unknown'] or (error_info(primary,codes)['cleanup_unknown'] if primary is not None else False),'production_resume':'NOT_EXECUTED'},sort_keys=True);status=2
    print(text);return status

if __name__=='__main__':sys.exit(main())
