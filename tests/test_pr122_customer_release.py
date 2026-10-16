import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_customer_release as r
from scripts.pr122_customer_core import canonical,digest,Denied

class ReleaseTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);b=Path(self.t.name);self.b=b
  for name,relative in [('CODE','code'),('CONFIG','config'),('STATE','transactions'),('DATA','data'),('HTTPS','nginx/site.conf'),('SNIPPET','nginx/customer/locations.conf'),('CURRENT','www/current'),('UNIT','units'),('LOCK','lock')]:
   p=b/relative;p.parent.mkdir(exist_ok=True,parents=True);pather=patch.object(r,name,p);pather.start();self.addCleanup(pather.stop)
  r.SNIPPET.parent.rmdir();r.CONFIG.mkdir();r.UNIT.mkdir();r.CURRENT.symlink_to(b/'old-release');r.HTTPS.write_bytes(b'server { '+r.ANCHOR+b' }');r.LOCK.touch()
  for f in ('config.json','runtime.json','TARGET_ACCEPTANCE.json'):(r.CONFIG/f).write_bytes(b'{}')
  self.source=b/'source';self.source.mkdir();files={
   'boot.py':b'# reviewed boot',
   'deploy/pr122-customer-center/locations.conf':b'location ^~ /customer/center/ {}',
   'deploy/pr122-customer-center/ui/index.html':b'fixture html',
   **{'deploy/pr122-customer-center/'+u:b'[Service]\n' for u in r.UNITS}}
  m={'source_commit':'a'*40,'files':[{'path':p,'size':len(v),'sha256':digest(v)} for p,v in files.items()]};raw=canonical(m)
  for p,v in files.items():q=self.source/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(v)
  (self.source/'CUSTOMER_MANIFEST.json').write_bytes(raw)
  self.base={'state':'READONLY_PLAN','transaction':r.TXN,'manifest_sha256':digest(raw),'source_commit':'a'*40,'main_current':str(self.b/'old-release'),'previous_https_sha256':digest(r.HTTPS.read_bytes()),'nginx':{'files':{str(r.HTTPS):digest(r.HTTPS.read_bytes())},'master':'fixture-master'},'account_uid':12345,'account_gid':12345,'config_sha256':digest(b'{}'),'runtime_config_sha256':digest(b'{}'),'target_acceptance_sha256':digest(b'{}'),'production_changes':0}
  self.approval={'decision':'INSTALL_APPROVED','transaction':r.TXN,'plan_sha256':digest(canonical(self.base)),'manifest_sha256':digest(raw),'source_commit':'a'*40,'max_executions':1,'rollback_approved':True,'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+600,'review_comment_id':5,'ci_run_id':6}
  self.calls=[];self.fail=None
 def fake_run(self,args):
  self.calls.append(args)
  if self.fail and self.fail(args):raise Denied('SIMULATED_INTERRUPTION')
  if args[0].endswith('curl'):return b'fixture html'
  return b''
 def inventory(self):
  f={str(r.HTTPS):digest(r.HTTPS.read_bytes())}
  if r.INCLUDE in r.HTTPS.read_bytes():f[str(r.SNIPPET)]=digest(r.SNIPPET.read_bytes())
  return {'files':f,'master':'fixture-master'}
 def patches(self):
  from contextlib import ExitStack
  stack=ExitStack()
  for name,val in [('plan',lambda f:dict(self.base)),('gate',lambda *a:self.approval),('run',self.fake_run),('inventory',self.inventory),('runtime_check',lambda uid:None)]:stack.enter_context(patch.object(r,name,val))
  stack.enter_context(patch.object(r.os,'uname',return_value=type('U',(),{'nodename':'iZvt5t8tlrm8oiZ'})()))
  stack.enter_context(patch.object(r.os,'geteuid',return_value=0));return stack
 def test_actual_filesystem_install_and_owned_rollback(self):
  old=r.HTTPS.read_bytes()
  with self.patches():
   out=r.apply(self.source,4);self.assertEqual(out['state'],'HTTPS_SMOKE_PASS_AWAIT_14_REAL_ACCEPTANCE');self.assertIn(r.INCLUDE,r.HTTPS.read_bytes());self.assertEqual(os.readlink(r.CURRENT),self.base['main_current'])
   out=r.rollback();self.assertEqual(out['state'],'ROLLED_BACK');self.assertEqual(r.HTTPS.read_bytes(),old);self.assertTrue(r.CODE.exists());self.assertTrue(out['private_data_preserved'])
 def test_source_drift_rejected_before_any_install(self):
  (self.source/'boot.py').write_bytes(b'changed')
  with self.patches(),self.assertRaises(Denied):r.apply(self.source,4)
  self.assertFalse(r.CODE.exists())
 def test_interrupted_phases_preserve_hold_and_restore(self):
  for marker in ('systemd-analyze','start','nginx','curl'):
   with self.subTest(stage=marker):
    # separate transaction files for each disposable case, no production retry.
    with tempfile.TemporaryDirectory() as td:
     old_state=r.STATE;old_code=r.CODE;old_snippet=r.SNIPPET;old_unit=r.UNIT
     with patch.object(r,'STATE',Path(td)/'state'),patch.object(r,'CODE',Path(td)/'code'),patch.object(r,'SNIPPET',Path(td)/'snippet/locations.conf'),patch.object(r,'UNIT',Path(td)/'units'):
      r.UNIT.mkdir();old=r.HTTPS.read_bytes();self.fail=lambda args: marker in args[0] or marker in args[1:]
      with self.patches():
       with self.assertRaises(Denied):r.apply(self.source,4)
       data=json.loads((r.STATE/r.TXN/'receipt.json').read_bytes());self.assertEqual(data['state'],'HOLD_PARTIAL');self.fail=None;r.rollback();self.assertEqual(r.HTTPS.read_bytes(),old)
 def test_unknown_and_foreign_config_prevent_rollback(self):
  with self.patches():
   r.apply(self.source,4);r.HTTPS.write_bytes(b'foreign config')
   with self.assertRaises(Denied):r.rollback()
 def test_machine_gate_exact_review_ci_expiry_and_owner(self):
  review={'decision':'AUDIT_PASS','reviewer_role':'INDEPENDENT_AUDITOR','manifest_sha256':self.approval['manifest_sha256'],'source_commit':'a'*40,'ci_run_id':6}
  def fetch(path):
   if path=='actions/runs/6':return {'conclusion':'success','head_sha':'a'*40,'path':'.github/workflows/pr122-customer-center.yml','event':'push'}
   cid=int(path.rsplit('/',1)[1]);return {'id':cid,'user':{'login':r.OWNER},'issue_url':'https://api.github.com/repos/x/y/issues/122','body':('XUANJUN_CUSTOMER_INSTALL\n'+json.dumps(self.approval)) if cid==4 else ('XUANJUN_CUSTOMER_REVIEW\n'+json.dumps(review))}
  self.assertEqual(r.gate(4,self.base,fetch)['ci_run_id'],6);self.approval['expires_unix']=0
  with self.assertRaises(Denied):r.gate(4,self.base,fetch)
  self.approval['expires_unix']=int(time.time())+600;review['manifest_sha256']='f'*64
  with self.assertRaises(Denied):r.gate(4,self.base,fetch)

if __name__=='__main__':unittest.main()
