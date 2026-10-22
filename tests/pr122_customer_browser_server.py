"""Isolated browser fixture for the complete customer preview/change/review/retest path.
The background signer is test-only and never represents production approval or deployment.
"""
import base64,hashlib,hmac,json,threading
from http.server import HTTPServer
from types import SimpleNamespace
from scripts.pr122_customer_core import Center,canonical,digest
from scripts.pr122_customer_http import App
from scripts.pr122_customer_providers import Providers
from scripts.pr122_customer_edit_jobs import drain,get
from scripts.pr122_customer_change_authority import import_snapshot
from tests.pr122_customer_change_fixture import snapshot
from tests.test_pr122_customer_small_edit import SmallEditTests

fixture=SmallEditTests();fixture.setUp()
root,key,now=fixture.root,fixture.key,fixture.now
stop=threading.Event();published=set()

def factory():return Center(root,{'v1':key},'v1',clock=lambda:now,mail_ready=True,scanner=lambda b:True)

def publish_ready(c):
    for row in c.db.execute("SELECT id FROM preview_edit_jobs WHERE state='CANDIDATE_READY' ORDER BY created,id").fetchall():
        job=row['id']
        if job in published:continue
        state=get(c,fixture.reviewer,'project-a',job)
        artifact=state['result']['artifact'];receipt=artifact['receipt'];body=base64.b64decode(artifact['page_base64'],validate=True)
        bound=SimpleNamespace(c=c,now=now,auth=fixture.auth,owner=fixture.owner)
        envelope=snapshot(bound,revision=2);data=envelope['payload'];entry=data['previews'][0]
        entry['manifest']['execution_scope']='TRUSTED_CUSTOMER_FRONTEND'
        entry['manifest']['pages']=[{'path':receipt['page'],'sha256':receipt['after_sha256']}]
        entry['manifest_sha256']=digest(canonical(entry['manifest']))
        entry['blobs']={receipt['after_sha256']:base64.b64encode(body).decode()}
        data['deliveries']=[{'project':'project-a','case':receipt['case'],'request_sha256':receipt['request_sha256'],'page':receipt['page'],'before_sha256':receipt['before_sha256'],'after_sha256':receipt['after_sha256'],'summary':'隔离浏览器fixture签入候选供复验','test_report_sha256':'c'*64,'deployment_receipt_sha256':'d'*64,'published_at':now}]
        envelope['signature']=hmac.new(fixture.auth,canonical(data),hashlib.sha256).hexdigest()
        import_snapshot(c,envelope,fixture.auth);published.add(job)

server=HTTPServer(('127.0.0.1',0),App(factory,Providers({}),'https://wenwenwenyiyiyi.work','deploy/pr122-customer-center/ui',source_identity=lambda connection,headers:'fixture-client').handler())

def worker():
    c=factory()
    try:
        while not stop.wait(.05):
            drain(c);publish_ready(c)
    finally:c.db.close()

thread=threading.Thread(target=worker,daemon=True);thread.start()
from scripts.pr122_customer_preview import route
print(json.dumps({'port':server.server_port,'initial_preview_url':route('project-a',fixture.path,fixture.sha),'initial_sha256':fixture.sha,'scope':'ISOLATED_FIXTURE_NOT_PRODUCTION','fixture_signer':'TEST_ONLY'}),flush=True)
try:server.serve_forever()
finally:
    stop.set();server.server_close();thread.join(timeout=3);fixture.c.db.close();fixture.tmp.cleanup()
