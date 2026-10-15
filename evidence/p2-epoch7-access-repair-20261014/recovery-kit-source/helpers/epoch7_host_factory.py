"""Explicit reviewed-input compiler and concrete retained host composition.

Compilation is pure and grants no authority. Assembly does not run the driver,
fetch an approval, acquire locks or execute a command. A protected loader must
first authenticate the complete source closure and the exact private inputs.
No optional adapters, fake approval IDs, host defaults or fallback commands.
"""
import copy
import os

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
import epoch7_python_identity as python_identity
import epoch7_bindings as bindings
from epoch7_injected_recovery import RecoveryGate, required_authorization
from epoch7_complete_approval import (CompleteApprovalVerifier, preapproval_sequence_contract,
    sequence_contract, sequence_contract_sha256)
from epoch7_recovery_sequence import context_from_gate, BoundedDiagnostics, PHASES
from epoch7_live_controls import FiniteLiveControls, validate_contract, SECTIONS, SIDECAR_POLICY
from epoch7_runtime_effects import Epoch7RuntimeEffects, BOOT_UNITS, command_contract
from epoch7_runtime_acceptance import RuntimeAcceptanceChecks, compile_acceptance_contract
from epoch7_host_phases import (ExistingInstallLock, BoundedActivationStore, ClaimAuthority,
    HostPhaseFilesystem, CoreHostPhases, MANIFEST, SOURCE, SOURCE_TREE, need, sha, decode,
    tls_metadata_candidate, retained_native_transition)
from epoch7_bounded_stager import FrozenBoundedInstaller, INSTALLER_SHA
from epoch7_exact_access import ExactAccessApplier, TARGETS as ACCESS_TARGETS
from epoch7_host_observer import LinuxProcessCensus, BoundedRetainedTLS, Epoch7HostObserver
from epoch7_resource_observer import ResourceReader, CheckpointResources
from epoch7_pre_active_guards import PreActiveGateGuards
from epoch7_host_containment import BoundLegacyFiles, HostContainment, BoundedContainmentScanner
from epoch7_host_driver import compose_driver
from epoch7_timer_tail import DeferredRenewalRuntime, RetainedRenewalTail, compile_timer_contract, timer_baseline_from_observation
from epoch7_resource_plan import (build_resource_views, build_resource_directories, build_access_rows, rendered_release_hashes)
from epoch7_acceptance_rows import compile_access_rows, acceptance_facts_from_observation
from epoch7_service_contract import compile_service_contract, require_complete_service_contract, service_facts_from_observation
import protected_command_evidence as command_evidence

INPUTS = frozenset(('snapshot','supporting_evidence','snapshot_policy','candidate','compiled',
    'observation','kit_manifest_sha256','additive_deltas','identity_payloads','prior_provision_bytes',
    'native_before','tls_journal_before','installer_source','artifact','resource_directories',
    'resource_views','unit_checkpoints','manager','process_roles','database_sidecar_policy',
    'access_rows','acceptance_access_rows','boot_before','activate_retained_renewal_timer',
    'executable_specs','timer_raw_baseline','source_manifest_raw','source_payloads',
    'sandbox_candidate_raw','legacy_units_raw','publisher_journal_raw','acceptance_facts','service_facts',
    'service_role_contract','unit_transition_contract'))


def missing_inputs(inputs):
    need(type(inputs) is dict, 'FACTORY_INPUT_MAPPING')
    return sorted(name for name in INPUTS if name not in inputs or inputs[name] is None)


def _fingerprint(value):
    # Typed child hashes prevent sentinel collisions and keep repeated full
    #17-checkpoint proofs below the unchanged2MiB canonical object bound.
    if type(value) is bytes:return ['bytes',len(value),sha(value)]
    if type(value) is dict:
        need(all(type(k) is str for k in value),'FACTORY_STRING_KEYS')
        return ['dict',len(value),[[k,d.digest(_fingerprint(v))] for k,v in sorted(value.items())]]
    if type(value) in (list,tuple):return [type(value).__name__,len(value),[d.digest(_fingerprint(v)) for v in value]]
    need(type(value) in (str,int,bool,type(None)),'FACTORY_FINITE_INPUT_TYPES')
    return [type(value).__name__,value]


def input_digest(inputs):return d.digest(['EPOCH7_TYPED_INPUT_V2',_fingerprint(inputs)])


def compiled_bytes(compiled):
    value=copy.deepcopy(compiled)
    for key in ('rendered_targets','old_rendered_targets'):
        need(type(value.get(key)) is dict,'FACTORY_PRIVATE_TARGET_BYTES')
        for path,raw in value[key].items():
            if type(raw) is str:raw=raw.encode('utf-8')
            need(type(raw) is bytes,'FACTORY_PRIVATE_TARGET_BYTES');value[key][path]=raw
    raw=value.get('tls_config_bytes')
    if type(raw) is str:raw=raw.encode('utf-8')
    need(type(raw) is bytes,'FACTORY_TLS_BYTES');value['tls_config_bytes']=raw
    return value


def runtime_database_before(supporting):
    row=supporting['retained']['database_sets'][d.DB]['file']
    keys=('uid','gid','mode','size','mtime_ns','ctime_ns','nlink')
    result={key:row[key] for key in keys}
    result.update(device=row['dev'],inode=row['ino'])
    need(all(type(x) is int and x>=0 for x in result.values()) and result['inode']>0 and
         result['uid']==0 and result['mode']==0o600 and result['nlink']==1,'FACTORY_DATABASE_BEFORE_STAMPS')
    return result


def retained_sidecar_pins(supporting):
    result={}
    for base in snap.DATABASES:
        if base==d.DB:continue
        found=supporting['retained']['database_sets'][base]['sidecars']
        for suffix in ('-wal','-shm','-journal'):
            row=found.get(suffix)
            result[base+suffix]=None if row is None else dict(row,kind='REGULAR')
    return result


