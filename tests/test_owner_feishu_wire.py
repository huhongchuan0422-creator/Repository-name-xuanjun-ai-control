import importlib.util
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import unittest

if 'P2_FEISHU_INTEGRATION_ROOT' not in os.environ:
    raise unittest.SkipTest('Overlaid package absent: caller integration NOT_RUN')
ROOT=pathlib.Path(os.environ['P2_FEISHU_INTEGRATION_ROOT'])
sys.path.insert(0,str(ROOT/'stage1'))


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path));value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value


class WireTests(unittest.TestCase):
    def setUp(self):
        from test_owner_feishu_runtime import RuntimeTests
        self.runtime=RuntimeTests();self.runtime.setUp();self.addCleanup(self.runtime.doCleanups)
        self.bridge=module('overlaid_owner_bridge',ROOT/'stage1/native_ledger_bridge.py')
        self.operations=module('overlaid_native_operations',ROOT/'stage1/native_ledger_operations.py')
        self.runtime.fixture.ledger.owner_feishu_endpoint=self.runtime.endpoint

    def test_real_unix_wire_typed_ledger_feishu_fixture_persisted_ack(self):
        from owner_feishu_bridge_cycle import run_cycle
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path=temp.name+'/ledger.sock';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        listener.bind(path);listener.listen(4);listener.settimeout(5)
        calls=[];errors=[]
        def serve():
            try:
                # begin + pre/post send guards + atomic finish
                for unused in range(4):
                    connection,_=listener.accept()
                    with connection:
                        connection.settimeout(5);raw=bytearray()
                        while b'\n' not in raw:raw.extend(connection.recv(65536))
                        request=json.loads(bytes(raw).split(b'\n')[0].decode('utf-8'))
                        self.assertEqual(set(request),{'operation','payload'})
                        self.assertEqual(request['operation'],'NATIVE_GATEWAY')
                        calls.append(request['payload']['request']['operation'])
                        result=self.operations.execute(self.runtime.fixture.ledger,request['payload'])
                        connection.sendall((json.dumps({'accepted':True,'result':result})+'\n').encode('utf-8'))
            except Exception as error:errors.append(error)
            finally:listener.close()
        thread=threading.Thread(target=serve);thread.start()
        try:
            result=run_cycle(lambda request:self.bridge.socket_call(
                {'socket_path':path,'server_uid':os.geteuid()},
                {'operation':'owner_delivery','request':request}),self.runtime.api,self.runtime.binding)
        finally:thread.join(6)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(result['state'],'ACKED');self.assertEqual(calls,['begin','guard','guard','finish'])
        self.assertEqual(self.runtime.state(),('ACKED','om_runtime',1))

    def test_server_uid_mismatch_before_request_send(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path=temp.name+'/ledger.sock';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        listener.bind(path);listener.listen(1)
        seen=[]
        def serve():
            connection,_=listener.accept()
            with connection:seen.append(connection.recv(1024))
            listener.close()
        thread=threading.Thread(target=serve);thread.start()
        with self.assertRaises(ValueError):self.bridge.socket_call(
            {'socket_path':path,'server_uid':os.geteuid()+1},{'operation':'owner_delivery','request':{'operation':'begin'}})
        thread.join(5);self.assertFalse(thread.is_alive());self.assertEqual(seen,[b''])
        self.assertEqual(self.runtime.state(),('PENDING',None,0))

    def test_existing_authenticated_server_rejects_unverified_bridge_before_ledger(self):
        from unittest.mock import patch
        server_module=module('overlaid_callback_server',ROOT/'stage1/uk_owner_callback_core.py')
        import struct
        class Connection:
            def getsockopt(self,*args):return struct.pack('3i',123,42,42)
            def recv(self,*args):raise AssertionError('must authenticate before reading request')
        server=server_module.LedgerOwnerDecisionServer(self.runtime.fixture.ledger.activation_store,
            self.runtime.fixture.ledger,43,native_identity={'uid':42})
        with patch.object(server_module,'verify_native_gateway_peer',return_value=False):
            with self.assertRaises(PermissionError):server.serve_connection(Connection())
        self.assertEqual(self.runtime.state(),('PENDING',None,0))

    def test_relay_fixed_owner_cycle_rejects_value_and_arbitrary_operations(self):
        relay=module('overlaid_relay',ROOT/'stage1/p2_gateway_relay.py')
        calls=[]
        class Controller:
            def owner_cycle(self):calls.append('owner_cycle');return {'state':'IDLE'}
        self.assertEqual(relay.execute(Controller(),{'operation':'owner_cycle'})['state'],'IDLE')
        for request in ({'operation':'owner_cycle','value':{'chat_id':'oc_other'}},
                        {'operation':'http','url':'https://invalid'}, {'operation':'sql'}):
            with self.assertRaises(ValueError):relay.execute(Controller(),request)
        self.assertEqual(calls,['owner_cycle'])
