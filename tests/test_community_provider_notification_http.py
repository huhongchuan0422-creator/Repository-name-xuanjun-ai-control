"""Actual bounded HTTP + signed fixture notification + original SaaS review DB."""
import concurrent.futures
import http.client
from http.server import HTTPServer
import sqlite3
import unittest
from unittest.mock import patch
import test_community_saas_provider_evidence as evidence_fixture
from scripts.community_provider_notification_http import make_handler,notification_path
from scripts.pr122_customer_source import TrustedNginxSource
from scripts.community_saas_order_preparation import status

class NotificationTransport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):evidence_fixture.FrozenClaimEvidence.setUpClass()
    def setUp(self):
        self.fx=evidence_fixture.FrozenClaimEvidence('test_valid_notification_creates_only_original_pending_finance_review');self.fx.setUp()
        self.path=notification_path(self.fx.inbox,'tenant1','ord1')
        self.server=HTTPServer(('127.0.0.1',0),make_handler(self.fx.inbox,self.fx.fx.owner,
            https_origin='https://example.test',trusted_proxy=TrustedNginxSource(65534)))
    def tearDown(self):self.server.server_close();self.fx.tearDown()
    def request(self,body=None,extra=(),path=None,sign=True,proxy=True):
        body=self.fx.event() if body is None else body
        signed=self.fx.crypto.signed(body) if sign else {}
        def client():
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
            try:
                conn.putrequest('POST',self.path if path is None else path,skip_host=True)
                conn.putheader('Host','example.test');conn.putheader('Content-Type','application/json')
                conn.putheader('Content-Length',str(len(body)))
                for k,v in [*signed.items(),*extra]:conn.putheader(k,v)
                conn.endheaders(body);reply=conn.getresponse();return reply.status,reply.read()
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(client)
            if proxy:
                with patch.object(TrustedNginxSource,'__call__',return_value='192.0.2.1'):self.server.handle_request()
            else:self.server.handle_request()
            return future.result()
    def test_ack_only_after_original_pending_review_is_committed(self):
        old=status(self.fx.fx.s,'ord1','tenant1')
        self.assertEqual(self.request(),(204,b''))
        self.assertFalse(self.fx.fx.s.in_transaction)
        self.assertEqual(self.fx.fx.s.execute('SELECT state FROM saas_review_tasks').fetchone()[0],'PENDING')
        self.assertEqual(status(self.fx.fx.s,'ord1','tenant1'),old)
    def test_repeated_callback_ack_does_not_duplicate_original_review(self):
        self.assertEqual(self.request()[0],204);self.assertEqual(self.request()[0],204)
        self.assertEqual(self.fx.fx.s.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],1)
    def test_missing_signature_wrong_amount_and_duplicate_header_never_ack(self):
        self.assertEqual(self.request(sign=False)[0],400)
        self.assertEqual(self.request(self.fx.event({'amount':{'total':999,'currency':'CNY'}}))[0],400)
        self.assertEqual(self.request(extra=(('wechatpay-serial',self.fx.crypto.kid),))[0],400)
        self.assertEqual(self.fx.fx.s.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],0)
    def test_unsigned_route_or_browser_origin_cannot_trigger_provider_intake(self):
        self.assertEqual(self.request(path=self.path+'?order=ord1')[0],404)
        self.assertEqual(self.request(extra=(('Origin','https://example.test'),))[0],403)
    def test_tcp_peer_cannot_impersonate_trusted_unix_nginx(self):
        self.assertEqual(self.request(proxy=False)[0],403)
        self.assertEqual(self.fx.fx.s.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],0)
    def test_database_failure_returns_unknown_failure_not_success_ack(self):
        old_timeout=self.fx.fx.s.execute('PRAGMA busy_timeout').fetchone()[0]
        with patch.object(self.fx.inbox,'receive',side_effect=sqlite3.OperationalError('busy')):
            result=self.request()
        self.assertEqual(result[0],503)
        self.assertEqual(self.fx.fx.s.execute('PRAGMA busy_timeout').fetchone()[0],old_timeout)
        self.assertNotIn(b'busy',result[1])
    def test_same_event_changed_body_fails_closed_after_first_ack(self):
        self.assertEqual(self.request()[0],204)
        self.assertEqual(self.request(self.fx.event({'transaction_id':'9999999'}))[0],400)

if __name__=='__main__':unittest.main()
