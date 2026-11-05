import unittest
from telegram_owner_send_canary import send
class Reply:
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return b'{"ok":true,"result":{"message_id":55}}'
class Tests(unittest.TestCase):
    def test_ack(self):
        self.assertEqual(send('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456','12345',opener=lambda req,timeout:Reply()),55)
    def test_invalid_chat(self):
        with self.assertRaises(ValueError):send('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456','bad')
    def test_invalid_token(self):
        with self.assertRaises(ValueError):send('bad','123')
if __name__=='__main__':unittest.main()
