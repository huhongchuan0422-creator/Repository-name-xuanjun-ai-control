from pathlib import Path
import sys,os,hashlib,json,subprocess
D=Path(__file__).resolve().parent
sys.path.insert(0,'/var/lib/xuanjun-community-preview/native-test-20261121/mini-wechat-direct-20261123-223sva0o')
from original_locks import writer_locks
P=Path('/etc/nginx/community-preview.inc');B=Path('/var/lib/xuanjun-community-preview/native-test-20261121/fixed-cashier-ads-backup-20261124-f7d2-1415/community-preview.inc.before')
with writer_locks():
 before=P.read_bytes();result=(D/'result/community-preview.inc').read_bytes();pins=json.loads((D/'before-pins.json').read_text());assert hashlib.sha256(before).hexdigest()==pins['community-preview.inc'],'NGINX_DRIFT_NO_OVERWRITE'
 fd=os.open(B,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(before);f.flush();os.fsync(f.fileno())
 st=P.stat();tmp=P.with_name('.community-preview.ad-preview.merge');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,st.st_mode&0o777)
 with os.fdopen(fd,'wb') as f:f.write(result);f.flush();os.fchown(f.fileno(),st.st_uid,st.st_gid);os.fsync(f.fileno())
 os.replace(tmp,P)
 tested=subprocess.run(['/usr/sbin/nginx','-t'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if tested.returncode:P.write_bytes(before);raise RuntimeError('NGINX_TEST_FAILED_ORIGINAL_RESTORED '+tested.stderr.decode())
 reload=subprocess.run(['/usr/bin/systemctl','reload','nginx'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if reload.returncode:
  P.write_bytes(before);subprocess.run(['/usr/sbin/nginx','-t'],check=True);subprocess.run(['/usr/bin/systemctl','reload','nginx'],check=True);raise RuntimeError('NGINX_RELOAD_FAILED_ORIGINAL_RESTORED')
 print('CURRENT_BASE_NGINX_TEST_RELOAD_PASS',hashlib.sha256(result).hexdigest())
