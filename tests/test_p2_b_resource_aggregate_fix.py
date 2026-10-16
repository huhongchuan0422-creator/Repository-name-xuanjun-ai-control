"""Exact-HEAD public resource-aggregate fixture gate; no host admission.

The new 25-case suite exercises hydration, compilation and real C binding/mutation.
It does not assemble the C production recovery application or admit installation.
"""
import ast,hashlib,io,json,os,pathlib,re,resource,signal,stat,subprocess,sys,tarfile,tempfile,time,types,unittest
FEATURE_ID='P2_RETAINED_RECOVERY'
MAX_LOG=1048576
MAX_ARTIFACT_FILE=33554432
ARCHIVE_SIZE=1041263
ARCHIVE_SHA='e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645'
MANIFEST_SHA='7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
ARCHIVE_TARGET='fixtures/epoch7-recovery-kit.tar.gz'
KIT_TARGET='kit/epoch7-recovery-candidate-r7'
ARCHIVE_HEADERS=295
ARCHIVE_MEMBERS=253
KIT_CACHE_FILES=252
PARENT_ARCHIVE_TARGET='fixtures/epoch7-kit-parentfix.tar.gz'
PARENT_ARCHIVE_SIZE=1045651
PARENT_ARCHIVE_SHA='6553938a56b882e17d13029fa9a06787131bb55a5c55bc1138e2b825277b7307'
PARENT_MANIFEST_SHA='b33b365ef1fd18458d85bcbbec44d883f3cc33bf859064cbdca6bfc3fad7d571'
PARENT_KIT_TARGET='kit/epoch7-recovery-candidate-r7-parentfix'
SUITE_NAMES=('aggregate','diagnostics','observer','builder','binding','delivery')
SUITES=(('aggregate',25),('diagnostics',12),('observer',6),('builder',32),('binding',10),('delivery',36))
DERIVED_TARGETS={}
REGISTRY_PATH='governance/features.json'
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz'
PARENT_ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-parentfix-dacd45a2.tar.gz'
CANDIDATE_TARGET='b-resource-aggregate-fix-candidate'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/'
WORKFLOW_PATH='.github/workflows/p2-b-resource-aggregate-fix.yml'
GATE_PATH='tests/test_p2_b_resource_aggregate_fix.py'
CONTRACT_PATH='tests/test_p2_b_resource_aggregate_fix_contract.py'
PINS_BOUND=True
WORKFLOW_SIZE=6056
WORKFLOW_SHA='f291c02a134b5311dafee7c692b8fd7c6d28734ab112ab82ceb9398bf5fe55d2'
SOURCE_TARGETS={'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-parentfix-dacd45a2.tar.gz': 'fixtures/epoch7-kit-parentfix.tar.gz',
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/epoch7_prepare.py': 'b-release-parent-fix-candidate/preparation-bound/epoch7_prepare.py',
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/epoch7_prepare_data.py': 'b-release-parent-fix-candidate/preparation-bound/epoch7_prepare_data.py',
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/epoch7_topology_projection.py': 'b-release-parent-fix-candidate/preparation-bound/epoch7_topology_projection.py',
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-delivery/epoch7_prepare_delivery.py': 'b-release-parent-fix-candidate/delivery-candidate/epoch7_prepare_delivery.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz': 'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/recovery-kit-manifest.json': 'b-resource-aggregate-fix-candidate/artifact/recovery-kit-manifest.json',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/verification.json': 'b-resource-aggregate-fix-candidate/artifact/verification.json',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build/OVERLAY_INPUTS.json': 'b-resource-aggregate-fix-candidate/build/OVERLAY_INPUTS.json',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build/build_resourcebind_kit.py': 'b-resource-aggregate-fix-candidate/build/build_resourcebind_kit.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build/test_build_resourcebind_kit.py': 'b-resource-aggregate-fix-candidate/build/test_build_resourcebind_kit.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/OWNER_PREPARATION_TEMPLATE.txt': 'b-resource-aggregate-fix-candidate/delivery-overlay/OWNER_PREPARATION_TEMPLATE.txt',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/epoch7_prepare_delivery.py': 'b-resource-aggregate-fix-candidate/delivery-overlay/epoch7_prepare_delivery.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/extract_epoch7_compiler_kit.py': 'b-resource-aggregate-fix-candidate/delivery-overlay/extract_epoch7_compiler_kit.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/test_resourcebind_delivery.py': 'b-resource-aggregate-fix-candidate/delivery-overlay/test_resourcebind_delivery.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/epoch7_recovery_entry.py': 'b-resource-aggregate-fix-candidate/kit-overlay/epoch7_recovery_entry.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/helpers/epoch7_host_factory.py': 'b-resource-aggregate-fix-candidate/kit-overlay/helpers/epoch7_host_factory.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/helpers/epoch7_host_observer.py': 'b-resource-aggregate-fix-candidate/kit-overlay/helpers/epoch7_host_observer.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/helpers/epoch7_resource_observer.py': 'b-resource-aggregate-fix-candidate/kit-overlay/helpers/epoch7_resource_observer.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/tests/host_factory/test_fresh_release_parent.py': 'b-resource-aggregate-fix-candidate/kit-overlay/tests/host_factory/test_fresh_release_parent.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/tests/live_controls/test_epoch7_observer_binding.py': 'b-resource-aggregate-fix-candidate/kit-overlay/tests/live_controls/test_epoch7_observer_binding.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/epoch7_prepare.py': 'b-resource-aggregate-fix-candidate/preparation-overlay/epoch7_prepare.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/epoch7_prepare_data.py': 'b-resource-aggregate-fix-candidate/preparation-overlay/epoch7_prepare_data.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/epoch7_topology_projection.py': 'b-resource-aggregate-fix-candidate/preparation-overlay/epoch7_topology_projection.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/test_compiler_binding.py': 'b-resource-aggregate-fix-candidate/preparation-overlay/test_compiler_binding.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/tests/resource_aggregate_fixture.py': 'b-resource-aggregate-fix-candidate/tests/resource_aggregate_fixture.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/tests/test_failure_labels.py': 'b-resource-aggregate-fix-candidate/tests/test_failure_labels.py',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/tests/test_resource_aggregate_closure.py': 'b-resource-aggregate-fix-candidate/tests/test_resource_aggregate_closure.py',
 'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/epoch7_prepare_delivery.py': 'b-release-parent-fix-candidate/delivery-candidate/baseline/epoch7_prepare_delivery.py',
 'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/test_epoch7_prepare_delivery.py': 'b-release-parent-fix-candidate/delivery-candidate/baseline/test_epoch7_prepare_delivery.py'}
