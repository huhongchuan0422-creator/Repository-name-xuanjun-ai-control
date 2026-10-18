"""Publish only the already-pinned public-source ZIP; never UK execution."""
import importlib.util
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('delivery',str(HERE/'prepare.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
raw=d.download(artifact_api=True)
d.verify(raw)
base='https://api.github.com/repos/'+d.REPO
token=os.environ['GH_TOKEN']
tag='p2-owner-6041-preparation'
headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
    'User-Agent':'p2-pinned-public-source-delivery'}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),d.NoRedirect())
def request(url,value=None,missing=False,binary=False):
    body=value if binary else (json.dumps(value).encode() if value is not None else None)
    h=dict(headers)
    if body is not None:h['Content-Type']='application/zip' if binary else 'application/json'
    try:
        with opener.open(urllib.request.Request(url,data=body,headers=h),timeout=60) as response:
            return json.loads(d.read_bound(response,1024*1024).decode())
    except urllib.error.HTTPError as e:
        if missing and e.code==404:return None
        raise RuntimeError('PUBLIC_DELIVERY_HTTP_'+str(e.code)) from None
release=request(base+'/releases/tags/'+tag,missing=True)
if release is None:
    release=request(base+'/releases',{
        'tag_name':tag,'target_commitish':d.COMMIT,'name':'P2 6041 pinned preparation package',
        'body':'Public source delivery only. Runtime '+d.COMMIT+
            '. Exact original Artifact12142409951 ZIP SHA256 '+d.ZIP_SHA+
            '. Owner preparation only; UK installation NOT_EXECUTED; P2_RELEASE=HOLD.',
        'draft':False,'prerelease':True,'make_latest':'false'})
d.need(release['tag_name']==tag and release['prerelease'] is True and
    release['draft'] is False,'RELEASE_IDENTITY')
ref=request(base+'/git/ref/tags/'+tag)
d.need(ref['object']['type']=='commit' and ref['object']['sha']==d.COMMIT,'RELEASE_SOURCE_TAG')
assets=request(base+'/releases/'+str(release['id'])+'/assets')
name='p2-12142409951.zip'
matches=[a for a in assets if a['name']==name]
d.need(len(matches)<=1,'DUPLICATE_RELEASE_ASSET')
if matches:asset=matches[0]
else:
    url='https://uploads.github.com/repos/'+d.REPO+'/releases/'+str(release['id'])+'/assets?name='+name
    asset=request(url,raw,binary=True)
d.need(asset['name']==name and asset['size']==len(raw) and
    asset.get('digest')=='sha256:'+d.ZIP_SHA,'PUBLIC_ASSET_DIGEST')
expected='https://github.com/'+d.REPO+'/releases/download/'+tag+'/'+name
d.need(asset['browser_download_url']==expected,'PUBLIC_ASSET_URL')
# Verify anonymously through the exact Owner path, not just the upload response.
public=d.download()
d.need(public==raw,'PUBLIC_DOWNLOAD_BYTES')
print('PUBLIC_DELIVERY='+json.dumps({'url':expected,'zip_sha256':d.ZIP_SHA,
    'asset_id':asset['id'],'runtime_commit':d.COMMIT,'uk_execution':'NOT_EXECUTED'},sort_keys=True))
