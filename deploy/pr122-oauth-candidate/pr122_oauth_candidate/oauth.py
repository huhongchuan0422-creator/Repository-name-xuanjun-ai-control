import argparse
import json
import os
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .douyin import DOUYIN_USER_INFO_URL, TEST_ACCOUNT_WHITELIST_SCOPE, DouyinOAuthStateStore, DouyinOpenApiClient, DouyinTokenLifecycleStore, parse_token_response, sanitize_user_info_response
from .tiktok import MINIMUM_READONLY_SCOPES as TIKTOK_MINIMUM_READONLY_SCOPES, TIKTOK_USER_INFO_URL, TikTokOAuthStateStore, TikTokOpenApiClient, TikTokTokenLifecycleStore, build_authorization_url as build_tiktok_authorization_url, fingerprint as tiktok_fingerprint, parse_token_response as parse_tiktok_token_response, sanitize_user_info_response as sanitize_tiktok_user_info_response
from .core import DOUYIN_ACCESS_TOKEN_REF, DOUYIN_CLIENT_KEY_REF, DOUYIN_CLIENT_SECRET_REF, DOUYIN_REFRESH_TOKEN_REF, TIKTOK_ACCESS_TOKEN_REF, TIKTOK_CLIENT_KEY_REF, TIKTOK_CLIENT_SECRET_REF, TIKTOK_REFRESH_TOKEN_REF, secure_headers


DOUYIN_REDIRECT_PATH = '/integrations/douyin/oauth/callback'

TIKTOK_REDIRECT_PATH = '/integrations/tiktok/oauth/callback'

TIKTOK_URL_PROPERTY_VERIFICATION_FILENAME = 'tiktokseZDn0fzmn8v7H8YWGlgzuT7PvLBQavc.txt'

TIKTOK_URL_PROPERTY_VERIFICATION_BODY = 'tiktok-developers-site-verification=ZDn0fzmn8v7H8YWGlgzuT7PvLBQavc\n'

TIKTOK_URL_PROPERTY_VERIFICATION_FILES = {TIKTOK_URL_PROPERTY_VERIFICATION_FILENAME: TIKTOK_URL_PROPERTY_VERIFICATION_BODY, 'tiktokaijLJ4RVKBQcCitJDTZ6LJsjOJ52cwBn.txt': 'tiktok-developers-site-verification=tiktokaijLJ4RVKBQcCitJDTZ6LJsjOJ52cwBn\n'}

def _html_escape(value):
    import html
    return html.escape(str(value), quote=True)

