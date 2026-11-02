"""Local candidate only: existing authenticated host and Protected Store ports.
No HTTP listener, storage implementation, credentials, deployment or secret reader.
Python 3.6 compatible. Never run this module as a server.
"""
import abc
import html
import re
from collections import namedtuple
from urllib.parse import parse_qsl

NAMES = (
    'COMMUNITY_ADMIN_ACCEPTANCE_URL',
    'COMMUNITY_ADMIN_ACCEPTANCE_USERNAME',
    'COMMUNITY_ADMIN_ACCEPTANCE_PASSWORD',
)
TTL_SECONDS = 600
PURPOSE = 'community-admin-acceptance'
VERSION = 'community-acceptance-v1'
QUESTION_ID = re.compile(r'\A[A-Za-z0-9_-]{22,128}\Z')
STATUSES = frozenset(('STORED', 'REPLAY_REJECTED', 'EXPIRED', 'FORBIDDEN',
                      'CANCELLED', 'INVALID', 'UNKNOWN', 'NOT_FOUND'))
Principal = namedtuple('Principal', 'subject session_binding')
Request = namedtuple('Request', 'question_id subject session_binding purpose version expires_at status')
# Values must never be added to this type or returned from any port.
Outcome = namedtuple('Outcome', 'status')

HEADERS = {
    'Cache-Control': 'no-store, max-age=0',
    'Pragma': 'no-cache',
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}

STATUS_TEXT = {
    'PENDING': ('等待填写', '请在原安全页填写，仅由 Owner 本人提交。'),
    'STORED': ('已安全保存', '本次请求已完成，不能再次提交。凭据是否可供验收浏览器使用仍须单独验证。'),
    'REPLAY_REJECTED': ('请勿重复提交', '本次请求已成功提交过；请查询原请求结果，不会覆盖已保存凭据。'),
    'EXPIRED': ('链接已过期', '自创建起 10 分钟已到，未接收本次输入。已保存的凭据不会因链接过期删除。'),
    'CANCELLED': ('请求已取消', '原授权或请求已结束，未接收本次输入。'),
    'FORBIDDEN': ('无法使用此请求', '请使用原已授权的手机登录会话；不要在聊天里发送密码或 token。'),
    'INVALID': ('输入未提交', '字段不完整或请求格式不符，请回原安全页检查；不要在聊天里粘贴内容。'),
    'NOT_FOUND': ('请求不可用', '未找到当前会话可用的请求。'),
    'UNKNOWN': ('正在确认原提交结果', '不要重复提交或创建替代写入。请查询原请求回执，确认是否已经保存。'),
}

def status_page(outcome):
    """Fixed text only. Existing controller uses 303 POST->authenticated GET.
    Never put body fields in Location/query/history. Even STORED is not final QA.
    """
    status = outcome.status if isinstance(outcome, Outcome) else 'UNKNOWN'
    title, detail = STATUS_TEXT.get(status, STATUS_TEXT['UNKNOWN'])
    body = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>安全输入结果</title><main style="font:18px system-ui;max-width:34rem;'
            'margin:2rem auto;padding:1rem;overflow-wrap:anywhere">'
            '<h1 role="status">' + title + '</h1><p>' + detail + '</p></main></html>')
    return dict(HEADERS), body

class SensitiveFields(dict):
    """Trusted request scope only. This is NOT a secrecy boundary against introspection."""
    def __repr__(self):
        return '<SensitiveFields REDACTED>'
    __str__ = __repr__

class ParsedForm:
    def __init__(self, csrf, values):
        self.csrf, self.values = csrf, values
    def __repr__(self):
        return '<ParsedForm REDACTED>'
    __str__ = __repr__

def decode_form(body, content_type, approved_body_limit):
    """Original trusted host calls only after auth, before Candidate.submit.
    No new capacity choice: require the original host's approved byte limit.
    No body/parse exception details are returned. Never expose this as AI tool.
    """
    try:
        if (type(approved_body_limit) is not int or approved_body_limit <= 0
                or not isinstance(body, bytes) or len(body) > approved_body_limit
                or content_type.lower().replace(' ', '') not in (
                    'application/x-www-form-urlencoded',
                    'application/x-www-form-urlencoded;charset=utf-8')):
            raise ValueError()
        text = body.decode('utf-8', errors='strict')
        if re.search(r'%(?![0-9A-Fa-f]{2})', text):
            raise ValueError()
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True,
                          encoding='utf-8', errors='strict')
        keys = [key for key, value in pairs]
        if len(set(keys)) != len(keys) or set(keys) != set(NAMES) | {'csrf'}:
            raise ValueError()
        fields = dict(pairs)
        csrf = fields.pop('csrf')
        return ParsedForm(csrf, SensitiveFields(fields))
    except Exception:
        raise Unbound('FORM_REJECTED') from None

