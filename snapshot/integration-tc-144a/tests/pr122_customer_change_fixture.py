"""Synthetic signed canonical records, only for isolated tests."""
import base64
import hashlib
import hmac
from scripts.pr122_customer_core import canonical,digest
from scripts.pr122_customer_change_authority import import_snapshot,PURPOSE

PAGE_BYTES=b'<!doctype html><title>Isolated reviewed preview fixture</title>'
PAGE_SHA=digest(PAGE_BYTES)

def snapshot(fixture,revision=1,documents=None,paths=None):
    p=fixture.c.db.execute('SELECT * FROM projects WHERE id=?',('project-a',)).fetchone()
    manifest={'project':'project-a','contract_ref':'contract-a','source_commit':'a'*40,'artifact_sha256':digest(b'fixture artifact'),'review_ref':'https://github.com/example/repo/pull/1#issuecomment-1','pages':[{'path':path,'sha256':PAGE_SHA} for path in (paths or ['/project/consumer/','/preview/consumer/'])]}
    payload={'purpose':PURPOSE,'revision':revision,'issued_at':fixture.now,'expires':fixture.now+3600,'previews':[{'project':'project-a','project_revision':p['revision'],'manifest':manifest,'manifest_sha256':digest(canonical(manifest)),'blobs':{PAGE_SHA:base64.b64encode(PAGE_BYTES).decode()}}],'documents':documents or []}
    return {'payload':payload,'signature':hmac.new(fixture.auth,canonical(payload),hashlib.sha256).hexdigest()}

def doc(fixture,kind='CONTRACT',text='确认按钮放在页面顶部',path='/project/consumer/',request_sha=None,document_id='contract-version-1'):
    source={'project':'project-a','contract_ref':'contract-a','kind':kind,'version':1,'text':text,'confirmed_by':fixture.owner,'confirmed_at':fixture.now-100,'source_ref':'https://contracts.example.test/immutable/contract-version-1','page':path,'page_sha256':PAGE_SHA,'request_sha256':request_sha,'new_order_ref':'order-new-1' if kind=='NEW_ORDER' else None}
    if kind=='NEW_ORDER':source['confirmed_at']=fixture.now
    raw=canonical(source).decode();sha=digest(raw.encode())
    return {'id':document_id,'project_revision':fixture.c.db.execute('SELECT revision FROM projects WHERE id=?',('project-a',)).fetchone()[0],'document_utf8':raw,'document_sha256':sha,'version_sha256':digest(canonical({'document_sha256':sha,'version':1,'project':'project-a','contract_ref':'contract-a'}))}

def seed(fixture,revision=1,documents=None,paths=None):
    return import_snapshot(fixture.c,snapshot(fixture,revision,documents,paths),fixture.auth)
