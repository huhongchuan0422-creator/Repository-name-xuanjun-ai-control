"""Real pipe/process protocol fixtures; never account/inference evidence."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from codex_app_server_worker import CodexAppServerWorker


SCRIPT = r'''
import json, sys, time
case = json.loads(sys.argv[1])
def send(value):
    sys.stdout.write(json.dumps(value) + '\n'); sys.stdout.flush()
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialized': continue
    identifier = request['id']
    if method == 'initialize': result = {}
    elif method == 'account/read':
        result = {'account': {'type': case.get('auth', 'chatgpt'), 'email': 'private@example.com'},
                  'requiresOpenaiAuth': True}
    elif method == 'thread/start':
        result = {'thread': {'id': 'thread-1', 'modelProvider': 'openai'},
                  'model': case.get('model', request['params']['model']),
                  'modelProvider': case.get('provider', 'openai')}
        if case.get('missing_model'): result.pop('model')
    elif method == 'turn/start':
        send({'id': identifier, 'result': {'turn': {'id': 'turn-1', 'status': 'inProgress'}}})
        if case.get('hang'): time.sleep(60)
        if case.get('flood'):
            sys.stdout.write('x' * 3000000); sys.stdout.flush(); time.sleep(60)
        if case.get('request'):
            send({'id': 100, 'method': 'item/commandExecution/requestApproval',
                  'params': {'command': 'secret_command'}})
            time.sleep(60)
        if case.get('reroute'):
            send({'method': 'model/rerouted', 'params': {'threadId': 'thread-1',
                  'turnId': 'turn-1', 'fromModel': request['params']['model'], 'toModel': 'gpt-6-astra'}})
        if case.get('tool'):
            send({'method': 'item/started', 'params': {'threadId': 'thread-1', 'turnId': 'turn-1',
                  'item': {'id': 'tool-1', 'type': case['tool']}}})
        item = {'method': 'item/completed', 'params': {'threadId': case.get('thread_id', 'thread-1'),
                'turnId': case.get('turn_id', 'turn-1'),
                'item': {'id': 'message-1', 'type': 'agentMessage',
                         'text': case.get('text', 'verified fixture output')}}}
        send(item)
        if case.get('duplicate'): send(item)
        send({'method': 'turn/completed', 'params': {'threadId': 'thread-1',
              'turn': {'id': 'turn-1', 'status': case.get('status', 'completed'), 'error': None}}})
        continue
    else: sys.exit(1)
    send({'id': identifier, 'result': result})
'''


class AppServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = os.path.join(self.directory.name, 'work')
        os.mkdir(self.work)
        self.calls = []

    def worker(self, case=None, sandbox='workspace-write', model='gpt-5.6-sol'):
        def runner(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return subprocess.Popen([sys.executable, '-c', SCRIPT, json.dumps(case or {})], **kwargs)
        return CodexAppServerWorker('/usr/bin/codex', self.work,
            self.directory.name + '/home', self.directory.name + '/auth',
            '/usr/bin:/bin', sandbox=sandbox, runner=runner, model=model)

    def test_native_response_evidence_and_fixture_never_live_pass(self):
        for model in ('gpt-5.6-sol',):
            result = self.worker(model=model).run('implement approved function')
            self.assertEqual(result['status'], 'COMPLETED')
            self.assertTrue(result['model_verified'])
            self.assertEqual((result['model'], result['provider']), (model, 'openai'))
            self.assertEqual(result['model_evidence_source'], 'APP_SERVER_THREAD_AND_TURN')
            self.assertTrue(result['simulated'])
            self.assertFalse(result['real_execution'])
            self.assertFalse(result['production_pass'])
            self.assertNotIn('private@example.com', str(result))

    def test_disallowed_model_is_rejected_before_transport_start(self):
        with self.assertRaises(ValueError):
            self.worker(model='gpt-6.1-sol')
        self.assertEqual(self.calls, [])

    def test_account_rejects_api_key_unknown_and_no_login(self):
        for auth in ('apiKey', 'amazonBedrock', 'UNKNOWN', None):
            result = self.worker({'auth': auth}).run('test')
            self.assertEqual(result['status'], 'OAUTH_ROUTE_UNCONFIRMED')
            self.assertFalse(result['model_verified'])
        self.assertEqual(len(self.calls), 4)  # One spawn, no alternate auth/retry.

    def test_requested_or_agent_claim_cannot_fabricate_model_evidence(self):
        for case in ({'missing_model': True, 'text': 'I used openai gpt-5.6-sol'},
                     {'model': 'gpt-6.1-sol'}, {'model': 'gpt-6-astra'},
                     {'provider': 'other'}):
            result = self.worker(case).run('test')
            self.assertEqual(result['status'], 'MODEL_EVIDENCE_NOT_VERIFIED')
            self.assertFalse(result['model_verified'])

    def test_foreign_thread_or_turn_and_duplicate_item_are_rejected(self):
        for case in ({'thread_id': 'other'}, {'turn_id': 'other'}, {'duplicate': True}):
            result = self.worker(case).run('test')
            self.assertNotEqual(result['status'], 'COMPLETED')
            self.assertFalse(result['model_verified'])

    def test_reroute_and_unapproved_tools_stop_without_replay(self):
        cases = [{'reroute': True}] + [{'tool': name} for name in
                 ('collabToolCall', 'mcpToolCall', 'dynamicToolCall')]
        for case in cases:
            result = self.worker(case).run('test')
            self.assertIn(result['status'], ('MODEL_ROUTE_CHANGED', 'TOOL_ROUTE_NOT_AUTHORIZED'))
            self.assertFalse(result['model_verified'])
        self.assertEqual(len(self.calls), len(cases))

    def test_failed_or_interrupted_turn_never_completed(self):
        for status in ('failed', 'interrupted'):
            result = self.worker({'status': status}).run('test')
            self.assertEqual(result['status'], 'TURN_FAILED')
            self.assertFalse(result['turn_completed'])

    def test_server_request_does_not_get_permission_or_payload_leak(self):
        result = self.worker({'request': True}).run('test')
        self.assertEqual(result['status'], 'HUMAN_INPUT_REQUIRED')
        self.assertNotIn('secret_command', str(result))

    def test_timeout_heartbeat_and_lease_loss_bound_process(self):
        beats = []
        result = self.worker({'hang': True}).run('test', timeout_seconds=0.2,
                   heartbeat=lambda: beats.append(1), heartbeat_seconds=0.02)
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertGreater(len(beats), 1)
        count = len(self.calls)
        result = self.worker().run('test', lease_check=lambda: False)
        self.assertEqual(result['status'], 'LEASE_LOST')
        self.assertEqual(len(self.calls), count)

    def test_output_limit_and_redaction(self):
        self.assertEqual(self.worker({'flood': True}).run('test')['status'], 'OUTPUT_LIMIT')
        result = self.worker({'text': 'password=private sk-abcdefghijklmnop'}).run('test')
        self.assertNotIn('private', result['output'])
        self.assertNotIn('sk-abcdefghijklmnop', result['output'])

    def test_auth_home_separation_and_explicit_sandbox(self):
        with self.assertRaises(ValueError):
            CodexAppServerWorker('/usr/bin/codex', self.work, self.work,
                                 self.work + '/auth', '/usr/bin')
        worker = self.worker()
        self.assertEqual(worker._sandbox_policy()['writableRoots'], [self.work])
        self.assertFalse(worker._sandbox_policy()['networkAccess'])
        self.assertNotIn(worker.home, worker._sandbox_policy()['readOnlyAccess']['readableRoots'])
        self.assertNotIn('OPENAI_API_KEY', worker.build_env())
        self.assertIn('features.multi_agent=false', worker.build_argv())

    def test_shared_worker_cannot_start_second_transport(self):
        worker = self.worker()
        worker._run_lock.acquire()
        try:
            self.assertEqual(worker.run('test')['status'], 'WORKER_BUSY')
            self.assertEqual(self.calls, [])
        finally:
            worker._run_lock.release()


if __name__ == '__main__':
    unittest.main()
