"""N1/N2 cleanup fault injections; no hosts, network or payment."""
import sqlite3
import unittest
from unittest.mock import patch
from scripts import community_demo_bootstrap as bootstrap
from scripts.community_demo_api import _close_all_owned, _OwnedLocalDemoHTTPServer

class CloseSpy:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
    def close(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("close_fault")

class CleanupTests(unittest.TestCase):
    def test_second_connection_failure_closes_first(self):
        actual = sqlite3.connect
        allocated = []
        def fail_second(*args, **kwargs):
            if kwargs.get("check_same_thread") is False:
                if allocated:
                    raise sqlite3.OperationalError("second_connect_fault")
                conn = actual(*args,**kwargs)
                allocated.append(conn)
                return conn
            return actual(*args,**kwargs)
        with patch.object(bootstrap.sqlite3, "connect",side_effect=fail_second):
            with self.assertRaisesRegex(sqlite3.OperationalError,"second_connect_fault"):
                bootstrap.fixture_stores()
        self.assertEqual(len(allocated),1)
        with self.assertRaises(sqlite3.ProgrammingError):
            allocated[0].execute("SELECT 1")
    def test_each_close_attempted_when_first_fails(self):
        a,b,c=CloseSpy(True),CloseSpy(),CloseSpy(True)
        with self.assertRaisesRegex(RuntimeError,"close_fault"):
            _close_all_owned([a,b,c])
        self.assertEqual([a.calls,b.calls,c.calls],[1,1,1])
    def test_server_close_is_idempotent_for_owned_handles(self):
        a,b=CloseSpy(True),CloseSpy()
        server=_OwnedLocalDemoHTTPServer(("127.0.0.1",0),None,[a,b])
        with self.assertRaisesRegex(RuntimeError,"close_fault"):
            server.server_close()
        server.server_close()
        self.assertEqual([a.calls,b.calls],[1,1])
    def test_normal_default_demo_closes_all_runtime_databases(self):
        from scripts.community_demo_api import serve_local
        srv=serve_local(port=0)
        owned=list(srv._owned_connections)
        srv.server_close()
        for db in owned:
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute("SELECT 1")
    def test_success_closes_seed_sources_before_transferring_runtime(self):
        real_m,real_a=bootstrap.open_store,bootstrap.open_offline
        created=[]
        def traced(factory):
            def build():
                conn=factory()
                created.append(conn)
                return conn
            return build
        with patch.object(bootstrap,"open_store",side_effect=traced(real_m)),patch.object(bootstrap,"open_offline",side_effect=traced(real_a)):
            runtime_m,runtime_a,_=bootstrap.fixture_stores()
        try:
            self.assertEqual(len(created),2)
            for seed in created:
                with self.assertRaises(sqlite3.ProgrammingError):
                    seed.execute("SELECT 1")
            self.assertEqual(runtime_m.execute("SELECT COUNT(*) FROM merchant_profiles").fetchone()[0],2)
            self.assertEqual(runtime_a.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],2)
        finally:
            runtime_m.close();runtime_a.close()
    def test_primary_backup_failure_survives_failing_source_close(self):
        real_m,real_a=bootstrap.open_store,bootstrap.open_offline
        class Proxy:
            def __init__(self,connection,fail_close=False,fail_backup=False):
                self.connection=connection
                self.fail_close=fail_close
                self.fail_backup=fail_backup
                self.calls=0
            def __getattr__(self,name):
                return getattr(self.connection,name)
            def __enter__(self):
                self.connection.__enter__();return self
            def __exit__(self,*args):
                return self.connection.__exit__(*args)
            def backup(self,target):
                if self.fail_backup:
                    raise ValueError("primary_backup_fault")
                return self.connection.backup(target)
            def close(self):
                self.calls+=1
                self.connection.close()
                if self.fail_close:
                    raise RuntimeError("source_close_fault")
        m=Proxy(real_m(),fail_backup=True)
        a=Proxy(real_a(),fail_close=True)
        actual_connect=sqlite3.connect
        runtimes=[]
        def tracked_connect(*args,**kwargs):
            handle=actual_connect(*args,**kwargs)
            if kwargs.get("check_same_thread") is False:
                runtimes.append(handle)
            return handle
        with patch.object(bootstrap,"open_store",return_value=m),patch.object(bootstrap,"open_offline",return_value=a),patch.object(bootstrap.sqlite3,"connect",side_effect=tracked_connect):
            with self.assertRaisesRegex(ValueError,"primary_backup_fault"):
                bootstrap.fixture_stores()
        self.assertEqual((m.calls,a.calls),(1,1))
        self.assertEqual(len(runtimes),2)
        for handle in runtimes:
            with self.assertRaises(sqlite3.ProgrammingError):
                handle.execute("SELECT 1")
    def test_source_close_failure_on_success_closes_runtime_too(self):
        real_m,real_a=bootstrap.open_store,bootstrap.open_offline
        class Proxy:
            def __init__(self,db,fail=False):
                self.db=db;self.fail=fail;self.calls=0
            def __getattr__(self,name):return getattr(self.db,name)
            def __enter__(self):
                self.db.__enter__();return self
            def __exit__(self,*args):return self.db.__exit__(*args)
            def close(self):
                self.calls+=1
                self.db.close()
                if self.fail:raise RuntimeError("source_close_fault")
        m=Proxy(real_m(),fail=True)
        a=Proxy(real_a())
        actual_connect=sqlite3.connect
        runtimes=[]
        def tracked(*args,**kwargs):
            db=actual_connect(*args,**kwargs)
            if kwargs.get("check_same_thread") is False:runtimes.append(db)
            return db
        with patch.object(bootstrap,"open_store",return_value=m),patch.object(bootstrap,"open_offline",return_value=a),patch.object(bootstrap.sqlite3,"connect",side_effect=tracked):
            with self.assertRaisesRegex(RuntimeError,"source_close_fault"):
                bootstrap.fixture_stores()
        self.assertEqual((m.calls,a.calls),(1,1))
        for db in runtimes:
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute("SELECT 1")
if __name__=="__main__":
    unittest.main()
