"""Connect the observed WeCom queue to the ORIGINAL admitted ingress gate.

Install only during the original exclusive startup, before any listener/worker.
No queue is copied, no accepted job is dropped, and no controller, journal,
seal descriptor or Writer is created here. The caller supplies the original
instance/source verifier and original callback/job identifiers.

This component has ordinary-fd/thread tests. It is not deployed to a live app,
does not establish complete source coverage and is not M99 acceptance.
"""
import queue
import re
import types


SOURCE_SHA256='aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402'


class QueueBindingHold(RuntimeError):
    pass


def need(ok,code):
    if not ok:raise QueueBindingHold(code)


class OriginalQueueFacade:
    """The observed producer uses put_nowait; only the bound worker consumes."""
    def __init__(self,owner):self.owner=owner
    def put_nowait(self,payload):
        self.owner.check()
        need(type(payload)is dict and bool(payload),'ORIGINAL_NONEMPTY_JOB_REQUIRED')
        token=self.owner.job_id(payload)
        self.owner.gate.submit(token,payload)
        return None
    def get(self,*args,**kwargs):
        raise QueueBindingHold('LEGACY_QUEUE_CONSUMPTION_FORBIDDEN')
    def get_nowait(self):
        raise QueueBindingHold('LEGACY_QUEUE_CONSUMPTION_FORBIDDEN')


class WeComQueueBinding:
    def __init__(self,ingress,original_gate,verify_original_instance,
                 verify_exclusive_startup,original_callback_id,original_job_id):
        need(all(callable(x) for x in (verify_original_instance,verify_exclusive_startup,
             original_callback_id,original_job_id)),'ORIGINAL_BINDING_CALLBACKS_REQUIRED')
        self.ingress=ingress;self.gate=original_gate
        self.verify=verify_original_instance;self.callback_id=original_callback_id;self.job_id=original_job_id
        need(verify_original_instance(ingress,SOURCE_SHA256)is True,'ORIGINAL_APP_SOURCE_NOT_VERIFIED')
        need(verify_exclusive_startup(ingress)is True,'EXCLUSIVE_PRELISTENER_STARTUP_REQUIRED')
        need('_pr99_queue_binding' not in vars(ingress),'SECOND_QUEUE_BINDING_FORBIDDEN')
        old=vars(ingress).get('jobs')
        need(type(old)is queue.Queue,'ORIGINAL_QUEUE_TYPE_REQUIRED')
        with old.mutex:
            need(not old.queue and old.unfinished_tasks==0,'EXISTING_ACCEPTED_QUEUE_PRESERVED')
        need(all(callable(getattr(original_gate,name,None)) for name in ('submit','process_one','run_sync','query')),
             'ORIGINAL_GATE_REQUIRED')
        state=original_gate.query()
        need(state['status']=='OPEN' and state['pending']==state['unknown']==0,'ORIGINAL_GATE_NOT_EMPTY_OPEN')
        worker=getattr(ingress,'worker_once',None);accept=getattr(ingress,'accept_callback',None)
        need(isinstance(worker,types.MethodType) and worker.__self__ is ingress and
             isinstance(accept,types.MethodType) and accept.__self__ is ingress,
             'ORIGINAL_BOUND_METHODS_REQUIRED')
        self.original_worker=worker;self.original_accept=accept;self.facade=OriginalQueueFacade(self)
        self.worker=self.worker_once;self.accept=self.accept_callback
        # Exclusive original startup is mandatory. Do not migrate a live queue
        # or keep a second consuming worker. One instance-dict update binds both
        # observed entry points and the producer's queue reference together.
        need(verify_exclusive_startup(ingress)is True,'STARTUP_EXCLUSIVITY_LOST')
        vars(ingress).update(jobs=self.facade,worker_once=self.worker,
                            accept_callback=self.accept,_pr99_queue_binding=self)
        self.check()

    def check(self):
        need(self.verify(self.ingress,SOURCE_SHA256)is True,'ORIGINAL_APP_BINDING_WITHDRAWN')
        value=vars(self.ingress)
        need(value.get('_pr99_queue_binding')is self and value.get('jobs')is self.facade and
             value.get('worker_once')is self.worker and value.get('accept_callback')is self.accept,
             'APPLICATION_BINDING_CHANGED_PRESERVE')

    def accept_callback(self,*args,**kwargs):
        self.check()
        token=self.callback_id(*args,**kwargs)
        need(type(token)is str and re.fullmatch('[A-Za-z0-9_-]{1,100}',token),'ORIGINAL_CALLBACK_ID_REQUIRED')
        # Tracks the audit write AFTER queue admission as well as enqueueing.
        # Any original callback exception remains UNKNOWN until original outcome
        # reconciliation, including a rejection that may have had no effects.
        return self.gate.run_sync(token,self.original_accept,*args,**kwargs)

    def worker_once(self,job=None):
        self.check()
        need(job is None,'DIRECT_JOB_BYPASS_FORBIDDEN')
        def handle(payload):
            self.check()
            # The original implementation gets from jobs only when job is
            # falsey. Nonempty original dictionaries avoid that second get.
            need(type(payload)is dict and bool(payload),'ORIGINAL_NONEMPTY_JOB_REQUIRED')
            result=self.original_worker(job=payload)
            self.check()
            return result
        # The gate acknowledges the accepted queued ticket ONLY after the
        # original worker returned and source binding is still valid.
        return self.gate.process_one(handle)

    def query(self):
        self.check()
        return {'scope':'PR99_WECOM_ORIGINAL_GATE_QUEUE_BINDING_NOT_GLOBAL_FENCE',
          'source_sha256':SOURCE_SHA256,'gate':self.gate.query(),
          'new_writer_created':False,'live_deployment_proven':False}
