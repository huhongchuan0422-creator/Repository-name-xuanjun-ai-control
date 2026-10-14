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
if __name__=="__main__":
    unittest.main()
