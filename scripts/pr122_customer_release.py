"""Fixed domestic first-install controller, separate review and exact plan permit.
No account/user creation, dependency installation, credential generation or DNS.
The Owner supplies pre-reviewed runtime, non-root account and private config.
Plan is read-only. Unknown/partial states never allow blind apply retry.
"""
import argparse
import json
import os
import pwd
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from scripts.pr122_customer_core import Denied,canonical,digest,private_path,secure_write

CODE=Path('/usr/local/lib/xuanjun-customer-center')
CONFIG=Path('/etc/xuanjun-customer-center')
STATE=Path('/var/lib/xuanjun-customer-release')
DATA=Path('/var/lib/xuanjun-customer-center')
HTTPS=Path('/etc/nginx/conf.d/pr122-apex-https.conf')
SNIPPET=Path('/etc/nginx/pr122-customer-center/locations.conf')
CURRENT=Path('/var/www/wenwenwenyiyiyi.work/current')
UNIT=Path('/etc/systemd/system')
TXN='pr122-customer-center-install-20261016'
ANCHOR=b'include /etc/nginx/pr122-site-hub/locations.conf;'
INCLUDE=b'include /etc/nginx/pr122-customer-center/locations.conf;\n    '
UNITS=('xuanjun-customer-center.service','xuanjun-customer-delivery.service','xuanjun-customer-delivery.timer')
LOCK=Path('/var/lib/xuanjun-pr122-site-hub/transaction.lock')
OWNER='huhongchuan0422-creator'
REPO=OWNER+'/Repository-name-xuanjun-ai-control'

def need(ok,msg):
    if not ok:raise Denied('HOLD:'+msg)
def run(args):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    need(p.returncode==0,'COMMAND:'+args[0]);return p.stdout

def source(source):
    source=private_path(source);raw=(source/'CUSTOMER_MANIFEST.json').read_bytes();manifest=json.loads(raw);files={}
    for row in manifest['files']:
        relative=Path(row['path']);need(not relative.is_absolute() and '..' not in relative.parts,'SOURCE_PATH')
        p=private_path(source/relative);b=p.read_bytes();need(len(b)==row['size'] and digest(b)==row['sha256'],'SOURCE_HASH');files[row['path']]=b
    need(len(files)==len(manifest['files']),'SOURCE_DUPLICATE');return manifest,raw,files

def inventory():
    # Reuse actual production Nginx source discovery, not guessed selectors/files.
    from scripts.pr122_site_hub_host_preflight import nginx_source
    value=nginx_source();need(value['status']=='SOURCE_INVENTORY_COMPLETE' and value['disk_config_trust'],'NGINX_TRUST')
    from scripts.pr122_site_hub_combined import Ops
    return {'files':{p:x['sha256'] for p,x in value['files'].items()},'master':Ops().nginx_identity()}

def private_config(path):
    private_path(path);s=path.stat();need(s.st_uid==0 and stat.S_ISREG(s.st_mode) and not s.st_mode&0o077,'ROOT_CONFIG_MODE');return json.loads(path.read_bytes())

