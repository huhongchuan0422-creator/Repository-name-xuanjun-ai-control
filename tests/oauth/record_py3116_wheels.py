"""CI-only exact wheel receipt; not a host installer or authorization source."""
import email.parser
import hashlib
import json
import platform
import re
import sqlite3
import ssl
import sys
import zipfile
from pathlib import Path


def receipt(lock_path, wheel_dir):
    expected = {}
    name = None
    for line in Path(lock_path).read_text().splitlines():
        match = re.match(r'^([A-Za-z0-9_-]+)==([^\s\\]+)', line)
        if match:
            name = match.group(1).lower().replace('_', '-')
            if name in expected:
                raise ValueError('DUPLICATE_PACKAGE')
            expected[name] = {'version': match.group(2), 'hashes': set()}
        for digest in re.findall(r'--hash=sha256:([0-9a-f]{64})', line):
            if name is None:
                raise ValueError('UNBOUND_HASH')
            expected[name]['hashes'].add(digest)
    if len(expected) != 18:
        raise ValueError('EXACT_18_PACKAGES_REQUIRED')
    rows = []
    seen = set()
    for path in sorted(Path(wheel_dir).iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != '.whl':
            raise ValueError('REGULAR_WHEEL_ONLY')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        # Validate bytes before ZIP parsing, against the inherited reviewed lock.
        if not any(digest in item['hashes'] for item in expected.values()):
            raise ValueError('UNREVIEWED_WHEEL')
        with zipfile.ZipFile(path) as z:
            metadata = [i for i in z.infolist() if i.filename.endswith('.dist-info/METADATA')]
            wheel = [i for i in z.infolist() if i.filename.endswith('.dist-info/WHEEL')]
            if len(metadata) != 1 or len(wheel) != 1:
                raise ValueError('AMBIGUOUS_METADATA')
            if metadata[0].file_size > 262144 or wheel[0].file_size > 16384:
                raise ValueError('METADATA_TOO_LARGE')
            msg = email.parser.Parser().parsestr(z.read(metadata[0]).decode())
            tags = [line[5:] for line in z.read(wheel[0]).decode().splitlines()
                    if line.startswith('Tag: ')]
        name = msg['Name'].lower().replace('_', '-')
        if name not in expected or name in seen:
            raise ValueError('WRONG_PACKAGE_SET')
        if msg['Version'] != expected[name]['version'] or digest not in expected[name]['hashes']:
            raise ValueError('PACKAGE_BINDING_MISMATCH')
        seen.add(name)
        rows.append({'name': name, 'version': msg['Version'], 'filename': path.name,
                     'bytes': len(raw), 'sha256': digest, 'tags': tags,
                     'requires_python': msg['Requires-Python']})
    if seen != set(expected):
        raise ValueError('INCOMPLETE_WHEELS')
    return sorted(rows, key=lambda row: row['name'])


def main():
    if sys.version_info[:3] != (3, 11, 6) or platform.machine() != 'x86_64':
        raise SystemExit('EXACT_CPYTHON_3116_X86_64_REQUIRED')
    lock, wheels, out = map(Path, sys.argv[1:])
    rows = receipt(lock, wheels)
    selected = '# Exact isolated CPython3.11.6 Linux x86_64 wheel selection; not live adoption.\n'
    selected += ''.join('{name}=={version} --hash=sha256:{sha256}\n'.format(**row) for row in rows)
    out.mkdir(exist_ok=True)
    (out/'requirements.cp3116.lock').write_text(selected)
    result = {'purpose': 'ISOLATED_CI_COMPATIBILITY_NOT_PRODUCTION',
              'python': platform.python_version(), 'soabi': __import__('sysconfig').get_config_var('SOABI'),
              'libc': platform.libc_ver(), 'openssl': ssl.OPENSSL_VERSION,
              'sqlite': sqlite3.sqlite_version, 'source_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
              'selected_lock_sha256': hashlib.sha256(selected.encode()).hexdigest(), 'wheels': rows}
    (out/'wheel-receipt.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(result, sort_keys=True))
    print('SELECTED_LOCK_BEGIN\n'+selected+'SELECTED_LOCK_END')


if __name__ == '__main__':
    main()
