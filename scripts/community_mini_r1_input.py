"""Exact R1 mini-program input for the existing development-upload workflow.

This helper only freezes/stages the already reviewed mini tree.  It never reads
WeChat credentials and never calls preview, upload, review, or release APIs.
"""
import argparse
import hashlib
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
SOURCE_SHA = '7ca1ac2a4e5a68704bb0cebe1c33049713070859'
SOURCE_TREE = '321134ffac48f3b960df051c53749a481aea872d'
ZIP_SHA256 = 'f23aeeb855559795658e15ee1158c1475219314f52b8ad98c3407fc44c6548af'
ZIP_BYTES = 371858
ZIP_MEMBERS = 76
BINDING_ID = 'community-mini-original-path-20261031T1223Z'
PREFIX = 'community-mini-7ca1ac2a/'
MINI_PREFIX = PREFIX + 'clients/community-mini/'
APPID = 'wx1d5f8873eaea5392'
PROFILE = 'uk-path-candidate'
BASE_URL = 'https://uk.wenwenwenyiyiyi.work/community-preview'
MAX_BYTES = 2_000_000
ROOT = Path(__file__).resolve().parents[1]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def strict_json(raw):
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    return json.loads(raw, object_pairs_hook=lambda pairs: _unique(pairs))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read_regular(path, limit=MAX_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGULAR_INPUT_REQUIRED')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, 'INPUT_SIZE_LIMIT')
        return raw
    finally:
        os.close(fd)


def write_new(path, raw):
    with open(path, 'xb') as stream:
        os.chmod(path, 0o600)
        stream.write(raw)


def control_context(env):
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == REPO
            and env.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and re.fullmatch('[0-9a-f]{40}', env.get('GITHUB_SHA', '') or '')
            and env.get('PREVIEW_CONTROL_SHA') == env.get('GITHUB_SHA')
            and env.get('PREVIEW_SOURCE_SHA') == SOURCE_SHA
            and env.get('PREVIEW_PRODUCT_TREE') == SOURCE_TREE
            and env.get('PREVIEW_PRODUCT_ZIP_SHA256') == ZIP_SHA256
            and env.get('PREVIEW_BINDING_ID') == BINDING_ID
            and env.get('PREVIEW_TARGET') == PROFILE
            and env.get('PREVIEW_ENABLED') == 'true'
            and env.get('IMAGE_BUILD_ENABLED') == 'false',
            'EXACT_R1_CONTROL_CONTEXT_REQUIRED')
    require(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '') or '')
            and re.fullmatch('[1-9][0-9]{0,4}', env.get('GITHUB_RUN_ATTEMPT', '') or ''),
            'EXACT_R1_RUN_CONTEXT_REQUIRED')
    return env['GITHUB_SHA']


def git_output(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], universal_newlines=True,
                                   stderr=subprocess.DEVNULL).strip()


def build_archive():
    require(git_output('rev-parse', SOURCE_SHA + '^{commit}') == SOURCE_SHA,
            'R1_SOURCE_COMMIT_REQUIRED')
    require(git_output('rev-parse', SOURCE_SHA + '^{tree}') == SOURCE_TREE,
            'R1_SOURCE_TREE_REQUIRED')
    raw = subprocess.check_output([
        'git', '-C', str(ROOT), 'archive', '--format=zip', '--prefix=' + PREFIX,
        SOURCE_SHA, 'clients/community-mini'], stderr=subprocess.DEVNULL)
    return verify_archive(raw)


def verify_archive(raw):
    require(len(raw) == ZIP_BYTES and hashlib.sha256(raw).hexdigest() == ZIP_SHA256,
            'R1_MINI_ZIP_SHA_REQUIRED')
    files = {}
    with zipfile.ZipFile(__import__('io').BytesIO(raw)) as archive:
        items = archive.infolist()
        require(len(items) == ZIP_MEMBERS and len(items) == len({item.filename for item in items}),
                'R1_MINI_MEMBER_SET_REQUIRED')
        for item in items:
            name = item.filename
            path = PurePosixPath(name)
            require(str(path) == name.rstrip('/') and not path.is_absolute() and '..' not in path.parts
                    and '\\' not in name and name.startswith(PREFIX), 'SAFE_R1_MINI_PATH_REQUIRED')
            if item.is_dir():
                continue
            require(name.startswith(MINI_PREFIX),
                    'SAFE_R1_MINI_FILE_REQUIRED')
            data = archive.read(item)
            files[name[len(MINI_PREFIX):]] = hashlib.sha256(data).hexdigest()
    require(len(files) == 66 and all(files), 'COMPLETE_R1_MINI_FILES_REQUIRED')
    return raw, files


def connected_app_sha(raw):
    with zipfile.ZipFile(__import__('io').BytesIO(raw)) as archive:
        app = archive.read(MINI_PREFIX + 'app.js').decode('utf-8')
    needle = "App({\n  globalData: {baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false},"
    replacement = "App({\n  globalData: {baseUrl: '" + BASE_URL + "', token: '', mode: 'WECHAT_LOGIN', payments: false, commerce: true},"
    require(app.count(needle) == 1, 'EXPECTED_R1_APP_BASELINE_REQUIRED')
    return hashlib.sha256(app.replace(needle, replacement).encode()).hexdigest()


def paths(env):
    suffix = env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']
    root = Path(env['RUNNER_TEMP']).resolve()
    return (root / ('community-mini-product-source-' + suffix),
            root / ('community-mini-product-context-' + suffix + '.json'))