def compile_checkpoint_contract(snapshot,views,units,manager,roles,sidecars,retained_sidecars,service_roles=None,unit_transitions=None):
    """Derive all17 resource digests; observations/specs are explicit inputs.

    Future raw inode/timestamp/approval hashes must not appear in a spec. Use
    semantic projections and authenticated own-write checks for generated data.
    This compiler does not manufacture missing unit states or process roles.
    """
    need(type(views) is list and type(units) is list and len(views)==len(units)==len(PHASES)+1,
         'FACTORY17_CHECKPOINT_INPUTS')
    points=[]
    for view,unit_policy in zip(views,units):
        need(type(view) is dict and set(view)==SECTIONS,'FACTORY_CHECKPOINT_SECTIONS')
        for rows in view.values():
            need(type(rows) is list and 1<=len(rows)<=8192 and
                 len({r['path'] for r in rows})==len(rows),'FACTORY_FINITE_RESOURCE_SPECS')
        points.append({'resources':{name:d.digest(rows) for name,rows in view.items()},
                       'units':copy.deepcopy(unit_policy)})
    dbs=snapshot['database_identities']
    need(type(service_roles) is dict and type(unit_transitions) is dict,'FACTORY_SCHEMA2_SERVICE_CONTRACTS_REQUIRED')
    return {'schema':2,'snapshot_sha256':snapshot['snapshot_sha256'],
            'service_role_contract':copy.deepcopy(service_roles),'unit_transition_contract':copy.deepcopy(unit_transitions),
            'runtime_manifest_sha256':MANIFEST,'manager':copy.deepcopy(manager),
            'checkpoints':points,'process_roles':copy.deepcopy(roles),
            'database_identities':copy.deepcopy(dbs),'database_sidecar_policy':copy.deepcopy(sidecars),
            'retained_sidecar_pins':copy.deepcopy(retained_sidecars)}


def build_executable_specs(observation,native_before):
    """Derive finite command identities from the same complete host bundle."""
    from epoch7_resource_plan import file_spec
    metadata=observation['unit_metadata']
    need(observation['kind']=='EPOCH7_OBSERVATION_ONLY_UNREVIEWED' and
         d.digest(metadata)==observation['unit_metadata_sha256'] and
         metadata['state']=='COMPLETE_UNREVIEWED' and metadata['unsupported_sections']==[] and
         all(v['state']=='MEASURED_UNREVIEWED' for v in metadata['sections'].values()),
         'FACTORY_COMPLETE_UNIT_METADATA_REQUIRED')
    retained=observation['evidence']['retained'];policy=observation['policy']
    need(d.digest(policy)==observation['policy_sha256'] and
         d.digest(observation['evidence'])==observation['evidence_sha256'], 'FACTORY_OBSERVATION_DIGESTS')
    components=retained['native_components']['components']
    for path in python_identity.PYTHON_PATHS:
        rows=[source[path] for source in (retained['files'],components) if path in source]
        if any('python_identity' in row for row in rows):
            specs=[file_spec(path,row) for row in rows]
            need(all(spec==specs[0] for spec in specs),'FACTORY_PYTHON_PAIR_MEASUREMENT_CONFLICT')
    measured=dict(retained['files']);measured.update(components)
    result={}
    for tool in policy['executables'].values():
        path=tool['path'];need(path in measured,'FACTORY_MEASURED_COMMAND_FILE')
        result[path]=file_spec(path,measured[path])
    native=decode(native_before)
    python_scope={'/usr/bin/python3','/usr/bin/python3.6','/etc/alternatives/python3',
        '/usr/libexec/platform-python','/usr/libexec/platform-python3.6','/usr/libexec/platform-python3.6m'}
    path=native['ledger']['python'];native_reference=retained['native_components'].get('python_reference')
    if native_reference is None:
        need(path in measured,'FACTORY_NATIVE_EXECUTABLE_METADATA');result[path]=file_spec(path,measured[path])
    else:
        need(set(native_reference)=={'reference_path','links','final'} and
             native_reference['reference_path']==path and path in python_scope and
             {row['path'] for row in native_reference['links']}|{native_reference['final']['path']}<=python_scope,
             'FACTORY_NATIVE_PYTHON_ALIAS_SCOPE')
        final=native_reference['final']
        # The frozen bridge/peer runtime requires a canonical native interpreter.
        # Unit ExecStart aliases have a separate measured reference below.
        need(final['path']==path and native_reference['links']==[],
             'FACTORY_NATIVE_PYTHON_CANONICAL_REQUIRED')
        spec=file_spec(final['path'],final['metadata'])
        need(final['path'] in measured and file_spec(final['path'],measured[final['path']])==spec,
             'FACTORY_NATIVE_PYTHON_FINAL_BINDING')
        result[final['path']]=spec
    path=native['gatewayIdentity']['exe']
    need(path in measured,'FACTORY_NATIVE_EXECUTABLE_METADATA');result[path]=file_spec(path,measured[path])
    sections=metadata['sections']
    scopes={'/usr/bin/python3':python_scope,
            '/usr/sbin/runuser':{'/usr/sbin/runuser','/usr/bin/runuser'},
            '/usr/sbin/nginx':{'/usr/sbin/nginx','/usr/bin/nginx'}}
    for name,path in (('python_reference','/usr/bin/python3'),('runuser_binary','/usr/sbin/runuser'),('nginx_binary','/usr/sbin/nginx')):
        proof=sections[name]['evidence'];proof=proof if name=='python_reference' else proof['reference']
        need(set(proof)=={'reference_path','links','final'} and proof['reference_path']==path and
             {row['path'] for row in proof['links']}|{proof['final']['path']}<=scopes[path],
             'FACTORY_EXECUTABLE_ALIAS_SCOPE')
        final=proof['final'];spec=file_spec(final['path'],final['metadata'])
        need(final['path'] not in result or result[final['path']]==spec,'FACTORY_EXECUTABLE_FINAL_CONFLICT')
        wrapper={'path':path,'kind':'EXECUTABLE_REFERENCE','reference':copy.deepcopy(proof)}
        need(path not in result or result[path]==wrapper or (path==final['path'] and result[path]==spec),
             'FACTORY_EXECUTABLE_REFERENCE_CONFLICT')
        result[path]=wrapper
        if final['path']!=path:result[final['path']]=spec
    launcher=sections['launcher']['evidence']
    need(launcher['path']=='/home/xuanjun_dev/.openclaw/bin/openclaw' and
         launcher['sha256']==launcher['metadata']['sha256'],'FACTORY_LAUNCHER_BINDING')
    result[launcher['path']]=file_spec(launcher['path'],launcher['metadata'])
    entry=launcher['entry_script'];need(entry['sha256']==entry['metadata']['sha256'],'FACTORY_LAUNCHER_ENTRY_BINDING')
    result[entry['path']]=file_spec(entry['path'],entry['metadata'])
    from epoch7_openclaw_recipe import DIRECT_WRAPPER_SHA,DIRECT_ENTRY
    if launcher['sha256']==DIRECT_WRAPPER_SHA:
        from unit_metadata import validate_node_reference
        identity=native['gatewayIdentity']
        reference=validate_node_reference(launcher.get('node_reference'),identity['exe'],identity['sha256'])
        final=reference['final'];actual=measured[identity['exe']]
        need(entry['path']==DIRECT_ENTRY and all(actual[k]==final['metadata'][k] for k in
             ('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns','sha256')),
             'FACTORY_DIRECT_NODE_REFERENCE_BINDING')
        result[identity['exe']]=dict(result[identity['exe']],node_reference=reference)
    else:need('node_reference' not in launcher,'FACTORY_ROOT_NODE_REFERENCE_FORBIDDEN')
    pairs=[spec['python_identity'] for spec in result.values() if 'python_identity' in spec]
    if pairs:
        proof=python_identity.validate_pair_proof(pairs[0])
        need(all(item==proof for item in pairs),'FACTORY_PYTHON_PAIR_PROOF_CONFLICT')
        for path in python_identity.PYTHON_PATHS:
            need(path in measured and measured[path].get('python_identity')==proof,
                 'FACTORY_PYTHON_PAIR_BOTH_MEASURED')
            spec=file_spec(path,measured[path])
            need(path not in result or result[path]==spec,'FACTORY_PYTHON_PAIR_SPEC_CONFLICT')
            result[path]=spec
    return result


