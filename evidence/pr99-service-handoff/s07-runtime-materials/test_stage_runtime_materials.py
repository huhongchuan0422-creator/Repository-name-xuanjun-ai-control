import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import sqlite3
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

NS=runpy.run_path(str(Path(__file__).with_name('stage_runtime_materials.py')))
G=NS['remote_pack'].__globals__

class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for n in NS['DIRS']:(self.root/n).mkdir(parents=True)
        (self.root/NS['DIRS'][0]/'credential-store.env').write_text('TRADING_CREDENTIAL_MASTER_KEY=synthetic-secret\n')
        (self.root/'sample.py').write_text('# fixture\n')
        (self.root/NS['DB']).parent.mkdir(parents=True)
        c=sqlite3.connect(str(self.root/NS['DB']));c.execute('create table sample(value text)');c.execute('insert into sample values (?)',('synthetic-private',));c.commit();c.close()
        self.header={'unit_hashes':{},'source_hashes':{'sample.py':NS['sha']((self.root/'sample.py').read_bytes())}}
    def tearDown(self):self.tmp.cleanup()
    def run_pack(self):
        buf=io.BytesIO();output=types.SimpleNamespace(buffer=buf)
        real=tempfile.mkdtemp
        with patch.dict(G,ROOT=self.root,EXTERNAL=(),unit_gate=lambda h:{'fixture':'stable'}),patch.object(NS['os'],'get euid'.replace(' ',''),return_value=0),patch.object(NS['os'],'uname',return_value=types.SimpleNamespace(nodename=NS['TOKYO'])),patch.object(NS['sys'],'stdout',output),patch.object(NS['tempfile'],'mkdtemp',side_effect=lambda **kw:real(prefix=kw.get('prefix',''),dir=str(self.root))):
            NS['remote_pack'](self.header)
        return buf.getvalue()
    def test_actual_sqlite_backup_private_archive(self):
        raw=self.run_pack();p=self.root/'received.tar';p.write_bytes(raw)
        m=NS['verify_archive'](p)
        self.assertEqual(m['database_integrity'],'PASS');self.assertFalse(m['final_cutover_snapshot'])
        self.assertIn('project/'+NS['DB'],m['files'])
        self.assertNotIn('synthetic-secret',json.dumps(m));self.assertNotIn('synthetic-private',json.dumps(m))
    def test_live_source_drift_rejected(self):
        self.header['source_hashes']['sample.py']='0'*64
        with self.assertRaisesRegex(RuntimeError,'LIVE_SOURCE_DRIFT'):self.run_pack()
    def test_symlink_not_followed(self):
        (self.root/NS['DIRS'][0]/'link').symlink_to(self.root/'sample.py')
        with self.assertRaisesRegex(RuntimeError,'NONREGULAR'):self.run_pack()
    def test_hardlink_rejected(self):
        import os
        (self.root/'other').write_text('fixture')
        os.link(self.root/'other',self.root/NS['DIRS'][0]/'hard')
        with self.assertRaisesRegex(RuntimeError,'NONREGULAR'):self.run_pack()
    def test_key_missing_holds(self):
        (self.root/NS['DIRS'][0]/'credential-store.env').write_text('OTHER=synthetic-secret\n')
        with self.assertRaisesRegex(RuntimeError,'MASTER_KEY_FILE_BINDING_UNKNOWN'):self.run_pack()
    def test_traversal_and_unrelated_paths_rejected(self):
        for p in ('../escape','/etc/shadow','project/runtime/secure-secrets-portal/../../escape','project/unrelated.txt'):
            self.assertFalse(NS['allowed_name'](p))
    def test_tampered_manifest_rejected(self):
        raw=self.run_pack();src=io.BytesIO(raw);out=io.BytesIO()
        with tarfile.open(fileobj=src,mode='r:') as a,tarfile.open(fileobj=out,mode='w') as b:
            for member in a:
                data=a.extractfile(member).read()
                if member.name=='PRIVATE_MANIFEST.json':
                    m=json.loads(data);next(iter(m['files'].values()))['sha256']='0'*64;data=json.dumps(m).encode();member.size=len(data)
                b.addfile(member,io.BytesIO(data))
        p=self.root/'tampered.tar';p.write_bytes(out.getvalue())
        with self.assertRaisesRegex(RuntimeError,'MANIFEST_MISMATCH'):NS['verify_archive'](p)

if __name__=='__main__':unittest.main()
