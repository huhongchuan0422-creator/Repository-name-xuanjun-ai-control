"""LOCAL candidate: original WeChat -> original Center reviewer web session.

Not installed or routed. Call only on original host's serialized Center thread.
No membership writes, provider IO, new schema, or alternate identity database.
"""
import hmac
import json
import secrets
from scripts.pr122_customer_core import canonical, digest
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_web_session import WebSession, COOKIE

KIND = 'COMMUNITY_REVIEWER_BROWSER_V1'
BROWSER_COOKIE = '__Host-xj_reviewer_browser'

class ReviewerWebBridge:
    def __init__(self, identity, web, scene, origin):
        if type(identity) is not CenterIdentity or type(web) is not WebSession or web.center is not identity.center:
            raise ValueError('SAME_ORIGINAL_SERVICES_REQUIRED')
        if web.onboarding is None or scene not in identity.scenes or not origin.startswith('https://') or '/' in origin[8:]:
            raise ValueError('PROTECTED_HOST_BINDING_REQUIRED')
        self.identity, self.web, self.c = identity, web, identity.center
        self.scene, self.origin = scene, origin
        self.project = identity.scenes[scene]['project']

    def _origin(self, origin):
        if origin != self.origin: raise PermissionError('SAME_ORIGIN_REQUIRED')

    def begin(self, *, origin, source):
        self._origin(origin)
        self.identity.limit_login_source(source, self.c.now()) # original 40/300
        browser, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.c.tx():
            challenge = self.c.challenge(KIND, '', dict(state='PENDING', browser=digest(browser.encode()),
                csrf=digest(csrf.encode()), origin=self.origin, scene=self.scene,
                project=self.project, verification=secrets.token_hex(16))) # original 600s
            row, data = self._load(challenge)
        return dict(challenge=challenge, csrf=csrf, verification=data['verification'], expires_at=row['expires']), self._cookie(BROWSER_COOKIE, browser, 600)

    @staticmethod
    def _cookie(name, value, ttl):
        return f'{name}={value}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={ttl}'

    def _load(self, challenge):
        if type(challenge) is not str or not 32 <= len(challenge) <= 128:
            raise PermissionError('INVALID_CHALLENGE')
        row = self.c.db.execute('SELECT * FROM challenges WHERE token=? AND kind=?', (digest(challenge.encode()), KIND)).fetchone()
        if row is None: raise PermissionError('INVALID_CHALLENGE')
        data = json.loads(self.c.decrypt(row['payload'], 'challenge'))
        if (data['origin'], data['scene'], data['project']) != (self.origin, self.scene, self.project):
            raise PermissionError('HOST_BINDING_CHANGED')
        return row, data

    def _save(self, row, data):
        self.c.db.execute('UPDATE challenges SET payload=? WHERE token=?', (self.c.encrypt(canonical(data), 'challenge'), row['token']))

    def _browser(self, data, browser, csrf, origin):
        self._origin(origin)
        if not all(type(x) is str and 32 <= len(x) <= 128 for x in (browser, csrf)):
            raise PermissionError('BROWSER_CSRF_REQUIRED')
        if not hmac.compare_digest(data['browser'], digest(browser.encode())) or not hmac.compare_digest(data['csrf'], digest(csrf.encode())):
            raise PermissionError('BROWSER_CSRF_REQUIRED')

    def _reviewer(self, uid):
        from scripts import community_wechat_registration as registration
        if registration.native(self.c, uid) is not None:
            project = registration.project(self.identity, uid, self.scene)
            if project['id'] != self.project:
                raise PermissionError('EXACT_SCENE_PROJECT_REQUIRED')
        else:
            self.identity.authorize_customer_project(uid, self.project)
        self.c.project(uid, self.project, ('REVIEWER',))
        if self.web.onboarding.reviewers.get(uid) != self.project:
            raise PermissionError('REVIEWER_HOST_MAPPING_REQUIRED')
        self.web.onboarding._reviewer(uid)

    def describe(self, challenge, mini_session):
        # Mini transport already authenticates its bearer; never return it or its CSRF.
        with self.c.tx():
            uid, pid, _ = self.identity._resolve(mini_session, self.scene)
            self._reviewer(uid)
            row, data = self._load(challenge)
            if row['used'] or row['expires'] <= self.c.now(): raise PermissionError('INVALID_CHALLENGE')
            return dict(origin=self.origin, project=pid, verification=data['verification'], state=data['state'], expires_at=row['expires'])

    def confirm(self, challenge, mini_session, *, verification, action):
        if action != 'CONFIRM_THIS_BROWSER': raise PermissionError('EXPLICIT_BROWSER_CONFIRMATION_REQUIRED')
        self.identity._time(self.c.now())
        with self.c.tx():
            uid, _, _ = self.identity._resolve(mini_session, self.scene)
            self._reviewer(uid)
            row, data = self._load(challenge)
            if row['used'] or row['expires'] <= self.c.now(): raise PermissionError('INVALID_CHALLENGE')
            if type(verification) is not str or not hmac.compare_digest(data['verification'], verification):
                raise PermissionError('WRONG_BROWSER_CONFIRMATION')
            session = self.c.db.execute('SELECT * FROM sessions WHERE token=?', (digest(mini_session.encode()),)).fetchone()
            key = self.c.idx('wechat-session:'+mini_session)
            meta = self.c.db.execute("SELECT payload FROM links WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=? AND user_id=? AND project=? AND active=1", (key, uid, self.project)).fetchone()
            subject = json.loads(self.c.decrypt(meta[0], 'wechat-mini-session'))['subject_idx']
            binding = dict(uid=uid, epoch=session['epoch'], mini_hash=session['token'], mini_key=key, subject=subject)
            if data['state'] == 'CONFIRMED':
                if data['binding'] != binding: raise PermissionError('CONFIRMATION_CONFLICT')
                return {'state':'CONFIRMED'}
            if data['state'] != 'PENDING': raise PermissionError('INVALID_CHALLENGE')
            data.update(state='CONFIRMED', binding=binding)
            self._save(row, data)
            self.c.audit(self.project, uid, 'REVIEWER_BROWSER_CONFIRMED', row['token'])
        return {'state':'CONFIRMED'}

    def _live(self, binding):
        self.identity._time(self.c.now())
        uid = binding['uid']
        row = self.c.db.execute('SELECT s.*,a.epoch current_epoch,a.verified FROM sessions s JOIN accounts a ON a.id=s.user_id WHERE s.token=?', (binding['mini_hash'],)).fetchone()
        if row is None or row['user_id'] != uid or row['epoch'] != binding['epoch'] or row['current_epoch'] != binding['epoch'] or row['verified'] != 1 or row['expires'] <= self.c.now():
            raise PermissionError('MINI_SESSION_REVOKED')
        for channel, key in [('WECHAT_MINI', binding['subject']), ('WECHAT_MINI_SESSION', binding['mini_key'])]:
            if self.c.db.execute('SELECT 1 FROM links WHERE channel=? AND subject_idx=? AND user_id=? AND project=? AND active=1', (channel, key, uid, self.project)).fetchone() is None:
                raise PermissionError('PROVIDER_LINK_REVOKED')
        self._reviewer(uid)

    def browser(self, challenge, *, browser, csrf, origin, action):
        if action not in ('QUERY', 'FINISH', 'CANCEL'): raise ValueError('EXACT_ACTION_REQUIRED')
        self.identity._time(self.c.now())
        with self.c.tx():
            row, data = self._load(challenge)
            self._browser(data, browser, csrf, origin)
            if action == 'CANCEL':
                # Cancellation racing finish revokes only this attempt's web session.
                if data.get('web_hash'): self.c.db.execute('DELETE FROM sessions WHERE token=?', (data['web_hash'],))
                if data['state'] != 'CANCELLED':
                    self.c.audit(self.project, data.get('binding', {}).get('uid', 'browser'), 'REVIEWER_BROWSER_CANCELLED', row['token'])
                data['state'] = 'CANCELLED'
                self.c.db.execute('UPDATE challenges SET used=1 WHERE token=?', (row['token'],))
                self._save(row, data)
                return {'state':'CANCELLED'}, None
            if data['state'] == 'CANCELLED': return {'state':'CANCELLED'}, None
            if row['expires'] <= self.c.now(): return {'state':'EXPIRED'}, None
            if data['state'] == 'PENDING': return {'state':'PENDING'}, None
            self._live(data['binding'])
            if data['state'] == 'ISSUED':
                # Response-loss/replay: never mint or reveal another credential.
                return {'state':'ISSUED', 'recovery':'CHECK_ORIGINAL_WEB_SESSION_OR_START_NEW'}, None
            if action == 'QUERY': return {'state':'CONFIRMED'}, None
            self.c.consume(challenge, KIND)
            token, web_csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            b = data['binding']
            self.c.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)', (digest(token.encode()), b['uid'], b['epoch'], digest(web_csrf.encode()), self.c.now()+3600))
            data.update(state='ISSUED', web_hash=digest(token.encode()))
            self._save(row, data)
            self.c.audit(self.project, b['uid'], 'REVIEWER_BROWSER_LOGIN', row['token'])
        return {'state':'ISSUED', 'csrf':web_csrf, 'user_id':b['uid']}, self._cookie(COOKIE, token, 3600)


