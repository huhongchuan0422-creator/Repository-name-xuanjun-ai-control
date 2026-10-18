"""Synthetic signed journeys and fail-closed persisted earnings observations."""
import copy
import hashlib
import json
import unittest
from unittest.mock import Mock
import test_community_reports as fixtures
from scripts.pr122_customer_core import canonical
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_provider_reference import provider_order_reference


class CommunityEarningsIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()

    def setUp(self):
        self.fx=fixtures.CommunityReportJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.fx.basket();self.c=self.fx.c
        self.fx.call('community_receiver_bind',dict(community_id=self.fx.cid,provider_workspace='finance',
            receiver_id='comm',expected_version=0),workspace='platform')
        self.fx.finance('rule_create',dict(rule_id='rule',version=1,shares_bps=dict(comm=1000),description='community',unfreeze_unsplit=True))
        self.fx.finance('rule_activate',dict(rule_id='rule',version=1,expected_revision=0))
        self.snapshot=self.fx.finance('rule_freeze',dict(reference='basket'))
        self.fx.complete_split()
        self.action_key=self.c.db.execute("SELECT subject_idx FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION'").fetchone()[0]
        self.action=self.fx.actions._load(self.action_key)
        self.lock=self.c.idx('provider-order-action:'+self.fx.reader._mchid+':'+provider_order_reference(self.fx.reader._mchid,DEMO_SCOPE,'basket'))
        self.snapshot_key=hashlib.sha256(canonical([DEMO_SCOPE,'ORDER','basket'])).hexdigest()

    def read(self,channel,key,context):
        row=self.c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',(channel,key,'project1')).fetchone()
        return json.loads(self.c.decrypt(row[0],context))

    def write(self,channel,key,record,context):
        with self.c.tx():
            changed=self.c.db.execute('UPDATE links SET payload=? WHERE channel=? AND subject_idx=? AND project=?',
                (self.c.encrypt(canonical(record),context),channel,key,'project1'))
            self.assertEqual(changed.rowcount,1)

    def save_action(self,record):self.write('COMMUNITY_PROVIDER_ACTION',self.action_key,record,'provider-action:'+self.action_key)
    def budget(self):return self.read('COMMUNITY_PROVIDER_ORDER_BUDGET',self.lock,'provider-order-budget')
    def save_budget(self,record):self.write('COMMUNITY_PROVIDER_ORDER_BUDGET',self.lock,record,'provider-order-budget')
    def save_snapshot(self,record):self.write('COMMUNITY_SPLIT_RULES_V1',self.snapshot_key,record,'community-split-rule:'+self.snapshot_key)
    def save_return(self,key,record):self.write('COMMUNITY_PROVIDER_RETURN',key,record,'community-provider-return:'+key)
    def report(self):return self.fx.call('community_earnings',dict(community_id=self.fx.cid,after_id=''))
    def denied(self):
        with self.assertRaisesRegex(ValueError,'COMMUNITY_(EARNINGS_INTEGRITY_CONFLICT|RETURN_EXCEEDS_CONFIRMED_SPLIT)'):
            self.report()

    def return_money(self,amount=3,request_id='return1',result='SUCCESS'):
        def provider(request):
            self.assertEqual(request.method,'POST')
            self.assertTrue(request.full_url.endswith('/v3/profitsharing/return-orders'))
            payload=json.loads(request.data)
            return self.fx.signed_response(dict(payload,result=result))
        self.fx.reader._fetch=Mock(side_effect=provider)
        self.fx.finance('split_return',dict(reference='basket',request_id=request_id,receiver_id='comm',amount_minor=amount,description='Synthetic return'))
        key=self.budget()['return_actions'][-1]
        return key,self.read('COMMUNITY_PROVIDER_RETURN',key,'community-provider-return:'+key)

    def test_signed_split_and_partial_return_preserve_original_records(self):
        self.assertEqual(self.report()['page_gross_minor'],10)
        self.return_money()
        before=[tuple(r) for r in self.c.db.execute("SELECT * FROM links WHERE channel LIKE 'COMMUNITY_PROVIDER_%' ORDER BY channel,subject_idx")]
        original=list(self.fx.fx.stage.demo.db.iterdump())
        report=self.report()
        self.assertEqual((report['page_gross_minor'],report['page_returns_minor'],report['page_net_minor']),(10,3,7))
        self.assertEqual(report['records'][0]['returned_minor'],3)
        self.assertEqual(report['finance_status'],'UNCONFIRMED')
        self.assertEqual(before,[tuple(r) for r in self.c.db.execute("SELECT * FROM links WHERE channel LIKE 'COMMUNITY_PROVIDER_%' ORDER BY channel,subject_idx")])
        self.assertEqual(original,list(self.fx.fx.stage.demo.db.iterdump()))

    def test_distinct_successful_returns_sum_once(self):
        self.return_money(2,'first');self.return_money(3,'second')
        self.assertEqual(self.report()['page_net_minor'],5)

    def test_failed_processing_and_unknown_returns_do_not_count(self):
        key,back=self.return_money(result='FAILED')
        for result in ('FAILED','PROCESSING',None):
            changed=copy.deepcopy(back)
            if result is None:changed.pop('result')
            else:changed['result']=result
            self.save_return(key,changed)
            with self.subTest(result=result):self.assertEqual(self.report()['page_net_minor'],10)

    def test_receiver_config_changes_do_not_reinterpret_original_identity(self):
        self.return_money()
        scope=tuple(DEMO_SCOPE[k] for k in ('tenant_id','merchant_id','store_id'))
        self.fx.actions.bindings[scope]['receivers']['comm']['account']='9999999999'
        self.assertEqual(self.report()['page_net_minor'],7)

    def test_missing_or_foreign_split_budget_is_rejected(self):
        budget=self.budget();budget['split_action']='e'*64;self.save_budget(budget);self.denied()
        with self.c.tx():self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_PROVIDER_ORDER_BUDGET' AND subject_idx=?",(self.lock,))
        self.denied()

    def test_duplicate_return_key_is_not_double_counted(self):
        key,_=self.return_money();budget=self.budget();budget['return_actions'].append(key);self.save_budget(budget);self.denied()

    def test_missing_return_record_is_not_silently_zero(self):
        self.return_money();budget=self.budget();budget['return_actions']=['e'*64];self.save_budget(budget);self.denied()

    def test_foreign_return_row_project_is_not_read(self):
        key,_=self.return_money()
        with self.c.tx():self.c.db.execute("UPDATE links SET project='unrelated' WHERE channel='COMMUNITY_PROVIDER_RETURN' AND subject_idx=?",(key,))
        self.denied()

    def test_return_identity_binding_is_required(self):
        key,back=self.return_money()
        changes=({'scope':dict(DEMO_SCOPE,tenant_id='other')},{'scope':dict(DEMO_SCOPE,merchant_id='other')},
                 {'scope':dict(DEMO_SCOPE,store_id='other')},{'project':'other'},{'reference':'other'},
                 {'request_id':'other'},{'receiver_id':'other'})
        for change in changes:
            self.save_return(key,dict(back,**change))
            with self.subTest(change=change):self.denied()

    def test_return_provider_identity_binding_is_required(self):
        key,back=self.return_money()
        for field in ('out_order_no','out_return_no','sub_mchid','return_mchid'):
            changed=copy.deepcopy(back);changed['payload'][field]='other';self.save_return(key,changed)
            with self.subTest(field=field):self.denied()

    def test_return_total_cannot_exceed_confirmed_split(self):
        first,back=self.return_money(6,'first');second,other=self.return_money(4,'second')
        other['payload']['amount']=5;self.save_return(second,other);self.denied()

    def test_split_action_identity_is_required(self):
        for field,value in (('project','other'),('scope_hash','f'*64),('policy_hash','f'*64),
                            ('provider_reference','other'),('request_id','other')):
            self.save_action(dict(self.action,**{field:value}))
            with self.subTest(field=field):self.denied()

    def test_duplicate_or_missing_receiver_observation_is_rejected(self):
        for receivers in ([],self.action['result']['receivers']*2):
            changed=copy.deepcopy(self.action);changed['result']['receivers']=receivers;self.save_action(changed)
            with self.subTest(receivers=receivers):self.denied()

    def test_return_without_finished_successful_split_is_rejected(self):
        self.return_money()
        for state,result in (('PROCESSING','SUCCESS'),('FINISHED','CLOSED'),('FINISHED','PENDING')):
            changed=copy.deepcopy(self.action);changed['result']['status']=state;changed['result']['receivers'][0]['result']=result
            self.save_action(changed)
            with self.subTest(state=state,result=result):self.denied()

    def test_pending_split_is_unconfirmed_and_not_earnings(self):
        changed=copy.deepcopy(self.action);changed['result']=dict(status='PROCESSING',receivers=[])
        self.save_action(changed);self.assertEqual(self.report()['records'],[])
        changed['result']=dict(status='PROCESSING',receivers=[dict(receiver_id='comm',amount_minor=10,result='PENDING')])
        self.save_action(changed);self.assertEqual(self.report()['page_gross_minor'],0)
        changed.pop('result');self.save_action(changed);self.assertEqual(self.report()['records'],[])

    def test_frozen_receiver_mapping_must_match_original_scope_and_id(self):
        for field,value in (('scope',dict(DEMO_SCOPE,store_id='other')),('receiver_id','other')):
            changed=copy.deepcopy(self.snapshot);changed['receiver_communities']['comm'][field]=value;self.save_snapshot(changed)
            with self.subTest(field=field):self.denied()

    def test_split_amount_must_equal_frozen_allocation(self):
        changed=copy.deepcopy(self.action);changed['result']['receivers'][0]['amount_minor']=500;self.save_action(changed);self.denied()


def invalid_money_case(amount,is_return):
    def test(self):
        if is_return:
            key,back=self.return_money();back['payload']['amount']=amount;self.save_return(key,back)
        else:
            changed=copy.deepcopy(self.action);changed['result']['receivers'][0]['amount_minor']=amount;self.save_action(changed)
        self.denied()
    return test


for index,amount in enumerate((True,False,0,-3,1.5,'3',None)):
    for is_return in (False,True):
        setattr(CommunityEarningsIntegrity,'test_invalid_'+('return' if is_return else 'split')+'_amount_'+str(index),invalid_money_case(amount,is_return))


if __name__=='__main__':unittest.main()
