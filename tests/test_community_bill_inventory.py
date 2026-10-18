"""Real Center snapshots and scope-safe bill diagnostics; synthetic provider data."""
import copy
import datetime as dt
import hashlib
import json
import sqlite3
import threading
import unittest
from unittest.mock import Mock,patch

import test_community_profitsharing_bill_schema as fixtures
from scripts.community_provider_bills import signed_bill_evidence
from scripts.community_provider_reference import provider_order_reference
from scripts.community_order_store import create_order
from scripts.pr122_customer_core import canonical


class LocalBillInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.ExactSplitDetailJourney.setUpClass()

    def setUp(self):
        self.j=fixtures.ExactSplitDetailJourney();self.j.setUp()
        self.addCleanup(self.j.doCleanups)
        self.j.accept()
        self.c,self.a,self.g,self.bills=self.j.c,self.j.a,self.j.g,self.j.bills
        self.date=(dt.datetime.fromtimestamp(self.c.now(),dt.timezone(dt.timedelta(hours=8))).date()-dt.timedelta(days=1)).isoformat()

    def result(self,bill=None):return self.bills.reconcile(self.g,self.j.bill() if bill is None else bill)

    def stored(self,result):
        digest=result['local_inventory']['snapshot_sha256']
        raw=self.c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_BILL_LOCAL_SNAPSHOT' AND subject_idx=?",(digest,)).fetchone()[0]
        value=json.loads(self.c.decrypt(raw,'community-bill-local-snapshot:'+digest))
        self.assertEqual(hashlib.sha256(canonical(value)).hexdigest(),digest)
        return value,raw

    def insert(self,channel,record,ref=None,active=1,key=None):
        kind='SPLIT' if channel=='COMMUNITY_PROVIDER_ACTION' else 'RETURN'
        if ref is None:ref=record['provider_reference'] if kind=='SPLIT' else record['payload']['out_return_no']
        key=key or hashlib.sha256(canonical([self.a.reader._mchid,kind,ref])).hexdigest()
        aad=('provider-action:' if kind=='SPLIT' else 'community-provider-return:')+key
        encrypted=self.c.encrypt(canonical(record),aad)
        self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,?)',(channel,key,self.g['user_id'],record.get('project',self.g['project']),encrypted,active))
        return key

    def split(self,suffix):
        saved=copy.deepcopy(self.a._load(self.j.key))
        ref='private-split-'+str(suffix)
        saved['provider_reference']=ref;saved['payload']['out_order_no']=ref
        saved['bill_evidence']['details']['out_order_no']=ref
        saved['bill_evidence']['details']['order_id']='private-order-'+str(suffix)
        saved['bill_evidence']['details']['receivers'][0]['detail_id']='private-detail-'+str(suffix)
        return saved

    def returned(self,suffix,status='SUCCESS'):
        payload=dict(sub_mchid=self.j.policy['sub_mchid'],out_order_no='synthetic-split',
            out_return_no='private-return-'+str(suffix),return_mchid='1234567892',amount=5)
        saved=dict(scope=self.g['scope'],project=self.g['project'],payload=payload,result=status)
        if status=='SUCCESS':
            data=dict(payload,order_id='synthetic-wechat-split',return_id='private-provider-return-'+str(suffix),
                result='SUCCESS',finish_time='2026-10-16T12:00:00+08:00')
            saved['bill_evidence']=signed_bill_evidence(data,'e'*64,'RETURN')
        return saved

    def fetch(self,raw,kind='SPLIT'):
        self.a._call=Mock(return_value=(dict(hash_type='SHA1',hash_value=hashlib.sha1(raw).hexdigest(),
            download_url='https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=synthetic'),'a'*64))
        self.bills._download=Mock(return_value=raw)
        return self.call('bill_fetch',kind=kind)

    def call(self,op,kind='SPLIT',**extra):
        return self.bills.dispatch(self.j.fx.web['token'],self.j.fx.web['csrf'],'finance',op,
                                   dict(kind=kind,bill_date=self.date,**extra))

    def test_complete_capture_remains_incomplete_provider_reconciliation(self):
        result=self.result();inv=result['local_inventory']
        self.assertEqual(inv['counts']['split_records'],1)
        self.assertEqual(inv['counts']['successful_split_details'],1)
        self.assertEqual(inv['reverse_candidates']['absent_from_selected_bill_count'],0)
        self.assertEqual(result['reverse_coverage'],'NOT_ESTABLISHED')
        self.assertEqual(inv['bill_date_membership'],'NOT_ASSIGNED')
        self.assertFalse(inv['complete_reconciliation_available'])
        self.assertEqual(inv['runtime_order_database'],'NOT_INCLUDED_IN_LOCAL_SNAPSHOT')
        self.assertEqual(result['finance_status'],'UNCONFIRMED')
        self.assertFalse(result['funds_retry_authorized'])

    def test_absent_candidates_are_opaque_date_free_and_never_missing_rows(self):
        self.insert('COMMUNITY_PROVIDER_ACTION',self.split('extra'))
        result=self.result();other=self.j.bill();other['bill_date']='2000-01-01'
        other['rows'][0]['分账时间']='1999-12-31 23:59:59'
        second=self.result(other)
        candidates=result['local_inventory']['reverse_candidates']
        self.assertEqual(candidates,second['local_inventory']['reverse_candidates'])
        self.assertEqual(candidates['absent_from_selected_bill_count'],1)
        self.assertFalse(candidates['establishes_missing_bill_rows'])
        self.assertRegex(candidates['opaque_detail_tokens'][0],'^[0-9a-f]{64}$')
        self.assertNotIn('missing_provider_rows',result)
        self.assertNotIn('private-',json.dumps(result))
        self.assertEqual(result['status'],'DETAIL_FIELDS_MATCH_RECONCILIATION_PENDING')

    def test_empty_bill_does_not_turn_all_local_successes_into_daily_missing(self):
        result=self.result(self.j.bill(rows=[]))
        self.assertEqual(result['local_inventory']['reverse_candidates']['absent_from_selected_bill_count'],1)
        self.assertEqual(result['exceptions'],[])
        self.assertEqual(result['reverse_coverage'],'NOT_ESTABLISHED')

    def test_closed_detail_is_counted_without_assuming_failed_summary_formula(self):
        saved=self.a._load(self.j.key)
        saved['bill_evidence']['details']['receivers'][0]['result']='CLOSED'
        saved['result']['receivers'][0]['result']='CLOSED';self.a._save(self.j.key,saved)
        result=self.result(self.j.bill(rows=[]));inv=result['local_inventory']
        self.assertEqual(inv['counts']['closed_split_details'],1)
        self.assertEqual(inv['reverse_candidates']['absent_from_selected_bill_count'],0)
        self.assertEqual(result['summary_amounts'],'NOT_RECONCILED')

    def test_unknown_processing_terminal_without_evidence_and_invalid_bindings_count(self):
        for suffix,status in (('unknown',None),('processing','PROCESSING'),('legacy','FINISHED')):
            saved=self.split(suffix);saved.pop('bill_evidence')
            if status is None:saved.pop('result')
            else:saved['result']['status']=status
            self.insert('COMMUNITY_PROVIDER_ACTION',saved)
        self.insert('COMMUNITY_PROVIDER_ACTION',self.split('bad-key'),key='f'*64)
        counts=self.result()['local_inventory']['counts']
        self.assertEqual(counts['split_records'],5)
        self.assertEqual(counts['split_nonterminal_records'],2)
        self.assertEqual(counts['split_missing_evidence_records'],3)
        self.assertEqual(counts['split_terminal_missing_evidence_records'],1)
        self.assertEqual(counts['invalid_binding_records'],1)

    def test_return_channel_enumerated_but_never_given_unverified_csv_join(self):
        for status in ('SUCCESS','FAILED','PROCESSING'):
            self.insert('COMMUNITY_PROVIDER_RETURN',self.returned(status,status))
        counts=self.result()['local_inventory']['counts']
        self.assertEqual(counts['return_records'],3)
        self.assertEqual(counts['return_terminal_records'],2)
        self.assertEqual(counts['return_nonterminal_records'],1)
        self.assertEqual(counts['successful_return_records'],1)
        self.assertEqual(counts['failed_return_records'],1)
        self.assertEqual(counts['return_missing_evidence_records'],2)
        self.assertEqual(counts['return_invalid_evidence_records'],0)

    def test_foreign_scope_and_project_never_contribute_records_tokens_or_counts(self):
        for suffix,change in (('scope',dict(scope=dict(self.g['scope'],store_id='private-other-store'))),
                              ('project',dict(project='private-other-project'))):
            saved=self.split(suffix);saved.update(change);self.insert('COMMUNITY_PROVIDER_ACTION',saved)
            saved=self.returned(suffix);saved.update(change);self.insert('COMMUNITY_PROVIDER_RETURN',saved)
        result=self.result();manifest,_=self.stored(result)
        self.assertEqual(result['local_inventory']['counts']['split_records'],1)
        self.assertEqual(result['local_inventory']['counts']['return_records'],0)
        self.assertEqual(len(manifest['records']),1)
        self.assertNotIn('private-other',json.dumps(result))
        self.assertNotIn('private-other',json.dumps(manifest))

    def test_inactive_records_are_visible_inventory_blockers_not_candidates(self):
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_PROVIDER_ACTION' AND subject_idx=?",(self.j.key,))
        result=self.result();inv=result['local_inventory']
        self.assertEqual(inv['counts']['split_records'],1)
        self.assertEqual(inv['counts']['inactive_records'],1)
        self.assertEqual(inv['reverse_candidates']['absent_from_selected_bill_count'],0)
        self.assertEqual(result['matched_detail_rows'],0)

    def test_malformed_scope_is_explicitly_rejected_not_silently_empty(self):
        original=self.a._load(self.j.key)
        for scope in (None,{},dict(self.g['scope'],store_id=False)):
            saved=dict(original,scope=scope);self.a._save(self.j.key,saved)
            with self.assertRaisesRegex(ValueError,'UNCLASSIFIABLE_LOCAL_BILL_INVENTORY_SCOPE'):self.result()
        self.a._save(self.j.key,{})
        with self.assertRaisesRegex(ValueError,'UNCLASSIFIABLE_LOCAL_BILL_INVENTORY_SCOPE'):self.result()
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_BILL_LOCAL_SNAPSHOT'").fetchone()[0],0)

    def test_invalid_evidence_cannot_match_forward_even_if_bool_equals_integer(self):
        saved=self.a._load(self.j.key)
        saved['payload']['receivers'][0]['amount']=True
        saved['bill_evidence']['details']['receivers'][0]['amount']=True
        self.a._save(self.j.key,saved)
        result=self.result(self.j.bill({'金额':'0.01'}))
        self.assertEqual(result['matched_detail_rows'],0)
        self.assertEqual(result['unknown_rows'][0]['reason'],'INVALID_LOCAL_SIGNED_DETAIL_EVIDENCE')
        self.assertEqual(result['local_inventory']['counts']['split_invalid_evidence_records'],1)

    def test_boolean_frozen_intent_cannot_match_valid_integer_evidence(self):
        saved=self.a._load(self.j.key)
        saved['payload']['receivers'][0]['amount']=True
        saved['bill_evidence']['details']['receivers'][0]['amount']=1
        self.a._save(self.j.key,saved)
        result=self.result(self.j.bill({'金额':'0.01'}))
        self.assertEqual(result['matched_detail_rows'],0)
        self.assertEqual(result['local_inventory']['counts']['split_invalid_evidence_records'],1)
        self.assertIn('LOCAL_SIGNED_DETAIL_EVIDENCE_COMPLETENESS',result['pending_evidence'])

    def test_corrupt_details_count_unknown_without_crash_or_forward_match(self):
        original=self.a._load(self.j.key)
        for detail in ({},[],None):
            saved=copy.deepcopy(original);saved['bill_evidence']['details']=detail;self.a._save(self.j.key,saved)
            result=self.result()
            self.assertEqual(result['matched_detail_rows'],0)
            self.assertEqual(result['local_inventory']['counts']['split_invalid_evidence_records'],1)

    def test_snapshot_persists_original_encrypted_records_after_later_mutation(self):
        result=self.result();manifest,raw=self.stored(result)
        self.assertNotIn(b'synthetic-detail',raw)
        self.assertNotIn(b'1234567892',raw)
        saved=self.a._load(self.j.key);saved.pop('bill_evidence');self.a._save(self.j.key,saved)
        self.assertEqual(self.stored(result)[0],manifest)
        second=self.result()
        self.assertNotEqual(result['local_inventory']['snapshot_sha256'],second['local_inventory']['snapshot_sha256'])
        self.assertEqual(second['local_inventory']['counts']['split_terminal_missing_evidence_records'],1)

    def test_snapshot_anchor_is_original_audit_not_provider_time(self):
        anchor=self.c.db.execute('SELECT seq,sha FROM audit WHERE project=? ORDER BY seq DESC LIMIT 1',(self.g['project'],)).fetchone()
        result=self.result();inv=result['local_inventory']
        self.assertEqual(inv['audit_watermark'],dict(seq=anchor[0],sha256=anchor[1]))
        self.assertEqual(inv['captured_at'],self.c.now())
        self.assertEqual(inv['cutoff_basis'],'LOCAL_SQLITE_SNAPSHOT_NOT_PROVIDER_BUSINESS_DATE')

    def test_candidate_presentation_cap_does_not_truncate_enumeration(self):
        for i in range(203):self.insert('COMMUNITY_PROVIDER_ACTION',self.split(i))
        inv=self.result()['local_inventory'];candidates=inv['reverse_candidates']
        self.assertEqual(inv['counts']['split_records'],204)
        self.assertEqual(candidates['absent_from_selected_bill_count'],203)
        self.assertEqual(len(candidates['opaque_detail_tokens']),200)
        self.assertTrue(candidates['truncated'])

    def test_same_transaction_captures_both_channels_before_concurrent_writer(self):
        path=self.c.db.execute('PRAGMA database_list').fetchone()[2]
        prepared=[]
        for channel,record,kind,aad in (('COMMUNITY_PROVIDER_ACTION',self.split('concurrent'),'SPLIT','provider-action:'),
                                        ('COMMUNITY_PROVIDER_RETURN',self.returned('concurrent'),'RETURN','community-provider-return:')):
            ref=record['provider_reference'] if kind=='SPLIT' else record['payload']['out_return_no']
            key=hashlib.sha256(canonical([self.a.reader._mchid,kind,ref])).hexdigest()
            prepared.append((channel,key,self.g['user_id'],self.g['project'],self.c.encrypt(canonical(record),aad+key),1))
        attempted=threading.Event();finished=threading.Event();errors=[]
        def write():
            db=sqlite3.connect(path,timeout=10)
            try:
                attempted.set();db.execute('BEGIN IMMEDIATE')
                db.executemany('INSERT INTO links VALUES(?,?,?,?,?,?)',prepared);db.commit()
            except Exception as error:errors.append(type(error).__name__)
            finally:db.close();finished.set()
        thread=threading.Thread(target=write);now=self.c.now
        def capture_clock():
            self.assertTrue(self.c.db.in_transaction)
            thread.start();self.assertTrue(attempted.wait(2))
            self.assertFalse(finished.is_set());return now()
        with patch.object(self.c,'now',side_effect=capture_clock):first=self.result()
        thread.join(12);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        counts=first['local_inventory']['counts']
        self.assertEqual((counts['split_records'],counts['return_records']),(1,0))
        counts=self.result()['local_inventory']['counts']
        self.assertEqual((counts['split_records'],counts['return_records']),(2,1))

    def test_forward_matches_use_captured_action_not_later_live_replacement(self):
        capture=self.bills._split_local_inventory
        def replace(*args):
            result=capture(*args)
            saved=self.a._load(self.j.key);saved.pop('bill_evidence');self.a._save(self.j.key,saved)
            return result
        with self.c.tx(),patch.object(self.bills,'_split_local_inventory',side_effect=replace):result=self.result()
        self.assertEqual(result['matched_detail_rows'],1)
        self.assertIn('bill_evidence',self.stored(result)[0]['records'][0]['record'])

    def test_require_complete_strict_bool_rejects_even_empty_bill_without_snapshots(self):
        self.fetch(fixtures.bill_bytes(rows=[],summary=['0','0','0','0','0']))
        for value in (True,):
            with self.assertRaisesRegex(ValueError,'COMPLETE_SPLIT_BILL_RECONCILIATION_UNAVAILABLE'):
                self.call('bill_reconcile',require_complete=value)
        for value in (1,'true',None):
            with self.assertRaisesRegex(ValueError,'INVALID_PROVIDER_BILL_FIELDS'):
                self.call('bill_reconcile',require_complete=value)
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM links WHERE channel='COMMUNITY_BILL_LOCAL_SNAPSHOT'").fetchone()[0],0)
        self.assertIn('local_inventory',self.call('bill_reconcile',require_complete=False))

    def test_require_complete_never_bypasses_current_authentication(self):
        with self.assertRaises(PermissionError):
            self.bills.dispatch(self.j.fx.web['token'],'','finance','bill_reconcile',
                dict(kind='SPLIT',bill_date=self.date,require_complete=True))

    def test_revocation_before_persistence_rolls_back_snapshot_and_reconciliation(self):
        self.fetch(fixtures.bill_bytes())
        capture=self.bills._split_local_inventory
        def revoke(*args):
            result=capture(*args);self.j.fx.ops.grants['finance']['role']='REVOKED';return result
        with patch.object(self.bills,'_split_local_inventory',side_effect=revoke),self.assertRaises(PermissionError):
            self.call('bill_reconcile')
        for channel in ('COMMUNITY_BILL_LOCAL_SNAPSHOT','COMMUNITY_BILL_RECONCILIATION'):
            self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM links WHERE channel=?',(channel,)).fetchone()[0],0)

    def test_audit_revocation_during_private_read_prevents_result_disclosure(self):
        self.fetch(fixtures.bill_bytes());self.call('bill_reconcile')
        decrypt=self.c.decrypt
        def revoke(raw,aad):
            result=decrypt(raw,aad)
            if aad.startswith('community-bill-reconciliation:'):
                self.j.fx.ops.grants['finance']['role']='REVOKED'
            return result
        with patch.object(self.c,'decrypt',side_effect=revoke),self.assertRaises(PermissionError):
            self.call('bill_audit',after_id='')

    def test_trade_preview_reveals_only_proven_current_scope_rows(self):
        foreign=dict(self.g['scope'],store_id='other-private-store')
        create_order(self.a.runtime.demo.db,foreign,'private-other-order',98765)
        own=provider_order_reference(self.a.reader._mchid,self.g['scope'],'basket')
        other=provider_order_reference(self.a.reader._mchid,foreign,'private-other-order')
        raw=('商户订单号,微信订单号,交易状态,订单金额,特约商户号,币种\n'
            +own+',synthetic-tx,SUCCESS,1.01,'+self.j.policy['sub_mchid']+',CNY\n'
            +other+',private-other-tx,SUCCESS,987.65,'+self.j.policy['sub_mchid']+',CNY\n'
            +'private-unknown,private-unknown-tx,SUCCESS,876.54,'+self.j.policy['sub_mchid']+',CNY\n').encode()
        self.fetch(raw,'TRADE');result=self.call('bill_rows',kind='TRADE',offset=0)
        self.assertEqual(result['records'][0]['商户订单号'],own)
        self.assertEqual(result['unattributed_rows_redacted'],2)
        for secret in (other,'private-other-tx','987.65','private-unknown','876.54'):
            self.assertNotIn(secret,json.dumps(result))

    def test_unbound_refund_row_cannot_reveal_refund_identity(self):
        own=provider_order_reference(self.a.reader._mchid,self.g['scope'],'basket')
        raw=('商户订单号,微信订单号,交易状态,订单金额,商户退款单号,微信退款单号\n'
             +own+',synthetic-tx,REFUND,1.01,private-refund,private-refund-id\n').encode()
        self.fetch(raw,'TRADE');result=self.call('bill_rows',kind='TRADE',offset=0)
        self.assertEqual(result['records'],[{}]);self.assertNotIn('private-refund',json.dumps(result))

    def test_split_preview_redacts_foreign_and_unproven_business_rows(self):
        saved=self.split('foreign');saved['scope']=dict(self.g['scope'],store_id='other-store')
        self.insert('COMMUNITY_PROVIDER_ACTION',saved)
        rows=[]
        for ref,tx,kind in (('synthetic-split','synthetic-tx','分出'),
                            (saved['provider_reference'],'private-other-tx','分出'),
                            ('synthetic-split','private-return-tx','分账回退')):
            row=self.j.bill()['rows'][0];row.update({'商户分账/回退单号':ref,'微信订单号':tx,'业务类型':kind})
            rows.append([row[k] for k in fixtures.SPLIT_COLUMNS])
        self.fetch(fixtures.bill_bytes(rows=rows));result=self.call('bill_rows',offset=0)
        self.assertEqual(result['records'][0]['微信订单号'],'synthetic-tx')
        self.assertEqual(result['records'][1:],[{},{}])
        self.assertNotIn('private-',json.dumps(result))


if __name__=='__main__':unittest.main()
