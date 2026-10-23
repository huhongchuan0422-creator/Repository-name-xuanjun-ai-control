"""Real Chinese synthetic certificate -> RapidOCR -> parser -> HTTP -> encrypted SQLite -> confirmation replay E2E."""
import io, os, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from services.ocr_engine.api import create_app, Principal
from services.ocr_engine.secure_store import SecureSQLiteJobStore

def make_synthetic_license():
    candidates = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]
    font_path = next((p for p in candidates if Path(p).is_file()), None)
    if not font_path:
        raise SystemExit("CHINESE_SYNTHETIC_FONT_MISSING")
    image = Image.new("RGB", (1800, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 48)
    lines = [
        "营业执照（合成测试，非真实证件）",
        "名称：玄钧AI新合成测试企业",
        "统一社会信用代码：91350100M000100Y43",
        "法定代表人：张测试",
        "住所：重庆市测试区示例路一号",
        "经营范围：软件开发测试",
    ]
    y = 55
    for line in lines:
        draw.text((55, y), line, font=font, fill="black")
        y += 125
    buf = io.BytesIO(); image.save(buf, format="PNG")
    return buf.getvalue()

def main():
    img = make_synthetic_license()
    key = Fernet.generate_key()
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "ocr-e2e.sqlite3")
        store = SecureSQLiteJobStore(db, key)
        principal = Principal(subject="synthetic-user", tenant_id="synthetic-tenant", permissions={"ocr:use"})
        app = create_app(authenticate=lambda token: principal if token == "synthetic-token" else (_ for _ in ()).throw(ValueError("bad token")),
                         store=store, authorize_application=lambda p, application_id: application_id == "synthetic-app",
                         authorize_attachment=lambda p, application_id, attachment_id: attachment_id == "synthetic-attachment")
        client = TestClient(app)
        headers = {"Authorization":"Bearer synthetic-token", "Idempotency-Key":"chinese-e2e-submit-0001"}
        response = client.post("/api/v1/ocr/jobs", headers=headers,
            data={"document_type":"business_license", "onboarding_application_id":"synthetic-app", "attachment_id":"synthetic-attachment"},
            files={"file":("synthetic-license.png", img, "image/png")})
        if response.status_code != 202:
            raise SystemExit("HTTP_SUBMIT_FAILED:" + str(response.status_code) + ":" + response.text)
        job_id = response.json()["job_id"]
        result = client.get("/api/v1/ocr/jobs/" + job_id, headers={"Authorization":"Bearer synthetic-token"})
        if result.status_code != 200:
            raise SystemExit("HTTP_RESULT_FAILED:" + str(result.status_code))
        payload = result.json()
        fields = payload.get("fields", {})
        print("E2E_STAGE=REAL_CHINESE_SYNTHETIC_IMAGE")
        print("E2E_HTTP_SUBMIT=PASS")
        print("E2E_JOB_STATUS=" + str(payload.get("status")))
        print("E2E_OCR_FIELDS=" + repr(fields))
        if not fields:
            raise SystemExit("CHINESE_OCR_NO_FIELDS_EXTRACTED")
        if payload.get("authenticity_verified") is not False or payload.get("requires_human_confirmation") is not True:
            raise SystemExit("HUMAN_REVIEW_GUARD_FAILED")
        confirm_headers = {"Authorization":"Bearer synthetic-token", "Idempotency-Key":"chinese-e2e-confirm-0001"}
        confirm_body = {"revision":1, "fields": {k: v["value"] for k, v in fields.items()}}
        confirmed = client.post("/api/v1/ocr/jobs/" + job_id + "/confirm", headers=confirm_headers, json=confirm_body)
        if confirmed.status_code != 200:
            raise SystemExit("HTTP_CONFIRM_FAILED:" + str(confirmed.status_code) + ":" + confirmed.text)
        replay = client.post("/api/v1/ocr/jobs/" + job_id + "/confirm", headers=confirm_headers, json=confirm_body)
        if replay.status_code != 200 or replay.json() != confirmed.json():
            raise SystemExit("CONFIRM_IDEMPOTENCY_REPLAY_FAILED")
        restarted = SecureSQLiteJobStore(db, key)
        persisted = restarted.get(job_id, "synthetic-tenant")
        audits = restarted.audit_events(job_id, "synthetic-tenant")
        if not persisted or persisted.get("status") != "confirmed" or len(audits) != 1:
            raise SystemExit("SQLITE_RESTART_OR_AUDIT_FAILED")
        same_submit = client.post("/api/v1/ocr/jobs", headers=headers,
            data={"document_type":"business_license", "onboarding_application_id":"synthetic-app"},
            files={"file":("synthetic-license.png", img, "image/png")})
        if same_submit.status_code != 202 or same_submit.json()["job_id"] != job_id:
            raise SystemExit("SUBMIT_IDEMPOTENCY_REPLAY_FAILED")
        print("E2E_HTTP_CONFIRM=PASS")
        print("E2E_CONFIRM_REPLAY=PASS")
        print("E2E_SQLITE_RESTART=PASS")
        print("E2E_AUDIT_EVENTS=" + str(len(audits)))
        print("E2E_SUBMIT_REPLAY=PASS")
        print("CHINESE_HTTP_SQLITE_FULL_CHAIN=PASS")

if __name__ == "__main__": main()