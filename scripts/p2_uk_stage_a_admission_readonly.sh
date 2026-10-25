/usr/bin/sudo -n -- /usr/bin/python3 -I -B -S - <<'UK_STAGE_A_ADMISSION_PY'
import os,sys,stat,json,hashlib,signal,re
HOST='iZd7oeikknn1z21sq6ji6zZ'
ROOT='/opt/xuanjun-cloud-connection/b5-successor-controller-staged-f0fe0d3978b7'
CONFIG='/etc/xuanjun-cloud-executor/connection.json'
BINDING='/etc/xuanjun-cloud-executor/b5-stage-a-binding.json'
DB='/var/lib/xuanjun-cloud-connection/queue.sqlite'
CURRENT='/opt/xuanjun-cloud-connection/current'
RELEASES=('/opt/xuanjun-cloud-connection/releases/e78bd7749414d1637012f57b65d2019955282fc3','/opt/xuanjun-cloud-connection/releases/f0fe0d3978b72a11e4fa4cfb9928424d60124940')
ROWS=[['RUNTIME_SOURCE_MANIFEST.json', 6651, '814c0779dfaaeefb79481864dd95a8e145f7074c60e8cc439fda7f9c5434098d', 'binding'], ['SUCCESSOR_CONTROLLER_SOURCE_MANIFEST.json', 2094, 'b185abacd62aba0316dc5fa4c6584effb0799fefdbeae3be7eab4c76869dc861', 'binding'], ['SUCCESSOR_SPEC.json', 23152, '84d1a193998959b4a7b2c25bc9a0d6e27082c6580faaa34de07296974785b309', 'binding'], ['new19-source/deployment/cloud-connection/oauth/authority.example.json', 471, '7d900b8a7829a9a89d20ace656d1470839404f7359b0aca1bf23b4feebf45244', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/domestic-py3116-compatibility.json', 6843, '2ce00bd99e35f8d3496fd1cae457df9841d136188a7fd014e06d62c17b818e6c', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/nginx-http01-bootstrap.conf.candidate', 462, '5367238723be7258185e2f83c7bbd410a6faafbd0472be722aac9264ade2d8e6', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/nginx-proxy.conf.candidate', 401, '7e052480371700645cc03a9b147b1d3db8b9bc0d82e9de4d2353d46213c5cb40', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/nginx-vhost-pre-egress.conf.candidate', 1276, '3084db85240b330699c06809dc29466303d8c65990c024199825b2ac94ef86b5', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/nginx-vhost.conf.candidate', 1390, 'a2643e88e1802615e18a623074c4899cb10c8e2554338943482739434fb6bee5', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/peer-observation.http.conf.template', 320, 'b0742e99793812ceea1bbbd5d34014fcb8977a098aedab05df87f093f16c8b64', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/peer-observation.location.conf.template', 358, '93575ab5d73465e0ca34d97b613cdd9b10e661cb217d8bc50c35c7b54a6b25ef', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/requirements.cp3116.lock', 1795, 'd1652d76675260ecc791d74950aa0636d94f7b646780b620b747caf845eead71', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/requirements.lock', 5158, 'a1b599978d9624aba2f55574625a3395159382a87edd85fd0985a9971192e4d4', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/resource.example.json', 390, '8ec9d5cec3795d3833ca8abc5c88589d71b24e3481b5fa0e872d5386748bbaab', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/run.py', 1633, 'c45093243a07b4a7a5dc5bef466e3347051131537d1c23de28f587b8243b7157', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/tls-approved.conf.candidate', 228, 'b6c4d753b2599c6f3ca514097603a9448354c44af0c1406be0006518a82363b1', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/xuanjun-cloud-oauth-py3116.service.candidate', 729, '1c3511ef8dc0f95d9b4ae7d3a989b25c10258eb8eb322c8cb29807866bc5e89c', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/xuanjun-cloud-oauth-resource.service.candidate', 814, '4bd19ae8e36166b27b247c4705bc8ed7fd1210c9b94609065d1a98b11bf0e581', 'runtime'], ['new19-source/deployment/cloud-connection/oauth/xuanjun-cloud-oauth.service.candidate', 722, '16911422086f3034a7d31d046930af9f6f767b2a020e902547696746c007538d', 'runtime'], ['new19-source/production/cloud_connection/action_binding.py', 4452, '7eb14ceccb4255ff90fe8f82c8184abea979984bcbe2e76c78fd34f4fd52e752', 'runtime'], ['new19-source/production/cloud_connection/archive_reader.py', 9230, '39f9aae289f4e7ef64d9579a7f11338bd46382f8906899c503901f778f911ddf', 'runtime'], ['new19-source/production/cloud_connection/credential_lifecycle.py', 6064, '26e8e0ec44ebb057a0106517824f9000406b93562c22b53f5929d3f66bb52620', 'runtime'], ['new19-source/production/cloud_connection/fixed_actions.py', 18669, '75fe7d4c2d24f125485ced1f2663171d22c92715241373b799a135fd0b3438f0', 'runtime'], ['new19-source/production/cloud_connection/github_network.py', 5503, '7fd03cfd85c242e615b0cfccd8888718bc069cbd57fb64c89fc9185ac4d9cfe6', 'runtime'], ['new19-source/production/cloud_connection/material_custody.py', 9525, 'a5ebcd971334ff2965d022d5040a72d7125adc64694a8b0183a4034364cf5352', 'runtime'], ['new19-source/production/cloud_connection/oauth_authority.py', 23614, '13424309f48afaaa52cdfad83633d1d4921cc481e9ebdd6081ce7185af031bd4', 'runtime'], ['new19-source/production/cloud_connection/oauth_entrypoint.py', 7428, '66b5c98d8e7e25ea6c6d95385e6e1c6737aa8357fdf1973054f9c3cd0fa37498', 'runtime'], ['new19-source/production/cloud_connection/oauth_http.py', 7596, 'ecfec4a91fb38e94e7bbc5720e47ce7b45cfebe9e33fd689b6a482f782c9398b', 'runtime'], ['new19-source/production/cloud_connection/oauth_resource.py', 11797, '23c94207865012de06c60d82a9bdf2d58ed3fe53a2b88e723477d61c93363558', 'runtime'], ['new19-source/production/cloud_connection/pr122_baseline_collector.py', 12809, 'c352c041ab62a1bf3c1c55afeea461ba935016e294975dfb515e19972365250f', 'runtime'], ['new19-source/production/cloud_connection/private_mcp.py', 9185, '3c8a94a92b39519bd6797656fed6282815f7fbe0fcd8a794fb0edc77da6e0f86', 'runtime'], ['new19-source/production/cloud_connection/private_transfer.py', 26055, 'be2f0ebbf6087fa6a1c804dc24fc67ef2d90ab507869e60125b0fd1cdad3cc5b', 'runtime'], ['new19-source/production/cloud_connection/queue.py', 14414, '603ac5eb330daba82f09b3f1c1d3399a544befc862ede004c95405eda913c8b6', 'runtime'], ['new19-source/production/cloud_connection/runtime.py', 14413, 'daafcd2dca1fcc673f241a37fd11b749ff65fae2f22d3e737c2e5ece74242b8e', 'runtime'], ['new19-source/production/cloud_connection/worker.py', 14424, 'ba309d089b38e3993f1cf794362364d85862bb6f5d0c48c4f2149855045a683e', 'runtime'], ['new19-source/reused-6825/pr17_b5_deployment_composition.py', 15798, '352b2297d325c1d90057a1223bad2f742e48eaa71cf8aaa1b58c56339b3a3ab2', 'runtime'], ['new19-source/reused-6825/pr17_b5_maintenance_runtime.py', 6724, '61cf0de7485cf012b920d740f5f95336ddd1668bcde3053c09e60b992301f30b', 'runtime'], ['new19-source/reused-6825/pr17_b5_original_algorithms.py', 8435, 'a2afb83417e64d6ee53c26a504156ab82255739fd9833bcf2446ebd3b164f575', 'runtime'], ['new19-source/reused-6825/pr17_b5_single_batch_witness.py', 19035, '5a31ef8444071953ee08f0274a4c92e2d21d4491928b379ab3c6f24d83ef4a1a', 'runtime'], ['new19-source/reused-6825/pr17_c53_r2_authority_adapter.py', 30911, 'b2ee975ce4d41433f4da53785bb35b5cf45d9b77dee3c554f9215b7ffe6b3a13', 'runtime'], ['new19-source/reused-6825/pr17_c53_r2_host_backend_candidate.py', 75983, 'b83e7410b8330b1ac199476355743415dcc42dc208903c7417f9437c5866df68', 'runtime'], ['new19-source/reused-6825/pr17_c53_r2_local_adapter.py', 5213, 'a4e6d7e4b2de7de78e693877b29f2df940301658dac2787b0f0a6373b61b097c', 'runtime'], ['new19-source/reused-6825/pr17_c53_r2_local_pinned_source_loader.py', 3632, 'd7bca83fdb5f23acced83e9e500642f6f37e97797e1c3a8094ae18316572a5fe', 'runtime'], ['new19-source/reused-6825/pr17_c53_r2_review_transaction.py', 31522, '6e98681cad506785dc5a0e6f159c1d49217c8940bba0a04b34bd41ac3b447f93', 'runtime'], ['new19-source/reused-6825/pr17_c53_r2_transaction_candidate.py', 10679, 'e0b693fb934bf15bf0afccc4350938c6ebc3eb0f1c39bc1c97f0d6053547c77f', 'runtime'], ['successor_analyst_read.py', 4005, '48181fb861851124a9b2cb247406865c17e87c85b93c7ed7bf9ebdd772660c24', 'controller'], ['successor_contract.py', 11820, '27de1ce838fdb4bca07c9bf0b8f43687ea044b171774c953b89ab683943c1bc8', 'controller'], ['successor_controller/pr17_b5_successor_authority.py', 35800, '1cf1249412e81fdea89f55834f52dbe531ce1fbe4e7093f4b171314cc075fd11', 'controller'], ['successor_controller/pr17_b5_successor_backend.py', 82662, 'd42ab08dae6b7b21d7ee165da7ca5d5c1847595bcdd599497bfa66bb52069b2f', 'controller'], ['successor_controller/pr17_b5_successor_binder.py', 3302, '9875280136cd8e2fa256590bde2e89d1ee9e01592884f8ad25057eb4254a290e', 'controller'], ['successor_controller/pr17_b5_successor_entry.py', 13983, 'f2eb482970db3ddbc386bcc689b756b7263932f50a43b86a3f179e84756a685a', 'controller'], ['successor_controller/pr17_b5_successor_fixed_io.py', 18323, '6c9af335a012cf5ec07a122042d1075121b52e2e62d0d383c06e1fd8a3c1dc9f', 'controller'], ['successor_controller/pr17_b5_successor_loader.py', 1411, '1d4439bfc66366f35ff4433404e5c4576a7a83770663e24c9386db4dea4afb4e', 'controller'], ['successor_controller/pr17_b5_successor_local.py', 5243, '2ca630af9e3326c2c02420ddda84039b88f8f25848dc95a30aef0170b0d41e99', 'controller'], ['successor_controller/pr17_b5_successor_release_gate.py', 9645, '3ffb0fd53b7d14ab804703c790e163633929343e4461150af042fcc863db8c68', 'controller'], ['successor_controller/pr17_b5_successor_review.py', 33533, '9a06d0950345ec4c02593d925d210d6acc8bb5458e757b1c115f0e41e4369d56', 'controller'], ['successor_controller/pr17_b5_successor_runtime.py', 6709, '6cb26e1e48a13101916cb71c2783c8a6ccbf518312edb8ae18d7715ec14ea4a2', 'controller'], ['successor_controller/pr17_b5_successor_witness.py', 36549, '46f1390cdd023ec1605357b1fd11e613e8ebd6a451ae9b05c4f0383864a9fa16', 'controller'], ['successor_source_loader.py', 3228, 'fcb804616a55d1e5a3fb75ac379f5424b080d7042859b7f105dd2d570906c7b6', 'controller']]
NAMES=('queue.py','worker.py','runtime.py','private_transfer.py','credential_lifecycle.py','fixed_actions.py','pr122_baseline_collector.py','archive_reader.py','material_custody.py','action_binding.py','b5_stage_a_fixed_action.py','pr17_b5_stage_a_frozen_candidate_v3.py')
BUDGET=2097152
used=0
class Stop(Exception): pass
class Deadline(BaseException): pass
def alarm(a,b): raise Deadline()
def ident(s): return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def parent(path):
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for p in path.split('/')[1:-1]:
   n=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=n
   s=os.fstat(fd)
   if s.st_uid!=0 or s.st_mode&0o022: raise Stop('PARENT_UNSAFE')
  return fd,path.rsplit('/',1)[1]
 except BaseException:
  os.close(fd);raise
