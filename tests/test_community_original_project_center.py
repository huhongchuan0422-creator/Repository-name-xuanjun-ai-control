"""Mini customer project center reuses the existing immutable Center operations."""
import unittest
import hashlib
import hmac
from scripts.pr122_customer_core import canonical
import test_community_reports as fixtures


class OriginalProjectCenterJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):
        self.fx=fixtures.CommunityReportJourney()
        self.fx.setUp()
    def tearDown(self):
        self.fx.tearDown()
    def consumer(self, op, params=None, token=None):
        return self.fx.commerce.consumer(token or self.fx.token,
                                         'shop1',op,params or {})

    def test_summary_and_checklist_use_original_project_and_customer_id(self):
        summary=self.consumer('project_summary')
        project,role,details=self.fx.c.project(self.fx.fx.uid1,'project1')
        self.assertEqual(summary['project_id'],project['id'])
        self.assertEqual(summary['customer_id'],project['customer'])
        self.assertEqual(summary['title'],details['title'])
        self.assertEqual(summary['role'],role)
        self.assertEqual(self.consumer('project_checklist'),
                         self.fx.c.checklist(self.fx.fx.uid1,'project1'))

    def test_project_feedback_archived_through_original_center(self):
        receipt=self.consumer('project_feedback',{'message':'请核对门店需求版本'})
        self.assertEqual(receipt['status'],'ARCHIVED')
        self.assertEqual(receipt['ai_response'],'PENDING_PROVIDER')
        archived=self.fx.c.messages(self.fx.fx.uid1,'project1')
        self.assertEqual(archived[-1]['body'],'请核对门店需求版本')

    def test_versioned_material_submit_and_independent_review_original_center(self):
        c=self.fx.c
        _,_,details=c.project(self.fx.fx.uid1,'project1')
        material=dict(id='material1',title='Fixture material',purpose='fixture material submission',
                      required=True,identity_requirements=[],official_url='https://example.org',
                      instructions='Only synthetic reference; never real customer secrets',
                      minimum_permissions=[],fees=[],verified_at=c.now(),formats=[],
                      valid_until=c.now()+3600,submission_type='SECRETREF',category='MATERIAL')
        project=dict(details,requirements=[material],reviewer_emails=['two@example.org'])
        payload=dict(revision=2,expires=c.now()+3600,projects=[project])
        key=b'a'*32
        c.import_authority(dict(payload=payload,signature=hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()),key)
        c.secretref=lambda project_id,item,kind,reference: (
            project_id=='project1' and item=='material1' and kind=='SECRETREF'
            and reference=='synthetic-reference')
        saved=c.save(self.fx.fx.uid1,'project1','material1',0,'SECRETREF','synthetic-reference')
        self.assertEqual(saved['state'],'PARTIAL')
        submitted=self.consumer('project_submit',dict(item='material1',revision=saved['revision']))
        self.assertEqual(submitted['state'],'SUBMITTED')
        with self.assertRaises(PermissionError):
            self.consumer('project_review',dict(item='material1',revision=submitted['revision'],action='begin_review',reason=''))
        reviewer=self.fx.fx.token('reviewer2','openid2')
        review=self.consumer('project_review',dict(item='material1',revision=submitted['revision'],action='begin_review',reason=''),token=reviewer)
        self.assertEqual(review['state'],'IN_REVIEW')
        approved=self.consumer('project_review',dict(item='material1',revision=review['revision'],action='approve',reason='synthetic acceptance'),token=reviewer)
        self.assertEqual(approved['state'],'ACCEPTED')
        self.assertEqual(self.consumer('project_checklist')['overall'],'ACCEPTED')
        with self.assertRaises(ValueError):
            self.consumer('project_review',dict(item='material1',revision=review['revision'],action='approve',reason='replay'),token=reviewer)

    def test_independent_review_never_granted_to_owner_or_editor(self):
        request=dict(item='material1',revision=1,action='approve',reason='checked')
        with self.assertRaisesRegex(PermissionError,'PROJECT_PERMISSION_REQUIRED'):
            self.consumer('project_review',request)
        reviewer_token=self.fx.fx.token('reviewer-code','openid2')
        with self.assertRaisesRegex(PermissionError,'PROJECT_PERMISSION_REQUIRED'):
            self.consumer('project_review',request,token=reviewer_token)
        with self.assertRaises(ValueError):
            self.consumer('project_review',dict(request,action='skip_validation'))

    def test_material_submit_cannot_mint_requirements_or_approve(self):
        before=self.fx.c.db.execute(
            'SELECT COUNT(*) FROM versions WHERE project=?',('project1',)).fetchone()[0]
        with self.assertRaises(ValueError):
            self.consumer('project_submit',{'item':'x','revision':0,'action':'approve'})
        with self.assertRaises((PermissionError,ValueError)):
            self.consumer('project_submit',{'item':'nonexistent','revision':0})
        after=self.fx.c.db.execute(
            'SELECT COUNT(*) FROM versions WHERE project=?',('project1',)).fetchone()[0]
        self.assertEqual(before,after)

    def test_invalid_fields_and_revoked_membership_fail_closed(self):
        with self.assertRaises(ValueError):
            self.consumer('project_summary',{'project':'other'})
        with self.assertRaises(ValueError):
            self.consumer('project_feedback',{'message':7})
        with self.fx.c.tx():
            self.fx.c.db.execute('UPDATE members SET active=0 WHERE project=? AND user_id=?',
                                 ('project1',self.fx.fx.uid1))
        with self.assertRaises(PermissionError):
            self.consumer('project_summary')
        with self.assertRaises(PermissionError):
            self.consumer('project_feedback',{'message':'must fail'})


if __name__ == '__main__':
    unittest.main()