def nss_projection(observation):
    value=observation['unit_metadata']['sections']['unit_nss']['evidence']
    return {'path':'/etc/passwd','kind':'NSS_BINDINGS',
        'prerequisites':copy.deepcopy(observation['evidence']['retained']['prerequisites']['identities']),
        'accounts':copy.deepcopy(value['accounts']),'group_ids':copy.deepcopy(value['named_groups']),
        'nss_by_primary':copy.deepcopy(value['nss_by_primary'])}


BOOT_RESTORED=frozenset(('xuanjun-uk-openclaw.service','xuanjun-uk-owner-callback.service',
                         'xuanjun-uk-owner-dashboard.service'))
BOOT_LOOKUP_ROOTS=frozenset(('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system',
    '/run/systemd/system.control','/run/systemd/transient','/run/systemd/generator.early',
    '/run/systemd/generator','/run/systemd/generator.late'))


def candidate_from_compiled(compiled,snapshot):
    compiled=compiled_bytes(compiled)
    rows=compiled['runtime']['provisioning'];need(len(rows)==24 and {r['target'] for r in rows}==d.TARGETS,
         'FACTORY_CANDIDATE24_PROPOSALS')
    targets={row['target']:{'kind':'FILE','sha256':sha(compiled['rendered_targets'][row['target']]),
        'uid':row['owner_uid'],'gid':row['group_gid'],'mode':row['mode']} for row in rows}
    config=decode(compiled['tls_config_bytes'])
    value={'manifest_sha256':compiled['manifest_sha256'],'activation':copy.deepcopy(compiled['activation_proposal']),
        'targets':targets,'tls_config_identity_sha256':d.digest({k:v for k,v in config.items() if k!='release_sha256'})}
    d.build_delta(snapshot,d.digest(snapshot),value)
    return value


def boot_before_from_observation(observation,compiled):
    """Finite v239 restored-unit states; unknown aliases/runtime links HOLD.

    Source: systemd/v239 src/shared/install.c 659-877,2425-2495 and
    src/shared/path-lookup.c 525-545. No masked=>disabled default exists.
    """
    from unit_metadata import install_fields
    metadata=observation['unit_metadata'];need(d.digest(metadata)==observation['unit_metadata_sha256'],
         'FACTORY_BOOT_METADATA_DIGEST')
    sections=metadata['sections'];section=sections.get('boot_links',{})
    need(section.get('state')=='MEASURED_UNREVIEWED','FACTORY_BOOT_LINK_OBSERVATION_REQUIRED')
    evidence=section['evidence'];need(set(evidence['units'])==BOOT_RESTORED and
         evidence['unsupported_roots']==[] and set(evidence['roots'])==BOOT_LOOKUP_ROOTS,
         'FACTORY_BOOT_COMPLETE_LOOKUP_ROOTS')
    for root,row in evidence['roots'].items():
        need(type(row.get('present')) is bool and type(row.get('links')) is list and
             (row['present'] is False and set(row)=={'present','directories','links'} and row.get('directories')=={} and row['links']==[] or
              row['present'] is True and row.get('scan_scope')=='BOUNDED_RECURSIVE_NOFOLLOW' and root in row['directories']),
             'FACTORY_BOOT_RECURSIVE_INVENTORY')
        if row['present']:
            need(type(row.get('selected_nonlinks')) is dict,'FACTORY_BOOT_NONLINK_INVENTORY_REQUIRED')
            # Only a lower-priority canonical vendor base is unambiguous: the
            # exact restored /etc base wins. Runtime control/transient/generator
            # entries cannot be ignored when predicting the restored state.
            for path,item in row['selected_nonlinks'].items():
                need(root=='/usr/lib/systemd/system' and path in {root+'/'+u for u in BOOT_RESTORED} and
                     item['kind']=='FILE' and item['metadata']['uid']==item['metadata']['gid']==0 and
                     item['metadata']['nlink']==1 and not item['metadata']['mode']&0o022,
                     'FACTORY_BOOT_UNSUPPORTED_SELECTED_NONLINK')
    compiled=compiled_bytes(compiled);result={};states=observation['evidence']['writers']['units']
    for unit in BOOT_UNITS:
        state=states[unit]['state'];path='/etc/systemd/system/'+unit
        if unit not in BOOT_RESTORED:
            need(state['UnitFileState'] in ('enabled','disabled'),'FACTORY_BOOT_EXISTING_ENABLEMENT')
            if path in compiled['rendered_targets']:
                need(install_fields(compiled['rendered_targets'][path])==install_fields(compiled['old_rendered_targets'][path]),
                     'FACTORY_BOOT_INSTALL_RULES_CHANGED')
            result[unit]=state['UnitFileState'];continue
        need(state['UnitFileState']=='masked' and state['LoadState']=='masked','FACTORY_BOOT_EXACT_RESTORED_MASK')
        if unit=='xuanjun-uk-openclaw.service':
            legacy=sections['legacy_gateway'];need(legacy['state']=='MEASURED_UNREVIEWED','FACTORY_BOOT_GATEWAY_INSTALL_FIELDS')
            fields=legacy['evidence']['public_install_fields']
        else:fields=install_fields(compiled['rendered_targets'][path])
        need(set(fields)=={'WantedBy','RequiredBy','Alias','Also'},'FACTORY_BOOT_INSTALL_FIELDS')
        def effective(name):
            values=[]
            for text in fields[name]:
                need(type(text) is str,'FACTORY_BOOT_INSTALL_LITERAL')
                if text:values.extend(text.split())
                else:values=[]
            return values
        need(not effective('Alias') and not effective('Also') and
             (effective('WantedBy') or effective('RequiredBy')),'FACTORY_BOOT_SUPPORTED_INSTALL_RULES')
        persistent=False
        for root,row in evidence['roots'].items():
            for link in row['links']:
                if link['unit']!=unit:continue
                need(link['path'].startswith(root+'/') and link['metadata']['uid']==link['metadata']['gid']==0 and
                     link['metadata']['nlink']==1,'FACTORY_BOOT_LINK_AUTHORITY')
                if link['kind']=='BASE_MASK':
                    need(link['path']==path and link['link']=='/dev/null','FACTORY_BOOT_UNEXPECTED_MASK');continue
                need(link['kind']=='DEPENDENCY' and os.path.basename(link['path'])==unit and
                     link['resolved_reference']==path,'FACTORY_BOOT_UNSUPPORTED_ALIAS')
                need(root=='/etc/systemd/system','FACTORY_BOOT_NONPERSISTENT_LINK_REQUIRES_REVIEW')
                persistent=True
        result[unit]='enabled' if persistent else 'disabled'
    return result


