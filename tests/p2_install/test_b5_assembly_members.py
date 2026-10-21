"""Synthetic selection fixtures; never execute archived SDK/parser."""
import hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
mod=load('four',ROOT/'scripts/p2_b5_assembly_members.py')
class FourMembers(unittest.TestCase):
 def setUp(self):
  self.original=mod.TARGETS;self.raw={n:b'x'*p['bytes'] for n,p in self.original.items()};mod.TARGETS={n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in self.raw.items()};self.rows={'root/'+n:dict(p) for n,p in mod.TARGETS.items()};self.reads=[]
 def tearDown(self):mod.TARGETS=self.original
 def get(self,n):self.reads.append(n);return self.raw[n[len('root/'):]]
 def analyze(self):return mod.analyze(self.rows,self.get,'root/',None,None)
 def test_exact_four_no_recursion(self):
  self.rows['root/unrelated.mjs']={'bytes':1,'sha256':'0'*64};report,selected=self.analyze();self.assertEqual(set(selected),set(mod.TARGETS));self.assertEqual(self.reads,['root/'+n for n in sorted(mod.TARGETS)]);self.assertEqual(sum(map(len,selected.values())),46229);self.assertEqual(report['owner_binding'],'UNBOUND')
 def test_missing_rejected_before_any_read(self):
  self.rows.pop('root/'+sorted(mod.TARGETS)[-1])
  with self.assertRaisesRegex(ValueError,'MEMBER_ABSENT'):self.analyze()
  self.assertEqual(self.reads,[])
 def test_all_manifest_pins_before_any_read(self):
  for key,value in [('bytes',1),('sha256','0'*64)]:
   row=self.rows['root/'+sorted(mod.TARGETS)[-1]];old=row[key];row[key]=value
   with self.assertRaisesRegex(ValueError,'MANIFEST_FIXED_PIN'):self.analyze()
   row[key]=old
  self.assertEqual(self.reads,[])
 def test_content_tamper_stops(self):
  n=sorted(mod.TARGETS)[0];self.raw[n]=b'y'*len(self.raw[n])
  with self.assertRaisesRegex(ValueError,'CONTENT_SHA'):self.analyze()
  self.assertEqual(self.reads,['root/'+n])
 def test_count_and_total_fixed(self):
  n=next(iter(mod.TARGETS));mod.TARGETS=dict(mod.TARGETS);mod.TARGETS.pop(n)
  with self.assertRaisesRegex(ValueError,'SELECTION_BOUND'):self.analyze()
  self.assertEqual(self.reads,[])
 def test_real_metadata_bundle_command_resources(self):
  meta=json.loads((ROOT/'docs/p2-b5-20261020/assembly-four-candidate.json').read_text());self.assertEqual(meta['selected_members'],self.original);self.assertEqual(meta['selected_bytes'],46229)
  boot=load('four_boot',ROOT/'scripts/p2_b5_assembly_bootstrap.py');rows=boot.unpack();self.assertEqual(rows['scripts/p2_b5_assembly_members.py'],(ROOT/'scripts/p2_b5_assembly_members.py').read_bytes());self.assertNotIn('scripts/p2_b5_shutdown_member.py',rows)
  for file,pin in [('scripts/p2_b5_assembly_bootstrap.py','bootstrap_sha256'),('docs/p2-b5-20261020/assembly-four.command','command_sha256')]:self.assertEqual(hashlib.sha256((ROOT/file).read_bytes()).hexdigest(),meta[pin])
  b=(ROOT/'scripts/p2_b5_assembly_bootstrap.py').read_bytes();self.assertEqual(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),meta['bootstrap_git_blob'])
  base=mod.load_base();self.assertEqual(base.MAX_SELECTED,16*1024*1024);self.assertEqual(base.MAX_REPORT,2*1024*1024);self.assertEqual(base.OUTPUT,'p2-b5-assembly-four-members-v1-20261021')
 def test_failure_keeps_partial_and_exclusive_outputs(self):
  base=mod.load_base()
  class Reader:
   PINS={};ROOT='root/';Hold=ValueError
   @staticmethod
   def select_files(*args):raise ValueError('FULL_SOURCE_HASH_FAILURE')
  with tempfile.TemporaryDirectory() as d:
   fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
   try:
    p=Path(d,'materials.tar');p.write_bytes(b'prior partial');self.assertEqual(base.run(-1,-1,fd,Reader,[],None),2);self.assertEqual(p.read_bytes(),b'prior partial')
    with self.assertRaises(FileExistsError):base.write_new(fd,'materials.tar',b'overwrite')
   finally:os.close(fd)
 def test_source_reference_lf_correction(self):
  b=(ROOT/'evidence/p2-b5-convergence-20261021/installation-prerequisites.json').read_bytes();e=json.loads((ROOT/'evidence/p2-b5-public-assembly-20261021/source-reference-resolution.json').read_text());c=e['correction']['source_reference_correction'];self.assertEqual(hashlib.sha256(b).hexdigest(),c['canonical_sha256']);self.assertEqual(hashlib.sha256(b+b'\n').hexdigest(),c['prior_claimed_sha256']);self.assertEqual(len(b),82903);self.assertEqual(c['canonical_git_blob'],hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest())
if __name__=='__main__':unittest.main()
