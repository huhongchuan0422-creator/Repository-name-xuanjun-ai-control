import copy
import json
from pathlib import Path
import tempfile
import unittest
from html.parser import HTMLParser
from scripts import pr122_showcase as s
from tests.test_pr122_showcase import project, page, milestone, obj, approvals, published
from tests.pr122_showcase_role_fixture import fixture_records, PROJECT, ROLES


class Links(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.links = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))


class RoleGenerationTests(unittest.TestCase):
    def test_branded_merchant_bundle_declaration_matches_current_public_bytes(self):
        root = Path(__file__).resolve().parents[1]
        public = root / 'showcase/projects/community-payment/views/merchant/v1/public'
        declaration = json.loads((root / 'showcase/projects/community-payment/merchant-v1.json').read_text())
        rows, _ = s.scan_public_tree(public)
        self.assertEqual(rows['index.html']['sha256'], declaration['artifact_sha256'])
        self.assertEqual(s.sha(s.canonical(rows)), declaration['release_artifact_sha256'])
        self.assertIn('玄钧AI新', (public / 'index.html').read_text())

    def test_six_role_fixture_generates_isolated_bilingual_routes(self):
        items, proof, pages, files = fixture_records()
        catalog = s.compile_catalog(items, proof, published_pages=pages)
        self.assertEqual(catalog['projects'][0]['state'], 'DEVELOPING')
        self.assertEqual(catalog['cases'], [])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'public'
            s.render(catalog, out, project_files=files)
            self.assertEqual(len(list(out.glob('showcase/**/roles/*/*/index.html'))), 12)
            for role, device in ROLES.items():
                clean = 'projects/' + PROJECT + '/roles/' + role + '/' + device + '/'
                for prefix, language in (('', 'zh-CN'), ('en/', 'en')):
                    text = (out / 'showcase' / prefix / clean / 'index.html').read_text()
                    links = Links(text).links
                    switches = [link for link in links if 'lang' in link]
                    self.assertEqual([(link['lang'], link['href']) for link in switches],
                                     [('zh-CN', '/showcase/' + clean), ('en', '/showcase/en/' + clean)])
                    self.assertEqual([link['lang'] for link in switches if link.get('aria-current') == 'page'], [language])
                    self.assertEqual([link['href'] for link in links if link['href'].startswith('#')],
                                     ['#feature-' + role + '-feature'])
                    implementations = [link['href'] for link in links if '/views/' in link['href']]
                    self.assertEqual(implementations, ['/showcase/projects/' + PROJECT + '/views/' + role + '/v1/'])
                    self.assertIn('/showcase/' + prefix + 'projects/' + PROJECT + '/', [link['href'] for link in links])
                    self.assertNotIn('primary-nav', text)

    def test_six_roles_without_functional_acceptance_never_render(self):
        items, proof, pages, files = fixture_records()
        items = [i for i in items if i['kind'] != 'feature_acceptance']
        catalog = s.compile_catalog(items, proof, published_pages=pages)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'public'
            s.render(catalog, out, project_files=files)
            self.assertEqual(list(out.glob('showcase/**/roles/*/*/index.html')), [])
            self.assertNotIn('/views/', (out / 'showcase/projects' / PROJECT / 'index.html').read_text())

    def test_revoked_role_acceptance_removes_only_that_role(self):
        items, proof, pages, _ = fixture_records()
        for role in ROLES:
            revoked = next(i for i in items if i['kind'] == 'feature_acceptance' and i['id'] == role + '-feature-accepted')
            filtered = {digest: value for digest, value in proof.items() if digest != s.sha(s.canonical(revoked))}
            catalog = s.compile_catalog(items, filtered, published_pages=pages)
            self.assertEqual({f['role'] for f in catalog['projects'][0]['features']}, set(ROLES) - {role})
            self.assertEqual(len(s.role_views(catalog['projects'][0])), 5)

    def test_ecosystem_links_preserve_language(self):
        items, proof, pages, _ = fixture_records()
        catalog = s.compile_catalog(items, proof, published_pages=pages)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'public'
            s.render(catalog, out)
            for prefix in ('', 'en/'):
                links = Links((out / 'showcase' / prefix / 'ecosystem/index.html').read_text()).links
                actual = [link['href'] for link in links if link['href'].startswith(('/ecosystem/', '/en/ecosystem/'))]
                self.assertEqual(actual, ['/' + prefix + 'ecosystem/' + suffix for suffix in ('', 'tiers/', 'ledger/', 'profit-sharing/')])

    def records(self):
        view=page();view['role']='consumer'
        feature=obj('feature','checkout-feature',role='consumer',device='phone',milestone_id='checkout',page_id='consumer',page_version=1,page_artifact_sha256=view['artifact_sha256'])
        return [project(),view,milestone('checkout'),feature]

    def accept(self,items):
        items=copy.deepcopy(items)
        c=s.compile_catalog(items,approvals(items),published_pages=published(items))
        for feature in (i for i in list(items) if i['kind']=='feature'):
            p=next(p for p in c['projects'] if p['project_id']==feature['project_id'])
            items.append(obj('feature_acceptance',feature['id']+'-accepted',project=feature['project_id'],project_version=p['version'],snapshot_sha256=p['snapshot_sha256'],members=p['snapshot_members'],feature_sha256=s.sha(s.canonical(feature)),evidence_url='https://github.com/example/repo/issues/3'))
        return items

    def catalog(self,items,proof=None,accept=True):
        if accept:items=self.accept(items)
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
        before=s.role_views(self.catalog(items[:-1])['projects'][0])[0]['body']
        after=s.role_views(self.catalog(items)['projects'][0])[0]['body']
        self.assertNotIn('#feature-order-history',before);self.assertIn('#feature-order-history',after)

    def test_done_and_reviewed_without_acceptance_cannot_generate_or_fallback(self):
        c=self.catalog(self.records(),accept=False)
        self.assertEqual(s.role_views(c['projects'][0]),[])
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';s.render(c,out)
            self.assertFalse((out/'showcase/projects/community-payment/roles').exists())
            self.assertNotIn('href="/visual/demo/"',(out/'showcase/projects/community-payment/index.html').read_text())

    def test_scoped_acceptance_does_not_claim_project_complete(self):
        c=self.catalog(self.records());self.assertTrue(c['projects'][0]['features'])
        self.assertEqual(c['projects'][0]['state'],'DEVELOPING');self.assertEqual(c['cases'],[])

    def test_stale_project_version_and_snapshot_are_rejected(self):
        for field in ('project_version','snapshot_sha256'):
            items=self.accept(self.records());items[-1][field]=2 if field=='project_version' else 'f'*64
            self.assertEqual(s.role_views(self.catalog(items,accept=False)['projects'][0]),[])

    def test_wrong_project_contract_cannot_authorize(self):
        items=self.accept(self.records());items[-1]['project_id']='other-project';items.append(project('other-project'))
        self.assertEqual(s.role_views(self.catalog(items,accept=False)['projects'][0]),[])

    def test_changed_member_and_feature_identity_are_rejected(self):
        for field in ('members','feature_sha256'):
            items=self.accept(self.records())
            if field=='members':items[-1]['members']=items[-1]['members'][:-1]
            else:items[-1]['feature_sha256']='f'*64
            self.assertEqual(s.role_views(self.catalog(items,accept=False)['projects'][0]),[])

    def test_revoked_feature_page_milestone_or_contract_cannot_generate(self):
        for kind in ('feature','page','milestone','feature_acceptance'):
            items=self.accept(self.records());proof=approvals(items)
            record=next(i for i in items if i['kind']==kind)
            proof.pop(s.sha(s.canonical(record)))
            self.assertEqual(s.role_views(self.catalog(items,proof,accept=False)['projects'][0]),[])

    def test_new_project_version_invalidates_scoped_acceptance(self):
        items=self.accept(self.records());new=copy.deepcopy(items[0]);new['version']=2;items.append(new)
        self.assertEqual(s.role_views(self.catalog(items,accept=False)['projects'][0]),[])

    def test_full_project_acceptance_does_not_replace_feature_acceptance(self):
        items=self.records();items.append(milestone('merchant'))
        c=self.catalog(items,accept=False);p=c['projects'][0]
        items.append(obj('acceptance','whole-project',project_version=1,snapshot_sha256=p['snapshot_sha256'],members=p['snapshot_members'],evidence_url='https://github.com/example/repo/issues/4'))
        c=self.catalog(items,accept=False);self.assertEqual(c['projects'][0]['state'],'ACCEPTED')
        self.assertEqual(s.role_views(c['projects'][0]),[])


if __name__=='__main__':unittest.main()