def startup_source_specs(observation,facts):
    from epoch7_resource_plan import file_spec
    from epoch7_openclaw_recipe import source_hashes
    value=facts['openclaw_recipe_evidence'];root=value['package_root'];rows=[]
    pins=source_hashes(value['launcher']['sha256'])
    need(set(value['files'])==set(pins),'FACTORY_COMPLETE_STARTUP_SOURCE_SET')
    for name,pin in sorted(pins.items()):
        row=value['files'][name]
        need(row['sha256']==pin,'FACTORY_STARTUP_SOURCE_PIN')
        rows.append(file_spec(root+'/'+name,dict(row['metadata'],sha256=pin)))
    source=observation['source_review_inputs']
    need(d.digest(source)==observation['source_review_inputs_sha256'],'FACTORY_STARTUP_SOURCE_EVIDENCE')
    mime=source['sections']['nginx_mime_types']
    need(mime['state']=='MEASURED_UNREVIEWED','FACTORY_NGINX_MIME_MEASURED')
    mime=mime['evidence'];need(mime['path']=='/etc/nginx/mime.types' and
         mime['metadata']['sha256']==mime['sha256'],'FACTORY_NGINX_MIME_PIN')
    rows.append(file_spec(mime['path'],mime['metadata']))
    return rows


def validated_finite_probe(observation):
    """Pure binding check; protected loader authenticates the original receipt.

    The independent earlier probe policy is never replaced by the later service
    plan hash. A self-consistent leaf proof alone cannot satisfy this boundary.
    """
    from node_sqlite_probe import validated_proof_from_attempt
    attempt=observation.get('finite_probe')
    need(type(attempt) is dict and type(attempt.get('policy')) is dict and
         type(attempt.get('policy_sha256')) is str,'FACTORY_ORIGINAL_FINITE_PROBE_PACKAGE_REQUIRED')
    original={key:copy.deepcopy(value) for key,value in observation.items() if key!='finite_probe'}
    d.hash_value(attempt['policy_sha256'])
    return validated_proof_from_attempt(attempt,attempt['policy'],original,attempt['policy_sha256'])


def measured_service_facts(observation,manifest_raw,boot_before,payloads):
    processes=observation['evidence']['writers']['processes']
    need(type(processes.get('background_processes')) is list and
         d.digest(processes['background_processes'])==processes.get('background_processes_sha256'),
         'FACTORY_MEASURED_BACKGROUND_PROCESS_PROJECTION')
    value=service_facts_from_observation(observation,manifest_raw,boot_before,
        processes['background_processes'],source_bytes=payloads)
    need(value['unsupported_sections']==[],'FACTORY_COMPLETE_SERVICE_METADATA')
    return value['fresh_facts']


def observation_inputs(observation):
    """Immutable provenance plus finite typed observations from one capture."""
    need(type(observation) is dict and observation.get('kind')=='EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
         'FACTORY_COMPLETE_OBSERVATION_REQUIRED')
    for name in ('snapshot','evidence','policy','probe_metadata','unit_metadata'):
        need(d.digest(observation[name])==observation[name+'_sha256'],'FACTORY_OBSERVATION_'+name.upper()+'_DIGEST')
    manager=observation['evidence']['writers']['manager']
    need(manager.get('uids')==[0,0,0,0] and all(type(v) is int for v in manager['uids']) and
         manager['pid']==1 and manager['binary_path'] in ('/usr/lib/systemd/systemd','/lib/systemd/systemd'),
         'FACTORY_MEASURED_SYSTEM_MANAGER')
    return {'snapshot':copy.deepcopy(observation['snapshot']),
        'supporting_evidence':copy.deepcopy(observation['evidence']),
        'snapshot_policy':copy.deepcopy(observation['policy']),
        'manager':{'pid':1,'uids':copy.deepcopy(manager['uids']),'starttime':manager['starttime'],'boot_id':manager['boot_id'],
            'executable':manager['binary_path'],'executable_sha256':manager['binary_sha256'],
            'channels_sha256':d.digest(manager['channels'])},
        'timer_raw_baseline':timer_baseline_from_observation(observation['probe_metadata']['retained_tls_schedule']),
        'database_sidecar_policy':copy.deepcopy(SIDECAR_POLICY)}


