"""Actual Flask MCP route, synthetic custody, no sockets or OAuth credentials."""
import base64
import unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_cloud_connection_material_custody as fixtures
from production.cloud_connection.oauth_http import create_resource_app
from production.cloud_connection.queue import Hold


class CustodyHTTPTests(unittest.TestCase):
    def test_http_custody_and_status_only_denial(self):
        fixture=fixtures.CustodyTests(methodName='test_custody_whole_regular_chain_readonly')
        fixture.setUp()
        try:
            fixture.success();fixture.ingest();fixture.q.db.execute('PRAGMA query_only=ON')
            opened=[]
            class Auth:
                def authenticate(self,header,scope,project,now):
                    if header!='Bearer synthetic-files-token' or scope!='project.files.read':raise Hold('OAUTH_SCOPE')
                    return 'fixture-reader'
            class Backend:
                db=fixture.q.db
                def close(self):pass
            def backend():opened.append(True);return Backend()
            catalog=fixture.policy.catalog
            app=create_resource_app(Auth(),backend,{catalog.sha:(catalog,{})},'https://authority.example.test/mcp',True,lambda:fixtures.NOW,{catalog.sha:[fixture.dest,fixture.owner]})
            client=app.test_client()
            message={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'read_project_chunk','arguments':dict(manifest_sha256=catalog.sha,request_id='fixture-request',object_ref='fixture-object',offset=0)}}
            headers={'Authorization':'Bearer synthetic-status-token','Host':'localhost'}
            with patch('socket.socket.connect',side_effect=AssertionError('network')):
                denied=client.post('/mcp',json=message,headers=headers,base_url='http://localhost')
                self.assertEqual(denied.status_code,401);self.assertEqual(opened,[])
                headers['Authorization']='Bearer synthetic-files-token'
                response=client.post('/mcp',json=message,headers=headers,base_url='http://localhost')
            self.assertEqual(response.status_code,200)
            self.assertEqual(base64.b64decode(response.get_json()['result']['structuredContent']['data']),fixture.body)
            self.assertEqual(len(opened),1)
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
