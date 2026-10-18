"""Explicit original-ID recovery across real Center/quote/order SQLite commits."""
import concurrent.futures
import hashlib
import json
import pathlib
import shutil
import sqlite3
import subprocess
import threading
import unittest
from unittest.mock import patch

import test_community_center_saas as fixtures
from scripts.community_center_saas import CenterSaas
from scripts.community_saas_phase2 import OfflineSaas
from scripts.community_stage_runtime import StageRuntime
from scripts.pr122_customer_core import Center, canonical

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SaasReservationRecovery(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.CustomerSaas(); self.base.setUp(); self.fx = self.base.fx
        self.quote_path = pathlib.Path(self.fx.stage.tmp.name)/'quotes-recovery.sqlite'
        self.order_path = pathlib.Path(self.fx.stage.tmp.name)/'saas-recovery.sqlite'
        for name,path in (('q',self.quote_path),('s',self.order_path)):
            old=getattr(self.fx.stage,name); new=sqlite3.connect(path)
            old.backup(new); old.close(); setattr(self.fx.stage,name,new)
        self.compose()

    def compose(self):
        self.fx.stage.api.saas = OfflineSaas(self.fx.stage.q,self.fx.stage.s,self.fx.stage.q)
        self.base.api = CenterSaas(self.fx.center,self.fx.stage.api,self.base.grants)

    def tearDown(self): self.base.tearDown()
    def call(self,*args,**kwargs): return self.base.call(*args,**kwargs)
    def quote(self): return self.base.quote()
    def reserve_order(self,after_commit=False):
        quote=self.quote(); args=dict(quote_id=quote['quote_id'],currency='CNY')
        original=self.fx.stage.api.dispatch
        def failure(principal,op,p,now):
            if op=='order_prepare':
                if after_commit: original(principal,op,p,now)
                raise RuntimeError('INJECTED_ORDER_INTERRUPTION')
            return original(principal,op,p,now)
        with patch.object(self.fx.stage.api,'dispatch',side_effect=failure):
            with self.assertRaisesRegex(RuntimeError,'INJECTED_ORDER_INTERRUPTION'): self.call('order_prepare',args)
        row=self.call('mine',dict(kind='ORDER',after_id=''))['records'][0]
        return args,row
    def reserve_quote(self,after_commit=False):
        original=self.fx.stage.api.saas.dispatch
        def failure(principal,op,p,now):
            if op=='quote':
                if after_commit: original(principal,op,p,now)
                raise RuntimeError('INJECTED_QUOTE_INTERRUPTION')
            return original(principal,op,p,now)
        with patch.object(self.fx.stage.api.saas,'dispatch',side_effect=failure):
            with self.assertRaisesRegex(RuntimeError,'INJECTED_QUOTE_INTERRUPTION'): self.quote()
        return self.call('mine',dict(kind='QUOTE',after_id=''))['records'][0]
    def reopen(self):
        self.fx.reopen()
        self.fx.stage.q.close(); self.fx.stage.s.close()
        self.fx.stage.q=sqlite3.connect(self.quote_path);self.fx.stage.s=sqlite3.connect(self.order_path)
        self.compose()
    def change_reservation(self,kind,reference,patches):
        c=self.fx.center
        raw=c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=?',('COMMUNITY_SAAS_'+kind,reference)).fetchone()[0]
        saved=json.loads(c.decrypt(raw,'community-saas:'+reference)); saved.update(patches)
        with c.tx():c.db.execute('UPDATE links SET payload=? WHERE channel=? AND subject_idx=?',(c.encrypt(canonical(saved),'community-saas:'+reference),'COMMUNITY_SAAS_'+kind,reference))

    def test_order_interruption_reopen_same_id_and_repeat_create_exactly_once(self):
        args,row=self.reserve_order();self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],0)
        self.reopen();self.fx.stage.now+=5
        result=self.call('order_prepare',args);again=self.call('order_prepare',args)
        self.assertEqual(result,again);self.assertEqual(result['order_id'],row['order_id'])
        self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],1)
        self.assertFalse(result['payment_confirmed']);self.assertFalse(result['entitlement_granted'])

    def test_committed_order_unknown_response_reads_even_after_quote_expiry(self):
        args,row=self.reserve_order(after_commit=True);self.reopen();self.fx.stage.now+=1801
        original=self.fx.stage.api.dispatch
        def reader(principal,op,p,now):
            self.assertNotEqual(op,'order_prepare');return original(principal,op,p,now)
        with patch.object(self.fx.stage.api,'dispatch',side_effect=reader):
            result=self.call('order_prepare',args)
        self.assertEqual(result['order_id'],row['order_id']);self.assertEqual(result['created_at'],row['created_at'])

    def test_missing_order_expired_quote_stays_missing_with_original_reservation(self):
        args,row=self.reserve_order();self.fx.stage.now+=1801
        with self.assertRaisesRegex(ValueError,'QUOTE_EXPIRED'):self.call('order_prepare',args)
        self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],0)
        self.assertEqual(self.call('mine',dict(kind='ORDER',after_id=''))['records'][0]['order_id'],row['order_id'])

    def test_missing_order_with_prior_lifecycle_is_integrity_hold_not_recreated(self):
        args,row=self.reserve_order()
        self.fx.stage.s.execute("INSERT INTO saas_order_lifecycle VALUES(?,'CONFIRMED_EXTERNAL','prior_proof',?)",(row['order_id'],self.fx.stage.now))
        self.fx.stage.s.commit()
        with self.assertRaisesRegex(PermissionError,'MISSING_ORIGINAL_ORDER_HAS_DOWNSTREAM_EVIDENCE'):
            self.call('order_prepare',args)
        self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],0)

    def test_changed_reservation_quote_currency_digest_or_subject_rejected(self):
        args,row=self.reserve_order();ref=row['order_id']
        for field,value in (('quote_id','sq_'+'f'*32),('currency','USD'),('order_id','so_'+'f'*32),('quote_sha256','f'*64)):
            self.change_reservation('ORDER',ref,{field:value})
            with self.assertRaisesRegex(PermissionError,'ORIGINAL_ORDER_RESERVATION_CHANGED'):self.call('order_prepare',args)
            self.change_reservation('ORDER',ref,{field:row[field]})
        with self.assertRaises(PermissionError):self.call('order_prepare',args,other=True)
        self.fx.center.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_SAAS_ORDER' AND subject_idx=?",(self.fx.uid2,ref))
        with self.assertRaises(PermissionError):self.call('order_prepare',args)
        self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],0)

    def test_new_currency_is_a_distinct_explicit_order_not_rebinding_existing_one(self):
        args,row=self.reserve_order();cny=self.call('order_prepare',args);usd=self.call('order_prepare',dict(args,currency='USD'))
        self.assertNotEqual(cny['order_id'],usd['order_id']);self.assertEqual(cny['order_id'],row['order_id'])
        self.assertEqual(usd['currency'],'USD');self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],2)
        with self.assertRaises(ValueError):self.call('order_prepare',dict(args,currency='EUR'))

    def test_original_quote_version_binding_checked_before_order_reservation(self):
        q=self.quote();self.change_reservation('QUOTE',q['quote_id'],{'version':2})
        with self.assertRaisesRegex(PermissionError,'ORIGINAL_QUOTE_RESERVATION_CHANGED'):
            self.call('order_prepare',dict(quote_id=q['quote_id'],currency='CNY'))
        self.assertEqual(self.call('mine',dict(kind='ORDER',after_id=''))['records'],[])

    def test_quote_interruption_explicit_recovery_preserves_price_time_and_id(self):
        row=self.reserve_quote();qid=row['quote_id'];self.reopen();self.fx.stage.now+=45
        with self.assertRaisesRegex(ValueError,'QUOTE_NOT_FOUND'):self.call('quote_read',dict(quote_id=qid))
        self.assertEqual(self.fx.stage.q.execute('SELECT count(*) FROM saas_quotes').fetchone()[0],0)
        result=self.call('quote_recover',dict(quote_id=qid));again=self.call('quote_recover',dict(quote_id=qid))
        self.assertEqual(result,again);self.assertEqual(result['quote_id'],qid);self.assertEqual(result['created_at'],row['created_at'])
        self.assertEqual(result['expires_at'],row['created_at']+1800);self.assertEqual(result['totals_by_cycle']['MONTH']['cny_minor'],1000)
        self.assertEqual(self.fx.stage.q.execute('SELECT count(*) FROM saas_quotes').fetchone()[0],1)
        self.assertNotIn('cost_cny_minor',result['lines'][0])

    def test_quote_committed_unknown_response_recovers_read_only_after_expiry(self):
        row=self.reserve_quote(after_commit=True);self.fx.stage.now+=1801
        original=self.fx.stage.api.saas.dispatch
        def reader(principal,op,p,now):
            self.assertNotEqual(op,'quote');return original(principal,op,p,now)
        with patch.object(self.fx.stage.api.saas,'dispatch',side_effect=reader):
            result=self.call('quote_recover',dict(quote_id=row['quote_id']))
        self.assertEqual(result['created_at'],row['created_at'])

    def test_expired_or_unfingerprinted_or_changed_source_cannot_recreate_quote(self):
        row=self.reserve_quote();qid=row['quote_id']
        self.change_reservation('QUOTE',qid,{'source_sha256':None})
        with self.assertRaisesRegex(PermissionError,'SOURCE_UNVERIFIED'):self.call('quote_recover',dict(quote_id=qid))
        self.change_reservation('QUOTE',qid,{'source_sha256':'f'*64})
        with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):self.call('quote_recover',dict(quote_id=qid))
        self.change_reservation('QUOTE',qid,{'source_sha256':row['source_sha256']});self.fx.stage.now+=1800
        with self.assertRaisesRegex(ValueError,'WINDOW_EXPIRED'):self.call('quote_recover',dict(quote_id=qid))
        self.assertEqual(self.fx.stage.q.execute('SELECT count(*) FROM saas_quotes').fetchone()[0],0)

    def test_quote_source_approval_change_does_not_retroactively_modify_original_request(self):
        from scripts.community_saas_offer_catalog import create_offer,approve_offer
        create_offer(self.fx.stage.q,'draft',1,'storefront_catalog','BUYOUT',[dict(type='MODULE_FEE',label='Draft',cycle='ONCE',quantity=1,cny_minor=99,usd_minor=9,cost_cny_minor=1,cost_usd_minor=1)])
        original=self.fx.stage.api.saas.dispatch
        def fail(principal,op,p,now):
            if op=='quote':raise RuntimeError('interruption')
            return original(principal,op,p,now)
        with patch.object(self.fx.stage.api.saas,'dispatch',side_effect=fail):
            with self.assertRaises(RuntimeError):self.call('quote',dict(offer_id='draft',version=1))
        qid=self.call('mine',dict(kind='QUOTE',after_id=''))['records'][0]['quote_id']
        approve_offer(self.fx.stage.q,'draft',1,'later_approval','later_cost',self.fx.stage.now)
        with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):self.call('quote_recover',dict(quote_id=qid))

    def test_recovery_rechecks_current_session_project_and_ownership(self):
        row=self.reserve_quote();params=dict(quote_id=row['quote_id'])
        with self.assertRaises(PermissionError):self.call('quote_recover',params,other=True)
        with self.assertRaises(ValueError):self.call('quote_recover',dict(params,created_at=self.fx.stage.now))
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.call('quote_recover',params)
        self.assertEqual(self.fx.stage.q.execute('SELECT count(*) FROM saas_quotes').fetchone()[0],0)

    def test_two_real_connections_recover_only_one_order(self):
        args,row=self.reserve_order();barrier=threading.Barrier(2);now=self.fx.stage.now
        def worker():
            c=Center(self.fx.tmp.name,{'testkey':b'k'*32},'testkey',clock=lambda:now,mail_ready=True)
            q=sqlite3.connect(self.quote_path);s=sqlite3.connect(self.order_path)
            try:
                rt=StageRuntime(self.fx.stage.demo,OfflineSaas(q,s,q),self.fx.stage.api.bindings,lambda:now)
                api=CenterSaas(c,rt,self.base.grants);barrier.wait(timeout=10)
                return api.dispatch(self.base.one['token'],self.base.one['csrf'],dict(workspace='one',operation='order_prepare',params=args))
            finally:q.close();s.close();c.db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0]['order_id'],row['order_id'])
        self.assertEqual(self.fx.stage.s.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],1)

    def test_two_real_connections_recover_only_one_quote(self):
        row=self.reserve_quote();barrier=threading.Barrier(2);now=self.fx.stage.now
        def worker():
            c=Center(self.fx.tmp.name,{'testkey':b'k'*32},'testkey',clock=lambda:now,mail_ready=True)
            q=sqlite3.connect(self.quote_path);s=sqlite3.connect(self.order_path)
            try:
                rt=StageRuntime(self.fx.stage.demo,OfflineSaas(q,s,q),self.fx.stage.api.bindings,lambda:now)
                api=CenterSaas(c,rt,self.base.grants);barrier.wait(timeout=10)
                return api.dispatch(self.base.one['token'],self.base.one['csrf'],dict(workspace='one',operation='quote_recover',params=dict(quote_id=row['quote_id'])))
            finally:q.close();s.close();c.db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.fx.stage.q.execute('SELECT count(*) FROM saas_quotes').fetchone()[0],1)

    def test_recovery_buttons_dom(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        subprocess.run([node,str(ROOT/'tests/community_saas_recovery_dom.cjs'),str(ROOT/'demos/community-stage/saas.js'),str(ROOT/'demos/community-stage/saas.html')],check=True,timeout=30)


if __name__=='__main__':unittest.main()
