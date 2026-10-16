"""Pure, exact-byte preparation for the retained epoch7 recovery candidate.

No host reads, network, approval creation or effects. Historical helpers execute
only after their fixed hashes authenticate, against a finite in-memory Path
facade. Their entrypoints and filesystem implementations are never invoked.
"""
import builtins
import copy
import hashlib
import json
import os
import types

BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
CAND = BASE + '/complete-install-candidate-38503014520'
TX = BASE + '/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5'
ORIGINAL_ROOT = CAND + '/xuanjun-p2-package'
V4_ROOT = CAND + '/epoch5-recovery-candidate-v4/xuanjun-p2-package'
ORIGINAL_PLAN = 'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'
V4_PLAN = '5938dad82a8597f8ac18af078843cfa30e8245729101b65dbc861e38f877edeb'
ORIGINAL_MANIFEST = '9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
V4_MANIFEST = '153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7'
V4_KIT = '12ec5e711b4a7de865e44323b887fefbac6cc7954d13609e58b7137bd34374e1'
V4_HELPERS = {
    'build_epoch5_runtime': 'b817107d2110e8ce17f020f0b856127b241fa9375c3d088bd3c1f526badda7af',
    'inspect_epoch3': '1b6197cdcb83d290e5e4995cd5b3b76a76db4ad51299ea285a08d21180c12c48',
    'prepare_epoch5_bindings': '270f3dde094813b3a69451fb30a3fa5f78b7733ed4c3d42df614eee0529796ab',
    'epoch5_plan': '6eb71affe3e3b321f6a10beac9de1af333fd265c26b29019b4d4747c5ef5c12a'}
V4_ORDER = ('build_epoch5_runtime', 'inspect_epoch3', 'prepare_epoch5_bindings', 'epoch5_plan')
MANIFEST_PATH = 'deploy/integration-manifest.json'
RAW_PATHS = {
    'native_before': '/etc/xuanjun-development/p2-native-binding.json',
    'tls_journal_before': TX + '/tls-lifecycle.json',
    'prior_provision_bytes': TX + '/epoch6-runtime-provisioning.json',
    'legacy_units_raw': TX + '/legacy-units.json',
    'publisher_journal_raw': TX + '/publisher-bootstrap.json',
    'sandbox_candidate_raw': TX + '/sandbox-profile-candidate.json'}
MAX_SOURCE = 2 * 1024 * 1024
MAX_PACKAGE = 16 * 1024 * 1024
STAT_FIELDS = ('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns')


def need(ok, label):
    if not ok: raise ValueError('EPOCH7_PREP_' + label)


def sha(raw):
    need(type(raw) is bytes, 'BYTES_REQUIRED')
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def parse(raw, maximum=MAX_SOURCE):
    need(type(raw) is bytes and 0 < len(raw) <= maximum, 'JSON_BOUND')
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'DUPLICATE_JSON')
            value[key] = item
        return value
    def reject(unused): raise ValueError('EPOCH7_PREP_NONFINITE_JSON')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)


def relative(path):
    need(type(path) is str and 0 < len(path) <= 1024 and not path.startswith('/') and
         all(x not in ('', '.', '..') for x in path.split('/')) and
         '\\' not in path and '\x00' not in path, 'RELATIVE_SOURCE_PATH')
    return path


def package(manifest_raw, payloads, expected):
    need(sha(manifest_raw) == expected, 'PACKAGE_MANIFEST_PIN')
    manifest = parse(manifest_raw)
    need(type(manifest.get('files')) is dict and len(manifest['files']) == 102 and
         type(payloads) is dict and set(payloads) == set(manifest['files']), 'EXACT102_SOURCE_SET')
    total = len(manifest_raw)
    for name, pin in manifest['files'].items():
        relative(name); raw = payloads[name]
        need(type(raw) is bytes and len(raw) <= MAX_SOURCE and sha(raw) == pin, 'SOURCE_BYTES_PIN')
        total += len(raw)
    need(total <= MAX_PACKAGE, 'PACKAGE_TOTAL_BOUND')
    result = dict(payloads); result[MANIFEST_PATH] = manifest_raw
    return result


class CachedPath(object):
    """Only the four read-only methods used by the fixed historical compiler."""
    def __init__(self, path, files):
        self.path = str(path); self.files = files
        need(self.path.startswith('/') and os.path.normpath(self.path) == self.path and
             '\x00' not in self.path, 'CACHED_PATH')
    def __truediv__(self, name):
        return CachedPath(self.path + '/' + relative(name), self.files)
    def __str__(self): return self.path
    def __eq__(self, other):
        return isinstance(other, CachedPath) and self.path == other.path and self.files is other.files
    def resolve(self): return self
    def absolute(self): return self
    def read_bytes(self):
        need(self.path in self.files, 'UNDECLARED_HISTORICAL_READ')
        return self.files[self.path]


