"""Prepare exact adopted core plan, no production apply."""
import os,sys,json,hashlib,stat,subprocess,base64,copy,socket
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
B='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
ROOT=os.environ['P2_REVIEW_ROOT']+'/xuanjun-p2-package'
RUN=sys.argv[1]
SOURCE='8743a953a2f92ecbf515ecaa6609c50993f4ac74';TREE='7c41607186e5ebc66003344a245742c0ba8d0315';MANIFEST='44ede26d72bbb776dc813d6eb4d057581e11440d17082a6f1a207fc377689b0a'
OLD='2b49066f37742dedd41657fb445c91f4204fd4a2a257f921dd9fd514e5b25f0e'
def read(p,expected=None):
 assert os.path.realpath(p)==p
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());r=f.read(1048577);assert s.st_uid==0 and stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600 and len(r)<=1048576
 if expected:assert hashlib.sha256(r).hexdigest()==expected
 return r
def h(r):return hashlib.sha256(r).hexdigest()
def pack(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def write(p,r):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(r);f.flush();os.fsync(f.fileno())
original=B+'/plan-p2pkg-38420216343-1/protected-core-install-plan.json'
p=json.loads(read(original,'6a7789a023d0cbb265663275ee7442fdd026eaaee0fc4ee4a0f237ec5a62e970'))
with open(ROOT+'/deploy/integration-manifest.json','rb') as f:mraw=f.read()
assert h(mraw)==MANIFEST
for rel,sha in json.loads(mraw)['files'].items():
 with open(ROOT+'/'+rel,'rb') as f:
  s=os.fstat(f.fileno());assert s.st_uid==0 and not s.st_mode&0o022
  assert h(f.read())==sha
d=B+'/adopted-core-plan-'+RUN;os.mkdir(d,0o700);os.mkdir(d+'/private-bootstrap',0o700)
oldrelease='integration-'+OLD[:16];release='integration-'+MANIFEST[:16]
changes=[(OLD,MANIFEST),('62d2e64d34feea1f02bffa7e8b597484bb98307f',SOURCE),('e75e549d87515aee1c022faa04e805f694088d6e',TREE),(oldrelease,release),('/tmp/p2pkg-38420216343-1/xuanjun-p2-package',ROOT)]
def replace(v):
 if isinstance(v,str):
  for a,b in changes:v=v.replace(a,b)
  return v
 if isinstance(v,list):return [replace(x) for x in v]
 if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
 return v
oldboot=p['runtime']['bootstrap'];boot=json.loads(read(oldboot['path'],oldboot['sha256']))
p=replace(p);rendered={}
for row in p['runtime']['provisioning']:
 with open(ROOT+'/'+row['source'],'rb') as f:raw=f.read()
 row['source_sha256']=h(raw)
 for token in list(row['replacements']):
  if token=='@@LEDGER_BRIDGE_CONFIG_SHA256@@':row['replacements'][token]=h(rendered['/etc/xuanjun-development/p2-native-ledger-client.json'])
 data=raw
 for token,val in sorted(row['replacements'].items()):data=data.replace(token.encode(),val.encode())
 assert b'@@' not in data
 row['rendered_sha256']=h(data);rendered[row['target']]=data
p['activation']['config_sha256']=h(rendered['/etc/xuanjun-development/dispatcher.json'])
plugin=p['runtime']['plugin']
for k,target in [('binding_sha256','binding_file'),('ledger_client_sha256','ledger_client_config'),('gateway_relay_sha256','gateway_relay_config')]:plugin[k]=h(rendered[plugin[target]])
for i,row in enumerate(boot['files']):
 data=read(row['source'],row['sha256'])
 if row['target']=='/etc/xuanjun-development/p2-native-binding.json':
  data=replace(data.decode()).encode()
 target=d+'/private-bootstrap/bootstrap-'+str(i);write(target,data);row['source']=target;row['sha256']=h(data)
boot['artifact_id']=11833798542
bootpath=d+'/protected-bootstrap-candidate-receipt.json';bootraw=pack(boot);write(bootpath,bootraw)
p['runtime']['bootstrap']={'path':bootpath,'sha256':h(bootraw)}
pubpath=B+'/publisher-realm-'+RUN+'/protected-publisher-inputs.json'
pubraw=read(pubpath);pub=json.loads(pubraw);assert pub['source_commit']==SOURCE and pub['source_tree']==TREE
p['runtime']['publisher']={'path':pubpath,'sha256':h(pubraw),'source_commit':SOURCE,'source_tree':TREE}
D=B+'/legacy-isolation-'+p['transaction_id']
p['cutover']['legacy_isolation']={'directory':D,'receipt_sha256':'70d8e244f7f72c15a16299b9eef19670cd7cdee452b1913d864af93c2f4824bc','original_plan_path':original,'original_plan_sha256':'6a7789a023d0cbb265663275ee7442fdd026eaaee0fc4ee4a0f237ec5a62e970','legacy_state_sha256':'fe57912b31e42665a895a1e0d7c64fde5cebaff6a99394d0183a3fe3d95ab7c1','database_sha256':'a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'}
p['runtime']['legacy_cutover']=copy.deepcopy(p['cutover'])
p['runtime']['auxiliary_isolation']={'path':D+'/auxiliary-owner/auxiliary-isolation-receipt.json','sha256':'d754368b2f7357de6a38015c0be119ba9fbf16e3847ec174451273820a2ec32b','transaction_id':p['transaction_id']}
sys.path.insert(0,ROOT+'/stage1')
from p2_install_entrypoint import validate_plan
assert validate_plan(p)
planraw=pack(p);planpath=d+'/protected-core-install-plan.json';write(planpath,planraw)
argv=['/usr/bin/python3','-I','-B',ROOT+'/scripts/uk-p2-install.py','--operation','verify-only','--plan',planpath,'--plan-sha256',h(planraw),'--receipt',d+'/install-receipt.json','--transaction-directory',d,'--release-installer',ROOT+'/scripts/uk-integration-install.py']
result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
if result.returncode:
 print('CLI_PREFLIGHT_HOLD='+result.stderr.decode()[-2000:]);raise ValueError('ACTUAL_CLI_PREFLIGHT_FAILED')
print(result.stdout.decode())
print('CORE_PLAN_PATH='+planpath)
print('CORE_PLAN_SHA256='+h(planraw))
print('CORE_PLAN_BYTE_COUNT='+str(len(planraw)))
print('CORE_PLAN_BYTES_BASE64='+base64.b64encode(planraw).decode())
print('INSTALL=NO; FENCE_MUTATION=NO; NEW_WRITER=NO; SECRET_VALUES_EXPORTED=NO')
