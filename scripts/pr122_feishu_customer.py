"""Candidate Feishu customer wiring on PR122's existing identity/evidence/outbox.

No listener, credentials, schema bootstrap, network call or production activation
at import. The existing App accepts the Providers subclass through make_app().
The original ops/installer are deliberately unchanged; integration needs review.
"""
import base64
import copy
import hashlib
import json
import re
import secrets

from scripts.pr122_customer_core import Denied, Unavailable, canonical, safe_text
from scripts.pr122_customer_evidence import append, authorized_records
from scripts.pr122_customer_profile import FULL
from scripts.pr122_customer_providers import Providers, VerifiedEvent, local_ai

SCOPE_KEY = 'feishu_customer_app_scope_v1'
PURPOSE = 'PLATFORM_CUSTOMER_SUPPORT'
RESERVED = {'owner_gateway', 'development', 'authentication_notifications'}


def _identity(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) is not None


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Denied('FEISHU_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def reject(value):
        raise Denied('FEISHU_NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


class CustomerFeishuProviders(Providers):
    """One dedicated custom app/tenant; reserved bots are never customer bots.

    scope comes from protected server configuration, never request JSON. Unknown
    app ownership is not admitted. This is not a multi-tenant store-app adapter.
    """
    def __init__(self, config, scope, **kwargs):
        required = {'schema', 'purpose', 'app_id', 'tenant_key',
                    'allowed_sender_tenants', 'reserved_app_ids'}
        if type(scope) is not dict or set(scope) != required:
            raise Unavailable('FEISHU_CUSTOMER_SCOPE_REQUIRED')
        reserved = scope['reserved_app_ids']
        tenants = scope['allowed_sender_tenants']
        if (type(scope['schema']) is not int or scope['schema'] != 1
                or scope['purpose'] != PURPOSE
                or not _identity(scope['app_id']) or not _identity(scope['tenant_key'])
                or type(reserved) is not dict or set(reserved) != RESERVED
                or not all(_identity(x) for x in reserved.values())
                or scope['app_id'] in reserved.values()
                or type(tenants) is not list or not 1 <= len(tenants) <= 100
                or not all(_identity(x) for x in tenants) or len(set(tenants)) != len(tenants)):
            raise Unavailable('FEISHU_CUSTOMER_SCOPE_REQUIRED')
        c = config.get('feishu') if type(config) is dict else None
        if type(c) is not dict or c.get('app_id') != scope['app_id']:
            raise Denied('FEISHU_CUSTOMER_APP_BINDING')
        self._scope = copy.deepcopy(scope)
        self._scope['allowed_sender_tenants'].sort()
        self.scope_digest = hashlib.sha256(canonical(self._scope)).hexdigest()
        super().__init__(copy.deepcopy(config), **kwargs)

    def require_config(self):
        if self.config.get('feishu', {}).get('app_id') != self._scope['app_id']:
            raise Denied('FEISHU_CUSTOMER_APP_BINDING')
        return self._scope

    def feishu(self, headers, raw):
        scope = self.require_config()
        if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
            raise Denied('FEISHU_EVENT_SIZE')
        # Reuse original signature, freshness, AES-CBC, token and p2p checks.
        value = super().feishu(headers, raw)
        outer = _strict_json(raw)
        ciphertext = base64.b64decode(outer['encrypt'], validate=True)
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        key = hashlib.sha256(self.config['feishu']['encrypt_key'].encode()).digest()
        decryptor = Cipher(algorithms.AES(key), modes.CBC(ciphertext[:16])).decryptor()
        padded = decryptor.update(ciphertext[16:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        document = _strict_json(unpadder.update(padded) + unpadder.finalize())
        if type(value) is dict:
            if (type(document.get('challenge')) is not str
                    or not 1 <= len(document['challenge']) <= 512):
                raise Denied('FEISHU_CHALLENGE')
            return value
        header = document['header']
        event = document['event']
        sender = event['sender']
        message = event['message']
        content = _strict_json(message['content'])
        mid = message.get('message_id')
        if (document.get('schema') != '2.0'
                or header.get('tenant_key') != scope['tenant_key']
                or sender.get('tenant_key') not in scope['allowed_sender_tenants']
                or not _identity(value[1]) or not _identity(mid)
                or not _identity(header.get('event_id'))
                or type(content) is not dict or set(content) != {'text'}
                or content['text'] != value[2]):
            raise Denied('FEISHU_CUSTOMER_EVENT_SCOPE')
        safe_text(content['text'], 4000)
        # Feishu documents that the same message can arrive with different
        # event_id values. Scope message_id by app+tenant, within original events.
        stable = 'fs_' + hashlib.sha256(canonical([
            scope['app_id'], scope['tenant_key'], mid])).hexdigest()[:60]
        return VerifiedEvent(stable, value[1], value[2], value.occurred_at)

    def send(self, channel, subject, text, event_id):
        if channel == 'FEISHU':
            self.require_config()
            if not _identity(subject) or not _identity(event_id):
                raise Denied('FEISHU_CUSTOMER_SEND_SCOPE')
        return super().send(channel, subject, text, event_id)


def admit_scope(center, providers, *, deployment_profile):
    """Reviewed preparation hook, not a public API or an automatic migration.

    New scope may only pin a DB with no historical Feishu objects. Old/unknown
    bindings require explicit migration evidence and are never silently adopted.
    Uses original settings/audit tables, not a second customer registry.
    """
    if deployment_profile != FULL:
        raise Denied('FULL_CUSTOMER_PROFILE_REQUIRED')
    providers.require_config()
    with center.tx():
        old = center.db.execute('SELECT v FROM settings WHERE k=?', (SCOPE_KEY,)).fetchone()
        if old:
            if old[0] != providers.scope_digest:
                raise Denied('FEISHU_CUSTOMER_SCOPE_MIGRATION_REQUIRED')
            return {'state': 'SCOPE_PIN_REUSED'}
        for table in ('links', 'events', 'messages'):
            if center.db.execute("SELECT 1 FROM " + table + " WHERE channel='FEISHU' LIMIT 1").fetchone():
                raise Denied('FEISHU_EXISTING_HISTORY_REQUIRES_MAPPING')
        center.db.execute('INSERT INTO settings VALUES(?,?)', (SCOPE_KEY, providers.scope_digest))
        center.audit('', '', 'FEISHU_CUSTOMER_SCOPE_ADMITTED', providers.scope_digest)
    return {'state': 'SCOPE_PINNED_NOT_CHANNEL_ACCEPTED'}


def require_scope(center, providers):
    providers.require_config()
    row = center.db.execute('SELECT v FROM settings WHERE k=?', (SCOPE_KEY,)).fetchone()
    if not row or row[0] != providers.scope_digest:
        raise Denied('FEISHU_CUSTOMER_SCOPE_NOT_ADMITTED')


def make_app(factory, providers, origin, assets, *, deployment_profile, **kwargs):
    """Wire the original HTTP routes without changing login-only or other bots."""
    if deployment_profile != FULL:
        raise Denied('FULL_CUSTOMER_PROFILE_REQUIRED')
    from scripts.pr122_customer_http import App
    def scoped_factory():
        center = factory()
        try:
            require_scope(center, providers)
            return center
        except BaseException:
            center.db.close()
            raise
    return App(scoped_factory, providers, origin, assets,
               deployment_profile=deployment_profile, **kwargs)


def prepare_next_reply(center, providers, *, deployment_profile, rpc=local_ai):
    """One durable AI claim on original ai_jobs; queue via original messages.

    Webhook never calls an LLM. A reviewed worker invokes this bounded step and
    the original drain_message. UNKNOWN is durable and never automatically retried.
    """
    if deployment_profile != FULL:
        raise Denied('FULL_CUSTOMER_PROFILE_REQUIRED')
    require_scope(center, providers)
    config = providers.config.get('web_ai')
    if not config or config.get('provider') != 'openai' or not config.get('model_key'):
        return {'state': 'PENDING_PROVIDER'}
    with center.tx():
        source = center.db.execute("""SELECT m.* FROM messages m
          LEFT JOIN ai_jobs a ON a.message_id=m.id
          WHERE m.channel='FEISHU' AND m.status='ARCHIVED' AND a.message_id IS NULL
          ORDER BY m.created,m.id LIMIT 1""").fetchone()
        if not source:
            return {'state': 'IDLE'}
        uid, pid, mid = source['user_id'], source['project'], source['id']
        project, records, _ = authorized_records(center, uid, pid)
        record = next((r['evidence'] for r in records if r['evidence']['message_id'] == mid), None)
        if not record or not re.fullmatch(r'fs_[0-9a-f]{60}', record.get('external_event_id') or ''):
            raise Denied('FEISHU_VERIFIED_SOURCE_REQUIRED')
        link = center.db.execute("""SELECT subject_idx,payload FROM links
          WHERE user_id=? AND project=? AND channel='FEISHU' AND active=1""", (uid, pid)).fetchall()
        if len(link) != 1:
            raise Denied('FEISHU_UNAMBIGUOUS_LINK_REQUIRED')
        link_snapshot = tuple(link[0])
        center.db.execute("INSERT INTO ai_jobs VALUES(?,'UNKNOWN',NULL)", (mid,))
        center.audit(pid, uid, 'FEISHU_AI_ATTEMPT_UNKNOWN', mid)
        context = {'message_id': mid, 'user_id': uid, 'project_id': pid,
                   'tenant_id': project['tenant'], 'customer_id': project['customer'],
                   'body': center.decrypt(source['payload'], mid).decode()}
    try:
        text = safe_text(rpc(config, context), 4000)
        with center.tx():
            require_scope(center, providers)
            project_now, _, _ = authorized_records(center, uid, pid)
            if project_now['tenant'] != context['tenant_id'] or project_now['customer'] != context['customer_id']:
                raise Denied('FEISHU_AI_CONTEXT_CHANGED')
            current = center.db.execute("""SELECT subject_idx,payload FROM links
              WHERE user_id=? AND project=? AND channel='FEISHU' AND active=1""", (uid, pid)).fetchall()
            if len(current) != 1 or tuple(current[0]) != link_snapshot:
                raise Denied('FEISHU_LINK_CHANGED_DURING_AI')
            job = center.db.execute('SELECT state FROM ai_jobs WHERE message_id=?', (mid,)).fetchone()
            if not job or job[0] != 'UNKNOWN':
                raise Denied('FEISHU_AI_CLAIM_CHANGED')
            # WEB_AI is the existing AI provenance channel; FEISHU is a separate
            # outbound delivery record linked to it in the same evidence chain.
            rid, outbound = 'm_' + secrets.token_hex(16), 'm_' + secrets.token_hex(16)
            for ident, channel, status, related in (
                    (rid, 'WEB_AI', 'ARCHIVED', mid),
                    (outbound, 'FEISHU', 'PENDING', rid)):
                center.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,NULL,?)',
                    (ident, pid, uid, channel, center.encrypt(text.encode(), ident), status, center.now()))
                center.audit(pid, uid, 'AI_REPLY_ARCHIVED' if channel == 'WEB_AI' else 'OUTBOUND_PENDING', ident)
                append(center, ident, related_message_id=related)
            center.db.execute("UPDATE ai_jobs SET state='ANSWERED',result_id=? WHERE message_id=?", (rid, mid))
        return {'state': 'ANSWERED', 'result_id': rid, 'outbound_id': outbound,
                'delivery_status': 'PENDING'}
    except Exception:
        return {'state': 'UNKNOWN'}
