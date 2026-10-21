import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('connection_enroll', str(ROOT / 'deployment/cloud-connection/enroll.py'))
enroll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enroll)

class EnrollmentTests(unittest.TestCase):
    def run_plan(self, bad_sha=False, existing=False, apply=False):
        class Reply:
            def __init__(self, url):
                self.url = url
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def geturl(self):
                return self.url
            def read(self, limit):
                path = self.url.split(enroll.SOURCE_COMMIT + '/')[1]
                raw = (ROOT / path).read_bytes()
                return raw + b'changed' if bad_sha else raw
        opener = SimpleNamespace(open=lambda url, timeout: Reply(url))
        def lstat(path):
            return SimpleNamespace(st_mode=0o100600, st_uid=1003 if path.endswith('github-intake-token') else 0, st_nlink=1)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(enroll.sys, 'argv', ['enroll'] + (['--apply'] if apply else [])))
            stack.enter_context(patch.object(enroll.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(enroll.os, 'uname', return_value=SimpleNamespace(nodename='iZd7oeikknn1z21sq6ji6zZ')))
            stack.enter_context(patch.object(enroll.os, 'umask'))
            stack.enter_context(patch.object(enroll, 'checked_dir'))
            stack.enter_context(patch.object(enroll.os.path, 'lexists', return_value=existing))
            stack.enter_context(patch.object(enroll.os, 'lstat', side_effect=lstat))
            stack.enter_context(patch.object(enroll.urllib.request, 'build_opener', return_value=opener))
            self.mkdir = stack.enter_context(patch.object(enroll.os, 'mkdir'))
            self.write = stack.enter_context(patch.object(enroll, 'exclusive'))
            self.symlink = stack.enter_context(patch.object(enroll.os, 'symlink'))
            self.commands = stack.enter_context(patch.object(enroll.subprocess, 'check_call'))
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            enroll.main()
            return output.getvalue()

    def test_plan_has_no_writes_or_service_calls(self):
        v = json.loads(self.run_plan())
        self.assertEqual(v['state'], 'PLAN_VERIFIED')
        self.assertEqual(v['oss'], 'NOT_USED')
        self.assertEqual(v['private_delivery'], 'NOT_CONNECTED')
        self.mkdir.assert_not_called()
        self.write.assert_not_called()
        self.commands.assert_not_called()

    def test_wrong_download_sha_stops_before_writes(self):
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_SHA'):
            self.run_plan(bad_sha=True)
        self.mkdir.assert_not_called()
        self.commands.assert_not_called()

    def test_existing_enrollment_not_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, 'NO_OVERWRITE'):
            self.run_plan(existing=True, apply=True)
        self.write.assert_not_called()
        self.commands.assert_not_called()

    def test_only_new_named_service_enabled(self):
        self.run_plan(apply=True)
        calls = [x[0][0] for x in self.commands.call_args_list]
        self.assertEqual(calls, [['systemctl', 'daemon-reload'],
            ['systemctl', 'enable', '--now', 'xuanjun-cloud-connection.service'],
            ['systemctl', 'is-active', '--quiet', 'xuanjun-cloud-connection.service']])
        self.assertEqual(self.write.call_count, 5)

    def test_manifest_matches_current_sources(self):
        for path, digest in enroll.FILES.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_wrong_host_refused(self):
        with patch.object(enroll.sys, 'argv', ['enroll']), patch.object(enroll.os, 'geteuid', return_value=0), patch.object(enroll.os, 'uname', return_value=SimpleNamespace(nodename='wrong')):
            with self.assertRaisesRegex(RuntimeError, 'EXACT_UK_ROOT'):
                enroll.main()
