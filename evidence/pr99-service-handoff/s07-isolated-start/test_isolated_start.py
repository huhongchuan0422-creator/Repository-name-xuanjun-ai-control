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
