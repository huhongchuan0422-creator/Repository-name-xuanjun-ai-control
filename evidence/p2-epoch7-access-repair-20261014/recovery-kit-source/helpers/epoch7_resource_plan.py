"""Deterministic17-checkpoint resource specs from measured retained state.

No future inode, timestamp, comment ID or raw context-bearing journal hash is
invented. New journals use exact semantic fields plus actual runtime binding;
the activation journal verifies its old prefix and actual approved append proofs.
"""
import copy
import os

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
from epoch7_recovery_sequence import PHASES
from epoch7_live_controls import SECTIONS
from epoch7_host_phases import MANIFEST, need, sha, decode, packed, tls_metadata_candidate
from epoch7_exact_access import decode_acl
from epoch7_runtime_effects import JOURNALS, BOOT_UNITS

RELEASE='/opt/xuanjun-control-releases/integration-'+MANIFEST[:16]
CLIENT='/etc/xuanjun-development/p2-native-ledger-client.json'


def file_spec(path,row):
    need(row['kind']=='FILE','RESOURCE_PLAN_REGULAR_FILE')
    return dict({k:row[k] for k in ('kind','uid','gid','mode','sha256')},path=path,
                access_acl=row.get('access_acl',decode_acl(None,row['mode'])))


def directory_spec(path,row):
    result={k:row[k] for k in ('uid','gid','mode','access_acl','default_acl')}
    if 'dev' in row and 'ino' in row:result.update(dev=row['dev'],ino=row['ino'])
    return dict(result,path=path,kind='DIRECTORY')


def absent(path):return {'path':path,'kind':'ABSENT'}

def private_file(path,raw):return file_spec(path,{'kind':'FILE','uid':0,'gid':0,'mode':0o600,'sha256':sha(raw)})


def projection(path,values,binding='runtime'):
    fields=[list(k) for k,v in values]
    selected=[{'path':list(k),'value':copy.deepcopy(v)} for k,v in values]
    return {'path':path,'kind':'JSON_CONTEXT_PROJECTION' if binding=='runtime' else 'JSON_BOUND_PROJECTION',
            'uid':0,'gid':0,'mode':0o600,'access_acl':decode_acl(None,0o600),
            'fields':fields,'sha256':d.digest(selected)}


def rendered_release_hashes(manifest_raw,payloads,installer_source):
    import epoch7_bindings as bindings
    from epoch7_bounded_stager import INSTALLER_SHA
    manifest=bindings.checked_manifest(manifest_raw,payloads)
    need(sha(manifest_raw)==MANIFEST and len(payloads)==107 and sha(installer_source)==INSTALLER_SHA,
         'RESOURCE_PLAN_EXACT107_RELEASE')
    namespace={'__name__':'epoch7_pure_identity_renderer'}
    exec(compile(installer_source,'<pinned-pure-resource-renderer>','exec'),namespace)
    return {path:sha(namespace['render_identity_bytes'](path,raw,MANIFEST,manifest))
            for path,raw in payloads.items()}


