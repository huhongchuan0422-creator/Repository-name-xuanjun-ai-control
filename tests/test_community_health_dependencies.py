"""Real loopback health checks over the original Center and business stores."""
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_community_mini_center_identity as fixture
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_http import serve
from scripts.community_mini_http import runtime_version
from scripts.community_mini_login import MiniGateway
from scripts.community_saas_modules import connect as module_connect
from scripts.community_stage_runtime import StageRuntime


class HealthDependencies(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterComposition();self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=MiniApplication(self.fx.center,self.tmp.name,self.fx.stage.api.bindings,
            self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,
            self.fx.identity.appid,'a'*32)
        self.addCleanup(self.app.close)
        self.server=self.app.listen()
        # A health check must never contact WeChat or obtain a new identity.
        for target in ('scripts.community_wechat_sp_readonly.PartnerOrderReader._fetch',
                       'scripts.community_mini_login.WechatCodeClient.exchange'):
            guard=patch(target,side_effect=AssertionError('NO_PROVIDER_IO_IN_HEALTH'))
            guard.start();self.addCleanup(guard.stop)

    def get(self,server=None,host=None,path='/community/health'):
        server=server or self.server
        def request():
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                connection.request('GET',path,headers={} if host is None else {'Host':host})
                response=connection.getresponse()
                return response.status,json.loads(response.read()),dict(response.getheaders())
            finally:connection.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(request);server.handle_request();return pending.result(timeout=5)

    def unavailable(self):
        status,result,_=self.get()
        self.assertEqual((status,result),(503,{'status':'UNAVAILABLE'}))

    def closed(self,name):
        self.app.stage.handles[('orders','merchants','ads','refunds','modules','saas-orders').index(name)].close()
        self.unavailable()

    def test_full_composition_ready_is_read_only_and_keeps_limited_claim(self):
        databases=[self.fx.center.db,*self.app.stage.handles]
        before=[db.total_changes for db in databases]
        status,result,headers=self.get()
        self.assertEqual(status,200)
        self.assertEqual(result,dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False))
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual([db.total_changes for db in databases],before)

    def test_health_reports_running_build_stamp_not_request_or_changed_environment(self):
        root=Path(self.tmp.name);(root/'scripts').mkdir()
        stamp=root/'COMMUNITY_SOURCE_SHA';stamp.write_text('a'*40+'\n')
        with patch('scripts.community_mini_http.__file__',str(root/'scripts/community_mini_http.py')), \
             patch.dict(os.environ,COMMUNITY_SOURCE_SHA='a'*40):
            server=serve(self.app.gateway)
        try:
            # The composition retains its build identity; later env changes or
            # request headers cannot claim another running image revision.
            with patch.dict(os.environ,COMMUNITY_SOURCE_SHA='b'*40):
                status,health,_=self.get(server)
            self.assertEqual(status,200)
            self.assertEqual(health['runtime_source_sha'],'a'*40)
            self.assertEqual(health['version_source'],'IMAGE_BUILD_STAMP')
            self.assertIsInstance(health['observed_at'],int)
            self.assertFalse(health['production_acceptance'])
        finally:server.server_close()

    def test_build_stamp_missing_malformed_or_env_mismatch_cannot_claim_runtime_sha(self):
        root=Path(self.tmp.name);stamp=root/'COMMUNITY_SOURCE_SHA'
        with patch('scripts.community_mini_http.__file__',str(root/'scripts/community_mini_http.py')), \
             patch.dict(os.environ,COMMUNITY_SOURCE_SHA='a'*40):
            self.assertIsNone(runtime_version())
            for data in ('bad','b'*40):
                stamp.write_text(data);self.assertIsNone(runtime_version())
            stamp.write_text('a'*40);self.assertEqual(runtime_version(),'a'*40)
            stamp.unlink();stamp.symlink_to(root/'missing')
            self.assertIsNone(runtime_version())

    def test_closed_orders_is_unavailable(self):self.closed('orders')
    def test_closed_merchants_is_unavailable(self):self.closed('merchants')
    def test_closed_ads_is_unavailable(self):self.closed('ads')
    def test_closed_refunds_is_unavailable(self):self.closed('refunds')
    def test_closed_modules_and_quotes_is_unavailable(self):self.closed('modules')
    def test_closed_saas_orders_is_unavailable(self):self.closed('saas-orders')

    def test_separate_quote_and_module_connections_are_both_checked(self):
        separate=module_connect();self.addCleanup(separate.close)
        original=self.app.stage.runtime.saas.modules
        self.app.stage.runtime.saas.modules=separate
        self.assertEqual(self.get()[0],200)
        separate.close();self.unavailable()
        self.app.stage.runtime.saas.modules=original
        # Exercise the other side even when quotes are not the module store.
        self.app.stage.runtime.saas.quotes=separate
        self.unavailable()

    def test_lost_admitted_saas_backend_is_not_silently_ignored(self):
        self.app.stage.runtime.saas=None
        self.unavailable()

    def test_admitted_saas_missing_connection_is_unavailable(self):
        self.app.stage.runtime.saas.orders=None
        self.unavailable()

    def test_original_community_only_runtime_does_not_require_saas(self):
        runtime=StageRuntime(self.app.stage.demo,None,self.fx.stage.api.bindings)
        identity=CenterIdentity(self.fx.center,runtime,self.fx.identity.appid,self.fx.scenes)
        gateway=MiniGateway(runtime,identity,self.app.gateway.provider)
        server=serve(gateway)
        try:
            self.assertEqual(self.get(server)[0],200)
            runtime.demo.ad_db.close()
            self.assertEqual(self.get(server)[:2],(503,{'status':'UNAVAILABLE'}))
        finally:server.server_close()

    def test_center_maintenance_and_recovery_remain_503_and_200(self):
        self.fx.center.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
        status,result,_=self.get()
        self.assertEqual((status,result['status']),(503,'MAINTENANCE'))
        self.assertFalse(result['production_acceptance'])
        self.fx.center.db.execute("UPDATE settings SET v='0' WHERE k='maintenance'")
        self.assertEqual(self.get()[0],200)

    def test_unavailable_or_missing_center_fails_closed(self):
        self.fx.center.db.close();self.unavailable()
        self.app.gateway.identity.center=None;self.unavailable()

    def test_wrong_host_stays_denied_and_unknown_route_stays_closed(self):
        self.assertEqual(self.get(host='untrusted.example')[:2],(403,{'error':'ORIGIN_DENIED'}))
        self.assertEqual(self.get(path='/community/health/private')[:2],(404,{'error':'NOT_FOUND'}))


if __name__=='__main__':unittest.main()
