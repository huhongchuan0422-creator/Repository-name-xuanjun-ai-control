"""Export one fixed saved finite-probe proof for independent review; no collection."""
import ast,base64,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,types,zlib
HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
KIT=BASE+'/epoch7-recovery-candidate-r6'
ENTRY_SHA='c56ba6d8281eeb1ecc062875a7f13defc223f6d5dd073a4490d1602b8cf1d3a5'
MANIFEST_SHA='70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc'
FILE='epoch7-observation-1311b9e9fa97cfd4.private.json'
OBS_SHA='b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246'
RECEIPT='epoch7-diagnostic-1311b9e9fa97cfd4.private.json'
RECEIPT_SHA='d91613287b4bf99dd250ed26ea71d84f93bdae027b367d544c387d99a7a054f1'
NONCE='2b2e5de048f23e85f3c022002fba7510'
SOURCE='0c8a0f2a97da0c3f00f53659cd6ef7fc7d4ec3ba'
def need(value):
    if not value:raise ValueError('DIAGNOSTIC_BOUNDARY')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def stamp(i):return tuple(getattr(i,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))


class Deadline(KeyboardInterrupt):pass


@contextlib.contextmanager
def bounded():
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0));previous=signal.getsignal(signal.SIGALRM)
    def expired(*unused):raise Deadline()
    signal.signal(signal.SIGALRM,expired);primary=None
    try:
        signal.setitimer(signal.ITIMER_REAL,60,1);yield
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


