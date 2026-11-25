"""Exact local review/package dependencies; no browser, credentials or live service."""
import ast
import fnmatch
import posixpath
import re
import unittest
from pathlib import Path
from scripts.community_review_runtime import native_review_sources

ROOT=Path(__file__).resolve().parents[1]
class NativeReviewDependencies(unittest.TestCase):
    def test_all_literal_local_requires_resolve_to_actual_exact_sources(self):
        sources=native_review_sources()
        for name,raw in sources.items():
            self.assertEqual(raw,(ROOT/'clients/community-mini'/name).read_text())
            if not name.endswith('.js'):
                continue
            for relative in re.findall(r"require\(['\"](\.[^'\"]+)['\"]\)",raw):
                target=posixpath.normpath(posixpath.join(posixpath.dirname(name),relative))
                if not target.endswith(('.js','.json')):
                    target+='.js'
                with self.subTest(source=name,target=target):
                    self.assertIn(target,sources)
        self.assertIn('pages/merchant-join/direct-ocr.js',sources)
        self.assertIn('pages/merchant-join/direct-proof.js',sources)
        self.assertIn('pages/user-agreement/content.js',sources)

    def test_stage_package_covers_every_declared_page_and_its_local_modules(self):
        import json
        source=ast.parse((ROOT/'scripts/community_stage_package.py').read_text())
        assignment=next(n for n in ast.walk(source) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='patterns' for t in n.targets))
        patterns=ast.literal_eval(assignment.value)
        pages=json.loads((ROOT/'clients/community-mini/app.json').read_text())['pages']
        for page in pages:
            for file in (ROOT/'clients/community-mini'/page).parent.iterdir():
                if file.suffix not in ('.js','.json','.wxml','.wxss'):
                    continue
                name=file.relative_to(ROOT).as_posix()
                with self.subTest(source=name):
                    self.assertTrue(any(fnmatch.fnmatchcase(name,p) for p in patterns),name)

if __name__=='__main__':
    unittest.main()
