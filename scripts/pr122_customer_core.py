"""PR122 server-owned identity/project/material service; no production bootstrap.

All methods are called by the authenticated HTTP boundary or the protected
operator command. Request JSON never supplies actors, verified flags or grants.
"""
import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from scripts.community_merchant_contract import valid_id

class Denied(PermissionError): pass
class Conflict(ValueError): pass
class Unavailable(RuntimeError): pass

def canonical(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
def digest(v): return hashlib.sha256(v).hexdigest()
def identifier(v):
    if not valid_id(v): raise ValueError('INVALID_ID')
    return v
def email(v):
    if type(v) is not str or not re.fullmatch(r'[^\s@]{1,100}@[^\s@.]{1,150}\.[^\s@]{2,40}',v): raise ValueError('INVALID_EMAIL')
    return v.casefold()
def safe_text(v, limit=4000):
    if type(v) is not str or not 1 <= len(v.strip()) <= limit: raise ValueError('INVALID_TEXT')
    # Additional guard, NOT a claim to detect arbitrary secrets in documents.
    if re.search(r'(?i)(BEGIN [\w ]*PRIVATE KEY|api[_ -]?key\s*[:=]|appsecret\s*[:=]|access_token\s*[:=]|password\s*[:=]|sk-[A-Za-z0-9]{12})',v):
        raise Denied('USE_OAUTH_OR_SECRETREF')
    return v

def private_path(p):
    p=Path(p)
    for q in (p, *p.parents):
        if q.is_symlink(): raise Denied('SYMLINK_PATH')
    return p

def secure_write(p, raw):
    private_path(p)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())

DDL='''
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,email_idx TEXT UNIQUE NOT NULL,email_enc BLOB NOT NULL,salt BLOB NOT NULL,password BLOB NOT NULL,verified INTEGER NOT NULL DEFAULT 0,epoch INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,epoch INTEGER NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS challenges(token TEXT PRIMARY KEY,kind TEXT NOT NULL,user_id TEXT NOT NULL,payload BLOB NOT NULL,expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rate_limits(k TEXT PRIMARY KEY,window INTEGER NOT NULL,n INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,customer TEXT NOT NULL,owner TEXT NOT NULL,authority_ref TEXT NOT NULL,revision INTEGER NOT NULL,expires INTEGER NOT NULL,payload BLOB NOT NULL,active INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS project_history(project TEXT NOT NULL,revision INTEGER NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(project,revision));
CREATE TABLE IF NOT EXISTS members(project TEXT NOT NULL,user_id TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL,PRIMARY KEY(project,user_id));
CREATE TABLE IF NOT EXISTS items(project TEXT NOT NULL,item TEXT NOT NULL,seq INTEGER NOT NULL,state TEXT NOT NULL,accepted INTEGER,PRIMARY KEY(project,item));
CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,project TEXT NOT NULL,item TEXT NOT NULL,seq INTEGER NOT NULL,actor TEXT NOT NULL,kind TEXT NOT NULL,payload BLOB NOT NULL,expires INTEGER,created INTEGER NOT NULL,UNIQUE(project,item,seq));
CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,version TEXT NOT NULL,project TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,sha TEXT NOT NULL,scan TEXT NOT NULL,key_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,project TEXT NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL,object_id TEXT NOT NULL,at INTEGER NOT NULL,parent TEXT NOT NULL,sha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS links(channel TEXT NOT NULL,subject_idx TEXT NOT NULL,user_id TEXT NOT NULL,project TEXT NOT NULL,payload BLOB NOT NULL,active INTEGER NOT NULL,PRIMARY KEY(channel,subject_idx,project));
CREATE TABLE IF NOT EXISTS events(channel TEXT NOT NULL,event_id TEXT NOT NULL,at INTEGER NOT NULL,PRIMARY KEY(channel,event_id));
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,project TEXT NOT NULL,user_id TEXT NOT NULL,channel TEXT NOT NULL,payload BLOB NOT NULL,status TEXT NOT NULL,provider_ref TEXT,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_jobs(message_id TEXT PRIMARY KEY,state TEXT NOT NULL,result_id TEXT);
CREATE TABLE IF NOT EXISTS change_events(id TEXT PRIMARY KEY,project TEXT NOT NULL,case_id TEXT NOT NULL,seq INTEGER NOT NULL,kind TEXT NOT NULL,actor TEXT NOT NULL,payload BLOB NOT NULL,created INTEGER NOT NULL,UNIQUE(project,case_id,seq));
CREATE TABLE IF NOT EXISTS preview_delivery_proofs(sha256 TEXT PRIMARY KEY,project TEXT NOT NULL,case_id TEXT NOT NULL,payload BLOB NOT NULL);
CREATE TRIGGER IF NOT EXISTS preview_delivery_no_update BEFORE UPDATE ON preview_delivery_proofs BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS preview_delivery_no_delete BEFORE DELETE ON preview_delivery_proofs BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TABLE IF NOT EXISTS preview_serves(id TEXT PRIMARY KEY,project TEXT NOT NULL,actor TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,page_sha256 TEXT NOT NULL,render_sha256 TEXT NOT NULL,payload BLOB NOT NULL,created INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS preview_serve_no_update BEFORE UPDATE ON preview_serves BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS preview_serve_no_delete BEFORE DELETE ON preview_serves BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TABLE IF NOT EXISTS change_authority(id TEXT PRIMARY KEY,payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS change_authority_history(revision INTEGER PRIMARY KEY,payload BLOB NOT NULL);
CREATE TRIGGER IF NOT EXISTS change_source_no_update BEFORE UPDATE ON change_authority_history BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS change_source_no_delete BEFORE DELETE ON change_authority_history BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS changes_no_update BEFORE UPDATE ON change_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS changes_no_delete BEFORE DELETE ON change_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,kind TEXT NOT NULL,user_id TEXT NOT NULL,payload BLOB NOT NULL,status TEXT NOT NULL,at INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS versions_no_update BEFORE UPDATE ON versions BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS versions_no_delete BEFORE DELETE ON versions BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
'''

