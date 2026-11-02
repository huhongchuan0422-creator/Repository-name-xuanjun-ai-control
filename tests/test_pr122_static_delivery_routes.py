"""Exact 4881 product routing through the real wrapper; no server or approval effects."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from scripts import pr122_site_hub_unified_release as release

ROOT=Path(__file__).resolve().parents[1]

class ExactDeliveryRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=ROOT/'evidence/pr122-delivery-release'
        raw=(folder/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes()
        if len(raw)!=537152 or hashlib.sha256(raw).hexdigest()!='4881d1e30da4815969cb44fd82411e0bef179cafa3444bf03f58e0ad8aabed80':
            raise AssertionError('EXACT_PUBLIC_ARTIFACT_REQUIRED')
        cls.pins=json.loads((folder/'ARTIFACT_BINDING.json').read_bytes())
        cls.data=release.entries(raw,cls.pins)
        cls.source=json.loads(cls.data['source-pin.json'])
        cls.new={p for p,h in cls.source['overlay_baselines'].items() if h is None}

    def changed(self,name,value):
        data=dict(self.data);data[name]=json.dumps(value).encode();return data

    def test_exact_entries_and_all_116_file_and_directory_routes(self):
        self.assertEqual(len(self.data),1256)
        self.assertEqual(len(json.loads(self.data['candidate-manifest.json'])['files']),1303)
        self.assertEqual(len(self.new),116)
        snippet,routes=release.routes(self.data)
        self.assertEqual(len(routes),214)
        for name in self.new:
            self.assertEqual(routes['/'+name],('file','/'+name))
            if name.endswith('/index.html'):
                self.assertEqual(routes['/'+name[:-10]],('file','/'+name))
                self.assertEqual(routes['/'+name[:-11]],('redirect','/'+name[:-10]))
        self.assertIn(b'application/javascript js mjs',snippet)

    def test_all_15_delivery_files_and_smoke_overlay_urls(self):
        files={p for p in self.new if p.startswith('delivery/')}
        self.assertEqual(len(files),15)
        self.assertEqual(files,{r['path'] for r in json.loads(self.data['candidate-manifest.json'])['files'] if r['path'].startswith('delivery/')})
        smoke=release.smoke_routes(self.data)
        for name in self.data:
            if not name.startswith('overlay/public/'):continue
            target='/'+name.removeprefix('overlay/public/')
            route='/' if target=='/index.html' else target[:-5] if target.count('/')==1 and target.endswith('.html') else target
            self.assertEqual(smoke[route],('file',target))
        self.assertEqual(smoke['/delivery/'],('file','/delivery/index.html'))
        self.assertEqual(smoke['/delivery/community-next/'],('file','/delivery/community-next/index.html'))

    def test_unknown_malformed_or_noninteger_contract_rejected(self):
        original=json.loads(self.data['BUILD_PROVENANCE.json'])
        for key,value in [('schema','UNREVIEWED_SCHEMA'),('new_files',117),('public_files',1304),('archive_members',True),('extra',1)]:
            changed=copy.deepcopy(original);changed['brand_contract'][key]=value
            with self.assertRaisesRegex(RuntimeError,'ROUTE_BRAND_CONTRACT'):
                release.routes(self.changed('BUILD_PROVENANCE.json',changed))

    def test_missing_or_extra_new_file_rejected(self):
        for extra in (False,True):
            source=copy.deepcopy(self.source)
            if extra:source['overlay_baselines']['delivery/unreviewed.html']=None
            else:source['overlay_baselines'][sorted(self.new)[0]]='0'*64
            with self.assertRaisesRegex(RuntimeError,'NEW_PUBLIC_COUNT'):
                release.routes(self.changed('source-pin.json',source))

    def test_116_cannot_use_missing_or_legacy_contract(self):
        data=dict(self.data);data.pop('BUILD_PROVENANCE.json')
        with self.assertRaisesRegex(RuntimeError,'NEW_PUBLIC_COUNT'):release.routes(data)
        provenance=json.loads(self.data['BUILD_PROVENANCE.json'])
        provenance['brand_contract']={'schema':'FULL_STATIC_BRAND_REVIEW_V1','brand':'玄钧AI新','archive_members':1241,'overlay_files':1197,'new_files':101,'public_files':1288}
        with self.assertRaisesRegex(RuntimeError,'NEW_PUBLIC_COUNT'):
            release.routes(self.changed('BUILD_PROVENANCE.json',provenance))

    def test_legacy_101_contract_unchanged(self):
        data=dict(self.data);data.pop('BUILD_PROVENANCE.json')
        source=copy.deepcopy(self.source)
        for name in self.new:
            if name.startswith('delivery/'):source['overlay_baselines'].pop(name)
        data['source-pin.json']=json.dumps(source).encode()
        self.assertEqual(sum(v is None for v in source['overlay_baselines'].values()),101)
        self.assertEqual(len(release.routes(data)[1]),193)

    def test_canonical_path_guard_retained(self):
        source=copy.deepcopy(self.source);source['overlay_baselines'].pop(sorted(self.new)[0]);source['overlay_baselines']['../escape.html']=None
        with self.assertRaisesRegex(RuntimeError,'ROUTE_PATH'):
            release.routes(self.changed('source-pin.json',source))

    def test_actual_package_hash_guard_retained(self):
        raw=(ROOT/'evidence/pr122-delivery-release/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'STATIC_PACKAGE_HASH'):
            release.entries(raw+b'\n',self.pins)

if __name__=='__main__':unittest.main()
