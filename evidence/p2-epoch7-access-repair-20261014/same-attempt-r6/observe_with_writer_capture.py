"""One unchanged r6 continuation, with same-call diagnostic-only writer capture."""
import ast,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,time,types,urllib.request
HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
KIT=BASE+'/epoch7-recovery-candidate-r6'
ENTRY_SHA='c56ba6d8281eeb1ecc062875a7f13defc223f6d5dd073a4490d1602b8cf1d3a5'
MANIFEST_SHA='70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'
FILE='epoch7-observation-27159841d4b6eeff.private.json'
OBS_SHA='d6f1c26e6e41e28d7e8207e1c2f3d083885ebb44cc117bfcecd98e1e5cea7c9b'
RECEIPT='epoch7-diagnostic-27159841d4b6eeff.private.json'
RECEIPT_SHA='92c56d0b827bb3b9218810639317192a68a056d4804d7fec2d5239e5aac6997c'
SOURCE='0c8a0f2a97da0c3f00f53659cd6ef7fc7d4ec3ba'


def need(value):
    if not value:raise ValueError('DIAGNOSTIC_BOUNDARY')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def stamp(i):return tuple(getattr(i,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))


class Deadline(KeyboardInterrupt):pass


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
    need(receipt.get('kind')=='OWNER_R6_RECEIPT_BOUND_CONTINUATION' and receipt.get('kit_source_commit')==SOURCE and receipt.get('kit_manifest_sha256')==MANIFEST_SHA)
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


def process_need(value,code):
    if not value:raise ValueError(code)


def stat_class(raw,pid,started):
    process_need(type(raw) is bytes and 0<len(raw)<=65536,'PROCESS_CAPTURE_DETAIL_SCHEMA')
    end=raw.rfind(b')');fields=raw[end+2:].split()
    process_need(raw.startswith((pid+' (').encode('ascii')) and end>0 and len(fields)>=20 and
        fields[6].isdigit() and fields[19].isdigit() and int(fields[19])==started,'PROCESS_CAPTURE_STAT_BINDING')
    return bool(int(fields[6])&0x00200000)


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


OUTER_COMMIT='3199565b2f0d91d788251a7d52e6b749937b991d'
OUTER_SHA='b3c10f53e4523c52ca140083422bd7c43e6a4465c51c2831b46ea14cec9454ad'
OUTER_SIZE=27133
OUTER_URL='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'+OUTER_COMMIT+'/evidence/p2-epoch7-access-repair-20261014/owner-diagnostic-r6/owner_diagnostic_r6.py'
FAILED_ID='27159841d4b6eeff'
FAILED_NONCE='d96f69960fdf29995d64633c1d697f09'
MODULES={'observe_epoch7':'helpers/observe_epoch7.py','snapshot_io':'helpers/snapshot_io.py','epoch7_snapshot':'helpers/epoch7_snapshot.py'}
CAPTURE_CODES=frozenset(('CAPTURE_AUTHENTICATION','CAPTURE_LINEAGE','CAPTURE_CALL_BOUND','CAPTURE_SCHEMA','CAPTURE_PROFILE_CHANGED','CAPTURE_PROFILE_CLEANUP_UNKNOWN','CAPTURE_TIME_BOUND'))

class CaptureAbort(KeyboardInterrupt):pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('CAPTURE_AUTHENTICATION')


def frozen_outer():
    with bounded(30):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(urllib.request.Request(OUTER_URL,headers={'Accept-Encoding':'identity'}),timeout=10) as response:
            need(response.status==200 and response.geturl()==OUTER_URL and response.headers.get('Content-Encoding','identity')=='identity')
            length=response.headers.get('Content-Length');need(length is None or length==str(OUTER_SIZE))
            raw=response.read(OUTER_SIZE+1)
        need(type(raw) is bytes and len(raw)==OUTER_SIZE and sha(raw)==OUTER_SHA)
        module=types.ModuleType('authenticated_original_r6_outer');module.__file__='<verified-r6-outer-'+OUTER_SHA+'>'
        exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
        need(module.READY is True and module.ENTRY_SHA==ENTRY_SHA and module.MANIFEST_SHA==MANIFEST_SHA and module.SOURCE==SOURCE and module.KIT==KIT)
        return module


