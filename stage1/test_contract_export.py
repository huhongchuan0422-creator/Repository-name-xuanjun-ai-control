import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('contract_export', str(Path(__file__).resolve().parent.parent / 'scripts' / 'uk-contract-export.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ContractTests(unittest.TestCase):
    def test_ast_export_redacts_all_unlisted_literal_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'source.py')
            with open(path, 'w') as stream:
                stream.write('password="private-value"\nnumber=123456789\nheader="Authorization"\nfield="request_id"\nraw=b"private-bytes"\n')
            class User:
                pw_uid = os.getuid()
            with patch.object(module.pwd, 'getpwnam', return_value=User()):
                exported = module.contract(path)
            self.assertFalse(exported['source_exported'])
            self.assertNotIn('source', exported)
            self.assertNotIn('private-value', exported['contract_ast'])
            self.assertNotIn('123456789', exported['contract_ast'])
            self.assertNotIn('private-bytes', exported['contract_ast'])
            self.assertIn('Authorization', exported['contract_ast'])
            self.assertIn('request_id', exported['contract_ast'])

    def test_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, 'target')
            os.mkdir(target)
            with open(os.path.join(target, 'source.py'), 'w') as stream:
                stream.write('pass\n')
            link = os.path.join(folder, 'link')
            os.symlink(target, link)
            class User:
                pw_uid = os.getuid()
            with patch.object(module.pwd, 'getpwnam', return_value=User()):
                with self.assertRaises(ValueError):
                    module.contract(os.path.join(link, 'source.py'))


if __name__ == '__main__':
    unittest.main()
