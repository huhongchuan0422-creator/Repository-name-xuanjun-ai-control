"""Public test fixture: real107 runtime/source compilers, synthetic host facts.

Only the central validator's four immutable private byte pins are test-mapped
to synthetic retained evidence. No validator or compiler result is mocked.
This module never observes or mutates production paths and grants no authority.
"""
import base64
import copy
import json
import os
import pathlib

import epoch7_delta as d
import epoch7_host_factory as f
import epoch7_host_phases as h
import epoch7_runtime_effects as runtime
import epoch7_snapshot as snap
import epoch7_openclaw_recipe as oc
from test_epoch7_openclaw_recipe import complete_fixture
from test_epoch7_acceptance_rows import fixture as access_fixture,observation_fixture
from test_epoch7_delta import fixture as delta_fixture
from test_node_sqlite_probe import fixture_attempt,fixture_proof
import node_sqlite_probe as np
import activation_control
from test_snapshot import native_transition_fixture,native_pin_context


def packed(value):return d.canonical(value)+b'\n'
def meta(raw=b'fixture',uid=0,gid=0,mode=0o644,ino=100):
    return {'kind':'FILE','sha256':h.sha(raw),'uid':uid,'gid':gid,'mode':mode,'dev':8,'ino':ino,
            'nlink':1,'size':len(raw),'mtime_ns':11,'ctime_ns':12}
def directory(uid=0,gid=0,mode=0o755,ino=500):
    from epoch7_exact_access import decode_acl
    return {'kind':'DIRECTORY','uid':uid,'gid':gid,'mode':mode,'dev':8,'ino':ino,'nlink':2,'size':4096,
            'mtime_ns':11,'ctime_ns':12,'access_acl':decode_acl(None,mode),'default_acl':''}


def native_fixture_raws(seed):
    value=json.loads(seed['native_before'].decode());ledger=value['ledger'];previous=ledger['bridge']
    original='/opt/xuanjun-control-releases/integration-'+snap.NATIVE_ORIGINAL_RELEASE[:16]+'/stage1/native_ledger_bridge.py'
    ledger['bridge']=original;ledger['files'][original]=ledger['files'].pop(previous)
    raws=native_transition_fixture(value)
    if raws[0]!=seed['native_before']:raise ValueError('SYNTHETIC_NATIVE_BYTES_CHANGED')
    return raws


def native_pins(seed):return native_pin_context(native_fixture_raws(seed))


