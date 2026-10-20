# 固定Python binary单一缺项取证｜待Owner确认

本命令未执行，不是安装；创建并清理一个临时Docker容器，读取其自身Python文件，无挂载、无网络、不更改应用目录。异常清理只限本次唯一名称且label匹配容器。执行后回传完整JSON，之后才能冻结expected descriptor和安装请求。

```bash
# 收件窗口：Owner｜B3唯一缺项取证（确认临时容器动作后执行，不是安装）
sudo -n /usr/bin/python3 -I -B -S - <<'PY'
import os,json,subprocess,uuid
assert os.geteuid()==0
assert os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
name='p2-b3-python-pin-'+uuid.uuid4().hex
program=r'''import os,sys,json,hashlib,stat
path=os.path.realpath('/usr/bin/python3.11')
assert path.startswith('/usr/bin/') and sys.version_info[:2]==(3,11)
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as source:
 before=os.fstat(source.fileno())
 assert stat.S_ISREG(before.st_mode)
 digest=hashlib.sha256()
 while True:
  raw=source.read(65536)
  if not raw:break
  digest.update(raw)
 after=os.fstat(source.fileno())
 assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
print(json.dumps({'scope':'ISOLATED_TEST_ONLY','purpose':'B3_BINARY_PIN_ONLY','declared_path':'/usr/bin/python3.11','canonical_path':path,'bytes':after.st_size,'sha256':digest.hexdigest(),'uid':os.geteuid(),'version':sys.version.split()[0],'installation_executed':False},sort_keys=True))'''
cmd=['/bin/docker','run','--rm','--pull=never','--name='+name,
 '--label=p2-b3-owner-probe='+name,'--user=1002:1002','--network=none',
 '--cap-drop=ALL','--security-opt=no-new-privileges','--read-only',
 '--pids-limit=96','--memory=512m','--memory-swap=1g','--log-driver=none',
 '--entrypoint=/usr/bin/python3.11',
 'sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d',
 '-I','-B','-S','-c',program]
try:
 result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
 print(result.stdout.decode('utf-8','replace'))
 print(result.stderr.decode('utf-8','replace'))
 print(json.dumps({'docker_exit_code':result.returncode,'installation_executed':False},sort_keys=True))
finally:
 probe=subprocess.run(['/bin/docker','inspect','--format','{{json .Config.Labels}}',name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 if probe.returncode==0:
  labels=json.loads(probe.stdout.decode())
  if labels.get('p2-b3-owner-probe')==name:
   subprocess.run(['/bin/docker','rm','--force',name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
PY
```
