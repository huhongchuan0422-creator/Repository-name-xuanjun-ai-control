import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts import pr122_showcase as s
from scripts import pr122_showcase_sources as source


def obj(kind,identifier,version=1,project='community-payment',**fields):
    return {'kind':kind,'id':identifier,'project_id':project,'version':version,'visibility':'PUBLIC','title':{'zh':'测试作品','en':'Test work'},'summary':{'zh':'有证据的演示','en':'An evidenced demonstration'},**fields}
def project(identifier='community-payment'):return obj('project',identifier,project=identifier,state='DEVELOPING',scenarios=[{'zh':'社区生活服务','en':'Community services'}],required_milestones=['checkout','merchant'])
def milestone(identifier):return obj('milestone',identifier,state='DONE',evidence_url='https://github.com/example/repo/issues/1')
def page(version=1,**fields):return obj('page','consumer',version,href='/visual/demo/',role='消费者',artifact_sha256=str(version)*64,release_artifact_sha256='a'*64,**fields)
def approvals(items):return {s.sha(s.canonical(i)):{'decision':'PUBLIC_CONTENT_APPROVED','comment_id':1,'commit':'a'*40,'ci_run_id':2} for i in items}
def published(items):return {i['href']:{'artifact_sha256':i['artifact_sha256'],'release_artifact_sha256':i['release_artifact_sha256']} for i in items if i['kind']=='page'}

