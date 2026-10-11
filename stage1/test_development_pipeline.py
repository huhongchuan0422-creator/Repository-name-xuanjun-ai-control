"""Pipeline contract tests: simulated fixtures never imply real CLI evidence."""
import copy
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest

from codex_worker import MODEL
from development_pipeline import (DevelopmentPipeline, CliBackend, UnknownEffect,
                                  digest_spec, safe_text, failure_fingerprint)
from execution_ledger import ExecutionLedger, LeaseLost

BASE = 'a' * 40
HEAD = 'b' * 40


class Ledger(object):
    def __init__(self):
        self.cp, self.finishes, self.alive, self.assertions = {}, [], True, 0
    def assert_live(self, *ids):
        self.assertions += 1
        if not self.alive:
            raise LeaseLost('stale')
        return True
    def heartbeat(self, *ids, **kwargs):
        return self.assert_live(*ids)
    def checkpoint(self, task, owner, fence, value):
        self.assert_live(task, owner, fence)
        self.cp = copy.deepcopy(value)
    def finish(self, task, owner, fence, state, effects='unknown'):
        self.assert_live(task, owner, fence)
        self.finishes.append((state, effects))
        return state


class Backend(object):
    simulated = False
    def __init__(self):
        self.calls, self.status, self.identity, self.clean = [], 'PASS', True, True
    def hit(self, name, fence):
        fence()
        self.calls.append(name)
    def prepare(self, repo, base, branch, fence):
        self.hit('prepare', fence)
        return '/isolated/' + branch.replace('/', '-')
    def commit(self, repo, workdir, branch, fence, expected_sha=None):
        self.hit('commit', fence)
        return HEAD
    def validate_commit(self, repo, workdir, base_sha, sha, fence):
        self.hit('validate_commit', fence)
        return True
    def open_pr(self, repo, workdir, branch, sha, fence):
        self.hit('pr', fence)
        return 12
    def reconcile(self, repo, workdir, branch, sha, pr, fence):
        self.hit('reconcile', fence)
        return self.identity
    def checks(self, repo, workdir, pr, sha, fence):
        self.hit('checks', fence)
        return {'status': self.status, 'sha': sha}
    def failure_logs(self, repo, workdir, sha, fence):
        self.hit('logs', fence)
        return 'password=do-not-leak\nassert failed'
    def freeze(self, repo, workdir, branch, sha, fence):
        self.hit('freeze', fence)
        if not self.clean:
            raise UnknownEffect('dirty')
        return workdir


class Worker(object):
    def __init__(self, owner, workdir, sandbox):
        self.owner, self.workdir, self.sandbox = owner, workdir, sandbox
    def run(self, prompt, **kwargs):
        assert kwargs['lease_check']()
        kwargs['heartbeat']()
        self.owner.prompts.append((self.sandbox, prompt))
        if self.owner.lose_lease:
            self.owner.ledger.alive = False
        if self.owner.failure:
            return {'status': 'FAILED', 'model': MODEL}
        return {'status': 'COMPLETED', 'turn_completed': True, 'model': self.owner.model,
                'requested_model': self.owner.model, 'provider': 'openai',
                'model_verified': self.owner.model_verified,
                'simulated': self.owner.simulated, 'real_execution': not self.owner.simulated,
                'output': json.dumps({'verdict': self.owner.verdict, 'commit': self.owner.qa_sha})}


