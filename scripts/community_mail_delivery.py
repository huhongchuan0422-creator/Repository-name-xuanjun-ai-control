"""Persistent multi-provider routing on the existing Center SQLite database."""
import calendar, hashlib, json, math, secrets, time, types
from urllib.parse import urlparse
PROVIDERS=('Resend','SMTP2GO','Brevo')
OUTCOMES=('NOT_SUBMITTED','DEFINITE_REJECTED','ACCEPTED','UNKNOWN')
UNCONFIGURED_RESEND_TEST_BASELINE={'daily':100,'monthly':3000}
DDL='''
CREATE TABLE IF NOT EXISTS mail_idempotency(message_key TEXT PRIMARY KEY,payload_sha256 TEXT NOT NULL,state TEXT NOT NULL,provider TEXT,attempt_id TEXT,created INTEGER NOT NULL,updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mail_provider_attempts(id TEXT PRIMARY KEY,message_key TEXT NOT NULL,provider TEXT NOT NULL,account_id TEXT NOT NULL,outcome TEXT NOT NULL,provider_ref TEXT,detail TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mail_quota_windows(provider TEXT NOT NULL,account_id TEXT NOT NULL,window_name TEXT NOT NULL,window_start INTEGER NOT NULL,window_end INTEGER NOT NULL,limit_value INTEGER NOT NULL,reserved INTEGER NOT NULL,PRIMARY KEY(provider,account_id,window_name,window_start));
CREATE TABLE IF NOT EXISTS mail_reservations(attempt_id TEXT NOT NULL,provider TEXT NOT NULL,account_id TEXT NOT NULL,window_name TEXT NOT NULL,window_start INTEGER NOT NULL,state TEXT NOT NULL,PRIMARY KEY(attempt_id,window_name,window_start));
CREATE TABLE IF NOT EXISTS mail_reconciliation(attempt_id TEXT PRIMARY KEY,provider TEXT NOT NULL,next_check INTEGER NOT NULL,checks INTEGER NOT NULL DEFAULT 0,last_error TEXT);
'''
class ProviderBinding:
    def __init__(self,provider,account_id,transport,endpoint,limits,authenticated=False):
        self.provider=provider;self.account_id=account_id;self.transport=transport;self.endpoint=endpoint;self.limits=dict(limits) if type(limits) is dict else limits;self.authenticated=authenticated
        if self.provider not in PROVIDERS or not self.account_id or not self.authenticated:raise ValueError('AUTHENTICATED_PROVIDER_BINDING_REQUIRED')
        if self.transport=='HTTP':
            try:parsed=urlparse(self.endpoint);valid=parsed.scheme=='https' and bool(parsed.hostname) and parsed.port in (None,443)
            except (TypeError,ValueError):valid=False
            if not valid:raise ValueError('HTTPS_443_PROVIDER_REQUIRED')
        elif self.transport=='SMTP':
            try:host,raw_port=self.endpoint.rsplit(':',1);port=int(raw_port)
            except (AttributeError,ValueError,IndexError):raise ValueError('SMTP_465_OR_587_REQUIRED') from None
            if not host or port not in (465,587):raise ValueError('SMTP_465_OR_587_REQUIRED')
        else:raise ValueError('HTTP_OR_SMTP_TRANSPORT_REQUIRED')
        if type(self.limits) is not dict or not self.limits:raise ValueError('PROVIDER_LIMIT_READBACK_REQUIRED')
        for name,value in self.limits.items():
            if name not in ('daily','monthly') and not (type(name) is str and name.startswith('rolling:')):raise ValueError('QUOTA_WINDOW_REQUIRED')
            if name.startswith('rolling:'):
                try:seconds=int(name.split(':',1)[1])
                except ValueError:raise ValueError('QUOTA_WINDOW_REQUIRED') from None
                if seconds<=0:raise ValueError('QUOTA_WINDOW_REQUIRED')
            if type(value) is not int or value<=0:raise ValueError('POSITIVE_PROVIDER_LIMIT_REQUIRED')