class Unbound(Exception):
    """Dependency absent; never include a raw cause in an HTTP/tool response."""

class ExistingHost(metaclass=abc.ABCMeta):
    """Adapter to the ORIGINAL authenticated HTTPS host, not new authentication.

    ready() fails unless existing TLS/loopback/routes, request-size/rate/connection
    controls, no sensitive access/error/APM/body logging, and CSRF/session binding
    have been verified. Capacity values come from the host, not this candidate.
    This abstract class grants no permissions and creates no keys or sessions.
    """
    @abc.abstractmethod
    def ready(self):
        raise Unbound()

    @abc.abstractmethod
    def authorize_owner(self, principal):
        """Verify existing authenticated Owner/session server-side, fail closed."""
        raise Unbound()

    @abc.abstractmethod
    def csrf_for(self, principal, request):
        """Existing synchronizer CSRF value; not Gateway token or setup code."""
        raise Unbound()

    @abc.abstractmethod
    def validate_post(self, principal, request, csrf, origin):
        """Exact original HTTPS origin, live auth, session/request-bound CSRF.
        No permanent tokens in URL. Host additionally rejects duplicate form keys,
        unexpected content types, oversize bodies and untrusted forwarded headers.
        """
        raise Unbound()

class ExistingProtectedStore(metaclass=abc.ABCMeta):
    """Required adapter, NOT a second secret/session database.

    Reuse original request lifecycle and Protected Store/SecretRef. Do not bind
    the financial production Store. No plaintext list/get/resolve method exists.
    The original Store has batch writes; the candidate durable receipt adapter joins
    that batch and its once-only receipt in the same managed state transaction.
    Independent sequential writes or a process-local receipt are NOT enough.
    Request records contain metadata only; plaintext must not be in request rows.
    Existing entry updates must use the original reviewed replacement semantics.
    No request expiry may expire/delete a committed SecretRef. Existing authorized
    update/delete remain original Store functions, not silently disabled here.
    """
    @abc.abstractmethod
    def ready(self):
        raise Unbound()

    @abc.abstractmethod
    def create_request(self, principal, purpose, version, ttl_seconds, names, allowed_hosts):
        """Original lifecycle issues non-bearer random question ID, no values.
        It atomically binds current owner/session, purpose/version and 600s TTL.
        An ID is locator only: knowledge of it must never grant authorization.
        """
        raise Unbound()

    @abc.abstractmethod
    def metadata(self, question_id):
        """Request type only; absent->None. Never return payload/store values."""
        raise Unbound()

    @abc.abstractmethod
    def submit_once(self, request, principal, values, allowed_hosts):
        """Inside ONE original durable transaction: recheck live authority,
        exact subject/session/purpose/version, server clock < expires_at, pending
        state, and allowed_hosts==(); commit all 3 protected values + stable refs
        and mark STORED exactly once. Never save plaintext in request metadata.
        Concurrent/replayed calls cannot overwrite. Expired/cancelled reject.
        Unknown commit/refresh outcome is queryable and must NOT be blindly retried.
        If store committed but runtime refresh failed, preserve STORED; reconcile
        original runtime refresh separately, never authorize another submission.
        Return Outcome with fixed status only; no exception/payload echoes.
        """
        raise Unbound()

    @abc.abstractmethod
    def status(self, request, principal):
        """Recheck live auth and binding. Return fixed status, never secret values.
        Reconcile an UNKNOWN against the original attempt, not a new write.
        """
        raise Unbound()

class ExistingBrowserInjection(metaclass=abc.ABCMeta):
    """Original trusted consumer only. No plaintext goes through agent/model.
    This interface is not evidence that any browser integration exists.
    """
    @abc.abstractmethod
    def capability(self):
        """Return proven support, UNKNOWN, or BROWSER_SECRET_INJECTION_UNSUPPORTED.
        Must prove exact host enforcement, no DOM/screenshot/tool/model leakage,
        auth-bound consumer, redirect checks and logs. Initial allowedHosts=[]
        prohibits egress even when the consumer is supported.
        """
        raise Unbound()

