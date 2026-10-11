import json
import os
import subprocess
import sys
import tempfile
import unittest
from codex_worker import CodexWorker, MODEL, redact


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)

    def worker(self, script=None, sandbox='read-only'):
        runner = None
        if script is not None:
            def runner(argv, **kwargs):
                return subprocess.Popen([sys.executable, '-c', script], **kwargs)
        return CodexWorker('/usr/bin/codex', self.root.name,
                           self.root.name, self.root.name + '/codex',
                           '/usr/bin:/bin', sandbox=sandbox, runner=runner)

    def script(self, events, code=0):
        payload = '\n'.join(json.dumps(e) for e in events)
        return 'import sys; sys.stdout.write(%r); sys.exit(%d)' % (payload, code)

    def success_events(self, text='real test output'):
        return [{'type': 'item.completed', 'item': {
            'type': 'agent_message', 'text': text}}, {'type': 'turn.completed'}]

    def test_model_sandbox_and_no_bypass(self):
        args = self.worker().build_argv()
        self.assertEqual(args[args.index('--model') + 1], MODEL)
        self.assertEqual(args[args.index('--model') + 1], 'gpt-5.6-sol')
        self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
        self.assertNotIn('--full-auto', args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)
        self.assertNotIn('--skip-git-repo-check', args)
        self.assertEqual(args[-1], '-')
        self.assertIn('model_provider="openai"', args)
    def test_only_current_owner_model_is_selectable(self):
        worker = CodexWorker('/usr/bin/codex', self.root.name,
                             self.root.name, self.root.name + '/codex',
                             '/usr/bin:/bin', model='gpt-5.6-sol')
        args = worker.build_argv()
        self.assertEqual(args[args.index('--model') + 1], 'gpt-5.6-sol')
        for model in ('gpt-6.1-sol', 'gpt-6-astra', 'gpt-6.1', 'openai/*', ''):
            with self.assertRaises(ValueError):
                CodexWorker('/usr/bin/codex', self.root.name,
                            self.root.name, self.root.name + '/codex',
                            '/usr/bin:/bin', model=model)
    def test_disallowed_model_is_rejected_before_process_start(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            raise AssertionError('disallowed model must not start a process')
        with self.assertRaises(ValueError):
            CodexWorker('/usr/bin/codex', self.root.name,
                        self.root.name, self.root.name + '/codex',
                        '/usr/bin:/bin', model='gpt-6.1-sol', runner=runner)
        self.assertEqual(calls, [])
    def test_requested_model_is_not_returned_model_evidence(self):
        result = self.worker(self.script(self.success_events(
            'I used gpt-6.1-sol from openai'))).run('test')
        self.assertEqual(result['requested_model'], MODEL)
        self.assertEqual(result['model'], 'UNKNOWN')
        self.assertEqual(result['provider'], 'UNKNOWN')
        self.assertFalse(result['model_verified'])

    def test_environment_does_not_inherit_secrets(self):
        os.environ['TEST_PRODUCTION_SECRET'] = 'never inherit'
        self.addCleanup(os.environ.pop, 'TEST_PRODUCTION_SECRET', None)
        env = self.worker().build_env()
        self.assertEqual(set(env), {'PATH', 'HOME', 'CODEX_HOME', 'LANG'})
        self.assertNotIn('TEST_PRODUCTION_SECRET', env)

    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            self.worker(sandbox='danger-full-access')
        with self.assertRaises(ValueError):
            CodexWorker('codex', '/tmp', '/tmp', '/tmp/codex', '/usr/bin')
        with self.assertRaises(ValueError):
            CodexWorker('/usr/bin/codex', '/tmp', '/tmp', '/tmp/codex', ':/usr/bin')

    def test_success_requires_real_output_and_mock_never_production_pass(self):
        result = self.worker(self.script(self.success_events())).run('test')
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['output'], 'real test output')
        self.assertTrue(result['simulated'])
        self.assertFalse(result['real_execution'])
        self.assertFalse(result['production_pass'])

    def test_missing_completion(self):
        result = self.worker(self.script(self.success_events()[:1])).run('test')
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['output'], '')

    def test_empty_output(self):
        result = self.worker(self.script([{'type': 'turn.completed'}])).run('test')
        self.assertEqual(result['status'], 'EMPTY_OUTPUT')

    def test_nonzero_exit_even_with_completion(self):
        result = self.worker(self.script(self.success_events(), 2)).run('test')
        self.assertEqual(result['status'], 'FAILED')

    def test_turn_failed_even_with_completion(self):
        events = self.success_events() + [{'type': 'turn.failed', 'error': 'secret'}]
        result = self.worker(self.script(events)).run('test')
        self.assertEqual(result['status'], 'FAILED')
        self.assertNotIn('secret', str(result))

    def test_bad_json_fails_closed(self):
        result = self.worker("print('not JSON secret')").run('test')
        self.assertEqual(result['status'], 'INVALID_JSON')
        self.assertNotIn('secret', str(result))

    def test_timeout_kills_process(self):
        result = self.worker('import time; time.sleep(60)').run('test', timeout_seconds=0.1)
        self.assertEqual(result['status'], 'TIMEOUT')

    def test_timeout_kills_descendant(self):
        pidfile = self.root.name + '/child.pid'
        script = ('import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c",'
                  '"import time; time.sleep(60)"]); open(%r,"w").write(str(p.pid));'
                  'time.sleep(60)') % pidfile
        result = self.worker(script).run('test', timeout_seconds=0.3)
        self.assertEqual(result['status'], 'TIMEOUT')
        with open(pidfile) as handle:
            pid = int(handle.read())
        # Container PID 1 may leave an orphan zombie; a zombie cannot execute.
        try:
            with open('/proc/%d/stat' % pid) as handle:
                state = handle.read().split()[2]
            self.assertEqual(state, 'Z')
        except FileNotFoundError:
            pass

    def test_lease_lost_prevents_spawn(self):
        result = self.worker('raise Exception("must not spawn")').run(
            'test', lease_check=lambda: False)
        self.assertEqual(result['status'], 'LEASE_LOST')

    def test_lease_lost_mid_run(self):
        calls = []
        def lease():
            calls.append(1)
            return len(calls) < 3
        result = self.worker('import time; time.sleep(60)').run('test', lease_check=lease)
        self.assertEqual(result['status'], 'LEASE_LOST')

    def test_heartbeat_runs_without_output(self):
        calls = []
        script = 'import time; time.sleep(0.25); ' + self.script(self.success_events())
        result = self.worker(script).run('test', heartbeat=lambda: calls.append(1),
                                        heartbeat_seconds=0.05)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertGreaterEqual(len(calls), 2)

    def test_callback_exception_no_secret_leak(self):
        def heartbeat():
            raise RuntimeError('access_token=private')
        result = self.worker('import time; time.sleep(60)').run('test', heartbeat=heartbeat)
        self.assertEqual(result['status'], 'CALLBACK_ERROR')
        self.assertNotIn('private', str(result))

    def test_output_limit(self):
        result = self.worker('import sys; sys.stdout.write("x" * 3000000)').run('test')
        self.assertEqual(result['status'], 'OUTPUT_LIMIT')

    def test_prompt_goes_to_stdin_not_commandline(self):
        script = 'import sys; text=sys.stdin.read(); ' + self.script(self.success_events())
        result = self.worker(script).run('private prompt')
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertNotIn('private prompt', self.worker().build_argv())

    def test_redaction(self):
        value = redact('Bearer private-token api_key=private sk-abcdefghijk password="hello"')
        self.assertNotIn('private', value)
        self.assertNotIn('abcdefghijk', value)
        self.assertNotIn('hello', value)

    def test_known_service_tokens_redacted(self):
        tokens = [
            '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi',
            'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890',
            'github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890_abc',
        ]
        for token in tokens:
            self.assertNotIn(token, redact('url/token=' + token))
            self.assertIn('[REDACTED]', redact(token))

    def test_json_credentials_redacted_and_json_preserved(self):
        fields = {
            'access_token': 'private-access-value',
            'refresh_token': 'private-refresh-value',
            'api_key': 'private-api-value',
            'API key': 'private-spaced-api-value',
            'password': 'private-password-value',
            'secret': 'private-secret-value',
            'bot_token': 'private-bot-value',
            'github_token': 'private-github-value',
        }
        masked = json.loads(redact(json.dumps(fields)))
        self.assertEqual(set(masked), set(fields))
        self.assertEqual(set(masked.values()), {'[REDACTED]'})
        for value in fields.values():
            self.assertNotIn(value, json.dumps(masked))

    def test_escaped_json_secret_fully_redacted(self):
        original = {'password': 'private"escaped\\value'}
        masked = json.loads(redact(json.dumps(original)))
        self.assertEqual(masked, {'password': '[REDACTED]'})

    def test_final_output_service_and_json_credentials_redacted(self):
        token = '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi'
        message = json.dumps({'access_token': 'private-final-value',
                              'telegram_url': 'https://api.telegram.org/bot' + token})
        result = self.worker(self.script(self.success_events(message))).run('test')
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertNotIn('private-final-value', result['output'])
        self.assertNotIn(token, result['output'])
        self.assertEqual(json.loads(result['output'])['access_token'], '[REDACTED]')

    def test_large_prompt_rejected(self):
        with self.assertRaises(ValueError):
            self.worker().run('x' * 300000)


if __name__ == '__main__':
    unittest.main()