def meta(path):
 fd,n=parent(path)
 try:return os.stat(n,dir_fd=fd,follow_symlinks=False)
 finally:os.close(fd)
def read(path,limit,modes=(0o600,0o644)):
 global used
 fd,n=parent(path);f=None
 try:
  if not hasattr(os,'O_NOATIME'):raise Stop('NOATIME_UNAVAILABLE')
  f=os.open(n,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_NOATIME,dir_fd=fd);s=os.fstat(f)
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_nlink!=1 or stat.S_IMODE(s.st_mode) not in modes or s.st_size>limit:raise Stop('FILE_UNSAFE')
  if used+s.st_size> BUDGET:raise Stop('READ_BUDGET')
  used+=s.st_size
  b=b''
  while len(b)<s.st_size:
   v=os.read(f,min(65536,s.st_size-len(b)))
   if not v:break
   b+=v
  if len(b)!=s.st_size or ident(s)!=ident(os.fstat(f)) or ident(s)!=ident(os.stat(n,dir_fd=fd,follow_symlinks=False)):raise Stop('IDENTITY_CHANGED')
  return b,ident(s)
 finally:
  if f is not None:os.close(f)
  os.close(fd)
def sha(b):return hashlib.sha256(b).hexdigest()
def pairs(items):
 d={}
 for k,v in items:
  if k in d:raise Stop('JSON_DUPLICATE')
  d[k]=v
 return d
