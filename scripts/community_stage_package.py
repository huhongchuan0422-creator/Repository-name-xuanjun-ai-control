"""Deterministic allowlisted offline review package; never an installer."""
import hashlib
import io
import json
import zipfile
from pathlib import Path


def build(root):
    root = Path(root)
    patterns = ('scripts/community_*.py', 'scripts/community_*.cjs', 'tests/test_community_*.py',
                'tests/test_community_*.mjs', 'tests/community_*.cjs',
                'tests/test_stage5_*.py', 'demos/community-local-e2e/*',
                'demos/community-stage/*', 'demos/community-stage/ui-preview/*', 'demos/community-payment/*',
                'demos/community-admin/*', 'clients/community-mini/*.js',
                'clients/community-mini/*.json', 'clients/community-mini/*.cjs',
                'clients/community-mini/*.wxss',
                'clients/community-mini/pages/checkout/*',
                'clients/community-mini/pages/home/*',
                'clients/community-mini/pages/profile/*',
                'clients/community-mini/pages/merchant/*',
                'clients/community-mini/pages/merchant-join/*',
                'deploy/community-preview/Dockerfile',
                'deploy/community-preview/requirements-runtime.lock',
                'deploy/community-preview/nginx-uk-path-candidate.conf',
                'deploy/community-preview/nginx-ui-preview-candidate.inc',
                'deploy/community-preview/prepare-mini.cjs',
                'deploy/community-preview/endpoint.cjs',
                'deploy/community-preview/endpoint-profiles.json',
                'deploy/community-preview/inspect-version-readonly.sh',
                'deploy/community-preview/readonly-version-manifest.json',
                'deploy/community-preview/connection-inputs.json',
                'docs/development/COMMUNITY_STAGE_INTEGRATION_20261017.md',
                'docs/development/COMMUNITY_CENTER_EXACT_INTEGRATION_20261018.md',
                'docs/development/COMMUNITY_FORMAL_BACKEND_HANDOFF_20261021.md',
                'docs/development/COMMUNITY_UI_PREVIEW_PAGE_MAP_20261022.md',
                'docs/development/COMMUNITY_MINI_DUAL_TERMINAL_REVIEW_20261022.md',
                'docs/development/COMMUNITY_ADMISSION_MINIMAL_DELTA_20261022.md',
                'docs/development/COMMUNITY_BILL_CONTRACT_EVIDENCE.json',
                'scripts/pr122_customer_core.py',
                'scripts/pr122_customer_source.py',
                'scripts/pr122_customer_evidence.py',
                'scripts/pr122_customer_activity_evidence.py',
                'scripts/pr122_customer_privacy.py',
                'scripts/pr122_customer_runtime.py',
                'docs/development/COMMUNITY_PINNED_DEPENDENCIES_20261017.json')
    paths = sorted({p for pattern in patterns for p in root.glob(pattern) if p.is_file()})
    files = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('PACKAGE_SYMLINK_DENIED')
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    required = {'scripts/community_stage_local.py', 'scripts/community_stage_runtime.py',
                'scripts/community_preview_readiness.py',
                'scripts/community_mini_host_config.py',
                'scripts/community_platform_host.py',
                'scripts/community_web_entries.py',
                'scripts/community_web_session.py',
                'demos/community-stage/web-session.js',
                *{'demos/community-stage/ui-preview/'+name for name in ('index.html','sources.js','preview.js','preview.css','original.css')},
                'scripts/community_persistent_runtime.py',
                'scripts/community_first_install.py',
                'scripts/community_wechat_registration.py',
                'scripts/community_stage_package.py', 'clients/community-mini/app.json',
                'scripts/pr122_customer_core.py', 'scripts/pr122_customer_source.py',
                'scripts/pr122_customer_runtime.py', 'scripts/pr122_customer_evidence.py',
                'scripts/pr122_customer_activity_evidence.py', 'scripts/pr122_customer_privacy.py',
                'deploy/community-preview/Dockerfile',
                'deploy/community-preview/requirements-runtime.lock',
                'deploy/community-preview/nginx-uk-path-candidate.conf',
                'deploy/community-preview/nginx-ui-preview-candidate.inc',
                'deploy/community-preview/prepare-mini.cjs',
                'deploy/community-preview/endpoint.cjs',
                'deploy/community-preview/endpoint-profiles.json',
                'deploy/community-preview/inspect-version-readonly.sh',
                'deploy/community-preview/readonly-version-manifest.json',
                'deploy/community-preview/connection-inputs.json',
                'clients/community-mini/pages/home/index.js',
                'clients/community-mini/app.wxss',
                'clients/community-mini/pages/home/index.json',
                'clients/community-mini/pages/home/index.wxml',
                'clients/community-mini/pages/profile/index.js',
                'clients/community-mini/pages/profile/index.json',
                'clients/community-mini/pages/profile/index.wxml',
                'clients/community-mini/pages/merchant/index.js',
                'clients/community-mini/pages/merchant/index.wxml',
                'clients/community-mini/pages/merchant-join/index.js',
                'clients/community-mini/pages/merchant-join/index.wxml',
                'clients/community-mini/merchant-form.js',
                'clients/community-mini/merchant-fields.json',
                'scripts/community_mini_merchant.py',
                'scripts/community_collection_code.py',
                'scripts/community_review_runtime.py',
                'demos/community-stage/review-runtime.html',
                'demos/community-stage/review-native.js'}
    if not required.issubset(files):
        raise ValueError('REQUIRED_SOURCE_MISSING')
    manifest = {'format': 1, 'purpose':'OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE',
                'production_payment':'HOLD', 'production_deployment':'HOLD',
                'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['MANIFEST.json'] = json.dumps(manifest, sort_keys=True, separators=(',',':')).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name,data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026,1,1,0,0,0))
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info,data)
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    data,digest=build(Path(__file__).resolve().parents[1])
    # Never replace an existing review artifact silently.
    with open(args.output,'xb') as out:out.write(data)
    print('OFFLINE_PACKAGE_SHA256='+digest)
