"""Private, append-only revision requests; no automatic billing or execution."""
import json
import re
import secrets
import html
from scripts.pr122_customer_core import canonical, digest, safe_text, identifier, Denied, Conflict
from scripts.pr122_customer_change_authority import preview, document


class Changes:
    def __init__(self, center):self.c=center

    def _request_sha(self,events):return digest(canonical({'event_id':events[0]['id'],'payload':events[0]['payload']}))

    def _events(self, uid, project, case):
        self.c.project(uid,project)
        rows=self.c.db.execute('SELECT * FROM change_events WHERE project=? AND case_id=? ORDER BY seq',(project,identifier(case))).fetchall()
        if not rows:raise Denied('CHANGE_NOT_FOUND')
        return [{**dict(r),'payload':json.loads(self.c.decrypt(r['payload'],r['id']))} for r in rows]

    def _append(self, uid, project, case, revision, kind, payload,guard=None):
        with self.c.tx():
            self.c.project(uid,project)
            if guard:guard()
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

    def submit(self, uid, project, page, version, text, intent='RECTIFICATION'):
        self.c.project(uid,project,{'OWNER'});bound=self._preview(uid,project,page,version)
        if intent not in ('RECTIFICATION','NEW_ORDER'):raise ValueError('REQUEST_INTENT')
        self.c.limit('change-submit:'+uid+':'+project,30,300)
        def guard():
            if self._preview(uid,project,page,version)!=bound:raise Conflict('AUTHORITY_CHANGED')
        return self._append(uid,project,'change_'+secrets.token_hex(12),0,'REQUEST',{'page':page,'page_sha256':version,'preview':bound,'request':safe_text(text),'intent':intent,'state':'REQUESTED'},guard)

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
        checked=self._evidence(uid,project,events,category,evidence)
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
            if self._evidence(uid,project,events,category,evidence)!=checked:raise Conflict('AUTHORITY_CHANGED')
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
