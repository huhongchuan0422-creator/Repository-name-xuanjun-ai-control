"""Offline S07/S08 candidate compiler. Never installs, starts or switches services."""
import hashlib,io,json,tarfile
from pathlib import Path
HOSTS={'korea':'iZmj7a5kwr75qc1tul4kf9Z','domestic':'iZvt5t8tlrm8oiZ','tokyo':'iZ6wee8q9z4t03hvqumwfhZ'}
ROLES={'portal':('scripts/secure_secrets_portal_server.py serve --host 127.0.0.1 --port 18080',18080),'contact':('-m ai_service.wecom_customer_contact_service',18781),'customer_service':('-m ai_service.wecom_customer_service',18780)}
RELEASE='/opt/xuanjun-migration-s07/releases/domestic-r1'

def need(ok,code):
 if not ok:raise ValueError(code)
def encoded(x):return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def hosts(receipt,run,job):
 need(receipt['run']==run and receipt['job']==job,'EVIDENCE_RUN_BINDING')
 rows=receipt['hosts'];need(len(rows)==3 and {r['host'] for r in rows}==set(HOSTS),'HOST_SET')
 out={}
 for row in rows:
  h=row['host'];r=row['receipt'];need(row['status']=='PASS' and row['invocation_status']=='Success','INVOKE_NOT_SUCCESS')
  need(r['hostname']==HOSTS[h] and r['uid']==0 and r['service_actions']==0 and r['business_api_requests']==0 and r['database_opened'] is False,'EVIDENCE_SCOPE')
  out[h]=r
 return out

