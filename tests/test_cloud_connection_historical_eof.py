import sys,pathlib,importlib.util,unittest,io,tarfile,tempfile,hashlib,os,json,base64,types,ast
from unittest.mock import patch
R=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from production.cloud_connection.private_transfer import stamp
from production.cloud_connection import archive_reader as ar, fixed_actions as fa
# Historical non-secret scope metadata only; no live source bodies or config.
CODE_PIN = 'f85fdb173b93729ee070ee4285d8ece4d85499b3dd8e4ac7c9894a9ce6058cee'
RECIPIENT = 'github-332398908'
PROJECT = 'p2-b5-material-analysis'
ARCHIVE_ROOT = '/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002'
PACKAGE_ROOT = '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
ARCHIVE_PREFIX = 'home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/'
ARCHIVE_SHA256 = 'e6d3a3cef96ee996eb4b130fb0bd9305438489326b85678a263998602413e485'
ARCHIVE_IDENTITY = (64771, 1845773, 33152, 1002, 1002, 1, 559237632, 1792487297836456594, 1792487297836456594)
EXACT_OBJECTS = (('dist/server-active-work-Bhfd47cA.mjs', 150, 'eff213117811b9237933a2148524605d0acd5f397a0344b78f48de07d51599b4'), ('dist/server-shutdown.runtime.js', 56, 'd479328d6a6d9a59cae80ae11bf91fb37ef193ad3bb75afb9ff5d6f7f78e5ece'), ('dist/server-startup-config-helpers-U6xkM_57.mjs', 137, '05234c987220249a923175b49d20d7edc5f49c091272fbdca2a2f151e9aae765'), ('dist/server-startup-early-BLUjqlAE.mjs', 4816, '1d457bf7c8373bc3f37acaa9039b588efa4e24a46d9d3d15751d88d84fa3b551'), ('dist/server-startup-post-attach-CsYAFanV.mjs', 53969, 'b62aa11d48ecedddf1b606f33114cdde8faf7fc193305eafddb918427024de22'), ('node_modules/@openclaw/fs-safe/package.json', 6870, '69241330487f571a0daf239e704dc82876227273bbea27b158cdf6f5e2181430'), ('node_modules/@openclaw/proxyline/package.json', 2318, '480f764c4f1c9fddd8274cea03ff44d896fe2d449e3b26d2ad9e0e6ef0265940'), ('node_modules/acorn/package.json', 1067, '5c1ed7259579a7899b303f514b0194adcb9fe474fc7d136a84c6a45f10eefc84'), ('node_modules/chalk/package.json', 1743, '5a853fc6dc0c529bc126f97645989e9d60d06a2e9b20f66a6b48b0e8ef9da3ef'), ('node_modules/commander/package.json', 1634, '6ea3e19871a9a05fa0c8b89595b6df05d23d266936b9785607128fd420864337'), ('node_modules/dotenv/package.json', 1752, 'f9783156e628b56d047138307f34007dd7c8e4122da2bd339799a95726f8acc3'), ('node_modules/execa/package.json', 3064, 'fda71910ec57173f450b88928ad3e91e24798c6b035e4d898682e12b6bdd73a5'), ('node_modules/import-meta-resolve/package.json', 2237, '41e75cac3cc4460b5e442cd4ab60907ba24a01b8a081c3fd8a84371b8f76d39b'), ('node_modules/json5/package.json', 1916, '1927c4592e3811cf9b8c86e568df1c41a373b628b4b322f88872395ef87e2ba5'), ('node_modules/p-limit/package.json', 1055, 'daa6b0d168d7197eccbfef1c678e8f00b79d063129bf48f4ee2db38dc605ca7f'), ('node_modules/semver/package.json', 1661, '7c94cb7f2a53c27b20d76386ec144c062894dbcc909cfabd0f728c37874b1776'), ('node_modules/tslog/package.json', 3872, 'ad14ef4bc8e740b741ff17fefa9189ad31450c2b8823d012a136c91a8c4b45ee'), ('node_modules/typebox/package.json', 2021, 'ee6da2e605b83e99f70dd12866e09e6c054921b034671d063d42cd0895547fd3'), ('node_modules/yaml/package.json', 3254, '1c6441703d8204a23ded0d37ddf57c3b69d821dc392f20852d1f605bb9b8861c'))

def member(name,data):
 i=tarfile.TarInfo(name);i.size=len(data);i.mode=0o600;return i.tobuf(format=tarfile.GNU_FORMAT)+data+b'\0'*((-len(data))%512)
def exact():
 plan=dict(filename='source-tree.tar.pending',identity=list(ARCHIVE_IDENTITY),member_prefix=ARCHIVE_PREFIX,max_headers=65536,max_read_bytes=32*1024*1024,sha256=ARCHIVE_SHA256)
 items=[dict(ref='b5-material-%02d'%(i+1),root_ref='b5-original-archive',relative_path=p,bytes=n,sha256=h) for i,(p,n,h) in enumerate(EXACT_OBJECTS[:5])];return plan,items
