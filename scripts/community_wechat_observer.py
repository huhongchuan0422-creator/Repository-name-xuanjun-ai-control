"""Original-host, exact-bound applyment4sub GET observation.
Protected policy only; no submission, account grants or business-state writes.
SQLite stays on the serial host thread. Worker receives only a public binding.
"""
import base64,copy,hashlib,json,re,threading,time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from scripts.pr122_customer_core import canonical
from scripts.community_provider_transport import request
from scripts.community_wechat_applyment import (official_signing_url,signed_response_context,
    submission_boundary,consumed_rejection_signatures)
STATES=frozenset(('APPLYMENT_STATE_EDITTING','APPLYMENT_STATE_AUDITING','APPLYMENT_STATE_REJECTED','APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED','APPLYMENT_STATE_SIGNING','APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED'))
TERMINAL=frozenset(('APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED'))
CHANNEL='COMMUNITY_WECHAT_OBSERVATION'
FIELDS=frozenset(('project','owner','application','business_code','applyment_id','provider_merchant','revision','active'))
def need(value,code='BOUND_OBSERVATION_NOT_AUTHORIZED'):
    if not value:raise PermissionError(code)
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def policy(value):
    need(type(value)is dict and set(value)=={'version','enabled','interval_seconds','grants'})
    need(value['version']==1 and type(value['enabled'])is bool)
    need(type(value['interval_seconds'])in (int,float) and 0<value['interval_seconds']<=86400)
    need(type(value['grants'])is dict)
    for key,g in value['grants'].items():
        need(type(g)is dict and set(g)==FIELDS and key==g['application'])
        need(type(g['active'])is bool and type(g['revision'])is int and g['revision']>=1)
        need(all(type(g[k])is str and g[k] for k in FIELDS-{'active','revision'}))
        need(re.fullmatch(r'[A-Za-z0-9_-]{1,64}',g['business_code'])is not None)
        need(re.fullmatch(r'[0-9]{1,32}',g['applyment_id'])is not None)
    return copy.deepcopy(value)
