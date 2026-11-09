import json
from pathlib import Path
import shutil
import tempfile
import unittest
from scripts import pr122_patent_public_preview as p

ROOT=Path(__file__).resolve().parents[1]
class PatentOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.source=self.base/'source'
        shutil.copytree(ROOT/'demos/pr122-patent-preview/original',self.source)
        self.out=self.base/'candidate'
    def test_exact_inputs_three_file_overlay_and_no_other_project_write(self):
        sentinel=self.base/'other-project';sentinel.write_text('preserved')
        receipt=p.compile_overlay(self.source,self.out)
        self.assertEqual(sorted(x.name for x in (self.out/'public'/p.DESTINATION).iterdir()),['app.js','index.html','style.css'])
        self.assertFalse(receipt['csp_changed']);self.assertEqual(receipt['production_changes'],0)
        self.assertEqual(sentinel.read_text(),'preserved')
    def test_style_adaptation_is_exactly_reversible_without_business_changes(self):
        receipt=p.compile_overlay(self.source,self.out)
        for name in ('index.html','app.js'):
            text=(self.out/'public'/p.DESTINATION/name).read_text()
            self.assertNotIn('style="',text)
            for row in receipt['exact_tag_replacements']:
                if row['file']==name:text=text.replace(row['after'],row['before'])
            self.assertEqual(text,(self.source/name).read_text())
        self.assertEqual(len(receipt['style_mapping']),7)
        self.assertTrue((self.out/'public'/p.DESTINATION/'style.css').read_bytes().startswith((self.source/'style.css').read_bytes()))
    def test_modified_input_rejected_before_output(self):
        with (self.source/'app.js').open('a') as stream:stream.write('// drift')
        with self.assertRaisesRegex(ValueError,'PATENT_INPUT_HASH'):p.compile_overlay(self.source,self.out)
        self.assertFalse(self.out.exists())
    def test_unexpected_member_rejected_before_output(self):
        (self.source/'customer-data.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'EXACT_PATENT_INPUT'):p.compile_overlay(self.source,self.out)
        self.assertFalse(self.out.exists())
    def test_existing_output_and_unknown_content_preserved(self):
        self.out.mkdir();sentinel=self.out/'unknown';sentinel.write_text('unknown')
        with self.assertRaises(FileExistsError):p.compile_overlay(self.source,self.out)
        self.assertEqual(sentinel.read_text(),'unknown')
    def test_symlink_source_rejected(self):
        (self.source/'app.js').unlink();(self.source/'app.js').symlink_to(ROOT/'demos/pr122-patent-preview/original/app.js')
        with self.assertRaisesRegex(ValueError,'PATENT_INPUT_TYPE'):p.compile_overlay(self.source,self.out)
    def test_original_publisher_csp_scanner_needs_no_new_inline_hash_or_directive(self):
        from scripts.pr122_website_release import Deadline,write_csp_metadata,InlineCollector
        p.compile_overlay(self.source,self.out)
        release=self.base/'release';release.mkdir()
        with Deadline(10) as deadline:receipt=write_csp_metadata(self.out/'public',release,deadline)
        policy=json.loads((release/'release-metadata/inline-csp.json').read_text())
        self.assertEqual(policy['script_hashes'],[]);self.assertEqual(policy['style_hashes'],[])
        self.assertNotIn('unsafe-inline',policy['policy']);self.assertIn("frame-ancestors 'none'",policy['policy'])
        original=InlineCollector();original.feed((self.source/'index.html').read_text())
        self.assertEqual(len(original.inline_attributes),2)
