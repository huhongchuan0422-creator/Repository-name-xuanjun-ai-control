"""Directory pagination through original encrypted Center and live project ACL.

All accounts and community records are local synthetic fixtures. No provider IO.
"""
import unittest

import test_community_mini_center_identity as fixtures
from scripts.community_center_communities import CHANNEL, CenterCommunities


class CommunityDirectoryPagination(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterComposition()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.c = self.fx.center
        self.web = self.c.login('one@example.org', 'FixturePassword123!')
        self.other = self.c.login('two@example.org', 'FixturePassword123!')
        self.grants = {
            'community': dict(user_id=self.fx.uid1, project='project1',
                              tenant='tenant1', role='COMMUNITY_ADMIN'),
            'other': dict(user_id=self.fx.uid2, project='project1',
                          tenant='tenant1', role='COMMUNITY_ADMIN'),
            'reviewer': dict(user_id=self.fx.uid2, project='project1',
                             tenant='tenant1', role='PLATFORM_REVIEWER'),
        }
        self.directory = CenterCommunities(self.c, self.grants)
        # Seed with the production encrypted writer, bypassing only registration
        # rate limits. Authentication, pagination, ACL and auditing remain real.
        with self.c.tx():
            self.owned = self.seed(self.grants['community'], 61, 0)
            self.foreign = self.seed(self.grants['other'], 3, 100)

    def seed(self, grant, count, offset):
        ids = set()
        for i in range(offset, offset + count):
            record = dict(id='co_' + format(i, '032x'), tenant=grant['tenant'],
                          owner=grant['user_id'], name='Synthetic community ' + str(i),
                          description='Offline fixture', contact='private fixture',
                          state='DRAFT', version=1, opinion='', updated_at=self.c.now())
            self.directory.write(grant, record)
            ids.add(record['id'])
        return ids

    def call(self, params=None, workspace='community', web=None, csrf=None,
             operation='mine'):
        web = self.web if web is None else web
        return self.directory.dispatch(
            web['token'], web['csrf'] if csrf is None else csrf,
            dict(workspace=workspace, operation=operation,
                 params={} if params is None else params))

    def test_legacy_empty_params_and_explicit_first_cursor_match(self):
        self.assertEqual(self.call(), self.call({'after_id': ''}))

    def test_all_pages_are_bounded_ordered_complete_and_without_duplicates(self):
        first = self.call()
        self.assertEqual(len(first['records']), 50)
        self.assertTrue(first['has_more'])
        expected = sorted(self.owned, key=lambda cid: self.directory.key('tenant1', cid))
        self.assertEqual([r['id'] for r in first['records']], expected[:50])
        self.assertEqual(first['next_cursor'], self.directory.key('tenant1', expected[49]))
        second = self.call({'after_id': first['next_cursor']})
        self.assertEqual([r['id'] for r in second['records']], expected[50:])
        self.assertFalse(second['has_more'])
        self.assertIsNone(second['next_cursor'])
        ids = [r['id'] for r in first['records'] + second['records']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), self.owned)
        self.assertEqual(second, self.call({'after_id': first['next_cursor']}))

    def test_exhausted_cursor_and_empty_owner_have_no_next_page(self):
        self.assertEqual(self.call({'after_id': 'f' * 64}),
                         dict(records=[], has_more=False, next_cursor=None))
        with self.c.tx():
            self.c.db.execute('UPDATE links SET active=0 WHERE channel=? AND user_id=?',
                              (CHANNEL, self.fx.uid2))
        self.assertEqual(self.call(workspace='other', web=self.other),
                         dict(records=[], has_more=False, next_cursor=None))

    def test_owner_and_workspace_isolation_on_continuation(self):
        cursor = self.call()['next_cursor']
        own = self.call(workspace='other', web=self.other)
        self.assertEqual({r['id'] for r in own['records']}, self.foreign)
        second = self.call({'after_id': cursor}, workspace='other', web=self.other)
        self.assertTrue({r['id'] for r in second['records']} <= self.foreign)
        with self.assertRaises(PermissionError):
            self.call({'after_id': cursor}, web=self.other)
        with self.assertRaises(PermissionError):
            self.call({'after_id': cursor}, workspace='other')

    def test_invalid_cursors_are_rejected_by_cursor_validator(self):
        for cursor in (None, True, 7, [], {}, 'x' * 64, 'A' * 64, 'a' * 63,
                       'a' * 65, "' OR 1=1", 'a' * 64 + '\n'):
            with self.subTest(cursor=cursor):
                with self.assertRaisesRegex(ValueError, 'INVALID_COMMUNITY_CURSOR'):
                    self.call({'after_id': cursor})

    def test_extra_fields_cannot_change_owner_scope_or_operation_contracts(self):
        for field in ('user_id', 'owner', 'tenant', 'project', 'status', 'role', 'limit'):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'INVALID_COMMUNITY_FIELDS'):
                    self.call({'after_id': '', field: 'foreign'})
        for params in ({}, {'after_id': ''}, {'status': 'ALL'}):
            with self.assertRaisesRegex(ValueError, 'INVALID_COMMUNITY_FIELDS'):
                self.call(params, operation='list', workspace='reviewer', web=self.other)

    def test_session_and_csrf_are_rechecked_on_continuation(self):
        params = {'after_id': self.call()['next_cursor']}
        for csrf in ('', 'wrong'):
            with self.assertRaises(PermissionError):
                self.call(params, csrf=csrf)
        self.c.logout(self.web['token'])
        with self.assertRaises(PermissionError):
            self.call(params)

    def test_membership_revocation_is_effective_on_continuation(self):
        params = {'after_id': self.call()['next_cursor']}
        with self.c.tx():
            self.c.db.execute('UPDATE members SET active=0 WHERE project=? AND user_id=?',
                              ('project1', self.fx.uid1))
        with self.assertRaises(PermissionError):
            self.call(params)

    def test_account_epoch_revocation_is_effective_on_continuation(self):
        params = {'after_id': self.call()['next_cursor']}
        with self.c.tx():
            self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',
                              (self.fx.uid1,))
        with self.assertRaises(PermissionError):
            self.call(params)

    def test_exact_page_boundary_and_reviewer_contract_are_preserved(self):
        tail = sorted(self.owned, key=lambda cid: self.directory.key('tenant1', cid))[50:]
        with self.c.tx():
            for cid in tail:
                self.c.db.execute('UPDATE links SET active=0 WHERE channel=? AND subject_idx=?',
                                  (CHANNEL, self.directory.key('tenant1', cid)))
        page = self.call({'after_id': ''})
        self.assertEqual(len(page['records']), 50)
        self.assertFalse(page['has_more'])
        self.assertIsNone(page['next_cursor'])
        first = self.call({'after_id': '', 'status': 'ALL'}, operation='list',
                          workspace='reviewer', web=self.other)
        second = self.call({'after_id': first['next_cursor'], 'status': 'ALL'},
                           operation='list', workspace='reviewer', web=self.other)
        self.assertEqual(len(first['records']), 50)
        self.assertEqual(len(second['records']), 3)
        self.assertFalse(second['has_more'])
        with self.assertRaises(PermissionError):
            self.call({'after_id': '', 'status': 'ALL'}, operation='list')

    def test_revoked_records_are_excluded_without_changing_storage_or_acl(self):
        first = self.call()
        tail = sorted(self.owned, key=lambda cid: self.directory.key('tenant1', cid))[50:]
        with self.c.tx():
            self.c.db.execute('UPDATE links SET active=0 WHERE channel=? AND subject_idx=?',
                              (CHANNEL, self.directory.key('tenant1', tail[0])))
        schema = self.c.db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()
        second = self.call({'after_id': first['next_cursor']})
        self.assertEqual([r['id'] for r in second['records']], tail[1:])
        self.assertEqual(schema, self.c.db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall())
        self.assertEqual(self.c.check_integrity()['integrity'], 'PASS')
        row = self.c.db.execute('SELECT payload FROM links WHERE channel=? LIMIT 1', (CHANNEL,)).fetchone()
        self.assertNotIn(b'private fixture', bytes(row[0]))


if __name__ == '__main__':
    unittest.main()