def plan(folder):
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','HOST_OR_ROOT')
    manifest,raw,files=source(folder)
    need(sys.version_info[:2]>=(3,11),'PYTHON_3_11_REQUIRED')
    import cryptography
    need(cryptography.__version__=='46.0.3','REVIEWED_CRYPTOGRAPHY_46_0_3_REQUIRED')
    account=pwd.getpwnam('xuanjun-customer');need(account.pw_uid>0 and account.pw_gid>0 and account.pw_shell in ('/sbin/nologin','/usr/sbin/nologin','/bin/false'),'ISOLATED_ACCOUNT_REQUIRED')
    for p in (CODE,DATA,SNIPPET.parent,STATE/TXN,*[UNIT/u for u in UNITS]):need(not os.path.lexists(p),'PREEXISTING:'+str(p))
    from scripts.pr122_customer_core import Center
    from scripts.pr122_customer_providers import Providers
    c=private_config(CONFIG/'config.json');runtime=private_config(CONFIG/'runtime.json')
    need(set(runtime)=={'keys','active_key','providers'},'RUNTIME_CREDENTIAL_MINIMUM')
    need(c['keys']==runtime['keys'] and c['active_key']==runtime['active_key'] and c['providers']==runtime['providers'],'CONFIG_BINDING')
    import base64
    need(len(base64.b64decode(c['backup_key'],validate=True))==32 and len(base64.b64decode(c['authority_verify_key'],validate=True))>=32,'PROTECTED_KEYS_REQUIRED')
    need(c['backup_key_ref'] and c['active_key'] in c['keys'] and all(len(base64.b64decode(v,validate=True))==32 for v in c['keys'].values()),'DATA_KEY_MAPPING')
    providers=Providers(runtime['providers']).status();need(all(runtime['providers'].get(k) for k in ('smtp','telegram','feishu','secretref','web_ai')),'REAL_PROVIDER_CONFIG_REQUIRED')
    # Source-only tests cannot satisfy actual scan/KMS/provider/authority evidence.
    acceptance=private_config(CONFIG/'TARGET_ACCEPTANCE.json')
    required=('canonical_identity_mapping','canonical_order_contract_export','canonical_customer_project_mapping','key_backup_recovery','scanner_clean_and_eicar','smtp_verified_account_recovery','telegram_callback_identity','feishu_callback_identity','secretref_metadata_authority','web_ai_provider_identity')
    need(set(acceptance)=={'manifest_sha256','evidence'} and acceptance['manifest_sha256']==digest(raw) and set(acceptance['evidence'])==set(required),'TARGET_ACCEPTANCE_BINDING')
    for key in required:
        v=acceptance['evidence'][key];need(type(v) is dict and set(v)=={'sha256','path'} and len(v['sha256'])==64,'TARGET_EVIDENCE_SCHEMA')
        p=private_path(v['path']);need(p.is_absolute() and str(p).startswith('/var/lib/xuanjun-customer-preflight/') and p.stat().st_uid==0 and not p.stat().st_mode&0o077 and digest(p.read_bytes())==v['sha256'],'TARGET_EVIDENCE_HASH')
    import grp
    grp.getgrnam('nginx')
    need(not os.path.lexists('/run/xuanjun-customer-api/http.sock'),'SOCKET_OCCUPIED')
    nginx=run(['/usr/sbin/nginx','-T']);need(b'/customer/center' not in nginx,'EXISTING_CUSTOMER_LOCATION')
    old=private_path(HTTPS).read_bytes();need(old.count(ANCHOR)==1 and INCLUDE not in old,'HTTPS_ANCHOR')
    baseline=inventory();run(['/usr/sbin/nginx','-t'])
    return {'state':'READONLY_PLAN','transaction':TXN,'manifest_sha256':digest(raw),'source_commit':manifest['source_commit'],'main_current':os.readlink(CURRENT),'previous_https_sha256':digest(old),'nginx':baseline,'account_uid':account.pw_uid,'account_gid':account.pw_gid,'config_sha256':digest((CONFIG/'config.json').read_bytes()),'runtime_config_sha256':digest((CONFIG/'runtime.json').read_bytes()),'target_acceptance_sha256':digest((CONFIG/'TARGET_ACCEPTANCE.json').read_bytes()),'production_changes':0}

def github(path):
    token=private_path(CONFIG/'github-readonly-token');st=token.stat();need(st.st_uid==0 and not st.st_mode&0o077,'GITHUB_READONLY_CREDENTIAL')
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,headers={'Authorization':'Bearer '+token.read_text().strip(),'Accept':'application/vnd.github+json','User-Agent':'PR122-Customer-Controlled-Release'})
    from scripts.pr122_customer_providers import NoRedirect
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as r:
        raw=r.read(2_000_001);need(len(raw)<=2_000_000,'GITHUB_RESPONSE_LIMIT');return json.loads(raw)

def gate(comment_id,expected_plan,fetch=github):
    c=fetch('issues/comments/'+str(comment_id));need(c['id']==comment_id and c['user']['login']==OWNER and c['issue_url'].endswith('/issues/122') and c['body'].startswith('XUANJUN_CUSTOMER_INSTALL\n'),'APPROVAL_ORIGIN')
    a=json.loads(c['body'].split('\n',1)[1]);need(a['decision']=='INSTALL_APPROVED' and a['transaction']==TXN and a['plan_sha256']==digest(canonical(expected_plan)) and a['manifest_sha256']==expected_plan['manifest_sha256'] and a['source_commit']==expected_plan['source_commit'] and a['max_executions']==1 and a['rollback_approved'] is True,'APPROVAL_BINDING')
    need(type(a['issued_unix']) is int and type(a['expires_unix']) is int and a['issued_unix']<=time.time()<a['expires_unix'] and 0<a['expires_unix']-a['issued_unix']<=7200,'APPROVAL_EXPIRY')
    r=fetch('issues/comments/'+str(a['review_comment_id']));need(r['id']!=comment_id and r['user']['login']==OWNER and r['issue_url'].endswith('/issues/122') and r['body'].startswith('XUANJUN_CUSTOMER_REVIEW\n'),'INDEPENDENT_REVIEW_ORIGIN')
    v=json.loads(r['body'].split('\n',1)[1]);need(v['decision']=='AUDIT_PASS' and v['reviewer_role']=='INDEPENDENT_AUDITOR' and v['manifest_sha256']==a['manifest_sha256'] and v['source_commit']==a['source_commit'] and v['ci_run_id']==a['ci_run_id'],'INDEPENDENT_REVIEW_BINDING')
    ci=fetch('actions/runs/'+str(a['ci_run_id']));need(ci['conclusion']=='success' and ci['head_sha']==a['source_commit'] and ci['path']=='.github/workflows/pr122-customer-center.yml' and ci['event'] in ('push','workflow_dispatch'),'EXACT_CUSTOMER_CI')
    return a

