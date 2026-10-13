"""Read-only exact RPM/TLS baseline; write a private preparation receipt only."""
import os,sys,socket,stat,json,hashlib,re,subprocess
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
RPMROOT='/tmp/p2pkg-38369525772-1/tls-rpm-preparation'
PLAN=BASE+'/plan-p2pkg-38408240449-1/protected-core-install-plan.json'
PLAN_SHA='cf9bafc710de17f2ae7fd5b8d27352138ec4e8deefbff368d9590c6608fe6f92'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,mode,maximum=16777216):
 assert os.path.realpath(path)==path
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(maximum+1);end=os.fstat(f.fileno())
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==mode and s.st_nlink==1 and len(raw)<=maximum
  assert (s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(end.st_size,end.st_mtime_ns,end.st_ctime_ns)
 return raw
def cmd(args,data=None):
 p=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
 return p.returncode,p.stdout,p.stderr
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and len(sys.argv)==2 and sys.argv[1].isdigit()
raw=read(PLAN,0o600);assert sha(raw)==PLAN_SHA;plan=json.loads(raw.decode())
receipt=read(RPMROOT+'/protected-tls-rpm-receipt.json',0o600)
assert sha(receipt)=='fe610cf7024a9f1914bfa318d34d20235aa47c9cb02cbff97f8702a0aa33689e'
items=json.loads(receipt.decode())['rpms'];assert len(items)==16
rows=[];paths=[];names=set()
for item in items:
 name=item['file'];assert '/' not in name and name.endswith('.rpm')
 path=RPMROOT+'/'+name;raw=read(path,0o400,67108864);assert sha(raw)==item['sha256']
 code,out,err=cmd(['/bin/rpm','--checksig',path]);text=(out+err).decode()
 assert code==0 and 'OK' in text and 'NOKEY' not in text and 'NOT OK' not in text
 fmt='%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}\n'
 code,out,err=cmd(['/bin/rpm','-qp','--qf',fmt,path]);assert code==0
 parts=out.decode().strip().split();assert len(parts)==5 and all(re.fullmatch(r'[A-Za-z0-9_.+:-]+',v) for v in parts)
 assert parts[0] not in names;names.add(parts[0])
 code,out,err=cmd(['/bin/rpm','-q','--qf',fmt,parts[0]])
 if code==1:before=None
 else:
  assert code==0
  before=out.decode().strip().split();assert len(before)==5
 state='NEW_PACKAGE' if before is None else 'SAME_VERSION' if before==parts else 'UPGRADE_OR_REPLACEMENT_REQUIRES_OLD_RPM'
 rows.append({'name':parts[0],'candidate':parts,'before':before,'state':state,'path':path,'sha256':item['sha256']});paths.append(path)
code,out,err=cmd(['/bin/rpm','-U','--test']+paths);assert code==0
refs=plan['tls']['references'];assert len(refs)==2
cert=next(x for x in refs if x['sha256']=='c4bfb6265349780c22c346657096291a96db804c2a3eac9b3ee0b62a2492a71d')
key=next(x for x in refs if x['sha256']=='0910affcb259decf8bf5ae8d9079bcc95831fadb24de422fcbbb5ab1330615ea')
for ref in refs:assert sha(read(ref['path'],0o600))==ref['sha256']
code,out,err=cmd(['/usr/bin/openssl','x509','-in',cert['path'],'-noout','-checkhost','uk.wenwenwenyiyiyi.work']);assert code==0 and b'does match certificate' in out
code,out,err=cmd(['/usr/bin/openssl','x509','-in',cert['path'],'-noout','-checkend','86400']);assert code==0
code,public,err=cmd(['/usr/bin/openssl','x509','-in',cert['path'],'-pubkey','-noout']);assert code==0
code,certder,err=cmd(['/usr/bin/openssl','pkey','-pubin','-outform','DER'],public);assert code==0
code,keyder,err=cmd(['/usr/bin/openssl','pkey','-in',key['path'],'-pubout','-outform','DER']);assert code==0 and keyder==certder
outdir=BASE+'/rpm-tls-baseline-'+sys.argv[1];os.mkdir(outdir,0o700)
hold=[row['name'] for row in rows if row['state']=='UPGRADE_OR_REPLACEMENT_REQUIRES_OLD_RPM']
public={'schema':1,'state':'RPM_TLS_READONLY_BASELINE_VERIFIED','rpm_count':16,'new_packages':sum(row['state']=='NEW_PACKAGE' for row in rows),'same_version_packages':sum(row['state']=='SAME_VERSION' for row in rows),'upgrade_packages_requiring_old_rpms':hold,'rpm_test_exit':0,'certificate_host_keypair_and_remaining_validity':True,'install':False,'services_changed':False,'canonical_ledger_changed':False,'model_calls':0,'writer_admission':False,'production_https_acceptance':False,'automatic_renewal_acceptance':False}
value={'schema':1,'core_plan_path':PLAN,'core_plan_sha256':PLAN_SHA,'packages':rows,'certificate_references':refs,'public_receipt':public,'install_admission':False}
raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode();path=outdir+'/protected-rpm-tls-baseline.json'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps(public,sort_keys=True));print('RPM_TLS_BASELINE_PATH='+path);print('RPM_TLS_BASELINE_SHA256='+sha(raw))
