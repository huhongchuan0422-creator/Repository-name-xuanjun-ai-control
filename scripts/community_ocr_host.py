"""Bounded same-owner OCR lifecycle; no listener, credentials or permission grant."""
import concurrent.futures
import queue
import threading
import time


import contextvars
import functools
import json
import logging
import re
import uuid

DIAGNOSTIC_STAGES = frozenset(('ADMISSION','QUEUE','AUTHENTICATION','APPLICATION_AUTHORIZATION',
    'SOURCE_BINDING','EXECUTION','RESULT_READ','CONFIRMATION','WRITEBACK'))
DIAGNOSTIC_REASONS = frozenset(('HOST_NOT_READY','REQUEST_IN_PROGRESS','ANOTHER_REQUEST_IN_PROGRESS',
    'OWNER_QUEUE_FULL','OWNER_WAIT_TIMEOUT','HOST_STOPPED','OWNER_THREAD_REQUIRED','AUTHENTICATION_FAILED',
    'APPLICATION_ACCESS_DENIED','SOURCE_BINDING_CHANGED','APPLICATION_REVISION_CHANGED','PROVIDER_VERSION_CHANGED',
    'ATTACHMENT_CHANGED','SOURCE_EXPIRED','JOB_NOT_FOUND','IDEMPOTENCY_CONFLICT','RATE_LIMITED','IMAGE_INVALID',
    'MODEL_UNAVAILABLE','MODEL_PIN_MISMATCH','INFERENCE_FAILED','RESULT_READ_FAILED','CONFIRMATION_FAILED',
    'WRITEBACK_FAILED','UNEXPECTED_FAILURE'))
_CURRENT_DIAGNOSTIC = contextvars.ContextVar('community_ocr_request_diagnostic', default=None)
_LOG = logging.getLogger('community.ocr.diagnostic')


def current_diagnostic():
    return _CURRENT_DIAGNOSTIC.get()