def _proposal(inputs):
    need(type(inputs) is dict and set(inputs)==INPUTS and not missing_inputs(inputs),
         'FACTORY_EXACT_COMPLETE_MEASURED_INPUTS_REQUIRED')
    measured=observation_inputs(inputs['observation'])
    need(all(input_digest(inputs[key])==input_digest(value) for key,value in measured.items()),'FACTORY_DERIVED_OBSERVATION_FIELDS')
    need(d.same(inputs['snapshot'],inputs['observation']['snapshot']) and
         d.same(inputs['supporting_evidence'],inputs['observation']['evidence']) and
         d.same(inputs['snapshot_policy'],inputs['observation']['policy']),'FACTORY_ONE_OBSERVATION_BINDING')
    validated_finite_probe(inputs['observation'])
    s=inputs['snapshot'];support=inputs['supporting_evidence'];policy=inputs['snapshot_policy']
    snapshot_sha=d.digest(s);d.validate_snapshot(s,snapshot_sha);snap.validate_policy(policy)
    need(support['snapshot_sha256']==snapshot_sha and d.digest(support['retained'])==s['retained_resource_sha256'] and
         support['retained']['policy_sha256']==d.digest(policy),'FACTORY_SUPPORTING_SNAPSHOT_BINDING')
    d.validate_provision_before(s,inputs['prior_provision_bytes'])
    c=inputs['candidate'];compiled=compiled_bytes(inputs['compiled'])
    need(d.same(c,candidate_from_compiled(compiled,s)),'FACTORY_SOURCE_DERIVED_CANDIDATE')
    need(compiled['kind']=='PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN' and compiled['install_admission'] is False and
         compiled['manifest_sha256']==c['manifest_sha256']==MANIFEST and
         compiled['source_commit']==SOURCE and compiled['source_tree']==SOURCE_TREE and
         type(compiled.get('control_repository_reconciliation')) is dict and
         d.same(compiled['control_repository_reconciliation']['observation'],support['retained'].get('control_git')) and
         compiled['control_repository_reconciliation']['observation_sha256']==d.digest(support['retained']['control_git']) and
         compiled.get('control_repository_reconciliation') is not None and
         d.same(compiled['activation_proposal'],c['activation']),'FACTORY_CURRENT_SOURCE_BINDING')
    need(set(compiled['rendered_targets'])==set(d.TARGETS) and len(c['targets'])==24,'FACTORY_EXACT24_TARGETS')
    rows={r['target']:r for r in compiled['runtime']['provisioning']}
    need(set(rows)==set(d.TARGETS),'FACTORY_RUNTIME_PROVISIONING_SET')
    for path,raw in compiled['rendered_targets'].items():
        need(sha(raw)==c['targets'][path]['sha256']==rows[path]['rendered_sha256'], 'FACTORY_TARGET_BYTES_BINDING')
    need(compiled['tls_config_bytes']==compiled['rendered_targets'][bindings.TLS],'FACTORY_TLS_RENDERED_BINDING')
    additions=copy.deepcopy(inputs['additive_deltas'])
    need(type(additions) is list and len(additions)==2 and len({x['path'] for x in additions})==2,
         'FACTORY_TWO_IDENTITY_PROPOSALS')
    additions.sort(key=lambda x:x['path'])
    need(set(inputs['identity_payloads'])=={x['path'] for x in additions},'FACTORY_IDENTITY_PAYLOAD_SET')
    for row in additions:
        need(sha(inputs['identity_payloads'][row['path']])==row['after']['sha256'],'FACTORY_IDENTITY_PAYLOAD_BINDING')
    delta=d.build_delta(s,snapshot_sha,c);security=d.digest(inputs['access_rows'])
    authorization=required_authorization(delta,inputs['kit_manifest_sha256'],security,additions)
    neutral=preapproval_sequence_contract(delta,authorization)
    native=decode(inputs['native_before']);old=native['ledger']
    native_transition,unused_native_records=retained_native_transition(s,support,inputs['native_before'])
    native_after=bindings.native_sidefile_delta(inputs['native_before'],compiled,
        old['files'][old['bridge']],old['files'][old['config']],native_transition)
    tls_after=tls_metadata_candidate(inputs['tls_journal_before'],compiled['tls_config_bytes'],s['tls'])
    need(sha(inputs['installer_source'])==INSTALLER_SHA,'FACTORY_PINNED_STAGER_SOURCE')
    a=inputs['artifact']
    need(type(a) is dict and set(a)=={'root','manifest','source_commit','source_tree','manifest_sha256','releases'} and
         a['source_commit']==SOURCE and a['source_tree']==SOURCE_TREE and a['manifest_sha256']==MANIFEST and
         a['releases']=='/opt/xuanjun-control-releases','FACTORY_ARTIFACT_BINDING')
    for key in ('root','manifest','releases'):
        need(type(a[key]) is str and os.path.isabs(a[key]) and os.path.normpath(a[key])==a[key],
             'FACTORY_ARTIFACT_ABSOLUTE_PATH')
    need(d.same(inputs['boot_before'],boot_before_from_observation(inputs['observation'],compiled)),
         'FACTORY_SOURCE_DERIVED_BOOT_BASELINE')
    need(type(inputs['boot_before']) is dict and set(inputs['boot_before'])==set(BOOT_UNITS) and
         all(v in ('enabled','disabled') for v in inputs['boot_before'].values()),'FACTORY_POST_RESTORE_BOOT_MAP')
    need(type(inputs['activate_retained_renewal_timer']) is bool,'FACTORY_EXPLICIT_TIMER_DECISION')
    command_contract(compiled,inputs['activate_retained_renewal_timer'])
    dbs={path:{k:support['retained']['database_sets'][path]['file'][k] for k in ('dev','ino')}
         for path in snap.DATABASES}
    live=compile_checkpoint_contract({'snapshot_sha256':snapshot_sha,'database_identities':dbs},
        inputs['resource_views'],inputs['unit_checkpoints'],inputs['manager'],inputs['process_roles'],
        inputs['database_sidecar_policy'],retained_sidecar_pins(support),
        inputs['service_role_contract'],inputs['unit_transition_contract'])
    validate_contract(live,neutral)
    tls={'journal':fs.TRANSACTION+'/tls-lifecycle.json','journal_sha256':sha(tls_after),
         'root':snap.TLS,'tree_sha256':s['tls']['tree_fingerprint_sha256'],
         'certificate_sha256':s['tls']['certificate_sha256'],
         'config_sha256':d.digest(decode(compiled['tls_config_bytes'])),
         'domain':'uk.wenwenwenyiyiyi.work','manifest_sha256':MANIFEST}
    need(sha(inputs['sandbox_candidate_raw'])==compiled['runtime']['sandbox_policy']['sha256'] and
         sha(inputs['legacy_units_raw'])==s['receipts']['legacy-units.json'],'FACTORY_RETAINED_INPUT_BYTES')
    wanted_access=build_access_rows(support,compiled)
    need(d.same(inputs['access_rows'],wanted_access),'FACTORY_SOURCE_DERIVED_ACCESS_ROWS')
    rendered=rendered_release_hashes(inputs['source_manifest_raw'],inputs['source_payloads'],inputs['installer_source'])
    need(d.same(inputs['acceptance_facts'],acceptance_facts_from_observation(inputs['observation'])),
         'FACTORY_MEASURED_ACCEPTANCE_FACTS')
    wanted_acceptance=compile_access_rows(compiled,inputs['identity_payloads'],inputs['source_manifest_raw'],rendered,
                                         inputs['acceptance_facts'])
    need(d.same(inputs['acceptance_access_rows'],wanted_acceptance),'FACTORY_SOURCE_DERIVED_ACCEPTANCE_ROWS')
    need(input_digest(inputs['service_facts'])==input_digest(measured_service_facts(inputs['observation'],inputs['source_manifest_raw'],
        inputs['boot_before'],inputs['source_payloads'])),'FACTORY_MEASURED_SERVICE_FACTS')
    need(d.same(inputs['service_facts']['boot_before'],inputs['boot_before']),'FACTORY_SERVICE_BOOT_BINDING')
    service_result=compile_service_contract(compiled,inputs['identity_payloads'],inputs['native_before'],
        inputs['acceptance_facts']['gateway_base_unit'],inputs['service_facts'],candidate_delta=delta)
    service=require_complete_service_contract(service_result)
    restored=service['unit_transition_contract'].get('gateway_restoration')
    legacy_gateway=decode(inputs['legacy_units_raw'])['units']['xuanjun-uk-openclaw.service']
    need(type(restored) is dict and all(restored[k]==legacy_gateway[k] for k in ('path','sha256','uid','gid','mode')) and
         restored['legacy_receipt_sha256']==s['receipts']['legacy-units.json'] and
         restored['boot_before']==inputs['boot_before']['xuanjun-uk-openclaw.service'],
         'FACTORY_EXACT_RESTORED_GATEWAY_POLICY_REQUIRED')
    need(d.same(inputs['unit_checkpoints'],service['unit_checkpoints']) and
         d.same(inputs['process_roles'],service['process_roles']) and
         d.same(inputs['service_role_contract'],service['service_role_contract']) and
         d.same(inputs['unit_transition_contract'],service['unit_transition_contract']),'FACTORY_SOURCE_DERIVED_SERVICE_POLICY')
    wanted_views=build_resource_views(s,support,compiled,additions,wanted_access,inputs['source_manifest_raw'],
        inputs['source_payloads'],inputs['installer_source'],native_after,inputs['tls_journal_before'],
        inputs['sandbox_candidate_raw'],decode(inputs['legacy_units_raw']),executable_specs=inputs['executable_specs'],policy=inputs['snapshot_policy'],
        publisher_journal_raw=inputs['publisher_journal_raw'],nss_projection=nss_projection(inputs['observation']),
        startup_sources=startup_source_specs(inputs['observation'],inputs['service_facts']))
    need(d.same(inputs['resource_views'],wanted_views) and
         d.same(inputs['resource_directories'],build_resource_directories(policy,wanted_views)),
         'FACTORY_SOURCE_DERIVED_COMPLETE_RESOURCE_VIEWS')
    acceptance=compile_acceptance_contract(neutral,inputs['acceptance_access_rows'],tls)
    runtime_database_before(support)
    compile_timer_contract(inputs['timer_raw_baseline'])
    executable_specs=inputs['executable_specs']
    need(type(executable_specs) is dict and executable_specs and all(k==v.get('path') and v.get('kind') in ('FILE','EXECUTABLE_REFERENCE')
         for k,v in executable_specs.items()),'FACTORY_EXACT_EXECUTABLE_SPECS')
    need(d.same(executable_specs,build_executable_specs(inputs['observation'],inputs['native_before'])),
         'FACTORY_SOURCE_DERIVED_EXECUTABLE_PINS')
    required={'/usr/bin/systemctl','/usr/bin/python3','/usr/bin/git','/usr/sbin/runuser','/usr/sbin/nginx',
              '/home/xuanjun_dev/.openclaw/bin/openclaw',old['python']}|{v['path'] for v in policy['executables'].values()}
    need(required<=set(executable_specs),'FACTORY_MISSING_EXECUTABLE_PINS')
    return compiled,delta,authorization,neutral,native_after,tls_after,live,tls,acceptance


