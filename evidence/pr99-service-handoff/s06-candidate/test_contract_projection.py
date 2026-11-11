import json
import unittest
import project_received_contract as m


class ProjectionTests(unittest.TestCase):
    def test_only_direct_python_entry_is_published(self):
        row = m.entry_summary(b'[Service]\nExecStart=/opt/trading-system/venv/bin/python -u scripts/secure_secrets_portal_server.py --token DO_NOT_PRINT\n')
        self.assertEqual(row['entrypoint'], 'scripts/secure_secrets_portal_server.py')
        self.assertNotIn('DO_NOT_PRINT', json.dumps(row))

    def test_python_inline_code_is_never_published(self):
        row = m.entry_summary(b'[Service]\nExecStart=/usr/bin/python3.11 -c "secret=DO_NOT_PRINT"\n')
        self.assertEqual(row['entrypoint'], 'UNKNOWN')
        self.assertNotIn('DO_NOT_PRINT', json.dumps(row))

    def test_ssh_shell_and_unknown_argv_are_never_published(self):
        for exe, expected in [('/usr/bin/ssh', 'SSH'), ('/bin/bash', 'SHELL'), ('/usr/bin/docker', 'DOCKER'), ('/private/DO_NOT_PRINT', 'UNKNOWN')]:
            row = m.entry_summary(('[Service]\nExecStart=' + exe + ' -c DO_NOT_PRINT\n').encode())
            self.assertEqual(row['program'], expected)
            self.assertNotIn('DO_NOT_PRINT', json.dumps(row))

    def test_reset_multiline_and_other_sections(self):
        row = m.entry_summary(b'[Unit]\nExecStart=/bin/bash DO_NOT_PRINT\n[Service]\nExecStart=/bin/bash OLD\nExecStart=\nExecStart=/usr/bin/python3.11 \\\n -B /opt/trading-system/scripts/secure_secrets_portal_server.py --secret DO_NOT_PRINT\n')
        self.assertEqual(row['exec_start_count'], 1)
        self.assertEqual(row['program'], 'PYTHON')
        self.assertTrue(row['entrypoint'].endswith('/secure_secrets_portal_server.py'))
        self.assertNotIn('DO_NOT_PRINT', json.dumps(row))

    def test_unknown_paths_and_traversal_redacted(self):
        for path in ['/opt/trading-system/../DO_NOT_PRINT', 'https://DO_NOT_PRINT', '/private/DO_NOT_PRINT']:
            self.assertEqual(m.safe_path(path), 'UNKNOWN_REDACTED')

    def test_full_projection_excludes_raw_auth_env_and_unknown_dependencies(self):
        name = 'secure-secrets-portal.service'
        private = {'environment_files_opened': False, 'database_opened': False, 'argv_read': False,
                   'units': {name: {'EnvironmentFiles': '/private/DO_NOT_PRINT', 'Environment': 'DO_NOT_PRINT',
                                    'WorkingDirectory': '/opt/trading-system', 'User': 'admin',
                                    'After': 'docker.service DO_NOT_PRINT.service'}}}
        files = {'private-runtime.json': json.dumps(private).encode(),
                 'units/' + name: b'[Service]\nEnvironment=TOKEN=DO_NOT_PRINT\nExecStart=/usr/bin/ssh --password DO_NOT_PRINT\n',
                 'dropins/provider-health-alert.conf': b'DO_NOT_PRINT'}
        result = m.projection(files, (name,))
        self.assertNotIn('DO_NOT_PRINT', json.dumps(result))
        self.assertTrue(result['units'][0]['environment_files_configured'])
        self.assertEqual(result['units'][0]['dependencies']['After'], ['docker.service'])

    def test_scope_drift_is_rejected(self):
        files = {'private-runtime.json': json.dumps({'environment_files_opened': True}).encode()}
        with self.assertRaisesRegex(RuntimeError, 'PRIVATE_METADATA_SCOPE'):
            m.projection(files, ())


if __name__ == '__main__':
    unittest.main()