def _reason(error, stage):
    # Match known static codes only. Never log/interpolate an exception message.
    code = str(error)
    exact = {
        'OCR_OWNER_TIMEOUT':'OWNER_WAIT_TIMEOUT','OCR_OWNER_QUEUE_FULL':'OWNER_QUEUE_FULL',
        'OCR_HOST_STOPPED':'HOST_STOPPED','OCR_CENTER_OWNER_THREAD_REQUIRED':'OWNER_THREAD_REQUIRED',
        'OCR_APPLICATION_DENIED':'APPLICATION_ACCESS_DENIED','APPLICATION_AUTHORIZATION_REVOKED':'APPLICATION_ACCESS_DENIED',
        'APPLICATION_OWNERSHIP_UNVERIFIED':'APPLICATION_ACCESS_DENIED',
        'AUTHENTICATION_REQUIRED':'AUTHENTICATION_FAILED','AUTHENTICATION_FAILED':'AUTHENTICATION_FAILED',
        'OCR_ORIGINAL_SESSION_REQUIRED':'AUTHENTICATION_FAILED','OCR_PRINCIPAL_CHANGED':'AUTHENTICATION_FAILED',
        'OCR_PERMISSION_DENIED':'AUTHENTICATION_FAILED','OCR_ATTACHMENT_BINDING_CHANGED':'SOURCE_BINDING_CHANGED',
        'ATTACHMENT_AUTHORIZATION_REVOKED':'SOURCE_BINDING_CHANGED','ATTACHMENT_CONTENT_BINDING_UNVERIFIED':'SOURCE_BINDING_CHANGED',
        'OCR_SOURCE_CHANGED':'SOURCE_BINDING_CHANGED','OCR_SHARED_SOURCE_CHANGED':'SOURCE_BINDING_CHANGED',
        'OCR_ATTACHMENT_EXPIRED':'SOURCE_EXPIRED','OCR_APPLICATION_REVISION_INVALID':'APPLICATION_REVISION_CHANGED',
        'OCR_APPLICATION_REVISION_CONFLICT':'APPLICATION_REVISION_CHANGED','OCR_PROVIDER_VERSION_CHANGED':'PROVIDER_VERSION_CHANGED',
        'OCR_PROVIDER_VERSION_CONFLICT':'PROVIDER_VERSION_CHANGED','OCR_ATTACHMENT_INTEGRITY':'ATTACHMENT_CHANGED',
        'OCR_ATTACHMENT_REQUIRED':'ATTACHMENT_CHANGED','OCR_JOB_NOT_FOUND':'JOB_NOT_FOUND','JOB_NOT_FOUND':'JOB_NOT_FOUND',
        'OCR_IDEMPOTENCY_CONFLICT':'IDEMPOTENCY_CONFLICT','OCR_CONFIRM_IDEMPOTENCY_CONFLICT':'IDEMPOTENCY_CONFLICT',
        'OCR_TENANT_RATE_LIMIT':'RATE_LIMITED','INVALID_IMAGE_SIZE':'IMAGE_INVALID','UNSUPPORTED_IMAGE_MAGIC':'IMAGE_INVALID',
        'IMAGE_DECODE_FAILED':'IMAGE_INVALID','IMAGE_PIXEL_LIMIT':'IMAGE_INVALID',
        'LICENSE_OCR_UPSTREAM_PIN_MISMATCH':'MODEL_PIN_MISMATCH','OCR_PINNED_DEPENDENCY_REQUIRED':'MODEL_PIN_MISMATCH',
        'OCR_INFERENCE_FAILED':'INFERENCE_FAILED',
    }
    if code in exact:return exact[code]
    for key in ('det','cls','rec'):
        if code == 'OCR_MODEL_SHA256_MISMATCH:'+key:return 'MODEL_PIN_MISMATCH'
        if code in ('OCR_MODEL_PATH_OR_SHA256_REQUIRED:'+key,'OCR_MODEL_FILE_UNAVAILABLE:'+key):return 'MODEL_UNAVAILABLE'
    if code=='OCR_MODEL_SHA256_REQUIRED':return 'MODEL_UNAVAILABLE'
    return {'AUTHENTICATION':'AUTHENTICATION_FAILED','APPLICATION_AUTHORIZATION':'APPLICATION_ACCESS_DENIED',
        'EXECUTION':'INFERENCE_FAILED','RESULT_READ':'RESULT_READ_FAILED',
        'CONFIRMATION':'CONFIRMATION_FAILED','WRITEBACK':'WRITEBACK_FAILED'}.get(stage,'UNEXPECTED_FAILURE')


def safe_diagnostic(value):
    if type(value) is not dict or value.get('version')!=1:return None
    if (value.get('stage') not in DIAGNOSTIC_STAGES or value.get('reason') not in DIAGNOSTIC_REASONS
            or type(value.get('diagnostic_id')) is not str or not re.fullmatch('[0-9a-f]{32}',value['diagnostic_id'])
            or type(value.get('retryable')) is not bool or type(value.get('request_retained')) is not bool):return None
    return {key:value[key] for key in ('version','diagnostic_id','stage','reason','retryable','request_retained')}


class _RequestDiagnostic:
    def __init__(self, action):
        self.action=action;self.diagnostic_id=uuid.uuid4().hex;self.stage='ADMISSION'
        self.failure=None;self.lock=threading.RLock();self.logged=False
        self.expected_provider_version=None;self.has_expected_binding=False;self.durable_job_retained=False
    def phase(self, stage):
        if stage in DIAGNOSTIC_STAGES:
            with self.lock:self.stage=stage
    def snapshot(self, reason, *, stage=None, retryable=False, retained=None):
        with self.lock:
            return dict(version=1,diagnostic_id=self.diagnostic_id,stage=stage or self.stage,
                reason=reason,retryable=retryable,request_retained=bool(retained or self.durable_job_retained))
    def fail(self, error=None, *, reason=None, stage=None):
        with self.lock:
            if self.failure is None:
                self.failure=self.snapshot(reason or _reason(error,stage or self.stage),stage=stage)
            if not self.logged:
                _LOG.warning('ocr_diagnostic %s',json.dumps(self.failure,sort_keys=True,separators=(',',':')))
                self.logged=True
            return dict(self.failure)