DERIVED_INPUTS=frozenset(('access_rows','acceptance_access_rows','resource_views','resource_directories',
                          'unit_checkpoints','process_roles','service_role_contract','unit_transition_contract','executable_specs','acceptance_facts',
                          'snapshot','supporting_evidence','snapshot_policy','manager','timer_raw_baseline','database_sidecar_policy','service_facts','candidate','boot_before'))


CACHE_INPUTS=frozenset(('installer_source','source_manifest_raw','source_payloads','artifact','kit_manifest_sha256'))
PRIVATE_BYTE_INPUTS=frozenset(('native_before','tls_journal_before','prior_provision_bytes',
    'legacy_units_raw','publisher_journal_raw','sandbox_candidate_raw'))


def host_input_contract():
    """Finite protected-loader input endpoint; no observations or effects."""
    seed=INPUTS-DERIVED_INPUTS
    return {'schema':1,'seed_fields':sorted(seed),'cached_fields':sorted(CACHE_INPUTS),
        'private_fields':sorted(seed-CACHE_INPUTS),'private_utf8_byte_fields':sorted(PRIVATE_BYTE_INPUTS),
        'identity_utf8_byte_paths':['/etc/xuanjun-development/p2-ledger-server-identity.json',
                                  '/etc/xuanjun-development/p2-owner-process-identity.json'],
        'source_commit':SOURCE,'source_tree':SOURCE_TREE,'runtime_manifest_sha256':MANIFEST,
        'derived_fields':sorted(DERIVED_INPUTS),'install_admission':False}


