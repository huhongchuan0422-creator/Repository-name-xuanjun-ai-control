"""Pure Python unittest suite. No Node, clients, network, or external packages."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from community_license_region import (DIRECTORY, RegionValidationError,
    region_for_exact_code, resolve_license_region, validate)


class LicenseRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((ROOT / 'scripts/community_license_region_areas.json').read_text())['rows']
        cls.fixtures = json.loads((ROOT / 'tests/fixtures/community_license_region.json').read_text())

    def test_directory_metadata(self):
        self.assertEqual(DIRECTORY['row_count'], 3240)
        self.assertEqual(DIRECTORY['observed_at_utc'], '2026-10-29T19:38:25Z')
        self.assertIsNone(DIRECTORY['effective_version'])
        self.assertEqual(DIRECTORY['xlsx_sha256'], 'c3e42f65b1dd2f4360972bdceccc3c522f987c015300fdae756c79682100511f')

    def test_final_image_module_and_directory_are_both_required(self):
        import shutil,subprocess,tempfile
        files=('scripts/community_license_region.py','scripts/community_license_region_areas.json')
        for missing in (None,*files):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'scripts').mkdir()
                for name in files:
                    if name!=missing:shutil.copyfile(ROOT/name,root/name)
                run=subprocess.run([sys.executable,'-B','-c',"from scripts.community_license_region import validate; assert validate('深圳市南山区合成路1号','440305')['ok']"],cwd=root,capture_output=True,text=True,timeout=10)
                if missing is None:self.assertEqual(run.returncode,0,run.stderr)
                else:
                    self.assertNotEqual(run.returncode,0)
                    self.assertIn('ModuleNotFoundError' if missing.endswith('.py') else 'FileNotFoundError',run.stderr)


    def test_fixtures(self):
        for case in self.fixtures:
            with self.subTest(case=case['id']):
                self.assertEqual(resolve_license_region(case['address']), case['expected'])

    def test_all_original_paths(self):
        for row in self.rows:
            self.assertEqual(validate(''.join(row[1:]) + '合成路1号', row[0])['row'], row)

    def test_all_collapsed_paths(self):
        for row in self.rows:
            names = [v for i, v in enumerate(row[1:]) if not i or v != row[i]]
            self.assertEqual(resolve_license_region(''.join(names) + '合成路2号')['code'], row[0])

    def test_all_two_level_paths(self):
        for row in self.rows:
            if row[2] != row[3]:
                self.assertEqual(resolve_license_region(''.join(row[2:]) + '合成路3号')['code'], row[0])

    def test_invalid_codes(self):
        for code in (None, '', '999999', 440305, True, {}, [], ' 440305', '440305 ', '440305\n'):
            with self.subTest(code=code), self.assertRaises(RegionValidationError) as caught:
                validate('广东省深圳市南山区合成路1号', code)
            self.assertEqual(caught.exception.reason, 'INVALID_REGION_CODE')
            self.assertEqual(caught.exception.correctionStep, 0)

    def test_conflicting_existing_code(self):
        with self.assertRaises(RegionValidationError) as caught:
            validate('广东省深圳市南山区合成路1号', '110105')
        self.assertEqual(caught.exception.reason, 'REGION_CODE_MISMATCH')

    def test_failed_address_cannot_be_bypassed_with_existing_code(self):
        for address in ('', '南山区', '河北省唐山市滦州市合成路1号', None):
            with self.assertRaises(RegionValidationError):
                validate(address, '440305')

    def test_no_mutation_or_address_retention(self):
        address = '广东省深圳市南山区合成隐私街道1号'
        result = resolve_license_region(address)
        result['row'][0] = '999999'
        region_for_exact_code('440305')[3] = '伪造区'
        self.assertEqual(resolve_license_region(address)['code'], '440305')
        self.assertNotIn('合成隐私', json.dumps(result, ensure_ascii=False))
        self.assertEqual(address, '广东省深圳市南山区合成隐私街道1号')

    def test_no_added_length_limit_or_truncation(self):
        tail = '合成路' * 100000
        self.assertEqual(resolve_license_region('广东省深圳市南山区' + tail)['code'], '440305')
        self.assertEqual(resolve_license_region('广东省深圳市南山区' + tail + '吉林省长春市朝阳区')['reason'], 'AMBIGUOUS_ADDRESS')
        self.assertFalse(resolve_license_region(tail)['ok'])
        self.assertFalse(resolve_license_region(' ' * 100000)['ok'])


if __name__ == '__main__':
    unittest.main()
