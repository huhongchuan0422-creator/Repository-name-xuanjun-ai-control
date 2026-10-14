import os,sys,pathlib,tempfile,json,subprocess,unittest,time
from unittest.mock import Mock,patch
sys.path.insert(0,str(pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'))
import p2_tls_lifecycle as tls

class DeadlineTests(unittest.TestCase):
 def test_both_renewal_modes_disable_internal_sleep(self):
  for dry in (False,True):
   args=tls.renewal_args(dry_run=dry)
   self.assertEqual(args.count('--no-random-sleep-on-renew'),1)
   self.assertEqual('--dry-run' in args,dry)
   self.assertEqual(args[:3],['renew','--cert-name',tls.DOMAIN])
   self.assertIn('--no-directory-hooks',args)
 def test_calls_use_common_renewal_policy(self):
  import ast
  tree=ast.parse(pathlib.Path(tls.__file__).read_text())
  funcs={n.name:n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
  for name in ('apply','renew'):
   calls=[n for n in ast.walk(funcs[name]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='renewal_args']
   self.assertEqual(len(calls),1)
  command_calls=[n for n in ast.walk(funcs['apply']) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='command']
  self.assertTrue(any(any(k.arg=='timeout' and getattr(k.value,'n',None)==240 for k in c.keywords) for c in command_calls))
 def timeout_case(self,kill_error=None):
  with tempfile.TemporaryDirectory() as root:
   os.chmod(root,0o700);os.mkdir(root+'/logs',0o700)
   process=Mock(pid=123,returncode=-9);process.poll.return_value=-9
   process.communicate.side_effect=[subprocess.TimeoutExpired('certbot',240),(b'partial',b'delay')]
   with patch.object(tls,'ROOT',root),patch.object(tls.subprocess,'Popen',return_value=process),patch.object(tls.os,'killpg',side_effect=kill_error) as kill:
    with self.assertRaisesRegex(ValueError,'TLS_COMMAND_TIMEOUT_HOLD'):tls.command(['certbot'],timeout=240)
   kill.assert_called_once_with(123,tls.signal.SIGKILL)
   self.assertEqual(process.communicate.call_args_list[0][1],{'timeout':240})
   value=json.loads(pathlib.Path(root+'/logs/command-failure.json').read_text())
   self.assertEqual(value['reason'],'TIMEOUT_BOUNDED_CLEANUP')
   self.assertEqual(value['timeout_seconds'],240)
   self.assertEqual(value['stderr'],'delay')
   self.assertGreater(process.communicate.call_args_list[1][1]['timeout'],0)
   self.assertLessEqual(process.communicate.call_args_list[1][1]['timeout'],tls.COMMAND_CLEANUP_SECONDS)
   self.assertEqual(value['cleanup']['descendants'],'UNKNOWN')
   self.assertEqual(os.stat(root+'/logs/command-failure.json').st_mode&0o777,0o600)
 def test_timeout_is_persisted(self):self.timeout_case()
 def test_exit_race_still_persists_failure(self):self.timeout_case(ProcessLookupError())

class CleanupBoundaryTests(unittest.TestCase):
 def test_no_unbounded_communicate_or_wait(self):
  import ast
  tree=ast.parse(pathlib.Path(tls.__file__).read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('communicate','wait')]
  self.assertTrue(calls)
  self.assertTrue(all(any(k.arg=='timeout' for k in c.keywords) for c in calls))
 def test_second_timeout_retains_partial_and_closes_pipes(self):
  process=Mock(pid=123,returncode=-9);process.poll.return_value=-9
  error=subprocess.TimeoutExpired('x',.1,output=b'prefix',stderr=b'error')
  process.communicate.side_effect=error
  with patch.object(tls.os,'killpg'):
   out,err,e=tls.bounded_command_cleanup(process,error)
  self.assertEqual((out,err),(b'prefix',b'error'))
  self.assertEqual(e['output'],'INCOMPLETE');self.assertEqual(e['descendants'],'UNKNOWN')
  process.stdout.close.assert_called_once();process.stderr.close.assert_called_once()
 def test_diagnostic_prefix_is_bounded(self):
  process=Mock(pid=123,returncode=-9);process.poll.return_value=-9
  error=subprocess.TimeoutExpired('x',.1,output=b'x'*2000000,stderr=b'y'*2000000)
  process.communicate.side_effect=error
  with patch.object(tls.os,'killpg'):out,err,e=tls.bounded_command_cleanup(process,error)
  self.assertEqual(len(out),1048576);self.assertEqual(len(err),1048576);self.assertTrue(e['captured_output_truncated'])
 def test_signal_permission_error_keeps_bounded_drain_and_unknown_descendants(self):
  process=Mock(pid=123,returncode=None);process.poll.return_value=None
  error=subprocess.TimeoutExpired('x',.1)
  process.communicate.side_effect=error;process.wait.side_effect=error
  with patch.object(tls.os,'killpg',side_effect=PermissionError('denied')):
   out,err,e=tls.bounded_command_cleanup(process,error)
  self.assertEqual(e['group_signal'],'FAILED');self.assertEqual(e['direct_process'],'UNKNOWN')
  self.assertIn('timeout',process.wait.call_args[1]);self.assertGreater(process.wait.call_args[1]['timeout'],0)
 def test_drain_interrupted_still_closes_and_reaps(self):
  process=Mock(pid=123,returncode=-9);process.poll.return_value=-9
  process.communicate.side_effect=KeyboardInterrupt()
  with patch.object(tls.os,'killpg'):out,err,e=tls.bounded_command_cleanup(process,KeyboardInterrupt())
  self.assertEqual(e['drain_error_type'],'KeyboardInterrupt');process.stdout.close.assert_called_once();process.stderr.close.assert_called_once()
 def test_expired_cleanup_budget_never_waits_again(self):
  process=Mock(pid=123,returncode=None);process.poll.return_value=None
  with patch.object(tls.os,'killpg'),patch.object(tls.time,'monotonic',side_effect=[0,3,3]):
   out,err,e=tls.bounded_command_cleanup(process,subprocess.TimeoutExpired('x',.1))
  process.communicate.assert_not_called();process.wait.assert_not_called();self.assertEqual(e['direct_process'],'UNKNOWN')
 def test_first_pipe_close_error_does_not_skip_second_or_reap(self):
  process=Mock(pid=123,returncode=-9);process.poll.return_value=-9
  process.communicate.side_effect=subprocess.TimeoutExpired('x',.1)
  process.stdout.close.side_effect=OSError('close')
  with patch.object(tls.os,'killpg'):out,err,e=tls.bounded_command_cleanup(process,subprocess.TimeoutExpired('x',.1))
  process.stderr.close.assert_called_once();process.poll.assert_called_once();self.assertEqual(e['stdout_close_error_type'],'OSError')
 def real_timeout(self,escaped=False,diagnostic_failure=False):
  with tempfile.TemporaryDirectory() as root:
   os.chmod(root,0o700);os.mkdir(root+'/logs',0o700)
   if escaped:
    code="import os,time\np=os.fork()\nif p==0:\n os.setsid()\n os.write(1,b'escaped pipe holder\\n')\n time.sleep(1.8)\n os._exit(0)\ntime.sleep(5)"
   else:code="import os,time;os.write(2,b'partial diagnostic');time.sleep(5)"
   start=time.monotonic()
   with patch.object(tls,'ROOT',root),patch.object(tls,'COMMAND_CLEANUP_SECONDS',.15):
    if diagnostic_failure:
     with patch.object(tls,'command_failure',side_effect=PermissionError('diagnostic denied')):
      with self.assertRaises(PermissionError):tls.command([sys.executable,'-I','-B','-c',code],timeout=.15)
    else:
     with self.assertRaisesRegex(ValueError,'TLS_COMMAND_TIMEOUT_HOLD'):tls.command([sys.executable,'-I','-B','-c',code],timeout=.15)
   elapsed=time.monotonic()-start
   self.assertLess(elapsed,1.2,'cleanup exceeded explicit .15s budget plus scheduling tolerance')
   if not diagnostic_failure:
    value=json.loads(pathlib.Path(root+'/logs/command-failure.json').read_text())
    self.assertEqual(value['cleanup']['descendants'],'UNKNOWN')
    self.assertEqual(value['cleanup']['output'],'INCOMPLETE' if escaped else 'COMPLETE')
    if escaped:self.assertIn('escaped pipe holder',value['stdout'])
   print('REAL_TLS_DEADLINE_PROBE escaped=%s diagnostic_failure=%s elapsed=%.3f deadline=.15 cleanup=.15' % (escaped,diagnostic_failure,elapsed))
 def test_real_escaped_pipe_holder_returns_before_descendant_exit(self):self.real_timeout(escaped=True)
 def test_real_normal_process_timeout_returns(self):self.real_timeout()
 def test_real_diagnostic_write_failure_does_not_extend_wait(self):self.real_timeout(escaped=True,diagnostic_failure=True)

if __name__=='__main__':unittest.main(verbosity=2)

