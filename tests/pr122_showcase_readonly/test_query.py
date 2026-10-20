import ast,errno,hashlib,importlib.util,json,os,stat,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
SOURCE=Path(__file__).resolve().parents[2]/'scripts/pr122_showcase_readonly.py'
sp=importlib.util.spec_from_file_location('query',str(SOURCE));m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
H='a'*64
def trust():return dict(schema=1,source_writer_principal='writer:one',reviewers={'reviewer:two':dict(status='ACTIVE',custody_evidence_sha256=H)},revoked_review_ids=[],anchors={m.ANCHOR:dict(body_sha256=m.BODY,scope='CONTENT',reviewer_principal='reviewer:two',custody_evidence_sha256=H,issued_unix=100,expires_unix=200)})
def policy():return dict(schema=1,mechanism_manifest_sha256=H,shell_tar_sha256=H,legacy_pages_sha256=H,reviewer_logins=['reviewer-two'])
class QueryTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(dir='/root');self.addCleanup(self.t.cleanup);self.root=Path(self.t.name);self.p=self.root/'input.json';self.p.write_text(json.dumps(trust()));self.p.chmod(0o600)
 def run_query(self,**kwargs):return m.observe(str(self.p),True,now=150,**kwargs)
 def test_stable_protected_file_and_selected_fields(self):
  r=self.run_query();self.assertEqual(r['sha256'],hashlib.sha256(self.p.read_bytes()).hexdigest());self.assertEqual(r['selected']['time_window'],'CURRENT_AT_OBSERVATION');self.assertTrue(r['selected']['expected_content_binding']);self.assertEqual(r['registration'],'UNKNOWN');self.assertEqual(r['selected']['independence'],'UNKNOWN_NOT_ATTESTED')
 def test_absent_leaf_and_missing_parent(self):
  self.p.unlink();self.assertEqual(self.run_query()['existence'],'ABSENT');r=m.observe(str(self.root/'missing'/'input.json'),True);self.assertEqual(r['missing_component'],str(self.root/'missing'));self.assertNotIn('sha256',r)
 def test_permission_denied_not_absent(self):
  with patch.object(m.os,'open',side_effect=PermissionError(errno.EACCES,'DO_NOT_PRINT_SECRET')):r=self.run_query()
  self.assertEqual(r['observation'],'ACCESS_DENIED');self.assertNotEqual(r['existence'],'ABSENT');self.assertNotIn('DO_NOT_PRINT_SECRET',json.dumps(r))
 def test_directory_symlink_fifo_and_hardlink_not_read(self):
  for kind in ('dir','symlink','fifo','hardlink'):
   p=self.root/kind
   if kind=='dir':p.mkdir()
   elif kind=='symlink':p.symlink_to(self.p)
   elif kind=='fifo':os.mkfifo(str(p),0o600)
   else:os.link(str(self.p),str(p))
   with patch.object(m.os,'read',side_effect=AssertionError('must not read')):r=m.observe(str(p),True)
   self.assertEqual(r['observation'],'UNKNOWN');self.assertNotIn('sha256',r)
 def test_unprotected_file_and_parent_rejected_without_read(self):
  self.p.chmod(0o644)
  with patch.object(m.os,'read',side_effect=AssertionError('must not read')):r=self.run_query()
  self.assertEqual(r['reason'],'UNPROTECTED_FILE');self.p.chmod(0o600);self.root.chmod(0o777)
  self.assertEqual(self.run_query()['reason'],'UNPROTECTED_ANCESTOR');self.root.chmod(0o700)
 def test_content_change_clears_digest_and_fields(self):
  def change():self.p.write_text('{}')
  r=self.run_query(checkpoint=change);self.assertEqual(r['reason'],'FILE_CHANGED');self.assertNotIn('sha256',r);self.assertNotIn('selected',r)
 def test_path_replacement_clears_digest_and_fields(self):
  def change():self.p.rename(self.root/'original');self.p.write_text('{}')
  r=self.run_query(checkpoint=change);self.assertEqual(r['reason'],'FILE_CHANGED');self.assertNotIn('sha256',r)
 def test_parent_path_replacement_clears_result(self):
  def change():self.root.rename(str(self.root)+'-moved');self.root.mkdir(mode=0o700)
  self.addCleanup(lambda:__import__('shutil').rmtree(str(self.root)+'-moved',ignore_errors=True))
  r=self.run_query(checkpoint=change);self.assertEqual(r['reason'],'PATH_CHANGED');self.assertNotIn('sha256',r)
 def test_main_fixed_paths_and_bounded_stdout(self):
  u=type('U',(),{'nodename':m.HOST})()
  with patch.object(m.os,'uname',return_value=u),patch.object(m,'observe',return_value={'existence':'UNKNOWN'}) as read,patch('builtins.print') as out:
   self.assertEqual(m.main(),0);self.assertEqual([c.args[0] for c in read.call_args_list],list(m.TARGETS));self.assertLess(len(out.call_args.args[0]),m.MAX_OUTPUT)
  with patch.object(m.os,'uname',return_value=u),patch.object(m,'observe',return_value={'excess':'x'*m.MAX_OUTPUT}),patch('builtins.print') as out:
   self.assertEqual(m.main(),2);self.assertEqual(json.loads(out.call_args.args[0])['reason'],'QUERY_INCOMPLETE')
 def test_no_input_mutations(self):
  raw=self.p.read_bytes();s=self.p.stat();self.run_query();a=self.p.stat();self.assertEqual(raw,self.p.read_bytes());self.assertEqual(m.ident(s),m.ident(a))
 def test_secret_unknown_fields_never_printed(self):
  v=trust();v['token']='SECRET_CANARY_TOKEN';v['anchors']['other']={'private_key':'SECRET_PRIVATE_KEY'};self.p.write_text(json.dumps(v));r=self.run_query();self.assertEqual(r['fields'],'UNKNOWN');self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('selected',r)
 def test_other_anchors_and_reviewer_secrets_not_selected(self):
  v=trust();v['anchors']['other']={'secret':'SECRET'};v['reviewers']['other']={'token':'SECRET'};r=m.selected(json.dumps(v).encode(),True,150);self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('other',json.dumps(r))
 def test_policy_outputs_only_public_hashes_and_login_digest(self):
  p=policy();r=m.selected(json.dumps(p).encode(),False,150);self.assertEqual(r['reviewer_logins_count'],1);self.assertNotIn('reviewer-two',json.dumps(r));self.assertEqual(r['schema'],1)
 def test_strict_schema_types_and_nonsecret_identifiers(self):
  for value in (True,2,'1'):
   v=trust();v['schema']=value
   with self.assertRaises(m.Unknown):m.selected(json.dumps(v).encode(),True,150)
  for key,value in [('source_writer_principal','secret\nwith lines'),('revoked_review_ids',[True])]:
   v=trust();v[key]=value
   with self.assertRaises(m.Unknown):m.selected(json.dumps(v).encode(),True,150)
 def test_missing_anchor_no_fake_absence_or_enrollment(self):
  v=trust();v['anchors']={};r=m.selected(json.dumps(v).encode(),True,150);self.assertEqual(r['target_anchor'],'NOT_PRESENT_IN_OBSERVED_DOCUMENT');self.assertNotIn('reviewer_principal',r)
 def test_revocation_expiry_mismatch_never_independence_pass(self):
  v=trust();v['revoked_review_ids']=[int(m.ANCHOR)];v['anchors'][m.ANCHOR]['body_sha256']=H;r=m.selected(json.dumps(v).encode(),True,250);self.assertTrue(r['target_review_revoked']);self.assertEqual(r['time_window'],'EXPIRED');self.assertFalse(r['expected_content_binding']);self.assertEqual(r['custody_provenance'],'UNKNOWN_NOT_ATTESTED')
 def test_depth_duplicate_number_and_field_bounds(self):
  for raw in (b'{"schema":1,"schema":1}',b'['*13+b'0'+b']'*13,b'{"x":1e300}',b'{"x":'+b'1'*21+b'}',json.dumps(dict((str(i),0) for i in range(1001))).encode()):
   with self.assertRaises(m.Unknown):m.bounded_json(raw)
 def test_oversized_input_no_read(self):
  with self.p.open('wb') as f:f.truncate(m.MAX_BYTES+1)
  with patch.object(m.os,'read',side_effect=AssertionError('must not read')):r=self.run_query()
  self.assertEqual(r['reason'],'FILE_BOUND')
 def test_io_failure_and_timeout_not_absent(self):
  with patch.object(m.os,'read',side_effect=OSError(errno.EIO,'SECRET')):r=self.run_query()
  self.assertEqual(r['observation'],'UNKNOWN');self.assertNotIn('SECRET',json.dumps(r))
  with patch.object(m.os,'read',side_effect=m.Unknown('TIME_BOUND')):
   with self.assertRaisesRegex(m.Unknown,'TIME_BOUND'):self.run_query()
 def test_json_and_selection_timeout_escape_observe(self):
  for target in ('bounded_json','selected'):
   with self.subTest(stage=target),patch.object(m,target,side_effect=m.Unknown('TIME_BOUND')):
    with self.assertRaisesRegex(m.Unknown,'TIME_BOUND'):self.run_query()
 def test_semantic_unknown_stays_a_field_observation(self):
  with patch.object(m,'selected',side_effect=m.Unknown('TRUST_SCHEMA')):r=self.run_query()
  self.assertEqual(r['fields'],'UNKNOWN');self.assertEqual(r['field_reason'],'TRUST_SCHEMA');self.assertEqual(r['observation'],'STABLE_BYTES_OBSERVED')
 def test_actual_sigalrm_in_json_and_selection_cli_is_global(self):
  # A separate Python process runs the real main and observe on synthetic files.
  # Fire the actual installed SIGALRM handler at each affected stage; no sleeps.
  second=self.root/'policy.json';second.write_text(json.dumps(policy()));second.chmod(0o600)
  program=r"""
import importlib.util,os,signal,sys
spec=importlib.util.spec_from_file_location('fixture_query',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.HOST=os.uname().nodename.split('.')[0]
m.TARGETS=(sys.argv[2],sys.argv[3])
original_observe=m.observe;calls=[]
def observe(path,*args,**kwargs):
 calls.append(path);return original_observe(path,*args,**kwargs)
m.observe=observe
original=getattr(m,sys.argv[4])
def interrupted(*args,**kwargs):
 os.kill(os.getpid(),signal.SIGALRM)
 return original(*args,**kwargs)
setattr(m,sys.argv[4],interrupted)
code=m.main()
assert calls==[sys.argv[2]],'SECOND_TARGET_MUST_NOT_BE_READ'
assert code==2,'GLOBAL_TIMEOUT_MUST_FAIL'
sys.exit(code)
"""
  for stage in ('bounded_json','selected'):
   with self.subTest(stage=stage):
    r=subprocess.run([sys.executable,'-I','-B','-S','-c',program,str(SOURCE),str(self.p),str(second),stage],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
    self.assertEqual(r.returncode,2,r.stderr.decode());self.assertEqual(r.stderr,b'');self.assertEqual(r.stdout,b'{"state":"UNKNOWN","reason":"QUERY_INCOMPLETE"}\n')
 def test_python36_syntax_and_wrong_host_no_access(self):
  ast.parse(SOURCE.read_text(),feature_version=(3,6))
  with patch.object(m.os,'uname',return_value=type('U',(),{'nodename':'wrong'})()),patch.object(m.os,'open',side_effect=AssertionError('no access')):
   with patch('builtins.print') as out:self.assertEqual(m.main(),2)
  self.assertNotIn('SECRET',str(out.call_args))
 def test_complete_candidate_embeds_exact_source(self):
  p=SOURCE.parents[1]/'docs/development/showcase-readonly/CANDIDATE.sh';c=p.read_text();self.assertEqual(c.split("<<'SHOWCASE_READONLY'\n",1)[1].rsplit('SHOWCASE_READONLY\n',1)[0],SOURCE.read_text())
if __name__=='__main__':unittest.main()
