"""Durable mail providers, shared quota, and original-Center integration."""
import calendar
import hashlib
import ipaddress
import json
import math
import secrets
import socket
import smtplib
import ssl
import time
import types
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

PROVIDERS=('Resend','SMTP2GO','Brevo')
ATTEMPT_STATES=('INFLIGHT','NOT_SUBMITTED','DEFINITE_REJECTED','ACCEPTED','UNKNOWN','DELIVERED')
TERMINAL_STATES=('DEFINITE_REJECTED','ACCEPTED','DELIVERED')
RESEND_CEILINGS={'daily':90,'monthly':2700}
DETAIL_CODES={'SUBMIT_STARTED','ACCEPTED_BY_PROVIDER','RATE_LIMITED','AUTH_FAILED','PROVIDER_REJECTED','TRANSPORT_TIMEOUT','TRANSPORT_UNCERTAIN','RECONCILIATION_PENDING','RECONCILED_NOT_SUBMITTED','DELIVERED_RECEIPT'}
HTTP_ENDPOINTS={'Resend':'https://api.resend.com','SMTP2GO':'https://api.smtp2go.com','Brevo':'https://api.brevo.com'}
SMTP_ENDPOINTS={'SMTP2GO':('smtp.smtp2go.com:465','smtp.smtp2go.com:587'),'Brevo':('smtp-relay.brevo.com:465','smtp-relay.brevo.com:587')}
DDL='''
CREATE TABLE IF NOT EXISTS mail_idempotency(message_key TEXT PRIMARY KEY,payload_sha256 TEXT NOT NULL,state TEXT NOT NULL,provider TEXT,attempt_id TEXT,created INTEGER NOT NULL,updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mail_provider_attempts(id TEXT PRIMARY KEY,message_key TEXT NOT NULL,provider TEXT NOT NULL,account_id TEXT NOT NULL,submission_key TEXT NOT NULL,outcome TEXT NOT NULL,provider_ref TEXT,detail TEXT NOT NULL,detail_sha256 TEXT,quota_scope TEXT,created INTEGER NOT NULL,updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mail_reconciliation(attempt_id TEXT PRIMARY KEY,provider TEXT NOT NULL,next_check INTEGER NOT NULL,checks INTEGER NOT NULL DEFAULT 0,last_error TEXT);
CREATE TABLE IF NOT EXISTS mail_quota_scopes(quota_kind TEXT NOT NULL,scope_key TEXT NOT NULL,window_name TEXT NOT NULL,ceiling INTEGER NOT NULL,PRIMARY KEY(quota_kind,scope_key,window_name));
CREATE TABLE IF NOT EXISTS mail_quota_events(attempt_id TEXT NOT NULL,quota_kind TEXT NOT NULL,scope_key TEXT NOT NULL,window_name TEXT NOT NULL,event_at INTEGER NOT NULL,state TEXT NOT NULL,PRIMARY KEY(attempt_id,quota_kind,scope_key,window_name));
CREATE UNIQUE INDEX IF NOT EXISTS mail_provider_reference_unique ON mail_provider_attempts(provider,provider_ref) WHERE provider_ref IS NOT NULL;
'''

def _sha(value):return hashlib.sha256(value.encode()).hexdigest()
def _validate_limits(value):
    if type(value) is not dict or not value:raise ValueError('PROVIDER_LIMIT_READBACK_REQUIRED')
    result={}
    for name,limit in value.items():
        if name not in ('daily','monthly') and not (type(name) is str and name.startswith('rolling:')):raise ValueError('QUOTA_WINDOW_REQUIRED')
        if name.startswith('rolling:'):
            try:seconds=int(name.split(':',1)[1])
            except ValueError:raise ValueError('QUOTA_WINDOW_REQUIRED') from None
            if seconds<=0:raise ValueError('QUOTA_WINDOW_REQUIRED')
        if type(limit) is not int or limit<=0:raise ValueError('POSITIVE_PROVIDER_LIMIT_REQUIRED')
        result[name]=limit
    return result

