"""Exact historical test inputs, not production admission or a new carrier.

The workflow fetches only fixed original commits and the existing fixed artifact.
Missing or changed input raises; this helper never downloads, skips or installs.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
A_COMMIT='1d639347f404f952998b3b414a95e48f66571c3c'
V1_COMMIT='3b6be4aa1ff06d088fe26f44f08b9a505c5b5513'
READONLY_COMMIT='4a0d8e2f48077b0254966e0e54947e910c56596f'
STAGE_A_COMMIT='2853904258ca036a4abcdc2c829278634c45370b'
POST_B_COMMIT='a93c4853b7bbb2a249d49b309c27b98c4082055d'
V1_ARCHIVE_SHA='aa8afb5c05240e3c4835680e8cec765fa4199f0b7f230e3adaced8bc489397f9'
V1_MANIFEST_SHA='e780675ef48c4cd077000c943c5ffe57b390277b6246d43939f54590aabd199a'
BC_ARCHIVE_SHA='5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4'
BC_MANIFEST_SHA='e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a'
POST_B_ARCHIVE_SHA='8556531d52b81ca87f3346f2d098de7aea50cf7838106482aadcc86188c374eb'
POST_B_MANIFEST_SHA='f7118e9a45c77cf260ae516864635d45af4a9159055da3f9ab983ff4ca95f99e'

HISTORY_PINS={'1d639347f404f952998b3b414a95e48f66571c3c': {'scripts/community_preview_site_prepare.py': '48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'},
 '2853904258ca036a4abcdc2c829278634c45370b': {'.github/workflows/chatgpt-community-wechat-sp-offline.yml': '7ad7294c54ad4cabc3eace5ac9ce99b1f5cf31a685341010080a8dd51dc6b073',
                                              'deploy/community-preview/prepare-site.sh': 'f1af825d4acec6d775956a16a19f5e65b3a58c6aae0e703164f84ee9429ba2c6',
                                              'deploy/community-preview/site-preparation-manifest.json': '77d4fa2895439c3f1685b2f4c6792aa335d8421a179b0d3e7d02ca172748302d',
                                              'deploy/community-preview/stage-a-delivery.json': '13bcf76be7478b1ddf56ceb9ac63f124bb7c7d2dac931209b3c70194b0adad25',
                                              'deploy/community-preview/stage-a-owner-call.sh': '84b97a7c88144b5fc3e54ea481d92fa30fd0a560c18654468591fac6a864bfd8',
                                              'docs/development/COMMUNITY_SITE_PREPARATION_STEPS_20261024.md': '2180e3f94a98adb2552babe80bebab87162ce3a39fa6fd70e0de4e431383b8ca',
                                              'docs/development/COMMUNITY_STAGE_A_COMPLETE_20261024.md': '1cc44d949c5c7ce65ad7851d42c69be55a16f156998ce5ea1906f495ad5451fa',
                                              'governance/features.json': '516859a1ea4694a19c3eb1ce5ebdbbe8c22eb7567f227a5820c9fa3b8ea8e563',
                                              'scripts/community_preview_site_prepare.py': '48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55',
                                              'scripts/community_preview_stage_a.py': '94326ff1f3eb5a3d71cdd0cd7ab1846e0beca3dc5e11d4be34c9cc8d2d000f65',
                                              'scripts/community_preview_stage_a_bundle.py': '21f968e4af21cc0efe39a94956a7531559daa49da4af0eb027918d5de1386daf',
                                              'tests/test_community_preview_preparation_steps.py': '0bacc3d87700a3afecdc3984c60fc64a1ce6361e656f3dabae6fcd8086100533',
                                              'tests/test_community_preview_stage_a.py': '0ee65ab44b36a34f798437f9de8a0ffb5fb6eb155a212a364e7fc652d03aef44'},
 '3b6be4aa1ff06d088fe26f44f08b9a505c5b5513': {'deploy/community-preview/control-oci2330-v1-manifest.json': 'e780675ef48c4cd077000c943c5ffe57b390277b6246d43939f54590aabd199a',
                                              'deploy/community-preview/f131-image-receipt.json': 'cba144af0ca2f753413f7bdcec92625c370c479c4708b1d4a1db0b35907c8b45',
                                              'deploy/community-preview/prepare-site.sh': 'f1af825d4acec6d775956a16a19f5e65b3a58c6aae0e703164f84ee9429ba2c6',
                                              'scripts/community_preview_control_carrier.py': '6d1838086f1db541da06398c7f81807ca64dd89afe2cd4657f386a6d29a02143',
                                              'scripts/community_preview_release_plan.py': 'e0870cfaf7f1bb16b8664e644ec616e150b0ada93146a8d955e64c5f3f7ec4b9',
                                              'scripts/community_preview_root_loader.py': '393b9c3f3e5720a1a9164aaafba0f2198fd5e461c49c4e58859c497ef5100f19',
                                              'scripts/community_preview_update_checkpoint.py': 'a73c1fe8ebb71abaefeb56ca880057e23876b5c005d315e4fb1268d3087064fd',
                                              'scripts/community_preview_update_composition.py': 'f3007cdd26d53e7348164d404186602335ee5f237963f5d6f627e5376cfdc4f1',
                                              'scripts/community_preview_upgrade.py': '2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
                                              'scripts/community_preview_version_inspect.py': '98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'},
 '4a0d8e2f48077b0254966e0e54947e910c56596f': {'deploy/community-preview/preupdate-five-readonly.py': 'ba614a215011ed66ec8d99a1a3862f26db10b3757797f890e5b954850cec7c53',
                                              'deploy/community-preview/preupdate-five-readonly.sh': '2b126401c4ba9d17b29e083e17be6528a561337cc1317a30d09174e55d364483',
                                              'deploy/community-preview/three-reasons-readonly.py': '3fb0ceeec0df1d8fb0237e4ffe7b4e0ac1f9cd20d6d632c627451c3e5589a1f6',
                                              'deploy/community-preview/three-reasons-readonly.sh': '1bd54508f5f39a208803d9ab75859d66a2c9c2a0d1af0f9b192ffeb81dfdde00',
                                              'scripts/community_preview_preupdate_bundle.py': 'bc7fb40c0759012d8d6ae179d492cf73e2e6ac10d7aaaa649680af2dd6a1516e',
                                              'scripts/community_preview_preupdate_observe.py': 'e3c0cbd1b5dd69353fe569821255fbfff8c1887846ca1a6a365d63238a2e9ebe',
                                              'scripts/community_preview_three_diagnostics.py': 'e017435f50c4851a85fbb085a86d81cbb430b7925d312ebcd413c83d157ce98a',
                                              'scripts/community_preview_update_composition.py': '6fb687b06aa6410ccc390611cdb572357534067615cf3588c32ca3c9ce006100',
                                              'scripts/community_preview_upgrade.py': '2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
                                              'scripts/community_preview_version_inspect.py': '98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'},
 'a93c4853b7bbb2a249d49b309c27b98c4082055d': {'deploy/community-preview/f131-image-receipt.json': 'cba144af0ca2f753413f7bdcec92625c370c479c4708b1d4a1db0b35907c8b45',
                                              'scripts/community_preview_bc_loader.py': 'da5889402610289578409f1863675a10fc5030f42d73fd2719383ad6203fe766',
                                              'scripts/community_preview_release_plan.py': '81c01a2f94ff71c0af4555b9026a60db0b5ce226a158601e1cf1b6aa4b646fae',
                                              'scripts/community_preview_site_prepare.py': 'ab725ed62e431e8ef827403018145b7682692ef6b608dcc1cc595cd4936125e6',
                                              'scripts/community_preview_stopped_handoff.py': 'ed5b5a347c26ffa5b8406067b7dd542199296d8b643226dbc3457eb6b00b4712',
                                              'scripts/community_preview_update_checkpoint.py': 'e9029ca3e0c36fb1656995fcbe77f46739ee7abfc490adbd0cf4808f0e41b826',
                                              'scripts/community_preview_update_composition.py': '9dcf2ab885e1ee1d9d0a5e1111282727e89381ec0e622f6fbce2a9887ba08062',
                                              'scripts/community_preview_upgrade.py': '2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
                                              'scripts/community_preview_version_inspect.py': '98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3'}}

def digest(raw):return hashlib.sha256(raw).hexdigest()

def bounded_file(path):
    path=Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('HISTORICAL_REGULAR_INPUT_REQUIRED')
    with path.open('rb') as stream:raw=stream.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('HISTORICAL_INPUT_OVERSIZE')
    return raw

def source(commit,path):
    expected=HISTORY_PINS.get(commit,{}).get(path)
    if expected is None:raise ValueError('UNREGISTERED_HISTORICAL_INPUT')
    fixture=os.environ.get('COMMUNITY_HISTORICAL_FIXTURES')
    if fixture:
        raw=bounded_file(Path(fixture)/'git'/commit/path)
    else:
        raw=subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)
    if digest(raw)!=expected:raise ValueError('HISTORICAL_SOURCE_SHA_MISMATCH')
    return raw

def a_source():
    path=os.environ.get('COMMUNITY_TEST_A_ENTRY_FILE')
    raw=bounded_file(path) if path else source(A_COMMIT,'scripts/community_preview_site_prepare.py')
    if digest(raw)!=HISTORY_PINS[A_COMMIT]['scripts/community_preview_site_prepare.py']:
        raise ValueError('HISTORICAL_A_ENTRY_SHA_MISMATCH')
    return raw

@contextlib.contextmanager
def historical_tree(commit):
    if commit not in HISTORY_PINS:raise ValueError('UNREGISTERED_HISTORICAL_COMMIT')
    with tempfile.TemporaryDirectory(prefix='community-historical-test-') as tmp:
        root=Path(tmp)
        for path in HISTORY_PINS[commit]:
            target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source(commit,path));target.chmod(0o600)
        yield root

def v1_carrier():
    # Exercise the unchanged current builder's frozen V1 guard on exact old bytes.
    from scripts import community_preview_control_carrier as carrier
    with historical_tree(V1_COMMIT) as root,patch.object(carrier,'ROOT',root):
        archive,manifest=carrier.build()
    if len(archive)!=111330 or digest(archive)!=V1_ARCHIVE_SHA or digest(manifest)!=V1_MANIFEST_SHA:
        raise ValueError('HISTORICAL_V1_PACKAGE_SHA_MISMATCH')
    return archive,manifest

def bc_carrier():
    from scripts import community_preview_bc_install as installer
    ap=os.environ.get('HANDOFF_OLD_ARCHIVE');mp=os.environ.get('HANDOFF_OLD_MANIFEST')
    if not ap or not mp:raise ValueError('EXACT_12572781194_BC_FIXTURE_REQUIRED')
    archive=bounded_file(ap);manifest=bounded_file(mp)
    if digest(archive)!=BC_ARCHIVE_SHA or digest(manifest)!=BC_MANIFEST_SHA:
        raise ValueError('HISTORICAL_BC_PACKAGE_SHA_MISMATCH')
    # Validate every member using the actual unchanged fixed installer contract.
    installer.validate_archive_contents(archive,manifest)
    return archive,manifest

def post_b_carrier():
    from scripts import community_preview_bc_build as builder
    from scripts import community_preview_carrier_handoff_admission as handoff
    with historical_tree(POST_B_COMMIT) as root,patch.object(builder,'ROOT',root):
        archive,manifest,_=builder.build()
    if digest(archive)!=POST_B_ARCHIVE_SHA or digest(manifest)!=POST_B_MANIFEST_SHA:
        raise ValueError('HISTORICAL_POST_B_PACKAGE_SHA_MISMATCH')
    handoff.members(archive,POST_B_MANIFEST_SHA,POST_B_ARCHIVE_SHA)
    return archive,manifest

# Exact original 37cd bytes for old fixed-composition tests only. These nested
# fixtures are outside the product package allowlist and never fetched at runtime.
COMPOSITION_FIXTURE_COMMIT='37cd60433fa5212423a64dd4b129a4c5274b245a'
COMPOSITION_FIXTURE_FILES={'deploy/community-preview/f131-image-receipt.json': {'bytes': 1356, 'sha256': 'cba144af0ca2f753413f7bdcec92625c370c479c4708b1d4a1db0b35907c8b45', 'git_blob_sha1': '2f49059421858507fb66b576aa378076855041c9'}, 'scripts/community_preview_release_plan.py': {'bytes': 10933, 'sha256': '81c01a2f94ff71c0af4555b9026a60db0b5ce226a158601e1cf1b6aa4b646fae', 'git_blob_sha1': '8568b083e87bab1f5b1415da19416e0c839546a7'}, 'scripts/community_preview_update_checkpoint.py': {'bytes': 26377, 'sha256': 'def3dd75f4ee71eef9e48ac97448b39b9eba1446df334e43d901c64fdb63014b', 'git_blob_sha1': '51bb073492070eb97fb151643b3ae178ee923d24'}, 'scripts/community_preview_update_composition.py': {'bytes': 34123, 'sha256': '8d1810aeb08d65b55f578eac45ade02d7da07aebfd6d370d395a2c6dbf40203d', 'git_blob_sha1': 'c2bcf537e75621f842be27219563671defc76e1f'}, 'scripts/community_preview_upgrade.py': {'bytes': 25382, 'sha256': '2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee', 'git_blob_sha1': '6a637afb440ab689ff132302591bd0a8e5448799'}, 'scripts/community_preview_version_inspect.py': {'bytes': 21615, 'sha256': '98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3', 'git_blob_sha1': 'c44a5518720ff8dece8602508b0c87895895cb34'}}

def composition_source(path):
    expected=COMPOSITION_FIXTURE_FILES.get(path)
    if expected is None:raise ValueError('UNREGISTERED_COMPOSITION_FIXTURE')
    raw=bounded_file(ROOT/'tests/fixtures/community-composition-37cd'/path)
    blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if len(raw)!=expected['bytes'] or digest(raw)!=expected['sha256'] or blob!=expected['git_blob_sha1']:
        raise ValueError('COMPOSITION_FIXTURE_SHA_MISMATCH')
    return raw

@contextlib.contextmanager
def historical_composition():
    """Load exact old admitted sources, never repin current OCR code as approved."""
    import importlib.util
    import scripts
    from contextlib import ExitStack
    with tempfile.TemporaryDirectory(prefix='community-composition-37cd-test-') as tmp:
        root=Path(tmp)
        for path in COMPOSITION_FIXTURE_FILES:
            target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(composition_source(path));target.chmod(0o600)
        def load(name):
            spec=importlib.util.spec_from_file_location('_community_37cd_'+name,root/'scripts'/('community_preview_'+name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        plan=load('release_plan');original=load('upgrade');observation=load('version_inspect')
        with ExitStack() as stack:
            for name,module in (('community_preview_release_plan',plan),('community_preview_upgrade',original),('community_preview_version_inspect',observation)):
                stack.enter_context(patch.object(scripts,name,module))
            controller=load('update_checkpoint')
            stack.enter_context(patch.object(scripts,'community_preview_update_checkpoint',controller))
            composition=load('update_composition')
        yield composition

def verify_inputs():
    for path in COMPOSITION_FIXTURE_FILES:composition_source(path)
    a_source();v1_carrier();bc_carrier();post_b_carrier()
    for commit,paths in HISTORY_PINS.items():
        for path in paths:source(commit,path)
    print('EXACT_HISTORICAL_TEST_INPUTS=PASS; PRODUCTION_EXECUTED=false')

class HistoricalFixtureContract(unittest.TestCase):
    def test_exact_local_composition_sources_match_old_admission_not_current_ocr(self):
        from scripts import community_preview_update_composition as current
        with historical_composition() as fixed:
            self.assertEqual(digest(Path(fixed.__file__).read_bytes()),COMPOSITION_FIXTURE_FILES['scripts/community_preview_update_composition.py']['sha256'])
            for module,pin in fixed.PINS.items():self.assertEqual(digest(Path(module.__file__).read_bytes()),pin)
            self.assertEqual(fixed.PRODUCT,current.PRODUCT);self.assertEqual(fixed.CONTROL,current.CONTROL)
            self.assertEqual(fixed.RECEIPT_SHA,current.RECEIPT_SHA)
            self.assertNotEqual(digest(Path(current.controller.__file__).read_bytes()),fixed.PINS[fixed.controller])
            self.assertNotEqual(digest(Path(current.plan.__file__).read_bytes()),fixed.PINS[fixed.plan])
    def test_local_composition_fixture_missing_changed_or_unregistered_fails_closed(self):
        with patch(__name__+'.bounded_file') as read:
            with self.assertRaisesRegex(ValueError,'UNREGISTERED'):composition_source('../arbitrary.py')
            read.assert_not_called()
        path='scripts/community_preview_release_plan.py'
        with patch(__name__+'.bounded_file',return_value=b'changed'):
            with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):composition_source(path)
        with patch(__name__+'.bounded_file',side_effect=FileNotFoundError),patch('subprocess.check_output') as git:
            with self.assertRaises(FileNotFoundError):composition_source(path)
            git.assert_not_called()
    def test_exact_original_entry_and_both_frozen_carriers(self):
        self.assertEqual(digest(a_source()),HISTORY_PINS[A_COMMIT]['scripts/community_preview_site_prepare.py'])
        self.assertEqual(digest(v1_carrier()[0]),V1_ARCHIVE_SHA)
        self.assertEqual(digest(bc_carrier()[0]),BC_ARCHIVE_SHA)
        self.assertEqual(digest(post_b_carrier()[0]),'8556531d52b81ca87f3346f2d098de7aea50cf7838106482aadcc86188c374eb')
    def test_unknown_commit_or_path_is_rejected_before_git_or_file_read(self):
        with patch('subprocess.check_output') as git,patch(__name__+'.bounded_file') as read:
            for commit,path in [('a'*40,'x'),(A_COMMIT,'../source.py')]:
                with self.assertRaisesRegex(ValueError,'UNREGISTERED'):source(commit,path)
            git.assert_not_called();read.assert_not_called()
    def test_changed_historical_bytes_fail_closed(self):
        with patch.dict(os.environ,{'COMMUNITY_HISTORICAL_FIXTURES':'/synthetic-not-read'}),patch(__name__+'.bounded_file',return_value=b'changed'):
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_MISMATCH'):source(A_COMMIT,'scripts/community_preview_site_prepare.py')
    def test_missing_fixture_is_error_not_skip_or_current_fallback(self):
        with patch.dict(os.environ,{'COMMUNITY_HISTORICAL_FIXTURES':'/synthetic-not-read'}),patch(__name__+'.bounded_file',side_effect=FileNotFoundError),patch('subprocess.check_output') as git:
            with self.assertRaises(FileNotFoundError):source(A_COMMIT,'scripts/community_preview_site_prepare.py')
            git.assert_not_called()
    def test_original_a_override_still_requires_exact_digest(self):
        with patch.dict(os.environ,{'COMMUNITY_TEST_A_ENTRY_FILE':'/synthetic-not-read'}),patch(__name__+'.bounded_file',return_value=b'changed'):
            with self.assertRaisesRegex(ValueError,'A_ENTRY_SHA_MISMATCH'):a_source()
    def test_bc_missing_or_changed_inputs_fail_closed(self):
        with patch.dict(os.environ,{'HANDOFF_OLD_ARCHIVE':'','HANDOFF_OLD_MANIFEST':''}):
            with self.assertRaisesRegex(ValueError,'12572781194'):bc_carrier()
        with patch.dict(os.environ,{'HANDOFF_OLD_ARCHIVE':'a','HANDOFF_OLD_MANIFEST':'b'}),patch(__name__+'.bounded_file',return_value=b'changed'):
            with self.assertRaisesRegex(ValueError,'BC_PACKAGE_SHA_MISMATCH'):bc_carrier()
    def test_v1_guard_rejects_drift_instead_of_repinning(self):
        from scripts import community_preview_control_carrier as carrier
        with historical_tree(V1_COMMIT) as root:
            path=root/'scripts/community_preview_update_composition.py';path.write_bytes(path.read_bytes()+b'\n# drift\n')
            with patch.object(carrier,'ROOT',root),self.assertRaisesRegex(ValueError,'FROZEN_V1_SOURCE_ONLY_USE_BC_BUILD'):
                carrier.build()
    def test_post_b_changed_builder_output_cannot_relabel_frozen_package(self):
        from scripts import community_preview_bc_build as builder
        with patch.object(builder,'build',return_value=(b'changed',b'changed',{})):
            with self.assertRaisesRegex(ValueError,'POST_B_PACKAGE_SHA_MISMATCH'):post_b_carrier()
    def test_fake_clock_direct_replacement_has_actual_caller(self):
        import inspect,time
        calls=[];real=time.monotonic
        def monotonic():
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                calls.append(True);return 0 if len(calls)==1 else 121
            return real()
        def resume_c_before_confirmation():return time.monotonic(),time.monotonic()
        with patch.object(time,'monotonic',new=monotonic):self.assertEqual(resume_c_before_confirmation(),(0,121))
        self.assertEqual(len(calls),2)

    def test_readonly_guard_rejects_drift_instead_of_repinning(self):
        from scripts import community_preview_preupdate_bundle as bundle
        with historical_tree(READONLY_COMMIT) as root:
            path=root/'scripts/community_preview_update_composition.py';path.write_bytes(path.read_bytes()+b'\n# drift\n')
            with patch.object(bundle,'ROOT',root),self.assertRaisesRegex(ValueError,'APPROVED_READONLY_SOURCE_CHANGED'):
                bundle.build()
    def test_workflow_preflight_covers_full_and_existing_historical_consumers(self):
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        def condition(name):return workflow.split('      - name: '+name+'\n',1)[1].splitlines()[0].split('if:',1)[1].strip().strip('"')
        prep=condition('Verify original historical inputs for source tests')
        full=condition('Complete Phase1 and Phase2 source regression')
        self.assertEqual(prep,condition('Retrieve and verify immutable nested 1d and 005c carrier fixtures'))
        # Preflight remains the original superset; only full regression excludes
        # the narrowly classified screenshot capture test with its explicit tag.
        capture_guard = " && !(steps.scope.outputs.capture_only == 'true' && contains(github.event.head_commit.message, '[web-session-browser-scope]'))"
        self.assertTrue(full.startswith('(') and full.endswith(')'+capture_guard))
        full_core = full[1:-len(')'+capture_guard)]
        self.assertEqual(full, '('+full_core+')'+capture_guard)
        self.assertTrue(prep.endswith(' || ('+full_core+')'))
        for marker in ['preview-b-resume-scope','preview-stopped-handoff-scope','preview-stage-a-scope','preview-post-receipt-scope','preview-preupdate-observation-scope']:self.assertIn('['+marker+']',prep)
        self.assertLess(workflow.index('      - name: Verify original historical inputs for source tests'),workflow.index('      - name: Issue76 carrier handoff isolated candidate tests'))
        block=workflow.split('      - name: Verify original historical inputs for source tests\n',1)[1].split('      - name:',1)[0]
        for commit in HISTORY_PINS:self.assertIn(commit,block)
        self.assertIn('python3 -B tests/test_community_historical_fixtures.py --verify-inputs',block)

if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--verify-inputs']:
        sys.path.insert(0,str(ROOT));verify_inputs()
    else:unittest.main()