def receipt(raw, files, env):
    return {
        'status': 'R1_MINI_EXACT_INPUT_VERIFIED_NOT_UPLOADED',
        'binding_id': BINDING_ID,
        'control_source_sha': control_context(env),
        'product_source_sha': SOURCE_SHA,
        'product_tree': SOURCE_TREE,
        'mini_zip_sha256': ZIP_SHA256,
        'mini_zip_bytes': ZIP_BYTES,
        'mini_zip_members': ZIP_MEMBERS,
        'source_files': files,
        'connected_app_sha256': connected_app_sha(raw),
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


def verify_receipt(value, env):
    control_context(env)
    require(value.get('status') == 'R1_MINI_EXACT_INPUT_VERIFIED_NOT_UPLOADED'
            and value.get('binding_id') == BINDING_ID
            and value.get('control_source_sha') == env['GITHUB_SHA']
            and value.get('product_source_sha') == SOURCE_SHA
            and value.get('product_tree') == SOURCE_TREE
            and value.get('mini_zip_sha256') == ZIP_SHA256
            and value.get('mini_zip_bytes') == ZIP_BYTES
            and value.get('mini_zip_members') == ZIP_MEMBERS
            and value.get('workflow_run_id') == env['GITHUB_RUN_ID']
            and value.get('workflow_run_attempt') == env['GITHUB_RUN_ATTEMPT']
            and value.get('appid') == APPID and value.get('profile') == PROFILE
            and value.get('baseUrl') == BASE_URL and value.get('payments') is False
            and value.get('upload_performed') is False
            and value.get('review_submitted') is False
            and value.get('public_release') is False,
            'R1_MINI_RECEIPT_REQUIRED')
    files = value.get('source_files')
    require(type(files) is dict and len(files) == 66
            and all(type(k) is str and type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
                    for k, v in files.items()), 'R1_MINI_FILE_MANIFEST_REQUIRED')
    return files


def stage(raw, value, env):
    _, files = verify_archive(raw)
    require(files == verify_receipt(value, env), 'R1_MINI_RECEIPT_FILES_REQUIRED')
    destination, context_file = paths(env)
    require(not destination.exists() and not context_file.exists(), 'R1_PRODUCT_OUTPUT_ALREADY_EXISTS')
    temp = Path(tempfile.mkdtemp(prefix='.r1-mini-', dir=destination.parent))
    try:
        mini = temp / 'clients/community-mini'
        with zipfile.ZipFile(__import__('io').BytesIO(raw)) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                relative = item.filename[len(MINI_PREFIX):]
                path = mini / relative
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                write_new(path, archive.read(item))
        os.rename(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    staged = dict(value, source_root=str(destination))
    write_new(context_file, (json.dumps(staged, sort_keys=True) + '\n').encode())
    return staged


def identity(env):
    destination, context_file = paths(env)
    require(env.get('COMMUNITY_PREVIEW_PRODUCT_CONTEXT') == str(context_file),
            'EXACT_R1_PRODUCT_CONTEXT_PATH_REQUIRED')
    value = strict_json(read_regular(context_file, 16384))
    expected = verify_receipt(value, env)
    require(value.get('source_root') == str(destination) and not destination.is_symlink(),
            'EXACT_R1_PRODUCT_SOURCE_ROOT_REQUIRED')
    mini = destination / 'clients/community-mini'
    actual = {}
    for path in mini.rglob('*'):
        require(not path.is_symlink(), 'R1_PRODUCT_SOURCE_SYMLINK_DENIED')
        if path.is_file():
            actual[path.relative_to(mini).as_posix()] = hashlib.sha256(read_regular(path)).hexdigest()
        else:
            require(path.is_dir(), 'R1_PRODUCT_SOURCE_REGULAR_REQUIRED')
    require(actual == expected, 'R1_PRODUCT_SOURCE_CHANGED')
    prepared = {name: digest for name, digest in actual.items() if not name.endswith('.test.cjs')}
    prepared['app.js'] = value['connected_app_sha256']
    require(len(prepared) == 36, 'R1_PREPARED_SOURCE_SET_REQUIRED')
    return {'product_source_sha': SOURCE_SHA, 'control_source_sha': value['control_source_sha'],
            'source_root': str(destination), 'prepared_files': prepared, 'fixed_product': True,
            'backend_source_sha': SOURCE_SHA, 'compatibility': 'EXACT_SOURCE_MATCH'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('build', 'stage', 'identity'))
    args = parser.parse_args()
    env = os.environ
    if args.operation == 'identity':
        print(json.dumps(identity(env), sort_keys=True))
        return
    control_context(env)
    if args.operation == 'build':
        require(not Path('r1-mini-source.zip').exists() and not Path('r1-mini-receipt.json').exists(),
                'R1_ADMISSION_OUTPUT_ALREADY_EXISTS')
        raw, files = build_archive()
        value = receipt(raw, files, env)
        write_new('r1-mini-source.zip', raw)
        write_new('r1-mini-receipt.json', (json.dumps(value, sort_keys=True) + '\n').encode())
        print('R1_MINI_EXACT_INPUT_VERIFIED_NO_UPLOAD')
    else:
        root = Path(env['RUNNER_TEMP']) / ('community-mini-r1-input-' + env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT'])
        stage(read_regular(root / 'r1-mini-source.zip'),
              strict_json(read_regular(root / 'r1-mini-receipt.json', 16384)), env)
        print('R1_MINI_EXACT_INPUT_STAGED_NO_UPLOAD')


if __name__ == '__main__':
    main()
