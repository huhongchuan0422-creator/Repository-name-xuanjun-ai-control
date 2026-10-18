"""Finite negative tests for the new versioned acceptance boundary."""
import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('versioned_full_gate',str(HERE/'verify_full.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class Contracts(unittest.TestCase):
    def row(self):return {'bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
    def test_exact_file_pin_accepts(self):g.file_record(b'abc',self.row())
    def test_wrong_size_refuses(self):
        row=self.row();row['bytes']=4
        with self.assertRaises(ValueError):g.file_record(b'abc',row)
    def test_boolean_size_refuses(self):
        row=self.row();row['bytes']=True
        with self.assertRaises(ValueError):g.file_record(b'abc',row)
    def test_malformed_sha_refuses(self):
        row=self.row();row['sha256']='z'*64
        with self.assertRaises(ValueError):g.file_record(b'abc',row)
    def test_changed_bytes_refuse(self):
        with self.assertRaises(ValueError):g.file_record(b'abd',self.row())
    def test_extra_pin_field_refuses(self):
        row=self.row();row['allow_override']=True
        with self.assertRaises(ValueError):g.file_record(b'abc',row)
    def test_non_bytes_refuses(self):
        with self.assertRaises(ValueError):g.file_record('abc',self.row())
    def test_parent_traversal_refuses(self):
        with self.assertRaises(ValueError):g.path_name('a/../b')
    def test_absolute_path_refuses(self):
        with self.assertRaises(ValueError):g.path_name('/a')
    def test_empty_path_component_refuses(self):
        with self.assertRaises(ValueError):g.path_name('a//b')
    def test_backslash_path_refuses(self):
        with self.assertRaises(ValueError):g.path_name('a\\b')
    def test_zero_or_invalid_source_identity_refuses(self):
        for value in ('0'*40,'x'*40,True,None):
            with self.subTest(value=value),self.assertRaises(ValueError):g.identity(value)
    def test_skip_failure_boolean_count_and_wrong_total_refuse(self):
        good={'state':'PASS','tests':17,'errors':0,'failures':0,'skips':0}
        g.exact_terminal(good,17)
        for key,value in (('tests',True),('tests',16),('errors',1),('failures',1),('skips',1),('state','HOLD')):
            row=dict(good);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):g.exact_terminal(row,17)
    def test_versioned_ports_retain_every_original_test_name(self):
        for sub,name,count in (('preparation','test_prepare_successor',31),('delivery','test_successor_delivery',47)):
            def names(path):
                return [n.name for n in ast.walk(ast.parse(path.read_bytes())) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
            original=names(HERE.parent/sub/(name+'.py'));current=names(HERE.parent/sub/(name+'_v2.py'))
            self.assertEqual(len(original),count);self.assertEqual(original,current)
    def test_inventory_rejects_unknown_file_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);candidate=root/g.PREFIX;candidate.mkdir(parents=True)
            file=candidate/'fixed.py';file.write_bytes(b'abc');file.chmod(0o444)
            records={g.PREFIX+'fixed.py':self.row()};g.inventory(root,records)
            extra=candidate/'extra.py';extra.write_bytes(b'extra')
            with self.assertRaises(ValueError):g.inventory(root,records)
            extra.unlink();extra.symlink_to(file)
            with self.assertRaises(ValueError):g.inventory(root,records)
            extra.unlink();outside=root/'outside';os.link(str(file),str(outside))
            with self.assertRaises(ValueError):g.inventory(root,records)

if __name__=='__main__':
    program=unittest.main(exit=False);r=program.result
    row={'state':'PASS' if r.wasSuccessful() else 'HOLD','tests':r.testsRun,
         'errors':len(r.errors),'failures':len(r.failures),'skips':len(r.skipped)}
    g.exact_terminal(row,15);print('FULL_V2_CONTRACT='+json.dumps(row,sort_keys=True))
