import json
import socket
import time
import threading
import unittest
from http.client import HTTPConnection
from scripts.community_order_store import connect
from scripts.community_demo_api import DemoService, handler, MAX_BODY, server_database
from http.server import HTTPServer

S = {'tenant_id':'t1','merchant_id':'m1','store_id':'s1'}
def order(reference='r1', amount=105, identity=S):
    return dict(identity, reference=reference, amount_minor=amount)
def transition(event='ev1', reference='r1', amount=105, tx='tx1', identity=S, target='SUCCESS'):
    return dict(identity, reference=reference, event_id=event, amount_minor=amount,
                transaction_id=tx, target=target)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db=connect()
        self.service=DemoService(self.db)
    def tearDown(self):
        self.db.close()
    def test_create_query_and_simulated_complete(self):
        self.assertEqual(self.service.dispatch('POST','/demo/orders',order())['state'],'PENDING')
        self.assertEqual(self.service.dispatch('POST','/demo/orders/state',dict(S,reference='r1'))['state'],'PENDING')
        final=self.service.dispatch('POST','/demo/orders/simulate',transition())
        self.assertEqual(final['state'],'SUCCESS')
        self.assertFalse(final['provider_settlement_verified'])
        self.assertEqual(self.service.dispatch('POST','/demo/orders/state',dict(S,reference='r1'))['state'],'SUCCESS')
    def test_scope_isolation(self):
        self.service.dispatch('POST','/demo/orders',order())
        for field in S:
            wrong=dict(S,reference='r1');wrong[field]='other'
            with self.assertRaises(ValueError):
                self.service.dispatch('POST','/demo/orders/state',wrong)
    def test_duplicate_event_and_changed_replay(self):
        self.service.dispatch('POST','/demo/orders',order())
        self.service.dispatch('POST','/demo/orders/simulate',transition())
        self.assertTrue(self.service.dispatch('POST','/demo/orders/simulate',transition())['duplicate'])
        for altered in (transition(amount=106),transition(tx='different')):
            with self.assertRaisesRegex(ValueError,'EVENT_ID_COLLISION'):
                self.service.dispatch('POST','/demo/orders/simulate',altered)
    def test_invalid_extra_fields_and_float_bool_amount(self):
        for bad in (dict(order(),extra='unsafe'),order(amount=True),order(amount=1.5),
                    order(reference='../escape'),order(amount=0)):
            with self.assertRaises(ValueError):
                self.service.dispatch('POST','/demo/orders',bad)
    def test_cross_merchant_same_reference_remains_isolated(self):
        self.service.dispatch('POST','/demo/orders',order())
        other=dict(S,merchant_id='m2')
        self.service.dispatch('POST','/demo/orders',order(identity=other))
        self.service.dispatch('POST','/demo/orders/simulate',transition())
        self.assertEqual(self.service.dispatch('POST','/demo/orders/state',dict(other,reference='r1'))['state'],'PENDING')
    def test_no_unknown_route(self):
        with self.assertRaises(ValueError):
            self.service.dispatch('POST','/live/wechat/pay',order())

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=server_database(':memory:')
        cls.server=HTTPServer(('127.0.0.1',0),handler(DemoService(cls.db)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(4)
        cls.server.server_close()
        cls.db.close()
    def post(self,path,raw,ctype='application/json'):
        conn=HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=3)
        conn.request('POST',path,body=raw,headers={'Content-Type':ctype})
        response=conn.getresponse()
        data=response.read()
        status=response.status
        conn.close()
        return status,json.loads(data)
    def test_post_end_to_end(self):
        status,data=self.post('/demo/orders',json.dumps(order('http1')))
        self.assertEqual(status,200)
        self.assertEqual(data['state'],'PENDING')
        status,data=self.post('/demo/orders/simulate',json.dumps(transition(event='http_ev',reference='http1')))
        self.assertEqual(status,200)
        self.assertEqual(data['state'],'SUCCESS')
    def test_duplicate_json_keys_rejected(self):
        status,_=self.post('/demo/orders','{"reference":"r1","reference":"r2"}')
        self.assertEqual(status,400)
    def test_no_query_or_wrong_content_type(self):
        self.assertEqual(self.post('/demo/orders?token=unsafe','{}')[0],404)
        self.assertEqual(self.post('/demo/orders','{}','text/plain')[0],415)
    def test_nonfinite_json_rejected(self):
        self.assertEqual(self.post('/demo/orders','{"amount_minor":NaN}')[0],400)
    def test_large_payload_rejected(self):
        self.assertEqual(self.post('/demo/orders','x'*(MAX_BODY+1))[0],400)
    def test_dns_rebinding_host_and_cross_origin_rejected(self):
        for headers in ({'Host':'evil.example'},
                        {'Origin':'https://evil.example'},
                        {'Origin':'null'}):
            conn=HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=3)
            conn.request('POST','/demo/orders',body=json.dumps(order('hostfail')),
                         headers={'Content-Type':'application/json',**headers})
            response=conn.getresponse()
            self.assertEqual(response.status,403)
            response.read()
            conn.close()
    def test_matching_local_origin_allowed(self):
        conn=HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=3)
        origin='http://127.0.0.1:'+str(self.server.server_address[1])
        conn.request('POST','/demo/orders',body=json.dumps(order('localorigin')),
                     headers={'Content-Type':'application/json','Origin':origin})
        response=conn.getresponse()
        self.assertEqual(response.status,200)
        response.read()
        conn.close()
    def raw_partial(self,reference,declared_extra=0,shutdown=True):
        payload=json.dumps(order(reference),separators=(',',':')).encode('utf-8')
        port=self.server.server_address[1]
        sock=socket.create_connection(('127.0.0.1',port),timeout=4)
        sock.settimeout(4)
        request=(f"POST /demo/orders HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                 f"Content-Type: application/json\r\nContent-Length: {len(payload)+declared_extra}\r\n"
                 "Connection: close\r\n\r\n").encode('ascii')
        try:
            sock.sendall(request+payload)
            if shutdown:
                sock.shutdown(socket.SHUT_WR)
            received=b''
            while True:
                part=sock.recv(4096)
                if not part:break
                received+=part
            return int(received.split(b' ',2)[1])
        finally:sock.close()
    def test_truncated_declared_length_must_not_create_order(self):
        status=self.raw_partial('truncated',declared_extra=20,shutdown=True)
        self.assertEqual(status,400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM orders WHERE reference='truncated'").fetchone()[0],0)
    def test_unfinished_socket_body_times_out_and_server_recovers(self):
        start=time.monotonic()
        status=self.raw_partial('incomplete',declared_extra=20,shutdown=False)
        self.assertEqual(status,408)
        self.assertLess(time.monotonic()-start,3.5)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM orders WHERE reference='incomplete'").fetchone()[0],0)
        self.assertEqual(self.post('/demo/orders',json.dumps(order('after_timeout')))[0],200)
    def test_no_real_pay_route(self):
        self.assertEqual(self.post('/api/pay/wechat','{}')[0],404)

if __name__=='__main__':
    unittest.main()
