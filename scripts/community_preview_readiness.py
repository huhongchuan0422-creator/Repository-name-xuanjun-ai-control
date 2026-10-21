"""Read-only allowlisted-target health gate before credentialed preview upload.

This proves connectivity only, not real login, merchant admission or acceptance.
"""
import json, os, time
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

ORIGIN='https://community-preview.wenwenwenyiyiyi.work'
URL=ORIGIN+'/community/health'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def target_for(profile):
    expected = {
        'legacy': 'https://community-preview.wenwenwenyiyiyi.work',
        'uk-path-candidate': 'https://uk.wenwenwenyiyiyi.work/community-preview',
    }
    profiles = json.loads((Path(__file__).resolve().parents[1] /
                          'deploy/community-preview/endpoint-profiles.json').read_text())
    if type(profile) is not str or profile not in expected or profiles != expected:
        raise ValueError('EXACT_PREVIEW_PROFILE_REQUIRED')
    base = profiles[profile]
    origin = 'https://' + base.split('/')[2]
    return dict(profile=profile, baseUrl=base, origin=origin,
                health_url=base+'/community/health')

def check(open_url=None, profile=None):
    opener=open_url or build_opener(NoRedirect()).open
    report=dict(origin=ORIGIN,status='BACKEND_NOT_READY',login_verified=False,
                customer_acceptance=False,payment_enabled=False)
    try:
        target=target_for(profile if profile is not None else os.environ.get('COMMUNITY_PREVIEW_PROFILE','legacy'))
        report.update(target,source_sha=os.environ.get('GITHUB_SHA'),observed_at=int(time.time()))
        url=target['health_url']
        with opener(Request(url,headers={'Accept':'application/json'}),timeout=10) as response:
            report['http_status']=response.status
            if response.status!=200 or response.geturl()!=url:return report
            if response.headers.get_content_type()!='application/json':return report
            raw=response.read(4097)
            if len(raw)>4096:return report
            value=json.loads(raw)
            if (type(value) is not dict or value.get('status')!='READY'
                    or value.get('scope')!='PROCESS_AND_DATABASE_CONNECTIVITY'
                    or value.get('production_acceptance') is not False):return report
            report['status']='BACKEND_HEALTH_VERIFIED'
    except Exception:
        # Never print remote content, exception text or credentials.
        pass
    return report

if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();report=check()
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    output.write_text(json.dumps(report,sort_keys=True)+'\n');output.chmod(0o600)
    print('PREVIEW_BACKEND_STATUS='+report['status'])
    raise SystemExit(0 if report['status']=='BACKEND_HEALTH_VERIFIED' else 2)