class Center:
    def __init__(self, root, keys, active_key, *, clock=time.time, mail_ready=False, scanner=None, secretref=None):
        self.root=private_path(root); self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.stat().st_mode & 0o077: raise Denied('PRIVATE_ROOT_MODE')
        self.objects=self.root/'objects'; self.objects.mkdir(mode=0o700,exist_ok=True)
        self.keys={identifier(k):v for k,v in keys.items()}
        if any(type(v) is not bytes or len(v)!=32 for v in self.keys.values()) or active_key not in keys: raise ValueError('KMS_KEYS_REQUIRED')
        self.key_id=active_key; self.clock=clock; self.mail_ready=mail_ready; self.scanner=scanner; self.secretref=secretref
        dbp=self.root/'center.sqlite'; private_path(dbp)
        self.db=sqlite3.connect(dbp,isolation_level=None,timeout=15)
        os.chmod(dbp,0o600); self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL'); self.db.execute('PRAGMA foreign_keys=ON'); self.db.executescript(DDL)
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('authority_revision','0')")
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('maintenance','0')")
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('index_key',?)",(self.key_id,))
        self.index_key=self.db.execute("SELECT v FROM settings WHERE k='index_key'").fetchone()[0]
        if self.index_key not in keys: raise Unavailable('INDEX_KEY_RESTORE_REQUIRED')
    def now(self): return int(self.clock())
    def idx(self,value): return hmac.new(self.keys[self.index_key],value.encode(),hashlib.sha256).hexdigest()
    def encrypt(self,value,aad):
        nonce=secrets.token_bytes(12)
        return canonical({'key':self.key_id,'data':base64.b64encode(nonce+AESGCM(self.keys[self.key_id]).encrypt(nonce,value,aad.encode())).decode()})
    def decrypt(self,value,aad):
        d=json.loads(value); raw=base64.b64decode(d['data'],validate=True)
        return AESGCM(self.keys[d['key']]).decrypt(raw[:12],raw[12:],aad.encode())
    @contextlib.contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield; self.db.commit()
        except BaseException: self.db.rollback(); raise
    def audit(self,project,actor,event,obj):
        prev=self.db.execute('SELECT sha FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        parent=prev[0] if prev else '0'*64; at=self.now()
        sha=digest(canonical([project,actor,event,obj,at,parent]))
        self.db.execute('INSERT INTO audit(project,actor,event,object_id,at,parent,sha) VALUES(?,?,?,?,?,?,?)',(project,actor,event,obj,at,parent,sha))
    def limit(self,scope,limit=8,seconds=900):
        k=self.idx(scope); now=self.now(); row=self.db.execute('SELECT window,n FROM rate_limits WHERE k=?',(k,)).fetchone()
        start,n=(row[0],row[1]) if row and now-row[0]<seconds else (now,0)
        if n>=limit: raise Denied('RATE_LIMIT')
        self.db.execute('INSERT OR REPLACE INTO rate_limits VALUES(?,?,?)',(k,start,n+1))
    def password(self,p,salt):
        if type(p) is not str or not 12<=len(p)<=128: raise ValueError('PASSWORD_12_TO_128')
        return hashlib.scrypt(p.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    def challenge(self,kind,user,payload,ttl=600):
        token=secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO challenges VALUES(?,?,?,?,?,0)',(digest(token.encode()),kind,user,self.encrypt(canonical(payload),'challenge'),self.now()+ttl))
        return token
    def consume(self,token,kind,user=None):
        if type(token) is not str or len(token)>128: raise Denied('INVALID_CHALLENGE')
        r=self.db.execute('SELECT * FROM challenges WHERE token=?',(digest(token.encode()),)).fetchone()
        if not r or r['kind']!=kind or r['used'] or r['expires']<=self.now() or (user and r['user_id']!=user): raise Denied('INVALID_CHALLENGE')
        self.db.execute('UPDATE challenges SET used=1 WHERE token=?',(r['token'],))
        return r['user_id'],json.loads(self.decrypt(r['payload'],'challenge'))
    def register(self,address,password):
        if not self.mail_ready: raise Unavailable('VERIFICATION_CHANNEL_PENDING')
        address=email(address); salt=secrets.token_bytes(16); pw=self.password(password,salt)
        with self.tx():
            self.limit('register:'+address,3)
            old=self.db.execute('SELECT id,verified FROM accounts WHERE email_idx=?',(self.idx(address),)).fetchone()
            if old:
                if not old['verified']:
                    self.db.execute("UPDATE challenges SET used=1 WHERE user_id=? AND kind='verify'",(old['id'],))
                    self.db.execute("UPDATE outbox SET status='CANCELLED' WHERE user_id=? AND kind='VERIFY' AND status='PENDING'",(old['id'],))
                    token=self.challenge('verify',old['id'],{});oid=secrets.token_hex(16)
                    self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,'VERIFY',old['id'],self.encrypt(canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()))
                return {'status':'CHECK_VERIFICATION_CHANNEL'}
            uid='u_'+secrets.token_hex(12)
            self.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password) VALUES(?,?,?,?,?)',(uid,self.idx(address),self.encrypt(address.encode(),uid),salt,pw))
            token=self.challenge('verify',uid,{})
            oid=secrets.token_hex(16)
            self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,'VERIFY',uid,self.encrypt(canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()))
            self.audit('',uid,'REGISTER',uid)
        return {'status':'CHECK_VERIFICATION_CHANNEL'}
    def verify(self,token,password):
        # Mailbox owner sets the activation password; a pre-registration attacker
        # must not retain the password chosen before email ownership verification.
        salt=secrets.token_bytes(16);pw=self.password(password,salt)
        with self.tx():
            uid,_=self.consume(token,'verify'); self.db.execute('UPDATE accounts SET verified=1,salt=?,password=?,epoch=epoch+1 WHERE id=?',(salt,pw,uid)); self.audit('',uid,'EMAIL_VERIFIED',uid)
        return {'verified':True}
    def login(self,address,password):
        address=email(address)
        # Failure counters must commit even when credential verification fails.
        with self.tx(): self.limit('login:'+address)
        r=self.db.execute('SELECT * FROM accounts WHERE email_idx=?',(self.idx(address),)).fetchone()
        salt=r['salt'] if r else b'0'*16
        good=hmac.compare_digest(self.password(password,salt), r['password'] if r else b'0'*32)
        if not r or not good or not r['verified']: raise Denied('INVALID_CREDENTIALS')
        token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
        with self.tx():
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token.encode()),r['id'],r['epoch'],digest(csrf.encode()),self.now()+3600))
            self.audit('',r['id'],'LOGIN',r['id'])
        return {'token':token,'csrf':csrf,'user_id':r['id']}
    def session(self,token,csrf=None):
        if self.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0]!='0': raise Unavailable('MAINTENANCE')
        if type(token) is not str or len(token)>128: raise Denied('AUTH_REQUIRED')
        r=self.db.execute('SELECT s.*,a.epoch current_epoch,a.verified FROM sessions s JOIN accounts a ON a.id=s.user_id WHERE s.token=?',(digest(token.encode()),)).fetchone()
        if not r or not r['verified'] or r['epoch']!=r['current_epoch'] or r['expires']<=self.now(): raise Denied('AUTH_REQUIRED')
        if csrf is not None and (type(csrf) is not str or not hmac.compare_digest(r['csrf'],digest(csrf.encode()))): raise Denied('CSRF_REQUIRED')
        return r['user_id']
    def logout(self,token):
        with self.tx(): self.db.execute('DELETE FROM sessions WHERE token=?',(digest(token.encode()),))
    def request_reset(self,address):
        if not self.mail_ready: raise Unavailable('VERIFICATION_CHANNEL_PENDING')
        address=email(address)
        with self.tx():
            self.limit('reset:'+address,3)
            r=self.db.execute('SELECT id FROM accounts WHERE email_idx=?',(self.idx(address),)).fetchone()
            if r:
                token=self.challenge('reset',r[0],{}); oid=secrets.token_hex(16)
                self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,'RESET',r[0],self.encrypt(canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()))
        return {'status':'CHECK_VERIFICATION_CHANNEL'}
    def reset(self,token,password):
        salt=secrets.token_bytes(16); pw=self.password(password,salt)
        with self.tx():
            uid,_=self.consume(token,'reset')
            self.db.execute('UPDATE accounts SET salt=?,password=?,epoch=epoch+1 WHERE id=?',(salt,pw,uid))
            self.db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            self.db.execute('UPDATE links SET active=0 WHERE user_id=?',(uid,))
            self.db.execute("UPDATE challenges SET used=1 WHERE user_id=? AND kind IN ('reset','invite','bind')",(uid,))
            self.audit('',uid,'PASSWORD_RESET',uid)
        return {'reset':True}
    def import_authority(self,document,key):
        """Protected operator only. This is an admission adapter, not a new CRM ledger.
        Full signed snapshots with monotonically increasing revisions revoke absent
        projects/grants. Canonical order/contract exporter must be mapped on target.
        """
        if len(key)<32 or set(document)!={'payload','signature'}: raise Denied('AUTHORITY_REQUIRED')
        data=document['payload']
        if not hmac.compare_digest(hmac.new(key,canonical(data),hashlib.sha256).hexdigest(),document['signature']): raise Denied('AUTHORITY_SIGNATURE')
        if set(data)!={'revision','expires','projects'} or type(data['revision']) is not int or not self.now()<data['expires']<=self.now()+86400: raise Denied('AUTHORITY_EXPIRY')
        if type(data['projects']) is not list or len(data['projects'])>10000: raise ValueError('AUTHORITY_SIZE')
        checked=[]; ids=set()
        for p in data['projects']:
            if set(p)!={'id','tenant','customer','owner_email','contract_ref','order_ref','verified_entity','title','requirements','reviewer_emails'} or p['verified_entity'] is not True: raise Denied('VERIFIED_CONTRACT_REQUIRED')
            for k in ('id','tenant','customer','contract_ref','order_ref'): identifier(p[k])
            if p['id'] in ids: raise Conflict('DUPLICATE_PROJECT')
            ids.add(p['id']); safe_text(p['title'],150)
            owner=self.db.execute('SELECT id FROM accounts WHERE email_idx=? AND verified=1',(self.idx(email(p['owner_email'])),)).fetchone()
            if not owner: raise Denied('VERIFIED_OWNER_ACCOUNT_REQUIRED')
            requirements=p['requirements']
            if type(requirements) is not list or len(requirements)>100: raise ValueError('REQUIREMENTS_SIZE')
            names=set()
            fields={'id','title','purpose','required','identity_requirements','official_url','instructions','minimum_permissions','fees','verified_at','formats','valid_until','submission_type','category'}
            for q in requirements:
                if set(q)!=fields or q['submission_type'] not in ('PRIVATE_DOCUMENT','SECRETREF','OAUTH','SERVER_CHALLENGE') or q['category'] not in ('MATERIAL','CONTRACT_DRAFT','CONTRACT_REVIEW','CONTRACT_EFFECTIVE','SIGNATURE_EVIDENCE','INTERNAL'): raise ValueError('REQUIREMENT_SCHEMA')
                identifier(q['id'])
                if q['id'] in names: raise Conflict('DUPLICATE_REQUIREMENT')
                names.add(q['id'])
                if type(q['required']) is not bool or not q['instructions'] or not q['purpose'] or q['fees'] is None: raise ValueError('REQUIREMENT_INCOMPLETE')
                if q['official_url'] and not q['official_url'].startswith('https://'): raise ValueError('OFFICIAL_HTTPS_REQUIRED')
            reviewers=[]
            for addr in p['reviewer_emails']:
                r=self.db.execute('SELECT id FROM accounts WHERE email_idx=? AND verified=1',(self.idx(email(addr)),)).fetchone()
                if not r or r[0]==owner[0]: raise Denied('SEPARATE_REVIEWER_REQUIRED')
                reviewers.append(r[0])
            checked.append((p,owner[0],reviewers))
        with self.tx():
            previous=int(self.db.execute("SELECT v FROM settings WHERE k='authority_revision'").fetchone()[0])
            if data['revision']<=previous: raise Conflict('AUTHORITY_REPLAY')
            self.db.execute('UPDATE projects SET active=0')
            self.db.execute("UPDATE members SET active=0 WHERE role IN ('OWNER','REVIEWER')")
            for p,owner,reviewers in checked:
                old=self.db.execute('SELECT tenant,customer,owner FROM projects WHERE id=?',(p['id'],)).fetchone()
                if old and tuple(old)!=(p['tenant'],p['customer'],owner): raise Denied('CONTRACT_SUBJECT_CHANGE_REQUIRES_NEW_PROJECT')
                self.db.execute('INSERT INTO project_history VALUES(?,?,?)',(p['id'],data['revision'],self.encrypt(canonical(p),'project:'+p['id'])))
                self.db.execute('INSERT OR REPLACE INTO projects VALUES(?,?,?,?,?,?,?,?,1)',(p['id'],p['tenant'],p['customer'],owner,p['contract_ref'],data['revision'],data['expires'],self.encrypt(canonical(p),'project:'+p['id'])))
                for uid,role in [(owner,'OWNER')]+[(x,'REVIEWER') for x in reviewers]: self.db.execute('INSERT OR REPLACE INTO members VALUES(?,?,?,1)',(p['id'],uid,role))
                for q in p['requirements']: self.db.execute("INSERT OR IGNORE INTO items VALUES(?,?,0,'NOT_STARTED',NULL)",(p['id'],q['id']))
                self.audit(p['id'],'authority','AUTHORITY_SYNC',str(data['revision']))
            self.db.execute("UPDATE settings SET v=? WHERE k='authority_revision'",(str(data['revision']),))
        return {'imported':len(checked),'revision':data['revision']}
    def project(self,uid,pid,roles=None):
        p=self.db.execute('SELECT * FROM projects WHERE id=? AND active=1',(identifier(pid),)).fetchone()
        m=self.db.execute('SELECT role FROM members WHERE project=? AND user_id=? AND active=1',(pid,uid)).fetchone()
        if not p or p['expires']<=self.now() or not m or (roles and m[0] not in roles): raise Denied('PROJECT_PERMISSION_REQUIRED')
        return p,m[0],json.loads(self.decrypt(p['payload'],'project:'+pid))
    def requirement(self,uid,pid,item,roles=None):
        p,role,data=self.project(uid,pid,roles)
        q=next((x for x in data['requirements'] if x['id']==item),None)
        if not q:
            for old in self.db.execute('SELECT payload FROM project_history WHERE project=? ORDER BY revision DESC',(pid,)):
                previous=json.loads(self.decrypt(old[0],'project:'+pid)); q=next((x for x in previous['requirements'] if x['id']==item),None)
                if q: break
        if not q or (q['category']=='INTERNAL' and role!='REVIEWER'): raise Denied('MATERIAL_PERMISSION_REQUIRED')
        return q,role
    def projects(self,uid):
        result=[]
        for r in self.db.execute('SELECT project FROM members WHERE user_id=? AND active=1',(uid,)):
            try:
                p,role,d=self.project(uid,r[0]); result.append({'id':p['id'],'title':d['title'],'role':role,'tenant':p['tenant'],'customer':p['customer']})
            except Denied: pass
        return result
    def checklist(self,uid,pid):
        p,role,d=self.project(uid,pid); result=[]
        for q in d['requirements']:
            if q['category']=='INTERNAL' and role!='REVIEWER': continue
            r=self.db.execute('SELECT * FROM items WHERE project=? AND item=?',(pid,q['id'])).fetchone()
            versions=[{'id':x['id'],'seq':x['seq'],'actor':x['actor'],'kind':x['kind'],'created':x['created'],'expires':x['expires'],'details':json.loads(self.decrypt(x['payload'],x['id']))} for x in self.db.execute('SELECT * FROM versions WHERE project=? AND item=? ORDER BY seq',(pid,q['id']))]
            versions=[v for v in versions if v['details'].get('category')!='INTERNAL' or role=='REVIEWER']
            latest=versions[-1] if versions else None
            recheck=bool(latest and latest['expires'] and latest['expires']<=self.now())
            result.append({**q,'state':r['state'],'revision':r['seq'],'accepted_revision':r['accepted'],'needs_reverification':recheck,'versions':versions})
        states=[x['state'] for x in result if x['required']]
        overall='ACCEPTED' if states and all(s=='ACCEPTED' for s in states) and not any(x['needs_reverification'] for x in result if x['required']) else 'PARTIAL' if any(s!='NOT_STARTED' for s in states) else 'NOT_STARTED'
        return {'project':pid,'items':result,'overall':overall,'requirements_revision':p['revision']}
    def invite(self,uid,pid,target_email,role):
        with self.tx():
            self.project(uid,pid,('OWNER',))
            if role not in ('EDITOR','VIEWER'): raise Denied('INVITABLE_ROLE')
            address=email(target_email)
            target=self.db.execute('SELECT id FROM accounts WHERE email_idx=? AND verified=1',(self.idx(address),)).fetchone()
            if not target: raise Denied('VERIFIED_TARGET_REQUIRED')
            if target[0]==uid: raise Denied('CANNOT_CHANGE_OWNER')
            old=self.db.execute('SELECT role FROM members WHERE project=? AND user_id=?',(pid,target[0])).fetchone()
            if old and old[0] in ('OWNER','REVIEWER'): raise Denied('PROTECTED_ROLE')
            token=self.challenge('invite',target[0],{'project':pid,'role':role,'inviter':uid},600)
            self.audit(pid,uid,'INVITE',target[0])
        return {'invitation':token,'expires_in':600,'target_user':target[0]}
    def accept_invite(self,uid,token):
        with self.tx():
            _,p=self.consume(token,'invite',uid); self.project(p['inviter'],p['project'],('OWNER',))
            old=self.db.execute('SELECT role FROM members WHERE project=? AND user_id=?',(p['project'],uid)).fetchone()
            if old and old[0] in ('OWNER','REVIEWER'): raise Denied('PROTECTED_ROLE')
            self.db.execute('INSERT OR REPLACE INTO members VALUES(?,?,?,1)',(p['project'],uid,p['role'])); self.audit(p['project'],uid,'INVITE_ACCEPT',uid)
        return {'joined':True}
    def revoke(self,uid,pid,target):
        with self.tx():
            self.project(uid,pid,('OWNER',)); r=self.db.execute('SELECT role FROM members WHERE project=? AND user_id=?',(pid,target)).fetchone()
            if not r or r[0] in ('OWNER','REVIEWER'): raise Denied('PROTECTED_ROLE')
            self.db.execute('UPDATE members SET active=0 WHERE project=? AND user_id=?',(pid,target)); self.db.execute('UPDATE links SET active=0 WHERE project=? AND user_id=?',(pid,target))
            self.db.execute("UPDATE challenges SET used=1 WHERE kind IN ('invite','bind','confirm_link') AND user_id=?",(target,)); self.audit(pid,uid,'REVOKE',target)
        return {'revoked':True}
    def save(self,uid,pid,item,revision,kind,content,expires=None):
        # No client-selected paths, file names, storage keys, scan results or actors.
        if type(revision) is not int or revision<0 or kind not in ('DOCUMENT','SECRETREF','SERVER_CHALLENGE','OAUTH'): raise ValueError('INVALID_SAVE')
        if expires is not None and (type(expires) is not int or expires<=self.now()): raise ValueError('INVALID_EXPIRY')
        with self.tx():
            self.limit('save:'+uid,30,3600)
            q,role=self.requirement(uid,pid,item,('OWNER','EDITOR','REVIEWER'))
            if role=='REVIEWER' and q['category']!='INTERNAL': raise Denied('REVIEWER_CANNOT_SUBMIT')
            if q['category']=='INTERNAL' and role!='REVIEWER': raise Denied('INTERNAL_ONLY')
            r=self.db.execute('SELECT * FROM items WHERE project=? AND item=?',(pid,item)).fetchone()
            if r['seq']!=revision or r['state'] in ('SUBMITTED','IN_REVIEW'): raise Conflict('VERSION_CONFLICT')
            version='v_'+secrets.token_hex(16); payload={}; oid=None
            if kind=='DOCUMENT':
                if q['submission_type']!='PRIVATE_DOCUMENT' or type(content) is not bytes or not 1<=len(content)<=5_000_000: raise Denied('DOCUMENT_ONLY_OR_LIMIT')
                if content.startswith(b'%PDF-'): mime='application/pdf'
                elif content.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
                elif content.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
                else: raise Denied('PDF_PNG_JPEG_ONLY')
                if mime not in q['formats']: raise Denied('FORMAT_NOT_REQUIRED')
                safe_text(content.decode('latin1'),5_000_000)
                # Scanner gets bytes in its isolated adapter. Unknown/failure never released.
                if self.scanner is None: raise Unavailable('SCANNER_PENDING')
                clean=self.scanner(content)
                if clean is not True: raise Denied('QUARANTINED_SCAN_NOT_CLEAN')
                import shutil
                usage=self.db.execute('SELECT count(*),coalesce(sum(size),0) FROM objects WHERE project=?',(pid,)).fetchone()
                if usage[0]>=1000 or usage[1]+len(content)>250_000_000 or shutil.disk_usage(self.root).free<max(50_000_000,3*len(content)):raise Unavailable('STORAGE_QUOTA_OR_CAPACITY')
                oid='o_'+secrets.token_hex(16)
                encrypted=self.encrypt(content,'object:'+pid+':'+oid)
                secure_write(self.objects/oid,encrypted)
                payload={'object_id':oid,'category':q['category']}
                self.db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?,?,?)',(oid,version,pid,mime,len(content),digest(content),'CLEAN',self.key_id))
            else:
                if q['submission_type']!=kind or self.secretref is None: raise Unavailable('DEDICATED_PROVIDER_PENDING')
                reference=safe_text(content,256)
                # Trusted host resolver verifies grant provenance & same project; never a client verified flag.
                if self.secretref(pid,item,kind,reference) is not True: raise Denied('REFERENCE_NOT_VERIFIED')
                payload={'reference':reference,'category':q['category']}
            self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',(version,pid,item,revision+1,uid,'SAVE',self.encrypt(canonical(payload),version),expires,self.now()))
            self.db.execute("UPDATE items SET seq=?,state='PARTIAL' WHERE project=? AND item=?",(revision+1,pid,item)); self.audit(pid,uid,'SAVE',version)
        return {'version':version,'revision':revision+1,'state':'PARTIAL'}
    def transition(self,uid,pid,item,revision,action,reason=''):
        mapping={('PARTIAL','submit'):'SUBMITTED',('NEEDS_CORRECTION','submit'):'SUBMITTED',('SUBMITTED','begin_review'):'IN_REVIEW',('IN_REVIEW','request_changes'):'NEEDS_CORRECTION',('IN_REVIEW','approve'):'ACCEPTED'}
        with self.tx():
            q,role=self.requirement(uid,pid,item)
            r=self.db.execute('SELECT * FROM items WHERE project=? AND item=?',(pid,item)).fetchone()
            state=mapping.get((r['state'],action))
            if type(revision) is not int or revision!=r['seq'] or not state: raise Conflict('VERSION_OR_TRANSITION')
            v=self.db.execute("SELECT * FROM versions WHERE project=? AND item=? AND kind='SAVE' ORDER BY seq DESC LIMIT 1",(pid,item)).fetchone()
            if not v or (v['expires'] and v['expires']<=self.now()): raise Denied('MATERIAL_EXPIRED')
            if json.loads(self.decrypt(v['payload'],v['id'])).get('category')!=q['category']:raise Denied('MATERIAL_CATEGORY_CHANGED_NEW_VERSION_REQUIRED')
            if action=='submit':
                if role not in ('OWNER','EDITOR') and not (role=='REVIEWER' and q['category']=='INTERNAL'): raise Denied('SUBMIT_ROLE')
            elif role!='REVIEWER' or v['actor']==uid: raise Denied('INDEPENDENT_REVIEW_REQUIRED')
            if action in ('request_changes','approve'): safe_text(reason,1000)
            version='v_'+secrets.token_hex(16); seq=revision+1
            self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',(version,pid,item,seq,uid,action,self.encrypt(canonical({'reason':reason,'source_version':v['id'],'category':q['category']}),version),v['expires'],self.now()))
            accepted=seq if state=='ACCEPTED' else r['accepted']
            self.db.execute('UPDATE items SET seq=?,state=?,accepted=? WHERE project=? AND item=?',(seq,state,accepted,pid,item)); self.audit(pid,uid,action.upper(),version)
        return {'state':state,'revision':seq,'accepted_revision':accepted}
    def download(self,uid,pid,oid):
        with self.tx():
            o=self.db.execute('SELECT o.*,v.item,v.payload version_payload FROM objects o JOIN versions v ON v.id=o.version WHERE o.id=? AND o.project=?',(identifier(oid),pid)).fetchone()
            if not o: raise Denied('OBJECT_PERMISSION_REQUIRED')
            q,role=self.requirement(uid,pid,o['item'])
            if json.loads(self.decrypt(o['version_payload'],o['version'])).get('category')=='INTERNAL' and role!='REVIEWER':raise Denied('HISTORICAL_INTERNAL_ONLY')
            if o['scan']!='CLEAN': raise Denied('QUARANTINED')
            raw=self.decrypt(private_path(self.objects/oid).read_bytes(),'object:'+pid+':'+oid)
            if len(raw)!=o['size'] or digest(raw)!=o['sha']: raise Denied('OBJECT_INTEGRITY')
            self.audit(pid,uid,'DOWNLOAD',oid)
        return raw,o['mime']
    def message(self,uid,pid,text,channel='WEB',event=None):
        self.project(uid,pid); self.limit('message:'+uid,20,60); safe_text(text,4000)
        mid='m_'+secrets.token_hex(16)
        self.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',(mid,pid,uid,channel,self.encrypt(text.encode(),mid),'ARCHIVED',self.now())); self.audit(pid,uid,'MESSAGE_ARCHIVED',mid)
        return {'id':mid,'status':'ARCHIVED','ai_response':'PENDING_PROVIDER'}
    def messages(self,uid,pid):
        self.project(uid,pid)
        return [{'id':r['id'],'channel':r['channel'],'body':self.decrypt(r['payload'],r['id']).decode(),'status':r['status'],'created':r['created']} for r in self.db.execute('SELECT * FROM messages WHERE project=? ORDER BY created,id LIMIT 200',(pid,))]
    def binding_challenge(self,uid,pid,channel,subject):
        if channel not in ('TELEGRAM','FEISHU') or type(subject) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',subject): raise ValueError('INVALID_CHANNEL_SUBJECT')
        with self.tx():
            self.project(uid,pid); self.limit('bind:'+uid,8); token=self.challenge('bind',uid,{'project':pid,'channel':channel,'subject':subject},300); self.audit(pid,uid,'BIND_CHALLENGE',channel)
        return {'challenge':token,'expires_in':300,'state':'AWAIT_PROVIDER_AND_WEB_CONFIRMATION'}
    def channel_event(self,channel,event_id,subject,text,*,now=None):
        """Only called after actual provider adapter verification, never public JSON directly."""
        identifier(event_id); safe_text(text,4000)
        with self.tx():
            if self.db.execute('SELECT 1 FROM events WHERE channel=? AND event_id=?',(channel,event_id)).fetchone(): return {'duplicate':True,'saved':True}
            if text.startswith('/bind '):
                uid,p=self.consume(text[6:].strip(),'bind')
                if p['channel']!=channel or p['subject']!=subject: raise Denied('CHALLENGE_SCOPE')
                self.project(uid,p['project']); old=self.db.execute('SELECT user_id FROM links WHERE channel=? AND subject_idx=?',(channel,self.idx(subject))).fetchall()
                if any(x[0]!=uid for x in old): raise Denied('CHANNEL_IDENTITY_CONFLICT')
                confirm=self.challenge('confirm_link',uid,{**p,'provider_event':event_id},300)
                # Confirmation token stays server-side; UI receives pending challenge IDs.
                result={'provider_verified':True,'web_confirmation_required':True}
            elif text.startswith('/project '):
                parts=text.split(' ',2)
                if len(parts)!=3: raise ValueError('PROJECT_AND_MESSAGE_REQUIRED')
                pid=identifier(parts[1]); r=self.db.execute('SELECT user_id FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',(channel,self.idx(subject),pid)).fetchone()
                if not r: raise Denied('CHANNEL_LINK_REQUIRED')
                result=self.message(r[0],pid,parts[2],channel,event_id)
            else: raise Denied('EXPLICIT_PROJECT_CONTEXT_REQUIRED')
            self.db.execute('INSERT INTO events VALUES(?,?,?)',(channel,event_id,self.now()))
        return result
    def pending_links(self,uid,pid):
        self.project(uid,pid)
        result=[]
        for r in self.db.execute("SELECT * FROM challenges WHERE user_id=? AND kind='confirm_link' AND used=0 AND expires>?",(uid,self.now())):
            p=json.loads(self.decrypt(r['payload'],'challenge'))
            if p['project']==pid: result.append({'id':r['token'],'channel':p['channel'],'subject':p['subject'],'expires':r['expires']})
        return result
    def confirm_link(self,uid,pid,challenge_id):
        with self.tx():
            self.project(uid,pid)
            r=self.db.execute("SELECT * FROM challenges WHERE token=? AND kind='confirm_link' AND user_id=? AND used=0 AND expires>?",(challenge_id,uid,self.now())).fetchone()
            if not r: raise Denied('CONFIRMATION_REQUIRED')
            p=json.loads(self.decrypt(r['payload'],'challenge'))
            if p['project']!=pid: raise Denied('LINK_PROJECT')
            old=self.db.execute('SELECT user_id FROM links WHERE channel=? AND subject_idx=?',(p['channel'],self.idx(p['subject']))).fetchall()
            if any(x[0]!=uid for x in old): raise Denied('CHANNEL_IDENTITY_CONFLICT')
            self.db.execute('INSERT OR REPLACE INTO links VALUES(?,?,?,?,?,1)',(p['channel'],self.idx(p['subject']),uid,pid,self.encrypt(p['subject'].encode(),'link')))
            self.db.execute('UPDATE challenges SET used=1 WHERE token=?',(challenge_id,)); self.audit(pid,uid,'LINK_CONFIRMED',p['channel'])
        return {'linked':True}
    def unlink(self,uid,pid,channel):
        with self.tx():
            self.project(uid,pid)
            self.db.execute('UPDATE links SET active=0 WHERE user_id=? AND project=? AND channel=?',(uid,pid,channel))
            self.db.execute("UPDATE challenges SET used=1 WHERE user_id=? AND kind IN ('bind','confirm_link')",(uid,)); self.audit(pid,uid,'UNLINK',channel)
        return {'unlinked':True}
    def check_integrity(self):
        if self.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise Denied('DB_INTEGRITY')
        parent='0'*64
        for r in self.db.execute('SELECT * FROM audit ORDER BY seq'):
            if r['parent']!=parent or r['sha']!=digest(canonical([r['project'],r['actor'],r['event'],r['object_id'],r['at'],parent])): raise Denied('AUDIT_CHAIN')
            parent=r['sha']
        for o in self.db.execute('SELECT * FROM objects'):
            raw=self.decrypt(private_path(self.objects/o['id']).read_bytes(),'object:'+o['project']+':'+o['id'])
            if len(raw)!=o['size'] or digest(raw)!=o['sha']: raise Denied('OBJECT_INTEGRITY')
        return {'integrity':'PASS','audit_head':parent,'objects':self.db.execute('SELECT count(*) FROM objects').fetchone()[0]}
