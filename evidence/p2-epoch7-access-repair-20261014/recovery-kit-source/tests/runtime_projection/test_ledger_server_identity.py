"""Offline exact-pin tests. Never read UK services or create ledger sockets."""
import copy
import errno
import hashlib
import json
import os
import stat
import socket
import subprocess
import sys
import time
import unittest
import types
from unittest import mock

import ledger_server_identity as identity
from ledger_read_transport import MonotonicIODeadline


def digest(raw): return hashlib.sha256(raw).hexdigest()


def fixture():
    active = {'schema': 1, 'state': 'ACTIVE', 'release_sha256': 'a' * 64,
        'config_sha256': 'b' * 64, 'binary_sha256': 'c' * 64,
        'ledger_uuid': '11111111-1111-1111-1111-111111111111', 'generation': 1,
        'epoch': 8, 'instance': '22222222-2222-2222-2222-222222222222',
        'db_path': '/var/lib/xuanjun-development/generations/1/state.sqlite',
        'ledger_socket': identity.SOCKET_PATH}
    release = '/opt/xuanjun-control-releases/integration-' + 'a' * 16 + '/stage1'
    units = {}
    for unit in identity.UNIT_PROPERTIES:
        units[unit] = {'Id': unit, 'LoadState': 'loaded', 'NeedDaemonReload': 'no',
            'FragmentPath': '/etc/systemd/system/' + unit, 'DropInPaths': ''}
    units[identity.SOCKET_UNIT].update(Listen=identity.SOCKET_PATH + ' (Stream)', Accept='no',
        Triggers=identity.SERVICE_UNIT, SocketUser='xuanjun-dispatcher', SocketGroup='xuanjun-ledger-client',
        SocketMode='0660', DirectoryMode='0711', RemoveOnStop='yes')
    units[identity.SERVICE_UNIT].update(User='xuanjun-dispatcher', Group='xuanjun-control-db',
        ExecStart=identity.expected_exec_start(release), WorkingDirectory=release, TriggeredBy=identity.SOCKET_UNIT)
    paths = [release + '/ledger_service.py', '/usr/bin/systemctl',
             '/usr/lib/systemd/systemd'] + [u['FragmentPath'] for u in units.values()]
    contents = {path: ('fixture bytes for ' + path).encode() for path in paths}
    p = {'schema': 2, 'trust_model': 'ROOT_MANAGER_DELIVERY_V1', 'exclusive_delivery_reviewed': True,
        'activation_binding': {key: active[key] for key in identity.BINDING_KEYS},
        'creator': {'pid': 1, 'uid': 0, 'gid': 0,
                    'pid_namespace_role': 'SYSTEM_INIT_SHARED_WITH_CLIENTS', 'topology_evidence_sha256': 'e'*64,
                    'exe': '/usr/lib/systemd/systemd', 'cgroup_sha256': digest(b'1:name=systemd:/init.scope\n')},
        'endpoint': {'path': identity.SOCKET_PATH, 'uid': 1002, 'gid': 1005, 'mode': 0o660},
        'files': {path: digest(raw) for path, raw in contents.items()}, 'units': units}
    return p, contents


