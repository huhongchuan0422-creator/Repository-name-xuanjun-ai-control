import json
import subprocess
import unittest
from types import SimpleNamespace
from ssh_transport import ExistingSSHChannel, ChannelHold, SOURCE, TARGET


class Tests(unittest.TestCase):
    def channel(self, body=None, code=0):
        self.calls = []
        def run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return SimpleNamespace(returncode=code, stdout=body, stderr=b'')
        return ExistingSSHChannel(SOURCE, run)

    def test_fixed_existing_channel(self):
        body = json.dumps({'host': TARGET, 'operation': 'status'}).encode()
        result = self.channel(body).query('status')
        self.assertEqual(result['host'], TARGET)
        self.assertEqual(len(self.calls), 1)
        self.assertIn('StrictHostKeyChecking=yes', self.calls[0][0])
        self.assertEqual(self.calls[0][0][-1],
                         '/usr/bin/sudo -n /usr/local/sbin/pr99-migration-target status')

    def test_no_uninstalled_mutation(self):
        with self.assertRaisesRegex(ChannelHold, 'NOT_INSTALLED'):
            self.channel().query('start')
        self.assertEqual(self.calls, [])

    def test_wrong_host(self):
        with self.assertRaises(ChannelHold):
            ExistingSSHChannel(TARGET)

    def test_nonzero_not_success(self):
        channel = self.channel(b'{}', 1)
        with self.assertRaisesRegex(ChannelHold, 'NONZERO'):
            channel.query('status')
        self.assertEqual(len(self.calls), 1)

    def test_timeout_no_retry(self):
        calls = []
        def run(*args, **kwargs):
            calls.append(1)
            raise subprocess.TimeoutExpired('ssh', 45)
        with self.assertRaisesRegex(ChannelHold, 'UNKNOWN'):
            ExistingSSHChannel(SOURCE, run).query('status')
        self.assertEqual(len(calls), 1)

    def test_wrong_target(self):
        with self.assertRaisesRegex(ChannelHold, 'BINDING'):
            self.channel(b'{"host":"other","operation":"status"}').query('status')

    def test_duplicate_key(self):
        with self.assertRaisesRegex(ChannelHold, 'DUPLICATE'):
            self.channel(b'{"host":"a","host":"b"}').query('status')

    def test_invalid_output(self):
        with self.assertRaisesRegex(ChannelHold, 'INVALID_JSON'):
            self.channel(b'PASS').query('status')


if __name__ == '__main__':
    unittest.main()
