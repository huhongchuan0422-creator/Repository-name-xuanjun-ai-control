import os,pathlib,sys,subprocess,unittest,stat
from unittest import mock
sys.path.insert(0,str(pathlib.Path(os.environ['P2_NEW_ROOT'])/'stage1'))
import epoch3_service_containment as subject

class Tests(unittest.TestCase):
 def setUp(self):
  self.scanner=mock.Mock();self.scanner.bounded_file_inventory.return_value={}
  self.run=mock.Mock(return_value=subprocess.CompletedProcess([],0,b'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\nControlGroup=\n',b''))
  info=mock.Mock(st_mode=stat.S_IFDIR|0o755,st_uid=0,st_dev=1,st_ino=2)
  self.patches=[mock.patch.object(subject.os,'open',return_value=99),mock.patch.object(subject.os,'close'),
   mock.patch.object(subject.os,'fstat',return_value=info),mock.patch.object(subject.os,'stat',return_value=info),
   mock.patch.object(subject.os,'listdir',return_value=[]),mock.patch.object(subject.os.path,'realpath',side_effect=lambda p:p)]
  for p in self.patches:p.start()
  self.obj=subject.ServiceContainment(self.scanner,self.run);self.obj.authority=lambda:None
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def test_controller_missing_rejected(self):
  with mock.patch.object(subject.os,'open',side_effect=FileNotFoundError()):
   with self.assertRaises(ValueError):self.obj.verify_all()
 def test_all_stops_attempted_after_timeout(self):
  self.run.side_effect=[subprocess.TimeoutExpired('stop',45)]+[subprocess.CompletedProcess([],0)]*(len(subject.UNITS)-1)
  r=self.obj.stop_all();self.assertEqual(len(r['stop_results']),len(subject.UNITS))
  self.assertEqual(r['stop_results'][0]['error_type'],'TimeoutExpired');self.assertFalse(r['verified_stopped'])
 def test_nonzero_stop_not_hidden(self):
  self.run.return_value=subprocess.CompletedProcess([],1)
  r=self.obj.stop_all();self.assertTrue(all(v['returncode']==1 for v in r['stop_results']))
 def test_verify_every_unit(self):
  self.assertTrue(self.obj.verify_all()['verified_stopped']);self.assertEqual(self.scanner.bounded_file_inventory.call_count,len(subject.UNITS))
 def test_cgroup_permission_error_rejected(self):
  self.scanner.bounded_file_inventory.side_effect=PermissionError('denied')
  with self.assertRaisesRegex(ValueError,'UNVERIFIED'):self.obj.verify_all()
  self.assertEqual(self.scanner.bounded_file_inventory.call_count,len(subject.UNITS))
 def test_running_pid_rejected(self):
  self.run.return_value.stdout=b'ActiveState=inactive\nMainPID=42\nControlPID=0\n'
  with self.assertRaises(ValueError):self.obj.verify_all()
 def test_unexpected_cgroup_rejected(self):
  self.run.return_value.stdout=b'ActiveState=inactive\nMainPID=0\nControlPID=0\nControlGroup=/other\n'
  with self.assertRaises(ValueError):self.obj.verify_all()
 def test_not_yet_installed_unit_explicit_absence(self):
  self.run.return_value=subprocess.CompletedProcess([],1,b'LoadState=not-found\nActiveState=inactive\nSubState=dead\n',b'')
  self.assertTrue(self.obj.verify_all()['verified_stopped'])
 def test_missing_unit_with_pid_rejected(self):
  self.run.return_value=subprocess.CompletedProcess([],1,b'LoadState=not-found\nActiveState=inactive\nSubState=dead\nMainPID=33\n',b'')
  with self.assertRaises(ValueError):self.obj.verify_all()
 def test_query_nonzero_rejected(self):
  self.run.return_value.returncode=1
  with self.assertRaises(ValueError):self.obj.verify_all()
 def test_duplicate_states_rejected(self):
  self.run.return_value.stdout+=b'MainPID=0\n'
  with self.assertRaises(ValueError):self.obj.verify_all()
 def test_forbidden_unit_never_queried(self):
  with self.assertRaises(ValueError):self.obj.observe_one('sshd.service')
  self.run.assert_not_called()
 def test_state_change_rejected(self):
  first=self.run.return_value
  second=subprocess.CompletedProcess([],0,first.stdout.replace(b'SubState=dead',b'SubState=failed'),b'')
  self.run.side_effect=[first,second]
  with self.assertRaisesRegex(ValueError,'STATE_RACE'):self.obj.observe_one(subject.UNITS[0])
if __name__=='__main__':unittest.main()
