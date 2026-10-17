"""Fail-closed provider boundaries. Provider callbacks do not accept caller proof.
No external API is called by import or constructor; test transports are injected
only by the test harness. Production requires protected config plus real receipts.
"""
import base64
import hashlib
import hmac
import json
import os
import smtplib
import ssl
import subprocess
import tempfile
import time
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives import padding
from scripts.pr122_customer_core import Denied,Unavailable,canonical,private_path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise Unavailable('PROVIDER_REDIRECT_REJECTED')

def post_json(url,body,headers=None):
    # All URLs constructed from fixed provider endpoints, never user-supplied.
    req=urllib.request.Request(url,canonical(body),{'Content-Type':'application/json',**(headers or {})},method='POST')
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as r:
        raw=r.read(1_000_001)
        if len(raw)>1_000_000: raise Unavailable('PROVIDER_RESPONSE_SIZE')
        return json.loads(raw)

def load_config(path):
    path=private_path(path);s=path.stat()
    if s.st_uid!=0 or s.st_mode & 0o077 or not path.is_file(): raise Denied('PROTECTED_CONFIG_REQUIRED')
    return json.loads(path.read_bytes())

class ClamScanner:
    def __init__(self,folder='/run/xuanjun-customer-scan',command='/usr/bin/clamdscan'):
        self.folder=private_path(folder); self.command=command
    def __call__(self,raw):
        # tmpfs private runtime dir, service-private, removed even on timeout.
        with tempfile.NamedTemporaryFile(dir=self.folder,prefix='scan-',delete=False) as f:
            name=f.name; os.chmod(name,0o600);f.write(raw);f.flush()
        try:
            r=subprocess.run([self.command,'--fdpass','--no-summary','--',name],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25,check=False)
            return r.returncode==0
        except (OSError,subprocess.TimeoutExpired): return False
        finally: Path(name).unlink(missing_ok=True)

def telegram_send(token,subject,text,*,connect=None):
    """Token-path protocol isolated to direct validated TLS. No env proxy,
    redirect, urllib request object, wire debug, TLS key log, raw exception or
    provider response is allowed to escape this transport boundary.
    """
    import http.client,re
    if type(token) is not str or not re.fullmatch(r'[A-Za-z0-9_:-]{1,256}',token):raise Unavailable('TELEGRAM_CREDENTIAL_INVALID')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_default_certs()
    context.minimum_version=ssl.TLSVersion.TLSv1_2;context.keylog_filename=None
    connection=None;result=None
    try:
        connection=(connect or http.client.HTTPSConnection)('api.telegram.org',443,timeout=12,context=context)
        connection.set_debuglevel(0)
        connection.request('POST','/bot'+token+'/sendMessage',body=canonical({'chat_id':subject,'text':text}),headers={'Content-Type':'application/json'})
        response=connection.getresponse()
        if response.status==200:
            raw=response.read(1_000_001)
            if len(raw)<=1_000_000:
                d=json.loads(raw);mid=d.get('result',{}).get('message_id')
                if d.get('ok') is True and type(mid) is int and mid>0:result={'ok':True,'result':{'message_id':mid}}
    except Exception:
        # Do not retain/chains/re-raise the secret-bearing transport exception.
        pass
    finally:
        if connection is not None:
            try:connection.close()
            except Exception:pass
    if result is None:raise Unavailable('TELEGRAM_REQUEST_UNCONFIRMED')
    return result

class VerifiedEvent(tuple):
    """Preserve existing three-value unpacking while retaining verified time."""
    def __new__(cls,event,subject,text,occurred_at):
        value=super().__new__(cls,(event,subject,text));value.occurred_at=occurred_at;return value

