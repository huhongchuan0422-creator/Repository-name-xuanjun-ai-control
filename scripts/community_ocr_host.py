"""Bounded same-owner OCR lifecycle; no listener, credentials or permission grant."""
import concurrent.futures
import queue
import threading
import time


class OcrPublicError(PermissionError):
    def __init__(self, code):
        if code not in ('OCR_SOURCE_CHANGED','OCR_AUTH_DENIED','OCR_UNAVAILABLE'):code='OCR_UNAVAILABLE'
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
            future.cancel();raise PermissionError('OCR_OWNER_TIMEOUT') from None
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
    def __init__(self, merchant, scene, api, store):
        from scripts.community_ocr_bridge import compose
        self.owner=OwnerCalls();self.merchant=merchant;self.scene=scene
        self.bridge,self.app=compose(merchant,scene,api,store,self.owner)
        self.worker=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='community-ocr')
        self.busy=False
    def dispatch(self, token, scene, params):
        self.owner.check()
        if self.busy:raise PermissionError('OCR_REQUEST_PENDING')
        if scene!=self.scene:raise PermissionError('OCR_SCENE_MISMATCH')
        if type(params) is not dict or type(params.get('action')) is not str:
            raise ValueError('OCR_EXACT_REQUEST_REQUIRED')
        action=params['action'];base={'action','application'}
        extras={'submit':{'document_type','idempotency_key'},'read':{'job_id'},
                'confirm':{'job_id','revision','fields','idempotency_key'},'delete':{'job_id'}}
        if action not in extras or set(params)!=base|extras[action]:raise ValueError('OCR_EXACT_REQUEST_REQUIRED')
        p=self.bridge.authenticate(token)
        if not self.bridge.authorize_application(p,params['application']):raise PermissionError('OCR_APPLICATION_DENIED')
        headers={'Authorization':'Bearer '+token}
        if action=='submit':
            source=self.bridge.source(p,params['application'],params['document_type'])
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
            path='/api/v1/ocr/jobs/'+params['job_id'];method={'read':'GET','delete':'DELETE','confirm':'POST'}[action];options={}
            if action=='confirm':
                path+='/confirm';headers['Idempotency-Key']=params['idempotency_key']
                options['json']={'revision':params['revision'],'fields':params['fields']}
        async def request():
            import httpx
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://community-ocr.invalid') as client:
                return await client.request(method,path,headers=headers,**options)
        def run():
            import asyncio
            return asyncio.run(request())
        self.busy=True
        try:
            future=self.worker.submit(run);deadline=time.monotonic()+self.owner.timeout
            while not future.done():
                self.owner.check()
                if time.monotonic()>=deadline:
                    self.close();raise PermissionError('OCR_REQUEST_TIMEOUT')
                self.owner.pump();time.sleep(.002)
            response=future.result()
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
