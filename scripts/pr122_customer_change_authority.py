"""Protected canonical-source import. No HTTP writer or client assertion trust."""
import base64
import hashlib
import hmac
import json
import re
from scripts.pr122_customer_core import canonical,digest,identifier,safe_text,Denied,Conflict

PURPOSE='PR122_CHANGE_AUTHORITY_V1'

def sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):raise Denied('SOURCE_HASH')
    return value

def project_record(c,pid,revision):
    p=c.db.execute('SELECT * FROM projects WHERE id=? AND active=1',(identifier(pid),)).fetchone()
    if not p or p['expires']<=c.now() or type(revision) is not int or p['revision']!=revision:raise Denied('SOURCE_PROJECT_REVISION')
    return p

def import_snapshot(c,envelope,key):
    """Called only by protected operator with canonical-source signed bytes.

    Signature authority must derive this from reviewed artifact and contract
    stores. It is not supplied by a customer or the assessment reviewer.
    """
    if type(key) is not bytes or len(key)!=32 or type(envelope) is not dict or set(envelope)!={'payload','signature'}:raise Denied('SOURCE_ENVELOPE')
    d=envelope['payload'];raw=canonical(d)
    if len(raw)>10000000 or type(envelope['signature']) is not str or not hmac.compare_digest(hmac.new(key,raw,hashlib.sha256).hexdigest(),envelope['signature']):raise Denied('SOURCE_SIGNATURE')
    if set(d) not in ({'purpose','revision','issued_at','expires','previews','documents'},{'purpose','revision','issued_at','expires','previews','documents','deliveries'}) or d['purpose']!=PURPOSE or type(d['revision']) is not int or d['revision']<1:raise Denied('SOURCE_SCHEMA')
    if any(type(d[k]) is not int for k in ('issued_at','expires')) or not c.now()-300<=d['issued_at']<=c.now() or not c.now()<d['expires']<=c.now()+3600:raise Denied('SOURCE_EXPIRY')
    if type(d['previews']) is not list or type(d['documents']) is not list or len(d['previews'])>100 or len(d['documents'])>1000:raise Denied('SOURCE_SIZE')
    previews=[];documents=[];seen=set()
    for entry in d['previews']:
        if set(entry)!={'project','project_revision','manifest','manifest_sha256','blobs'}:raise Denied('PREVIEW_SOURCE_SCHEMA')
        p=project_record(c,entry['project'],entry['project_revision']);m=entry['manifest'];sha(entry['manifest_sha256'])
        if type(m) is not dict or set(m)!={'project','contract_ref','source_commit','artifact_sha256','review_ref','pages'} or digest(canonical(m))!=entry['manifest_sha256']:raise Denied('PREVIEW_MANIFEST_HASH')
        if m['project']!=p['id'] or m['contract_ref']!=p['authority_ref'] or not re.fullmatch('[0-9a-f]{40}',m['source_commit']) or not re.fullmatch(r'https://github.com/[^\s]+#issuecomment-[0-9]+',m['review_ref']):raise Denied('REVIEWED_PREVIEW_BINDING')
        sha(m['artifact_sha256'])
        if type(m['pages']) is not list or not 1<=len(m['pages'])<=100 or type(entry['blobs']) is not dict:raise Denied('PREVIEW_PAGE_SET')
        for page in m['pages']:
            if set(page)!={'path','sha256'} or not re.fullmatch(r'/[A-Za-z0-9/_\-.]{1,300}',page['path']) or '..' in page['path']:raise Denied('PREVIEW_PAGE_PATH')
            sha(page['sha256']);key_id=(p['id'],page['path'],page['sha256'])
            if key_id in seen:raise Denied('DUPLICATE_PREVIEW_PAGE')
            seen.add(key_id)
            data=base64.b64decode(entry['blobs'].get(page['sha256'],''),validate=True)
            if len(data)>1000000 or digest(data)!=page['sha256']:raise Denied('PREVIEW_PAGE_BYTES')
            previews.append({'project':p['id'],'project_revision':p['revision'],'owner':p['owner'],'page':page['path'],'page_sha256':page['sha256'],'manifest_sha256':entry['manifest_sha256'],'artifact_sha256':m['artifact_sha256'],'review_ref':m['review_ref']})
    docids=set()
    for entry in d['documents']:
        if set(entry)!={'id','project_revision','document_utf8','document_sha256','version_sha256'}:raise Denied('DOCUMENT_SOURCE_SCHEMA')
        identifier(entry['id']);sha(entry['document_sha256']);sha(entry['version_sha256'])
        if entry['id'] in docids:raise Denied('DUPLICATE_DOCUMENT')
        docids.add(entry['id'])
        if type(entry['document_utf8']) is not str or len(entry['document_utf8'])>1000000 or digest(entry['document_utf8'].encode())!=entry['document_sha256']:raise Denied('DOCUMENT_BYTES')
        doc=json.loads(entry['document_utf8'])
        if type(doc) is not dict or set(doc)!={'project','contract_ref','kind','version','text','confirmed_by','confirmed_at','source_ref','page','page_sha256','request_sha256','new_order_ref'}:raise Denied('DOCUMENT_SCHEMA')
        p=project_record(c,doc['project'],entry['project_revision'])
        if doc['contract_ref']!=p['authority_ref'] or doc['confirmed_by']!=p['owner'] or type(doc['confirmed_at']) is not int or not 0<doc['confirmed_at']<=c.now() or type(doc['version']) is not int or doc['version']<1:raise Denied('CONFIRMED_CONTRACT_BINDING')
        if doc['kind'] not in ('CONTRACT','REQUIREMENTS','ACCEPTED_VERSION','NEW_ORDER') or type(doc['source_ref']) is not str or not doc['source_ref'].startswith('https://'):raise Denied('CONTRACT_SOURCE_REQUIRED')
        safe_text(doc['text']);sha(doc['page_sha256'])
        if type(doc['page']) is not str or not re.fullmatch(r'/[A-Za-z0-9/_\-.]{1,300}',doc['page']) or '..' in doc['page']:raise Denied('DOCUMENT_PAGE_BINDING')
        if entry['version_sha256']!=digest(canonical({'document_sha256':entry['document_sha256'],'version':doc['version'],'project':p['id'],'contract_ref':p['authority_ref']})):raise Denied('DOCUMENT_VERSION_HASH')
        if doc['kind']=='NEW_ORDER':
            sha(doc['request_sha256']);identifier(doc['new_order_ref'])
            original=json.loads(c.decrypt(p['payload'],'project:'+p['id']))
            if doc['new_order_ref']==original['order_ref']:raise Denied('SEPARATE_NEW_ORDER_REQUIRED')
        elif doc['request_sha256'] is not None or doc['new_order_ref'] is not None:raise Denied('HISTORICAL_DOCUMENT_SCOPE')
        documents.append({**doc,'id':entry['id'],'project_revision':p['revision'],'document_utf8':entry['document_utf8'],'document_sha256':entry['document_sha256'],'version_sha256':entry['version_sha256']})
    deliveries=d.get('deliveries',[])
    if type(deliveries) is not list or len(deliveries)>1000:raise Denied('DELIVERY_SIZE')
    delivery_ids=set()
    for delivery in deliveries:
        fields={'project','case','request_sha256','page','before_sha256','after_sha256','summary','test_report_sha256','deployment_receipt_sha256','published_at'}
        if type(delivery) is not dict or set(delivery)!=fields:raise Denied('DELIVERY_SCHEMA')
        identifier(delivery['case']);safe_text(delivery['summary'],1000)
        for field in ('request_sha256','before_sha256','after_sha256','test_report_sha256','deployment_receipt_sha256'):sha(delivery[field])
        if delivery['before_sha256']==delivery['after_sha256'] or type(delivery['published_at']) is not int or not 0<delivery['published_at']<=c.now():raise Denied('DELIVERY_VERSION_OR_TIME')
        if (delivery['project'],delivery['case']) in delivery_ids:raise Denied('DELIVERY_DUPLICATE')
        delivery_ids.add((delivery['project'],delivery['case']))
        if not any(x['project']==delivery['project'] and x['page']==delivery['page'] and x['page_sha256']==delivery['after_sha256'] for x in previews):raise Denied('DELIVERY_NOT_CURRENT_PREVIEW')
        rows=c.db.execute('SELECT * FROM change_events WHERE project=? AND case_id=? ORDER BY seq',(delivery['project'],delivery['case'])).fetchall()
        if not rows or rows[0]['kind']!='REQUEST':raise Denied('DELIVERY_REQUEST')
        first=rows[0];request=json.loads(c.decrypt(first['payload'],first['id']))
        if delivery['request_sha256']!=digest(canonical({'event_id':first['id'],'payload':request})) or delivery['page']!=request['page'] or delivery['before_sha256']!=request['page_sha256'] or delivery['published_at']<first['created']:raise Denied('DELIVERY_REQUEST_BINDING')
        # This is an attestation from the protected publication source, not an HTTP assertion.
        # It must be issued after tests and actual private-preview availability checks.
        last=rows[-1];state=json.loads(c.decrypt(last['payload'],last['id'])).get('state')
        if state not in ('FREE_APPROVED','CUSTOMER_CONFIRMED','RETEST_ACCEPTED','RETEST_FEEDBACK'):raise Denied('DELIVERY_NOT_APPROVED')
    stored={'revision':d['revision'],'expires':d['expires'],'imported_at':c.now(),'previews':previews,'documents':documents,'deliveries':deliveries,'source_sha256':digest(raw)}
    with c.tx():
        if stored['expires']<=c.now():raise Denied('SOURCE_EXPIRY')
        for record in [*previews,*documents]:project_record(c,record['project'],record['project_revision'])
        for delivery in deliveries:
            last=c.db.execute('SELECT * FROM change_events WHERE project=? AND case_id=? ORDER BY seq DESC LIMIT 1',(delivery['project'],delivery['case'])).fetchone()
            if not last or json.loads(c.decrypt(last['payload'],last['id'])).get('state') not in ('FREE_APPROVED','CUSTOMER_CONFIRMED','RETEST_ACCEPTED','RETEST_FEEDBACK'):raise Denied('DELIVERY_APPROVAL_CHANGED')
        row=c.db.execute('SELECT payload FROM change_authority WHERE id=?',('current',)).fetchone()
        if row and json.loads(c.decrypt(row[0],'change-authority'))['revision']>=d['revision']:raise Conflict('SOURCE_REPLAY')
        c.db.execute('INSERT INTO change_authority_history VALUES(?,?)',(d['revision'],c.encrypt(canonical(envelope),'change-authority-source:'+str(d['revision']))))
        c.db.execute('INSERT OR REPLACE INTO change_authority VALUES(?,?)',('current',c.encrypt(canonical(stored),'change-authority')))
        c.audit('','operator','CHANGE_AUTHORITY_IMPORT',digest(raw))
    return {'revision':d['revision'],'previews':len(previews),'documents':len(documents)}

def load(c):
    row=c.db.execute('SELECT payload FROM change_authority WHERE id=?',('current',)).fetchone()
    if not row:raise Denied('CHANGE_AUTHORITY_NOT_CONNECTED')
    d=json.loads(c.decrypt(row[0],'change-authority'))
    if d['expires']<=c.now():raise Denied('CHANGE_AUTHORITY_EXPIRED')
    return d

def preview(c,uid,project,page,version):
    p,_,_=c.project(uid,project,{'OWNER'});d=load(c)
    record=next((x for x in d['previews'] if x['project']==project and x['project_revision']==p['revision'] and x['owner']==uid and x['page']==page and x['page_sha256']==version),None)
    if not record:raise Denied('AUTHORIZED_REVIEWED_PREVIEW_REQUIRED')
    return {**record,'authority_revision':d['revision']}

def document(c,uid,project,document_id,page,version):
    p,_,_=c.project(uid,project);d=load(c)
    record=next((x for x in d['documents'] if x['id']==identifier(document_id) and x['project']==project and x['project_revision']==p['revision'] and x['page']==page and x['page_sha256']==version),None)
    if not record:raise Denied('CANONICAL_DOCUMENT_REQUIRED')
    return record
