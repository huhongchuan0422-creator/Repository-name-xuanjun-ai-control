"""Deterministic allowlisted offline review package; never an installer."""
import hashlib
import io
import json
import zipfile
from pathlib import Path


def build(root):
    root = Path(root)
    patterns = ('docs/development/COMMUNITY_FIXED_PRODUCT_PREVIEW_20261028.md', 'docs/development/COMMUNITY_OCR_HOST_UI_HANDOFF_20261024.md', 'docs/development/COMMUNITY_OCR_SOURCE_CONTRACT_20261024.md', 'scripts/community_ocr_dependency.json', 'services/ocr_engine/api.py', 'services/ocr_engine/secure_store.py',
                'deploy/community-preview/ocr-recovery-api-store.patch', 'deploy/community-preview/ocr-bank-card-successor.patch', 'deploy/community-preview/ocr-id-back-api.patch', 'scripts/community_license_region_areas.json', 'tests/fixtures/community_license_region.json', 'scripts/community_*.py', 'scripts/community_*.cjs', 'tests/test_community_*.py',
                'tests/test_community_*.mjs', 'tests/community_*.cjs',
                'tests/community_platform_image_startup.py',
                'tests/community_license_runtime_checks.py',
                'tests/community_identity_api_runtime_checks.py',
                'tests/community_ocr_full_host_resources.py',
                'tests/fixtures/community_license_columns90_image.json',
                'tests/fixtures/community_document_failure_geometry.json',
                'tests/fixtures/community_license_label_noise_geometry.json',
                'tests/fixtures/community_license_layout_heldout.json',
                'tests/fixtures/license_address_stop_rows.json',
    'tests/fixtures/license_target_no_separator_rows.json',
                'scripts/community_ocr_resource_acceptance.sh',
                'tests/fixtures/community_ocr_resource_images.json',
                'tests/fixtures/community_license_layout/columns-0.json',
                'tests/fixtures/community_license_layout/columns-180.json',
                'tests/fixtures/community_license_layout/columns-270.json',
                'tests/fixtures/community_license_layout/columns-90.json',
                'tests/fixtures/community_license_layout/inline-0.json',
                'tests/fixtures/community_license_layout/inline-180.json',
                'tests/fixtures/community_license_layout/inline-270.json',
                'tests/fixtures/community_license_layout/inline-90.json',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.000.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.001.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.002.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.003.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.004.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.005.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.006.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.007.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.008.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.009.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.010.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.011.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.012.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.013.b64',
                'tests/test_stage5_*.py', 'demos/community-local-e2e/*',
                'demos/community-stage/*', 'demos/community-stage/ui-preview/*', 'demos/community-payment/*',
                'demos/community-admin/*', 'clients/community-mini/*.js',
                'clients/community-mini/*.json', 'clients/community-mini/*.cjs',
                'clients/community-mini/*.wxss',
                'clients/community-mini/assets/community-demo-storefront-v1.jpg',
                'clients/community-mini/pages/checkout/*',
                'clients/community-mini/pages/home/*',
                'clients/community-mini/pages/profile/*',
                'clients/community-mini/pages/merchant/*',
                'clients/community-mini/pages/merchant-join/*',
                'deploy/community-preview/Dockerfile',
                'deploy/community-preview/Dockerfile.ui-successor',
                'deploy/community-preview/COMMUNITY_SOURCE_SHA.successor',
                'deploy/community-preview/community-admin-ui-contract.json',
                'docs/development/COMMUNITY_ID_BACK_COMPATIBILITY_20261106.md',
                'deploy/community-preview/requirements-runtime.lock',
                'deploy/community-preview/nginx-uk-path-candidate.conf',
                'deploy/community-preview/nginx-ui-preview-candidate.inc',
                'deploy/community-preview/prepare-mini.cjs',
                'deploy/community-preview/endpoint.cjs',
                'deploy/community-preview/endpoint-profiles.json',
                'deploy/community-preview/native-backend-compatibility.json',
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
    required = {'tests/test_community_license_address_boundary.py',
                'tests/fixtures/license_address_stop_rows.json',
    'tests/fixtures/license_target_no_separator_rows.json',
                'services/ocr_engine/api.py', 'services/ocr_engine/secure_store.py',
                'deploy/community-preview/ocr-recovery-api-store.patch', 'deploy/community-preview/ocr-id-back-api.patch',
                'scripts/community_identity_layout.py', 'tests/test_community_identity_layout.py', 'tests/test_community_document_orientation.py',
                'tests/test_community_id_back_contract.py','docs/development/COMMUNITY_FIXED_PRODUCT_PREVIEW_20261028.md', 'scripts/community_preview_fixed_product.py', 'scripts/community_mini_r1_input.py', 'scripts/community_stage_local.py', 'scripts/community_stage_runtime.py',
                'scripts/community_preview_readiness.py',
                'scripts/community_mini_host_config.py',
                'scripts/community_platform_host.py',
                'scripts/community_uploaded_image_scanner.py',
                'scripts/community_license_region.py',
                'scripts/community_license_region_areas.json',
                'tests/test_community_license_region.py',
                'tests/test_community_mini_region_validation.py',
                'tests/fixtures/community_license_region.json',
                'clients/community-mini/merchant-license-region.js',
                'tests/test_community_uploaded_image_scanner.py',
                'tests/community_platform_image_startup.py',
                'tests/community_license_runtime_checks.py',
                'tests/community_identity_api_runtime_checks.py',
                'tests/community_ocr_full_host_resources.py',
                'tests/fixtures/community_license_columns90_image.json',
                'tests/fixtures/community_document_failure_geometry.json',
                'tests/fixtures/community_license_label_noise_geometry.json',
                'tests/fixtures/community_license_layout_heldout.json',
                'tests/fixtures/license_address_stop_rows.json',
    'tests/fixtures/license_target_no_separator_rows.json',
                'scripts/community_ocr_resource_acceptance.sh',
                'tests/fixtures/community_ocr_resource_images.json',
                'tests/fixtures/community_license_layout/columns-0.json',
                'tests/fixtures/community_license_layout/columns-180.json',
                'tests/fixtures/community_license_layout/columns-270.json',
                'tests/fixtures/community_license_layout/columns-90.json',
                'tests/fixtures/community_license_layout/inline-0.json',
                'tests/fixtures/community_license_layout/inline-180.json',
                'tests/fixtures/community_license_layout/inline-270.json',
                'tests/fixtures/community_license_layout/inline-90.json',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.000.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.001.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.002.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.003.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.004.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.005.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.006.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.007.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.008.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.009.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.010.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.011.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.012.b64',
                'tests/fixtures/community_ocr_resource_parts/maximum_20mp.013.b64',
                'scripts/community_web_entries.py',
                'scripts/community_web_session.py',
                'scripts/community_reviewer_web_bridge.py',
                'scripts/community_platform_reviewer_admission.py',
                'scripts/community_reviewer_maintenance.py',
                'scripts/community_admin_route_inventory.py',
                'scripts/community_admin_authority.py',
                'scripts/community_admin_bootstrap.py',
                'scripts/community_admin_preflight.py',
                'scripts/community_admin_recovery.py',
                'scripts/community_admin_policy.py',
                'scripts/community_admin_policy_maintenance.py',
                'scripts/community_admin_management.py',
                'scripts/community_admin_route_gate.py',
                'tests/test_community_admin_authority.py',
                'tests/test_community_admin_bootstrap.py',
                'tests/test_community_admin_preflight.py',
                'tests/test_community_admin_policy.py',
                'tests/test_community_admin_ui.py',
                'tests/test_community_original_route_restrictions.py',
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
                'deploy/community-preview/Dockerfile.ui-successor',
                'deploy/community-preview/COMMUNITY_SOURCE_SHA.successor',
                'deploy/community-preview/community-admin-ui-contract.json',
                'docs/development/COMMUNITY_ID_BACK_COMPATIBILITY_20261106.md',
                'deploy/community-preview/requirements-runtime.lock',
                'deploy/community-preview/nginx-uk-path-candidate.conf',
                'deploy/community-preview/nginx-ui-preview-candidate.inc',
                'deploy/community-preview/prepare-mini.cjs',
                'deploy/community-preview/endpoint.cjs',
                'deploy/community-preview/endpoint-profiles.json',
                'deploy/community-preview/native-backend-compatibility.json',
                'deploy/community-preview/inspect-version-readonly.sh',
                'deploy/community-preview/readonly-version-manifest.json',
                'deploy/community-preview/connection-inputs.json',
                'clients/community-mini/pages/home/index.js',
                'clients/community-mini/app.wxss',
                'clients/community-mini/assets/community-demo-storefront-v1.jpg',
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
    # Preserve the exact approved successor pair and its upstream patch evidence.
    # A complete ZIP must be usable by the original offline image-input preparer.
    lock = json.loads(files['scripts/community_ocr_dependency.json'])
    successor = lock.get('local_successor', {})
    sources = {'api.py':'services/ocr_engine/api.py',
               'secure_store.py':'services/ocr_engine/secure_store.py'}
    patch = successor.get('patch_path')
    approved_patches = {
        'deploy/community-preview/ocr-recovery-api-store.patch',
        'deploy/community-preview/ocr-bank-card-successor.patch',
    }
    if successor.get('source_files') != sources or patch not in approved_patches:
        raise ValueError('OCR_SUCCESSOR_PACKAGE_BINDING_MISMATCH')
    if patch not in files:
        raise ValueError('REQUIRED_SOURCE_MISSING')
    if patch == 'deploy/community-preview/ocr-bank-card-successor.patch':
        bank_required = {'scripts/community_bank_card_layout.py',
                         'tests/test_community_bank_card_layout.py',
                         'tests/test_community_h5_bank_ocr.py',
                         'tests/test_community_h5_ocr.py',
                         'scripts/community_h5.py',
                         'scripts/community_h5_context.py'}
        if not bank_required.issubset(files):
            raise ValueError('REQUIRED_SOURCE_MISSING')
    for name, relative in sources.items():
        if hashlib.sha256(files[relative]).hexdigest() != lock.get('files', {}).get(name):
            raise ValueError('OCR_SUCCESSOR_SOURCE_HASH_MISMATCH')
    if hashlib.sha256(files[patch]).hexdigest() != successor.get('patch_sha256'):
        raise ValueError('OCR_SUCCESSOR_PATCH_HASH_MISMATCH')
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
