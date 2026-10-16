import json
import unittest
from unittest import mock
from korea.phase_c import source_schema as schema
from readonly_reconciliation_adapter import TABLE_SPECS


class SchemaTests(unittest.TestCase):
    def test_frozen_columns_match_existing_reconciliation_contract(self):
        self.assertEqual(schema.REQUIRED,{table:cols for table,cols in TABLE_SPECS.values()})
    def test_sql_with_nested_default_is_lexed_without_execution_or_literals(self):
        raw=b'''raise RuntimeError("must not execute")
SQL="""CREATE TABLE IF NOT EXISTS account_capabilities (
id INTEGER PRIMARY KEY, account_id TEXT, environment TEXT DEFAULT('private-literal'),
position_mode TEXT, status TEXT, verified_time INTEGER);"""
'''
        result=schema.declarations(raw)
        self.assertEqual(result['account_capabilities'][0],set(schema.REQUIRED['account_capabilities']))
        self.assertNotIn('private-literal',repr(result))
    def test_orm_names_only_and_dynamic_sql_remains_unresolved(self):
        result=schema.declarations(b'''class Account:
 __tablename__='account_snapshots'
 id=Column(Integer)
 snapshot_id=sql.Column(Text)
 secret_value=Column('not-exported')
sql=f"CREATE TABLE {unknown} ({private})"
''')
        self.assertEqual(result,{'account_snapshots':[{'id','snapshot_id'}]})
    def test_root_refused_before_source_open(self):
        with mock.patch.object(schema.os,'geteuid',return_value=0),\
             mock.patch.object(schema.os,'open',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(RuntimeError,'NONROOT_TOKYO_REQUIRED'):schema.main()
