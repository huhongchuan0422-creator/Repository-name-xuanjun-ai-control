import copy
from pathlib import Path
import tempfile
import unittest
from scripts import pr122_showcase as s
from tests.test_pr122_showcase import project, page, milestone, obj, approvals, published


class RoleGenerationTests(unittest.TestCase):
    def records(self):
        view=page();view['role']='consumer'
        feature=obj('feature','checkout-feature',role='consumer',device='phone',milestone_id='checkout',page_id='consumer',page_version=1,page_artifact_sha256=view['artifact_sha256'])
        return [project(),view,milestone('checkout'),feature]

    def catalog(self,items,proof=None):
        return s.compile_catalog(items,proof if proof is not None else approvals(items),published_pages=published(items))

    def test_acceptance_automatically_generates_role_page_without_html(self):
        items=self.records();catalog=self.catalog(items)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';s.render(catalog,out)
            role=out/'showcase/projects/community-payment/roles/consumer/phone/index.html'
            self.assertTrue(role.is_file())
            text=role.read_text();self.assertIn('当前角色功能',text)
            self.assertNotIn('merchant',text);self.assertNotIn('iframe',text)
            self.assertIn('/visual/demo/',text)
            self.assertIn('/roles/consumer/phone/',(out/'showcase/projects/community-payment/index.html').read_text())

    def test_draft_feature_and_unfinished_acceptance_never_generate(self):
        items=self.records()
        self.assertEqual(s.role_views(self.catalog(items,approvals(items[:-1]))['projects'][0]),[])
        items[2]['state']='IN_PROGRESS'
        self.assertEqual(s.role_views(self.catalog(items)['projects'][0]),[])

    def test_new_page_version_cannot_inherit_feature_acceptance(self):
        items=self.records();new=copy.deepcopy(items[1]);new['version']=2;new['artifact_sha256']='2'*64;items.append(new)
        self.assertEqual(s.role_views(self.catalog(items)['projects'][0]),[])

    def test_role_mismatch_cannot_generate(self):
        items=self.records();items[1]['role']='merchant'
        self.assertEqual(s.role_views(self.catalog(items)['projects'][0]),[])

    def test_consumer_desktop_contract_is_rejected(self):
        feature=self.records()[-1];feature['device']='desktop'
        with self.assertRaisesRegex(ValueError,'PHONE_FIRST_ROLE'):s.validate(feature)

    def test_multiple_roles_and_projects_do_not_mix(self):
        items=self.records();merchant=copy.deepcopy(items[1]);merchant.update(id='merchant',role='merchant',href='/merchant/')
        feature=copy.deepcopy(items[-1]);feature.update(id='merchant-feature',role='merchant',page_id='merchant')
        items.extend([merchant,feature,project('other-project')]);c=self.catalog(items)
        views=s.role_views(c['projects'][0]);self.assertEqual(len(views),2)
        self.assertNotIn('/merchant/',next(v['body'] for v in views if '/consumer/' in v['href']))
        self.assertEqual(s.role_views(c['projects'][1]),[])

    def test_accepted_new_function_updates_only_its_role_navigation(self):
        items=self.records();new=copy.deepcopy(items[-1]);new['id']='order-history';new['title']={'zh':'订单','en':'Orders'};items.append(new)
        before=s.role_views(self.catalog(items,approvals(items[:-1]))['projects'][0])[0]['body']
        after=s.role_views(self.catalog(items)['projects'][0])[0]['body']
        self.assertNotIn('#feature-order-history',before);self.assertIn('#feature-order-history',after)


if __name__=='__main__':unittest.main()
