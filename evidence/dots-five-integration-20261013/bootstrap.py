"""Download exact historical fixtures; no host services, credentials or install."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
TAR_SHA='25999a0491a94ce8b9c1c24262ccba38bdfc737e32193ae2825c7de9202a205b'

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise ValueError('HTTPS_ONLY')
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            result.remove_header('Authorization')
        return result


def get(url, limit, token=None):
    headers={'User-Agent':'xuanjun-pinned-fixture'}
    if token:
        if urllib.parse.urlparse(url).netloc != 'api.github.com':raise ValueError('TOKEN_HOST')
        headers['Authorization']='Bearer '+token
    request=urllib.request.Request(url,headers=headers)
    with urllib.request.build_opener(Redirect()).open(request,timeout=30) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('DOWNLOAD_BOUND')
    return data


def main(root):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=False)
    deps=root/'dependencies';deps.mkdir()
    for item in json.loads(Path(__file__).with_name('dependencies.json').read_text()):
        url='https://raw.githubusercontent.com/{}/{}/{}'.format(REPOSITORY,item['commit'],item['path'])
        data=get(url,262144)
        if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('DEPENDENCY_HASH')
        (deps/item['name']).write_bytes(data)
    archive=get('https://api.github.com/repos/'+REPOSITORY+'/actions/artifacts/11786072168/zip',8388608,os.environ.get('GH_TOKEN'))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        items=z.infolist()
        if len(items)>10 or sum(i.file_size for i in items)>10000000:raise ValueError('ZIP_BOUND')
        if [i.filename for i in items].count('p2-candidate.tar.gz')!=1:raise ValueError('ZIP_IDENTITY')
        data=z.read('p2-candidate.tar.gz')
    if hashlib.sha256(data).hexdigest()!=TAR_SHA:raise ValueError('TAR_HASH')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
        members=tar.getmembers()
        if len(members)>300 or sum(m.size for m in members)>20000000:raise ValueError('TAR_BOUND')
        seen=set()
        for m in members:
            p=PurePosixPath(m.name)
            if p.is_absolute() or '..' in p.parts or not (m.isfile() or m.isdir()) or m.name in seen:
                raise ValueError('UNSAFE_ARCHIVE_MEMBER')
            seen.add(m.name)
        for m in members:
            target=root.joinpath(*PurePosixPath(m.name).parts)
            if m.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(tar.extractfile(m).read())
    print('PINNED_HISTORICAL_FIXTURES_READY_NOT_CURRENT_P2_ACCEPTANCE')

if __name__=='__main__':main(sys.argv[1])
