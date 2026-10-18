"""Original capture -> received fd reconciliation -> original Writer handoff.

No cloud dispatch, staging directory, claim, Writer epoch or path-guard fallback.
Real transport must already have populated the exact admitted target fds and
recorded receive_final in the original journal. Original authority supplies the
actual assignment CAS/query/verification; fixture acknowledgements are not trust.
"""
import fcntl
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import time

from catalogue_binding import digest, encode
from held_proof import HeldProof

HOST='iZvt5t8tlrm8oiZ'
RELEASE='/opt/xuanjun-migration-s07/releases/domestic-final-v1'
SHA=re.compile('[0-9a-f]{64}')
LINKS={'venv/bin/python':'python3','venv/bin/python3':'/usr/bin/python3',
       'venv/bin/python3.11':'python3','venv/lib64':'lib'}


class HandoffHold(RuntimeError):pass


def need(ok,code):
    if not ok:raise HandoffHold(code)


def file_sha(raw):return hashlib.sha256(raw).hexdigest()


def relative(value):
    need(type(value)is str and 0<len(value)<=500 and '\0' not in value and
         str(PurePosixPath(value))==value and not value.startswith('/') and
         all(p not in ('','.','..') for p in value.split('/')),'FINAL_RELATIVE_PATH')
    return value


class OriginalSourceEvidence:
    """Verified read-only source query; no cross-host descriptor assumption.

    The original authenticated transport supplies query/verification. This view
    does not create a source process, RunCommand, task, claim or Writer. Source
    native fds remain on Tokyo; target native fds remain on the domestic host.
    """
    def __init__(self,controller,capture_contract,query_original,verify_original):
        self.controller=controller;self.config=json.loads(encode(capture_contract))
        self.config_digest=digest(self.config)
        need(callable(query_original) and callable(verify_original),'ORIGINAL_SOURCE_QUERY_REQUIRED')
        self.query=query_original;self.verify=verify_original
        self._config()

    def _config(self):
        self.controller._bound('query')
        claim,_,_=self.controller.load()
        need(digest(self.config)==self.config_digest==claim['plan']['bindings']['final_manifest_contract'],'ORIGINAL_SOURCE_CONTRACT_BINDING')
        need(type(self.config)is dict and set(self.config)=={'schema','writer_inventory_sha256','epoch','wal_sources','jobs','handoff'} and
             type(self.config.get('schema'))is int and self.config['schema']==1 and
             type(self.config.get('epoch'))is int and self.config['epoch']==self.controller.binding['epoch'] and
             self.config.get('writer_inventory_sha256')==self.controller.binding['writer_inventory_sha256'],
             'ORIGINAL_SOURCE_CONTRACT_SCOPE')

    def verified(self):
        self._config();_,events,_=self.controller.load()
        results=[e['receipt'] for e in events if e.get('type')=='RESULT' and e['receipt']['stage']=='final_snapshot']
        requests=[e['request'] for e in events if e.get('type')=='INTENT' and e['request']['stage']=='final_snapshot']
        need(len(results)==len(requests)==1 and results[0]['status']=='SUCCEEDED','ORIGINAL_CAPTURE_NOT_TERMINAL')
        req=requests[0];expected=results[0]
        proof=self.query(req,expected)
        need(type(proof)is dict and self.verify(req,expected,proof)is True,'ORIGINAL_SOURCE_QUERY_NOT_VERIFIED')
        keys={'source_host','transaction_id','plan_digest','epoch','snapshot_result','fence_raw','snapshot_raw','current_fence_sha256','captured_outputs_verified'}
        need(set(proof)==keys and proof['source_host']=='iZ6wee8q9z4t03hvqumwfhZ' and
             proof['transaction_id']==self.controller.binding['transaction_id'] and
             proof['plan_digest']==self.controller.binding['plan_digest'] and
             proof['epoch']==self.controller.binding['epoch'] and proof['snapshot_result']==expected and
             proof['captured_outputs_verified']is True,'ORIGINAL_SOURCE_QUERY_BINDING')
        raw=proof['snapshot_raw'];fence_raw=proof['fence_raw']
        need(type(raw)is bytes and len(raw)<=2097152 and type(fence_raw)is bytes and len(fence_raw)<=16384,'SOURCE_PROOF_BOUND')
        snapshot=json.loads(raw);fence=json.loads(fence_raw)
        need(encode(snapshot)==raw and encode(fence)==fence_raw and file_sha(raw)==expected['evidence'],'SOURCE_PROOF_BYTES_BINDING')
        need(snapshot.get('action')=='PR99_BOUND_CAPTURE_V1' and snapshot.get('capture_contract_sha256')==self.config_digest and
             snapshot.get('source_fence_sha256')==file_sha(fence_raw)==proof['current_fence_sha256'] and
             snapshot.get('transaction_id')==proof['transaction_id'] and snapshot.get('plan_digest')==proof['plan_digest'] and
             snapshot.get('epoch')==proof['epoch'],'SOURCE_CAPTURE_AND_CURRENT_FENCE_BINDING')
        need(fence.get('action')=='PR99_SOURCE_WRITER_FENCE_V1' and fence.get('source_host')==proof['source_host'] and
             fence.get('transaction_id')==proof['transaction_id'] and fence.get('plan_digest')==proof['plan_digest'] and
             fence.get('writer_epoch')==proof['epoch'] and fence.get('writer_inventory_sha256')==self.controller.binding['writer_inventory_sha256'] and
             fence.get('writers_stopped')is True and fence.get('inflight_drained')is True and
             fence.get('unresolved_shared_writers')==[],'SOURCE_REAL_FENCE_REQUIRED')
        recorded_fences=[e['receipt'] for e in events if e.get('type')=='RESULT' and e['receipt']['stage']=='fence_source']
        need(len(recorded_fences)==1 and recorded_fences[0]['status']=='SUCCEEDED' and
             recorded_fences[0]['evidence']==file_sha(fence_raw),'ORIGINAL_FENCE_RESULT_BINDING')
        need(type(fence.get('observed_at'))is type(snapshot.get('observed_at'))is int and
             0<fence['observed_at']<=snapshot['observed_at']<=int(time.time()),'SOURCE_CAPTURE_TIME_ORDER')
        self._config()
        return snapshot,fence,fence_raw


