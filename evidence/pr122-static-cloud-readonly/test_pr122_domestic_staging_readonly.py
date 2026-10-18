"""Local fixtures only. Never dispatches a command or reads production paths."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('fixed_readonly', HERE / 'pr122_domestic_staging_readonly.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class FixedReadonlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / 'root-evidence'
        self.b = self.root / 'runner-evidence'
        self.a.mkdir(); self.b.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(mod, 'ROOTS', (str(self.a), str(self.b))).start()
        patch.object(mod, 'ROOT_UID', os.geteuid()).start()
        patch.object(mod, 'RUNNER_UID', os.geteuid()).start()
        patch.object(mod, 'RUNNER_HOME', str(self.b)).start()
        patch.object(mod.os, 'geteuid', return_value=0).start()
        patch.object(mod.os, 'uname', return_value=SimpleNamespace(nodename=mod.HOST)).start()

    def populated(self):
        for label, root, relative, _ in mod.FILES:
            p = Path(mod.ROOTS[root]) / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('fixture-' + label).encode())

    def observe(self, path='file', limit=100):
        return mod._observe(str(self.a), path, limit, time.monotonic() + 10, [1000])

    def test_exact_eight_fixed_candidates(self):
        self.assertEqual(len(mod.FILES), 8)
        self.assertEqual([r[2] for r in mod.FILES if r[1] == 1], ['approved-release.tar.gz'])
        self.assertTrue(all('..' not in r[2].split('/') for r in mod.FILES))
        self.assertFalse(any('bundle/' in r[2] for r in mod.FILES))
        self.assertTrue(all(r[2].startswith('pr122-unified-release/') for r in mod.FILES if r[1] == 0))
        self.assertFalse(any('TOKYO' in r[2] for r in mod.FILES))

    def test_missing_roots_and_files_are_normal_absence(self):
        self.a.rmdir(); self.b.rmdir()
        result = mod.collect()
        self.assertEqual(result['state'], 'OBSERVATION_COMPLETE')
        self.assertTrue(all(r['state'] == 'ABSENT' for r in result['files']))

    def test_hashes_only_no_body_or_paths(self):
        self.populated()
        result = mod.collect()
        encoded = json.dumps(result)
        self.assertEqual(result['state'], 'OBSERVATION_COMPLETE')
        self.assertLess(len(encoded.encode()), mod.MAX_OUTPUT_BYTES)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn('fixture-', encoded)
        for row in result['files']:
            self.assertEqual(set(row), {'label', 'state', 'size', 'sha256'})
            raw = ('fixture-' + row['label']).encode()
            self.assertEqual(row['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(row['size'], len(raw))

    def test_unlisted_file_never_opened(self):
        (self.a / 'secret').write_text('DO_NOT_READ')
        real_open = os.open
        calls = []
        def watched(path, *args, **kwargs):
            calls.append(path)
            return real_open(path, *args, **kwargs)
        with patch.object(mod.os, 'open', side_effect=watched):
            mod.collect()
        self.assertNotIn('secret', calls)

    def test_identity_root_and_host(self):
        with patch.object(mod.os, 'geteuid', return_value=1002):
            with self.assertRaisesRegex(mod.Hold, 'FIXED_HOST_ROOT_REQUIRED'): mod.collect()
        with patch.object(mod.os, 'uname', return_value=SimpleNamespace(nodename='foreign')):
            with self.assertRaisesRegex(mod.Hold, 'FIXED_HOST_ROOT_REQUIRED'): mod.collect()

    def test_final_symlink_even_dangling_rejected(self):
        (self.a / 'file').symlink_to('missing')
        with self.assertRaisesRegex(mod.Hold, 'UNSAFE_FILE|OWNER_OR_MODE'): self.observe()

    def test_parent_symlink_rejected(self):
        (self.a / 'nested').symlink_to(self.b, target_is_directory=True)
        with self.assertRaisesRegex(mod.Hold, 'UNSAFE_DIRECTORY'): self.observe('nested/file')

    def test_root_symlink_rejected(self):
        self.a.rmdir(); self.a.symlink_to(self.b, target_is_directory=True)
        with self.assertRaisesRegex(mod.Hold, 'UNSAFE_DIRECTORY'): self.observe()

    def test_directory_file_and_hardlink_rejected(self):
        (self.a / 'file').mkdir()
        with self.assertRaisesRegex(mod.Hold, 'UNSAFE_FILE'): self.observe()
        (self.a / 'file').rmdir()
        (self.a / 'target').write_bytes(b'x'); os.link(self.a / 'target', self.a / 'file')
        with self.assertRaisesRegex(mod.Hold, 'UNSAFE_FILE'): self.observe()

    def test_fifo_rejected_without_opening(self):
        os.mkfifo(self.a / 'file')
        with self.assertRaisesRegex(mod.Hold, 'UNSAFE_FILE'): self.observe()

    def test_per_file_limit(self):
        (self.a / 'file').write_bytes(b'x' * 101)
        with self.assertRaisesRegex(mod.Hold, 'FILE_SIZE_LIMIT'): self.observe()

    def test_total_limit(self):
        (self.a / 'file').write_bytes(b'1234')
        with self.assertRaisesRegex(mod.Hold, 'TOTAL_SIZE_LIMIT'):
            mod._observe(str(self.a), 'file', 100, time.monotonic() + 10, [3])

    def test_deadline(self):
        with self.assertRaisesRegex(mod.Hold, 'DEADLINE'):
            mod._observe(str(self.a), 'file', 100, 0, [100])

    def test_file_changed_mid_read_is_hold(self):
        p = self.a / 'file'; p.write_bytes(b'1234')
        real_read = os.read
        changed = [False]
        def read(fd, size):
            data = real_read(fd, size)
            if data and not changed[0]:
                changed[0] = True; p.write_bytes(b'5678')
            return data
        with patch.object(mod.os, 'read', side_effect=read):
            with self.assertRaisesRegex(mod.Hold, 'FILE_CHANGED'): self.observe()

    def test_file_replacement_mid_read_is_hold(self):
        p = self.a / 'file'; p.write_bytes(b'1234')
        real_read = os.read; changed = [False]
        def read(fd, size):
            data = real_read(fd, size)
            if data and not changed[0]:
                changed[0] = True; p.rename(self.a / 'old'); p.write_bytes(b'1234')
            return data
        with patch.object(mod.os, 'read', side_effect=read):
            with self.assertRaisesRegex(mod.Hold, 'FILE_CHANGED|FILE_REPLACED'): self.observe()

    def test_parent_replacement_mid_read_is_hold(self):
        nested = self.a / 'nested'; nested.mkdir(); (nested / 'file').write_bytes(b'1234')
        real_read = os.read; changed = [False]
        def read(fd, size):
            data = real_read(fd, size)
            if data and not changed[0]:
                changed[0] = True; nested.rename(self.a / 'old'); nested.mkdir()
            return data
        with patch.object(mod.os, 'read', side_effect=read):
            with self.assertRaisesRegex(mod.Hold, 'DIRECTORY_CHANGED|DIRECTORY_REPLACED'):
                self.observe('nested/file')

    def test_access_error_is_sanitized(self):
        (self.a / 'file').write_bytes(b'1234')
        with patch.object(mod.os, 'read', side_effect=PermissionError('secret-path')):
            with self.assertRaisesRegex(mod.Hold, '^FILE_ACCESS$'): self.observe()

    def test_file_and_directory_writable_modes_rejected(self):
        p = self.a / 'file'; p.write_bytes(b'1234'); p.chmod(0o666)
        with self.assertRaisesRegex(mod.Hold, 'OWNER_OR_MODE'): self.observe()
        p.chmod(0o600); self.a.chmod(0o777)
        with self.assertRaisesRegex(mod.Hold, 'OWNER_OR_MODE'): self.observe()

    def test_unexpected_owner_rejected(self):
        info = SimpleNamespace(st_uid=mod.ROOT_UID + 99, st_mode=stat.S_IFREG | 0o600)
        with self.assertRaisesRegex(mod.Hold, 'OWNER_OR_MODE'): mod._protected(info, mod.ROOT_UID)

    def test_uid1002_allowance_only_fixed_runner_subtree(self):
        with patch.object(mod, 'ROOTS', ('/root/pr122-unified-release-4ryrkhl9', '/home/githubrunner/pr122-unified-release-6218264390')), patch.object(mod, 'ROOT_UID', 0), patch.object(mod, 'RUNNER_UID', 1002), patch.object(mod, 'RUNNER_HOME', '/home/githubrunner'):
            self.assertEqual(mod._owner('/home', mod.ROOTS[1]), 0)
            self.assertEqual(mod._owner('/home/githubrunner', mod.ROOTS[1]), 1002)
            self.assertEqual(mod._owner('/home/githubrunner/known', mod.ROOTS[1]), 1002)
            self.assertEqual(mod._owner('/home/githubrunner-other', mod.ROOTS[1]), 0)
            self.assertEqual(mod._owner('/root', mod.ROOTS[0]), 0)

    def test_file_disappearing_between_stat_and_open_is_hold(self):
        p = self.a / 'file'; p.write_bytes(b'1234')
        real_open = os.open
        def opened(path, *args, **kwargs):
            if path == 'file': p.unlink()
            return real_open(path, *args, **kwargs)
        with patch.object(mod.os, 'open', side_effect=opened):
            with self.assertRaisesRegex(mod.Hold, 'PATH_DISAPPEARED'): self.observe()

    def test_absence_rechecked_and_appearing_path_holds(self):
        real_stat = os.stat; calls = [0]
        fake = SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
        def observed(path, *args, **kwargs):
            if path == 'file':
                calls[0] += 1
                if calls[0] == 1: raise FileNotFoundError()
                return fake
            return real_stat(path, *args, **kwargs)
        with patch.object(mod.os, 'stat', side_effect=observed):
            with self.assertRaisesRegex(mod.Hold, 'PATH_APPEARED'): self.observe()
        self.assertEqual(calls[0], 2)

    def test_first_hold_stops_all_later_reads(self):
        with patch.object(mod, '_observe', side_effect=mod.Hold('OWNER_OR_MODE')) as read:
            result = mod.collect()
        self.assertEqual(read.call_count, 1)
        self.assertEqual(result['files'][0]['state'], 'HOLD')
        self.assertTrue(all(r['state'] == 'NOT_READ' for r in result['files'][1:]))

    def test_process_alarm_installed_and_restored(self):
        with patch.object(mod.signal, 'getsignal', return_value='old'), patch.object(mod.signal, 'signal') as handler, patch.object(mod.signal, 'alarm') as alarm:
            mod.collect()
        self.assertEqual(alarm.call_args_list[0].args, (20,))
        self.assertEqual(alarm.call_args_list[-1].args, (0,))
        self.assertEqual(handler.call_args_list[-1].args, (mod.signal.SIGALRM, 'old'))

    def test_source_size_under_eight_kib(self):
        self.assertLess((HERE / 'pr122_domestic_staging_readonly.py').stat().st_size, 8192)

    def test_main_rejects_arguments_without_reading(self):
        with patch.object(mod.sys, 'argv', ['helper', '/arbitrary']), patch.object(mod, 'collect') as call:
            with patch('sys.stdout', new_callable=io.StringIO) as out:
                self.assertEqual(mod.main(), 2)
        call.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['reason'], 'NO_ARGUMENTS_ALLOWED')

    def test_collect_holds_one_unsafe_item_without_disclosing_body(self):
        self.populated()
        p = self.b / 'approved-release.tar.gz'; p.unlink(); p.symlink_to('/not-opened-secret')
        result = mod.collect()
        self.assertEqual(result['state'], 'HOLD')
        self.assertIn(result['files'][-1]['reason'], ('UNSAFE_FILE', 'OWNER_OR_MODE'))
        self.assertNotIn('/not-opened-secret', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