PREP=BASE+'/epoch7-preparation-candidate-r6-contracts'
PROBE_ROOT='/run/xj-p2-proof-'+NONCE
PROBE_SHA='b6d0676992cb973d39f31dc652ea6aecf2d9747964a50f0ede23ed76ca1088b5'
MAX_OUTPUT=524288
DROPINS={'reread': 'EXACT_PRE_POST', 'roots': {'/etc/systemd/system/xuanjun-ledger.socket.d': {'files': {}, 'metadata': None, 'parent_metadata': {'ctime_ns': 1791988264717936099, 'dev': 64771, 'gid': 0, 'ino': 785234, 'mode': 493, 'mtime_ns': 1791988264717936099, 'nlink': 14, 'size': 4096, 'uid': 0}, 'present': False}, '/run/systemd/system/xuanjun-ledger.socket.d': {'files': {}, 'metadata': None, 'parent_metadata': {'ctime_ns': 1792054494058440476, 'dev': 25, 'gid': 0, 'ino': 3, 'mode': 493, 'mtime_ns': 1792054494058440476, 'nlink': 3, 'size': 80, 'uid': 0}, 'present': False}, '/usr/lib/systemd/system/xuanjun-ledger.socket.d': {'files': {}, 'metadata': None, 'parent_metadata': {'ctime_ns': 1791957693105388758, 'dev': 64771, 'gid': 0, 'ino': 1053327, 'mode': 493, 'mtime_ns': 1791957693105388758, 'nlink': 29, 'size': 16384, 'uid': 0}, 'present': False}}, 'schema': 1, 'unit': 'xuanjun-ledger.socket'}
SOURCE_MANIFEST={'files': {'epoch7_prepare.py': '44b181cac0da6da287bd98455a0d49fc4285a83d8a58c875bf1af98ebf49295d', 'epoch7_prepare_data.py': '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 'epoch7_topology_projection.py': 'f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854'}, 'schema': 1}
EXPECTED_BODY={'decision': 'ACCEPTED_EXACT_EPOCH7_ROOT_MANAGER_TOPOLOGY_ONLY', 'evidence_records_sha256': 'e26b2333f78a76e94261449d83b05d0467f930dc9c17e8963cd70b2735e3852e', 'exclusive_delivery_accepted': True, 'observation_sha256': '2536b5fddff1e918222a10fdd97846832af82e3b2f14919ce150ca5bd6ef3820', 'preparation_source_manifest_sha256': 'c169a9885c190660b449c3a8358f585bed56d0da064a570670115ba0f872563c', 'probe_input_sha256': '71817761e1b5c805140bf340a214998898a74227dc24aed4c5e1edf3947d548b', 'probe_policy_sha256': '7083a3ba187606702dd21b1b390948ed1c348897219082cf2e4aa3a8962ec5be', 'probe_receipt_sha256': 'b6d0676992cb973d39f31dc652ea6aecf2d9747964a50f0ede23ed76ca1088b5', 'production_acceptance': 'PENDING', 'production_resume_authorized': False, 'recovery_kit_manifest_sha256': '70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc', 'reviewer': 'CHATGPT_NATIVE_TASK5', 'runtime_manifest_sha256': '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa', 'schema': 1, 'socket_dropins_sha256': '7412f8e70c998cf6fd8cedcbc444c0715747ff7421e49910c08d66cec43df7b7', 'source_files': {'deploy/integration-manifest.json': '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa', 'node_sqlite_probe.py': 'c2f580021c36e72574e3a67201c90a9fc09f22ee7ede396650dc970757151f7a', 'probe_driver.py': '90f203a4aafe591fa508a444847557b8115df79bbad4e4096bd1cc371a935dbd', 'probe_helpers.py': '0b62410b57193eb7ce984f5002bf71e1c31242e37e58f6296ad74da247cc1468'}, 'systemd_version_evidence': 'PINNED_DRIVER_CHECK_HOST_BEFORE_RECEIPT', 'topology_sha256': '9cc4fa1ccc90cd2f950283b3ff6a0ae22350f21b2163edcae4643ff76f22757c', 'transaction_id': 'c529c379-9341-4510-8384-fc6be1e412e5'}
OBS_CANONICAL_SHA='2536b5fddff1e918222a10fdd97846832af82e3b2f14919ce150ca5bd6ef3820'
EXPECTED_BODY_SHA='cc4764bdab37c3bedad9171e72aafd86b59812e82b6acdf196a39a1257a6df36'

PHASE='INPUT_VALIDATION'
SAFE_CODES={'DIAGNOSTIC_BOUNDARY'}
SAFE_FILES={}

def remember_source(label,path,raw):
    SAFE_FILES[path]=label
    for item in ast.walk(ast.parse(raw)):
        if isinstance(item,ast.Str) and type(item.s) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',item.s):
            SAFE_CODES.add(item.s)
            for prefix in ('TOPOLOGY_','NODE_SQLITE_','EPOCH7_KIT_','EXPORT_','EXPORT_SCHEMA_'):
                if len(prefix+item.s)<=160:SAFE_CODES.add(prefix+item.s)


def error_summary(error):
    classes=('ValueError','TypeError','KeyError','RuntimeError','OSError','FileNotFoundError',
             'PermissionError','KeyboardInterrupt','SystemExit','Deadline')
    result={'exception_class':type(error).__name__ if type(error).__name__ in classes else 'UNLISTED_CLASS',
            'code':'UNLISTED_CODE','public_source_frames':[]}
    if type(error) is ValueError and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in SAFE_CODES:
        result['code']=error.args[0]
    tb=error.__traceback__;count=0
    while tb is not None and count<64:
        name=tb.tb_frame.f_code.co_filename
        if name in SAFE_FILES:result['public_source_frames'].append({'source':SAFE_FILES[name],'line':tb.tb_lineno})
        tb=tb.tb_next;count+=1
    return result


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


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
    need(receipt.get('success') is True and observed.get('probe_observations_complete') is True)
    need(value.get('kind')=='EPOCH7_OBSERVATION_ONLY_UNREVIEWED' and value.get('install_admission')=='NOT_GRANTED')
    need(sha(canonical(value))==OBS_CANONICAL_SHA and value.get('finite_probe',{}).get('nonce')==NONCE)
    return value,receipt


def read_sources(entry):
    result={}
    with entry.DescriptorTree(PREP) as tree:
        for name,pin in sorted(SOURCE_MANIFEST['files'].items()):
            raw=tree.read(name,1048576);need(sha(raw)==pin);result[name]=raw
        tree.recheck()
    need(sha(canonical(SOURCE_MANIFEST))==EXPECTED_BODY['preparation_source_manifest_sha256'])
    return result


def read_probe(entry,observation):
    binding=observation['finite_probe']['result']['created_receipt']
    need(binding['path']==PROBE_ROOT+'/created-receipt.json' and binding['sha256']==PROBE_SHA)
    with entry.DescriptorTree(PROBE_ROOT) as tree:
        before=os.stat('created-receipt.json',dir_fd=tree.fd,follow_symlinks=False)
        raw=tree.read('created-receipt.json',131072,private=True)
        after=os.stat('created-receipt.json',dir_fd=tree.fd,follow_symlinks=False)
        metadata={k:getattr(after,'st_'+k) for k in ('dev','ino','uid','gid','nlink','size','mtime_ns','ctime_ns')}
        metadata['mode']=stat.S_IMODE(after.st_mode)
        need(stamp(before)==stamp(after) and sha(raw)==PROBE_SHA and metadata==binding['metadata'])
        tree.recheck()
    receipt=entry.decode(raw)
    need(canonical(receipt)+b'\n'==raw)
    return raw,metadata,receipt


def source_buffers(kit,topology):
    result={name:kit.cache['helpers/'+name] for name in topology.SOURCE_PINS if name!='deploy/integration-manifest.json'}
    result['deploy/integration-manifest.json']=kit.cache['xuanjun-p2-package/deploy/integration-manifest.json']
    return result


# Filled only with the exact separately reviewed schema source at freeze.
SCHEMA_BYTES=23175
SCHEMA_SHA='4b3560afaebfb62fc7dc18d7648f0131a4d6756a5c971ea5469b7741d32126e8'
SCHEMA_ZLIB_BASE64='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'


def load_schema():
    need(0<SCHEMA_BYTES<=131072 and re.fullmatch('[0-9a-f]{64}',SCHEMA_SHA))
    packed=base64.b64decode(SCHEMA_ZLIB_BASE64,validate=True);need(len(packed)<=65536)
    decoder=zlib.decompressobj();raw=decoder.decompress(packed,SCHEMA_BYTES+1)
    need(len(raw)==SCHEMA_BYTES and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and sha(raw)==SCHEMA_SHA)
    module=types.ModuleType('fixed_export_schema')
    remember_source('FIXED_EXPORT_SCHEMA','<fixed-export-schema>',raw)
    exec(compile(raw,'<fixed-export-schema>','exec',dont_inherit=True),module.__dict__)
    return module


def export_value(observation,probe_raw,metadata,receipt,kit,topology,schema):
    need(sha(canonical(DROPINS))==EXPECTED_BODY['socket_dropins_sha256'])
    need(sha(canonical(EXPECTED_BODY))==EXPECTED_BODY_SHA)
    proposal=topology.project_topology(observation,probe_raw,metadata,MANIFEST_SHA,
        source_buffers(kit,topology),DROPINS,EXPECTED_BODY['preparation_source_manifest_sha256'])
    need(canonical(proposal['expected_review_body'])==canonical(EXPECTED_BODY))
    need(proposal['topology_sha256']==EXPECTED_BODY['topology_sha256'] and
         proposal['bindings']['evidence_records_sha256']==EXPECTED_BODY['evidence_records_sha256'])
    schema.validate_export(observation['finite_probe'],receipt,metadata,topology)
    proof_input={name:observation[name] for name in ('snapshot_sha256','unit_metadata_sha256')}
    proof_input['retained_resource_sha256']=observation['snapshot']['retained_resource_sha256']
    need(sha(canonical(proof_input))==EXPECTED_BODY['probe_input_sha256'])
    evidence={'events':receipt['events'],'resources':receipt['resources'],
              'socket_identity':receipt['socket_identity'],'socket_dropins':DROPINS}
    need(sha(canonical(evidence))==EXPECTED_BODY['evidence_records_sha256'])
    result={'schema':1,'kind':'SAVED_FINITE_PROBE_REVIEW_EVIDENCE_NO_APPROVAL',
        'state':'COMPLETE_SAVED_DATA_EXPORT','observation_id':'1311b9e9fa97cfd4','nonce':NONCE,
        'bindings':proposal['bindings'],'observation_file_sha256':OBS_SHA,
        'diagnostic_receipt_sha256':RECEIPT_SHA,'observation_full_canonical_sha256':OBS_CANONICAL_SHA,
        'whole_observation_validation':'EXACT_PRIVATE_BYTES_AUTHENTICATED_AND_FROZEN_TOPOLOGY_PROJECTOR_VALIDATED'
        ,'ancillary_acceptance':'PRIOR_SUCCESSFUL_PREPARATION_REPORTED_NOT_RERUN_BY_EXPORTER',
        'local_recomputation_scope':['probe_policy_sha256','probe_input_sha256','probe_receipt_sha256',
            'evidence_records_sha256','socket_dropins_sha256','topology_sha256','expected_review_body_sha256'],
        'finite_probe':observation['finite_probe'],'probe_receipt':receipt,'probe_receipt_metadata':metadata,
        'probe_receipt_raw_base64':base64.b64encode(probe_raw).decode('ascii'),
        'probe_receipt_raw_form':'EXACT_CANONICAL_JSON_PLUS_LF','probe_input':proof_input,
        'socket_dropins':DROPINS,'socket_dropins_provenance':'ORIGINAL_RECORDED_PROPOSAL_NOT_FRESH_COLLECTION',
        'preparation_sources':SOURCE_MANIFEST,'export_schema_sha256':SCHEMA_SHA,
        'topology':proposal['topology'],'topology_raw_utf8':proposal['topology_raw'].decode('utf-8'),
        'topology_bytes':len(proposal['topology_raw']),'topology_sha256':proposal['topology_sha256'],
        'unsigned_expected_review_body':proposal['expected_review_body'],'expected_review_body_sha256':EXPECTED_BODY_SHA,
        'collection':'NOT_RUN','probe':'NOT_RUN','proposal_operation':'NOT_RUN',
        'approval_fetch':'NOT_RUN','install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    need(len(canonical(result))<=MAX_OUTPUT)
    return result


def load_entry(raw):
    need(sha(raw)==ENTRY_SHA)
    entry=types.ModuleType('verified_saved_evidence_entry');entry.__file__=KIT+'/epoch7_recovery_entry.py'
    exec(compile(raw,entry.__file__,'exec',dont_inherit=True),entry.__dict__)
    return entry


def main():
    global PHASE
    frozen_cleanup_uncertain=False;emission_started=False
    try:
        need(os.geteuid()==os.getegid()==0 and socket.gethostname().split('.')[0]==HOST)
        need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
        with bounded():
            PHASE='ENTRY_AUTHENTICATION'
            raw=entry_bytes();remember_source('FROZEN_ENTRY',KIT+'/epoch7_recovery_entry.py',raw);entry=load_entry(raw)
            frozen_cleanup_uncertain=True
            PHASE='VERIFY_KIT'
            kit=entry.verify_kit(KIT,MANIFEST_SHA)
            for name,body in kit.cache.items():
                if name.endswith('.py'):remember_source('KIT:'+name,KIT+'/'+name,body)
            need(kit.manifest['kit_source_commit']==SOURCE)
            PHASE='READ_SAVED_OBSERVATION_AND_DIAGNOSTIC'
            observation,diagnostic=read_pair(entry)
            PHASE='READ_PREPARATION_SOURCES'
            sources=read_sources(entry)
            for name,body in sources.items():remember_source('PREPARATION:'+name,PREP+'/'+name,body)
            PHASE='READ_SAVED_PROBE_RECEIPT'
            probe_raw,metadata,receipt=read_probe(entry,observation)
            PHASE='LOAD_FIXED_EXPORT_SCHEMA'
            schema=load_schema()
            with kit.imports():
                topology=types.ModuleType('verified_saved_topology_projection')
                source=sources['epoch7_topology_projection.py']
                exec(compile(source,PREP+'/epoch7_topology_projection.py','exec',dont_inherit=True),topology.__dict__)
                PHASE='PURE_PROJECTION_AND_STRICT_EXPORT_SCHEMA'
                result=export_value(observation,probe_raw,metadata,receipt,kit,topology,schema)
            # Repeat only the same fixed protected reads and source authentication.
            PHASE='FINAL_FIXED_RECHECKS'
            again,again_diagnostic=read_pair(entry)
            need(canonical(again)==canonical(observation) and canonical(again_diagnostic)==canonical(diagnostic))
            again_raw,again_meta,unused=read_probe(entry,again)
            need(again_raw==probe_raw and again_meta==metadata and read_sources(entry)==sources)
            entry.verify_kit(KIT,MANIFEST_SHA)
            frozen_cleanup_uncertain=False
            encoded=canonical(result);need(len(encoded)<=MAX_OUTPUT)
        # Separate finite delivery budget; never retry a possibly partial write.
        with bounded():
            PHASE='BOUNDED_OUTPUT'
            emission_started=True
            print(encoded.decode('utf-8'),flush=True)
        return 0
    except BaseException as error:
        if emission_started:return 2
        failure={'schema':1,'kind':'SAVED_FINITE_PROBE_REVIEW_EVIDENCE_NO_APPROVAL','state':'HOLD',
            'failure_code':'EXPORT_DEADLINE' if isinstance(error,Deadline) else 'EXPORT_SCOPE_HASH_SCHEMA_OR_BOUNDARY_FAILED',
            'failed_phase':PHASE,'error':error_summary(error),
            'cleanup_unknown':frozen_cleanup_uncertain or getattr(error,'diagnostic_cleanup_failed',False) is True,
            'errno':error.errno if isinstance(error,OSError) and type(error.errno) is int else None,
            'collection':'NOT_RUN','probe':'NOT_RUN','proposal_operation':'NOT_RUN',
            'approval_fetch':'NOT_RUN','install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        try:
            with bounded():print(json.dumps(failure,sort_keys=True),flush=True)
        except BaseException:pass
        return 2

if __name__=='__main__':sys.exit(main())
