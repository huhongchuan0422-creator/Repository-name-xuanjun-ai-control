"""Original file schemas and composition, synthetic identities, no provider IO."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.community_persistent_runtime import PersistentRuntime, NAMES
from scripts.community_saas_phase2 import Principal
from scripts.community_merchant_store import upsert_profile
from scripts.community_order_store import create_order, state

class PersistentHost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'business'
        self.scope = dict(tenant_id='tenant1', merchant_id='merchant1', store_id='store1')
        self.customer = Principal('tenant1', 'CUSTOMER')
        self.bindings = {self.customer: self.scope}
        self.clock = lambda: 1700000000
    def initialize(self):
        return PersistentRuntime.initialize(str(self.root), self.bindings, clock=self.clock)
    def reopen(self):
        return PersistentRuntime.open(str(self.root), self.bindings, clock=self.clock)
    def test_original_schemas_no_seed_no_random_keys_and_no_demo_admin(self):
        with patch('os.urandom', side_effect=AssertionError('NO_GENERATED_CREDENTIALS')):
            with self.initialize() as owner:
                runtime = owner.runtime
                self.assertIsNone(runtime.demo.qr_key)
                self.assertIsNone(runtime.demo.admin_policy)
                self.assertIs(runtime.saas.quotes, runtime.saas.modules)
                for db in owner.handles:
                    names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                    for table in names:
                        self.assertEqual(db.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0], 0)
                with self.assertRaises(ValueError):
                    runtime.dispatch(self.customer, 'community.qr', {'context':'mini'}, None)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'runtime.lock'} | {n+'.sqlite' for n in NAMES})
    def test_real_persistence_after_independent_process_restart(self):
        with self.initialize() as owner:
            create_order(owner.runtime.demo.db, self.scope, 'persisted_order', 123)
        code = """import sys,json
from scripts.community_persistent_runtime import PersistentRuntime
from scripts.community_saas_phase2 import Principal
from scripts.community_order_store import state
p=Principal('tenant1','CUSTOMER')
s=dict(tenant_id='tenant1',merchant_id='merchant1',store_id='store1')
with PersistentRuntime.open(sys.argv[1],{p:s},clock=lambda:1700000000) as owner:
 print(json.dumps(state(owner.runtime.demo.db,s,'persisted_order')))
"""
        result = subprocess.run([sys.executable, '-B', '-c', code, str(self.root)],
                                capture_output=True, text=True, timeout=15, check=True)
        self.assertEqual(json.loads(result.stdout)['amount_minor'], 123)
    def test_second_writer_and_reinitialization_refused_without_overwrite(self):
        with self.initialize() as owner:
            create_order(owner.runtime.demo.db, self.scope, 'one', 99)
            with self.assertRaises(BlockingIOError): self.reopen()
            with self.assertRaises(FileExistsError): self.initialize()
            self.assertEqual(state(owner.runtime.demo.db, self.scope, 'one')['amount_minor'], 99)
        with self.reopen() as owner:
            self.assertEqual(state(owner.runtime.demo.db, self.scope, 'one')['state'], 'PENDING')
    def test_missing_database_is_not_created_and_unknown_schema_is_not_repaired(self):
        with self.initialize(): pass
        missing = self.root/'refunds.sqlite'
        missing.unlink()
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaises(FileNotFoundError): self.reopen()
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})
        self.assertFalse(missing.exists())
        db=sqlite3.connect(missing);db.execute('CREATE TABLE unexpected(value)');db.commit();db.close()
        os.chmod(missing,0o600)
        with self.assertRaisesRegex(ValueError,'CURRENT_RUNTIME_SCHEMA_REQUIRED'): self.reopen()
        db=sqlite3.connect(missing)
        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('unexpected',)])
        db.close()
    def test_partial_initialization_preserved_and_never_retried(self):
        with patch('scripts.community_merchant_store.open_store',side_effect=RuntimeError('synthetic disk fault')):
            with self.assertRaisesRegex(RuntimeError,'synthetic disk fault'): self.initialize()
        self.assertTrue((self.root/'orders.sqlite').exists())
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaises(FileExistsError):self.initialize()
        with self.assertRaises(FileNotFoundError):self.reopen()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
    def test_symlink_hardlink_and_public_file_refused_before_database_open(self):
        with self.initialize():pass
        target=self.root/'orders.sqlite'
        original=target.read_bytes()
        target.unlink();target.symlink_to(self.root/'merchants.sqlite')
        with patch('sqlite3.connect',side_effect=AssertionError('NO_DB_OPEN')):
            with self.assertRaises(PermissionError):self.reopen()
        target.unlink();target.write_bytes(original);os.chmod(target,0o600)
        alias=self.root/'alias';os.link(target,alias)
        with patch('sqlite3.connect',side_effect=AssertionError('NO_DB_OPEN')):
            with self.assertRaises(PermissionError):self.reopen()
        alias.unlink();os.chmod(target,0o644)
        with patch('sqlite3.connect',side_effect=AssertionError('NO_DB_OPEN')):
            with self.assertRaises(PermissionError):self.reopen()
    def test_bad_bindings_clock_and_nonprivate_parent_have_no_creation(self):
        for bindings,clock in (({},self.clock),({Principal('other','CUSTOMER'):self.scope},self.clock),(self.bindings,None)):
            with self.assertRaises((ValueError,PermissionError)):
                PersistentRuntime.initialize(str(self.root),bindings,clock=clock)
            self.assertFalse(self.root.exists())
        os.chmod(self.tmp.name,0o755)
        with self.assertRaises(PermissionError):self.initialize()
        self.assertFalse(self.root.exists())
        os.chmod(self.tmp.name,0o700)
    def test_same_original_application_composition_and_borrowed_ownership(self):
        import test_community_mini_center_identity as fixture
        from scripts.community_mini_application import MiniApplication
        from scripts.community_mini_host_config import stores
        fx=fixture.ExistingCenterComposition();fx.setUp()
        try:
            with PersistentRuntime.initialize(str(self.root),fx.stage.api.bindings,clock=fx.center.now) as owner:
                config=dict(version=1,appid=fx.identity.appid,https_origin='https://uk.wenwenwenyiyiyi.work',
                    scenes={'shop1':dict(project='project1',principal='customer')},
                    stores={name:db.execute('PRAGMA database_list').fetchone()[2]
                            for name,db in stores(fx.center,owner.runtime).items()})
                with patch('scripts.community_mini_application.LocalStage',side_effect=AssertionError('NO_LOCAL_STAGE')):
                    app=MiniApplication.from_existing_runtime(fx.center,owner.runtime,
                        {'customer':fx.stage.customer},config,'a'*32)
                    app.configure_operations({'merchant':dict(user_id=fx.uid1,project='project1',
                        project_roles=['OWNER'],principal=fx.stage.merchant)})
                    app.configure_commerce()
                    self.assertIs(app.identity.runtime,owner.runtime)
                    self.assertIsNone(getattr(app.gateway,'payments',None))
                    app.close()
                self.assertEqual(owner.runtime.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0],0)
                self.assertEqual(fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],2)
        finally:fx.tearDown()

if __name__=='__main__':unittest.main()
