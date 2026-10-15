"""Offline R7 exported-subset verification; hidden observation stays unavailable."""
import base64,hashlib,io,json,pathlib,re,sys,tarfile,types
ARCHIVE_SHA='e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645'
ARCHIVE_BYTES=1041263
EXPORTER_SHA='a436d97072bf0062a94f9ccbd030aef1a08214f12f74645efd12d89d9f464815'

def need(value):
    if not value:raise ValueError('OFFLINE_EVIDENCE_BINDING_FAILED')

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()

def verify_packet(packet,topology,schema):
    """Pure verifier; full observation hash is a binding, never recomputed here."""
    need(type(packet) is dict and packet['state']=='COMPLETE_SAVED_DATA_EXPORT' and packet['kind']=='SAVED_R7_FINITE_PROBE_REVIEW_EVIDENCE_NO_APPROVAL')
    attempt=packet['finite_probe'];receipt=packet['probe_receipt'];metadata=packet['probe_receipt_metadata']
    schema.validate_export(attempt,receipt,metadata,topology)
    raw=base64.b64decode(packet['probe_receipt_raw_base64'],validate=True)
    need(raw==canonical(receipt)+b'\n' and len(raw)==metadata['size'])
    bindings=packet['bindings'];policy=topology.probe.validate_policy(attempt['policy'])
    computed={'probe_policy_sha256':sha(canonical(policy)+b'\n'),
        'probe_input_sha256':sha(canonical(packet['probe_input'])),'probe_receipt_sha256':sha(raw),
        'saved_unit_dropins_sha256':sha(canonical(topology.validate_saved_unit_dropins(packet['saved_unit_dropins'])))}
    need(packet['saved_unit_dropins']['unit_metadata_sha256']==packet['probe_input']['unit_metadata_sha256'])
    need(set(packet['probe_input'])=={'snapshot_sha256','retained_resource_sha256','unit_metadata_sha256'})
    for value in packet['probe_input'].values():topology.sha(value)
    computed['evidence_records_sha256']=sha(canonical({'events':receipt['events'],
        'resources':receipt['resources'],'socket_identity':receipt['socket_identity'],
        'saved_unit_dropins':packet['saved_unit_dropins']}))
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
    need(sha(canonical(packet['saved_projection_sources']))==bindings['saved_projection_source_manifest_sha256'])
    body=topology.expected_review_body(computed['topology_sha256'],bindings)
    need(canonical(body)==canonical(packet['unsigned_expected_review_body']))
    computed['expected_review_body_sha256']=sha(canonical(body))
    need(computed['expected_review_body_sha256']==packet['expected_review_body_sha256'])
    need(bindings['observation_sha256']==packet['observation_full_canonical_sha256'])
    return {'state':'PASS_EXPORTED_SUBSET_ONLY','computed':computed,
        'whole_observation_recomputed':False,'whole_observation_binding':bindings['observation_sha256'],
        'full_host_observation_authentication':'REPORTED_BY_HASH_PINNED_EXPORTER',
        'hidden_observation_provenance':'RAW_FILE_PIN_AND_NORMALIZED_HASH_NOT_RECOMPUTED_FROM_SUBSET',
        'fresh_directory_authority':'NOT_REPRESENTED_BY_SAVED_INVENTORY',
        'independent_mechanism_review':'STILL_REQUIRED','approval_issued':False,'production_resume':'NOT_EXECUTED'}