class Tests(unittest.TestCase):
 def test_exact_historical_gate(self):
  p,i=exact();self.assertTrue(ar.historical_member_boundary(p,i));self.assertTrue(ar.historical_member_boundary(p,i[:1]))
 def test_gate_wrong_plan(self):
  p,i=exact()
  for k,v in [('sha256','0'*64),('filename','other.tar'),('member_prefix','')]:
   q=dict(p);q[k]=v;self.assertFalse(ar.historical_member_boundary(q,i))
  for idx in (3,6):
   q=dict(p,identity=list(p['identity']));q['identity'][idx]+=1;self.assertFalse(ar.historical_member_boundary(q,i))
 def test_gate_wrong_object(self):
  p,i=exact()
  for k,v in [('relative_path','other'),('bytes',151),('sha256','0'*64)]:
   a=dict(i[0]);a[k]=v;self.assertFalse(ar.historical_member_boundary(p,[a]))
 def read(self,raw,historical):
  data=b'A'*150
  with tempfile.TemporaryDirectory(prefix='eof-synthetic-') as d:
   f=pathlib.Path(d)/'fixture.tar';f.write_bytes(raw);f.chmod(0o600)
   plan=dict(filename=f.name,identity=list(stamp(f.stat())),member_prefix='',max_headers=100,max_read_bytes=65536,sha256=hashlib.sha256(raw).hexdigest())
   item=dict(ref='test',relative_path='target',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   with patch.object(ar,'historical_member_boundary',return_value=historical),patch.object(ar,'directory',side_effect=lambda *a:os.open(d,os.O_RDONLY|os.O_DIRECTORY)):
    return ar.read_archive_members(d,os.getuid(),[item],plan)
 def test_complete_boundary_selected_last(self):self.assertEqual(self.read(member('target',b'A'*150),True)['test'],b'A'*150)
 def test_complete_boundary_unselected_last(self):self.assertIn('test',self.read(member('target',b'A'*150)+member('other',b'B'*1024),True))
 def test_normal_mode_still_rejects_boundary(self):
  with self.assertRaises(ar.Hold):self.read(member('target',b'A'*150),False)
 def test_partial_rejected(self):
  base=member('target',b'A'*150)
  for tail in (b'X'*100,b'X'*512,member('other',b'B'*1024)[:-512],b'\0'*512):
   with self.subTest(length=len(tail)):
    with self.assertRaises((ar.Hold,tarfile.TarError)):self.read(base+tail,True)
 def test_normal_eof_retained(self):
  for hist in (False,True):self.assertIn('test',self.read(member('target',b'A'*150)+b'\0'*1024,hist))
 def test_gnu_longlink_complete_and_partial(self):
  base=member('target',b'A'*150);long=member('long-'+('x'*150),b'B'*700)
  self.assertIn('test',self.read(base+long,True))
  for cut in (512,600,1024,len(long)-512):
   with self.subTest(cut=cut):
    with self.assertRaises((ar.Hold,tarfile.TarError)):self.read(base+long[:cut],True)
 def test_command_budget_and_dependencies(self):
  p,items=exact();items += [dict(ref='b5-material-%02d'%(i+6),root_ref='b5-original-packages',relative_path=v[0],bytes=v[1],sha256=v[2]) for i,v in enumerate(EXACT_OBJECTS[5:])];policy=object.__new__(fa.ApprovedObjectsPolicy)
  policy.binding={'roots':{'b5-original-archive':[ARCHIVE_ROOT,1002],'b5-original-packages':[PACKAGE_ROOT,1002]},'archives':{'b5-original-archive':p},'requests':{x['ref']:'l2-b5-b5-material-e78-20261023-%02d'%(j+1) for j,x in enumerate(items)},'recipient_id':RECIPIENT,'execution_uid':0,'execution_user':'root','reader_sha256':hashlib.sha256((R/'production/cloud_connection/private_transfer.py').read_bytes()).hexdigest(),'archive_reader_sha256':hashlib.sha256((R/'production/cloud_connection/archive_reader.py').read_bytes()).hexdigest()}
  policy.catalog=types.SimpleNamespace(objects={x['ref']:x for x in items},sha='a'*64,value=dict(project=PROJECT,executor_sha256=CODE_PIN,valid_from=1792725835,valid_until=1792729435))
  sizes=[]
  for x in items:
   req=dict(schema=1,request_id=policy.binding['requests'][x['ref']],project=PROJECT,target='uk',operation='fetch_approved_object',executor_sha256=CODE_PIN,arguments=dict(manifest_sha256='a'*64,object_ref=x['ref'],recipient_id=RECIPIENT),expires_unix=1792729435)
   c=policy.command(req);sizes.append(len(base64.b64encode(c['CommandContent'].encode())))
  self.assertLessEqual(max(sizes),16384);print('synthetic_command_max_encoded',max(sizes))
if __name__=='__main__':unittest.main()