def _endpoint(provider,transport,endpoint,allowlist):
    if type(allowlist) not in (tuple,list) or endpoint not in allowlist:raise ValueError('EXACT_PROVIDER_ENDPOINT_ALLOWLIST_REQUIRED')
    if transport=='HTTP':
        parsed=urlparse(endpoint)
        if parsed.scheme!='https' or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('HTTPS_443_PROVIDER_REQUIRED')
        try:ip=ipaddress.ip_address(parsed.hostname)
        except ValueError:ip=None
        if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):raise ValueError('PUBLIC_PROVIDER_ENDPOINT_REQUIRED')
        if endpoint.rstrip('/')!=HTTP_ENDPOINTS.get(provider):raise ValueError('PINNED_PROVIDER_ENDPOINT_REQUIRED')
    elif transport=='SMTP':
        if endpoint not in SMTP_ENDPOINTS.get(provider,()):raise ValueError('PINNED_SMTP_ENDPOINT_REQUIRED')
    else:raise ValueError('HTTP_OR_SMTP_TRANSPORT_REQUIRED')

def _public_addresses(host,port,resolver):
    try:rows=resolver(host,port,0,socket.SOCK_STREAM)
    except (OSError,TypeError):raise ValueError('PROVIDER_DNS_RESOLUTION_REQUIRED') from None
    addresses=set()
    for row in rows:
        try:address=row[4][0];ip=ipaddress.ip_address(address)
        except (IndexError,TypeError,ValueError):raise ValueError('PUBLIC_PROVIDER_ADDRESS_REQUIRED') from None
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_unspecified or ip.is_multicast):
            raise ValueError('PUBLIC_PROVIDER_ADDRESS_REQUIRED')
        addresses.add(str(ip))
    if not addresses:raise ValueError('PROVIDER_DNS_RESOLUTION_REQUIRED')
    return addresses

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,message,headers,newurl):return None


class ProviderBinding:
    def __init__(self,provider,account_id,transport,endpoint,limits,authenticated=False,quota_scope='center-default',pool_limits=None,from_address='noreply@example.invalid'):
        self.provider=provider;self.account_id=account_id;self.transport=transport;self.endpoint=endpoint;self.limits=_validate_limits(limits);self.authenticated=authenticated is True;self.quota_scope=quota_scope;self.pool_limits=_validate_limits(pool_limits or limits);self.from_address=from_address
        if provider not in PROVIDERS or type(account_id) is not str or not account_id or not self.authenticated:raise ValueError('AUTHENTICATED_PROVIDER_BINDING_REQUIRED')
        if provider=='Resend' and not {'daily','monthly'}<=set(self.limits):raise ValueError('RESEND_DAILY_MONTHLY_READBACK_REQUIRED')
        _endpoint(provider,transport,endpoint,[endpoint])
        if type(quota_scope) is not str or not quota_scope or type(from_address) is not str or '@' not in from_address:raise ValueError('EXPLICIT_QUOTA_SCOPE_AND_SENDER_REQUIRED')

