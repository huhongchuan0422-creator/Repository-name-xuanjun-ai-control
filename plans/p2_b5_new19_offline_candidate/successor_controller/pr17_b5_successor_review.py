"""PR17 c53 successor transaction implementation, independent review candidate.

No implicit execution. Does not import or run old e78 CLI. A future live backend
must be independently reviewed and must authenticate grant/ACK before side effects.
This module supplies exact config generation, an ordered state machine, immutable
checkpoint intents, protected backups, one-lock admission, and fail-closed recovery.
"""
import copy
import hashlib
import json
import re

import pr17_b5_successor_binder as binder

HOST = binder.HOST
SPEC_CANON_SHA = '7ff2992ed2a4ba84063e03d62456f71f3ed757cc2a8eefb495c20aab719f8b28'
COMMIT = binder.COMMIT
PIN = binder.CODEPIN
MANIFEST = binder.MANIFEST
PROJ = binder.PROJECT
RECIP = binder.RECIPIENT
SUBJECT = binder.ACTOR
ETC = binder.ETC
DB = '/var/lib/xuanjun-cloud-connection/queue.sqlite'
LOCK = '/var/lib/xuanjun-cloud-connection/worker.lock'
CONFIGS = (ETC+'/connection.json', ETC+'/oauth-resource.json', ETC+'/oauth-resource.env')
SLOTS = (binder.BIND, binder.CUSTODY, binder.CATALOG)
BASES = ('/opt/xuanjun-cloud-connection', '/opt/xuanjun-cloud-oauth')
ROOTS = {'b5-original-archive':[binder.ARCHIVE_ROOT,1002],
         'b5-original-packages':[binder.PACKAGE_ROOT,1002]}
SOURCE_PRODUCER = binder.SOURCE_PRODUCER
ARCHIVE_META = dict(filename='source-tree.tar.pending',
    identity=list(binder.ARCHIVE_IDENTITY), member_prefix=binder.ARCHIVE_PREFIX,
    max_headers=65536, max_read_bytes=32*1024*1024, sha256=binder.ARCHIVE_SHA)

class Hold(RuntimeError):
    pass

def require(ok, code):
    if not ok: raise Hold(code)

def canon(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def sha(raw): return hashlib.sha256(raw).hexdigest()

def strict_json(raw):
    def pairs(xs):
        d={}
        for k,v in xs:
            require(k not in d,'DUPLICATE_KEY')
            d[k]=v
        return d
    try:
        d=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Hold('NONFINITE')))
    except Hold: raise
    except (TypeError,ValueError,UnicodeError): raise Hold('INVALID_JSON') from None
    require(type(d) is dict,'JSON_OBJECT')
    return d

def env_read(raw):
    try: lines=raw.decode('ascii').splitlines()
    except UnicodeError: raise Hold('ENV_ENCODING') from None
    d={}; keys=[]
    for line in lines:
        k,sep,v=line.partition('=')
        require(sep=='=' and k not in d and v and not any(x in v for x in ('\r','\x00')),'ENV_FORMAT')
        d[k]=v;keys.append(k)
    require(set(d)=={'OAUTH_CONFIG_SHA256','OAUTH_SOURCE_MANIFEST_SHA256','SSL_CERT_FILE'},'ENV_KEYS')
    require(re.fullmatch('[0-9a-f]{64}',d['OAUTH_CONFIG_SHA256']) is not None,'ENV_CONFIG_DIGEST')
    require(d['OAUTH_SOURCE_MANIFEST_SHA256']==binder.E78_MANIFEST,'ENV_E78_MANIFEST')
    require(d['SSL_CERT_FILE']==binder.CERT,'ENV_CERT')
    return d,keys

