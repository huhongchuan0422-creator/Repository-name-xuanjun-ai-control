"""New workbench data flows and original Center browser cookie authorization."""
import concurrent.futures
import json
import unittest
import urllib.request
import urllib.error
import test_community_center_operations as fixture
from scripts.community_mini_http import serve
from scripts.community_order_store import create_order

class Workbench(unittest.TestCase):
    def setUp(self):self.fx=fixture.ExistingCenterOperations();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def call(self,op,params=None,workspace='merchant'):
        return self.fx.call(self.fx.body(workspace,'community.'+op,params))
    def test_paused_profile_can_be_loaded_and_updated_with_version(self):
        r=self.call('merchant_settings');p=r['profile'];self.assertIsNotNone(p)
        record={k:p[k] for k in ('name','description','contact','status')};record['status']='PAUSED'
        self.call('profile',dict(record=record,expected_version=p['version']))
        updated=self.call('merchant_settings')['profile'];self.assertEqual(updated['status'],'PAUSED')
        self.assertEqual(updated['version'],p['version']+1)
        with self.assertRaises(ValueError):self.call('profile',dict(record=record,expected_version=p['version']))
    def test_paged_orders_filter_export_and_scope(self):
        rt=self.fx.fx.stage.api;identity=rt.bindings[self.fx.fx.stage.merchant];db=rt.demo.db
        for ref in ('a','b','c'):create_order(db,identity,ref,101)
        create_order(db,dict(identity,store_id='other'),'private',999)
        args=dict(limit=2,after_id='',status='PENDING');r=self.call('orders_page',args)
        self.assertEqual([x['reference'] for x in r['orders']],['a','b']);self.assertEqual(r['next_cursor'],'b')
        r=self.call('orders_page',dict(args,after_id='b'));self.assertEqual([x['reference'] for x in r['orders']],['c']);self.assertFalse(r['has_more'])
        export=self.call('orders_export',args);self.assertEqual(export['row_count'],2);self.assertNotIn('private',export['csv']);self.assertIn('state,simulation_only',export['csv'])
        self.assertEqual(self.call('orders_page',dict(args,status='SUCCESS'))['orders'],[])
        with self.assertRaises(PermissionError):self.call('orders_export',args,'staff')
        with self.assertRaises(PermissionError):self.call('merchant_settings',workspace='staff')
        for patch in [dict(limit=True),dict(after_id="' OR 1=1"),dict(status='ANY')]:
            with self.assertRaises(ValueError):self.call('orders_page',dict(args,**patch))
    def test_order_detail_refund_history_and_split_use_original_records(self):
        rt=self.fx.fx.stage.api;identity=rt.bindings[self.fx.fx.stage.merchant]
        create_order(rt.demo.db,identity,'detail_order',101)
        rt.simulate_from_operator(self.fx.fx.stage.owner,'detail_order','paid_event','SUCCESS','fixture_tx')
        before=self.call('order_detail',dict(reference='detail_order'))
        self.assertEqual(before['remaining_preview_minor'],101)
        self.assertEqual(before['events'][0]['to_state'],'SUCCESS')
        request=dict(reference='detail_order',event_id='refund_request',amount_minor=11)
        self.call('refund_record',request);self.call('refund_record',request)
        after=self.call('order_detail',dict(reference='detail_order'))
        self.assertEqual(after['refund_preview_total_minor'],11)
        self.assertEqual(len(after['refund_previews']),1)
        self.assertFalse(after['provider_refund_executed'])
        split=self.call('split_preview',dict(reference='detail_order',shares_bps={'merchant':9000,'platform':1000}))
        self.assertEqual(sum(split['allocations_minor'].values()),90)
        self.assertEqual(self.call('order_detail',dict(reference='detail_order'),workspace='staff')['order']['state'],'SUCCESS')
        with self.assertRaises(ValueError):self.call('order_detail',dict(reference='private_other_store'))
    def test_browser_cookie_transport_and_ambiguous_credentials(self):
        server=serve(self.fx.fx.gateway,operations=self.fx.operations)
        def request(path,headers=None,body=None):
            data=None if body is None else json.dumps(body).encode()
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=data,headers=headers or {})
            try:
                with urllib.request.urlopen(req,timeout=3) as response:return response.status,response.read()
            except urllib.error.HTTPError as e:return e.code,e.read()
        def once(path,headers=None,body=None):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                f=pool.submit(request,path,headers,body);server.handle_request();return f.result()
        try:
            self.assertEqual(once('/merchant/workbench')[0],200)
            headers={'Content-Type':'application/json','Cookie':'__Host-xj_customer='+self.fx.web['token'],'X-CSRF-Token':self.fx.web['csrf']}
            self.assertEqual(once('/community/operations',headers,self.fx.body())[0],200)
            self.assertEqual(once('/community/operations',dict(headers,**{'X-Center-Session':self.fx.web['token']}),self.fx.body())[0],403)
            self.assertEqual(once('/community/operations',dict(headers,**{'X-CSRF-Token':'wrong'}),self.fx.body())[0],403)
        finally:server.server_close()

if __name__=='__main__':unittest.main()
