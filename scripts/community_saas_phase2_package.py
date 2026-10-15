"""Create a deterministic OFFLINE-ONLY Stage5 Phase2 candidate archive.

This is not a deploy authorization. Excludes databases, API credentials, secrets,
production configuration and real payment integration.
"""
import hashlib
import io
import json
import pathlib
import zipfile

ASSETS=(
    "scripts/community_saas_phase2.py",
    "scripts/community_saas_phase2_http.py",
    "scripts/community_saas_phase2_recovery.py",
    "scripts/community_saas_order_preparation.py",
    "scripts/community_saas_offline_handoff.py",
    "demos/community-local-e2e/saas-panel.html",
    "demos/community-local-e2e/saas-panel.mjs",
    "demos/community-local-e2e/saas-panel.test.mjs",
    "tests/test_stage5_saas_phase2.py",
    "tests/test_stage5_saas_phase2_http.py",
    "tests/test_stage5_saas_phase2_recovery.py",
    "tests/test_stage5_saas_phase2_backup_path.py",
    "tests/test_stage5_saas_order_preparation.py",
    "tests/test_stage5_saas_offline_handoff.py",
)
def build(root):
    root=pathlib.Path(root).resolve()
    sha={}
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for relative in ASSETS:
            requested=root/relative
            if requested.is_symlink():raise ValueError("UNSAFE_OR_MISSING_ASSET")
            path=requested.resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("UNSAFE_OR_MISSING_ASSET")
            data=path.read_bytes()
            if b"BEGIN PRIVATE KEY" in data or b"sk_live_" in data:
                raise ValueError("POSSIBLE_CREDENTIAL_IN_PACKAGE")
            sha[relative]=hashlib.sha256(data).hexdigest()
            meta=zipfile.ZipInfo(relative,date_time=(1980,1,1,0,0,0))
            meta.external_attr=(0o644<<16)
            meta.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(meta,data)
        manifest={"kind":"STAGE5_PHASE2_OFFLINE_CANDIDATE",
                  "production_install_authorized":False,
                  "wechat_payment_connected":False,
                  "customer_entitlement_execution_connected":False,
                  "assets_sha256":sha}
        meta=zipfile.ZipInfo("manifest.json",date_time=(1980,1,1,0,0,0))
        meta.external_attr=(0o644<<16);meta.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(meta,json.dumps(manifest,sort_keys=True,separators=(",",":")).encode())
    blob=out.getvalue()
    return {"archive_bytes":blob,"sha256":hashlib.sha256(blob).hexdigest(),
            "manifest":manifest}

def inspect(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=z.namelist()
        if sorted(names)!=sorted([*ASSETS,"manifest.json"]) or len(names)!=len(set(names)):
            raise ValueError("PACKAGE_ASSET_MISMATCH")
        manifest=json.loads(z.read("manifest.json"))
        if manifest.get("production_install_authorized") is not False:
            raise ValueError("PRODUCTION_FLAG_NOT_ALLOWED")
        if set(manifest.get("assets_sha256",{}))!=set(ASSETS):
            raise ValueError("MANIFEST_ASSET_MISMATCH")
        for path in ASSETS:
            if hashlib.sha256(z.read(path)).hexdigest()!=manifest["assets_sha256"][path]:
                raise ValueError("PACKAGE_CONTENT_TAMPERED")
    return {"verified":True,"production_install_authorized":False}
