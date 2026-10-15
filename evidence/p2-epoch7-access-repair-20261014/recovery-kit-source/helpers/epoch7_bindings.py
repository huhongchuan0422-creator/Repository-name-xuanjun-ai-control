"""Pure in-memory24 retained-target compiler; no install or source authority.

Private output contains reference metadata and must not be published. Additional
Owner/server identity targets, host snapshot, ACLs and approval remain separate.
"""
import copy
import hashlib
import json
import re

OLD_MANIFEST = '153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7'
OLD_PLAN = '5938dad82a8597f8ac18af078843cfa30e8245729101b65dbc861e38f877edeb'
RENDERER = '943f4d04861d8b580008af457d90187622a9de2d1c8cd66c93a721b8ac2be0f3'
REVIEWED_CONTROLLER_MANIFEST = '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c'
REVIEWED_CONTROLLER_BINARY = '1de3690ede78832da9dd2f2607db0b5ae88d6f9d4de87e1cb1ce64f35dab8421'
CONTROLLER_PATH = 'stage1/native_gateway_controller.py'
RENDERER_PATH = 'scripts/uk-integration-install.py'
CLIENT = '/etc/xuanjun-development/p2-native-ledger-client.json'
BINDING = '/etc/xuanjun-development/p2-native-controller.binding.json'
DISPATCHER = '/etc/xuanjun-development/dispatcher.json'
TLS = '/etc/xuanjun-development/tls-renewal.json'
TOKEN = re.compile(br'@@[A-Z0-9_]+@@')


def sha(raw): return hashlib.sha256(raw).hexdigest()

def need(value, reason):
    if not value: raise ValueError('EPOCH7_BINDINGS_' + reason)

