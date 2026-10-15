"""Offline subset verification. No whole-observation reconstruction or approval."""
import base64,hashlib,io,json,pathlib,sys,tarfile,types
ARCHIVE_SHA='600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83'
ARCHIVE_BYTES=1032979
EXPORTER_SHA='dd1f6c2a701dbf849ff5e3361e226b5be505cd72d65aa3d58f6b0a1e68ee30fc'
TOPOLOGY_SHA='f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854'

def need(value):
    if not value:raise ValueError('OFFLINE_EVIDENCE_BINDING_FAILED')

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()

def verify_packet(packet,topology,schema):
    """Pure verifier; full observation hash is a binding, never recomputed here."""
    need(type(packet) is dict and packet['state']=='COMPLETE_SAVED_DATA_EXPORT' and packet['kind']=='SAVED_FINITE_PROBE_REVIEW_EVIDENCE_NO_APPROVAL')
    attempt=packet['finite_probe'];receipt=packet['probe_receipt'];metadata=packet['probe_receipt_metadata']
    schema.validate_export(attempt,receipt,metadata,topology)
    raw=base64.b64decode(packet['probe_receipt_raw_base64'],validate=True)
    need(raw==canonical(receipt)+b'\n' and len(raw)==metadata['size'])
    bindings=packet['bindings'];policy=topology.probe.validate_policy(attempt['policy'])
    computed={'probe_policy_sha256':sha(canonical(policy)+b'\n'),
        'probe_input_sha256':sha(canonical(packet['probe_input'])),'probe_receipt_sha256':sha(raw),
        'socket_dropins_sha256':sha(canonical(topology.validate_socket_dropins(packet['socket_dropins'])))}
    need(set(packet['probe_input'])=={'snapshot_sha256','retained_resource_sha256','unit_metadata_sha256'})
    for value in packet['probe_input'].values():topology.sha(value)
    computed['evidence_records_sha256']=sha(canonical({'events':receipt['events'],
        'resources':receipt['resources'],'socket_identity':receipt['socket_identity'],
        'socket_dropins':packet['socket_dropins']}))
    # The original projector derives only these public values after all case,
    # resource, server and cross-binding checks repeated by the strict schema.
    manager=next(row['evidence'] for row in attempt['result']['cases'][0]['readpaths'] if row['path_class']=='manager-process')
    derived={'schema':1,'purpose':'ROOT_MANAGER_SHARED_INIT_PROOF',
        'creator':{'pid':1,'uid':0,'gid':int(manager['status']['Gid'].split()[0]),
            'exe':next(row['path'] for row in policy['public_files'] if row['path']!='/usr/bin/systemctl'),
            'cgroup_sha256':manager['cgroup_sha256'],'pid_namespace_role':'SYSTEM_INIT_SHARED_WITH_CLIENTS'},
        'endpoint_identity':{key:receipt['socket_identity'][key] for key in ('uid','gid','mode')},
        'clients':{role:{'same_pid_namespace':True,'same_proc_namespace':True,'readpaths_verified':True}
                   for role in ('broker','dashboard','callback','native')},
        'exclusive_delivery_reviewed':True,'systemd_version':239,
        'evidence_records_sha256':computed['evidence_records_sha256']}
    topology._topology(derived)
    topology_raw=canonical(derived)+b'\n';computed['topology_sha256']=sha(topology_raw)
    need(derived==packet['topology'] and topology_raw==packet['topology_raw_utf8'].encode('utf-8') and len(topology_raw)==packet['topology_bytes'])
    need(computed['topology_sha256']==packet['topology_sha256'])
    for name,value in computed.items():
        if name!='topology_sha256':need(bindings[name]==value)
    need(computed['probe_policy_sha256']==attempt['policy_sha256']==receipt['policy_sha256'])
    need(computed['probe_input_sha256']==policy['node_sqlite']['probe_input_sha256'])
    need(computed['probe_receipt_sha256']==attempt['result']['created_receipt']['sha256'])
    need(canonical(metadata)==canonical(attempt['result']['created_receipt']['metadata']))
    need(sha(canonical(packet['preparation_sources']))==bindings['preparation_source_manifest_sha256'])
    body=topology.expected_review_body(computed['topology_sha256'],bindings)
    need(canonical(body)==canonical(packet['unsigned_expected_review_body']))
    computed['expected_review_body_sha256']=sha(canonical(body))
    need(computed['expected_review_body_sha256']==packet['expected_review_body_sha256'])
    need(bindings['observation_sha256']==packet['observation_full_canonical_sha256'])
    return {'state':'PASS_EXPORTED_SUBSET_ONLY','computed':computed,
        'whole_observation_recomputed':False,'whole_observation_binding':bindings['observation_sha256'],
        'full_host_observation_authentication':'REPORTED_BY_HASH_PINNED_EXPORTER',
        'independent_mechanism_review':'STILL_REQUIRED','approval_issued':False,'production_resume':'NOT_EXECUTED'}


