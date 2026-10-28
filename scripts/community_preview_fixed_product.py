"""Fixed f131 product admission for the ORIGINAL preview workflow, never deployment.
GITHUB_SHA remains the control revision. No arbitrary artifact/ref/product is accepted.
"""
import argparse, datetime, hashlib, io, json, os, re, stat, tempfile, time, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BRANCH = 'feature/chatgpt-community-wechat-sp-offline-20261017'
WORKFLOW = '.github/workflows/chatgpt-community-wechat-sp-offline.yml'
PRODUCT_SHA = 'f13155ed63a3137d41766ee587d9b4b96a81477f'
PRODUCT_RUN = 40058542631
PRODUCT_JOB = 120766815688
ARTIFACT_ID = 12546258346
ARTIFACT_SIZE = 992283
ARTIFACT_SHA256 = '21c15e3bb8ff1bb2b54ba3f7d950eea5b96cc62df98d94ee2155d4fff146b0ec'
SOURCE_SHA256 = '125ec8633e173d582d5ca5cd3dccc21d2d97104723fb61a136911c48e12d47d1'
MANIFEST_SHA256 = '5dc52185ab0b7cb9eecaea59da6e57de20dcad051547361530bf6ee75405f9e8'
APPID = 'wx1d5f8873eaea5392'
PROFILE = 'uk-path-candidate'
BASE_URL = 'https://uk.wenwenwenyiyiyi.work/community-preview'
CONNECTED_APP_SHA256 = '07eaedb76bc73f278eeab7235cf2f921cee0c875f890fdc26c82fb4e4699b42e'
MAX_BYTES = 20000000

def require(value, message):
    if not value:
        raise ValueError(message)

def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs)

def context(env):
    control = env.get('GITHUB_SHA', '')
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == REPO
            and env.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and re.fullmatch('[0-9a-f]{40}', control)
            and env.get('PREVIEW_CONTROL_SHA') == control
            and env.get('PREVIEW_SOURCE_SHA') == PRODUCT_SHA
            and env.get('PREVIEW_TARGET') == PROFILE
            and env.get('PREVIEW_EVIDENCE_RUN_ID') == str(PRODUCT_RUN)
            and env.get('PREVIEW_ENABLED') == 'true'
            and env.get('IMAGE_BUILD_ENABLED', 'false') == 'false'
            and re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', ''))
            and re.fullmatch('[1-9][0-9]{0,9}', env.get('GITHUB_RUN_ATTEMPT', ''))
            and env.get('GITHUB_RUN_ID') != str(PRODUCT_RUN),
            'EXACT_FIXED_PRODUCT_CONTROL_CONTEXT_REQUIRED')
    return control

def evidence(run, jobs, artifacts, env, now=None):
    control = context(env)
    now = time.time() if now is None else now
    require(run.get('id') == PRODUCT_RUN and run.get('head_sha') == PRODUCT_SHA
            and run.get('head_branch') == BRANCH and run.get('path') == WORKFLOW
            and run.get('event') == 'push' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success'
            and run.get('repository', {}).get('full_name') == REPO
            and run.get('head_repository', {}).get('full_name') == REPO,
            'FIXED_PRODUCT_PUSH_EVIDENCE_REQUIRED')
    require(type(jobs.get('total_count')) is int and jobs['total_count'] <= 100
            and type(artifacts.get('total_count')) is int and artifacts['total_count'] <= 100,
            'BOUNDED_COMPLETE_EVIDENCE_REQUIRED')
    require(len(jobs.get('jobs', [])) == jobs['total_count']
            and len(artifacts.get('artifacts', [])) == artifacts['total_count'],
            'COMPLETE_EVIDENCE_PAGE_REQUIRED')
    selected = [j for j in jobs['jobs'] if j.get('name') == 'test']
    require(len(selected) == 1 and selected[0].get('id') == PRODUCT_JOB
            and selected[0].get('status') == 'completed'
            and selected[0].get('conclusion') == 'success'
            and any(s.get('name') == 'Preview entry evidence affected scope (offline only)'
                    and s.get('status') == 'completed' and s.get('conclusion') == 'success'
                    for s in selected[0].get('steps', [])), 'FIXED_PRODUCT_TEST_REQUIRED')
    selected = [a for a in artifacts['artifacts']
                if a.get('name') == 'community-phase-integration-evidence']
    require(len(selected) == 1, 'ONE_FIXED_SOURCE_ARTIFACT_REQUIRED')
    a = selected[0]
    binding = a.get('workflow_run', {})
    expiry = datetime.datetime.strptime(a.get('expires_at', ''), '%Y-%m-%dT%H:%M:%SZ').replace(
        tzinfo=datetime.timezone.utc).timestamp()
    require(a.get('id') == ARTIFACT_ID and a.get('expired') is False and expiry > now
            and a.get('size_in_bytes') == ARTIFACT_SIZE
            and a.get('digest') == 'sha256:' + ARTIFACT_SHA256
            and binding.get('id') == PRODUCT_RUN and binding.get('head_sha') == PRODUCT_SHA
            and binding.get('head_branch') == BRANCH
            and binding.get('repository_id') == 1413132159
            and binding.get('head_repository_id') == 1413132159,
            'FIXED_UNEXPIRED_ARTIFACT_BINDING_REQUIRED')
    return dict(status='FIXED_F131_PRODUCT_EVIDENCE_VERIFIED', control_source_sha=control,
                product_source_sha=PRODUCT_SHA, product_run_id=PRODUCT_RUN,
                product_test_job_id=PRODUCT_JOB, artifact_id=ARTIFACT_ID,
                artifact_sha256=ARTIFACT_SHA256, source_zip_sha256=SOURCE_SHA256,
                source_manifest_sha256=MANIFEST_SHA256, expires_at=a['expires_at'],
                workflow_run_id=env['GITHUB_RUN_ID'],
                workflow_run_attempt=env['GITHUB_RUN_ATTEMPT'],
                appid=APPID, profile=PROFILE, baseUrl=BASE_URL,
                artifact_bytes_reverified=True, upload_performed=False)

