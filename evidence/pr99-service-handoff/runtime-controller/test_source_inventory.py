import tempfile
import unittest
from pathlib import Path
from source_inventory import python_entry, inspect_graph


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'ai_service').mkdir()
        (self.root / 'ai_service/__init__.py').write_text('')
        (self.root / 'ai_service/wecom.py').write_text('from .store import Repository\n')
        (self.root / 'ai_service/store.py').write_text('def save():\n    SessionLocal().commit()\n')

    def test_module_entry_previously_missed(self):
        result = python_entry(['/usr/bin/python3.11', '-I', '-m', 'ai_service.wecom'], self.root, self.root)
        self.assertEqual(result, self.root / 'ai_service/wecom.py')

    def test_script_entry(self):
        result = python_entry(['/usr/bin/python3', 'ai_service/wecom.py'], self.root, self.root)
        self.assertEqual(result, self.root / 'ai_service/wecom.py')

    def test_relative_import_and_write_dependency(self):
        result = inspect_graph(self.root / 'ai_service/wecom.py', self.root)
        self.assertIn('SessionLocal', result['ai_service/store.py']['database_markers'])
        self.assertIn('commit', result['ai_service/store.py']['database_markers'])

    def test_dynamic_import_remains_unknown(self):
        (self.root / 'ai_service/wecom.py').write_text('__import__(runtime_name)\n')
        result = inspect_graph(self.root / 'ai_service/wecom.py', self.root)
        self.assertEqual(result['ai_service/wecom.py']['unresolved_dynamic_import_lines'], [1])

    def test_no_source_or_secret_values_in_evidence(self):
        marker = 'PRIVATE_VALUE_MUST_NOT_BE_PRINTED'
        (self.root / 'ai_service/wecom.py').write_text('secret = "' + marker + '"\n')
        self.assertNotIn(marker, str(inspect_graph(self.root / 'ai_service/wecom.py', self.root)))

    def test_inline_python_not_claimed_resolved(self):
        self.assertIsNone(python_entry(['/usr/bin/python3', '-c', 'anything'], self.root, self.root))

    def test_symlink_rejected(self):
        (self.root / 'ai_service/alias.py').symlink_to('store.py')
        with self.assertRaisesRegex(RuntimeError, 'UNSAFE'):
            inspect_graph(self.root / 'ai_service/alias.py', self.root)


if __name__ == '__main__':
    unittest.main()
