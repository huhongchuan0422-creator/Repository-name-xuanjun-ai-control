import os,sys,json,socket,struct,unittest
sys.path.insert(0,os.path.join(os.environ['P2_SOURCE_ROOT'],'stage1'))
from uk_owner_callback_core import LedgerOwnerDecisionServer,_strict_json
class Connection:
    def __init__(self,uid,value):self.uid=uid;self.raw=json.dumps(value).encode()+b'\n';self.sent=None
    def getsockopt(self,*a):return struct.pack('3i',123,self.uid,123)
    def recv(self,n):result=self.raw[:n];self.raw=self.raw[n:];return result
    def sendall(self,data):self.sent=data
class Ledger:
    def native_observation(self,request):return {'task':{'fence':request['fence']}}
class Tests(unittest.TestCase):
    def setUp(self):self.server=LedgerOwnerDecisionServer(None,Ledger(),1003,native_uid=1002)
    def test_native_role_existing_socket(self):
        c=Connection(1002,{'operation':'NATIVE_GATEWAY','payload':{'operation':'read','request':{'fence':1}}})
        self.server.serve_connection(c)
        self.assertEqual(json.loads(c.sent),{'accepted':True,'result':{'task':{'fence':1}}})
    def test_unknown_peer_rejected_before_read(self):
        c=Connection(1004,{})
        with self.assertRaises(PermissionError):self.server.serve_connection(c)
        self.assertIsNone(c.sent);self.assertEqual(c.raw,b'{}\n')
    def test_callback_cannot_use_native_role(self):
        c=Connection(1003,{'operation':'NATIVE_GATEWAY','payload':{}})
        with self.assertRaises(ValueError):self.server.serve_connection(c)
    def test_native_cannot_use_owner_decision(self):
        c=Connection(1002,{'operation':'OWNER_DECISION','event':{}})
        with self.assertRaises(PermissionError):self.server.serve_connection(c)
    def test_arbitrary_sql_operation_rejected(self):
        c=Connection(1002,{'operation':'NATIVE_GATEWAY','payload':{'operation':'sql','query':'DELETE FROM tasks'}})
        with self.assertRaises(ValueError):self.server.serve_connection(c)
    def test_duplicate_nested_key_rejected(self):
        with self.assertRaises(ValueError):_strict_json('{"a":{"fence":1,"fence":2}}')
    def test_normal_numbers_preserve_types_and_overflow_rejected(self):
        self.assertEqual(_strict_json('{"i":123,"f":1.5}'),{'i':123,'f':1.5})
        for raw in ['1e9999','-1e9999','{"a":[1e9999]}','NaN']:
            with self.assertRaises(ValueError):_strict_json(raw)
if __name__=='__main__':unittest.main(verbosity=2)