def _attach_failure(error, context=None, *, stage=None, reason=None):
    context=context or current_diagnostic() or _RequestDiagnostic(None)
    existing=safe_diagnostic(getattr(error,'ocr_diagnostic',None))
    if existing is None:
        error.ocr_diagnostic=context.fail(error,stage=stage,reason=reason)
    return error


def _pending(context, *, retained, reason='REQUEST_IN_PROGRESS'):
    error=PermissionError('OCR_REQUEST_PENDING')
    context=context or _RequestDiagnostic(None)
    error.ocr_diagnostic=context.snapshot(reason,retryable=True,retained=retained)
    return error


class OcrPublicError(PermissionError):
    def __init__(self, code, diagnostic=None):
        if code not in ('OCR_SOURCE_CHANGED','OCR_AUTH_DENIED','OCR_UNAVAILABLE','OCR_REQUEST_PENDING'):code='OCR_UNAVAILABLE'
        self.code=code
        self.ocr_diagnostic=safe_diagnostic(diagnostic)
        if self.ocr_diagnostic is None:
            context=current_diagnostic() or _RequestDiagnostic(None)
            if code=='OCR_REQUEST_PENDING':self.ocr_diagnostic=context.snapshot('REQUEST_IN_PROGRESS',retryable=True,retained=False)
            else:self.ocr_diagnostic=context.fail(reason='HOST_NOT_READY' if code=='OCR_UNAVAILABLE' else 'AUTHENTICATION_FAILED' if code=='OCR_AUTH_DENIED' else 'SOURCE_BINDING_CHANGED')
        super().__init__(code)
    def public_payload(self):
        return {'error':self.code,'ocr_diagnostic':dict(self.ocr_diagnostic)}