def validate_packet_pins(packet,exporter,topology):
    fields={'schema','kind','state','observation_id','nonce','bindings','observation_file_sha256',
        'diagnostic_receipt_sha256','observation_full_canonical_sha256','whole_observation_validation',
        'core_policy_sha256','snapshot_sha256','ancillary_acceptance','local_recomputation_scope',
        'finite_probe','probe_receipt','probe_receipt_metadata','probe_receipt_raw_base64','probe_receipt_raw_form',
        'probe_input','saved_unit_dropins','saved_unit_dropins_provenance','saved_projection_sources',
        'export_schema_sha256','topology','topology_raw_utf8','topology_bytes','topology_sha256',
        'unsigned_expected_review_body','expected_review_body_sha256','fresh_directory_authority',
        'final_plan_preparation','collection','probe','proposal_operation','approval_fetch','install_admission','production_resume'}
    need(type(packet) is dict and set(packet)==fields and type(packet['schema']) is int and packet['schema']==2)
    need(packet['kind']=='SAVED_R7_FINITE_PROBE_REVIEW_EVIDENCE_NO_APPROVAL' and packet['state']=='COMPLETE_SAVED_DATA_EXPORT')
    need(packet['observation_file_sha256']==exporter.OBS_SHA and packet['diagnostic_receipt_sha256']==exporter.RECEIPT_SHA and
         packet['observation_id']==exporter.OBSERVATION_ID and packet['nonce']==exporter.NONCE and
         packet['core_policy_sha256']==exporter.POLICY_SHA and packet['snapshot_sha256']==exporter.SNAPSHOT_SHA and
         packet['export_schema_sha256']==exporter.SOURCE_MANIFEST['files']['export_schema.py'])
    need(packet['probe_input']['snapshot_sha256']==exporter.SNAPSHOT_SHA)
    for name in ('collection','probe','approval_fetch'):need(packet[name]=='NOT_RUN')
    need(packet['proposal_operation']=='PURE_SAVED_PROJECTION_ONLY' and packet['install_admission']=='NOT_GRANTED' and
         packet['production_resume']=='NOT_EXECUTED' and packet['final_plan_preparation']=='PENDING_SEPARATE_REVIEWED_FRESH_CHECKS')
    need(packet['whole_observation_validation']=='EXACT_PRIVATE_BYTES_AUTHENTICATED_AND_GENUINE_R7_PURE_VALIDATORS_PASSED' and
         packet['ancillary_acceptance']=='SAVED_OBSERVATION_VALIDATED_NO_NEW_COLLECTION' and
         packet['saved_unit_dropins_provenance']=='AUTHENTICATED_R7_SAVED_COLLECTOR_CONTENT_AND_PRESENCE' and
         packet['fresh_directory_authority']=='NOT_REPRESENTED_BY_SAVED_INVENTORY' and
         packet['probe_receipt_raw_form']=='EXACT_CANONICAL_JSON_PLUS_LF')
    need(canonical(packet['saved_projection_sources'])==canonical(exporter.SOURCE_MANIFEST))
    need(packet['local_recomputation_scope']==exporter.RECOMPUTED)
    bindings=packet['bindings'];need(type(bindings) is dict and set(bindings)==topology.BINDING_FIELDS)
    need(bindings['recovery_kit_manifest_sha256']==exporter.MANIFEST_SHA and
         bindings['runtime_manifest_sha256']==exporter.RUNTIME_SHA and
         canonical(bindings['source_files'])==canonical(topology.SOURCE_PINS))
    for name,value in bindings.items():
        if name!='source_files':topology.sha(value)
    topology.sha(packet['observation_full_canonical_sha256'])
    need(bindings['observation_sha256']==packet['observation_full_canonical_sha256'])
    need(canonical(packet['unsigned_expected_review_body'])==canonical(topology.expected_review_body(packet['topology_sha256'],bindings)))
    need(sha(canonical(packet['unsigned_expected_review_body']))==packet['expected_review_body_sha256'])


def read(path,maximum):
    with open(str(path),'rb') as stream:raw=stream.read(maximum+1)
    need(len(raw)<=maximum);return raw


def decode_packet(raw,expected_sha,entry):
    # This digest is supplied out-of-band from the exact received attachment.
    # No value inside the packet may substitute for this delivery-integrity pin.
    need(type(expected_sha) is str and re.fullmatch('[0-9a-f]{64}',expected_sha) and sha(raw)==expected_sha)
    return entry.decode(raw)


def authenticated_kit(archive,exporter):
    need(len(archive)==ARCHIVE_BYTES and sha(archive)==ARCHIVE_SHA)
    files={};prefix='epoch7-recovery-candidate-r7/'
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        for member in tar.getmembers():
            if member.isdir():continue
            need(member.isfile() and member.name.startswith(prefix) and member.size<=33554432)
            name=member.name[len(prefix):];need(name not in files)
            files[name]=tar.extractfile(member).read()
    need(len(files)==253 and sha(files['epoch7_recovery_entry.py'])==exporter.ENTRY_SHA)
    entry=types.ModuleType('offline_verified_entry');entry.__file__='/offline-public-kit/epoch7_recovery_entry.py'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec'),entry.__dict__)
    raw=files.pop(entry.MANIFEST);need(sha(raw)==exporter.MANIFEST_SHA)
    manifest=entry.validate_manifest(entry.decode(raw));need(set(files)==set(manifest['files']) and manifest['kit_source_commit']==exporter.SOURCE)
    for name,data in files.items():need(sha(data)==manifest['files'][name])
    entry.validate_runtime(manifest,files)
    return entry,entry.VerifiedKit('/offline-public-kit',manifest,files,exporter.MANIFEST_SHA,raw_manifest=raw)


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    need(len(args)==3 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    here=pathlib.Path(__file__).resolve().parent
    source=read(here/'export_saved_evidence.py',262144);need(sha(source)==EXPORTER_SHA)
    exporter=types.ModuleType('verified_public_exporter');exec(compile(source,str(here/'export_saved_evidence.py'),'exec'),exporter.__dict__)
    entry,kit=authenticated_kit(read(args[1],ARCHIVE_BYTES),exporter)
    raw=read(args[0],exporter.MAX_OUTPUT);packet=decode_packet(raw,args[2],entry)
    with kit.imports():
        modules=exporter.pure_modules(exporter.embedded_sources())
        topology=modules['epoch7_topology_projection.py'];schema=modules['export_schema.py']
        validate_packet_pins(packet,exporter,topology)
        result=verify_packet(packet,topology,schema)
        result['received_packet_sha256']=sha(raw)
        result['packet_delivery_integrity']='MATCHED_SEPARATELY_SUPPLIED_DIGEST'
    print(json.dumps(result,sort_keys=True));return 0

if __name__=='__main__':sys.exit(main())
