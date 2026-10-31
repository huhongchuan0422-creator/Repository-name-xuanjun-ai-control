"""Private, append-only revision requests; no automatic billing or execution."""
import json
import re
import secrets
import html
import os
import sqlite3
import stat
from scripts.pr122_customer_core import canonical, digest, safe_text, identifier, Denied, Conflict
from scripts.pr122_customer_change_authority import preview, document, load


class Changes:
    def __init__(self, center):self.c=center

    @staticmethod
    def canonical_task(db_path, project, task_id, policy):
        """Read one existing task from the canonical registry; never create it."""
        project=identifier(project);task_id=identifier(task_id)
        required_policy={'task_id','attempt_id','spec_sha256','owner','writer_scope','authority_caller_id','board_id'}
        if (type(db_path) is not str or not db_path.startswith('/') or
                type(policy) is not dict or set(policy)!=required_policy or
                any(type(policy[k]) is not str or not policy[k] for k in required_policy) or
                identifier(policy['task_id'])!=task_id or
                not re.fullmatch(r'[0-9a-f]{64}',policy['spec_sha256'])):
            raise Denied('TASK_REGISTRY_CONFIG')
        path=os.path.realpath(db_path)
        parent=os.path.dirname(path)
        flags=os.O_RDONLY|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
        try:
            parent_fd=os.open(parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0))
            fd=os.open(os.path.basename(path),flags,dir_fd=parent_fd)
        except OSError as exc:
            raise Denied('TASK_REGISTRY_UNAVAILABLE') from exc
        file_stat=os.fstat(fd);parent_stat=os.fstat(parent_fd)
        runtime_ids={os.getegid(),*os.getgroups()}
        try:
            with open('/proc/self/status',encoding='ascii') as source:status=source.read()
            capabilities=int(re.search(r'^CapEff:\s*([0-9a-fA-F]+)$',status,re.M).group(1),16)
        except (OSError,AttributeError,ValueError) as exc:
            os.close(fd);os.close(parent_fd)
            raise Denied('TASK_REGISTRY_RUNTIME_IDENTITY') from exc
        fd_path='/proc/self/fd/'+str(fd);parent_fd_path='/proc/self/fd/'+str(parent_fd)
        if (path!=db_path or not stat.S_ISREG(file_stat.st_mode) or
                os.geteuid()==0 or capabilities!=0 or
                file_stat.st_uid==os.geteuid() or parent_stat.st_uid==os.geteuid() or
                file_stat.st_gid in runtime_ids or parent_stat.st_gid in runtime_ids or
                os.access(fd_path,os.W_OK,effective_ids=True) or
                os.access(parent_fd_path,os.W_OK,effective_ids=True)):
            os.close(fd);os.close(parent_fd)
            raise Denied('TASK_REGISTRY_NOT_READ_ONLY')
        for suffix in ('-wal','-journal'):
            try:os.stat(os.path.basename(path)+suffix,dir_fd=parent_fd,follow_symlinks=False)
            except FileNotFoundError:continue
            except OSError as exc:
                os.close(fd);os.close(parent_fd);raise Denied('TASK_REGISTRY_UNAVAILABLE') from exc
            os.close(fd);os.close(parent_fd);raise Denied('TASK_REGISTRY_NOT_CHECKPOINTED')
        try:db=sqlite3.connect('file:'+fd_path+'?mode=ro&immutable=1',uri=True,timeout=2)
        except sqlite3.Error as exc:
            os.close(fd);os.close(parent_fd);raise Denied('TASK_REGISTRY_UNAVAILABLE') from exc
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA schema_version').fetchone()
            sqlite_fds=[]
            for value in os.listdir('/proc/self/fd'):
                try:opened_by_sqlite=os.fstat(int(value))
                except (OSError,ValueError):continue
                if (int(value)!=fd and
                        (opened_by_sqlite.st_dev,opened_by_sqlite.st_ino)==(file_stat.st_dev,file_stat.st_ino)):
                    sqlite_fds.append(int(value))
            if not sqlite_fds:raise Denied('TASK_REGISTRY_DESCRIPTOR_BINDING')
            opened=os.stat(fd_path)
            if (opened.st_dev,opened.st_ino)!=(file_stat.st_dev,file_stat.st_ino):
                raise Denied('TASK_REGISTRY_CHANGED')
            tables={row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'tasks','gateway_task_metadata'}<=tables:
                raise Denied('TASK_REGISTRY_SCHEMA')
            task_columns={row[1] for row in db.execute('PRAGMA table_info(tasks)')}
            meta_columns={row[1] for row in db.execute('PRAGMA table_info(gateway_task_metadata)')}
            if not {'authority_caller_id'}<=task_columns or not {'tenant_id','requester_principal_id'}<=meta_columns:
                raise Denied('TASK_REGISTRY_IDENTITY_SCHEMA')
            row=db.execute('''SELECT t.task_id,t.state,t.attempt_id,
                t.spec_sha256,t.writer_scope,t.owner,t.authority_caller_id,
                m.project_id,m.board_id,m.tenant_id,m.requester_principal_id
                FROM tasks t JOIN gateway_task_metadata m
                ON m.task_id=t.task_id WHERE t.task_id=? AND m.project_id=?''',
                (task_id,project)).fetchone()
            if row is None:raise Denied('CANONICAL_TASK_NOT_FOUND')
            record=dict(row)
            if (record['state'] not in {'READY','RECEIVED','STARTED','RUNNING','HANDOFF_PENDING'} or
                    any(type(record[k]) is not str or not record[k] or record[k]=='UNKNOWN'
                        for k in ('attempt_id','spec_sha256','writer_scope','owner','authority_caller_id','tenant_id','requester_principal_id')) or
                    not re.fullmatch(r'[0-9a-f]{64}',record['spec_sha256']) or
                    any(record[k]!=policy[k] for k in required_policy)):
                raise Denied('CANONICAL_TASK_NOT_EXECUTABLE')
            opened=os.stat(fd_path)
            if (opened.st_dev,opened.st_ino)!=(file_stat.st_dev,file_stat.st_ino):
                raise Denied('TASK_REGISTRY_CHANGED')
            for sqlite_fd in sqlite_fds:
                current=os.fstat(sqlite_fd)
                if (current.st_dev,current.st_ino)!=(file_stat.st_dev,file_stat.st_ino):
                    raise Denied('TASK_REGISTRY_CHANGED')
            record['registry_record_sha256']=digest(canonical(record))
            record['registry']='CANONICAL_TASK_REGISTRY'
            return record
        except sqlite3.Error as exc:
            raise Denied('TASK_REGISTRY_UNAVAILABLE') from exc
        finally:
            db.close();os.close(fd);os.close(parent_fd)

    def _canonical_task(self, project, task_id):
        if self.c.task_registry_context is None:
            raise Denied('TASK_REGISTRY_NOT_CONFIGURED')
        record=self.c.task_registry_context(project,task_id)
        if type(record) is not dict or record.get('task_id')!=task_id or record.get('project_id')!=project:
            raise Denied('CANONICAL_TASK_BINDING')
        return record

    def _review_identity(self, uid, project):
        """Return the existing explicitly confirmed PR122/Task-Center subject."""
        from scripts.pr122_customer_identity import verified_mapping
        p,_,_=self.c.project(uid,project,{'OWNER'})
        row=self.c.db.execute('''SELECT * FROM identity_mappings
            WHERE user_id=? AND tenant_id=? AND project_id=?''',(uid,p['tenant'],project)).fetchone()
        if (row is None or row['status']!='ACTIVE' or row['expires']<=self.c.now() or
                row['authority_revision']!=p['revision']):
            raise Denied('CROSS_SERVICE_IDENTITY_MAPPING_UNAVAILABLE')
        value=verified_mapping(self.c,row)
        return {'tenant_id':p['tenant'],'requester_principal_id':value['domestic_customer_id'],
                'mapping_id':row['id'],'mapping_version':row['version'],
                'authority_revision':p['revision']}

    def review_approval_capability(self, uid, project):
        try:self._review_identity(uid,project)
        except Denied:return {'enabled':False,'reason':'CROSS_SERVICE_IDENTITY_MAPPING_UNAVAILABLE'}
        return {'enabled':False,'reason':'TASK_REGISTRY_REQUESTER_PRINCIPAL_NOT_AVAILABLE'}

    def _request_sha(self,events):return digest(canonical({'event_id':events[0]['id'],'payload':events[0]['payload']}))

    def _events(self, uid, project, case):
        if not self.c.db.in_transaction:
            with self.c.tx():return self._events(uid,project,case)
        self.c.project(uid,project)
        rows=self.c.db.execute('SELECT * FROM change_events WHERE project=? AND case_id=? ORDER BY seq',(project,identifier(case))).fetchall()
        if not rows:raise Denied('CHANGE_NOT_FOUND')
        result=[];parent='0'*64
        for r in rows:
            event={**dict(r),'payload':json.loads(self.c.decrypt(r['payload'],r['id']))}
            event['payload_sha256']=digest(canonical(event['payload']))
            proof={k:event[k] for k in ('id','project','case_id','seq','kind','actor','created','payload_sha256')}
            proof['parent_sha256']=parent;parent=digest(canonical(proof))
            event['credential']={**proof,'sha256':parent,'anchor_state':'LOCAL_ONLY','on_chain':False}
            result.append(event)
        self.c.audit(project,uid,'CHANGE_HISTORY_READ',case)
        return result

    def _append(self, uid, project, case, revision, kind, payload,guard=None,submit_key=None):
        with self.c.tx():
            self.c.project(uid,project)
            if guard:guard()
            if submit_key is not None:
                # BEGIN IMMEDIATE in Center.tx serializes competing requests.
                # The original change_events table remains the only source of truth.
                for row in self.c.db.execute(
                    "SELECT id,case_id,seq,payload FROM change_events WHERE project=? AND actor=? AND kind='REQUEST'",
                    (project,uid)):
                    prior=json.loads(self.c.decrypt(row['payload'],row['id']))
                    if prior.get('idempotency_key')!=submit_key:continue
                    if prior.get('request_sha256')!=payload['request_sha256']:
                        raise Conflict('IDEMPOTENCY_KEY_REUSED')
                    return {'id':row['case_id'],'revision':row['seq'],'event_id':row['id'],**prior}
                # Charge quota only for the first committed logical request.
                self.c.limit('change-submit:'+uid+':'+project,30,300)
            latest=self.c.db.execute('SELECT MAX(seq) FROM change_events WHERE project=? AND case_id=?',(project,case)).fetchone()[0] or 0
            if type(revision) is not int or revision!=latest:raise Conflict('CHANGE_REVISION')
            eid='ce_'+secrets.token_hex(16);seq=revision+1
            self.c.db.execute('INSERT INTO change_events VALUES(?,?,?,?,?,?,?,?)',(eid,project,case,seq,kind,uid,self.c.encrypt(canonical(payload),eid),self.c.now()))
            self.c.audit(project,uid,'CHANGE_'+kind,eid)
        return {'id':case,'revision':seq,'event_id':eid,**payload}

    def _page(self, page, version):
        if type(page) is not str or not re.fullmatch(r'/[A-Za-z0-9/_\-.]{1,300}',page) or '..' in page:raise ValueError('PAGE_PATH')
        if type(version) is not str or not re.fullmatch(r'[0-9a-f]{64}',version):raise ValueError('PAGE_VERSION_SHA256')

    def _preview(self, uid, project, page, version):
        self._page(page,version)
        return preview(self.c,uid,project,page,version)

    def baseline(self, uid, project, page, version, document_id):
        self.c.project(uid,project,{'OWNER'});self._page(page,version)
        bound=self._preview(uid,project,page,version)
        doc=document(self.c,uid,project,document_id,page,version)
        if doc['kind'] not in ('CONTRACT','REQUIREMENTS','ACCEPTED_VERSION'):raise Denied('ORIGINAL_CONTRACT_DOCUMENT_REQUIRED')
        self.c.limit('change-baseline:'+uid+':'+project,20,3600)
        def guard():
            if self._preview(uid,project,page,version)!=bound or document(self.c,uid,project,document_id,page,version)!=doc:raise Conflict('AUTHORITY_CHANGED')
        return self._append(uid,project,'baseline_'+secrets.token_hex(12),0,'BASELINE',{'page':page,'page_sha256':version,'document_id':doc['id'],'document_sha256':doc['document_sha256'],'version_sha256':doc['version_sha256'],'confirmed_requirement':doc['text'],'confirmed_by':doc['confirmed_by'],'confirmed_at':doc['confirmed_at'],'source_ref':doc['source_ref'],'preview':bound,'state':'CANONICAL_BASELINE_SELECTED'},guard)

    def submit(self, uid, project, page, version, text, intent='RECTIFICATION', idempotency_key=None):
        self.c.project(uid,project,{'OWNER'});bound=self._preview(uid,project,page,version)
        if intent not in ('RECTIFICATION','NEW_ORDER'):raise ValueError('REQUEST_INTENT')
        if idempotency_key is None:
            # Exact legacy ordering: valid identity/authority and intent consume
            # the original quota before request text validation.
            self.c.limit('change-submit:'+uid+':'+project,30,300)
            request=safe_text(text)
            def guard():
                if self._preview(uid,project,page,version)!=bound:raise Conflict('AUTHORITY_CHANGED')
            payload={'page':page,'page_sha256':version,'preview':bound,'request':request,'intent':intent,'state':'REQUESTED'}
            return self._append(uid,project,'change_'+secrets.token_hex(12),0,'REQUEST',payload,guard)
        if type(idempotency_key) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',idempotency_key):
            raise ValueError('INVALID_IDEMPOTENCY_KEY')
        request=safe_text(text)
        def guard():
            if self._preview(uid,project,page,version)!=bound:raise Conflict('AUTHORITY_CHANGED')
        payload={'page':page,'page_sha256':version,'preview':bound,'request':request,'intent':intent,'state':'REQUESTED','idempotency_key':idempotency_key}
        payload['request_sha256']=digest(canonical({'page':page,'version':version,'request':request,'intent':intent}))
        return self._append(uid,project,'change_'+secrets.token_hex(12),0,'REQUEST',payload,guard,idempotency_key)

    def confirm_new_scope(self, uid, project, case, revision, document_id):
        self.c.project(uid,project,{'OWNER'});events=self._events(uid,project,case);request=events[0]['payload']
        if events[0]['kind']!='REQUEST' or request.get('intent')!='NEW_ORDER' or events[-1]['payload']['state'] not in ('REQUESTED','NEEDS_EVIDENCE'):raise Denied('SEPARATE_CUSTOMER_NEW_ORDER_REQUIRED')
        self._preview(uid,project,request['page'],request['page_sha256'])
        doc=document(self.c,uid,project,document_id,request['page'],request['page_sha256'])
        if doc['kind']!='NEW_ORDER' or doc['request_sha256']!=self._request_sha(events) or doc['text']!=request['request'] or doc['confirmed_by']!=uid or doc['confirmed_at']<events[0]['created']:raise Denied('EXACT_CUSTOMER_NEW_REQUIREMENT_REQUIRED')
        def guard():
            self._preview(uid,project,request['page'],request['page_sha256'])
            if document(self.c,uid,project,document_id,request['page'],request['page_sha256'])!=doc:raise Conflict('AUTHORITY_CHANGED')
        return self._append(uid,project,case,revision,'NEW_SCOPE_CONFIRM',{'state':'NEW_REQUIREMENT_CONFIRMED','page':request['page'],'page_sha256':request['page_sha256'],'document_id':doc['id'],'document_sha256':doc['document_sha256'],'version_sha256':doc['version_sha256'],'request_sha256':self._request_sha(events)},guard)

    def preview_footer(self, uid, project, page, version):
        """For the authorized private-preview renderer, never a public catalog."""
        self.c.project(uid,project,{'OWNER'});self._preview(uid,project,page,version)
        return '<section data-project-feedback="'+html.escape(project,quote=True)+'" data-page-path="'+html.escape(page,quote=True)+'" data-page-sha256="'+version+'"></section><script src="/customer/center/feedback.js" defer></script>'

    def review_status(self, uid, project, page, version):
        """Durable design review for one exact page version; comments are separate."""
        self.c.project(uid,project,{'OWNER'});self._preview(uid,project,page,version)
        case='review_'+digest(canonical({'project':project,'page':page,'version':version}))[:40]
        events=[]
        for row in self.c.db.execute(
                'SELECT * FROM change_events WHERE project=? AND case_id=? ORDER BY seq',
                (project,case)):
            events.append({'id':row['id'],'seq':row['seq'],'kind':row['kind'],
                'actor':row['actor'],'created':row['created'],
                'payload':json.loads(self.c.decrypt(row['payload'],row['id']))})
        comments=[]
        for row in self.c.db.execute(
                "SELECT id,case_id,actor,payload,created FROM change_events WHERE project=? AND kind='REQUEST' ORDER BY rowid",
                (project,)):
            payload=json.loads(self.c.decrypt(row['payload'],row['id']))
            if payload.get('page')==page and payload.get('page_sha256')==version:
                comments.append({'id':row['id'],'case_id':row['case_id'],
                    'actor':row['actor'],'created':row['created'],
                    'text':payload['request'],'intent':payload['intent']})
        last=events[-1] if events else None
        receipt=None
        if last and last['kind']=='DESIGN_APPROVAL':
            receipt={'event_id':last['id'],'task_id':last['payload']['task_id'],
                'task_registry_record_sha256':last['payload']['task_registry']['registry_record_sha256'],
                'record_sha256':digest(canonical(last['payload']))}
        return {'project':project,'page':page,'page_sha256':version,
            'state':last['payload']['state'] if last else 'PENDING_REVIEW',
            'comment_count':len(comments),'comments':comments,'events':events,
            'approval_receipt':receipt,
            'meaning':'DESIGN_APPROVAL_ONLY_NOT_QA_RELEASE_OR_ACCEPTANCE'}

    def approve_reviewed_version(self, uid, project, page, version, task_id, reason):
        self.c.project(uid,project,{'OWNER'});bound=self._preview(uid,project,page,version)
        identity=self._review_identity(uid,project)
        task_id=identifier(task_id);task=self._canonical_task(project,task_id)
        if (task.get('tenant_id')!=identity['tenant_id'] or
                task.get('requester_principal_id')!=identity['requester_principal_id']):
            raise Denied('CROSS_SERVICE_IDENTITY_BINDING')
        status=self.review_status(uid,project,page,version)
        if status['state']=='DESIGN_APPROVED_TASK_BOUND':
            if status['approval_receipt']['task_id']!=task_id:raise Conflict('REVIEW_TASK_CONFLICT')
            return status
        case='review_'+digest(canonical({'project':project,'page':page,'version':version}))[:40]
        def guard():
            if self._preview(uid,project,page,version)!=bound:raise Conflict('AUTHORITY_CHANGED')
            if self._review_identity(uid,project)!=identity:raise Conflict('IDENTITY_MAPPING_CHANGED')
            if self._canonical_task(project,task_id)!=task:raise Conflict('TASK_REGISTRY_CHANGED')
        self._append(uid,project,case,0,'DESIGN_APPROVAL',
            {'state':'DESIGN_APPROVED_TASK_BOUND','page':page,'page_sha256':version,
             'preview':bound,'reason':safe_text(reason),'design_approval':True,
             'task_id':task_id,'task_registry':task,
             'identity_binding':{'tenant_id':identity['tenant_id'],'mapping_id':identity['mapping_id'],
                'mapping_version':identity['mapping_version'],'authority_revision':identity['authority_revision'],
                'requester_principal_sha256':digest(identity['requester_principal_id'].encode())},
             'technical_qa':False,'release_approval':False,
             'business_acceptance':False},guard)
        return self.review_status(uid,project,page,version)

    def _evidence(self, uid, project, events, category, evidence):
        request=events[0];r=request['payload'];p,_,_=self.c.project(uid,project)
        self._preview(p['owner'],project,r['page'],r['page_sha256'])
        checked=[]
        for eid in evidence:
            record=self.c.db.execute('SELECT rowid AS event_order,* FROM change_events WHERE id=? AND project=?',(identifier(eid),project)).fetchone()
            if not record or record['kind'] not in ('BASELINE','NEW_SCOPE_CONFIRM'):raise Denied('CANONICAL_EVIDENCE_REQUIRED')
            payload=json.loads(self.c.decrypt(record['payload'],record['id']))
            if not payload.get('document_id'):raise Denied('LEGACY_TEXT_IS_NOT_CONTRACT_EVIDENCE')
            doc=document(self.c,uid,project,payload['document_id'],r['page'],r['page_sha256'])
            if payload.get('document_sha256')!=doc['document_sha256'] or payload.get('version_sha256')!=doc['version_sha256']:raise Denied('EVIDENCE_DOCUMENT_DRIFT')
            if record['actor']!=doc['confirmed_by'] or payload.get('page')!=r['page'] or payload.get('page_sha256')!=r['page_sha256']:raise Denied('EVIDENCE_IDENTITY')
            if category=='CLIENT_CHANGE':
                request_order=self.c.db.execute('SELECT rowid FROM change_events WHERE id=?',(request['id'],)).fetchone()[0]
                if record['kind']!='BASELINE' or doc['kind'] not in ('CONTRACT','REQUIREMENTS','ACCEPTED_VERSION') or record['event_order']>=request_order or doc['confirmed_at']>request['created']:raise Denied('PRIOR_CONTRACT_EVIDENCE_REQUIRED')
            elif category=='NEW_SCOPE':
                if r.get('intent')!='NEW_ORDER' or record['kind']!='NEW_SCOPE_CONFIRM' or record['case_id']!=request['case_id'] or doc['kind']!='NEW_ORDER' or doc['request_sha256']!=self._request_sha(events) or payload.get('request_sha256')!=doc['request_sha256'] or doc['text']!=r['request']:raise Denied('SEPARATE_NEW_REQUIREMENT_REQUIRED')
            checked.append({'event_id':record['id'],'actor':doc['confirmed_by'],'confirmed_at':doc['confirmed_at'],'sha256':digest(canonical(payload)),'document_id':doc['id'],'document_sha256':doc['document_sha256'],'version_sha256':doc['version_sha256'],'source_ref':doc['source_ref'],'requirement':doc['text']})
        return checked

    def assess(self, uid, project, case, revision, category, minutes, lines, evidence, explanation):
        self.c.project(uid,project,{'REVIEWER'});events=self._events(uid,project,case)
        if events[0]['kind']!='REQUEST' or events[-1]['payload']['state'] not in ('REQUESTED','NEEDS_EVIDENCE','NEW_REQUIREMENT_CONFIRMED','QUOTED','FREE_APPROVED','DISPUTED'):raise Conflict('ASSESSMENT_STATE')
        if category not in ('PROVIDER_DEFECT','IN_SCOPE_SMALL','CLIENT_CHANGE','NEW_SCOPE','UNKNOWN'):raise ValueError('CHANGE_CATEGORY')
        if type(minutes) is not int or not 0<=minutes<=10000000:raise ValueError('ESTIMATE_REQUIRED')
        if type(lines) is not list or len(lines)>50 or type(evidence) is not list or len(evidence)>20:raise ValueError('ASSESSMENT_SIZE')
        for line in lines:
            if type(line) is not dict or set(line)!={'description','cny_minor','usd_minor'}:raise ValueError('QUOTE_LINE')
            safe_text(line['description'],200)
            if any(type(line[k]) is not int or not 0<=line[k]<=1000000000 for k in ('cny_minor','usd_minor')):raise ValueError('DUAL_PRICE_REQUIRED')
        # Free fixes need current authorization, never historical contract retrieval.
        if category in ('PROVIDER_DEFECT','IN_SCOPE_SMALL'):
            if evidence:raise ValueError('FREE_FIX_DOES_NOT_REQUIRE_CONTRACT_LOOKUP')
            p,_,_=self.c.project(uid,project);r=events[0]['payload']
            self._preview(p['owner'],project,r['page'],r['page_sha256']);checked=[]
        else:checked=self._evidence(uid,project,events,category,evidence)
        cny=sum(x['cny_minor'] for x in lines);usd=sum(x['usd_minor'] for x in lines)
        if category in ('PROVIDER_DEFECT','IN_SCOPE_SMALL') and (cny or usd):raise Denied('INCLUDED_FIX_MUST_BE_FREE')
        if category in ('CLIENT_CHANGE','NEW_SCOPE') and not checked:state='NEEDS_EVIDENCE';lines=[];cny=usd=0
        elif category=='UNKNOWN':state='NEEDS_EVIDENCE';lines=[];cny=usd=0
        elif category in ('PROVIDER_DEFECT','IN_SCOPE_SMALL'):state='FREE_APPROVED'
        else:
            if not lines:raise ValueError('ITEMIZED_QUOTE_REQUIRED')
            state='QUOTED'
        payload={'state':state,'category':category,'estimated_minutes':minutes,'lines':lines,'totals':None if state=='NEEDS_EVIDENCE' else {'cny_minor':cny,'usd_minor':usd},'evidence':checked,'explanation':safe_text(explanation),'automatic_charge':False,'automatic_execution':False}
        def guard():
            if category in ('PROVIDER_DEFECT','IN_SCOPE_SMALL'):
                p,_,_=self.c.project(uid,project);r=events[0]['payload'];self._preview(p['owner'],project,r['page'],r['page_sha256'])
            elif self._evidence(uid,project,events,category,evidence)!=checked:raise Conflict('AUTHORITY_CHANGED')
        return self._append(uid,project,case,revision,'ASSESSMENT',payload,guard)

    def respond(self, uid, project, case, revision, action, reason):
        self.c.project(uid,project,{'OWNER'});events=self._events(uid,project,case);last=events[-1]
        if last['kind']!='ASSESSMENT' or last['payload']['state'] not in ('QUOTED','FREE_APPROVED'):raise Conflict('QUOTE_REQUIRED')
        if action not in ('CONFIRM','DISPUTE'):raise ValueError('CUSTOMER_ACTION')
        if action=='CONFIRM':
            a=last['payload'];checked=self._evidence(uid,project,events,a['category'],[x['event_id'] for x in a['evidence']])
            if a['category'] in ('CLIENT_CHANGE','NEW_SCOPE') and (not checked or checked!=a['evidence']):raise Denied('CURRENT_CANONICAL_EVIDENCE_REQUIRED')
        def guard():
            if action=='CONFIRM' and self._evidence(uid,project,events,last['payload']['category'],[x['event_id'] for x in last['payload']['evidence']])!=last['payload']['evidence']:raise Conflict('AUTHORITY_CHANGED')
        return self._append(uid,project,case,revision,'CUSTOMER_RESPONSE',{'state':'CUSTOMER_CONFIRMED' if action=='CONFIRM' else 'DISPUTED','assessment_event_id':last['id'],'assessment_sha256':digest(canonical(last['payload'])),'reason':safe_text(reason),'automatic_charge':False,'automatic_execution':False},guard)

    def list(self, uid, project):
        self.c.project(uid,project)
        cases=[r[0] for r in self.c.db.execute('SELECT DISTINCT case_id FROM change_events WHERE project=?',(project,))]
        return {'project':project,'cases':[{'id':case,'events':self._events(uid,project,case)} for case in cases]}

    def page_updates(self, uid, project, page, version):
        self.c.project(uid,project,{'OWNER'});self._preview(uid,project,page,version)
        result=[]
        for record in load(self.c).get('deliveries',[]):
            if record['project']!=project or record['page']!=page or record['after_sha256']!=version:continue
            events=self._events(uid,project,record['case']);last=events[-1]
            delivery_sha=digest(canonical(record))
            confirmed=last['kind']=='RETEST' and last['payload'].get('delivery_sha256')==delivery_sha and last['payload']['state']=='RETEST_ACCEPTED'
            result.append({**record,'revision':last['seq'],'delivery_sha256':delivery_sha,'state':'RETEST_ACCEPTED' if confirmed else 'AWAIT_RETEST','label':'已按您的建议调整，并已确认通过' if confirmed else '已按您的建议调整，待您复验'})
        return {'updates':result}

    def retest(self, uid, project, case, revision, page, version, delivery_sha256, action, reason):
        if action not in ('ACCEPT','FEEDBACK'):raise ValueError('RETEST_ACTION')
        def current():
            records=self.page_updates(uid,project,page,version)['updates']
            match=next((r for r in records if r['case']==case and r['delivery_sha256']==delivery_sha256),None)
            if not match or match['state']!='AWAIT_RETEST':raise Denied('CURRENT_DELIVERY_REQUIRED')
        current()
        return self._append(uid,project,case,revision,'RETEST',{'state':'RETEST_ACCEPTED' if action=='ACCEPT' else 'RETEST_FEEDBACK','delivery_sha256':delivery_sha256,'page':page,'page_sha256':version,'reason':safe_text(reason),'automatic_charge':False},current)
