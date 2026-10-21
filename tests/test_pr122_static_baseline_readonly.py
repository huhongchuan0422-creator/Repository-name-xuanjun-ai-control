"""Fixed-path, synthetic local FD fixtures only; never invoke real collect()."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from tools import pr122_static_baseline_readonly as probe


SECRET = 'SYNTHETIC-PRIVATE-BODY-DO-NOT-PRINT'


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        for _, path in probe.FILES + probe.METADATA:
            item = self.path(path); item.parent.mkdir(parents=True, exist_ok=True)
            item.write_text(SECRET); item.chmod(0o600)
        self.path(probe.RECEIPT).write_text(json.dumps({
            'state': 'HTTPS_SMOKE_PASS_AWAIT_BROWSER', 'intent': None,
            'password': SECRET, 'unknown': {'secret': SECRET}}))
        for _, path, prefix in probe.LINKS:
            target = self.path(prefix + 'pr122-synthetic')
            target.mkdir(parents=True, exist_ok=True)
            link = self.path(path)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(prefix + 'pr122-synthetic')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.reader = probe._Reader(fd, uid=os.geteuid())
        os.close(fd)
        self.addCleanup(self.reader.close)

    def path(self, path):
        return self.root / path.lstrip('/')

    def test_complete_fixed_fixture_metadata_hash_and_no_body(self):
        result = probe._observe(self.reader)
        self.assertEqual(result['state'], 'OBSERVATION_ONLY')
        self.assertEqual(len(result['observations']), 20)
        labels = [r['label'] for r in result['observations']]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(result['inputs_root'], 'UNKNOWN_NOT_READ')
        self.assertEqual(result['source_root'], 'UNKNOWN_NOT_READ')
        self.assertEqual(result['writer_fence_lock_availability'], 'UNKNOWN')
        self.assertEqual(result['production_changes'], 0)
        publisher = next(r for r in result['observations'] if r['label'] == 'INSTALLED_PUBLISHER')
        self.assertEqual(publisher['sha256'], hashlib.sha256(SECRET.encode()).hexdigest())

    def test_exact_original_nginx_13_paths(self):
        original = json.loads((Path(__file__).resolve().parents[1] /
            'deploy/pr122-site-hub-unified/HOST_PINS.json').read_bytes())
        self.assertEqual(set(probe.NGINX), set(original['nginx']))
        self.assertEqual(len(probe.NGINX), 13)

    def test_outside_and_traversal_read_rejected_before_open(self):
        for path in ('/etc/shadow', '/etc/nginx/../shadow', '//etc/nginx/nginx.conf',
                     '/root/guessed-inputs/R2_CANDIDATE_MANIFEST.json'):
            with self.subTest(path=path), patch.object(os, 'open') as opened:
                with self.assertRaises(probe.Hold): self.reader.file(path)
                opened.assert_not_called()

    def test_unknown_roots_never_scan_or_guess(self):
        with patch.object(os, 'listdir', side_effect=AssertionError('NO_SCAN')), \
             patch.object(os, 'scandir', side_effect=AssertionError('NO_SCAN')):
            result = probe._observe(self.reader)
        self.assertEqual(result['state'], 'OBSERVATION_ONLY')
        self.assertEqual(result['previous_manifest_and_count'], 'UNKNOWN_NOT_READ')

    def test_lock_and_ledger_are_metadata_only(self):
        forbidden = {p for _, p in probe.METADATA}
        original = os.open
        def opened(name, flags, *args, **kwargs):
            self.assertNotIn(name, [p.rsplit('/', 1)[1] for p in forbidden])
            self.assertEqual(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), 0)
            return original(name, flags, *args, **kwargs)
        with patch.object(os, 'open', side_effect=opened):
            result = probe._observe(self.reader)
        rows = result['observations'][-2:]
        self.assertTrue(all(r['state'] == 'METADATA_ONLY' and 'sha256' not in r for r in rows))

    def test_link_escape_and_noncanonical_targets_rejected(self):
        label, path, prefix = probe.LINKS[0]
        for target in ('/etc', prefix + '../secret', prefix + 'pr122-good/extra',
                       'releases/../secret', '/var/www/other/releases/pr122-x'):
            link = self.path(path); link.unlink(); link.symlink_to(target)
            with self.subTest(target=target), self.assertRaises(probe.Hold):
                self.reader.link(path, prefix)
            self.reader.records.clear()

    def test_current_link_relative_bounded_release_is_valid(self):
        _, path, prefix = probe.LINKS[0]
        link = self.path(path); link.unlink(); link.symlink_to('releases/pr122-synthetic')
        self.assertEqual(self.reader.link(path, prefix)['target'], prefix + 'pr122-synthetic')

    def test_symlink_ancestor_never_followed(self):
        publisher = next(p for l, p in probe.FILES if l == 'INSTALLED_PUBLISHER')
        parent = self.path(publisher).parent
        moved = parent.with_name('moved'); parent.rename(moved); parent.symlink_to(moved)
        with self.assertRaises(probe.Hold): self.reader.file(publisher)

    def test_symlink_hardlink_fifo_refused_before_file_open(self):
        path = probe.FILES[1][1]
        item = self.path(path)
        item.unlink(); item.symlink_to('/etc/shadow')
        with self.assertRaises(probe.Hold): self.reader.file(path)
        item.unlink(); item.write_text(SECRET); os.link(item, item.with_name('hardlink'))
        with self.assertRaises(probe.Hold): self.reader.file(path)
        item.unlink(); os.mkfifo(item)
        with self.assertRaises(probe.Hold): self.reader.file(path)

    def test_wrong_owner_and_writable_file_refused(self):
        item = self.path(probe.FILES[1][1]); item.chmod(0o666)
        with self.assertRaises(probe.Hold): self.reader.file(probe.FILES[1][1])
        item.chmod(0o600)
        with patch.object(self.reader, 'uid', self.reader.uid + 1):
            with self.assertRaises(probe.Hold): self.reader.file(probe.FILES[1][1])

    def test_file_size_and_total_budget_fail_before_content_read(self):
        path = probe.FILES[1][1]
        for setting, value in (('remaining', 0),):
            setattr(self.reader, setting, value)
            with patch.object(os, 'read') as read, self.assertRaises(probe.Hold):
                self.reader.file(path)
            read.assert_not_called()
        with patch.object(probe, 'FILE_LIMIT', 1), patch.object(os, 'read') as read:
            with self.assertRaises(probe.Hold): self.reader.file(path)
            read.assert_not_called()

    def test_growth_and_inode_replacement_during_read_refused(self):
        path = probe.FILES[1][1]; item = self.path(path)
        original = os.read
        changed = False
        def read(fd, size):
            nonlocal changed
            data = original(fd, size)
            if not changed:
                changed = True
                replacement = item.with_name('replacement'); replacement.write_text(SECRET)
                replacement.chmod(0o600); replacement.replace(item)
            return data
        with patch.object(os, 'read', side_effect=read), self.assertRaises(probe.Hold):
            self.reader.file(path)

    def test_final_stability_detects_prior_file_replacement(self):
        path = probe.FILES[1][1]
        self.reader.file(path)
        item = self.path(path); item.unlink(); item.write_text(SECRET)
        with self.assertRaises(probe.Hold): self.reader.stable()

    def test_growth_past_declared_size_during_read_is_refused(self):
        path = probe.FILES[1][1]; item = self.path(path)
        original = os.read
        changed = False
        def read(fd, size):
            nonlocal changed
            block = original(fd, size)
            if not changed:
                changed = True
                with item.open('ab') as out: out.write(b'grown')
            return block
        with patch.object(os, 'read', side_effect=read), self.assertRaises(probe.Hold):
            self.reader.file(path)

    def test_link_replacement_during_readlink_is_refused(self):
        _, path, prefix = probe.LINKS[0]
        link = self.path(path)
        original = os.readlink
        def readlink(*args, **kwargs):
            value = original(*args, **kwargs)
            link.unlink(); link.symlink_to(prefix + 'pr122-synthetic')
            return value
        with patch.object(os, 'readlink', side_effect=readlink), self.assertRaises(probe.Hold):
            self.reader.link(path, prefix)

    def test_reader_growth_exhausts_remaining_budget(self):
        path = probe.FILES[1][1]
        self.reader.remaining = len(SECRET)
        original = os.read
        def read(fd, size):
            block = original(fd, size)
            return block + b'over-budget' if block else block
        with patch.object(os, 'read', side_effect=read), self.assertRaises(probe.Hold):
            self.reader.file(path)

    def test_directory_replacement_after_open_is_refused(self):
        self.reader.file(probe.FILES[1][1])
        parent = self.path('/usr/local/libexec'); parent.rename(parent.with_name('old'))
        parent.mkdir()
        with self.assertRaises(probe.Hold): self.reader.stable()

    def test_absent_file_is_rechecked_and_appearance_refused(self):
        path = probe.FILES[1][1]; item = self.path(path); item.unlink()
        row, raw = self.reader.file(path)
        self.assertEqual(row['state'], 'ABSENT'); self.assertIsNone(raw)
        item.write_text(SECRET)
        with self.assertRaises(probe.Hold): self.reader.stable()

    def test_deadline_and_path_budgets(self):
        self.reader.deadline = 0
        with self.assertRaises(probe.Hold): self.reader.file(probe.FILES[1][1])
        self.reader.deadline = float('inf'); self.reader.calls = probe.PATH_LIMIT
        with self.assertRaises(probe.Hold): self.reader.file(probe.FILES[1][1])

    def test_receipt_unknown_values_and_exception_text_do_not_escape(self):
        for raw in (json.dumps({'state': SECRET, 'intent': SECRET}).encode(),):
            self.assertNotIn(SECRET, json.dumps(probe._receipt_summary(raw)))
        for raw in (b'{"state":1,"state":2}', b'[]', b'{"x":NaN}'):
            with self.assertRaises((probe.Hold, ValueError)): probe._receipt_summary(raw)
        with patch.object(self.reader, 'file', side_effect=OSError(SECRET)):
            result = probe._observe(self.reader)
        self.assertEqual(result['state'], 'HOLD')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertTrue(any(x['state'] == 'NOT_READ' for x in result['observations']))


class EntryTests(unittest.TestCase):
    def test_wrong_identity_or_arguments_never_open_root(self):
        for uid, host, argv in ((1, probe.HOST, ['tool']), (0, 'wrong', ['tool']),
                                (0, probe.HOST, ['tool', '--path=/etc/shadow'])):
            with patch.object(os, 'geteuid', return_value=uid), \
                 patch.object(os, 'uname', return_value=SimpleNamespace(nodename=host)), \
                 patch.object(probe.sys, 'argv', argv), patch.object(os, 'open') as opened, \
                 redirect_stdout(io.StringIO()) as out:
                self.assertEqual(probe.main(), 2)
                opened.assert_not_called()
                self.assertEqual(json.loads(out.getvalue())['state'], 'HOLD')

    def test_output_budget_and_unexpected_exception_sanitized(self):
        for value in ({'state': 'OBSERVATION_ONLY', 'data': 'x' * 40000},):
            with patch.object(os, 'geteuid', return_value=0), \
                 patch.object(os, 'uname', return_value=SimpleNamespace(nodename=probe.HOST)), \
                 patch.object(probe.sys, 'argv', ['tool']), \
                 patch.object(probe, 'collect', return_value=value), \
                 redirect_stdout(io.StringIO()) as out:
                self.assertEqual(probe.main(), 2)
                self.assertLess(len(out.getvalue()), 1024)

    def test_source_has_no_write_lock_process_network_or_scan_api(self):
        tree = ast.parse(Path(probe.__file__).read_text())
        forbidden = {'flock', 'lockf', 'mkdir', 'makedirs', 'chmod', 'chown', 'unlink',
                     'replace', 'rename', 'write', 'write_bytes', 'write_text',
                     'listdir', 'scandir', 'walk', 'glob', 'rglob', 'system', 'Popen',
                     'socket', 'urlopen'}
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)}
        self.assertFalse(calls & forbidden)
        imports = {n.names[0].name for n in tree.body if isinstance(n, ast.Import)}
        self.assertFalse(imports & {'fcntl', 'subprocess', 'socket', 'urllib', 'requests'})


if __name__ == '__main__':
    unittest.main()
