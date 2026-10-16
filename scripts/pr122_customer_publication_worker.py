"""Credential-isolated local publisher. No model/network/shell calls.
Only valid independently signed reports can update canonical delivery snapshots.
"""
import base64
import ctypes
import fcntl
import json
import os
from pathlib import Path
import pwd
import socket
import stat
from scripts.pr122_customer_core import Center,Denied,canonical,digest,private_path
from scripts.pr122_customer_delivery_source import issue

DATA=Path('/var/lib/xuanjun-customer-center')
NOTIFY='/run/xuanjun-customer-publication/notify.sock'

def enqueue(c,uid,project,case,serve_id,report):
    c.project(uid,project,{'REVIEWER'})
    packet={'project':project,'case':case,'serve_id':serve_id,'report':report};raw=canonical(packet)
    if len(raw)>100000 or type(report) is not dict or set(report)!={'payload','key_id','signature'}:raise Denied('BOUNDED_SIGNED_REPORT_REQUIRED')
    key=digest(canonical({'actor':uid,'packet':packet}))
    with c.tx():
        c.project(uid,project,{'REVIEWER'});c.limit('publication:'+uid+':'+project,20,3600)
        c.db.execute('INSERT OR IGNORE INTO preview_publication_jobs VALUES(?,?,?,?,?,?,?)',(key,project,uid,'QUEUED',c.encrypt(raw,key),c.now(),None))
        c.audit(project,uid,'DELIVERY_REPORT_QUEUED',key)
    state=c.db.execute('SELECT state FROM preview_publication_jobs WHERE id=?',(key,)).fetchone()[0]
    notified=False
    try:
        if state!='QUEUED':return {'id':key,'state':state,'notification_sent':False,'queue_result_is_not_acceptance':True}
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:s.settimeout(.2);s.sendto(b'1',NOTIFY);notified=True
    except OSError:pass # Timer drains durable queue if socket is absent/unavailable.
    return {'id':key,'state':state,'notification_sent':notified,'queue_result_is_not_acceptance':True}

def status(c,uid,project,job):
    c.project(uid,project,{'REVIEWER'})
    row=c.db.execute('SELECT * FROM preview_publication_jobs WHERE id=? AND project=?',(job,project)).fetchone()
    if not row:raise Denied('PUBLICATION_JOB_NOT_FOUND')
    return {'id':row['id'],'state':row['state'],'result':json.loads(c.decrypt(row['result'],'result:'+row['id'])) if row['result'] else None,'queue_result_is_not_acceptance':True}

def drain(c,trust,key):
    done=held=0
    rows=c.db.execute("SELECT * FROM preview_publication_jobs WHERE state='QUEUED' ORDER BY created,id LIMIT 8").fetchall()
    for row in rows:
        with c.tx():
            changed=c.db.execute("UPDATE preview_publication_jobs SET state='PROCESSING' WHERE id=? AND state='QUEUED'",(row['id'],)).rowcount
            if changed!=1:continue
        try:
            c.project(row['actor'],row['project'],{'REVIEWER'})
            packet=json.loads(c.decrypt(row['payload'],row['id']))
            result=issue(c,packet['project'],packet['case'],packet['serve_id'],packet['report'],trust,key);state='DONE';done+=1
        except BaseException:
            result={'state':'HOLD_INVALID_OR_UNKNOWN','retry_allowed':False};state='HOLD_UNKNOWN';held+=1
        with c.tx():
            c.db.execute('UPDATE preview_publication_jobs SET state=?,result=? WHERE id=?',(state,c.encrypt(canonical(result),'result:'+row['id']),row['id']))
            c.audit(row['project'],'publisher','PUBLICATION_'+state,row['id'])
    unknown=c.db.execute("SELECT COUNT(*) FROM preview_publication_jobs WHERE state IN ('PROCESSING','HOLD_UNKNOWN')").fetchone()[0]
    return {'done':done,'held':held,'unknown':unknown,'model_api_calls':0,'automatic_retry':False}

def nondumpable():
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(4,0,0,0,0)!=0 or libc.prctl(3,0,0,0,0)!=0:raise Denied('EFFECTIVE_NONDUMPABLE_REQUIRED')

def main_worker():
    if os.geteuid()!=0 or os.uname().nodename!='iZvt5t8tlrm8oiZ':raise Denied('PROTECTED_PUBLISHER_START_REQUIRED')
    cred=private_path(Path(os.environ.get('CREDENTIALS_DIRECTORY','/nonexistent'))/'publisher.json')
    for p in (cred,*cred.parents):
        s=p.lstat()
        if s.st_uid!=0 or s.st_mode&0o022:raise Denied('ROOT_PUBLISHER_CREDENTIAL_PATH')
    s=cred.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_mode&0o077 or s.st_nlink!=1 or s.st_size>1000000:raise Denied('ROOT_PUBLISHER_CREDENTIAL_REQUIRED')
    config=json.loads(cred.read_bytes())
    if set(config)!={'keys','active_key','authority_sign_key','preview_test_trust'}:raise Denied('PUBLISHER_MINIMUM_CREDENTIALS')
    # Drain only fixed activation datagrams, never parse commands/paths from socket.
    if os.environ.get('LISTEN_PID')==str(os.getpid()) and os.environ.get('LISTEN_FDS')=='1':
        with socket.socket(fileno=3) as activation:
            if activation.family!=socket.AF_UNIX or activation.type!=socket.SOCK_DGRAM:raise Denied('FIXED_ACTIVATION_SOCKET')
            activation.setblocking(False)
            for _ in range(128):
                try:activation.recv(1)
                except BlockingIOError:break
    account=pwd.getpwnam('xuanjun-customer')
    if account.pw_uid<=0 or account.pw_gid<=0:raise Denied('PUBLISHER_NONROOT_IDENTITY')
    os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid);nondumpable();os.umask(0o077)
    c=Center(DATA,{k:base64.b64decode(v,validate=True) for k,v in config['keys'].items()},config['active_key'])
    try:
        lock=DATA/'publication-worker.lock'
        fd=os.open(lock,os.O_RDONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'rb') as held:
            st=os.fstat(held.fileno())
            if st.st_uid!=account.pw_uid or not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_mode&0o077:raise Denied('PUBLISHER_LOCK_IDENTITY')
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return {**drain(c,config['preview_test_trust'],base64.b64decode(config['authority_sign_key'],validate=True)),'uid':os.geteuid(),'gid':os.getegid(),'effective_nondumpable':True,'providers_loaded':False}
    finally:c.db.close()
