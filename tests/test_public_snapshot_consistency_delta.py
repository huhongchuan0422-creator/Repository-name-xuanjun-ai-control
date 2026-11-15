import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.environ.get('TEST_APP_SCRIPTS',os.path.join(ROOT,'scripts')))
import task_center_app as app
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_supervisor import Supervisor

KEY=b'0123456789abcdef0123456789abcdef'

class PublicSnapshotConsistency(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.mkdtemp();self.db=os.path.join(self.tmp,'fixture.sqlite')
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        GatewayKernel(supervisor,authority).register_graph(authority.issue('tenant-fixture','seed'),demo_graph('tenant-fixture'))
        supervisor.db.execute("UPDATE tasks SET state='READY',last_event_at=100")
        supervisor.db.commit();supervisor.close()
    def tearDown(self):shutil.rmtree(self.tmp)
    @staticmethod
    def board(result):return next(x for x in result['boards'] if x['board_id']=='research-development')
    def test_concurrent_wal_writer_cannot_mix_counts_and_source_time(self):
        writer=sqlite3.connect(self.db,timeout=2)
        self.assertEqual(writer.execute('PRAGMA journal_mode').fetchone()[0].lower(),'wal')
        original=app._read_only_connection; calls=[];errors=[]
        def open_traced(*args,**kwargs):
            conn=original(*args,**kwargs)
            def trace(sql):
                if 'SELECT MAX(t.last_event_at)' in sql and not calls:
                    calls.append(True)
                    try:
                        writer.execute("UPDATE tasks SET state='STARTED',last_event_at=200 WHERE task_id='demo-c'")
                        writer.commit()
                    except Exception as exc:errors.append(repr(exc))
            conn.set_trace_callback(trace);return conn
        try:
            with patch.object(app,'_read_only_connection',side_effect=open_traced):
                before=app.read_only_public_projection(self.db,KEY,'tenant-fixture','viewer')
            after=app.read_only_public_projection(self.db,KEY,'tenant-fixture','viewer')
        finally:writer.close()
        self.assertEqual(calls,[True]);self.assertEqual(errors,[])
        self.assertEqual(self.board(before)['active_count'],0)
        self.assertEqual(before['observed_at'],100)
        self.assertEqual(self.board(after)['active_count'],1)
        self.assertEqual(after['observed_at'],200)
        self.assertNotEqual(before['snapshot_sha256'],after['snapshot_sha256'])
        for result in (before,after):
            public={k:result[k] for k in ('mode','production_status','observed_at','boards')}
            raw=json.dumps(public,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
            self.assertEqual(result['snapshot_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['observed_at_unit'],'unix_seconds')
            self.assertEqual(result['observed_at_semantics'],'MAX_CANONICAL_TASK_LAST_EVENT_AT')
            self.assertEqual(result['freshness'],'UNKNOWN');self.assertIsNone(result['valid_until'])
            self.assertNotIn('tenant-fixture',json.dumps(result))
            self.assertNotIn('demo-c',json.dumps(result))
    def test_public_read_does_not_change_database_or_wal(self):
        writer=sqlite3.connect(self.db,timeout=2)
        try:
            writer.execute("UPDATE tasks SET last_event_at=123 WHERE task_id='demo-c'")
            writer.commit()
            paths=(self.db,self.db+'-wal')
            def digests():
                result=[]
                for path in paths:
                    with open(path,'rb') as stream:result.append(hashlib.sha256(stream.read()).hexdigest())
                return result
            before=digests()
            value=app.read_only_public_projection(self.db,KEY,'tenant-fixture','viewer')
            self.assertEqual(value['observed_at'],123)
            self.assertEqual(digests(),before)
        finally:writer.close()
    def test_anonymous_http_response_and_legacy_projection(self):
        server=app.make_server(self.db,KEY,'tenant-fixture','viewer',port=0)
        thread=threading.Thread(target=server.serve_forever);thread.daemon=True;thread.start()
        try:
            root='http://127.0.0.1:%d'%server.server_port
            with urlopen(root+'/api/public-projection',timeout=3) as response:
                self.assertEqual(response.status,200);self.assertEqual(response.headers['Cache-Control'],'no-store')
                public=json.loads(response.read().decode('utf-8'))
            self.assertEqual(public['source'],'task-center-public-projection')
            self.assertEqual(public['schema_version'],1)
            self.assertEqual(public['observed_at'],100)
            self.assertNotIn('tasks',public);self.assertNotIn('tenant_id',public)
            with urlopen(root+'/api/projection',timeout=3) as response:
                private=json.loads(response.read().decode('utf-8'))
            self.assertEqual(private['schema'],3);self.assertEqual(private['tenant_id'],'tenant-fixture')
            self.assertEqual(len(private['tasks']),3)
        finally:server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':unittest.main()
