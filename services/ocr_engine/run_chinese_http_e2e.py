"""Real synthetic Chinese business license and ID-front OCR over HTTP; encrypted SQLite persistence across independent app/store instances."""
import io, os, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from services.ocr_engine.api import create_app, Principal
from services.ocr_engine.secure_store import SecureSQLiteJobStore

def make_synthetic_document(kind):
    font_candidates = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]
    font_path = next((p for p in font_candidates if Path(p).is_file()), None)
    if not font_path: raise SystemExit("CHINESE_SYNTHETIC_FONT_MISSING")
    image = Image.new("RGB", (1800, 1000), "white"); draw = ImageDraw.Draw(image); font = ImageFont.truetype(font_path, 48)
    if kind == "business_license":
        lines = ["营业执照（合成测试，非真实证件）","名称：玄钧AI新合成测试企业","统一社会信用代码：91350100M000100Y43","法定代表人：张测试","住所：重庆市测试区示例路一号","经营范围：软件开发测试"]
    elif kind == "id_front":
        lines = ["居民身份证（合成测试，非真实证件）","姓名：张测试","性别：男 民族：汉","出生：1990年01月01日","住址：重庆市测试区示例路一号","公民身份号码：110101199001010011"]
    else: raise ValueError("UNSUPPORTED_SYNTHETIC_DOCUMENT")
    y=45
    for line in lines: draw.text((55,y),line,font=font,fill="black"); y+=145
    buf=io.BytesIO(); image.save(buf,format="PNG"); return buf.getvalue()

def main():
    key=Fernet.generate_key()
    with tempfile.TemporaryDirectory() as tmp:
        db=os.path.join(tmp,"ocr-e2e.sqlite3")
        principal=Principal(subject="synthetic-user",tenant_id="synthetic-tenant",permissions={"ocr:use"})
        def make_client():
            store=SecureSQLiteJobStore(db,key)
            app=create_app(authenticate=lambda token: principal if token=="synthetic-token" else (_ for _ in ()).throw(ValueError("bad token")),
                store=store, authorize_application=lambda p, app_id: app_id=="synthetic-app",
                authorize_attachment=lambda p, app_id, attachment_id: attachment_id in {"synthetic-license-attachment","synthetic-id-attachment"})
            return TestClient(app)
        with make_client() as client:
            results=[]
            for kind,attachment in (("business_license","synthetic-license-attachment"),("id_front","synthetic-id-attachment")):
                img=make_synthetic_document(kind)
                headers={"Authorization":"Bearer synthetic-token","Idempotency-Key":"submit-"+kind+"-00001"}
                response=client.post("/api/v1/ocr/jobs",headers=headers,
                    data={"document_type":kind,"onboarding_application_id":"synthetic-app","attachment_id":attachment},
                    files={"file":(kind+".png",img,"image/png")})
                if response.status_code!=202: raise SystemExit("HTTP_SUBMIT_FAILED:"+kind+":"+str(response.status_code)+":"+response.text)
                job_id=response.json()["job_id"]
                read=client.get("/api/v1/ocr/jobs/"+job_id,headers={"Authorization":"Bearer synthetic-token"})
                if read.status_code!=200: raise SystemExit("HTTP_READ_FAILED:"+kind+":"+str(read.status_code))
                payload=read.json(); fields=payload.get("fields",{})
                print("E2E_DOCUMENT="+kind)
                print("E2E_STATUS="+str(payload.get("status")))
                print("E2E_FIELDS="+repr(fields))
                if not fields: raise SystemExit("OCR_FIELDS_EMPTY:"+kind)
                if payload.get("authenticity_verified") is not False or payload.get("requires_human_confirmation") is not True: raise SystemExit("HUMAN_REVIEW_GUARD_FAILED:"+kind)
                confirm_headers={"Authorization":"Bearer synthetic-token","Idempotency-Key":"confirm-"+kind+"-00001"}
                body={"revision":1,"fields":{k:v["value"] for k,v in fields.items()}}
                confirmed=client.post("/api/v1/ocr/jobs/"+job_id+"/confirm",headers=confirm_headers,json=body)
                if confirmed.status_code!=200: raise SystemExit("CONFIRM_FAILED:"+kind+":"+str(confirmed.status_code)+":"+confirmed.text)
                replay=client.post("/api/v1/ocr/jobs/"+job_id+"/confirm",headers=confirm_headers,json=body)
                if replay.status_code!=200 or replay.json()!=confirmed.json(): raise SystemExit("CONFIRM_REPLAY_FAILED:"+kind)
                results.append((kind,attachment,job_id,img,headers,body,confirm_headers,confirmed.json()))
        # New store and new FastAPI app/client = independent-process boundary analogue; no state from old objects reused.
        with make_client() as restarted:
            for kind,attachment,job_id,img,headers,body,confirm_headers,confirm_response in results:
                read=restarted.get("/api/v1/ocr/jobs/"+job_id,headers={"Authorization":"Bearer synthetic-token"})
                if read.status_code!=200 or read.json().get("status")!="confirmed": raise SystemExit("RESTART_CONFIRMATION_NOT_PERSISTED:"+kind)
                same=restarted.post("/api/v1/ocr/jobs",headers=headers,
                    data={"document_type":kind,"onboarding_application_id":"synthetic-app","attachment_id":attachment},
                    files={"file":(kind+".png",img,"image/png")})
                if same.status_code!=202 or same.json().get("job_id")!=job_id: raise SystemExit("SUBMIT_REPLAY_FAILED:"+kind)
                replay=restarted.post("/api/v1/ocr/jobs/"+job_id+"/confirm",headers=confirm_headers,json=body)
                if replay.status_code!=200 or replay.json()!=confirm_response: raise SystemExit("CONFIRM_REPLAY_AFTER_RESTART_FAILED:"+kind)
                store=restarted.app.state.ocr_job_store
                events=store.audit_events(job_id,"synthetic-tenant")
                if len(events)!=1 or events[0].get("event")!="USER_CONFIRMATION": raise SystemExit("AUDIT_PERSISTENCE_FAILED:"+kind)
                print("E2E_RESTART_CONFIRMATION=PASS:"+kind)
                print("E2E_SUBMIT_IDEMPOTENCY=PASS:"+kind)
                print("E2E_CONFIRM_IDEMPOTENCY=PASS:"+kind)
                print("E2E_AUDIT_PERSISTENCE=PASS:"+kind)
        # Exercise simultaneous independent connections: same idempotency key and payload must resolve to one durable job.
        with make_client() as concurrent:
            from concurrent.futures import ThreadPoolExecutor
            img=make_synthetic_document("business_license")
            def submit_once(_):
                return concurrent.post("/api/v1/ocr/jobs",headers={"Authorization":"Bearer synthetic-token","Idempotency-Key":"concurrent-license-0001"},
                    data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-license-attachment"},
                    files={"file":("license.png",img,"image/png")})
            with ThreadPoolExecutor(max_workers=4) as pool: responses=list(pool.map(submit_once,range(4)))
            if any(r.status_code!=202 for r in responses) or len({r.json()["job_id"] for r in responses})!=1: raise SystemExit("CONCURRENT_IDEMPOTENCY_ISOLATION_FAILED")
            print("E2E_CONCURRENT_IDEMPOTENCY=PASS")
        print("CHINESE_LICENSE_AND_ID_HTTP_SQLITE_E2E=PASS")

if __name__=="__main__": main()