def prepare_host_inputs(seed):
    """Derive all ACL/access/resource/service rows from one pinned finite seed.

    This returns explicit source/compiler HOLDs for unsupported active wrappers;
    an Owner is never asked to fill future checkpoint hashes or process argv.
    """
    need(type(seed) is dict and set(seed)==INPUTS-DERIVED_INPUTS and
         all(v is not None for v in seed.values()),'FACTORY_COMPLETE_MEASURED_SEED_REQUIRED')
    value=copy.deepcopy(seed);value.update(observation_inputs(value['observation']))
    if 'finite_probe' not in value['observation']:
        return {'state':'HOLD','unresolved':[{'unit':'xuanjun-uk-openclaw.service',
            'code':'ORIGINAL_FINITE_PROBE_PACKAGE_REQUIRED'}],'install_admission':False,'inputs':None}
    validated_finite_probe(value['observation'])
    compiled=compiled_bytes(value['compiled'])
    native_transition,unused_native_records=retained_native_transition(
        value['snapshot'],value['supporting_evidence'],value['native_before'])
    value['candidate']=candidate_from_compiled(compiled,value['snapshot'])
    value['boot_before']=boot_before_from_observation(value['observation'],compiled)
    value['executable_specs']=build_executable_specs(value['observation'],value['native_before'])
    value['acceptance_facts']=acceptance_facts_from_observation(value['observation'])
    value['service_facts']=measured_service_facts(value['observation'],value['source_manifest_raw'],value['boot_before'],value['source_payloads'])
    access=build_access_rows(value['supporting_evidence'],compiled)
    rendered=rendered_release_hashes(value['source_manifest_raw'],value['source_payloads'],value['installer_source'])
    acceptance=compile_access_rows(compiled,value['identity_payloads'],value['source_manifest_raw'],rendered,value['acceptance_facts'])
    service=compile_service_contract(compiled,value['identity_payloads'],value['native_before'],
        value['acceptance_facts']['gateway_base_unit'],value['service_facts'],
        candidate_delta=d.build_delta(value['snapshot'],d.digest(value['snapshot']),value['candidate']))
    if service['state']!='COMPLETE':
        return {'state':'HOLD','unresolved':copy.deepcopy(service['unresolved']),
                'install_admission':False,'inputs':None}
    service=require_complete_service_contract(service)
    old=decode(value['native_before'])['ledger']
    native_after=bindings.native_sidefile_delta(value['native_before'],compiled,
        old['files'][old['bridge']],old['files'][old['config']],native_transition)
    views=build_resource_views(value['snapshot'],value['supporting_evidence'],compiled,value['additive_deltas'],
        access,value['source_manifest_raw'],value['source_payloads'],value['installer_source'],native_after,
        value['tls_journal_before'],value['sandbox_candidate_raw'],decode(value['legacy_units_raw']),executable_specs=value['executable_specs'],policy=value['snapshot_policy'],
        publisher_journal_raw=value['publisher_journal_raw'],nss_projection=nss_projection(value['observation']),
        startup_sources=startup_source_specs(value['observation'],value['service_facts']))
    value.update(access_rows=access,acceptance_access_rows=acceptance,resource_views=views,
        resource_directories=build_resource_directories(value['snapshot_policy'],views),
        unit_checkpoints=service['unit_checkpoints'],process_roles=service['process_roles'],
        service_role_contract=service['service_role_contract'],unit_transition_contract=service['unit_transition_contract'])
    compile_host_contract(value)
    return {'state':'COMPILED_NOT_ADMITTED','unresolved':[],'install_admission':False,'inputs':value}


def compile_host_contract(inputs):
    compiled,delta,authorization,neutral,native_after,tls_after,live,tls,acceptance=_proposal(inputs)
    return {'host_contract':{'schema':1,'input_sha256':input_digest(inputs),
                'sequence_contract_sha256':sequence_contract_sha256(neutral),
                'native_after_sha256':sha(native_after),'tls_after_sha256':sha(tls_after),
                'acceptance_contract_sha256':d.digest(acceptance),
                'timer_contract_sha256':d.digest(compile_timer_contract(inputs['timer_raw_baseline'])),
                'production_acceptance':'PENDING'},
            'resource_observer':{'views_sha256':d.digest(inputs['resource_views']),
                'directories_sha256':d.digest(inputs['resource_directories']),
                'snapshot_policy_sha256':d.digest(inputs['snapshot_policy'])},
            'live_controls':live}


class ExecutablePins(object):
    def __init__(self,reader,specs):self.reader=reader;self.specs=copy.deepcopy(specs);self.digest=d.digest(specs)
    def begin_guard(self,deadline):self.reader.guard_deadline=deadline
    def __call__(self,path):
        need(d.digest(self.specs)==self.digest and path in self.specs,'FACTORY_UNREVIEWED_EXECUTABLE')
        self.reader.start();spec=self.specs[path]
        if spec['kind']=='EXECUTABLE_REFERENCE':return self.reader.executable_reference(spec['reference'])
        self.reader.observe(spec);return True


