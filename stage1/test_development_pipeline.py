"""Pipeline contract tests: simulated fixtures never imply real CLI evidence."""
import copy
import json
import os
import subprocess
import tempfile
import unittest

from codex_worker import MODEL
from development_pipeline import (DevelopmentPipeline, CliBackend, UnknownEffect,
                                  digest_spec, safe_text)
from execution_ledger import LeaseLost

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
                'simulated': self.owner.simulated, 'real_execution': not self.owner.simulated,
                'output': json.dumps({'verdict': self.owner.verdict, 'commit': self.owner.qa_sha})}


class Factory(object):
    def __init__(self, ledger):
        self.ledger, self.prompts = ledger, []
        self.simulated, self.failure, self.lose_lease = False, False, False
        self.model, self.verdict, self.qa_sha = MODEL, 'PASS', HEAD
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
        result = self.pipeline.run(self.claim)
        for _ in range(3):
            self.assertEqual(result['reason'], 'PATCH_READY')
            self.assertNotIn('do-not-leak', self.ledger.cp['failure_log'])
            result = self.resume()
        self.assertEqual(result['reason'], 'PATCH_LIMIT_REACHED')
        self.assertEqual(len(self.factory.prompts), 4)
        self.assertNotIn('read-only', [p[0] for p in self.factory.prompts])
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