def verify_observed_bytes(spec, baselines):
    """Bound *current* e78 withdrawal bytes; do not assume three slots absent.

    Expected SHA is from Owner's 19:20 observation and must be rechecked under
    original lock adjacent to later changes by the live backend.
    """
    require(type(baselines) is dict and set(baselines)==set(CONFIGS+SLOTS),'BASELINE_SIX')
    expect={p:spec['observed_baseline']['files'][p]['sha256'] for p in CONFIGS[:2]+SLOTS}
    for p in CONFIGS+SLOTS:
        raw=baselines[p]
        require(type(raw) is bytes and len(raw)<=16384,'BASELINE_BYTES')
        if p in expect: require(sha(raw)==expect[p],'BASELINE_HASH_CHANGED')
    conn=strict_json(baselines[CONFIGS[0]])
    require(set(conn)=={'executor_sha256','allowed_actor_ids','github_token_ref','github_token_owner',
                       'credentials_ref','state_root','poll_seconds'},'WITHDRAWN_CONNECTION_FIELDS')
    require(conn['executor_sha256']==binder.E78_PIN and conn['allowed_actor_ids']==[332398908],
            'E78_WITHDRAWN_SCOPE')
    require(conn['state_root']=='/var/lib/xuanjun-cloud-connection','STATE_ROOT')
    resource=strict_json(baselines[CONFIGS[1]])
    require(sha(baselines[CONFIGS[1]])==binder.RESOURCE_SHA,'RESOURCE_ORIGINAL')
    env,order=env_read(baselines[CONFIGS[2]])
    require(env['OAUTH_CONFIG_SHA256']==binder.RESOURCE_SHA,'ENV_RESOURCE_SHA')
    return conn,resource,env,order

def make_bundle(spec,baselines,source_blobs,*,batch_id,approval_ref,window_start,authenticated=False):
    """Generate six exact protected configuration bytes + 19 frozen envelopes.

    This only constructs bytes. 'authenticated' is intentionally an external
    argument that MUST be True after real authorization is independently verified;
    it is NOT proof or consent and is never used to authorize transactions.
    """
    binder.verify_supplied_source(spec,source_blobs)
    require(type(batch_id) is str and re.fullmatch('[a-z0-9][a-z0-9-]{15,47}',batch_id),'BATCH_FORMAT')
    require(type(approval_ref) is str and binder.TOKEN.fullmatch(approval_ref),'APPROVAL_REF_SYNTAX')
    require(type(window_start) is int and 0<window_start<253402000000,'WINDOW_TIME')
    require(type(authenticated) is bool,'AUTH_FLAG_TYPE')
    expected_id=['l2-b5-'+batch_id+'-%02d'%(i+1) for i in range(19)]
    require(len(set(expected_id))==19 and all(binder.TOKEN.fullmatch(x) for x in expected_id),'REQUEST_ID_FORMAT')
    require(not any(x.startswith('l2-b5-b5-material-e78-20261023-') for x in expected_id),'OLD_ID_REUSE')
    conn,resource,env,order=verify_observed_bytes(spec,baselines)
    objects=[{'ref':'b5-material-%02d'%(i+1), 'root_ref': 'b5-original-archive' if i<5 else 'b5-original-packages',
              'relative_path':x['relative_path'],'bytes':x['bytes'],'sha256':x['sha256']}
             for i,x in enumerate(spec['objects'])]
    require(len(objects)==19 and sum(x['bytes'] for x in objects)==93592,'OBJECT_TOTAL')
    catalog=dict(schema=1,project=PROJ,approval_ref=approval_ref,source_commit=SOURCE_PRODUCER,
                 executor_sha256=PIN,target='uk',valid_from=window_start,valid_until=window_start+3600,
                 recipients=[RECIP],objects=objects)
    catalog_raw=canon(catalog);cat_sha=sha(catalog_raw)
    policy=dict(project=PROJ,max_objects=19,max_object_bytes=53969,max_total_bytes=93592,
                recipients=[RECIP],root_refs=list(ROOTS))
    requests={x['ref']:rid for x,rid in zip(objects,expected_id)}
    binding=dict(schema=1,catalog=catalog,catalog_sha256=cat_sha,policy=policy,
                 roots=copy.deepcopy(ROOTS),recipient_id=RECIP,requests=requests,
                 execution_user='root',execution_uid=0,
                 reader_sha256=sha(source_blobs['production/cloud_connection/private_transfer.py']),
                 archive_reader_sha256=sha(source_blobs['production/cloud_connection/archive_reader.py']),
                 archives={'b5-original-archive':copy.deepcopy(ARCHIVE_META)})
    binding_raw=canon(binding)
    require(len(binding_raw)<=16384,'BINDING_BUDGET')
    hook=dict(metadata_ref=binder.BIND,metadata_sha256=sha(binding_raw))
    custody=dict(schema=1,enabled=True,approved_objects=hook,
                 destination_root=binder.DEST,destination_owner=0)
    # Preserve the original subject/project; add only the approved B5 mapping.
    require(type(resource.get('settings')) is dict,'RESOURCE_SETTINGS')
    settings=resource['settings']
    require(type(settings.get('subjects')) is dict,'RESOURCE_SUBJECTS')
    sub=settings['subjects'].get(SUBJECT)
    require(type(sub) is dict and type(sub.get('projects')) is list,'RESOURCE_SUBJECT')
    require(PROJ not in sub['projects'],'B5_ALREADY_EXPOSED')
    sub['projects'].append(PROJ);sub['recipient']=RECIP
    resource['catalogs']=[dict(manifest_ref=binder.CATALOG,manifest_sha256=cat_sha,
                               policy=copy.deepcopy(policy),roots=copy.deepcopy(ROOTS))]
    resource['custodies']={cat_sha:[binder.DEST,0]}
    resource_raw=canon(resource)
    conn['executor_sha256']=PIN;conn['approved_objects']=hook
    env['OAUTH_CONFIG_SHA256']=sha(resource_raw)
    env['OAUTH_SOURCE_MANIFEST_SHA256']=MANIFEST
    env_raw=('\n'.join(k+'='+env[k] for k in order)+'\n').encode('ascii')
    files={CONFIGS[0]:canon(conn), CONFIGS[1]:resource_raw,CONFIGS[2]:env_raw,
           binder.BIND:binding_raw,binder.CUSTODY:canon(custody),binder.CATALOG:catalog_raw}
    envelopes=[{'schema':1,'request_id':requests[obj['ref']],'project':PROJ,'target':'uk',
                'operation':'fetch_approved_object','executor_sha256':PIN,
                'arguments':{'manifest_sha256':cat_sha,'object_ref':obj['ref'],'recipient_id':RECIP},
                'expires_unix':window_start+3600} for obj in objects]
    return seal_bundle({'files':files,'file_sha':{p:sha(v) for p,v in files.items()},'catalog_sha':cat_sha,
            'requests':envelopes,'envelopes':['XJ_CLOUD_TASK_V1\n'+canon(x).decode('utf-8') for x in envelopes],
            'batch_id':batch_id,'window_start':window_start,'window_end':window_start+3600,
            'authority_verified':False,'grant_created':False,'submitted':False})

