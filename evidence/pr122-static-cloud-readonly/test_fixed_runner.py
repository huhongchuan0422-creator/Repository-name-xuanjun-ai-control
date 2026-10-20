import ast
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import socket
import tempfile
import unittest
import urllib.error
from email.message import Message
from unittest import mock
import zipfile

import github_evidence as ge
import fixed_runner as fr

HEAD = 'a' * 40
SOURCE = 'c' * 40
NONCE = 'b' * 64


def run(run_id=2, number=2, head=HEAD):
    return {'id': run_id, 'workflow_id': 11, 'run_number': number, 'run_attempt': 1,
            'event': 'pull_request', 'path': ge.WORKFLOW_PATH,
            'repository': {'id': ge.REPOSITORY_ID}, 'head_repository': {'id': ge.REPOSITORY_ID},
            'head_branch': ge.BRANCH, 'head_sha': head,
            'actor': {'id': ge.OWNER_ID}, 'triggering_actor': {'id': ge.OWNER_ID}}


def job(run_id=1, state='skipped'):
    return {'id': 100 + run_id, 'run_id': run_id, 'name': ge.DISPATCH_JOB,
            'started_at': '2026-10-18T16:36:27Z', 'status': 'completed',
            'conclusion': state, 'steps': [] if state == 'skipped' else [{'name': 'Set up job'}]}


def fixture(mode='dispatch'):
    # Actual GET /pulls/122 shape recorded by the parent: draft PR, historical
    # storefront base, and the real next25 head, not the separate website branch.
    pr = {'number': 122, 'state': 'open', 'draft': True,
          'head': {'sha': HEAD, 'ref': ge.BRANCH, 'repo': {'id': ge.REPOSITORY_ID}},
          'base': {'ref': 'feature/stage5-merchant-platform-storefront-ui-20261014',
                   'repo': {'id': ge.REPOSITORY_ID}}}
    prefix = 'pr122-ro-' if mode == 'dispatch' else 'pr122-roq-'
    event = {'action': 'labeled', 'number': 122, 'pull_request': pr,
             'repository': {'id': ge.REPOSITORY_ID, 'full_name': ge.REPOSITORY},
             'sender': {'id': ge.OWNER_ID}, 'label': {'name': prefix + HEAD}}
    env = {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_REPOSITORY': ge.REPOSITORY,
           'GITHUB_REPOSITORY_ID': str(ge.REPOSITORY_ID), 'GITHUB_ACTOR_ID': str(ge.OWNER_ID),
           'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_ID': '2', 'READONLY_SOURCE_HEAD': SOURCE}
    return event, env


class FakeGitHub:
    def __init__(self, mode='dispatch'):
        self.event, self.env = fixture(mode)
        self.current = run()
        self.history = [run(1, 1), self.current]
        self.job_rows = {1: [job()]}
        self.artifact = None
        self.reads = []
        self.source_head = SOURCE
        self.workflow_raw = ge.TEMPLATE_PATH.read_bytes().replace(ge.SOURCE_PLACEHOLDER.encode(), SOURCE.encode())

    def get(self, path):
        if path == '/pulls/122':
            return copy.deepcopy(self.event['pull_request'])
        if path == '/git/ref/heads/' + ge.SOURCE_BRANCH:
            return {'ref': 'refs/heads/' + ge.SOURCE_BRANCH,
                    'object': {'type': 'commit', 'sha': self.source_head}}
        if path == '/contents/' + ge.WORKFLOW_PATH + '?ref=' + HEAD:
            return {'type': 'file', 'path': ge.WORKFLOW_PATH, 'encoding': 'base64',
                    'content': base64.b64encode(self.workflow_raw).decode()}
        raise AssertionError(path)

    def run(self, run_id):
        assert run_id == 2
        return copy.deepcopy(self.current)

    def runs(self, workflow_id):
        assert workflow_id == 11
        return copy.deepcopy(self.history)

    def jobs(self, run_id):
        return copy.deepcopy(self.job_rows[run_id])

    def read_artifact(self, run_id, name, member, artifact_id=None):
        self.reads.append((run_id, name, member, artifact_id))
        if isinstance(self.artifact, Exception):
            raise self.artifact
        return copy.deepcopy(self.artifact)


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.socket_guard = mock.patch.object(socket, 'socket', side_effect=AssertionError('NO_NETWORK_TEST'))
        self.socket_guard.start()

    def tearDown(self):
        self.socket_guard.stop()


