"""Exact-HEAD, offline claim-only successor fixture gate. No host admission.

Only new focused suites run. The selected public archive supplies immutable
historical fixture definitions; its old test suites are never executed.
"""
import ast,hashlib,io,json,os,pathlib,re,resource,signal,stat,subprocess,sys,tarfile,tempfile,time,types,unittest
FEATURE_ID='P2_RETAINED_RECOVERY'
MAX_LOG=1048576
MAX_ARTIFACT_FILE=33554432
CANDIDATE_TARGET='c-capability-lifecycle-candidate'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/'
REGISTRY_PATH='governance/features.json'
WORKFLOW_PATH='.github/workflows/p2-capability-lifecycle.yml'
GATE_PATH='tests/test_p2_capability_lifecycle.py'
CONTRACT_PATH='tests/test_p2_capability_lifecycle_contract.py'
SELECTED_ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz'
SELECTED_ARCHIVE_TARGET='b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz'
SELECTED_ARCHIVE_SIZE=1056853
SELECTED_ARCHIVE_SHA='6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e'
SELECTED_MANIFEST_SHA='6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
SELECTED_ENTRY_SHA='071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5'
BASELINE_SOURCE_COMMIT='ef21ca95331769622c294c65bb60ec7ceed0c392'
BASELINE_SOURCE_TREE='5a70c5627afe75fcd475c20e71ee9bfb0b6a156d'
# Immutable source identity is separate from the later current checkout HEAD.
COMPILER_SOURCE_COMMIT='105996ed06a0bdb5d025914cf08ebd448425f739'
COMPILER_SOURCE_TREE='343d315b3ead6266a626b5875dbdd6c2fa0309af'
DEPENDENCY_PUBLICATION_COMMIT='e2df38160e635af96dcfd63a1b75cf64671e4935'
DEPENDENCY_PUBLICATION_TREE='ac85f40c5717ccf147606d265808e629127cc918'
SUCCESSOR_ARCHIVE_PATH=PUBLIC_PREFIX+'artifact/epoch7-kit-claim-lifecycle.tar.gz'
SUCCESSOR_ARCHIVE_TARGET=CANDIDATE_TARGET+'/artifact/epoch7-kit-claim-lifecycle.tar.gz'
SUCCESSOR_MANIFEST_PATH=PUBLIC_PREFIX+'artifact/recovery-kit-manifest.json'
SUCCESSOR_REPORT_PATH=PUBLIC_PREFIX+'artifact/build-result.json'
SUCCESSOR_ARCHIVE_SIZE=1074448
SUCCESSOR_ARCHIVE_SHA='bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3'
SUCCESSOR_MANIFEST_SHA='91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392'
SUCCESSOR_ENTRY_SHA='21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890'
SUCCESSOR_ENTRY_BYTES=56593

KIT_TARGET=CANDIDATE_TARGET+'/baseline'
SUITE_NAMES=('collector','preflight','routing','factory','census','transactions','lifecycle','preparation','delivery','builder')
SUITES=(('collector', 26),
 ('preflight', 11),
 ('routing', 27),
 ('factory', 26),
 ('census', 12),
 ('transactions', 55),
 ('lifecycle', 40),
 ('preparation', 31),
 ('delivery', 47),
 ('builder', 50))
