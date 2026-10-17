import runpy
from pathlib import Path
import unittest
N=runpy.run_path(str(Path(__file__).with_name('inspect_closure.py')))
class ClosureTests(unittest.TestCase):
 def scan(self,files,initial):
  index={N['module_name'](p):p for p in files}
  return N['closure'](index,initial,files.__getitem__)
 def test_lazy_table_relative_and_recursive_import(self):
  files={'app.py':b'from database.repositories import AuditRepository',
   'database/__init__.py':b'',
   'database/repositories/__init__.py':b"TABLE={'AuditRepository':('audit_repository','AuditRepository')}\ndef __getattr__(name):\n return import_module(TABLE[name][0])",
   'database/repositories/audit_repository.py':b'from .base import Base',
   'database/repositories/base.py':b'import sqlite3'}
  selected,_,dynamic,external=self.scan(files,['app.py'])
  self.assertEqual(selected,set(files));self.assertEqual(dynamic[0]['kind'],'import_module')
  self.assertIn('sqlite3',external)
 def test_literal_dynamic_import_and_parent_initializer(self):
  files={'app.py':b"importlib.import_module('pkg.worker')",'pkg/__init__.py':b'','pkg/worker.py':b''}
  self.assertEqual(self.scan(files,['app.py'])[0],set(files))
 def test_no_business_execution(self):
  files={'app.py':b"raise RuntimeError('must never execute')\nimport pkg",'pkg/__init__.py':b''}
  self.assertEqual(self.scan(files,['app.py'])[0],set(files))
 def test_nonmodule_strings_not_admitted(self):
  files={'app.py':b"secret='https://example.invalid/private'",'unrelated.py':b''}
  self.assertEqual(self.scan(files,['app.py'])[0],{'app.py'})
 def test_dynamic_unknown_is_explicit(self):
  files={'app.py':b'importlib.import_module(variable)'}
  row=self.scan(files,['app.py'])[2][0]
  self.assertFalse(row['literal_first_argument'])
 def test_cycle_terminates(self):
  files={'a.py':b'import b','b.py':b'import a'}
  self.assertEqual(self.scan(files,['a.py'])[0],set(files))
if __name__=='__main__':unittest.main()