def bundle_seal(bundle):
    data={k:v for k,v in bundle.items() if k!='generation_seal'}
    # Canonical hash of fixed generator outputs, not grant/consent.
    data=dict(data)
    data['files']={k:sha(v) for k,v in sorted(data['files'].items())}
    return sha(canon(data))

def validate_bundle(spec,bundle,*,verified_baselines=None,verified_source_blobs=None):
    require(type(bundle) is dict and set(bundle['files'])==set(CONFIGS+SLOTS),'BUNDLE_SIX')
    require(bundle.get('generation_seal')==bundle_seal(bundle),'BUNDLE_MUTATED')
    require({p:sha(v) for p,v in bundle['files'].items()}==bundle['file_sha'],'BUNDLE_HASHES')
    docs={p:strict_json(bundle['files'][p]) for p in CONFIGS[:2]+SLOTS}
    env,order=env_read(bundle['files'][CONFIGS[2]]) if False else (None,None)
    env_raw=bundle['files'][CONFIGS[2]].decode('ascii')
    pairs=[row.split('=',1) for row in env_raw.splitlines()]
    require(all(len(x)==2 for x in pairs) and len(pairs)==3 and len({x[0] for x in pairs})==3,'BUNDLE_ENV_FORMAT')
    env=dict(pairs)
    require(env.get('OAUTH_CONFIG_SHA256')==sha(bundle['files'][CONFIGS[1]]) and
            env.get('OAUTH_SOURCE_MANIFEST_SHA256')==MANIFEST and
            env.get('SSL_CERT_FILE')==binder.CERT,'BUNDLE_ENV_BINDING')
    catalog=docs[binder.CATALOG]; binding=docs[binder.BIND];custody=docs[binder.CUSTODY]
    cat_hash=sha(bundle['files'][binder.CATALOG]);bind_hash=sha(bundle['files'][binder.BIND])
    require(cat_hash==bundle['catalog_sha'] and binding.get('catalog_sha256')==cat_hash,'BUNDLE_CATALOG_SHA')
    require(docs[CONFIGS[0]].get('executor_sha256')==PIN and
       docs[CONFIGS[0]].get('approved_objects')=={'metadata_ref':binder.BIND,'metadata_sha256':bind_hash},'BUNDLE_CONNECTION_HOOK')
    require(custody.get('approved_objects')==docs[CONFIGS[0]]['approved_objects'],'BUNDLE_CUSTODY_HOOK')
    resource=docs[CONFIGS[1]]
    require(resource.get('catalogs',[{}])[0].get('manifest_sha256')==cat_hash and
       cat_hash in resource.get('custodies',{}),'BUNDLE_RESOURCE_BINDING')
    objects=catalog.get('objects')
    require(type(objects) is list and len(objects)==19 and
       all(type(x) is dict for x in objects),'BUNDLE_OBJECTS')
    fixed=spec['objects']
    for i,(obj,meta) in enumerate(zip(objects,fixed)):
        require(obj.get('ref')=='b5-material-%02d'%(i+1) and
          (obj.get('relative_path'),obj.get('bytes'),obj.get('sha256'))==
          (meta['relative_path'],meta['bytes'],meta['sha256']),'BUNDLE_OBJECT_IDENTITY')
    require(len(bundle.get('requests',[]))==19 and len(bundle.get('envelopes',[]))==19,'BUNDLE_REQUEST_COUNT')
    for i,(req,wire) in enumerate(zip(bundle['requests'],bundle['envelopes'])):
        require(wire=='XJ_CLOUD_TASK_V1\n'+canon(req).decode('utf-8'),'BUNDLE_ENVELOPE')
        require(req.get('request_id')==binding['requests'][objects[i]['ref']] and
                req.get('arguments')=={'manifest_sha256':cat_hash,'object_ref':objects[i]['ref'],'recipient_id':RECIP} and
                req.get('executor_sha256')==PIN and req.get('expires_unix')==bundle['window_end'], 'BUNDLE_REQUEST_PIN')
    require(catalog.get('valid_from')==bundle['window_start'] and
            catalog.get('valid_until')==bundle['window_end']==bundle['window_start']+3600,'BUNDLE_WINDOW')
    require(type(verified_baselines) is dict and
            type(verified_source_blobs) is dict,'GENERATOR_INPUTS_NOT_VERIFIED')
    expected=make_bundle(
        spec,verified_baselines,verified_source_blobs,
        batch_id=bundle['batch_id'],approval_ref=catalog['approval_ref'],
        window_start=bundle['window_start'])
    for path in CONFIGS+SLOTS:
        require(bundle['files'][path]==expected['files'][path],
                'GENERATOR_CLOSURE_FILE:'+path)
    require(bundle['requests']==expected['requests'] and
            bundle['envelopes']==expected['envelopes'] and
            bundle==expected,'GENERATOR_CLOSURE_MISMATCH')
    return True

