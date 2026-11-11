import gzip,hashlib,io,json
from pathlib import Path
import runpy,sqlite3,tarfile,tempfile,unittest
N=runpy.run_path(str(Path(__file__).with_name('transfer_private_materials.py')))
SOURCE=runpy.run_path(str(Path(__file__).parent.parent/'s07-runtime-materials'/'stage_runtime_materials.py'))
class TransferTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'fixture.db';c=sqlite3.connect(p);c.execute('create table fixture(v text)');c.execute('insert into fixture values (?)',('private-fixture',));c.commit();c.close();db=p.read_bytes()
  cls.data={'project/'+SOURCE['DB']:db,'project/runtime/secure-secrets-portal/credential-store.env':b'TRADING_CREDENTIAL_MASTER_KEY=synthetic-only\n'}
  for i in range(163):cls.data['project/runtime/secure-secrets-portal/fixture-'+str(i)+'.json']=b''
  first='project/runtime/secure-secrets-portal/fixture-0.json'
  cls.data[first]=b'x'*(47099890-sum(map(len,cls.data.values())))
  cls.raw=cls.archive(cls.data)
 @staticmethod
 def archive(data,tamper=False,extra=None):
  manifest={'status':'S07_PRELIMINARY_PRIVATE_MATERIALS_STAGED','source_host':SOURCE['TOKYO'],'final_cutover_snapshot':False,
   'files':{n:{'bytes':len(b),'sha256':N['sha'](b)} for n,b in data.items()}}
  if tamper:next(iter(manifest['files'].values()))['sha256']='0'*64
  rows=dict(data);rows['PRIVATE_MANIFEST.json']=json.dumps(manifest).encode()
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w') as t:
   for n,b in rows.items():
    m=tarfile.TarInfo(n);m.size=len(b);t.addfile(m,io.BytesIO(b))
   if extra:
    m=tarfile.TarInfo(extra);m.size=0;t.addfile(m,io.BytesIO())
  return out.getvalue()
 def test_private_roundtrip_and_real_sqlite(self):
  manifest,data=N['checked_members'](self.raw,SOURCE)
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'received';N['install_private'](root,data)
   c=sqlite3.connect((root/'project'/SOURCE['DB']).as_uri()+'?mode=ro',uri=True)
   self.assertEqual(c.execute('pragma integrity_check').fetchall(),[('ok',)]);c.close()
   self.assertEqual(len(data),165)
 def test_wire_hash_and_length(self):
  b=b'fixture';wire=gzip.compress(b);h={'wire_bytes':len(wire),'wire_sha256':N['sha'](wire),'tar_bytes':len(b),'tar_sha256':N['sha'](b)}
  self.assertEqual(N['decompress_checked'](wire,h),b)
  with self.assertRaisesRegex(RuntimeError,'WIRE_DIGEST'):N['decompress_checked'](wire+b'x',h)
 def test_expansion_bound(self):
  from unittest.mock import patch
  wire=gzip.compress(b'x'*100);h={'wire_bytes':len(wire),'wire_sha256':N['sha'](wire),'tar_bytes':100,'tar_sha256':N['sha'](b'x'*100)}
  with patch.dict(N['decompress_checked'].__globals__,MAX_RAW=10):
   with self.assertRaisesRegex(RuntimeError,'ARCHIVE_DIGEST'):N['decompress_checked'](wire,h)
 def test_traversal_rejected_before_extract(self):
  raw=self.archive({},extra='../escape')
  with self.assertRaisesRegex(RuntimeError,'MEMBER_REJECTED'):N['checked_members'](raw,SOURCE)
 def test_duplicate_rejected(self):
  raw=self.archive({},extra='PRIVATE_MANIFEST.json')
  with self.assertRaisesRegex(RuntimeError,'MEMBER_REJECTED'):N['checked_members'](raw,SOURCE)
 def test_tampered_manifest(self):
  raw=self.archive({'project/'+SOURCE['DB']:b'fixture'},tamper=True)
  with self.assertRaisesRegex(RuntimeError,'MATERIAL_MANIFEST'):N['checked_members'](raw,SOURCE)
 def test_existing_destination_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'keep').write_text('original')
   with self.assertRaisesRegex(RuntimeError,'DIRECTORY_EXISTS'):N['install_private'](root,{})
   self.assertEqual((root/'keep').read_text(),'original')
if __name__=='__main__':unittest.main()