def dispatch(gateway, web, path, headers, body, source, origin):
    """Exact transport adapter; original handler retains proxy/body-size checks."""
    if type(body) is not dict or type(body.get('scene')) is not str:
        raise ValueError('EXACT_BRIDGE_BODY_REQUIRED')
    bridge = ReviewerWebBridge(gateway.identity, web, body['scene'], origin)
    if path == '/mini/reviewer-login':
        if any(headers.get_all(k, []) for k in ('Origin','Cookie','Authorization','X-Center-Session','X-Center-CSRF','X-CSRF-Token')):
            raise PermissionError('MINI_BEARER_SESSION_REQUIRED')
        values = headers.get_all('X-Community-Session', [])
        if len(values) != 1: raise PermissionError('MINI_BEARER_SESSION_REQUIRED')
        if body.get('action') == 'DESCRIBE' and set(body) == {'scene','challenge','action'}:
            return bridge.describe(body['challenge'], values[0]), None
        if body.get('action') == 'CONFIRM_THIS_BROWSER' and set(body) == {'scene','challenge','action','verification'}:
            return bridge.confirm(body['challenge'], values[0], action=body['action'], verification=body['verification']), None
        raise ValueError('EXACT_MINI_CONFIRMATION_REQUIRED')
    if path != '/community/session/wechat': raise ValueError('UNKNOWN_BRIDGE_ROUTE')
    if headers.get_all('Origin', []) != [origin] or headers.get_all('Sec-Fetch-Site', []) not in ([], ['same-origin']):
        raise PermissionError('SAME_ORIGIN_REQUIRED')
    if any(headers.get_all(k, []) for k in ('Authorization','X-Community-Session','X-Center-Session','X-Center-CSRF')):
        raise PermissionError('BROWSER_COOKIE_REQUIRED')
    if len(headers.get_all('Cookie', [])) > 1: raise PermissionError('AMBIGUOUS_COOKIE')
    if body.get('action') == 'BEGIN' and set(body) == {'scene','action'}:
        return bridge.begin(origin=origin, source=source)
    if set(body) != {'scene','challenge','action'}: raise ValueError('EXACT_BROWSER_BODY_REQUIRED')
    cookies = [p.strip().partition('=')[2] for p in headers.get('Cookie','').split(';') if p.strip().partition('=')[0] == BROWSER_COOKIE]
    csrf = headers.get_all('X-CSRF-Token', [])
    if len(cookies) != 1 or len(csrf) != 1: raise PermissionError('BROWSER_CSRF_REQUIRED')
    return bridge.browser(body['challenge'], browser=cookies[0], csrf=csrf[0], origin=origin, action=body['action'])
