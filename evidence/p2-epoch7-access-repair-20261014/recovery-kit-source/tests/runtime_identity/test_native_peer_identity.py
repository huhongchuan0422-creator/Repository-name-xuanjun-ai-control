"""Local logic tests. Ownership and proc are fixtures, not UK kernel proof."""
from __future__ import print_function
import errno
import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import tempfile
import types
import unittest
from unittest import mock

# Staged-kit adapter: normal import is served by the authenticated byte cache.
import native_peer_identity as s
ROOT = pathlib.Path(s.__file__).resolve().parents[1]
REAL_STAT, REAL_FSTAT, REAL_OPEN, REAL_READ = os.stat, os.fstat, os.open, os.read
REAL_READLINK = os.readlink


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def changed_info(info, **changes):
    names = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
             'st_size', 'st_mtime_ns', 'st_ctime_ns')
    values = {name: getattr(info, name) for name in names}
    values.update(changes)
    return types.SimpleNamespace(**values)


class NativePeerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='epoch7-native-identity-')
        self.root = pathlib.Path(self.tmp.name)
        self.proc = self.root / 'proc'
        self.peer, self.parent, self.uid = 321, 123, 1002
        self.python = self.root / 'python3'
        self.gateway = self.root / 'gateway'
        self.bridge = self.root / 'native_ledger_bridge.py'
        self.config = self.root / 'client.json'
        self.binding_path = self.root / 'binding.json'
        for path, raw in ((self.python, b'python bytes'), (self.gateway, b'node bytes'),
                          (self.bridge, b'bridge bytes'), (self.config, b'config bytes')):
            path.write_bytes(raw)
            path.chmod(0o644)
        for pid, exe, ppid, start in ((self.peer, self.python, self.parent, 200),
                                      (self.parent, self.gateway, 1, 100)):
            directory = self.proc / str(pid)
            directory.mkdir(parents=True)
            (directory / 'exe').symlink_to(exe)
            self.write_status(pid, ppid=ppid)
            self.write_stat(pid, start)
        self.cmdline = b'\0'.join(x.encode('utf-8') for x in
            (str(self.python), '-B', str(self.bridge), '--config', str(self.config))) + b'\0'
        self.write_proc(self.peer, 'cmdline', self.cmdline)
        self.write_proc(self.parent, 'cgroup', b'0::/system.slice/pinned.service\n')
        self.identity = dict(uid=self.uid, gateway_exe=str(self.gateway),
            gateway_exe_sha256=digest(b'node bytes'),
            gateway_cgroup='/system.slice/pinned.service', bridge_python=str(self.python),
            bridge_python_sha256=digest(b'python bytes'), bridge_path=str(self.bridge),
            bridge_config=str(self.config), bridge_sha256=digest(b'bridge bytes'),
            bridge_config_sha256=digest(b'config bytes'))
        self.binding = {'gatewayIdentity': {'user': 'gateway', 'exe': str(self.gateway),
            'sha256': self.identity['gateway_exe_sha256'],
            'cgroup': self.identity['gateway_cgroup']}, 'ledger': {
            'python': str(self.python), 'pythonSha256': self.identity['bridge_python_sha256'],
            'bridge': str(self.bridge), 'config': str(self.config), 'files': {
                str(self.bridge): self.identity['bridge_sha256'],
                str(self.config): self.identity['bridge_config_sha256']}}}
        self.write_binding()
        self.owner_overrides = {}
        self.patches = [mock.patch.object(s.os, 'fstat', side_effect=self.fstat),
                        mock.patch.object(s.os, 'stat', side_effect=self.stat),
                        mock.patch.object(s.pwd, 'getpwnam',
                                          return_value=types.SimpleNamespace(pw_uid=self.uid))]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def spoof_owner(self, info):
        gateway = REAL_STAT(str(self.gateway))
        uid = self.uid if (info.st_dev, info.st_ino) == (gateway.st_dev, gateway.st_ino) else 0
        uid = self.owner_overrides.get((info.st_dev, info.st_ino), uid)
        return changed_info(info, st_uid=uid)

    def fstat(self, fd):
        return self.spoof_owner(REAL_FSTAT(fd))

    def stat(self, path, *args, **kwargs):
        return self.spoof_owner(REAL_STAT(path, *args, **kwargs))

    def wrong_owner(self, path, uid):
        info = REAL_STAT(str(path))
        self.owner_overrides[(info.st_dev, info.st_ino)] = uid

    def write_proc(self, pid, name, raw):
        (self.proc / str(pid) / name).write_bytes(raw)

    def write_status(self, pid, ppid=None, uids=None):
        if ppid is None:
            ppid = self.parent if pid == self.peer else 1
        if uids is None:
            uids = [self.uid] * 4
        self.write_proc(pid, 'status', ('Name:\tfixture\nPPid:\t%d\nUid:\t%s\n' %
                        (ppid, ' '.join(str(x) for x in uids))).encode('ascii'))

    def write_stat(self, pid, start, comm='fixture (with) spaces'):
        fields = ['S', str(self.parent if pid == self.peer else 1)] + ['0'] * 17 + [str(start)]
        self.write_proc(pid, 'stat', ('%d (%s) %s\n' %
                                    (pid, comm, ' '.join(fields))).encode('ascii'))

    def write_binding(self):
        self.binding_path.write_text(json.dumps(self.binding))
        self.binding_path.chmod(0o644)

    def verify(self, **changes):
        identity = dict(self.identity)
        identity.update(changes)
        return s.verify_native_gateway_peer(self.peer, self.uid, identity, str(self.proc))

    def test_current_valid_peer(self):
        self.assertTrue(self.verify())

    def test_valid_v1_cgroup(self):
        self.write_proc(self.parent, 'cgroup', b'11:memory:/other\n1:name=systemd:/system.slice/pinned.service\n')
        self.assertTrue(self.verify())

    def test_starttime_parser_handles_parentheses_and_spaces(self):
        self.assertEqual(s._proc_starttime(str(self.proc), self.peer), 200)

    def test_invalid_socket_uid_and_arguments(self):
        for pid, uid, ident in ((self.peer, 1003, self.identity), (True, self.uid, self.identity),
                                (0, self.uid, self.identity), (self.peer, True, self.identity),
                                (self.peer, self.uid, None), (self.peer, self.uid, {})):
            with self.subTest(pid=pid, uid=uid, identity=ident):
                self.assertFalse(s.verify_native_gateway_peer(pid, uid, ident, str(self.proc)))

    def test_all_four_peer_and_parent_uids_are_required(self):
        for pid in (self.peer, self.parent):
            for index in range(4):
                uids = [self.uid] * 4
                uids[index] = 1003
                self.write_status(pid, uids=uids)
                self.assertFalse(self.verify())
            self.write_status(pid, uids=[self.uid] * 3)
            self.assertFalse(self.verify())
            self.write_status(pid)
        self.assertTrue(self.verify())

    def test_wrong_parent(self):
        for parent in (0, 999):
            self.write_status(self.peer, ppid=parent)
            self.assertFalse(self.verify())

    def test_wrong_python_path(self):
        self.assertFalse(self.verify(bridge_python=str(self.root / 'other-python')))

    def test_wrong_gateway_path(self):
        self.assertFalse(self.verify(gateway_exe=str(self.root / 'other-node')))

    def test_deleted_gateway_path_rejected(self):
        original = REAL_READLINK
        target = str(self.proc / str(self.parent) / 'exe')
        def readlink(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return value + ' (deleted)' if path == target else value
        with mock.patch.object(s.os, 'readlink', side_effect=readlink):
            self.assertFalse(self.verify())

    def test_wrong_executable_hashes(self):
        for field in ('bridge_python_sha256', 'gateway_exe_sha256'):
            self.assertFalse(self.verify(**{field: '0' * 64}))

    def test_wrong_bridge_or_config_hash(self):
        for field in ('bridge_sha256', 'bridge_config_sha256'):
            self.assertFalse(self.verify(**{field: '0' * 64}))

    def test_wrong_executable_owners(self):
        for path, uid in ((self.python, self.uid), (self.gateway, 0)):
            self.wrong_owner(path, uid)
            self.assertFalse(self.verify())
            self.owner_overrides.clear()

    def test_wrong_root_file_owners(self):
        for path in (self.bridge, self.config):
            self.wrong_owner(path, self.uid)
            self.assertFalse(self.verify())
            self.owner_overrides.clear()

    def test_group_or_world_writable_files_rejected(self):
        for path in (self.python, self.gateway, self.bridge, self.config):
            for mode in (0o664, 0o646):
                path.chmod(mode)
                self.assertFalse(self.verify())
            path.chmod(0o644)
        self.assertTrue(self.verify())

    def test_nonregular_executable_rejected(self):
        real = self.fstat
        gateway_info = REAL_STAT(str(self.gateway))
        def fstat(fd):
            info = real(fd)
            if info.st_ino == gateway_info.st_ino:
                return changed_info(info, st_mode=stat.S_IFIFO | 0o600)
            return info
        with mock.patch.object(s.os, 'fstat', side_effect=fstat):
            self.assertFalse(self.verify())

    def test_exact_argv_required(self):
        for cmdline in (self.cmdline + b'--extra\0', self.cmdline.replace(b'-B\0', b''),
                        self.cmdline.replace(b'--config\0', b'--other\0'), b''):
            self.write_proc(self.peer, 'cmdline', cmdline)
            self.assertFalse(self.verify())

    def test_exact_cgroup_required(self):
        for raw in (b'0::/system.slice/pinned.service-other\n', b'0::/other\n', b'bad\n'):
            self.write_proc(self.parent, 'cgroup', raw)
            self.assertFalse(self.verify())

    def test_readlink_eacces_fails_closed(self):
        with mock.patch.object(s.os, 'readlink', side_effect=PermissionError(errno.EACCES, 'denied')):
            self.assertFalse(self.verify())

    def test_proc_executable_open_eacces_fails_closed(self):
        def opener(path, flags, *args, **kwargs):
            if str(path).endswith('/exe'):
                raise PermissionError(errno.EACCES, 'denied')
            return REAL_OPEN(path, flags, *args, **kwargs)
        with mock.patch.object(s.os, 'open', side_effect=opener):
            self.assertFalse(self.verify())

    def test_proc_stat_eacces_fails_closed(self):
        with mock.patch.object(s.os, 'stat', side_effect=PermissionError(errno.EACCES, 'denied')):
            self.assertFalse(self.verify())

    def test_read_error_fails_closed(self):
        with mock.patch.object(s.os, 'read', side_effect=OSError(errno.EIO, 'read failure')):
            self.assertFalse(self.verify())

    def test_executable_read_error_closes_descriptor(self):
        seen = []
        def read(fd, count):
            target = REAL_READLINK('/proc/self/fd/' + str(fd))
            if target == str(self.gateway):
                seen.append(fd)
                raise OSError(errno.EIO, 'read failure')
            return REAL_READ(fd, count)
        with mock.patch.object(s.os, 'read', side_effect=read):
            self.assertFalse(self.verify())
        self.assertEqual(len(seen), 1)
        with self.assertRaises(OSError):
            REAL_FSTAT(seen[0])

    def test_missing_proc_field_fails_closed(self):
        for pid, name in ((self.peer, 'stat'), (self.parent, 'stat'), (self.peer, 'status'),
                          (self.parent, 'status'), (self.peer, 'exe'), (self.parent, 'exe'),
                          (self.peer, 'cmdline'), (self.parent, 'cgroup')):
            path = self.proc / str(pid) / name
            saved = str(path) + '.saved'
            os.rename(str(path), saved)
            self.assertFalse(self.verify(), (pid, name))
            os.rename(saved, str(path))

    def test_malformed_starttime_rejected(self):
        for raw in (b'', b'999 (x) S 1\n', b'321 (x) S 1\n',
                    b'321 (x) ' + b'0 ' * 19 + b'bad\n'):
            self.write_proc(self.peer, 'stat', raw)
            self.assertFalse(self.verify())

    def test_pid_reuse_of_peer_or_parent_rejected(self):
        original = s._proc_starttime
        for pid in (self.peer, self.parent):
            calls = []
            def start(proc_root, target):
                result = original(proc_root, target)
                if target == pid:
                    calls.append(target)
                    if len(calls) > 1:
                        result += 1
                return result
            with mock.patch.object(s, '_proc_starttime', side_effect=start):
                self.assertFalse(self.verify())
            self.assertEqual(len(calls), 2)

    def test_reparent_or_uid_change_during_validation_rejected(self):
        original = s._proc_bytes
        for target, variant in ((self.peer, 'parent'), (self.peer, 'uid'), (self.parent, 'uid')):
            counts = []
            def proc_bytes(root, pid, name, maximum=65536):
                raw = original(root, pid, name, maximum)
                if pid == target and name == 'status':
                    counts.append(1)
                    if len(counts) > 1:
                        if variant == 'parent':
                            return raw.replace(b'PPid:\t123', b'PPid:\t999')
                        return raw.replace(b'1002', b'1003')
                return raw
            with mock.patch.object(s, '_proc_bytes', side_effect=proc_bytes):
                self.assertFalse(self.verify())

    def test_argv_or_cgroup_changes_during_validation_rejected(self):
        original = s._proc_bytes
        for pid, field in ((self.peer, 'cmdline'), (self.parent, 'cgroup')):
            calls = []
            def proc_bytes(root, target, name, maximum=65536):
                raw = original(root, target, name, maximum)
                if (target, name) == (pid, field):
                    calls.append(1)
                    if len(calls) > 1:
                        raw += b'changed'
                return raw
            with mock.patch.object(s, '_proc_bytes', side_effect=proc_bytes):
                self.assertFalse(self.verify())

    def test_executable_metadata_change_rejected(self):
        real = self.fstat
        gateway_info = REAL_STAT(str(self.gateway))
        calls = []
        def fstat(fd):
            info = real(fd)
            if info.st_ino == gateway_info.st_ino:
                calls.append(1)
                if len(calls) > 1:
                    return changed_info(info, st_mtime_ns=info.st_mtime_ns + 1)
            return info
        with mock.patch.object(s.os, 'fstat', side_effect=fstat):
            self.assertFalse(self.verify())

    def test_process_executable_inode_change_rejected(self):
        real = self.stat
        target = str(self.proc / str(self.parent) / 'exe')
        def statter(path, *args, **kwargs):
            info = real(path, *args, **kwargs)
            return changed_info(info, st_ino=info.st_ino + 1) if path == target else info
        with mock.patch.object(s.os, 'stat', side_effect=statter):
            self.assertFalse(self.verify())

    def test_executable_size_bound(self):
        with self.assertRaises(ValueError):
            s._proc_exe_sha256(str(self.proc), self.parent, str(self.gateway), self.uid, maximum=3)

    def test_bounded_reads_and_short_read_supported(self):
        counts = []
        def read(fd, count):
            counts.append(count)
            return REAL_READ(fd, min(count, 2))
        with mock.patch.object(s.os, 'read', side_effect=read):
            result, unused = s._proc_exe_sha256(
                str(self.proc), self.parent, str(self.gateway), self.uid, maximum=10)
        self.assertEqual(result, digest(b'node bytes'))
        self.assertLessEqual(max(counts), 11)

    def test_growing_executable_exceeds_read_bound(self):
        reads = []
        def read(fd, count):
            reads.append(count)
            return b'x' * count
        with mock.patch.object(s.os, 'read', side_effect=read):
            with self.assertRaises(ValueError):
                s._proc_exe_sha256(str(self.proc), self.parent, str(self.gateway), self.uid, maximum=10)
        self.assertEqual(reads, [11])

    def test_premature_eof_rejected(self):
        with mock.patch.object(s.os, 'read', return_value=b''):
            with self.assertRaises(ValueError):
                s._proc_exe_sha256(str(self.proc), self.parent, str(self.gateway), self.uid)

    def test_startup_keeps_python_bridge_config_hashes(self):
        self.assertEqual(s.load_native_peer_identity(str(self.binding_path)), self.identity)
        for path in (self.python, self.bridge, self.config):
            original = path.read_bytes()
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                s.load_native_peer_identity(str(self.binding_path))
            path.write_bytes(original)

    def test_startup_does_not_traverse_hidden_gateway_path(self):
        hidden = '/home/gateway/hidden/runtime/node'
        self.binding['gatewayIdentity']['exe'] = hidden
        self.write_binding()
        realpath = os.path.realpath
        def canonical(path, *args, **kwargs):
            if path == hidden:
                raise AssertionError('traversed hidden Gateway path')
            return realpath(path, *args, **kwargs)
        def opener(path, flags, *args, **kwargs):
            if path == hidden:
                raise AssertionError('opened hidden Gateway path')
            return REAL_OPEN(path, flags, *args, **kwargs)
        with mock.patch.object(s.os.path, 'realpath', side_effect=canonical), \
                mock.patch.object(s.os, 'open', side_effect=opener):
            identity = s.load_native_peer_identity(str(self.binding_path))
        self.assertEqual(identity['gateway_exe'], hidden)

    def test_live_hash_does_not_open_hidden_gateway_path(self):
        hidden = '/home/gateway/hidden/runtime/node'
        target = str(self.proc / str(self.parent) / 'exe')
        opened = []
        def readlink(path, *args, **kwargs):
            return hidden if path == target else REAL_READLINK(path, *args, **kwargs)
        def opener(path, flags, *args, **kwargs):
            opened.append(path)
            if path == hidden:
                raise AssertionError('opened hidden Gateway path')
            return REAL_OPEN(path, flags, *args, **kwargs)
        with mock.patch.object(s.os, 'readlink', side_effect=readlink), \
                mock.patch.object(s.os, 'open', side_effect=opener):
            self.assertTrue(self.verify(gateway_exe=hidden))
        self.assertIn(target, opened)
        self.assertNotIn(hidden, opened)

    def test_deferred_gateway_hash_is_mandatory_at_admission(self):
        self.binding['gatewayIdentity']['sha256'] = '0' * 64
        self.write_binding()
        identity = s.load_native_peer_identity(str(self.binding_path))
        self.assertFalse(s.verify_native_gateway_peer(self.peer, self.uid, identity, str(self.proc)))

    def test_noncanonical_gateway_binding_rejected(self):
        for path in ('relative/node', '//home/node', '/home/../node', '/home//node',
                     '/home/./node', '/home/node/', '/home/node\0bad'):
            self.binding['gatewayIdentity']['exe'] = path
            self.write_binding()
            with self.assertRaises(ValueError):
                s.load_native_peer_identity(str(self.binding_path))

    def test_unreadable_startup_config_fails_closed(self):
        def opener(path, flags, *args, **kwargs):
            if path == str(self.config):
                raise PermissionError(errno.EACCES, 'config denied')
            return REAL_OPEN(path, flags, *args, **kwargs)
        with mock.patch.object(s.os, 'open', side_effect=opener):
            with self.assertRaises(PermissionError):
                s.load_native_peer_identity(str(self.binding_path))

    def test_startup_binding_permissions_retained(self):
        self.binding_path.chmod(0o666)
        with self.assertRaises(ValueError):
            s.load_native_peer_identity(str(self.binding_path))

    def test_service_minimal_security_delta(self):
        service = (ROOT / 'deploy/xuanjun-ledger.service').read_text()
        expected = ('User=xuanjun-dispatcher', 'Group=xuanjun-control-db',
                    'ProtectHome=yes', 'ProtectSystem=strict', 'NoNewPrivileges=yes',
                    'PrivateTmp=yes', 'PrivateDevices=yes', 'ProtectControlGroups=yes',
                    'RestrictSUIDSGID=yes', 'RestrictAddressFamilies=AF_UNIX',
                    'CapabilityBoundingSet=CAP_SYS_PTRACE',
                    'AmbientCapabilities=CAP_SYS_PTRACE',
                    'SystemCallFilter=~ptrace process_vm_readv process_vm_writev',
                    'SystemCallArchitectures=native')
        for line in expected:
            self.assertIn(line + '\n', service)
        self.assertNotIn('CAP_DAC', service)
        # Reviewed package delta: one explicit dispatcher group is required.
        self.assertEqual([line for line in service.splitlines() if line.startswith('SupplementaryGroups=')],
                         ['SupplementaryGroups=xuanjun-dispatcher'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
