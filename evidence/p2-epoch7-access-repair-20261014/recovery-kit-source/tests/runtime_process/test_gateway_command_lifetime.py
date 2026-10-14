"""Offline Gateway transport tests. No Gateway/model/network command executes."""
import hashlib
import os
import signal
import shlex
import sys
import time
import unittest
from unittest import mock

import ledger_server_identity as lifetime
import native_gateway_controller as gateway
from test_runtime_command_lifetime import OwnedChildFixture


class GatewayCommandLifetimeTests(OwnedChildFixture, unittest.TestCase):
    def setUp(self):
        super(GatewayCommandLifetimeTests, self).setUp()
        # Hosted Python toolcache files may legitimately be group-writable.
        # Pin a private owner-executable fixture, never relax production checks.
        self.executable = self.directory.name + '/fixture-python'
        with open(self.executable, 'w') as stream:
            stream.write('#!/bin/sh\nexec ' + shlex.quote(os.path.realpath(sys.executable)) + ' "$@"\n')
        os.chmod(self.executable, 0o500)
        self.assertEqual(os.stat(self.executable).st_mode & 0o777, 0o500)
        with open(self.executable, 'rb') as stream: digest = hashlib.sha256(stream.read()).hexdigest()
        self.config = {'openclaw_bin': self.executable, 'openclaw_sha256': digest,
            'openclaw_owner_uid': os.stat(self.executable).st_uid,
            'gateway_home': '/nonexistent', 'gateway_path': '/usr/bin:/bin'}
        self.controller = gateway.GatewayController(self.config)

    def gateway_source(self, source, timeout=3.0):
        original = lifetime._bounded_owned_command
        def shortened(argv, environment, production_timeout, maximum):
            self.assertEqual(production_timeout, 30); self.assertEqual(maximum, 1048576)
            self.assertEqual(environment, {'HOME': '/nonexistent', 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            return original(argv, environment, timeout, maximum)
        with mock.patch.object(gateway, '_bounded_owned_command', side_effect=shortened), \
                mock.patch.object(lifetime.subprocess, 'Popen', side_effect=self.spawn):
            try: return self.controller._run([self.executable, '-B', '-c', source])
            except BaseException as error:
                self.record_cleanup_unknown(error)
                raise

    def test_success_json_and_public_call_contract(self):
        self.assertEqual(self.gateway_source('print("{}")'), {})
        with mock.patch.object(gateway, '_bounded_owned_command', return_value=b'{}') as run:
            self.assertEqual(self.controller.preflight({}), {})
        argv = run.call_args[0][0]
        self.assertEqual(argv[:4], [self.executable, 'gateway', 'call', 'xuanjun.execution.inspect'])
        self.assertEqual(argv[-1], '--json')

    def test_selector_setup_failure_maps_static_error_after_cleanup(self):
        with mock.patch.object(lifetime.selectors, 'DefaultSelector', side_effect=OSError('secret fixture')):
            with self.assertRaisesRegex(gateway.NativeContractError, '^Gateway effect unknown; no retry$'):
                self.gateway_source('import time;time.sleep(10)')

    def test_timeout_is_bounded(self):
        started = time.monotonic()
        with self.assertRaises(gateway.NativeContractError): self.gateway_source('import time;time.sleep(10)', timeout=1.0)
        self.assertLess(time.monotonic() - started, 4.0)
        process = self.children[-1]
        if process.returncode is None and process.pid in self.pending_reaps: process.wait(timeout=2)
        self.assertEqual(process.returncode, -signal.SIGKILL)

    def test_exited_leader_held_pipe_is_killed_before_and_during_capture(self):
        for before in (False, True):
            self.pipe_holder(before, invoke=lambda code:self.gateway_source(code, timeout=1.0))

    def test_stderr_and_stdout_flood_are_bounded(self):
        for fd in (1, 2):
            with self.assertRaises(gateway.NativeContractError):
                self.gateway_source('import os\nwhile True:os.write(%d,b"x"*65536)' % fd)

    def test_malformed_duplicate_nonfinite_and_nonzero_response_fail(self):
        for raw in (b'{', b'\xff', b'{"a":1,"a":2}', b'NaN'):
            with self.assertRaises((ValueError, UnicodeError)):
                self.gateway_source('import os;os.write(1,%r)' % raw)
        with self.assertRaises(gateway.NativeContractError): self.gateway_source('raise SystemExit(2)')

    def test_interrupt_propagates_after_cleanup(self):
        with mock.patch.object(lifetime.selectors, 'DefaultSelector', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.gateway_source('import time;time.sleep(10)')

    def test_bad_executable_pin_never_spawns(self):
        self.controller.sha256 = '0' * 64
        with mock.patch.object(gateway, '_bounded_owned_command') as run:
            with self.assertRaises(gateway.NativeContractError): self.controller._run(['/unused'])
            run.assert_not_called()

    def test_executable_read_is_finite_and_nonblocking(self):
        original_open, original_read = os.open, os.read
        flags, sizes = [], []
        def opened(path, value, *args, **kwargs):
            flags.append(value); return original_open(path, value, *args, **kwargs)
        def read(fd, size):
            sizes.append(size); return original_read(fd, size)
        with mock.patch.object(gateway.os, 'open', side_effect=opened), \
                mock.patch.object(gateway.os, 'read', side_effect=read), \
                mock.patch.object(gateway, '_bounded_owned_command', return_value=b'{}'):
            self.assertEqual(self.controller._run(['/fixture']), {})
        self.assertEqual(len(flags), 1)
        self.assertTrue(flags[0] & os.O_NOFOLLOW and flags[0] & os.O_NONBLOCK)
        self.assertTrue(sizes and all(0 < size <= 65536 for size in sizes))

    def test_executable_replaced_by_fifo_refuses_before_read_or_spawn(self):
        path = self.directory.name + '/fifo'; os.mkfifo(path)
        original_open = os.open; descriptors = []
        def replaced(unused_path, flags):
            fd = original_open(path, flags); descriptors.append(fd); return fd
        with mock.patch.object(gateway.os, 'open', side_effect=replaced), \
                mock.patch.object(gateway.os, 'read', side_effect=AssertionError('FIFO read')), \
                mock.patch.object(gateway, '_bounded_owned_command') as run:
            with self.assertRaisesRegex(gateway.NativeContractError, 'executable changed'):
                self.controller._run(['/unused'])
            run.assert_not_called()
        with self.assertRaises(OSError): os.fstat(descriptors[0])


if __name__ == '__main__': unittest.main()