class Backend(object):
    def __init__(self, policy, contents):
        self.p = copy.deepcopy(policy); self.contents = dict(contents)
        self.raw = json.dumps(policy, sort_keys=True).encode()
        self.identity = (1, 2, stat.S_IFREG | 0o644, 0, 0, 1, len(self.raw), 0, 0)
        self.endpoint_value = dict(policy['endpoint'], dev=1, inode=99, acl_sha256=digest(b''))
        self.active = dict(policy['activation_binding'], schema=1, state='ACTIVE', config_sha256='b'*64)
        self.chain = (('/', (1, 1, stat.S_IFDIR | 0o755, 0, 0), digest(b'')),)
        self.creator_value = {'boot_id': '12345678-1234-1234-1234-123456789abc', 'starttime': 123,
                              'cgroup_sha256': policy['creator']['cgroup_sha256']}
        self.units = copy.deepcopy(policy['units'])
        self.units[identity.SOCKET_UNIT].update(ActiveState='active', SubState='listening')
        self.units[identity.SERVICE_UNIT].update(ActiveState='active', SubState='running',
            MainPID='70', InvocationID='d' * 32)
        self.calls = []
        self.config_metadata = ('private root:1003 0640 fixture',)
    def private_config_metadata(self, deadline):
        deadline.check(); self.calls.append(('private_config_metadata', identity.CONFIG_PATH))
        return self.config_metadata
    def read(self, path, maximum, deadline, protected=False):
        deadline.check(); self.calls.append(('read', path, protected))
        if path == identity.POLICY_PATH: return self.raw, self.identity
        return self.contents[path], (1, 3, stat.S_IFREG | 0o644, 0, 0, 1, len(self.contents[path]), 0, 0)
    def endpoint(self, deadline):
        deadline.check(); self.calls.append(('endpoint',))
        return copy.deepcopy(self.endpoint_value), copy.deepcopy(self.chain)
    def creator(self, creator, deadline):
        deadline.check(); self.calls.append(('creator', creator['pid']))
        return copy.deepcopy(self.creator_value)
    def unit(self, unit, deadline):
        deadline.check(); self.calls.append(('unit', unit))
        return copy.deepcopy(self.units[unit])


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.p, contents = fixture(); self.b = Backend(self.p, contents)
        self.active = copy.deepcopy(self.b.active)
        self.store = mock.Mock(); self.store.read.side_effect = lambda **kw: copy.deepcopy(self.active)
    def load(self): return identity.load_server_verifier(self.store, _backend=self.b)
    def session(self): return self.load().session(identity.SOCKET_PATH, MonotonicIODeadline(5))
    def test_explicit_measured_init_manager_admits_fixed_endpoint(self):
        session = self.session()
        self.assertIs(session.verify((1, 0, 0)), True)
        self.assertIs(session.finish((1, 0, 0)), True)
        self.assertEqual(len([c for c in self.b.calls if c[0] == 'unit']), 4)
        self.assertTrue(all(c[2] for c in self.b.calls if c[0] == 'read'))
    def test_policy_is_not_a_callable_true_shortcut(self):
        with self.assertRaisesRegex(ValueError, 'LIFECYCLE'): self.load()(1, 0, 0, identity.SOCKET_PATH)
    def test_missing_policy_fail_closed_before_activation(self):
        self.b.read = mock.Mock(side_effect=FileNotFoundError(errno.ENOENT, 'missing'))
        with self.assertRaises(FileNotFoundError): self.load()
        self.store.read.assert_not_called()
    def test_only_fixed_policy_and_socket_paths(self):
        with self.assertRaises(ValueError): identity.load_server_verifier(self.store, '/tmp/policy', _backend=self.b)
        with self.assertRaises(ValueError): self.load().session('/tmp/socket', MonotonicIODeadline(5))
    def test_policy_mode_owner_link_are_exact(self):
        for index, value in ((2, stat.S_IFREG | 0o600), (3, 1004), (4, 1004), (5, 2)):
            old = self.b.identity; changed = list(old); changed[index] = value; self.b.identity = tuple(changed)
            with self.assertRaises(ValueError): self.load()
            self.b.identity = old
    def test_no_missing_unknown_type_confused_or_guessed_creator(self):
        mutations = [lambda p: p.pop('creator'), lambda p: p.update(extra=True),
            lambda p: p.update(schema=True), lambda p: p.update(exclusive_delivery_reviewed=1),
            lambda p: p['creator'].pop('pid'), lambda p: p['creator'].update(pid=0),
            lambda p: p['creator'].update(uid=1004), lambda p: p['creator'].update(starttime=True),
            lambda p: p['endpoint'].update(inode=True), lambda p: p['endpoint'].update(mode=0o666),
            lambda p: p['creator'].update(exe='/tmp/systemd'),
            lambda p: p['files'].update({'/etc/shadow': 'f' * 64})]
        for mutate in mutations:
            p = copy.deepcopy(self.p); mutate(p)
            with self.subTest(policy=p):
                with self.assertRaises((ValueError, KeyError)): identity.validate_policy(p)
    def test_policy_duplicate_json_keys_rejected(self):
        self.b.raw = b'{"schema":1,"schema":1}'
        with self.assertRaises(ValueError): self.load()
    def test_bad_peer_and_type_alias_denied(self):
        for peer in ((17, 0, 0), (1, 1002, 0), (1, 0, 1004), (1, False, 0)):
            with self.assertRaises(ValueError): self.session().verify(peer)
    def test_policy_replaced_before_connect_denied(self):
        verifier = self.load(); self.b.identity = tuple([1, 99] + list(self.b.identity[2:]))
        with self.assertRaisesRegex(ValueError, 'POLICY_CHANGED'):
            verifier.session(identity.SOCKET_PATH, MonotonicIODeadline(5))
    def test_policy_content_changed_after_connect_denied(self):
        session = self.session(); self.b.raw += b' '
        with self.assertRaisesRegex(ValueError, 'POLICY_CHANGED'): session.verify((1, 0, 0))
    def test_socket_inode_owner_group_mode_acl_changes_reject(self):
        for field, value in (('inode', 100), ('uid', 0), ('gid', 0), ('mode', 0o666), ('acl_sha256', 'f'*64)):
            self.b.endpoint_value = dict(self.p['endpoint'], dev=1, inode=99, acl_sha256=digest(b''))
            session = self.session(); self.b.endpoint_value[field] = value
            with self.assertRaises(ValueError): session.verify((1, 0, 0))
    def test_parent_replacement_after_send_denied(self):
        session = self.session(); session.verify((1, 0, 0)); self.b.chain = ('replaced',)
        with self.assertRaisesRegex(ValueError, 'RESPONSE_RACE'): session.finish((1, 0, 0))
    def test_boot_starttime_and_cgroup_reuse_denied(self):
        for key, value in (('boot_id', 'another'), ('starttime', 124), ('cgroup_sha256', 'f'*64)):
            self.b.creator_value = {'boot_id': '12345678-1234-1234-1234-123456789abc', 'starttime': 123,
                                   'cgroup_sha256': self.p['creator']['cgroup_sha256']}
            session = self.session(); self.b.creator_value[key] = value
            with self.assertRaises(ValueError): session.verify((1, 0, 0))
    def test_protected_manager_unit_script_config_byte_changes_deny(self):
        for path in self.p['files']:
            old = self.b.contents[path]; self.b.contents[path] = old + b'changed'
            with self.assertRaisesRegex(ValueError, 'FILE_CHANGED'): self.session()
            self.b.contents[path] = old
    def test_loaded_manager_binding_not_disk_hash_alone(self):
        for field, value in (('NeedDaemonReload', 'yes'), ('Triggers', 'other.service'), ('Accept', 'yes')):
            old = self.b.units[identity.SOCKET_UNIT][field]; self.b.units[identity.SOCKET_UNIT][field] = value
            with self.assertRaisesRegex(ValueError, 'LOADED_UNIT_CHANGED'): self.session()
            self.b.units[identity.SOCKET_UNIT][field] = old
    def test_missing_or_unprintable_properties_cannot_be_pinned(self):
        for mutate in (lambda p: p['units'][identity.SOCKET_UNIT].pop('Triggers'),
                       lambda p: p['units'][identity.SERVICE_UNIT].update(ExecStart='[unprintable]')):
            p = copy.deepcopy(self.p); mutate(p)
            with self.assertRaises(ValueError): identity.validate_policy(p)
    def test_activation_stale_type_confused_and_post_response_change(self):
        session = self.session(); session.verify((1, 0, 0)); self.active['epoch'] += 1
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_CHANGED'): session.finish((1, 0, 0))
        self.active = copy.deepcopy(self.b.active); self.active['generation'] = True
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_CHANGED'): self.session()
    def test_service_restart_mid_exchange_denied_but_between_requests_allowed(self):
        session = self.session(); session.verify((1, 0, 0)); self.b.units[identity.SERVICE_UNIT]['InvocationID'] = 'e'*32
        with self.assertRaisesRegex(ValueError, 'SERVICE_RESTART'): session.finish((1, 0, 0))
        another = self.session(); another.verify((1, 0, 0)); self.assertTrue(another.finish((1, 0, 0)))
    def test_inactive_service_may_activate_but_response_requires_live_approved_unit(self):
        self.b.units[identity.SERVICE_UNIT].update(ActiveState='inactive', SubState='dead', MainPID='0', InvocationID='')
        session = self.session(); session.verify((1, 0, 0))
        with self.assertRaisesRegex(ValueError, 'SERVICE_NOT_ACTIVE'): session.finish((1, 0, 0))
        self.b.units[identity.SERVICE_UNIT].update(ActiveState='active', SubState='running', MainPID='80', InvocationID='e'*32)
        self.assertTrue(session.finish((1, 0, 0)))
    def test_new_boot_and_recreated_socket_between_sessions_need_no_pin_rewrite(self):
        verifier = self.load()
        first = verifier.session(identity.SOCKET_PATH, MonotonicIODeadline(5))
        first.verify((1, 0, 0)); first.finish((1, 0, 0))
        unchanged = self.b.raw
        self.b.creator_value.update(boot_id='22345678-1234-1234-1234-123456789abc', starttime=2)
        self.b.endpoint_value.update(dev=2, inode=900)
        second = verifier.session(identity.SOCKET_PATH, MonotonicIODeadline(5))
        second.verify((1, 0, 0)); self.assertTrue(second.finish((1, 0, 0)))
        self.assertEqual(self.b.raw, unchanged)

    def test_valid_boot_uuid_change_during_session_rejects(self):
        session = self.session()
        self.b.creator_value['boot_id'] = '22345678-1234-1234-1234-123456789abc'
        with self.assertRaisesRegex(ValueError, 'CONNECT_RACE'): session.verify((1, 0, 0))

    def test_early_init_zero_starttime_allowed_but_bool_negative_reject(self):
        self.b.creator_value['starttime'] = 0
        session = self.session(); session.verify((1, 0, 0)); self.assertTrue(session.finish((1, 0, 0)))
        for invalid in (False, -1, '0'):
            self.b.creator_value['starttime'] = invalid
            with self.assertRaises(ValueError): self.session()

    def test_measured_init_role_and_evidence_are_mandatory_not_pid_guess(self):
        for key, value in (('pid', 17), ('pid_namespace_role', 'unknown'),
                           ('topology_evidence_sha256', ''), ('uid', 1004)):
            policy = copy.deepcopy(self.p); policy['creator'][key] = value
            with self.assertRaises(ValueError): identity.validate_policy(policy)
        policy = copy.deepcopy(self.p); del policy['creator']['pid_namespace_role']
        with self.assertRaises(ValueError): identity.validate_policy(policy)

    def test_config_hash_is_dynamic_but_full_activation_must_stay_stable(self):
        self.assertNotIn('config_sha256', self.p['activation_binding'])
        self.active['config_sha256'] = 'd'*64
        stable = self.session(); stable.verify((1, 0, 0)); self.assertTrue(stable.finish((1, 0, 0)))
        changing = self.session(); changing.verify((1, 0, 0)); self.active['config_sha256'] = 'e'*64
        with self.assertRaises(ValueError): changing.finish((1, 0, 0))

    def test_dispatcher_config_is_metadata_only_and_changes_reject(self):
        self.assertNotIn(identity.CONFIG_PATH, self.p['files'])
        session = self.session(); session.verify((1, 0, 0))
        self.assertFalse(any(call[0] == 'read' and call[1] == identity.CONFIG_PATH for call in self.b.calls))
        self.b.config_metadata = ('changed private file',)
        with self.assertRaises(ValueError): session.finish((1, 0, 0))

    def test_response_peer_changed_denied(self):
        session = self.session(); session.verify((1, 0, 0))
        with self.assertRaisesRegex(ValueError, 'PEER_CHANGED'): session.finish((18, 0, 0))
    def test_exhausted_deadline_stops_before_any_host_work(self):
        deadline = MonotonicIODeadline(1)
        deadline.expires = time.monotonic() - 1
        with self.assertRaises(socket.timeout): self.load().session(identity.SOCKET_PATH, deadline)
    def test_normalizes_only_single_known_execstart_format(self):
        release = self.p['units'][identity.SERVICE_UNIT]['WorkingDirectory']
        command = '/usr/bin/python3 ' + release + '/ledger_service.py --config ' + identity.CONFIG_PATH
        raw = '{ path=/usr/bin/python3 ; argv[]=' + command + ' ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }'
        self.assertEqual(identity.normalize_exec_start(raw), identity.expected_exec_start(release))
        for bad in ('[unprintable]', raw+raw, raw.replace('ignore_errors=no', 'ignore_errors=maybe'), raw+'\nextra'):
            with self.assertRaises(ValueError): identity.normalize_exec_start(bad)


