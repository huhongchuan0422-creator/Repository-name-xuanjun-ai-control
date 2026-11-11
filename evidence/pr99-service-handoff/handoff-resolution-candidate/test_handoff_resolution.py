import ast
import hashlib
import json
import unittest
from unittest import mock
import resolve_received_handoff as m


class ResolutionTests(unittest.TestCase):
    def test_module_entry_matches_only_received_source_manifest(self):
        raw = b'[Service]\nExecStart=/usr/bin/python3.11 -u -m ai_service.wecom_customer_service --token DO_NOT_PRINT\n'
        p = m.command_plan(raw, {'ai_service/wecom_customer_service.py'})
        self.assertEqual(p['source_entry'], 'ai_service/wecom_customer_service.py')
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p))
        missing = m.command_plan(raw, set())
        self.assertIsNone(missing['source_entry'])
        self.assertEqual(missing['unmatched_entry']['name'], 'ai_service.wecom_customer_service')
        self.assertNotIn('DO_NOT_PRINT', json.dumps(missing))

    def test_unknown_python_inline_code_is_never_evaluated(self):
        p = m.command_plan(b'[Service]\nExecStart=/usr/bin/python3.11 -c "raise RuntimeError(\'DO_NOT_PRINT\')"\n', set())
        self.assertIsNone(p['source_entry'])
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p['unmatched_entry']))
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p))

    def test_ssh_forward_direction_and_credentials_remain_private(self):
        raw = b'[Service]\nEnvironment=SECRET=DO_NOT_PRINT\nExecStart=/usr/bin/ssh -NT -i /private/DO_NOT_PRINT -o StrictHostKeyChecking=yes -R 127.0.0.1:19444:127.0.0.1:18443 admin@47.101.152.210\n'
        p = m.command_plan(raw, set())
        self.assertEqual(p['ssh']['destination'], '47.101.152.210')
        self.assertEqual(p['ssh']['forwardings'][0], {'kind': 'R', 'bind': '127.0.0.1', 'listen_port': 19444, 'target': '127.0.0.1', 'target_port': 18443})
        self.assertTrue(p['ssh']['identity_file_configured'])
        self.assertEqual(p['environment_assignment_count'], 1)
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p))

    def test_ipv6_and_invalid_secret_targets(self):
        p = m.forwarding('L', '[::1]:1234:[::1]:4321')
        self.assertEqual(p['bind'], '::1')
        self.assertEqual(p['target'], '::1')
        self.assertEqual(m.forwarding('R', 'DO_NOT_PRINT')['status'], 'UNKNOWN_REDACTED')
        self.assertEqual(m.address('DO_NOT_PRINT'), 'UNKNOWN_REDACTED')
        self.assertEqual(m.address('https://DO_NOT_PRINT'), 'UNKNOWN_REDACTED')

    def test_docker_prefix_and_arguments_hidden(self):
        p = m.command_plan(b'[Service]\nExecStart=-/usr/local/bin/docker start -a DO_NOT_PRINT\n', set())
        self.assertEqual(p['program'], 'DOCKER')
        self.assertEqual(p['container_operation'], 'start')
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p))

    def test_unit_reset_and_other_commands_counted_not_executed(self):
        p = m.command_plan(b'[Service]\nExecStart=/bin/sh DO_NOT_PRINT\nExecStart=\nExecStart=/usr/bin/ssh -NT root@47.245.53.152\nExecStartPre=/bin/sh DO_NOT_PRINT\nExecStop=/bin/sh DO_NOT_PRINT\n', set())
        self.assertEqual(p['program'], 'SSH')
        self.assertEqual(p['extra_start_stop_commands'], 2)
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p))

    def fixture(self):
        data = {'pkg/__init__.py': b'from . import shared\n',
                'pkg/entry.py': b'import json\nfrom . import child\nfrom .shared import value\nimport requests\n',
                'pkg/child.py': b'from . import entry\n',
                'pkg/shared.py': b'value=1\n'}
        rows = {p: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for p, b in data.items()}
        return data, rows

    def test_real_ast_recursive_relative_import_cycle_and_package_initializers(self):
        data, rows = self.fixture()
        p = m.closure('pkg/entry.py', rows, data.__getitem__)
        self.assertEqual(p['source_files'], 4)
        self.assertEqual(p['missing_local_modules'], [])
        self.assertEqual(p['third_party_module_names'], ['requests'])
        self.assertFalse(p['runtime_data_or_configuration_closure_proven'])

    def test_source_hash_drift_stops_before_parse_or_execution(self):
        data, rows = self.fixture()
        data['pkg/entry.py'] += b'raise RuntimeError("DO_NOT_PRINT")\n'
        with self.assertRaisesRegex(m.Hold, 'RECEIVED_SOURCE_DRIFT'):
            m.closure('pkg/entry.py', rows, data.__getitem__)

    def test_missing_local_and_dynamic_imports_remain_explicit(self):
        data, rows = self.fixture()
        data['pkg/entry.py'] = b'import pkg.missing\nimport importlib\nimportlib.import_module("DO_NOT_PRINT")\n'
        rows['pkg/entry.py'] = {'bytes': len(data['pkg/entry.py']), 'sha256': m.sha(data['pkg/entry.py'])}
        p = m.closure('pkg/entry.py', rows, data.__getitem__)
        self.assertEqual(p['missing_local_modules'], ['pkg.missing'])
        self.assertEqual(p['dynamic_loading_calls'], 1)
        self.assertNotIn('DO_NOT_PRINT', json.dumps(p))

    def test_verified_manifest_aggregate_and_scope_are_enforced(self):
        rows = [{'path': 'code/pkg/p%04d.py' % n, 'bytes': n, 'sha256': m.sha(str(n).encode())} for n in range(1363)]
        aggregate = m.sha(''.join(r['path'][5:] + '\0' + r['sha256'] + '\0' + str(r['bytes']) + '\n' for r in rows).encode())
        rows.append({'path': 'database/trading.db', 'bytes': 100, 'sha256': m.DB_SHA})
        with mock.patch.object(m, 'SOURCE_AGGREGATE', aggregate):
            self.assertEqual(len(m.source_manifest({'files': rows})), 1363)
            rows[0]['sha256'] = '0' * 64
            with self.assertRaisesRegex(m.Hold, 'SOURCE_AGGREGATE_CHANGED'):
                m.source_manifest({'files': rows})


if __name__ == '__main__':
    unittest.main()