def parse(b):
 d=json.loads(b.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(Stop('JSON_NONFINITE')))
 if type(d) is not dict:raise Stop('JSON_SHAPE')
 return d
def issha(v):return type(v) is str and re.fullmatch('[0-9a-f]{64}',v) is not None
def observe(fn):
 try:return fn()
 except FileNotFoundError:return {'state':'ABSENT'}
 except PermissionError:return {'state':'NOT_OBSERVED_PERMISSION'}
 except Stop as e:return {'state':e.args[0]}
 except Exception:return {'state':'NOT_OBSERVED_SAFE_ERROR'}
def config():
 b,i=read(CONFIG,16384,(0o600,));d=parse(b);p=d.get('executor_sha256')
 return {'state':'OBSERVED','identity':i,'sha256':sha(b),'executor_sha256':p if issha(p) else None,'actor_matches':d.get('allowed_actor_ids')==[332398908],'state_root_matches':d.get('state_root')=='/var/lib/xuanjun-cloud-connection','github_owner_matches':d.get('github_token_owner')==1003,'b5_hook_present':'b5_stage_a' in d,'website_hook_present':'website_baseline' in d,'b5_hook_reference_matches':type(d.get('b5_stage_a')) is dict and d['b5_stage_a'].get('metadata_ref')==BINDING,'b5_hook_sha256':d.get('b5_stage_a',{}).get('metadata_sha256') if type(d.get('b5_stage_a')) is dict and issha(d['b5_stage_a'].get('metadata_sha256')) else None}