def seal_bundle(bundle):
    bundle['generation_seal']=bundle_seal(bundle)
    return bundle

class Transaction:
    """Live-capable *protocol*, but actual effects require a separately reviewed backend.

    Backend must bind exact host and approval through its own trusted source,
    preserve state before side effects, and authenticate receipts. Boolean
    caller input is NOT an authority. No real backend is bundled in this file.
    """
    def __init__(self,spec,bundle,backend):
        require(type(spec) is dict and sha(canon(spec))==SPEC_CANON_SHA,'SPEC_OBJECT_NOT_PINNED')
        require(type(bundle) is dict and type(bundle.get('requests')) is list and len(bundle['requests'])==19,'BUNDLE_REQUEST_SET')
        require(len({x['request_id'] for x in bundle['requests']})==19,'BUNDLE_REQUEST_DUPLICATE')
        require(type(bundle.get('files')) is dict and set(bundle['files'])==set(CONFIGS+SLOTS),'BUNDLE_FILES_SCOPE')
        # This object is constructed only from the exact generator output, never
        # from caller-supplied arbitrary config bytes or request envelopes.
        # The externally sealed bundle is not trusted provenance.
        # Closure is verified against frozen trusted inputs before first checkpoint.
        self.spec=spec; self.bundle=bundle; self.b=backend
        self.stage='NEW'; self.worker_stop_attempted=False
        self.worker_start_attempted=None; self.state_unknown=True
        self.locked=False;self.backup_done=False;self.changed=[];self.started=False
        self.trace=[];self.stop_outcome={'state':'NOT_ATTEMPTED'}
    def note(self,state):
        self.stage=state;self.trace.append(state)
        self.b.checkpoint(state)
    def guarded(self,method,*args):
        action=getattr(self.b,method,None)
        require(callable(action),'SUCCESSOR_BACKEND_METHOD_MISSING')
        if method in (
                'stop_worker_bounded','acquire_original_lock_once',
                'backup_existing_exact','publish_two_releases_exact',
                'replace_one_existing_verified','switch_current_verified',
                'restart_resource_bounded','persist_new_worker_attempt_before_start',
                'start_worker_bounded','enable_window_60m',
                'submit_original_intake_once','custody_once_authenticated',
                'close_b5_exposure_success_successor_only',
                'verify_original_archive_identity_and_whole_digest'):
            # Shared action lease serializes admission and the whole bounded
            # call with exclusive revocation. Cleanup stays available.
            with self.b.witness_action():
                return action(*args)
        return action(*args)
    def execute(self):
        """Execute only with an independently authorized backend injected.

        Not invoked by module's main. Authorization is checked by the backend;
        generation alone never activates or reserves a request ID.
        """
        try:
            baselines,sources=self.guarded('get_generator_inputs_verified',self.spec)
            validate_bundle(self.spec,self.bundle,
                verified_baselines=baselines,
                verified_source_blobs=sources)
            # All original queue/custody/receiver/recovery interfaces must be
            # enrolled together before even the witness reservation. A later
            # missing method must never first surface after service stop.
            self.guarded('preflight_original_capabilities')
            self.guarded('preflight_runtime_attachment')
            self.note('PRECONDITIONS')
            self.guarded('verify_activation_admission',self.bundle,self.spec)
            self.guarded('verify_analyst_ack',self.bundle,self.spec)
            self.guarded('reserve_batch_and_targets',self.bundle,self.spec)
            self.note('STOP_ATTEMPT')
            self.worker_stop_attempted=True
            self.guarded('stop_worker_bounded')
            self.guarded('verify_worker_exited')
            # The original worker is proven stopped; no new-worker start attempt
            # has occurred in this transaction. Any later uncertainty overrides it.
            self.worker_start_attempted=False
            self.note('LOCK_ADMISSION')
            self.guarded('acquire_original_lock_once')
            self.locked=True
            self.guarded('check_queue_and_target_conflicts',tuple(x['request_id'] for x in self.bundle['requests']),self.spec)
            self.note('BACKUP')
            validate_bundle(self.spec,self.bundle,
                verified_baselines=baselines,
                verified_source_blobs=sources)
            self.guarded('backup_existing_exact',CONFIGS+SLOTS,tuple(b+'/current' for b in BASES),self.spec)
            self.backup_done=True
            self.note('PUBLISH_SUCCESSOR')
            self.guarded('publish_two_releases_exact',COMMIT,MANIFEST,PIN,self.spec)
            self.note('ACTIVATE_SUCCESSOR')
            # Not cross-file atomic. Each checkpoint must be durable; if any
            # intermediate replacement fails, follow branch-specific recovery.
            for path in CONFIGS+SLOTS:
                self.note('REPLACE_'+path.rsplit('/',1)[-1])
                # Record MAY_HAVE_CHANGED before calling a non-atomic leaf replace.
                # If it fails after a side effect, recovery must recheck identities.
                self.changed.append(path)
                self.guarded('replace_one_existing_verified',path,self.bundle['files'][path],self.spec)
            for base in BASES:
                self.note('CURRENT_'+base.rsplit('/',1)[-1])
                self.changed.append(base+'/current')
                self.guarded('switch_current_verified',base,COMMIT,self.spec)
            self.guarded('persist_activation_identity')
            self.note('RESOURCE_READINESS')
            self.guarded('restart_resource_bounded')
            self.guarded('verify_resource_readiness')
            self.guarded('restore_tunnel_only_if_previously_changed')
            # Activation-readiness is distinct from authority to read B5.
            # Marker is internal ordering only, never approval evidence.
            self.b.activation_committed=True
            self.note('POST_ACTIVATION_B5_AUTH')
            self.guarded('verify_maintenance_window_admission',self.bundle,self.spec)
            self.note('RELEASE_DB_LOCK')
            self.guarded('close_readonly_db')
            self.guarded('release_original_lock')
            self.locked=False
            self.note('NEW_WORKER_START_ATTEMPT')
            # Fail closed if checkpoint uncertain, before any attempt.
            self.worker_start_attempted=None
            self.guarded('persist_new_worker_attempt_before_start')
            self.worker_start_attempted=True
            self.guarded('start_worker_bounded')
            self.guarded('verify_worker_stable')
            self.guarded('attach_original_after_worker_start')
            self.note('ACTIVATED_HOLD_WINDOW')
            # Actual grant/ACK and window approval must be *freshly* rechecked
            # before starting the 60-minute window. No implicit dispatch.
            self.guarded('verify_window_admission',self.bundle,self.spec)
            self.guarded('enable_window_60m',self.bundle)
            self.note('WINDOW_ENABLED')
            return {'state':'WINDOW_ENABLED_NOT_DELIVERED','trace':self.trace[:],
                    'new_requests':0,'received':0,'installation':'NOT_EXECUTED'}
        except BaseException:
            self.fail_closed()
            return {'state':'HOLD_PRESERVE_HISTORY','phase':self.stage,
                    'trace':self.trace[:],'worker_start_attempted':self.worker_start_attempted,
                    'received':0,'installation':'NOT_EXECUTED', 'stop_outcome':self.stop_outcome}
        finally:
            if self.locked:
                try:self.guarded('close_readonly_db')
                except BaseException:pass
                try:self.guarded('release_original_lock')
                except BaseException:pass
                self.locked=False
    def fail_closed(self):
        self.note_failure_safely()
        # Strict: only literal False/False/True proof permits review of precise
        # pre-start backup recovery. None is not False and stays on c53.
        proof=False
        # Re-query a canonical state provider: a missing callback, unexpected
        # value or error must remain UNKNOWN. Never infer known state from a
        # success-looking synthetic queue snapshot.
        try:
            fresh=self.guarded('canonical_state_unknown')
            self.state_unknown=fresh if type(fresh) is bool else True
            proof=self.guarded('prove_no_new_operations_canonically') is True
        except BaseException:
            self.state_unknown=True
            proof=False
        decision=binder.rollback_classification(worker_start_attempted=self.worker_start_attempted,
                         state_unknown=self.state_unknown,no_new_operations_proven=proof)
        if (decision['state']=='PRE_WORKER_RESTORE_MAY_BE_REVIEWED' and self.backup_done):
            try:self.guarded('restore_exact_backups_pre_start_only',tuple(reversed(self.changed)),self.spec)
            except BaseException:
                try:self.stop_outcome=self.guarded('close_b5_exposure_and_stop_c53_fail_closed')
                except BaseException as exc:self.stop_outcome={'state':'UNKNOWN','reason':type(exc).__name__}
        elif self.worker_stop_attempted:
            try:self.stop_outcome=self.guarded('close_b5_exposure_and_stop_c53_fail_closed')
            except BaseException as exc:self.stop_outcome={'state':'UNKNOWN','reason':type(exc).__name__}
        # Pre-admission failures must not stop an otherwise healthy old worker.
    def note_failure_safely(self):
        try:self.b.checkpoint('FAILURE_'+self.stage)
        except BaseException:pass

    def run_19_after_window(self):
        """Second-stage executor: requires existing live window + fresh authority.

        No offline boolean can fake SUCCESS. The backend verifies immutable queue
        receipts and each original InvokeId/nonce/recipient/catalog before returning.
        Custody executes once after the 19 receipts, and reading 19 bodies is a
        distinct later stage through the original connector, not this method.
        """
        require(self.stage=='WINDOW_ENABLED','WINDOW_NOT_ENABLED')
        try:
            self.guarded('verify_window_admission',self.bundle,self.spec)
            self.note('INTEGRITY_CHECK_BEFORE_INTAKE')
            self.guarded('check_fixed_envelope_size_limit',self.bundle,16384)
            self.note('INTAKE_19')
            for request in self.bundle['requests']:
                self.guarded('verify_window_admission',self.bundle,self.spec)
                receipt=self.guarded('submit_original_intake_once',request)
                require(type(receipt) is dict and receipt.get('request_id')==request['request_id'],
                        'INTAKE_RECEIPT_UNKNOWN')
                require(receipt.get('state') in ('PENDING','ACCEPTED'),
                        'INTAKE_REJECTED_FAILED_OR_UNKNOWN')
                # POST is SENT at most. The running original worker, not this
                # POST response, must later write the canonical READY row.
                require(receipt['state']=='PENDING','INTAKE_POST_NOT_PENDING')
            self.note('INTAKE_SENT_AWAITING_READY')
            return {'state':'INTAKE_SENT_AWAITING_READY','submitted':19,
                    'accepted':'NOT_YET_PROVEN','received':0}
        except BaseException:
            try:self.stop_outcome=self.guarded('close_b5_exposure_and_stop_c53_fail_closed')
            except BaseException as exc:self.stop_outcome={'state':'UNKNOWN','reason':type(exc).__name__}
            self.note_failure_safely()
            return {'state':'HOLD_KEEP_HISTORY_NO_REPLAY','received':0,'expected':19,'stop_outcome':self.stop_outcome}

    @staticmethod
    def recover_intake_readonly(backend,bundle):
        """Fresh-process observation from protected reservation/intent records.

        This deliberately does not construct a live Transaction or call its
        action-bearing continuation. Custody and body delivery require a
        separately proven active binding and fresh original authorization.
        """
        require(type(bundle) is dict and type(bundle.get('requests')) is list,
                'RECOVERY_BUNDLE_TYPE')
        return backend.recover_intake_readonly(bundle)

    def resume_recovered_custody(self):
        """One exact continuation after a fresh protected, read-only reconcile.

        Missing/mixed intents, uncertain custody, expired window or missing
        original approval never reaches an action. No path replays a POST.
        """
        require(getattr(self.b,'recovered_from_protected',False) is True and
                self.b.activation_committed is True,
                'RECOVERY_ACTIVATION_NOT_BOUND')
        observed=self.recover_intake_readonly(self.b,self.bundle)
        require(observed.get('state')=='SUCCESS_OBSERVED_READONLY' and
                observed.get('ready_count')==19 and
                observed.get('success_count')==19 and
                observed.get('last_checkpoint') in
                    ('INTAKE_SENT_AWAITING_READY','WAIT_19_SUCCESS'),
                'RECOVERY_CUSTODY_NOT_PROVEN_NO_RETRY')
        self.stage=observed['last_checkpoint']
        # The existing action path rechecks the current witness, both scopes,
        # original Queue receipts and full archive immediately before custody.
        return self.continue_after_original_ready()

    def resume_recovered_b5_http_wait(self):
        """Restore only the waiting phase; neither custody nor POST is retried.

        The protected checkpoint and original Queue must still agree. A later
        close requires separate B5 tool provenance and exact close approval.
        """
        require(getattr(self.b,'recovered_from_protected',False) is True and
                self.b.activation_committed is True,
                'RECOVERY_ACTIVATION_NOT_BOUND')
        observed=self.recover_intake_readonly(self.b,self.bundle)
        require(observed.get('state')=='B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY' and
                observed.get('ready_count')==19 and
                observed.get('success_count')==19 and
                observed.get('last_checkpoint')=='READY_FOR_B5_HTTP_NOT_RECEIVED' and
                observed.get('mutation_allowed') is False,
                'RECOVERY_B5_HTTP_WAIT_NOT_PROVEN')
        self.stage='READY_FOR_B5_HTTP_NOT_RECEIVED'
        return {'state':'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY',
                'received':0,'expected':19,'mutation_allowed':False}

    def continue_after_original_ready(self):
        """Explicit read-only reconciliation; never submits or repeats a POST."""
        require(self.stage in ('INTAKE_SENT_AWAITING_READY','WAIT_19_SUCCESS'),
                'INTAKE_PHASE_NOT_RECOVERED')
        try:
            self.guarded('verify_window_admission',self.bundle,self.spec)
            if self.stage=='INTAKE_SENT_AWAITING_READY':
                for request in self.bundle['requests']:
                    self.guarded('observe_original_intake_ready',request)
                self.note('WAIT_19_SUCCESS')
            count=self.guarded('observe_original_success_progress',
                tuple(x['request_id'] for x in self.bundle['requests']),self.bundle)
            if count<19:
                return {'state':'WAIT_ORIGINAL_SUCCESS_NO_REPOST',
                        'success_count':count,'received':0}
            self.note('CHECK_19_SUCCESS')
            self.guarded('verify_original_success_receipts',tuple(x['request_id'] for x in self.bundle['requests']),
                          self.bundle,self.spec)
            self.note('ONE_CUSTODY')
            self.guarded('verify_original_archive_identity_and_whole_digest',559237632,binder.ARCHIVE_SHA)
            self.guarded('custody_once_authenticated',self.bundle,self.spec)
            self.note('READY_FOR_B5_HTTP_NOT_RECEIVED')
            return {'state':'CUSTODY_COMPLETE_DELIVERY_NOT_PROVEN','received':0,'expected':19}
        except Hold as exc:
            if str(exc) in ('B5_INTAKE_PENDING_OR_UNKNOWN_NO_REPOST',
                            'INTAKE_READY_NOT_PROVEN'):
                return {'state':'WAIT_ORIGINAL_READY_NO_REPOST','received':0,
                        'expected':19}
            try:self.stop_outcome=self.guarded('close_b5_exposure_and_stop_c53_fail_closed')
            except BaseException as close_exc:self.stop_outcome={'state':'UNKNOWN','reason':type(close_exc).__name__}
            self.note_failure_safely()
            return {'state':'HOLD_KEEP_HISTORY_NO_REPLAY','received':0,'expected':19,'stop_outcome':self.stop_outcome}
        except BaseException:
            try:self.stop_outcome=self.guarded('close_b5_exposure_and_stop_c53_fail_closed')
            except BaseException as exc:self.stop_outcome={'state':'UNKNOWN','reason':type(exc).__name__}
            self.note_failure_safely()
            return {'state':'HOLD_KEEP_HISTORY_NO_REPLAY','received':0,'expected':19,'stop_outcome':self.stop_outcome}

    def receive_and_verify_19(self):
        """Maintenance has no analyst bearer or body transport."""
        raise Hold('B5_HTTP_REQUEST_LOCAL_ONLY')

    def close_after_b5_http(self, proof):
        """Requires a trusted B5 tool provenance and a separate close scope.

        A hash or caller-supplied dictionary cannot stand for either receipt.
        Missing original producers remain HOLD without side effects.
        """
        require(self.stage=='READY_FOR_B5_HTTP_NOT_RECEIVED',
                'B5_HTTP_CUSTODY_REQUIRED')
        self.guarded('verify_b5_http_provenance',proof,self.bundle,self.spec)
        self.guarded('approve_precise_b5_exposure_close',self.bundle,self.spec)
        self.guarded('close_b5_exposure_success_successor_only')
        self.note('CLOSED_RECEIVED_19')
        return {'state':'RECEIVED_VERIFIED_19_CLOSED',
                'received':19,'bytes':93592,'installed':False}

    def execute_full(self):
        """Single audited continuation, no silent phase retries or synthetic receipts.

        An authenticated backend must re-check approval, grant and ACK at the
        respective phase. First unknown/failed phase returns HOLD. 19 receipts,
        one custody and receiver bytes are distinct stages.
        """
        activated=self.execute()
        if activated.get('state')!='WINDOW_ENABLED_NOT_DELIVERED':
            return activated
        custody=self.run_19_after_window()
        return custody  # Explicit later reconciliation; never an implicit repost.

def main():
    raise SystemExit('REVIEW_ONLY_BACKEND_NOT_PROVIDED_NO_LIVE_EXECUTION')

if __name__=='__main__': main()
