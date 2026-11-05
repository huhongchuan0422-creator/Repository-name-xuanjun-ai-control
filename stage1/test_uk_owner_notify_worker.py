import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uk_owner_notify_worker import deliver, once, private_text

class TestNotify(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name, 'state.sqlite')
        self.token = os.path.join(self.temp.name, 'bot')
        self.lock = os.path.join(self.temp.name, 'lock')
        with open(self.token, 'w') as stream: stream.write('dummy-token')
        os.chmod(self.token, 0o600)
        c = sqlite3.connect(self.db)
        c.executescript("""CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER);
            CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT);
            INSERT INTO tasks VALUES('a','WAITING_HUMAN',4);
            INSERT INTO approvals VALUES('a','PENDING');""")
        c.commit(); c.close()
    def tearDown(self):
        self.temp.cleanup()
    def test_no_duplicate_send_after_ack(self):
        with patch('uk_owner_notify_worker.deliver', return_value=71) as send:
            self.assertEqual(once(self.db,self.token,'123','456',self.lock),(1,1))
            self.assertEqual(once(self.db,self.token,'123','456',self.lock),(0,0))
            self.assertEqual(send.call_count,1)
    def test_token_permissions(self):
        os.chmod(self.token,0o644)
        with self.assertRaises(ValueError): private_text(self.token)
    def test_telegram_ack_chat_match(self):
        class Response:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,_): return self.data
        def fake(req,timeout):
            return Response(b'{"ok":true,"result":{"message_id":19,"chat":{"id":456}}}')
        self.assertEqual(deliver('dummy','456','req',opener=fake),19)
        def wrong(req,timeout):
            return Response(b'{"ok":true,"result":{"message_id":19,"chat":{"id":999}}}')
        with self.assertRaises(RuntimeError):
            deliver('dummy','456','req',opener=wrong)
    def test_failed_delivery_not_acked(self):
        with patch('uk_owner_notify_worker.deliver',side_effect=RuntimeError('network')):
            with self.assertRaises(RuntimeError):
                once(self.db,self.token,'123','456',self.lock)
        c = sqlite3.connect(self.db)
        self.assertEqual(c.execute("SELECT state FROM owner_notification_outbox").fetchone()[0],'PENDING')
        c.close()

if __name__ == '__main__': unittest.main()
