"""Synthetic, offline operation receipts. No production enrollment or cloud I/O."""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from production.cloud_connection.queue import Queue, Hold, canonical, TARGETS
from production.cloud_connection.worker import execute_ready, query_existing, HOSTS, fixed_command
from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy, SEALED
from production.cloud_connection.runtime import approved_object_hook, code_pin
from production.cloud_connection.private_transfer import bound_job, export_chunk

NOW = 1800000000
PIN = 'a' * 64
ACTOR = 332398908


class ApprovedObjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.body = b'synthetic inert source\n'
        obj = {'ref': 'fixture-object', 'root_ref': 'fixture-root', 'relative_path': 'package.json',
               'bytes': len(self.body), 'sha256': hashlib.sha256(self.body).hexdigest()}
        catalog = {'schema': 1, 'project': 'fixture-analysis', 'approval_ref': 'offline-fixture-not-approval',
                   'source_commit': 'b' * 40, 'executor_sha256': PIN, 'target': 'uk',
                   'valid_from': NOW - 10, 'valid_until': NOW + 100,
                   'recipients': ['fixture-reader'], 'objects': [obj]}
        self.binding = {'schema': 1, 'catalog': catalog,
                        'catalog_sha256': hashlib.sha256(canonical(catalog).encode()).hexdigest(),
                        'policy': {'project': 'fixture-analysis', 'max_objects': 19, 'max_object_bytes': 53969,
                                   'max_total_bytes': 93592, 'recipients': ['fixture-reader'], 'root_refs': ['fixture-root']},
                        'roots': {'fixture-root': ['/synthetic-not-enrolled', 1002]},
                        'recipient_id': 'fixture-reader', 'requests': {'fixture-object': 'fixture-request'},
                        'execution_user': 'fixture_reader', 'execution_uid': 1002,
                        'reader_sha256': hashlib.sha256((Path(__file__).resolve().parents[1] / 'production/cloud_connection/private_transfer.py').read_bytes()).hexdigest()}
        self.policy = self.make_policy()
        self.request = {'schema': 1, 'request_id': 'fixture-request', 'project': 'fixture-analysis',
                        'target': 'uk', 'operation': 'fetch_approved_object', 'executor_sha256': PIN,
                        'arguments': {'manifest_sha256': self.policy.catalog.sha, 'object_ref': 'fixture-object',
                                      'recipient_id': 'fixture-reader'}, 'expires_unix': NOW + 60}
        self.q = Queue(self.tmp.name + '/queue.sqlite', PIN, {ACTOR}, approved_objects=self.policy)
        self.calls = []

    def tearDown(self):
        self.q.close()
        self.tmp.cleanup()

    def make_policy(self, binding=None):
        raw = canonical(self.binding if binding is None else binding).encode()
        return ApprovedObjectsPolicy(raw, hashlib.sha256(raw).hexdigest())

    def response(self):
        item = self.binding['catalog']['objects'][0]
        v = {'hostname': HOSTS['uk'], 'uid': 1002,
             'nonce': hashlib.sha256(canonical(self.request).encode()).hexdigest(),
             'manifest_sha256': self.policy.catalog.sha, 'object_ref': item['ref'],
             'recipient_id': 'fixture-reader', 'bytes': item['bytes'], 'sha256': item['sha256']}
        return {'InvocationResult': {'InvokeId': 'fixture-invoke', 'InstanceId': TARGETS['uk'][2],
                                    'InvocationStatus': 'Success', 'ExitCode': 0, 'Output': canonical(v)}}

    def cloud(self, response=None, lost=False):
        outer = self
        class Cloud:
            def call(self, target, action, args):
                outer.calls.append((target, action))
                if action == 'RunCommand':
                    if lost:
                        raise OSError('synthetic uncertain transport')
                    return {'InvokeId': 'fixture-invoke'}
                return outer.response() if response is None else response
        return Cloud()

    def submit(self):
        return self.q.submit(canonical(self.request), ACTOR, NOW)

    def start(self):
        self.submit()
        execute_ready(self.q, self.cloud(), 'fixture-request', NOW)

    def test_default_off_submit(self):
        self.q.approved_objects = None
        with self.assertRaises(Hold): self.submit()

    def test_default_off_dispatch(self):
        self.submit()
        self.q.approved_objects = None
        with self.assertRaises(Hold): execute_ready(self.q, self.cloud(), 'fixture-request', NOW)
        self.assertEqual(self.calls, [])

    def test_default_off_query(self):
        self.start()
        self.q.approved_objects = None
        before = len(self.calls)
        with self.assertRaises(Hold): query_existing(self.q, self.cloud(), 'fixture-request', lambda *a: self.fail('sink'))
        self.assertNotEqual(self.q.inspect('fixture-request')['state'], 'SUCCESS')
        self.assertEqual(len(self.calls), before)

    def test_actual_queue_receipt_unlocks_only_bound_job(self):
        self.start()
        result = query_existing(self.q, self.cloud(), 'fixture-request', lambda *a: self.fail('body sink'))
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(bound_job(self.q.db, self.policy.catalog, 'fixture-request', 'fixture-object', 'fixture-reader'), 'fixture-invoke')
        with self.assertRaises(Hold): bound_job(self.q.db, self.policy.catalog, 'fixture-request', 'fixture-object', 'other-reader')
        with patch('production.cloud_connection.private_transfer.read_object', return_value=self.body) as read:
            value = export_chunk(self.q.db, self.policy.catalog, self.binding['roots'], 'fixture-request', 'fixture-object', 'fixture-reader', 0, NOW)
            self.assertEqual(base64.b64decode(value['data']), self.body)
            read.assert_called_once()

    def test_remote_success_does_not_prove_local_source_root(self):
        self.start()
        query_existing(self.q, self.cloud(), 'fixture-request', lambda *a: self.fail('sink'))
        with patch('production.cloud_connection.private_transfer.read_object', side_effect=Hold('ROOT_NOT_PRESENT')):
            with self.assertRaises(Hold): export_chunk(self.q.db, self.policy.catalog, self.binding['roots'], 'fixture-request', 'fixture-object', 'fixture-reader', 0, NOW)

    def test_replay_and_unknown_never_dispatch_again(self):
        self.submit()
        with self.assertRaises(OSError): execute_ready(self.q, self.cloud(lost=True), 'fixture-request', NOW)
        self.assertEqual(self.q.inspect('fixture-request')['state'], 'UNKNOWN')
        with self.assertRaises(Hold): execute_ready(self.q, self.cloud(), 'fixture-request', NOW)
        self.assertEqual(len(self.calls), 1)

    def test_success_requery_no_new_cloud_call(self):
        self.start()
        query_existing(self.q, self.cloud(), 'fixture-request', lambda *a: self.fail('sink'))
        count = len(self.calls)
        query_existing(self.q, self.cloud(), 'fixture-request', lambda *a: self.fail('sink'))
        self.assertEqual(len(self.calls), count)
        with self.assertRaises(Hold): execute_ready(self.q, self.cloud(), 'fixture-request', NOW)

    def test_wrong_actor_and_request_bindings(self):
        with self.assertRaises(Hold): self.q.submit(canonical(self.request), 7, NOW)
        for key, value in [('request_id', 'renamed-request'), ('project', 'other'), ('target', 'domestic'),
                           ('operation', 'probe'), ('executor_sha256', 'c' * 64)]:
            r = copy.deepcopy(self.request); r[key] = value
            with self.subTest(key=key), self.assertRaises(Hold): self.policy.validate(r, ACTOR, NOW)
        for key, value in [('manifest_sha256', 'c' * 64), ('object_ref', 'other'), ('recipient_id', 'other')]:
            r = copy.deepcopy(self.request); r['arguments'][key] = value
            with self.subTest(key=key), self.assertRaises(Hold): self.policy.validate(r, ACTOR, NOW)

    def test_request_cannot_supply_path_or_identity(self):
        for key in ('path', 'root_ref', 'uid', 'command', '_meta'):
            r = copy.deepcopy(self.request); r['arguments'][key] = '/etc/passwd'
            with self.subTest(key=key), self.assertRaises(Hold): self.policy.command(r)

    def test_expiry_and_future_window(self):
        for now in (NOW - 11, NOW + 100):
            with self.assertRaises(Hold): self.policy.validate(self.request, ACTOR, now)
        r = copy.deepcopy(self.request); r['expires_unix'] = NOW + 101
        with self.assertRaises(Hold): self.policy.validate(r, ACTOR, NOW)

    def test_binding_hash_fields_budget_and_sealed(self):
        raw = canonical(self.binding).encode()
        with self.assertRaises(Hold): ApprovedObjectsPolicy(raw, '0' * 64)
        for key, value in [('max_objects', 20), ('max_total_bytes', 93593), ('max_object_bytes', 53970), ('max_objects', True)]:
            b = copy.deepcopy(self.binding); b['policy'][key] = value
            with self.subTest(key=key), self.assertRaises(Hold): self.make_policy(b)
        b = copy.deepcopy(self.binding); b['requests']['fixture-object'] = SEALED
        with self.assertRaises(Hold): self.make_policy(b)
        b = copy.deepcopy(self.binding); b['extra'] = True
        with self.assertRaises(Hold): self.make_policy(b)

    def test_root_and_execution_identity_validation(self):
        for root in ('relative', '/', '/safe/../other'):
            b = copy.deepcopy(self.binding); b['roots']['fixture-root'][0] = root
            with self.subTest(root=root), self.assertRaises(Hold): self.make_policy(b)
        for user in ('root;id', '-root', 'root\n'):
            b = copy.deepcopy(self.binding); b['execution_user'] = user
            with self.assertRaises(Hold): self.make_policy(b)

    def test_command_is_metadata_only_and_reader_is_original(self):
        command = self.policy.command(self.request)
        argv = shlex.split(command['CommandContent'])
        self.assertEqual(argv[:5], ['/usr/bin/python3', '-I', '-B', '-S', '-c'])
        code = argv[5]
        ast.parse(code)
        import inspect
        from production.cloud_connection import private_transfer
        self.assertIn(inspect.getsource(private_transfer.read_object), code)
        self.assertNotIn('base64', code)
        self.assertNotIn('subprocess', code)
        self.assertEqual(command['WorkingUser'], 'fixture_reader')
        self.assertEqual(command['Timeout'], 45)
        with self.assertRaises(Hold): fixed_command(self.request)
        r = copy.deepcopy(self.request); r['operation'] = 'probe'
        with self.assertRaises(Hold): self.policy.command(r)
        with self.assertRaises(Hold): self.policy.result(r, 'fixture-invoke', self.response())

    def test_wrong_remote_metadata_never_success(self):
        for key, value in [('hostname', 'wrong'), ('uid', True), ('nonce', 'wrong'), ('bytes', True),
                           ('sha256', '0' * 64), ('recipient_id', 'wrong'), ('object_ref', 'other'), ('manifest_sha256', '0' * 64)]:
            response = self.response(); v = json.loads(response['InvocationResult']['Output']); v[key] = value
            response['InvocationResult']['Output'] = canonical(v)
            with self.subTest(key=key), self.assertRaises(Hold): self.policy.result(self.request, 'fixture-invoke', response)
        response = self.response(); v = json.loads(response['InvocationResult']['Output']); v['base64'] = 'SECRET'
        response['InvocationResult']['Output'] = canonical(v)
        with self.assertRaises(Hold): self.policy.result(self.request, 'fixture-invoke', response)

    def test_result_target_status_exit_and_pending(self):
        for key, value in [('InvokeId', 'other'), ('InstanceId', 'other')]:
            r = self.response(); r['InvocationResult'][key] = value
            with self.assertRaises(Hold): self.policy.result(self.request, 'fixture-invoke', r)
        for key, value in [('ExitCode', 1), ('InvocationStatus', 'Failed')]:
            r = self.response(); r['InvocationResult'][key] = value
            self.assertEqual(self.policy.result(self.request, 'fixture-invoke', r)[0]['state'], 'FAILED')
        r = self.response(); r['InvocationResult']['InvocationStatus'] = 'Running'
        self.assertEqual(self.policy.result(self.request, 'fixture-invoke', r), (None, None))

    def test_duplicate_and_oversize_output_rejected(self):
        for output in ('{"uid":1002,"uid":1002}', 'x' * 8193, 'invalid base64'):
            r = self.response(); r['InvocationResult']['Output'] = output
            with self.assertRaises(Hold): self.policy.result(self.request, 'fixture-invoke', r)
        r = self.response(); r['InvocationResult']['Output'] = base64.b64encode(r['InvocationResult']['Output'].encode()).decode()
        self.assertEqual(self.policy.result(self.request, 'fixture-invoke', r)[0]['state'], 'SUCCESS')

    def test_optional_host_binding_is_fixed_and_off_by_default(self):
        with patch('production.cloud_connection.runtime.protected_read', side_effect=AssertionError('off')):
            self.assertIsNone(approved_object_hook({}))
        raw = canonical(self.binding).encode()
        entry = {'metadata_ref': '/etc/xuanjun-cloud-executor/approved-objects-binding.json',
                 'metadata_sha256': hashlib.sha256(raw).hexdigest()}
        with patch('production.cloud_connection.runtime.protected_read', return_value=raw) as read:
            self.assertEqual(approved_object_hook({'approved_objects': entry}).sha, entry['metadata_sha256'])
            read.assert_called_once_with(entry['metadata_ref'], 16384)
        entry['metadata_ref'] = '/tmp/other'
        with patch('production.cloud_connection.runtime.protected_read', side_effect=AssertionError('wrong path read')):
            with self.assertRaises(Hold): approved_object_hook({'approved_objects': entry})

    def test_unknown_result_does_not_fabricate_success(self):
        self.start()
        r = self.response(); r['InvocationResult']['Output'] = '{}'
        with self.assertRaises(Hold): query_existing(self.q, self.cloud(r), 'fixture-request', lambda *a: self.fail('sink'))
        self.assertNotEqual(self.q.inspect('fixture-request')['state'], 'SUCCESS')

    def test_generated_collector_checks_identity_expiry_before_read(self):
        code = shlex.split(self.policy.command(self.request)['CommandContent'])[5]
        tree = ast.parse(code)
        tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == 'read_object')]
        compiled = compile(tree, '<synthetic-collector>', 'exec')
        for host, uid, when in [('wrong-host', 1002, NOW), (HOSTS['uk'], 0, NOW),
                                (HOSTS['uk'], 1002, NOW + 60), (HOSTS['uk'], 1002, NOW - 11)]:
            calls = []
            def fake_read(*args):
                calls.append(args)
                return self.body
            with patch('os.uname') as uname, patch('os.geteuid', return_value=uid), patch('time.time', return_value=when):
                uname.return_value.nodename = host
                with self.assertRaises(SystemExit) as caught: exec(compiled, {'read_object': fake_read})
                self.assertEqual(caught.exception.code, 2)
            self.assertEqual(calls, [])
        calls = []
        def fake_read(*args):
            calls.append(args)
            return self.body
        with patch('os.uname') as uname, patch('os.geteuid', return_value=1002), patch('time.time', return_value=NOW), patch('builtins.print') as output:
            uname.return_value.nodename = HOSTS['uk']
            exec(compiled, {'read_object': fake_read})
            emitted = json.loads(output.call_args[0][0])
        self.assertEqual(len(calls), 1)
        self.assertEqual(set(emitted), {'hostname', 'uid', 'nonce', 'manifest_sha256', 'object_ref', 'recipient_id', 'bytes', 'sha256'})
        self.assertNotIn(self.body.decode(), canonical(emitted))

    def test_collector_exception_has_no_stdout_or_traceback(self):
        code = shlex.split(self.policy.command(self.request)['CommandContent'])[5]
        tree = ast.parse(code)
        tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == 'read_object')]
        compiled = compile(tree, '<synthetic-collector>', 'exec')
        from unittest.mock import Mock
        reader = Mock(side_effect=OSError('synthetic sensitive exception not for output'))
        with patch('os.uname') as uname, patch('os.geteuid', return_value=1002), patch('time.time', return_value=NOW), patch('builtins.print') as output:
            uname.return_value.nodename = HOSTS['uk']
            with self.assertRaises(SystemExit) as caught:
                exec(compiled, {'read_object': reader})
            self.assertEqual(caught.exception.code, 2)
            output.assert_not_called()
            reader.assert_called_once()

    def test_failed_result_cannot_persist_untrusted_exit_payload(self):
        for exit_code in (True, None, 'raw-error', {'raw': 'payload'}, ['payload'], 2 ** 32):
            r = self.response(); r['InvocationResult']['InvocationStatus'] = 'Failed'
            r['InvocationResult']['ExitCode'] = exit_code
            with self.subTest(value=exit_code), self.assertRaises(Hold):
                self.policy.result(self.request, 'fixture-invoke', r)

    def test_reader_pin_and_duplicate_request_binding_rejected(self):
        b = copy.deepcopy(self.binding); b['reader_sha256'] = '0' * 64
        with self.assertRaises(Hold): self.make_policy(b).command(self.request)
        b = copy.deepcopy(self.binding)
        obj = dict(b['catalog']['objects'][0], ref='second', relative_path='other.json')
        b['catalog']['objects'].append(obj)
        b['catalog_sha256'] = hashlib.sha256(canonical(b['catalog']).encode()).hexdigest()
        b['requests']['second'] = b['requests']['fixture-object']
        with self.assertRaises(Hold): self.make_policy(b)
        self.submit()
        r = copy.deepcopy(self.request); r['expires_unix'] -= 1
        with self.assertRaises(Hold): self.q.submit(canonical(r), ACTOR, NOW)

    def test_existing_os_request_still_works_without_policy(self):
        self.q.approved_objects = None
        r = dict(self.request, request_id='old-os', operation='fetch_os_release',
                 arguments={'path': '/etc/os-release', 'max_bytes': 65536})
        self.assertEqual(self.q.submit(canonical(r), ACTOR, NOW)['state'], 'READY')


if __name__ == '__main__':
    unittest.main()