class Candidate:
    def __init__(self, host, store, mount_path=''):
        # Existing host mount only, never an origin or user-controlled URL.
        if not isinstance(mount_path, str) or not re.match(r'\A(?:/[A-Za-z0-9_-]+)*\Z', mount_path):
            raise Unbound('INVALID_EXISTING_MOUNT')
        self.host, self.store, self.mount_path = host, store, mount_path

    def _authorized(self, principal):
        return (isinstance(principal, Principal) and bool(principal.subject)
                and bool(principal.session_binding)
                and self.host.ready() is True and self.store.ready() is True
                and self.host.authorize_owner(principal) is True)

    @staticmethod
    def _bound(request, principal, expected_question_id=None):
        return (isinstance(request, Request)
                and (expected_question_id is None or request.question_id == expected_question_id)
                and request.subject == principal.subject
                and request.session_binding == principal.session_binding
                and request.purpose == PURPOSE and request.version == VERSION
                and isinstance(request.question_id, str)
                and QUESTION_ID.match(request.question_id) is not None)

    def create(self, principal):
        try:
            return self._create(principal)
        except Exception:
            raise Unbound('REQUEST_CREATION_UNCONFIRMED_QUERY_ORIGINAL') from None

    def _create(self, principal):
        if not self._authorized(principal):
            raise Unbound('HOST_OR_STORE_OR_AUTH_NOT_READY')
        request = self.store.create_request(principal, PURPOSE, VERSION,
                                            TTL_SECONDS, NAMES, ())
        if not self._bound(request, principal):
            raise Unbound('REQUEST_BINDING_INVALID')
        return request

    def page(self, principal, question_id):
        try:
            return self._page(principal, question_id)
        except Exception:
            raise Unbound('PAGE_UNAVAILABLE') from None

    def _page(self, principal, question_id):
        """Authenticated metadata-only GET. Never consumes the request."""
        if not self._authorized(principal) or not QUESTION_ID.match(question_id):
            raise Unbound('FORBIDDEN')
        request = self.store.metadata(question_id)
        if not self._bound(request, principal, question_id):
            raise Unbound('FORBIDDEN')
        state = self.store.status(request, principal)
        if state.status != 'PENDING':
            return status_page(state)
        csrf = html.escape(self.host.csrf_for(principal, request), quote=True)
        fields = ''.join(
            '<label>{label}<input type="password" name="{name}" required '
            'autocomplete="off" autocapitalize="none" spellcheck="false"></label>'
            .format(label=label, name=name)
            for name, label in zip(NAMES, ('验收地址', '验收用户名', '验收密码')))
        body = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>社区后台验收 · 安全输入</title>
<style>body{{font:16px system-ui;max-width:34rem;margin:2rem auto;padding:0 1rem 8rem;overflow-wrap:anywhere}}label{{display:block;margin:1rem 0}}input,button{{display:block;box-sizing:border-box;width:100%;padding:.85rem;font:inherit;min-height:48px}}small{{display:block;color:#555}}</style>
<h1>社区后台验收账号</h1><p>仅在此页面填写，不要在聊天中发送账号或密码。</p>
<small>用途：community-admin-acceptance · 版本：community-acceptance-v1</small>
<p>链接自创建起 10 分钟有效，只能成功提交一次。提交后凭据保存在原受保护存储，直至更新或删除。</p>
<form method="post" action="{mount}/ask/{qid}" autocomplete="off">
<input type="hidden" name="csrf" value="{csrf}">{fields}
<button type="submit">安全提交一次</button></form>
<p>提交结果不明时查询原请求；不要重复提交。初始外发目标为空，未授权任何外发。</p></html>'''.format(mount=self.mount_path, qid=question_id, csrf=csrf, fields=fields)
        return dict(HEADERS), body

    def submit(self, principal, question_id, method, origin, csrf, values):
        """Trusted host invokes this directly; NOT an agent/model tool.
        Never log args, exceptions, locals or request bodies. Do not add retry.
        Input values necessarily exist transiently in Owner browser and trusted
        server memory; no promise of cryptographic memory erasure is made.
        """
        try:
            if method != 'POST' or not self._authorized(principal):
                return Outcome('FORBIDDEN')
            if not isinstance(question_id, str) or not QUESTION_ID.match(question_id):
                return Outcome('INVALID')
            request = self.store.metadata(question_id)
            if not self._bound(request, principal, question_id):
                return Outcome('FORBIDDEN')
            if self.host.validate_post(principal, request, csrf, origin) is not True:
                return Outcome('FORBIDDEN')
            if (not isinstance(values, dict) or set(values) != set(NAMES)
                    or any(not isinstance(v, str) or not v for v in values.values())):
                return Outcome('INVALID')
            # No normalization: preserve supplied credential bytes at host boundary.
            result = self.store.submit_once(request, principal, values, ())
            return result if isinstance(result, Outcome) and result.status in STATUSES else Outcome('UNKNOWN')
        except Exception:
            # Raw errors might contain supplied credentials; never return/log them.
            # UNKNOWN means query original receipt; it does not imply not executed.
            return Outcome('UNKNOWN')

    def result(self, principal, question_id):
        try:
            if not self._authorized(principal) or not QUESTION_ID.match(question_id):
                return Outcome('FORBIDDEN')
            request = self.store.metadata(question_id)
            if not self._bound(request, principal, question_id):
                return Outcome('FORBIDDEN')
            result = self.store.status(request, principal)
            allowed = STATUSES | frozenset(('PENDING',))
            return result if isinstance(result, Outcome) and result.status in allowed else Outcome('UNKNOWN')
        except Exception:
            return Outcome('UNKNOWN')
