"""Owner-approved rejected application reopening, on original reviewer authority."""
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixtures


class ReopenAdmission(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.connect','socket.socket.bind'):
            guard=patch(name,side_effect=AssertionError('NO_NETWORK_OR_LISTENER'));guard.start();self.addCleanup(guard.stop)
        self.fx=fixtures.MerchantAdmissionJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.c=self.fx.fx.center
    def rejected(self):return self.fx.review(self.fx.complete(),'REJECT','ORIGINAL_REJECTION_REASON')
    def history(self,app):return self.fx.call('history',dict(application=app['application'],after_revision=0))['records']

    def test_reviewer_reopens_same_application_for_correction_then_independent_review(self):
        rejected=self.rejected()
        with self.assertRaises(ValueError):self.fx.draft(rejected)
        reopened=self.fx.review(rejected,'REOPEN','REOPEN_FOR_CORRECTION_REASON')
        self.assertEqual(reopened['application'],rejected['application']);self.assertEqual(reopened['status'],'CORRECTION_REQUIRED')
        with self.assertRaises(ValueError):self.fx.call('submit',dict(application=reopened['application'],revision=reopened['revision']))
        changed=self.fx.draft(reopened);submitted=self.fx.call('submit',dict(application=changed['application'],revision=changed['revision']))
        with self.assertRaisesRegex(ValueError,'MATERIAL_REVIEW_REQUIRED'):
            self.fx.call('review',dict(application=submitted['application'],revision=submitted['revision'],action='APPROVE',note='new overall review required'),True)
        approved=self.fx.review(submitted,'APPROVE');self.assertEqual(approved['status'],'APPROVED')
        history=self.history(approved)
        self.assertEqual([r['note'] for r in history if r['event'] in ('REJECT','REOPEN')],['ORIGINAL_REJECTION_REASON','REOPEN_FOR_CORRECTION_REASON'])
        self.assertEqual([r['status_after'] for r in history if r['event']=='REOPEN'],['CORRECTION_REQUIRED'])
        self.assertFalse(approved['payment_enabled']);self.assertEqual(self.c.check_integrity()['integrity'],'PASS')

    def test_applicant_cannot_unlock_even_if_registered_reviewer_and_original_reviewer_revocation_applies(self):
        app=self.rejected()
        with self.assertRaises(PermissionError):self.fx.call('review',dict(application=app['application'],revision=app['revision'],action='REOPEN',note='cannot self unlock'))
        self.c.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.fx.fx.uid1,));self.c.db.commit();self.fx.service.reviewers[self.fx.fx.uid1]='project1'
        with self.assertRaises(PermissionError):self.fx.call('review',dict(application=app['application'],revision=app['revision'],action='REOPEN',note='still cannot self unlock'))
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid2,));self.c.db.commit()
        with self.assertRaises(PermissionError):self.fx.review(app,'REOPEN','reviewer revoked')
        self.assertEqual(self.fx.call('read',dict(application=app['application']))['status'],'REJECTED')

    def test_reason_is_required_and_only_rejected_state_can_be_reopened(self):
        draft=self.fx.draft()
        with self.assertRaises(ValueError):self.fx.review(draft,'REOPEN','wrong state')
        app=self.rejected();before=self.history(app)
        for note in ['', '   ']:
            with self.assertRaises(ValueError):self.fx.review(app,'REOPEN',note)
        self.assertEqual(self.history(app),before)
        reopened=self.fx.review(app,'REOPEN','valid reason')
        with self.assertRaises(ValueError):self.fx.review(app,'REOPEN','stale replay')
        with self.assertRaises(ValueError):self.fx.review(reopened,'REOPEN','already open')

    def test_reopening_invalidates_current_material_acceptance_without_erasing_prior_review(self):
        app=self.fx.complete()
        app=self.fx.call('review_material',dict(application=app['application'],revision=app['revision'],kind='business_license',decision='ACCEPTED',note='OLD_ACCEPTANCE'),True)
        app=self.fx.review(app,'REJECT','OTHER_REQUIREMENTS_REJECTED')
        app=self.fx.review(app,'REOPEN','new independent review')
        self.assertTrue(all(record['review']=='PENDING' for record in app['materials'].values()))
        row=next(r for r in self.history(app) if r['event']=='REVIEW_MATERIAL')
        self.assertEqual(row['note'],'OLD_ACCEPTANCE');self.assertEqual(row['decision'],'ACCEPTED')

    def test_history_write_failure_leaves_rejection_and_no_partial_reopen_event(self):
        app=self.rejected();before=self.history(app)
        with patch('scripts.community_onboarding_history.append',side_effect=OSError('history unavailable')):
            with self.assertRaises(OSError):self.fx.review(app,'REOPEN','must remain atomic')
        current=self.fx.call('read',dict(application=app['application']))
        self.assertEqual((current['revision'],current['status']),(app['revision'],'REJECTED'));self.assertEqual(self.history(app),before)


if __name__=='__main__':unittest.main()