def reproduce_v4(original_raw, original_manifest, original_payloads,
                 v4_manifest, v4_payloads, kit_raw, helper_bytes):
    """Reproduce5938 exactly; imports are fixed hashes, sources are cached bytes."""
    need(sha(original_raw) == ORIGINAL_PLAN and len(original_raw) <= MAX_SOURCE, 'ORIGINAL_PLAN_PIN')
    need(sha(kit_raw) == V4_KIT and type(helper_bytes) is dict and
         set(helper_bytes) == set(V4_HELPERS), 'HISTORICAL_KIT_SCOPE')
    kit = parse(kit_raw)
    files = {}
    for root, raw, payloads, expected in (
            (ORIGINAL_ROOT, original_manifest, original_payloads, ORIGINAL_MANIFEST),
            (V4_ROOT, v4_manifest, v4_payloads, V4_MANIFEST)):
        for name, data in package(raw, payloads, expected).items(): files[root+'/'+name] = data
    for name, expected in V4_HELPERS.items():
        raw = helper_bytes[name]
        need(type(raw) is bytes and len(raw) <= 65536 and sha(raw) == expected and
             kit['helper_files'].get(name+'.py') == expected, 'HISTORICAL_HELPER_PIN')
    modules = {}
    allowed = frozenset(('argparse','hashlib','json','os','pathlib','runpy','copy','re',
                         'stat','socket','subprocess','sys','tempfile','shutil','secrets'))
    def local_import(name, globals=None, locals=None, fromlist=(), level=0):
        need(level == 0, 'HISTORICAL_RELATIVE_IMPORT')
        if name in V4_HELPERS:
            need(name in modules, 'HISTORICAL_IMPORT_ORDER')
            return modules[name]
        need(name in allowed, 'HISTORICAL_IMPORT_SCOPE')
        return builtins.__import__(name, globals, locals, fromlist, level)
    safe_builtins = dict(vars(builtins)); safe_builtins['__import__'] = local_import
    for name in V4_ORDER:
        module = types.ModuleType(name); module.__file__ = '<hash-pinned-'+name+'>'
        module.__dict__['__builtins__'] = safe_builtins
        exec(compile(helper_bytes[name], module.__file__, 'exec'), module.__dict__)
        modules[name] = module
    # Namespace-only substitution, never monkeypatch global pathlib or sys.modules.
    modules['prepare_epoch5_bindings'].pathlib = types.SimpleNamespace(
        Path=lambda name: CachedPath(name, files))
    value = modules['epoch5_plan'].compile_plan(original_raw, ORIGINAL_ROOT, V4_ROOT)
    raw = modules['epoch5_plan'].canonical(value)
    need(sha(raw) == V4_PLAN, 'REPRODUCED_V4_PLAN_PIN')
    return raw


def validate_observation(value, factory):
    need(type(value) is dict and value.get('kind') == 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
         'COMPLETE_OBSERVATION_REQUIRED')
    factory.observation_inputs(value)
    factory.d.validate_snapshot(value['snapshot'],value['snapshot_sha256'])
    factory.snap.validate_policy(value['policy'])
    need(value['evidence']['snapshot_sha256']==value['snapshot_sha256'] and
         factory.d.digest(value['evidence']['retained'])==value['snapshot']['retained_resource_sha256'] and
         value['evidence']['retained']['policy_sha256']==value['policy_sha256'], 'OBSERVATION_RETAINED_BINDING')
    from epoch7_acceptance_rows import acceptance_facts_from_observation
    acceptance_facts_from_observation(value)
    factory.validated_finite_probe(value)
    return value


def retained_buffers(observation, measured):
    """Require precisely six raw+metadata samples matching the full observation."""
    need(type(measured) is dict and set(measured) == set(RAW_PATHS), 'SIX_RETAINED_BUFFERS')
    files = observation['evidence']['retained']['files']; result = {}
    for key, path in sorted(RAW_PATHS.items()):
        item = measured[key]
        need(type(item) is dict and set(item) == {'raw','metadata'} and path in files,
             'RETAINED_BUFFER_ROW')
        raw, actual, wanted = item['raw'], item['metadata'], files[path]
        need(type(raw) is bytes and len(raw) <= MAX_SOURCE and sha(raw) == wanted['sha256'] and
             len(raw) == wanted['size'] and all(type(actual.get(k)) is int and
             actual[k] == wanted[k] for k in STAT_FIELDS), 'RETAINED_BUFFER_CHANGED')
        need(actual.get('kind') == wanted.get('kind') == 'FILE', 'RETAINED_BUFFER_KIND')
        # Strict roundtrip; never normalize private whitespace/newlines.
        need(raw.decode('utf-8').encode('utf-8') == raw, 'RETAINED_UTF8')
        result[key] = raw
    return result