def prior_hold():
    with bounded(60):
        raw=entry_bytes();entry=types.ModuleType('verified_prior_r6_entry');entry.__file__=KIT+'/epoch7_recovery_entry.py'
        exec(compile(raw,entry.__file__,'exec',dont_inherit=True),entry.__dict__)
        kit=entry.verify_kit(KIT,MANIFEST_SHA)
        try:value,receipt=read_pair(entry)
        except BaseException as error:error.diagnostic_cleanup_failed=True;raise
        observed=receipt['observation'];attempt=value.get('finite_probe')
        need(observed.get('kind')=='EPOCH7_OBSERVATION_ONLY_HOLD' and observed.get('probe_stage')=='HOLD_NOT_EXECUTED' and
             observed.get('policy_sha256') is None and observed.get('snapshot_sha256') is None and type(attempt) is dict and
             attempt.get('nonce')==FAILED_NONCE and attempt.get('stage')=='HOLD_NOT_EXECUTED' and
             value.get('kind')=='EPOCH7_OBSERVATION_ONLY_HOLD' and value.get('failure_code')=='WRITER_OBSERVATION_CHANGED')
        return {'diagnostic_receipt_sha256':RECEIPT_SHA,'observation_sha256':OBS_SHA,'observation_id':FAILED_ID,
                'nonce':FAILED_NONCE,'status':'EXACT_STORED_HOLD_VERIFIED','previous_hold_attribution':'UNKNOWN_NOT_RECONSTRUCTED'}


def validate_process(raw,original_digest):
    record={'state':'UNKNOWN','reason':'PROCESS_CAPTURE_VALIDATION_FAILED'}
    sample,count,value,details,detail_failure=raw
    try:
        process_need(type(sample) is dict and len(sample)<=65536,'PROCESS_CAPTURE_MAP_SCHEMA')
        for pid,row in sample.items():
            process_need(type(pid) is str and re.fullmatch('[1-9][0-9]{0,9}',pid) is not None and int(pid)<2**31 and
                type(row) is dict and set(row)=={'starttime','uids'} and type(row['starttime']) is int and 0<=row['starttime']<2**64 and
                type(row['uids']) is list and len(row['uids'])==4 and all(type(uid) is int and 0<=uid<2**32 for uid in row['uids']),
                'PROCESS_CAPTURE_MAP_SCHEMA')
        encoded=canonical(sample,MAX_CENSUS)
        process_need(type(value) is dict and original_digest(sample)==value.get('process_identity_sha256'),'PROCESS_CAPTURE_DIGEST_BINDING')
        process_need(type(count) is int and 0<=count<=1000000 and count==value.get('fd_count'),'PROCESS_CAPTURE_FD_BINDING')
        record.update(state='CAPTURED_FROM_ORIGINAL_RETURN',sample=json.loads(encoded.decode('ascii')),
            process_identity_sha256=value['process_identity_sha256'],fd_count=count,details_state='UNKNOWN',details_reason=detail_failure)
        record.pop('reason',None)
        process_need(detail_failure is None,detail_failure or 'PROCESS_CAPTURE_DETAIL_SCHEMA')
        process_need(set(details)==set(sample),'PROCESS_CAPTURE_DETAIL_SCHEMA')
        typed={}
        for pid,row in sample.items():
            part=details[pid]
            process_need(len(part['stat'])==2 and len(part['comm'])==1 and type(part.get('fd_count')) is int and
                0<=part['fd_count']<=1000000,'PROCESS_CAPTURE_DETAIL_SCHEMA')
            first=stat_class(part['stat'][0],pid,row['starttime']);last=stat_class(part['stat'][1],pid,row['starttime'])
            process_need(first==last,'PROCESS_CAPTURE_STAT_BINDING')
            comm=part['comm'][0].strip()
            typed[pid]={'kernel_thread':first,'comm_sha256':sha(comm),'comm_label':COMM_LABELS.get(comm,'UNLISTED_COMM_HASH_ONLY'),'fd_count':part['fd_count']}
        process_need(sum(row['fd_count'] for row in typed.values())==count,'PROCESS_CAPTURE_FD_BINDING')
        record.update(details_state='EXACT_ORIGINAL_STAT_COMM_FD_BOUND',details=typed);record.pop('details_reason',None)
    except Exception as error:
        code=error.args[0] if type(error) is ValueError and len(error.args)==1 else None
        reason=code if code in PROCESS_CODES else 'PROCESS_CAPTURE_VALIDATION_FAILED'
        if record['state']=='CAPTURED_FROM_ORIGINAL_RETURN':record['details_reason']=reason
        else:record['reason']=reason
    return record


