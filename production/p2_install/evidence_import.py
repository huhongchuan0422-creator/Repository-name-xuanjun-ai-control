"""B2 isolated evidence packaging adapter; exact ea31 performs installation/recovery."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import uuid
from production.p2_artifacts import installer as artifacts

NAMES = ('b1-receipt.json', 'b1-summary.json')
LIMIT = 4 * 1024 * 1024
ORIGIN_REFS = {
    'b1-receipt.json': '/var/lib/xuanjun-p2-isolated-test/artifacts/.p2_artifacts/receipts/p2-uk-isolated-20261020--b1-release.json',
    'b1-summary.json': '/var/lib/xuanjun-p2-isolated-test/logs/b1-first-install-20261020/summary.json'}
B1_RECEIPT_SHA = '2aa0616f8d9cc57e4dc367198fcb40b1d9cfe88ffa46221273c62cf4ad6e069a'


def read_regular(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('SOURCE_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        source = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(source, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > LIMIT:
                raise ValueError('SOURCE_TYPE_OR_SIZE')
            raw = stream.read(LIMIT + 1)
            after = os.fstat(stream.fileno())
            fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fields(before) != fields(after) or len(raw) != before.st_size:
                raise ValueError('SOURCE_CHANGED')
            return raw
    finally:
        os.close(fd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def index_bytes(spec):
    if not isinstance(spec, dict):
        raise ValueError('UNKNOWN_SOURCE_SPEC')
    if spec.get('scope') != 'ISOLATED_TEST_ONLY' or spec.get('origin_scope') not in (
            'ISOLATED_B1_EVIDENCE', 'SYNTHETIC_TEST_ONLY'):
        raise ValueError('UNKNOWN_SOURCE_SCOPE')
    if not isinstance(spec.get('sources'), dict) or set(spec['sources']) != set(NAMES):
        raise ValueError('UNKNOWN_SOURCE_SET')
    for value in spec['sources'].values():
        if not isinstance(value, dict) or not artifacts.HEX.fullmatch(value.get('sha256', '')) or not value.get('origin_ref'):
            raise ValueError('UNKNOWN_SOURCE_BINDING')
    if spec['origin_scope'] == 'ISOLATED_B1_EVIDENCE':
        if any(spec['sources'][n]['origin_ref'] != ORIGIN_REFS[n] for n in NAMES):
            raise ValueError('UNKNOWN_B1_ORIGIN')
        if spec['sources']['b1-receipt.json']['sha256'] != B1_RECEIPT_SHA:
            raise ValueError('UNKNOWN_B1_RECEIPT')
        if (spec.get('root'), spec.get('source_root'), spec.get('installation_id'), spec.get('batch_id'), spec.get('attempt_id')) != (
                '/var/lib/xuanjun-p2-isolated-test/b2-evidence', '/source',
                'p2-uk-isolated-20261020', 'b2-preserve', 'b2-preserve-a1'):
            raise ValueError('B2_FIXED_SCOPE_MISMATCH')
    return artifacts.encode({'schema': 1, 'scope': spec['scope'], 'origin_scope': spec['origin_scope'],
        'production_history': False, 'sources': spec['sources']})


def publish(path, raw):
    if os.path.lexists(str(path)):
        if read_regular(path) != raw:
            raise ValueError('PREPARED_EVIDENCE_CONFLICT')
        return
    # Keep interrupted and linked staging files as evidence; never overwrite/unlink.
    pending = path.parent / ('.' + path.name + '.pending-' + uuid.uuid4().hex)
    fd = os.open(str(pending), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    try:
        os.link(str(pending), str(path))
    except FileExistsError:
        if read_regular(path) != raw:
            raise ValueError('PREPARED_EVIDENCE_CONFLICT')
    artifacts.fsync_dir(path.parent)


def component_request(spec, root, archive_sha):
    index = index_bytes(spec)
    return {k: spec[k] for k in ('schema', 'scope', 'installation_id', 'batch_id', 'attempt_id')} | {
        'root': str(root), 'inputs': {'operation': 'install', 'archive': str(root / 'b2-input.tar'),
        'archive_sha256': archive_sha, 'files': dict(
            {n: spec['sources'][n]['sha256'] for n in NAMES}, **{'INDEX.json': sha(index)}),
        'modes': {n: 0o600 for n in NAMES + ('INDEX.json',)}}}


def dispatch(spec, action):
    try:
        index = index_bytes(spec)  # UNKNOWN never creates component state.
        root = artifacts.request_check(spec)
        lock = os.open(str(root / '.b2.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError('LOCK_IDENTITY')
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            intent_path = root / 'b2-intent.json'
            spec_sha = sha(artifacts.encode(spec))
            if os.path.lexists(str(intent_path)):
                intent = json.loads(read_regular(intent_path))
                if intent['spec_sha256'] != spec_sha:
                    raise ValueError('REQUEST_CONFLICT')
                request = component_request(spec, root, intent['archive_sha256'])
                if intent['component_request'] != request:
                    raise ValueError('INTENT_CONFLICT')
            else:
                if action == 'inspect':
                    return {'scope': spec['scope'], 'status': 'NO_EFFECT', 'receipt': None}
                contents = {n: read_regular(Path(spec['source_root']) / n) for n in NAMES}
                for name, raw in contents.items():
                    if sha(raw) != spec['sources'][name]['sha256']:
                        raise ValueError('SOURCE_DIGEST_MISMATCH')
                contents['INDEX.json'] = index
                output = io.BytesIO()
                with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
                    for name, raw in sorted(contents.items()):
                        member = tarfile.TarInfo(name)
                        member.size, member.mode, member.mtime = len(raw), 0o600, 0
                        archive.addfile(member, io.BytesIO(raw))
                raw = output.getvalue()
                publish(root / 'b2-input.tar', raw)
                request = component_request(spec, root, sha(raw))
                publish(intent_path, artifacts.encode({'spec_sha256': spec_sha,
                    'archive_sha256': sha(raw), 'component_request': request}))
            return getattr(artifacts, action)(request)
        finally:
            os.close(lock)
    except (ValueError, OSError, KeyError, TypeError, artifacts.Stop) as exc:
        return {'scope': 'ISOLATED_TEST_ONLY', 'status': 'UNKNOWN',
                'receipt': None, 'error': {'code': getattr(exc, 'code', str(exc))}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('execute', 'inspect', 'recover'))
    args = parser.parse_args()
    result = dispatch(json.load(__import__('sys').stdin), args.action)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('COMMITTED', 'NO_EFFECT') else 2


if __name__ == '__main__':
    raise SystemExit(main())
