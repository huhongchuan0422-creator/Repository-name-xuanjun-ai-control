import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from tests.test_pr122_showcase_trust import anchored
from scripts import pr122_showcase_sources as source
from scripts import pr122_showcase_promote as promotion
from scripts.community_saas_offers import open_offer_store,register_offer,add_component,change_offer_status
from scripts.community_saas_cost_pricing import open_cost_store,save_cost

class AuthorityTests(unittest.TestCase):
    def test_effective_offer_dual_prices_and_readonly_authority_files(self):
        with tempfile.TemporaryDirectory() as td:
            offers=Path(td)/'offers.sqlite';costs=Path(td)/'costs.sqlite'
            db=open_offer_store(offers);cost=open_cost_store(costs)
            register_offer(db,'offer','merchant_operations','MONTHLY',1,30,True,'test license','TEST_EVIDENCE_NOT_A_LIVE_PRICE')
            add_component(db,'offer','license','MODULE_LICENSE','MONTHLY',10000,1990,'TEST_PRICE_SOURCE')
            save_cost(cost,'offer','license','VERIFIED_ACTUAL',1000,200,'TEST_COST_SOURCE','MONTHLY')
            for state in ('PREVIEW','APPROVED','EFFECTIVE'):change_offer_status(db,'offer',state,cost_db=cost)
            db.close();cost.close();before=(offers.read_bytes(),costs.read_bytes())
            result=source.module_prices(offers,costs,{'merchant_operations':'b'*64})
            self.assertEqual(result['merchant_operations']['offers'][0]['totals_by_cadence']['MONTHLY'],{'cny_minor':10000,'usd_minor':1990})
            self.assertEqual(before,(offers.read_bytes(),costs.read_bytes()))
    def test_cost_unknown_does_not_become_a_public_zero_cost_quote(self):
        with tempfile.TemporaryDirectory() as td:
            offers=Path(td)/'offers.sqlite';costs=Path(td)/'costs.sqlite';db=open_offer_store(offers);cost=open_cost_store(costs)
            register_offer(db,'offer','merchant_operations','MONTHLY',1,30,True,'test','TEST_PRICE_BASIS')
            add_component(db,'offer','license','MODULE_LICENSE','MONTHLY',10000,1990,'TEST_PRICE_SOURCE')
            for state in ('PREVIEW','APPROVED'):change_offer_status(db,'offer',state,cost_db=cost)
            with self.assertRaisesRegex(ValueError,'COST_INCOMPLETE'):change_offer_status(db,'offer','EFFECTIVE',cost_db=cost)
            db.close();cost.close();self.assertEqual(source.module_prices(offers,costs,{'merchant_operations':'b'*64}),{})
    def gate_fixture(self):
        now=int(time.time());gate={'decision':'RELEASE_APPROVED','scope':'SHOWCASE_STATIC_ONLY','max_executions':1,'rollback_approved':True,'issued_unix':now-1,'expires_unix':now+600,'artifact_id':10,'ci_run_id':20,'tar_sha256':'a'*64,'package_manifest_sha256':'b'*64,'commit':'c'*40,'review_comment_id':30}
        def fetch(path):
            if path=='issues/comments/40':return {'id':40,'user':{'login':'owner'},'issue_url':'https://api.github.com/repos/'+source.REPO+'/issues/122','body':'XUANJUN_SHOWCASE_RELEASE\n'+json.dumps(gate)}
            if path=='issues/comments/30':return {'id':30,'user':{'login':'auditor'},'issue_url':'https://api.github.com/repos/'+source.REPO+'/issues/122','body':'XUANJUN_SHOWCASE_PUBLICATION_REVIEW\n'+json.dumps({'decision':'AUDIT_PASS','reviewer_role':'INDEPENDENT_AUDITOR',**{k:gate[k] for k in ('tar_sha256','package_manifest_sha256','commit','ci_run_id')}})}
            if path=='actions/runs/20':return {'head_sha':'c'*40,'conclusion':'success','status':'completed','workflow_id':source.WORKFLOW_ID,'event':'workflow_dispatch'}
            if path=='actions/artifacts/10':return {'expired':False,'workflow_run':{'id':20,'head_sha':'c'*40}}
            raise AssertionError(path)
        patch=mock.patch('scripts.pr122_showcase_trust.load',side_effect=lambda: anchored(fetch('issues/comments/30'), 'PUBLICATION'));patch.start();self.addCleanup(patch.stop)
        return gate,fetch,{'publishers':['owner'],'reviewers':['auditor']}
    def test_separate_publication_review_ci_artifact_and_one_use_permission(self):
        gate,fetch,policy=self.gate_fixture();result=promotion.approval(40,policy,fetch);self.assertEqual(result['release_comment_id'],40)
        with self.assertRaisesRegex(ValueError,'RELEASE_COMMENT_ORIGIN'):promotion.approval(40,{**policy,'publishers':['someone-else']},fetch)
        gate['expires_unix']=0
        with self.assertRaisesRegex(ValueError,'RELEASE_EXPIRY'):promotion.approval(40,policy,fetch)
    def test_failed_or_wrong_ci_cannot_be_promoted(self):
        gate,fetch,policy=self.gate_fixture()
        def wrong(path):
            result=fetch(path)
            if path=='actions/runs/20':result['head_sha']='d'*40
            return result
        with self.assertRaisesRegex(ValueError,'EXACT_RELEASE_CI'):promotion.approval(40,policy,wrong)

if __name__=='__main__':unittest.main()
