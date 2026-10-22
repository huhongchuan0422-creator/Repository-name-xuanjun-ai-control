"""Protected config and source-default tests; no service enrollment."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from production.cloud_connection.oauth_entrypoint import private_bytes, load_app, HOSTS
from production.cloud_connection.queue import Hold


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root');self.root=Path(self.tmp.name)
        self.file=self.root/'config.json';self.file.write_bytes(b'{}');os.chmod(str(self.file),0o600)
    def tearDown(self):self.tmp.cleanup()

    def test_descriptor_path_rejects_symlink_and_writable_parent(self):
        alias=self.root/'alias';alias.symlink_to(self.file)
        with self.assertRaises(OSError):private_bytes(str(alias),100)
        os.chmod(str(self.root),0o777)
        try:
            with self.assertRaises(Hold):private_bytes(str(self.file),100)
        finally:os.chmod(str(self.root),0o700)

    def test_private_file_type_mode_size_and_nlink(self):
        self.assertEqual(private_bytes(str(self.file),100),b'{}')
        self.assertEqual(private_bytes(str(self.file),100,False)[0],self.file.stat().st_dev)
        os.chmod(str(self.file),0o644)
        with self.assertRaises(Hold):private_bytes(str(self.file),100)
        os.chmod(str(self.file),0o600)
        with self.assertRaises(Hold):private_bytes(str(self.file),1)
        os.link(str(self.file),str(self.root/'hardlink'))
        with self.assertRaises(Hold):private_bytes(str(self.file),100)

    def test_examples_cannot_start_or_implicitly_create_state(self):
        root=Path(__file__).resolve().parents[2]
        for kind in ('resource','authority'):
            raw=(root/'deployment/cloud-connection/oauth'/ (kind+'.example.json')).read_bytes()
            self.file.write_bytes(raw)
            with patch('production.cloud_connection.oauth_entrypoint.os.uname',return_value=SimpleNamespace(nodename=HOSTS[kind])):
                with self.assertRaisesRegex(Hold,'NOT_ENROLLED'):
                    load_app(kind,str(self.file),hashlib.sha256(raw).hexdigest())

    def test_source_manifest_matches_all_runtime_files(self):
        root=Path(__file__).resolve().parents[2]
        manifest=root/'deployment/cloud-connection/oauth/SOURCE_MANIFEST.json'
        self.assertTrue(manifest.exists())
        doc=json.loads(manifest.read_text());paths=set()
        for entry in doc['files']:
            self.assertNotIn(entry['path'],paths);paths.add(entry['path'])
            raw=(root/entry['path']).read_bytes()
            self.assertEqual(len(raw),entry['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
        for name in ('oauth_resource.py','oauth_authority.py','oauth_http.py','oauth_entrypoint.py',
                     'private_transfer.py','private_mcp.py','queue.py','runtime.py','worker.py'):
            self.assertIn('production/cloud_connection/'+name,paths)