class SameAttemptCapture(object):
    def __init__(self,outer):
        self.outer=outer;self.entry=None;self.kit=None;self.codes={};self.functions={};self.modules={}
        self.ids={};self.backend=None;self.raw_pair=[];self.raw_process=[];self.samples=[]
        self.calls=0;self.processes=types.SimpleNamespace(calls=0,records=[])
        self.details={};self.detail_failure=None;self.charged=0;self.reason=None;self.cleanup_unknown=False
        self.request=None;self.run_id=None;self.host_calls=0;self.compare_calls=0;self.started=None;self.disarmed=False;self.profile_hook=None
        self.collector_returned=False;self.observation_status={};self.units=();self.masks=()
    def fail(self,code):
        if self.reason is None:self.reason=code
    def stage(self,value):
        process_need(self.entry is None and type(value) is tuple and len(value)==3,'CAPTURE_AUTHENTICATION')
        entry,kit,unused=value
        process_need(type(entry) is types.ModuleType and type(kit) is entry.VerifiedKit and kit.root==KIT and kit.digest==MANIFEST_SHA and
            kit.manifest['kit_source_commit']==SOURCE and len(kit.cache)==249,'CAPTURE_AUTHENTICATION')
        process_need(all(kit.manifest['modules'].get(name)==path and sha(kit.cache[path])==kit.manifest['files'][path] for name,path in MODULES.items()),'CAPTURE_AUTHENTICATION')
        self.entry,self.kit=entry,kit
        self.codes['loader']=entry.CachedSources.exec_module.__code__;self.codes['entry_observe']=entry.VerifiedKit.observe.__code__
    def imported(self,frame):
        loader=frame.f_locals.get('self');module=frame.f_locals.get('module')
        process_need(type(loader) is self.entry.CachedSources and loader.cache is self.kit.cache and loader.root==KIT and
            loader.modules==self.kit.manifest['modules'],'CAPTURE_AUTHENTICATION')
        name=getattr(module,'__name__',None)
        if name not in MODULES:return
        process_need(type(module) is types.ModuleType and module.__loader__ is loader and module.__file__==KIT+'/'+MODULES[name] and
            name in loader.loaded and sha(loader.cache[MODULES[name]])==self.kit.manifest['files'][MODULES[name]],'CAPTURE_AUTHENTICATION')
        process_need(name not in self.modules,'CAPTURE_AUTHENTICATION');self.modules[name]=module
        if name=='observe_epoch7':
            for key,attr in (('host','observe_host'),('observe','observe_with_io')):self.codes[key]=getattr(module,attr).__code__
        elif name=='snapshot_io':
            self.codes['writers']=module.LocalReadOnlyIO.writers.__code__;self.codes['scan']=module.LocalReadOnlyIO._process_scan.__code__
            nested=[x for x in self.codes['scan'].co_consts if isinstance(x,types.CodeType) and x.co_name=='procfile']
            process_need(len(nested)==1,'CAPTURE_AUTHENTICATION');self.codes['procfile']=nested[0]
        else:
            self.codes['collect']=module.collect.__code__;self.codes['compare']=module.validate_writer_transition.__code__
            self.functions['validate']=module.validate_writers;self.functions['digest']=module.d.digest
            self.units=tuple(sorted(module.WRITER_UNITS));self.masks=tuple(sorted(module.LEGACY_MASKS))
    def disarm(self):
        try:
            process_need(sys.getprofile() is self.profile_hook and sys.gettrace() is None,'CAPTURE_PROFILE_CHANGED')
            sys.setprofile(None)
            process_need(sys.getprofile() is None,'CAPTURE_PROFILE_CLEANUP_UNKNOWN');self.disarmed=True
        except BaseException as error:
            self.cleanup_unknown=True
            failure=CaptureAbort('CAPTURE_PROFILE_CLEANUP_UNKNOWN');failure.diagnostic_cleanup_failed=True
            raise failure from error
    def event(self,frame,event,value):
        code=frame.f_code;parent=frame.f_back
        if code is self.outer.run.__code__ and event=='call':
            process_need(self.run_id is None and (frame.f_locals.get('identifier'),frame.f_locals.get('nonce'))==self.request,'CAPTURE_LINEAGE')
            self.run_id=id(frame)
        if event=='return' and code is self.outer.stage_kit.__code__:
            if value is not None:
                process_need(parent is not None and parent.f_code is self.outer.run.__code__ and id(parent)==self.run_id,'CAPTURE_LINEAGE');self.stage(value)
            return
        if self.entry is None:return
        if event=='return' and code is self.codes.get('loader'):
            if frame.f_locals.get('module') is not None:self.imported(frame)
            return
        if code is self.codes.get('host'):
            if event=='call':
                process_need(self.host_calls==0 and parent is not None and parent.f_code is self.codes['entry_observe'] and parent.f_locals.get('self') is self.kit,'CAPTURE_LINEAGE')
                self.host_calls+=1;self.ids['host']=id(frame);self.started=time.monotonic()
            elif event=='return' and id(frame)==self.ids.get('host'):
                if self.started is not None and time.monotonic()-self.started>600:self.fail('CAPTURE_TIME_BOUND')
                if type(value) is dict:
                    for key in ('kind','failure_code','policy_sha256','snapshot_sha256'):
                        item=value.get(key)
                        if item is None or type(item) is str:self.observation_status[key]=item
                if type(value) is dict:self.disarm()
                else:
                    try:self.disarm()
                    except BaseException:self.cleanup_unknown=True;self.fail('CAPTURE_PROFILE_CLEANUP_UNKNOWN')
            return
        if self.started is None:return
        if time.monotonic()-self.started>600:
            self.fail('CAPTURE_TIME_BOUND');self.disarm();raise Deadline()
        if self.reason is not None:return
        if code is self.codes.get('observe') and event=='call':
            process_need(parent is not None and id(parent)==self.ids.get('host'),'CAPTURE_LINEAGE')
            self.ids['observe']=id(frame);self.backend=frame.f_locals.get('io')
            process_need(type(self.backend) is self.modules['observe_epoch7'].ObservationIO,'CAPTURE_LINEAGE')
        elif code is self.codes.get('collect'):
            if event=='call':
                process_need(parent is not None and id(parent)==self.ids.get('observe') and frame.f_locals.get('io') is self.backend,'CAPTURE_LINEAGE');self.ids['collect']=id(frame)
            elif event=='return' and id(frame)==self.ids.get('collect'):
                self.collector_returned=type(value) is tuple and len(value)==2
                if not self.raw_pair and 'before_writers' in frame.f_locals:self.raw_pair=[frame.f_locals['before_writers']]
        elif code is self.codes.get('compare') and event=='call':
            process_need(parent is not None and id(parent)==self.ids.get('collect') and self.compare_calls==0,'CAPTURE_LINEAGE')
            process_need(frame.f_locals.get('before') is parent.f_locals.get('before_writers') and frame.f_locals.get('after') is parent.f_locals.get('after_writers'),'CAPTURE_LINEAGE')
            self.compare_calls+=1;self.raw_pair=[frame.f_locals.get('before'),frame.f_locals.get('after')]
        elif code is self.codes.get('writers'):
            if event=='call':
                process_need(parent is not None and id(parent)==self.ids.get('collect') and frame.f_locals.get('self') is self.backend,'CAPTURE_LINEAGE')
                process_need(self.calls<2,'CAPTURE_CALL_BOUND');self.calls+=1;self.ids['writers']=id(frame)
            elif event=='return' and id(frame)==self.ids.get('writers'):self.ids.pop('writers',None)
        elif code is self.codes.get('scan'):
            if event=='call':
                process_need(parent is not None and id(parent)==self.ids.get('writers') and frame.f_locals.get('self') is self.backend,'CAPTURE_LINEAGE')
                process_need(self.processes.calls<2,'CAPTURE_CALL_BOUND');self.processes.calls+=1;self.ids['scan']=id(frame);self.details={};self.detail_failure=None
            elif event=='return' and id(frame)==self.ids.get('scan'):
                self.raw_process.append((frame.f_locals.get('result'),frame.f_locals.get('fd_count'),value,self.details,self.detail_failure))
                self.details={};self.ids.pop('scan',None)
        elif code is self.codes.get('procfile') and event=='return' and self.detail_failure is None:
            if parent is None or id(parent)!=self.ids.get('scan') or parent.f_code is not self.codes['scan'] or parent.f_locals.get('self') is not self.backend:return
            name=frame.f_locals.get('name')
            if name not in ('stat','comm'):return
            pid=parent.f_locals.get('pid')
            if type(pid) is not str or len(pid)>10 or type(value) is not bytes or len(value)>(65536 if name=='stat' else 256):self.detail_failure='PROCESS_CAPTURE_DETAIL_SCHEMA';return
            self.charged+=len(value)
            if self.charged>MAX_PROC_CAPTURE or (pid not in self.details and len(self.details)>=65536):self.detail_failure='PROCESS_CAPTURE_DETAIL_BOUND';return
            part=self.details.setdefault(pid,{'stat':[],'comm':[]})
            if len(part[name])>=(2 if name=='stat' else 1):self.detail_failure='PROCESS_CAPTURE_DETAIL_SCHEMA';return
            part[name].append(value)
            if name=='stat' and len(part[name])==2:
                names=parent.f_locals.get('fd_names');part['fd_count']=len(names) if type(names) is list else None
    def hook(self,frame,event,value):
        try:self.event(frame,event,value)
        except (KeyboardInterrupt,SystemExit):raise
        except Exception as error:
            self.fail(error.args[0] if type(error) is ValueError and len(error.args)==1 and error.args[0] in CAPTURE_CODES else 'CAPTURE_SCHEMA')
            if getattr(error,'diagnostic_cleanup_failed',False):self.cleanup_unknown=True
            try:self.disarm()
            except BaseException:
                if event=='return' and value is None:self.cleanup_unknown=True
                else:raise
    def invoke(self,identifier,nonce):
        process_need(sys.getprofile() is None and sys.gettrace() is None,'PROCESS_CAPTURE_PROFILE_PRESENT')
        primary=None;self.profile_hook=self.hook;self.request=(identifier,nonce)
        try:
            sys.setprofile(self.profile_hook)
            return self.outer.run(identifier,nonce,True,True)
        except BaseException as error:primary=error;raise
        finally:
            failed=False
            try:
                current=sys.getprofile()
                failed=(current is not None if self.disarmed else current is not self.profile_hook) or sys.gettrace() is not None
            except BaseException:failed=True
            try:sys.setprofile(None)
            except BaseException:failed=True
            try:failed=failed or sys.getprofile() is not None
            except BaseException:failed=True
            if failed:
                self.cleanup_unknown=True;self.fail('CAPTURE_PROFILE_CLEANUP_UNKNOWN')
                if primary is not None:primary.diagnostic_cleanup_failed=True
    def projection(self):
        try:
            process_need(self.reason is None,'CAPTURE_SCHEMA')
            process_need(len(self.raw_pair)<=2 and len(self.raw_process)<=2,'CAPTURE_CALL_BOUND')
            for row in self.raw_pair:
                self.functions['validate'](row);self.samples.append(json.loads(canonical(row).decode('ascii')))
            for row in self.raw_process:self.processes.records.append(validate_process(row,self.functions['digest']))
            result=project(self,self.units,self.masks)
            result.update(capture_state='COMPLETE' if len(self.samples)==2 else 'UNKNOWN_NOT_REACHED',collector_returned=self.collector_returned,comparison_reached=self.compare_calls==1)
            public=public_codes(self.kit.cache) if self.kit is not None else frozenset()
            result['original_core_status']={key:(value if value is None or (key.endswith('_sha256') and re.fullmatch('[0-9a-f]{64}',value)) or value in public else 'REDACTED_UNLISTED_CODE') for key,value in self.observation_status.items()}
            return result
        except Exception as error:
            return {'capture_state':'UNKNOWN','reason':self.reason or 'CAPTURE_VALIDATION_FAILED','successful_validated_samples':len(self.samples),'attempted_call_count':self.calls,'attempted_scan_count':self.processes.calls,'collector_returned':self.collector_returned}
        finally:
            self.raw_pair[:]=[];self.raw_process[:]=[];self.details.clear();self.backend=None


