"""Original admission timeline, immutable evidence and current Center authority."""
import json
import sqlite3
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixtures
from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_onboarding_history import ITEM


class AdmissionHistory(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.connect','socket.socket.bind'):
            guard=patch(name,side_effect=AssertionError('NO_NETWORK_OR_LISTENER'));guard.start();self.addCleanup(guard.stop)
        self.fx=fixtures.MerchantAdmissionJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.c=self.fx.fx.center

    def history(self,app,after=0,review=False):
        return self.fx.call('review_history' if review else 'history',dict(application=app['application'],after_revision=after),review)

    def test_correction_reason_and_original_material_versions_survive_resubmit(self):
        app=self.fx.complete();app=self.fx.review(app,'CORRECTION','FIRST_CORRECTION_REASON_FIXTURE')
        before=self.history(app);correction=before['records'][-1]
        version=next(m['version'] for m in correction['materials'] if m['kind']=='storefront_photo')
        app=self.fx.upload(app,'storefront_photo',b'%PDF-new clear fixture')
        app=self.fx.draft(app);app=self.fx.call('submit',dict(application=app['application'],revision=app['revision']))
        result=self.history(app);saved=next(r for r in result['records'] if r['event']=='CORRECTION')
        self.assertEqual(saved,correction);self.assertEqual(saved['note'],'FIRST_CORRECTION_REASON_FIXTURE')
        self.assertEqual(saved['actor'],self.fx.fx.uid2);self.assertEqual(saved['occurred_at'],self.c.now())
        latest=next(m['version'] for m in result['records'][-1]['materials'] if m['kind']=='storefront_photo')
        self.assertNotEqual(latest,version);self.assertEqual(len(result['material_versions']),len(before['material_versions'])+1)
        self.assertEqual(result['records'][-1]['previous_revision'],app['revision']-1)
        self.assertNotIn('object_id',json.dumps(result));self.assertNotIn('content_base64',json.dumps(result))
        self.assertEqual(self.history(app,review=True),result)
        self.assertEqual(self.c.check_integrity()['integrity'],'PASS')

    def test_material_review_preserves_exact_material_and_decision(self):
        app=self.fx.complete()
        app=self.fx.call('review_material',dict(application=app['application'],revision=app['revision'],kind='business_license',decision='NEEDS_CORRECTION',note='CLEARER_LICENSE_REQUIRED'),True)
        row=self.history(app)['records'][-1]
        self.assertEqual((row['event'],row['material_kind'],row['decision'],row['note']),('REVIEW_MATERIAL','business_license','NEEDS_CORRECTION','CLEARER_LICENSE_REQUIRED'))
        material=next(m for m in row['materials'] if m['kind']=='business_license')
        self.assertEqual(material['review'],dict(decision='NEEDS_CORRECTION',note='CLEARER_LICENSE_REQUIRED',reviewer=self.fx.fx.uid2))

    def test_original_account_without_project_can_read_own_timeline_and_reopen(self):
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,));self.c.db.commit()
        app=self.fx.upload(self.fx.draft(),'business_license');expected=self.history(app)
        self.fx.fx.reopen();self.c=self.fx.fx.center;self.fx.service=MerchantOnboarding(self.c,{self.fx.fx.uid2:'project1'})
        self.assertEqual(self.history(app),expected)

    def test_application_owner_review_mapping_and_current_reviewer_role_are_required(self):
        app=self.fx.draft();web=self.fx.reviewer
        with self.assertRaises(PermissionError):
            self.fx.service.dispatch(web['token'],web['csrf'],dict(operation='history',params=dict(application=app['application'],after_revision=0)))
        with self.assertRaises(PermissionError):self.fx.call('review_history',dict(application=app['application'],after_revision=0))
        self.assertEqual(len(self.history(app,review=True)['records']),1)
        self.fx.service.reviewers.clear()
        with self.assertRaises(PermissionError):self.history(app,review=True)
        self.fx.service.reviewers[self.fx.fx.uid2]='project1'
        self.c.db.execute("UPDATE members SET role='OWNER' WHERE user_id=?",(self.fx.fx.uid2,));self.c.db.commit()
        with self.assertRaises(PermissionError):self.history(app,review=True)

    def test_csrf_epoch_and_strict_cursor_each_page(self):
        app=self.fx.draft();web=self.fx.applicant
        for cursor in [True,-1,'0',None,[]]:
            with self.assertRaises(ValueError):self.history(app,cursor)
        for csrf in ['', 'wrong']:
            with self.assertRaises(PermissionError):self.fx.service.dispatch(web['token'],csrf,dict(operation='history',params=dict(application=app['application'],after_revision=0)))
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.fx.uid1,));self.c.db.commit()
        with self.assertRaises(PermissionError):self.history(app)

    def test_fifty_one_events_page_only_this_application_without_gaps_or_duplicates(self):
        app=self.fx.draft()
        for _ in range(50):app=self.fx.draft(app)
        other=self.fx.draft()
        first=self.history(app);second=self.history(app,first['next_revision'])
        self.assertEqual([r['revision'] for r in first['records']+second['records']],list(range(1,52)))
        self.assertEqual((len(first['records']),first['has_more'],first['next_revision']),(50,True,50))
        self.assertEqual((len(second['records']),second['has_more'],second['next_revision']),(1,False,None))
        self.assertEqual(len(self.history(other)['records']),1)

    def test_future_details_are_encrypted_and_original_versions_triggers_are_append_only(self):
        app=self.fx.review(self.fx.complete(),'CORRECTION','PRIVATE_HISTORY_REASON')
        rows=self.c.db.execute('SELECT id,payload FROM versions WHERE project=? AND item=?',(app['application'],ITEM)).fetchall()
        self.assertTrue(rows)
        for row in rows:self.assertNotIn(b'PRIVATE_HISTORY_REASON',bytes(row['payload']))
        for sql in ('UPDATE versions SET kind=kind WHERE id=?','DELETE FROM versions WHERE id=?'):
            with self.assertRaisesRegex(sqlite3.IntegrityError,'APPEND_ONLY'):self.c.db.execute(sql,(rows[0]['id'],))
            self.c.db.rollback()
        self.assertEqual(self.history(app)['records'][-1]['note'],'PRIVATE_HISTORY_REASON')

    def test_snapshot_failure_rolls_back_workflow_event_audit_and_metadata(self):
        app=self.fx.draft();before=self.history(app)
        counts={table:self.c.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ['versions','audit','onboarding_events']}
        with patch('scripts.community_onboarding_history.append',side_effect=OSError('synthetic history write failed')):
            with self.assertRaises(OSError):self.fx.draft(app)
        self.assertEqual(self.history(app),before)
        for table,count in counts.items():self.assertEqual(self.c.db.execute('SELECT count(*) FROM '+table).fetchone()[0],count)
        self.assertEqual(self.fx.call('read',dict(application=app['application']))['revision'],app['revision'])

    def test_stale_write_does_not_duplicate_timeline(self):
        app=self.fx.draft();current=self.fx.draft(app);before=self.history(current)
        with self.assertRaises(ValueError):self.fx.draft(app)
        self.assertEqual(self.history(current),before)

    def test_legacy_event_uses_unique_original_audit_time_without_inventing_reason_or_material_join(self):
        with patch('scripts.community_onboarding_history.append'):
            app=self.fx.review(self.fx.complete(),'CORRECTION','LEGACY_REASON_NOT_IN_EVENT')
        result=self.history(app);row=result['records'][-1]
        self.assertEqual(row['event'],'CORRECTION');self.assertEqual(row['occurred_at'],self.c.now())
        self.assertEqual(row['evidence'],'LEGACY_EVENT_ONLY');self.assertIsNone(row['note']);self.assertIsNone(row['materials'])
        self.assertEqual(len(result['material_versions']),len(app['required_materials']))
        self.assertNotIn('LEGACY_REASON_NOT_IN_EVENT',json.dumps(result))
        with self.c.tx():self.c.audit(app['application'],self.fx.fx.uid2,'MERCHANT_ONBOARDING_REVIEW',str(app['revision']))
        self.assertIsNone(self.history(app)['records'][-1]['occurred_at'])

    def test_legacy_without_matching_audit_time_does_not_borrow_nearby_audit(self):
        with patch('scripts.community_onboarding_history.append'),patch.object(self.c,'audit'):
            app=self.fx.draft()
        with self.c.tx():self.c.audit(app['application'],self.fx.fx.uid1,'MERCHANT_ONBOARDING_SAVE','99')
        row=self.history(app)['records'][0]
        self.assertIsNone(row['occurred_at']);self.assertEqual(row['revision'],1)

    def test_reviewer_revoked_during_decrypt_cannot_receive_timeline(self):
        app=self.fx.draft();decrypt=self.c.decrypt
        def revoke(raw,aad):
            value=decrypt(raw,aad)
            if aad.startswith('v_'):self.fx.service.reviewers.clear()
            return value
        with patch.object(self.c,'decrypt',side_effect=revoke):
            with self.assertRaises(PermissionError):self.history(app,review=True)

    def test_snapshot_cannot_be_rebound_to_another_application_or_leak_internal_object_fields(self):
        app=self.fx.upload(self.fx.draft(),'business_license');decrypt=self.c.decrypt
        for mode in ['application','material']:
            def tamper(raw,aad):
                value=decrypt(raw,aad)
                if aad.startswith('v_'):
                    data=json.loads(value)
                    if data.get('format')==1:
                        if mode=='application':data['application']='other-application'
                        elif data['materials']:data['materials'][0]['object_id']='private-object-id'
                        return json.dumps(data).encode()
                return value
            with patch.object(self.c,'decrypt',side_effect=tamper),self.assertRaises((PermissionError,ValueError)):self.history(app)


if __name__=='__main__':unittest.main()
