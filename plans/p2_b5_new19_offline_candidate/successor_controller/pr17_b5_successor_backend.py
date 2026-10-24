"""PR17 c53 R2 POSIX backend candidate. Not executable by itself.

This adapter relies ONLY on byte-pinned old R2 helpers as an I/O primitive,
not on its e78 Transaction, entry(), execute() or old request IDs. It must be
bound to an independently reviewed, authenticated original-client authority
provider. Without that provider all live actions fail before service stop.
No credentials, grant or ACK are created here.
"""
import os
import fcntl
import sqlite3
import stat
import time
import hashlib
import json
import re
import ctypes
import pr17_b5_successor_binder as binder

import pr17_b5_successor_review as c53

class Hold(c53.Hold):
    pass

def _rename_release_noreplace(directory, old, new):
    libc=ctypes.CDLL(None,use_errno=True)
    rename=getattr(libc,'renameat2',None)
    c53.require(rename is not None,'RELEASE_ATOMIC_NOREPLACE_UNAVAILABLE')
    rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,
                     ctypes.c_char_p,ctypes.c_uint)
    rename.restype=ctypes.c_int
    if rename(directory,old.encode('ascii'),directory,new.encode('ascii'),1)!=0:
        raise Hold('RELEASE_ATOMIC_NOREPLACE_FAILED')