def make_seed(service_fixture=complete_fixture):
    args,unused=service_fixture();service,identities,native_gateway,gateway_raw,facts=copy.deepcopy(args)
    compiled,unused,manifest_raw,rendered,acceptance=access_fixture()
    package=pathlib.Path(activation_control.__file__).resolve().parent.parent
    manifest=json.loads(manifest_raw.decode());payloads={p:(package/p).read_bytes() for p in manifest['files']}
    compiled['rendered_targets'].update({p:v.encode() if type(v) is str else v for p,v in service['rendered_targets'].items()})
    # Real unit bytes plus a synthetic fixed retained Gateway unit/Install row.
    gateway_raw+=b'[Install]\nWantedBy=multi-user.target\n'
    profile=packed({'env':{'shellEnv':{'enabled':False}},'proxy':{'enabled':False},'agents':{},'plugins':{}})
    candidate_profile=profile
    tls_config={'root':snap.TLS,'domain':'uk.wenwenwenyiyiyi.work','release_sha256':h.MANIFEST,
        'transaction_id':d.TX,'transaction_directory':snap.TRANSACTION,'schema':1}
    compiled['tls_config_bytes']=packed(tls_config);compiled['rendered_targets'][snap.TLS_CONFIG]=packed(tls_config)
    compiled['old_rendered_targets']={p:raw.replace(h.MANIFEST.encode(),d.OLD_MANIFEST.encode()).replace(
        h.MANIFEST[:16].encode(),d.OLD_MANIFEST[:16].encode()) for p,raw in compiled['rendered_targets'].items()}
    snapshot,unused=delta_fixture();snapshot['activation']['config_sha256']=h.sha(compiled['old_rendered_targets'][f.bindings.DISPATCHER])
    compiled['activation_proposal']=dict(snapshot['activation'],epoch=8,release_sha256=h.MANIFEST,
        binary_sha256=d.NEW_BINARY,config_sha256=h.sha(compiled['rendered_targets'][f.bindings.DISPATCHER]))
    rows={r['target']:r for r in service['runtime']['provisioning']}
    compiled['runtime']['provisioning']=[]
    for index,(path,raw) in enumerate(sorted(compiled['rendered_targets'].items())):
        row=copy.deepcopy(rows.get(path,{}));row.update(target=path,owner_uid=0,group_gid=0,
            mode=0o640 if path==f.bindings.CLIENT else 0o644,rendered_sha256=h.sha(raw))
        compiled['runtime']['provisioning'].append(row)
        if path not in d.OWNER_MASKS:snapshot['targets'][path]=meta(compiled['old_rendered_targets'][path],mode=row['mode'],ino=1000+index)
    compiled['source_commit']=h.SOURCE;compiled['source_tree']=h.SOURCE_TREE
    compiled['runtime'].update(release_directory='integration-'+h.MANIFEST[:16],services=list(runtime.ALLOWED_SERVICES),
        sandbox_policy={'sha256':h.sha(candidate_profile)},plugin={'id':runtime.P2_PLUGIN_ID,
        'gateway_service':runtime.GATEWAY_SERVICE,'openclaw_bin':oc.LAUNCHER,'service_user':'xuanjun_dev',
        'source':'plugins/p2-native-controller','binding_file':f.bindings.BINDING,
        'binding_sha256':h.sha(compiled['rendered_targets'][f.bindings.BINDING])})
    old_bridge='/opt/xuanjun-control-releases/integration-'+snap.NATIVE_ORIGINAL_RELEASE[:16]+'/stage1/native_ledger_bridge.py'
    newledger=json.loads(compiled['rendered_targets'][f.bindings.BINDING].decode())['ledger']
    oldledger=copy.deepcopy(newledger);oldledger.update(bridge=old_bridge,files={old_bridge:d.digest('synthetic retained bridge'),
        f.bindings.CLIENT:h.sha(compiled['old_rendered_targets'][f.bindings.CLIENT])})
    native_raws=native_transition_fixture({'ledger':oldledger,'gatewayIdentity':json.loads(native_gateway.decode())['gatewayIdentity']})
    native,native_prior,native_original,native_attempt=native_raws
    oldledger=json.loads(native.decode())['ledger'];old_bridge=oldledger['bridge']
    with native_pin_context(native_raws):native_transition=snap.validate_native_transition(*native_raws)
    legacy={'schema':1,'units':{},'source_before':{}}
    for unit in (oc.GATEWAY,'xuanjun-uk-stage1-minimal.service'):
        raw=gateway_raw if unit==oc.GATEWAY else b'[Service]\nExecStart=/bin/false\n'
        legacy['units'][unit]={'path':'/etc/systemd/system/'+unit,'backup':snap.TRANSACTION+'/'+unit+'.backup',
            'sha256':h.sha(raw),'uid':0,'gid':0,'mode':0o644,'was_active':False}
    legacy_raw=packed(legacy)
    tls_before=packed({'schema':1,'state':h.READY,'config':dict(tls_config,release_sha256=d.OLD_MANIFEST),
        'fingerprint':snapshot['tls']['tree_fingerprint_sha256'],'certificate_sha256':snapshot['tls']['certificate_sha256']})
    snapshot['tls'].update(journal_sha256=h.sha(tls_before),config_identity_sha256=d.digest({k:v for k,v in tls_config.items() if k!='release_sha256'}))
    snapshot['sandbox']['profile_sha256']=h.sha(profile)
    prior=packed({'schema':1,'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY','rollback_complete':False,
        'targets':[{'target':path,'rendered_sha256':h.sha(compiled['old_rendered_targets'][path]),
            'uid':0,'gid':0,'mode':next(r['mode'] for r in compiled['runtime']['provisioning'] if r['target']==path),
            'previous':{'masked':True} if path in d.OWNER_MASKS else None} for path in sorted(d.TARGETS)]})
    publishers={'schema':1,'directories':[{'target':path,'stage':os.path.dirname(path)+'/.p2-publisher-synthetic',
        'state':'PUBLISHED','dev':8,'ino':700+i,'fingerprint':d.digest(path)} for i,path in enumerate(sorted(snap.PUBLISHERS))]}
    publisher_raw=packed(publishers)
    special={'legacy-units.json':legacy_raw,'tls-lifecycle.json':tls_before,'epoch6-runtime-provisioning.json':prior,
             'publisher-bootstrap.json':publisher_raw,'epoch5-prior-native-binding.json':native_prior,
             'epoch5-recovery-execution.json':native_attempt}
    files={p:meta(packed({'fixture':p}),mode=0o600) for p in snap.MANDATORY_FILES}
    for path,row in snapshot['targets'].items():
        if row['kind']=='FILE':files[path]=copy.deepcopy(row)
    for name in d.PRESERVED_RECEIPTS:
        raw=special.get(name,packed({'synthetic':name}));files[snap.TRANSACTION+'/'+name]=meta(raw,mode=0o600)
        snapshot['receipts'][name]=h.sha(raw)
    snapshot['attempt']['sha256']=snapshot['receipts']['epoch5-recovery-execution.json']
    files[snap.NATIVE_ORIGINAL]=meta(native_original,mode=0o600)
    snapshot['sandbox']['journal_sha256']=snapshot['receipts']['sandbox-profile.json']
    for path,raw,owner,group,mode in ((snap.NATIVE,native,0,0,0o644),(snap.PROFILE,profile,1002,1002,0o600),
            (snap.ACTIVE,packed(snapshot['activation']),0,0,0o644),(snap.EPOCHS,b'synthetic epoch chain\n',0,0,0o644),
            (snap.INSTALL_LOCK,b'',0,0,0o600),(snap.ACTIVATION_LOCK,b'',0,0,0o644)):
        files[path]=meta(raw,owner,group,mode)
    snapshot['epoch_journal_sha256']=files[snap.EPOCHS]['sha256']
    for unit,row in legacy['units'].items():files[row['backup']]=meta(gateway_raw if unit==oc.GATEWAY else b'[Service]\nExecStart=/bin/false\n',mode=0o600)
    # Build exact six-role public acceptance facts from the same NSS and unit bytes.
    nss=facts['nss'];acceptance['accounts']={name:copy.deepcopy(nss['accounts'][name]) for name in acceptance['accounts']}
    acceptance['group_ids']={key:value for key,value in nss['groups'].items() if key not in ('root','nginx')}
    acceptance['nss_by_primary']={}
    for key,groups in nss['initgroups'].items():
        name,gid=key.split(':')
        if name in ('xuanjun_dev','xuanjun-dispatcher','xuanjun-callback'):acceptance['nss_by_primary'].setdefault(name,{})[gid]=groups
    from epoch7_acceptance_rows import unit_fields
    acceptance['gateway_base_unit']={'path':oc.GATEWAY and '/etc/systemd/system/'+oc.GATEWAY,
        'sha256':h.sha(gateway_raw),'public_service_fields':__import__('unit_metadata').service_fields(gateway_raw,gateway=True)}
    dropin='/etc/systemd/system/'+oc.GATEWAY+'.d/20-p2-docker.conf'
    acceptance['unit_dropins'][oc.GATEWAY]=[{'path':dropin,'sha256':h.sha(compiled['old_rendered_targets'][dropin]),
        'public_service_fields':unit_fields(compiled['old_rendered_targets'][dropin])}]
    observation=observation_fixture(acceptance);sections=observation['unit_metadata']['sections']
    sections['unit_nss']['evidence']['accounts']=copy.deepcopy(nss['accounts'])
    sections['unit_nss']['evidence']['named_groups']=copy.deepcopy(nss['groups'])
    by_primary={}
    for key,groups in nss['initgroups'].items():name,gid=key.split(':');by_primary.setdefault(name,{})[gid]=groups
    sections['unit_nss']['evidence']['nss_by_primary']=by_primary
    source=facts['openclaw_recipe_evidence'];node=source['node'];nodefile=dict(node['metadata'],kind='FILE',sha256=node['sha256'])
    python=facts['executables']['/usr/bin/python3'];pyrow=meta(b'\x7fELFsynthetic Python',mode=0o755);pyrow['sha256']=python['sha256']
    components={node['path']:nodefile,python['path']:pyrow,old_bridge:meta(b'old bridge')}
    components[old_bridge]['sha256']=oldledger['files'][old_bridge]
    def reference(path,final,info):
        return {'reference_path':path,'links':[] if path==final else [{'path':path,'link':final,
            'metadata':{'dev':8,'ino':200,'uid':0,'gid':0,'mode':0o777,'nlink':1,'size':len(final),'mtime_ns':11,'ctime_ns':12}}],
            'final':{'path':final,'sha256':info['sha256'],'format':'ELF','metadata':info}}
    sections['python_reference']['evidence']=reference('/usr/bin/python3',python['path'],pyrow)
    sections['native_gateway']['evidence']={'gateway_identity':json.loads(native.decode())['gatewayIdentity']}
    for label,path in (('runuser_binary','/usr/sbin/runuser'),('nginx_binary','/usr/sbin/nginx')):
        row=meta(b'\x7fELFsynthetic '+label.encode(),mode=0o755,ino=400)
        if label=='nginx_binary':row['sha256']=facts['executables'][path]['sha256']
        ref=reference(path,path,row);sections[label]['evidence']=dict(ref['final'],reference=ref);files[path]=row
    wrapper_sha=source['launcher']['sha256'];wrapperrow=meta(b'synthetic wrapper',1002,1002,0o755);wrapperrow['sha256']=wrapper_sha
    entry=source['launcher']['recipe']['entry_script'];relative=entry[len(source['package_root'])+1:]
    entryrow=dict(source['files'][relative]['metadata'],sha256=oc.source_hashes(wrapper_sha)[relative])
    sections['launcher']['evidence']={'path':oc.LAUNCHER,'sha256':wrapper_sha,'metadata':wrapperrow,
        'entry_script':{'path':entry,'sha256':entryrow['sha256'],'metadata':entryrow},'recipe':source['launcher']['recipe']}
    if 'node_reference' in source['launcher']:
        sections['launcher']['evidence']['node_reference']=copy.deepcopy(source['launcher']['node_reference'])
    sections['legacy_gateway']['evidence'].update(backup_path=legacy['units'][oc.GATEWAY]['backup'],
        backup_sha256=h.sha(gateway_raw),journal_sha256=h.sha(legacy_raw),original_unit={k:legacy['units'][oc.GATEWAY][k] for k in ('path','sha256','uid','gid','mode')},
        public_service_fields=acceptance['gateway_base_unit']['public_service_fields'],
        public_install_fields={'WantedBy':['multi-user.target'],'RequiredBy':[],'Alias':[],'Also':[]})
    sections['online_cpus']['evidence']={'online_count':2}
    roots={root:{'present':False,'directories':{},'links':[]} for root in f.BOOT_LOOKUP_ROOTS}
    roots['/etc/systemd/system']={'present':True,'directories':{'/etc/systemd/system':{}},'links':[],
        'selected_nonlinks':{},'scan_scope':'BOUNDED_RECURSIVE_NOFOLLOW','all_link_inventory_sha256':d.digest('fixture')}
    sections['boot_links']['evidence']={'units':sorted(f.BOOT_RESTORED),'roots':roots,'unsupported_roots':[]}
    states=copy.deepcopy(facts['unit_states'])
    for unit in f.BOOT_RESTORED:states[unit].update(LoadState='masked',UnitFileState='masked')
    manager={'pid':1,'uids':[0]*4,'gids':[0]*4,'groups':[0,777],'starttime':1,'boot_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        'binary_path':'/usr/lib/systemd/systemd','binary_sha256':d.digest('manager'),'channels':{}}
    files[manager['binary_path']]=dict(meta(b'manager',mode=0o755),sha256=manager['binary_sha256'])
    executables={}
    for label in ('systemctl','openssl','rpm','systemd','git'):
        path=manager['binary_path'] if label=='systemd' else '/usr/bin/'+label
        if path not in files:files[path]=meta(b'\x7fELF'+label.encode(),mode=0o755)
        if label=='git':files[path].update(sha256=facts['executables']['git']['sha256'],dev=8,ino=88)
        executables[label]={'path':path,'sha256':files[path]['sha256']}
    # Prior generation and immutable archive inventories are synthetic metadata.
    databases={path:{'file':meta(('synthetic '+path).encode(),uid=1002 if path==snap.SOURCE_DB else 0,mode=0o600,ino=600+i),
        'sidecars':{}} for i,path in enumerate(snap.DATABASES)}
    snapshot['database'].update({k:databases[d.DB]['file'][k] for k in ('sha256','dev','ino','uid','gid','mode','nlink')})
    releases={};release_evidence={}
    for digest in ('1'*64,'338e488c4203e23d'+'2'*48,d.OLD_MANIFEST):
        path='/opt/xuanjun-control-releases/integration-'+digest[:16]
        row=meta(b'synthetic old source',mode=0o444)
        releases[path]={'manifest_sha256':digest,'payloads':{'stage1/native.py':row['sha256']},'caches':{},
            'cache_staging':'/opt/xuanjun-control-releases/.integration-'+'a'*16}
        release_evidence[path]={'manifest_sha256':digest,'files':{'stage1/native.py':row},'caches':{}}
    snapshot['cache_inventories']={path:d.digest(row) for path,row in releases.items()}
    for path,row in acceptance['bootstrap'].items():files[path]=dict(meta(b'synthetic owner secret',1004,1006,0o600),sha256=row['sha256'])
    prerequisites={'binaries':{},'directories':{'/opt/xuanjun-control-releases':directory(mode=0o750)},
                   'identities':{},'rpm_nevra':{'nginx':facts['nginx_recipe_evidence']['rpm_nevra']}}
    control={'schema':1,'path':'/var/lib/xuanjun-development/control.git','head_commit':'a'*40,'head_tree':'b'*40,
        'publisher_reference_sha256':d.digest('publisher ref'),'publisher_journal_sha256':h.sha(publisher_raw),
        'publisher_fingerprint_sha256':d.digest('publisher fp'),'git_sha256':files['/usr/bin/git']['sha256']}
    compiled['control_repository_reconciliation']={'observation':control,'observation_sha256':d.digest(control)}
    retained={'files':files,'native_components':{'components':components},'native_binding_transition':native_transition,'prerequisites':prerequisites,
        'release_evidence':release_evidence,'database_sets':databases,'tls':{'file_metadata':{}},
        'bootstrap':acceptance['bootstrap'],'control_git':control}
    # Complete source profile + MIME bytes are public fixture content only.
    mime=facts['nginx_recipe_evidence']['mime_types'];mime_meta=meta(mime['raw'])
    source_review={'sections':{'nginx_mime_types':{'state':'MEASURED_UNREVIEWED','evidence':{
        'path':mime['path'],'sha256':mime['sha256'],'metadata':mime_meta,
        'private_content_base64':base64.b64encode(mime['raw']).decode()}}}}
    source['quiet_bootstrap']['source_bindings']['/etc/systemd/system/'+oc.GATEWAY]=h.sha(gateway_raw)
    source['quiet_bootstrap']['manager_sha256']=d.digest(manager);source.pop('node_probe')
    observation['openclaw_profile']={'schema':1,'state':'COMPLETE_UNREVIEWED','missing_fields':[],
        'sections':{'fixture':{'state':'MEASURED_UNREVIEWED'}},'recipe_evidence':source}
    observation['openclaw_profile_sha256']=d.digest(observation['openclaw_profile'])
    observation['source_review_inputs']=source_review;observation['source_review_inputs_sha256']=d.digest(source_review)
    # Every source ancestor is explicitly synthetic/pinned, never a host default.
    dirs={'/':{'uid':0,'gid':0,'mode':0o755}}
    allpaths=set(files)|set(components)|{source['package_root']+'/'+name for name in oc.source_hashes(wrapper_sha)}|{mime['path'],oc.LAUNCHER,entry}
    for path in allpaths|set(snap.DATABASES):
        parent=os.path.dirname(path)
        while parent!='/':
            dirs[parent]={'uid':0,'gid':0,'mode':0o700 if parent==snap.TRANSACTION or parent.startswith(snap.TRANSACTION+'/') else 0o755}
            parent=os.path.dirname(parent)
    if 'node_reference' in source['launcher']:
        for path,row in source['launcher']['node_reference']['ancestors'].items():
            dirs[path]={k:row[k] for k in ('uid','gid','mode')}
    dirs[d.GENERATION]={'uid':1003,'gid':1006,'mode':0o750};dirs['/opt/xuanjun-control-releases']={'uid':0,'gid':0,'mode':0o750}
    policy={'schema':1,'kind':'EPOCH7_MEASURED_READ_ONLY_PINS','hostname':snap.HOST,'transaction_id':d.TX,
        'owner_evidence_sha256':d.digest('synthetic owner'),'files':{p:{k:v[k] for k in ('sha256','uid','gid','mode')} for p,v in files.items()},
        'directories':dirs,'transaction_inventory':{p[len(snap.TRANSACTION)+1:]:v['sha256'] for p,v in files.items() if p.startswith(snap.TRANSACTION+'/')},
        'releases':releases,'databases':{p:dict({k:v['file'][k] for k in ('sha256','uid','gid','mode')},sidecars={},logical_manifest_sha256=d.digest('logical')) for p,v in databases.items()},
        'scheduler_files':{},'control_units':{u:{'/etc/systemd/system/'+u:d.digest(u)} for u in snap.WRITER_UNITS if u.startswith(('xj-','xuanjun-'))},'executables':executables}
    retained['policy_sha256']=d.digest(policy);snapshot['retained_resource_sha256']=d.digest(retained)
    evidence={'retained':retained,'snapshot_sha256':d.digest(snapshot),'writers':{'manager':manager,
        'units':{u:{'state':v} for u,v in states.items()},'processes':{'background_processes':[],'background_processes_sha256':d.digest([])}}}
    resolution=copy.deepcopy(facts['command_resolutions']['xuanjun-development-dispatcher.service'])
    sections['command_resolutions']['evidence']={'unit':'xuanjun-development-dispatcher.service','resolution':resolution,
        'collector_path_used':False,'provenance':{'source':'SYSTEM_MANAGER_CHILD_ENVIRONMENT','manager_sha256':d.digest(manager),
        'dropins_sha256':d.digest(sections['dropins']['evidence']['units']['xuanjun-development-dispatcher.service']),
        'systemctl_sha256':files['/usr/bin/systemctl']['sha256'],
        'unit_sha256':h.sha(compiled['old_rendered_targets']['/etc/systemd/system/xuanjun-development-dispatcher.service'])}}
    observation.update(snapshot=snapshot,evidence=evidence,policy=policy,probe_metadata={'retained_tls_schedule':{
        'raw':{'xuanjun-p2-tls-renew.timer':{'NextElapseUSecMonotonic':'0','LastTriggerUSecMonotonic':'0','ActiveEnterTimestampMonotonic':'0'},
               'xuanjun-p2-tls-renew.service':{'ActiveEnterTimestampMonotonic':'0','ExecMainStartTimestampMonotonic':'0'}},'missing_fields':[]}})
    for key in ('snapshot','evidence','policy','unit_metadata','probe_metadata'):observation[key+'_sha256']=d.digest(observation[key])
    attempt,probe_policy,unused,unused_pin=fixture_attempt();probe_policy['node_sqlite']=np.binding_from_observation(observation)
    pin=h.sha(packed(probe_policy));proof=fixture_proof(node,probe_policy['nonce'],pin,probe_policy['node_sqlite']['probe_input_sha256'])
    receipt_raw=packed({'schema':1,'nonce':probe_policy['nonce'],'policy_sha256':pin,'events':[{'event':'NODE_SQLITE_OBSERVED','detail':proof}]})
    attempt.update(policy=probe_policy,policy_sha256=pin);attempt['result']['node_sqlite']=proof
    attempt['result']['created_receipt'].update(sha256=h.sha(receipt_raw),metadata={k:v for k,v in meta(receipt_raw,mode=0o600).items() if k not in ('kind','sha256')},
        node_sqlite_event_sha256=d.digest(proof))
    observation['finite_probe']=attempt
    identities=dict(identities);identities['/etc/xuanjun-development/p2-ledger-server-identity.json']=b'{"synthetic":"server policy"}\n'
    additions=[{'path':path,'after':{'kind':'FILE','uid':0,'gid':0,'mode':0o644,'sha256':h.sha(raw)},
                'provenance':{'synthetic':'NOT_HOST_AUTHORITY'}} for path,raw in sorted(identities.items())]
    return {'observation':observation,'compiled':compiled,'identity_payloads':identities,'additive_deltas':additions,
        'activate_retained_renewal_timer':True,'native_before':native,'tls_journal_before':tls_before,'prior_provision_bytes':prior,
        'legacy_units_raw':legacy_raw,'publisher_journal_raw':publisher_raw,'sandbox_candidate_raw':candidate_profile,
        'source_manifest_raw':manifest_raw,'source_payloads':payloads,'installer_source':(package/'scripts/uk-integration-install.py').read_bytes(),
        'artifact':{'root':'/fixture/authenticated-runtime','manifest':'/fixture/authenticated-runtime/deploy/integration-manifest.json',
            'source_commit':h.SOURCE,'source_tree':h.SOURCE_TREE,'manifest_sha256':h.MANIFEST,'releases':'/opt/xuanjun-control-releases'},
        'kit_manifest_sha256':d.digest('synthetic authenticated kit')}