class MailDelivery:
    def __init__(self,db,bindings=(),transports=None,*,clock=time.time):
        self.db=db;self.clock=clock;self.bindings=tuple(sorted(bindings,key=lambda b:PROVIDERS.index(b.provider)));self.transports=transports or {};db.executescript(DDL);seen=set()
        for b in self.bindings:
            if not isinstance(b,ProviderBinding) or (b.provider,b.account_id) in seen:raise ValueError('UNIQUE_PROVIDER_BINDING_REQUIRED')
            seen.add((b.provider,b.account_id))
            if b.provider not in self.transports:raise ValueError('PROVIDER_TRANSPORT_REQUIRED')
            attest=getattr(self.transports[b.provider],'authenticated',None)
            if not callable(attest) or attest(b) is not True:raise ValueError('AUTHENTICATED_PROVIDER_TRANSPORT_REQUIRED')
    @property
    def ready(self):return bool(self.bindings)
    @property
    def provider_state(self):
        configured={b.provider for b in self.bindings};return {p:('READY' if p in configured else 'NOT_CONFIGURED') for p in PROVIDERS}
    def _windows(self,b,now):
        tm=time.gmtime(now);day=calendar.timegm((tm.tm_year,tm.tm_mon,tm.tm_mday,0,0,0));month=calendar.timegm((tm.tm_year,tm.tm_mon,1,0,0,0));ny,nm=((tm.tm_year+1,1) if tm.tm_mon==12 else (tm.tm_year,tm.tm_mon+1));out=[]
        for name,limit in b.limits.items():
            if name=='daily':start,end=day,day+86400
            elif name=='monthly':start,end=month,calendar.timegm((ny,nm,1,0,0,0))
            else:seconds=int(name.split(':',1)[1]);start=now-now%seconds;end=start+seconds
            out.append((name,start,end,limit))
        return out
    def _result(self,key):
        r=self.db.execute('SELECT * FROM mail_idempotency WHERE message_key=?',(key,)).fetchone();return dict(r) if r else None
    def _reserve(self,key,sha,b,now):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            sequence=self.db.execute('SELECT count(*) FROM mail_provider_attempts WHERE message_key=? AND provider=? AND account_id=?',(key,b.provider,b.account_id)).fetchone()[0]+1
            aid=hashlib.sha256((key+'|'+b.provider+'|'+b.account_id+'|'+str(sequence)).encode()).hexdigest()
            old=self.db.execute('SELECT * FROM mail_idempotency WHERE message_key=?',(key,)).fetchone()
            if old:
                if old['payload_sha256']!=sha:raise ValueError('IDEMPOTENCY_PAYLOAD_MISMATCH')
                self.db.commit();return None,dict(old)
            windows=[]
            for name,start,end,limit in self._windows(b,now):
                self.db.execute('INSERT OR IGNORE INTO mail_quota_windows VALUES(?,?,?,?,?,?,0)',(b.provider,b.account_id,name,start,end,limit));row=self.db.execute('SELECT * FROM mail_quota_windows WHERE provider=? AND account_id=? AND window_name=? AND window_start=?',(b.provider,b.account_id,name,start)).fetchone()
                if row['limit_value']!=limit:self.db.execute('UPDATE mail_quota_windows SET limit_value=? WHERE provider=? AND account_id=? AND window_name=? AND window_start=?',(limit,b.provider,b.account_id,name,start))
                if row['reserved']+1>math.floor(limit*.9):self.db.rollback();return False,None
                windows.append((name,start))
            self.db.execute('INSERT INTO mail_idempotency VALUES(?,?,?,?,?,?,?)',(key,sha,'UNKNOWN',b.provider,aid,now,now));self.db.execute('INSERT INTO mail_provider_attempts VALUES(?,?,?,?,?,?,?,?,?)',(aid,key,b.provider,b.account_id,'UNKNOWN',None,'RESERVED_BEFORE_TRANSPORT',now,now))
            for name,start in windows:
                self.db.execute('UPDATE mail_quota_windows SET reserved=reserved+1 WHERE provider=? AND account_id=? AND window_name=? AND window_start=?',(b.provider,b.account_id,name,start));self.db.execute('INSERT INTO mail_reservations VALUES(?,?,?,?,?,?)',(aid,b.provider,b.account_id,name,start,'HELD'))
            self.db.execute('INSERT INTO mail_reconciliation VALUES(?,?,?,0,NULL)',(aid,b.provider,now));self.db.commit();return aid,None
        except BaseException:self.db.rollback();raise
    def _finish(self,aid,outcome,detail,ref=None,forget=False):
        if outcome not in OUTCOMES:raise ValueError('INVALID_PROVIDER_OUTCOME')
        now=int(self.clock());self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT * FROM mail_provider_attempts WHERE id=?',(aid,)).fetchone()
            if not row or row['outcome'] not in ('UNKNOWN',outcome):raise ValueError('ATTEMPT_ALREADY_FINAL')
            self.db.execute('UPDATE mail_provider_attempts SET outcome=?,provider_ref=?,detail=?,updated=? WHERE id=?',(outcome,ref,detail,now,aid));self.db.execute('UPDATE mail_idempotency SET state=?,updated=? WHERE attempt_id=?',(outcome,now,aid))
            if outcome=='NOT_SUBMITTED':
                for r in self.db.execute("SELECT * FROM mail_reservations WHERE attempt_id=? AND state='HELD'",(aid,)).fetchall():self.db.execute('UPDATE mail_quota_windows SET reserved=reserved-1 WHERE provider=? AND account_id=? AND window_name=? AND window_start=?',(r['provider'],r['account_id'],r['window_name'],r['window_start']))
                self.db.execute("UPDATE mail_reservations SET state='RELEASED' WHERE attempt_id=? AND state='HELD'",(aid,))
            elif outcome!='UNKNOWN':self.db.execute("UPDATE mail_reservations SET state='COUNTED' WHERE attempt_id=? AND state='HELD'",(aid,))
            if outcome!='UNKNOWN':self.db.execute('DELETE FROM mail_reconciliation WHERE attempt_id=?',(aid,))
            if forget:self.db.execute('DELETE FROM mail_idempotency WHERE attempt_id=?',(aid,))
            self.db.commit()
        except BaseException:self.db.rollback();raise
    def send(self,key,message):
        if type(key) is not str or not key or type(message) is not dict:raise ValueError('MAIL_MESSAGE_REQUIRED')
        sha=hashlib.sha256(json.dumps(message,sort_keys=True,separators=(',',':')).encode()).hexdigest();old=self._result(key)
        if old:
            if old['payload_sha256']!=sha:raise ValueError('IDEMPOTENCY_PAYLOAD_MISMATCH')
            return old
        if not self.ready:return {'message_key':key,'state':'UNAVAILABLE','reason':'VERIFICATION_CHANNEL_PENDING'}
        for b in self.bindings:
            aid,prior=self._reserve(key,sha,b,int(self.clock()))
            if prior:return prior
            if aid is False:continue
            try:result=self.transports[b.provider].submit(b,message,aid)
            except TimeoutError:return self._result(key)
            outcome=result.get('outcome') if type(result) is dict else None
            if outcome=='429':self._finish(aid,'NOT_SUBMITTED','HTTP_429',forget=True);continue
            if outcome not in OUTCOMES:raise ValueError('EXACT_PROVIDER_RESULT_REQUIRED')
            self._finish(aid,outcome,result.get('detail',outcome),result.get('provider_ref'));return self._result(key)
        return {'message_key':key,'state':'UNAVAILABLE','reason':'QUOTA_OR_PROVIDER_UNAVAILABLE'}
    def record_receipt(self,provider,provider_ref):
        row=self.db.execute("SELECT * FROM mail_provider_attempts WHERE provider=? AND provider_ref=? AND outcome='ACCEPTED'",(provider,provider_ref)).fetchone()
        if not row:return None
        now=int(self.clock());self.db.execute("UPDATE mail_provider_attempts SET detail='DELIVERED_RECEIPT',updated=? WHERE id=?",(now,row['id']));self.db.execute("UPDATE mail_idempotency SET state='DELIVERED',updated=? WHERE attempt_id=?",(now,row['id']));return self._result(row['message_key'])
    def reconcile_unknown(self,aid):
        row=self.db.execute("SELECT * FROM mail_provider_attempts WHERE id=? AND outcome='UNKNOWN'",(aid,)).fetchone()
        if not row:return None
        b=next((x for x in self.bindings if (x.provider,x.account_id)==(row['provider'],row['account_id'])),None)
        if not b:return {'attempt_id':aid,'state':'UNKNOWN'}
        result=self.transports[row['provider']].reconcile(b,row['provider_ref'],aid);state=result.get('outcome') if type(result) is dict else None
        if state=='DELIVERED':
            now=int(self.clock());self.db.execute('BEGIN IMMEDIATE')
            try:self.db.execute("UPDATE mail_provider_attempts SET detail='DELIVERED_RECEIPT',updated=? WHERE id=?",(now,aid));self.db.execute("UPDATE mail_idempotency SET state='DELIVERED',updated=? WHERE attempt_id=?",(now,aid));self.db.execute("UPDATE mail_reservations SET state='COUNTED' WHERE attempt_id=? AND state='HELD'",(aid,));self.db.execute('DELETE FROM mail_reconciliation WHERE attempt_id=?',(aid,));self.db.commit()
            except BaseException:self.db.rollback();raise
        elif state in OUTCOMES:self._finish(aid,state,result.get('detail',state),result.get('provider_ref'))
        else:self.db.execute('UPDATE mail_reconciliation SET checks=checks+1,next_check=?,last_error=? WHERE attempt_id=?',(int(self.clock())+60,'STILL_UNKNOWN',aid))
        return self._result(row['message_key'])
