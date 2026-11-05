import unittest
from unittest.mock import patch
from telegram_owner_transport import OwnerTelegramTransport

class TestOwnerTransport(unittest.TestCase):
    def setUp(self):
        self.t=OwnerTelegramTransport("test","123","456","key","https://uk.invalid/owner","auth")
        self.ref=lambda _:{"state":"WAITING_HUMAN","expires_at":99999999999,"task_id":"task","fence":3}
    def test_wrong_owner(self):
        self.assertEqual(self.t.accept_update({"message":{"chat":{"id":123,"type":"private"},"from":{"id":999},"text":"/approve ref"}},self.ref),"IGNORED")
    def test_wrong_chat(self):
        self.assertEqual(self.t.accept_update({"message":{"chat":{"id":999,"type":"private"},"from":{"id":456},"text":"/approve ref"}},self.ref),"IGNORED")
    def test_https_required(self):
        with self.assertRaises(ValueError):
            OwnerTelegramTransport("x","1","1","k","http://bad","auth")
    def test_expired(self):
        ref=lambda _ : dict(self.ref("x"),expires_at=1)
        self.assertEqual(self.t.accept_update({"message":{"chat":{"id":123,"type":"private"},"from":{"id":456},"text":"/approve ref"}},ref),"IGNORED")
    def test_signed_reject(self):
        class Resp:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n): return b'{"accepted":true}'
        with patch("urllib.request.urlopen",return_value=Resp()) as call:
            outcome=self.t.accept_update({"update_id":2,"message":{"chat":{"id":123,"type":"private"},"from":{"id":456},"text":"/reject ref"}},self.ref)
        self.assertEqual(outcome,"ACCEPTED")
        self.assertTrue(call.call_args[0][0].get_header("X-xuanjun-signature"))
if __name__=="__main__": unittest.main()