class FinalHandoff:
    def __init__(self,controller,capture,target_fds,check_target,observe_members,
                 checkpoint_fd,check_checkpoint,assignment_fd,check_assignment,
                 assign_original,query_original,verify_original):
        self.c=controller;self.capture=capture
        need(isinstance(capture,OriginalSourceEvidence) and capture.controller is controller,'ORIGINAL_CONTROLLER_REQUIRED')
        self.check_target=check_target;self.members=observe_members
        self.assign=assign_original;self.query_assignment=query_original;self.verify=verify_original
        need(all(callable(f) for f in (check_target,observe_members,assign_original,query_original,verify_original)),
             'ORIGINAL_TARGET_AND_ASSIGNMENT_BINDINGS_REQUIRED')
        self.config=json.loads(encode(capture.config.get('handoff')))
        self.config_digest=digest(self.config)
        self.fds=dict(target_fds);self.identities={}
        self.checkpoint=HeldProof(checkpoint_fd,controller,check_checkpoint,limit=2097152)
        self.assignment=HeldProof(assignment_fd,controller,check_assignment)
        self._config()

    def _config(self):
        self.c._bound('query');self.capture._config()
        need(digest(self.config)==self.config_digest and self.capture.config.get('handoff')==self.config,'HANDOFF_CONFIG_DRIFT')
        x=self.config
        need(type(x)is dict and set(x)=={'schema','host','release','identity','files','links','database_job_id','start_source_sha256'},'HANDOFF_SCHEMA')
        need(type(x['schema'])is int and x['schema']==1 and x['host']==HOST and x['release']==RELEASE,'FINAL_FIXED_TARGET')
        who=x['identity']
        need(type(who)is dict and set(who)=={'name','uid','gid'} and who['name']=='xuanjun-s07','FINAL_IDENTITY_SCHEMA')
        need(all(type(who[k])is int and 0<who[k]<65534 and who[k]not in (1000,1001) for k in ('uid','gid')),'FINAL_DEDICATED_IDENTITY')
        claim,_,_=self.c.load()
        need(digest(who)==claim['plan']['bindings']['runtime_identity'],'ORIGINAL_TARGET_IDENTITY_BINDING')
        need(type(x['start_source_sha256'])is str and SHA.fullmatch(x['start_source_sha256']),'FINAL_START_SOURCE_BINDING')
        need(type(x['files'])is dict and 0<len(x['files'])<=12000 and set(self.fds)==set(x['files']),'FINAL_FILE_SET')
        need(x['links']==LINKS,'FINAL_LINK_SET')
        paths=set(x['files'])|set(x['links'])
        for name in paths:
            relative(name)
            need(not any(str(p) in paths for p in PurePosixPath(name).parents if str(p)!='.'),'FINAL_MEMBER_PARENT_OVERLAP')
        jobs={j['id']:j for j in self.capture.config['jobs']};used=set()
        need(x['database_job_id'] in jobs and jobs[x['database_job_id']]['kind']=='SQLITE','FINAL_PRIMARY_DATABASE')
        identities=set()
        for name,row in x['files'].items():
            need(type(row)is dict and set(row)=={'job_id','sha256','bytes','uid','gid','mode'},'FINAL_FILE_SCHEMA')
            if row['job_id'] is None:
                need(type(row['sha256'])is str and SHA.fullmatch(row['sha256']) and
                     type(row['bytes'])is int and 0<=row['bytes']<=67108864,'STATIC_FILE_BINDING')
            else:
                need(row['job_id'] in jobs and row['job_id']not in used and row['sha256'] is row['bytes'] is None,'CAPTURE_JOB_TARGET_BINDING')
                used.add(row['job_id'])
            need(type(row['uid'])is type(row['gid'])is int and type(row['mode'])is int and
                 row['uid']in (0,who['uid']) and row['gid']in (0,who['gid']) and
                 row['mode']in (0o400,0o600,0o640,0o644,0o750,0o755),'FINAL_FILE_OWNER_MODE')
            fd=self.fds[name]
            need(type(fd)is int,'ORIGINAL_RECEIVED_FD_REQUIRED')
            s=os.fstat(fd);flags=fcntl.fcntl(fd,fcntl.F_GETFL);identity=(s.st_dev,s.st_ino)
            need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=67108864 and
                 s.st_uid==row['uid'] and s.st_gid==row['gid'] and stat.S_IMODE(s.st_mode)==row['mode'] and
                 flags&os.O_ACCMODE in (os.O_RDONLY,os.O_RDWR) and not flags&os.O_APPEND,'RECEIVED_FD_IDENTITY')
            need(identity not in identities,'RECEIVED_FD_ALIAS');identities.add(identity)
            need(self.identities.get(name,identity)==identity,'RECEIVED_FD_REPLACED');self.identities[name]=identity
        need(used==set(jobs),'UNCOVERED_CAPTURE_JOB')
        proof_ids={(os.fstat(p.fd).st_dev,os.fstat(p.fd).st_ino) for p in (self.checkpoint,self.assignment)}
        need(len(proof_ids)==2 and not identities.intersection(proof_ids),'PROOF_OR_DATA_FD_ALIAS')
        need(self.check_target(x,self.identities)is True,'ORIGINAL_TARGET_PATH_IDENTITY_REQUIRED')

    def _recorded(self,stage):
        claim,events,_=self.c.load()
        results=[e['receipt'] for e in events if e.get('type')=='RESULT' and e['receipt']['stage']==stage]
        intents=[e['request'] for e in events if e.get('type')=='INTENT' and e['request']['stage']==stage]
        need(len(results)==len(intents)==1 and results[0]['status']=='SUCCEEDED','ORIGINAL_'+stage.upper()+'_RESULT_REQUIRED')
        return intents[0],results[0]

    def _captured(self):
        self._config()
        self._recorded('final_snapshot')
        saved,fence,fence_raw=self.capture.verified()
        need(saved['transaction_id']==self.c.binding['transaction_id'] and
             saved['plan_digest']==self.c.binding['plan_digest'] and saved['epoch']==self.c.binding['epoch'],'FINAL_TRANSACTION_BINDING')
        return saved,fence,fence_raw

    def _received(self):
        saved,fence,fence_raw=self._captured();self._recorded('receive_final')
        observed=self.members()
        need(type(observed)is dict and set(observed)=={'files','links'} and
             type(observed['files'])is list and len(observed['files'])==len(set(observed['files'])) and
             set(observed['files'])==set(self.config['files']) and observed['links']==self.config['links'],'RECEIVED_COMPLETE_MEMBERSHIP')
        all_files={};data_files={};total=0
        for name,row in self.config['files'].items():
            self.c._bound('query');fd=self.fds[name];before=os.fstat(fd)
            need((before.st_dev,before.st_ino)==self.identities[name],'RECEIVED_FD_REPLACED')
            raw=os.pread(fd,67108865,0);after=os.fstat(fd)
            need((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns) and len(raw)==before.st_size<=67108864,'RECEIVED_DATA_DRIFT')
            actual=file_sha(raw);size=len(raw);total+=size
            need(total<=536870912,'RECEIVED_TOTAL_BOUND')
            if row['job_id']is None:expected=row
            else:
                expected=saved['results'].get(row['job_id'])
                need(type(expected)is dict and expected.get('class')in ('FINAL_FENCED_SQLITE_CANDIDATE','FINAL_FENCED_FILE_CANDIDATE') and
                     expected.get('fence_proof_sha256')==file_sha(fence_raw),'RECEIVED_CAPTURE_BINDING')
                if expected['class']=='FINAL_FENCED_SQLITE_CANDIDATE':need(expected.get('integrity')=='PASS','RECEIVED_DATABASE_INTEGRITY')
                data_files[name]=actual
            need(type(expected.get('sha256'))is str and SHA.fullmatch(expected['sha256']) and
                 type(expected.get('bytes'))is int and actual==expected['sha256'] and size==expected['bytes'],
                 'RECEIVED_BYTES_HASH_MISMATCH')
            all_files[name]=actual
        need(self.members()==observed,'RECEIVED_MEMBERSHIP_CHANGED')
        self._config();need(self.capture.verified()[2]==fence_raw,'SOURCE_FENCE_CHANGED_DURING_RECONCILE')
        primary=saved['results'][self.config['database_job_id']]
        checkpoint={'class':'FINAL_CANONICAL_CHECKPOINT','source_fence_sha256':file_sha(fence_raw),
          'files':data_files,'database_integrity':'PASS','database_schema_sha256':primary['schema_sha256'],
          'captured_at':saved['observed_at'],'transaction_id':self.c.binding['transaction_id'],
          'plan_digest':self.c.binding['plan_digest'],'writer_inventory_sha256':self.c.binding['writer_inventory_sha256'],
          'writer_epoch':self.c.binding['epoch'],'full_file_hashes_sha256':digest(all_files),'observed_at':int(time.time())}
        return checkpoint,all_files,fence_raw

    def _reconcile(self,request,query_only=False):
        checkpoint,_,_=self._received()
        stored=self.checkpoint(checkpoint,query_only=query_only)
        return self._receipt(request,digest(stored))

    def _assignment_input(self):
        _,reconciled=self._recorded('reconcile_final')
        expected,all_files,fence_raw=self._received()
        checkpoint=self.checkpoint(expected,query_only=True)
        need(digest(checkpoint)==reconciled['evidence'],'ORIGINAL_FINAL_CHECKPOINT_EVIDENCE')
        return {'action':'PR99_CANONICAL_WRITER_ASSIGNMENT_V1','target_host':HOST,'release':RELEASE,
          'checkpoint_sha256':digest(checkpoint),'writer_inventory_sha256':self.c.binding['writer_inventory_sha256'],
          'writer_epoch':self.c.binding['epoch'],'target_identity':'xuanjun-s07','source_writer_resumed':False,
          'scope':['portal','contact','customer-service'],'transaction_id':self.c.binding['transaction_id'],
          'plan_digest':self.c.binding['plan_digest'],'source_fence_sha256':file_sha(fence_raw)},checkpoint,all_files

    def _assign(self,request,query_only=False):
        binding,checkpoint,all_files=self._assignment_input()
        if query_only:proof=self.query_assignment(request,binding)
        else:
            self.c._bound('dispatch')
            proof=self.assign(request,binding)
        # The actual original assignment authority must verify its durable CAS
        # result. A locally constructed document/boolean is not a Writer grant.
        need(type(proof)is dict and self.verify(request,binding,proof)is True,'ORIGINAL_WRITER_ASSIGNMENT_NOT_VERIFIED')
        need(proof.get('binding')==binding and proof.get('status')=='TARGET_ASSIGNED_NOT_STARTED' and
             proof.get('exclusive')is True and type(proof.get('authority_receipt_sha256'))is str and
             SHA.fullmatch(proof['authority_receipt_sha256']),'ORIGINAL_WRITER_ASSIGNMENT_BINDING')
        current,_,_=self._assignment_input()
        need(current==binding,'POST_ASSIGNMENT_FINAL_BINDING_CHANGED')
        document={**binding,'authority_receipt_sha256':proof['authority_receipt_sha256'],'observed_at':int(time.time())}
        stored=self.assignment(document,query_only=query_only)
        return self._receipt(request,digest(stored))

    def _receipt(self,request,evidence):
        return {'request_digest':self.c.m.digest(request),'operation_id':request['operation_id'],
          'stage':request['stage'],'status':'SUCCEEDED','evidence':evidence}

    def perform(self,request):
        self._config()
        need(request.get('stage')in ('reconcile_final','assign_writer'),'HANDOFF_STAGE_SCOPE')
        action=self._reconcile if request['stage']=='reconcile_final' else self._assign
        return self.c.perform(request,lambda r:action(r),lambda r:action(r,True))
