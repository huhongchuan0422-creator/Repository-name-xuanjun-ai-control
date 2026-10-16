#!/usr/bin/env python3
"""One-time fixed-host showcase installation. Requires a separate exact permit.

It does not change the main current pointer, existing preview Runtime or DNS.
Unknown/partial results are retained; only explicit owned rollback is allowed.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from scripts import pr122_showcase_promote as promotion
from scripts import pr122_site_hub_host_preflight as host_inventory
from scripts import pr122_site_hub_combined as fixed_ops
from scripts.pr122_showcase import need,sha,canonical
from scripts.pr122_showcase_sources import github

CODE=Path('/usr/local/lib/xuanjun-showcase')
CONFIG=Path('/etc/xuanjun-showcase')
NGINX=Path('/etc/nginx/pr122-showcase/locations.conf')
HTTPS=Path('/etc/nginx/conf.d/pr122-apex-https.conf')
STATE=Path('/var/lib/xuanjun-showcase-install')
SERVICE=Path('/etc/systemd/system/xuanjun-showcase-publish.service')
TIMER=Path('/etc/systemd/system/xuanjun-showcase-publish.timer')
MAIN_CURRENT=Path('/var/www/wenwenwenyiyiyi.work/current')
ENABLE=Path('/etc/systemd/system/timers.target.wants/xuanjun-showcase-publish.timer')
OWNER='huhongchuan0422-creator'
ANCHOR=b'include /etc/nginx/pr122-site-hub/locations.conf;'
EXTRA=b'include /etc/nginx/pr122-showcase/locations.conf;\n    '


def command(args):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    need(r.returncode==0,'COMMAND_FAILED:'+args[0]+':'+str(r.returncode));return r.stdout


def gate(comment_id,manifest_sha,fetch=github):
    comment=fetch('issues/comments/'+str(comment_id))
    need(comment['id']==comment_id and comment['user']['login']==OWNER and comment['issue_url'].endswith('/issues/122'),'INSTALL_APPROVAL_ORIGIN')
    need(comment['body'].startswith('XUANJUN_SHOWCASE_INSTALL\n'),'INSTALL_APPROVAL_FORMAT')
    approval=json.loads(comment['body'].split('\n',1)[1])
    need(approval.get('decision')=='INSTALL_APPROVED' and approval.get('mechanism_manifest_sha256')==manifest_sha and approval.get('max_executions')==1 and approval.get('rollback_approved') is True,'INSTALL_APPROVAL_BINDING')
    need(type(approval.get('issued_unix')) is int and type(approval.get('expires_unix')) is int and approval['issued_unix']<=time.time()<approval['expires_unix'] and 0<approval['expires_unix']-approval['issued_unix']<=7200,'INSTALL_APPROVAL_EXPIRY')
    review=fetch('issues/comments/'+str(approval['review_comment_id']))
    need(review['user']['login']==OWNER and review['issue_url'].endswith('/issues/122') and review['body'].startswith('XUANJUN_SHOWCASE_MECHANISM_REVIEW\n'),'INSTALL_INDEPENDENT_REVIEW_ORIGIN')
    from scripts.pr122_showcase_trust import verify as verify_independent
    verify_independent(review, 'MECHANISM')
    verdict=json.loads(review['body'].split('\n',1)[1])
    need(verdict.get('decision')=='AUDIT_PASS' and verdict.get('reviewer_role')=='INDEPENDENT_AUDITOR' and verdict.get('mechanism_manifest_sha256')==manifest_sha,'INSTALL_INDEPENDENT_REVIEW_BINDING')
    need(review['id']!=comment_id,'SEPARATE_INSTALL_REVIEW')
    for key in ('commit','ci_run_id'):need(verdict.get(key)==approval.get(key),'INSTALL_REVIEW_CI_BINDING')
    run=fetch('actions/runs/'+str(approval['ci_run_id']))
    need(run['head_sha']==approval['commit'] and run['conclusion']=='success' and run['workflow_id']==386249451,'INSTALL_EXACT_CI')
    return approval


def nginx_files():
    observed=host_inventory.nginx_source()
    need(observed['status']=='SOURCE_INVENTORY_COMPLETE' and observed['disk_config_trust'],'NGINX_SOURCE_UNTRUSTED')
    files={name:value['sha256'] for name,value in observed['files'].items()}
    return files

def nginx_snapshot():return sha(canonical(nginx_files()))

def nginx_identity():return fixed_ops.Ops().nginx_identity()

def read(path,engine):return engine.read_trusted_bytes(path,0)[0]
def write_new(path,raw,mode=0o644):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    except BaseException:raise


def install(source,comment_id):
    engine=promotion.load_engine();source=Path(source)
    raw=read(source/'MECHANISM_MANIFEST.json',engine);manifest=json.loads(raw);approval=gate(comment_id,sha(raw))
    need(approval['transaction_id']=='pr122-showcase-install-20261016','FIXED_INSTALL_TRANSACTION')
    folder=STATE/approval['transaction_id'];need(not folder.exists(),'INSTALL_TRANSACTION_EXISTS_NO_RETRY')
    files={}
    for row in manifest['files']:
        relative=Path(row['path']);need(not relative.is_absolute() and '..' not in relative.parts,'SOURCE_PATH')
        raw=read(source/relative,engine);need(len(raw)==row['size'] and sha(raw)==row['sha256'],'INSTALL_SOURCE_HASH');files[row['path']]=raw
    # Read-only preflight, before any installation transaction is created.
    for path in (CODE,NGINX.parent,SERVICE,TIMER,ENABLE):need(not path.exists() and not path.is_symlink(),'PREEXISTING_INSTALL_OBJECT:'+str(path))
    need(not (CONFIG/'policy.json').exists(),'PREEXISTING_POLICY')
    token=CONFIG/'github-readonly-token';raw=read(token,engine)
    need(raw.strip() and not token.stat().st_mode&0o077,'READONLY_GITHUB_CREDENTIAL_REQUIRED')
    old=read(HTTPS,engine);need(sha(old)==approval['previous_https_sha256'] and old.count(ANCHOR)==1 and EXTRA not in old,'HTTPS_BASELINE_DRIFT')
    current=os.readlink(MAIN_CURRENT);need(current==approval['main_current'],'MAIN_CURRENT_DRIFT')
    previous_inventory=nginx_snapshot();need(previous_inventory==approval['previous_nginx_inventory_sha256'],'NGINX_INVENTORY_DRIFT')
    previous_process=nginx_identity()
    inventory=command(['/usr/sbin/nginx','-T'])
    import re
    need(not re.search(rb'location\s+[^\n{]*?/showcase(?:/|[\s{])',inventory),'EXISTING_SHOWCASE_LOCATION')
    engine.secure_dir(STATE,0o700,0,True);folder.mkdir(mode=0o700)
    write_new(folder/'previous-https.conf',old,0o600)
    receipt={'state':'INSTALLING','approval':approval,'completed':[],'owned_files':{},'previous_https_sha256':sha(old),'main_current':current,'previous_nginx_files':nginx_files()}
    def save():engine.atomic_json(folder/'receipt.json',receipt)
    def emit(path,data):
        receipt['owned_files'][str(path)]=sha(data);save();write_new(path,data)
    save()
    try:
        engine.secure_dir(CODE,0o755,0,True);engine.secure_dir(CODE/'scripts',0o755,0,True)
        engine.secure_dir(NGINX.parent,0o755,0,True);engine.secure_dir(promotion.BASE,0o755,0,True)
        for name,data in files.items():
            if name.startswith('scripts/'):emit(CODE/name,data)
        emit(CODE/'MECHANISM_MANIFEST.json',read(source/'MECHANISM_MANIFEST.json',engine))
        emit(NGINX,files['deploy/pr122-showcase/locations.conf'])
        policy={'publishers':[OWNER],'reviewers':[OWNER],'github_token_file':str(token),'mechanism_manifest_sha256':sha(read(source/'MECHANISM_MANIFEST.json',engine))}
        emit(CONFIG/'policy.json',canonical(policy))
        emit(SERVICE,files['deploy/pr122-showcase/xuanjun-showcase-publish.service'])
        emit(TIMER,files['deploy/pr122-showcase/xuanjun-showcase-publish.timer'])
        receipt['completed'].append('FILES_INSTALLED');save()
        command(['/usr/bin/systemd-analyze','verify',str(SERVICE),str(TIMER)])
        # Existing HTTPS bytes must still match immediately before replacement.
        need(time.time()<approval['expires_unix'],'INSTALL_APPROVAL_EXPIRED_BEFORE_ACTIVATION')
        need(nginx_snapshot()==previous_inventory and nginx_identity()==previous_process,'NGINX_CHANGED_DURING_INSTALL')
        need(read(HTTPS,engine)==old,'HTTPS_CHANGED_DURING_INSTALL')
        patched=old.replace(ANCHOR,EXTRA+ANCHOR)
        receipt['patched_https_sha256']=sha(patched);receipt['intent']='HTTPS_REPLACE';save()
        temporary=HTTPS.with_name(HTTPS.name+'.showcase-'+approval['transaction_id'])
        receipt['owned_files'][str(temporary)]=sha(patched);save()
        write_new(temporary,patched);os.replace(temporary,HTTPS);engine.fsync_dir(HTTPS.parent)
        command(['/usr/sbin/nginx','-t']);command(['/usr/bin/systemctl','daemon-reload']);command(['/usr/bin/systemctl','reload','nginx.service'])
        receipt['completed'].append('NGINX_CONNECTED');receipt['intent']='TIMER_ENABLE';save()
        command(['/usr/bin/systemctl','enable','--now',TIMER.name])
        need(os.readlink(MAIN_CURRENT)==current,'MAIN_CURRENT_CHANGED')
        receipt.update(state='INSTALLED_AWAIT_FIRST_APPROVED_PUBLICATION',intent=None);save();return receipt
    except BaseException as error:
        receipt.update(state='HOLD_PARTIAL',failure=type(error).__name__);save();raise


def rollback():
    engine=promotion.load_engine();folder=STATE/'pr122-showcase-install-20261016'
    receipt=json.loads(read(folder/'receipt.json',engine));need(receipt['approval']['rollback_approved'] is True,'ROLLBACK_NOT_APPROVED')
    need(receipt['state']!='ROLLED_BACK','ALREADY_ROLLED_BACK')
    old=read(folder/'previous-https.conf',engine);need(sha(old)==receipt['previous_https_sha256'],'BACKUP_CONFIG_HASH')
    need(sha(read(HTTPS,engine)) in {sha(old),receipt.get('patched_https_sha256')},'FOREIGN_HTTPS_CONFIG')
    need(os.readlink(MAIN_CURRENT)==receipt['main_current'],'FOREIGN_MAIN_CURRENT')
    expected=dict(receipt['previous_nginx_files']);expected[str(HTTPS)]=sha(read(HTTPS,engine))
    if EXTRA in read(HTTPS,engine):expected[str(NGINX)]=receipt['owned_files'][str(NGINX)]
    need(nginx_files()==expected,'FOREIGN_NGINX_INCLUDE_SET')
    for name,expected in receipt['owned_files'].items():
        p=Path(name)
        if p.exists() or p.is_symlink():need(sha(read(p,engine))==expected,'FOREIGN_INSTALLED_FILE:'+name)
    if ENABLE.exists() or ENABLE.is_symlink():need(ENABLE.is_symlink() and ENABLE.lstat().st_uid==0 and os.readlink(ENABLE)==str(TIMER),'FOREIGN_TIMER_ENABLE')
    # Retain any approved showcase snapshots and their receipts; only remove the
    # owned delivery channel and restore the exact previous HTTPS include bytes.
    receipt.update(state='ROLLBACK_IN_PROGRESS');engine.atomic_json(folder/'receipt.json',receipt)
    command(['/usr/bin/systemctl','daemon-reload'])
    if str(TIMER) in receipt['owned_files'] and TIMER.exists():command(['/usr/bin/systemctl','disable','--now',TIMER.name])
    if str(SERVICE) in receipt['owned_files'] and SERVICE.exists():command(['/usr/bin/systemctl','stop',SERVICE.name])
    if read(HTTPS,engine)!=old:
        temporary=HTTPS.with_name(HTTPS.name+'.showcase-restore');write_new(temporary,old);os.replace(temporary,HTTPS);engine.fsync_dir(HTTPS.parent)
    command(['/usr/sbin/nginx','-t']);command(['/usr/bin/systemctl','reload','nginx.service'])
    for name in receipt['owned_files']:
        if Path(name).exists():Path(name).unlink()
    command(['/usr/bin/systemctl','daemon-reload'])
    need(read(HTTPS,engine)==old,'RESTORED_HTTPS_HASH')
    receipt.update(state='ROLLED_BACK',intent=None,runtime_changes=0,main_current_changes=0);engine.atomic_json(folder/'receipt.json',receipt);return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('install','rollback'));p.add_argument('--source',type=Path);p.add_argument('--approval-comment-id',type=int);args=p.parse_args()
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','FIXED_HOST_ROOT_REQUIRED');os.umask(0o022)
    if args.command=='install':need(args.source and args.approval_comment_id,'INSTALL_INPUTS_REQUIRED')
    import fcntl
    lock=Path('/var/lib/xuanjun-pr122-site-hub/transaction.lock')
    engine=promotion.load_engine()
    with engine.open_trusted_file(lock,0) as (fd,_):
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(install(args.source,args.approval_comment_id) if args.command=='install' else rollback(),sort_keys=True))

if __name__=='__main__':main()
