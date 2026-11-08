"""Reproduce unavailable test-only Actions ZIPs from their unchanged Git sources.

Runs the historical offline builder in a temporary detached worktree. Never
installs anything or publishes the generated carrier/document files. Both the
original outer transport digest and inner test-input digests remain mandatory.
"""
import hashlib
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'deploy/community-preview/stopped-handoff-v1-delivery/'
SPECS = {
    'old': ('1d639347f404f952998b3b414a95e48f66571c3c',
            'a9b034ce85734cf26f4b18058f6840f6434aac0c31322b0664fda7e78eb68956',
            '5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4',
            'e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a'),
    'new': ('005c7448d5fe56b1def83fd4aa4cf9ffc4c8aaa1',
            'f529ca439a9decc95efa4cf4f93391e0ba93719565ad952629d752ef7640ca34',
            '2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff',
            'd1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd'),
}
SOURCE_NAMES = (
    'scripts/community_preview_stopped_handoff.py',
    'scripts/community_preview_bc_loader.py',
    'scripts/community_preview_bc_build.py',
    'scripts/community_preview_bc_install.py',
    'deploy/community-preview/install-stopped-v1.sh',
    'tests/test_community_preview_stopped_handoff.py',
    'tests/test_community_preview_bc_install.py',
    'docs/development/COMMUNITY_STOPPED_HANDOFF_V1.md',
)
# This is ZIP-format metadata, not a changed evidence date or an execution receipt.
# The original Actions wrapper used Node's deflate implementation and data
# descriptors; Python's current compressor does not reproduce those outer bytes.
NODE_DEFLATE = "let a=[];process.stdin.on('data',b=>a.push(b));process.stdin.on('end',()=>process.stdout.write(require('zlib').deflateRawSync(Buffer.concat(a),{level:6})));"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


def names_for(label):
    require(label in SPECS, 'UNREGISTERED_HISTORICAL_ARTIFACT')
    delivery = ['control-stopped-v1.zip', 'delivery.json', 'manifest.json',
                'owner-bc.sh', 'recover-known-failure.sh']
    if label == 'new':
        delivery.append('resume-b-partial.sh')
    return [PREFIX + n for n in delivery] + list(SOURCE_NAMES)


def wrapper(label, files):
    """Recreate the original ZIP wrapper, failing if any expected bytes differ."""
    names = names_for(label)
    require(set(files) == set(names), 'HISTORICAL_WRAPPER_MEMBER_SET')
    output = bytearray()
    central = bytearray()
    for name in names:
        data = files[name]
        require(isinstance(data, bytes) and len(data) <= 2 * 1024 * 1024,
                'HISTORICAL_WRAPPER_INPUT_INVALID')
        if label == 'old':
            second = 12 if name in ('scripts/community_preview_bc_loader.py',
                                   'scripts/community_preview_bc_build.py') else 10
            dt = (2026, 10, 24, 19, 27, second)
        else:
            dt = (2026, 10, 25, 3, 55, 48)
        time = (dt[3] << 11) | (dt[4] << 5) | (dt[5] // 2)
        date = ((dt[0] - 1980) << 9) | (dt[1] << 5) | dt[2]
        compressed = subprocess.run([os.environ.get('COMMUNITY_ARTIFACT_NODE', 'node'), '-e', NODE_DEFLATE], input=data,
                                    capture_output=True, check=True).stdout
        encoded = name.encode('utf-8')
        offset = len(output)
        crc = zlib.crc32(data)
        output += struct.pack('<4s5H3I2H', b'PK\x03\x04', 20, 8, 8, time, date,
                              0, 0, 0, len(encoded), 0) + encoded + compressed
        output += struct.pack('<4s3I', b'PK\x07\x08', crc, len(compressed), len(data))
        central += struct.pack('<4s6H3I5H2I', b'PK\x01\x02', 813, 20, 8, 8,
                               time, date, crc, len(compressed), len(data),
                               len(encoded), 0, 0, 0, 0, 2175008800, offset) + encoded
    start = len(output)
    output += central
    output += struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, len(names), len(names),
                          len(central), start, 0)
    body = bytes(output)
    if digest(body) != SPECS[label][1]:
        print('HISTORICAL_RECOVERY_COMPRESSION_DIAGNOSTIC', label,
              'outer_sha256=' + digest(body),
              'inner_sha256=' + digest(files[PREFIX + 'control-stopped-v1.zip']),
              'manifest_sha256=' + digest(files[PREFIX + 'manifest.json']),
              'python_zlib=' + zlib.ZLIB_RUNTIME_VERSION, file=sys.stderr)
        print(subprocess.check_output([os.environ.get('COMMUNITY_ARTIFACT_NODE', 'node'), '-p', 'JSON.stringify(process.versions)'],
                                      text=True).strip(), file=sys.stderr)
    validate(label, body)
    return body


def validate(label, body):
    require(label in SPECS, 'UNREGISTERED_HISTORICAL_ARTIFACT')
    _, outer_sha, archive_sha, manifest_sha = SPECS[label]
    require(len(body) <= 2 * 1024 * 1024 and digest(body) == outer_sha,
            'HISTORICAL_OUTER_ARTIFACT_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(body)) as outer:
        require(outer.namelist() == names_for(label), 'HISTORICAL_WRAPPER_MEMBER_SET')
        archive = outer.read(PREFIX + 'control-stopped-v1.zip')
        manifest = outer.read(PREFIX + 'manifest.json')
    require(digest(archive) == archive_sha and digest(manifest) == manifest_sha,
            'HISTORICAL_INNER_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(archive)) as nested:
        require(nested.read('manifest.json') == manifest, 'HISTORICAL_INNER_MANIFEST_MISMATCH')


def recover_artifact(label, repo=ROOT):
    require(label in SPECS, 'UNREGISTERED_HISTORICAL_ARTIFACT')
    repo = Path(repo).resolve()
    commit = SPECS[label][0]
    actual = subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'],
                                     cwd=repo, text=True).strip()
    require(actual == commit, 'HISTORICAL_COMMIT_MISMATCH')
    # Git owns the new worktree identity. Never reuse or overwrite an old path.
    with tempfile.TemporaryDirectory(prefix='community-exact-artifact-') as tmp:
        work = Path(tmp) / 'source'
        subprocess.run(['git', 'worktree', 'add', '--detach', str(work), commit],
                       cwd=repo, check=True, capture_output=True)
        try:
            require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=work,
                                            text=True).strip() == commit,
                    'HISTORICAL_WORKTREE_COMMIT_MISMATCH')
            # Reproduce the historical builder's original commit-bound environment,
            # only for this isolated child. The live checkout/GitHub identity stays unchanged.
            builder_env = dict(os.environ, GITHUB_SHA=commit)
            subprocess.run([sys.executable, '-B', '-m', 'scripts.community_preview_bc_build'],
                           cwd=work, env=builder_env, check=True, capture_output=True)
            files = {}
            for name in names_for(label):
                path = work / name
                require(not path.is_symlink() and path.is_file(),
                        'HISTORICAL_REGULAR_INPUT_REQUIRED')
                data = path.read_bytes()
                require(len(data) <= 2 * 1024 * 1024, 'HISTORICAL_INPUT_OVERSIZE')
                if not name.startswith(PREFIX):
                    original = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=repo)
                    require(data == original, 'HISTORICAL_SOURCE_CHANGED')
                files[name] = data
            return wrapper(label, files)
        finally:
            subprocess.run(['git', 'worktree', 'remove', '--force', str(work)],
                           cwd=repo, check=True, capture_output=True)
