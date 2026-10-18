"""Connect original journal -> verified drain/Fence -> admitted WAL/file I/O.

No CLI, RPC, credentials, new Journal/claim/Writer, alternate guard or issuer.
The original admitted fd owner supplies all live dependencies. This candidate
does not remove the original guard's release/M99 prerequisite.
"""
import hashlib
import json
from pathlib import Path
import re
import time

import node_bindings as wal
from catalogue_binding import digest, encode
from held_proof import HeldProof
from source_fence import SourceFence, LinuxFenceBackend


class SessionHold(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise SessionHold(code)


def wal_source_manifest():
    base=Path(wal.__file__).parent
    return {n:hashlib.sha256((base/n).read_bytes()).hexdigest() for n in
            ('node_bindings.py','lost_invoke_reconciliation.py','sqlite_wal_vfs.py')}


class CaptureSession:
    def __init__(self, controller, catalogue, verify_catalogue, original_guard,
                 cgroup_bindings, check_backend_binding, verify_real_drain,
                 fence_output_fd, check_fence_output, snapshot_output_fd,
                 check_snapshot_output, capture_contract):
        controller._bound('query')
        self.controller=controller
        self.io=original_guard
        self.config=json.loads(encode(capture_contract))
        self.config_digest=digest(self.config)
        self._config()
        self.fence_output=HeldProof(fence_output_fd,controller,check_fence_output)
        self.snapshot_output=HeldProof(snapshot_output_fd,controller,check_snapshot_output,limit=2097152)
        self.provider=SourceFence(controller,catalogue,controller.binding['writer_inventory_sha256'],verify_catalogue,
            LinuxFenceBackend(original_guard,cgroup_bindings,check_backend_binding),verify_real_drain,self.fence_output)
        self.objects={o['id']:o for o in self.provider.catalogue['objects']}
        covered=set();destinations=[]
        for job in self.config['jobs']:
            need(type(job)is dict and set(job)=={'id','kind','source_id','destination','schema_sha256','wal_id','shm_id'},'CAPTURE_JOB_SCHEMA')
            need(type(job['id'])is str and re.fullmatch('[A-Za-z0-9_-]{1,80}',job['id']), 'CAPTURE_JOB_ID')
            obj=self.objects.get(job['source_id'])
            need(obj and obj['kind']=='FILE' and obj['classification']=='COPY_FENCED','CAPTURE_SOURCE_NOT_FENCED')
            need(job['kind'] in ('SQLITE','FILE'), 'CAPTURE_JOB_KIND')
            members=[job['source_id']]
            if job['kind']=='SQLITE':
                need(type(job['schema_sha256'])is str and re.fullmatch('[0-9a-f]{64}',job['schema_sha256']),'SQLITE_SCHEMA_REQUIRED')
                for name,suffix in (('wal_id','-wal'),('shm_id','-shm')):
                    member=job[name]
                    if member is not None:
                        side=self.objects.get(member)
                        need(side and side['path']==obj['path']+suffix and side['kind']=='FILE' and side['classification']=='COPY_FENCED', 'SIDECAR_BINDING')
                        members.append(member)
            else:
                need(job['schema_sha256'] is job['wal_id'] is job['shm_id'] is None,'FILE_JOB_SIDECAR')
            need(not covered.intersection(members), 'DUPLICATE_CAPTURE_MEMBER');covered.update(members)
            path=job['destination']
            need(type(path)is str and '\0' not in path and Path(path).is_absolute() and '..' not in Path(path).parts and str(Path(path))==path,'CAPTURE_DESTINATION')
            target=Path(path)
            for source in self.objects.values():
                p=Path(source['path'])
                need(target!=p and target not in p.parents and p not in target.parents,'CAPTURE_SOURCE_DESTINATION_OVERLAP')
            need(all(target!=p and target not in p.parents and p not in target.parents for p in destinations),'CAPTURE_OUTPUT_OVERLAP')
            destinations.append(target)
        need(len({j['id'] for j in self.config['jobs']})==len(self.config['jobs']), 'DUPLICATE_JOB_ID')
        expected={o['id'] for o in self.objects.values() if o['kind']=='FILE' and o['classification']=='COPY_FENCED'}
        need(covered==expected,'UNCOVERED_FENCED_DATA_FILE')

    def _config(self):
        self.controller._bound('query')
        need(digest(self.config)==self.config_digest,'CAPTURE_CONFIG_DRIFT')
        keys={'schema','writer_inventory_sha256','epoch','wal_sources','jobs'}
        need(type(self.config)is dict and set(self.config) in (keys,keys|{'handoff'}), 'CAPTURE_CONFIG_SCHEMA')
        need(type(self.config['schema'])is int and self.config['schema']==1 and self.config['epoch']==self.controller.binding['epoch'] and
             self.config['writer_inventory_sha256']==self.controller.binding['writer_inventory_sha256'], 'CAPTURE_WRITER_BINDING')
        claim,_,_=self.controller.load()
        # Bind the capture INPUT contract, never the as-yet-uncreated fence hash.
        # The real fence RESULT is obtained from the original durable journal.
        need(self.config_digest==claim['plan']['bindings']['final_manifest_contract'], 'ORIGINAL_CAPTURE_CONTRACT_BINDING')
        need(self.config['wal_sources']==wal_source_manifest(), 'ACCEPTED_WAL_SOURCE_DRIFT')
        need(type(self.config['jobs'])is list and 0<len(self.config['jobs'])<=12000,'CAPTURE_JOB_COUNT')
        need(self.io is not None and all(callable(getattr(self.io,n,None)) for n in
             ('check','read','exists','mkdir','write','create_fd','sync')), 'ORIGINAL_ADMITTED_GUARD_REQUIRED')
        need(self.io.check() is True,'ORIGINAL_GUARD_BINDING')

    def _fence(self):
        self._config()
        claim,events,_=self.controller.load()
        result=[e['receipt'] for e in events if e.get('type')=='RESULT' and e['receipt']['stage']=='fence_source']
        intent=[e['request'] for e in events if e.get('type')=='INTENT' and e['request']['stage']=='fence_source']
        need(len(result)==len(intent)==1 and result[0]['status']=='SUCCEEDED','DURABLE_FENCE_RESULT_REQUIRED')
        current=self.provider.query(intent[0])
        need(current==result[0],'LIVE_FENCE_CHANGED_PRESERVE')
        return result[0]['evidence']

    def _write_bound(self):
        self.controller._bound('dispatch')
        claim,_,_=self.controller.load()
        self.controller.m.validate_plan(claim['plan'],self.controller.binding['plan_digest'],time.time())
        return self._fence()

    def _material(self,job,query_only=False):
        source=Path(self.objects[job['source_id']]['path']);destination=Path(job['destination'])
        proof=self._fence()
        if not query_only:
            self._write_bound()
        if job['kind']=='SQLITE':
            for name,suffix in (('wal_id','-wal'),('shm_id','-shm')):
                need(self.io.exists(source.with_name(source.name+suffix)) == (job[name] is not None), 'SIDECAR_MEMBERSHIP_CHANGED')
            if not query_only:
                return wal.snapshot_sqlite_with_original_io(self.io,source,destination,self._write_bound,job['schema_sha256'])
            receipt=json.loads(self.io.read(destination/'sqlite-checkpoint.receipt.json',1048576))
            need(receipt.get('class')=='FINAL_FENCED_SQLITE_CANDIDATE' and receipt.get('fence_proof_sha256')==proof and
                 receipt.get('schema_sha256')==job['schema_sha256'] and receipt.get('integrity')=='PASS', 'SNAPSHOT_RECEIPT_BINDING')
            recovery=receipt.get('recovery',{})
            main=self.io.read(source,67108864)
            w=self.io.read(source.with_name(source.name+'-wal'),67108864) if job['wal_id'] is not None else None
            need(recovery.get('input_main_sha256')==wal.sha(main) and recovery.get('input_wal_sha256')==(None if w is None else wal.sha(w)),'CAPTURE_SOURCE_CHANGED')
            output=self.io.read(destination/'final.db',67108864)
            need(wal.sha(output)==receipt.get('sha256') and len(output)==receipt.get('bytes'),'CAPTURE_OUTPUT_CHANGED')
            need(self.io.read(destination/'captured/source.db',67108864)==main and
                 (w is None or self.io.read(destination/'captured/source.db-wal',67108864)==w),'CAPTURE_ORIGINAL_BYTES_CHANGED')
            self._fence()
            return receipt
        main=self.io.read(source,67108864)
        if not query_only:
            fd=self.io.create_fd(destination,mode=0o600)
            try:
                import os
                self._write_bound()
                need(os.fstat(fd).st_size==0,'FILE_OUTPUT_NOT_EMPTY')
                offset=0
                while offset<len(main):
                    self._write_bound();n=os.pwrite(fd,main[offset:offset+1048576],offset)
                    need(n>0,'PARTIAL_FILE_PRESERVE');offset+=n
                os.fsync(fd);need(os.pread(fd,len(main)+1,0)==main,'FILE_OUTPUT_DRIFT')
                os.fchmod(fd,0o400);os.fsync(fd)
            finally:
                os.close(fd)
            self.io.sync(destination.parent)
        need(self.io.read(source,67108864)==main and self.io.read(destination,67108864)==main,'FILE_CAPTURE_DRIFT')
        self._fence()
        return {'class':'FINAL_FENCED_FILE_CANDIDATE','fence_proof_sha256':proof,'sha256':wal.sha(main),'bytes':len(main)}

    def _snapshot(self,request,query_only=False):
        proof=self._fence()
        result={job['id']:self._material(job,query_only) for job in self.config['jobs']}
        payload={'action':'PR99_BOUND_CAPTURE_V1','transaction_id':self.controller.binding['transaction_id'],
            'plan_digest':self.controller.binding['plan_digest'],'epoch':self.controller.binding['epoch'],
            'capture_contract_sha256':self.config_digest,'source_fence_sha256':proof,'results':result,'observed_at':int(time.time())}
        stored=self.snapshot_output(payload,query_only=query_only)
        need(stored['observed_at']<=payload['observed_at'],'SNAPSHOT_TIME')
        return {'request_digest':self.controller.m.digest(request),'operation_id':request['operation_id'],
                'stage':'final_snapshot','status':'SUCCEEDED','evidence':digest(stored)}

    def perform(self,request):
        """The ONLY mutation entry: original intent is durable before provider I/O.

        Existing intent always selects query, including after partial capture.
        Query never creates output, reapplies a fence or reruns SQLite recovery.
        """
        self._config()
        need(request.get('stage') in ('fence_source','final_snapshot'),'SESSION_STAGE_SCOPE')
        def dispatch(req):
            return self.provider.dispatch(req) if req['stage']=='fence_source' else self._snapshot(req)
        def query(req):
            return self.provider.query(req) if req['stage']=='fence_source' else self._snapshot(req,True)
        return self.controller.perform(request,dispatch,query)
