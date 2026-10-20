"""Synthetic archive tests only, never UK data or a runtime tree."""
import ast,hashlib,importlib.util,io,json,os,stat,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
SCRIPT=Path(__file__).resolve().parents[2]/'scripts/p2_b5_three_files.py'
spec=importlib.util.spec_from_file_location('three',str(SCRIPT));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def hash_(b):return hashlib.sha256(b).hexdigest()
class ThreeTests(unittest.TestCase):
 def root(self):
  t=tempfile.TemporaryDirectory(dir='/root',prefix='b5-three-test-');self.addCleanup(t.cleanup);return Path(t.name)
 def fixture(self,extra=None,kind=None,duplicate=False,long=False,finish=True,malicious_pax=None,format_=tarfile.PAX_FORMAT):
  selected={'package.json':b'{"version":"fixture"}', 'dist/loader-runtime-load-DpgEqnzx.mjs':b'export const fixture=1;', 'dist/context-DyPstb2Q.mjs':b'export{}'}
  files={m.ROOT+k:v for k,v in selected.items()};files['usr/lib64/fixture.so']=b'not executed'
  if long:files[m.ROOT+'nested/'+('a'*120)+'/unicode-'+('\u6d4b'*20)+'.mjs']=b'long-name'
  if extra:files.update(extra)
  buf=io.BytesIO();rows=[]
  with tarfile.open(fileobj=buf,mode='w',format=format_) as tar:
   for i,(name,raw) in enumerate(files.items()):
    info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o600;info.uid=info.gid=os.getuid();info.mtime=0
    if i==0 and kind:info.type=kind;info.linkname='outside'
    if i==0 and malicious_pax:info.pax_headers=malicious_pax
    tar.addfile(info,io.BytesIO(raw))
    if duplicate and i==0:tar.addfile(info,io.BytesIO(raw))
    rows.append({'path':'/'+name,'bytes':len(raw),'sha256':hash_(raw),'uid':os.getuid(),'gid':os.getuid(),'mode':0o600,'kind':'fixture'})
  rawtar=buf.getvalue()
  if not finish:
   # Compute the exact full-member boundary, excluding tar end marker/padding.
   with tarfile.open(fileobj=io.BytesIO(rawtar),mode='r:') as tar:
    members=tar.getmembers();last=members[-1];end=last.offset_data+((last.size+511)//512)*512
   rawtar=rawtar[:end]
  manifest=m.encoded({'scope':'ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT','files':rows,'files_count':len(rows),'bytes':sum(len(v) for v in files.values())})
  root=self.root();a=root/'source.tar';a.write_bytes(rawtar);mfile=root/'manifest.json';mfile.write_bytes(manifest);out=root/'output';out.mkdir(mode=0o700)
  pins={'tar_bytes':len(rawtar),'tar_sha256':hash_(rawtar),'manifest_bytes':len(manifest),'manifest_sha256':hash_(manifest),'members':len(rows),'targets':{k:(len(v),hash_(v)) for k,v in selected.items()}}
  return root,a,mfile,out,pins,selected
 def select(self,fixture,checkpoint=None):
  _,a,mf,_,pins,_=fixture
  with a.open('rb') as x,mf.open('rb') as y:return m.select_files(x.fileno(),y.fileno(),pins,checkpoint)
 def test_correct_all_content_and_only_three_payloads(self):
  f=self.fixture();selected,e=self.select(f);self.assertEqual(selected,f[-1]);self.assertEqual(e['members_verified'],4);self.assertTrue(e['all_members_content_sha_verified']);raw=m.small_archive(selected);self.assertLess(len(raw),m.MAX_SMALL)
  with tarfile.open(fileobj=io.BytesIO(raw)) as tar:self.assertEqual(set(tar.getnames()),set(selected));self.assertTrue(all(x.isfile() for x in tar.getmembers()))
 def replace_tar(self,f,raw):
  f[1].write_bytes(raw);f[4].update(tar_bytes=len(raw),tar_sha256=hash_(raw));return f
 def header_change(self,raw,offset,field,value):
  raw=bytearray(raw);h=raw[offset:offset+512];h[field:field+len(value)]=value;h[148:156]=b' '*8;h[148:156]=('%06o\0 '%sum(h)).encode();raw[offset:offset+512]=h;return bytes(raw)
 def test_prior_failure_readback_is_bound_and_immutable(self):
  root=self.root();old=root/'p2-b5-three-files-20261020';old.mkdir(mode=0o700)
  host=m.encoded({'state':'HOLD','error':'CHILD_FAILED_RETAIN_OUTPUT'});receipt=m.encoded({'state':'HOLD','error':'TAR_FORMAT'})
  for name,raw in [('host-result.json',host),('receipt.json',receipt)]:
   (old/name).write_bytes(raw);(old/name).chmod(0o600)
  fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
  try:
   with self.assertRaisesRegex(m.Hold,'PRIOR_HOST_RESULT_BINDING'):m.prior_failure(fd,os.getuid())
   original=m.sha
   with patch.object(m,'sha',side_effect=lambda raw:'e40abcd5304e4ab0e29c83a4865528272aca2b0ddb97e6d3df8d9941544c3bd6' if raw==host else original(raw)):
    result=m.prior_failure(fd,os.getuid());self.assertEqual(result['receipt.json']['error'],'TAR_FORMAT')
   self.assertEqual((old/'receipt.json').read_bytes(),receipt);self.assertEqual((old/'host-result.json').read_bytes(),host)
   (old/'receipt.json').unlink();(old/'receipt.json').symlink_to(old/'host-result.json')
   with patch.object(m,'sha',side_effect=lambda raw:'e40abcd5304e4ab0e29c83a4865528272aca2b0ddb97e6d3df8d9941544c3bd6' if raw==host else original(raw)):
    with self.assertRaises(OSError):m.prior_failure(fd,os.getuid())
  finally:os.close(fd)
 def test_python36_default_gnu_regular_and_long_unicode(self):
  # CPython v3.6.8 Lib/tarfile.py DEFAULT_FORMAT=GNU_FORMAT.
  # Explicit GNU reproduces its writer without relying on a newer default.
  for long in (False,True):
   f=self.fixture(long=long,format_=tarfile.GNU_FORMAT);selected,e=self.select(f)
   self.assertEqual(selected,f[-1]);self.assertEqual(e['members_verified'],5 if long else 4)
 def test_gnu_longname_utf8_split_at_byte100(self):
  f=self.fixture(extra={'x'*99+'测'*4:b'unicode'},format_=tarfile.GNU_FORMAT)
  self.assertEqual(self.select(f)[1]['members_verified'],5)
 def test_gnu_special_extensions_and_oldgnu_fields_rejected(self):
  for kind in (b'K',b'S',b'g',b'X',b'1',b'2',b'3',b'4',b'5',b'6',b'7'):
   f=self.fixture(format_=tarfile.GNU_FORMAT);raw=self.header_change(f[1].read_bytes(),0,156,kind)
   with self.assertRaises(m.Hold):self.select(self.replace_tar(f,raw))
  for field in (345,369,386,482,500):
   f=self.fixture(format_=tarfile.GNU_FORMAT);raw=self.header_change(f[1].read_bytes(),0,field,b'1')
   with self.assertRaisesRegex(m.Hold,'GNU_EXTENSION_NOT_ALLOWED'):self.select(self.replace_tar(f,raw))
 def test_gnu_longname_payload_rejects_unsafe_or_unbounded(self):
  for raw in (b'a',b'a\0b\0',b'../escape\0',b'/absolute\0',b'a//b\0',b'a\\b\0',b'x'*4097+b'\0'):
   with self.assertRaises(m.Hold):m.gnu_path(raw)
 def test_gnu_nested_mixed_dangling_and_fallback_rejected(self):
  f=self.fixture(long=True,format_=tarfile.GNU_FORMAT);raw=f[1].read_bytes()
  offset=0
  while raw[offset+156:offset+157]!=b'L':
   size=int(raw[offset+124:offset+136].strip(b'\0 '),8);offset+=512+((size+511)//512)*512
  size=int(raw[offset+124:offset+136].strip(b'\0 '),8);following=offset+512+((size+511)//512)*512
  cases=[self.header_change(raw,following,257,b'ustar\000'),
         self.header_change(raw,following,156,b'L'),
         self.header_change(raw,following,0,b'bad'),raw[:following],
         self.header_change(raw,offset,124,b'00000010002\0')]
  # payload's final NUL is mandatory, even with a recomputed outer digest.
  bad=bytearray(raw);bad[offset+512+size-1]=65;cases.append(bytes(bad))
  for changed in cases:
   with self.assertRaises(m.Hold):self.select(self.replace_tar(f,changed))
 def test_gnu_all_contents_and_boundary_still_checked(self):
  f=self.fixture(long=True,format_=tarfile.GNU_FORMAT,finish=False)
  self.assertEqual(self.select(f)[1]['source_tar_termination'],'MEMBER_BOUNDARY_EOF')
  raw=f[1].read_bytes().replace(b'not executed',b'NOT executed')
  with self.assertRaisesRegex(m.Hold,'TAR_MEMBER_CONTENT_SHA'):self.select(self.replace_tar(f,raw))
 def test_full_tar_and_manifest_digest_mismatch(self):
  for key in ('tar_sha256','manifest_sha256'):
   f=self.fixture();f[4][key]='0'*64
   with self.assertRaisesRegex(m.Hold,'SHA'):self.select(f)
 def test_nonselected_member_content_is_also_hashed(self):
  f=self.fixture();raw=f[1].read_bytes().replace(b'not executed',b'NOT executed');f[1].write_bytes(raw);f[4]['tar_sha256']=hash_(raw)
  with self.assertRaisesRegex(m.Hold,'TAR_MEMBER_CONTENT_SHA'):self.select(f)
 def test_duplicate_and_link_special_sparse_rejected(self):
  with self.assertRaisesRegex(m.Hold,'DUPLICATE_TAR_MEMBER'):self.select(self.fixture(duplicate=True))
  for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.FIFOTYPE,tarfile.CHRTYPE,tarfile.GNUTYPE_SPARSE):
   with self.assertRaises(m.Hold):self.select(self.fixture(kind=kind))
 def test_real_pax_long_unicode_paths_supported(self):
  _,e=self.select(self.fixture(long=True));self.assertEqual(e['members_verified'],5)
 def test_malicious_pax_keys_and_traversal_rejected(self):
  for key in ('size','GNU.sparse.map','SCHILY.xattr.user.foo'):
   with self.assertRaises(m.Hold):self.select(self.fixture(malicious_pax={key:'1'}))
  for value in ('../escape','/absolute','a//b','a/./b','a\\b'):
   with self.assertRaises(m.Hold):m.pax_path(('%d path=%s\n'%(len(value)+9,value)).encode())
 def test_member_boundary_without_end_marker_is_explicit(self):
  _,e=self.select(self.fixture(finish=False));self.assertEqual(e['source_tar_termination'],'MEMBER_BOUNDARY_EOF')
 def test_trailing_nonzero_data_rejected(self):
  f=self.fixture();raw=f[1].read_bytes()+b'x'*512;f[1].write_bytes(raw);f[4].update(tar_bytes=len(raw),tar_sha256=hash_(raw))
  with self.assertRaisesRegex(m.Hold,'TAR_TRAILING_DATA'):self.select(f)
 def test_truncated_member_rejected(self):
  f=self.fixture(finish=False);raw=f[1].read_bytes()[:-512];f[1].write_bytes(raw);f[4].update(tar_bytes=len(raw),tar_sha256=hash_(raw))
  with self.assertRaises(m.Hold):self.select(f)
 def test_manifest_metadata_and_set_mismatch(self):
  f=self.fixture();obj=json.loads(f[2].read_text());obj['files'][-1]['uid']+=1;raw=m.encoded(obj);f[2].write_bytes(raw);f[4].update(manifest_bytes=len(raw),manifest_sha256=hash_(raw))
  with self.assertRaisesRegex(m.Hold,'TAR_METADATA'):self.select(f)
 def test_source_mutation_after_hash_rejected(self):
  f=self.fixture()
  def mutate(event):
   if event=='HASHED':os.utime(str(f[1]),ns=(1000000000,1000000000))
  with self.assertRaisesRegex(m.Hold,'SOURCE_CHANGED'):self.select(f,mutate)
 def test_nofollow_parent_leaf_and_path_replacement(self):
  root=self.root();(root/'data').write_bytes(b'abc');p=m.PinnedFile(str(root/'data'),(os.getuid(),));self.addCleanup(p.close);(root/'data').rename(root/'old');(root/'data').write_bytes(b'abc')
  with self.assertRaisesRegex(m.Hold,'INPUT_(FD|PATH)_CHANGED'):p.check()
  (root/'alias').symlink_to(root/'data')
  with self.assertRaises(OSError):m.PinnedFile(str(root/'alias'),(os.getuid(),))
 def test_no_overwrite_and_private_output(self):
  f=self.fixture();fd=os.open(str(f[3]),os.O_RDONLY|os.O_DIRECTORY)
  try:
   m.write_new(fd,'sentinel',b'prior')
   with self.assertRaises(FileExistsError):m.write_new(fd,'sentinel',b'replace')
   os.chmod(str(f[3]),0o755)
   with f[1].open('rb') as a,f[2].open('rb') as b:
    with self.assertRaisesRegex(m.Hold,'OUTPUT_UID_OR_MODE'):m.run(a.fileno(),b.fileno(),fd,f[4])
  finally:os.close(fd)
  self.assertEqual((f[3]/'sentinel').read_bytes(),b'prior')
 def test_failed_validation_keeps_receipt_and_inputs(self):
  f=self.fixture();original=[p.read_bytes() for p in f[1:3]];f[4]['tar_sha256']='0'*64;fd=os.open(str(f[3]),os.O_RDONLY|os.O_DIRECTORY)
  try:
   with f[1].open('rb') as a,f[2].open('rb') as b:self.assertEqual(m.run(a.fileno(),b.fileno(),fd,f[4]),2)
  finally:os.close(fd)
  self.assertEqual([p.read_bytes() for p in f[1:3]],original);self.assertFalse((f[3]/'three-files.tar').exists());self.assertEqual(json.loads((f[3]/'receipt.json').read_text())['error'],'TAR_SHA')
 def test_interrupted_write_leaves_partial_no_false_receipt(self):
  f=self.fixture();fd=os.open(str(f[3]),os.O_RDONLY|os.O_DIRECTORY)
  try:
   original=m.write_new
   def interrupted(directory,name,raw):
    if name=='three-files.tar':original(directory,name,raw[:512]);raise KeyboardInterrupt()
    original(directory,name,raw)
   with f[1].open('rb') as a,f[2].open('rb') as b,patch.object(m,'write_new',interrupted):
    with self.assertRaises(KeyboardInterrupt):m.run(a.fileno(),b.fileno(),fd,f[4])
  finally:os.close(fd)
  self.assertEqual((f[3]/'three-files.tar').stat().st_size,512);self.assertFalse((f[3]/'receipt.json').exists())
 def test_full_20000_member_scale(self):
  f=self.fixture(extra={m.ROOT+'fixtures/'+('a'*110)+'/m%05d.mjs'%i:b'' for i in range(19996)},format_=tarfile.GNU_FORMAT)
  _,e=self.select(f);self.assertEqual(e['members_verified'],20000);self.assertTrue(e['all_members_content_sha_verified'])
 def test_parent_small_readback_rejects_tamper(self):
  f=self.fixture();selected,_=self.select(f);p=f[0]/'small.tar';raw=m.small_archive(selected);p.write_bytes(raw)
  with p.open('rb') as stream:self.assertEqual(m.verify_small(stream.fileno(),f[4]),sum(map(len,selected.values())))
  p.write_bytes(raw.replace(b'export{}',b'EXPORT{}'))
  with p.open('rb') as stream:
   with self.assertRaisesRegex(m.Hold,'SMALL_CONTENT_SHA'):m.verify_small(stream.fileno(),f[4])
 def test_actual_uid_child_uses_only_input_and_output_fds(self):
  f=self.fixture()
  try:os.chown(str(f[3]),1002,1002)
  except OSError:
   if os.environ.get('B5_REQUIRE_UID')=='1':raise
   self.skipTest('local chown unavailable; mandatory Hosted UID test')
  out=os.open(str(f[3]),os.O_RDONLY|os.O_DIRECTORY)
  with f[1].open('rb') as a,f[2].open('rb') as b:
   pid=os.fork()
   if pid==0:
    try:os.setgroups([]);os.setgid(1002);os.setuid(1002);os._exit(m.run(a.fileno(),b.fileno(),out,f[4]))
    except BaseException:os._exit(3)
   _,status=os.waitpid(pid,0)
  os.close(out);self.assertEqual(status,0);self.assertEqual((f[3]/'three-files.tar').stat().st_uid,1002);self.assertEqual(f[0].stat().st_mode&0o777,0o700)
 def test_real_sigkill_preserves_partial_output_and_inputs(self):
  f=self.fixture();before=[hash_(p.read_bytes()) for p in f[1:3]];out=os.open(str(f[3]),os.O_RDONLY|os.O_DIRECTORY);original=m.write_new
  with f[1].open('rb') as a,f[2].open('rb') as b:
   pid=os.fork()
   if pid==0:
    def stop_during_write(directory,name,raw):
     if name=='three-files.tar':original(directory,name,raw[:512]);os.kill(os.getpid(),9)
     original(directory,name,raw)
    m.write_new=stop_during_write;m.run(a.fileno(),b.fileno(),out,f[4]);os._exit(4)
   _,status=os.waitpid(pid,0)
  os.close(out);self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),9);self.assertEqual((f[3]/'three-files.tar').stat().st_size,512);self.assertFalse((f[3]/'receipt.json').exists());self.assertEqual([hash_(p.read_bytes()) for p in f[1:3]],before)
 def test_pax_duplicate_path_rejected(self):
  def record(value):
   body=b'path='+value+b'\n';n=len(body)+2
   while len(str(n))+1+len(body)!=n:n=len(str(n))+1+len(body)
   return str(n).encode()+b' '+body
  with self.assertRaisesRegex(m.Hold,'PAX_KEY_NOT_ALLOWED'):m.pax_path(record(b'safe')+record(b'safe'))
 def test_production_sizes_fit_one_mib_envelope(self):
  selected={name:b'x'*spec[0] for name,spec in m.PINS['targets'].items()}
  self.assertEqual(sum(map(len,selected.values())),419045);self.assertLess(len(m.small_archive(selected)),1024*1024)
 def test_explicit_parser_and_output_bounds(self):
  f=self.fixture();f[4]['tar_bytes']=m.MAX_TAR+512
  with self.assertRaisesRegex(m.Hold,'TAR_BOUND'):self.select(f)
  f=self.fixture()
  with patch.object(m,'MAX_MEMBERS',3):
   with self.assertRaisesRegex(m.Hold,'MANIFEST_COUNT'):self.select(f)
  with patch.object(m,'MAX_SMALL',1):
   with self.assertRaisesRegex(m.Hold,'SMALL_ARCHIVE_BOUND'):m.small_archive(f[-1])
 def test_python36_no_network_runtime_or_extractall(self):
  raw=SCRIPT.read_text();ast.parse(raw,feature_version=(3,6));self.assertNotIn('import subprocess',raw);self.assertNotIn('urllib',raw);self.assertNotIn('.extractall(',raw)
  r=subprocess.run([sys.executable,'-I','-B','-S',str(SCRIPT)],stdout=subprocess.PIPE);self.assertEqual(r.returncode,2);self.assertIn(b'FIXED_HOST_ROOT_REQUIRED',r.stdout)
if __name__=='__main__':unittest.main()