class Factory(object):
    def __init__(self, ledger):
        self.ledger, self.prompts = ledger, []
        self.simulated, self.failure, self.lose_lease = False, False, False
        self.model, self.verdict, self.qa_sha = MODEL, 'PASS', HEAD
        self.model_verified = True
    def __call__(self, workdir, sandbox):
        return Worker(self, workdir, sandbox)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.ledger, self.backend = Ledger(), Backend()
        self.factory = Factory(self.ledger)
        self.pipeline = DevelopmentPipeline(self.ledger, self.backend, self.factory, ['owner/repo'])
        spec = {'repo': 'owner/repo', 'type': 'CODEX_EXEC', 'prompt': 'implement function',
                'heavy': True, 'timeout_seconds': 60, 'base_sha': BASE}
        self.claim = {'task_id': 'T-1', 'worker_id': 'w', 'fence': 1, 'spec': spec,
                      'spec_hash': digest_spec(spec), 'checkpoint': {}}
    def resume(self):
        self.claim['checkpoint'] = copy.deepcopy(self.ledger.cp)
        return self.pipeline.run(self.claim)
    def test_real_contract_accepts_only_frozen_ci_and_independent_qa(self):
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['state'], 'DONE')
        self.assertFalse(result['production_pass'])
        self.assertEqual(result['checkpoint']['qa_commit'], HEAD)
        self.assertEqual([p[0] for p in self.factory.prompts], ['workspace-write', 'read-only'])
        self.assertGreater(self.ledger.assertions, 10)
    def test_mock_completion_cannot_be_real_done(self):
        self.factory.simulated = True
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['state'], 'WAITING_HUMAN')
        self.assertEqual(result['reason'], 'SIMULATED_ACCEPTANCE_ONLY')
        self.assertFalse(result['real_execution'])
    def test_unverified_model_pauses_before_commit_and_never_replays(self):
        self.factory.model_verified = False
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['state'], 'WAITING_HUMAN')
        self.assertEqual(result['reason'], 'MODEL_EVIDENCE_NOT_VERIFIED')
        self.assertNotIn('commit', self.backend.calls)
        self.assertEqual(self.ledger.cp['phase'], 'IN_FLIGHT_CODEX')
        self.resume()
        self.assertEqual(len(self.factory.prompts), 1)
    def test_verified_sole_fallback_obeys_same_ci_and_qa_gates(self):
        self.factory.model = 'gpt-5.6-sol'
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['state'], 'DONE')
        self.assertEqual(result['checkpoint']['qa_commit'], HEAD)
        self.assertFalse(result['production_pass'])
    def test_unverified_qa_cannot_accept_frozen_commit(self):
        original = self.factory.__class__.__call__
        factory = self.factory
        def worker(workdir, sandbox):
            if sandbox == 'read-only':
                factory.model_verified = False
            return original(factory, workdir, sandbox)
        self.pipeline.worker_factory = worker
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['state'], 'WAITING_HUMAN')
        self.assertEqual(result['reason'], 'QA_MODEL_EVIDENCE_NOT_VERIFIED')
        self.assertNotIn('qa_commit', result['checkpoint'])
    def test_backend_simulation_also_blocks_done(self):
        self.backend.simulated = True
        self.assertEqual(self.pipeline.run(self.claim)['state'], 'WAITING_HUMAN')
    def test_pending_ci_is_checkpointed_without_claiming_acceptance(self):
        self.backend.status = 'PENDING'
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['state'], 'RUNNING')
        self.assertEqual(self.ledger.cp['phase'], 'CI_WAIT')
        self.assertEqual(len(self.factory.prompts), 1)
        self.backend.status = 'PASS'
        self.assertEqual(self.resume()['state'], 'DONE')
        self.assertEqual(self.backend.calls.count('prepare'), 1)
    def test_three_patch_attempts_are_bounded_and_logs_redacted(self):
        self.backend.status = 'FAIL'
        # Different failing commits and diagnostics permit bounded progress.
        def commit(repo, workdir, branch, fence, expected_sha=None):
            self.backend.hit('commit', fence)
            return '%040x' % self.backend.calls.count('commit')
        def logs(repo, workdir, sha, fence):
            self.backend.hit('logs', fence)
            return 'password=do-not-leak\nassert failed at case ' + sha[-1]
        self.backend.commit, self.backend.failure_logs = commit, logs
        result = self.pipeline.run(self.claim)
        for _ in range(3):
            self.assertEqual(result['reason'], 'PATCH_READY')
            self.assertNotIn('do-not-leak', self.ledger.cp['failure_log'])
            result = self.resume()
        self.assertEqual(result['reason'], 'PATCH_LIMIT_REACHED')
        self.assertEqual(len(self.factory.prompts), 4)
        self.assertNotIn('read-only', [p[0] for p in self.factory.prompts])
        self.assertEqual(self.ledger.cp['patch_attempts'], 3)
        self.assertEqual(len(self.ledger.cp['ci_failures']), 4)

    def test_same_failure_after_one_patch_pauses_without_more_model_turns(self):
        self.backend.status = 'FAIL'
        def commit(repo, workdir, branch, fence, expected_sha=None):
            self.backend.hit('commit', fence)
            return '%040x' % self.backend.calls.count('commit')
        self.backend.commit = commit
        first = self.pipeline.run(self.claim)
        self.assertEqual(first['reason'], 'PATCH_READY')
        second = self.resume()
        self.assertEqual(second['state'], 'WAITING_HUMAN')
        self.assertEqual(second['reason'], 'REPEATED_CI_FAILURE')
        self.assertEqual(second['checkpoint']['failure_fingerprint_count'], 2)
        self.assertEqual(second['checkpoint']['patch_attempts'], 1)
        self.assertEqual(len(self.factory.prompts), 2)
        self.assertFalse(second['production_pass'])
        # Manual resume must not reinterpret the same failing SHA as new work.
        self.assertEqual(self.resume()['reason'], 'REPEATED_CI_FAILURE')
        self.assertEqual(len(self.factory.prompts), 2)
        self.assertEqual(self.ledger.cp['failure_fingerprint_count'], 2)

    def test_empty_failure_evidence_does_not_trigger_blind_patch_or_model_fallback(self):
        for log in ('', ' \n ', None, '2026-10-11T06:20:21.000Z ' + HEAD):
            self.setUp()
            self.backend.status = 'FAIL'
            self.backend.failure_logs = lambda *args: log
            result = self.pipeline.run(self.claim)
            self.assertEqual(result['state'], 'WAITING_HUMAN')
            self.assertEqual(result['reason'], 'CI_FAILURE_EVIDENCE_MISSING')
            self.assertIsNone(result['checkpoint']['failure_fingerprint'])
            self.assertEqual(result['checkpoint']['patch_attempts'], 0)
            self.assertEqual(len(self.factory.prompts), 1)

    def test_invalid_patch_budget_cannot_be_reset_by_checkpoint(self):
        for attempts in (-1, 4, True, '0'):
            self.claim['checkpoint'] = {'phase': 'NEW', 'patch_attempts': attempts}
            self.assertEqual(self.pipeline.run(self.claim)['reason'], 'PATCH_BUDGET_INVALID')
        self.assertFalse(self.backend.calls)

    def test_failure_fingerprint_normalizes_only_timestamp_and_current_commit(self):
        a = failure_fingerprint('2026-10-11T06:20:21.100Z error case 17 ' + HEAD, HEAD)
        b = failure_fingerprint('2026-10-12T08:21:22.100Z error case 17 ' + BASE, BASE)
        self.assertEqual(a, b)
        self.assertNotEqual(a, failure_fingerprint('error case 18 ' + BASE, BASE))
        self.assertEqual(failure_fingerprint('password=one\nassert failed', HEAD),
                         failure_fingerprint('password=two\nassert failed', HEAD))

    def test_real_ledger_roundtrip_preserves_failure_and_patch_budget(self):
        from test_execution_ledger import SCHEMA
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, 'tasks.db')
            with sqlite3.connect(path) as conn:
                conn.executescript(SCHEMA)
                conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                             ('T-1', 'CODEX_EXEC', 'PENDING', '[]', None, None, 0, '{}', 0))
            ledger = ExecutionLedger(path, ['owner/repo'])
            ledger.register_spec('T-1', self.claim['spec'], 'owner', True)
            factory = Factory(ledger)
            pipeline = DevelopmentPipeline(ledger, self.backend, factory, ['owner/repo'])
            claim = ledger.claim('worker', ttl=180)
            self.backend.status = 'FAIL'
            first = pipeline.run(claim)
            persisted = ledger.observation('T-1')['checkpoint']
            self.assertEqual(persisted, first['checkpoint'])
            self.assertEqual(persisted['patch_attempts'], 1)
            # A fresh pipeline process continues the persisted repair budget.
            claim['checkpoint'] = persisted
            self.backend.commit = lambda *args, **kwargs: 'c' * 40
            second = DevelopmentPipeline(ledger, self.backend, factory, ['owner/repo']).run(claim)
            self.assertEqual(second['reason'], 'REPEATED_CI_FAILURE')
            snapshot = ledger.observation('T-1')
            self.assertEqual(snapshot['state'], 'WAITING_HUMAN')
            self.assertEqual(snapshot['checkpoint']['patch_attempts'], 1)
            self.assertEqual(snapshot['checkpoint']['failure_fingerprint_count'], 2)

    def test_restarted_dispatcher_resumes_ci_without_replaying_developer(self):
        from test_execution_ledger import SCHEMA
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, 'tasks.db')
            with sqlite3.connect(path) as conn:
                conn.executescript(SCHEMA)
                conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                             ('T-1', 'CODEX_EXEC', 'PENDING', '[]', None, None, 0, '{}', 0))
            now = [1000]
            ledger = ExecutionLedger(path, ['owner/repo'], clock=lambda: now[0])
            ledger.register_spec('T-1', self.claim['spec'], 'owner', True)
            factory = Factory(ledger)
            pipeline = DevelopmentPipeline(ledger, self.backend, factory, ['owner/repo'])
            original = ledger.claim('old-worker', ttl=180)
            self.backend.status = 'PENDING'
            waiting = pipeline.run(original)
            self.assertEqual(waiting['reason'], 'CI_PENDING')
            self.assertEqual(len(factory.prompts), 1)
            # A fresh process and expired old lease: retain the exact checkpoint,
            # invalidate the old worker, and reconcile before polling again.
            now[0] += 181
            restarted = ExecutionLedger(path, ['owner/repo'], clock=lambda: now[0])
            self.assertEqual(restarted.recover_expired(), ['T-1'])
            self.assertEqual(restarted.observation('T-1')['state'], 'PENDING')
            recovered = restarted.claim('new-worker', ttl=180)
            self.assertEqual(recovered['checkpoint'], waiting['checkpoint'])
            self.assertGreater(recovered['fence'], original['fence'])
            with self.assertRaises(LeaseLost):
                ledger.assert_live(*self.token_from(original))
            self.backend.status = 'PASS'
            factory.ledger = restarted
            result = DevelopmentPipeline(restarted, self.backend, factory, ['owner/repo']).run(recovered)
            self.assertEqual(result['state'], 'DONE')
            self.assertEqual([p[0] for p in factory.prompts], ['workspace-write', 'read-only'])
            self.assertEqual(self.backend.calls.count('prepare'), 1)
            self.assertEqual(self.backend.calls.count('commit'), 1)

    @staticmethod
    def token_from(claim):
        return claim['task_id'], claim['worker_id'], claim['fence']

    def test_expired_checkpoint_with_inflight_or_tampered_binding_never_auto_requeues(self):
        from test_execution_ledger import SCHEMA
        variants = ({'phase': 'IN_FLIGHT_CODEX'}, {'phase': 'IN_FLIGHT_PR'},
                    {'spec_hash': '0' * 64}, {'spec_digest': '0' * 64},
                    {'sha': 'main'}, {'pr': True}, {'patch_attempts': 4},
                    {'patch_attempts': True}, {'branch': 'codex/task-foreign'})
        for changes in variants:
            with tempfile.TemporaryDirectory() as temp:
                path = os.path.join(temp, 'tasks.db')
                with sqlite3.connect(path) as conn:
                    conn.executescript(SCHEMA)
                    conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                                 ('T-1', 'CODEX_EXEC', 'PENDING', '[]', None, None, 0, '{}', 0))
                now = [1000]
                ledger = ExecutionLedger(path, ['owner/repo'], clock=lambda: now[0])
                ledger.register_spec('T-1', self.claim['spec'], 'owner', True)
                factory = Factory(ledger)
                self.backend.status = 'PENDING'
                claim = ledger.claim('old', ttl=180)
                result = DevelopmentPipeline(ledger, self.backend, factory, ['owner/repo']).run(claim)
                checkpoint = dict(result['checkpoint'], **changes)
                ledger.checkpoint(*self.token_from(claim), value=checkpoint)
                now[0] += 181
                ledger.recover_expired()
                self.assertEqual(ledger.observation('T-1')['state'], 'WAITING_HUMAN')
                self.assertIsNone(ledger.claim('new'))
                self.assertEqual(len(factory.prompts), 1)
    def test_checkpoint_reconciles_pr_before_resuming(self):
        self.backend.status = 'PENDING'
        self.pipeline.run(self.claim)
        self.backend.identity = False
        self.assertEqual(self.resume()['reason'], 'EXTERNAL_IDENTITY_MISMATCH')
        self.assertEqual(len(self.factory.prompts), 1)
    def test_inflight_crash_has_no_automatic_replay(self):
        self.backend.status = 'PENDING'
        self.pipeline.run(self.claim)
        self.ledger.cp['phase'] = 'IN_FLIGHT_PR'
        count = len(self.backend.calls)
        self.assertEqual(self.resume()['reason'], 'UNCERTAIN_EXTERNAL_EFFECT')
        self.assertEqual(len(self.backend.calls), count)
    def test_wrong_qa_sha_is_rejected(self):
        self.factory.qa_sha = BASE
        self.assertEqual(self.pipeline.run(self.claim)['reason'], 'QA_REJECTED')
    def test_failed_qa_is_rejected(self):
        self.factory.verdict = 'FAIL'
        self.assertEqual(self.pipeline.run(self.claim)['reason'], 'QA_REJECTED')
    def test_fixed_sol_model(self):
        self.factory.model = 'gpt-6-astra'
        self.assertEqual(self.pipeline.run(self.claim)['reason'], 'MODEL_POLICY_MISMATCH')
        self.assertNotIn('commit', self.backend.calls)
    def test_worker_precommit_is_blocked_before_push(self):
        class PrecommitWorker(Worker):
            def run(worker, prompt, **kwargs):
                result = super(PrecommitWorker, worker).run(prompt, **kwargs)
                self.backend.identity = False
                return result
        self.pipeline.worker_factory = lambda work, sandbox: PrecommitWorker(self.factory, work, sandbox)
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['reason'], 'WORKER_CHANGED_COMMIT_HISTORY')
        self.assertNotIn('commit', self.backend.calls)
        self.assertNotIn('pr', self.backend.calls)

    def test_lease_loss_never_finishes_or_commits(self):
        self.factory.lose_lease = True
        result = self.pipeline.run(self.claim)
        self.assertEqual(result['reason'], 'LEASE_LOST')
        self.assertEqual(self.ledger.finishes, [])
        self.assertNotIn('commit', self.backend.calls)
    def test_unknown_codex_failure_requires_review_not_resource_retry(self):
        self.factory.failure = True
        self.assertEqual(self.pipeline.run(self.claim)['state'], 'WAITING_HUMAN')
        self.assertEqual(self.ledger.finishes[-1][1], 'unknown')
    def test_resource_preflight_pauses_before_effects_and_resumes(self):
        self.pipeline.resource_check = lambda: 'UNKNOWN'
        self.assertEqual(self.pipeline.run(self.claim)['state'], 'PAUSED_RESOURCE')
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.ledger.finishes[-1], ('PAUSED_RESOURCE', 'none'))
        self.pipeline.resource_check = lambda: 'READY'
        self.assertEqual(self.resume()['state'], 'DONE')
    def test_claim_spec_hash_and_base_are_bound(self):
        self.claim['spec']['prompt'] = 'changed instructions'
        with self.assertRaises(ValueError):
            self.pipeline.run(self.claim)
        self.assertFalse(self.backend.calls)
    def test_repository_allowlist_and_invalid_base_fail_before_effects(self):
        self.claim['spec']['base_sha'] = '$(rm -rf /)'
        with self.assertRaises(ValueError):
            self.pipeline.run(self.claim)
        self.assertFalse(self.backend.calls)
    def test_log_is_bounded_and_redacted(self):
        self.assertNotIn('sk-abcdefghijklmnop', safe_text('sk-abcdefghijklmnop'))
        self.assertEqual(len(safe_text('x' * 50000)), 16000)


