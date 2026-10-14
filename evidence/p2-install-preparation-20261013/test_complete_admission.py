import hashlib,importlib.util,json,pathlib,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('executor',str(ROOT/'complete_install_executor.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AdmissionTests(unittest.TestCase):
 def value(self):return {'schema':1,'reviewer':'CHATGPT_NATIVE_TASK5','decision':'APPROVED_FOR_PROTECTED_INSTALL_AND_FENCED_ROLLBACK','release_granted':True,'owner_install_scope_authorized':True,'accept_acme_terms':True}
 def fetch(self,value,mutator=lambda c:None):
  body=m.MARKER+json.dumps(value);c={'id':123,'user':{'login':'huhongchuan0422-creator','id':332398908},'body':body};mutator(c)
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return json.dumps(c).encode()
  with patch.object(m.urllib.request,'build_opener') as opener:
   opener.return_value.open.return_value=Response();return m.fetch_review(123,hashlib.sha256(body.encode()).hexdigest())
 def test_actual_matching_approval_accepted(self):self.assertEqual(self.fetch(self.value())['release_granted'],True)
 def test_id_author_and_body_drift_rejected(self):
  for change in (lambda c:c.update(id=124),lambda c:c['user'].update(login='other'),lambda c:c.update(body=c['body']+'changed')):
   with self.assertRaises(ValueError):self.fetch(self.value(),change)
 def test_limited_pass_is_not_install_authorization(self):
  for key,val in [('decision','PASS_WITH_SCOPE_LIMITS'),('release_granted',False),('owner_install_scope_authorized',False),('accept_acme_terms',False),('reviewer','WORK_NATIVE')]:
   v=self.value();v[key]=val
   with self.assertRaises(ValueError):self.fetch(v)
 def test_complete_source_plan_and_code_bindings(self):
  g={'source_commit':'a'*40,'source_tree':'b'*40,'artifact_id':100,'manifest_sha256':'c'*64}
  v={'source':'a'*40,'tree':'b'*40,'artifact':100,'manifest_sha256':'c'*64,'plan_sha256':'d'*64,'outer_gate_sha256':'e'*64,'executor_sha256':'f'*64,'auditor_sha256':'1'*64,'transaction_id':m.TX}
  m.bind_review(v,g,'d'*64,'e'*64,'f'*64,'1'*64)
  for k in v:
   altered=dict(v);altered[k]='drift'
   with self.assertRaises(ValueError):m.bind_review(altered,g,'d'*64,'e'*64,'f'*64,'1'*64)
 def test_auditor_and_preparer_share_source_tree_and_manifest(self):
  import ast
  prepare=ast.parse((ROOT/'prepare_complete_install_candidate.py').read_text())
  constants={n.targets[0].id:n.value.s for n in prepare.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and isinstance(n.value,ast.Str)}
  audit=ast.parse((ROOT/'consolidated_readiness.py').read_text())
  comparisons={}
  for node in ast.walk(audit):
   if isinstance(node,ast.Compare) and len(node.ops)==1 and isinstance(node.ops[0],ast.Eq) and isinstance(node.comparators[0],ast.Str):
    expression=ast.dump(node.left)
    for key in ('source_commit','source_tree','manifest_sha256'):
     if key in expression and 'artifact' in expression:comparisons[key]=node.comparators[0].s
  self.assertEqual(comparisons,{'source_commit':constants['SOURCE'],'source_tree':constants['TREE'],'manifest_sha256':constants['MANIFEST']})
 def test_caller_and_root_loader_share_current_code_hash(self):
  expected=hashlib.sha256((ROOT/'complete_install_executor.py').read_bytes()).hexdigest()
  s=(ROOT/'execute_complete_review_bound.py').read_text();self.assertEqual(s.count(expected),2)
if __name__=='__main__':unittest.main(verbosity=2)
