import json,os,shutil,tempfile,unittest,subprocess
from pathlib import Path
from scripts.community_mini_snapshot_build import build,REPO,REF
ROOT=Path(__file__).resolve().parents[1]
class CurrentControl(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  p=self.root/'deploy/community-preview';p.mkdir(parents=True)
  shutil.copytree(ROOT/'deploy/community-preview/hangzhou-snapshot',p/'hangzhou-snapshot')
  self.env=dict(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REPOSITORY=REPO,GITHUB_REF=REF,GITHUB_SHA='c'*40,PREVIEW_CONTROL_SHA='c'*40,PREVIEW_ENABLED='true',PREVIEW_TARGET='uk-path-candidate',COMMUNITY_SNAPSHOT_FROM_SOURCE='true')
 def test_new_control_binds_unchanged_pinned_archive(self):
  build(self.root,self.env);b=json.loads((self.root/'hangzhou-snapshot-input/binding.json').read_text());self.assertEqual(b['control_source_sha'],'c'*40);self.assertEqual(b['archive_sha256'],'69b8c4c9647a51912be10ff3e68eb32aae78fc89dcee49c21746f32222f85b33');self.assertEqual((self.root/'hangzhou-snapshot-input/snapshot.zip').read_bytes(),(self.root/'deploy/community-preview/hangzhou-snapshot/snapshot.zip').read_bytes())
 def test_wrong_event_ref_repo_control_enable_target_are_rejected(self):
  for k,v in [('GITHUB_EVENT_NAME','pull_request'),('GITHUB_REF','refs/heads/other'),('GITHUB_REPOSITORY','other/repo'),('PREVIEW_CONTROL_SHA','d'*40),('PREVIEW_ENABLED','false'),('PREVIEW_TARGET','other'),('COMMUNITY_SNAPSHOT_FROM_SOURCE','false')]:
   with self.subTest(field=k):
    with self.assertRaises(ValueError):build(self.root,dict(self.env,**{k:v}))
 def test_original_push_contract_unchanged(self):
  build(self.root,dict(self.env,GITHUB_EVENT_NAME='push',COMMUNITY_SNAPSHOT_PUSH='true',COMMUNITY_SNAPSHOT_FROM_SOURCE='false'))
 def test_same_output_not_overwritten(self):
  build(self.root,self.env)
  with self.assertRaises(ValueError):build(self.root,self.env)
 def test_workflow_guard_rejects_mixed_artifact_and_wrong_product(self):
  text=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
  guard=text.split('      - name: Validate exact current-control snapshot mode',1)[1].split('      - name:',1)[0].split('        run: |',1)[1]
  script=chr(10).join(line[10:] for line in guard.splitlines() if line.strip())
  env=dict(os.environ,GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF=REF,GITHUB_SHA='c'*40,ENABLED='true',PRODUCT='hangzhou-snapshot',CONTROL='c'*40,TARGET='uk-path-candidate',IMAGE='false',OLD_RUN='',OLD_ARTIFACT='',OLD_BINDING='')
  self.assertEqual(subprocess.run(['bash','-e','-c',script],env=env).returncode,0)
  for k,v in [('PRODUCT','legacy-4f'),('OLD_ARTIFACT','14882807728'),('CONTROL','d'*40),('IMAGE','true')]:
   self.assertNotEqual(subprocess.run(['bash','-e','-c',script],env=dict(env,**{k:v})).returncode,0)
 def test_sdk_reuse_does_not_reinstall_or_repack(self):
  text=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
  sdk=text.split('  mini-sdk:',1)[1].split('  mini-preview:',1)[0]
  self.assertIn('if: inputs.snapshot_from_source != true',sdk.split('npm install',1)[0])
  reuse=sdk.split('- name: Reuse exact successful SDK artifacts',1)[1].split('- uses: actions/upload-artifact',1)[0]
  self.assertIn('run-id: 45312094116',reuse);self.assertNotIn('npm install',reuse);self.assertNotIn('tar ',reuse)
if __name__=='__main__':unittest.main()
