import ast
import unittest
import runpy
from pathlib import Path
from types import SimpleNamespace
subject = SimpleNamespace(**runpy.run_path(str(Path(__file__).with_name('storage_source_analysis.py')), run_name='analysis_definitions'))


class StorageAnalysisTests(unittest.TestCase):
    def analyze(self, source, filename='ai_service/example.py'):
        return subject.analyze_source(source, filename, Defaults, shape)

    def test_package_and_module_candidates(self):
        self.assertEqual(subject.module_candidates('database.repositories'),
            ('database/repositories.py', 'database/repositories/__init__.py'))

    def test_module_traversal_rejected(self):
        for value in ('../secret', 'a..b', '/etc/passwd', 'a/b', '', 'a;run()'):
            with self.assertRaises(ValueError):
                subject.module_candidates(value)

    def test_relative_package_export(self):
        tree = ast.parse('from .credential_repository import CredentialRepository')
        self.assertEqual(subject.imports(tree, 'database/repositories/__init__.py'),
            {'CredentialRepository': 'database.repositories.credential_repository.CredentialRepository'})

    def test_nested_optional_import(self):
        result = self.analyze('def factory():\n from douyin.tokens import DouyinTokenLifecycleStore\n return DouyinTokenLifecycleStore(root=unknown)')
        self.assertEqual(result['constructors'][0]['name'], 'douyin.tokens.DouyinTokenLifecycleStore')
        self.assertEqual(result['constructors'][0]['keywords'][0]['name'], 'root')

    def test_keyword_runtime_path_bound(self):
        result = self.analyze('from pathlib import Path\nROOT=Path("/opt/trading-system/runtime/portal")\nx=CredentialStore(path=ROOT / "credentials.json")')
        value = result['constructors'][0]['keywords'][0]['value']
        self.assertEqual(value['source_runtime_path'], '/opt/trading-system/runtime/portal/credentials.json')

    def test_private_keyword_literal_redacted(self):
        result = self.analyze('x=CredentialStore(master_key="DO_NOT_DISCLOSE_ABC")')
        self.assertNotIn('DO_NOT_DISCLOSE_ABC', str(result))
        self.assertIsNone(result['constructors'][0]['keywords'][0]['value']['source_runtime_path'])

    def test_environment_always_unknown(self):
        result = self.analyze('import os\nx=CredentialStore(path=os.getenv("TRADING_DATABASE_URL", "/opt/trading-system/runtime/default.db"))')
        self.assertIsNone(result['constructors'][0]['keywords'][0]['value']['source_runtime_path'])

    def test_required_parameter_unknown(self):
        result = self.analyze('def make(path):\n return CredentialStore(path=path)')
        self.assertIsNone(result['constructors'][0]['keywords'][0]['value']['source_runtime_path'])

    def test_class_default_assignment(self):
        result = self.analyze('from pathlib import Path\nclass CredentialStore:\n def __init__(self,path=Path("/opt/trading-system/runtime/credentials.json")):\n  self.path=path')
        self.assertEqual(result['path_assignments'][0]['value']['source_runtime_path'], '/opt/trading-system/runtime/credentials.json')

    def test_cli_default_source_only(self):
        result = self.analyze('from pathlib import Path\nROOT=Path("/opt/trading-system/runtime/portal")\nparser.add_argument("--state-root",default=ROOT)')
        self.assertEqual(result['cli_defaults'][0]['default']['source_runtime_path'], '/opt/trading-system/runtime/portal')

    def test_arbitrary_code_never_executed(self):
        result = self.analyze('raise RuntimeError("MUST_NOT_RUN")\nimport uninstalled_business_module\nx=CredentialStore(path=open("/etc/shadow").read())')
        self.assertIsNone(result['constructors'][0]['keywords'][0]['value']['source_runtime_path'])
        self.assertNotIn('/etc/shadow', str(result))

    def test_traversal_private_and_nonruntime_not_paths(self):
        for value in ('/opt/trading-system/runtime/../secret', '/opt/trading-system/runtime/./a', '/etc/shadow', '/opt/trading-system/runtime/token?secret=x'):
            self.assertIsNone(subject.runtime_path(value))

    def test_conditional_unknown_is_not_absent(self):
        result = self.analyze('def factory(path):\n if condition:\n  return CredentialStore(path=path or "/opt/trading-system/runtime/fallback.json")')
        self.assertIsNone(result['constructors'][0]['keywords'][0]['value']['source_runtime_path'])

    def test_loop_does_not_retain_stale_path(self):
        result = self.analyze('path="/opt/trading-system/runtime/old.json"\nfor path in unknown:\n pass\nx=CredentialStore(path=path)')
        self.assertIsNone(result['constructors'][0]['keywords'][0]['value']['source_runtime_path'])

    def test_unknown_kwargs_expansion_is_explicit(self):
        result = self.analyze('x=CredentialStore(**configuration)')
        self.assertEqual(result['constructors'][0]['keywords'][0]['name'], 'EXPANSION_UNRESOLVED')


if __name__ == '__main__':
    host = runpy.run_path(str(Path(__file__).with_name('app_storage_map_host.py')), run_name='test_definitions')
    Defaults, shape = host['Defaults'], host['shape']
    unittest.main()
