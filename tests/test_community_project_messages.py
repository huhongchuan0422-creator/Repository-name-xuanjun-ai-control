"""Real original SQLite message pages and provenance guards; synthetic data only."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import unittest
import urllib.request

import test_community_mini_center_identity as fixtures
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce
from scripts.community_mini_http import serve
from scripts.community_project_messages import read_page
from scripts.pr122_customer_evidence import append, authorized_records


class ProjectMessagePagination(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterComposition(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.c = self.fx.center
        self.token = self.fx.token()
        self.configure()

    def configure(self):
        grant = dict(user_id=self.fx.uid1, project='project1', project_roles=['OWNER'], principal=self.fx.stage.merchant)
        self.commerce = Commerce(CenterOperations(self.c, self.fx.stage.api, {'merchant': grant}), self.fx.identity)
        self.fx.gateway.commerce = self.commerce

    def call(self, params=None, token=None):
        return self.commerce.consumer(token or self.token, 'shop1', 'project_messages',
                                      {} if params is None else params)

    def seed(self, count, *, start=0, legacy=False):
        # Original encrypted schema and evidence writer, without irrelevant
        # submission rate limits. Deliberate tied times exercise the full key.
        with self.c.tx():
            for n in range(start, start+count):
                mid = 'legacy_' + str(n) if legacy else 'm_' + format(n, '032x')
                self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',
                    (mid, 'project1', self.fx.uid1, 'WEB', self.c.encrypt(('synthetic '+str(n)).encode(), mid),
                     'ARCHIVED', 'private-provider-reference', self.c.now()+n//20))
                append(self.c, mid, legacy=legacy)
        return mid if count else None

    def test_201_original_submissions_all_accessible_once_in_original_order(self):
        for n in range(201):
            if n and n % 20 == 0: self.fx.stage.now += 61
            receipt = self.commerce.consumer(self.token, 'shop1', 'project_feedback', {'message': 'synthetic '+str(n)})
        original_first = self.c.messages(self.fx.uid1, 'project1')
        records, cursor, sizes = [], '', []
        while True:
            page = self.call({'after_id': cursor})
            records.extend(page['records']); sizes.append(len(page['records']))
            self.assertEqual(page['source'], 'ORIGINAL_CENTER_ARCHIVE')
            self.assertIs(page['provider_reply_verified'], False)
            if not page['has_more']:
                self.assertIsNone(page['next_cursor']); break
            self.assertNotEqual(page['next_cursor'], cursor); cursor = page['next_cursor']
        self.assertEqual(sizes, [50, 50, 50, 50, 1])
        self.assertEqual(records[:200], original_first)
        self.assertEqual(len({r['id'] for r in records}), 201)
        self.assertIn(receipt['id'], {r['id'] for r in records})
        self.assertEqual([(r['created'],r['id']) for r in records], sorted((r['created'],r['id']) for r in records))
        self.assertEqual(self.c.check_integrity()['integrity'], 'PASS')

    def test_empty_legacy_request_and_exhausted_cursor(self):
        expected = dict(records=[],has_more=False,next_cursor=None,source='ORIGINAL_CENTER_ARCHIVE',provider_reply_verified=False)
        self.assertEqual(self.call(), expected)
        self.seed(51)
        self.assertEqual(self.call(), self.call({'after_id': ''}))
        self.assertEqual(self.call({'after_id': json.dumps([2**53-1,'zz'])}), expected)
        self.assertEqual(self.call({'after_id': json.dumps([self.c.now()+2,'m_zz'])}), expected)

    def test_cursor_survives_reopen_and_reads_new_records_after_key(self):
        self.seed(51)
        first = self.call(); cursor = first['next_cursor']
        self.seed(3,start=51)
        self.fx.reopen(); self.c=self.fx.center; self.configure()
        second = self.call({'after_id':cursor})
        self.assertEqual(len(second['records']),4)
        self.assertEqual(len({r['id'] for r in first['records']+second['records']}),54)
        self.assertEqual(second,self.call({'after_id':cursor}))

    def test_legacy_known_project_keeps_original_projection_and_unknown_provenance(self):
        self.seed(3,legacy=True)
        before = [tuple(row) for row in self.c.db.execute('SELECT * FROM messages ORDER BY id')]
        self.assertEqual(self.call()['records'], self.c.messages(self.fx.uid1,'project1'))
        for record in self.call()['records']:
            self.assertEqual(set(record), {'id','channel','body','status','created'})
            self.assertNotIn('private-provider-reference', json.dumps(record))
        _, records, _ = authorized_records(self.c,self.fx.uid1,'project1')
        self.assertTrue(all(r['evidence']['provenance']=='LEGACY_BACKFILL_UNKNOWN_CONTEXT' for r in records))
        self.assertTrue(all(r['evidence']['sender_role'] is None for r in records))
        self.assertEqual(before,[tuple(row) for row in self.c.db.execute('SELECT * FROM messages ORDER BY id')])

    def test_wrong_actor_cannot_select_project_and_live_revocation_blocks_continuation(self):
        self.seed(51); cursor=self.call()['next_cursor']
        for key in ('user_id','project','tenant','limit','raw','verified'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.call({'after_id':cursor,key:'other'})
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError): self.call({'after_id':cursor})
        with self.assertRaises(PermissionError): read_page(self.c,self.fx.uid1,'project1',{'after_id':cursor})

    def test_orphan_legacy_identity_remains_unknown_after_project_id_reappears(self):
        # Reproduce the original migration's orphan case on synthetic SQLite:
        # historical absence must not be blessed by a later project assignment.
        with self.c.tx():
            original=tuple(self.c.db.execute("SELECT * FROM projects WHERE id='project1'").fetchone())
            self.c.db.execute("DELETE FROM projects WHERE id='project1'")
            self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',
                ('legacy_orphan','project1',self.fx.uid1,'WEB',self.c.encrypt(b'unknown origin','legacy_orphan'),
                 'ARCHIVED',None,self.c.now()))
            evidence=append(self.c,'legacy_orphan',legacy=True)
            self.assertIsNone(evidence['tenant_id']);self.assertIsNone(evidence['customer_id'])
            self.c.db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?)',original)
        with self.assertRaisesRegex(PermissionError,'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):self.call()
        with self.assertRaisesRegex(PermissionError,'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            self.call({'after_id':json.dumps([2**53-1,'zz'])})

    def test_current_member_can_read_shared_project_but_unrelated_account_cannot(self):
        self.seed(51); cursor=self.call()['next_cursor']
        second=self.fx.token('second','openid2')
        self.assertEqual(self.call({'after_id':cursor},second),self.call({'after_id':cursor}))
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid2,))
        with self.assertRaises(PermissionError): self.call({'after_id':cursor},second)

    def test_session_logout_and_wechat_unlink_block_even_empty_page(self):
        self.seed(1)
        cursor=json.dumps([2**53-1,'zz'])
        self.c.logout(self.token)
        with self.assertRaises(PermissionError): self.call({'after_id':cursor})
        token=self.fx.token('newcode')
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI'")
        with self.assertRaises(PermissionError): self.call({'after_id':cursor},token)

    def test_identity_drift_and_corrupt_out_of_page_evidence_never_silently_skip(self):
        self.seed(51); cursor=self.call()['next_cursor']
        self.c.db.execute("UPDATE projects SET customer='reassigned' WHERE id='project1'")
        with self.assertRaisesRegex(PermissionError,'MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT'):
            self.call({'after_id':cursor})
        self.c.db.execute("UPDATE projects SET customer='customer1' WHERE id='project1'")
        first=self.c.db.execute('SELECT id FROM messages ORDER BY created,id LIMIT 1').fetchone()[0]
        self.c.db.execute('UPDATE messages SET payload=? WHERE id=?',(self.c.encrypt(b'changed',first),first))
        with self.assertRaisesRegex(PermissionError,'MESSAGE_CONTENT_INTEGRITY'):
            self.call({'after_id':cursor})
        with self.assertRaises(PermissionError): self.call({'after_id':json.dumps([2**53-1,'zz'])})

    def test_missing_evidence_is_not_backfilled_or_read(self):
        self.c.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',
            ('untracked','project1',self.fx.uid1,'WEB',self.c.encrypt(b'unknown','untracked'),'ARCHIVED',None,self.c.now()))
        with self.assertRaisesRegex(PermissionError,'MESSAGE_EVIDENCE_MISSING'):self.call()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM message_evidence').fetchone()[0],0)

    def test_invalid_cursor_is_rejected_without_sql_or_limit_override(self):
        for value in (None, True, 4, [], {}, 'x'*161, 'not json', '{}', 'null', '[]', '[true,"m"]',
                      '[1.2,"m"]', '[1,"m","x"]', '[1,"a/b"]', '[9007199254740992,"m"]', '[1,"x\\n"]'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'INVALID_PROJECT_MESSAGE_CURSOR'):
                self.call({'after_id':value})
        for params in (None, [], 'x'):
            with self.assertRaises(ValueError):read_page(self.c,self.fx.uid1,'project1',params)

    def test_original_history_safety_bound_remains_enforced(self):
        # Test the original guard without forging 10,001 evidence records.
        from unittest.mock import patch
        self.seed(2)
        with patch('scripts.pr122_customer_evidence.MAX_HISTORY',1):
            with self.assertRaisesRegex(RuntimeError,'BOUNDED_HISTORY_REQUIRES_OPERATOR'):self.call()

    def test_original_mini_http_routes_page_and_returns_no_raw_evidence(self):
        self.seed(51); first=self.call()
        server=serve(self.fx.gateway,commerce=self.commerce)
        try:
            def send():
                request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/api',
                    data=json.dumps(dict(scene='shop1',operation='commerce.project_messages',params={'after_id':first['next_cursor']})).encode(),
                    headers={'Content-Type':'application/json','X-Community-Session':self.token})
                with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(send);server.handle_request();result=pending.result()
            self.assertIs(result['payment_enabled'],False)
            self.assertEqual(len(result['result']['records']),1)
            self.assertNotIn('provider_ref',json.dumps(result));self.assertNotIn('payload',json.dumps(result))
        finally:server.server_close()

    def test_pinned_core_unchanged(self):
        path=Path(__file__).resolve().parents[1]/'scripts/pr122_customer_core.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),fixtures.PINNED_CORE_SHA256)


if __name__=='__main__':unittest.main()
