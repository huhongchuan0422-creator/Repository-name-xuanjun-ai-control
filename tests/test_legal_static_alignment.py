"""Static-only integration checks. No customer data or signing/payment interfaces."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('static_builder', ROOT/'scripts/build_legal_previews.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class StaticAlignment(unittest.TestCase):
    def test_reviewed_html_bytes_survive_rebuild(self):
        expected = {'custom-development': '04b3f5d112780bbc3c6d742f235beaaa9947993d97ed89ca4b892955b6cf0462',
                    'custom-sow': '752200d5ae7849dbb13870969b814cc7e6ee471584b2e54635e8b5309e15e8aa'}
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);shutil.copytree(ROOT/'docs/legal',r/'docs/legal')
            builder.build(r)
            first={p.name:p.read_bytes() for p in (r/'demos/legal').glob('*.html')}
            builder.build(r)
            self.assertEqual(first,{p.name:p.read_bytes() for p in (r/'demos/legal').glob('*.html')})
            for key,sha in expected.items():self.assertEqual(hashlib.sha256(first[key+'.html']).hexdigest(),sha)
            index=first['index.html'].decode()
            self.assertNotIn('custom-sow.html',index)
            self.assertNotIn('主合同＋',index)
            self.assertIn('21份对客草案',index)
            self.assertIn('custom-development.html',index)

    def test_clean_build_matches_every_checked_in_preview(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);shutil.copytree(ROOT/'docs/legal',r/'docs/legal')
            builder.build(r)
            expected={p.name:p.read_bytes() for p in (ROOT/'demos/legal').glob('*.html')}
            self.assertEqual(expected,{p.name:p.read_bytes() for p in (r/'demos/legal').glob('*.html')})

    def test_service_template_and_html_are_aligned(self):
        import html
        source=(ROOT/'docs/legal/templates/service-package-rights.md').read_text()
        page=(ROOT/'demos/legal/service-package-rights.html').read_text()
        registry=json.loads((ROOT/'docs/legal/registry.json').read_text())
        entry=next(e for e in registry['documents'] if e['id']=='service-package-rights')
        self.assertEqual(entry['version'],'2026-10-17-draft.2')
        self.assertEqual(entry['source_sha256'],hashlib.sha256(source.encode()).hexdigest())
        self.assertIn('版本：'+entry['version'],source)
        self.assertIn('版本：'+entry['version'],page)
        self.assertNotIn('2026-10-15-draft.1',source)
        self.assertIn('<pre>'+html.escape(source)+'</pre>',page)
        self.assertIn(hashlib.sha256(source.encode()).hexdigest(),page)
        self.assertIn('普通合格自营费用抵扣上限90%',source)
        self.assertIn('折后合格定制开发费的最多50%',source)
        self.assertIn('第三方采购、模型/资源成本及明确排除项不抵扣',source)
        self.assertIn('1亿元累计有效交易额门槛',source)
        self.assertIn('每1点权益值',source)
        self.assertIn('总量2000万点权益值；推荐活动池300万点中用户210万点、团队90万点。',source)
        self.assertIn('每份最低实付10元起，可多份叠加',source)

    def test_internal_document_cannot_gain_public_route_or_signature(self):
        for field,value in [('preview','demos/legal/custom-sow.html'),('planned_route','/legal/custom-sow/'),('signature_enabled',True),('status','DRAFT_NOT_FOR_SIGNATURE')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                r=Path(td);shutil.copytree(ROOT/'docs/legal',r/'docs/legal')
                registry=json.loads((r/'docs/legal/registry.json').read_text())
                entry=next(x for x in registry['documents'] if x['id']=='custom-sow');entry[field]=value
                (r/'docs/legal/registry.json').write_text(json.dumps(registry))
                with self.assertRaises(ValueError):builder.build(r)

    def test_reviewed_binding_cannot_silently_drift(self):
        for field,value in [('version','changed'),('title','changed')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                r=Path(td);shutil.copytree(ROOT/'docs/legal',r/'docs/legal')
                registry=json.loads((r/'docs/legal/registry.json').read_text())
                entry=next(x for x in registry['documents'] if x['id']=='custom-development');entry[field]=value
                (r/'docs/legal/registry.json').write_text(json.dumps(registry))
                with self.assertRaisesRegex(ValueError,'REVIEWED_STATIC_VERSION_MISMATCH'):builder.build(r)

if __name__=='__main__':unittest.main()