class OwnerCalls:
    def __init__(self, capacity=8, timeout=5):
        self.owner=threading.get_ident();self.pending=queue.Queue(maxsize=capacity)
        self.timeout=timeout;self.closed=False;self.lock=threading.RLock()
    def check(self):
        if threading.get_ident()!=self.owner:raise PermissionError('OCR_CENTER_OWNER_THREAD_REQUIRED')
        if self.closed:raise PermissionError('OCR_HOST_STOPPED')
    def __call__(self, operation):
        context=getattr(operation,'ocr_context',None) or current_diagnostic()
        stage=getattr(operation,'ocr_stage',None)
        with self.lock:
            if self.closed:raise PermissionError('OCR_HOST_STOPPED')
            if threading.get_ident()==self.owner:return operation()
            future=concurrent.futures.Future()
            try:self.pending.put_nowait((time.monotonic()+self.timeout,operation,future))
            except queue.Full:raise _attach_failure(PermissionError('OCR_OWNER_QUEUE_FULL'),context,stage=stage) from None
        try:return future.result(timeout=self.timeout)
        except concurrent.futures.TimeoutError:
            with self.lock:future.cancel()
            raise _attach_failure(PermissionError('OCR_OWNER_TIMEOUT'),context,stage=stage) from None
    def pump(self):
        self.check()
        try:deadline,operation,future=self.pending.get_nowait()
        except queue.Empty:return
        if time.monotonic()>=deadline:
            future.cancel();return
        if not future.set_running_or_notify_cancel():return
        try:future.set_result(operation())
        except BaseException as error:
            _attach_failure(error,getattr(operation,'ocr_context',None),stage=getattr(operation,'ocr_stage',None))
            future.set_exception(error)
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
        @functools.wraps(run_license_layout_ocr)
        def tracked_infer(*args, **kwargs):
            context=current_diagnostic()
            if context:
                context.phase('EXECUTION');context.durable_job_retained=True
            try:return run_license_layout_ocr(*args, **kwargs)
            except BaseException as error:
                _attach_failure(error,context,stage='EXECUTION');raise
        self.bridge,self.app=compose(merchant,scene,api,store,self.owner,
            infer=tracked_infer,applicant_mode=applicant_mode)
        self.worker=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='community-ocr')
        self.busy=False;self.inflight=None;self.inflight_key=None;self.inflight_source=None
    def service_actions(self):
        # Called only by the original serial server's owner thread. One existing
        # bounded-queue callback per idle iteration; no new thread or timeout.
        self.owner.pump()

    def dispatch(self, token, scene, params):
        context=_RequestDiagnostic(params.get('action') if type(params) is dict else None)
        reset=_CURRENT_DIAGNOSTIC.set(context)
        try:return self._dispatch(token,scene,params)
        except BaseException as error:
            if safe_diagnostic(getattr(error,'ocr_diagnostic',None)) is None:
                if not isinstance(error, PermissionError):context.phase({'submit':'EXECUTION','read':'RESULT_READ','confirm':'CONFIRMATION','apply_confirmed':'WRITEBACK'}.get(context.action,'ADMISSION'))
                _attach_failure(error,context)
            raise
        finally:_CURRENT_DIAGNOSTIC.reset(reset)

    def _dispatch(self, token, scene, params):
        context=current_diagnostic()
        self.owner.check()
        if self.busy:raise _pending(context,retained=False,reason='ANOTHER_REQUEST_IN_PROGRESS')
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
            context.expected_provider_version=job.get('provider_version');context.has_expected_binding=True
            context.durable_job_retained=True
            if action=='apply_confirmed':
                context.phase('WRITEBACK')
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
        request_context=context
        def run():
            import asyncio
            reset=_CURRENT_DIAGNOSTIC.set(request_context)
            request_context.phase({'submit':'QUEUE','read':'RESULT_READ','confirm':'CONFIRMATION','apply_confirmed':'WRITEBACK'}.get(action,'ADMISSION'))
            try:return asyncio.run(request())
            finally:_CURRENT_DIAGNOSTIC.reset(reset)
        self.busy=True
        try:
            if self.inflight is not None and self.inflight_key!=key:
                if not self.inflight.done():
                    context.phase('QUEUE')
                    raise _pending(context,retained=False,reason='ANOTHER_REQUEST_IN_PROGRESS')
                # Completed unrelated response is not returned to this caller.
                self.inflight=None;self.inflight_key=None;self.inflight_source=None
            if self.inflight is None:
                context.phase('QUEUE')
                self.inflight_diagnostic=context
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
                    raise _pending(getattr(self,'inflight_diagnostic',context),retained=True)
                self.owner.pump();time.sleep(.002)
            completed_context=getattr(self,'inflight_diagnostic',context)
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
                error=PermissionError(detail)
                if completed_context.failure is not None:error.ocr_diagnostic=dict(completed_context.failure)
                else:_attach_failure(error,completed_context)
                raise error
            if action in ('read','confirm'):
                # A completed API future may wait across several client polls.
                # Recheck its original job binding immediately before releasing
                # fields/confirmation; API-time authorization is not a lease.
                context.phase('SOURCE_BINDING')
                latest=self.bridge.source(current,params['application'],job['document_type'])
                reason=None
                if latest['application_revision']!=job.get('application_revision'):
                    reason='APPLICATION_REVISION_CHANGED'
                elif (latest['attachment_id']!=job['attachment_id']
                        or latest['document_sha256']!=job['document_sha256']
                        or latest['document_type']!=job['document_type']):
                    reason='ATTACHMENT_CHANGED'
                elif (job.get('provider_version') is not None and
                        (type(latest.get('wechat_version')) is not type(job['provider_version'])
                         or latest.get('wechat_version')!=job['provider_version'])):
                    reason='PROVIDER_VERSION_CHANGED'
                if reason:
                    raise _attach_failure(PermissionError('OCR_SOURCE_CHANGED'),context,
                        stage='SOURCE_BINDING',reason=reason)
            return {'status_code':response.status_code,'result':response.json() if response.status_code!=204 else None,
                    'writeback':'NOT_REQUESTED_MANUAL_SUGGESTIONS_ONLY'}
        finally:self.busy=False
    def close(self):
        self.owner.close();self.worker.shutdown(wait=False,cancel_futures=True)