PINS={'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-parentfix-dacd45a2.tar.gz': (1045651,
                                                                                              '6553938a56b882e17d13029fa9a06787131bb55a5c55bc1138e2b825277b7307',
                                                                                              'fixtures/epoch7-kit-parentfix.tar.gz'),
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/epoch7_prepare.py': (55827,
                                                                                        'd32b55ab2164965b486dbe2d834281c5404d59fb454278e67ec32c306f34deb9',
                                                                                        'b-release-parent-fix-candidate/preparation-bound/epoch7_prepare.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/epoch7_prepare_data.py': (13888,
                                                                                             '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1',
                                                                                             'b-release-parent-fix-candidate/preparation-bound/epoch7_prepare_data.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/epoch7_topology_projection.py': (36482,
                                                                                                    '0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6',
                                                                                                    'b-release-parent-fix-candidate/preparation-bound/epoch7_topology_projection.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-release-parent-delivery/epoch7_prepare_delivery.py': (39006,
                                                                                                    '8bc04315cbe23ee5338ccdc3341f536b15088550ef0d01e655ed4bb4fbb0f7d9',
                                                                                                    'b-release-parent-fix-candidate/delivery-candidate/epoch7_prepare_delivery.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz': (1056853,
                                                                                                                '6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e',
                                                                                                                'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/recovery-kit-manifest.json': (62561,
                                                                                                            '6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030',
                                                                                                            'b-resource-aggregate-fix-candidate/artifact/recovery-kit-manifest.json'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/verification.json': (1355,
                                                                                                   '3fbc5b4234983b82b46006abc9e2adaa37591cada09ad694ea3919d9e3132927',
                                                                                                   'b-resource-aggregate-fix-candidate/artifact/verification.json'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build/OVERLAY_INPUTS.json': (3406,
                                                                                                  'eca79573770c1cedd4f21b06f77a078d996ed6a01532843573ecd6abd818f060',
                                                                                                  'b-resource-aggregate-fix-candidate/build/OVERLAY_INPUTS.json'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build/build_resourcebind_kit.py': (17353,
                                                                                                        'b5ddfa98594daf85c5c33387396e5e57f560b6ccfe0dd533772cb817b26c87dd',
                                                                                                        'b-resource-aggregate-fix-candidate/build/build_resourcebind_kit.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build/test_build_resourcebind_kit.py': (20006,
                                                                                                             '2cf5f98352cf38c1bbb42d2c7ca4ee0076dfa3e7fcbc6b40fe0b09e164347203',
                                                                                                             'b-resource-aggregate-fix-candidate/build/test_build_resourcebind_kit.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/OWNER_PREPARATION_TEMPLATE.txt': (5431,
                                                                                                                        'dc0b65a70e57ff56b375052bfab2b40a277f5b5a39e8c94c401232dd6092355f',
                                                                                                                        'b-resource-aggregate-fix-candidate/delivery-overlay/OWNER_PREPARATION_TEMPLATE.txt'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/epoch7_prepare_delivery.py': (39288,
                                                                                                                    'b7d6abfd97734e10b3b4a8b27bf9004baff684110a7acac12e480a315604cac6',
                                                                                                                    'b-resource-aggregate-fix-candidate/delivery-overlay/epoch7_prepare_delivery.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/extract_epoch7_compiler_kit.py': (10192,
                                                                                                                        'be71e68b382b5826d44c760ffc8bdb96e71f28613f7b344928c96b95adf10dd9',
                                                                                                                        'b-resource-aggregate-fix-candidate/delivery-overlay/extract_epoch7_compiler_kit.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/delivery-overlay/test_resourcebind_delivery.py': (36465,
                                                                                                                       'c3e95550466af344781e1835e1b77b1ff8edb083159807ef261cceb3e6a3ebaf',
                                                                                                                       'b-resource-aggregate-fix-candidate/delivery-overlay/test_resourcebind_delivery.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/epoch7_recovery_entry.py': (55774,
                                                                                                             '071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5',
                                                                                                             'b-resource-aggregate-fix-candidate/kit-overlay/epoch7_recovery_entry.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/helpers/epoch7_host_factory.py': (46994,
                                                                                                                   'f7c08543aa703859092fff9073ad27bedd4b281fdaa45eeb5de5bcd960bc94b3',
                                                                                                                   'b-resource-aggregate-fix-candidate/kit-overlay/helpers/epoch7_host_factory.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/helpers/epoch7_host_observer.py': (45924,
                                                                                                                    'ec0d0618251469a5e0df241097c14b2aa608a6152ad6ea24ee1bed3ee1466cee',
                                                                                                                    'b-resource-aggregate-fix-candidate/kit-overlay/helpers/epoch7_host_observer.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/helpers/epoch7_resource_observer.py': (34728,
                                                                                                                        'c0caee8274378c442da3cd5acbb77a99c999d309122f046f233cedce8f4f2e04',
                                                                                                                        'b-resource-aggregate-fix-candidate/kit-overlay/helpers/epoch7_resource_observer.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/tests/host_factory/test_fresh_release_parent.py': (17235,
                                                                                                                                    'cc09a45c213c1385c6297f95ff237ab75c501dca7b70f771fa92ba101b2eb7e2',
                                                                                                                                    'b-resource-aggregate-fix-candidate/kit-overlay/tests/host_factory/test_fresh_release_parent.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay/tests/live_controls/test_epoch7_observer_binding.py': (5738,
                                                                                                                                        'fde0be3b536c504a8dda2eb4732dd99b2366c7e565b97fdba2e7fec4805515a2',
                                                                                                                                        'b-resource-aggregate-fix-candidate/kit-overlay/tests/live_controls/test_epoch7_observer_binding.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/epoch7_prepare.py': (55833,
                                                                                                              '18d3c459bc14f4a3c00317c5a407d18178059209830763564dced41d9af945fd',
                                                                                                              'b-resource-aggregate-fix-candidate/preparation-overlay/epoch7_prepare.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/epoch7_prepare_data.py': (13888,
                                                                                                                   '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1',
                                                                                                                   'b-resource-aggregate-fix-candidate/preparation-overlay/epoch7_prepare_data.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/epoch7_topology_projection.py': (36482,
                                                                                                                          '0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6',
                                                                                                                          'b-resource-aggregate-fix-candidate/preparation-overlay/epoch7_topology_projection.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/preparation-overlay/test_compiler_binding.py': (10179,
                                                                                                                     '4c78e43b8597642dedb10c1bdb4f8da39e706cf483d20bceabdbc37f699723d8',
                                                                                                                     'b-resource-aggregate-fix-candidate/preparation-overlay/test_compiler_binding.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/tests/resource_aggregate_fixture.py': (13753,
                                                                                                            '4e6a35f9c3e297e4fd63d783a46b3ce432bfb5c121e6621dfaee96c3f97307fb',
                                                                                                            'b-resource-aggregate-fix-candidate/tests/resource_aggregate_fixture.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/tests/test_failure_labels.py': (7925,
                                                                                                     '147b19b01fe0654adf48add0c9ac23eb89426f00d43582c0bfbb0d3f9c254b3c',
                                                                                                     'b-resource-aggregate-fix-candidate/tests/test_failure_labels.py'),
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/tests/test_resource_aggregate_closure.py': (25005,
                                                                                                                 'b417b2a9df5972e429151d2edad121c11248ce581067cb70b7a366cf6c9b95a1',
                                                                                                                 'b-resource-aggregate-fix-candidate/tests/test_resource_aggregate_closure.py'),
 'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/epoch7_prepare_delivery.py': (27421,
                                                                                                        '087df34edd0e2568870ced2c53c9bb0c28ae900d0a4bf7ec8642d8db80a30313',
                                                                                                        'b-release-parent-fix-candidate/delivery-candidate/baseline/epoch7_prepare_delivery.py'),
 'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/test_epoch7_prepare_delivery.py': (25796,
                                                                                                             '13f4cb0a85ee6a096a0f0a85026ad34d0f5288154f6ab56014bec52b2d405314',
                                                                                                             'b-release-parent-fix-candidate/delivery-candidate/baseline/test_epoch7_prepare_delivery.py')}
PUBLIC_DIRECTORIES=('evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/kit-overlay',
 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/build')


# The successor checkout can advance without redefining the selected compiler.
COMPILER_SOURCE_COMMIT='ef21ca95331769622c294c65bb60ec7ceed0c392'
COMPILER_SOURCE_TREE='5a70c5627afe75fcd475c20e71ee9bfb0b6a156d'
DEPENDENCY_PUBLICATION_COMMIT='170c3fd74eb612f2529d1062e07c83e4263f78b1'
DEPENDENCY_PUBLICATION_TREE='ef8d15619dcb1b350eb139bbb964716f4f00497a'
SELECTED_ARCHIVE_PATH=PUBLIC_PREFIX+'artifact/epoch7-kit-resourcebind.tar.gz'
SELECTED_ARCHIVE_TARGET=CANDIDATE_TARGET+'/artifact/epoch7-kit-resourcebind.tar.gz'
SELECTED_MANIFEST_PATH=PUBLIC_PREFIX+'artifact/recovery-kit-manifest.json'
SELECTED_VERIFICATION_PATH=PUBLIC_PREFIX+'artifact/verification.json'
SELECTED_ARCHIVE_SIZE=1056853
SELECTED_ARCHIVE_SHA='6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e'
SELECTED_MANIFEST_SHA='6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
SELECTED_ENTRY_SHA='071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5'

def need(value,label):
    if not value:raise ValueError(label)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def unique(rows):
        result={}
        for key,value in rows:
            need(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
        return result
    return json.loads(raw.decode('ascii'),object_pairs_hook=unique)


def safe_name(name):
    need(type(name) is str and name and not name.startswith('/') and '\\' not in name and '\0' not in name
         and all(part not in ('','.','..') for part in name.split('/')),'FINITE_RELATIVE_PATH')
    return name


def publication_pins():
    need(PINS_BOUND is True,'RESOURCE_AGGREGATE_CI_PUBLICATION_NOT_BOUND')
    need(all(type(value) is str and re.fullmatch('[0-9a-f]{40}',value) for value in
        (DEPENDENCY_PUBLICATION_COMMIT,DEPENDENCY_PUBLICATION_TREE)),'DEPENDENCY_PUBLICATION_NOT_BOUND')
    need(type(SUITES) is tuple and tuple(name for name,count in SUITES)==SUITE_NAMES
         and all(type(count) is int and count>0 for name,count in SUITES),'EXACT_SUITE_COUNTS_NOT_BOUND')
    need(len(set(SOURCE_TARGETS.values()))==len(SOURCE_TARGETS),'EXACT_PUBLIC_TARGETS')
    need(set(PINS)==set(SOURCE_TARGETS),'EXACT_PUBLIC_INPUTS')
    for path,row in PINS.items():
        need(type(row) in (tuple,list) and len(row)==3,'PUBLIC_PIN_SHAPE')
        size,pin,target=row
        need(type(size) is int and 0<size<=33554432 and type(pin) is str and len(pin)==64
             and all(c in '0123456789abcdef' for c in pin) and target==SOURCE_TARGETS[path],'PUBLIC_PIN_SHAPE')
        safe_name(path);safe_name(target)
    need(type(WORKFLOW_SIZE) is int and 0<WORKFLOW_SIZE<=65536 and type(WORKFLOW_SHA) is str
         and len(WORKFLOW_SHA)==64 and all(c in '0123456789abcdef' for c in WORKFLOW_SHA),'WORKFLOW_NOT_BOUND')


def read_pin(root,relative,size,pin):
    path=root/relative;need(path.resolve()==path,'PUBLIC_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno());need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'PUBLIC_FILE_TYPE')
        raw=stream.read(size+1);after=os.fstat(stream.fileno())
    stamp=lambda s:tuple(getattr(s,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))
    need(stamp(before)==stamp(after)==stamp(os.lstat(str(path))),'PUBLIC_FILE_CHANGED')
    need(len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN');return raw


def git(root,args):
    # These fixed rev-parse requests return only one object identifier.
    raw=subprocess.check_output(['/usr/bin/git','-C',str(root)]+args,timeout=15)
    need(len(raw)<=128,'GIT_OUTPUT_BOUND');value=raw.decode('ascii').strip()
    need(re.fullmatch('[0-9a-f]{40}',value),'GIT_OBJECT_FORMAT');return value


def verified_path(root,head,relative,maximum=1048576):
    safe_name(relative);path=root/relative
    need(path.resolve()==path,'SOURCE_PATH_ALIAS')
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        first=os.fstat(stream.fileno());need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_size<=maximum,'SOURCE_FILE_TYPE_OR_BOUND')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
    stamp=lambda row:tuple(getattr(row,'st_'+name) for name in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))
    need(len(raw)<=maximum and stamp(first)==stamp(after)==stamp(os.lstat(str(path))),'SOURCE_CHANGED_OR_BOUND')
    blob=hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()
    need(blob==git(root,['rev-parse','--verify',head+':'+relative]),'EXACT_HEAD_BLOB_MISMATCH')
    return raw


def archive_files(raw):
    need(type(raw) is bytes and len(raw)==ARCHIVE_SIZE and digest(raw)==ARCHIVE_SHA,'ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r7/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)==ARCHIVE_HEADERS,'ARCHIVE_HEADER_COUNT')
        for row in rows:
            if row.isdir():continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'ARCHIVE_MEMBER')
            name=safe_name(row.name[len(prefix):]);need(name not in files,'ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'ARCHIVE_BYTES');files[name]=body
    need(len(files)==ARCHIVE_MEMBERS,'ARCHIVE_MEMBER_COUNT')
    need(digest(files['recovery-kit-manifest.json'])==MANIFEST_SHA,'MANIFEST_PIN')
    manifest=strict_json(files['recovery-kit-manifest.json'])
    need(len(manifest['files'])==KIT_CACHE_FILES,'KIT_CACHE_COUNT')
    need(set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'ARCHIVE_SOURCE_PIN')
    return files


def parent_archive_files(raw):
    need(type(raw) is bytes and len(raw)==PARENT_ARCHIVE_SIZE and digest(raw)==PARENT_ARCHIVE_SHA,'PARENT_ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r7-parentfix/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)==296,'PARENT_ARCHIVE_HEADER_COUNT')
        for row in rows:
            if row.isdir():continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'PARENT_ARCHIVE_MEMBER')
            name=safe_name(row.name[len(prefix):]);need(name not in files,'PARENT_ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'PARENT_ARCHIVE_BYTES');files[name]=body
    need(len(files)==254,'PARENT_ARCHIVE_MEMBER_COUNT')
    need(digest(files['recovery-kit-manifest.json'])==PARENT_MANIFEST_SHA,'PARENT_MANIFEST_PIN')
    manifest=strict_json(files['recovery-kit-manifest.json'])
    need(len(manifest['files'])==253 and set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_PARENT_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'PARENT_ARCHIVE_SOURCE_PIN')
    return files


def selected_archive_files(raw):
    need(type(raw) is bytes and len(raw)==SELECTED_ARCHIVE_SIZE and digest(raw)==SELECTED_ARCHIVE_SHA,'SELECTED_ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r7-resourcebind/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)==298,'SELECTED_ARCHIVE_HEADER_COUNT')
        for row in rows:
            if row.isdir():continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'SELECTED_ARCHIVE_MEMBER')
            name=safe_name(row.name[len(prefix):]);need(name not in files,'SELECTED_ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'SELECTED_ARCHIVE_BYTES');files[name]=body
    need(len(files)==256,'SELECTED_ARCHIVE_MEMBER_COUNT')
    need(digest(files['recovery-kit-manifest.json'])==SELECTED_MANIFEST_SHA,'SELECTED_MANIFEST_PIN')
    manifest=strict_json(files['recovery-kit-manifest.json'])
    need(len(manifest['files'])==255 and set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_SELECTED_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'SELECTED_ARCHIVE_SOURCE_PIN')
    need(manifest['kit_source_commit']==COMPILER_SOURCE_COMMIT and
        manifest['kit_source_tree']==COMPILER_SOURCE_TREE,'SELECTED_COMPILER_SOURCE')
    need(digest(files['epoch7_recovery_entry.py'])==SELECTED_ENTRY_SHA,'SELECTED_ENTRY_PIN')
    return files


def fixtures(root,records=None):
    publication_pins()
    def exact(path,size,pin):
        raw=read_pin(root,path,size,pin) if records is None else records[path]
        need(len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN');return raw
    result={target:exact(path,size,pin) for path,(size,pin,target) in PINS.items()}
    raw=exact(ARCHIVE_PATH,ARCHIVE_SIZE,ARCHIVE_SHA)
    result.update({KIT_TARGET+'/'+name:body for name,body in archive_files(raw).items()})
    result[ARCHIVE_TARGET]=raw
    for target,source in DERIVED_TARGETS.items():
        size,pin,unused=PINS[source];result[target]=exact(source,size,pin)
    parent=parent_archive_files(result[PARENT_ARCHIVE_TARGET])
    result.update({PARENT_KIT_TARGET+'/'+name:body for name,body in parent.items()})
    selected=selected_archive_files(result[SELECTED_ARCHIVE_TARGET])
    need(selected['recovery-kit-manifest.json']==records[SELECTED_MANIFEST_PATH] if records is not None else
        selected['recovery-kit-manifest.json']==read_pin(root,SELECTED_MANIFEST_PATH,*PINS[SELECTED_MANIFEST_PATH][:2]),'SELECTED_STANDALONE_MANIFEST')
    return result


def public_inventory(root):
    found=set()
    for prefix in PUBLIC_DIRECTORIES:
        for path in (root/prefix).rglob('*'):
            row=path.lstat();need(not stat.S_ISLNK(row.st_mode),'PUBLIC_SOURCE_ALIAS')
            if stat.S_ISDIR(row.st_mode):continue
            need(stat.S_ISREG(row.st_mode),'PUBLIC_SOURCE_TYPE');found.add(path.relative_to(root).as_posix())
    expected={path for path in SOURCE_TARGETS if any(path.startswith(prefix+'/') for prefix in PUBLIC_DIRECTORIES)}
    need(found==expected,'PUBLIC_SOURCE_ALLOWLIST')


def registry_contract(raw):
    # Registry additions are allowed; this gate authenticates its own registration
    # in the exact current HEAD rather than pinning an unrelated historical file.
    need(type(raw) is bytes and 0<len(raw)<=1048576,'REGISTRY_BOUND')
    value=strict_json(raw)
    need(type(value) is dict and type(value.get('schema_version')) is int and
         value['schema_version']==1 and type(value.get('features')) is list and
         0<len(value['features'])<=256,'REGISTRY_SCHEMA')
    need(all(type(row) is dict for row in value['features']),'REGISTRY_FEATURE_SHAPE')
    rows=[row for row in value['features'] if row.get('feature_id')==FEATURE_ID]
    need(len(rows)==1 and rows[0].get('status')=='IN_DEVELOPMENT','REGISTRY_FEATURE_SCOPE')
    acceptance=rows[0].get('acceptance')
    need(type(acceptance) is dict and type(acceptance.get('tests')) is list,'REGISTRY_TESTS')
    paths=acceptance['tests']
    need(0<len(paths)<=1024 and all(type(path) is str and
         re.fullmatch(r'tests/[A-Za-z0-9_./-]+\.py',path) and
         all(part not in ('','.','..') for part in path.split('/')) for path in paths),
         'REGISTRY_TEST_PATH')
    need(len(paths)==len(set(paths)) and
         all(paths.count(path)==1 for path in (GATE_PATH,CONTRACT_PATH)),
         'REGISTRY_REQUIRED_TESTS')


def bound_delivery_contract(raw):
    names={'PINS_BOUND','PUBLICATION_COMMIT','ARCHIVE_COMMIT','ARCHIVE_SHA','ARCHIVE_SIZE',
           'COMPILER_SOURCE','COMPILER_TREE','COMPILER_MANIFEST_SHA','COMPILER_ENTRY_SHA','COMPILER_CACHE_COUNT'}
    values={}
    for node in ast.parse(raw.decode('utf-8')).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in names:
                need(name not in values,'DELIVERY_DUPLICATE_CONSTANT')
                values[name]=ast.literal_eval(node.value)
    expected={'PINS_BOUND':True,'PUBLICATION_COMMIT':DEPENDENCY_PUBLICATION_COMMIT,
        'ARCHIVE_COMMIT':DEPENDENCY_PUBLICATION_COMMIT,'ARCHIVE_SHA':SELECTED_ARCHIVE_SHA,
        'ARCHIVE_SIZE':SELECTED_ARCHIVE_SIZE,'COMPILER_SOURCE':COMPILER_SOURCE_COMMIT,
        'COMPILER_TREE':COMPILER_SOURCE_TREE,'COMPILER_MANIFEST_SHA':SELECTED_MANIFEST_SHA,
        'COMPILER_ENTRY_SHA':SELECTED_ENTRY_SHA,'COMPILER_CACHE_COUNT':255}
    need(json.dumps(values,sort_keys=True)==json.dumps(expected,sort_keys=True),'BOUND_DELIVERY_PUBLICATION_CONTRACT')


def checkout_records(root,head):
    paths=set(PINS)|{GATE_PATH,CONTRACT_PATH,WORKFLOW_PATH,REGISTRY_PATH,ARCHIVE_PATH}
    records={path:verified_path(root,head,path,ARCHIVE_SIZE if path==ARCHIVE_PATH else max(1048576,PINS[path][0]) if path in PINS else 1048576) for path in sorted(paths)}
    need(pathlib.Path(__file__).read_bytes()==records[GATE_PATH],'CHECKPOINT_NOT_EXACT_HEAD')
    need(len(records[WORKFLOW_PATH])==WORKFLOW_SIZE and digest(records[WORKFLOW_PATH])==WORKFLOW_SHA,'WORKFLOW_PIN')
    registry_contract(records[REGISTRY_PATH])
    bound_delivery_contract(records[PUBLIC_PREFIX+'delivery-overlay/epoch7_prepare_delivery.py'])
    return records


def write_fixture_file(path,name,raw):
    if len(raw)<=MAX_LOG:
        with path.open('xb') as stream:stream.write(raw)
        return
    need(name==SELECTED_ARCHIVE_TARGET and len(raw)==SELECTED_ARCHIVE_SIZE and
        digest(raw)==SELECTED_ARCHIVE_SHA,'OVERSIZED_FIXTURE_NOT_SELECTED_ARCHIVE')
    before=resource.getrlimit(resource.RLIMIT_FSIZE)
    need(before[1]==resource.RLIM_INFINITY or before[1]>=MAX_ARTIFACT_FILE,'ARTIFACT_STAGING_HARD_BOUND')
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_ARTIFACT_FILE,before[1]))
        with path.open('xb') as stream:stream.write(raw)
    finally:resource.setrlimit(resource.RLIMIT_FSIZE,before)


def materialize(root,files):
    need(not root.exists(),'FIXTURE_EXISTS');root.mkdir(mode=0o700)
    allowed=set(SOURCE_TARGETS.values())|set(DERIVED_TARGETS)|{ARCHIVE_TARGET}
    for name,raw in sorted(files.items()):
        safe_name(name)
        need(name in allowed or name.startswith(KIT_TARGET+'/') or name.startswith(PARENT_KIT_TARGET+'/'),'FIXTURE_PATH')
        path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        write_fixture_file(path,name,raw)
    (root/KIT_TARGET/'helpers/fixtures').mkdir(mode=0o700,parents=True,exist_ok=True)
    (root/PARENT_KIT_TARGET/'helpers/fixtures').mkdir(mode=0o700,parents=True,exist_ok=True)
    return root


def check_materialized(root,files):
    found={p.relative_to(root).as_posix():p for p in root.rglob('*') if not p.is_dir()}
    need(set(found)==set(files),'FIXTURE_INVENTORY')
    for path in root.rglob('*'):need(not path.is_symlink(),'FIXTURE_ALIAS')
    for name,path in found.items():
        need(path.is_file() and path.read_bytes()==files[name],'FIXTURE_DRIFT')


def output_file_limit(file_limit=MAX_LOG,hard_limit=MAX_LOG):
    # CI-only limit inherited by disposable fixture children, not production.
    resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,hard_limit))


def run_child(argv,cwd,timeout,new_session=True,file_limit=MAX_LOG):
    """Outer owns one session; nested tests remain inside it until final group kill."""
    need(type(file_limit) is int and file_limit in (MAX_LOG,MAX_ARTIFACT_FILE),'CHILD_FILE_BOUND')
    log=tempfile.TemporaryFile();child=None;primary=None;cleanup=[];raw=b'';code=None;owned=False
    try:
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        child=subprocess.Popen(argv,cwd=str(cwd),env=env,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=new_session,preexec_fn=lambda:output_file_limit(
                file_limit,MAX_ARTIFACT_FILE if new_session else file_limit));owned=True
        if new_session:
            deadline=time.monotonic()+timeout
            while True:
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
                # WNOWAIT retains the group leader's PID ownership through killpg.
                try:status=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                except ChildProcessError:
                    owned=False;error=RuntimeError('CHILD_OWNERSHIP_UNKNOWN');error.preparation_ci_cleanup_unknown=True;raise error
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
                if status is not None:break
                need(os.fstat(log.fileno()).st_size<MAX_LOG,'CHILD_LOG_BOUND')
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
                time.sleep(.02)
        else:
            code=child.wait(timeout=timeout);owned=False
    except BaseException as error:primary=error
    finally:
        if child is not None and owned and not new_session and child.returncode is not None:
            # Popen.wait may reap while handling KeyboardInterrupt. Do not signal a reused PID.
            owned=False;code=child.returncode
        if child is not None and owned:
            try:
                if new_session:os.killpg(child.pid,signal.SIGKILL)
                else:os.kill(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            except BaseException as error:cleanup.append(error)
            try:code=child.wait(timeout=5);owned=False
            except BaseException as error:cleanup.append(error)
        elif child is not None and child.returncode is None:
            # Ownership was lost; never signal a potentially reused PGID.
            try:code=child.wait(timeout=5)
            except BaseException as error:cleanup.append(error)
        if primary is None and not cleanup:
            try:
                size=os.fstat(log.fileno()).st_size;need(size<MAX_LOG,'CHILD_LOG_BOUND')
                log.seek(0);raw=log.read(MAX_LOG);need(len(raw)<MAX_LOG,'CHILD_LOG_BOUND')
            except BaseException as error:primary=error
        try:log.close()
        except BaseException as error:cleanup.append(error)
    if primary is not None:
        if cleanup:primary.preparation_ci_cleanup_unknown=True
        raise primary
    if cleanup:
        error=RuntimeError('CHILD_CLEANUP_UNKNOWN');error.preparation_ci_cleanup_unknown=True;raise error
    return code,raw


def summary(name,count):
    return {'schema':1,'state':'PASS','suite':name,'tests':count,'errors':0,'failures':0,'skips':0,
        'python':sys.version.split()[0],'host_NOT_RUN':True,'network_NOT_RUN':True}


def terminal(raw,name,count):
    need(type(raw) is bytes and raw.splitlines(),'PUBLIC_TEST_EMPTY')
    value=strict_json(raw.splitlines()[-1])
    # JSON representation preserves bool/int distinction that Python equality loses.
    need(json.dumps(value,sort_keys=True)==json.dumps(summary(name,count),sort_keys=True),'PUBLIC_TEST_FAILURE_OR_SKIP')
    return value


def clean_import():
    # Real native imports, no module stubs, monkeypatches, or site-packages.
    import ctypes, uuid
    need(ctypes.CDLL(None).getpid()==os.getpid(),'CLEAN_CTYPES_NATIVE_CALL')
    need(len(uuid.uuid4().bytes)==16,'CLEAN_UUID_IMPORT')


def aggregate():
    return {'schema':1,'state':'PASS','tests':sum(count for name,count in SUITES),
        'suite_counts':dict(SUITES),'errors':0,'failures':0,'skips':0,
        'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,
        'fresh_authority_NOT_RUN':True,'production_resume':'NOT_EXECUTED',
        'preparation_compiler_binding':'SELECTED_RESOURCEBIND','delivery_pins_bound':True,
        'c_scope':'HYDRATION_COMPILE_REAL_BINDING_MUTATION_ONLY','c_application_assembly':'NOT_RUN',
        'source_bound_build_verified':True,'manifest_pin_count':255,'artifact_file_count':256,
        'runtime_files_preserved':107,'runtime_package_files_preserved':110,
        'original_archive_sha256':ARCHIVE_SHA,'parent_archive_sha256':PARENT_ARCHIVE_SHA,
        'selected_archive_sha256':SELECTED_ARCHIVE_SHA,'selected_manifest_sha256':SELECTED_MANIFEST_SHA,
        'compiler_source_commit':COMPILER_SOURCE_COMMIT,'compiler_source_tree':COMPILER_SOURCE_TREE,
        'selected_compiler_contents_reproduced':True}


def run_suite(root,name):
    need(name in dict(SUITES),'UNKNOWN_FOCUSED_SUITE');clean_import()
    # Synthetic mkdir fixtures need declared modes, only in this disposable child.
    os.umask(0o022)
    candidate=root/CANDIDATE_TARGET;kit=root/PARENT_KIT_TARGET
    os.environ['EPOCH7_RESOURCE_TEST_KIT_ROOT']=str(kit)
    os.environ['EPOCH7_RESOURCE_TEST_HELPERS']=str(candidate/'kit-overlay/helpers')
    os.environ['EPOCH7_RESOURCE_TEST_ENTRY']=str(candidate/'kit-overlay/epoch7_recovery_entry.py')
    os.environ['EPOCH7_RESOURCE_TEST_PREPARATION_ROOT']=str(root/'b-release-parent-fix-candidate/preparation-bound')
    os.environ['RESOURCEBIND_BASELINE_ARCHIVE']=str(root/PARENT_ARCHIVE_TARGET)
    os.environ['EPOCH7_PREP_TEST_KIT_ROOT']=str(root/KIT_TARGET)
    os.environ['EPOCH7_COMPILER_TEST_ARCHIVE']=str(root/SELECTED_ARCHIVE_TARGET)
    paths=[candidate/'tests',candidate/'kit-overlay/helpers',kit/'helpers',
           kit/'xuanjun-p2-package/stage1',kit/'xuanjun-p2-package/scripts']
    paths.extend(sorted(p for p in (kit/'tests').iterdir() if p.is_dir()))
    sys.path[:0]=[str(p) for p in paths]
    names={'aggregate':[candidate/'tests/test_resource_aggregate_closure.py'],
           'diagnostics':[candidate/'tests/test_failure_labels.py'],
           'observer':[candidate/'kit-overlay/tests/live_controls/test_epoch7_observer_binding.py'],
           'builder':[candidate/'build/test_build_resourcebind_kit.py'],
           'binding':[candidate/'preparation-overlay/test_compiler_binding.py'],
           'delivery':[candidate/'delivery-overlay/test_resourcebind_delivery.py']}
    suite=unittest.TestSuite()
    for index,path in enumerate(names[name]):
        label='resourcebind_focused_'+name+'_'+str(index);module=types.ModuleType(label)
        module.__file__=str(path);sys.modules[label]=module
        exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    wanted=dict(SUITES)[name];need(suite.countTestCases()==wanted,'EXACT_FOCUSED_TEST_COUNT')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    need(result.wasSuccessful() and not result.skipped and result.testsRun==wanted,'FOCUSED_TEST_FAILURE_OR_SKIP')
    print(json.dumps(summary(name,wanted),sort_keys=True))


def build_exact_source(work,output_dir,head,tree):
    output_dir.mkdir(mode=0o700)
    archive=output_dir/'epoch7-kit-resourcebind.tar.gz';metadata=output_dir/'build-metadata.json'
    argv=[sys.executable,'-I','-B','-S',str(work/CANDIDATE_TARGET/'build/build_resourcebind_kit.py'),
          '--archive',str(work/PARENT_ARCHIVE_TARGET),'--candidate-root',str(work/CANDIDATE_TARGET),
          '--source-commit',head,'--source-tree',tree,'--output',str(archive),'--metadata',str(metadata)]
    code,raw=run_child(argv,work,180,new_session=False,file_limit=MAX_ARTIFACT_FILE)
    print(raw.decode('utf-8','replace'));need(code==0,'SOURCE_BOUND_BUILD_FAILED')
    terminal=strict_json(raw.splitlines()[-1]);value=strict_json(metadata.read_bytes());out=value['output']
    need(terminal=={key:item for key,item in out.items() if key!='files'},'BUILD_TERMINAL_MISMATCH')
    need(out['source_commit']==head and out['source_tree']==tree and out['file_count']==256
         and out['manifest_pin_count']==255 and out['root']=='epoch7-recovery-candidate-r7-resourcebind',
         'BUILD_SOURCE_OR_INVENTORY_MISMATCH')
    read_pin(output_dir,archive.name,out['archive_bytes'],out['archive_sha256'])
    need(value['runtime_files_preserved']==107 and value['runtime_package_files_preserved']==110
         and value['modules_unchanged'] is True and value['host_collection']=='NOT_RUN'
         and value['production_resume_authorized'] is False,'BUILD_SCOPE_MISMATCH')
    selected=selected_archive_files((work/SELECTED_ARCHIVE_TARGET).read_bytes())
    need(type(out['archive_bytes']) is int and 0<out['archive_bytes']<=MAX_ARTIFACT_FILE,'REBUILD_ARCHIVE_BOUND')
    rebuilt={}
    with tarfile.open(str(archive),mode='r:gz') as stream:
        members=stream.getmembers();need(len(members)==298,'REBUILD_HEADER_COUNT')
        for member in members:
            if member.isdir():continue
            prefix='epoch7-recovery-candidate-r7-resourcebind/'
            need(member.isreg() and member.name.startswith(prefix),'REBUILD_MEMBER')
            name=safe_name(member.name[len(prefix):])
            need(name in selected and name not in rebuilt and member.size==len(selected[name]),'REBUILD_MEMBER_SCOPE')
            with stream.extractfile(member) as source:body=source.read(member.size+1)
            need(body==selected[name],'REBUILD_SELECTED_BYTES');rebuilt[name]=body
    need(set(rebuilt)==set(selected),'REBUILD_EXACT_SELECTED_FILES')
    need(out['manifest_sha256']==SELECTED_MANIFEST_SHA,'REBUILD_SELECTED_MANIFEST')
    # Canonical contents must match across official Python/zlib versions.
    # The selected public compressed archive is independently pinned above.
    print('SELECTED_COMPILER_CONTENTS_VERIFIED='+json.dumps({'files':len(rebuilt),
        'manifest_sha256':SELECTED_MANIFEST_SHA,'selected_archive_sha256':SELECTED_ARCHIVE_SHA,
        'rebuilt_archive_sha256':out['archive_sha256'],
        'compressed_bytes_identical':out['archive_sha256']==SELECTED_ARCHIVE_SHA},sort_keys=True))
    print('SOURCE_BOUND_BUILD_VERIFIED='+json.dumps(terminal,sort_keys=True))


def worker():
    publication_pins();need(os.getsid(0)==os.getpid(),'WORKER_OWNED_SESSION_REQUIRED')
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']);public_inventory(root)
    tree=git(root,['rev-parse','--verify',head+'^{tree}'])
    print('CI_SOURCE_IDENTITIES='+json.dumps({'current_checkout':{'commit':head,'tree':tree},
        'resourcebind_build_source':{'commit':COMPILER_SOURCE_COMMIT,'tree':COMPILER_SOURCE_TREE},
        'dependency_publication':{'commit':DEPENDENCY_PUBLICATION_COMMIT,'tree':DEPENDENCY_PUBLICATION_TREE}},sort_keys=True))
    records=checkout_records(root,head);files=fixtures(root,records)
    clean_import()
    with tempfile.TemporaryDirectory(prefix='p2-resourcebind-public-') as folder:
        work=materialize(pathlib.Path(folder)/'fixture',files)
        check_materialized(work,files)
        for name,wanted in SUITES:
            argv=[sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--suite',str(work),name]
            code,raw=run_child(argv,work,180,new_session=False)
            print(raw.decode('utf-8','replace'));need(code==0,'PUBLIC_TEST_PROCESS_FAILED')
            terminal(raw,name,wanted)
            check_materialized(work,files)
        build_exact_source(work,pathlib.Path(folder)/'artifact',COMPILER_SOURCE_COMMIT,COMPILER_SOURCE_TREE)
        check_materialized(work,files)
        public_inventory(root)
        need(git(root,['rev-parse','--verify','HEAD'])==head,'HEAD_CHANGED')
        need(checkout_records(root,head)==records,'INPUT_CHANGED_AFTER_TEST')
    print(json.dumps(aggregate(),sort_keys=True))


class ResourceAggregatePublicTests(unittest.TestCase):
    def test_exact_public_focused_suites(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,600)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        self.assertEqual(strict_json(raw.splitlines()[-1]),aggregate())
    def test_exact_readonly_workflow_contract(self):
        publication_pins();root=pathlib.Path(__file__).resolve().parents[1]
        raw=read_pin(root,WORKFLOW_PATH,WORKFLOW_SIZE,WORKFLOW_SHA)
        text=raw.decode('utf-8');self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        for name in ('test_p2_b_resource_aggregate_fix.py','test_p2_b_resource_aggregate_fix_contract.py'):
            self.assertIn('python3 -I -B -S tests/'+name+' -v',text)
        self.assertNotIn('secrets.',text);self.assertIn('timeout-minutes: 12',text)
        self.assertIn('python:3.6.15-bullseye',text);self.assertIn('python:3.12-bookworm',text)


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    elif len(sys.argv)==4 and sys.argv[1]=='--suite':run_suite(pathlib.Path(sys.argv[2]).resolve(),sys.argv[3])
    else:unittest.main(verbosity=2)