def source_files(raw):
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256, 'FIXED_PRODUCT_SOURCE_SHA_REQUIRED')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        items = z.infolist()
        require(0 < len(items) < 2000 and len(items) == len({i.filename for i in items})
                and sum(i.file_size for i in items) < 10000000, 'BOUNDED_SOURCE_REQUIRED')
        manifest_raw = z.read('MANIFEST.json')
        require(hashlib.sha256(manifest_raw).hexdigest() == MANIFEST_SHA256,
                'FIXED_PRODUCT_MANIFEST_SHA_REQUIRED')
        manifest = strict_json(manifest_raw)
        require(manifest.get('format') == 1
                and manifest.get('purpose') == 'OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE'
                and manifest.get('production_payment') == 'HOLD'
                and manifest.get('production_deployment') == 'HOLD'
                and set(z.namelist()) == set(manifest['files']) | {'MANIFEST.json'},
                'COMPLETE_PRODUCT_MANIFEST_REQUIRED')
        files = {}
        for item in items:
            p = PurePosixPath(item.filename)
            require(not p.is_absolute() and '..' not in p.parts and chr(92) not in item.filename
                    and str(p) == item.filename and stat.S_ISREG(item.external_attr >> 16),
                    'SAFE_REGULAR_PRODUCT_FILE_REQUIRED')
            data = z.read(item)
            require(item.filename == 'MANIFEST.json'
                    or hashlib.sha256(data).hexdigest() == manifest['files'][item.filename],
                    'PRODUCT_FILE_SHA_REQUIRED')
            files[item.filename] = data
    config = strict_json(files['clients/community-mini/project.config.json'])
    require(config.get('appid') == APPID and config.get('compileType') == 'miniprogram'
            and config.get('miniprogramRoot') == './', 'FIXED_PRODUCT_APPID_REQUIRED')
    require(strict_json(files['deploy/community-preview/endpoint-profiles.json']).get(PROFILE) == BASE_URL,
            'FIXED_PRODUCT_ENDPOINT_REQUIRED')
    return files

