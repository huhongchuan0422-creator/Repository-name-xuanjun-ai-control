"""Private, append-only revision requests; no automatic billing or execution."""
import json
import re
import secrets
import html
from scripts.pr122_customer_core import canonical, digest, safe_text, identifier, Denied, Conflict


class Changes:
    def __init__(self, center):self.c=center

    def _events(self, uid, project, case):
        self.c.project(uid,project)
        rows=self.c.db.execute('SELECT * FROM change_events WHERE project=? AND case_id=? ORDER BY seq',(project,identifier(case))).fetchall()
        if not rows:raise Denied('CHANGE_NOT_FOUND')
        return [{**dict(r),'payload':json.loads(self.c.decrypt(r['payload'],r['id']))} for r in rows]

    def _append(self, uid, project, case, revision, kind, payload):
        with self.c.tx():
            self.c.project(uid,project)
            latest=self.c.db.execute('SELECT MAX(seq) FROM change_events WHERE project=? AND case_id=?',(project,case)).fetchone()[0] or 0
            if type(revision) is not int or revision!=latest:raise Conflict('CHANGE_REVISION')
            eid='ce_'+secrets.token_hex(16);seq=revision+1
            self.c.db.execute('INSERT INTO change_events VALUES(?,?,?,?,?,?,?,?)',(eid,project,case,seq,kind,uid,self.c.encrypt(canonical(payload),eid),self.c.now()))
            self.c.audit(project,uid,'CHANGE_'+kind,eid)
        return {'id':case,'revision':seq,'event_id':eid,**payload}

    def _page(self, page, version):
        if type(page) is not str or not re.fullmatch(r'/[A-Za-z0-9/_\-.]{1,300}',page) or '..' in page:raise ValueError('PAGE_PATH')
        if type(version) is not str or not re.fullmatch(r'[0-9a-f]{64}',version):raise ValueError('PAGE_VERSION_SHA256')

    def baseline(self, uid, project, page, version, text):
        self.c.project(uid,project,{'OWNER'});self._page(page,version)
        self.c.limit('change-baseline:'+uid+':'+project,20,3600)
        # The server timestamps this explicit confirmation; never backdate it.
        return self._append(uid,project,'baseline_'+secrets.token_hex(12),0,'BASELINE',{'page':page,'page_sha256':version,'confirmed_requirement':safe_text(text),'state':'CUSTOMER_CONFIRMED'})

    def submit(self, uid, project, page, version, text):
        self.c.project(uid,project,{'OWNER','EDITOR','VIEWER'});self._page(page,version)
        self.c.limit('change-submit:'+uid+':'+project,30,300)
        return self._append(uid,project,'change_'+secrets.token_hex(12),0,'REQUEST',{'page':page,'page_sha256':version,'request':safe_text(text),'state':'REQUESTED'})

    def preview_footer(self, uid, project, page, version):
        """For the authorized private-preview renderer, never a public catalog."""
        self.c.project(uid,project,{'OWNER','EDITOR','VIEWER'});self._page(page,version)
        return '<section data-project-feedback="'+html.escape(project,quote=True)+'" data-page-path="'+html.escape(page,quote=True)+'" data-page-sha256="'+version+'"></section><script src="/customer/center/feedback.js" defer></script>'

    def assess(self, uid, project, case, revision, category, minutes, lines, evidence, explanation):
        self.c.project(uid,project,{'REVIEWER'});events=self._events(uid,project,case)
        if events[0]['kind']!='REQUEST' or events[-1]['payload']['state'] not in ('REQUESTED','NEEDS_EVIDENCE','QUOTED','FREE_APPROVED','DISPUTED'):raise Conflict('ASSESSMENT_STATE')
        if category not in ('PROVIDER_DEFECT','IN_SCOPE_SMALL','CLIENT_CHANGE','NEW_SCOPE','UNKNOWN'):raise ValueError('CHANGE_CATEGORY')
        if type(minutes) is not int or not 0<=minutes<=10000000:raise ValueError('ESTIMATE_REQUIRED')
        if type(lines) is not list or len(lines)>50 or type(evidence) is not list or len(evidence)>20:raise ValueError('ASSESSMENT_SIZE')
        checked=[]
        for line in lines:
            if type(line) is not dict or set(line)!={'description','cny_minor','usd_minor'}:raise ValueError('QUOTE_LINE')
            safe_text(line['description'],200)
            if any(type(line[k]) is not int or not 0<=line[k]<=1000000000 for k in ('cny_minor','usd_minor')):raise ValueError('DUAL_PRICE_REQUIRED')
        for eid in evidence:
            record=self.c.db.execute('SELECT * FROM change_events WHERE id=? AND project=? AND kind=?',(identifier(eid),project,'BASELINE')).fetchone()
            if not record:raise Denied('BASELINE_EVIDENCE_REQUIRED')
            payload=json.loads(self.c.decrypt(record['payload'],record['id']))
            request=events[0]
            # seq supplies strict order even when timestamps share one second.
            order=self.c.db.execute('SELECT rowid FROM change_events WHERE id=?',(record['id'],)).fetchone()[0]
            request_order=self.c.db.execute('SELECT rowid FROM change_events WHERE id=?',(request['id'],)).fetchone()[0]
            if order>=request_order or payload['page']!=request['payload']['page'] or payload['page_sha256']!=request['payload']['page_sha256']:raise Denied('PRIOR_EXACT_BASELINE_REQUIRED')
            checked.append({'event_id':record['id'],'actor':record['actor'],'confirmed_at':record['created'],'sha256':digest(canonical(payload)),'requirement':payload['confirmed_requirement']})
        cny=sum(x['cny_minor'] for x in lines);usd=sum(x['usd_minor'] for x in lines)
        if category in ('PROVIDER_DEFECT','IN_SCOPE_SMALL') and (cny or usd):raise Denied('INCLUDED_FIX_MUST_BE_FREE')
        if category=='CLIENT_CHANGE' and not checked:state='NEEDS_EVIDENCE';lines=[];cny=usd=0
        elif category=='UNKNOWN':state='NEEDS_EVIDENCE';lines=[];cny=usd=0
        elif category in ('PROVIDER_DEFECT','IN_SCOPE_SMALL'):state='FREE_APPROVED'
        else:
            if not lines:raise ValueError('ITEMIZED_QUOTE_REQUIRED')
            state='QUOTED'
        payload={'state':state,'category':category,'estimated_minutes':minutes,'lines':lines,'totals':{'cny_minor':cny,'usd_minor':usd},'evidence':checked,'explanation':safe_text(explanation),'automatic_charge':False,'automatic_execution':False}
        return self._append(uid,project,case,revision,'ASSESSMENT',payload)

    def respond(self, uid, project, case, revision, action, reason):
        self.c.project(uid,project,{'OWNER'});events=self._events(uid,project,case);last=events[-1]
        if last['kind']!='ASSESSMENT' or last['payload']['state'] not in ('QUOTED','FREE_APPROVED'):raise Conflict('QUOTE_REQUIRED')
        if action not in ('CONFIRM','DISPUTE'):raise ValueError('CUSTOMER_ACTION')
        return self._append(uid,project,case,revision,'CUSTOMER_RESPONSE',{'state':'CUSTOMER_CONFIRMED' if action=='CONFIRM' else 'DISPUTED','assessment_event_id':last['id'],'assessment_sha256':digest(canonical(last['payload'])),'reason':safe_text(reason),'automatic_charge':False,'automatic_execution':False})

    def list(self, uid, project):
        self.c.project(uid,project)
        cases=[r[0] for r in self.c.db.execute('SELECT DISTINCT case_id FROM change_events WHERE project=?',(project,))]
        return {'project':project,'cases':[{'id':case,'events':self._events(uid,project,case)} for case in cases]}