class AdmissionTests(OfflineCase):
    def test_actual_draft_pr122_api_shape_admitted(self):
        api = FakeGitHub()
        self.assertEqual(ge.BRANCH, 'feature/stage5-next25-integration-20261015')
        self.assertTrue(api.event['pull_request']['draft'])
        self.assertEqual(api.get('/pulls/122')['base']['ref'],
                         'feature/stage5-merchant-platform-storefront-ui-20261014')
        self.assertEqual(ge.live_admission(api, api.event, api.env, 'dispatch')['head_sha'], HEAD)

    def test_old_website_workbranch_rejected_in_event_and_api(self):
        old = 'feature/work-pr122-site-hub-integration-20261016'
        event, env = fixture()
        event['pull_request']['head']['ref'] = old
        with self.assertRaisesRegex(ge.Hold, 'EVENT_NOT_EXACT'):
            ge.validate_event(event, env, 'dispatch')
        api = FakeGitHub(); event = copy.deepcopy(api.event)
        api.event['pull_request']['head']['ref'] = old
        with self.assertRaisesRegex(ge.Hold, 'CURRENT_PR_HEAD_CHANGED'):
            ge.live_admission(api, event, api.env, 'dispatch')

    def test_dual_heads_bound_independently(self):
        api = FakeGitHub()
        result = ge.live_admission(api, api.event, api.env, 'dispatch')
        self.assertEqual(result['head_sha'], HEAD)
        self.assertEqual(result['readonly_source_head'], SOURCE)
        self.assertNotEqual(HEAD, SOURCE)

    def test_source_branch_move_rejected(self):
        api = FakeGitHub(); api.source_head = 'd' * 40
        with self.assertRaisesRegex(ge.Hold, 'SOURCE_BRANCH_MOVED'):
            ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_event_workflow_must_equal_exact_substituted_template(self):
        for changed in ('foreign', 'free_input', 'wrong_sha'):
            api = FakeGitHub()
            if changed == 'foreign': api.workflow_raw += b'\n# unreviewed change\n'
            elif changed == 'free_input': api.workflow_raw = api.workflow_raw.replace(SOURCE.encode(), b'${{ inputs.source }}')
            else: api.workflow_raw = api.workflow_raw.replace(SOURCE.encode(), b'd' * 40)
            with self.assertRaisesRegex(ge.Hold, 'EVENT_WORKFLOW_SOURCE_BINDING'):
                ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_missing_or_placeholder_source_rejected(self):
        for source in ('', ge.SOURCE_PLACEHOLDER, SOURCE[:12]):
            api = FakeGitHub(); api.env['READONLY_SOURCE_HEAD'] = source
            with self.assertRaisesRegex(ge.Hold, 'SOURCE_HEAD_REQUIRED'):
                ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_skipped_with_real_nonnull_started_at_allows_first_dispatch(self):
        api = FakeGitHub()
        result = ge.live_admission(api, api.event, api.env, 'dispatch')
        self.assertEqual(result['source_run_id'], 2)

    def test_real_skipped_fixture_shape(self):
        # Exact shape of run39145761632/recover-readonly's API observation.
        row = job()
        row.update(status='completed', conclusion='skipped', steps=[],
                   started_at='2026-10-18T16:36:27Z')
        api = FakeGitHub(); api.job_rows[1] = [row]
        ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_consumed_cloud_job_blocks_remove_add_label(self):
        api = FakeGitHub(); api.job_rows[1] = [job(state='success')]
        with self.assertRaisesRegex(ge.Hold, 'ALREADY_STARTED'):
            ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_queued_running_cancelled_partial_all_block(self):
        for status, conclusion, steps, started in [
                ('queued', None, [], None), ('in_progress', None, [], None),
                ('completed', 'cancelled', [], None), ('completed', 'skipped', [{}], 'x')]:
            with self.subTest(status=status, conclusion=conclusion):
                api = FakeGitHub(); row = job()
                row.update(status=status, conclusion=conclusion, steps=steps, started_at=started)
                api.job_rows[1] = [row]
                with self.assertRaises(ge.Hold):
                    ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_deleted_run_gap_blocks(self):
        api = FakeGitHub(); api.history = [api.current]
        with self.assertRaisesRegex(ge.Hold, 'HISTORY_GAP'):
            ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_missing_cloud_job_blocks(self):
        api = FakeGitHub(); api.job_rows[1] = []
        with self.assertRaisesRegex(ge.Hold, 'HISTORY_MISSING'):
            ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_missing_job_evidence_blocks(self):
        for key in ('steps', 'status', 'conclusion', 'started_at', 'run_id'):
            api = FakeGitHub(); del api.job_rows[1][0][key]
            with self.assertRaises(ge.Hold):
                ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_current_head_changed_blocks(self):
        api = FakeGitHub(); event = copy.deepcopy(api.event)
        api.event['pull_request']['head']['sha'] = 'c' * 40
        with self.assertRaisesRegex(ge.Hold, 'HEAD_CHANGED'):
            ge.live_admission(api, event, api.env, 'dispatch')

    def test_event_actor_repo_branch_label_and_rerun_fail_closed(self):
        mutations = [lambda e, v: v.update(GITHUB_RUN_ATTEMPT='2'),
                     lambda e, v: v.update(GITHUB_ACTOR_ID='1'),
                     lambda e, v: v.update(GITHUB_EVENT_NAME='push'),
                     lambda e, v: e['sender'].update(id=1),
                     lambda e, v: e['repository'].update(id=1),
                     lambda e, v: e['pull_request']['head'].update(ref='main'),
                     lambda e, v: e['pull_request']['head']['repo'].update(id=1),
                     lambda e, v: e['label'].update(name='pr122-ro-' + HEAD[:12]),
                     lambda e, v: e.update(number=99)]
        for change in mutations:
            event, env = fixture(); change(event, env)
            with self.assertRaises(ge.Hold): ge.validate_event(event, env, 'dispatch')

    def test_api_rerun_rejected(self):
        api = FakeGitHub(); api.current['run_attempt'] = 2
        with self.assertRaises(ge.Hold): ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_query_only_requires_unique_previous_consumed_run(self):
        api = FakeGitHub('query'); api.job_rows[1] = [job(state='success')]
        admitted = ge.live_admission(api, api.event, api.env, 'query')
        self.assertEqual(admitted['source_run_id'], 1)
        api.job_rows[1] = [job()]
        with self.assertRaises(ge.Hold): ge.live_admission(api, api.event, api.env, 'query')

    def test_jobs_all_attempts_duplicate_cloud_job_is_query_ambiguous(self):
        api = FakeGitHub('query')
        first = job(state='success'); second = dict(first, id=999)
        api.job_rows[1] = [first, second]
        with self.assertRaisesRegex(ge.Hold, 'SOURCE_NOT_UNIQUE'):
            ge.live_admission(api, api.event, api.env, 'query')
        reader = ge.GitHub('fake')
        with mock.patch.object(reader, 'collection', return_value=[]) as collection:
            reader.jobs(7)
        self.assertIn('filter=all', collection.call_args.args[0])


