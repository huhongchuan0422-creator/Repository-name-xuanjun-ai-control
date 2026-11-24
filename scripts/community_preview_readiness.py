"""Read-only allowlisted-target health gate before credentialed preview upload.

This proves connectivity only, not real login, merchant admission or acceptance.
"""
import hashlib, json, os, re, time
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ORIGIN='https://community-preview.wenwenwenyiyiyi.work'
URL=ORIGIN+'/community/health'

FIXED_FRONTEND = '4f1c3aea2c01ead25c5bd075535b8ce7bd9cd5f5'
FIXED_BACKEND = '4f1c3aea2c01ead25c5bd075535b8ce7bd9cd5f5'
FIXED_PROOF_SHA256 = '548d9cd1c92d14ad848cb83205338333ecda0dd45718f0df7de4831063d61367'
FIXED_COMPATIBILITY = 'EXACT_SOURCE_MATCH'
CURRENT_FRONTEND = 'b024a90465205e18dedf3f7296a470ae7035c30a'
CURRENT_BACKEND = 'b024a90465205e18dedf3f7296a470ae7035c30a'
CURRENT_COMPATIBILITY = 'EXACT_SOURCE_MATCH'

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
        snapshot=None
        expected_backend=head
        compatibility='EXACT_SOURCE_MATCH'
        if product_identity and product_identity.get('fixed_product'):
            legacy = (head == FIXED_FRONTEND and product_identity.get('backend_source_sha') == FIXED_BACKEND
                      and product_identity.get('compatibility') == FIXED_COMPATIBILITY
                      and product_identity.get('compatibility_sha256') == FIXED_PROOF_SHA256)
            exact_source = (head == product_identity.get('backend_source_sha')
                            and product_identity.get('compatibility') == 'EXACT_SOURCE_MATCH'
                            and 'compatibility_sha256' not in product_identity)
            current = (head == CURRENT_FRONTEND
                       and product_identity.get('backend_source_sha') == CURRENT_BACKEND
                       and product_identity.get('compatibility') == CURRENT_COMPATIBILITY
                       and 'compatibility_sha256' not in product_identity)
            snapshot = product_identity.get('snapshot_binding')
            if snapshot:
                if head!=snapshot['manifest_sha256'] or product_identity['control_source_sha']!=snapshot['control_source_sha']:return report
                report.update(frontend_manifest_sha256=head,frontend_archive_sha256=snapshot['archive_sha256'],compatibility_evidence_sha256=snapshot['compatibility_evidence_sha256'])
            if not (legacy or exact_source or current or snapshot):return report
            expected_backend=product_identity['backend_source_sha']
            compatibility='EXACT_REVIEWED_SNAPSHOT_BACKEND_PAIR' if snapshot else CURRENT_COMPATIBILITY if current else 'EXACT_SOURCE_MATCH'
            if legacy:report['compatibility_sha256']=FIXED_PROOF_SHA256
        if not re.fullmatch('[0-9a-f]{64}' if product_identity and product_identity.get('snapshot_binding') else '[0-9a-f]{40}',head or ''):return report
        url=target['health_url']
        with opener(Request(url,headers={'Accept':'application/json'}),timeout=10) as response:
            report['http_status']=response.status
            if response.status!=200 or response.geturl()!=url:return report
            if response.headers.get_content_type()!='application/json':return report
            budget=65536 if product_identity and product_identity.get('snapshot_binding') else 4096
            raw=response.read(budget+1)
            if len(raw)>budget:return report
            value=json.loads(raw)
            if (type(value) is not dict or value.get('status')!='READY'
                    or value.get('scope')!='PROCESS_AND_DATABASE_CONNECTIVITY'
                    or value.get('production_acceptance') is not False):return report
            # Only the responding runtime supplies the backend SHA. Only the exact source equality or independently pinned native/backend pair
            # is admitted; no arbitrary cross-version allowance.
            backend=value.get('runtime_source_sha')
            report['backend_source_sha']=backend if type(backend) is str and re.fullmatch('[0-9a-f]{40}',backend) else None
            now=int(time.time());observed=value.get('observed_at')
            version=value.get('version_source')
            if version=='NATIVE_PROCESS_ENV_BASELINE_WITH_STARTUP_SOURCE_PINS':
                # Exact installed native coverage only; never treat baseline as overlay revision.
                contract=json.loads((Path(__file__).resolve().parents[1]/'deploy/community-preview/native-snapshot-version.json').read_text())
                pins=value.get('startup_source_pins')
                if not snapshot or head!=contract['frontend_manifest_sha256'] or snapshot['archive_sha256']!=contract['frontend_archive_sha256'] or expected_backend!=contract['runtime_source_sha']:return report
                if value.get('source_coverage')!=contract['source_coverage'] or value.get('startup_source_manifest_sha256')!=contract['startup_source_manifest_sha256']:return report
                if type(pins) is not dict or not pins or any(type(k) is not str or type(v) is not str or not re.fullmatch('[0-9a-f]{64}',v) for k,v in pins.items()):return report
                if hashlib.sha256(json.dumps(pins,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=contract['startup_source_manifest_sha256']:return report
                report.update(source_coverage=value['source_coverage'],startup_source_manifest_sha256=value['startup_source_manifest_sha256'],startup_source_pins=pins)
            elif version!='IMAGE_BUILD_STAMP':return report
            if (report['backend_source_sha']!=expected_backend
                    or type(observed) is not int or observed>now+30 or now-observed>600):return report
            report.update(observed_at=now,backend_observed_at=observed,
                          backend_version_source=version,compatibility=compatibility)
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
    kind=os.environ.get('COMMUNITY_FIXED_PRODUCT_KIND','legacy-4f')
    if kind not in ('legacy-4f','r1-7ca1ac2a','current-48df','hangzhou-snapshot'):raise SystemExit('FIXED_PRODUCT_KIND_REQUIRED')
    helper=('community_mini_snapshot_input.py' if kind=='hangzhou-snapshot' else 'community_mini_r1_input.py' if kind=='r1-7ca1ac2a' else
            'community_mini_current_input.py' if kind=='current-48df' else
            'community_preview_fixed_product.py')
    spec=importlib.util.spec_from_file_location('fixed_product',Path(__file__).with_name(helper))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    report=check(product_identity=helper.identity(os.environ))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    output.write_text(json.dumps(report,sort_keys=True)+'\n');output.chmod(0o600)
    print('PREVIEW_BACKEND_STATUS='+report['status'])
    raise SystemExit(0 if report['status']=='BACKEND_HEALTH_VERIFIED' else 2)