class ApplymentObserver:
    def __init__(self,applyment,policy_loader,*,expected_project):
        self.applyment=applyment;self.onboarding=applyment.onboarding;self.center=applyment.center
        self.reader=applyment.reader;self.load_policy=policy_loader
        need(type(expected_project)is str and bool(expected_project))
        self.expected_project=expected_project;self.current_policy()
        self.thread=threading.get_ident();self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='applyment-get')
        self.pending=None;self.due={};self.closed=False
        from scripts.community_owner_submit_recovery import OwnerSubmissionRecovery
        self.owner_recovery=OwnerSubmissionRecovery(applyment,expected_project)
    def current_policy(self):
        p=policy(self.load_policy())
        need(all(g['project']==self.expected_project for g in p['grants'].values()),'OBSERVATION_ORIGINAL_PROJECT_REQUIRED')
        return p
    def owner_thread(self):need(threading.get_ident()==self.thread,'SERIAL_OWNER_THREAD_REQUIRED')
    def snapshot(self,application):
        self.owner_thread();p=self.current_policy();g=p['grants'].get(application)
        need(p['enabled'] and g is not None and g['active'])
        c=self.center
        a=c.db.execute('SELECT verified,epoch FROM accounts WHERE id=?',(g['owner'],)).fetchone()
        need(a is not None and a[0]==1)
        project=c.db.execute('SELECT active,expires FROM projects WHERE id=?',(g['project'],)).fetchone()
        need(project is not None and project[0]==1 and project[1]>c.now())
        # Protected exact grant supplies independently confirmed project binding;
        # an existing origin, if present, must agree. Never infer from links.project.
        for channel in ('COMMUNITY_ONBOARDING','COMMUNITY_WECHAT_APPLYMENT'):
            bound=c.db.execute('SELECT user_id FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',(channel,application,application)).fetchone()
            need(bound is not None and bound[0]==g['owner'])
        owner,meta,platform=self.onboarding._load(application,g['owner'],False)
        need(owner==g['owner'] and platform['status']!='WITHDRAWN')
        r=self.applyment._read(application)
        from scripts.community_single_restore_realm import realm_compatible
        need(realm_compatible(c,application,g['owner'],meta,r,g['project']))
        need(type(r)is dict and r.get('state')!='SUBMISSION_UNKNOWN')
        need(r.get('business_code')==g['business_code'] and r.get('applyment_id')==g['applyment_id'])
        need(r.get('provider_sp_mchid')==g['provider_merchant']==self.applyment.reader_for_record(r)._mchid)
        # Stored proof comes only from the original verified submission/recovery.
        receipts=list(r.get('submission_receipts',[]))
        if type(r.get('submission_recovery_receipt'))is dict:receipts.append(r['submission_recovery_receipt'])
        need(any(type(x)is dict and x.get('business_code')==g['business_code'] and x.get('applyment_id')==g['applyment_id'] and type(x.get('signed_at'))is int and re.fullmatch('[a-f0-9]{64}',str(x.get('signature_sha256',''))) for x in receipts))
        return {'grant':g,'record':r,'meta':meta,'platform':platform,'account':tuple(a),'project':tuple(project)}
    def stored(self,application):
        self.owner_thread();row=self.center.db.execute("SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1",(CHANNEL,application,application)).fetchone()
        return None if row is None else json.loads(self.center.decrypt(row[0],'wechat-observation:'+application))
    def _matching(self,saved,snapshot):
        return type(saved)is dict and saved.get('binding')==snapshot['grant'] and saved.get('record_digest')==digest(snapshot['record'])
    def prepare(self,application):
        snapshot=self.snapshot(application);saved=self.stored(application)
        state=saved.get('provider_state') if self._matching(saved,snapshot) else snapshot['record'].get('provider_state')
        if state in TERMINAL:return None
        return {'snapshot':snapshot,'previous':saved}
    @staticmethod
    def network(reader,binding):
        # No Center, SQLite, records/materials, request-controlled path or POST.
        need(reader._mchid==binding['provider_merchant'],'OBSERVATION_PROVIDER_READER_MISMATCH')
        return request(reader,'GET','/v3/applyment4sub/applyment/business_code/'+binding['business_code'],include_verification=True)
    def commit(self,prepared,result):
        self.owner_thread();g=prepared['snapshot']['grant'];application=g['application'];c=self.center
        with c.tx():
            current=self.snapshot(application);need(current==prepared['snapshot'],'OBSERVATION_BINDING_CHANGED')
            previous=self.stored(application);need(previous==prepared['previous'],'OBSERVATION_CAS_CHANGED')
            data,response_digest,verification=result;proof=signed_response_context(verification)
            need(data.get('business_code')==g['business_code'] and str(data.get('applyment_id'))==g['applyment_id'],'OBSERVATION_RESPONSE_MISMATCH')
            need(type(data.get('applyment_id'))in (str,int) and type(data.get('applyment_id'))is not bool)
            state=data.get('applyment_state');need(state in STATES,'OBSERVATION_STATE_UNKNOWN')
            r=current['record'];prior=r.get('provider_query_signed_at');oldstate=r.get('provider_state')
            if self._matching(previous,current) and previous.get('provider_query_signed_at',-1)>=(prior if prior is not None else -1):
                prior=previous.get('provider_query_signed_at');oldstate=previous.get('provider_state')
            need(proof['signed_at']>submission_boundary(r) and proof['signature_sha256'] not in consumed_rejection_signatures(r),'OBSERVATION_STALE_RESPONSE')
            need(prior is None or proof['signed_at']>prior or proof['signed_at']==prior and state==oldstate,'OBSERVATION_STALE_RESPONSE')
            need(oldstate not in TERMINAL or state==oldstate,'OBSERVATION_TERMINAL_CONFLICT')
            need(type(response_digest)is str and re.fullmatch('[a-f0-9]{64}',response_digest)is not None)
            saved={'binding':g,'record_digest':digest(r),'provider_state':state,'provider_observed_at':c.now(),'provider_query_signed_at':proof['signed_at'],'provider_query_signature_sha256':proof['signature_sha256'],'provider_response_sha256':response_digest,'sync_error':None,'provider_sign_url':None,'provider_sign_url_proof':None}
            if state=='APPLYMENT_STATE_FINISHED' and data.get('sub_mchid') is not None:
                sub=data['sub_mchid']
                need(type(sub) is str and re.fullmatch('[0-9]{6,32}',sub) is not None,'SIGNED_SUBMERCHANT_REQUIRED')
                saved['merchant_binding']=dict(application=application,owner=g['owner'],project=g['project'],
                    business_code=g['business_code'],applyment_id=g['applyment_id'],
                    platform_revision=current['platform']['revision'],account_epoch=current['account'][1],
                    sub_mchid=sub,record_digest=digest(r),signed_at=proof['signed_at'],
                    signature_sha256=proof['signature_sha256'],response_sha256=response_digest)
            if state in ('APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED') and data.get('sign_url') is not None:
                saved['provider_sign_url']=official_signing_url(data['sign_url'])
                saved['provider_sign_url_proof']={'applyment_id':g['applyment_id'],**proof}
            c.db.execute("INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET user_id=excluded.user_id,payload=excluded.payload,active=1",(CHANNEL,application,g['owner'],application,c.encrypt(canonical(saved),'wechat-observation:'+application)))
            from scripts.community_signing_notices import append as signing_notice
            signing_notice(c,g,saved)
        return self.projection(current,saved)
    def collection_binding(self,application):
        """Server-only signed merchant binding; never a JSAPI/product entitlement."""
        snapshot=self.snapshot(application);saved=self.stored(application)
        if (not self._matching(saved,snapshot) or saved.get('provider_state')!='APPLYMENT_STATE_FINISHED'
                or saved.get('sync_error') is not None):return None
        b=saved.get('merchant_binding')
        if type(b) is not dict:return None
        g=snapshot['grant'];sub=b.get('sub_mchid')
        if type(sub) is not str or re.fullmatch('[0-9]{6,32}',sub) is None:return None
        expected=dict(application=application,owner=g['owner'],project=g['project'],
            business_code=g['business_code'],applyment_id=g['applyment_id'],
            platform_revision=snapshot['platform']['revision'],account_epoch=snapshot['account'][1],
            sub_mchid=sub,record_digest=digest(snapshot['record']),signed_at=saved['provider_query_signed_at'],
            signature_sha256=saved['provider_query_signature_sha256'],response_sha256=saved['provider_response_sha256'])
        return dict(b) if b==expected else None

    def ensure_collection_binding(self,application):
        # Older FINISHED observations intentionally omitted sub_mchid. Read it
        # through the SAME signed GET + snapshot/CAS commit, never patch a DB row.
        with self.center.tx():
            current=self.snapshot(application);previous=self.stored(application)
            existing=self.collection_binding(application)
            if existing is not None:return existing
            need(self._matching(previous,current) and previous.get('provider_state')=='APPLYMENT_STATE_FINISHED'
                 and previous.get('sync_error') is None,'CURRENT_FINISHED_MERCHANT_REQUIRED')
            prepared={'snapshot':current,'previous':previous}
        result=self.network(self.applyment.reader_for_record(current['record']),current['grant'])
        self.commit(prepared,result)
        with self.center.tx():
            binding=self.collection_binding(application)
            need(binding is not None,'SIGNED_SUBMERCHANT_REQUIRED')
            return binding

    def failed(self,prepared):
        self.owner_thread();g=prepared['snapshot']['grant'];app=g['application'];c=self.center
        with c.tx():
            current=self.snapshot(app);need(current==prepared['snapshot'],'OBSERVATION_BINDING_CHANGED')
            previous=self.stored(app);need(previous==prepared['previous'],'OBSERVATION_CAS_CHANGED')
            if self._matching(previous,current):saved=copy.deepcopy(previous)
            else:
                r=current['record'];saved={'binding':g,'record_digest':digest(r)}
                for key in ('provider_state','provider_observed_at','provider_query_signed_at','provider_query_signature_sha256','provider_response_sha256','provider_sign_url','provider_sign_url_proof'):
                    saved[key]=r.get(key)
            saved.update(sync_error='PROVIDER_OBSERVATION_UNAVAILABLE',sync_error_at=c.now())
            c.db.execute("INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET user_id=excluded.user_id,payload=excluded.payload,active=1",(CHANNEL,app,g['owner'],app,c.encrypt(canonical(saved),'wechat-observation:'+app)))

    @staticmethod
    def qr_available(source,applyment_id):
        proof=source.get('provider_sign_url_proof')
        if (source.get('provider_state') not in ('APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED')
                or type(proof)is not dict or proof.get('applyment_id')!=applyment_id
                or proof.get('signed_at')!=source.get('provider_query_signed_at')
                or proof.get('signature_sha256')!=source.get('provider_query_signature_sha256')):return False
        try:official_signing_url(source.get('provider_sign_url'))
        except (ValueError,TypeError):return False
        return True

    def projection(self,snapshot,saved):
        r=snapshot['record'];g=snapshot['grant'];source=saved if self._matching(saved,snapshot) else r
        return {'application':g['application'],'applyment_id':g['applyment_id'],'provider_state':source.get('provider_state','UNKNOWN'),'provider_observed_at':source.get('provider_observed_at'),'provider_query_signed_at':source.get('provider_query_signed_at'),'sync_error':source.get('sync_error'),'sync_error_at':source.get('sync_error_at'),'qr_available':self.qr_available(source,g['applyment_id']),'provider_workflow':{'scope':'SIGNED_PROVIDER_OBSERVATION','payment_enabled':False},'payment_enabled':False}
    def read(self,session,csrf,application,qr=False,expected_project=None):
        self.owner_thread();uid=self.center.session(session,csrf)
        # Exact protected project/application/owner binding BEFORE any application read.
        # No ROOT/reviewer shortcut and no read-then-reject on another project.
        p=self.current_policy();g=p['grants'].get(application)
        need(p['enabled'] and g is not None and g['active'] and g['owner']==uid)
        need(expected_project is None or g['project']==expected_project,'APPLICANT_PROJECT_MISMATCH')
        snapshot=self.snapshot(application);need(snapshot['grant']==g)
        with self.center.tx():self.center.limit('wechat-applyment:'+uid,20,60)
        saved=self.stored(application);out=self.projection(snapshot,saved)
        if qr:
            source=saved if self._matching(saved,snapshot) else snapshot['record'];proof=source.get('provider_sign_url_proof')
            need(out['provider_state'] in ('APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED') and type(proof)is dict,'VERIFIED_PROVIDER_SIGN_URL_REQUIRED')
            need(proof.get('applyment_id')==out['applyment_id'] and proof.get('signed_at')==source.get('provider_query_signed_at') and proof.get('signature_sha256')==source.get('provider_query_signature_sha256'),'VERIFIED_PROVIDER_SIGN_URL_REQUIRED')
            url=official_signing_url(source.get('provider_sign_url'))
            import qrcode
            from qrcode.image.svg import SvgPathImage
            image=qrcode.make(url,image_factory=SvgPathImage,box_size=8,border=4);buf=BytesIO();image.save(buf)
            out.update(svg_data='data:image/svg+xml;base64,'+base64.b64encode(buf.getvalue()).decode(),url_sha256=hashlib.sha256(url.encode()).hexdigest())
            from qrcode.image.pil import PilImage
            png=BytesIO();qrcode.make(url,image_factory=PilImage,box_size=8,border=4).save(png,format='PNG')
            out.update(png_data='data:image/png;base64,'+base64.b64encode(png.getvalue()).decode())
        return out
    def display_record(self,application,record):
        # Caller already has original read/reviewer permission. Never expose binding.
        try:s=self.snapshot(application);saved=self.stored(application)
        except (PermissionError,ValueError):
            status=getattr(self.load_policy,'status',None)
            reason=status(application) if status is not None else None
            if reason in (None,'NOT_SUBMITTED'):return record
            result=copy.deepcopy(record);result['sync_error']='DISCOVERY_'+reason;result['provider_sync_error']='DISCOVERY_'+reason
            return result
        if not self._matching(saved,s):return record
        result=copy.deepcopy(record)
        for k in ('provider_state','provider_observed_at','provider_query_signed_at','provider_query_signature_sha256','provider_response_sha256','provider_sign_url','provider_sign_url_proof','sync_error','sync_error_at'):
            result[k]=saved.get(k)
        result['provider_sync_error']=saved.get('sync_error')
        result['provider_sync_error_at']=saved.get('sync_error_at')
        return result
    def service_actions(self):
        self.owner_thread()
        if self.closed:return
        self.owner_recovery.service_actions()
        if self.pending is not None:
            prepared,future=self.pending
            if not future.done():return
            self.pending=None;app=prepared['snapshot']['grant']['application']
            try:self.commit(prepared,future.result())
            except Exception:
                try:self.failed(prepared)
                except Exception:pass # Revoked/CAS failures never write or log raw data.
            try:interval=self.current_policy()['interval_seconds']
            except Exception:interval=60
            self.due[app]=time.monotonic()+interval
        try:p=self.current_policy()
        except Exception:return
        if not p['enabled']:return
        for app in p['grants']:
            if self.due.get(app,0)>time.monotonic():continue
            try:prepared=self.prepare(app)
            except Exception:
                self.due[app]=time.monotonic()+p['interval_seconds'];continue
            if prepared is None:continue
            binding=copy.deepcopy(prepared['snapshot']['grant'])
            self.pending=(prepared,self.worker.submit(self.network,self.applyment.reader_for_record(prepared['snapshot']['record']),binding));break
    def close(self):
        self.owner_thread();self.closed=True
        self.owner_recovery.close()
        if self.pending:self.pending[1].cancel()
        self.worker.shutdown(wait=True,cancel_futures=True);self.pending=None