class CliBackendTest(unittest.TestCase):
    def test_code_task_cannot_modify_its_own_gates_or_deployment_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = CliBackend({'owner/repo': temp}, os.path.join(temp, 'work'),
                                 os.path.join(temp, 'home'), '/usr/bin', ['unit'])
            for name in ('stage1/development_pipeline.py', 'stage1/execution_ledger.py',
                         'stage1/codex_app_server_worker.py', 'stage1/owner_update_router.py',
                         '.github/workflows/ci.yml', 'scripts/deploy.py', 'nested/AGENTS.md',
                         'worker.service', '.codex/config.toml'):
                with self.assertRaises(UnknownEffect):
                    backend._validate_paths([name], temp, changed=True)
            # A base repository may contain reviewed enforcement code; only its
            # mutation is denied. Normal modules remain editable.
            backend._validate_paths(['stage1/development_pipeline.py'], temp)
            backend._validate_paths(['module/feature.py'], temp, changed=True)

    def test_git_is_argv_only_and_dedicated_environment(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, b'[]', b'')
        with tempfile.TemporaryDirectory() as temp:
            backend = CliBackend({'owner/repo': temp}, os.path.join(temp, 'work'),
                                 os.path.join(temp, 'home'), '/usr/bin:/bin', ['unit'], runner=runner)
            fences = []
            backend._git(['status', '--porcelain'], temp, lambda: fences.append(True))
            argv, kwargs = calls[0]
            self.assertIsInstance(argv, list)
            self.assertNotIn('shell', kwargs)
            self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
            self.assertEqual(kwargs['env']['HOME'], os.path.join(temp, 'home'))
            self.assertEqual(len(fences), 1)
            self.assertIn('core.hooksPath=/dev/null', argv)
    def test_restricted_paths_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = CliBackend({'owner/repo': temp}, os.path.join(temp, 'work'),
                                 os.path.join(temp, 'home'), '/usr/bin', ['unit'])
            for name in ['.env', '.env.production', 'nested/secret.json', '../prod', '/etc/passwd', 'id_rsa', 'cert.pem']:
                with self.assertRaises(UnknownEffect):
                    backend._validate_paths([name], temp)
            os.symlink('/etc/passwd', os.path.join(temp, 'escape'))
            with self.assertRaises(UnknownEffect):
                backend._validate_paths(['escape'], temp)
    def test_actual_local_git_prepare_and_commit_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, 'source')
            os.mkdir(source)
            def git(args):
                return subprocess.check_output(['git'] + args, cwd=source).decode().strip()
            git(['init', '-q'])
            git(['config', 'user.name', 'Test'])
            git(['config', 'user.email', 'test@localhost'])
            with open(os.path.join(source, 'code.py'), 'w') as handle:
                handle.write('value = 1\n')
            git(['add', '.'])
            git(['commit', '-qm', 'base'])
            base = git(['rev-parse', 'HEAD'])
            backend = CliBackend({'owner/repo': source}, os.path.join(temp, 'work'),
                                 os.path.join(temp, 'home'), '/usr/bin:/bin', ['unit'])
            branch = 'codex/task-' + '1' * 24
            work = backend.prepare('owner/repo', base, branch, lambda: True)
            with open(os.path.join(work, 'code.py'), 'w') as handle:
                handle.write('value = 2\n')
            commit = backend.commit('owner/repo', work, branch, lambda: True)
            self.assertNotEqual(commit, base)
            self.assertTrue(backend.reconcile('owner/repo', work, branch, commit, None, lambda: True))
            self.assertEqual(backend.freeze('owner/repo', work, branch, commit, lambda: True), work)
            self.assertTrue(backend.validate_commit('owner/repo', work, base, commit, lambda: True))
            with open(os.path.join(work, '.env'), 'w') as handle:
                handle.write('SECRET=no')
            with self.assertRaises(UnknownEffect):
                backend.commit('owner/repo', work, branch, lambda: True)
    def test_secret_in_precommitted_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, 'source')
            os.mkdir(source)
            def git(args):
                return subprocess.check_output(['git'] + args, cwd=source).decode().strip()
            git(['init', '-q'])
            git(['config', 'user.name', 'Test'])
            git(['config', 'user.email', 'test@localhost'])
            with open(os.path.join(source, 'code.py'), 'w') as handle:
                handle.write('value = 1\n')
            git(['add', '.'])
            git(['commit', '-qm', 'base'])
            base = git(['rev-parse', 'HEAD'])
            with open(os.path.join(source, 'code.py'), 'w') as handle:
                handle.write('key = "sk-abcdefghijklmnop"\n')
            git(['add', '.'])
            git(['commit', '-qm', 'secret'])
            with open(os.path.join(source, 'code.py'), 'w') as handle:
                handle.write('value = 2\n')
            git(['add', '.'])
            git(['commit', '-qm', 'remove secret'])
            head = git(['rev-parse', 'HEAD'])
            backend = CliBackend({'owner/repo': source}, os.path.join(temp, 'work'),
                                 os.path.join(temp, 'home'), '/usr/bin:/bin', ['unit'])
            with self.assertRaises(UnknownEffect):
                backend.validate_commit('owner/repo', source, base, head, lambda: True)

    def test_ci_requires_required_checks_exact_sha(self):
        data = {'total_count': 1, 'check_runs': [{'name': 'unit', 'id': 1,
                'head_sha': BASE, 'status': 'completed', 'conclusion': 'success'}]}
        def runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, json.dumps(data).encode(), b'')
        with tempfile.TemporaryDirectory() as temp:
            backend = CliBackend({'owner/repo': temp}, os.path.join(temp, 'work'),
                                 os.path.join(temp, 'home'), '/usr/bin', ['unit'], runner)
            self.assertEqual(backend.checks('owner/repo', temp, 1, HEAD, lambda: True)['status'], 'PENDING')
            data['check_runs'][0]['head_sha'] = HEAD
            self.assertEqual(backend.checks('owner/repo', temp, 1, HEAD, lambda: True)['status'], 'PASS')
            data['check_runs'][0]['conclusion'] = 'skipped'
            self.assertEqual(backend.checks('owner/repo', temp, 1, HEAD, lambda: True)['status'], 'FAIL')
            data['total_count'] = 10
            self.assertEqual(backend.checks('owner/repo', temp, 1, HEAD, lambda: True)['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