def render_douyin_page(service, session_id, message=None):
    session = service.sessions.get(session_id)
    if not session:
        return (HTTPStatus.NOT_FOUND, 'SESSION_NOT_FOUND')
    if service._require_session(session_id).__class__ is dict:
        return (HTTPStatus.GONE, 'SESSION_EXPIRED')
    if 'douyin' not in session.required_credential_types:
        return (HTTPStatus.FORBIDDEN, 'FORM_NOT_ALLOWED')
    if 'douyin' in getattr(session, 'used_forms', {}):
        return (HTTPStatus.GONE, 'FORM_ALREADY_USED')
    headers = secure_headers()
    status_line = f'<p class="status">{_html_escape(message)}</p>' if message else ''
    redirect_uri = _html_escape((session.portal_origin or '').rstrip('/') + DOUYIN_REDIRECT_PATH)
    body = f'<!doctype html>\n<html lang="zh-CN">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Secure Secrets Portal</title>\n  <style>\n    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f7f9; color: #17202a; }}\n    main {{ max-width: 720px; margin: 48px auto; padding: 0 20px; }}\n    section {{ background: #fff; border: 1px solid #d9dee7; border-radius: 8px; padding: 24px; }}\n    h1 {{ font-size: 24px; margin: 0 0 16px; }}\n    h2 {{ font-size: 19px; margin: 18px 0 8px; }}\n    p {{ line-height: 1.55; }}\n    label {{ display: block; font-weight: 600; margin-top: 16px; }}\n    input {{ width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px 12px; border: 1px solid #aeb8c6; border-radius: 6px; font-size: 15px; }}\n    button {{ margin-top: 20px; padding: 11px 18px; border: 0; border-radius: 6px; background: #1769e0; color: #fff; font-weight: 700; cursor: pointer; }}\n    .notice {{ background: #eef5ff; border-left: 4px solid #1769e0; padding: 12px 14px; }}\n    .danger {{ color: #8a1f11; font-weight: 700; }}\n    .status {{ color: #135f2c; font-weight: 700; }}\n    code {{ word-break: break-all; }}\n  </style>\n</head>\n<body>\n<main>\n  <section>\n    <h1>Secure Secrets Portal</h1>\n    <div class="notice">安全提交<br>请勿通过飞书、OpenClaw聊天、企业微信、命令行、截图或工程文档发送 Client Secret。</div>\n    {status_line}\n    <h2>抖音开放平台 OAuth 只读接入</h2>\n    <p>用途：仅用于 Owner 抖音账号授权、Token 安全保存、user_info 只读验证。</p>\n    <p>回调地址：<code>{redirect_uri}</code></p>\n    <p class="danger">不会用于：视频上传、视频创建、公开发布、私信、评论、点赞、关注、客户数据采集或交易执行。</p>\n    <form method="post" action="/submit/douyin" autocomplete="off">\n      <input type="hidden" name="session_id" value="{_html_escape(session.submission_id)}">\n      <input type="hidden" name="csrf_token" value="{_html_escape(session.nonce)}">\n      <input type="hidden" name="configured_redirect_uri" value="{redirect_uri}">\n      <label>Application Name（可选）\n        <input name="application_name" autocomplete="off">\n      </label>\n      <label>Client Key\n        <input name="client_key" type="password" required autocomplete="off">\n      </label>\n      <label>Client Secret\n        <input name="client_secret" type="password" required autocomplete="off">\n      </label>\n      <button type="submit">安全提交</button>\n    </form>\n  </section>\n</main>\n</body>\n</html>'
    return (HTTPStatus.OK, headers, body)

