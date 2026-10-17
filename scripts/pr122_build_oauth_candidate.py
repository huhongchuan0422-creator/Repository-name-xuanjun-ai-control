#!/usr/bin/env python3
"""Build an OFFLINE OAuth library candidate from pinned Tokyo source.

No installer, service start, credential import or production acceptance implied.
Validates pinned upstream provenance and copies hash-bound maintained templates.
Persistence differs from upstream to address R1-R3; independent review is required.
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


def build(source, destination, http_adapter):
    # The upstream archive remains provenance, not an authority to regenerate
    # vulnerable original persistence. R1-R3 use reviewed maintained templates.
    template = http_adapter.parent
    manifest_path = template.parent / 'MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    if (manifest['source_archive_sha256'] != SOURCE_SHA
            or manifest['source_entry_sha256'] != ENTRY_SHA):
        raise ValueError('TEMPLATE_PROVENANCE_MISMATCH')
    expected = {'__init__.py','core.py','oauth.py','douyin.py','tiktok.py',
                'http_candidate.py','storage.py'}
    if {p.name for p in template.glob('*.py')} != expected:
        raise ValueError('TEMPLATE_MODULE_SET_MISMATCH')
    files = {}
    for name in sorted(expected):
        path = template / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('UNTRUSTED_TEMPLATE')
        data = path.read_bytes()
        ast.parse(data)
        relative = 'pr122_oauth_candidate/' + name
        if hashlib.sha256(data).hexdigest() != manifest['files'].get(relative):
            raise ValueError('TEMPLATE_HASH_MISMATCH')
        files[relative] = data
    if set(files) != set(manifest['files']):
        raise ValueError('TEMPLATE_MANIFEST_MISMATCH')
    destination.mkdir(mode=0o700)
    (destination/'pr122_oauth_candidate').mkdir(mode=0o700)
    for relative, data in files.items():
        (destination/relative).write_bytes(data)
    (destination/'MANIFEST.json').write_bytes(manifest_path.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_archive', type=Path)
    parser.add_argument('new_output_directory', type=Path)
    parser.add_argument('--http-adapter', type=Path, default=Path(__file__).resolve().parents[1]
                        / 'deploy/pr122-oauth-candidate/pr122_oauth_candidate/http_candidate.py')
    args = parser.parse_args()
    build(source_archive(args.source_archive), args.new_output_directory, args.http_adapter)
