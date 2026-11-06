"""Bounded same-owner OCR lifecycle; no listener, credentials or permission grant."""
import concurrent.futures
import queue
import threading
import time


class OcrPublicError(PermissionError):
    def __init__(self, code):
        if code not in ('OCR_SOURCE_CHANGED','OCR_AUTH_DENIED','OCR_UNAVAILABLE','OCR_REQUEST_PENDING'):code='OCR_UNAVAILABLE'
        self.code=code
        super().__init__(code)


class OwnerCalls:
    def __init__(self, capacity=8, timeout=5):
        self.owner=threading.get_ident();self.pending=queue.Queue(maxsize=capacity)
        self.timeout=timeout;self.closed=False;self.lock=threading.RLock()
    def check(self):
        if threading.get_ident()!=self.owner:raise PermissionError('OCR_CENTER_OWNER_THREAD_REQUIRED')
        if self.closed:raise PermissionError('OCR_HOST_STOPPED')
    def __call__(self, operation):
        with self.lock:
            if self.closed:raise PermissionError('OCR_HOST_STOPPED')
            if threading.get_ident()==self.owner:return operation()
            future=concurrent.futures.Future()
            try:self.pending.put_nowait((time.monotonic()+self.timeout,operation,future))
            except queue.Full:raise PermissionError('OCR_OWNER_QUEUE_FULL') from None
        try:return future.result(timeout=self.timeout)
        except concurrent.futures.TimeoutError:
            with self.lock:future.cancel()
            raise PermissionError('OCR_OWNER_TIMEOUT') from None
    def pump(self):
        self.check()
        try:deadline,operation,future=self.pending.get_nowait()
        except queue.Empty:return
        if time.monotonic()>=deadline:
            future.cancel();return
        if not future.set_running_or_notify_cancel():return
        try:future.set_result(operation())
        except BaseException as error:future.set_exception(error)
    def close(self):
        with self.lock:
            self.closed=True
            while True:
                try:_,_,future=self.pending.get_nowait()
                except queue.Empty:break
                if not future.done():future.set_exception(PermissionError('OCR_HOST_STOPPED'))