class PaginationTests(OfflineCase):
    def test_two_complete_pages(self):
        api = ge.GitHub('fake')
        pages = [{'total_count': 101, 'jobs': [{'id': i} for i in range(100)]},
                 {'total_count': 101, 'jobs': [{'id': 100}]}]
        with mock.patch.object(api, 'get', side_effect=pages):
            self.assertEqual(len(api.collection('/actions/runs/2/jobs', 'jobs')), 101)

    def test_truncated_or_changed_or_duplicate_pages_fail(self):
        for pages in [
            [{'total_count': 2, 'jobs': [{'id': 1}]}],
            [{'total_count': 2, 'jobs': [{'id': 1}, {'id': 1}]}],
            [{'total_count': 101, 'jobs': [{'id': i} for i in range(100)]},
             {'total_count': 102, 'jobs': [{'id': 100}]}]]:
            api = ge.GitHub('fake')
            with mock.patch.object(api, 'get', side_effect=pages), self.assertRaises(ge.Hold):
                api.collection('/actions/runs/2/jobs', 'jobs')


class ArtifactTests(OfflineCase):
    def artifact(self, value=None, member='intent.json'):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr(member, ge.encoded(value or {'status': 'intent'}))
        raw = out.getvalue()
        metadata = {'id': 4, 'name': 'expected', 'expired': False, 'size_in_bytes': len(raw),
                    'digest': 'sha256:' + hashlib.sha256(raw).hexdigest()}
        return raw, metadata

    def test_zip_digest_and_member_verified(self):
        raw, meta = self.artifact()
        api = ge.GitHub('fake')
        with mock.patch.object(api, 'artifacts', return_value=[meta]), mock.patch.object(api, 'request', return_value=raw):
            self.assertEqual(api.read_artifact(2, 'expected', 'intent.json', 4), {'status': 'intent'})

    def test_digest_expiry_duplicate_name_wrong_id_fail(self):
        for kind in ('digest', 'expired', 'duplicate', 'wrong_id', 'member'):
            raw, meta = self.artifact(member='wrong.json' if kind == 'member' else 'intent.json')
            if kind == 'digest': meta['digest'] = 'sha256:' + '0' * 64
            if kind == 'expired': meta['expired'] = True
            rows = [meta, meta] if kind == 'duplicate' else [meta]
            api = ge.GitHub('fake')
            with mock.patch.object(api, 'artifacts', return_value=rows), mock.patch.object(api, 'request', return_value=raw), self.assertRaises(ge.Hold):
                api.read_artifact(2, 'expected', 'intent.json', 5 if kind == 'wrong_id' else 4)

    def test_duplicate_json_rejected(self):
        with self.assertRaises(ge.Hold): ge.strict_json('{"a":1,"a":2}')

    def test_artifact_redirect_never_forwards_token(self):
        headers = Message(); headers['Location'] = 'https://test.blob.core.windows.net/archive?sig=private'
        redirect = urllib.error.HTTPError('https://api.github.com/test', 302, 'Found', headers, None)
        response = mock.MagicMock(); response.__enter__.return_value.read.return_value = b'zip'
        opener = mock.Mock(); opener.open.side_effect = [redirect, response]
        api = ge.GitHub('secret-github-token', opener=opener)
        self.assertEqual(api.request('/repos/' + ge.REPOSITORY + '/actions/artifacts/4/zip', redirect=True), b'zip')
        first = opener.open.call_args_list[0].args[0]
        second = opener.open.call_args_list[1].args[0]
        self.assertIn('Authorization', dict(first.header_items()))
        self.assertNotIn('Authorization', dict(second.header_items()))

    def test_artifact_redirect_wrong_host_and_second_redirect_hold(self):
        for url in ('http://test.blob.core.windows.net/a', 'https://attacker.test/a'):
            headers = Message(); headers['Location'] = url
            opener = mock.Mock(); opener.open.side_effect = urllib.error.HTTPError('x', 302, 'Found', headers, None)
            with self.assertRaises(ge.Hold):
                ge.GitHub('fake', opener=opener).request('/repos/' + ge.REPOSITORY + '/actions/artifacts/4/zip', redirect=True)
            self.assertEqual(opener.open.call_count, 1)
        headers = Message(); headers['Location'] = 'https://test.blob.core.windows.net/a'
        redirect = urllib.error.HTTPError('x', 302, 'Found', headers, None)
        opener = mock.Mock(); opener.open.side_effect = [redirect, redirect]
        with self.assertRaises(ge.Hold):
            ge.GitHub('fake', opener=opener).request('/repos/' + ge.REPOSITORY + '/actions/artifacts/4/zip', redirect=True)
        self.assertEqual(opener.open.call_count, 2)


class RunnerTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.state = mock.patch.object(fr, 'STATE', Path(self.temp.name) / 'state'); self.state.start()
        self.api = FakeGitHub()
        self.admission = ge.live_admission(self.api, self.api.event, self.api.env, 'dispatch')
        self.intent = fr.intent_for(self.admission, NONCE)
        self.api.artifact = self.intent

    def tearDown(self):
        self.state.stop(); self.temp.cleanup(); super().tearDown()

    def receipt(self):
        return {'schema': 1, 'scope': fr.SCOPE, 'state': 'OBSERVATION_COMPLETE',
                'files': [{'label': label, 'state': 'ABSENT'} for label in fr.LABELS],
                'production_changes': 0, 'deployment_performed': False}

    def record(self):
        return {'schema': 1, 'scope': fr.SCOPE, 'intent_sha256': fr.digest(ge.encoded(self.intent)),
                'head_sha': HEAD, 'run_id': 2, 'instance_id': fr.INSTANCE,
                'readonly_source_head': SOURCE,
                'command_sha256': self.intent['command_sha256'],
                'status': 'DISPATCHED_QUERY_ONLY', 'invoke_id': 't-sh_mock-1'}

    def output(self):
        return {'schema': 1, 'scope': fr.SCOPE, 'head_sha': HEAD, 'nonce': NONCE,
                'readonly_source_head': SOURCE,
                'helper_sha256': fr.HELPER_SHA256, 'hostname': fr.HOST, 'uid': 0,
                'receipt': self.receipt()}

    def test_frozen_exact_helper_command_budget_and_compile_only(self):
        self.assertEqual(fr.digest(fr.HELPER_BYTES), fr.HELPER_SHA256)
        shell = fr.fixed_command(HEAD, NONCE, SOURCE)
        self.assertLessEqual(len(base64.b64encode(shell.encode())), 16384)
        args = shlex.split(shell.split('\n', 2)[2])
        compile(args[-1], 'fixed_wrapper.py', 'exec')  # Never execute host reads.
        self.assertIn('except BaseException:', args[-1])
        tree = ast.parse(fr.HELPER_BYTES)
        collect = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'collect')
        self.assertIn('signal.alarm(DEADLINE_SECONDS)', ast.unparse(collect))

    def test_size_guard_rejects_oversized_helper(self):
        source = os.urandom(50000)
        with mock.patch.object(fr, 'HELPER_BYTES', source), mock.patch.object(fr, 'HELPER_SHA256', fr.digest(source)), self.assertRaisesRegex(ge.Hold, 'WIRE_TOO_LARGE'):
            fr.fixed_command(HEAD, NONCE, SOURCE)

    def test_dispatch_requires_readback_before_cloud(self):
        fr.local_write('intent.json', self.intent)
        calls = []
        def dispatch(intent):
            self.assertTrue(self.api.reads)
            calls.append(intent)
            return {'InvokeId': 't-sh_mock-1'}
        cloud = mock.Mock(); cloud.dispatch.side_effect = dispatch
        result = fr.dispatch_once(self.api, self.api.event, self.api.env, cloud, 42)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result, fr.local_read('dispatch.json'))
        with self.assertRaises(FileExistsError):
            fr.dispatch_once(self.api, self.api.event, self.api.env, cloud, 42)
        self.assertEqual(len(calls), 1)

    def test_artifact_failure_no_sts_no_dispatch(self):
        fr.local_write('intent.json', self.intent)
        self.api.artifact = ge.Hold('ARTIFACT_UNAVAILABLE')
        cloud = mock.Mock()
        with self.assertRaises(ge.Hold):
            fr.dispatch_once(self.api, self.api.event, self.api.env, cloud, 42)
        cloud.dispatch.assert_not_called()

    def test_unknown_invoke_persists_and_never_retries(self):
        for response in ({}, {'InvokeId': 'bad\nvalue'}):
            with self.subTest(response=response):
                state = Path(self.temp.name) / ('case' + str(len(list(Path(self.temp.name).iterdir()))))
                with mock.patch.object(fr, 'STATE', state):
                    fr.local_write('intent.json', self.intent)
                    cloud = mock.Mock(); cloud.dispatch.return_value = response
                    with self.assertRaisesRegex(ge.Hold, 'UNKNOWN'):
                        fr.dispatch_once(self.api, self.api.event, self.api.env, cloud, 42)
                    self.assertIsNone(fr.local_read('dispatch.json')['invoke_id'])
                    cloud.dispatch.assert_called_once()

    def test_rpc_exception_never_propagates_private_error(self):
        fr.local_write('intent.json', self.intent)
        cloud = mock.Mock(); cloud.dispatch.side_effect = RuntimeError('SECRET_MUST_NOT_ESCAPE')
        with self.assertRaises(ge.Hold) as found:
            fr.dispatch_once(self.api, self.api.event, self.api.env, cloud, 42)
        self.assertNotIn('SECRET', str(found.exception))
        self.assertEqual(fr.local_read('dispatch.json')['status'], 'UNKNOWN_NO_INVOKE_NO_REPLAY')

    def test_plain_and_base64_receipt(self):
        raw = json.dumps(self.output())
        self.assertEqual(fr.validated_output(raw, self.intent), self.receipt())
        self.assertEqual(fr.validated_output(base64.b64encode(raw.encode()).decode(), self.intent), self.receipt())

    def test_wrong_nonce_host_uid_scope_and_unknown_field_rejected(self):
        for key, value in [('nonce', '0' * 64), ('hostname', 'other'), ('uid', True),
                           ('scope', 'OTHER'), ('head_sha', '0' * 40), ('readonly_source_head', HEAD),
                           ('helper_sha256', '0' * 64), ('secret', 'x')]:
            out = self.output(); out[key] = value
            with self.assertRaises(ge.Hold): fr.validated_output(json.dumps(out), self.intent)

    def test_output_excess_and_file_content_rejected(self):
        with self.assertRaises(ge.Hold): fr.validated_output('x' * 9000, self.intent)
        out = self.output(); out['receipt']['files'][0]['contents'] = 'PRIVATE'
        with self.assertRaises(ge.Hold): fr.validated_output(json.dumps(out), self.intent)

    def test_hold_then_not_read_is_strict(self):
        value = self.receipt(); value['state'] = 'HOLD'
        value['files'][0] = {'label': fr.LABELS[0], 'state': 'HOLD', 'reason': 'OWNER_OR_MODE'}
        value['files'][1:] = [{'label': label, 'state': 'NOT_READ'} for label in fr.LABELS[1:]]
        fr.validate_receipt(value)
        value['files'][1]['state'] = 'ABSENT'
        with self.assertRaises(ge.Hold): fr.validate_receipt(value)

    def test_query_cannot_dispatch(self):
        cloud = mock.Mock()
        cloud.query.return_value = {'InvocationResult': {'InstanceId': fr.INSTANCE,
            'InvokeId': 't-sh_mock-1', 'InvocationStatus': 'Success', 'ExitCode': 0,
            'Output': json.dumps(self.output())}}
        result = fr.query_only(cloud, self.intent, self.record())
        self.assertEqual(result['status'], 'OBSERVATION_COMPLETE')
        cloud.dispatch.assert_not_called()

    def test_query_command_instance_and_invoke_provenance(self):
        for key, value in [('command_sha256', '0' * 64), ('instance_id', 'other'),
                           ('intent_sha256', '0' * 64), ('readonly_source_head', HEAD),
                           ('invoke_id', None), ('run_id', 1)]:
            record = self.record(); record[key] = value
            cloud = mock.Mock()
            with self.assertRaises(ge.Hold): fr.query_only(cloud, self.intent, record)
            cloud.query.assert_not_called(); cloud.dispatch.assert_not_called()

    def test_query_pending_window_stays_query_only(self):
        cloud = mock.Mock(); cloud.query.return_value = {'InvocationResult': {
            'InstanceId': fr.INSTANCE, 'InvokeId': 't-sh_mock-1', 'InvocationStatus': 'Running'}}
        with self.assertRaisesRegex(ge.Hold, 'PENDING_PRESERVE'):
            fr.query_only(cloud, self.intent, self.record(), clock=mock.Mock(side_effect=[0, 1, 181]), sleep=lambda _: None)
        cloud.query.assert_called_once(); cloud.dispatch.assert_not_called()

    def test_original_pending_shape_may_omit_ids_but_terminal_must_bind(self):
        cloud = mock.Mock()
        terminal = {'InstanceId': fr.INSTANCE, 'InvokeId': 't-sh_mock-1',
                    'InvocationStatus': 'Success', 'ExitCode': 0, 'Output': json.dumps(self.output())}
        cloud.query.side_effect = [{'InvocationResult': {'InvocationStatus': 'Pending'}},
                                  {'InvocationResult': terminal}]
        result = fr.query_only(cloud, self.intent, self.record(), sleep=lambda _: None)
        self.assertEqual(result['status'], 'OBSERVATION_COMPLETE')
        self.assertEqual(cloud.query.call_count, 2)
        cloud.dispatch.assert_not_called()
        for wrong in ({'InvocationStatus': 'Running', 'InstanceId': 'wrong'},
                      {'InvocationStatus': 'Success', 'ExitCode': 0, 'Output': json.dumps(self.output())}):
            cloud = mock.Mock(); cloud.query.return_value = {'InvocationResult': wrong}
            with self.assertRaises(ge.Hold):
                fr.query_only(cloud, self.intent, self.record(), sleep=lambda _: None)
            cloud.query.assert_called_once(); cloud.dispatch.assert_not_called()

    def test_remote_hold_is_never_pass(self):
        output = self.output(); receipt = output['receipt']; receipt['state'] = 'HOLD'
        receipt['files'] = [{'label': fr.LABELS[0], 'state': 'HOLD', 'reason': 'UNSAFE_PATH'}]
        receipt['files'] += [{'label': label, 'state': 'NOT_READ'} for label in fr.LABELS[1:]]
        cloud = mock.Mock(); cloud.query.return_value = {'InvocationResult': {
            'InstanceId': fr.INSTANCE, 'InvokeId': 't-sh_mock-1', 'InvocationStatus': 'Success',
            'ExitCode': 0, 'Output': json.dumps(output)}}
        result = fr.query_only(cloud, self.intent, self.record())
        self.assertEqual(result['status'], 'HOLD')
        cloud.dispatch.assert_not_called()

    def test_query_wrong_response_instance_no_output_escape(self):
        cloud = mock.Mock(); cloud.query.return_value = {'InvocationResult': {
            'InstanceId': 'other', 'InvokeId': 't-sh_mock-1', 'InvocationStatus': 'Success',
            'ExitCode': 0, 'Output': 'SECRET'}}
        with self.assertRaises(ge.Hold) as caught:
            fr.query_only(cloud, self.intent, self.record())
        self.assertNotIn('SECRET', str(caught.exception))
        cloud.dispatch.assert_not_called()

    def test_cloud_wrapper_only_fixed_actions_and_host(self):
        calls = []
        def rpc(endpoint, version, action, credentials, **params):
            calls.append((endpoint, action, params))
            if action == 'AssumeRole':
                return {'Credentials': {'AccessKeyId': 'test-id', 'AccessKeySecret': 'test-secret', 'SecurityToken': 'test-token'}}
            return {'InvokeId': 't-sh_mock-1'}
        cloud = fr.FixedCloud(('fake-id', 'fake-secret', ''), rpc=rpc)
        cloud.dispatch(self.intent); cloud.query('t-sh_mock-1')
        self.assertEqual([c[1] for c in calls], ['AssumeRole', 'RunCommand', 'DescribeInvocationResult'])
        self.assertEqual(calls[0][2]['RoleArn'], fr.ROLE)
        for endpoint, _, params in calls[1:]:
            self.assertEqual(endpoint, fr.ENDPOINT); self.assertEqual(params['InstanceId'], fr.INSTANCE)

    def test_workflow_gates_and_artifact_order(self):
        text = (Path(__file__).parent / 'pr122-staging-readonly.yml').read_text()
        self.assertIn('cancel-in-progress: false', text)
        self.assertIn("github.actor_id == '332398908'", text)
        self.assertIn("github.repository_id == '1413132159'", text)
        self.assertIn('branches: [feature/stage5-next25-integration-20261015]', text)
        self.assertEqual(text.count("github.event.pull_request.head.ref == 'feature/stage5-next25-integration-20261015'"), 2)
        self.assertNotIn('feature/work-pr122-site-hub-integration-20261016', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertNotIn('self-hosted', text)
        self.assertLess(text.index('Persist intent before STS'), text.index('dispatch exactly once'))
        self.assertIn('overwrite: false', text)
        self.assertEqual(text.count(ge.SOURCE_PLACEHOLDER), 4)
        substituted = text.replace(ge.SOURCE_PLACEHOLDER, SOURCE)
        self.assertEqual(substituted.count("ref: '" + SOURCE + "'"), 3)
        source_workflow = (Path(__file__).parent / 'pr122-ro-source-tests.yml').read_text()
        self.assertIn('branches: [feature/work-pr122-site-hub-integration-20261016]', source_workflow)
        self.assertNotIn('secrets.', source_workflow)
        self.assertNotIn('RunCommand', source_workflow)
        self.assertNotIn('pull_request:', source_workflow)

    def test_checkout_provenance_checks_pinned_git_head_and_clean_tree(self):
        workspace = Path(self.temp.name)
        env = {'GITHUB_WORKSPACE': str(workspace), 'READONLY_SOURCE_HEAD': SOURCE}
        filename = str(workspace / 'evidence/pr122-static-cloud-readonly/fixed_runner.py')
        good = mock.Mock(returncode=0, stdout=(SOURCE + '\n').encode())
        with mock.patch.object(fr, '__file__', filename), mock.patch.object(Path, 'cwd', return_value=workspace):
            runner = mock.Mock(side_effect=[good, mock.Mock(returncode=0)])
            fr.verify_source_checkout(env, runner)
            self.assertEqual(runner.call_args_list[0].args[0], ['git', 'rev-parse', 'HEAD'])
            for results in ([mock.Mock(returncode=0, stdout=(HEAD + '\n').encode())],
                            [good, mock.Mock(returncode=1)]):
                with self.assertRaises(ge.Hold):
                    fr.verify_source_checkout(env, mock.Mock(side_effect=results))



class LabelBoundaryTests(OfflineCase):
    def test_exact_label_lengths_and_event_rejection(self):
        for mode, prefix, expected in (('dispatch', 'pr122-ro-', 49),
                                       ('query', 'pr122-roq-', 50)):
            event, env = fixture(mode)
            self.assertEqual(event['label']['name'], prefix + HEAD)
            self.assertEqual(len(event['label']['name']), expected)
            self.assertLessEqual(len(event['label']['name']), 50)
            self.assertEqual(ge.validate_event(event, env, mode)[0], HEAD)
            wrongs = [prefix + '0' * 40, prefix + HEAD[:-1],
                      ('pr122-roq-' if mode == 'dispatch' else 'pr122-ro-') + HEAD,
                      ('pr122-staging-readonly-' if mode == 'dispatch' else
                       'pr122-staging-readonly-query-') + HEAD]
            for wrong in wrongs:
                with self.subTest(mode=mode, label=wrong):
                    altered = copy.deepcopy(event)
                    altered['label']['name'] = wrong
                    with self.assertRaisesRegex(ge.Hold, 'EVENT_NOT_EXACT'):
                        ge.validate_event(altered, env, mode)

    def test_duplicate_label_does_not_allow_second_dispatch(self):
        api = FakeGitHub()
        api.history = [run(1, 1), run(2, 2), run(3, 3)]
        api.current = run(3, 3)
        api.env['GITHUB_RUN_ID'] = '3'
        api.job_rows[2] = [job(2, 'success')]
        with self.assertRaisesRegex(ge.Hold, 'HEAD_CLOUD_JOB_ALREADY_STARTED'):
            ge.live_admission(api, api.event, api.env, 'dispatch')

    def test_history_missing_page_or_deleted_run_stays_hold(self):
        api = FakeGitHub()
        api.history = [run(1, 1), run(2, 3)]
        with self.assertRaisesRegex(ge.Hold, 'RUN_HISTORY_GAP_HOLD'):
            ge.live_admission(api, api.event, api.env, 'dispatch')
        class NoHistory(FakeGitHub):
            def runs(self, workflow_id):
                raise ge.Hold('HISTORY_MISSING_PAGE')
        other = NoHistory()
        with self.assertRaisesRegex(ge.Hold, 'HISTORY_MISSING_PAGE'):
            ge.live_admission(other, other.event, other.env, 'dispatch')

    def test_yaml_exact_labels_and_template_identity(self):
        text = ge.TEMPLATE_PATH.read_text()
        self.assertIn("format('pr122-ro-{0}'", text)
        self.assertIn("format('pr122-roq-{0}'", text)
        self.assertNotIn("format('pr122-staging-readonly-", text)


if __name__ == '__main__':
    unittest.main()
