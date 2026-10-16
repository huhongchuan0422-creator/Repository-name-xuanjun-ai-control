"""Actual disposable static publisher, with explicit fake HTTPS, no host services."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from scripts import pr122_showcase as view
from scripts import pr122_showcase_package as package
from scripts import pr122_showcase_promote as promote

@unittest.skipUnless(os.geteuid()==0,'Disposable root filesystem tests')
class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/root',prefix='showcase-publish-test-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/'showcase'
        patch=mock.patch.object(promote,'BASE',self.base);patch.start();self.addCleanup(patch.stop)
        self.engine=promote.load_engine();self.counter=0
    def candidate(self,preview=False):
        self.counter+=1;folder=self.root/('public-'+str(self.counter));catalog=view.compile_catalog([],{});manifest=view.render(catalog,folder,preview)
        # Change a byte between versions, keeping the full tree manifest honest.
        page=folder/'showcase/index.html';page.write_text(page.read_text().replace('探索玄钧云汇','探索玄钧云汇 '+str(self.counter)))
        for row in manifest['files']:
            p=folder/row['path'];row.update(size=p.stat().st_size,sha256=view.sha(p.read_bytes()))
        (folder/'SHOWCASE_MANIFEST.json').write_text(json.dumps(manifest));target=self.root/('candidate-'+str(self.counter)+'.tar.gz')
        receipt=package.build(folder,target,preview)
        previous=os.readlink(self.base/'current') if (self.base/'current').is_symlink() else None
        digest=None
        if previous:
            with self.engine.Deadline(30) as deadline:digest=view.sha(view.canonical(self.engine.snapshot(Path(previous)/'public',deadline)))
        gate={**receipt,'artifact_id':self.counter,'expires_unix':int(time.time())+600,'previous_release':previous,'previous_manifest_sha256':digest,'rollback_approved':True}
        return target.read_bytes(),gate
    def publish(self,raw,gate):return promote.publish(raw,gate,self.engine,lambda *_:{'scope':'FAKE_HTTPS_ONLY','browser':'NOT_RUN'})
    def test_first_snapshot_and_rollback_to_unpublished(self):
        raw,gate=self.candidate();self.assertEqual(self.publish(raw,gate)['state'],'HTTPS_SMOKE_PASS_AWAIT_BROWSER')
        self.assertTrue((self.base/'current/public/showcase/projects/index.html').is_file())
        self.assertEqual(promote.rollback(1,self.engine)['state'],'ROLLED_BACK');self.assertFalse((self.base/'current').exists())
    def test_update_and_verified_previous_snapshot_rollback(self):
        raw,gate=self.candidate();self.publish(raw,gate);old=os.readlink(self.base/'current')
        raw,gate=self.candidate();self.publish(raw,gate);self.assertNotEqual(os.readlink(self.base/'current'),old)
        promote.rollback(2,self.engine);self.assertEqual(os.readlink(self.base/'current'),old)
    def test_preview_package_cannot_publish(self):
        raw,gate=self.candidate(True)
        with self.assertRaisesRegex(ValueError,'NOT_A_PRODUCTION_CANDIDATE'):self.publish(raw,gate)
        self.assertFalse(self.base.exists())
    def test_no_blind_apply_retry(self):
        raw,gate=self.candidate();self.publish(raw,gate)
        with self.assertRaisesRegex(ValueError,'TRANSACTION_EXISTS'):self.publish(raw,gate)
    def test_old_tree_drift_is_not_adopted(self):
        raw,gate=self.candidate();self.publish(raw,gate);raw,gate=self.candidate()
        (self.base/'current/public/showcase/index.html').write_text('foreign edit')
        with self.assertRaisesRegex(ValueError,'PREVIOUS_MANIFEST_DRIFT'):self.publish(raw,gate)
    def test_https_failure_leaves_inspectable_transaction_and_controlled_rollback(self):
        raw,gate=self.candidate()
        with self.assertRaisesRegex(RuntimeError,'HTTPS_FAILED'):
            promote.publish(raw,gate,self.engine,lambda *_:(_ for _ in ()).throw(RuntimeError('HTTPS_FAILED')))
        self.assertTrue((self.base/'transactions/showcase-1.json').exists());self.assertEqual(promote.rollback(1,self.engine)['state'],'ROLLED_BACK')

    def test_registration_page_update_acceptance_and_saas_listing_end_to_end(self):
        from types import SimpleNamespace
        from scripts.pr122_showcase_register import register
        from tests.test_pr122_showcase import obj,approvals
        from scripts.pr122_showcase_sources import module_prices
        from scripts.community_saas_offers import open_offer_store,register_offer,add_component,change_offer_status
        from scripts.community_saas_cost_pricing import open_cost_store,save_cost
        registry=self.root/'registry'
        common=dict(registry=registry,version=1,title_zh='验证作品',title_en='Validation work',summary_zh='仅测试夹具',summary_en='Test fixture only')
        def intake(kind,pid,id,**extra):
            return register(SimpleNamespace(**{**common,'kind':kind,'project_id':pid,'id':id,**extra}))
        for pid in ('community-payment','parallel-project'):
            intake('project',pid,pid,milestone=['verified-demo'],scenario_zh='测试流程',scenario_en='Test workflow')
        source=self.root/'role-source';source.mkdir();(source/'index.html').write_text('<!doctype html><html><head><title>TEST ONLY</title></head><body>Simulation fixture</body></html>')
        intake('page','community-payment','consumer',public=source)
        items=view.discover(registry);authority=approvals(items)
        def compile_snapshot():
            eligible,assets=view.project_public_pages(registry,items,authority)
            return view.compile_catalog(items,authority,published_pages=eligible),assets
        catalog,assets=compile_snapshot();self.assertEqual(len(catalog['developing']),2)
        def deploy(catalog,assets,identifier):
            folder=self.root/('lifecycle-'+str(identifier));manifest=view.render(catalog,folder,project_files=assets)
            (folder/'SHOWCASE_MANIFEST.json').write_text(json.dumps(manifest));path=self.root/('lifecycle-'+str(identifier)+'.tar.gz')
            receipt=package.build(folder,path);previous=os.readlink(self.base/'current') if (self.base/'current').is_symlink() else None;baseline=None
            if previous:
                with self.engine.Deadline(30) as deadline:baseline=view.sha(view.canonical(self.engine.snapshot(Path(previous)/'public',deadline)))
            gate={**receipt,'artifact_id':identifier,'expires_unix':int(time.time())+600,'previous_release':previous,'previous_manifest_sha256':baseline,'rollback_approved':True}
            self.publish(path.read_bytes(),gate)
        deploy(catalog,assets,101)
        intake('page','community-payment','platform',public=source);items=view.discover(registry)
        catalog,assets=compile_snapshot();self.assertEqual(len(catalog['projects'][0]['pages']),1)
        authority=approvals(items);catalog,assets=compile_snapshot();self.assertEqual(len(catalog['projects'][0]['pages']),2)
        deploy(catalog,assets,102)
        milestone=obj('milestone','verified-demo',state='DONE',evidence_url='https://github.com/example/test/issues/1');items.append(milestone);authority=approvals(items)
        catalog,assets=compile_snapshot();acceptance=obj('acceptance','acceptance',project_version=1,snapshot_sha256=catalog['projects'][0]['snapshot_sha256'],members=catalog['projects'][0]['snapshot_members'],evidence_url='https://github.com/example/test/issues/2');items.append(acceptance)
        sealed=view.sha((Path(__file__).resolve().parents[1]/'scripts/community_saas_modules.py').read_bytes())
        module=obj('module','merchant-module',module_id='merchant_operations',requirements=[],package_sha256=sealed,demo_href='/showcase/projects/community-payment/views/consumer/v1/');items.append(module);authority=approvals(items)
        offers=self.root/'offers.sqlite';costs=self.root/'costs.sqlite';db=open_offer_store(offers);cost=open_cost_store(costs)
        register_offer(db,'test-offer','merchant_operations','MONTHLY',1,30,True,'TEST LICENSE','TEST PRICE BASIS')
        add_component(db,'test-offer','license','MODULE_LICENSE','MONTHLY',10000,1990,'TEST PRICE SOURCE')
        save_cost(cost,'test-offer','license','VERIFIED_ACTUAL',1000,200,'TEST COST SOURCE','MONTHLY')
        for state in ('PREVIEW','APPROVED','EFFECTIVE'):change_offer_status(db,'test-offer',state,cost_db=cost)
        db.close();cost.close();prices=module_prices(offers,costs,{'merchant_operations':sealed})
        eligible,assets=view.project_public_pages(registry,items,authority);catalog=view.compile_catalog(items,authority,prices,eligible)
        self.assertEqual(len(catalog['cases']),1);self.assertEqual(len(catalog['modules']),1);self.assertFalse(catalog['modules'][0]['purchase_enabled'])
        deploy(catalog,assets,103)
        published=json.loads((self.base/'current/public/showcase/catalog.json').read_text());self.assertEqual(len(published['cases']),1);self.assertEqual(len(published['modules']),1)
        self.assertEqual(promote.rollback(103,self.engine)['state'],'ROLLED_BACK')
        restored=json.loads((self.base/'current/public/showcase/catalog.json').read_text());self.assertEqual(restored['cases'],[]);self.assertEqual(restored['modules'],[])
        report={'status':'PASS','scope':'Disposable root filesystem; fixture reviews/prices and fake HTTPS; NOT production acceptance','steps':['register two projects','independent project entries','new role held before review','new role visible after review','snapshot acceptance moves project to cases','registered module with effective CNY/USD offer enters market','verified previous snapshot rollback'],'real_payment':False,'production_deployed':False}
        import os as environment
        if environment.environ.get('XJ_SHOWCASE_REPORT_DIR'):(Path(environment.environ['XJ_SHOWCASE_REPORT_DIR'])/'SHOWCASE_LIFECYCLE_REPORT.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':unittest.main()