class R2HostBackend:
    def __init__(self, *, legacy_io, spec, source_blobs, observed_bytes,
                 authority=None, release_gate=None):
        self.legacy=legacy_io
        self.spec=spec
        c53.require(type(observed_bytes) is dict and
                    type(source_blobs) is dict,'GENERATOR_INPUT_TYPE')
        self.frozen_baselines=dict(observed_bytes)
        self.source_blobs=dict(source_blobs)
        self.generator_identities={}
        self.generator_inputs_verified=False
        self.authority=authority
        self.release_gate=release_gate
        self.paths=spec['fixed_paths']
        self.job=self.paths['job_proposed']
        self.db=None;self.lock_fd=None;self.reserved=False;self.seq=0
        self.verified_original_db=False
        self.before={};self.links={};self.new={};self.worker_stopped=False
        self.tried_start=False;self.window_open=False;self.activation_committed=False
        self.expected_ids=tuple(spec['batch']['draft_request_ids'])
        self.bundle=None;self.stop_outcome=None
        c53.require(self.job=='/opt/xuanjun-cloud-connection/l2-b5-staged-'+c53.COMMIT[:12],'JOB_SCOPE')
        self.release_commit=c53.COMMIT
        self.runtime_manifest_sha256=c53.MANIFEST
        self.original_archive_sha256=binder.ARCHIVE_SHA
        self.backup_verified=False
        c53.require(tuple(self.paths['configs'])==c53.CONFIGS,'CONFIG_SCOPE')
        c53.require(tuple(self.paths['protected_slots'])==c53.SLOTS,'SLOT_SCOPE')
        c53.require(tuple(self.paths['current'])==tuple(x+'/current' for x in c53.BASES),'CURRENT_SCOPE')
        c53.require(tuple(self.paths['target_release'])==tuple(x+'/releases/'+c53.COMMIT for x in c53.BASES),'RELEASE_SCOPE')
        c53.require(tuple(self.paths['stage_proposed'])==tuple(x+'/releases/.l2-b5-staged-'+c53.COMMIT[:12] for x in c53.BASES),'STAGE_SCOPE')

    def _guard_host(self):
        c53.require(os.geteuid()==0 and os.getegid()==0 and os.environ.get('SUDO_UID')=='1000', 'IDENTITY')
        c53.require(os.uname().nodename==c53.HOST,'UK_HOST')

    def verify_external_release(self, phase):
        from pr17_b5_successor_release_gate import ExternalReleaseGate
        c53.require(type(self.release_gate) is ExternalReleaseGate,
                    'EXTERNAL_RELEASE_BINDER_NOT_BOUND')
        return self.release_gate.check(phase, self.spec)

    def get_generator_inputs_verified(self,spec):
        # Only the fixed six protected inputs and 33 pinned c53 source bytes.
        # This observation does NOT imply grant, consent or analyst ACK.
        self._guard_host()
        c53.require(spec is self.spec,'GENERATOR_SPEC_CHANGED')
        c53.require(set(self.frozen_baselines)==set(c53.CONFIGS+c53.SLOTS),
                    'GENERATOR_BASELINE_SCOPE')
        baselines={};identities={}
        for path in c53.CONFIGS+c53.SLOTS:
            raw,ident=self.legacy.read(path)
            c53.require(raw==self.frozen_baselines[path],
                        'GENERATOR_BASELINE_CHANGED')
            baselines[path]=raw
            identities[path]=ident
        c53.verify_observed_bytes(spec,baselines)
        c53.binder.verify_supplied_source(spec,self.source_blobs)
        self.generator_identities=identities
        self.generator_inputs_verified=True
        return dict(baselines),dict(self.source_blobs)

    def _auth(self, name, *args):
        # No fallback to status-only, random shell or legacy success. The
        # injected provider must be reviewed to verify signed original-client
        # consent and actual B5 analyst identity; unavailable => HOLD.
        c53.require(self.authority is not None,'AUTH_PROVIDER_NOT_CONNECTED')
        method=getattr(self.authority,name,None)
        c53.require(callable(method),'AUTH_METHOD_UNAVAILABLE')
        return method(*args)

    def preflight_original_capabilities(self):
        # Require the exact production bridge and a positive enrollment proof
        # for all eleven original operations before a reservation or stop.
        # The current adapter intentionally HOLDs: original Queue.submit,
        # private_mcp and custody primitives are not an authenticated caller.
        self.verify_external_release('preflight')
        from pr17_b5_successor_authority import ExistingRequestAuthority
        c53.require(type(self.authority) is ExistingRequestAuthority,
                    'ORIGINAL_AUTHORITY_TYPE')
        return self.authority.preflight_original_capabilities()

    def preflight_runtime_attachment(self):
        """A missing original runtime binder must fail before reservation/stop."""
        from pr17_b5_successor_authority import ExistingRequestAuthority
        c53.require(type(self.authority) is ExistingRequestAuthority,
                    'ORIGINAL_AUTHORITY_TYPE')
        return self.authority.preflight_runtime_attachment()

    def witness_action(self):
        from pr17_b5_successor_authority import ExistingRequestAuthority
        c53.require(type(self.authority) is ExistingRequestAuthority,
                    'WITNESS_AUTHORITY_TYPE')
        return self._auth('witness_action')

    def _receipt(self,name,*args):
        if name in ('verify_owner_maintenance_scope','verify_b5_analyst_ack'):
            from pr17_b5_successor_authority import ExistingRequestAuthority
            c53.require(type(self.authority) is ExistingRequestAuthority,
                        'WITNESS_AUTHORITY_TYPE')
        evidence=self._auth(name,*args)
        expected_source=('ORIGINAL_PROTECTED_OBSERVATION' if name ==
            'verify_fixed_receiver_target_conflicts' else
            'UK_OWNER_WITNESS_SINGLE_BATCH' if name in
            ('verify_owner_maintenance_scope','verify_b5_analyst_ack') else
            'ORIGINAL_ALGORITHM_VERIFIED' if name in
            ('verify_nineteen_original_success_receipts',
             'verify_original_archive_custody','custody_once') else
            'ORIGINAL_AUTHENTICATED_CLIENT')
        c53.require(type(evidence) is dict and evidence.get('verified') is True
                    and evidence.get('source')==expected_source
                    and isinstance(evidence.get('evidence_sha256'),str)
                    and len(evidence['evidence_sha256'])==64,'AUTH_RECEIPT_UNKNOWN')
        return evidence

    def checkpoint(self,phase):
        if not self.reserved:return
        self.seq+=1
        data=c53.canon({'schema':1,'phase':phase,'sequence':self.seq,
                        'release_commit':c53.COMMIT,'project':c53.PROJ})+b'\n'
        self.legacy.newfile(self.job+'/checkpoint-%03d.json'%self.seq,data)

    def recover_intake_readonly(self,bundle):
        """Reconcile a prior attempt; this entry has no publish/submit path.

        All records are read through the original protected-file reader. A
        missing SENT record means POST may have happened and is never retried.
        The original authenticated queue observer supplies canonical READY and
        SUCCESS facts; a stored intent alone proves neither.
        """
        self.verify_external_release('recover')
        from production.cloud_connection.queue import canonical
        c53.require(type(bundle) is dict and type(bundle.get('requests')) is list
                    and len(bundle['requests'])==19,'RECOVERY_REQUEST_SCOPE')
        ids=tuple(r['request_id'] for r in bundle['requests'])
        c53.require(ids==self.expected_ids and len(set(ids))==19,
                    'RECOVERY_REQUEST_IDS')
        try:
            reservation=c53.strict_json(self.legacy.read(self.job+'/reservation.json')[0])
            window=c53.strict_json(self.legacy.read(self.job+'/window-open.json')[0])
        except FileNotFoundError:
            raise Hold('RECOVERY_RESERVATION_OR_WINDOW_ABSENT') from None
        c53.require(reservation.get('batch')==bundle['batch_id'] and
                    reservation.get('ids')==list(ids) and
                    reservation.get('catalog_sha256')==bundle['catalog_sha'] and
                    reservation.get('request_set_sha256')==c53.sha(c53.canon(bundle['requests'])) and
                    reservation.get('window_start')==bundle['window_start'] and
                    reservation.get('window_end')==bundle['window_end'] and
                    reservation.get('generation_seal')==bundle['generation_seal'] and
                    reservation.get('release')==c53.COMMIT and
                    reservation.get('state')=='RESERVED_NOT_SUBMITTED',
                    'RECOVERY_RESERVATION_BINDING')
        c53.require(window.get('catalog_sha256')==bundle['catalog_sha'] and
                    window.get('window_start')==bundle['window_start'] and
                    window.get('window_end')==bundle['window_end'] and
                    window.get('state')=='ACTIVE_NOT_DELIVERED',
                    'RECOVERY_WINDOW_BINDING')
        # Preserve the original T0/T1 even when the inspection happens later.
        c53.require(type(window['window_start']) is int and
                    type(window['window_end']) is int and
                    window['window_end']-window['window_start']==3600,
                    'RECOVERY_WINDOW_TIME')
        # The original checkpoint stream is append-only. A gap or a failed
        # terminal phase is not a license to infer an earlier success.
        checkpoints=[];gap=False
        for number in range(1,65):
            try:raw,_=self.legacy.read(self.job+'/checkpoint-%03d.json'%number)
            except FileNotFoundError:
                gap=True;continue
            c53.require(not gap,'RECOVERY_CHECKPOINT_GAP')
            row=c53.strict_json(raw)
            c53.require(row.get('schema')==1 and
                        type(row.get('sequence')) is int and
                        row['sequence']==number and
                        row.get('release_commit')==c53.COMMIT and
                        row.get('project')==c53.PROJ and
                        type(row.get('phase')) is str,
                        'RECOVERY_CHECKPOINT_BINDING')
            checkpoints.append(row['phase'])
        c53.require(checkpoints and 'INTAKE_19' in checkpoints and
                    checkpoints[-1] in ('INTAKE_19','INTAKE_SENT_AWAITING_READY',
                        'WAIT_19_SUCCESS','CHECK_19_SUCCESS','ONE_CUSTODY',
                        'READY_FOR_B5_HTTP_NOT_RECEIVED'),
                    'RECOVERY_CHECKPOINT_PHASE')
        c53.require(len(checkpoints)<64,'RECOVERY_CHECKPOINT_BOUND')
        self.seq=len(checkpoints)
        self.reserved=True
        self.bundle=bundle
        self.window_open=True
        pending=[]; ready=[]
        for request in bundle['requests']:
            rid=request['request_id']
            digest=c53.sha(canonical(request).encode())
            try:
                raw,_=self.legacy.read(self.job+'/intake-'+rid+'.intent.json')
            except FileNotFoundError:
                pending.append(rid);continue
            intent=c53.strict_json(raw)
            c53.require(intent=={'request_id':rid,'request_sha256':digest,
                'catalog_sha256':bundle['catalog_sha'],'actor_id':332398908,
                'state':'POST_MAY_HAVE_OCCURRED_NO_REPOST'},
                'RECOVERY_INTENT_BINDING')
            try:
                sent=c53.strict_json(self.legacy.read(
                    self.job+'/intake-'+rid+'.sent.json')[0])
            except FileNotFoundError:
                pending.append(rid);continue
            c53.require(sent.get('request_id')==rid and
                        sent.get('request_sha256')==digest and
                        type(sent.get('comment_id')) is int and
                        sent.get('state')=='SENT_NOT_ACCEPTED' and len(sent)==4,
                        'RECOVERY_SENT_BINDING')
            try:
                observation=self._auth('observe_original_intake_ready',request)
            except Exception as exc:
                if str(exc) not in ('INTAKE_READY_NOT_PROVEN',
                                    'B5_INTAKE_PENDING_OR_UNKNOWN_NO_REPOST'):
                    raise Hold('RECOVERY_READY_OBSERVER_UNKNOWN') from None
                pending.append(rid);continue
            if type(observation) is dict and observation.get('request_id')==rid and observation.get('state')=='ACCEPTED':
                ready.append(rid)
            else: pending.append(rid)
        if pending:
            c53.require(checkpoints[-1]!='READY_FOR_B5_HTTP_NOT_RECEIVED',
                        'RECOVERY_CUSTODY_CHECKPOINT_CONFLICT')
            return {'state':'UNKNOWN_OR_PENDING_NO_REPOST','ready_count':len(ready),
                    'pending_count':len(pending),'last_checkpoint':checkpoints[-1],
                    'mutation_allowed':False}
        count=self._auth('observe_original_success_progress',ids,bundle['catalog_sha'])
        c53.require(type(count) is int and 0<=count<=19,'RECOVERY_PROGRESS_UNKNOWN')
        if checkpoints[-1]=='READY_FOR_B5_HTTP_NOT_RECEIVED':
            c53.require(count==19,'RECOVERY_CUSTODY_SUCCESS_CHANGED')
        state=('B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY' if
               checkpoints[-1]=='READY_FOR_B5_HTTP_NOT_RECEIVED' else
               'CUSTODY_UNKNOWN_NO_RETRY' if checkpoints[-1]=='ONE_CUSTODY' else
               'SUCCESS_OBSERVED_READONLY' if count==19 else 'WAIT_ORIGINAL_SUCCESS_NO_REPOST')
        return {'state':state,'ready_count':19,'success_count':count,
                'last_checkpoint':checkpoints[-1], 'mutation_allowed':False}

    def observe_poststart_canonical_readonly(self,bundle):
        """Correlate protected job intent/SENT with the original live Queue.

        This is a status observation, not a proof that no later operation can
        begin and never an approval for restore, close or another POST.
        """
        from production.cloud_connection.queue import canonical
        c53.require(self.tried_start is True and self.activation_committed is True
                    and self.authority is not None and bundle is self.bundle,
                    'POSTSTART_OBSERVATION_CONTEXT')
        original=self.authority._bound_original(active=True)
        c53.require(original.runtime_phase=='observe' and
                    original.queue.db.execute('PRAGMA query_only').fetchone()==(1,),
                    'POSTSTART_READONLY_QUEUE_REQUIRED')
        outcome=self.recover_intake_readonly(bundle)
        ids=tuple(x['request_id'] for x in bundle['requests'])
        db=original.queue.db
        # The original Queue has connection_jobs, not an outbox table. A
        # single read-only snapshot binds each exact request and actor.
        db.execute('BEGIN')
        try:
            rows=db.execute('SELECT request_id,project,request_sha,actor_id,state,invoke_id,receipt_json '
                            'FROM connection_jobs WHERE request_id IN ('+
                            ','.join('?' for _ in ids)+')',ids).fetchall()
        finally:db.execute('ROLLBACK')
        c53.require(len(rows)<=19,'POSTSTART_QUEUE_SNAPSHOT')
        states={row[0]:row[4] for row in rows}
        c53.require(len(states)==len(rows) and set(states)<=set(ids),
                    'POSTSTART_QUEUE_IDS')
        expected={r['request_id']:r for r in bundle['requests']}
        for rid,project,digest,actor,_,_,_ in rows:
            c53.require(project==c53.PROJ and type(actor) is int and
                        actor==332398908 and
                        digest==c53.sha(canonical(expected[rid]).encode()),
                        'POSTSTART_QUEUE_REQUEST_BINDING')
        complete=(outcome['state']=='SUCCESS_OBSERVED_READONLY' and
                  len(rows)==19 and
                  all(state=='SUCCESS' and type(invoke) is str and invoke and
                      type(receipt) is str and receipt
                      for _,_,_,_,state,invoke,receipt in rows))
        return {'state':'SUCCESS_SNAPSHOT_READONLY' if complete else
                'UNKNOWN_OR_PENDING_NO_REPOST',
                'ready_count':outcome.get('ready_count',0),
                'success_count':outcome.get('success_count',0),
                'queue_rows':len(rows),
                'mutation_allowed':False}

    def verify_activation_admission(self,bundle,spec):
        self._guard_host()
        # Actual transaction entry guard, before reservation or worker stop.
        # The original SQLite lock-stage guard repeats this check later.
        try:
            task_ids=os.listdir('/proc/self/task')
        except OSError:
            raise Hold('QUERY_ENTRY_THREAD_IDENTITY_UNKNOWN') from None
        c53.require(len(task_ids)==1,'QUERY_ENTRY_NOT_SINGLE_THREADED')
        owner=self._receipt('verify_owner_maintenance_scope',c53.HOST,c53.COMMIT,
                      self.job,self.expected_ids)
        c53.require(owner.get('host')==c53.HOST and owner.get('commit')==c53.COMMIT
                    and owner.get('job')==self.job and owner.get('approved') is True,
                    'OWNER_MAINTENANCE_SCOPE_UNPROVEN')

    def read_activated_resource_verified(self):
        self._guard_host()
        path=c53.CONFIGS[1]
        c53.require(self.activation_committed is True and self.bundle is not None
                    and path in self.new,'RESOURCE_NOT_ACTIVATED')
        observed={}
        for current in (path,c53.binder.CATALOG):
            c53.require(current in self.new,'RESOURCE_CATALOG_NOT_ACTIVATED')
            raw,identity=self.legacy.read(current)
            c53.require(identity==self.new[current] and raw==self.bundle['files'][current],
                        'FOREIGN_ACTIVATED_RESOURCE_OR_CATALOG')
            observed[current]=raw
        return observed[path]

    def persist_activation_identity(self):
        """Publish one protected snapshot only after all eight activations."""
        c53.require(self.bundle is not None and self.reserved and self.lock_fd is not None,
                    'ACTIVATION_SNAPSHOT_ORDER')
        paths=c53.CONFIGS+c53.SLOTS
        links=tuple(base+'/current' for base in c53.BASES)
        c53.require(set(self.new)==set(paths+links),'ACTIVATION_SNAPSHOT_SCOPE')
        files={}
        for path in paths:
            raw,ident=self.legacy.read(path)
            c53.require(raw==self.bundle['files'][path] and ident==self.new[path],
                        'ACTIVATION_SNAPSHOT_FILE_CHANGED')
            files[path]={'sha256':c53.sha(raw),'identity':ident}
        currents={}
        for base in c53.BASES:
            d=self.legacy.parent(base)
            try:
                st=os.stat('current',dir_fd=d,follow_symlinks=False)
                ident=self.legacy.identity(st)
                target=os.readlink('current',dir_fd=d)
            finally:os.close(d)
            c53.require(stat.S_ISLNK(st.st_mode) and ident==self.new[base+'/current']
                        and target==base+'/releases/'+c53.COMMIT,
                        'ACTIVATION_SNAPSHOT_LINK_CHANGED')
            currents[base+'/current']={'target':target,'identity':ident}
        record={'schema':1,'release_commit':c53.COMMIT,
                'catalog_sha256':self.bundle['catalog_sha'],
                'generation_seal':self.bundle['generation_seal'],
                'request_set_sha256':c53.sha(c53.canon(self.bundle['requests'])),
                'files':files,'currents':currents}
        self.legacy.newfile(self.job+'/activation-identity.json',c53.canon(record)+b'\n')

    def restore_activation_identity_readonly(self,bundle):
        """Bind a fresh process to unchanged protected files and two links."""
        try:
            marker=c53.strict_json(self.legacy.read(
                self.job+'/NEW_WORKER_START_ATTEMPT.json')[0])
            window=c53.strict_json(self.legacy.read(self.job+'/window-open.json')[0])
        except FileNotFoundError:
            raise Hold('RECOVERY_ACTIVATION_PROOF_ABSENT') from None
        c53.require(marker=={'state':'ATTEMPT_STARTED_NO_REPLAY',
                             'release':c53.COMMIT} and
                    window.get('state')=='ACTIVE_NOT_DELIVERED' and
                    window.get('catalog_sha256')==bundle['catalog_sha'] and
                    window.get('window_start')==bundle['window_start'] and
                    window.get('window_end')==bundle['window_end'],
                    'RECOVERY_WORKER_WINDOW_BINDING')
        self.legacy.stable_unit('xuanjun-cloud-connection.service')
        try:record=c53.strict_json(self.legacy.read(self.job+'/activation-identity.json')[0])
        except FileNotFoundError:raise Hold('RECOVERY_ACTIVATION_PROOF_ABSENT') from None
        paths=c53.CONFIGS+c53.SLOTS
        links=tuple(base+'/current' for base in c53.BASES)
        c53.require(record.get('schema')==1 and
                    record.get('release_commit')==c53.COMMIT and
                    record.get('catalog_sha256')==bundle['catalog_sha'] and
                    record.get('generation_seal')==bundle['generation_seal'] and
                    record.get('request_set_sha256')==c53.sha(c53.canon(bundle['requests']))
                    and type(record.get('files')) is dict and
                    set(record['files'])==set(paths) and
                    type(record.get('currents')) is dict and
                    set(record['currents'])==set(links),
                    'RECOVERY_ACTIVATION_BINDING')
        observed={}
        for path in paths:
            raw,ident=self.legacy.read(path)
            saved=record['files'][path]
            c53.require(type(saved) is dict and
                        saved.get('sha256')==c53.sha(bundle['files'][path]) and
                        raw==bundle['files'][path] and
                        c53.canon(ident)==c53.canon(saved.get('identity')),
                        'RECOVERY_ACTIVATION_FILE_CHANGED')
            observed[path]=ident
        for base in c53.BASES:
            d=self.legacy.parent(base)
            try:
                st=os.stat('current',dir_fd=d,follow_symlinks=False)
                ident=self.legacy.identity(st)
                target=os.readlink('current',dir_fd=d)
            finally:os.close(d)
            saved=record['currents'][base+'/current']
            c53.require(stat.S_ISLNK(st.st_mode) and type(saved) is dict and
                        target==saved.get('target')==base+'/releases/'+c53.COMMIT and
                        c53.canon(ident)==c53.canon(saved.get('identity')),
                        'RECOVERY_ACTIVATION_LINK_CHANGED')
            observed[base+'/current']=ident
        # The durable attempt marker and currently stable original unit were
        # both verified above. Recover the fact, never call start a second time.
        self.bundle=bundle;self.new=observed;self.activation_committed=True
        self.tried_start=True
        self.window_open=True
        self.recovered_from_protected=True
        return True

    def verify_post_activation_b5_read_admission(self,bundle,spec):
        self._guard_host()
        c53.require(getattr(self,'activation_committed',False) is True,
                    'B5_AUTH_BEFORE_ACTIVATION')
        grant=self._receipt('verify_existing_grant',c53.SUBJECT,c53.RECIP,c53.PROJ,
                      'connection.status','project.files.read',bundle['catalog_sha'])
        c53.require(grant.get('grant_active') is True and
                    grant.get('subject')==c53.SUBJECT and grant.get('recipient')==c53.RECIP and
                    grant.get('project')==c53.PROJ and grant.get('catalog_sha256')==bundle['catalog_sha']
                    and type(grant.get('scopes')) is list and
                    set(grant['scopes'])>= {'connection.status','project.files.read'},'LIVE_GRANT_SCOPE_UNPROVEN')

    def verify_maintenance_window_admission(self,bundle,spec):
        """Current Owner/B5 witness and original enrolled UK transport only.

        The B5 analyst's project.files.read grant is verified later by each
        original request-local OAuth HTTP call, never passed to this process.
        """
        c53.require(self.activation_committed is True and self.bundle is bundle,
                    'MAINTENANCE_ACTIVATION_REQUIRED')
        self.verify_activation_admission(bundle,spec)
        self.verify_analyst_ack(bundle,spec)
        self.authority._bound_original(active=self.tried_start).preflight()
        c53.require(bundle['window_start']<=int(time.time())<bundle['window_end'],
                    'MAINTENANCE_WINDOW_EXPIRED')
        return True

    def verify_live_approval_and_grant(self,bundle,spec):
        # Compatibility entry: still fails closed without real maintenance
        # approval; reading qualification can only run after activation.
        self.verify_activation_admission(bundle,spec)
        self.verify_post_activation_b5_read_admission(bundle,spec)

    def verify_analyst_ack(self,bundle,spec):
        ack=self._receipt('verify_b5_analyst_ack',c53.SUBJECT,c53.RECIP,c53.PROJ,
                      'fetch_approved_object',bundle['catalog_sha'],self.expected_ids)
        c53.require(ack.get('analyst_ready') is True and ack.get('subject')==c53.SUBJECT
                    and ack.get('recipient')==c53.RECIP and ack.get('project')==c53.PROJ
                    and ack.get('operation')=='fetch_approved_object'
                    and ack.get('catalog_sha256')==bundle['catalog_sha']
                    and tuple(ack.get('request_ids',()))==self.expected_ids,
                    'ANALYST_ACK_BINDING_UNPROVEN')

    def reserve_batch_and_targets(self,bundle,spec):
        c53.require(self.generator_inputs_verified is True,
                    'GENERATOR_INPUTS_NOT_VERIFIED')
        c53.validate_bundle(spec,bundle,
            verified_baselines=self.frozen_baselines,
            verified_source_blobs=self.source_blobs)
        self.bundle=bundle
        c53.require(tuple(x['request_id'] for x in bundle['requests'])==self.expected_ids,'IDS_NOT_FROZEN')
        witness=self._auth('witness_pair_digest')
        c53.require(type(witness) is str and len(witness)==64 and
                    all(c in '0123456789abcdef' for c in witness),
                    'RESERVATION_WITNESS_BINDING')
        for path in self.paths['target_release']+self.paths['stage_proposed']:
            self.legacy.absent(path)
        self.legacy.absent(self.job)
        consumed=self._auth('consume_witness_once')
        c53.require(consumed==witness,'RESERVATION_WITNESS_CHANGED')
        self.legacy.mkdir(self.job,0o700)
        self.reserved=True
        data=c53.canon({'batch':bundle['batch_id'],'ids':self.expected_ids,
                        'catalog_sha256':bundle['catalog_sha'],'release':c53.COMMIT,
                        'request_set_sha256':c53.sha(c53.canon(bundle['requests'])),
                        'generation_seal':bundle['generation_seal'],
                        'approval_ref':c53.strict_json(bundle['files'][c53.binder.CATALOG])['approval_ref'],
                        'attempt_id':self.authority.attempt_id,
                        'window_start':bundle['window_start'],
                        'window_end':bundle['window_end'],
                        'witness_pair_sha256':witness,
                        'state':'RESERVED_NOT_SUBMITTED'})+b'\n'
        self.legacy.newfile(self.job+'/reservation.json',data)

    def stop_worker_bounded(self):
        self.legacy.command(['/usr/bin/systemctl','stop','xuanjun-cloud-connection.service'],60)
        self.worker_stopped=True

    def verify_worker_exited(self):
        self.legacy.command(['/usr/bin/systemctl','is-active','--quiet',
                             'xuanjun-cloud-connection.service'],10,(3,))

    def acquire_original_lock_once(self):
        c53.require(self.worker_stopped and self.lock_fd is None,'LOCK_ORDER')
        root=self.legacy.state_directory()
        try:
            fd=os.open('worker.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=root)
            s=os.fstat(fd)
            if not (stat.S_ISREG(s.st_mode) and s.st_dev==64771 and s.st_ino==1845924
                    and s.st_uid==s.st_gid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600):
                os.close(fd);raise Hold('ORIGINAL_LOCK_IDENTITY')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BaseException:os.close(fd);raise
            self.lock_fd=fd
        finally:os.close(root)

    @staticmethod
    def _snapshot_live_fds():
        """Complete FD set, not merely newly appearing regular-file FDs."""
        result={}
        try:
            names=os.listdir('/proc/self/fd')
            for entry in names:
                if not entry.isdigit():continue
                fd=int(entry)
                try:st=os.fstat(fd)
                except OSError:continue  # /proc enumeration descriptor closed
                result[fd]=(st.st_dev,st.st_ino,stat.S_IFMT(st.st_mode))
        except OSError:
            raise Hold('SQLITE_FD_PROVENANCE_UNAVAILABLE') from None
        return result

    def _connect_verified_original_queue(self, code):
        """Fail closed unless a unique new SQLite FD is demonstrably isolated.

        Python sqlite3 exposes no per-connection OS fd. The old assumption that
        "one newly opened A fd" belongs to the SQLite connection is false when
        a cached connection B exists. Admit only a single-threaded, FD-quiescent
        process with no preexisting unrelated descriptors. Without that actual
        process boundary this is HOLD, not a production provenance claim.
        """
        root=self.legacy.state_directory()
        held=None;conn=None
        try:
            held=os.open('queue.sqlite',
                os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=root)
            initial=os.fstat(held)
            self.legacy.database_identity(initial)
            original=(initial.st_dev,initial.st_ino)
            # immutable SQLite is only sound for a quiescent, exclusive database:
            # caller must hold original worker lock, worker must be stopped,
            # journal/WAL/SHM absence must have been proved by both callers.
            c53.require(self.lock_fd is not None,
                        code+'_ORIGINAL_LOCK_REQUIRED')
            c53.require(self.worker_stopped is True,
                        code+'_WORKER_NOT_PROVEN_STOPPED')
            try:threads=os.listdir('/proc/self/task')
            except OSError:
                raise Hold(code+'_THREAD_BOUNDARY_UNKNOWN') from None
            c53.require(len(threads)==1,code+'_NOT_SINGLE_THREADED')
            pre=self._snapshot_live_fds()
            allowed={0,1,2,root,held,self.lock_fd}
            # A preexisting cached SQLite B (or any unknown FD) is disallowed
            # even if a bogus connect() subsequently opens an unrelated A FD.
            c53.require(set(pre)<=allowed and held in pre,
                        code+'_PREEXISTING_FD_UNKNOWN')
            c53.require(pre[held][:2]==original,code+'_PINNED_FD_CHANGED')
            uri='file:/proc/self/fd/%d?mode=ro&immutable=1'%held
            conn=sqlite3.connect(uri,uri=True,timeout=0,isolation_level=None)
            post=self._snapshot_live_fds()
            c53.require(all(post.get(fd)==identity for fd,identity in pre.items()),
                        code+'_FD_SET_CHANGED')
            new=set(post)-set(pre)
            c53.require(len(new)==1,code+'_CONNECTED_FD_AMBIGUOUS')
            sqlite_fd=next(iter(new))
            c53.require(post[sqlite_fd][:2]==original and
                        post[sqlite_fd][2]==stat.S_IFREG,
                        code+'_CONNECTED_FD_MISMATCH')
            # Independently bind SQLite's own declared main database. This
            # excludes cached :memory: connections, attached databases, and
            # file-backed B connections even if an unrelated A FD appears.
            database_rows=conn.execute('PRAGMA database_list').fetchall()
            c53.require(len(database_rows)==1 and
                        database_rows[0][1]=='main' and
                        type(database_rows[0][2]) is str and
                        database_rows[0][2].startswith('/'),
                        code+'_SQLITE_MAIN_PATH_UNKNOWN')
            # SQLite resolves /proc/self/fd to an absolute pathname at open.
            # During a legitimate A->B->A rename, that former pathname may
            # vanish after A is moved back. Accept only an original-directory
            # pathname; the already enforced exclusive FD boundary remains
            # the authoritative identity check.
            c53.require(os.path.dirname(database_rows[0][2])==
                        os.path.dirname(c53.DB),
                        code+'_SQLITE_MAIN_DIRECTORY_MISMATCH')
            try:
                actual_main=os.stat(database_rows[0][2])
            except FileNotFoundError:
                actual_main=None
            except OSError:
                raise Hold(code+'_SQLITE_MAIN_PATH_UNKNOWN') from None
            if actual_main is not None:
                c53.require((actual_main.st_dev,actual_main.st_ino)==original,
                            code+'_SQLITE_MAIN_IDENTITY_MISMATCH')
            named=os.stat('queue.sqlite',dir_fd=root,follow_symlinks=False)
            self.legacy.database_identity(named)
            c53.require((named.st_dev,named.st_ino)==original,
                        code+'_NAMED_PATH_CHANGED')
            # No callback or other FD-changing operation occurred during the
            # connect window; prove isolation again immediately before query.
            c53.require(len(os.listdir('/proc/self/task'))==1,
                        code+'_THREAD_BOUNDARY_CHANGED')
            c53.require(self._snapshot_live_fds()==post,
                        code+'_FD_SET_CHANGED')
            conn.execute('PRAGMA query_only=ON')
            self.db=conn
            self.sqlite_bound_fd=sqlite_fd
            self.verified_original_db=True
            conn=None
        finally:
            if conn is not None:conn.close()
            if held is not None:os.close(held)
            os.close(root)

    def check_queue_and_target_conflicts(self,ids,spec):
        c53.require(self.lock_fd is not None and tuple(ids)==self.expected_ids,'QUEUE_LOCK_OR_IDENTITY')
        self.legacy.check_original_database()
        for suffix in ('-wal','-shm','-journal'):
            self.legacy.absent(c53.DB+suffix)
        self._connect_verified_original_queue('ADMISSION_DB')
        count=self.db.execute('SELECT count(*) FROM connection_jobs WHERE request_id IN ('+
                ','.join('?' for _ in ids)+')',ids).fetchone()[0]
        c53.require(count==0,'NEW_IDS_CONFLICT')
        outbox_columns=[row[1] for row in self.db.execute('PRAGMA table_info(connection_outbox)')]
        c53.require(outbox_columns==['request_id','body','state','comment_id'],
                    'ORIGINAL_OUTBOX_SCHEMA_UNKNOWN')
        ready=self.db.execute("SELECT count(*) FROM connection_jobs WHERE state='READY'").fetchone()[0]
        outbox=self.db.execute("SELECT count(*) FROM connection_outbox WHERE state IN ('READY','POSTING')").fetchone()[0]
        active=self.db.execute("SELECT count(*) FROM connection_jobs WHERE project=? AND state IN ('READY','DISPATCHING','UNKNOWN')",(c53.PROJ,)).fetchone()[0]
        c53.require(ready==0 and outbox==0 and active==0,'ORIGINAL_QUEUE_CONFLICT')
        # Queue was opened with the stopped worker lock. Read all nonterminal
        # original requests and the current protected old binding, not merely
        # invoke/outbox heuristics or the 19 proposed IDs.
        policy_receipt=self.observe_cross_project_old_policy_dependency(tuple(ids),c53.PROJ)
        c53.require(policy_receipt.get('dependent_active') == 0 and
                    policy_receipt.get('project')==c53.PROJ,
                    'OLD_POLICY_DEPENDENCY_UNKNOWN')
        # Do not demand unrelated historical UNKNOWN=0; only dependent B5 rows
        # and active outbox are admission blockers. Receiver directory contents
        # cannot be inferred from nlink=2 and need original fixed-target checks.
        receiver=self._receipt('verify_fixed_receiver_target_conflicts',self.paths['receiver_root'],ids)
        c53.require(receiver.get('no_conflicts') is True and receiver.get('receiver_root')==self.paths['receiver_root'],
                    'RECEIVER_TARGET_CONFLICT_UNKNOWN')

    def observe_prestart_old_policy_dependency(self, ids, project, _fixture_path=None):
        """A: bounded observation before reservation; live WAL is held.

        This is not a mutation permit. B reopens and reclassifies after stop
        and exclusive lock. The fixture path is never supplied by production.
        """
        c53.require(self.lock_fd is None and self.worker_stopped is not True and
                    tuple(ids)==self.expected_ids and project==c53.PROJ,
                    'OLD_POLICY_PRECHECK_PHASE')
        from urllib.parse import quote
        path=c53.DB if _fixture_path is None else _fixture_path
        held=None;parent=None;db=None
        deadline=time.monotonic()+5.0
        try:
            parent=(self.legacy.state_directory() if _fixture_path is None else
                    os.open(os.path.dirname(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
            held=os.open(os.path.basename(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,
                         dir_fd=parent)
            original=os.fstat(held)
            # The original protected state owner knows the pinned DB identity;
            # self-consistent inode observations alone cannot authenticate it.
            self.legacy.database_identity(original)
            c53.require(stat.S_ISREG(original.st_mode) and original.st_nlink==1 and
                        original.st_uid==os.geteuid() and
                        stat.S_IMODE(original.st_mode) in (0o600,0o400),
                        'OLD_POLICY_PRECHECK_DB_IDENTITY')
            sidecars={}
            for suffix in ('-wal','-shm'):
                try:sidecars[suffix]=os.stat(path+suffix,follow_symlinks=False)
                except FileNotFoundError:sidecars[suffix]=None
            header=os.pread(held,20,0)
            c53.require(len(header)==20 and header[:16]==b'SQLite format 3\x00',
                        'OLD_POLICY_PRECHECK_DB_HEADER')
            # SQLite mode=ro/query_only still updates WAL shared-memory read
            # marks. No live-WAL read is permitted until that side effect has
            # an explicit coordination decision. Never use immutable on WAL.
            c53.require(header[18:20]!=b'\x02\x02',
                        'OLD_POLICY_PRECHECK_WAL_READER_MARK_UNKNOWN')
            try:tasks=os.listdir('/proc/self/task')
            except OSError:raise Hold('OLD_POLICY_PRECHECK_THREAD_UNKNOWN') from None
            c53.require(len(tasks)==1,'OLD_POLICY_PRECHECK_THREAD_UNKNOWN')
            db=sqlite3.connect('file:'+quote(path)+'?mode=ro',uri=True,
                               timeout=0,isolation_level=None)
            named=os.stat(os.path.basename(path),dir_fd=parent,follow_symlinks=False)
            c53.require((original.st_dev,original.st_ino)==(named.st_dev,named.st_ino),
                        'OLD_POLICY_PRECHECK_DB_CHANGED')
            db.execute('PRAGMA query_only=ON')
            c53.require(db.execute('PRAGMA query_only').fetchone()==(1,),
                        'OLD_POLICY_PRECHECK_NOT_READONLY')
            db.execute('BEGIN')
            columns=[x[1] for x in db.execute('PRAGMA table_info(connection_jobs)')]
            main=db.execute('PRAGMA database_list').fetchall()
            c53.require(len(main)==1 and main[0][1]=='main' and
                        main[0][2]==path,'OLD_POLICY_PRECHECK_MAIN_PATH')
            c53.require(columns==['request_id','project','request_json','request_sha',
                                  'actor_id','state','invoke_id','receipt_json'],
                        'OLD_POLICY_PRECHECK_SCHEMA')
            schema=db.execute("SELECT name,type,sql FROM sqlite_master WHERE name IN "
                              "('connection_jobs','connection_active_project',"
                              "'connection_no_delete','connection_no_replace',"
                              "'connection_no_rebind') ORDER BY name").fetchall()
            normalized=[(name,kind,re.sub(r'\s+',' ',sql).strip())
                        for name,kind,sql in schema if type(sql) is str]
            c53.require(len(normalized)==5 and
                        c53.sha(json.dumps(normalized,separators=(',',':')).encode())==
                        'a9da8c2cf0d012fff81cb8e35da09d044d82f31991e5ae24ad5cdd9ba800d2f3',
                        'OLD_POLICY_PRECHECK_SCHEMA')
            before=db.execute('PRAGMA data_version').fetchone()
            result=self._classify_old_policy_dependencies(db,ids,project,deadline)
            after=db.execute('PRAGMA data_version').fetchone()
            c53.require(before==after,'OLD_POLICY_PRECHECK_DB_CHANGED')
            current=os.fstat(held)
            named=os.stat(os.path.basename(path),dir_fd=parent,follow_symlinks=False)
            self.legacy.database_identity(current)
            self.legacy.database_identity(named)
            c53.require((original.st_dev,original.st_ino)==
                        (current.st_dev,current.st_ino)==(named.st_dev,named.st_ino),
                        'OLD_POLICY_PRECHECK_DB_CHANGED')
            for suffix,previous in sidecars.items():
                try:present=os.stat(path+suffix,follow_symlinks=False)
                except FileNotFoundError:present=None
                c53.require((previous is None and present is None) or
                            (previous is not None and present is not None and
                             stat.S_ISREG(previous.st_mode) and
                             (previous.st_dev,previous.st_ino)==
                             (present.st_dev,present.st_ino)),
                            'OLD_POLICY_PRECHECK_SIDECAR_CHANGED')
            db.execute('COMMIT')
            c53.require(result['dependent_active']==0 and result['unresolved']==0,
                        'OLD_POLICY_PRECHECK_DEPENDENCY')
            c53.require(time.monotonic()<deadline,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN')
            return dict(result,phase='PRECHECK_OBSERVATION')
        except BaseException:
            if db is not None and db.in_transaction:db.execute('ROLLBACK')
            raise
        finally:
            if db is not None:db.close()
            if held is not None:os.close(held)
            if parent is not None:os.close(parent)

    def observe_cross_project_old_policy_dependency(self, ids, project):
        """B: classify again after worker exit, lock and original DB FD proof."""
        c53.require(self.lock_fd is not None and self.worker_stopped is True and
                    self.verified_original_db is True and self.db is not None and
                    tuple(ids)==self.expected_ids and project==c53.PROJ,
                    'OLD_POLICY_LOCK_OR_DB_UNKNOWN')
        result=self._classify_old_policy_dependencies(self.db,ids,project)
        c53.require(result['dependent_active']==0 and result['unresolved']==0,
                    'OLD_POLICY_LOCKED_DEPENDENCY')
        return dict(result,phase='LOCKED_REOBSERVATION')

    def _classify_old_policy_dependencies(self, db, ids, project, deadline=None):
        """One strict classifier for A and B; no expiry revalidation on fetch."""
        from production.cloud_connection.queue import canonical, decode, FIELDS, TARGETS
        from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
        if deadline is None:deadline=time.monotonic()+5.0
        c53.require(time.monotonic()<deadline,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN')
        def progress():return int(time.monotonic()>=deadline)
        db.set_progress_handler(progress,1000)
        try:return self._classify_old_policy_bounded(db,ids,project,deadline,
                                                      canonical,decode,FIELDS,TARGETS,
                                                      ApprovedObjectsPolicy)
        except sqlite3.OperationalError as exc:
            if time.monotonic()>=deadline:
                raise Hold('OLD_POLICY_SCAN_DEADLINE_UNKNOWN') from None
            raise Hold('OLD_POLICY_SCAN_SQLITE_UNKNOWN') from exc
        finally:db.set_progress_handler(None,0)

    def _classify_old_policy_bounded(self,db,ids,project,deadline,
                                     canonical,decode,FIELDS,TARGETS,
                                     ApprovedObjectsPolicy):
        c53.require(time.monotonic()<deadline,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN')
        raw, identity=self.legacy.read(c53.CONFIGS[0])
        c53.require(raw==self.frozen_baselines[c53.CONFIGS[0]] and identity is not None,
                    'OLD_POLICY_CONFIG_CHANGED')
        config=c53.strict_json(raw)
        hook=config.get('approved_objects')
        policy=None
        if hook is not None:
            c53.require(type(hook) is dict and set(hook)=={'metadata_ref','metadata_sha256'}
                        and type(hook['metadata_ref']) is str and
                        hook['metadata_ref']==c53.binder.BIND and
                        type(hook['metadata_sha256']) is str and
                        len(hook['metadata_sha256'])==64,
                        'OLD_POLICY_HOOK_UNKNOWN')
            policy_raw, policy_identity=self.legacy.read(hook['metadata_ref'])
            c53.require(policy_identity is not None and
                        c53.sha(policy_raw)==hook['metadata_sha256'],
                        'OLD_POLICY_SOURCE_CHANGED')
            policy=ApprovedObjectsPolicy(policy_raw,hook['metadata_sha256'])
        where="state IN ('READY','DISPATCHING','UNKNOWN')"
        count,largest,total=db.execute(
            'SELECT count(*),coalesce(max(length(CAST(request_json AS BLOB))),0),'
            'coalesce(sum(length(CAST(request_json AS BLOB))),0) '
            'FROM connection_jobs WHERE '+where).fetchone()
        c53.require(type(count) is int and count<=10000 and
                    type(largest) is int and largest<=16384 and
                    type(total) is int and total<=8*1024*1024,
                    'OLD_POLICY_SCAN_BUDGET_UNKNOWN')
        # Only after the complete row/byte admission may SQLite return any
        # request_json to Python. Never fetchall an unchecked result set.
        query=("SELECT request_id,project,request_json,request_sha,actor_id,state "
               "FROM connection_jobs WHERE "+where+" ORDER BY request_id")
        dependent=0
        observed=0
        digest_rows=hashlib.sha256()
        for rid, row_project, raw_request, digest, actor, state in db.execute(query):
            c53.require(time.monotonic()<deadline,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN')
            observed+=1
            c53.require(observed<=count,'OLD_POLICY_SCAN_CHANGED')
            digest_rows.update(c53.canon([rid,row_project,raw_request,digest,actor,state]))
            c53.require(type(raw_request) is str and len(raw_request.encode('utf-8'))<=16384
                        and type(digest) is str and c53.sha(raw_request.encode())==digest,
                        'OLD_POLICY_REQUEST_HASH_UNKNOWN')
            request=decode(raw_request)
            c53.require(canonical(request)==raw_request and
                        set(request)==FIELDS and
                        request.get('request_id')==rid and
                        request.get('project')==row_project and
                        type(actor) is int and actor==332398908 and
                        type(request.get('operation')) is str and
                        request.get('target') in TARGETS and
                        type(request.get('expires_unix')) is int,
                        'OLD_POLICY_REQUEST_BINDING_UNKNOWN')
            operation=request['operation']
            if operation=='fetch_approved_object':
                c53.require(policy is not None,'OLD_POLICY_FETCH_WITHOUT_SOURCE_UNKNOWN')
                try:policy.request_object(request)
                except BaseException:
                    raise Hold('OLD_POLICY_FETCH_BINDING_UNKNOWN') from None
                dependent+=int(row_project!=project)
            else:
                c53.require((operation=='probe' and request['arguments']=={}) or
                            (operation=='fetch_os_release' and request['arguments']==
                             {'path':'/etc/os-release','max_bytes':65536}),
                            'OLD_POLICY_OPERATION_UNKNOWN')
        # The protected source and the complete bounded set must still be the
        # same immediately before returning zero. A lock protects the worker,
        # while this readback catches a changed source or independent writer.
        config_after, identity_after=self.legacy.read(c53.CONFIGS[0])
        c53.require((config_after,identity_after)==(raw,identity),
                    'OLD_POLICY_CONFIG_CHANGED')
        if hook is not None:
            policy_after, policy_identity_after=self.legacy.read(hook['metadata_ref'])
            c53.require((policy_after,policy_identity_after)==
                        (policy_raw,policy_identity),'OLD_POLICY_SOURCE_CHANGED')
        c53.require(observed==count,'OLD_POLICY_SCAN_CHANGED')
        again=hashlib.sha256();observed_again=0
        for row in db.execute(query):
            c53.require(time.monotonic()<deadline,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN')
            observed_again+=1
            c53.require(observed_again<=count,'OLD_POLICY_QUEUE_CHANGED')
            again.update(c53.canon(list(row)))
        c53.require(observed_again==count and digest_rows.digest()==again.digest(),
                    'OLD_POLICY_QUEUE_CHANGED')
        fields={'project':project,'dependent_active':dependent,'unresolved':0,
                'active_rows':count,'old_binding_sha256':hook['metadata_sha256'] if hook else None}
        c53.require(time.monotonic()<deadline,'OLD_POLICY_SCAN_DEADLINE_UNKNOWN')
        return dict(fields,verified=True,source='ORIGINAL_PROTECTED_OBSERVATION',
                    evidence_sha256=c53.sha(c53.canon(fields)))

    def backup_existing_exact(self,files,current,spec):
        c53.require(self.bundle is not None,'BUNDLE_NOT_GENERATED')
        c53.require(self.generator_inputs_verified is True,
                    'GENERATOR_INPUTS_NOT_VERIFIED')
        c53.validate_bundle(spec,self.bundle,
            verified_baselines=self.frozen_baselines,
            verified_source_blobs=self.source_blobs)
        c53.require(self.lock_fd is not None and self.db is not None,'BACKUP_REQUIRES_LOCK')
        observed=spec['observed_baseline']['files']
        backups=self.paths['backups_proposed']
        require_paths=tuple(files)==c53.CONFIGS+c53.SLOTS
        c53.require(require_paths and tuple(current)==tuple(x+'/current' for x in c53.BASES),'BACKUP_SCOPE')
        for i,path in enumerate(files):
            raw,ident=self.legacy.read(path)
            c53.require(raw==self.frozen_baselines[path] and
                        ident==self.generator_identities[path],
                        'LOCKED_BASELINE_CHANGED')
            if path!=c53.CONFIGS[2]:
                c53.require(c53.sha(raw)==observed[path]['sha256'],'BASELINE_CHANGED')
            self.before[path]=(raw,ident)
            dst=backups['configs'][i] if i<3 else backups['protected_slots'][i-3]
            self.legacy.newfile(dst,raw)
        # Actual byte-level cross-file/schema validation happens *after*
        # hashing the observed baseline, not from a stale 19:20 snapshot.
        c53.verify_observed_bytes(spec,{p:x[0] for p,x in self.before.items()})
        for base in c53.BASES:
            d=self.legacy.parent(base)
            try:
                st=os.stat('current',dir_fd=d,follow_symlinks=False)
                dest=os.readlink('current',dir_fd=d)
                c53.require(stat.S_ISLNK(st.st_mode) and st.st_uid==st.st_gid==0
                            and st.st_nlink==1 and dest==base+'/releases/e78bd7749414d1637012f57b65d2019955282fc3','LINK_BASELINE')
                self.links[base]=(dest,self.legacy.identity(st))
            finally:os.close(d)
        self.legacy.newfile(backups['links'],c53.canon(self.links)+b'\n')

    def publish_two_releases_exact(self,commit,manifest,pin,spec):
        self.verify_external_release('publish')
        c53.require(self.lock_fd is not None and self.before,'PUBLISH_PREREQUISITE')
        c53.require(self.generator_inputs_verified is True and spec is self.spec,
                    'PUBLISH_GENERATOR_BINDING')
        c53.require((commit,manifest,pin)==(c53.COMMIT,c53.MANIFEST,c53.PIN),'RELEASE_PIN')
        binder=c53.binder
        binder.verify_supplied_source(spec,self.source_blobs)
        for base,stage,target in zip(c53.BASES,self.paths['stage_proposed'],self.paths['target_release']):
            self.legacy.absent(stage);self.legacy.absent(target)
            self.legacy.mkdir(stage,0o755)
            created=set()
            for relative,raw in sorted(self.source_blobs.items()):
                c53.require(type(relative) is str and not relative.startswith('/') and '..' not in relative.split('/'),'SOURCE_MEMBER_PATH')
                parts=relative.split('/')[:-1]
                for j in range(1,len(parts)+1):
                    sub='/'.join(parts[:j])
                    if sub not in created:
                        self.legacy.mkdir(stage+'/'+sub,0o755);created.add(sub)
                self.legacy.newfile(stage+'/'+relative,raw,0o644)
            d=self.legacy.parent(base+'/releases')
            try:
                self.legacy.absent(target)
                _rename_release_noreplace(d,os.path.basename(stage),
                                          os.path.basename(target))
                os.fsync(d)
            finally:os.close(d)
            self.checkpoint('RELEASE_PUBLISHED_'+base.rsplit('/',1)[-1])

    def replace_one_existing_verified(self,path,raw,spec):
        c53.require(self.bundle is not None,'BUNDLE_NOT_GENERATED')
        c53.require(self.generator_inputs_verified is True,
                    'GENERATOR_INPUTS_NOT_VERIFIED')
        c53.validate_bundle(spec,self.bundle,
            verified_baselines=self.frozen_baselines,
            verified_source_blobs=self.source_blobs)
        c53.require(raw==self.bundle['files'].get(path),'EXTERNAL_CONFIG_REJECTED')
        c53.require(self.lock_fd is not None and path in c53.CONFIGS+c53.SLOTS,'REPLACE_LOCK_SCOPE')
        previous=self.before[path]
        current,ident=self.legacy.read(path)
        c53.require(current==previous[0] and ident==previous[1],'FOREIGN_CONFIG_CHANGE')
        stage=path+'.l2-b5-staged-'+c53.COMMIT[:12]
        self.legacy.absent(stage)
        self.legacy.newfile(stage,raw)
        self.checkpoint('REPLACE_INTENT_'+path.rsplit('/',1)[-1])
        d=self.legacy.parent(os.path.dirname(path))
        try:
            current2,ident2=self.legacy.read(path)
            c53.require(current2==current and ident2==ident,'REPLACE_RACE')
            os.replace(os.path.basename(stage),os.path.basename(path),src_dir_fd=d,dst_dir_fd=d)
            os.fsync(d)
        finally:os.close(d)
        self.new[path]=self.legacy.read(path)[1]

    def switch_current_verified(self,base,commit,spec):
        c53.require(self.lock_fd is not None and base in c53.BASES and commit==c53.COMMIT,'LINK_SCOPE')
        old,identity=self.links[base]
        d=self.legacy.parent(base)
        try:
            c53.require(self.legacy.identity(os.stat('current',dir_fd=d,follow_symlinks=False))==identity
                        and os.readlink('current',dir_fd=d)==old,'FOREIGN_LINK_CHANGE')
            self.legacy.absent(base+'/current.l2-b5-staged-'+c53.COMMIT[:12])
            os.symlink(base+'/releases/'+commit,'current.l2-b5-staged-'+c53.COMMIT[:12],dir_fd=d)
            self.checkpoint('SWITCH_CURRENT_INTENT_'+base.rsplit('/',1)[-1])
            os.replace('current.l2-b5-staged-'+c53.COMMIT[:12],'current',src_dir_fd=d,dst_dir_fd=d)
            os.fsync(d)
            self.new[base+'/current']=self.legacy.identity(os.stat('current',dir_fd=d,follow_symlinks=False))
        finally:os.close(d)

    def restart_resource_bounded(self):
        self.legacy.command(['/usr/bin/systemctl','restart','xuanjun-cloud-oauth-resource.service'],20)
    def verify_resource_readiness(self): self.legacy.resource_ready()
    def restore_tunnel_only_if_previously_changed(self):
        # No blanket restart: original tunnel remains untouched if not changed.
        return None
    def close_readonly_db(self):
        if self.db is not None:self.db.close();self.db=None
        self.sqlite_bound_fd=None
        self.verified_original_db=False
    def release_original_lock(self):
        if self.lock_fd is not None:os.close(self.lock_fd);self.lock_fd=None
    def persist_new_worker_attempt_before_start(self):
        c53.require(self.db is None and self.lock_fd is None,'UNLOCK_BEFORE_START')
        self.legacy.newfile(self.job+'/NEW_WORKER_START_ATTEMPT.json',
                            c53.canon({'state':'ATTEMPT_STARTED_NO_REPLAY','release':c53.COMMIT})+b'\n')
        self.tried_start=True
    def attach_original_after_worker_start(self):
        c53.require(self.db is None and self.lock_fd is None and self.tried_start,
                    'RUNTIME_ATTACHMENT_ORDER')
        self._auth('attach_original_after_worker_start')
        c53.require(self.bundle is not None and self.activation_committed is True,
                    'RUNTIME_ATTACHMENT_ACTIVATION')
        return True
    def start_worker_bounded(self):
        self.verify_external_release('start')
        c53.require(self.tried_start,'START_MARKER_REQUIRED')
        self.legacy.command(['/usr/bin/systemctl','start','xuanjun-cloud-connection.service'],20)
    def verify_worker_stable(self):self.legacy.stable_unit('xuanjun-cloud-connection.service')
    def verify_window_admission(self,bundle,spec):
        return self.verify_maintenance_window_admission(bundle,spec)
    def enable_window_60m(self,bundle):
        now=int(time.time())
        c53.require(type(bundle['window_start']) is int and type(bundle['window_end']) is int
                    and bundle['window_end']-bundle['window_start']==3600
                    and bundle['window_start']<=now<bundle['window_end'],'WINDOW_INVALID_OR_EXPIRED')
        self.legacy.newfile(self.job+'/window-open.json',
             c53.canon({'window_start':bundle['window_start'],'window_end':bundle['window_end'],
                         'catalog_sha256':bundle['catalog_sha'],'opened_at':now,
                         'remaining_seconds_at_open':bundle['window_end']-now,
                         'state':'ACTIVE_NOT_DELIVERED'})+b'\n')
        self.window_open=True
    def check_fixed_envelope_size_limit(self,bundle,limit):
        c53.require(limit==16384 and all(len(x.encode('utf-8'))<=limit for x in bundle['envelopes']),'COMMAND_BUDGET')
    def submit_original_intake_once(self,request):
        rid=request.get('request_id') if type(request) is dict else None
        c53.require(rid in self.expected_ids and self.window_open is True,
                    'INTAKE_FIXED_WINDOW_IDENTITY')
        from production.cloud_connection.queue import canonical
        digest=c53.sha(canonical(request).encode())
        intent=self.job+'/intake-'+rid+'.intent.json'
        sent=self.job+'/intake-'+rid+'.sent.json'
        def persist_intent(actual, actual_digest):
            c53.require((actual,actual_digest)==(rid,digest), 'INTAKE_INTENT_BINDING')
            self.legacy.absent(intent)
            self.legacy.newfile(intent,c53.canon({'request_id':rid,'request_sha256':digest,
                'catalog_sha256':self.bundle['catalog_sha'],'actor_id':332398908,
                'state':'POST_MAY_HAVE_OCCURRED_NO_REPOST'})+b'\n')
        def persist_sent(actual, actual_digest, comment_id):
            c53.require((actual,actual_digest)==(rid,digest) and
                        type(comment_id) is int,'INTAKE_SENT_BINDING')
            self.legacy.newfile(sent,c53.canon({'request_id':rid,'request_sha256':digest,
                'comment_id':comment_id,'state':'SENT_NOT_ACCEPTED'})+b'\n')
        receipt=self._auth('submit_original_intake_once',request,persist_intent,persist_sent)
        c53.require(type(receipt) is dict and receipt.get('request_id')==rid and
                    receipt.get('state')=='SENT_NOT_ACCEPTED','INTAKE_NOT_SENT')
        return {'request_id':rid,'state':'PENDING'}

    def observe_original_intake_ready(self,request):
        rid=request.get('request_id') if type(request) is dict else None
        c53.require(rid in self.expected_ids and self.window_open is True,
                    'INTAKE_OBSERVATION_SCOPE')
        raw,_=self.legacy.read(self.job+'/intake-'+rid+'.intent.json')
        from production.cloud_connection.queue import canonical
        intent=c53.strict_json(raw)
        c53.require(intent=={'request_id':rid,
            'request_sha256':c53.sha(canonical(request).encode()),
            'catalog_sha256':self.bundle['catalog_sha'],'actor_id':332398908,
            'state':'POST_MAY_HAVE_OCCURRED_NO_REPOST'},
            'INTAKE_INTENT_CHANGED')
        observed=self._auth('observe_original_intake_ready',request)
        c53.require(type(observed) is dict and observed.get('request_id')==rid and
                    observed.get('state')=='ACCEPTED','INTAKE_READY_NOT_PROVEN')
        return observed
    def observe_original_success_progress(self,ids,bundle):
        c53.require(tuple(ids)==self.expected_ids and
                    bundle['catalog_sha']==self.bundle['catalog_sha'],
                    'SUCCESS_PROGRESS_SCOPE')
        count=self._auth('observe_original_success_progress',ids,bundle['catalog_sha'])
        c53.require(type(count) is int and 0<=count<=19,
                    'SUCCESS_PROGRESS_UNKNOWN')
        return count
    def verify_original_success_receipts(self,ids,bundle,spec):
        receipts=self._receipt('verify_nineteen_original_success_receipts',ids,bundle['catalog_sha'])
        c53.require(receipts.get('success_count')==19 and receipts.get('invoke_bound_count')==19
                    and receipts.get('sha_bound_count')==19 and receipts.get('catalog_sha256')==bundle['catalog_sha'],
                    'NINETEEN_SUCCESS_NOT_PROVEN')
    def verify_original_archive_identity_and_whole_digest(self,size,digest):
        r=self._receipt('verify_original_archive_custody',size,digest)
        c53.require(r.get('whole_sha_verified') is True and r.get('source_bytes')==559237632
                    and r.get('sha256')==binder.ARCHIVE_SHA,'ARCHIVE_WHOLE_SHA_UNPROVEN')
    def custody_once_authenticated(self,bundle,spec):
        self.verify_window_admission(bundle,spec)
        receipt=self._receipt('custody_once',self.job,bundle['catalog_sha'])
        c53.require(receipt.get('state')=='MATERIAL_CUSTODY_COMPLETE' and
                    receipt.get('objects')==19 and receipt.get('bytes')==93592 and
                    receipt.get('catalog_sha256')==bundle['catalog_sha'] and
                    receipt.get('source_execution') is False,'CUSTODY_RECEIPT_UNPROVEN')
        return receipt
    def read_original_project_body(self,request,catalog_sha,obj):
        # Original approved reader is the ONLY allowed transport. It must supply
        # exact object bytes from the SUCCESS-bound request using contiguous
        # fixed offsets and the same authenticated recipient. Missing API=>HOLD.
        c53.require(self.bundle is not None and catalog_sha==self.bundle['catalog_sha'],
                    'RECEIVER_CURRENT_CATALOG')
        self.verify_window_admission(self.bundle,self.spec)
        body=self._auth('read_project_chunk_complete',request,catalog_sha,obj)
        c53.require(type(body) is bytes,'RECEIVER_BODY_UNKNOWN')
        return body

    def verify_b5_http_provenance(self,proof,bundle,spec):
        c53.require(bundle is self.bundle and spec is self.spec and
                    type(proof) is dict and
                    proof.get('state') ==
                    'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
                    'B5_HTTP_PROOF_BOUNDARY')
        # The local SHA proof is deliberately insufficient. Only the B5
        # request-local cloud tool's authenticated provenance may close it.
        return self._auth('verify_b5_http_provenance',proof,bundle['catalog_sha'],
                          self.expected_ids)

    def approve_precise_b5_exposure_close(self,bundle,spec):
        c53.require(bundle is self.bundle and spec is self.spec,
                    'SUCCESSOR_CLOSE_SCOPE')
        return self._auth('approve_c53_b5_exposure_close',self.job)

    def close_b5_exposure_success_successor_only(self):
        # The original close implementation rechecks its own independent
        # approval before touching the worker. No alias bypasses that gate.
        return self.close_b5_exposure_success_c53_only()
    def close_b5_exposure_success_c53_only(self):
        # Successful delivery closeout never restores the e78 runtime or removes
        # queue history. It disables only B5 exposure; consent is not revoked.
        approved=self._receipt('approve_c53_b5_exposure_close',self.job)
        c53.require(approved.get('approved') is True and approved.get('job')==self.job,
                    'SUCCESSOR_CLOSEOUT_NOT_APPROVED')
        self.legacy.command(['/usr/bin/systemctl','stop','xuanjun-cloud-connection.service'],60)
        self.legacy.command(['/usr/bin/systemctl','is-active','--quiet',
                             'xuanjun-cloud-connection.service'],10,(3,))
        self.worker_stopped=True
        try:
            from pr17_b5_successor_authority import ExistingRequestAuthority
            c53.require(type(self.authority) is ExistingRequestAuthority and
                        self.authority.original is not None,
                        'CLOSEOUT_ORIGINAL_OBSERVER_UNKNOWN')
            self.authority.original.release_observer_for_closeout()
            self.acquire_original_lock_once()
            self.legacy.check_original_database()
            for suffix in ('-wal','-shm','-journal'):
                self.legacy.absent(c53.DB+suffix)
            self._connect_verified_original_queue('CLOSEOUT_DB')
            q='SELECT state,invoke_id FROM connection_jobs WHERE request_id IN ('+','.join('?' for _ in self.expected_ids)+')'
            rows=self.db.execute(q,self.expected_ids).fetchall()
            c53.require(len(rows)==19 and all(state=='SUCCESS' and invoke is not None for state,invoke in rows),'CLOSEOUT_19_NOT_TERMINAL')
            nonterminal=self.db.execute("SELECT count(*) FROM connection_jobs WHERE project=? AND state IN ('READY','DISPATCHING','UNKNOWN')",(c53.PROJ,)).fetchone()[0]
            outbox=self.db.execute("SELECT count(*) FROM connection_outbox WHERE state IN ('READY','POSTING')").fetchone()[0]
            c53.require(nonterminal==0 and outbox==0,'CLOSEOUT_QUEUE_CONFLICT')
            resource_original, _=self.before[c53.CONFIGS[1]]
            c53.require(c53.sha(resource_original)==c53.binder.RESOURCE_SHA,'CLOSEOUT_ORIGINAL_RESOURCE')
            connection=c53.strict_json(self.bundle['files'][c53.CONFIGS[0]])
            c53.require(connection.pop('approved_objects',None) is not None,'CLOSEOUT_HOOK_NOT_ACTIVE')
            c53.require(connection['executor_sha256']==c53.PIN,'CLOSEOUT_SUCCESSOR_PIN')
            oldenv,order=c53.env_read(self.before[c53.CONFIGS[2]][0])
            oldenv['OAUTH_CONFIG_SHA256']=c53.binder.RESOURCE_SHA
            oldenv['OAUTH_SOURCE_MANIFEST_SHA256']=c53.MANIFEST
            env_raw=('\n'.join(k+'='+oldenv[k] for k in order)+'\n').encode('ascii')
            closefiles={c53.CONFIGS[1]:resource_original,c53.CONFIGS[2]:env_raw,
                        c53.CONFIGS[0]:c53.canon(connection)}
            for p in c53.CONFIGS[1:]:
                self._close_replace_one(p,closefiles[p])
            self.legacy.command(['/usr/bin/systemctl','restart','xuanjun-cloud-oauth-resource.service'],20)
            self.legacy.resource_ready()
            self._close_replace_one(c53.CONFIGS[0],closefiles[c53.CONFIGS[0]])
            self.close_readonly_db();self.release_original_lock()
            self.legacy.newfile(self.job+'/CLOSEOUT_WORKER_START_ATTEMPT.json',c53.canon({'state':'SUCCESSOR_START_ATTEMPT_NO_REPLAY'})+b'\n')
            self.legacy.command(['/usr/bin/systemctl','start','xuanjun-cloud-connection.service'],20)
            self.legacy.stable_unit('xuanjun-cloud-connection.service')
            self.legacy.newfile(self.job+'/b5-exposure-closed.json',c53.canon({'state':'B5_CLOSED_SUCCESSOR_HISTORY_PRESERVED','grant_revoked':False})+b'\n')
        except BaseException:
            self.close_b5_exposure_and_stop_c53_fail_closed()
            raise
        finally:
            self.close_readonly_db();self.release_original_lock()

    def _close_replace_one(self,path,raw):
        c53.require(self.lock_fd is not None and path in c53.CONFIGS,'CLOSEOUT_LOCK_SCOPE')
        before,identity_before=self.legacy.read(path)
        c53.require(path in self.new and self.new[path] is not None,
                    'CLOSEOUT_NEW_IDENTITY_MISSING')
        c53.require(identity_before==self.new[path],
                    'CLOSEOUT_FOREIGN_INODE')
        c53.require(c53.sha(before)==self.bundle['file_sha'][path],
                    'CLOSEOUT_FOREIGN_CONFIG')
        stage=path+'.l2-b5-staged-f0fe0d3978b7-close'
        self.legacy.absent(stage)
        self.legacy.newfile(stage,raw)
        self.checkpoint('CLOSEOUT_REPLACE_INTENT_'+path.rsplit('/',1)[-1])
        d=self.legacy.parent(os.path.dirname(path))
        try:
            current,identity_current=self.legacy.read(path)
            c53.require(current==before and
                        identity_current==identity_before and
                        identity_current==self.new[path],
                        'CLOSEOUT_CONFIG_IDENTITY_CHANGED')
            os.replace(os.path.basename(stage),os.path.basename(path),src_dir_fd=d,dst_dir_fd=d)
            os.fsync(d)
        finally:os.close(d)
    def canonical_state_unknown(self):
        # Only a canonical independently validated queue audit may return False.
        try:
            observed=self._auth('canonical_state_unknown',self.job)
            return observed if type(observed) is bool else True
        except BaseException:return True
    def prove_no_new_operations_canonically(self):
        return self._auth('prove_no_new_operations_canonically',self.job) is True
    def canonical_prestart_no_new_operations(self):
        """Narrow original-DB proof only before any new worker start marker.

        This never proves old-policy dependency, grant, or restore approval.
        It is valid only under the original stopped-worker lock and the exact
        read-only DB handle already admitted by _connect_verified_original_queue.
        """
        if (self.lock_fd is None or self.db is None or
                self.verified_original_db is not True or
                self.worker_stopped is not True
                or self.tried_start is not False or self.window_open is not False
                or self.bundle is None or self.reserved is not True):
            return False
        try:
            self.legacy.absent(self.job+'/NEW_WORKER_START_ATTEMPT.json')
            self.legacy.absent(self.job+'/window-open.json')
            for rid in self.expected_ids:
                self.legacy.absent(self.job+'/intake-'+rid+'.intent.json')
                self.legacy.absent(self.job+'/intake-'+rid+'.sent.json')
            ids=tuple(self.expected_ids)
            c53.require(len(ids)==19 and len(set(ids))==19 and
                        ids==tuple(x['request_id'] for x in self.bundle['requests']),
                        'CANONICAL_PRESTART_REQUEST_BINDING')
            query=','.join('?' for _ in ids)
            jobs=self.db.execute('SELECT count(*) FROM connection_jobs WHERE request_id IN ('+query+')',ids).fetchone()
            outbox=self.db.execute('SELECT count(*) FROM connection_outbox WHERE request_id IN ('+query+')',ids).fetchone()
            return jobs==(0,) and outbox==(0,)
        except BaseException:
            return False

    def observe_fixed_receiver_target_readonly(self, root, ids):
        """Conservative original target observation; existing content HOLDs.

        This proves an empty protected receiver at the instant of observation,
        not old-policy independence or a future write reservation.
        """
        c53.require(root==self.paths['receiver_root'] and
                    tuple(ids)==self.expected_ids and len(set(ids))==19,
                    'RECEIVER_OBSERVATION_SCOPE')
        from production.cloud_connection.private_transfer import directory
        fd=directory(root,0,private=True)
        try:
            before=os.fstat(fd)
            c53.require(os.listdir(fd)==[], 'RECEIVER_NOT_EMPTY')
            second=directory(root,0,private=True)
            try:
                after=os.fstat(second)
                c53.require((before.st_dev,before.st_ino,before.st_mode)==
                            (after.st_dev,after.st_ino,after.st_mode) and
                            os.listdir(second)==[], 'RECEIVER_IDENTITY_CHANGED')
            finally:os.close(second)
        finally:os.close(fd)
        record={'receiver_root':root,'no_conflicts':True,
                'request_set_sha256':c53.sha(c53.canon(list(ids)))}
        return dict(record,verified=True,source='ORIGINAL_PROTECTED_OBSERVATION',
                    evidence_sha256=c53.sha(c53.canon(record)))
    def restore_exact_backups_pre_start_only(self,changed,spec):
        c53.require(not self.tried_start and self.lock_fd is not None,'RESTORE_AFTER_START_OR_LOCK_LOST')
        approved=self._receipt('approve_precise_pre_start_restore',self.job)
        c53.require(approved.get('approved') is True and approved.get('job')==self.job,
                    'RESTORE_NOT_APPROVED_OR_JOB_MISMATCH')
        # The actual byte backup and identity CAS are checked before every
        # replacement; cannot copy back DB/lock/receiver or unrelated files.
        for path in changed:
            c53.require(path in self.before or path in self.new,'RESTORE_PATH_SCOPE')
            if path in self.before:
                raw,ident=self.before[path]
                current,current_id=self.legacy.read(path)
                c53.require(current_id==self.new.get(path),'RESTORE_FOREIGN_CONFIG')
                stage=path+'.l2-b5-staged-f0fe0d3978b7-restore'
                self.legacy.absent(stage);self.legacy.newfile(stage,raw)
                d=self.legacy.parent(os.path.dirname(path))
                try:
                    c53.require(self.legacy.read(path)[1]==current_id,'RESTORE_RACE')
                    os.replace(os.path.basename(stage),os.path.basename(path),src_dir_fd=d,dst_dir_fd=d)
                    os.fsync(d)
                finally:os.close(d)
            else:
                base=os.path.dirname(path)
                dest,oldid=self.links[base]
                d=self.legacy.parent(base)
                try:
                    now=self.legacy.identity(os.stat('current',dir_fd=d,follow_symlinks=False))
                    c53.require(now==self.new.get(path),'RESTORE_LINK_RACE')
                    stage='current.l2-b5-staged-f0fe0d3978b7-restore'
                    self.legacy.absent(base+'/'+stage)
                    os.symlink(dest,stage,dir_fd=d)
                    os.replace(stage,'current',src_dir_fd=d,dst_dir_fd=d)
                    os.fsync(d)
                finally:os.close(d)
        self.close_readonly_db()
        self.release_original_lock()
        self.legacy.command(['/usr/bin/systemctl','restart','xuanjun-cloud-oauth-resource.service'],20)
        self.legacy.resource_ready()
        self.legacy.command(['/usr/bin/systemctl','start','xuanjun-cloud-connection.service'],20)
    def close_b5_exposure_and_stop_c53_fail_closed(self):
        # After possible worker start: never restore e78/old policy/DB.
        # Stopping fixed services is a bounded fail-closed action; no grant revoke.
        outcomes=[]
        for unit in ('xuanjun-cloud-connection.service','xuanjun-cloud-oauth-resource.service'):
            state='UNKNOWN'
            try:
                self.legacy.command(['/usr/bin/systemctl','stop',unit],60)
                self.legacy.command(['/usr/bin/systemctl','is-active','--quiet',unit],10,(3,))
                state='INACTIVE_CONFIRMED'
            except BaseException:
                state='STOP_FAILED_OR_UNKNOWN'
            outcomes.append({'unit':unit,'state':state})
        self.stop_outcome={'state':'ALL_STOPPED' if all(x['state']=='INACTIVE_CONFIRMED' for x in outcomes) else 'UNKNOWN',
                           'units':outcomes}
        return self.stop_outcome


def prepare_bound_transaction(*, spec_raw, observed_bytes, source_blobs,
                              batch_id, approval_ref, window_start,
                              legacy_io, authority=None, release_gate=None):
    """Explicit generator -> sealed transaction -> backend linkage.

    Does not execute the transaction or create grant/ACK; absent authority
    remains HOLD upon execute() before worker stop. Caller must supply real
    baseline bytes, 32 source files plus pinned manifest, and a separately
    reviewed authenticated authority provider.
    """
    spec=c53.binder.verify_spec_bytes(spec_raw)
    bundle=c53.make_bundle(spec,observed_bytes,source_blobs,
                           batch_id=batch_id,approval_ref=approval_ref,
                           window_start=window_start)
    c53.validate_bundle(spec,bundle,
        verified_baselines=observed_bytes,
        verified_source_blobs=source_blobs)
    backend=R2HostBackend(legacy_io=legacy_io,spec=spec,
                           source_blobs=source_blobs,
                           observed_bytes=observed_bytes,authority=authority,
                           release_gate=release_gate)
    if authority is not None:
        from pr17_b5_successor_authority import ExistingRequestAuthority
        c53.require(type(authority) is ExistingRequestAuthority,'ORIGINAL_AUTHORITY_TYPE')
        authority.precheck_old_policy_reader=backend.observe_prestart_old_policy_dependency
        authority.old_policy_reader=backend.observe_cross_project_old_policy_dependency
    transaction=c53.Transaction(spec,bundle,backend)
    return transaction
