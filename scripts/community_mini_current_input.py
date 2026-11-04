"""Freeze and stage the current reviewed mini tree for one development upload.

This helper has no provider credentials and never calls preview, upload, review,
or release APIs.  It binds the exact mini subtree that is compatible with the
installed reviewed points backend while allowing a separate control commit.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH = 'feature/chatgpt-community-wechat-sp-offline-20261017'
PRODUCT_SOURCE_SHA = '57c2bfc781244f27532ae10ad838ff921b8e52fb'
MINI_TREE = '1fbb21d2f5cfe5dc70708850bc85524f5e01902d'
MANIFEST_SHA256 = '6e229f83aaf2181589bb69bc35b38a667b47d30b1335ba869aa670443f04375e'
BINDING_ID = 'community-mini-merchant-auto-ocr-after-upload-development-upload-20261104'
BACKEND_SOURCE_SHA = '1b4b6f5b2dad2e239db8adb919ef9859198f7291'
COMPATIBILITY = 'BACKEND_COMPATIBLE_UI_ONLY'
PREFIX = 'community-mini-current/clients/community-mini/'
APPID = 'wx1d5f8873eaea5392'
PROFILE = 'uk-path-candidate'
BASE_URL = 'https://uk.wenwenwenyiyiyi.work/community-preview'
MAX_BYTES = 2_000_000
ROOT = Path(__file__).resolve().parents[1]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical_manifest(files):
    raw = ''.join(name + '\0' + files[name] + '\n' for name in sorted(files)).encode()
    return hashlib.sha256(raw).hexdigest()


def control_context(env):
    require(env.get('GITHUB_EVENT_NAME') == 'push'
            and env.get('GITHUB_REPOSITORY') == REPO
            and env.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and re.fullmatch('[0-9a-f]{40}', env.get('GITHUB_SHA', '') or '')
            and env.get('PREVIEW_CONTROL_SHA') == env.get('GITHUB_SHA')
            and env.get('PREVIEW_SOURCE_SHA') == PRODUCT_SOURCE_SHA
            and env.get('PREVIEW_TARGET') == PROFILE
            and env.get('PREVIEW_ENABLED') == 'true'
            and env.get('IMAGE_BUILD_ENABLED') == 'false',
            'EXACT_CURRENT_CONTROL_CONTEXT_REQUIRED')
    require(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '') or '')
            and re.fullmatch('[1-9][0-9]{0,4}', env.get('GITHUB_RUN_ATTEMPT', '') or ''),
            'EXACT_CURRENT_RUN_CONTEXT_REQUIRED')
    return env['GITHUB_SHA']


def git_output(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], universal_newlines=True,
                                   stderr=subprocess.DEVNULL).strip()


def source_files():
    require(git_output('rev-parse', 'HEAD:clients/community-mini') == MINI_TREE,
            'CURRENT_MINI_TREE_REQUIRED')
    files = {}
    for line in git_output('ls-tree', '-r', 'HEAD', 'clients/community-mini').splitlines():
        meta, name = line.split('\t', 1)
        mode, kind, blob = meta.split()
        require(mode == '100644' and kind == 'blob' and name.startswith('clients/community-mini/'),
                'CURRENT_MINI_REGULAR_FILES_REQUIRED')
        relative = name[len('clients/community-mini/'):]
        raw = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', 'blob', blob])
        require(len(raw) <= MAX_BYTES, 'CURRENT_MINI_FILE_SIZE_REQUIRED')
        files[relative] = (raw, hashlib.sha256(raw).hexdigest())
    hashes = {name: value[1] for name, value in files.items()}
    require(len(files) == 70 and canonical_manifest(hashes) == MANIFEST_SHA256,
            'CURRENT_MINI_MANIFEST_REQUIRED')
    return files


def build_archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(PREFIX + name, (2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, files[name][0])
    return output.getvalue()


def receipt(raw, files, env):
    app = files['app.js'][0].decode()
    needle = "App({\n  globalData: {baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false},"
    replacement = "App({\n  globalData: {baseUrl: '" + BASE_URL + "', token: '', mode: 'WECHAT_LOGIN', payments: false, commerce: true},"
    require(app.count(needle) == 1, 'EXPECTED_CURRENT_APP_BASELINE_REQUIRED')
    return {
        'status': 'CURRENT_MINI_EXACT_INPUT_VERIFIED_NOT_UPLOADED',
        'binding_id': BINDING_ID,
        'control_source_sha': control_context(env),
        'product_source_sha': PRODUCT_SOURCE_SHA,
        'mini_tree': MINI_TREE,
        'manifest_sha256': MANIFEST_SHA256,
        'mini_zip_sha256': hashlib.sha256(raw).hexdigest(),
        'backend_source_sha': BACKEND_SOURCE_SHA,
        'compatibility': COMPATIBILITY,
        'source_files': {name: files[name][1] for name in sorted(files)},
        'connected_app_sha256': hashlib.sha256(app.replace(needle, replacement).encode()).hexdigest(),
        'workflow_run_id': env['GITHUB_RUN_ID'],
        'workflow_run_attempt': env['GITHUB_RUN_ATTEMPT'],
        'appid': APPID,
        'profile': PROFILE,
        'baseUrl': BASE_URL,
        'payments': False,
        'upload_performed': False,
        'review_submitted': False,
        'public_release': False,
    }


def paths(env):
    suffix = env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']
    root = Path(env['RUNNER_TEMP']).resolve()
    return root / ('community-mini-current-source-' + suffix), root / ('community-mini-current-context-' + suffix + '.json')


def read_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        raw = os.read(fd, 65537)
        require(len(raw) <= 65536 and stat.S_ISREG(os.fstat(fd).st_mode), 'CURRENT_RECEIPT_REQUIRED')
    finally:
        os.close(fd)
    return json.loads(raw)


def verify_receipt(value, raw, env):
    control_context(env)
    require(value.get('status') == 'CURRENT_MINI_EXACT_INPUT_VERIFIED_NOT_UPLOADED'
            and value.get('binding_id') == BINDING_ID
            and value.get('control_source_sha') == env['GITHUB_SHA']
            and value.get('product_source_sha') == PRODUCT_SOURCE_SHA
            and value.get('mini_tree') == MINI_TREE
            and value.get('manifest_sha256') == MANIFEST_SHA256
            and value.get('mini_zip_sha256') == hashlib.sha256(raw).hexdigest()
            and value.get('backend_source_sha') == BACKEND_SOURCE_SHA
            and value.get('compatibility') == COMPATIBILITY
            and 'compatibility_sha256' not in value
            and value.get('workflow_run_id') == env['GITHUB_RUN_ID']
            and value.get('workflow_run_attempt') == env['GITHUB_RUN_ATTEMPT']
            and value.get('appid') == APPID and value.get('profile') == PROFILE
            and value.get('baseUrl') == BASE_URL and value.get('payments') is False
            and value.get('upload_performed') is False
            and value.get('review_submitted') is False
            and value.get('public_release') is False,
            'CURRENT_MINI_RECEIPT_REQUIRED')
    hashes = value.get('source_files')
    require(type(hashes) is dict and len(hashes) == 70 and canonical_manifest(hashes) == MANIFEST_SHA256,
            'CURRENT_MINI_RECEIPT_FILES_REQUIRED')
    return hashes


def build(env):
    require(not Path('current-mini-source.zip').exists() and not Path('current-mini-receipt.json').exists(),
            'CURRENT_MINI_OUTPUT_ALREADY_EXISTS')
    files = source_files()
    raw = build_archive(files)
    value = receipt(raw, files, env)
    Path('current-mini-source.zip').write_bytes(raw)
    Path('current-mini-receipt.json').write_text(json.dumps(value, sort_keys=True) + '\n')


def stage(env):
    raw = Path('current-mini-source.zip').read_bytes()
    value = read_json('current-mini-receipt.json')
    hashes = verify_receipt(value, raw, env)
    destination, context = paths(env)
    require(not destination.exists() and not context.exists(), 'CURRENT_MINI_STAGE_ALREADY_EXISTS')
    temp = Path(tempfile.mkdtemp(prefix='.current-mini-', dir=destination.parent))
    try:
        mini = temp / 'clients/community-mini'
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            require(len(names) == 70 and len(names) == len(set(names)), 'CURRENT_MINI_ARCHIVE_SET_REQUIRED')
            for name in names:
                pure = PurePosixPath(name)
                require(not pure.is_absolute() and '..' not in pure.parts and name.startswith(PREFIX),
                        'CURRENT_MINI_ARCHIVE_PATH_REQUIRED')
                relative = name[len(PREFIX):]
                require(relative in hashes and hashlib.sha256(archive.read(name)).hexdigest() == hashes[relative],
                        'CURRENT_MINI_ARCHIVE_HASH_REQUIRED')
                path = mini / relative
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with path.open('xb') as stream:
                    stream.write(archive.read(name))
                path.chmod(0o600)
        os.rename(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    staged = dict(value, source_root=str(destination))
    context.write_text(json.dumps(staged, sort_keys=True) + '\n')
    context.chmod(0o600)


def identity(env):
    destination, context = paths(env)
    require(env.get('COMMUNITY_PREVIEW_PRODUCT_CONTEXT') == str(context), 'CURRENT_PRODUCT_CONTEXT_PATH_REQUIRED')
    value = read_json(context)
    raw = Path(env['CURRENT_MINI_ARCHIVE_PATH']).read_bytes() if env.get('CURRENT_MINI_ARCHIVE_PATH') else b''
    # The archive was verified before staging; identity re-verifies the staged file manifest.
    require(value.get('control_source_sha') == control_context(env)
            and value.get('product_source_sha') == PRODUCT_SOURCE_SHA
            and value.get('manifest_sha256') == MANIFEST_SHA256
            and value.get('source_root') == str(destination), 'CURRENT_PRODUCT_CONTEXT_REQUIRED')
    mini = destination / 'clients/community-mini'
    actual = {}
    for path in mini.rglob('*'):
        require(not path.is_symlink(), 'CURRENT_PRODUCT_SYMLINK_DENIED')
        if path.is_file():
            actual[path.relative_to(mini).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    require(actual == value['source_files'] and canonical_manifest(actual) == MANIFEST_SHA256,
            'CURRENT_PRODUCT_SOURCE_CHANGED')
    prepared = {name: digest for name, digest in actual.items() if not name.endswith('.test.cjs')}
    prepared['app.js'] = value['connected_app_sha256']
    require(len(prepared) == 40, 'CURRENT_PREPARED_SOURCE_SET_REQUIRED')
    return {'product_source_sha': PRODUCT_SOURCE_SHA, 'control_source_sha': value['control_source_sha'],
            'source_root': str(destination), 'prepared_files': prepared, 'fixed_product': True,
            'backend_source_sha': BACKEND_SOURCE_SHA, 'compatibility': COMPATIBILITY}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('build', 'stage', 'identity'))
    args = parser.parse_args()
    if args.operation == 'build':
        build(os.environ)
    elif args.operation == 'stage':
        stage(os.environ)
    else:
        print(json.dumps(identity(os.environ), sort_keys=True))


if __name__ == '__main__':
    main()