def compile_bindings(old_plan_raw, old_manifest, old_payloads, manifest, payloads,
                     observation, factory):
    """Reconcile only the measured retained publisher HEAD; never choose a HEAD."""
    binding = factory.bindings
    old = parse(old_plan_raw); reference = old['runtime']['publisher']
    row = next(x for x in old['runtime']['provisioning'] if x['target'] == binding.DISPATCHER)
    namespace = {'__name__':'epoch7_prepare_exact_renderer'}
    source = old_payloads[binding.RENDERER_PATH]
    need(sha(source) == binding.RENDERER, 'RENDERER_PIN')
    exec(compile(source, '<hash-pinned-identity-renderer>', 'exec'), namespace)
    raw = namespace['render_identity_bytes'](row['source'], old_payloads[row['source']],
                                           binding.OLD_MANIFEST, parse(old_manifest))
    dispatcher = binding.render(raw, row['replacements'])
    need(sha(dispatcher) == row['rendered_sha256'], 'RETAINED_DISPATCHER_RENDER')
    control = copy.deepcopy(observation['evidence']['retained']['control_git'])
    reconciliation = {'schema':1,'purpose':'DISPATCHER_RETAINED_CONTROL_HEAD',
        'old_dispatcher_sha256':sha(dispatcher),'old_source_commit':parse(dispatcher)['source_commit'],
        'publisher_reference_sha256':sha(binding.canonical(reference)),
        'observation_sha256':sha(binding.canonical(control)),'observation':control}
    return binding.compile_retained_bindings(old_plan_raw, old_manifest, old_payloads,
        manifest, payloads, factory.SOURCE, factory.SOURCE_TREE, reconciliation)


def additive_absence(observation, path):
    import epoch7_additive_identity as owner
    import epoch7_additive_server as server
    need(path in (owner.PATH,server.PATH), 'ADDITIVE_PATH')
    retained = observation['evidence']['retained']
    need(path in retained['additive_paths_absent'], 'ADDITIVE_MEASURED_ABSENCE')
    parent = retained['prerequisites']['directories'][owner.PARENT]
    need(parent['kind'] == 'DIRECTORY' and (parent['uid'],parent['gid'],parent['mode']) == (0,0,0o755)
         and parent['default_acl'] == '' and parent['access_acl'] == 'user::rwx\ngroup::r-x\nother::r-x\n',
         'ADDITIVE_PARENT_AUTHORITY')
    return {'path':path,'kind':'ABSENT','parent':dict(
        {k:parent[k] for k in ('kind','uid','gid','mode','dev','ino')},
        path=owner.PARENT,acl_sha256=sha(parent['access_acl'].encode('ascii')))}


def owner_policy(observation, compiled, manifest_raw):
    import epoch7_additive_identity as owner
    manifest = parse(manifest_raw); release = '/opt/xuanjun-control-releases/integration-'+sha(manifest_raw)[:16]
    reference = observation['unit_metadata']['sections']['python_reference']['evidence']
    final = reference['final']; measured = final['metadata']
    interpreter = dict({k:measured[k] for k in ('uid','gid','mode','dev','ino','nlink')},
                       path=final['path'],kind='FILE',sha256=final['sha256'])
    unit = compiled['rendered_targets'][owner.UNIT]
    script = release+'/'+owner.SCRIPT_REL
    policy = {'schema':1,'callback_uid':1004,'release_sha256':sha(manifest_raw),
        'python_exe':final['path'],'python_sha256':final['sha256'],'script':script,
        'script_sha256':manifest['files'][owner.SCRIPT_REL], 'unit_file':owner.UNIT,
        'unit_sha256':sha(unit),'argv':owner.expected_argv(script),'cgroup':owner.CGROUP}
    raw = canonical(policy)+b'\n'
    delta = owner.compile_addition(raw, sha(raw), manifest_raw, sha(manifest_raw), unit,
                                   interpreter, additive_absence(observation,owner.PATH))
    return raw, delta


def seed_wire(seed):
    """The loader's exact11 private fields; bytes only at named fixed positions."""
    import epoch7_host_factory as factory
    private_fields = (factory.INPUTS-factory.DERIVED_INPUTS)-factory.CACHE_INPUTS
    need(type(seed) is dict and set(seed) == factory.INPUTS-factory.DERIVED_INPUTS, 'EXACT_SEED_FIELDS')
    private = copy.deepcopy({key:seed[key] for key in private_fields})
    for key in RAW_PATHS:
        need(type(private[key]) is bytes, 'PRIVATE_RAW_BYTES')
        private[key] = private[key].decode('utf-8')
    for key in ('rendered_targets','old_rendered_targets'):
        private['compiled'][key] = {path:raw.decode('utf-8') for path,raw in private['compiled'][key].items()}
    private['compiled']['tls_config_bytes'] = private['compiled']['tls_config_bytes'].decode('utf-8')
    private['identity_payloads'] = {path:raw.decode('utf-8') for path,raw in private['identity_payloads'].items()}
    need(type(private['activate_retained_renewal_timer']) is bool, 'EXPLICIT_TIMER_DECISION')
    raw = canonical({'schema':1,'seed':private})+b'\n'
    need(len(raw) <= 64*1024*1024, 'PRIVATE_SEED_BOUND')
    return raw
