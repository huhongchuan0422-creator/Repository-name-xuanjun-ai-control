"""Isolated authenticated fixture server, never a production entry point."""
import json,os,sys,tempfile
from http.server import HTTPServer
from pathlib import Path
from tests.test_pr122_customer_center import CustomerTests
from scripts.pr122_customer_core import Center
from scripts.pr122_customer_http import App
from scripts.pr122_customer_providers import Providers
fixture=CustomerTests();fixture.setUp()
root=fixture.root;key=fixture.key;now=fixture.now
# Test login accounts are confirmed by the trusted local fixture, not a bypass in
# application routes. No fixture registration endpoint exists.
def factory():return Center(root,{'v1':key},'v1',clock=lambda:now,mail_ready=True,scanner=lambda b:True)
server=HTTPServer(('127.0.0.1',0),App(factory,Providers({}),'https://wenwenwenyiyiyi.work','deploy/pr122-customer-center/ui',source_identity=lambda connection,headers:'fixture-client').handler())
print(json.dumps({'port':server.server_port,'scope':'ISOLATED_FIXTURE_NOT_PRODUCTION'}),flush=True)
try:server.serve_forever()
finally:server.server_close();fixture.c.db.close();fixture.tmp.cleanup()