def assemble_host_driver(approved_plan_raw,inputs,review_id,review_body_sha256):
    """Return the actual driver; never execute it or substitute approval/pins."""
    contract=compile_host_contract(inputs)
    need(type(approved_plan_raw) is bytes,'FACTORY_REVIEWED_PLAN_BYTES')
    plan=decode(approved_plan_raw)
    need(all(name in plan and d.same(plan[name],value) for name,value in contract.items()),
         'FACTORY_COMPLETE_REVIEWED_PLAN_BINDING')
    compiled,delta,authorization,neutral,native_after,tls_after,live,tls,acceptance=_proposal(inputs)
    context=dict(neutral,review_id=review_id);context['context_sha256']=d.digest(context)
    sequence_contract(context)  # Checks genuine fresh ID shape; never fetches it here.
    support=inputs['supporting_evidence']['retained'];files=support['files']
    lock=ExistingInstallLock(files[snap.INSTALL_LOCK])
    activation=BoundedActivationStore(files[snap.ACTIVATION_LOCK])
    verifier=CompleteApprovalVerifier(review_id,review_body_sha256,lock.held)
    binding={'review_id':review_id,'approval_body_sha256':review_body_sha256,
             'authorization_sha256':d.digest(authorization),'delta_sha256':d.digest(delta),
             'complete_delta_sha256':authorization['complete_delta_sha256'],
             'additive_targets_sha256':authorization['additive_targets_sha256'],
             'snapshot_sha256':context['snapshot_sha256']}
    authority=ClaimAuthority(lock,verifier,context,binding)
    def publish(evidence):
        authority.receipt()
        return command_evidence.publish_protected(fs.TRANSACTION,evidence)
    diagnostics=BoundedDiagnostics(publish)
    reader=ResourceReader(inputs['resource_directories'],authority)
    executable=ExecutablePins(reader,inputs['executable_specs'])
    resources=CheckpointResources(context,reader,inputs['resource_views'],contract['resource_observer']['views_sha256'])
    census=LinuxProcessCensus(context,authority,diagnostics,executable,live['database_identities'],live['manager'],live['retained_sidecar_pins'])
    retained_tls=BoundedRetainedTLS(inputs['snapshot_policy'],authority,diagnostics,executable)
    observer=Epoch7HostObserver(context,inputs['snapshot_policy'],d.digest(inputs['snapshot_policy']),
        lock,activation,authority,resources,census,retained_tls,inputs['snapshot'])
    guards=PreActiveGateGuards(observer,authority,diagnostics,executable)
    gate=RecoveryGate(inputs['snapshot'],inputs['candidate'],context['snapshot_sha256'],
        inputs['kit_manifest_sha256'],context['security_delta_sha256'],review_id,verifier,guards,
        inputs['prior_provision_bytes'],additive_deltas=inputs['additive_deltas'])
    verifier.bind(gate,sha(approved_plan_raw))
    need(d.same(context,context_from_gate(gate)),'FACTORY_CONTEXT_CONSTRUCTION_MISMATCH')
    controls=FiniteLiveControls(approved_plan_raw,context,verifier,lock,authority,observer)
    outer_io=HostPhaseFilesystem(authority);retained_io=fs.ProtectedFilesystem(gate)
    installer=FrozenBoundedInstaller(inputs['installer_source'],inputs['artifact']['root'],decode(inputs['native_before'])['ledger']['python'],
        lambda:controls.effect_check(context,'stage_exact_release'),executable,diagnostics)
    native_transition,native_records=retained_native_transition(inputs['snapshot'],inputs['supporting_evidence'],inputs['native_before'])
    core=CoreHostPhases(outer_io,activation,controls,context,sha(approved_plan_raw),inputs['snapshot'],
        inputs['candidate'],inputs['native_before'],native_after,files[snap.NATIVE],
        compiled['tls_config_bytes'],installer,inputs['artifact'],
        native_transition=native_transition,native_proof_metadata=native_records)
    guards.bind(gate,retained_io,core,controls)
    checks=RuntimeAcceptanceChecks(context,inputs['acceptance_access_rows'],tls,controls.effect_check,
        diagnostics,d.digest(acceptance))
    scanner=BoundedContainmentScanner(census,authority)
    timer_tail=RetainedRenewalTail(context,authority,diagnostics,executable,inputs['timer_raw_baseline'],
        contract['host_contract']['timer_contract_sha256'],controls)
    runtime=DeferredRenewalRuntime(fs.TRANSACTION,compiled,context,activation.read,
        controls.effect_check,controls.cleanup_check,diagnostics,runtime_database_before(inputs['supporting_evidence']),
        checks.verify_runtime_access,checks.post_install_checks,inputs['boot_before'],
        activate_retained_renewal_timer=inputs['activate_retained_renewal_timer'],containment_scanner=scanner,timer_tail=timer_tail)
    observer.bind_effects(gate,runtime,outer_io)
    def before(path):
        need(path in ACCESS_TARGETS,'FACTORY_ACCESS_RESOLVER_SCOPE')
        if path=='/opt/xuanjun-control-releases':
            need(hasattr(core,'staged_release_parent'),'FACTORY_STAGE_OBSERVATION_REQUIRED')
            return copy.deepcopy(core.staged_release_parent)
        row=copy.deepcopy(gate.current_targets[path])
        need(row['sha256']==inputs['candidate']['targets'][path]['sha256'],'FACTORY_OWNED_REPLACEMENT_REQUIRED')
        return dict(row,access_acl='user::rw-\ngroup::r--\nother::---\n',default_acl='')
    access=ExactAccessApplier(outer_io,context,inputs['access_rows'],context['security_delta_sha256'],controls.effect_check,before)
    legacy=BoundLegacyFiles(outer_io,context,inputs['snapshot']['receipts']['legacy-units.json'],
        controls.effect_check,controls.cleanup_check,diagnostics,executable)
    runtime.bind_legacy(legacy)
    containment=HostContainment(outer_io,context,core,runtime,legacy,controls.cleanup_check,observer)
    return compose_driver(gate,controls,core,runtime,access,legacy,containment,outer_io,retained_io,
                          diagnostics,{r['path']:compiled['rendered_targets'][r['path']] for r in delta['changes'] if r['operation']!='RETAIN'},
                          inputs['identity_payloads'])