def validate_packet_pins(packet,exporter):
    fields={'schema','kind','state','observation_id','nonce','bindings','observation_file_sha256',
        'diagnostic_receipt_sha256','observation_full_canonical_sha256','whole_observation_validation',
        'ancillary_acceptance','local_recomputation_scope','finite_probe','probe_receipt','probe_receipt_metadata',
        'probe_receipt_raw_base64','probe_receipt_raw_form','probe_input','socket_dropins','socket_dropins_provenance',
        'preparation_sources','export_schema_sha256','topology','topology_raw_utf8','topology_bytes','topology_sha256',
        'unsigned_expected_review_body','expected_review_body_sha256','collection','probe','proposal_operation',
        'approval_fetch','install_admission','production_resume'}
    need(type(packet) is dict and set(packet)==fields and type(packet['schema']) is int and packet['schema']==1)
    need(packet['kind']=='SAVED_FINITE_PROBE_REVIEW_EVIDENCE_NO_APPROVAL' and packet['state']=='COMPLETE_SAVED_DATA_EXPORT')
    need(canonical(packet['unsigned_expected_review_body'])==canonical(exporter.EXPECTED_BODY))
    need(packet['expected_review_body_sha256']==exporter.EXPECTED_BODY_SHA and
         packet['observation_file_sha256']==exporter.OBS_SHA and packet['diagnostic_receipt_sha256']==exporter.RECEIPT_SHA and
         packet['observation_full_canonical_sha256']==exporter.OBS_CANONICAL_SHA and
         packet['observation_id']=='1311b9e9fa97cfd4' and packet['nonce']==exporter.NONCE and
         packet['export_schema_sha256']==exporter.SCHEMA_SHA)
    for name in ('collection','probe','proposal_operation','approval_fetch'):need(packet[name]=='NOT_RUN')
    need(packet['install_admission']=='NOT_GRANTED' and packet['production_resume']=='NOT_EXECUTED')
    need(packet['whole_observation_validation']=='EXACT_PRIVATE_BYTES_AUTHENTICATED_AND_FROZEN_TOPOLOGY_PROJECTOR_VALIDATED' and
         packet['ancillary_acceptance']=='PRIOR_SUCCESSFUL_PREPARATION_REPORTED_NOT_RERUN_BY_EXPORTER' and
         packet['socket_dropins_provenance']=='ORIGINAL_RECORDED_PROPOSAL_NOT_FRESH_COLLECTION' and
         packet['probe_receipt_raw_form']=='EXACT_CANONICAL_JSON_PLUS_LF')
    need(canonical(packet['socket_dropins'])==canonical(exporter.DROPINS) and
         canonical(packet['preparation_sources'])==canonical(exporter.SOURCE_MANIFEST))
    need(packet['local_recomputation_scope']==['probe_policy_sha256','probe_input_sha256','probe_receipt_sha256',
        'evidence_records_sha256','socket_dropins_sha256','topology_sha256','expected_review_body_sha256'])
    need(set(packet['bindings'])==set(exporter.EXPECTED_BODY)-{'schema','reviewer','decision','transaction_id',
        'topology_sha256','exclusive_delivery_accepted','systemd_version_evidence','production_resume_authorized','production_acceptance'})
    for name,value in packet['bindings'].items():need(canonical(value)==canonical(exporter.EXPECTED_BODY[name]))


def read(path,maximum):
    with open(str(path),'rb') as stream:raw=stream.read(maximum+1)
    need(len(raw)<=maximum);return raw


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    need(len(args)==3 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    here=pathlib.Path(__file__).resolve().parent
    source=read(here/'export_saved_evidence.py',262144);need(sha(source)==EXPORTER_SHA)
    exporter=types.ModuleType('verified_public_exporter');exec(compile(source,str(here/'export_saved_evidence.py'),'exec'),exporter.__dict__)
    archive=read(args[1],ARCHIVE_BYTES);need(len(archive)==ARCHIVE_BYTES and sha(archive)==ARCHIVE_SHA)
    files={};prefix='epoch7-recovery-candidate-r6/'
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        for member in tar.getmembers():
            if member.isdir():continue
            need(member.isfile() and member.name.startswith(prefix) and member.size<=33554432)
            name=member.name[len(prefix):];need(name not in files)
            files[name]=tar.extractfile(member).read()
    need(len(files)==250 and sha(files['epoch7_recovery_entry.py'])==exporter.ENTRY_SHA)
    entry=types.ModuleType('offline_verified_entry');entry.__file__='/offline-public-kit/epoch7_recovery_entry.py'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec'),entry.__dict__)
    raw=files.pop(entry.MANIFEST);need(sha(raw)==exporter.MANIFEST_SHA)
    manifest=entry.validate_manifest(entry.decode(raw));need(set(files)==set(manifest['files']))
    for name,data in files.items():need(sha(data)==manifest['files'][name])
    entry.validate_runtime(manifest,files)
    kit=entry.VerifiedKit('/offline-public-kit',manifest,files,exporter.MANIFEST_SHA,raw_manifest=raw)
    topology_raw=read(args[2],1048576);need(sha(topology_raw)==TOPOLOGY_SHA)
    packet=entry.decode(read(args[0],exporter.MAX_OUTPUT));schema=exporter.load_schema()
    validate_packet_pins(packet,exporter)
    with kit.imports():
        topology=types.ModuleType('offline_verified_topology')
        exec(compile(topology_raw,'<verified-topology-projection>','exec'),topology.__dict__)
        result=verify_packet(packet,topology,schema)
        need(result['computed']['topology_sha256']==exporter.EXPECTED_BODY['topology_sha256'] and
             result['computed']['evidence_records_sha256']==exporter.EXPECTED_BODY['evidence_records_sha256'])
    print(json.dumps(result,sort_keys=True));return 0

if __name__=='__main__':sys.exit(main())