def envelope(original,capture,identifier,nonce,prior):
    projection=capture.projection()
    result={'schema':1,'kind':'R6_SAME_ATTEMPT_CONTINUATION_CAPTURE','observation_id':identifier,'nonce':nonce,
        'kit_source_commit':SOURCE,'kit_manifest_sha256':MANIFEST_SHA,'outer_commit':OUTER_COMMIT,
        'prior_failed_attempt':prior,'original_result':original,'same_attempt_writer_capture':projection,
        'supplemental_complete':projection['capture_state']=='COMPLETE' and not capture.cleanup_unknown,
        'cleanup_unknown':capture.cleanup_unknown,'automatic_retry':False,'additional_proc_reads':0,
        'timing_perturbation':'POSSIBLE','production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED'}
    observed=original.get('observation',{}) if type(original) is dict else {}
    result['durable_bindings']={key:(original.get('diagnostic_receipt_sha256') if key=='diagnostic_receipt_sha256' else observed.get(key)) for key in ('diagnostic_receipt_sha256','private_file_sha256','snapshot_sha256','policy_sha256')}
    result['success']=type(original) is dict and original.get('success') is True and not capture.cleanup_unknown
    raw=canonical(result,MAX_OUTPUT);return raw.decode('ascii'),0 if result['success'] else 2


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--observation-id',required=True);parser.add_argument('--nonce',required=True)
    parser.add_argument('--execute-reviewed-diagnostic',action='store_true');parser.add_argument('--execute-reviewed-probe',action='store_true')
    args=parser.parse_args(argv);original=None;capture=None;prior=None;stage='PRECONDITIONS';emission_started=False
    try:
        need(os.geteuid()==os.getegid()==0 and socket.gethostname().split('.')[0]==HOST and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
        need(args.execute_reviewed_diagnostic and args.execute_reviewed_probe and re.fullmatch('[0-9a-f]{16}',args.observation_id) and re.fullmatch('[0-9a-f]{32}',args.nonce) and args.observation_id!=FAILED_ID and args.nonce!=FAILED_NONCE)
        stage='PRIOR_FAILED_HOLD';prior=prior_hold();stage='ORIGINAL_OUTER_AUTHENTICATION';outer=frozen_outer()
        capture=SameAttemptCapture(outer);stage='ORIGINAL_CONTINUATION_ONCE';original=capture.invoke(args.observation_id,args.nonce)
        stage='SUPPLEMENTAL_PROJECTION'
        with bounded(10):
            text,code=envelope(original,capture,args.observation_id,args.nonce,prior);emission_started=True;print(text,flush=True)
        return code
    except BaseException as error:
        result={'schema':1,'kind':'R6_SAME_ATTEMPT_CONTINUATION_CAPTURE','stage':stage,'success':False,
            'original_result':original,'prior_failed_attempt':prior,'observation_id':args.observation_id,'nonce':args.nonce,
            'failure':error_info(error,set(CAPTURE_CODES)|set(PROCESS_CODES)|set(CLEANUP)),
            'cleanup_unknown':getattr(error,'diagnostic_cleanup_failed',False) is True or (capture is not None and capture.cleanup_unknown),
            'automatic_retry':False,'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        # A failed bounded emission is not retried on a potentially blocked pipe.
        if emission_started:return 2
        try:
            with bounded(10):print(canonical(result,MAX_OUTPUT).decode('ascii'),flush=True)
        except BaseException:pass
        return 2

if __name__=='__main__':sys.exit(main())
