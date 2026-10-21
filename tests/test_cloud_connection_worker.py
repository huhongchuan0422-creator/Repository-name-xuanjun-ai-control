import base64
import hashlib
import json
import unittest

from production.cloud_connection.queue import Hold, canonical
from production.cloud_connection.worker import (HOSTS, PREFIX, execute_ready,
    fixed_command, query_existing, receive, validate_result)
import test_cloud_connection_queue as queue_cases
ACTOR, NOW, request = queue_cases.ACTOR, queue_cases.NOW, queue_cases.request



def response(r, state='Success', exit_code=0):
    body = {'hostname': HOSTS[r['target']], 'uid': 1000,
            'nonce': hashlib.sha256(canonical(r).encode()).hexdigest()}
    if r['operation'] == 'fetch_os_release':
        data = b'NAME=non-sensitive-fixture\n'
        body.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                    base64=base64.b64encode(data).decode())
    return {'InvocationResult': {'InvokeId': 't-one',
        'InstanceId': '09207081a09a466aa0079b07b5e3e7ca',
        'InvocationStatus': state, 'ExitCode': exit_code,
        'Output': base64.b64encode(json.dumps(body).encode()).decode()}}


class TransportTests(unittest.TestCase):
    setUp = queue_cases.ConnectionQueueTests.setUp
    tearDown = queue_cases.ConnectionQueueTests.tearDown
    submit = queue_cases.ConnectionQueueTests.submit

    def test_dispatch_intent_precedes_network(self):
        self.submit()
        q = self.q
        class Cloud:
            def call(self, target, action, extra):
                assert q.inspect('job-1')['state'] == 'DISPATCHING'
                raise TimeoutError('not a real network call')
        with self.assertRaises(TimeoutError):
            execute_ready(q, Cloud(), 'job-1', NOW)
        self.assertEqual(q.inspect('job-1')['state'], 'UNKNOWN')

    def test_receive_uses_api_actor_not_body(self):
        class Feed:
            def comments(self, since):
                return [{'id': 1, 'body': PREFIX + json.dumps(request()),
                         'user': {'id': 123}, 'created_at': 'x', 'updated_at': 'x'},
                        {'id': 2, 'body': PREFIX + json.dumps(request()),
                         'user': {'id': ACTOR}, 'created_at': 'x', 'updated_at': 'x'}]
        out = receive(Feed(), self.q, 'x', NOW)
        self.assertEqual([x['state'] for x in out], ['REJECTED_ACTOR', 'READY'])

    def test_edited_request_rejected(self):
        class Feed:
            def comments(self, since):
                return [{'id': 1, 'body': PREFIX + json.dumps(request()),
                         'user': {'id': ACTOR}, 'created_at': 'x', 'updated_at': 'y'}]
        self.assertEqual(receive(Feed(), self.q, 'x', NOW)[0]['state'], 'REJECTED_EDIT')

    def test_fixed_command_has_no_user_shell(self):
        command = fixed_command(request())
        self.assertIn('/usr/bin/python3 -I -B', command)
        self.assertNotIn('sudo', command)
        self.assertNotIn('curl', command)

    def test_encoded_result(self):
        receipt, data = validate_result(request(), 't-one', response(request()))
        self.assertEqual(receipt['state'], 'SUCCESS')
        self.assertIsNone(data)

    def test_wrong_invoke(self):
        with self.assertRaisesRegex(Hold, 'TARGET'):
            validate_result(request(), 't-two', response(request()))

    def test_wrong_instance(self):
        r = response(request())
        r['InvocationResult']['InstanceId'] = 'wrong'
        with self.assertRaisesRegex(Hold, 'TARGET'):
            validate_result(request(), 't-one', r)

    def test_no_success_for_pending(self):
        self.assertEqual(validate_result(request(), 't-one', response(request(), 'Running')), (None, None))

    def test_nonzero_exit_is_failed(self):
        self.assertEqual(validate_result(request(), 't-one', response(request(), 'Failed', 1))[0]['state'], 'FAILED')

    def test_wrong_remote_identity(self):
        v = response(request())
        b = json.loads(base64.b64decode(v['InvocationResult']['Output']))
        b['hostname'] = 'wrong'
        v['InvocationResult']['Output'] = json.dumps(b)
        with self.assertRaisesRegex(Hold, 'IDENTITY'):
            validate_result(request(), 't-one', v)

    def test_file_digest(self):
        r = request()
        r.update(operation='fetch_os_release', arguments={'path': '/etc/os-release', 'max_bytes': 65536})
        receipt, data = validate_result(r, 't-one', response(r))
        self.assertEqual(hashlib.sha256(data).hexdigest(), receipt['sha256'])

    def test_no_public_file_fallback(self):
        r = request()
        r.update(operation='fetch_os_release', arguments={'path': '/etc/os-release', 'max_bytes': 65536})
        self.submit(r)
        self.q.begin_dispatch('job-1', NOW)
        self.q.record_invoke('job-1', 't-one')
        class Cloud:
            def call(self, target, action, extra):
                assert action == 'DescribeInvocationResult'
                return response(r)
        def missing_sink(*args):
            raise Hold('PRIVATE_FILE_SINK_NOT_ENROLLED')
        with self.assertRaisesRegex(Hold, 'PRIVATE_FILE'):
            query_existing(self.q, Cloud(), 'job-1', missing_sink)
        self.assertNotEqual(self.q.inspect('job-1')['state'], 'SUCCESS')


if __name__ == '__main__':
    unittest.main()
