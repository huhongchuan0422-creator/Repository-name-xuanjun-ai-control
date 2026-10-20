import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from portal_lifecycle import PortalLifecycle, LifecycleHold, LifecycleUnknown, digest


class Harness(PortalLifecycle):
    def bound(self, request):
        return b'candidate'

    def service(self):
        return {'ActiveState': 'active', 'MainPID': '123', 'DropInPaths': ''}


class Tests(unittest.TestCase):
    def build(self, final=None, business=None, loaded=None, runner=None):
        self.published = []
        def publish(*args, **kwargs):
            self.published.append((args, kwargs))
            return {'original_publisher': True}
        return Harness(lambda request: True, publish,
                       final or (lambda request: {'status': 'HOLD'}),
                       business or (lambda request: {'status': 'HOLD'}),
                       loaded or (lambda request: {'status': 'HOLD'}),
                       runner=runner or (lambda *a, **k: None))

    def test_missing_verifier_rejected(self):
        with self.assertRaisesRegex(LifecycleHold, 'ADAPTERS_REQUIRED'):
            PortalLifecycle(lambda request: True, None, None, None, None)

    def test_wrong_stage_no_command(self):
        actions = []
        worker = self.build(runner=lambda *a, **k: actions.append(a))
        with self.assertRaisesRegex(LifecycleHold, 'EXACT_LIFECYCLE_STAGE'):
            worker.start_owned({'stage': 'inspect_protected'})
        self.assertEqual(actions, [])

    def test_final_sync_unknown_no_start(self):
        actions = []
        worker = self.build(runner=lambda *a, **k: actions.append(a))
        with self.assertRaisesRegex(LifecycleHold, 'FINAL_DATA'):
            worker.start_owned({'stage': 'start_owned'})
        self.assertEqual(actions, [])

    def test_business_hold_no_route_write(self):
        worker = self.build()
        with patch('portal_lifecycle.root_read', return_value=b'original'), patch('portal_lifecycle.replace_route') as replace:
            with self.assertRaisesRegex(LifecycleHold, 'BUSINESS_ACCEPTANCE'):
                worker.cutover_route({'stage': 'cutover_route'})
        replace.assert_not_called()

    def test_invalid_nginx_restores_exact_owned_bytes_without_reload(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=1, stdout=b'', stderr=b'')
        worker = self.build(business=lambda req: {'status': 'PASS'}, runner=runner)
        with patch('portal_lifecycle.root_read', return_value=b'original'), patch('portal_lifecycle.replace_route') as replace:
            with self.assertRaisesRegex(LifecycleHold, 'ORIGINAL_RESTORED'):
                worker.cutover_route({'stage': 'cutover_route'})
        self.assertEqual([call.args for call in replace.call_args_list],
                         [(b'original', b'candidate'), (b'candidate', b'original')])
        self.assertEqual(calls, [['/usr/sbin/nginx', '-t']])

    def test_reload_timeout_preserves_unknown_no_compensating_reload(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            if argv[0] == '/usr/bin/systemctl':
                raise subprocess.TimeoutExpired(argv, 20)
            return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        worker = self.build(business=lambda req: {'status': 'PASS'}, runner=runner)
        with patch('portal_lifecycle.root_read', return_value=b'original'), patch('portal_lifecycle.replace_route') as replace:
            with self.assertRaises(LifecycleUnknown):
                worker.cutover_route({'stage': 'cutover_route'})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(len(calls), 2)
        self.assertFalse(self.published)

    def test_disk_candidate_alone_not_loaded_route_proof(self):
        worker = self.build()
        with patch('portal_lifecycle.root_read', return_value=b'candidate'):
            with self.assertRaisesRegex(LifecycleHold, 'LOADED_ROUTE'):
                worker.query_route({'stage': 'cutover_route'})
        self.assertFalse(self.published)

    def test_successful_query_uses_original_publisher_query_only(self):
        worker = self.build(loaded=lambda req: {'status': 'PASS', 'upstream': '127.0.0.1:18080',
                                              'route_sha256': digest(b'candidate')})
        with patch('portal_lifecycle.root_read', return_value=b'candidate'):
            result = worker.query_route({'stage': 'cutover_route'})
        self.assertTrue(result['original_publisher'])
        self.assertTrue(self.published[0][1]['query_only'])


if __name__ == '__main__':
    unittest.main()
