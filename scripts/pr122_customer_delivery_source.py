"""Protected publication source: signed exact tests + server-owned served bytes.
No HTTP writer, model calls, key generation or install privilege is provided here.
"""
import base64
import copy
import hashlib
import hmac
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from scripts.pr122_customer_core import canonical,digest,Denied
from scripts.pr122_customer_change_authority import load,import_snapshot
from scripts.pr122_customer_changes import Changes

REQUIRED={'render','assets','javascript','csp','desktop','mobile','project_isolation','feedback','retest'}

def issue(c,project,case,serve_id,report,trust,source_key):
    """Operator uses independently enrolled test signer and current source key.
    report is a machine test receipt, not independent installation permission.
    """
    if type(source_key) is not bytes or len(source_key)!=32:raise Denied('PROTECTED_SOURCE_KEY_REQUIRED')
    current=load(c);owner=c.db.execute('SELECT owner FROM projects WHERE id=?',(project,)).fetchone()
    if not owner:raise Denied('PROJECT_NOT_FOUND')
    p,_,_=c.project(owner[0],project,{'OWNER'})
    events=Changes(c)._events(p['owner'],project,case);request=events[0]['payload']
    if events[0]['kind']!='REQUEST' or events[-1]['payload']['state'] not in ('FREE_APPROVED','CUSTOMER_CONFIRMED','RETEST_FEEDBACK'):raise Denied('APPROVED_CHANGE_REQUIRED')
    row=c.db.execute('SELECT * FROM preview_serves WHERE id=? AND project=? AND actor=?',(serve_id,project,p['owner'])).fetchone()
    if not row:raise Denied('SERVER_OWNED_DELIVERY_REQUIRED')
    served=json.loads(c.decrypt(row['payload'],row['id']))
    if type(report) is not dict or set(report)!={'payload','key_id','signature'}:raise Denied('SIGNED_TEST_REPORT_REQUIRED')
    if type(trust) is not dict or set(trust)!={'source_writer_principal','keys','allowed_harness_sha256'}:raise Denied('TEST_SIGNER_TRUST_REQUIRED')
    key=trust['keys'].get(report['key_id']);test=report['payload']
    if not key or set(key)!={'principal','public_key_b64','state','custody_evidence_sha256'} or key['state']!='ACTIVE' or key['principal']==trust['source_writer_principal'] or not __import__('re').fullmatch('[0-9a-f]{64}',key['custody_evidence_sha256']):raise Denied('ENROLLED_TEST_SIGNER_REQUIRED')
    try:Ed25519PublicKey.from_public_bytes(base64.b64decode(key['public_key_b64'],validate=True)).verify(base64.b64decode(report['signature'],validate=True),canonical(test))
    except Exception:raise Denied('TEST_REPORT_SIGNATURE') from None
    fields={'purpose','project','case','request_sha256','page','before_sha256','after_sha256','manifest_sha256','source_commit','artifact_sha256','render_sha256','harness_sha256','checks','issued_at','expires','summary'}
    if type(test) is not dict or set(test)!=fields or test['purpose']!='PR122_PRIVATE_PREVIEW_TEST_V1':raise Denied('TEST_REPORT_SCHEMA')
    if test['harness_sha256'] not in trust['allowed_harness_sha256'] or type(test['checks']) is not dict or set(test['checks'])!=REQUIRED or any(v!='PASS' for v in test['checks'].values()):raise Denied('EXACT_TESTS_REQUIRED')
    if any(type(test[k]) is not int for k in ('issued_at','expires')) or not test['issued_at']<=row['created']<=c.now()<test['expires'] or test['expires']-test['issued_at']>86400:raise Denied('TEST_REPORT_EXPIRED_OR_PREDEPLOYMENT')
    if test['project']!=project or test['case']!=case or test['request_sha256']!=Changes(c)._request_sha(events) or test['page']!=request['page'] or test['before_sha256']!=request['page_sha256']:raise Denied('TEST_REQUEST_BINDING')
    selected=next((r for r in current['previews'] if r['project']==project and r['page']==test['page'] and r['page_sha256']==test['after_sha256']),None)
    if not selected or served['authority_revision']!=current['revision'] or served['page']!=test['page'] or served['page_sha256']!=test['after_sha256'] or served['manifest_sha256']!=selected['manifest_sha256']:raise Denied('CURRENT_DEPLOYMENT_REQUIRED')
    for field in ('manifest_sha256','source_commit','artifact_sha256','render_sha256'):
        if test[field]!=served[field]:raise Denied('TEST_DEPLOYMENT_BINDING')
    source=c.db.execute('SELECT payload FROM change_authority_history WHERE revision=?',(current['revision'],)).fetchone()
    envelope=json.loads(c.decrypt(source[0],'change-authority-source:'+str(current['revision'])))
    if digest(canonical(envelope['payload']))!=current['source_sha256'] or not hmac.compare_digest(hmac.new(source_key,canonical(envelope['payload']),hashlib.sha256).hexdigest(),envelope['signature']):raise Denied('CURRENT_SOURCE_SIGNATURE')
    payload=copy.deepcopy(envelope['payload']);payload['revision']+=1;payload['issued_at']=c.now();payload['expires']=min(current['expires'],test['expires'])
    delivery={'project':project,'case':case,'request_sha256':test['request_sha256'],'page':test['page'],'before_sha256':test['before_sha256'],'after_sha256':test['after_sha256'],'summary':test['summary'],'test_report_sha256':digest(canonical(report)),'deployment_receipt_sha256':digest(canonical(served)),'published_at':row['created']}
    payload['deliveries']=[x for x in payload.get('deliveries',[]) if (x['project'],x['case'])!=(project,case)]+[delivery]
    proof={'test':report,'serve_id':serve_id,'served':served,'delivery':delivery};proof_sha=digest(canonical(proof))
    with c.tx():
        if load(c)['revision']!=current['revision']:raise Denied('DELIVERY_SOURCE_CHANGED')
        c.db.execute('INSERT OR IGNORE INTO preview_delivery_proofs VALUES(?,?,?,?)',(proof_sha,project,case,c.encrypt(canonical(proof),proof_sha)))
        c.audit(project,'operator','DELIVERY_EVIDENCE_RECORDED',proof_sha)
    result=import_snapshot(c,{'payload':payload,'signature':hmac.new(source_key,canonical(payload),hashlib.sha256).hexdigest()},source_key)
    return {**result,'proof_sha256':proof_sha,'delivery_sha256':digest(canonical(delivery)),'source':'SIGNED_TEST_AND_AUTHENTICATED_HTTP_SERVE','production_https_browser':'NOT_ESTABLISHED_BY_THIS_SOURCE'}