PINS_BOUND=True
WORKFLOW_SIZE=5336
WORKFLOW_SHA='41b50b74ff4cf272b6c360f278413a21cf4e1fb6aa84dcd99edff90ce6fd96e6'
SOURCE_TARGETS={'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz': 'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/C_TRANSACTION_SEMANTICS.md': 'c-capability-lifecycle-candidate/C_TRANSACTION_SEMANTICS.md',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/README.md': 'c-capability-lifecycle-candidate/README.md',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/SOURCE_IDENTITY.json': 'c-capability-lifecycle-candidate/SOURCE_IDENTITY.json',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/artifact/build-result.json': 'c-capability-lifecycle-candidate/artifact/build-result.json',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/artifact/epoch7-kit-claim-lifecycle.tar.gz': 'c-capability-lifecycle-candidate/artifact/epoch7-kit-claim-lifecycle.tar.gz',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/artifact/recovery-kit-manifest.json': 'c-capability-lifecycle-candidate/artifact/recovery-kit-manifest.json',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/build/OVERLAY_INPUTS.json': 'c-capability-lifecycle-candidate/build/OVERLAY_INPUTS.json',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/build/build_claim_successor_kit.py': 'c-capability-lifecycle-candidate/build/build_claim_successor_kit.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/build/test_build_claim_successor_kit.py': 'c-capability-lifecycle-candidate/build/test_build_claim_successor_kit.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/PREPARATION_COMMAND.UNBOUND.txt': 'c-capability-lifecycle-candidate/delivery/PREPARATION_COMMAND.UNBOUND.txt',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/README.md': 'c-capability-lifecycle-candidate/delivery/README.md',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/epoch7_prepare_successor_delivery.py': 'c-capability-lifecycle-candidate/delivery/epoch7_prepare_successor_delivery.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/extract_epoch7_successor_kit.py': 'c-capability-lifecycle-candidate/delivery/extract_epoch7_successor_kit.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/test_successor_delivery.py': 'c-capability-lifecycle-candidate/delivery/test_successor_delivery.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/epoch7_recovery_entry.py': 'c-capability-lifecycle-candidate/kit-overlay/epoch7_recovery_entry.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_claim_successor.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_claim_successor.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_approval.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_approval.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_complete_approval.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_complete_approval.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_delta.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_delta.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_containment.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_containment.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_factory.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_factory.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_observer.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_observer.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_phases.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_phases.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_injected_recovery.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_injected_recovery.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_live_controls.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_live_controls.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_pre_active_guards.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_pre_active_guards.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_protected_fs.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_protected_fs.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_recovery_sequence.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_recovery_sequence.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_resource_plan.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_resource_plan.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_snapshot.py': 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_snapshot.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/preparation/README.md': 'c-capability-lifecycle-candidate/preparation/README.md',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/preparation/epoch7_prepare_successor.py': 'c-capability-lifecycle-candidate/preparation/epoch7_prepare_successor.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/preparation/test_prepare_successor.py': 'c-capability-lifecycle-candidate/preparation/test_prepare_successor.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/synthetic_historical_seed.py': 'c-capability-lifecycle-candidate/tests/synthetic_historical_seed.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_capability_lifecycle.py': 'c-capability-lifecycle-candidate/tests/test_capability_lifecycle.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_census_race_classification.py': 'c-capability-lifecycle-candidate/tests/test_census_race_classification.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_predecessor_snapshot.py': 'c-capability-lifecycle-candidate/tests/test_predecessor_snapshot.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_approval_factory_entry.py': 'c-capability-lifecycle-candidate/tests/test_successor_approval_factory_entry.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_preflight_integration.py': 'c-capability-lifecycle-candidate/tests/test_successor_preflight_integration.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_resource_routing.py': 'c-capability-lifecycle-candidate/tests/test_successor_resource_routing.py',
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_transactions.py': 'c-capability-lifecycle-candidate/tests/test_successor_transactions.py'}
PINS={'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz': (1056853,
                                                                                                                '6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e',
                                                                                                                'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/C_TRANSACTION_SEMANTICS.md': (4905,
                                                                                                 '34eec14744d724316805efa8e60bf5ad3f36a6aa67b24c3211b2105fea02449b',
                                                                                                 'c-capability-lifecycle-candidate/C_TRANSACTION_SEMANTICS.md'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/README.md': (7801,
                                                                                'bf75a69ae187519dd71c4db68eef7c735152e5338c58d978017add5126041d77',
                                                                                'c-capability-lifecycle-candidate/README.md'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/SOURCE_IDENTITY.json': (13121,
                                                                                           '506af286886ff0706265e0d23a336a52311739b78f46e60d9012e572fdb35924',
                                                                                           'c-capability-lifecycle-candidate/SOURCE_IDENTITY.json'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/artifact/build-result.json': (79105,
                                                                                                 'bf4eeed1654fe037e76a9ecdd9400595bf4d2b13dfc785001316621ee4b25c40',
                                                                                                 'c-capability-lifecycle-candidate/artifact/build-result.json'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/artifact/epoch7-kit-claim-lifecycle.tar.gz': (1074448,
                                                                                                                 'bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3',
                                                                                                                 'c-capability-lifecycle-candidate/artifact/epoch7-kit-claim-lifecycle.tar.gz'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/artifact/recovery-kit-manifest.json': (62752,
                                                                                                          '91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392',
                                                                                                          'c-capability-lifecycle-candidate/artifact/recovery-kit-manifest.json'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/build/OVERLAY_INPUTS.json': (5577, '1cc4936490742024f06055f91788394116749751c00b1b69172ba1da79413a60',
                                                                                                'c-capability-lifecycle-candidate/build/OVERLAY_INPUTS.json'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/build/build_claim_successor_kit.py': (20859, '4acc729d6f0be4fb073296f706e4913b4b4591acb193ba7ab905157cb2abd511',
                                                                                                         'c-capability-lifecycle-candidate/build/build_claim_successor_kit.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/build/test_build_claim_successor_kit.py': (35764, 'd8d5d41db84709272a7b8ee05e268699ae4faee93e2cf876febb2dba58aa3f1e',
                                                                                                              'c-capability-lifecycle-candidate/build/test_build_claim_successor_kit.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/PREPARATION_COMMAND.UNBOUND.txt': (1023,
                                                                                                               'afb40f8be4110bf1fdc704bdfb12488a122dedc532dda19dd825a5b08c18c291',
                                                                                                               'c-capability-lifecycle-candidate/delivery/PREPARATION_COMMAND.UNBOUND.txt'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/README.md': (4072,
                                                                                         '0f6ab10be9b0dee07f12dc7bf27fc7795e72766ca68ead6801ee7696feaedba3',
                                                                                         'c-capability-lifecycle-candidate/delivery/README.md'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/epoch7_prepare_successor_delivery.py': (42469,
                                                                                                                    '252385a552b81f6c3c390bdace95a013dc07db0afffef276739bac67b463106a',
                                                                                                                    'c-capability-lifecycle-candidate/delivery/epoch7_prepare_successor_delivery.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/extract_epoch7_successor_kit.py': (10222,
                                                                                                               '30c5fa4fd0e818b2baa95bc7163f88bb0a60b548e9ca23d1cf0b1142c6b6d50f',
                                                                                                               'c-capability-lifecycle-candidate/delivery/extract_epoch7_successor_kit.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/delivery/test_successor_delivery.py': (35589,
                                                                                                          '713efcd9c16744cf6aa44c7f776cbbcb13a9cb01aba5c3c3b2ee75be5eaf8753',
                                                                                                          'c-capability-lifecycle-candidate/delivery/test_successor_delivery.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/epoch7_recovery_entry.py': (56593,
                                                                                                           '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890',
                                                                                                           'c-capability-lifecycle-candidate/kit-overlay/epoch7_recovery_entry.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_claim_successor.py': (39213,
                                                                                                                    '583120b8692ba84a44a94dbf7a3927a8042465d535c8ce9e3ccc5eea0063122a',
                                                                                                                    'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_claim_successor.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_approval.py': (8983, '0587f0e1f81e7f70ab098a13b1e0a3b47cad40344e4237128716953f2ad34f55', 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_approval.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_complete_approval.py': (16092,
                                                                                                                      'aacfc5a7dfe9badb5ad6037dad5fbdf15bc6e2a41c5ff032263a01a987240216',
                                                                                                                      'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_complete_approval.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_delta.py': (24030,
                                                                                                          'cd9bf06169668ec305a58308594aa4eb4f47b3ec6a908f2ecdb30ae3b0bb27ba',
                                                                                                          'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_delta.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_containment.py': (16124,
                                                                                                                     '7ff5c58b2aeb1b2c794629532b3e326113664fbd29a038f2f2f04a5b550a19dc',
                                                                                                                     'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_containment.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_factory.py': (47755,
                                                                                                                 '6d37155f55f6ae8dace399d69618deda03544bff6d9fc0d20b1918d4ceecd531',
                                                                                                                 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_factory.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_observer.py': (47961,
                                                                                                                  '97f735aff70f8c051aa4b76633be67ce3692bd10f979100f496b1637b086753d',
                                                                                                                  'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_observer.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_host_phases.py': (36672,
                                                                                                                '1423cba44df64030f302c8d42230c296bf50de376938977b2441c79e7de43ddf',
                                                                                                                'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_host_phases.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_injected_recovery.py': (23243,
                                                                                                                      'c8a22c90261c6db3b557e45b0f4452a280f2bbe924bef318791866415a41aaae',
                                                                                                                      'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_injected_recovery.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_live_controls.py': (40759,
                                                                                                                  '294c7102467ff5158fc674322d7c572d3f5df005a7424e1bbe4171b1487d4979',
                                                                                                                  'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_live_controls.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_pre_active_guards.py': (16500,
                                                                                                                      '82b5c1d64801789ab1016e5c80cd54eb04f54433a11c13349e009cc5763ccfcf',
                                                                                                                      'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_pre_active_guards.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_protected_fs.py': (25544,
                                                                                                                 'e6a1e80c4dccd0702c3b95b475862bad251bd0291d0db7ed7c806cb37fc57b9f',
                                                                                                                 'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_protected_fs.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_recovery_sequence.py': (36334,
                                                                                                                      'b941d51744f58bfe81d1fc89c18053e1f42e04f325d99e0300172f23e41231f8',
                                                                                                                      'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_recovery_sequence.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_resource_plan.py': (25057,
                                                                                                                  '5898ed8fac9a266702fd3b61098bc1b29405cdc2c9844d538f67855bea0e69dc',
                                                                                                                  'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_resource_plan.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/kit-overlay/helpers/epoch7_snapshot.py': (56532,
                                                                                                             '99e5a13f94b14b09b1434c0cb6cb19c02ea7394c45b2896a5d24d006b0b59f73',
                                                                                                             'c-capability-lifecycle-candidate/kit-overlay/helpers/epoch7_snapshot.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/preparation/README.md': (11758,
                                                                                            '7f37fd3f2d5356e082ee22f32d4064940cd9ef630d357d4bc11abb5dfaa92524',
                                                                                            'c-capability-lifecycle-candidate/preparation/README.md'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/preparation/epoch7_prepare_successor.py': (37390,
                                                                                                              '71b7f9b6a63e96042194b218042a44929ed51033065c445aa9281feae76b38f5',
                                                                                                              'c-capability-lifecycle-candidate/preparation/epoch7_prepare_successor.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/preparation/test_prepare_successor.py': (34833,
                                                                                                            'd51bf4d1026454c1d0c3eb81b4bdc97a3eb994a1cbd329e497106d0016e41e7a',
                                                                                                            'c-capability-lifecycle-candidate/preparation/test_prepare_successor.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/synthetic_historical_seed.py': (3140,
                                                                                                         'a46fc664f0ecb489796fedd22042b0a181871737ede5b5347c6b8abb61e701f0',
                                                                                                         'c-capability-lifecycle-candidate/tests/synthetic_historical_seed.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_capability_lifecycle.py': (41913,
                                                                                                         '03d906a9afeadce197c5fc2a52600c905e94c9056d669e9b08988b77cbcba29e',
                                                                                                         'c-capability-lifecycle-candidate/tests/test_capability_lifecycle.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_census_race_classification.py': (17027,
                                                                                                               'e520affdb19ec9c0faa8804bb1060b6952579e03ced33e0b7c3ba788f6891d63',
                                                                                                               'c-capability-lifecycle-candidate/tests/test_census_race_classification.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_predecessor_snapshot.py': (35063,
                                                                                                         '367e5d222d251ef1ff7158f27cca8f0671b7d9e95b7c342aafe5ff7b485abcd7',
                                                                                                         'c-capability-lifecycle-candidate/tests/test_predecessor_snapshot.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_approval_factory_entry.py': (27029,
                                                                                                                     'b4deae453ab587594e3bac3570332e1cc2fa8383a4fc1f4cacf965435bf2bb62',
                                                                                                                     'c-capability-lifecycle-candidate/tests/test_successor_approval_factory_entry.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_preflight_integration.py': (24417,
                                                                                                                    '12f619c9f657f26f83ef38c6fa8c28c7687e0b687fa5586aa55fdf36d54fe200',
                                                                                                                    'c-capability-lifecycle-candidate/tests/test_successor_preflight_integration.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_resource_routing.py': (27041,
                                                                                                               'ff39d05b41f760293b6e058ab9d1a5332a81d96209cdbd4aad537dac375c75ff',
                                                                                                               'c-capability-lifecycle-candidate/tests/test_successor_resource_routing.py'),
 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/tests/test_successor_transactions.py': (63942,
                                                                                                           'b244b8c8478cf54fbf0ff2200591f28d296d8b0887939421e30a60dc376db996',
                                                                                                           'c-capability-lifecycle-candidate/tests/test_successor_transactions.py')}
PUBLIC_DIRECTORIES=(PUBLIC_PREFIX+'kit-overlay',PUBLIC_PREFIX+'tests',PUBLIC_PREFIX+'build',PUBLIC_PREFIX+'preparation',PUBLIC_PREFIX+'delivery',PUBLIC_PREFIX+'artifact')

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


def selected_archive_files(raw):
    need(type(raw) is bytes and len(raw)==SELECTED_ARCHIVE_SIZE and digest(raw)==SELECTED_ARCHIVE_SHA,'SELECTED_ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r7-resourcebind/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)==298,'SELECTED_ARCHIVE_HEADER_COUNT')
        seen=set();dirs=set()
        for row in rows:
            safe_name(row.name);need(row.name not in seen,'SELECTED_ARCHIVE_DUPLICATE');seen.add(row.name)
            need(row.name==prefix[:-1] or row.name.startswith(prefix),'SELECTED_ARCHIVE_ROOT')
            need(not row.pax_headers and not row.linkname,'SELECTED_ARCHIVE_EXTENDED_OR_LINK')
            if row.isdir():
                need(row.size==0,'SELECTED_DIRECTORY_BYTES');dirs.add(row.name);continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'SELECTED_ARCHIVE_MEMBER')
            name=safe_name(row.name[len(prefix):]);need(name not in files,'SELECTED_ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'SELECTED_ARCHIVE_BYTES');files[name]=body
    full={prefix+name for name in files}
    expected_dirs={name.rsplit('/',i)[0] for name in full for i in range(1,name.count('/')+1)}
    need(dirs==expected_dirs and not dirs.intersection(full),'SELECTED_DIRECTORY_CLOSURE')
    need(len(files)==256,'SELECTED_ARCHIVE_MEMBER_COUNT')
    need(digest(files['recovery-kit-manifest.json'])==SELECTED_MANIFEST_SHA,'SELECTED_MANIFEST_PIN')
    manifest=strict_json(files['recovery-kit-manifest.json'])
    need(len(manifest['files'])==255 and set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_SELECTED_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'SELECTED_ARCHIVE_SOURCE_PIN')
    need(manifest['kit_source_commit']==BASELINE_SOURCE_COMMIT and
        manifest['kit_source_tree']==BASELINE_SOURCE_TREE,'SELECTED_COMPILER_SOURCE')
    need(digest(files['epoch7_recovery_entry.py'])==SELECTED_ENTRY_SHA,'SELECTED_ENTRY_PIN')
    return files


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


def write_fixture_file(path,name,raw):
    if len(raw)<=MAX_LOG:
        with path.open('xb') as stream:stream.write(raw)
        return
    archives={SELECTED_ARCHIVE_TARGET:(SELECTED_ARCHIVE_SIZE,SELECTED_ARCHIVE_SHA),
              SUCCESSOR_ARCHIVE_TARGET:(SUCCESSOR_ARCHIVE_SIZE,SUCCESSOR_ARCHIVE_SHA)}
    need(name in archives and len(raw)==archives[name][0] and
        digest(raw)==archives[name][1],'OVERSIZED_FIXTURE_NOT_SELECTED_ARCHIVE')
    before=resource.getrlimit(resource.RLIMIT_FSIZE)
    need(before[1]==resource.RLIM_INFINITY or before[1]>=MAX_ARTIFACT_FILE,'ARTIFACT_STAGING_HARD_BOUND')
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_ARTIFACT_FILE,before[1]))
        with path.open('xb') as stream:stream.write(raw)
    finally:resource.setrlimit(resource.RLIMIT_FSIZE,before)


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



def publication_pins():
    need(PINS_BOUND is True,'CLAIM_SUCCESSOR_CI_PUBLICATION_NOT_BOUND')
    need(all(type(value) is str and re.fullmatch('[0-9a-f]{40}',value) and value!='0'*40
         for value in (DEPENDENCY_PUBLICATION_COMMIT,DEPENDENCY_PUBLICATION_TREE)),
         'DEPENDENCY_PUBLICATION_NOT_BOUND')
    need(type(SUITES) is tuple and tuple(name for name,count in SUITES)==SUITE_NAMES
         and all(type(count) is int and count>0 for name,count in SUITES),'EXACT_SUITE_COUNTS_NOT_BOUND')
    need(len(set(SOURCE_TARGETS.values()))==len(SOURCE_TARGETS),'EXACT_PUBLIC_TARGETS')
    need(set(PINS)==set(SOURCE_TARGETS),'EXACT_PUBLIC_INPUTS')
    for path,row in PINS.items():
        need(type(row) in (tuple,list) and len(row)==3,'PUBLIC_PIN_SHAPE')
        size,pin,target=row
        need(type(size) is int and 0<size<=MAX_ARTIFACT_FILE and type(pin) is str
             and re.fullmatch('[0-9a-f]{64}',pin) and target==SOURCE_TARGETS[path],'PUBLIC_PIN_SHAPE')
        safe_name(path);safe_name(target)
    need(type(WORKFLOW_SIZE) is int and 0<WORKFLOW_SIZE<=65536 and type(WORKFLOW_SHA) is str
         and re.fullmatch('[0-9a-f]{64}',WORKFLOW_SHA),'WORKFLOW_NOT_BOUND')


def successor_archive_files(raw):
    need(type(raw) is bytes and len(raw)==SUCCESSOR_ARCHIVE_SIZE and digest(raw)==SUCCESSOR_ARCHIVE_SHA,'SUCCESSOR_ARCHIVE_PIN')
    files={};prefix='epoch7-recovery-candidate-r7-claim-lifecycle/'
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        rows=archive.getmembers();need(len(rows)==299,'SUCCESSOR_ARCHIVE_HEADER_COUNT')
        seen=set();dirs=set()
        for row in rows:
            safe_name(row.name);need(row.name not in seen,'SUCCESSOR_ARCHIVE_DUPLICATE');seen.add(row.name)
            need(row.name==prefix[:-1] or row.name.startswith(prefix),'SUCCESSOR_ARCHIVE_ROOT')
            need(not row.pax_headers and not row.linkname,'SUCCESSOR_ARCHIVE_EXTENDED_OR_LINK')
            if row.isdir():
                need(row.size==0,'SUCCESSOR_DIRECTORY_BYTES');dirs.add(row.name);continue
            need(row.isreg() and row.name.startswith(prefix) and 0<=row.size<=33554432,'SUCCESSOR_ARCHIVE_MEMBER')
            name=safe_name(row.name[len(prefix):]);need(name not in files,'SUCCESSOR_ARCHIVE_NAME')
            with archive.extractfile(row) as stream:body=stream.read(row.size+1)
            need(len(body)==row.size,'SUCCESSOR_ARCHIVE_BYTES');files[name]=body
    full={prefix+name for name in files}
    expected_dirs={name.rsplit('/',i)[0] for name in full for i in range(1,name.count('/')+1)}
    need(dirs==expected_dirs and not dirs.intersection(full),'SUCCESSOR_DIRECTORY_CLOSURE')
    need(len(files)==257,'SUCCESSOR_ARCHIVE_MEMBER_COUNT')
    need(digest(files['recovery-kit-manifest.json'])==SUCCESSOR_MANIFEST_SHA,'SUCCESSOR_MANIFEST_PIN')
    manifest=strict_json(files['recovery-kit-manifest.json'])
    need(len(manifest['files'])==256 and set(files)==set(manifest['files'])|{'recovery-kit-manifest.json'},'EXACT_SUCCESSOR_ARCHIVE_FILES')
    for name,pin in manifest['files'].items():need(digest(files[name])==pin,'SUCCESSOR_ARCHIVE_SOURCE_PIN')
    need(manifest['kit_source_commit']==COMPILER_SOURCE_COMMIT and
        manifest['kit_source_tree']==COMPILER_SOURCE_TREE,'SUCCESSOR_COMPILER_SOURCE')
    need(digest(files['epoch7_recovery_entry.py'])==SUCCESSOR_ENTRY_SHA,'SUCCESSOR_ENTRY_PIN')
    return files

def literal_contract(raw,names,label):
    values={}
    for node in ast.parse(raw.decode('utf-8')).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in names:
                need(name not in values,label+'_DUPLICATE_CONSTANT')
                values[name]=ast.literal_eval(node.value)
    need(set(values)==set(names),label+'_CONSTANT_SCOPE')
    return values

def equal_contract(actual,expected,label):
    # Serialized comparison retains the bool/int distinction Python equality loses.
    need(json.dumps(actual,sort_keys=True)==json.dumps(expected,sort_keys=True),label)

def bound_preparer_contract(raw):
    expected={'NEW_KIT_SHA':SUCCESSOR_MANIFEST_SHA,'NEW_ENTRY_SHA':SUCCESSOR_ENTRY_SHA,
        'NEW_ENTRY_BYTES':SUCCESSOR_ENTRY_BYTES,'NEW_SOURCE':COMPILER_SOURCE_COMMIT,
        'NEW_TREE':COMPILER_SOURCE_TREE}
    equal_contract(literal_contract(raw,expected,'PREPARER'),expected,'BOUND_PREPARER_CONTRACT')

def bound_delivery_contract(raw):
    prep=PUBLIC_PREFIX+'preparation/epoch7_prepare_successor.py'
    expected={'PINS_BOUND':True,'PUBLICATION_COMMIT':DEPENDENCY_PUBLICATION_COMMIT,
        'ARCHIVE_COMMIT':DEPENDENCY_PUBLICATION_COMMIT,'ARCHIVE_SHA':SUCCESSOR_ARCHIVE_SHA,
        'ARCHIVE_SIZE':SUCCESSOR_ARCHIVE_SIZE,'COMPILER_SOURCE':COMPILER_SOURCE_COMMIT,
        'COMPILER_TREE':COMPILER_SOURCE_TREE,'COMPILER_MANIFEST_SHA':SUCCESSOR_MANIFEST_SHA,
        'COMPILER_ENTRY_SHA':SUCCESSOR_ENTRY_SHA,'COMPILER_ENTRY_BYTES':SUCCESSOR_ENTRY_BYTES,
        'COMPILER_CACHE_COUNT':256,'SOURCES':{'epoch7_prepare_successor.py':(PINS[prep][1],PINS[prep][0])}}
    equal_contract(literal_contract(raw,expected,'DELIVERY'),expected,'BOUND_DELIVERY_CONTRACT')

def bound_dependency_contract(records):
    selected=successor_archive_files(records[SUCCESSOR_ARCHIVE_PATH])
    need(selected['recovery-kit-manifest.json']==records[SUCCESSOR_MANIFEST_PATH],
         'SUCCESSOR_STANDALONE_MANIFEST')
    report=strict_json(records[SUCCESSOR_REPORT_PATH]);out=report['output']
    equal_contract({key:out[key] for key in ('root','archive_bytes','archive_sha256','manifest_sha256',
        'source_commit','source_tree','file_count','manifest_pin_count')},
        {'root':'epoch7-recovery-candidate-r7-claim-lifecycle','archive_bytes':SUCCESSOR_ARCHIVE_SIZE,
         'archive_sha256':SUCCESSOR_ARCHIVE_SHA,'manifest_sha256':SUCCESSOR_MANIFEST_SHA,
         'source_commit':COMPILER_SOURCE_COMMIT,'source_tree':COMPILER_SOURCE_TREE,
         'file_count':257,'manifest_pin_count':256},'SUCCESSOR_REPORT_SCOPE')
    equal_contract(out['files'],{name:digest(body) for name,body in selected.items()},
                   'SUCCESSOR_REPORT_FILES')
    need(report['host_collection']=='NOT_RUN' and report['production_resume_authorized'] is False
         and report['runtime_files_preserved']==107 and report['runtime_package_files_preserved']==110
         and report['business_phases_preserved']==16,'SUCCESSOR_REPORT_AUTHORITY')
    bound_preparer_contract(records[PUBLIC_PREFIX+'preparation/epoch7_prepare_successor.py'])
    bound_delivery_contract(records[PUBLIC_PREFIX+'delivery/epoch7_prepare_successor_delivery.py'])


def checkout_records(root,head):
    paths=set(PINS)|{GATE_PATH,CONTRACT_PATH,WORKFLOW_PATH,REGISTRY_PATH}
    records={path:verified_path(root,head,path,max(MAX_LOG,PINS[path][0]) if path in PINS else MAX_LOG)
             for path in sorted(paths)}
    need(pathlib.Path(__file__).read_bytes()==records[GATE_PATH],'CHECKPOINT_NOT_EXACT_HEAD')
    need(len(records[WORKFLOW_PATH])==WORKFLOW_SIZE and digest(records[WORKFLOW_PATH])==WORKFLOW_SHA,'WORKFLOW_PIN')
    registry_contract(records[REGISTRY_PATH])
    bound_dependency_contract(records)
    return records


def fixtures(root,records=None):
    publication_pins()
    result={}
    for path,(size,pin,target) in PINS.items():
        raw=read_pin(root,path,size,pin) if records is None else records[path]
        need(type(raw) is bytes and len(raw)==size and digest(raw)==pin,'PUBLIC_FILE_PIN')
        result[target]=raw
    selected=selected_archive_files(result[SELECTED_ARCHIVE_TARGET])
    successor_archive_files(result[SUCCESSOR_ARCHIVE_TARGET])
    result.update({KIT_TARGET+'/'+name:body for name,body in selected.items()})
    return result


def materialize(root,files):
    need(not root.exists(),'FIXTURE_EXISTS');root.mkdir(mode=0o700)
    allowed=set(SOURCE_TARGETS.values())
    for name,raw in sorted(files.items()):
        safe_name(name);need(name in allowed or name.startswith(KIT_TARGET+'/'),'FIXTURE_PATH')
        path=root/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        write_fixture_file(path,name,raw)
    (root/KIT_TARGET/'helpers/fixtures').mkdir(mode=0o700,parents=True,exist_ok=True)
    return root


def aggregate():
    return {'schema':1,'state':'PASS','tests':sum(count for name,count in SUITES),
        'suite_counts':dict(SUITES),'errors':0,'failures':0,'skips':0,
        'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True,
        'fresh_authority_NOT_RUN':True,'production_resume':'NOT_EXECUTED',
        'c_scope':'LOCAL_SYNTHETIC_CAPABILITY_LIFECYCLE_ONLY','old_suites_NOT_RUN':True,
        'source_bound_build_verified':True,'manifest_pin_count':256,'artifact_file_count':257,
        'runtime_files_preserved':107,'runtime_package_files_preserved':110,'business_phases_preserved':16,
        'selected_archive_sha256':SELECTED_ARCHIVE_SHA,'selected_manifest_sha256':SELECTED_MANIFEST_SHA,
        'successor_archive_sha256':SUCCESSOR_ARCHIVE_SHA,'successor_manifest_sha256':SUCCESSOR_MANIFEST_SHA,
        'compiler_source_commit':COMPILER_SOURCE_COMMIT,'compiler_source_tree':COMPILER_SOURCE_TREE,
        'bound_preparation_and_delivery_verified':True,'selected_successor_contents_reproduced':True}


def run_suite(root,name):
    need(name in dict(SUITES),'UNKNOWN_FOCUSED_SUITE');clean_import()
    os.umask(0o022)
    candidate=root/CANDIDATE_TARGET;kit=root/KIT_TARGET
    os.environ['CLAIM_SUCCESSOR_BASELINE_ARCHIVE']=str(root/SELECTED_ARCHIVE_TARGET)
    os.environ['EPOCH7_SUCCESSOR_PREPARATION']=str(candidate/'preparation')
    paths=[candidate/'tests',candidate/'kit-overlay/helpers',kit/'helpers',
           kit/'xuanjun-p2-package/stage1',kit/'xuanjun-p2-package/scripts']
    paths.extend(sorted(p for p in (kit/'tests').iterdir() if p.is_dir()))
    sys.path[:0]=[str(p) for p in paths]
    names={'collector':candidate/'tests/test_predecessor_snapshot.py',
           'preflight':candidate/'tests/test_successor_preflight_integration.py',
           'routing':candidate/'tests/test_successor_resource_routing.py',
           'factory':candidate/'tests/test_successor_approval_factory_entry.py',
           'census':candidate/'tests/test_census_race_classification.py',
           'transactions':candidate/'tests/test_successor_transactions.py',
           'lifecycle':candidate/'tests/test_capability_lifecycle.py',
           'preparation':candidate/'preparation/test_prepare_successor.py',
           'delivery':candidate/'delivery/test_successor_delivery.py',
           'builder':candidate/'build/test_build_claim_successor_kit.py'}
    path=names[name];label='claim_successor_focused_'+name;module=types.ModuleType(label)
    module.__file__=str(path);sys.modules[label]=module
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    wanted=dict(SUITES)[name]
    if name in ('routing','transactions','lifecycle'):
        # Record unittest's actual inner result, never count the portable wrapper.
        original=unittest.TextTestRunner;results=[]
        class RecordingRunner(original):
            def run(self,suite):
                need(suite.countTestCases()==wanted,'EXACT_FOCUSED_TEST_COUNT')
                result=super(RecordingRunner,self).run(suite);results.append(result);return result
        unittest.TextTestRunner=RecordingRunner
        try:
            code=(module.original.run_isolated(extra_suite_factory=module.lifecycle_suite,include_existing=False)
                  if name=='lifecycle' else module.run_isolated())
        finally:unittest.TextTestRunner=original
        need(code==0 and len(results)==1,'FOCUSED_ISOLATED_FAILURE');result=results[0]
    else:
        suite=unittest.defaultTestLoader.loadTestsFromModule(module)
        need(suite.countTestCases()==wanted,'EXACT_FOCUSED_TEST_COUNT')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    need(result.wasSuccessful() and not result.skipped and result.testsRun==wanted,'FOCUSED_TEST_FAILURE_OR_SKIP')
    print(json.dumps(summary(name,wanted),sort_keys=True))


def build_exact_source(work,output_dir,head,tree):
    output_dir.mkdir(mode=0o700)
    archive=output_dir/'epoch7-kit-claim-lifecycle.tar.gz';metadata=output_dir/'build-metadata.json'
    argv=[sys.executable,'-I','-B','-S',str(work/CANDIDATE_TARGET/'build/build_claim_successor_kit.py'),
          '--archive',str(work/SELECTED_ARCHIVE_TARGET),'--candidate-root',str(work/CANDIDATE_TARGET),
          '--source-commit',head,'--source-tree',tree,'--output',str(archive),'--metadata',str(metadata)]
    code,raw=run_child(argv,work,180,new_session=False,file_limit=MAX_ARTIFACT_FILE)
    print(raw.decode('utf-8','replace'));need(code==0,'SOURCE_BOUND_BUILD_FAILED')
    final=strict_json(raw.splitlines()[-1]);value=strict_json(metadata.read_bytes());out=value['output']
    need(final=={key:item for key,item in out.items() if key!='files'},'BUILD_TERMINAL_MISMATCH')
    need(out['source_commit']==head and out['source_tree']==tree and out['file_count']==257
         and out['manifest_pin_count']==256 and out['root']=='epoch7-recovery-candidate-r7-claim-lifecycle',
         'BUILD_SOURCE_OR_INVENTORY_MISMATCH')
    need(type(out['archive_bytes']) is int and 0<out['archive_bytes']<=MAX_ARTIFACT_FILE,'REBUILD_ARCHIVE_BOUND')
    read_pin(output_dir,archive.name,out['archive_bytes'],out['archive_sha256'])
    need(value['runtime_files_preserved']==107 and value['runtime_package_files_preserved']==110
         and value['business_phases_preserved']==16 and value['phase_logic_unchanged'] is True
         and value['existing_modules_unchanged'] is True and value['module_added']=='epoch7_claim_successor'
         and value['host_collection']=='NOT_RUN' and value['production_resume_authorized'] is False,'BUILD_SCOPE_MISMATCH')
    selected=selected_archive_files((work/SELECTED_ARCHIVE_TARGET).read_bytes())
    mapping=strict_json((work/CANDIDATE_TARGET/'build/OVERLAY_INPUTS.json').read_bytes())
    expected=dict(selected)
    for row in mapping['files']:
        expected[row['kit_target']]=(work/CANDIDATE_TARGET/row['source']).read_bytes()
    old_manifest=strict_json(selected['recovery-kit-manifest.json'])
    manifest=dict(old_manifest);manifest['kit_source_commit']=head;manifest['kit_source_tree']=tree
    manifest['production_resume']='AUTHENTICATED_CLAIM_SUCCESSOR_APPROVAL_GATED_SINGLE_ATTEMPT'
    manifest['status']='CLAIM_SUCCESSOR_CANDIDATE_REQUIRES_NEW_EXACT_APPROVAL'
    manifest['modules']=dict(old_manifest['modules'],epoch7_claim_successor='helpers/epoch7_claim_successor.py')
    manifest['files']={name:digest(body) for name,body in expected.items() if name!='recovery-kit-manifest.json'}
    expected['recovery-kit-manifest.json']=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
    rebuilt={};prefix='epoch7-recovery-candidate-r7-claim-lifecycle/'
    with tarfile.open(str(archive),mode='r:gz') as stream:
        members=stream.getmembers();need(len(members)==299,'REBUILD_HEADER_COUNT')
        for member in members:
            if member.isdir():continue
            need(member.isreg() and member.name.startswith(prefix) and not member.linkname
                 and not member.pax_headers,'REBUILD_MEMBER')
            name=safe_name(member.name[len(prefix):])
            need(name in expected and name not in rebuilt and member.size==len(expected[name]),'REBUILD_MEMBER_SCOPE')
            with stream.extractfile(member) as source:body=source.read(member.size+1)
            need(body==expected[name],'REBUILD_EXPECTED_BYTES');rebuilt[name]=body
    need(set(rebuilt)==set(expected),'REBUILD_EXACT_EXPECTED_FILES')
    need(out['manifest_sha256']==digest(expected['recovery-kit-manifest.json']),'REBUILD_MANIFEST')
    selected_successor=successor_archive_files((work/SUCCESSOR_ARCHIVE_TARGET).read_bytes())
    need(rebuilt==selected_successor,'REBUILD_SELECTED_SUCCESSOR_BYTES')
    need(out['manifest_sha256']==SUCCESSOR_MANIFEST_SHA,'REBUILD_SELECTED_SUCCESSOR_MANIFEST')
    published_report=strict_json((work/CANDIDATE_TARGET/'artifact/build-result.json').read_bytes())
    normalized=dict(value);normalized['output']=dict(out)
    for key in ('archive_bytes','archive_sha256'):
        normalized['output'][key]=published_report['output'][key]
    need(json.dumps(normalized,sort_keys=True)==json.dumps(published_report,sort_keys=True),
         'REBUILD_SELECTED_METADATA')
    print('SELECTED_SUCCESSOR_CONTENTS_VERIFIED='+json.dumps({'files':len(rebuilt),
        'manifest_sha256':SUCCESSOR_MANIFEST_SHA,'selected_archive_sha256':SUCCESSOR_ARCHIVE_SHA,
        'rebuilt_archive_sha256':out['archive_sha256'],
        'compressed_bytes_identical':out['archive_sha256']==SUCCESSOR_ARCHIVE_SHA},sort_keys=True))
    print('SOURCE_BOUND_BUILD_VERIFIED='+json.dumps(final,sort_keys=True))


def worker():
    publication_pins();need(os.getsid(0)==os.getpid(),'WORKER_OWNED_SESSION_REQUIRED')
    root=pathlib.Path(__file__).resolve().parents[1]
    head=git(root,['rev-parse','--verify','HEAD']);public_inventory(root)
    tree=git(root,['rev-parse','--verify',head+'^{tree}'])
    print('CI_SOURCE_IDENTITIES='+json.dumps({'current_checkout':{'commit':head,'tree':tree},
        'selected_baseline_source':{'commit':BASELINE_SOURCE_COMMIT,'tree':BASELINE_SOURCE_TREE},
        'claim_successor_build_source':{'commit':COMPILER_SOURCE_COMMIT,'tree':COMPILER_SOURCE_TREE},
        'dependency_publication':{'commit':DEPENDENCY_PUBLICATION_COMMIT,'tree':DEPENDENCY_PUBLICATION_TREE}},sort_keys=True))
    records=checkout_records(root,head);files=fixtures(root,records);clean_import()
    with tempfile.TemporaryDirectory(prefix='p2-claim-successor-public-') as folder:
        work=materialize(pathlib.Path(folder)/'fixture',files);check_materialized(work,files)
        for name,wanted in SUITES:
            argv=[sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--suite',str(work),name]
            code,raw=run_child(argv,work,240,new_session=False,
                               file_limit=MAX_ARTIFACT_FILE if name=='builder' else MAX_LOG)
            print(raw.decode('utf-8','replace'));need(code==0,'PUBLIC_TEST_PROCESS_FAILED')
            terminal(raw,name,wanted);check_materialized(work,files)
        build_exact_source(work,pathlib.Path(folder)/'artifact',COMPILER_SOURCE_COMMIT,COMPILER_SOURCE_TREE)
        check_materialized(work,files);public_inventory(root)
        need(git(root,['rev-parse','--verify','HEAD'])==head,'HEAD_CHANGED')
        need(checkout_records(root,head)==records,'INPUT_CHANGED_AFTER_TEST')
    print(json.dumps(aggregate(),sort_keys=True))


class ClaimSuccessorPublicTests(unittest.TestCase):
    def test_exact_public_focused_suites(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code,raw=run_child([sys.executable,'-I','-B','-S',str(pathlib.Path(__file__).resolve()),'--worker'],root,900)
        print(raw.decode('utf-8','replace'));self.assertEqual(code,0)
        self.assertEqual(strict_json(raw.splitlines()[-1]),aggregate())
    def test_exact_readonly_workflow_contract(self):
        publication_pins();root=pathlib.Path(__file__).resolve().parents[1]
        raw=read_pin(root,WORKFLOW_PATH,WORKFLOW_SIZE,WORKFLOW_SHA)
        text=raw.decode('utf-8');self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        for name in ('test_p2_capability_lifecycle.py','test_p2_capability_lifecycle_contract.py'):
            self.assertIn('python3 -I -B -S tests/'+name+' -v',text)
        self.assertNotIn('secrets.',text);self.assertIn('timeout-minutes: 20',text)
        self.assertIn('python:3.6.15-bullseye',text);self.assertIn('python:3.12-bookworm',text)


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:worker()
    elif len(sys.argv)==4 and sys.argv[1]=='--suite':run_suite(pathlib.Path(sys.argv[2]).resolve(),sys.argv[3])
    else:unittest.main(verbosity=2)