def atomic_json(p,d):
    import secrets
    temp=p.with_name(p.name+'.new-'+secrets.token_hex(8));secure_write(temp,canonical(d));os.replace(temp,p)
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def runtime_check(expected_uid):
    pid=run(['/usr/bin/systemctl','show',UNITS[0],'-p','MainPID','--value']).decode().strip();need(pid.isdigit() and int(pid)>1,'RUNTIME_PID')
    proc=Path('/proc')/pid;status=(proc/'status').read_text();uid=status.split('Uid:')[1].split()[0]
    need(int(uid)==expected_uid and uid!='0','NON_ROOT_RUNTIME')
    need('NoNewPrivs:\t1' in status and int(status.split('CapEff:')[1].split()[0],16)==0,'RUNTIME_PRIVILEGES')
    need(os.readlink(proc/'ns/mnt')!=os.readlink('/proc/1/ns/mnt'),'SEPARATE_MOUNT_NAMESPACE')

def apply(folder,comment):
    # Lock original website/Nginx mutation boundary, shared with showcase install.
    import fcntl
    lock=private_path(LOCK);fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        observed=plan(folder);approval=gate(comment,observed);manifest,raw,files=source(folder)
        STATE.mkdir(mode=0o700,exist_ok=True);txn=STATE/TXN;txn.mkdir(mode=0o700)
        receipt={'state':'INSTALLING','approval_comment':comment,'approval':approval,'plan':observed,'owned':{},'completed':[],'intent':None}
        def save():atomic_json(txn/'receipt.json',receipt)
        save();old=HTTPS.read_bytes();secure_write(txn/'https.before',old)
        try:
            # Recheck process/source drift and permit after durable backup.
            need(plan_without_absence(observed)==observed,'ACTIVATION_DRIFT');gate(comment,observed)
            CODE.mkdir(mode=0o755);receipt['completed'].append('CODE_DIRECTORY');save()
            for relative,b in files.items():
                p=CODE/relative;p.parent.mkdir(mode=0o755,parents=True,exist_ok=True);receipt['owned'][str(p)]=digest(b);receipt['intent']=str(p);save();secure_write(p,b);os.chmod(p,0o644);receipt['intent']=None;save()
            receipt['owned'][str(CODE/'CUSTOMER_MANIFEST.json')]=digest(raw);receipt['intent']='MANIFEST';save();secure_write(CODE/'CUSTOMER_MANIFEST.json',raw);os.chmod(CODE/'CUSTOMER_MANIFEST.json',0o644);receipt['intent']=None;save()
            SNIPPET.parent.mkdir(mode=0o755)
            for p,b in [(SNIPPET,files['deploy/pr122-customer-center/locations.conf'])]+[(UNIT/u,files['deploy/pr122-customer-center/'+u]) for u in UNITS]:
                receipt['intent']=str(p);receipt['owned'][str(p)]=digest(b);save();secure_write(p,b);os.chmod(p,0o644);receipt['intent']=None;save()
            receipt['intent']='START_RUNTIME';save();run(['/usr/bin/systemctl','daemon-reload']);run(['/usr/bin/systemd-analyze','verify',*[str(UNIT/u) for u in UNITS]]);run(['/usr/bin/systemctl','start',UNITS[0]]);receipt['completed'].append('RUNTIME_STARTED');receipt['intent']=None;save()
            runtime_check(observed['account_uid'])
            need(time.time()<approval['expires_unix'],'APPROVAL_EXPIRED_BEFORE_NGINX')
            need(digest(HTTPS.read_bytes())==observed['previous_https_sha256'] and inventory()==observed['nginx'] and os.readlink(CURRENT)==observed['main_current'],'BEFORE_NGINX_DRIFT')
            new=old.replace(ANCHOR,INCLUDE+ANCHOR);receipt['new_https_sha256']=digest(new);receipt['intent']='NGINX_INSTALL';save()
            temp=HTTPS.with_name('pr122-customer.temporary');secure_write(temp,new);os.chmod(temp,0o644);os.replace(temp,HTTPS);receipt['completed'].append('NGINX_INSTALLED');receipt['intent']=None;save()
            run(['/usr/sbin/nginx','-t']);run(['/usr/bin/systemctl','reload','nginx']);run(['/usr/bin/systemctl','enable','--now',UNITS[2]])
            data=run(['/usr/bin/curl','--noproxy','*','--resolve','wenwenwenyiyiyi.work:443:127.0.0.1','--fail','--silent','--show-error','--max-time','15','https://wenwenwenyiyiyi.work/customer/center/'])
            need(digest(data)==digest(files['deploy/pr122-customer-center/ui/index.html']),'REAL_HTTPS_HTML')
            receipt['state']='HTTPS_SMOKE_PASS_AWAIT_14_REAL_ACCEPTANCE';receipt['completed'].append('HTTPS_SMOKE');save();return receipt
        except BaseException:
            receipt['state']='HOLD_PARTIAL';save();raise

