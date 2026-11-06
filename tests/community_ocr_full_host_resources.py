"""Image-only full PlatformHost + original scanner + real OCR resource acceptance.

One fresh container runs one case. No production identities, network, real
materials, model stubs, auth bypasses, runtime limit changes or new flags.
The only mocked external boundary is the original fixture WeChat code exchange;
all registration/session/link/owner/source/store checks execute normally.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import threading
import sqlite3
from unittest.mock import Mock, patch

EXPECTED_MEMORY = 4 * 1024**3  # Latest user-approved maximum, not preallocation.


def cgroup_snapshot():
    root=Path('/sys/fs/cgroup')
    names=('memory.current','memory.peak','memory.max','memory.events',
           'memory.swap.current','memory.swap.max','cpu.max','pids.current','pids.max')
    return {name:(root/name).read_text().strip() if (root/name).is_file() else None for name in names}


def verify_environment():
    if (os.geteuid(),os.getegid()) != (10001,1008):raise AssertionError('EXPECTED_IMAGE_NONROOT_IDENTITY')
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    assert status['NoNewPrivs'].strip()=='1','NO_NEW_PRIVILEGES_REQUIRED'
    assert int(status['CapEff'].strip(),16)==0,'CAPABILITIES_MUST_BE_DROPPED'
    assert os.statvfs('/').f_flag & os.ST_RDONLY,'READ_ONLY_ROOT_REQUIRED'
    assert set(line.split(':')[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]) <= {'lo'},'NETWORK_NONE_REQUIRED'
    cg=cgroup_snapshot()
    assert cg['memory.max']==str(EXPECTED_MEMORY),'EXACT_APPROVED_MEMORY_LIMIT_REQUIRED'
    assert cg['memory.swap.max']=='0','NO_ADDITIONAL_SWAP_REQUIRED'
    quota,period=map(int,cg['cpu.max'].split())
    assert quota*2==period,'ORIGINAL_HALF_CPU_REQUIRED'
    assert cg['pids.max']=='64','ORIGINAL_PIDS_64_REQUIRED'
    assert cg['memory.peak'] is not None,'CGROUP_V2_KERNEL_PEAK_REQUIRED'
    return cg


def run_case(case, *, enforce_limits=True):
    # enforce_limits=False exists only for local functional diagnostics, cannot
    # be selected by the command-line entry point, and never yields acceptance.
    assert os.geteuid()!=0,'NONROOT_REQUIRED'
    stages=[];started=time.monotonic()
    def record(phase, **facts):
        row={'phase':phase,'elapsed_seconds':round(time.monotonic()-started,4),
             'cgroup':cgroup_snapshot(),**facts}
        stages.append(row)
        print('RESOURCE_STAGE '+json.dumps(row,sort_keys=True),flush=True)
    record('begin',constraints_verified=False)
    if enforce_limits:
        verify_environment()
        record('constraints_verified',constraints_verified=True)
    import test_community_platform_host as host_fixture
    from services.ocr_engine import api,ocr_core
    from cryptography.fernet import Fernet
    from scripts.community_mini_merchant import MiniMerchant
    from scripts.community_uploaded_image_scanner import UploadedImageScanner
    ocr_core._verified_model_paths()
    fixture=json.loads((Path(__file__).parent/'fixtures/community_ocr_resource_images.json').read_text())
    assert fixture['scope']=='SYNTHETIC_ONLY_FULL_HOST_RESOURCE_CASES'
    image=fixture['cases'][case]
    fixture_root=Path(__file__).parent/'fixtures'
    if case=='clear':
        assert image['base64_fixture']=='community_license_columns90_image.json'
        encoded=json.loads((fixture_root/image['base64_fixture']).read_text())['png_base64']
    else:
        chunks=[]
        for index,part in enumerate(image['base64_parts']):
            assert part['file']==f'community_ocr_resource_parts/maximum_20mp.{index:03d}.b64'
            body=(fixture_root/part['file']).read_bytes()
            assert len(body)==part['bytes'] and hashlib.sha256(body).hexdigest()==part['sha256']
            chunks.append(body.decode('ascii'))
        encoded=''.join(chunks);del chunks,body
    raw=base64.b64decode(encoded,validate=True)
    del encoded
    assert hashlib.sha256(raw).hexdigest()==image['sha256'] and len(raw)==image['bytes']
    if case=='maximum_20mp':assert image['width']*image['height']==20_000_000
    # No PIL/image generation here: creation happens before the constrained
    # container, while original upload/scanner/decode are included below.
    # Historical image fixtures retain their original scope text. It is no
    # longer an OCR business target; keep all other expected fields unchanged.
    expected={name:value for name,value in fixture['expected'].items() if name!='business_scope'};del fixture
    engine_calls=[]
    engine_initializations=[]
    def profile(frame,event,arg):
        if event=='call' and frame.f_code.co_name=='__call__' and frame.f_globals.get('__name__')=='rapidocr.main':engine_calls.append(1)
        if event=='call' and frame.f_code.co_name=='__init__' and frame.f_globals.get('__name__')=='rapidocr.main':engine_initializations.append(1)
    previous_profile=threading.getprofile()
    threading.setprofile(profile)
    fx=host_fixture.FormalHost();fx.setUp()
    try:
        key=Fernet.generate_key()
        key_path=fx.write('synthetic-ocr-key.json',{'ocr_encryption_key':key.decode('ascii')})
        db_path=fx.root/'synthetic-ocr.sqlite'
        store=api.SecureSQLiteJobStore(str(db_path),key);db_path.chmod(0o600)
        # Original store opens a short-lived connection per operation, not a
        # second permanently open DB owner. No key/token values are logged.
        del store,key
        with fx.open() as host:
            assert host.configure_applicant_image_scanner()=='APPLICANT_IMAGE_SCANNER_CONFIGURED'
            service=host.configure_applicant_ocr(str(key_path),str(db_path))
            assert isinstance(host.center.scanner,UploadedImageScanner)
            app=host.application
            assert service is app.gateway.ocr and service.applicant_mode
            assert not app.onboarding.wechat_applyment.enabled
            assert getattr(app.gateway,'payments',None) is None
            # Existing fixture registers & verifies accounts and binds openid1.
            # Only external WeChat exchange is synthetic; original login creates
            # a real bound mini session, consumed by all downstream checks.
            app.gateway.provider.exchange=Mock(return_value={'appid':app.identity.appid,'openid':'openid1'})
            token=app.gateway.login({'code':'synthetic_resource_once'})['session_token']
            assert host.center.session(token)==fx.fx.uid1
            merchant=MiniMerchant(app.identity,app.onboarding,app.operations,ocr=service)
            def onboarding(operation,params):
                return merchant.dispatch(token,'',{'operation':'onboarding','params':{'operation':operation,'params':params}})
            draft=onboarding('save',{'application':None,'revision':0,
                'fields':{'legal_name':'Synthetic OCR Fixture','store_name':'Synthetic Store','address':'Synthetic Address','contact':'Synthetic Contact'},
                'entity_type':'ENTERPRISE','category':'GENERAL','delegated':False})
            application=draft['application']
            record('full_host_and_application_ready')
            draft=onboarding('upload',{'application':application,'revision':draft['revision'],
                'kind':'business_license','content_base64':base64.b64encode(raw).decode(),'expires_at':None})
            del raw,image
            owner=service.bridge.authenticate(token)
            source=service.bridge.source(owner,application,'business_license')
            assert source['data'] and source['document_type']=='business_license'
            scanner_sha=hashlib.sha256(source['data']).hexdigest()
            from PIL import Image
            import io
            with Image.open(io.BytesIO(source['data'])) as scanned:
                scanned_size=list(scanned.size)
            if case=='maximum_20mp':assert scanned_size[0]*scanned_size[1]==20_000_000,'SCANNER_SILENTLY_REDUCED_PIXELS'
            del source
            record('original_scanner_upload_complete',sanitized_sha256=scanner_sha,scanned_size=scanned_size)
            params={'action':'submit','application':application,'document_type':'business_license','idempotency_key':'synthetic-resource-same-request-0001'}
            submits=0;pending=0
            # This is a CI watchdog, not a changed product timeout/retry rule.
            # Resume exact original Host request after PENDING, never new jobs.
            deadline=time.monotonic()+180
            while True:
                try:
                    submits+=1
                    result=merchant.dispatch(token,'',{'operation':'ocr','params':params})
                    break
                except PermissionError as error:
                    if str(error)!='OCR_REQUEST_PENDING':raise
                    pending+=1
                    if time.monotonic()>deadline:raise AssertionError('CI_RESOURCE_CASE_WATCHDOG_EXPIRED')
                    time.sleep(.05)
            job_id=result['result']['job_id']
            read=merchant.dispatch(token,'',{'operation':'ocr','params':{'action':'read','application':application,'job_id':job_id}})['result']
            assert read['status']=='needs_review',read.get('error_code','OCR_NOT_REVIEWABLE')
            assert 'business_scope' not in read['fields'],'REMOVED_SCOPE_TARGET_RETURNED'
            for name,value in expected.items():
                assert read['fields'][name]['value']==value,'SYNTHETIC_FIELD_MISMATCH_'+name
                assert read['fields'][name]['requires_review'] is True
            assert read['requires_human_confirmation'] is True and not read.get('authenticity_verified')
            assert not read.get('confirmed_fields'),'UNREQUESTED_CONFIRMATION'
            after=onboarding('read',{'application':application})
            assert after['revision']==draft['revision'],'UNREQUESTED_APPLICATION_WRITEBACK'
            # One business job evaluates four real pixel orientations using
            # one engine. This is not four submissions or an automatic retry.
            assert len(engine_calls)==4,'FOUR_ORIENTATION_INFERENCES_REQUIRED'
            assert len(engine_initializations)==1,'ONE_SHARED_ORIENTATION_ENGINE_REQUIRED'
            with sqlite3.connect(str(db_path)) as database:
                assert database.execute('SELECT count(*) FROM ocr_jobs').fetchone()[0]==1,'DUPLICATE_OCR_JOB'
            record('ocr_read_verified',actual_model_calls=len(engine_calls),engine_initializations=len(engine_initializations),pending_resumes=pending,submit_dispatch_calls=submits,
                matching_expected_fields=len(expected),manual_confirmation_preserved=True)
        record('host_closed')
    finally:
        fx.doCleanups()
        threading.setprofile(previous_profile)
    if enforce_limits:
        events=dict(line.split() for line in cgroup_snapshot()['memory.events'].splitlines())
        assert int(events.get('oom_kill',0))==0 and int(events.get('oom',0))==0,'CGROUP_OOM_EVENT'
    final={'scope':'FULL_PLATFORM_HOST_SYNTHETIC_ONLY','case':case,'accepted':bool(enforce_limits),
           'functional_checks_passed':True,'production_limits_enforced':bool(enforce_limits),
           'memory_limit_bytes':EXPECTED_MEMORY,'elapsed_seconds':round(time.monotonic()-started,4),
           'final_cgroup':cgroup_snapshot(),'stages':stages}
    print('RESOURCE_RESULT '+json.dumps(final,sort_keys=True),flush=True)
    return final


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('clear','maximum_20mp'),required=True)
    args=parser.parse_args()
    # Local AF_UNIX/ASGI transport is legitimate. Forbid external HTTP provider
    # requests in addition to the container's --network=none boundary.
    with patch('urllib.request.urlopen',side_effect=AssertionError('NO_PROVIDER_NETWORK')):
        run_case(args.case)
