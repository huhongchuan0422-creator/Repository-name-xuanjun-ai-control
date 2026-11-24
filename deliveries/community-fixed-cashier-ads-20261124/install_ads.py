"""Original native lifecycle; exact current-base four-file transaction, no plan or authority writes."""
import sys,os,json,types,hashlib
from pathlib import Path
D=Path(__file__).resolve().parent;S=D.parent
sys.path[:0]=[str(S),'/var/lib/xuanjun-community-preview/native-test-20261121/mini-wechat-direct-20261123-223sva0o']
import preflight as pf
import native_lifecycle as life
from original_locks import writer_locks
pf.PID=1098618
base=json.loads((D/'before-pins.json').read_text());pins=json.loads((D/'result-pins.json').read_text());preserve=json.loads((D/'preserve-installed-pins.json').read_text())
after={n:h for n,h in pins.items() if n!='community-preview.inc'};before={n:base[n] for n in after if base[n]!='ABSENT'}
pf.APPS=set(after);life.SWAP=set(before)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with writer_locks():
 for n,h in preserve.items():assert sha(pf.APP/n)==h,('SHARED_OVERLAY_DRIFT',n)
 proc=Path('/proc')/str(pf.PID)
 flags=pf.parse_argv([os.fsdecode(x) for x in (proc/'cmdline').read_bytes().split(bytes([0])) if x])
 relay=Path(os.readlink(proc/'fd'/flags[life.RELAY_FLAG]));direct=Path(os.readlink(proc/'fd'/flags[life.DIRECT_FLAG]))
 a=types.SimpleNamespace(relay_path=relay,direct_path=direct,overlay=D/'result',backup=pf.ROOT/'fixed-cashier-ads-backup-20261124-f7d2-1415')
 plan=pf.read_plan(relay,direct,a.overlay,after)
 print('CURRENT_6149_BASE_ADS_PREFLIGHT_PASS PRESERVE_HOST_HTTP_SESSION_SHOWCASE',flush=True)
 if '--apply' in sys.argv:
  print(life.apply_exact(a,plan,after,before),flush=True)
  for n,h in after.items():assert sha(pf.APP/n)==h,('RESULT_MISMATCH',n)
  for n,h in preserve.items():assert sha(pf.APP/n)==h,('PRESERVED_OVERLAY_CHANGED',n)
print('ORIGINAL_NINE_LOCKS_RELEASED_NO_AUTHORITY_OR_PLAN_CHANGE',flush=True)