def compile_candidate(runtime,endpoints):
 r=hosts(runtime,38999602793,117299532997);e=hosts(endpoints,39000291289,117301596227)
 units={u['unit']:u for u in r['domestic']['units']}
 for name in ('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service','xuanjun-wecom-customer-service.service'):
  need(units[name]['LoadState']=='not-found','DOMESTIC_UNIT_ALREADY_OWNED')
 occupied={int(x['local'].rsplit(':',1)[1]) for x in r['domestic']['listeners']}
 need(not occupied.intersection({18080,18780,18781}),'PLANNED_PORT_OCCUPIED')
 expected={
 'provider-neutral-tokyo-tunnel.service':('47.101.152.210','openclaw_ops',[{'flag':'-L','binding':'127.0.0.1:19443:127.0.0.1:18443'}]),
 'domestic-model-rpc-tunnel.service':('47.101.152.210','openclaw_ops',[{'flag':'-R','binding':'127.0.0.1:19444:127.0.0.1:20443'}]),
 'korea-novel-model-rpc-tunnel.service':('43.108.99.66','admin',[{'flag':'-L','binding':'127.0.0.1:18761:127.0.0.1:18760'},{'flag':'-R','binding':'127.0.0.1:19444:127.0.0.1:20443'}])}
 for item in e['tokyo']['ssh']:
  need(item['unit'] in expected and len(item['commands'])==1,'TUNNEL_SET')
  c=item['commands'][0];dest,user,forward=expected[item['unit']]
  need(c['destination']==dest and c['user']==user and c['forwards']==forward and c['port']==22,'TUNNEL_BINDING')
 need({x['unit'] for x in e['tokyo']['ssh']}==set(expected),'TUNNEL_SET')
 files={}
 for role,(cmd,port) in ROLES.items():
  # These are review templates for a future copied runtime, never active /etc units.
  unit='[Unit]\nDescription=PR99 domestic '+role+' candidate\nAfter=network.target\n\n[Service]\nType=simple\nUser=65534\nGroup=65534\nRootDirectory='+RELEASE+'/rootfs\nWorkingDirectory=/opt/trading-system\nExecStart=/venv/bin/python '+cmd+'\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nEnvironment=PYTHONPATH=/opt/trading-system\nUMask=0077\nNoNewPrivileges=yes\nPrivateTmp=yes\nPrivateDevices=yes\nProtectSystem=strict\nReadWritePaths=/opt/trading-system/runtime\nCapabilityBoundingSet=\nRestrictSUIDSGID=yes\nRestart=no\nTimeoutStopSec=15\nKillMode=control-group\nStandardOutput=null\nStandardError=null\n'
  files['units/xuanjun-pr99-domestic-'+role+'.service.template']=unit.encode()
 plan={
 'schema':1,'status':'REVIEW_CANDIDATE_NOT_INSTALLABLE','production_authorization':False,'services_installed':False,'source_evidence':{'runtime_run':runtime['run'],'endpoint_run':endpoints['run'],'runtime_sha256':digest(encoded(runtime)),'endpoints_sha256':digest(encoded(endpoints))},
 'target':{'hostname':HOSTS['domestic'],'instance':'3a22c458934142eea89ec6e3bf481a57','release':RELEASE,'uid_gid':'65534:65534','ports':{k:v[1] for k,v in ROLES.items()}},
 'templates':'NO_INSTALL_SECTION_NO_ENABLE_NO_DEPLOY_ENTRY; dependency/env/bind mounts require final contract before activation',
 'transaction_order':[
 'verify exact independent approval and expiry, host, actor and one-use attempt',
 'recheck original canonical ownership; reject any concurrent/unknown migration execution',
 'capture protected units, bridge, PR122 site/current, winctl and ports before changing anything',
 'verify 124 source pins against current Tokyo; verify staged preliminary materials without treating them as final',
 'stage new versioned root and private data with no writes into shared /opt/trading-system',
 'resolve client bridge URL and authentic pin/HMAC to domestic existing bridge; no auth bypass',
 'prove non-mutating private-network auth-denial, restart and rollback on copied data',
 'obtain exact final source writer fence, one WAL-aware checkpoint and canonical target writer assignment',
 'install exact reviewed units only after final inputs; no automatic enable/start in preparation',
 'activate under one-use approval, test exact private health/auth routes, switch only approved upstream locations',
 'record before/after protected identity, all InvokeIds, health and writer reconciliation; then independent acceptance'],
 'rollback':[
 'before traffic/writer handoff: stop only newly introduced exact units, verify cgroups and listeners gone, preserve candidate and journal',
 'after routing but before accepted target writes: restore only saved exact route fragments after hash compare and nginx syntax check; revalidate original upstream',
 'after target writes: fence target first, reconcile committed target state through canonical recovery; never restore stale preliminary DB or blindly restart old writer',
 'restore previous unit bytes/modes only if prestate recorded and current bytes match this transaction; unknown changes HOLD',
 'never delete root-private source archives, v4 attempts, shared bridge, PR122 current, UK masks or Finance timers'],
 'remaining_gates':{
 'client_effective_bridge_endpoint_and_env':'PENDING: source defaults are not effective runtime config; no new secret values needed',
 'persistent_runtime_identity_and_bind_mounts':'PENDING: templates do not establish uid/mount compatibility or complete write-set',
 'real_auth_restart_rollback_acceptance':'PENDING: health200 alone insufficient',
 'final_snapshot_and_single_writer':'PENDING: preliminary165 copy is not canonical',
 'exact_install_cutover_independent_permission':'PENDING: existing RAM access is transport authorization',
 'model_executor_destination':'PENDING: domestic/Korea reverse19444 still lead to Tokyo20443; UK/P2 original writer owns replacement',
 'cloudflare_and_vpn_ownership':'PENDING: three host-network cloudflared containers and tailscale exit must be resolved',
 'finance_timers':'PRESERVE: four active Tokyo timers until explicit successor/retirement decision',
 'tokyo_retirement':'HOLD until every retained responsibility accepted or explicitly cancelled'},
 'owner_manual_commands_required':False,'background_executor_installed':False}
 files['PLAN.json']=encoded(plan)
 files['MANIFEST.json']=encoded({'schema':1,'status':plan['status'],'files':{p:digest(b) for p,b in sorted(files.items())},'private_credentials_included':False})
 return files

def archive(files):
 out=io.BytesIO()
 with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as t:
  for name,b in sorted(files.items()):
   i=tarfile.TarInfo(name);i.size=len(b);i.mode=0o600;i.mtime=0;i.uid=i.gid=0;t.addfile(i,io.BytesIO(b))
 return out.getvalue()
if __name__=='__main__':
 import sys
 need(len(sys.argv)==4,'USAGE_RUNTIME_ENDPOINTS_OUTPUT_NEW')
 files=compile_candidate(json.loads(Path(sys.argv[1]).read_bytes()),json.loads(Path(sys.argv[2]).read_bytes()))
 b=archive(files)
 with Path(sys.argv[3]).open('xb') as f:f.write(b)
 print(json.dumps({'status':'REVIEW_CANDIDATE_BUILT_NOT_INSTALLED','tar_sha256':digest(b),'bytes':len(b),'files':len(files),'service_actions':0},sort_keys=True))