def binding():
 b,i=read(BINDING,16384,(0o600,));d=parse(b)
 return {'state':'OBSERVED','identity':i,'sha256':sha(b),'project_matches':d.get('project')=='p2-b5-material-analysis','target_matches':d.get('target')=='uk','operation_matches':d.get('operation')=='b5_stage_a_precheck','execution_identity_matches':d.get('execution_identity')=='admin','v3_sha_matches':d.get('adapter_sha256')=='e3f36cdf2b80d98a0a193d82055fdaf44baf49c8e2b0e9b5da0fb9138615f672','request_id_present':type(d.get('request_id')) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',d['request_id']) is not None,'valid_from':d.get('valid_from') if type(d.get('valid_from')) is int else None,'valid_until':d.get('valid_until') if type(d.get('valid_until')) is int else None,'single_consumption':'UNKNOWN_NOT_QUERIED'}
def sources():
 s=meta(ROOT)
 if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise Stop('ROOT_UNSAFE')
 out={'state':'OBSERVED','root_identity':ident(s),'expected':len(ROWS),'matched':0,'missing':0,'mismatched':0,'unobserved':0}
 for rel,size,digest,category in ROWS:
  def one():
   b,i=read(ROOT+'/'+rel,size)
   return {'state':'MATCH' if len(b)==size and sha(b)==digest else 'MISMATCH'}
  a=observe(one)['state'];key='matched' if a=='MATCH' else 'missing' if a=='ABSENT' else 'mismatched' if a=='MISMATCH' else 'unobserved';out[key]+=1
 if ident(s)!=ident(meta(ROOT)):raise Stop('ROOT_CHANGED')
 out['all_3_metadata_14_controller_42_runtime_match']=out['matched']==59
 return out
def worker():
 fd,n=parent(CURRENT)
 try:
  s=os.stat(n,dir_fd=fd,follow_symlinks=False)
  if not stat.S_ISLNK(s.st_mode) or s.st_uid!=0:raise Stop('CURRENT_UNSAFE')
  target=os.readlink(n,dir_fd=fd)
  if ident(s)!=ident(os.stat(n,dir_fd=fd,follow_symlinks=False)):raise Stop('CURRENT_CHANGED')
  if target not in RELEASES:return {'state':'UNKNOWN_RELEASE_NOT_READ','current_identity':ident(s),'target_sha256':sha(target.encode())}
  records=[]
  for name in NAMES:
   try:b,i=read(target+'/production/cloud_connection/'+name,131072)
   except FileNotFoundError:break
   records.append([name,sha(b)])
  if ident(s)!=ident(os.stat(n,dir_fd=fd,follow_symlinks=False)) or os.readlink(n,dir_fd=fd)!=target:raise Stop('CURRENT_CHANGED')
  def pin(r):return sha(json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
  return {'state':'OBSERVED','current_identity':ident(s),'release':target.rsplit('/',1)[1],'source_files_read':len(records),'nine_file_pin':pin(records[:9]) if len(records)>=9 else None,'candidate_twelve_file_pin':pin(records) if len(records)==12 else None,'active_process':'UNKNOWN_NOT_QUERIED'}
 finally:os.close(fd)
def dbmeta():
 result={'state':'METADATA_ONLY','sqlite_connected':False,'conflicts':'UNKNOWN_DB_NOT_OPENED','rows_read':0}
 for suffix,label in (('','main'),('-wal','wal'),('-shm','shm'),('-journal','journal')):
  def one():
   s=meta(DB+suffix)
   return {'state':'PRESENT','identity':ident(s),'regular':stat.S_ISREG(s.st_mode),'historical_db_identity_matches':s.st_dev==64771 and s.st_ino==1845925 if suffix=='' else None}
  result[label]=observe(one)
 return result
def main():
 signal.signal(signal.SIGALRM,alarm);signal.alarm(20)
 out={'scope':'UK_STAGE_A_ADMISSION_METADATA_ONLY','host_matches':os.uname().nodename==HOST,'euid':os.geteuid(),'egid':os.getegid(),'sudo_uid_1000':os.environ.get('SUDO_UID')=='1000','writes':False,'network':False,'product_imports':False,'stage_a_executed':False,'db_rows_read':0}
 rc=0
 try:
  if not out['host_matches'] or out['euid']!=0 or out['egid']!=0 or not out['sudo_uid_1000']:raise Stop('HOST_OR_SUDO_IDENTITY_HOLD')
  out['worker']=observe(worker);out['config']=observe(config);out['binding']=observe(binding);out['frozen_root']=observe(sources);out['queue']=observe(dbmeta)
  out['state']='OBSERVED_REVIEW_REQUIRED'
 except Deadline:out['state']='DEADLINE_HOLD';rc=2
 except Stop:out['state']='HOST_OR_SUDO_IDENTITY_HOLD';rc=2
 except Exception:out['state']='SAFE_ERROR_HOLD';rc=2
 finally:signal.alarm(0)
 out['read_bytes']=used
 raw=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False)
 if len(raw.encode())>16384:raw='{"state":"OUTPUT_BOUND_HOLD"}';rc=2
 print(raw);return rc
if __name__=='__main__':sys.exit(main())
UK_STAGE_A_ADMISSION_PY
rc=$?
printf '\nEXIT_CODE=%s\n' "$rc"
