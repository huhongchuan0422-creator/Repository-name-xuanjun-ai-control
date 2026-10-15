"""Create a deterministic OFFLINE-ONLY Stage5 Phase2 candidate archive.

This is not a deploy authorization. Excludes databases, API credentials, secrets,
production configuration and real payment integration.
"""
import hashlib
import io
import json
import pathlib
import re
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
        for info in z.infolist():
            if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
                raise ValueError("PACKAGE_MEMBER_UNSAFE")
            if info.filename=="manifest.json" and info.file_size>65536:
                raise ValueError("PACKAGE_MEMBER_UNSAFE")
            kind=(info.external_attr>>16)&0o170000
            if kind not in (0,0o100000) or info.file_size>4_000_000:
                raise ValueError("PACKAGE_MEMBER_UNSAFE")
        def strict_pairs(pairs):
            value={}
            for key,item in pairs:
                if key in value:raise ValueError("DUPLICATE_MANIFEST_KEY")
                value[key]=item
            return value
        manifest=json.loads(z.read("manifest.json"),object_pairs_hook=strict_pairs)
        if type(manifest) is not dict or set(manifest)!={"kind","production_install_authorized",
                "wechat_payment_connected","customer_entitlement_execution_connected","assets_sha256"}:
            raise ValueError("INVALID_MANIFEST_FIELDS")
        if manifest["kind"]!="STAGE5_PHASE2_OFFLINE_CANDIDATE" or (
                manifest["wechat_payment_connected"] is not False or
                manifest["customer_entitlement_execution_connected"] is not False):
            raise ValueError("INVALID_OFFLINE_SCOPE")
        if manifest.get("production_install_authorized") is not False:
            raise ValueError("PRODUCTION_FLAG_NOT_ALLOWED")
        if type(manifest["assets_sha256"]) is not dict or set(manifest["assets_sha256"])!=set(ASSETS):
            raise ValueError("MANIFEST_ASSET_MISMATCH")
        for path in ASSETS:
            expected=manifest["assets_sha256"][path]
            if type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}",expected) is None:
                raise ValueError("INVALID_ASSET_DIGEST")
            if hashlib.sha256(z.read(path)).hexdigest()!=expected:
                raise ValueError("PACKAGE_CONTENT_TAMPERED")
    return {"verified":True,"production_install_authorized":False}
