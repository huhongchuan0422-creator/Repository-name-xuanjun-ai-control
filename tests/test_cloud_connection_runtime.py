import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import test_cloud_connection_queue as cases
import test_cloud_connection_worker as transport
from production.cloud_connection.queue import Hold
from production.cloud_connection.runtime import Loop, PrivateStore
from production.cloud_connection.worker import PREFIX

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/root')
        self.root = Path(self.tmp.name)
        self.store = PrivateStore(self.root)
    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
    def put(self, data=b'private fixture'):
        return self.store.put('job-1', data, hashlib.sha256(data).hexdigest())
    def test_reopen(self):
        ref = self.put()
        other = PrivateStore(self.root)
        try:
            self.assertEqual(other.read(ref.split(':')[1]), b'private fixture')
        finally:
            other.close()
    def test_idempotent_and_rebind(self):
        self.assertEqual(self.put(), self.put())
        with self.assertRaisesRegex(Hold, 'REBOUND'):
            self.put(b'different')
    def test_no_traversal(self):
        with self.assertRaises(Hold):
            self.store.put('../escape', b'', hashlib.sha256(b'').hexdigest())
    def test_wrong_sha(self):
        with self.assertRaises(Hold):
            self.store.put('job-1', b'secret', '0' * 64)
        self.assertEqual(os.listdir(self.root), [])
    def test_symlink_object(self):
        (self.root / (hashlib.sha256(b'job-1').hexdigest() + '.bin')).symlink_to('/etc/os-release')
        with self.assertRaises(OSError):
            self.put()
    def test_symlink_directory(self):
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            PrivateStore(self.root / 'link')
    def test_quota(self):
        self.store.max_total = 1
        with self.assertRaisesRegex(Hold, 'QUOTA'):
            self.put()
        self.assertEqual(os.listdir(self.root), [])
    def test_unprotected_object(self):
        ref = self.put()
        os.chmod(self.root / ref.split(':')[1], 0o644)
        with self.assertRaisesRegex(Hold, 'METADATA'):
            self.put()

class LoopTests(unittest.TestCase):
    setUp = cases.ConnectionQueueTests.setUp
    tearDown = cases.ConnectionQueueTests.tearDown
    def make(self, request=None, fail_post=False):
        self.posts, self.dispatches, self.files = [], [], []
        owner = self
        r = request or cases.request()
        class Github:
            def comments(self, since):
                return [{'id': 1, 'body': PREFIX + json.dumps(r), 'user': {'id': cases.ACTOR},
                         'created_at': 'x', 'updated_at': 'x'}]
            def call(self, suffix, data):
                owner.posts.append(data['body'])
                if fail_post:
                    raise Hold('HTTP_UNKNOWN')
                return {'id': 123}
        class Cloud:
            def call(self, target, action, extra):
                if action == 'RunCommand':
                    owner.dispatches.append(extra)
                    return {'InvokeId': 't-one'}
                return transport.response(r)
        class Store:
            def put(self, rid, data, sha):
                owner.files.append(data)
                return 'server-private:object'
        return Loop(self.q, Github(), Cloud(), Store())
    def test_cycle_repeat(self):
        loop = self.make()
        loop.tick(cases.NOW)
        loop.tick(cases.NOW + 1)
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.q.inspect('job-1')['state'], 'SUCCESS')
    def test_no_public_file(self):
        r = cases.request()
        r.update(operation='fetch_os_release', arguments={'path': '/etc/os-release', 'max_bytes': 65536})
        self.make(r).tick(cases.NOW)
        self.assertEqual(len(self.files), 1)
        self.assertNotIn('base64', self.posts[0])
        self.assertNotIn('NAME=', self.posts[0])
        self.assertIn('NOT_DELIVERED', self.posts[0])
    def test_unknown_post_no_repeat(self):
        loop = self.make(fail_post=True)
        loop.tick(cases.NOW)
        loop.tick(cases.NOW + 1)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.q.db.execute('SELECT state FROM connection_outbox').fetchone(), ('UNKNOWN',))
    def test_crash_before_invoke(self):
        loop = self.make()
        self.q.submit(json.dumps(cases.request()), cases.ACTOR, cases.NOW)
        self.q.begin_dispatch('job-1', cases.NOW)
        loop.tick(cases.NOW + 1)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.q.inspect('job-1')['state'], 'UNKNOWN')
    def test_existing_invoke_only(self):
        loop = self.make()
        self.q.submit(json.dumps(cases.request()), cases.ACTOR, cases.NOW)
        self.q.begin_dispatch('job-1', cases.NOW)
        self.q.record_invoke('job-1', 't-one')
        self.q.unknown('job-1')
        loop.tick(cases.NOW + 1)
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.q.inspect('job-1')['state'], 'SUCCESS')