class ShowcaseTests(unittest.TestCase):
    def test_register_parallel_projects_and_independent_entries(self):
        items=[project(),project('other-project')];c=s.compile_catalog(items,approvals(items))
        self.assertEqual(len(c['developing']),2)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';s.render(c,out)
            self.assertTrue((out/'showcase/projects/community-payment/index.html').is_file());self.assertTrue((out/'showcase/projects/other-project/index.html').is_file())
    def test_new_role_discovered_only_after_review_and_deployment(self):
        items=[project(),page()];c=s.compile_catalog(items,approvals(items[:1]),published_pages=published(items));self.assertEqual(c['projects'][0]['pages'],[])
        self.assertEqual(len(s.compile_catalog(items,approvals(items),published_pages=published(items))['projects'][0]['pages']),1)
    def test_unreviewed_or_unpublished_new_version_retains_last_safe_version(self):
        items=[project(),page(),page(2)]
        c=s.compile_catalog(items,approvals(items[:2]),published_pages=published(items[:2]));self.assertEqual(c['projects'][0]['pages'][0]['version'],1)
        c=s.compile_catalog(items,approvals(items),published_pages=published(items[:2]));self.assertEqual(c['projects'][0]['pages'][0]['version'],1)
    def test_acceptance_exact_snapshot_promotes_to_case_without_manual_page_edit(self):
        items=[project(),page(),milestone('checkout'),milestone('merchant')]
        c=s.compile_catalog(items,approvals(items),published_pages=published(items));self.assertEqual(c['cases'],[])
        event=obj('acceptance','accepted',project_version=1,snapshot_sha256=c['projects'][0]['snapshot_sha256'],members=c['projects'][0]['snapshot_members'],evidence_url='https://github.com/example/repo/issues/2')
        items.append(event);c=s.compile_catalog(items,approvals(items),published_pages=published(items));self.assertEqual(len(c['cases']),1);self.assertEqual(c['developing'],[])
    def test_acceptance_missing_required_milestone_stays_developing(self):
        items=[project(),page(),milestone('checkout')];c=s.compile_catalog(items,approvals(items),published_pages=published(items))
        items.append(obj('acceptance','accepted',project_version=1,snapshot_sha256=c['projects'][0]['snapshot_sha256'],members=c['projects'][0]['snapshot_members'],evidence_url='https://github.com/example/repo/issues/2'))
        c=s.compile_catalog(items,approvals(items),published_pages=published(items));self.assertEqual(c['cases'],[]);self.assertEqual(c['projects'][0]['progress'],{'done':1,'total':2,'percent':None})
    def test_module_registration_then_reviewed_dual_currency_listing(self):
        module=obj('module','merchant-module',module_id='merchant_operations',package_sha256='b'*64,demo_href='/visual/demo/')
        items=[project(),module];c=s.compile_catalog(items,approvals(items));self.assertEqual(c['modules'],[]);self.assertTrue(c['registration_candidates'])
        prices={'merchant_operations':{'publication_eligible':True,'package_sha256':'b'*64,'offers':[{'mode':'MONTHLY','totals_by_cadence':{'MONTHLY':{'cny_minor':10000,'usd_minor':1990}}}]}}
        c=s.compile_catalog(items,approvals(items),prices);self.assertEqual(len(c['modules']),1);self.assertFalse(c['modules'][0]['purchase_enabled'])
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';s.render(c,out);text=(out/'showcase/modules/index.html').read_text();self.assertIn('¥100.00 / US$19.90',text)
    def test_changed_package_cannot_reuse_module_price_admission(self):
        item=obj('module','module',module_id='merchant_operations',package_sha256='b'*64,demo_href='/demo/')
        c=s.compile_catalog([project(),item],approvals([project(),item]),{'merchant_operations':{'publication_eligible':True,'package_sha256':'c'*64,'offers':[]}});self.assertEqual(c['modules'],[])
    def test_private_and_unknown_fields_do_not_leak(self):
        private=project('private-project');private['visibility']='PRIVATE';items=[project(),private];c=s.compile_catalog(items,approvals(items));self.assertEqual(len(c['projects']),1)
        bad=project();bad['customer_phone']='private'
        with self.assertRaisesRegex(ValueError,'UNKNOWN_OR_MISSING_FIELDS'):s.compile_catalog([bad],approvals([bad]))
    def test_no_author_supplied_approved_flag(self):
        item=project();item['approved']=True
        with self.assertRaises(ValueError):s.validate(item)
    def test_route_injection_rejected(self):
        for href in ('//evil.test/','/../secret','/%2e%2e/private','javascript:alert(1)','/\\evil'):
            with self.subTest(href=href):
                item=page();item['href']=href
                with self.assertRaises(ValueError):s.validate(item)
    def test_real_github_review_origin_and_exact_ci(self):
        items=[project()];identifier=s.sha(s.canonical(items[0]));raw=s.canonical(items[0]);blobsha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        review={'decision':'PUBLIC_CONTENT_APPROVED','reviewer_role':'INDEPENDENT_AUDITOR','commit':'a'*40,'ci_run_id':9,'object_sha256':[identifier]}
        def fetch(path):
            if path.startswith('issues/comments/'):return {'id':7,'user':{'login':'reviewer'},'issue_url':'https://api.github.com/repos/'+source.REPO+'/issues/122','body':'XUANJUN_SHOWCASE_REVIEW\n'+json.dumps(review)}
            if path.startswith('actions/runs/'):return {'head_sha':'a'*40,'status':'completed','conclusion':'success','workflow_id':source.WORKFLOW_ID,'event':'push'}
            if path.startswith('git/trees/'):return {'truncated':False,'tree':[{'type':'blob','sha':blobsha,'path':'showcase/projects/community-payment/project-v1.json'}]}
            return {'content':base64.b64encode(raw).decode()}
        self.assertIn(identifier,source.verify_review(7,items,{'reviewer'},fetch))
        with self.assertRaisesRegex(ValueError,'REVIEW_ORIGIN'):source.verify_review(7,items,{'author'},fetch)
        review['commit']='b'*40
        with self.assertRaisesRegex(ValueError,'EXACT_CI_GATE'):source.verify_review(7,items,{'reviewer'},fetch)
    def test_render_escapes_copy_and_keeps_icp_bilingual(self):
        item=project();item['title']['zh']='<img src=x onerror=alert(1)>';c=s.compile_catalog([item],approvals([item]))
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';m=s.render(c,out,preview=True)
            for path in out.rglob('*.html'):
                text=path.read_text();self.assertNotIn('<img src=x',text);self.assertIn('渝ICP备2026024862号',text)
            self.assertTrue((out/'showcase/en/projects/community-payment/index.html').is_file());self.assertTrue(m['preview_only'])

    def test_new_customer_page_bundle_publishes_with_navigation_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'registry';public=root/'projects/community-payment/views/consumer/v1/public';public.mkdir(parents=True)
            raw=b'<!doctype html><html><head><title>Consumer</title></head><body>Simulation</body></html>';(public/'index.html').write_bytes(raw)
            item=page();item['href']='/showcase/projects/community-payment/views/consumer/v1/';item['artifact_sha256']=s.sha(raw)
            item['release_artifact_sha256']=s.sha(s.canonical({'index.html':{'sha256':s.sha(raw),'size':len(raw)}}))
            items=[project(),item];authority=approvals(items)
            eligible,files=s.project_public_pages(root,items,authority)
            c=s.compile_catalog(items,authority,published_pages=eligible);self.assertEqual(len(c['projects'][0]['pages']),1)
            out=Path(td)/'out';s.render(c,out,project_files=files)
            self.assertEqual((out/'showcase/projects/community-payment/views/consumer/v1/index.html').read_bytes(),raw)
            (public/'index.html').write_bytes(b'changed after review')
            with self.assertRaisesRegex(ValueError,'PAGE_BUNDLE_IDENTITY'):s.project_public_pages(root,items,authority)

    def test_discovery_adds_role_without_central_navigation_change(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'projects/community-payment';folder.mkdir(parents=True)
            for name,item in [('project-v1',project()),('consumer-v1',page())]:(folder/(name+'.json')).write_text(json.dumps(item))
            self.assertEqual(len(s.discover(root)),2)
            role=page();role['id']='platform';role['href']='/platform/'
            (folder/'platform-v1.json').write_text(json.dumps(role));items=s.discover(root)
            c=s.compile_catalog(items,approvals(items),published_pages=published(items));self.assertEqual(len(c['projects'][0]['pages']),2)

    def test_accepted_case_keeps_verified_snapshot_while_next_version_develops(self):
        items=[project(),page(),milestone('checkout'),milestone('merchant')]
        c=s.compile_catalog(items,approvals(items),published_pages=published(items))
        items.append(obj('acceptance','accepted',project_version=1,snapshot_sha256=c['projects'][0]['snapshot_sha256'],members=c['projects'][0]['snapshot_members'],evidence_url='https://github.com/example/test/issues/2'))
        newer=page(2);newer['href']='/visual/demo-v2/';items.append(newer)
        c=s.compile_catalog(items,approvals(items),published_pages=published(items))
        self.assertEqual(len(c['cases']),1);self.assertEqual(c['cases'][0]['pages'][0]['version'],1)
        self.assertEqual(c['projects'][0]['pages'][0]['version'],2);self.assertEqual(c['projects'][0]['state'],'DEVELOPING')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'public';s.render(c,out)
            self.assertIn('/visual/demo/',(out/'showcase/cases/community-payment/index.html').read_text())
            self.assertIn('/visual/demo-v2/',(out/'showcase/projects/community-payment/index.html').read_text())

if __name__=='__main__':unittest.main()