class BackendTests(unittest.TestCase):
    @staticmethod
    def info(mode, uid=0):
        return types.SimpleNamespace(st_dev=1, st_ino=7, st_mode=mode, st_uid=uid,
            st_gid=0, st_nlink=1, st_size=0, st_mtime_ns=0, st_ctime_ns=0)

    def test_root_manager_checks_private_and_fallback_system_bus_paths(self):
        backend = identity.OSBackend()
        with mock.patch.object(os, 'geteuid', return_value=0), \
                mock.patch.object(backend, 'chain', return_value=('protected',)) as chain, \
                mock.patch.object(os, 'lstat', return_value=self.info(stat.S_IFSOCK | 0o666)):
            value = backend.manager_channel(MonotonicIODeadline(5))
        self.assertEqual([item[0] for item in value], ['/run/dbus/system_bus_socket', '/run/systemd/private'])
        self.assertEqual(chain.call_count, 2)

    def test_unprivileged_manager_checks_system_bus_without_proc_exe(self):
        backend = identity.OSBackend()
        for uid in (1002, 1004):
            with mock.patch.object(os, 'geteuid', return_value=uid), \
                    mock.patch.object(backend, 'chain', return_value=('protected',)), \
                    mock.patch.object(os, 'lstat', return_value=self.info(stat.S_IFSOCK | 0o666)):
                value = backend.manager_channel(MonotonicIODeadline(5))
            self.assertEqual([item[0] for item in value], ['/run/dbus/system_bus_socket'])

    def test_nonroot_or_nonsocket_manager_channel_rejected(self):
        backend = identity.OSBackend()
        for info in (self.info(stat.S_IFSOCK | 0o666, uid=1004), self.info(stat.S_IFREG | 0o644)):
            with mock.patch.object(backend, 'chain', return_value=('protected',)), \
                    mock.patch.object(os, 'lstat', return_value=info):
                with self.assertRaises(ValueError): backend.manager_channel(MonotonicIODeadline(5))

    def test_nonroot_writable_or_symlink_ancestor_rejected(self):
        backend = identity.OSBackend()
        for info in (self.info(stat.S_IFDIR | 0o755, uid=1004),
                     self.info(stat.S_IFDIR | 0o775), self.info(stat.S_IFLNK | 0o777)):
            with mock.patch.object(os.path, 'realpath', side_effect=lambda p: p), \
                    mock.patch.object(os, 'lstat', return_value=info):
                with self.assertRaises(ValueError): backend.chain(identity.SOCKET_PATH, MonotonicIODeadline(5))

    def test_private_config_metadata_does_not_open_read_or_hash_private_bytes(self):
        backend = identity.OSBackend(); info = self.info(stat.S_IFREG | 0o640)
        info.st_gid = 1003
        with mock.patch.object(backend, 'chain', return_value=('protected',)), \
                mock.patch.object(backend, 'acl', return_value=b''), \
                mock.patch.object(os, 'lstat', return_value=info), \
                mock.patch.object(os, 'open', side_effect=AssertionError('private bytes opened')):
            result = backend.private_config_metadata(MonotonicIODeadline(5))
        self.assertEqual(result[0][3:6], (0, 1003, 1))

    def test_private_config_unsafe_metadata_and_path_race_reject(self):
        backend = identity.OSBackend()
        for unsafe in (self.info(stat.S_IFREG | 0o660), self.info(stat.S_IFREG | 0o640, uid=1004),
                       self.info(stat.S_IFLNK | 0o777)):
            with mock.patch.object(backend, 'chain', return_value=('protected',)), \
                    mock.patch.object(os, 'lstat', return_value=unsafe):
                with self.assertRaises(ValueError): backend.private_config_metadata(MonotonicIODeadline(5))
        before, after = self.info(stat.S_IFREG | 0o640), self.info(stat.S_IFREG | 0o640)
        after.st_ino = 99
        with mock.patch.object(backend, 'chain', return_value=('protected',)), \
                mock.patch.object(backend, 'acl', return_value=b''), \
                mock.patch.object(os, 'lstat', side_effect=[before, after]), \
                mock.patch.object(os, 'open', side_effect=AssertionError('private bytes opened')):
            with self.assertRaisesRegex(ValueError, 'PRIVATE_CONFIG_RACE'):
                backend.private_config_metadata(MonotonicIODeadline(5))

    def test_unreadable_or_unknown_acl_never_silently_ignored(self):
        backend = identity.OSBackend()
        for error in (PermissionError(errno.EACCES, 'unreadable'), OSError(errno.EOPNOTSUPP, 'unsupported')):
            with mock.patch.object(os, 'getxattr', side_effect=error):
                with self.assertRaises(OSError): backend.acl('/run', MonotonicIODeadline(5))
        with mock.patch.object(os, 'getxattr', return_value=b'bad'):
            with self.assertRaises(ValueError): backend.acl('/run', MonotonicIODeadline(5))
        with mock.patch.object(os, 'getxattr', side_effect=OSError(errno.ENODATA, 'absent')):
            self.assertEqual(backend.acl('/run', MonotonicIODeadline(5)), b'')

    def test_creator_only_reads_unprivileged_metadata(self):
        p, unused = fixture(); backend = identity.OSBackend(); paths = []
        def read(path, maximum, deadline):
            paths.append(path)
            if path.endswith('/boot_id'): raw = b'12345678-1234-1234-1234-123456789abc' + b'\n'
            elif path.endswith('/stat'): raw = b'1 (systemd) S ' + b'0 '*18 + b'123 0'
            elif path.endswith('/status'): raw = b'Uid:\t0 0 0 0\nGid:\t0 0 0 0\nGroups:\t\n'
            elif path.endswith('/cgroup'): raw = b'1:name=systemd:/init.scope\n'
            else: raise AssertionError(path)
            return raw, ()
        with mock.patch.object(backend, 'read', side_effect=read), mock.patch.object(os, 'readlink', side_effect=AssertionError('proc exe forbidden')):
            result = backend.creator(p['creator'], MonotonicIODeadline(5))
        self.assertEqual(result['starttime'], 123)
        self.assertFalse(any(path.endswith('/exe') for path in paths))
    def test_creator_malformed_duplicate_ids_or_lifetime_reject(self):
        p, unused = fixture(); backend = identity.OSBackend()
        for status in (b'Uid: 0 0 0\nGid: 0 0 0 0\n', b'Uid: 0 0 0 0\nUid: 0 0 0 0\nGid: 0 0 0 0\n', b'Uid: 0 1004 0 0\nGid: 0 0 0 0\n'):
            def read(path, *args):
                if path.endswith('/boot_id'): return b'12345678-1234-1234-1234-123456789abc', ()
                if path.endswith('/stat'): return b'1 (systemd) S '+b'0 '*18+b'123 0', ()
                if path.endswith('/status'): return status, ()
                return b'1:name=systemd:/init.scope\n', ()
            with mock.patch.object(backend, 'read', side_effect=read):
                with self.assertRaises(ValueError): backend.creator(p['creator'], MonotonicIODeadline(5))
    def test_unit_reader_is_fixed_bounded_and_does_not_inherit_dbus_env(self):
        p, unused = fixture(); backend = identity.OSBackend(); real = subprocess.Popen
        values = dict(p['units'][identity.SOCKET_UNIT], ActiveState='active', SubState='listening')
        raw = '\n'.join(k+'='+v for k,v in values.items())
        def popen(argv, **kwargs):
            self.assertEqual(argv[:4], ['/usr/bin/systemctl', '--system', 'show', '--no-pager'])
            self.assertEqual(argv[-1], identity.SOCKET_UNIT)
            self.assertNotIn('DBUS_SYSTEM_BUS_ADDRESS', kwargs['env'])
            self.assertNotIn('LD_PRELOAD', kwargs['env'])
            return real([sys.executable, '-B', '-c', 'print('+repr(raw)+')'], **kwargs)
        with mock.patch.object(backend, 'manager_channel', return_value=('fixture',)), mock.patch.object(subprocess, 'Popen', side_effect=popen):
            self.assertEqual(backend.unit(identity.SOCKET_UNIT, MonotonicIODeadline(5)), values)
    def test_manager_unknown_or_missing_properties_reject(self):
        backend = identity.OSBackend(); real = subprocess.Popen
        for raw in ('Id=xuanjun-ledger.socket', 'Secret=hidden'):
            def popen(argv, **kwargs): return real([sys.executable, '-B', '-c', 'print('+repr(raw)+')'], **kwargs)
            with mock.patch.object(backend, 'manager_channel', return_value=('fixture',)), mock.patch.object(subprocess, 'Popen', side_effect=popen):
                with self.assertRaises(ValueError): backend.unit(identity.SOCKET_UNIT, MonotonicIODeadline(5))
    def test_manager_nonzero_exit_and_channel_replacement_reject(self):
        p, unused = fixture(); backend = identity.OSBackend(); real = subprocess.Popen
        values = dict(p['units'][identity.SOCKET_UNIT], ActiveState='active', SubState='listening')
        raw = '\n'.join(k+'='+v for k,v in values.items())
        for code, observations in (("raise SystemExit(2)", [('same',), ('same',)]),
                                   ('print('+repr(raw)+')', [('before',), ('after',)])):
            def popen(argv, **kwargs): return real([sys.executable, '-B', '-c', code], **kwargs)
            with mock.patch.object(backend, 'manager_channel', side_effect=observations), \
                    mock.patch.object(subprocess, 'Popen', side_effect=popen):
                with self.assertRaises(ValueError): backend.unit(identity.SOCKET_UNIT, MonotonicIODeadline(5))

    def test_manager_slow_or_oversized_fixture_is_bounded(self):
        backend = identity.OSBackend(); real = subprocess.Popen
        for code in ('import time;time.sleep(10)', "print('x'*40000)"):
            def popen(argv, **kwargs): return real([sys.executable, '-B', '-c', code], **kwargs)
            with mock.patch.object(backend, 'manager_channel', return_value=('fixture',)), mock.patch.object(subprocess, 'Popen', side_effect=popen):
                with self.assertRaises((ValueError, socket.timeout)): backend.unit(identity.SOCKET_UNIT, MonotonicIODeadline(0.1))


if __name__ == '__main__': unittest.main()
