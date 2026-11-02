"""Synthetic regression for the two existing approved Nginx include paths."""
import ast
import hashlib
from pathlib import Path
import stat
import types
import unittest
from unittest.mock import patch

from scripts import pr122_site_hub_host_preflight as preflight

ROOT = Path(__file__).resolve().parents[1]
TLS = '/etc/xuanjun-cloud-oauth/tls-approved.conf'
PROXY = '/etc/xuanjun-cloud-oauth/proxy-approved.conf'

class ApprovedCloudAuthIncludeTests(unittest.TestCase):
    def observe(self, extra=None):
        files = {
            '/etc/nginx/nginx.conf': ('include ' + TLS + '; include ' + PROXY + ';').encode(),
            TLS: b'ssl_certificate_key /private/KEY; ssl_protocols TLSv1.2;',
            PROXY: b'proxy_set_header Authorization "Bearer SYNTHETIC_SECRET";'}
        if extra:
            files[PROXY] = ('include ' + extra + ';').encode()
        reads = []
        def read(path):
            reads.append(str(path))
            return files[str(path)]
        def info(path):
            return types.SimpleNamespace(st_dev=1, st_ino=3,
                st_size=len(files[str(path)]), st_mtime_ns=1,
                st_mode=stat.S_IFREG | 0o600, st_uid=0)
        with patch.object(Path, 'resolve', lambda p, strict=True: p), \
             patch.object(Path, 'read_bytes', read), \
             patch.object(Path, 'stat', info), \
             patch.object(preflight.glob, 'glob', lambda p: [p]):
            result = preflight.nginx_source()
        return result, reads

    def test_exact_existing_paths_fingerprinted(self):
        result, reads = self.observe()
        self.assertEqual(result['status'], 'SOURCE_INVENTORY_COMPLETE')
        self.assertTrue(result['disk_config_trust'])
        self.assertEqual(set(reads), {'/etc/nginx/nginx.conf', TLS, PROXY})

    def test_key_and_other_values_are_not_exported(self):
        result, reads = self.observe()
        self.assertNotIn('/private/KEY', reads)
        self.assertNotIn('SYNTHETIC_SECRET', repr(result))
        self.assertFalse(result['private_keys_read'])
        self.assertFalse(result['raw_config_exported'])

    def test_other_paths_remain_rejected(self):
        for path in ('/etc/xuanjun-cloud-oauth/other.conf', TLS + '.evil',
                     '/etc/xuanjun-cloud-auth/tls-approved.conf',
                     '/etc/xuanjun-cloud-auth/proxy-approved.conf',
                     '/outside/another.conf'):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, '^INCLUDE_OUTSIDE_PUBLIC_CONFIG_ROOT$'):
                    self.observe(path)

    def test_combined_preflight_pin_matches_actual_source(self):
        tree = ast.parse((ROOT / 'scripts/pr122_site_hub_combined.py').read_text())
        values = [ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign) and len(n.targets) == 1
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'PREFLIGHT_SHA']
        actual = hashlib.sha256((ROOT / 'scripts/pr122_site_hub_host_preflight.py').read_bytes()).hexdigest()
        self.assertEqual(values, [actual])

    def test_unified_helper_pin_matches_actual_source(self):
        tree = ast.parse((ROOT / 'scripts/pr122_site_hub_unified_release.py').read_text())
        values = [ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign) and len(n.targets) == 1
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'HELPER_SHA']
        actual = hashlib.sha256((ROOT / 'scripts/pr122_site_hub_combined.py').read_bytes()).hexdigest()
        self.assertEqual(values, [actual])

    def test_actual_helper_load_preserves_preflight_pin(self):
        from scripts import pr122_site_hub_unified_release as unified
        helper = unified._load_helper()
        actual = hashlib.sha256((ROOT / 'scripts/pr122_site_hub_host_preflight.py').read_bytes()).hexdigest()
        self.assertEqual(helper.PREFLIGHT_SHA, actual)
        self.assertEqual(helper.HERE, (ROOT / 'scripts/pr122_site_hub_combined.py').resolve())

if __name__ == '__main__':
    unittest.main()