def build_resource_views(snapshot,support,compiled,additions,security_rows,manifest_raw,
                         payloads,installer_source,native_after,tls_journal_before,
                         sandbox_candidate_raw,legacy_units,*,executable_specs,policy,publisher_journal_raw,nss_projection,startup_sources=()):
    """Return complete static resource views, not authority or host measurements.

    legacy_units is the exact decoded retained legacy-units.json receipt. The
    source-owned Gateway restoration primitive independently verifies backup
    bytes, masks and immediate CAS. Fresh platform directories remain required.
    """
    retained=support['retained'];files=retained['files']
    need(d.digest(retained)==snapshot['retained_resource_sha256'],'RESOURCE_PLAN_RETAINED_BINDING')
    hashes=rendered_release_hashes(manifest_raw,payloads,installer_source)
    need(type(legacy_units) is dict and 'units' in legacy_units,'RESOURCE_PLAN_LEGACY_RECEIPT')
    needed={snap.ACTIVE,snap.EPOCHS,snap.NATIVE,snap.PROFILE,d.DB,fs.TRANSACTION+'/tls-lifecycle.json'}|set(d.TARGETS)
    need(sha(publisher_journal_raw)==snapshot['receipts']['publisher-bootstrap.json'],
         'RESOURCE_PLAN_PUBLISHER_JOURNAL')
    publisher=decode(publisher_journal_raw)
    need(type(publisher.get('directories')) is list and len(publisher['directories'])==2 and
         {row['target'] for row in publisher['directories']}==snap.PUBLISHERS,'RESOURCE_PLAN_PUBLISHER_SET')
    baseline={name:{} for name in SECTIONS}
    def put(section,spec):baseline[section][spec['path']]=copy.deepcopy(spec)
    def remove(section,path):baseline[section].pop(path,None)
    def historical(path,row):
        if path not in needed:put('historical',file_spec(path,row))
    need(type(nss_projection) is dict and nss_projection.get('kind')=='NSS_BINDINGS',
         'RESOURCE_PLAN_MEASURED_NSS_REQUIRED')
    put('historical',nss_projection)
    for path,row in files.items():historical(path,row)
    need(type(startup_sources) in (list,tuple) and len(startup_sources)<=64,'RESOURCE_PLAN_STARTUP_SOURCE_BOUND')
    for spec in startup_sources:
        need(spec['kind']=='FILE' and spec['path'] not in needed,'RESOURCE_PLAN_STARTUP_IMMUTABLE_SCOPE')
        put('historical',spec)
    for row in publisher['directories']:
        need(row['state']=='PUBLISHED' and os.path.dirname(row['stage'])==os.path.dirname(row['target']) and
             os.path.basename(row['stage']).startswith('.p2-publisher-'),'RESOURCE_PLAN_PUBLISHER_STAGE')
        put('historical',{'path':row['target'],'kind':'PUBLISHER_FINGERPRINT','uid':1003,'gid':1003,
            'dev':row['dev'],'ino':row['ino'],'sha256':row['fingerprint']})
        put('historical',absent(row['stage']))
    for root in snap.SCHEDULER_ROOTS:
        inventory={path:digest for path,digest in policy['scheduler_files'].items() if path==root or path.startswith(root+'/')}
        put('historical',{'path':root,'kind':'OPTIONAL_INVENTORY','sha256':d.digest(inventory)})
    for path,row in retained['native_components']['components'].items():historical(path,row)
    for path,row in retained['prerequisites']['binaries'].items():historical(path,row)
    need(type(executable_specs) is dict and executable_specs,'RESOURCE_PLAN_COMMAND_COVERAGE')
    for path,spec in executable_specs.items():
        if spec['kind']=='FILE':put('historical',spec)
        else:
            need(spec['kind']=='EXECUTABLE_REFERENCE','RESOURCE_PLAN_COMMAND_KIND')
            proof=spec['reference']
            for link in proof['links']:
                put('historical',{'path':link['path'],'kind':'LINK','uid':link['metadata']['uid'],
                    'gid':link['metadata']['gid'],'sha256':sha(link['link'].encode('utf-8'))})
            final=proof['final'];put('historical',file_spec(final['path'],final['metadata']))
    for root,evidence in retained['release_evidence'].items():
        inventory={root+'/INTEGRATION_MANIFEST.json':evidence['manifest_sha256']}
        for relative,row in evidence['files'].items():historical(root+'/'+relative,row);inventory[root+'/'+relative]=row['sha256']
        for relative,row in evidence['caches'].items():historical(root+'/'+relative,row['file']);inventory[root+'/'+relative]=row['file']['sha256']
        put('historical',{'path':root,'kind':'TREE_INVENTORY','sha256':d.digest(inventory)})
    for base,row in retained['database_sets'].items():
        if base!=d.DB:historical(base,row['file'])
        for suffix in ('-wal','-shm','-journal'):
            path=base+suffix
            if base==d.DB:continue  # Dynamic sidecars are checked by full FD census.
            put('historical',file_spec(path,row['sidecars'][suffix]) if suffix in row['sidecars'] else absent(path))
    # All context-free static sections remain nonempty without making a claim
    # that a shared anchor alone covers their domain; mutable objects below are
    # checked in their actual owning section and by concrete phase proof.
    anchor=private_file(fs.TRANSACTION+'/epoch5-recovery-execution.json',b'')
    anchor['sha256']=snapshot['receipts']['epoch5-recovery-execution.json']
    for section in ('access','runtime_access'):put(section,anchor)
    put('historical',projection(fs.TRANSACTION+'/epoch7-recovery-execution.json',
        [(('transaction_id',),d.TX)],binding='inner'))
    release_parent=retained['prerequisites']['directories']['/opt/xuanjun-control-releases']
    put('release',directory_spec('/opt/xuanjun-control-releases',release_parent));put('release',absent(RELEASE))
    for path,row in snapshot['targets'].items():
        put('targets',{'path':path,'kind':'MASK','uid':row['uid'],'gid':row['gid'],'link':'/dev/null'}
            if row['kind']=='MASK' else file_spec(path,row))
    put('targets',absent(fs.TRANSACTION+'/epoch8-runtime-provisioning.json'))
    changed=[p for p,row in snapshot['targets'].items() if row['kind']=='MASK' or row['sha256']!=sha(compiled['rendered_targets'][p])]
    for path in changed:put('targets',absent(fs.TRANSACTION+'/epoch7-target-before-'+sha(path.encode('utf-8'))+'.private'))
    for addition in additions:put('identities',absent(addition['path']))
    for name in ('epoch7-owner-identity-publication.json','epoch7-server-identity-publication.json'):
        put('identities',absent(fs.TRANSACTION+'/'+name))
    put('generation',directory_spec(d.GENERATION,snapshot['generation']))
    put('generation',absent(fs.TRANSACTION+'/epoch7-generation-access.json'))
    put('native',file_spec(snap.NATIVE,files[snap.NATIVE]))
    put('native',absent(fs.TRANSACTION+'/epoch7-prior-native-binding.json'))
    put('tls',file_spec(fs.TRANSACTION+'/tls-lifecycle.json',files[fs.TRANSACTION+'/tls-lifecycle.json']))
    for name in ('epoch8-tls-renewal-candidate.json','epoch7-prior-tls-lifecycle.json'):put('tls',absent(fs.TRANSACTION+'/'+name))
    for rel,row in retained['tls']['file_metadata'].items():
        path=snap.TLS+'/'+rel
        if row['kind']=='FILE':put('tls',file_spec(path,row))
        elif row['kind']=='LINK':put('tls',{'path':path,'kind':'LINK','uid':row['uid'],'gid':row['gid'],'sha256':row['target_sha256']})
        else:put('tls',directory_spec(path,row))
    put('sandbox',file_spec(snap.PROFILE,files[snap.PROFILE]))
    for name in JOURNALS[:3]:put('sandbox',absent(fs.TRANSACTION+'/'+name))
    put('plugin',absent(snap.PLUGIN_PATH));put('plugin',absent(fs.TRANSACTION+'/'+JOURNALS[3]))
    plugin_id='xuanjun-p2-native-controller'
    plugin_fields=[['plugins','entries',plugin_id,'enabled'],['plugins','entries',plugin_id,'config']]
    put('plugin',dict(file_spec(snap.PROFILE,files[snap.PROFILE]),kind='JSON_OPTIONAL_PROJECTION',fields=plugin_fields,
        sha256=d.digest([{'path':field,'found':False,'value':None} for field in plugin_fields])))
    db=snapshot['database'];put('database',dict({k:db[k] for k in ('uid','gid','mode','dev','ino','nlink')},
        path=d.DB,kind='DATABASE_IDENTITY',access_acl=decode_acl(None,db['mode'])))
    put('database',absent(fs.TRANSACTION+'/ledger-access.json'))
    put('boot',absent(fs.TRANSACTION+'/runtime-boot.json'))
    for unit,row in legacy_units['units'].items():
        put('gateway',{'path':row['path'],'kind':'MASK','uid':0,'gid':0,'link':'/dev/null'})
    def activation(value):
        put('activation',file_spec(snap.ACTIVE,dict(files[snap.ACTIVE],sha256=sha(packed(value)))))
        put('activation',dict(file_spec(snap.EPOCHS,files[snap.EPOCHS]),kind='EPOCH_CHAIN',
            descriptor=copy.deepcopy(value),prefix_size=files[snap.EPOCHS]['size'],
            prefix_sha256=snapshot['epoch_journal_sha256'],sha256=d.digest(value)))
    activation(snapshot['activation']);views=[]
    def append():
        need(all(baseline[n] for n in SECTIONS),'RESOURCE_PLAN_SECTION_COVERAGE')
        views.append({n:[copy.deepcopy(baseline[n][p]) for p in sorted(baseline[n])] for n in SECTIONS})
    append()
    for phase in PHASES:
        if phase=='stage_exact_release':
            inventory={RELEASE+'/'+p:v for p,v in hashes.items()};inventory[RELEASE+'/INTEGRATION_MANIFEST.json']=MANIFEST
            put('release',{'path':RELEASE,'kind':'TREE_INVENTORY','sha256':d.digest(inventory)})
            for path,digest in inventory.items():
                mode=0o555 if path in (RELEASE+'/scripts/xj-root-broker-client',RELEASE+'/scripts/uk-owner-workbench-config.py') else 0o444
                put('release',file_spec(path,{'kind':'FILE','uid':0,'gid':0,'mode':mode,'sha256':digest}))
        elif phase=='rebind_prepared_epoch':
            activation(compiled['activation_proposal'])
            put('native',file_spec(snap.NATIVE,dict(files[snap.NATIVE],sha256=sha(native_after))))
            prior=dict(files[snap.NATIVE],mode=0o600)
            put('native',file_spec(fs.TRANSACTION+'/epoch7-prior-native-binding.json',prior))
            put('tls',private_file(fs.TRANSACTION+'/epoch8-tls-renewal-candidate.json',compiled['tls_config_bytes']))
        elif phase=='quiesce_exact_epoch':activation(dict(compiled['activation_proposal'],state='QUIESCED'))
        elif phase=='replace_retained_targets':
            for path,row in snapshot['targets'].items():
                spec=file_spec(path,dict(row,kind='FILE',sha256=sha(compiled['rendered_targets'][path]),
                    uid=next(r['owner_uid'] for r in compiled['runtime']['provisioning'] if r['target']==path),
                    gid=next(r['group_gid'] for r in compiled['runtime']['provisioning'] if r['target']==path),
                    mode=next(r['mode'] for r in compiled['runtime']['provisioning'] if r['target']==path)))
                # Provisioning schema uses integer IDs/modes, enforced by candidate compiler.
                put('targets',spec)
            for path in changed:
                old=snapshot['targets'][path];digest=old['sha256'] if old['kind']=='FILE' else d.digest(old)
                put('targets',file_spec(fs.TRANSACTION+'/epoch7-target-before-'+sha(path.encode('utf-8'))+'.private',
                    {'kind':'FILE','uid':0,'gid':0,'mode':0o600,'sha256':digest}))
            put('targets',projection(fs.TRANSACTION+'/epoch8-runtime-provisioning.json',[(('state','stage'),'TARGET_DELTA_COMPLETE')],'inner'))
        elif phase=='publish_reviewed_identities':
            for addition in additions:put('identities',file_spec(addition['path'],addition['after']))
            for name in ('epoch7-owner-identity-publication.json','epoch7-server-identity-publication.json'):
                put('identities',projection(fs.TRANSACTION+'/'+name,[(('state','stage'),'ADDITIVE_PUBLICATION_DONE')],'inner'))
        elif phase=='change_generation_access':
            row=dict(snapshot['generation'],mode=0o700,access_acl=decode_acl(None,0o700))
            put('generation',directory_spec(d.GENERATION,row))
            put('generation',projection(fs.TRANSACTION+'/epoch7-generation-access.json',[(('state','stage'),'GENERATION_ACCESS_DONE')],'inner'))
        elif phase=='apply_reviewed_access':
            for row in security_rows:
                section='release' if row['path']=='/opt/xuanjun-control-releases' else 'targets'
                baseline[section][row['path']]['access_acl']=row['proposal']['after_acl']
        elif phase=='rebind_tls_metadata_only':
            put('tls',private_file(fs.TRANSACTION+'/epoch7-prior-tls-lifecycle.json',tls_journal_before))
            put('tls',private_file(fs.TRANSACTION+'/tls-lifecycle.json',tls_metadata_candidate(tls_journal_before,compiled['tls_config_bytes'],snapshot['tls'])))
        elif phase=='apply_fresh_sandbox':
            from p2_sandbox_profile import stable
            put('sandbox',dict(file_spec(snap.PROFILE,files[snap.PROFILE]),kind='SANDBOX_STABLE',sha256=d.digest(stable(sandbox_candidate_raw))))
            for name,digest in ((JOURNALS[1],snapshot['sandbox']['profile_sha256']),(JOURNALS[2],sha(sandbox_candidate_raw))):
                put('sandbox',file_spec(fs.TRANSACTION+'/'+name,{'kind':'FILE','uid':0,'gid':0,'mode':0o600,'sha256':digest}))
            put('sandbox',projection(fs.TRANSACTION+'/'+JOURNALS[0],[(('state',),'APPLIED'),(('original_sha256',),snapshot['sandbox']['profile_sha256']),
                (('candidate_sha256',),sha(sandbox_candidate_raw))]))
        elif phase=='install_verified_plugin':
            entry=baseline['sandbox'][fs.TRANSACTION+'/'+JOURNALS[0]]
            entry['sha256']=d.digest([{'path':['state'],'value':'CLI_CAPTURED'},
                {'path':['original_sha256'],'value':snapshot['sandbox']['profile_sha256']},
                {'path':['candidate_sha256'],'value':sha(sandbox_candidate_raw)}])
            plugin_files={snap.PLUGIN_PATH+'/'+p[len('plugins/p2-native-controller/'):]:v for p,v in hashes.items() if p.startswith('plugins/p2-native-controller/')}
            need(plugin_files,'RESOURCE_PLAN_PLUGIN_SOURCE_SET')
            put('plugin',{'path':snap.PLUGIN_PATH,'kind':'TREE_INVENTORY','sha256':d.digest(plugin_files)})
            plugin=compiled['runtime']['plugin']
            baseline['plugin'][snap.PROFILE]['sha256']=d.digest([
                {'path':plugin_fields[0],'found':True,'value':True},
                {'path':plugin_fields[1],'found':True,'value':{'bindingFile':plugin['binding_file'],'bindingSha256':plugin['binding_sha256']}}])
            put('plugin',projection(fs.TRANSACTION+'/'+JOURNALS[3],[(('state',),'INSTALLED'),(('previous',),'ABSENT')]))
        elif phase=='reopen_existing_database':
            baseline['database'][d.DB].update(uid=1003,gid=1006)
            put('database',projection(fs.TRANSACTION+'/ledger-access.json',[(('state',),'REOPENED')]))
        elif phase=='activate_exact_epoch':activation(dict(compiled['activation_proposal'],state='ACTIVE'))
        elif phase=='activate_new_services':
            gateway=legacy_units['units']['xuanjun-uk-openclaw.service']
            put('gateway',file_spec(gateway['path'],dict(gateway,kind='FILE')))
            put('boot',projection(fs.TRANSACTION+'/runtime-boot.json',[(('state',),'ENABLED'),(('units',),list(BOOT_UNITS))]))
        append()
    need(len(views)==17,'RESOURCE_PLAN17_VIEWS')
    return views


