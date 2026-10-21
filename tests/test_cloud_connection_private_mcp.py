import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import test_cloud_connection_queue as cases
from production.cloud_connection.queue import Hold, Queue
from production.cloud_connection.runtime import PrivateStore
from production.cloud_connection.private_mcp import PrivateMcp

class PrivateMcpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/root')
        self.root = Path(self.tmp.name)
        (self.root / 'private-results').mkdir(mode=0o700)
        q = Queue(str(self.root / 'queue.sqlite'), cases.PIN, {cases.ACTOR})
        r = cases.request()
        r.update(operation='fetch_os_release', arguments={'path': '/etc/os-release', 'max_bytes': 65536})
        q.submit(json.dumps(r), cases.ACTOR, cases.NOW)
        q.begin_dispatch('job-1', cases.NOW)
        q.record_invoke('job-1', 't-one')
        self.data = b'NAME=non-sensitive-test\n'
        self.sha = hashlib.sha256(self.data).hexdigest()
        store = PrivateStore(self.root / 'private-results')
        ref = store.put('job-1', self.data, self.sha)
        store.close()
        q.terminal('job-1','t-one',{'state':'SUCCESS','invoke_id':'t-one','file_ref':ref,
                                  'sha256':self.sha,'bytes':len(self.data)})
        q.close()
        os.chmod(self.root / 'queue.sqlite', 0o600)
        self.m = PrivateMcp(self.root)
    def tearDown(self):
        self.m.close()
        self.tmp.cleanup()
    def call(self, name, args=None):
        return self.m.call(name, {'request_id':'job-1'} if args is None else args)
    def rpc(self, method, params=None, mid=1):
        return self.m.handle({'jsonrpc':'2.0','id':mid,'method':method,'params':params or {}})
    def initialize(self):
        v=self.rpc('initialize', {'protocolVersion':'2025-03-26','clientInfo':{'name':'fixture','version':'1'},'capabilities':{}})
        self.assertIn('result',v)
        self.assertIsNone(self.m.handle({'jsonrpc':'2.0','method':'notifications/initialized'}))
    def test_complete_private_file_sha(self):
        self.initialize()
        v=self.rpc('tools/call',{'name':'read_result_file','arguments':{'request_id':'job-1'}})
        s=v['result']['structuredContent']
        self.assertEqual(base64.b64decode(s['data']),self.data)
        self.assertEqual(s['sha256'],self.sha)
    def test_status_contains_no_bytes(self):
        s=self.call('connection_status')['structuredContent']
        self.assertNotIn('data',s)
        self.assertEqual(s['production_authorization'],'NOT_GRANTED')
    def test_no_arbitrary_path(self):
        with self.assertRaises(Hold):
            self.call('read_result_file',{'request_id':'job-1','path':'/etc/shadow'})
    def test_no_request_path_traversal(self):
        with self.assertRaises(Hold):
            self.call('read_result_file',{'request_id':'../other'})
    def test_unsupported_execution_tool(self):
        with self.assertRaises(Hold):
            self.call('run_shell')
    def test_unknown_request(self):
        with self.assertRaises(Hold):
            self.call('read_result_file',{'request_id':'missing'})
    def test_readonly_database(self):
        import sqlite3
        with self.assertRaises(sqlite3.OperationalError):
            self.m.db.execute('DELETE FROM connection_jobs')
    def test_hash_tamper_not_returned(self):
        name=hashlib.sha256(b'job-1').hexdigest()+'.bin'
        (self.root/'private-results'/name).write_bytes(b'changed')
        with self.assertRaisesRegex(Hold,'SHA'):
            self.call('read_result_file')
    def test_symlink_not_followed(self):
        name=hashlib.sha256(b'job-1').hexdigest()+'.bin'
        p=self.root/'private-results'/name
        p.unlink()
        p.symlink_to('/etc/shadow')
        with self.assertRaises(OSError):
            self.call('read_result_file')
    def test_handshake_required(self):
        self.assertIn('error',self.rpc('tools/list'))
        self.initialize()
        self.assertEqual(len(self.rpc('tools/list')['result']['tools']),2)
    def test_notifications_never_read_files(self):
        self.assertIsNone(self.m.handle({'jsonrpc':'2.0','method':'tools/call','params':{'name':'read_result_file','arguments':{'request_id':'job-1'}}}))
    def test_bad_fields_sanitized(self):
        self.initialize()
        v=self.rpc('tools/call',{'name':'read_result_file','arguments':{'request_id':'job-1','path':'/secret'}})
        self.assertEqual(v['error']['message'],'HOLD_PRIVATE_TOOL')
        self.assertNotIn('/secret',json.dumps(v))
    def test_unsupported_protocol_does_not_initialize(self):
        self.assertIn('error',self.rpc('initialize',{'protocolVersion':'unreviewed'}))
        self.assertFalse(self.m.initialized)