class Providers:
    def __init__(self,config,*,post=post_json,clock=time.time,telegram_transport=telegram_send):
        self.config=config;self.post=post;self.clock=clock;self.telegram_transport=telegram_transport
    def status(self):
        # A config is not an actual accepted end-to-end connection.
        return {k:{'state':'CONFIGURED_AWAIT_ACCEPTANCE' if self.config.get(k) else 'PENDING_CONNECTION','accepted':False} for k in ('smtp','telegram','feishu','secretref','web_ai')}
    def telegram(self,headers,raw):
        c=self.config.get('telegram')
        if not c or len(c.get('webhook_secret',''))<32: raise Unavailable('TELEGRAM_PENDING')
        value=headers.get('X-Telegram-Bot-Api-Secret-Token','')
        if not hmac.compare_digest(value,c['webhook_secret']): raise Denied('TELEGRAM_SIGNATURE')
        d=json.loads(raw); m=d.get('message',{}); sender=m.get('from',{});chat=m.get('chat',{})
        if type(d.get('update_id')) is not int or sender.get('is_bot') is not False or chat.get('type')!='private' or type(sender.get('id')) is not int or sender['id']!=chat.get('id'): raise Denied('PRIVATE_PROVIDER_IDENTITY_REQUIRED')
        if type(m.get('date')) is not int or abs(self.clock()-m['date'])>300: raise Denied('PROVIDER_EVENT_EXPIRED')
        if set(m).intersection({'document','photo','video','audio','voice'}): raise Denied('PRIVATE_PORTAL_UPLOAD_ONLY')
        return VerifiedEvent(str(d['update_id']),str(sender['id']),m.get('text',''),m['date'])
    def feishu(self,headers,raw):
        c=self.config.get('feishu')
        if not c or not c.get('encrypt_key') or not c.get('verification_token') or not c.get('app_id'): raise Unavailable('FEISHU_PENDING')
        stamp=headers.get('X-Lark-Request-Timestamp','');nonce=headers.get('X-Lark-Request-Nonce','');signature=headers.get('X-Lark-Signature','')
        if not stamp.isdigit() or abs(self.clock()-int(stamp))>300 or not 8<=len(nonce)<=128: raise Denied('FEISHU_EVENT_EXPIRED')
        expected=hashlib.sha256(stamp.encode()+nonce.encode()+c['encrypt_key'].encode()+raw).hexdigest()
        if not hmac.compare_digest(expected,signature): raise Denied('FEISHU_SIGNATURE')
        outer=json.loads(raw)
        if set(outer)!={'encrypt'}: raise Denied('FEISHU_ENCRYPTED_ONLY')
        ciphertext=base64.b64decode(outer['encrypt'],validate=True)
        if len(ciphertext)<32 or len(ciphertext)%16: raise Denied('FEISHU_CIPHERTEXT')
        key=hashlib.sha256(c['encrypt_key'].encode()).digest()
        decryptor=Cipher(algorithms.AES(key),modes.CBC(ciphertext[:16])).decryptor()
        padded=decryptor.update(ciphertext[16:])+decryptor.finalize()
        unpad=padding.PKCS7(128).unpadder(); d=json.loads(unpad.update(padded)+unpad.finalize())
        if d.get('type')=='url_verification':
            if not hmac.compare_digest(d.get('token',''),c['verification_token']): raise Denied('FEISHU_TOKEN')
            return {'challenge':d['challenge']}
        h=d.get('header',{});e=d.get('event',{});m=e.get('message',{});sender=e.get('sender',{})
        if h.get('app_id')!=c['app_id'] or not hmac.compare_digest(h.get('token',''),c['verification_token']) or h.get('event_type')!='im.message.receive_v1': raise Denied('FEISHU_APP_SCOPE')
        if not str(h.get('create_time','')).isdigit() or abs(self.clock()-int(h['create_time'])/1000)>300: raise Denied('FEISHU_EVENT_EXPIRED')
        if m.get('chat_type')!='p2p' or m.get('message_type')!='text' or sender.get('sender_type')!='user': raise Denied('PRIVATE_TEXT_ONLY')
        subject=sender.get('sender_id',{}).get('open_id')
        if not subject or not h.get('event_id'): raise Denied('FEISHU_IDENTITY_REQUIRED')
        return VerifiedEvent(h['event_id'],subject,json.loads(m['content']).get('text',''),int(h['create_time'])//1000)
    def send(self,channel,subject,text,event_id):
        if channel=='TELEGRAM':
            c=self.config.get('telegram')
            if not c or not c.get('bot_token'): raise Unavailable('TELEGRAM_PENDING')
            r=self.telegram_transport(c['bot_token'],subject,text)
            if r.get('ok') is not True or not r.get('result',{}).get('message_id'): raise Unavailable('TELEGRAM_NOT_ACCEPTED')
            return 'ACCEPTED',str(r['result']['message_id']) # API acceptance is not recipient delivery.
        if channel=='FEISHU':
            c=self.config.get('feishu')
            if not c or not c.get('app_secret'): raise Unavailable('FEISHU_PENDING')
            auth=self.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',{'app_id':c['app_id'],'app_secret':c['app_secret']})
            if auth.get('code')!=0 or not auth.get('tenant_access_token'): raise Unavailable('FEISHU_TOKEN_PENDING')
            r=self.post('https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id',{'receive_id':subject,'msg_type':'text','content':json.dumps({'text':text},ensure_ascii=False),'uuid':event_id},{'Authorization':'Bearer '+auth['tenant_access_token']})
            if r.get('code')!=0 or not r.get('data',{}).get('message_id'): raise Unavailable('FEISHU_NOT_ACCEPTED')
            return 'ACCEPTED',r['data']['message_id']
        raise ValueError('INVALID_CHANNEL')
    def mail(self,address,purpose,token,origin):
        c=self.config.get('smtp')
        if not c: raise Unavailable('MAIL_PENDING')
        # Tokens are entered in an authenticated-origin form, not URL/query logs.
        msg=EmailMessage();msg['From']=c['sender'];msg['To']=address;msg['Subject']='玄钧云汇：'+('验证邮箱' if purpose=='VERIFY' else '重置密码')
        msg.set_content('请在 '+origin+'/customer/center/ 输入一次性验证码（10分钟有效）：\n'+token+'\n不要转发给他人。')
        with smtplib.SMTP(c['host'],int(c.get('port',587)),timeout=12) as smtp:
            smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo();smtp.login(c['username'],c['password']);smtp.send_message(msg)
        return 'ACCEPTED' # Not proof of inbox delivery.

def drain_mail(center,providers,origin):
    """Claim persisted before I/O; interrupted/timeout remains UNKNOWN, no auto resend."""
    r=center.db.execute("SELECT * FROM outbox WHERE status='PENDING' ORDER BY at LIMIT 1").fetchone()
    if not r:return {'pending':False}
    with center.tx():
        changed=center.db.execute("UPDATE outbox SET status='UNKNOWN' WHERE id=? AND status='PENDING'",(r['id'],)).rowcount
    if not changed:return {'claimed':False}
    try:
        p=json.loads(center.decrypt(r['payload'],'outbox:'+r['id']));status=providers.mail(p['email'],r['kind'],p['token'],origin)
    except Exception: return {'status':'UNKNOWN'}
    with center.tx():center.db.execute('UPDATE outbox SET status=? WHERE id=?',(status,r['id']))
    return {'status':status}

def enqueue(center,uid,pid,channel,text):
    from scripts.pr122_customer_core import safe_text
    if channel not in ('TELEGRAM','FEISHU'):raise ValueError('CHANNEL')
    with center.tx():
        from scripts.pr122_customer_evidence import authorized_records
        authorized_records(center,uid,pid);safe_text(text)
        link=center.db.execute('SELECT * FROM links WHERE user_id=? AND project=? AND channel=? AND active=1',(uid,pid,channel)).fetchone()
        if not link:raise Denied('LINK_REQUIRED')
        import secrets
        mid='m_'+secrets.token_hex(16)
        center.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',(mid,pid,uid,channel,center.encrypt(text.encode(),mid),'PENDING',center.now()));center.audit(pid,uid,'OUTBOUND_PENDING',mid)
        from scripts.pr122_customer_evidence import append
        append(center,mid)
        return {'id':mid,'status':'PENDING'}

def drain_message(center,providers):
    r=center.db.execute("SELECT * FROM messages WHERE status='PENDING' ORDER BY created LIMIT 1").fetchone()
    if not r:return {'pending':False}
    with center.tx():
        from scripts.pr122_customer_evidence import authorized_records
        authorized_records(center,r['user_id'],r['project'])
        link=center.db.execute('SELECT * FROM links WHERE user_id=? AND project=? AND channel=? AND active=1',(r['user_id'],r['project'],r['channel'])).fetchone()
        if not link:raise Denied('LINK_REVOKED')
        if center.db.execute("UPDATE messages SET status='UNKNOWN' WHERE id=? AND status='PENDING'",(r['id'],)).rowcount!=1:return {'claimed':False}
        center.audit(r['project'],r['user_id'],'OUTBOUND_ATTEMPT_UNKNOWN',r['id'])
    try:
        subject=center.decrypt(link['payload'],'link').decode();text=center.decrypt(r['payload'],r['id']).decode()
        status,ref=providers.send(r['channel'],subject,text,r['id'])
    except Exception:return {'status':'UNKNOWN'}
    with center.tx():
        center.db.execute('UPDATE messages SET status=?,provider_ref=? WHERE id=?',(status,ref,r['id']));center.audit(r['project'],r['user_id'],'OUTBOUND_ACCEPTED',r['id'])
    return {'status':status,'provider_ref':ref}

class SecretRefMetadata:
    """Only metadata to a pre-mapped local authoritative service; never secret values.
    An operator pins socket path/peer UID. No request-selected host or transport.
    """
    def __init__(self,path,peer_uid):
        self.path=private_path(path);self.peer_uid=peer_uid
        if str(self.path)!='/run/xuanjun-secretref/metadata.sock' or type(peer_uid) is not int or peer_uid<=0:raise Denied('PINNED_SECRETREF_REQUIRED')
    def __call__(self,project,item,kind,reference):
        import socket,struct
        try:
            s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(3)
            with s:
                s.connect(str(self.path));pid,uid,gid=struct.unpack('3i',s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid!=self.peer_uid:return False
                raw=canonical({'operation':'validate_reference','project_id':project,'item_id':item,'kind':kind,'reference':reference})
                s.sendall(struct.pack('!I',len(raw))+raw)
                def read(n):
                    result=b''
                    while len(result)<n:
                        part=s.recv(n-len(result))
                        if not part:raise Unavailable('SECRETREF_TRUNCATED')
                        result+=part
                    return result
                size=struct.unpack('!I',read(4))[0]
                if size>16384:return False
                d=json.loads(read(size))
                return set(d)=={'project_id','item_id','kind','reference','active','expires_at'} and d['project_id']==project and d['item_id']==item and d['kind']==kind and d['reference']==reference and d['active'] is True and type(d['expires_at']) is int and d['expires_at']>time.time()
        except (OSError,ValueError,Unavailable):return False

def local_ai(config,context):
    """Provider-neutral host bridge with a pinned approved OpenAI model identity.
    The host bridge owns provider credentials; customer material secrets are never
    forwarded. No external model call occurs in tests or when mapping is absent.
    """
    import socket,struct
    if config.get('socket')!='/run/xuanjun-customer-ai/reply.sock' or type(config.get('peer_uid')) is not int or config['peer_uid']<=0 or config.get('provider')!='openai' or not config.get('model_key'):raise Unavailable('APPROVED_AI_MAPPING_REQUIRED')
    raw=canonical(context)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(15);s.connect(str(private_path(config['socket'])))
        _,uid,_=struct.unpack('3i',s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid!=config['peer_uid']:raise Denied('AI_PEER_IDENTITY')
        s.sendall(struct.pack('!I',len(raw))+raw)
        def read(n):
            value=b''
            while len(value)<n:
                part=s.recv(n-len(value))
                if not part:raise Unavailable('AI_TRUNCATED')
                value+=part
            return value
        size=struct.unpack('!I',read(4))[0]
        if not 1<=size<=64000:raise Denied('AI_RESPONSE_LIMIT')
        d=json.loads(read(size))
        if set(d)!={'message_id','request_sha256','provider','model_key','text'} or d['message_id']!=context['message_id'] or d['request_sha256']!=hashlib.sha256(raw).hexdigest() or d['provider']!=config['provider'] or d['model_key']!=config['model_key']:raise Denied('AI_CONTEXT_BINDING')
        return d['text']

def ai_reply(center,uid,pid,mid,providers,*,rpc=local_ai):
    import secrets
    from scripts.pr122_customer_core import safe_text
    c=providers.config.get('web_ai')
    if not c:return {'state':'PENDING_PROVIDER'}
    with center.tx():
        from scripts.pr122_customer_evidence import authorized_records
        p,_,_=authorized_records(center,uid,pid);source=center.db.execute("SELECT * FROM messages WHERE id=? AND project=? AND user_id=? AND channel='WEB'",(mid,pid,uid)).fetchone()
        if not source:raise Denied('AI_SOURCE_MESSAGE')
        old=center.db.execute('SELECT state,result_id FROM ai_jobs WHERE message_id=?',(mid,)).fetchone()
        if old:return {'state':old[0],'result_id':old[1]}
        center.db.execute("INSERT INTO ai_jobs VALUES(?,'UNKNOWN',NULL)",(mid,))
        context={'message_id':mid,'user_id':uid,'project_id':pid,'tenant_id':p['tenant'],'customer_id':p['customer'],'body':center.decrypt(source['payload'],mid).decode()}
    try:
        text=safe_text(rpc(c,context),4000)
        with center.tx():
            authorized_records(center,uid,pid);rid='m_'+secrets.token_hex(16)
            center.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',(rid,pid,uid,'WEB_AI',center.encrypt(text.encode(),rid),'ARCHIVED',center.now()));center.db.execute("UPDATE ai_jobs SET state='ANSWERED',result_id=? WHERE message_id=?",(rid,mid));center.audit(pid,uid,'AI_REPLY_ARCHIVED',rid)
            from scripts.pr122_customer_evidence import append
            append(center,rid,related_message_id=mid)
        return {'state':'ANSWERED','result_id':rid}
    except Exception:return {'state':'UNKNOWN'}