def build_resource_directories(policy,views):
    """Reviewed old ancestry plus only the fixed newly staged source ancestors."""
    result={}
    for path,row in policy['directories'].items():
        result[path]=[dict({k:row[k] for k in ('uid','gid','mode')},
            access_acl=decode_acl(None,row['mode']),default_acl='')]
    for view in views:
        for rows in view.values():
            for spec in rows:
                if spec['kind']=='DIRECTORY' and spec['path'] in result:
                    row={k:spec[k] for k in ('uid','gid','mode','access_acl','default_acl')}
                    if row not in result[spec['path']]:result[spec['path']].append(row)
                if spec['path'].startswith(RELEASE+'/'):
                    parent=os.path.dirname(spec['path'])
                    while parent==RELEASE or parent.startswith(RELEASE+'/'):
                        result[parent]=[{'uid':0,'gid':0,'mode':0o555,
                            'access_acl':decode_acl(None,0o555),'default_acl':''}]
                        parent=os.path.dirname(parent)
    need('/' in result and all(1<=len(rows)<=3 for rows in result.values()),'RESOURCE_PLAN_FINITE_ANCESTRY')
    return result


def build_access_rows(support,compiled):
    from exact_access_plan import propose
    parent=support['retained']['prerequisites']['directories']['/opt/xuanjun-control-releases']
    rows=[]
    before={k:parent[k] for k in ('uid','gid','mode','dev','ino','access_acl','default_acl')}
    before.update(kind='DIRECTORY',sha256=None,state_source='stage_exact_release_observed')
    rows.append({'path':'/opt/xuanjun-control-releases','before_binding':before,
                 'proposal':propose(before['access_acl'],'release_traversal',[1002,1003,1004])})
    target=next(row for row in compiled['runtime']['provisioning'] if row['target']==CLIENT)
    before={'kind':'FILE','uid':target['owner_uid'],'gid':target['group_gid'],'mode':target['mode'],
            'sha256':sha(compiled['rendered_targets'][CLIENT]),'access_acl':decode_acl(None,target['mode']),
            'default_acl':'','state_source':'inner_provision_observed_after'}
    rows.append({'path':CLIENT,'before_binding':before,
                 'proposal':propose(before['access_acl'],'ledger_client_binding_read',[1003])})
    return rows