def archive_source(raw):
    require(len(raw) == ARTIFACT_SIZE and hashlib.sha256(raw).hexdigest() == ARTIFACT_SHA256,
            'FIXED_ARTIFACT_BYTES_SHA_REQUIRED')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(len(z.infolist()) == 2
                and set(z.namelist()) == {'community-tests.log', 'community-stage-source.zip'},
                'FIXED_ARTIFACT_MEMBERS_REQUIRED')
        source = z.read('community-stage-source.zip')
    source_files(source)
    return source

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def read_api(suffix):
    url = 'https://api.github.com/repos/' + REPO + suffix
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers={'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'community-fixed-product-preview'}), timeout=10) as r:
        require(r.status == 200 and r.geturl() == url, 'EXACT_GITHUB_RESPONSE_REQUIRED')
        data = r.read(1048577)
        require(len(data) <= 1048576, 'EVIDENCE_SIZE_LIMIT')
        return strict_json(data)

def download_archive(token):
    # The repository token is used ONLY for this fixed GitHub API request.
    # Signed storage GET never receives Authorization; redirects are not followed.
    from urllib.error import HTTPError
    require(bool(token), 'EXISTING_GITHUB_TOKEN_REQUIRED')
    url = 'https://api.github.com/repos/' + REPO + '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip'
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(Request(url, headers={'Authorization': 'Bearer ' + token,
                              'Accept': 'application/vnd.github+json'}), timeout=10)
    except HTTPError as exc:
        require(exc.code == 302, 'FIXED_ARTIFACT_REDIRECT_REQUIRED')
        location = exc.headers.get('Location', '')
        exc.close()
    else:
        response.close()
        raise ValueError('FIXED_ARTIFACT_REDIRECT_REQUIRED')
    parsed = urlparse(location)
    require(parsed.scheme == 'https' and parsed.hostname
            and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and not parsed.fragment
            and any(parsed.hostname.endswith(s) for s in (
                '.blob.core.windows.net', '.actions.githubusercontent.com',
                '.githubusercontent.com', '.s3.amazonaws.com')),
            'GITHUB_ARTIFACT_STORAGE_REQUIRED')
    with opener.open(Request(location), timeout=30) as r:
        require(r.status == 200 and r.geturl() == location, 'ARTIFACT_RESPONSE_REQUIRED')
        data = r.read(MAX_BYTES + 1)
        require(len(data) <= MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
        return data

def write_new(path, data):
    with open(path, 'xb') as f:
        os.chmod(path, 0o600)
        f.write(data)

def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'REGULAR_INPUT_REQUIRED')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read(limit + 1)
        require(len(data) <= limit, 'INPUT_SIZE_LIMIT')
        return data
    finally:
        os.close(fd)

def paths(env):
    suffix = env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT']
    temp = Path(env['RUNNER_TEMP']).resolve()
    return temp / ('community-mini-product-source-' + suffix), temp / ('community-mini-product-context-' + suffix + '.json')

def verify_receipt(receipt, env):
    control = context(env)
    require(receipt.get('status') == 'FIXED_F131_PRODUCT_EVIDENCE_VERIFIED'
            and receipt.get('control_source_sha') == control
            and receipt.get('product_source_sha') == PRODUCT_SHA
            and receipt.get('product_run_id') == PRODUCT_RUN
            and receipt.get('product_test_job_id') == PRODUCT_JOB
            and receipt.get('artifact_id') == ARTIFACT_ID
            and receipt.get('artifact_sha256') == ARTIFACT_SHA256
            and receipt.get('source_zip_sha256') == SOURCE_SHA256
            and receipt.get('source_manifest_sha256') == MANIFEST_SHA256
            and receipt.get('workflow_run_id') == env['GITHUB_RUN_ID']
            and receipt.get('workflow_run_attempt') == env['GITHUB_RUN_ATTEMPT']
            and receipt.get('appid') == APPID and receipt.get('profile') == PROFILE
            and receipt.get('baseUrl') == BASE_URL and receipt.get('artifact_bytes_reverified') is True
            and receipt.get('upload_performed') is False, 'FIXED_PRODUCT_RECEIPT_REQUIRED')
    expiry = datetime.datetime.strptime(receipt.get('expires_at', ''), '%Y-%m-%dT%H:%M:%SZ').replace(
        tzinfo=datetime.timezone.utc).timestamp()
    require(expiry > time.time(), 'FIXED_PRODUCT_ARTIFACT_EXPIRED')
    return control

def stage(source, receipt, env):
    verify_receipt(receipt, env)
    files = source_files(source)
    destination, context_file = paths(env)
    require(not destination.exists() and not destination.is_symlink()
            and not context_file.exists() and not context_file.is_symlink(), 'PRODUCT_OUTPUT_ALREADY_EXISTS')
    import shutil
    temp = Path(tempfile.mkdtemp(prefix='.fixed-product-', dir=destination.parent))
    try:
        for name, data in files.items():
            p = temp / name
            p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_new(p, data)
        os.rename(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    receipt = dict(receipt, source_root=str(destination))
    write_new(context_file, (json.dumps(receipt, sort_keys=True) + '\n').encode())
    return receipt

def identity(env):
    require(env.get('COMMUNITY_FIXED_PRODUCT_PREVIEW', 'false') in ('true', 'false'), 'EXACT_PRODUCT_MODE_REQUIRED')
    if env.get('COMMUNITY_FIXED_PRODUCT_PREVIEW', 'false') != 'true':
        require(not env.get('COMMUNITY_PREVIEW_PRODUCT_CONTEXT'), 'UNEXPECTED_PRODUCT_CONTEXT')
        return dict(product_source_sha=env.get('GITHUB_SHA'), control_source_sha=env.get('GITHUB_SHA'),
                    source_root=None, fixed_product=False)
    destination, context_file = paths(env)
    require(env.get('COMMUNITY_PREVIEW_PRODUCT_CONTEXT') == str(context_file), 'EXACT_PRODUCT_CONTEXT_PATH_REQUIRED')
    receipt = strict_json(read_regular(context_file, 16384))
    verify_receipt(receipt, env)
    require(receipt.get('source_root') == str(destination) and not destination.is_symlink(),
            'EXACT_PRODUCT_SOURCE_ROOT_REQUIRED')
    manifest_raw = read_regular(destination / 'MANIFEST.json', 1000000)
    require(hashlib.sha256(manifest_raw).hexdigest() == MANIFEST_SHA256, 'FIXED_PRODUCT_MANIFEST_SHA_REQUIRED')
    manifest = strict_json(manifest_raw)['files']
    require(not (destination / 'clients').is_symlink(), 'PRODUCT_SOURCE_SYMLINK_DENIED')
    mini = destination / 'clients/community-mini'
    require(not mini.is_symlink() and mini.is_dir(), 'PRODUCT_SOURCE_SYMLINK_DENIED')
    expected = {k[len('clients/community-mini/'):]: v for k, v in manifest.items()
                if k.startswith('clients/community-mini/')}
    actual = {}
    for p in mini.rglob('*'):
        require(not p.is_symlink(), 'PRODUCT_SOURCE_SYMLINK_DENIED')
        if p.is_file():
            actual[p.relative_to(mini).as_posix()] = hashlib.sha256(read_regular(p, 10000000)).hexdigest()
        else:
            require(p.is_dir(), 'PRODUCT_SOURCE_REGULAR_REQUIRED')
    require(actual == expected, 'FIXED_PRODUCT_SOURCE_CHANGED')
    prepared = {k: v for k, v in expected.items() if not k.endswith('.test.cjs')}
    prepared['app.js'] = CONNECTED_APP_SHA256
    require(len(prepared) == 27, 'FIXED_PREPARED_SOURCE_SET_REQUIRED')
    return dict(product_source_sha=PRODUCT_SHA, control_source_sha=receipt['control_source_sha'],
                source_root=str(destination), prepared_files=prepared, fixed_product=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('admit', 'stage', 'identity'))
    args = parser.parse_args()
    env = os.environ
    if args.operation == 'identity':
        print(json.dumps(identity(env), sort_keys=True))
        return
    context(env)
    if args.operation == 'admit':
        require(not Path('fixed-product-source.zip').exists() and not Path('fixed-product-receipt.json').exists(),
                'PRODUCT_ADMISSION_OUTPUT_ALREADY_EXISTS')
        prefix = '/actions/runs/' + str(PRODUCT_RUN)
        receipt = evidence(read_api(prefix), read_api(prefix + '/jobs?per_page=100'),
                           read_api(prefix + '/artifacts?per_page=100'), env)
        source = archive_source(download_archive(env.get('GITHUB_TOKEN', '')))
        write_new('fixed-product-source.zip', source)
        write_new('fixed-product-receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode())
        print('FIXED_F131_PRODUCT_SOURCE_VERIFIED_NO_UPLOAD')
    else:
        root = Path(env['RUNNER_TEMP']) / ('community-mini-fixed-input-' + env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT'])
        stage(read_regular(root / 'fixed-product-source.zip', MAX_BYTES),
              strict_json(read_regular(root / 'fixed-product-receipt.json', 16384)), env)
        print('FIXED_F131_PRODUCT_STAGED_NO_UPLOAD')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('FIXED_PRODUCT_PREVIEW_ADMISSION_FAILED')

