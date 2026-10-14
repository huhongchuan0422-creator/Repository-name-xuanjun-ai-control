import os,sys,pathlib,tempfile,json,subprocess,unittest
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
   process=Mock(pid=123,returncode=-9)
   process.communicate.side_effect=[subprocess.TimeoutExpired('certbot',240),(b'partial',b'delay')]
   with patch.object(tls,'ROOT',root),patch.object(tls.subprocess,'Popen',return_value=process),patch.object(tls.os,'killpg',side_effect=kill_error) as kill:
    with self.assertRaisesRegex(ValueError,'TLS_COMMAND_TIMEOUT_GROUP_KILLED'):tls.command(['certbot'],timeout=240)
   kill.assert_called_once_with(123,tls.signal.SIGKILL)
   self.assertEqual(process.communicate.call_args_list[0][1],{'timeout':240})
   value=json.loads(pathlib.Path(root+'/logs/command-failure.json').read_text())
   self.assertEqual(value['reason'],'TIMEOUT_GROUP_KILLED_OR_EXITED')
   self.assertEqual(value['timeout_seconds'],240)
   self.assertEqual(value['stderr'],'delay')
   self.assertEqual(os.stat(root+'/logs/command-failure.json').st_mode&0o777,0o600)
 def test_timeout_is_persisted(self):self.timeout_case()
 def test_exit_race_still_persists_failure(self):self.timeout_case(ProcessLookupError())

if __name__=='__main__':unittest.main(verbosity=2)