class ProviderHTTPTransport:
    def __init__(self,provider,endpoint,secret,allowlist,opener=None,address_resolver=None):
        _endpoint(provider,'HTTP',endpoint,allowlist);self.provider=provider;self.endpoint=endpoint.rstrip('/');self._secret=secret;self._opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open;self._resolver=address_resolver or socket.getaddrinfo;self._authenticated=False
        self.idempotent_submission=provider in ('Resend','Brevo')
        if type(secret) is not str or not secret:raise ValueError('SECRETREF_RESOLUTION_REQUIRED')
    def _headers(self,submission_key=None):
        if self.provider=='Resend':headers={'Authorization':'Bearer '+self._secret,'Content-Type':'application/json'}
        elif self.provider=='SMTP2GO':headers={'X-Smtp2go-Api-Key':self._secret,'Content-Type':'application/json'}
        else:headers={'api-key':self._secret,'Content-Type':'application/json'}
        if submission_key and self.provider=='Resend':headers['Idempotency-Key']=submission_key
        if submission_key and self.provider=='Brevo':headers['idempotency-key']=submission_key
        return headers
    def _validate_url(self,url):
        parsed=urlparse(url);base=urlparse(self.endpoint)
        if (parsed.scheme,parsed.hostname,parsed.port or 443)!=(base.scheme,base.hostname,base.port or 443):raise ValueError('PROVIDER_FINAL_URL_DENIED')
        _public_addresses(parsed.hostname,parsed.port or 443,self._resolver)
    def _call(self,method,path,payload=None,submission_key=None):
        url=self.endpoint+path;self._validate_url(url)
        raw=None if payload is None else json.dumps(payload,separators=(',',':')).encode();response=self._opener(Request(url,data=raw,headers=self._headers(submission_key),method=method),timeout=20)
        status=getattr(response,'status',getattr(response,'code',200))
        if 300<=status<400:raise HTTPError(url,status,'PROVIDER_REDIRECT_DENIED',getattr(response,'headers',{}),None)
        final=response.geturl() if hasattr(response,'geturl') else url;self._validate_url(final or url)
        body=response.read();return json.loads(body.decode()) if body else {}
    def authenticate(self):
        paths={'Resend':'/domains?limit=1','SMTP2GO':'/v3/stats/email_summary','Brevo':'/v3/account'}
        self._call('GET' if self.provider!='SMTP2GO' else 'POST',paths[self.provider],{} if self.provider=='SMTP2GO' else None);self._authenticated=True;return True
    def authenticated(self,binding):return self._authenticated and binding.provider==self.provider and binding.endpoint.rstrip('/')==self.endpoint
    def submit(self,binding,message,attempt_id,submission_key):
        payload={'from':binding.from_address,'to':[message['email']],'subject':message.get('subject',message['kind']),'text':message.get('text',message['code'])}
        paths={'Resend':'/emails','SMTP2GO':'/v3/email/send','Brevo':'/v3/smtp/email'}
        if self.provider=='Brevo':payload={'sender':{'email':binding.from_address},'to':[{'email':message['email']}],'subject':payload['subject'],'textContent':payload['text']}
        try:data=self._call('POST',paths[self.provider],payload,submission_key)
        except HTTPError as error:
            if error.code==429:return {'outcome':'NOT_SUBMITTED','detail_code':'RATE_LIMITED'}
            if 300<=error.code<400:return {'outcome':'DEFINITE_REJECTED','detail_code':'PROVIDER_REJECTED'}
            if error.code in (401,403):return {'outcome':'NOT_SUBMITTED','detail_code':'AUTH_FAILED'}
            return {'outcome':'DEFINITE_REJECTED','detail_code':'PROVIDER_REJECTED'}
        except (TimeoutError,URLError,ValueError):return {'outcome':'UNKNOWN','detail_code':'TRANSPORT_UNCERTAIN'}
        ref=data.get('id') or data.get('request_id') or data.get('messageId') or data.get('message-id')
        if type(ref) is not str or not ref:return {'outcome':'UNKNOWN','detail_code':'TRANSPORT_UNCERTAIN'}
        return {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':ref}
    def reconcile(self,binding,provider_ref,attempt_id,submission_key):
        if not provider_ref:return {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'}
        try:
            if self.provider=='Resend':data=self._call('GET','/emails/'+provider_ref)
            elif self.provider=='Brevo':data=self._call('GET','/v3/smtp/statistics/events?'+urlencode({'messageId':provider_ref}))
            else:data=self._call('POST','/v3/email/status',{'email_id':provider_ref})
        except HTTPError as error:
            if error.code==404:return {'outcome':'NOT_SUBMITTED','detail_code':'RECONCILED_NOT_SUBMITTED'}
            return {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'}
        except (TimeoutError,URLError):return {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'}
        status=str(data.get('status') or data.get('last_event') or '').lower()
        if status in ('delivered','delivery'):return {'outcome':'DELIVERED','detail_code':'DELIVERED_RECEIPT','provider_ref':provider_ref}
        if status in ('not_submitted','not-found'):return {'outcome':'NOT_SUBMITTED','detail_code':'RECONCILED_NOT_SUBMITTED'}
        if status in ('accepted','queued','sent'):return {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':provider_ref}
        return {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'}

class ProviderSMTPTransport:
    def __init__(self,provider,endpoint,username,password,allowlist,smtp_factory=None,receipt_lookup=None):
        _endpoint(provider,'SMTP',endpoint,allowlist);self.provider=provider;self.endpoint=endpoint;self.username=username;self._password=password;self._factory=smtp_factory;self._receipt_lookup=receipt_lookup;self._authenticated=False
        if not username or not password:raise ValueError('SECRETREF_RESOLUTION_REQUIRED')
        self.idempotent_submission=False
    def _connect(self):
        host,raw=self.endpoint.rsplit(':',1);port=int(raw);context=ssl.create_default_context()
        if port==465:
            factory=self._factory or smtplib.SMTP_SSL;client=factory(host,port,context=context)
        else:
            factory=self._factory or smtplib.SMTP;client=factory(host,port);client.ehlo();client.starttls(context=context);client.ehlo()
        return client
    def authenticate(self):
        client=self._connect()
        try:client.login(self.username,self._password);self._authenticated=True
        finally:client.quit()
        return True
    def authenticated(self,binding):return self._authenticated and binding.provider==self.provider and binding.endpoint==self.endpoint
    def submit(self,binding,message,attempt_id,submission_key):
        mail=EmailMessage();mail['From']=binding.from_address;mail['To']=message['email'];mail['Subject']=message.get('subject',message['kind']);mail['Message-ID']='<'+attempt_id+'@mail.local>';mail.set_content(message.get('text',message['code']))
        try:
            client=self._connect()
            try:client.login(self.username,self._password);refused=client.send_message(mail)
            finally:client.quit()
        except smtplib.SMTPRecipientsRefused:return {'outcome':'DEFINITE_REJECTED','detail_code':'PROVIDER_REJECTED'}
        except smtplib.SMTPAuthenticationError:return {'outcome':'NOT_SUBMITTED','detail_code':'AUTH_FAILED'}
        except (TimeoutError,smtplib.SMTPServerDisconnected,OSError):return {'outcome':'UNKNOWN','detail_code':'TRANSPORT_UNCERTAIN'}
        if refused:return {'outcome':'DEFINITE_REJECTED','detail_code':'PROVIDER_REJECTED'}
        return {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':attempt_id}
    def reconcile(self,binding,provider_ref,attempt_id,submission_key):
        if self._receipt_lookup is None:return {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'}
        result=self._receipt_lookup(self.provider,provider_ref or attempt_id)
        if result=='DELIVERED':return {'outcome':'DELIVERED','detail_code':'DELIVERED_RECEIPT','provider_ref':provider_ref or attempt_id}
        if result=='NOT_SUBMITTED':return {'outcome':'NOT_SUBMITTED','detail_code':'RECONCILED_NOT_SUBMITTED'}
        return {'outcome':'UNKNOWN','detail_code':'RECONCILIATION_PENDING'}

def build_mail_configuration(config,secret_resolver,opener=None,smtp_factory=None,receipt_lookup=None,address_resolver=None):
    if type(config) is not dict or set(config)!=set(('version','endpoint_allowlist','bindings')) or config['version']!=1 or not callable(secret_resolver):raise ValueError('EXACT_PROTECTED_MAIL_CONFIG_REQUIRED')
    allowlist=config['endpoint_allowlist'];bindings=[];transports={}
    if type(config['bindings']) is not list:raise ValueError('EXACT_PROTECTED_MAIL_CONFIG_REQUIRED')
    for item in config['bindings']:
        fields=set(('provider','account_id','transport','endpoint','quota_scope','from_address','secret_ref'))
        if type(item) is not dict or set(item)!=fields:raise ValueError('EXACT_PROVIDER_BINDING_CONFIG_REQUIRED')
        _endpoint(item['provider'],item['transport'],item['endpoint'],allowlist)
        reference=urlparse(item['secret_ref']) if type(item['secret_ref']) is str else None
        if reference is None or reference.scheme!='secretref' or reference.query or reference.fragment:raise ValueError('SECRETREF_REFERENCE_REQUIRED')

        resolved=secret_resolver(item['secret_ref'],item['provider'],item['account_id'])
        if type(resolved) is not dict or set(resolved)-set(('secret','username','password','limits','pool_limits')):raise ValueError('EXACT_SECRETREF_READBACK_REQUIRED')
        limits=_validate_limits(resolved.get('limits'));pool=_validate_limits(resolved.get('pool_limits',limits))
        if item['transport']=='HTTP':transport=ProviderHTTPTransport(item['provider'],item['endpoint'],resolved.get('secret'),allowlist,opener,address_resolver);transport.authenticate()
        else:transport=ProviderSMTPTransport(item['provider'],item['endpoint'],resolved.get('username'),resolved.get('password'),allowlist,smtp_factory,receipt_lookup);transport.authenticate()
        binding=ProviderBinding(item['provider'],item['account_id'],item['transport'],item['endpoint'],limits,True,item['quota_scope'],pool,item['from_address'])
        bindings.append(binding);transports[(item['provider'],item['account_id'])]=transport
    return bindings,transports

def protected_secretref_resolver(reference,provider,account_id):
    """Resolve only a protected host-owned SecretRef document."""
    from pathlib import Path
    from scripts.community_mini_host_config import load_protected
    if type(reference) is not str:raise ValueError('SECRETREF_REFERENCE_REQUIRED')
    parsed=urlparse(reference)
    if parsed.scheme!='secretref' or parsed.netloc or parsed.query or parsed.fragment or not parsed.path.startswith('/') or '..' in Path(parsed.path).parts:
        raise ValueError('SECRETREF_REFERENCE_REQUIRED')
    value=load_protected(parsed.path)
    if (type(value) is not dict or set(value)!=set(('provider','account_id','readback'))
            or value['provider']!=provider or value['account_id']!=account_id
            or type(value['readback']) is not dict):
        raise ValueError('SECRETREF_BINDING_MISMATCH')
    return value['readback']

def optional_mail_configuration(config,secret_resolver=None,opener=None,smtp_factory=None,receipt_lookup=None,address_resolver=None):
    if config is None:return (),{}
    resolver=secret_resolver if callable(secret_resolver) else protected_secretref_resolver
    try:return build_mail_configuration(config,resolver,opener,smtp_factory,receipt_lookup,address_resolver)
    except (OSError,PermissionError,ValueError):
        # A missing/unresolvable binding is explicitly NOT_CONFIGURED.
        return (),{}


class MailDelivery:
    def __init__(self,db,bindings=(),transports=None,clock=time.time,after_submit=None):
        self.db=db;self.clock=clock;self.after_submit=after_submit;self.bindings=tuple(sorted(bindings,key=lambda b:PROVIDERS.index(b.provider)));self.transports=transports or {};self._migrate();seen=set();pools={}
        for binding in self.bindings:
            key=(binding.provider,binding.account_id)
            if key in seen:raise ValueError('UNIQUE_PROVIDER_BINDING_REQUIRED')
            seen.add(key);transport=self.transports.get(key) or self.transports.get(binding.provider)
            if transport is None or transport.authenticated(binding) is not True:raise ValueError('AUTHENTICATED_PROVIDER_TRANSPORT_REQUIRED')
            previous=pools.setdefault(binding.quota_scope,binding.pool_limits)
            if previous!=binding.pool_limits:raise ValueError('CONSISTENT_SHARED_POOL_LIMITS_REQUIRED')
        self._migrate_legacy_reservations();self._register_scopes()
    def _migrate(self):
        self.db.executescript(DDL)
        columns={r[1] for r in self.db.execute('PRAGMA table_info(mail_provider_attempts)')}
        for name,kind in (('detail_sha256','TEXT'),('quota_scope','TEXT'),('submission_key','TEXT')):
            if name not in columns:self.db.execute('ALTER TABLE mail_provider_attempts ADD COLUMN '+name+' '+kind)
        for row in self.db.execute('SELECT id FROM mail_provider_attempts WHERE submission_key IS NULL').fetchall():
            self.db.execute('UPDATE mail_provider_attempts SET submission_key=? WHERE id=?',(_sha('submission|'+row[0]),row[0]))
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS mail_provider_submission_unique ON mail_provider_attempts(provider,submission_key)')
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS mail_message_submission_unique ON mail_provider_attempts(message_key,provider,submission_key)')
        self.db.execute("INSERT OR REPLACE INTO settings(k,v) VALUES('mail_schema_version','3')")
    @property
    def ready(self):return bool(self.bindings)
    @property
    def provider_state(self):
        configured={b.provider for b in self.bindings};return {p:('READY' if p in configured else 'NOT_CONFIGURED') for p in PROVIDERS}
    def _migrate_legacy_reservations(self):
        exists=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mail_reservations'").fetchone()
        if not exists:return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for binding in self.bindings:
                rows=self.db.execute('SELECT r.attempt_id,r.window_name,r.state,a.created FROM mail_reservations r JOIN mail_provider_attempts a ON a.id=r.attempt_id WHERE r.provider=? AND r.account_id=?',(binding.provider,binding.account_id)).fetchall()
                for row in rows:
                    state='RELEASED' if row['state']=='RELEASED' else ('HELD' if row['state']=='HELD' else 'COUNTED')
                    self.db.execute('INSERT OR IGNORE INTO mail_quota_events VALUES(?,?,?,?,?,?)',(row['attempt_id'],'ACCOUNT',binding.provider+':'+binding.account_id,row['window_name'],row['created'],state))
                    if row['window_name'] in binding.pool_limits:self.db.execute('INSERT OR IGNORE INTO mail_quota_events VALUES(?,?,?,?,?,?)',(row['attempt_id'],'POOL',binding.quota_scope,row['window_name'],row['created'],state))
            self.db.commit()
        except BaseException:self.db.rollback();raise
    def _register_scopes(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for binding in self.bindings:
                for kind,scope,name,ceiling in self._specs(binding):
                    self.db.execute('INSERT OR IGNORE INTO mail_quota_scopes VALUES(?,?,?,?)',(kind,scope,name,ceiling))
                    row=self.db.execute('SELECT ceiling FROM mail_quota_scopes WHERE quota_kind=? AND scope_key=? AND window_name=?',(kind,scope,name)).fetchone()
                    if row[0]!=ceiling:raise ValueError('PERSISTED_QUOTA_SCOPE_MISMATCH')
            self.db.commit()
        except BaseException:self.db.rollback();raise
    def _transport(self,binding):return self.transports.get((binding.provider,binding.account_id)) or self.transports.get(binding.provider)
    def _ceiling(self,binding,name,limit,kind):
        value=math.floor(limit*.9)
        if kind=='ACCOUNT' and binding.provider=='Resend' and name in RESEND_CEILINGS:value=min(value,RESEND_CEILINGS[name])
        return value
    def _lower(self,name,now):
        tm=time.gmtime(now)
        if name=='daily':return calendar.timegm((tm.tm_year,tm.tm_mon,tm.tm_mday,0,0,0))
        if name=='monthly':return calendar.timegm((tm.tm_year,tm.tm_mon,1,0,0,0))
        return now-int(name.split(':',1)[1])+1
    def _specs(self,binding):
        result=[]
        for kind,scope,limits in (('POOL',binding.quota_scope,binding.pool_limits),('ACCOUNT',binding.provider+':'+binding.account_id,binding.limits)):
            for name,limit in limits.items():result.append((kind,scope,name,self._ceiling(binding,name,limit,kind)))
        return result
    def _result(self,key):
        row=self.db.execute('SELECT * FROM mail_idempotency WHERE message_key=?',(key,)).fetchone();return dict(row) if row else None
    def _reserve(self,key,payload_sha,binding,now):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT * FROM mail_idempotency WHERE message_key=?',(key,)).fetchone()
            if old and old['payload_sha256']!=payload_sha:raise ValueError('IDEMPOTENCY_PAYLOAD_MISMATCH')
            if old and old['state'] not in ('NOT_SUBMITTED','UNAVAILABLE'):self.db.commit();return None,dict(old)
            specs=self._specs(binding)
            for kind,scope,name,ceiling in specs:
                used=self.db.execute("SELECT count(*) FROM mail_quota_events WHERE quota_kind=? AND scope_key=? AND window_name=? AND event_at>=? AND state!='RELEASED'",(kind,scope,name,self._lower(name,now))).fetchone()[0]
                if used+1>ceiling:self.db.rollback();return False,None
            sequence=self.db.execute('SELECT count(*) FROM mail_provider_attempts WHERE message_key=?',(key,)).fetchone()[0]+1;attempt_id=_sha(key+'|'+str(sequence)+'|'+binding.provider+'|'+binding.account_id)
            submission_key=_sha('submission|'+attempt_id)
            if old:self.db.execute("UPDATE mail_idempotency SET state='INFLIGHT',provider=?,attempt_id=?,updated=? WHERE message_key=?",(binding.provider,attempt_id,now,key))
            else:self.db.execute("INSERT INTO mail_idempotency VALUES(?,?,?,?,?,?,?)",(key,payload_sha,'INFLIGHT',binding.provider,attempt_id,now,now))
            self.db.execute('INSERT INTO mail_provider_attempts(id,message_key,provider,account_id,submission_key,outcome,provider_ref,detail,detail_sha256,quota_scope,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(attempt_id,key,binding.provider,binding.account_id,submission_key,'INFLIGHT',None,'SUBMIT_STARTED',_sha('SUBMIT_STARTED'),binding.quota_scope,now,now))
            for kind,scope,name,ceiling in specs:self.db.execute('INSERT INTO mail_quota_events VALUES(?,?,?,?,?,?)',(attempt_id,kind,scope,name,now,'HELD'))
            self.db.execute('INSERT INTO mail_reconciliation VALUES(?,?,?,0,NULL)',(attempt_id,binding.provider,now));self.db.commit();return attempt_id,None
        except BaseException:self.db.rollback();raise
    def _finish(self,attempt_id,outcome,detail_code,provider_ref=None):
        if outcome not in ATTEMPT_STATES or outcome=='INFLIGHT' or detail_code not in DETAIL_CODES:raise ValueError('CONTROLLED_PROVIDER_RESULT_REQUIRED')
        now=int(self.clock());self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT * FROM mail_provider_attempts WHERE id=?',(attempt_id,)).fetchone()
            if not row or row['outcome'] not in ('INFLIGHT','UNKNOWN',outcome):raise ValueError('ATTEMPT_ALREADY_FINAL')
            self.db.execute('UPDATE mail_provider_attempts SET outcome=?,provider_ref=?,detail=?,detail_sha256=?,updated=? WHERE id=?',(outcome,provider_ref,detail_code,_sha(detail_code),now,attempt_id))
            self.db.execute('UPDATE mail_idempotency SET state=?,updated=? WHERE attempt_id=?',(outcome,now,attempt_id))
            if outcome=='NOT_SUBMITTED':self.db.execute("UPDATE mail_quota_events SET state='RELEASED' WHERE attempt_id=? AND state='HELD'",(attempt_id,))
            elif outcome in ('ACCEPTED','DEFINITE_REJECTED','DELIVERED'):self.db.execute("UPDATE mail_quota_events SET state='COUNTED' WHERE attempt_id=? AND state='HELD'",(attempt_id,))
            if outcome not in ('INFLIGHT','UNKNOWN'):self.db.execute('DELETE FROM mail_reconciliation WHERE attempt_id=?',(attempt_id,))
            self.db.commit()
        except BaseException:self.db.rollback();raise
    def _order(self,key):
        rows=self.db.execute("SELECT provider FROM mail_provider_attempts WHERE message_key=? AND outcome='NOT_SUBMITTED'",(key,)).fetchall();tried={r[0] for r in rows};untried=[b for b in self.bindings if b.provider not in tried]
        return untried or list(self.bindings)
    def _mark_unavailable(self,key,sha,now):
        row=self._result(key)
        if row:self.db.execute("UPDATE mail_idempotency SET state='UNAVAILABLE',updated=? WHERE message_key=? AND state IN ('NOT_SUBMITTED','UNAVAILABLE')",(now,key))
        else:self.db.execute("INSERT INTO mail_idempotency VALUES(?,?,?,?,?,?,?)",(key,sha,'UNAVAILABLE',None,None,now,now))
        return self._result(key)
    def _execute_attempt(self,row,binding,message):
        try:result=self._transport(binding).submit(binding,message,row['id'],row['submission_key'])
        except Exception:
            self._finish(row['id'],'UNKNOWN','TRANSPORT_UNCERTAIN');return self._result(row['message_key'])
        if self.after_submit is not None:self.after_submit(row['id'],row['submission_key'],result)
        outcome=result.get('outcome') if type(result) is dict else None;detail=result.get('detail_code') if type(result) is dict else None
        if outcome not in ATTEMPT_STATES or outcome=='INFLIGHT':raise ValueError('EXACT_PROVIDER_RESULT_REQUIRED')
        self._finish(row['id'],outcome,detail,result.get('provider_ref'))
        return self._result(row['message_key'])
    def _recover_inflight(self,old,message):
        row=self.db.execute("SELECT * FROM mail_provider_attempts WHERE id=? AND outcome='INFLIGHT'",(old['attempt_id'],)).fetchone()
        if not row:return old
        binding=next((b for b in self.bindings if b.provider==row['provider'] and b.account_id==row['account_id']),None)
        if binding is None:return old
        transport=self._transport(binding)
        if getattr(transport,'idempotent_submission',False) is not True:return old
        return self._execute_attempt(row,binding,message)

    def send(self,key,message):
        if type(key) is not str or not key or type(message) is not dict:raise ValueError('MAIL_MESSAGE_REQUIRED')
        sha=hashlib.sha256(json.dumps(message,sort_keys=True,separators=(',',':')).encode()).hexdigest();old=self._result(key)
        if old:
            if old['payload_sha256']!=sha:raise ValueError('IDEMPOTENCY_PAYLOAD_MISMATCH')
            if old['state']=='INFLIGHT':return self._recover_inflight(old,message)
            if old['state'] not in ('NOT_SUBMITTED','UNAVAILABLE'):return old
        if not self.ready:return {'message_key':key,'state':'UNAVAILABLE','reason':'VERIFICATION_CHANNEL_PENDING'}
        for binding in self._order(key):
            attempt_id,prior=self._reserve(key,sha,binding,int(self.clock()))
            if prior:return prior
            if attempt_id is False:continue
            row=self.db.execute('SELECT * FROM mail_provider_attempts WHERE id=?',(attempt_id,)).fetchone();result=self._execute_attempt(row,binding,message)
            if result['state']=='NOT_SUBMITTED':continue
            return result
        return self._mark_unavailable(key,sha,int(self.clock()))
    def reconcile(self,attempt_id):
        row=self.db.execute("SELECT * FROM mail_provider_attempts WHERE id=? AND outcome IN ('INFLIGHT','UNKNOWN')",(attempt_id,)).fetchone()
        if not row:return None
        binding=next((b for b in self.bindings if b.provider==row['provider'] and b.account_id==row['account_id']),None)
        if binding is None:return {'attempt_id':attempt_id,'state':row['outcome']}
        result=self._transport(binding).reconcile(binding,row['provider_ref'],attempt_id,row['submission_key']);outcome=result.get('outcome');detail=result.get('detail_code')
        if outcome in ATTEMPT_STATES and outcome!='INFLIGHT':self._finish(attempt_id,outcome,detail,result.get('provider_ref'))
        else:self.db.execute('UPDATE mail_reconciliation SET checks=checks+1,next_check=?,last_error=? WHERE attempt_id=?',(int(self.clock())+60,'RECONCILIATION_PENDING',attempt_id))
        return self._result(row['message_key'])
    def reconcile_unknown(self,attempt_id):return self.reconcile(attempt_id)
    def record_receipt(self,provider,provider_ref):
        now=int(self.clock());self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute("SELECT * FROM mail_provider_attempts WHERE provider=? AND provider_ref=? AND outcome='ACCEPTED'",(provider,provider_ref)).fetchone()
            if not row:self.db.commit();return None
            self.db.execute("UPDATE mail_provider_attempts SET outcome='DELIVERED',detail='DELIVERED_RECEIPT',detail_sha256=?,updated=? WHERE id=?",(_sha('DELIVERED_RECEIPT'),now,row['id']));self.db.execute("UPDATE mail_idempotency SET state='DELIVERED',updated=? WHERE attempt_id=?",(now,row['id']));self.db.commit();return self._result(row['message_key'])
        except BaseException:self.db.rollback();raise

def install(center,bindings=(),transports=None):
    delivery=MailDelivery(center.db,bindings,transports,clock=center.clock);center.mail_delivery=delivery;center.mail_ready=delivery.ready
    def mail_challenge(self,kind,outbox_kind,user,address):
        for row in self.db.execute("SELECT * FROM outbox WHERE user_id=? AND kind=? AND status!='CANCELLED' ORDER BY at DESC,rowid DESC",(user,outbox_kind)).fetchall():
            payload=json.loads(self.decrypt(row['payload'],'outbox:'+row['id']));token=payload.get('token');challenge=self.db.execute('SELECT expires,used FROM challenges WHERE token=? AND kind=? AND user_id=?',(_sha(token),kind,user)).fetchone() if type(token) is str else None
            if challenge and not challenge['used'] and challenge['expires']>self.now():
                if row['status'] in ('PENDING','UNKNOWN','INFLIGHT'):return row['id'],token
                oid=secrets.token_hex(16);self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,outbox_kind,user,self.encrypt(self._mail_canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()));return oid,token
        self.db.execute("UPDATE outbox SET status='CANCELLED' WHERE user_id=? AND kind=? AND status='PENDING'",(user,outbox_kind));token=self.challenge(kind,user,{});oid=secrets.token_hex(16);self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?)',(oid,outbox_kind,user,self.encrypt(self._mail_canonical({'email':address,'token':token}),'outbox:'+oid),'PENDING',self.now()));return oid,token
    def deliver_outbox(self,oid):
        row=self.db.execute('SELECT * FROM outbox WHERE id=?',(oid,)).fetchone();payload=json.loads(self.decrypt(row['payload'],'outbox:'+oid));result=self.mail_delivery.send('outbox:'+oid,{'kind':row['kind'],'email':payload['email'],'code':payload['token']})
        if result.get('state') in ATTEMPT_STATES:self.db.execute('UPDATE outbox SET status=? WHERE id=?',(result['state'],oid))
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
    center._mail_unavailable=Unavailable;center._mail_canonical=canonical;center.mail_challenge=types.MethodType(mail_challenge,center);center.deliver_outbox=types.MethodType(deliver_outbox,center);center.register=types.MethodType(register,center);center.request_reset=types.MethodType(request_reset,center)
    return delivery
