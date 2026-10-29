"""Read-only allowlisted-target health gate before credentialed preview upload.

This proves connectivity only, not real login, merchant admission or acceptance.
"""
import json, os, re, time
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

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

def check(open_url=None, profile=None, product_identity=None):
    opener=open_url or build_opener(ProxyHandler({}), NoRedirect()).open
    report=dict(origin=ORIGIN,status='BACKEND_NOT_READY',login_verified=False,
                customer_acceptance=False,payment_enabled=False)
    try:
        target=target_for(profile if profile is not None else os.environ.get('COMMUNITY_PREVIEW_PROFILE','legacy'))
        head=(product_identity['product_source_sha'] if product_identity else os.environ.get('GITHUB_SHA'))
        if product_identity and product_identity['fixed_product']:
            report['control_source_sha']=product_identity['control_source_sha']
        report.update(target,frontend_source_sha=head,compatibility='UNVERIFIED')
        if not re.fullmatch('[0-9a-f]{40}',head or ''):return report
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
            # Only the responding runtime supplies the backend SHA. This version
            # admits exact source equality; no unreviewed cross-version pair.
            backend=value.get('runtime_source_sha')
            report['backend_source_sha']=backend if type(backend) is str and re.fullmatch('[0-9a-f]{40}',backend) else None
            now=int(time.time());observed=value.get('observed_at')
            if (report['backend_source_sha']!=head or value.get('version_source')!='IMAGE_BUILD_STAMP'
                    or type(observed) is not int or observed>now+30 or now-observed>600):return report
            report.update(observed_at=now,backend_observed_at=observed,
                          backend_version_source='IMAGE_BUILD_STAMP',compatibility='EXACT_SOURCE_MATCH')
            report['status']='BACKEND_HEALTH_VERIFIED'
    except Exception:
        # Never print remote content, exception text or credentials.
        pass
    return report

if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args()
    # -I keeps imports isolated; load only our checked-out adjacent control helper.
    import importlib.util
    spec=importlib.util.spec_from_file_location('fixed_product',Path(__file__).with_name('community_preview_fixed_product.py'))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    report=check(product_identity=helper.identity(os.environ))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    output.write_text(json.dumps(report,sort_keys=True)+'\n');output.chmod(0o600)
    print('PREVIEW_BACKEND_STATUS='+report['status'])
    raise SystemExit(0 if report['status']=='BACKEND_HEALTH_VERIFIED' else 2)
