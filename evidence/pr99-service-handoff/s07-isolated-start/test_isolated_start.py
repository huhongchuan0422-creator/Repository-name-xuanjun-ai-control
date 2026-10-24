import os
from pathlib import Path
import runpy,tempfile,unittest
from unittest.mock import patch
N=runpy.run_path(str(Path(__file__).with_name('isolated_start.py')))
class IsolatedTests(unittest.TestCase):
 def test_exact_module_command(self):
  got=N['launch_command']('/usr/bin/python3 -u -m ai_service.wecom_customer_service --host 0.0.0.0 --port 18780','ai_service/wecom_customer_service.py',18780)
  self.assertEqual(got,['/venv/bin/python','-B','-u','-m','ai_service.wecom_customer_service','--host','127.0.0.1','--port','18780'])
 def test_exact_script_command(self):
  got=N['launch_command']('/usr/bin/python3 scripts/secure_secrets_portal_server.py','scripts/secure_secrets_portal_server.py',18080)
  self.assertEqual(got[-1],'/opt/trading-system/scripts/secure_secrets_portal_server.py')
 def test_observed_portal_serve_and_remote_revalidation(self):
  entry='scripts/secure_secrets_portal_server.py'
  got=N['launch_command']('/usr/bin/python3 /opt/trading-system/'+entry+' serve --host 127.0.0.1 --port 18080',entry,18080)
  self.assertEqual(got,['/venv/bin/python','-B','-u','/opt/trading-system/'+entry,'serve','--host','127.0.0.1','--port','18080'])
  import shlex
  self.assertEqual(N['launch_command']('/usr/bin/python3 '+shlex.join(got[3:]),entry,18080),got)
 def test_subcommand_scope_rejected(self):
  for entry,tail,port in (
   ('scripts/secure_secrets_portal_server.py','reset',18080),
   ('scripts/secure_secrets_portal_server.py','serve serve',18080),
   ('ai_service/wecom_customer_contact_service.py','serve',18781)):
   with self.assertRaises(RuntimeError):
    N['launch_command']('/usr/bin/python3 /opt/trading-system/'+entry+' '+tail,entry,port)
 def test_public_directories_override_private_umask(self):
  import stat
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'root'
   mask=os.umask(0o077)
   try:
    N['public_directory'](root)
    for name in ('etc','dev','venv'):
     N['public_directory'](root/name)
   finally:os.umask(mask)
   for p in (root,root/'etc',root/'dev',root/'venv'):
    self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o755)
   (root/'etc'/'hosts').write_text('127.0.0.1 localhost')
   (root/'etc'/'hosts').chmod(0o444)
 def test_chroot_uid65534_read(self):
  if os.geteuid()!=0:self.skipTest('root required')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'root';N['public_directory'](root)
   for name in ('etc','dev','venv'):N['public_directory'](root/name)
   (root/'etc'/'hosts').write_text('127.0.0.1 localhost');(root/'etc'/'hosts').chmod(0o444)
   import subprocess,sys
   code="import os;os.chroot("+repr(str(root))+");os.chdir('/');os.setgroups([]);os.setgid(65534);os.setuid(65534);assert open('/etc/hosts').read()=='127.0.0.1 localhost';assert os.access('/dev',os.X_OK);assert os.access('/venv',os.X_OK)"
   result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,text=True,timeout=10)
   if result.returncode and 'Operation not permitted' in result.stderr:
    self.skipTest('runtime disallows chroot or uid/gid transition; host validation pending')
   self.assertEqual(result.returncode,0,result.stderr)
 def test_public_directory_rejects_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'real').mkdir();(root/'link').symlink_to(root/'real')
   with self.assertRaisesRegex(RuntimeError,'DIRECTORY_TYPE'):
    N['public_directory'](root/'link')
 def test_shell_and_unknown_entry_rejected(self):
  for cmd in ('/bin/sh -c something','/usr/bin/python3 /tmp/other.py'):
   with self.assertRaises(RuntimeError):N['launch_command'](cmd,'scripts/secure_secrets_portal_server.py',18080)
 def test_worker_external_port_and_storage_options_rejected(self):
  for tail in ('--worker yes','--port 9999','--host 1.2.3.4','--state-root /tmp/other','--host 127.0.0.1 --host 127.0.0.1'):
   with self.assertRaises(RuntimeError):N['launch_command']('/usr/bin/python3 scripts/secure_secrets_portal_server.py '+tail,'scripts/secure_secrets_portal_server.py',18080)
 def test_copy_is_separate_and_referral_has_no_link(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'root';root.mkdir()
   sources={'scripts/a.py':b'print("fixture")'}
   data={'project/database/data/trading.db':b'fixture-db','referral/0.json':b'fixture-private'}
   with patch.object(os,'chown'):
    project=N['copy_project'](root,sources,data)
   self.assertEqual((project/'database/data/trading.db').read_bytes(),b'fixture-db')
   p=root/'home/admin/.openclaw/workspace/xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json'
   self.assertTrue(p.is_file());self.assertFalse(p.parent.is_symlink())
 def test_source_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(RuntimeError,'SOURCE_PATH'):N['copy_project'](Path(d),{'../escape':b'x'},{})
 def test_source_data_collision_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(RuntimeError,'COLLISION'):N['copy_project'](Path(d),{'scripts/a.py':b'old'},{'project/scripts/a.py':b'new'})
 def test_frozen_helper_sha_rejected_before_execution(self):
  with self.assertRaisesRegex(RuntimeError,'HASH_CHANGED'):N['load'](b'raise Exception("must not execute")','0'*64)
if __name__=='__main__':unittest.main()