def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON')
            result[key] = value
        return result
    def constant(unused): raise ValueError('EPOCH7_BINDINGS_NONFINITE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)

def render(raw, replacements):
    need(type(replacements) is dict, 'REPLACEMENTS')
    for key, value in sorted(replacements.items()):
        need(type(key) is str and re.fullmatch(r'@@[A-Z0-9_]+@@', key)
             and type(value) is str, 'REPLACEMENT_TYPE')
        raw = raw.replace(key.encode('ascii'), value.encode('utf-8'))
    need(not TOKEN.search(raw), 'UNRESOLVED_TOKEN')
    return raw

def checked_manifest(raw, payload):
    manifest = parse(raw)
    need(type(payload) is dict and type(manifest.get('files')) is dict
         and set(payload) == set(manifest['files']), 'EXACT_PAYLOAD_SET')
    for path, expected in manifest['files'].items():
        need(type(path) is str and path and not path.startswith('/')
             and all(p not in ('', '.', '..') for p in path.split('/'))
             and '\\' not in path and '\0' not in path, 'PAYLOAD_PATH')
        need(type(payload[path]) is bytes and sha(payload[path]) == expected,
             'PAYLOAD_HASH')
    need(sha(payload[RENDERER_PATH]) == RENDERER, 'PINNED_RENDERER')
    return manifest

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('utf-8')

def reconcile_control_source(old_dispatcher_raw,publisher,reconciliation):
    """Separate retained task-repository identity from runtime package identity.

    This pure check proposes bytes only. The complete review must bind the
    reconciliation and the loader must match its observation against the fresh
    snapshot's evidence.retained.control_git; these assertions grant no authority.
    """
    old=parse(old_dispatcher_raw);old_commit=old.get('source_commit')
    need(type(publisher) is dict and set(publisher)=={'path','sha256','source_commit','source_tree'}
         and all(type(publisher[k]) is str and re.fullmatch(r'[0-9a-f]{40}',publisher[k])
                 for k in ('source_commit','source_tree')),'RETAINED_PUBLISHER_REFERENCE')
    need(type(old_commit) is str and re.fullmatch(r'[0-9a-f]{40}',old_commit), 'RETAINED_DISPATCHER_SOURCE')
    if reconciliation is None:
        need(old_commit==publisher['source_commit'],'EXPLICIT_CONTROL_HEAD_RECONCILIATION_REQUIRED')
        return old_commit,None
    keys={'schema','purpose','old_dispatcher_sha256','old_source_commit',
          'publisher_reference_sha256','observation_sha256','observation'}
    need(type(reconciliation) is dict and set(reconciliation)==keys and
         type(reconciliation['schema']) is int and reconciliation['schema']==1 and
         reconciliation['purpose']=='DISPATCHER_RETAINED_CONTROL_HEAD','CONTROL_RECONCILIATION_SCHEMA')
    ref_sha=sha(canonical(publisher));observed=reconciliation['observation']
    need(reconciliation['old_dispatcher_sha256']==sha(old_dispatcher_raw) and
         reconciliation['old_source_commit']==old_commit and
         reconciliation['publisher_reference_sha256']==ref_sha,'CONTROL_OLD_BINDINGS')
    fields={'schema','path','head_commit','head_tree','publisher_reference_sha256',
            'publisher_journal_sha256','publisher_fingerprint_sha256','git_sha256'}
    need(type(observed) is dict and set(observed)==fields and type(observed['schema']) is int and
         observed['schema']==1 and observed['path']=='/var/lib/xuanjun-development/control.git',
         'CONTROL_OBSERVATION_SCHEMA')
    need(observed['head_commit']==publisher['source_commit'] and
         observed['head_tree']==publisher['source_tree'] and
         observed['publisher_reference_sha256']==ref_sha,'CONTROL_RETAINED_HEAD_MISMATCH')
    need(all(type(observed[k]) is str and re.fullmatch(r'[0-9a-f]{64}',observed[k]) for k in
         ('publisher_journal_sha256','publisher_fingerprint_sha256','git_sha256')) and
         reconciliation['observation_sha256']==sha(canonical(observed)),'CONTROL_OBSERVATION_DIGEST')
    return observed['head_commit'],copy.deepcopy(reconciliation)

def bind_controller_binary(original_activation,old_manifest,new_manifest,new_manifest_sha256):
    """No authority: bind source bytes; changed controller has one finite pair."""
    old_binary=old_manifest['files'][CONTROLLER_PATH]
    new_binary=new_manifest['files'][CONTROLLER_PATH]
    need(original_activation['binary_sha256']==old_binary,'ORIGINAL_CONTROLLER_MANIFEST_BINDING')
    if new_binary!=old_binary or new_manifest_sha256==REVIEWED_CONTROLLER_MANIFEST:
        need((new_manifest_sha256,new_binary)==(REVIEWED_CONTROLLER_MANIFEST,REVIEWED_CONTROLLER_BINARY),
             'CONTROLLER_BINARY_CHANGED_UNREVIEWED_PAIR')
    return new_binary


def compile_retained_bindings(old_plan_raw, old_manifest_raw, old_payload,
                              new_manifest_raw, new_payload, source_commit, source_tree,
                              control_reconciliation=None):
    need(sha(old_plan_raw) == OLD_PLAN and sha(old_manifest_raw) == OLD_MANIFEST,
         'EXACT_V4_INPUTS')
    need(all(type(v) is str and re.fullmatch(r'[0-9a-f]{40}', v)
             for v in (source_commit, source_tree)), 'SOURCE_IDENTIFIERS')
    old = checked_manifest(old_manifest_raw, old_payload)
    new = checked_manifest(new_manifest_raw, new_payload)
    need(len(old['files']) == 102 and set(old['files']).issubset(new['files']), 'NO_DELETIONS')
    need({k:v for k,v in old.items() if k != 'files'} ==
         {k:v for k,v in new.items() if k != 'files'}, 'MANIFEST_CONTRACT')
    need(all(re.fullmatch(r'stage1/[a-z][a-z0-9_]*\.py', name)
             for name in set(new['files']) - set(old['files'])), 'ADDITIVE_HELPER_SCOPE')
    namespace = {'__name__':'p2_epoch7_pinned_pure_renderer'}
    exec(compile(old_payload[RENDERER_PATH], '<pinned-pure-renderer>', 'exec'), namespace)
    namespace['_validate_install_contract'](new)
    identity_render = namespace['render_identity_bytes']
    plan = parse(old_plan_raw)
    rows = copy.deepcopy(plan['runtime']['provisioning'])
    need(len(rows) == 24 and len({r['target'] for r in rows}) == 24, 'TARGET_COUNT')
    old_targets = {}
    for row in rows:
        raw = identity_render(row['source'], old_payload[row['source']], OLD_MANIFEST, old)
        need(sha(raw) == row['source_sha256'], 'OLD_RENDERED_SOURCE')
        result = render(raw, row['replacements'])
        need(sha(result) == row['rendered_sha256'], 'OLD_TARGET_HASH')
        old_targets[row['target']] = result
    control_commit,reconciliation=reconcile_control_source(old_targets[DISPATCHER],
        plan['runtime']['publisher'],control_reconciliation)
    digest = sha(new_manifest_raw)
    need(digest != OLD_MANIFEST, 'NEW_CANDIDATE_REQUIRED')
    base = '/opt/xuanjun-control-releases/integration-' + digest[:16]
    bridge = base + '/stage1/native_ledger_bridge.py'
    updates = {'@@ARTIFACT_SHA256@@':digest, '@@PACKAGE_SHA256@@':digest,
        '@@RELEASE_DIRECTORY@@':'integration-'+digest[:16], '@@RELEASE@@':base,
        '@@LEDGER_BRIDGE_PATH@@':bridge, '@@SOURCE_COMMIT@@':control_commit,
        '@@LEDGER_BRIDGE_SHA256@@':new['files']['stage1/native_ledger_bridge.py']}
    by_target = {r['target']:r for r in rows}
    # Render the client first: the controller binding embeds its exact new bytes.
    ordered = [by_target[CLIENT]] + [r for r in rows if r['target'] != CLIENT]
    targets = {}
    for row in ordered:
        for token in set(row['replacements']) & set(updates):
            row['replacements'][token] = updates[token]
        raw = identity_render(row['source'], new_payload[row['source']], digest, new)
        result = render(raw, row['replacements'])
        need(OLD_MANIFEST.encode() not in result and
             ('integration-'+OLD_MANIFEST[:16]).encode() not in result, 'STALE_RELEASE')
        row['source_sha256'], row['rendered_sha256'] = sha(raw), sha(result)
        targets[row['target']] = result
        if row['target'] == CLIENT:
            updates['@@LEDGER_BRIDGE_CONFIG_SHA256@@'] = sha(result)
    binding = parse(targets[BINDING])['ledger']
    need(binding['bridge'] == bridge and binding['config'] == CLIENT and
         binding['files'] == {bridge:new['files']['stage1/native_ledger_bridge.py'],
                              CLIENT:sha(targets[CLIENT])}, 'NATIVE_BINDING_HASHES')
    tls = parse(targets[TLS])
    need(tls['release_sha256'] == digest, 'TLS_RELEASE')
    old_tls = parse(old_targets[TLS])
    need({k:v for k,v in tls.items() if k != 'release_sha256'} ==
         {k:v for k,v in old_tls.items() if k != 'release_sha256'}, 'TLS_RETENTION_SCOPE')
    new_binary=bind_controller_binary(plan['activation_proposal'],old,new,digest)
    active = copy.deepcopy(plan['activation_proposal'])
    active.update(epoch=8, state='PREPARED', release_sha256=digest,
                  config_sha256=sha(targets[DISPATCHER]), binary_sha256=new_binary)
    need(all(active[key]==plan['activation_proposal'][key] for key in
        ('schema','ledger_uuid','generation','instance','db_path','ledger_socket')),
        'CANONICAL_LEDGER_IDENTITY_CHANGED')
    runtime = copy.deepcopy(plan['runtime'])
    runtime['provisioning'] = rows
    runtime['release_directory'] = 'integration-'+digest[:16]
    prior_tls_path = runtime['tls_renewal']['path']
    need(prior_tls_path.endswith('/epoch6-tls-renewal-candidate.json'), 'TLS_CANDIDATE_PATH')
    runtime['tls_renewal'] = {'path':prior_tls_path[:-len('epoch6-tls-renewal-candidate.json')] +
        'epoch8-tls-renewal-candidate.json', 'sha256':sha(targets[TLS])}
    for path_key, hash_key in (('binding_file','binding_sha256'),
            ('ledger_client_config','ledger_client_sha256'),
            ('gateway_relay_config','gateway_relay_sha256')):
        runtime['plugin'][hash_key] = sha(targets[runtime['plugin'][path_key]])
    return {'kind':'PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN', 'source_commit':source_commit,
        'source_tree':source_tree, 'source_provenance':'REQUIRES_INDEPENDENT_READBACK',
        'control_repository_reconciliation':reconciliation,
        'manifest_sha256':digest, 'runtime':runtime, 'activation_proposal':active,
        'rendered_targets':targets, 'old_rendered_targets':old_targets,
        'tls_config_bytes':targets[TLS], 'install_admission':False,
        'additional_identity_targets':'REQUIRES_FINAL_COMPILERS_AND_MEASUREMENTS'}

# Immutable epoch4 baseline, retained only as history. The current epoch7
# sidefile must be authenticated by the completed epoch5 owned-transition proof.
RETAINED_NATIVE_SHA = '91c65c9fbc5c2cf68648672b4c096d7df376ecfbc605bc4cc838300bd302f629'
RETAINED_NATIVE_RELEASE = '338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09'

def native_sidefile_delta(before, compiled, old_bridge_sha256, old_client_sha256,
                          native_transition):
    """Return exact proposed bytes only. No filesystem access, CAS or admission."""
    from epoch7_snapshot import validate_native_transition_evidence
    validate_native_transition_evidence(native_transition,before)
    need(type(compiled) is dict and compiled.get('kind') == 'PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN'
         and compiled.get('install_admission') is False, 'COMPILED_BINDINGS_REQUIRED')
    value = parse(before)
    need(type(value) is dict and set(value) == {'ledger','gatewayIdentity'}, 'NATIVE_SCHEMA')
    ledger=value['ledger']
    need(type(ledger) is dict and set(ledger)=={'python','pythonSha256','bridge','config','files'},
         'NATIVE_LEDGER_SCHEMA')
    old_bridge='/opt/xuanjun-control-releases/integration-'+native_transition['after_release_sha256'][:16]+'/stage1/native_ledger_bridge.py'
    need(ledger['bridge']==old_bridge and ledger['config']==CLIENT and
         ledger['files']=={old_bridge:old_bridge_sha256, CLIENT:old_client_sha256}, 'NATIVE_OLD_FILE_PINS')
    manifest_sha = compiled.get('manifest_sha256')
    need(type(manifest_sha) is str and re.fullmatch(r'[0-9a-f]{64}', manifest_sha), 'NATIVE_NEW_MANIFEST')
    targets = compiled['rendered_targets']
    rows = {r['target']:r for r in compiled['runtime']['provisioning']}
    need(all(rows[p]['rendered_sha256'] == sha(targets[p]) for p in (BINDING, CLIENT)),
         'NATIVE_COMPILED_TARGET_DRIFT')
    new_ledger=parse(targets[BINDING])['ledger']
    new_bridge = '/opt/xuanjun-control-releases/integration-'+manifest_sha[:16]+'/stage1/native_ledger_bridge.py'
    need(type(new_ledger) is dict and set(new_ledger) == set(ledger) and
         new_ledger['bridge'] == new_bridge and new_ledger['config'] == CLIENT and
         set(new_ledger['files']) == {new_bridge, CLIENT} and
         new_ledger['files'][CLIENT] == sha(targets[CLIENT]), 'NATIVE_NEW_FILE_PINS')
    need(ledger['python']==new_ledger['python'] and ledger['pythonSha256']==new_ledger['pythonSha256'],
         'NATIVE_INTERPRETER_CHANGED')
    value['ledger']=copy.deepcopy(new_ledger)
    after=(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(all(pin[:16].encode() not in after for pin in
         (native_transition['before_release_sha256'],native_transition['after_release_sha256'])),
         'NATIVE_STALE_RELEASE')
    return after