def render_tiktok_page(service, session_id, message=None):
    session = service.sessions.get(session_id)
    if not session:
        return (HTTPStatus.NOT_FOUND, 'SESSION_NOT_FOUND')
    if service._require_session(session_id).__class__ is dict:
        return (HTTPStatus.GONE, 'SESSION_EXPIRED')
    if 'tiktok' not in session.required_credential_types:
        return (HTTPStatus.FORBIDDEN, 'FORM_NOT_ALLOWED')
    if 'tiktok' in getattr(session, 'used_forms', {}):
        return (HTTPStatus.GONE, 'FORM_ALREADY_USED')
    headers = secure_headers()
    status_line = f'<p class="status">{_html_escape(message)}</p>' if message else ''
    redirect_uri = _html_escape((session.portal_origin or '').rstrip('/') + TIKTOK_REDIRECT_PATH)
    body = f'<!doctype html>\n<html lang="zh-CN">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Secure Secrets Portal</title>\n  <style>\n    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f7f9; color: #17202a; }}\n    main {{ max-width: 720px; margin: 48px auto; padding: 0 20px; }}\n    section {{ background: #fff; border: 1px solid #d9dee7; border-radius: 8px; padding: 24px; }}\n    h1 {{ font-size: 24px; margin: 0 0 16px; }}\n    h2 {{ font-size: 19px; margin: 18px 0 8px; }}\n    p {{ line-height: 1.55; }}\n    label {{ display: block; font-weight: 600; margin-top: 16px; }}\n    input {{ width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px 12px; border: 1px solid #aeb8c6; border-radius: 6px; font-size: 15px; }}\n    button {{ margin-top: 20px; padding: 11px 18px; border: 0; border-radius: 6px; background: #1769e0; color: #fff; font-weight: 700; cursor: pointer; }}\n    .notice {{ background: #eef5ff; border-left: 4px solid #1769e0; padding: 12px 14px; }}\n    .danger {{ color: #8a1f11; font-weight: 700; }}\n    .status {{ color: #135f2c; font-weight: 700; }}\n    code {{ word-break: break-all; }}\n  </style>\n</head>\n<body>\n<main>\n  <section>\n    <h1>Secure Secrets Portal</h1>\n    <div class="notice">安全提交<br>请勿通过飞书、OpenClaw聊天、企业微信、命令行、截图或工程文档发送 Client Secret。</div>\n    {status_line}\n    <h2>TikTok Login Kit Sandbox</h2>\n    <p>用途：仅用于 Sandbox Login Kit 授权、Token 安全保存、user.info.basic 只读验证。</p>\n    <p>Sandbox：Xuanjun LoginKit Demo</p>\n    <p>回调地址：<code>{redirect_uri}</code></p>\n    <p class="danger">不会用于：Content Posting API、视频上传、Direct Post、公开发布、私信、评论或客户数据采集。</p>\n    <form method="post" action="/submit/tiktok" autocomplete="off">\n      <input type="hidden" name="session_id" value="{_html_escape(session.submission_id)}">\n      <input type="hidden" name="csrf_token" value="{_html_escape(session.nonce)}">\n      <input type="hidden" name="configured_redirect_uri" value="{redirect_uri}">\n      <input type="hidden" name="sandbox_name" value="Xuanjun LoginKit Demo">\n      <label>Application Name\n        <input name="application_name" value="XuanjunAIContentManagementPlatform" autocomplete="off">\n      </label>\n      <label>Client Key\n        <input name="client_key" type="password" required autocomplete="off">\n      </label>\n      <label>Client Secret\n        <input name="client_secret" type="password" required autocomplete="off">\n      </label>\n      <button type="submit">安全提交</button>\n    </form>\n  </section>\n</main>\n</body>\n</html>'
    return (HTTPStatus.OK, headers, body)

def _record_douyin_callback_audit(service, payload):
    event = {'operation': 'DOUYIN_OAUTH_CALLBACK', 'provider': 'douyin', 'result': payload.get('status', 'REJECTED'), 'sanitized_error_code': payload.get('sanitized_error_code', ''), 'oauth_callback': payload.get('oauth_callback', ''), 'access_token_exchange': payload.get('access_token_exchange', ''), 'token_stored_securely': payload.get('token_stored_securely', ''), 'user_info_api': payload.get('user_info_api', ''), 'secret_value_exposed': False}
    try:
        service.operations_store.record_audit(event)
    except Exception:
        pass

def _finish_douyin_callback(service, payload):
    _record_douyin_callback_audit(service, payload)
    return payload

