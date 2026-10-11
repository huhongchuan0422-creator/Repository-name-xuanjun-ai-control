import base64
import copy
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
MODULE = importlib.util.spec_from_file_location('intake', str(ROOT / 'scripts/uk-work-intake.py'))
i = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(i)
RAW = (ROOT / i.SPEC_PATH).read_bytes()
DESIGN = (ROOT / json.loads(RAW.decode('utf-8'))['design']).read_bytes()


def envelope(manual=False):
    raw = RAW
    if not manual:
        spec = json.loads(raw.decode('utf-8'))
        spec['spec_revision'] = 'future_bounded_revision'
        raw = i.encoded(spec)
    return {'schema': 1, 'repository': i.REPO, 'branch': i.BRANCH,
            'control_source_sha': i.MANUAL_SOURCE, 'spec_sha256': i.digest(raw),
            'spec_base64': base64.b64encode(raw).decode('ascii'),
            'design_sha256': i.digest(DESIGN),
            'design_base64': base64.b64encode(DESIGN).decode('ascii')}


def reported(e):
    return {'server': i.HOST, 'control_source_sha': e['control_source_sha'],
            'spec_sha256': e['spec_sha256'], 'actual_model': i.MODELS[1],
            'state': 'STARTED', 'roles': {'A1': 'STARTED'}, 'blocker': None}


def concurrent_accept(directory, e, log):
    store = i.Store(directory)
    try:
        def wake(*args):
            with open(log, 'ab') as stream:
                stream.write(b'one wake\n')
            return reported(e)
        i.accept(e, store, wake)
    finally:
        store.close()


def refuse_fifo(directory):
    store = i.Store(directory)
    try:
        try:
            store.load('a' * 64)
        except ValueError:
            return
        raise AssertionError('FIFO accepted')
    finally:
        store.close()


class IntakeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        os.chmod(self.directory.name, 0o700)
        self.store = i.Store(self.directory.name)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_manual_start_is_imported_without_another_model_request(self):
        with patch.object(i, 'gateway_wake') as wake:
            result = i.accept(envelope(True), self.store, wake)
            self.assertEqual(result['state'], 'STARTED_OWNER_RELAYED')
            self.assertFalse(result['wake_executed'])
            self.assertEqual(result['manual_control_source_sha'], i.MANUAL_SOURCE)
            wake.assert_not_called()

    def test_identical_spec_under_new_documentation_sha_never_restarts(self):
        e = envelope()
        with patch.object(i, 'gateway_wake', return_value=reported(e)) as wake:
            first = i.accept(e, self.store, wake)
            e['control_source_sha'] = 'a' * 40
            second = i.accept(e, self.store, wake)
            wake.assert_called_once()
            self.assertEqual(first['receipt_key'], second['receipt_key'])
            self.assertEqual(second['observed_control_source_sha'], 'a' * 40)
            self.assertFalse(second['wake_executed'])

    def test_gateway_timeout_and_invalid_receipt_never_auto_retry(self):
        for effect in (TimeoutError(), {'control_source_sha': 'b' * 40}):
            e = envelope()
            raw = json.loads(base64.b64decode(e['spec_base64']).decode('utf-8'))
            raw['spec_revision'] += str(type(effect))
            data = i.encoded(raw)
            e.update(spec_sha256=i.digest(data), spec_base64=base64.b64encode(data).decode('ascii'))
            with patch.object(i, 'gateway_wake') as wake:
                if isinstance(effect, Exception):
                    wake.side_effect = effect
                else:
                    wake.return_value = effect
                result = i.accept(e, self.store, wake)
                self.assertEqual(result['state'], 'WAITING_RECONCILIATION_EFFECT_UNKNOWN')
                i.accept(e, self.store, wake)
                wake.assert_called_once()

    def test_crash_after_durable_dispatch_marker_prevents_second_wake(self):
        e = envelope()
        with patch.object(i, 'gateway_wake', side_effect=SystemExit('crash')) as wake:
            with self.assertRaises(SystemExit):
                i.accept(e, self.store, wake)
        with patch.object(i, 'gateway_wake') as wake:
            result = i.accept(e, self.store, wake)
            self.assertEqual(result['state'], 'DISPATCHING_EFFECT_UNKNOWN_NO_AUTORETRY')
            wake.assert_not_called()

    def test_nonapproved_models_api_permissions_budget_and_digest_are_rejected(self):
        changes = [('models', 'sole_fallback', 'astra'), ('models', 'route', 'API_KEY'),
                   ('permissions', 'production_db_write', True),
                   ('permissions', 'old_coordinator_codex_exec', True),
                   ('budget', 'patch_rounds_total', 4), ('budget', 'patch_rounds_total', True)]
        for section, field, value in changes:
            e = envelope()
            spec = json.loads(base64.b64decode(e['spec_base64']).decode('utf-8'))
            spec[section][field] = value
            raw = i.encoded(spec)
            e.update(spec_sha256=i.digest(raw), spec_base64=base64.b64encode(raw).decode('ascii'))
            with patch.object(i, 'gateway_wake') as wake, self.assertRaises(ValueError):
                i.accept(e, self.store, wake)
            wake.assert_not_called()
        e = envelope()
        e['spec_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            i.validate(e)

    def test_changed_design_requires_new_spec_without_second_wake(self):
        e = envelope()
        i.accept(e, self.store, lambda *args: reported(e))
        raw = DESIGN + b'\nchanged contract\n'
        e.update(design_base64=base64.b64encode(raw).decode('ascii'), design_sha256=i.digest(raw))
        with patch.object(i, 'gateway_wake') as wake:
            self.assertEqual(i.accept(e, self.store, wake)['state'], 'HOLD_DESIGN_CHANGED_NEW_SPEC_REQUIRED')
            wake.assert_not_called()

    def test_receipt_does_not_store_extra_secrets_or_developer_free_text(self):
        e = envelope()
        response = reported(e)
        response.update(token='must-not-persist', blocker='private auth diagnostic')
        result = i.accept(e, self.store, lambda *args: response)
        self.assertNotIn('must-not-persist', json.dumps(result))
        self.assertEqual(result['agent_receipt']['blocker'], 'REDACTED_UNKNOWN_BLOCKER')
        self.assertFalse(result['production_pass'])
        self.assertFalse(result['independent_role_start_probe'])

    def test_concurrent_consumers_wake_exactly_once(self):
        e = envelope()
        log = os.path.join(self.directory.name, 'calls')
        processes = [multiprocessing.Process(target=concurrent_accept,
                     args=(self.directory.name, e, log)) for _ in range(4)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(8)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(Path(log).read_bytes(), b'one wake\n')

    def test_shared_read_mode_survives_service_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o2750)
            store = i.Store(directory, shared=True)
            previous = os.umask(0o077)
            try:
                store.save('a' * 64, {'state': 'RECEIVED'})
                info = os.stat(os.path.join(directory, 'a' * 64 + '.json'))
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o640)
                self.assertEqual(info.st_gid, os.stat(directory).st_gid)
                self.assertEqual(store.load('a' * 64)['state'], 'RECEIVED')
            finally:
                os.umask(previous)
                store.close()

    def test_symlink_receipt_and_world_writable_directory_refused(self):
        os.symlink('/dev/null', os.path.join(self.directory.name, 'a' * 64 + '.json'))
        with self.assertRaises(OSError):
            self.store.load('a' * 64)
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o777)
            with self.assertRaises(ValueError):
                i.Store(directory)

    def test_wrong_server_or_root_stops_before_configuration_read(self):
        with patch.object(i.os, 'getuid', return_value=0), patch.object(i, 'read_file') as read:
            with self.assertRaises(SystemExit):
                i.main()
            read.assert_not_called()

    def test_replayed_receipt_discards_secret_and_forces_production_false(self):
        e = envelope()
        result = i.accept(e, self.store, lambda *args: reported(e))
        result.update(token='secret-sentinel', production_pass=True)
        self.store.save(result['receipt_key'], result)
        clean = i.accept(e, self.store, lambda *args: self.fail('duplicate wake'))
        self.assertFalse(clean['production_pass'])
        self.assertNotIn('secret-sentinel', json.dumps(clean))
        self.assertNotIn('secret-sentinel', json.dumps(i.clean_receipt(result, result['receipt_key'])))

    def test_transport_rejects_unrelated_metadata_and_claimed_different_model(self):
        e = envelope()
        response = reported(e)
        data = {'status': 'ok', 'result': {'payloads': [{'text': json.dumps(response)}]},
                'unrelated': {'model': 'gpt-5.6-sol', 'provider': 'openai'}}
        with self.assertRaises(ValueError):
            i.transport_receipt(data)
        data['result']['meta'] = {'agentMeta': {'model': 'gpt-5.6-sol', 'provider': 'openai'}}
        self.assertEqual(i.transport_receipt(data)['actual_model'], i.MODELS[1])
        response['actual_model'] = i.MODELS[0]
        data['result']['payloads'][0]['text'] = json.dumps(response)
        with self.assertRaises(ValueError):
            i.transport_receipt(data)

    def test_source_changed_during_auth_prevents_agent_send(self):
        auth = i.encoded({'provider': 'openai', 'profiles': [{'type': 'oauth'}]})
        with patch.object(i, 'run_bounded', return_value=(0, auth)) as run, \
                patch.object(i, 'current_source', return_value=False), patch.object(i.pwd, 'getpwnam'):
            with self.assertRaises(ValueError):
                i.gateway_wake({}, envelope(), {}, RAW, DESIGN, 'a' * 64)
            self.assertEqual(run.call_count, 1)
            self.assertIn('auth', run.call_args[0][0])

    def test_duplicate_json_keys_bool_schema_and_malformed_sections_are_rejected(self):
        with self.assertRaises(ValueError):
            i.parse('{"state":"ok","state":"other"}')
        e = envelope()
        e['schema'] = True
        with self.assertRaises(ValueError):
            i.validate(e)
        for section in ('permissions', 'models', 'budget'):
            e = envelope()
            spec = json.loads(RAW.decode('utf-8'))
            spec[section] = []
            raw = i.encoded(spec)
            e.update(spec_sha256=i.digest(raw), spec_base64=base64.b64encode(raw).decode('ascii'))
            with self.assertRaises(ValueError):
                i.validate(e)

    def test_hardlinked_receipt_is_refused(self):
        key = 'a' * 64
        self.store.save(key, {'state': 'RECEIVED'})
        os.link(os.path.join(self.directory.name, key + '.json'),
                os.path.join(self.directory.name, 'second'))
        with self.assertRaises(ValueError):
            self.store.load(key)

    def test_fifo_receipt_is_refused_without_blocking(self):
        os.mkfifo(os.path.join(self.directory.name, 'a' * 64 + '.json'), 0o600)
        process = multiprocessing.Process(target=refuse_fifo, args=(self.directory.name,))
        process.start()
        process.join(2)
        if process.is_alive():
            process.terminate()
            process.join(2)
            self.fail('FIFO blocked consumer')
        self.assertEqual(process.exitcode, 0)

    def test_actual_subprocess_output_is_bounded_before_buffering(self):
        with self.assertRaises(ValueError):
            i.run_bounded([sys.executable, '-c', 'print("x" * 100000)'],
                          {'PATH': '/usr/bin:/bin'}, 5, 1024)
        code, raw = i.run_bounded([sys.executable, '-c', 'print("ok")'],
                                 {'PATH': '/usr/bin:/bin'}, 5, 1024)
        self.assertEqual((code, raw), (0, b'ok\n'))

    def test_git_replace_cannot_substitute_source_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(['/usr/bin/git', '-C', directory] + list(args),
                                               stderr=subprocess.DEVNULL).strip()
            git('init')
            Path(directory, 'plans').mkdir()
            Path(directory, 'plans/spec.json').write_bytes(b'approved bytes')
            git('add', 'plans/spec.json')
            tree = git('write-tree').decode('ascii')
            base = git('-c', 'user.name=QA', '-c', 'user.email=qa@example.invalid',
                       'commit-tree', tree, '-m', 'approved').decode('ascii')
            Path(directory, 'plans/spec.json').write_bytes(b'replacement bytes')
            git('add', 'plans/spec.json')
            tree = git('write-tree').decode('ascii')
            other = git('-c', 'user.name=QA', '-c', 'user.email=qa@example.invalid',
                        'commit-tree', tree, '-m', 'replacement').decode('ascii')
            git('replace', base, other)
            self.assertEqual(git('cat-file', 'blob', base + ':plans/spec.json'), b'replacement bytes')
            self.assertEqual(i.source_blob(directory, base, 'plans/spec.json', 1024), b'approved bytes')

    def test_largest_envelope_can_be_read_and_republished_with_same_limit(self):
        e = envelope()
        design = b'x' * 32768
        e.update(design_base64=base64.b64encode(design).decode('ascii'), design_sha256=i.digest(design))
        spec = json.loads(base64.b64decode(e['spec_base64']).decode('utf-8'))
        spec['padding'] = 'x' * 16000
        raw = i.encoded(spec)
        e.update(spec_base64=base64.b64encode(raw).decode('ascii'), spec_sha256=i.digest(raw))
        i.validate(e)
        self.assertGreater(len(i.encoded(e)), 65536)
        self.store.save('a' * 64, e)
        self.assertEqual(self.store.load('a' * 64, i.MAX_ENVELOPE), e)
