"""Isolated, non-integrated tree calculation for the producer path only.

No authority, no Git mutation and no execution. Caller must authenticate the
project, combo baseline, exact input trees and writer lease before any write.
"""
import hashlib

PATH = 'scripts/task_center_app.py'
REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'


def oid(kind, raw):
    return hashlib.sha1((f'{kind} {len(raw)}\0').encode() + raw).hexdigest()


def parse_tree(raw):
    entries = []
    while raw:
        header, raw = raw.split(b'\0', 1)
        mode, name = header.split(b' ', 1)
        if len(raw) < 20 or not name or b'/' in name:
            raise ValueError('INVALID_TREE_ENTRY')
        entries.append((mode, name, raw[:20]))
        raw = raw[20:]
    if len({name for _, name, _ in entries}) != len(entries):
        raise ValueError('DUPLICATE_TREE_ENTRY')
    return entries


def replace(raw, name, old_oid, new_oid, expected_mode):
    entries = parse_tree(raw)
    found = 0
    out = bytearray()
    for mode, key, value in entries:
        if key == name:
            found += 1
            if mode != expected_mode or value.hex() != old_oid:
                raise ValueError('EXACT_BASE_ENTRY_REQUIRED')
            value = bytes.fromhex(new_oid)
            if len(value) != 20:
                raise ValueError('EXACT_SHA1_REQUIRED')
        out += mode + b' ' + key + b'\0' + value
    if found != 1:
        raise ValueError('EXACT_BASE_ENTRY_REQUIRED')
    return bytes(out)


def plan(repository, path, expected_root, root_raw, scripts_raw, base_blob, source):
    if repository != REPOSITORY or path != PATH:
        raise ValueError('EXACT_PRODUCER_SCOPE_REQUIRED')
    if not isinstance(source, bytes) or not 1 <= len(source) <= 131072:
        raise ValueError('SOURCE_BYTE_LIMIT')
    if oid('tree', root_raw) != expected_root:
        raise ValueError('BASE_TREE_MISMATCH')
    scripts_oid = oid('tree', scripts_raw)
    blob_oid = oid('blob', source)
    new_scripts = replace(scripts_raw, b'task_center_app.py', base_blob, blob_oid, b'100755')
    new_root = replace(root_raw, b'scripts', scripts_oid, oid('tree', new_scripts), b'40000')
    return {'blob_oid': blob_oid, 'scripts_oid': oid('tree', new_scripts),
            'tree_oid': oid('tree', new_root), 'scripts_raw': new_scripts, 'root_raw': new_root}