def handle_douyin_oauth_callback(service, origin, query):
    error = (query.get('error') or [''])[0]
    if error:
        return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'AUTHORIZATION_DENIED'})
    code = (query.get('code') or [''])[0]
    state = (query.get('state') or [''])[0]
    if not code or not state:
        return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'CALLBACK_ARGUMENT_MISSING'})
    consumed = DouyinOAuthStateStore(DEFAULT_STATE_ROOT / 'douyin-oauth-state').consume_state(state)
    if consumed.get('status') != 'PASS':
        return _finish_douyin_callback(service, consumed)
    expected_redirect_uri = consumed['state'].get('redirect_uri')
    actual_redirect_uri = origin.rstrip('/') + DOUYIN_REDIRECT_PATH
    if expected_redirect_uri != actual_redirect_uri:
        return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'REDIRECT_URI_MISMATCH'})
    scopes = consumed['state'].get('scopes') or []
    if scopes == [TEST_ACCOUNT_WHITELIST_SCOPE]:
        return _finish_douyin_callback(service, {'status': 'PASS', 'oauth_callback': 'PASS', 'test_account_whitelist_authorization': 'PASS', 'access_token_exchange': 'SKIPPED_FOR_TRIAL_WHITELIST', 'token_stored_securely': 'SKIPPED_FOR_TRIAL_WHITELIST', 'user_info_api': 'SKIPPED_FOR_TRIAL_WHITELIST', 'secret_value_exposed': False})
    client_key = service.operations_store.read_secret(DOUYIN_CLIENT_KEY_REF)
    client_secret = service.operations_store.read_secret(DOUYIN_CLIENT_SECRET_REF)
    if not client_key or not client_secret:
        return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'SECRETREF_MISSING'})
    client = DouyinOpenApiClient(timeout_seconds=10)
    try:
        token_payload = client.exchange_access_token(client_key=client_key, client_secret=client_secret, code=code)
    except Exception:
        return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'AUTH_CODE_EXCHANGE_FAILED'})
    parsed = parse_token_response(token_payload, client_key=client_key)
    if parsed.get('status') != 'PASS':
        return _finish_douyin_callback(service, parsed)
    access_token = parsed['access_token']
    refresh_token = parsed['refresh_token']
    open_id = parsed['open_id']
    lifecycle = parsed['lifecycle']
    for ref, value, purpose in ((DOUYIN_ACCESS_TOKEN_REF, access_token, 'douyin access token for readonly user_info canary'), (DOUYIN_REFRESH_TOKEN_REF, refresh_token, 'douyin refresh token for lifecycle management')):
        result = service.operations_store.store_secret(ref, value, 'douyin', 'douyin_open_api_oauth', purpose, actor='OWNER-HHC', metadata=lifecycle.as_public_dict())
        if result.get('status') != 'CONFIGURED':
            return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'TOKEN_STORAGE_FAILED'})
    DouyinTokenLifecycleStore(DEFAULT_STATE_ROOT / 'douyin-token-state').save(lifecycle)
    try:
        user_info = client.user_info(access_token=access_token, open_id=open_id)
    except Exception:
        return _finish_douyin_callback(service, {'status': 'REJECTED', 'sanitized_error_code': 'USER_INFO_API_FAILED'})
    sanitized_user = sanitize_user_info_response(user_info)
    if sanitized_user.get('status') != 'PASS':
        return _finish_douyin_callback(service, sanitized_user)
    service.operations_store.record_audit({'operation': 'DOUYIN_USER_INFO_CANARY', 'provider': 'douyin', 'endpoint': DOUYIN_USER_INFO_URL, 'origin': origin, 'open_id_masked': sanitized_user['open_id_masked'], 'nickname': sanitized_user.get('nickname', ''), 'result': 'PASS'})
    return _finish_douyin_callback(service, {'status': 'PASS', 'oauth_callback': 'PASS', 'access_token_exchange': 'PASS', 'token_stored_securely': 'PASS', 'user_info_api': 'PASS', 'open_id_masked': sanitized_user['open_id_masked'], 'union_id_masked': sanitized_user['union_id_masked'], 'nickname': sanitized_user.get('nickname', ''), 'secret_value_exposed': False})

def _record_tiktok_audit(service, payload):
    event = {'operation': payload.get('operation', 'TIKTOK_LOGIN_KIT'), 'provider': 'tiktok', 'result': payload.get('status', 'REJECTED'), 'sanitized_error_code': payload.get('sanitized_error_code', ''), 'oauth_callback': payload.get('oauth_callback', ''), 'access_token_exchange': payload.get('access_token_exchange', ''), 'token_stored_securely': payload.get('token_stored_securely', ''), 'user_info_api': payload.get('user_info_api', ''), 'secret_value_exposed': False}
    try:
        service.operations_store.record_audit(event)
    except Exception:
        pass

