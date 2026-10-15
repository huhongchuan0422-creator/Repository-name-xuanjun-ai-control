#!/usr/bin/env python3
"""Build an OFFLINE OAuth library candidate from pinned Tokyo source.

No installer, service start, credential import or production acceptance implied.
Only the source dependency boundary is changed; independent review is required.
"""
import argparse
import ast
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath

SOURCE_SHA = '10b9c11fb8a6e07d9edab449faf9c72f6bb36e65ced79d7d65fbf1b69c28bd23'
ENTRY_SHA = '528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006'


def source_archive(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError('SOURCE_HASH_MISMATCH')
    result = {}
    with tarfile.open(path) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or '..' in name.parts
                    or name.suffix != '.py' or member.size > 2_000_000
                    or member.name in result):
                raise ValueError('UNSAFE_SOURCE_MEMBER')
            result[member.name] = archive.extractfile(member).read().decode('utf-8')
    if hashlib.sha256(result['scripts/secure_secrets_portal_server.py'].encode()).hexdigest() != ENTRY_SHA:
        raise ValueError('ENTRY_HASH_MISMATCH')
    return result


def declarations(text):
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node
    return result


def closure(nodes, names):
    selected = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in selected or name not in nodes:
            continue
        selected.add(name)
        pending.extend(n.id for n in ast.walk(nodes[name])
                       if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load))
    unique = {id(nodes[n]): nodes[n] for n in selected}
    return '\n\n'.join(ast.unparse(n) for n in sorted(unique.values(), key=lambda n: n.lineno))


CORE_IMPORTS = '''import fcntl, hashlib, html, json, os, secrets, tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
'''


def build(source, destination):
    # Fail instead of overwriting any earlier candidate or receipt.
    destination.mkdir(mode=0o700)
    pkg = destination / 'pr122_oauth_candidate'
    pkg.mkdir(mode=0o700)
    (pkg / '__init__.py').write_text('"""Offline candidate, no production entry point."""\n')
    portal = declarations(source['ai_service/secure_secrets_portal.py'])
    intake = declarations(source['trading_execution/secure_credential_intake.py'])
    # Reuse the original passive session record; exclude all trading services.
    portal['CredentialSubmissionSession'] = intake['CredentialSubmissionSession']
    service = portal['SecureSecretsPortalService']
    store_init = next(n for n in portal['OperationsSecretRefStore'].body
                      if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    store_init.args.defaults = []
    store_init.body[0] = ast.parse('self.root = Path(root)').body[0]
    keep = {'create_session', 'submit_douyin', 'submit_tiktok', '_require_session',
            '_validate_submit', '_validate_submit_session', '_sanitized_session', '_status_only'}
    service.body = [n for n in service.body if isinstance(n, ast.FunctionDef) and n.name in keep]
    init = ast.parse('''def __init__(self, state_root, operations_root):
    self.operations_store = OperationsSecretRefStore(operations_root)
    self.sessions = FileBackedSubmissionSessionRepository(Path(state_root) / 'sessions')
    self.ttl_seconds = 1800
    self.max_attempts_per_form = 3
''').body[0]
    service.body.insert(0, init)
    # Scope restriction applies to direct library calls too, not only HTTP.
    method = next(n for n in service.body if n.name == 'create_session')
    method.body[0:0] = ast.parse('''if not allowed_forms or not set(allowed_forms) <= {'douyin', 'tiktok'}:
    raise ValueError('OAUTH_FORMS_ONLY')
''').body
    # Former unrestricted defaults are unreachable; remove their declarations.
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tuple':
            node.args = [ast.Name(id='allowed_forms', ctx=ast.Load())]
    ast.fix_missing_locations(service)
    core_seeds = {
        'CredentialSubmissionSession', 'SecureSecretsPortalService', 'OperationsSecretRefStore',
        'FileBackedSubmissionSessionRepository', 'secure_headers'}
    core_seeds.update(n for n in portal if n.startswith(('TIKTOK_', 'DOUYIN_')) and n.endswith('_REF'))
    core = CORE_IMPORTS + '\nSTATUS_PENDING = "PENDING"\n' + closure(portal, core_seeds)
    (pkg / 'core.py').write_text(core + '\n')
    for provider in ('douyin', 'tiktok'):
        (pkg / (provider + '.py')).write_text(source[provider + '/open_api_foundation.py'])
    entry = source['scripts/secure_secrets_portal_server.py']
    nodes = declarations(entry)
    selected = closure(nodes, {'render_douyin_page', 'render_tiktok_page',
        'handle_douyin_oauth_callback', 'handle_tiktok_oauth_start',
        'handle_tiktok_oauth_callback', 'tiktok_connection_status',
        'tiktok_callback_redirect_location', 'TIKTOK_URL_PROPERTY_VERIFICATION_FILES'})
    imports = []
    for node in ast.parse(entry).body:
        if isinstance(node, ast.Import):
            imports.append(ast.unparse(node))
        elif isinstance(node, ast.ImportFrom):
            if node.module in ('http', 'http.server', 'pathlib'):
                imports.append(ast.unparse(node))
            elif node.module in ('douyin.open_api_foundation', 'tiktok.open_api_foundation'):
                node.module = node.module.split('.')[0]
                node.level = 1
                imports.append(ast.unparse(node))
    # Only actually defined core constants are imported, not unrelated defaults.
    names = declarations(core)
    used = {n.id for n in ast.walk(ast.parse(selected)) if isinstance(n, ast.Name)}
    names_to_import = sorted(used & names.keys())
    helpers = '\n'.join(imports) + '\nfrom .core import ' + ', '.join(names_to_import) + '\n' + selected
    helpers += '''

def configure_state_root(root):
    """Call once before serving. No default production root is permitted."""
    global DEFAULT_STATE_ROOT, TIKTOK_APP_ICON_PATH
    DEFAULT_STATE_ROOT = Path(root)
    TIKTOK_APP_ICON_PATH = DEFAULT_STATE_ROOT / 'public' / 'xuanjun-tiktok-icon.png'
'''
    # Require explicit configuration instead of retaining Tokyo runtime paths.
    helpers = helpers.replace("DEFAULT_STATE_ROOT = Path('/opt/trading-system/runtime/secure-secrets-portal')", '')
    (pkg / 'oauth.py').write_text(helpers + '\n')
    hashes = {}
    for path in sorted(pkg.glob('*.py')):
        ast.parse(path.read_text())
        hashes[str(path.relative_to(destination))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (destination / 'MANIFEST.json').write_text(json.dumps({
        'status': 'OFFLINE_LIBRARY_CANDIDATE_NOT_DEPLOYABLE',
        'source_archive_sha256': SOURCE_SHA, 'source_entry_sha256': ENTRY_SHA,
        'production_change': False, 'files': hashes,
        'remaining': ['HTTP adapter', 'protected state handoff', 'existing non-OAuth route successors',
                      'independent review', 'host acceptance', 'TLS and DNS gates']
    }, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_archive', type=Path)
    parser.add_argument('new_output_directory', type=Path)
    args = parser.parse_args()
    build(source_archive(args.source_archive), args.new_output_directory)