def default_unconfigured_delivery(db,*,clock=time.time):return MailDelivery(db,(),{},clock=clock)


def install(center,bindings=(),transports=None):
    """Attach mail migration/routing to one existing Center without a new identity store."""
    delivery=MailDelivery(center.db,bindings,transports,clock=center.clock);center.mail_delivery=delivery;center.mail_ready=delivery.ready
    def mail_challenge(self,kind,outbox_kind,user,address):
        for row in self.db.execute("SELECT * FROM outbox WHERE user_id=? AND kind=? AND status!='CANCELLED' ORDER BY at DESC,rowid DESC",(user,outbox_kind)).fetchall():
            payload=json.loads(self.decrypt(row['payload'],'outbox:'+row['id']));token=payload.get('token')
            challenge=self.db.execute('SELECT expires,used FROM challenges WHERE token=? AND kind=? AND user_id=?',(hashlib.sha256(token.encode()).hexdigest(),kind,user)).fetchone() if type(token) is str else None
            if challenge and not challenge['used'] and challenge['expires']>self.now():
                if row['status'] in ('PENDING','UNKNOWN'):return row['id'],token
                oid=secrets.token_hex(16);self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,outbox_kind,user,self.encrypt(self._mail_canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()));return oid,token
        self.db.execute("UPDATE outbox SET status='CANCELLED' WHERE user_id=? AND kind=? AND status='PENDING'",(user,outbox_kind));token=self.challenge(kind,user,{})
        oid=secrets.token_hex(16);self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,outbox_kind,user,self.encrypt(self._mail_canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()));return oid,token
    def deliver_outbox(self,oid):
        row=self.db.execute('SELECT * FROM outbox WHERE id=?',(oid,)).fetchone();payload=json.loads(self.decrypt(row['payload'],'outbox:'+oid));result=self.mail_delivery.send('outbox:'+oid,{'kind':row['kind'],'email':payload['email'],'code':payload['token']})
        if result.get('state') in ('ACCEPTED','DELIVERED','DEFINITE_REJECTED','UNKNOWN'):self.db.execute('UPDATE outbox SET status=? WHERE id=?',(result['state'],oid))
        return result
    def register(self,address,password):
        from scripts.pr122_customer_core import email
        if not self.mail_ready:raise self._mail_unavailable('VERIFICATION_CHANNEL_PENDING')
        address=email(address);salt=secrets.token_bytes(16);pw=self.password(password,salt);oid=None
        with self.tx():
            self.limit('register:'+address,3);old=self.db.execute('SELECT id,verified FROM accounts WHERE email_idx=?',(self.idx(address),)).fetchone()
            if old:
                if not old['verified']:oid,_=self.mail_challenge('verify','VERIFY',old['id'],address)
            else:
                uid='u_'+secrets.token_hex(12);self.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password) VALUES(?,?,?,?,?)',(uid,self.idx(address),self.encrypt(address.encode(),uid),salt,pw));oid,_=self.mail_challenge('verify','VERIFY',uid,address);self.audit('',uid,'REGISTER',uid)
        if oid:self.deliver_outbox(oid)
        return {'status':'CHECK_VERIFICATION_CHANNEL'}
    def request_reset(self,address):
        from scripts.pr122_customer_core import email
        if not self.mail_ready:raise self._mail_unavailable('VERIFICATION_CHANNEL_PENDING')
        address=email(address);oid=None
        with self.tx():
            self.limit('reset:'+address,3);row=self.db.execute('SELECT id FROM accounts WHERE email_idx=?',(self.idx(address),)).fetchone()
            if row:oid,_=self.mail_challenge('reset','RESET',row[0],address)
        if oid:self.deliver_outbox(oid)
        return {'status':'CHECK_VERIFICATION_CHANNEL'}
    from scripts.pr122_customer_core import Unavailable,canonical
    center._mail_unavailable=Unavailable;center._mail_canonical=canonical
    center.mail_challenge=types.MethodType(mail_challenge,center);center.deliver_outbox=types.MethodType(deliver_outbox,center);center.register=types.MethodType(register,center);center.request_reset=types.MethodType(request_reset,center)
    return delivery