def _finish_tiktok(service, payload):
    _record_tiktok_audit(service, payload)
    return payload

def _tiktok_existing_binding_payload(token_store):
    existing = token_store.load_status().get('account') or {}
    existing_account = existing.get('account') or {}
    if existing.get('status') != 'CONNECTED' or existing_account.get('status') != 'PASS':
        return None
    return {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'PASS', 'oauth_callback': 'PASS', 'access_token_exchange': 'PASS', 'token_stored_securely': 'PASS', 'account_binding': 'EXISTING', 'user_info_api': 'TEMPORARY_FAILED_EXISTING_BINDING_USED', 'open_id_masked': existing_account.get('open_id_masked', 'MISSING'), 'union_id_masked': existing_account.get('union_id_masked', 'MISSING'), 'display_name': existing_account.get('display_name', ''), 'secret_value_exposed': False}

def handle_tiktok_oauth_start(service, origin):
    client_key = service.operations_store.read_secret(TIKTOK_CLIENT_KEY_REF)
    if not client_key:
        return (None, _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_START', 'status': 'REJECTED', 'sanitized_error_code': 'CLIENT_KEY_SECRETREF_MISSING'}))
    redirect_uri = origin.rstrip('/') + TIKTOK_REDIRECT_PATH
    state = TikTokOAuthStateStore(DEFAULT_STATE_ROOT / 'tiktok-oauth-state').create_state(redirect_uri=redirect_uri, scopes=TIKTOK_MINIMUM_READONLY_SCOPES, client_key_fingerprint=tiktok_fingerprint(client_key))
    url = build_tiktok_authorization_url(client_key=client_key, redirect_uri=redirect_uri, state=state['state'], scopes=TIKTOK_MINIMUM_READONLY_SCOPES)
    _record_tiktok_audit(service, {'operation': 'TIKTOK_OAUTH_START', 'status': 'PASS', 'oauth_callback': 'PENDING', 'secret_value_exposed': False})
    return (url, None)

def handle_tiktok_oauth_callback(service, origin, query):
    error = (query.get('error') or [''])[0]
    if error:
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'AUTHORIZATION_DENIED'})
    code = (query.get('code') or [''])[0]
    state = (query.get('state') or [''])[0]
    if not code or not state:
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'CALLBACK_ARGUMENT_MISSING'})
    consumed = TikTokOAuthStateStore(DEFAULT_STATE_ROOT / 'tiktok-oauth-state').consume_state(state)
    if consumed.get('status') != 'PASS':
        consumed['operation'] = 'TIKTOK_OAUTH_CALLBACK'
        return _finish_tiktok(service, consumed)
    expected_redirect_uri = consumed['state'].get('redirect_uri')
    actual_redirect_uri = origin.rstrip('/') + TIKTOK_REDIRECT_PATH
    if expected_redirect_uri != actual_redirect_uri:
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'REDIRECT_URI_MISMATCH'})
    if consumed['state'].get('scopes') != list(TIKTOK_MINIMUM_READONLY_SCOPES):
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'UNEXPECTED_SCOPE'})
    client_key = service.operations_store.read_secret(TIKTOK_CLIENT_KEY_REF)
    client_secret = service.operations_store.read_secret(TIKTOK_CLIENT_SECRET_REF)
    if not client_key or not client_secret:
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'SECRETREF_MISSING'})
    client = TikTokOpenApiClient(timeout_seconds=10)
    try:
        token_payload = client.exchange_access_token(client_key=client_key, client_secret=client_secret, code=code, redirect_uri=actual_redirect_uri)
    except Exception:
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'AUTH_CODE_EXCHANGE_FAILED'})
    parsed = parse_tiktok_token_response(token_payload, client_key=client_key)
    if parsed.get('status') != 'PASS':
        parsed['operation'] = 'TIKTOK_OAUTH_CALLBACK'
        return _finish_tiktok(service, parsed)
    access_token = parsed['access_token']
    refresh_token = parsed['refresh_token']
    lifecycle = parsed['lifecycle']
    for ref, value, purpose in ((TIKTOK_ACCESS_TOKEN_REF, access_token, 'tiktok sandbox access token for user.info.basic canary'), (TIKTOK_REFRESH_TOKEN_REF, refresh_token, 'tiktok sandbox refresh token for lifecycle management')):
        result = service.operations_store.store_secret(ref, value, 'tiktok', 'tiktok_login_kit_sandbox', purpose, actor='OWNER-HHC', metadata=lifecycle.as_public_dict())
        if result.get('status') != 'CONFIGURED':
            return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'TOKEN_STORAGE_FAILED'})
    token_store = TikTokTokenLifecycleStore(DEFAULT_STATE_ROOT / 'tiktok-token-state')
    token_store.save(lifecycle)
    try:
        user_info = client.user_info(access_token=access_token)
    except Exception:
        fallback = _tiktok_existing_binding_payload(token_store)
        if fallback:
            return _finish_tiktok(service, fallback)
        return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'REJECTED', 'sanitized_error_code': 'USER_INFO_API_FAILED'})
    sanitized_user = sanitize_tiktok_user_info_response(user_info)
    if sanitized_user.get('status') != 'PASS':
        fallback = _tiktok_existing_binding_payload(token_store)
        if fallback:
            fallback['user_info_api'] = 'SANITIZED_FAILED_EXISTING_BINDING_USED'
            return _finish_tiktok(service, fallback)
        sanitized_user['operation'] = 'TIKTOK_OAUTH_CALLBACK'
        return _finish_tiktok(service, sanitized_user)
    token_store.save_account_binding(sanitized_user)
    service.operations_store.record_audit({'operation': 'TIKTOK_USER_INFO_BASIC_CANARY', 'provider': 'tiktok', 'endpoint': TIKTOK_USER_INFO_URL, 'origin': origin, 'open_id_masked': sanitized_user['open_id_masked'], 'display_name': sanitized_user.get('display_name', ''), 'result': 'PASS'})
    return _finish_tiktok(service, {'operation': 'TIKTOK_OAUTH_CALLBACK', 'status': 'PASS', 'oauth_callback': 'PASS', 'access_token_exchange': 'PASS', 'token_stored_securely': 'PASS', 'account_binding': 'PASS', 'user_info_api': 'PASS', 'open_id_masked': sanitized_user['open_id_masked'], 'union_id_masked': sanitized_user['union_id_masked'], 'display_name': sanitized_user.get('display_name', ''), 'secret_value_exposed': False})

def tiktok_connection_status():
    state = TikTokTokenLifecycleStore(DEFAULT_STATE_ROOT / 'tiktok-token-state').load_status()
    account = state.get('account')
    connected = bool(account and account.get('status') == 'CONNECTED')
    return {'status': 'PASS', 'provider': 'tiktok', 'connected': connected, 'scope': 'user.info.basic', 'account': account.get('account') if connected else None, 'token_status': state.get('token', {}).get('status', 'MISSING'), 'secret_value_exposed': False, 'content_posting_api_added': False, 'video_upload': False, 'direct_post': False, 'publication': False, 'comment_write': False, 'private_message_write': False}

def tiktok_callback_redirect_location(payload):
    result = 'pass' if payload.get('status') == 'PASS' else 'check_status'
    return '/integrations/tiktok?oauth_callback=' + urllib.parse.quote(result)

def configure_state_root(root):
    """Call once before serving. No default production root is permitted."""
    global DEFAULT_STATE_ROOT, TIKTOK_APP_ICON_PATH
    DEFAULT_STATE_ROOT = Path(root)
    TIKTOK_APP_ICON_PATH = DEFAULT_STATE_ROOT / 'public' / 'xuanjun-tiktok-icon.png'

