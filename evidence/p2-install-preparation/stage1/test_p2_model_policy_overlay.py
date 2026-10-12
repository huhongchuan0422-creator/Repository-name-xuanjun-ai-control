"""Release-package guard for the Owner's current single-model policy."""
import os
import tempfile
import unittest

from codex_worker import ALLOWED_MODELS, MODEL, OPENCLAW_MODEL, CodexWorker


class P2ModelPolicyOverlayTests(unittest.TestCase):
    def test_only_56_is_admitted_before_transport_start(self):
        self.assertEqual(MODEL, 'gpt-5.6-sol')
        self.assertEqual(OPENCLAW_MODEL, 'openai/gpt-5.6-sol')
        self.assertEqual(ALLOWED_MODELS, ('gpt-5.6-sol',))
        with tempfile.TemporaryDirectory() as root:
            work = os.path.join(root, 'work')
            home = os.path.join(root, 'home')
            auth = os.path.join(root, 'auth')
            os.mkdir(work)
            os.mkdir(home)
            os.mkdir(auth)
            worker = CodexWorker('/usr/bin/codex', work, home, auth,
                                 '/usr/bin:/bin', model='gpt-5.6-sol')
            self.assertEqual(worker.model, 'gpt-5.6-sol')
            for value in ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6.1', ''):
                with self.assertRaises(ValueError):
                    CodexWorker('/usr/bin/codex', work, home, auth,
                                '/usr/bin:/bin', model=value)


if __name__ == '__main__':
    unittest.main()
