"""Mini identity on the existing exact PR122 Center database, without new tables.

Reuses accounts/sessions/links/events/audit and live project permissions. No
second Identity/CRM/queue is created. Caller must supply the admitted Center
instance and StageRuntime; source reuse does not authorize host installation.
"""
import hashlib
import json
import secrets
from pathlib import Path
from scripts.pr122_customer_core import Center,canonical,digest
from scripts.community_mini_login import IdentityPort
from scripts.community_saas_phase2 import Principal
from scripts.community_merchant_contract import scope,payment_amount

class CenterIdentity(IdentityPort):
    def __init__(self,center,runtime,appid,scenes):
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest()!='f9a736fa954bcc3fbdf2eea317bb0b71559864126c940ac6738a4bc9e4a87bd4':
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        if type(center) is not Center or type(scenes) is not dict or not scenes:
            raise ValueError('EXISTING_CENTER_REQUIRED')
        self.center,self.runtime,self.appid=center,runtime,appid
        self.scenes={}
        from scripts.community_mini_login import APPID,SCENE
        if type(appid) is not str or not APPID.fullmatch(appid):raise ValueError('INVALID_APPID')
        for scene,binding in scenes.items():
            if type(scene) is not str or not SCENE.fullmatch(scene) or type(binding) is not dict or set(binding)!={'project','principal'}:
                raise ValueError('INVALID_SCENE_BINDING')
            principal=binding['principal']
            if type(principal) is not Principal or principal.role!='CUSTOMER' or principal not in runtime.bindings:
                raise PermissionError('REGISTERED_CUSTOMER_REQUIRED')
            self.scenes[scene]=dict(binding)
    def _time(self,now):
        if type(now) is not int or now!=self.center.now():raise ValueError('CENTER_CLOCK_MISMATCH')
        if self.center.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0]!='0':
            raise PermissionError('CENTER_MAINTENANCE')
    def _subject(self,appid,openid):
        if appid!=self.appid or type(openid) is not str or not 1<=len(openid)<=128:raise PermissionError('PROVIDER_SUBJECT_REQUIRED')
        return self.center.idx('wechat-mini:'+appid+':'+openid)
    def authorize_binding(self,web_session,csrf,now,consume_limit=True):
        """Reuse the current Center session and CSRF before any provider IO."""
        self._time(now)
        if type(csrf) is not str or not csrf:
            raise PermissionError('CENTER_CSRF_REQUIRED')
        uid=self.center.session(web_session,csrf)
        if consume_limit:
            with self.center.tx():
                self.center.limit('wechat-bind:'+uid,5,900)
        return uid
    def limit_login_source(self,source,now):
        self._time(now)
        if type(source) is not str or not source.isascii() or not 1<=len(source)<=128:
            raise PermissionError('TRUSTED_SOURCE_REQUIRED')
        with self.center.tx():
            # Share the original Center HTTP source quota, not a second counter.
            self.center.limit('auth-source:'+source,40,300)
    def _resolve(self,token,scene):
        binding=self.scenes.get(scene)
        if binding is None:raise PermissionError('SCENE_NOT_REGISTERED')
        uid=self.center.session(token)
        session_key=self.center.idx('wechat-session:'+token)
        meta=self.center.db.execute("SELECT payload FROM links WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=? AND user_id=? AND project=? AND active=1",(session_key,uid,binding['project'])).fetchone()
        if meta is None:raise PermissionError('MINI_SESSION_BINDING_REQUIRED')
        subject=json.loads(self.center.decrypt(meta[0],'wechat-mini-session'))['subject_idx']
        if self.center.db.execute("SELECT 1 FROM links WHERE channel='WECHAT_MINI' AND subject_idx=? AND user_id=? AND project=? AND active=1",(subject,uid,binding['project'])).fetchone() is None:
            raise PermissionError('PROVIDER_LINK_REVOKED')
        project,_,_=self.center.project(uid,binding['project'],('OWNER','EDITOR'))
        principal=binding['principal']
        if project['tenant']!=principal.tenant_id:raise PermissionError('PROJECT_TENANT_MISMATCH')
        return uid,binding['project'],principal
    def bind_existing_account(self,web_session,appid,openid):
        """Protected Python binding after trusted provider exchange; no HTTP route.

        web_session authenticates an existing verified account. No registration,
        caller role or verified boolean is accepted. Operator must invoke only
        with the subject obtained from WechatCodeClient.exchange.
        """
        center=self.center;subject=self._subject(appid,openid)
        with center.tx():
            uid=center.session(web_session)
            old=center.db.execute("SELECT user_id FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?",(subject,)).fetchall()
            if any(row[0]!=uid for row in old):raise PermissionError('SUBJECT_ALREADY_BOUND')
            permitted=[]
            for binding in self.scenes.values():
                try:project,_,_=center.project(uid,binding['project'],('OWNER','EDITOR'))
                except PermissionError:continue
                if project['tenant']==binding['principal'].tenant_id:permitted.append(binding['project'])
            if not permitted:raise PermissionError('EXISTING_PROJECT_MEMBERSHIP_REQUIRED')
            for pid in sorted(set(permitted)):
                # Existing disabled binding can only be reactivated by that same
                # verified account through this protected binding operation.
                payload=center.encrypt(canonical({'appid':appid}),'wechat-mini-link')
                center.db.execute("INSERT INTO links VALUES('WECHAT_MINI',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET active=1",
                                  (subject,uid,pid,payload))
                center.audit(pid,uid,'WECHAT_MINI_BIND',subject)
        return {'bound':True}
    def reserve_code(self,appid,code_sha256,now):
        self._time(now)
        if appid!=self.appid or type(code_sha256) is not str or len(code_sha256)!=64:raise ValueError('INVALID_CODE_DIGEST')
        attempt=self.center.idx('wechat-code:'+appid+':'+code_sha256)
        with self.center.tx():
            if self.center.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_MINI_LOGIN' AND event_id=?",(attempt,)).fetchone():
                raise PermissionError('LOGIN_CODE_ALREADY_CONSUMED')
            self.center.db.execute("INSERT INTO events VALUES('WECHAT_MINI_LOGIN',?,?)",(attempt,now))
            self.center.audit('','wechat-mini','WECHAT_LOGIN_RESERVED',attempt)
        return attempt
    def issue_session(self,attempt,appid,openid,now):
        self._time(now);subject=self._subject(appid,openid);c=self.center
        with c.tx():
            if c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_MINI_LOGIN' AND event_id=?",(attempt,)).fetchone() is None:
                raise PermissionError('LOGIN_RESERVATION_REQUIRED')
            if c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_MINI_LOGIN_FAILED' AND event_id=?",(attempt,)).fetchone():
                raise PermissionError('FAILED_LOGIN_CONSUMED')
            c.db.execute("INSERT INTO events VALUES('WECHAT_MINI_LOGIN_ISSUED',?,?)",(attempt,now))
            rows=c.db.execute("SELECT DISTINCT user_id FROM links WHERE channel='WECHAT_MINI' AND subject_idx=? AND active=1",(subject,)).fetchall()
            if len(rows)!=1:raise PermissionError('EXISTING_ACCOUNT_LINK_REQUIRED')
            uid=rows[0][0];account=c.db.execute('SELECT verified,epoch FROM accounts WHERE id=?',(uid,)).fetchone()
            if account is None or account[0]!=1:raise PermissionError('VERIFIED_ACCOUNT_REQUIRED')
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);expires=now+3600
            c.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token.encode()),uid,account[1],digest(csrf.encode()),expires))
            session_key=c.idx('wechat-session:'+token)
            for row in c.db.execute("SELECT project FROM links WHERE channel='WECHAT_MINI' AND subject_idx=? AND user_id=? AND active=1",(subject,uid)).fetchall():
                payload=c.encrypt(canonical({'subject_idx':subject,'openid':openid}),'wechat-mini-session')
                c.db.execute("INSERT INTO links VALUES('WECHAT_MINI_SESSION',?,?,?,?,1)",(session_key,uid,row[0],payload))
            c.audit('',uid,'WECHAT_MINI_LOGIN',attempt)
        return {'session_token':token,'expires_at':expires}
    def abandon_attempt(self,attempt,reason,now):
        self._time(now)
        with self.center.tx():
            self.center.db.execute("INSERT OR IGNORE INTO events VALUES('WECHAT_MINI_LOGIN_FAILED',?,?)",(attempt,now))
            self.center.audit('','wechat-mini','WECHAT_LOGIN_UNKNOWN_OR_REJECTED',attempt)
    def resolve(self,token,scene,now):
        self._time(now)
        return self._resolve(token,scene)[2]
    def _order_key(self,principal,reference):
        identity=self.runtime.bindings[principal];scope(identity)
        return self.center.idx('community-order:'+canonical([identity,reference]).decode()),identity
    def reserve_order(self,token,scene,reference,amount_minor,now):
        self._time(now);payment_amount(amount_minor,'CNY',reference);c=self.center
        with c.tx():
            uid,pid,principal=self._resolve(token,scene);key,identity=self._order_key(principal,reference)
            # Any prior ownership record (including inactive/history) is retained.
            if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_ORDER' AND subject_idx=?",(key,)).fetchone():
                raise PermissionError('ORDER_REFERENCE_ALREADY_RESERVED')
            t,m,s=scope(identity)
            if self.runtime.demo.db.execute('SELECT 1 FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,reference)).fetchone():
                raise PermissionError('LEGACY_ORDER_CANNOT_BE_CLAIMED')
            payload=c.encrypt(canonical({'scope':identity,'reference':reference,'amount_minor':amount_minor}),'community-order:'+key)
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_ORDER',?,?,?,?,1)",(key,uid,pid,payload))
            c.audit(pid,uid,'COMMUNITY_ORDER_RESERVED',key)
    def authorize_order_read(self,token,scene,reference,now):
        self._time(now);c=self.center
        uid,pid,principal=self._resolve(token,scene);key,identity=self._order_key(principal,reference)
        record=c.db.execute("SELECT user_id,project,payload FROM links WHERE channel='COMMUNITY_ORDER' AND subject_idx=? AND active=1",(key,)).fetchone()
        if record is None or record['user_id']!=uid or record['project']!=pid:raise PermissionError('CUSTOMER_ORDER_DENIED')
        payload=json.loads(c.decrypt(record['payload'],'community-order:'+key))
        from scripts.community_order_store import state
        order=state(self.runtime.demo.db,identity,reference)
        if payload!={'scope':identity,'reference':reference,'amount_minor':order['amount_minor']}:
            raise PermissionError('ORDER_BINDING_MISMATCH')
    def revoke(self,token,now):
        self._time(now);self.center.logout(token)