class HostOcr:
    def __init__(self, merchant, scene, api, store, *, applicant_mode=False):
        from scripts.community_ocr_bridge import compose
        self.owner=OwnerCalls();self.merchant=merchant;self.scene=scene;self.applicant_mode=applicant_mode
        from scripts.community_license_inference import run_license_layout_ocr
        self.bridge,self.app=compose(merchant,scene,api,store,self.owner,
            infer=run_license_layout_ocr,applicant_mode=applicant_mode)
        self.worker=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='community-ocr')
        self.busy=False;self.inflight=None;self.inflight_key=None;self.inflight_source=None
    def dispatch(self, token, scene, params):
        self.owner.check()
        if self.busy:raise PermissionError('OCR_REQUEST_PENDING')
        if self.applicant_mode:
            # Supplied store contexts must still be valid; never downgrade a bad one.
            if scene:self.merchant.context(token,scene)
        elif scene!=self.scene:raise PermissionError('OCR_SCENE_MISMATCH')
        if type(params) is not dict or type(params.get('action')) is not str:
            raise ValueError('OCR_EXACT_REQUEST_REQUIRED')
        action=params['action'];base={'action','application'}
        extras={'submit':{'document_type','idempotency_key'},'read':{'job_id'},
                'confirm':{'job_id','revision','fields','idempotency_key','application_revision','provider_version'},'delete':{'job_id'},'apply_confirmed':{'job_id','confirmation_revision'}}
        if action not in extras or set(params)!=base|extras[action]:raise ValueError('OCR_EXACT_REQUEST_REQUIRED')
        p=self.bridge.authenticate(token)
        if not self.bridge.authorize_application(p,params['application']):raise PermissionError('OCR_APPLICATION_DENIED')
        key=(token,scene,repr(sorted(params.items())))
        headers={'Authorization':'Bearer '+token}
        if action=='submit':
            source=self.bridge.source(p,params['application'],params['document_type'])
            snapshot={k:v for k,v in source.items() if k!='data'}
            method='POST';path='/api/v1/ocr/jobs'
            headers['Idempotency-Key']=params['idempotency_key']
            options={'data':dict(document_type=source['document_type'],onboarding_application_id=params['application'],attachment_id=source['attachment_id']),
                     'files':{'file':('document',source['data'],source['mime'])}}
        else:
            job=self.bridge.store.get(params['job_id'],p.tenant_id)
            if not job or job['subject']!=p.subject or job['onboarding_application_id']!=params['application']:
                raise PermissionError('OCR_JOB_NOT_FOUND')
            if type(params['job_id']) is not str or not __import__('re').fullmatch('[a-f0-9-]{36}',params['job_id']):
                raise ValueError('OCR_JOB_ID_INVALID')
            if action=='apply_confirmed':
                # Explicit human application of an already-persisted confirmation.
                # Caller supplies no field values or permission; bridge rereads the
                # encrypted job, attachment, session and both original CAS versions.
                result=self.bridge.apply_confirmed(p,params['job_id'],expected_confirmation_revision=params['confirmation_revision'])
                return {'status_code':200,'result':result,'writeback':'WRITTEN' if result.get('written') is True else 'NO_EMPTY_FIELDS_CHANGED'}
            path='/api/v1/ocr/jobs/'+params['job_id'];method={'read':'GET','delete':'DELETE','confirm':'POST'}[action];options={}
            if action=='confirm':
                path+='/confirm';headers['Idempotency-Key']=params['idempotency_key']
                options['json']={key:params[key] for key in ('revision','fields','application_revision','provider_version')}
        async def request():
            import httpx
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://community-ocr.invalid') as client:
                return await client.request(method,path,headers=headers,**options)
        def run():
            import asyncio
            return asyncio.run(request())
        self.busy=True
        try:
            if self.inflight is not None and self.inflight_key!=key:
                if not self.inflight.done():raise PermissionError('OCR_REQUEST_PENDING')
                # Completed unrelated response is not returned to this caller.
                self.inflight=None;self.inflight_key=None;self.inflight_source=None
            if self.inflight is None:
                self.inflight=self.worker.submit(run);self.inflight_key=key
                self.inflight_source=snapshot if action=='submit' else None
            elif action=='submit' and snapshot!=self.inflight_source:
                raise PermissionError('OCR_SOURCE_CHANGED')
            future=self.inflight;deadline=time.monotonic()+self.owner.timeout
            while not future.done():
                self.owner.check()
                if time.monotonic()>=deadline:
                    # Retain the original future. A retry of this exact request
                    # resumes it; never enqueue duplicate inference or close the host.
                    raise PermissionError('OCR_REQUEST_PENDING')
                self.owner.pump();time.sleep(.002)
            try:response=future.result()
            finally:
                self.inflight=None;self.inflight_key=None;self.inflight_source=None
            # Never release a late result across session/source/revision changes.
            current=self.bridge.authenticate(token)
            if not self.bridge.authorize_application(current,params['application']):
                raise PermissionError('OCR_APPLICATION_DENIED')
            if action=='submit':
                latest=self.bridge.source(current,params['application'],params['document_type'])
                if {k:v for k,v in latest.items() if k!='data'}!=snapshot:
                    raise PermissionError('OCR_SOURCE_CHANGED')
            if response.status_code>=400:
                detail=response.json().get('detail','OCR_REQUEST_REJECTED')
                # Static API error codes only; no exception/body or identity echo.
                if type(detail) is not str or not __import__('re').fullmatch('[A-Z_]{1,100}',detail):detail='OCR_REQUEST_REJECTED'
                raise PermissionError(detail)
            return {'status_code':response.status_code,'result':response.json() if response.status_code!=204 else None,
                    'writeback':'NOT_REQUESTED_MANUAL_SUGGESTIONS_ONLY'}
        finally:self.busy=False
    def close(self):
        self.owner.close();self.worker.shutdown(wait=False,cancel_futures=True)
