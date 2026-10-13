import json,os,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'))
import p2_rpm_prerequisites as m
class Rpm(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.root.chmod(0o700);self.obj=m.RpmPrerequisites(str(self.root));self.installed={};self.effects=[];self.active=False;self.modified=False;self.partial=False;self.bad_sig=False
  self.rows=[{'name':n,'candidate':[n,'0','1','1','noarch'],'before':None,'state':'NEW_PACKAGE','path':m.CACHE+'/'+n+'.rpm','sha256':'a'*64} for n in sorted(m.NAMES)]
  self.source=self.root/'source.json';self.source.write_text(json.dumps({'schema':1,'packages':self.rows}));self.source.chmod(0o600)
  self.ref={'path':'/var/lib/xuanjun-p2-preparation/synthetic/baseline.json','sha256':m.hash_bytes(self.source.read_bytes())}
  self.prereq={'users':{'nginx':{'uid':1008,'gid':1008,'home':'/var/lib/xuanjun-development/nginx-home','groups':[]}}}
  reader=m.private_read
  self.patches=[patch.object(m,'private_read',side_effect=lambda p:self.source.read_bytes() if p==self.ref['path'] else reader(p)),patch.object(m,'package_bytes',return_value=None),patch.object(m,'command',side_effect=self.command),patch.object(m.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1008,pw_gid=1008,pw_dir='/var/lib/xuanjun-development/nginx-home',pw_shell='/sbin/nologin')),patch.object(m.grp,'getgrnam',return_value=types.SimpleNamespace(gr_gid=1008,gr_mem=[])),patch.object(m.os,'getgrouplist',return_value=[1008])]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def result(self,text='',code=0):return types.SimpleNamespace(returncode=code,stdout=text.encode(),stderr=b'')
 def command(self,args,check=True):
  if args[0]=='/usr/bin/systemctl':
   if 'UnitFileState' in args[-1]:return self.result('ActiveState='+('active' if self.active else 'inactive')+'\nSubState='+('running' if self.active else 'dead')+'\nMainPID='+('7' if self.active else '0')+'\nUnitFileState=masked\nControlGroup=\n')
   return self.result('ActiveState=inactive\nMainPID=0\n')
  if '--checksig' in args:return self.result('NOKEY' if self.bad_sig else 'OK')
  if '-qp' in args:
   if 'FILENAMES' in args[-2]:return self.result()
   row=next(r for r in self.rows if r['path']==args[-1]);return self.result(' '.join(row['candidate']))
  if '-q' in args:
   row=self.installed.get(args[-1]);return self.result(' '.join(row),0) if row else self.result('',1)
  if '-V' in args:return self.result('S.5....T. synthetic' if self.modified else '',1 if self.modified else 0)
  if '--test' in args:return self.result()
  if '-U' in args:
   self.effects.append(('install',args))
   for row in self.rows[:3] if self.partial else self.rows:self.installed[row['name']]=row['candidate'][:]
   if self.partial:raise ValueError('synthetic partial install')
   return self.result()
  if '-e' in args:
   self.effects.append(('erase',args))
   for name in args[4:]:self.installed.pop(name,None)
   return self.result()
  raise AssertionError(args)
 def apply(self):self.obj.apply(self.ref,self.prereq)
 def test_install_erase_repeated_rollback(self):
  self.apply();self.assertEqual(len(self.installed),16);self.obj.rollback();self.obj.rollback();self.assertEqual(self.installed,{})
  self.assertTrue(all('--noscripts' in args and '--notriggers' in args and '--nodeps' not in args for op,args in self.effects))
 def test_partial_install_intent_can_restore_only_known_prefix(self):
  self.partial=True
  with self.assertRaisesRegex(ValueError,'partial'):self.apply()
  self.assertEqual(len(self.installed),3);self.obj.rollback();self.assertEqual(self.installed,{})
 def test_live_old_executor_blocks_install_effect(self):
  self.active=True
  with self.assertRaisesRegex(ValueError,'OLD_EXECUTOR_NOT_QUIESCED'):self.apply()
  self.assertEqual(self.effects,[]);self.assertFalse(os.path.exists(self.obj.path))
 def test_modified_payload_prevents_all_erase(self):
  self.apply();self.modified=True
  with self.assertRaisesRegex(ValueError,'PAYLOAD_CHANGED'):self.obj.rollback()
  self.assertEqual(len(self.installed),16);self.assertEqual(len(self.effects),1)
 def test_unknown_version_prevents_all_erase(self):
  self.apply();self.installed[self.rows[0]['name']][-2]='foreign'
  with self.assertRaisesRegex(ValueError,'VERSION_CHANGED'):self.obj.rollback()
  self.assertEqual(len(self.effects),1)
 def test_missing_acknowledged_package_holds(self):
  self.apply();self.installed.pop(self.rows[0]['name'])
  with self.assertRaisesRegex(ValueError,'INSTALLED_PACKAGE_MISSING'):self.obj.rollback()
  self.assertEqual(len(self.effects),1)
 def test_duplicate_install_never_overwrites_journal(self):
  self.apply();before=pathlib.Path(self.obj.path).read_bytes()
  with self.assertRaisesRegex(ValueError,'EXISTING_TRANSACTION'):self.apply()
  self.assertEqual(pathlib.Path(self.obj.path).read_bytes(),before);self.assertEqual(len(self.effects),1)
 def test_changed_baseline_blocks_all_erase(self):
  self.apply();self.source.write_text('{}')
  with self.assertRaisesRegex(ValueError,'BASELINE_CHANGED'):self.obj.rollback()
  self.assertEqual(len(self.effects),1)
 def test_missing_nginx_identity_blocks_install(self):
  self.prereq['users'].clear()
  with self.assertRaisesRegex(ValueError,'DEDICATED_NGINX_IDENTITY'):self.apply()
  self.assertEqual(self.effects,[])
 def test_database_supplementary_group_blocks_nginx_install(self):
  with patch.object(m.os,'getgrouplist',return_value=[1008,1006]):
   with self.assertRaisesRegex(ValueError,'NGINX_IDENTITY_CHANGED'):self.apply()
  self.assertEqual(self.effects,[])
 def test_unsigned_candidate_blocks_install(self):
  self.bad_sig=True
  with self.assertRaisesRegex(ValueError,'RPM_SIGNATURE'):self.apply()
  self.assertEqual(self.effects,[])
 def test_reinstall_after_rollback_never_removed(self):
  self.apply();self.obj.rollback();self.installed[self.rows[0]['name']]=self.rows[0]['candidate'][:]
  with self.assertRaisesRegex(ValueError,'VERSION_CHANGED'):self.obj.rollback()
  self.assertEqual(len(self.effects),2)
if __name__=='__main__':unittest.main()
