# Dependency metadata only; pending Owner confirmation. NOT a B5 install command.
sudo -n /usr/bin/python3 -I -B -S - <<'PY'
import os,hashlib,subprocess,json
from urllib.request import build_opener,ProxyHandler
assert os.getuid()==os.geteuid()==0
assert os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
url='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/80232a76636de2943cde78461a69fd55838cf045/scripts/p2_b5_sdk_inventory.py'
with build_opener(ProxyHandler({})).open(url,timeout=30) as response:raw=response.read(65537)
assert len(raw)<=65536 and hashlib.sha256(raw).hexdigest()=='23fc5facba74ef4db05b0c982c73f36b0c8a498a43e71fc86e5282e5ac336dce'
result=subprocess.run(['/usr/bin/sudo','-n','-u','xuanjun_dev','--','/usr/bin/python3','-I','-B','-S','-'],
    input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
print(result.stdout.decode('utf8','replace'))
print(result.stderr.decode('utf8','replace'))
print(json.dumps({'inventory_exit_code':result.returncode,'purpose':'DEPENDENCY_METADATA_ONLY',
                  'loader_executed':False,'installation_executed':False,'cp11':'NOT_EXECUTED'},sort_keys=True))
PY