def plan_without_absence(expected):
    # No new effects yet except the release receipt and its root-private backup.
    value=dict(expected);value['nginx']=inventory();value['main_current']=os.readlink(CURRENT);value['previous_https_sha256']=digest(HTTPS.read_bytes())
    for key,path in [('config_sha256',CONFIG/'config.json'),('runtime_config_sha256',CONFIG/'runtime.json'),('target_acceptance_sha256',CONFIG/'TARGET_ACCEPTANCE.json')]:value[key]=digest(path.read_bytes())
    return value

def rollback():
    import fcntl
    fd=os.open(private_path(LOCK),os.O_RDWR|os.O_NOFOLLOW)
    with os.fdopen(fd,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _rollback_locked()

def _rollback_locked():
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','HOST_OR_ROOT')
    txn=STATE/TXN;r=json.loads(private_path(txn/'receipt.json').read_bytes());need(r['approval']['rollback_approved'] is True and r['state']!='ROLLED_BACK','OWNED_ROLLBACK')
    old=(txn/'https.before').read_bytes();need(digest(old)==r['plan']['previous_https_sha256'] and os.readlink(CURRENT)==r['plan']['main_current'],'BACKUP_OR_MAIN_DRIFT')
    for p,h in r['owned'].items():
        if os.path.lexists(p):need(private_path(p).is_file() and digest(Path(p).read_bytes())==h,'OWNED_FILE_DRIFT')
    current=HTTPS.read_bytes();need(digest(current) in (r['plan']['previous_https_sha256'],r.get('new_https_sha256')),'HTTPS_FOREIGN_DRIFT')
    # Original Nginx files other than our one source must be unchanged.
    observed=inventory()['files'];oldmap=r['plan']['nginx']['files']
    for p,h in oldmap.items():
        if p!=str(HTTPS):need(observed.get(p)==h,'FOREIGN_NGINX_DRIFT')
    need(set(observed).issubset(set(oldmap)|{str(SNIPPET)}),'FOREIGN_NGINX_ADDITION')
    enable=UNIT/'timers.target.wants'/UNITS[2]
    if os.path.lexists(enable):need(enable.is_symlink() and enable.lstat().st_uid==0 and os.readlink(enable)==str(UNIT/UNITS[2]),'FOREIGN_TIMER_ENABLE')
    r['state']='ROLLING_BACK';atomic_json(txn/'receipt.json',r)
    # Only newly-owned units; absent/not-started phases are handled explicitly.
    if str(UNIT/UNITS[2]) in r['owned'] and (UNIT/UNITS[2]).exists():run(['/usr/bin/systemctl','disable','--now',UNITS[2]])
    if str(UNIT/UNITS[0]) in r['owned'] and (UNIT/UNITS[0]).exists():run(['/usr/bin/systemctl','stop',UNITS[0]])
    if digest(current)!=digest(old):
        temp=HTTPS.with_name('pr122-customer.rollback');secure_write(temp,old);os.chmod(temp,0o644);os.replace(temp,HTTPS);run(['/usr/sbin/nginx','-t']);run(['/usr/bin/systemctl','reload','nginx'])
    for path in list(r['owned']):
        p=Path(path)
        if not str(p).startswith(str(CODE)+'/') and p.exists():p.unlink()
    run(['/usr/bin/systemctl','daemon-reload'])
    # Code, private project data, keys and all receipts retained, never restore an
    # old account DB or resurrect revoked grants as part of binary rollback.
    r['state']='ROLLED_BACK';r['private_data_preserved']=True;r['real_browser']='PENDING';atomic_json(txn/'receipt.json',r);return r

def main():
    os.umask(0o022)
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('plan','apply','rollback'));ap.add_argument('--source');ap.add_argument('--approval',type=int);a=ap.parse_args()
    result=plan(a.source) if a.action=='plan' else apply(a.source,a.approval) if a.action=='apply' else rollback()
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
