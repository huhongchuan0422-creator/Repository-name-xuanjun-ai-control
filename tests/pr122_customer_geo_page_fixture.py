"""TEST ONLY: original temporary Center and original HTTP handler over stdio.
No socket, live DB, credentials, source material, provider or production command.
"""
import json,sys
from tests.test_pr122_customer_geo_versions import VersionTests
from tests.test_pr122_customer_geo import Wire
from scripts import pr122_customer_http as http,pr122_customer_ops as ops
from scripts.pr122_customer_core import canonical

fixture=VersionTests('test_original_import_factory_http_snapshot_hit_without_new_ledger')
fixture.setUp()
fixture.seed();fixture.admit(version_document_id=fixture.document_id)
revision=1

def reply(data):
 print(json.dumps(data),flush=True)

try:
 reply({'ready':True,'csrf':fixture.users['owner']['csrf'],'scope':fixture.scope})
 for line in sys.stdin:
  command=json.loads(line)
  if command.get('control')=='disable-entitlement':
   revision+=1;fixture.admit(revision=revision,enabled=False,version_document_id=fixture.document_id)
   reply({'controlled':'synthetic-only'});continue
  if command.get('control')=='stats':
   row=fixture.c.db.execute('SELECT revision FROM geo_brand WHERE project=?',('project-a',)).fetchone()
   reply({'brand_revision':row[0] if row else 0,'commands':fixture.c.db.execute('SELECT count(*) FROM geo_commands').fetchone()[0]});continue
  options=command['options'];url=command['url']
  if not url.startswith('/customer/center/api/') or '?' in url:raise ValueError('TEST_ROUTE_REQUIRED')
  body=(options.get('body') or '').encode();method=options.get('method','GET')
  headers={'Host':'wenwenwenyiyiyi.work','Content-Length':str(len(body))}
  headers.update(options.get('headers',{}))
  if method=='POST':headers['Origin']='https://wenwenwenyiyiyi.work' # simulated same-origin browser
  if options.get('credentials')=='same-origin':headers['Cookie']=http.COOKIE+'='+fixture.users['owner']['token']
  request=(method+' '+url+' HTTP/1.1'+chr(13)+chr(10)+(chr(13)+chr(10)).join(k+': '+v for k,v in headers.items())+chr(13)+chr(10)+chr(13)+chr(10)).encode()+body
  wire=Wire(request)
  http.App(fixture.factory,ops.Providers({}),'https://wenwenwenyiyiyi.work','.').handler()(wire,('synthetic',0),object())
  head,raw=wire.output.getvalue().split(bytes([13,10,13,10]),1)
  reply({'status':int(head.split(b' ')[1]),'body':json.loads(raw)})
finally:
 fixture.doCleanups()
