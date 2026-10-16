#!/usr/bin/env python3
"""Zero-model pull of approved PR122 publication events. Never executes fetched code."""
import argparse
import io
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from scripts import pr122_showcase_promote as promote
from scripts.pr122_showcase import need,sha


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def artifact_package(identifier,token):
    # Never forward the GitHub credential to the object-storage redirect.
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/artifacts/'+str(identifier)+'/zip'
    request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+token,'User-Agent':'XuanJun-Showcase-Publisher'})
    opener=urllib.request.build_opener(NoRedirect)
    try:response=opener.open(request,timeout=20)
    except urllib.error.HTTPError as error:
        need(error.code in (302,303,307),'ARTIFACT_DOWNLOAD_FAILED')
        redirect=error.headers['Location'];parsed=urllib.parse.urlsplit(redirect)
        need(parsed.scheme=='https' and parsed.hostname and (parsed.hostname.endswith('.blob.core.windows.net') or parsed.hostname.endswith('.amazonaws.com') or parsed.hostname.endswith('.githubusercontent.com')),'UNTRUSTED_ARTIFACT_REDIRECT')
        response=urllib.request.urlopen(urllib.request.Request(redirect,headers={'User-Agent':'XuanJun-Showcase-Publisher'}),timeout=30)
    with response:
        raw=response.read(20000001);need(len(raw)<=20000000,'ARTIFACT_ZIP_LIMIT')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        need(len(archive.infolist())<=100,'ARTIFACT_MEMBER_LIMIT')
        matches=[i for i in archive.infolist() if i.filename=='SHOWCASE_RELEASE.tar.gz']
        need(len(matches)==1 and matches[0].file_size<=16000000,'SHOWCASE_ARTIFACT_MEMBER')
        return archive.read(matches[0])


def poll(policy,engine=None,fetch=promote.github,download=artifact_package):
    engine=engine or promote.load_engine()
    marker=promote.BASE/'AUTOMATION_HOLD.json'
    if marker.exists():
        engine.read_trusted_bytes(marker,0)
        raise ValueError('OPERATOR_RECOVERY_REQUIRED_NO_NETWORK_OR_RETRY')
    # Incomplete/unknown transactions stop automation rather than being retried.
    if (promote.BASE/'transactions').exists():
        for path in (promote.BASE/'transactions').glob('*.json'):
            raw,_=engine.read_trusted_bytes(path,0);r=json.loads(raw)
            artifact_id=int(path.stem.removeprefix('showcase-'))
            recovery=promote.BASE/'inputs'/path.stem/'RECOVERY.json'
            if recovery.exists():
                data,_=engine.read_trusted_bytes(recovery,0)
                if json.loads(data).get('state')=='ABORTED_BEFORE_ACTIVATION':continue
            need(r['state'] in ('CHECKED','ROLLED_BACK'),'UNKNOWN_TRANSACTION_REQUIRES_OPERATOR:'+path.stem)
            if r['state']=='CHECKED':
                success=promote.BASE/'inputs'/path.stem/'HTTPS_RECEIPT.json'
                need(success.is_file(),'HTTPS_RESULT_UNKNOWN_REQUIRES_OPERATOR:'+path.stem)
    token_path=Path(policy['github_token_file']);raw,_=engine.read_trusted_bytes(token_path,0)
    need((token_path.stat().st_mode&0o077)==0,'TOKEN_MODE_MUST_BE_PRIVATE')
    token=raw.decode().strip();need(token and '\n' not in token,'READONLY_ACTIONS_TOKEN_REQUIRED')
    if fetch is promote.github:
        def authenticated(path):
            from scripts.pr122_showcase_sources import REPO
            request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'XuanJun-Showcase-Publisher'})
            with urllib.request.urlopen(request,timeout=20) as response:
                raw=response.read(4000001);need(len(raw)<=4000000,'GITHUB_RESPONSE_LIMIT');return json.loads(raw)
        fetch=authenticated
    comments=[]
    for page in range(1,21):
        batch=fetch('issues/122/comments?per_page=100&page='+str(page));need(type(batch) is list,'COMMENT_RESPONSE')
        comments.extend(batch)
        if len(batch)<100:break
    else:raise ValueError('COMMENT_HISTORY_LIMIT')
    candidates=[c for c in comments if c['user']['login'] in policy['publishers'] and c['body'].startswith('XUANJUN_SHOWCASE_RELEASE\n')]
    for comment in sorted(candidates,key=lambda c:c['id']):
        gate=json.loads(comment['body'].split('\n',1)[1]);identifier=gate.get('artifact_id')
        need(type(identifier) is int and identifier>0,'ARTIFACT_ID')
        folder=promote.BASE/'inputs'/('showcase-'+str(identifier))
        if folder.exists():continue  # Consumed permit; never reapply this artifact.
        if gate.get('expires_unix',0)<=__import__('time').time():continue
        gate=promote.approval(comment['id'],policy,fetch)
        package=download(identifier,token);need(sha(package)==gate['tar_sha256'],'DOWNLOADED_PACKAGE_HASH')
        return promote.publish(package,gate,engine)
    return {'state':'NO_NEW_APPROVED_RELEASE','production_changes':0}


def main():
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','FIXED_HOST_ROOT_REQUIRED')
    engine=promote.load_engine();raw,_=engine.read_trusted_bytes(promote.POLICY,0);policy=json.loads(raw)
    os.umask(0o022)
    # Nonblocking process lock also fences the interval before publisher.prepare.
    import fcntl
    engine.secure_dir(promote.BASE,0o755,0,True)
    path=promote.BASE/'poll.lock';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        need(os.fstat(fd).st_uid==0 and __import__('stat').S_ISREG(os.fstat(fd).st_mode),'POLL_LOCK_IDENTITY')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:print(json.dumps(poll(policy,engine),sort_keys=True))
        except BaseException as error:
            marker=promote.BASE/'AUTOMATION_HOLD.json'
            if not marker.exists():engine.atomic_json(marker,{'state':'HOLD_REQUIRES_OPERATOR','failure_class':type(error).__name__,'fingerprint':sha((type(error).__name__+str(error)).encode()),'created_unix':int(__import__('time').time()),'automatic_retry':False})
            raise
    finally:os.close(fd)

if __name__=='__main__':main()
