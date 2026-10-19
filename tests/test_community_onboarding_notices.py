"""Private in-app admission results on original owner and notification storage."""
import json
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixtures


class OnboardingNotices(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.bind','socket.socket.connect'):
            guard=patch(name,side_effect=AssertionError('NO_NETWORK_OR_LISTENER'));guard.start();self.addCleanup(guard.stop)
        self.fx=fixtures.MerchantAdmissionJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.c=self.fx.fx.center
    def notices(self,app,after=''):
        return self.fx.call('notices',dict(application=app['application'],after_id=after))
    def mark(self,app,key):
        return self.fx.call('notice_read',dict(application=app['application'],notice_id=key))
    def corrected(self):return self.fx.review(self.fx.complete(),'CORRECTION','PRIVATE_CORRECTION_DETAIL')

    def test_overall_review_creates_private_original_in_app_notice(self):
        app=self.corrected()
        rows=self.c.db.execute("SELECT subject_idx FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND user_id=? AND project=?",(self.fx.fx.uid1,app['application'])).fetchall()
        self.assertEqual(len(rows),1)
        result=self.notices(app);record=result['records'][0]
        self.assertEqual(record['application'],app['application']);self.assertEqual(record['revision'],app['revision'])
        self.assertEqual(record['status'],'CORRECTION_REQUIRED');self.assertFalse(record['read'])
        self.assertNotIn('PRIVATE_CORRECTION_DETAIL',json.dumps(result));self.assertNotIn('object_id',json.dumps(result))
        self.assertEqual(result['next_cursor'],None);self.assertFalse(result['has_more'])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM messages').fetchone()[0],0)

    def test_existing_account_without_crm_project_can_read_and_mark_own_result(self):
        app=self.corrected()
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,));self.c.db.commit()
        record=self.notices(app)['records'][0]
        self.assertTrue(self.mark(app,record['id'])['read']);self.assertTrue(self.notices(app)['records'][0]['read'])
        self.assertTrue(self.mark(app,record['id'])['read'])

    def test_results_use_distinct_original_versions_and_replay_is_not_notified_again(self):
        app=self.corrected();app=self.fx.draft(app);app=self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
        rejected=self.fx.review(app,'REJECT','PRIVATE_REJECTION')
        app=self.fx.review(rejected,'REOPEN','PRIVATE_REOPEN')
        app=self.fx.draft(app);app=self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
        app=self.fx.review(app,'APPROVE')
        records=self.notices(app)['records'];self.assertEqual(len(records),4)
        self.assertEqual({r['event'] for r in records},{'CORRECTION','REJECT','REOPEN','APPROVE'})
        self.assertEqual(len({r['id'] for r in records}),4)
        with self.assertRaises(ValueError):self.fx.review(rejected,'REOPEN','stale replay')
        self.assertEqual(self.notices(app)['records'],records)
        self.assertNotIn('PRIVATE_',json.dumps(records));self.assertFalse(app['payment_enabled'])

    def test_other_account_and_other_application_cannot_read_or_mark_notice(self):
        app=self.corrected();other=self.corrected();key=self.notices(app)['records'][0]['id']
        for operation,params in [('notices',dict(application=app['application'],after_id='')),
                                 ('notice_read',dict(application=app['application'],notice_id=key))]:
            with self.assertRaises(PermissionError):self.fx.call(operation,params,True)
        with self.assertRaises(PermissionError):self.mark(other,key)
        self.assertEqual(len(self.notices(other)['records']),1)
        self.assertNotEqual(self.notices(other)['records'][0]['id'],key)

    def test_original_application_access_revocation_and_session_epoch_are_live(self):
        app=self.corrected();key=self.notices(app)['records'][0]['id']
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ONBOARDING' AND project=?",(app['application'],));self.c.db.commit()
        with self.assertRaises(PermissionError):self.notices(app)
        with self.assertRaises(PermissionError):self.mark(app,key)
        self.c.db.execute("UPDATE links SET active=1 WHERE channel='COMMUNITY_ONBOARDING' AND project=?",(app['application'],))
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.fx.uid1,));self.c.db.commit()
        with self.assertRaises(PermissionError):self.notices(app)

    def test_csrf_cursor_and_browser_authority_fields_cannot_expand_access(self):
        app=self.corrected();web=self.fx.applicant
        for cursor in (None,True,-1,'not-a-cursor'):
            with self.assertRaises(ValueError):self.notices(app,cursor)
        for csrf in ('','wrong'):
            with self.assertRaises(PermissionError):self.fx.service.dispatch(web['token'],csrf,dict(operation='notices',params=dict(application=app['application'],after_id='')))
        with self.assertRaises(ValueError):self.fx.call('notices',dict(application=app['application'],after_id='',user_id=self.fx.fx.uid1))
        with self.assertRaises(ValueError):self.mark(app,'bad')

    def test_notice_failure_rolls_back_review_history_state_and_original_audit(self):
        from scripts.community_onboarding_history import ITEM
        app=self.fx.complete()
        def snapshot():
            return tuple(tuple(tuple(row) for row in self.c.db.execute(query,args)) for query,args in [
                ('SELECT * FROM onboarding WHERE application=?',(app['application'],)),
                ('SELECT * FROM onboarding_events WHERE application=?',(app['application'],)),
                ('SELECT * FROM versions WHERE project=? AND item=?',(app['application'],ITEM)),
                ('SELECT * FROM audit',()),
                ("SELECT * FROM links WHERE channel='COMMUNITY_NOTICE_V1'",())])
        before=snapshot()
        with patch('scripts.community_onboarding_notices.notify',side_effect=OSError('notification write unavailable')):
            with self.assertRaises(OSError):self.fx.review(app,'CORRECTION','cannot lose this result')
        self.assertEqual(snapshot(),before)
        self.assertEqual(self.fx.call('read',dict(application=app['application']))['status'],'SUBMITTED')

    def test_fifty_one_notices_page_only_authorized_application_without_loss_or_duplicate(self):
        app=self.fx.complete()
        for n in range(51):
            if n and n%20==0:
                self.fx.fx.stage.now+=3601
                self.fx.applicant=self.c.login('one@example.org','FixturePassword123!')
                self.fx.reviewer=self.c.login('two@example.org','FixturePassword123!')
            app=self.fx.review(app,'CORRECTION','fixture result '+str(n))
            if n<50:
                app=self.fx.draft(app);app=self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
        other=self.corrected();first=self.notices(app);second=self.notices(app,first['next_cursor'])
        self.assertEqual((len(first['records']),first['has_more']),(50,True))
        self.assertEqual((len(second['records']),second['has_more'],second['next_cursor']),(1,False,None))
        ids=[r['id'] for r in first['records']+second['records']]
        self.assertEqual(len(set(ids)),51);self.assertEqual(ids,sorted(ids))
        self.assertNotIn(self.notices(other)['records'][0]['id'],ids)

    def test_notice_payload_application_event_and_private_message_are_bound(self):
        app=self.corrected();record=self.notices(app)['records'][0];key=record['id']
        row=self.c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=?",(key,)).fetchone()
        original=json.loads(self.c.decrypt(row[0],'community-notice:'+key))
        for change in ({'reference':'ma_'+'b'*32+':9'},{'kind':'REFUND_RESULT'},{'message':'PRIVATE_UNRELATED_DETAIL'},{'read':1},{'created_at':True}):
            self.c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=?",(self.c.encrypt(json.dumps(dict(original,**change)).encode(),'community-notice:'+key),key));self.c.db.commit()
            with self.assertRaises(PermissionError):self.notices(app)
            with self.assertRaises(PermissionError):self.mark(app,key)

    def test_revocation_during_notice_decrypt_prevents_read_or_mark_projection(self):
        app=self.corrected();record=self.notices(app)['records'][0];decrypt=self.c.decrypt
        def revoked(payload,aad):
            value=decrypt(payload,aad)
            if aad=='community-notice:'+record['id']:
                self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ONBOARDING' AND project=?",(app['application'],))
            return value
        with patch.object(self.c,'decrypt',side_effect=revoked):
            with self.assertRaises(PermissionError):self.notices(app)
            with self.assertRaises(PermissionError):self.mark(app,record['id'])
        self.assertFalse(self.notices(app)['records'][0]['read'])

    def test_legacy_results_are_not_retroactively_invented_and_restart_preserves_read(self):
        app=self.corrected();record=self.notices(app)['records'][0];self.mark(app,record['id'])
        self.fx.fx.reopen();self.c=self.fx.fx.center
        from scripts.community_merchant_onboarding import MerchantOnboarding
        self.fx.service=MerchantOnboarding(self.c,{self.fx.fx.uid2:'project1'})
        self.assertTrue(self.notices(app)['records'][0]['read'])
        self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND project=?",(app['application'],));self.c.db.commit()
        self.assertEqual(self.notices(app)['records'],[])
        self.assertEqual(self.fx.call('history',dict(application=app['application'],after_revision=0))['records'][-1]['event'],'CORRECTION')


if __name__=='__main__':unittest.main()
