"""Fetch SHA-pinned reviewed dependencies and original frozen102 fixtures.

    python bootstrap.py NEW_PRIVATE_DIRECTORY
No deployed code, services, Owner credentials, model or host operations.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
FIXTURE = {'execution_ledger.py': '8c607f0e2222d906b8450b302dad014a69dfedcb710a257731454e0d97aaf8c6',
           'activation_control.py': '169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4',
           'owner_dashboard.py': '12d39df66ad7cb66810ebd4dd84cc6b61981b8b597591880e39d4d29258f741d'}
TAR_SHA = 'c2d593d662fbce4a0c2fa454cc4a18dbec327c0bd0bf3d6d72849d9a5a79970d'


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('HTTPS_ONLY')
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            result.remove_header('Authorization')
        return result


def get(url, limit):
    if urllib.parse.urlsplit(url).netloc != 'api.github.com':
        raise ValueError('FIXED_GITHUB_SOURCE_REQUIRED')
    headers = {'User-Agent': 'xuanjun-work-foundation-fixture', 'Accept': 'application/vnd.github.raw+json'}
    token = os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.build_opener(Redirect()).open(urllib.request.Request(url, headers=headers), timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('FIXTURE_DOWNLOAD_BOUND')
    return data


def unpack_selected(archive, destination):
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        info = z.infolist()
        if len(info) > 10 or sum(x.file_size for x in info) > 20000000 or z.namelist().count('p2-candidate.tar.gz') != 1:
            raise ValueError('FIXTURE_ZIP_BOUND')
        data = z.read('p2-candidate.tar.gz')
    if hashlib.sha256(data).hexdigest() != TAR_SHA:
        raise ValueError('ORIGINAL102_ARCHIVE_HASH')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 500 or sum(m.size for m in members) > 30000000:
            raise ValueError('FIXTURE_TAR_BOUND')
        for name, expected in FIXTURE.items():
            path = 'xuanjun-p2-package/stage1/' + name
            matches = [m for m in members if m.name == path]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 1048576:
                raise ValueError('FIXTURE_MEMBER_IDENTITY')
            content = tar.extractfile(matches[0]).read(1048577)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('FIXTURE_MEMBER_HASH')
            # Only exact known basenames; never extract arbitrary archive paths.
            with (destination / name).open('xb') as stream:
                stream.write(content)


def main(directory):
    root = Path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for item in json.loads(Path(__file__).with_name('pins.json').read_text()):
        url = 'https://api.github.com/repos/{}/contents/{}?ref={}'.format(REPO, item['path'], item['commit'])
        content = get(url, 262144)
        if hashlib.sha256(content).hexdigest() != item['sha256']:
            raise ValueError('FOUNDATION_HASH_MISMATCH')
        with (root / item['name']).open('xb') as stream:
            stream.write(content)
    unpack_selected(get('https://api.github.com/repos/' + REPO + '/actions/artifacts/11865804223/zip', 16777216), root)
    print('EXACT_FOUNDATION_AND_ORIGINAL102_TEST_FIXTURES_READY_NOT_INSTALLED_ACCEPTANCE')


if __name__ == '__main__':
    main(sys.argv[1])
