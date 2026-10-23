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
    import hashlib
    key=Fernet.generate_key()
    with tempfile.TemporaryDirectory() as tmp:
        db=os.path.join(tmp,'ocr-e2e.sqlite3')
        principal=Principal(subject='synthetic-user',tenant_id='synthetic-tenant',permissions={'ocr:use'})
        docs=[('business_license','synthetic-license-attachment'),('id_front','synthetic-id-attachment')]
        images={kind:make_synthetic_document(kind) for kind,_ in docs}
        authorized_hashes={attachment:hashlib.sha256(images[kind]).hexdigest() for kind,attachment in docs}
        revoked_apps=set(); revoked_attachments=set()
        def app_auth(p, app_id): return app_id=='synthetic-app' and app_id not in revoked_apps
        def attachment_auth(p, app_id, attachment_id, supplied_sha256):
            expected=authorized_hashes.get(attachment_id)
            return {'authorized': expected is not None and expected==supplied_sha256 and attachment_id not in revoked_attachments, 'content_sha256': expected or ''}
        def make_client():
            store=SecureSQLiteJobStore(db,key)
            app=create_app(authenticate=lambda token: principal if token=='synthetic-token' else (_ for _ in ()).throw(ValueError('bad token')),
                store=store,authorize_application=app_auth,authorize_attachment=attachment_auth)
            return TestClient(app)
        results=[]
        with make_client() as client:
            for kind,attachment in docs:
                img=images[kind]
                headers={'Authorization':'Bearer synthetic-token','Idempotency-Key':'submit-'+kind+'-00001'}
                response=client.post('/api/v1/ocr/jobs',headers=headers,data={'document_type':kind,'onboarding_application_id':'synthetic-app','attachment_id':attachment},files={'file':(kind+'.png',img,'image/png')})
                if response.status_code!=202: raise SystemExit('HTTP_SUBMIT_FAILED:'+kind+':'+str(response.status_code)+':'+response.text)
                job_id=response.json()['job_id']
                read=client.get('/api/v1/ocr/jobs/'+job_id,headers={'Authorization':'Bearer synthetic-token'})
                if read.status_code!=200: raise SystemExit('HTTP_READ_FAILED:'+kind+':'+str(read.status_code)+':'+read.text)
                payload=read.json(); fields=payload.get('fields',{})
                print('E2E_DOCUMENT='+kind); print('E2E_FIELDS='+repr(fields))
                if not fields or payload.get('authenticity_verified') is not False or payload.get('requires_human_confirmation') is not True: raise SystemExit('OCR_OR_REVIEW_GUARD_FAILED:'+kind)
                confirm_headers={'Authorization':'Bearer synthetic-token','Idempotency-Key':'confirm-'+kind+'-00001'}
                body={'revision':1,'fields':{k:v['value'] for k,v in fields.items()}}
                confirmed=client.post('/api/v1/ocr/jobs/'+job_id+'/confirm',headers=confirm_headers,json=body)
                if confirmed.status_code!=200: raise SystemExit('CONFIRM_FAILED:'+kind+':'+str(confirmed.status_code)+':'+confirmed.text)
                replay=client.post('/api/v1/ocr/jobs/'+job_id+'/confirm',headers=confirm_headers,json=body)
                if replay.status_code!=200 or replay.json()!=confirmed.json(): raise SystemExit('CONFIRM_REPLAY_FAILED:'+kind)
                readback=client.get('/api/v1/ocr/jobs/'+job_id,headers={'Authorization':'Bearer synthetic-token'})
                if readback.status_code!=200 or readback.json().get('confirmed_fields')!=body['fields'] or readback.json().get('confirmation_revision')!=1: raise SystemExit('CONFIRMED_FIELDS_READBACK_FAILED:'+kind)
                results.append((kind,attachment,job_id,img,headers,body,confirm_headers,confirmed.json()))
        with make_client() as restarted:
            for kind,attachment,job_id,img,headers,body,confirm_headers,confirm_response in results:
                read=restarted.get('/api/v1/ocr/jobs/'+job_id,headers={'Authorization':'Bearer synthetic-token'})
                if read.status_code!=200 or read.json().get('status')!='confirmed': raise SystemExit('RESTART_CONFIRMATION_NOT_PERSISTED:'+kind)
                same=restarted.post('/api/v1/ocr/jobs',headers=headers,data={'document_type':kind,'onboarding_application_id':'synthetic-app','attachment_id':attachment},files={'file':(kind+'.png',img,'image/png')})
                if same.status_code!=202 or same.json().get('job_id')!=job_id: raise SystemExit('SUBMIT_REPLAY_FAILED:'+kind)
                replay=restarted.post('/api/v1/ocr/jobs/'+job_id+'/confirm',headers=confirm_headers,json=body)
                if replay.status_code!=200 or replay.json()!=confirm_response: raise SystemExit('CONFIRM_REPLAY_AFTER_RESTART_FAILED:'+kind)
                events=restarted.app.state.ocr_job_store.audit_events(job_id,'synthetic-tenant')
                if len(events)!=1 or events[0].get('event')!='USER_CONFIRMATION': raise SystemExit('AUDIT_PERSISTENCE_FAILED:'+kind)
                wrong=bytes([137,80,78,71,13,10,26,10])+b'wrong synthetic bytes'
                bad=restarted.post('/api/v1/ocr/jobs',headers={'Authorization':'Bearer synthetic-token','Idempotency-Key':'wrong-bytes-'+kind+'-0001'},data={'document_type':kind,'onboarding_application_id':'synthetic-app','attachment_id':attachment},files={'file':(kind+'.png',wrong,'image/png')})
                if bad.status_code!=403 or 'ATTACHMENT_CONTENT_BINDING_UNVERIFIED' not in bad.text: raise SystemExit('WRONG_CONTENT_NOT_REJECTED:'+kind)
                print('E2E_RESTART_CONFIRMATION=PASS:'+kind); print('E2E_CONFIRM_READBACK=PASS:'+kind); print('E2E_SUBMIT_IDEMPOTENCY=PASS:'+kind); print('E2E_AUDIT_PERSISTENCE=PASS:'+kind); print('E2E_WRONG_CONTENT_REJECTED=PASS:'+kind)
        print('CHINESE_LICENSE_AND_ID_HTTP_SQLITE_E2E=PASS')

if __name__=='__main__': main()
