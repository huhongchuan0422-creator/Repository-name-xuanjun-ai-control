from __future__ import print_function

import io
import json
import os
import unittest

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
import sys;sys.path.insert(0,os.path.join(ROOT,'scripts'))
from task_center_mcp import TaskCenterMCP,TOOLS


class Response(object):
    def __init__(self,value):self.value=value
    def read(self):return json.dumps(self.value).encode('utf-8')


class TaskCenterMCPTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        def opener(request,timeout=None):
            self.requests.append(request)
            if request.full_url.endswith('/api/projection'):
                return Response({'tasks':[{'task_id':'task-a','tenant_id':'tenant-a'}]})
            if request.data is None:return Response({'candidates':[],'requests':[]})
            value=json.loads(request.data.decode('utf-8'))
            return Response({'state':'OK','echo':value})
        self.mcp=TaskCenterMCP('http://127.0.0.1:8080','admin-token',
          'actor-token','developer-1',opener)

    def test_tool_schema_has_no_identity_shell_sql_or_path(self):
        encoded=json.dumps(TOOLS)
        for forbidden in ('tenant_id','principal_id','role_id','shell','sql','path'):
            self.assertNotIn(forbidden,encoded.lower())
        self.assertEqual(len({x['name'] for x in TOOLS}),len(TOOLS))

    def test_loopback_url_cannot_be_bypassed_with_userinfo(self):
        for bad in ('http://127.0.0.1:8080@evil.example',
                    'http://127.0.0.1:8080/path',
                    'http://127.0.0.1:8080?next=evil'):
            with self.assertRaisesRegex(ValueError,'LOOPBACK_TASK_CENTER'):
                TaskCenterMCP(bad,'admin','actor','principal',lambda _:None)

    def test_read_is_task_scoped_and_writes_use_server_bound_actor(self):
        result=self.mcp.call('task_read_context',{'task_id':'task-a'})
        self.assertEqual(result['task']['task_id'],'task-a')
        submitted=self.mcp.call('task_submit_artifact',{'task_id':'task-a',
          'artifact_sha256':'a'*64,'checklist_sha256':'b'*64})
        self.assertEqual(submitted['echo']['submitted_by'],'developer-1')
        request=self.requests[-1]
        self.assertEqual(request.headers['X-test-actor-token'],'actor-token')
        self.assertNotIn('tenant_id',submitted['echo'])

    def test_initialize_list_and_duplicate_progress_map_to_existing_api(self):
        initialized=self.mcp.rpc({'jsonrpc':'2.0','id':1,'method':'initialize'})
        self.assertEqual(initialized['result']['serverInfo']['name'],
          'xuanjun-task-center')
        listed=self.mcp.rpc({'jsonrpc':'2.0','id':2,'method':'tools/list'})
        self.assertGreaterEqual(len(listed['result']['tools']),7)
        args={'task_id':'task-a','event_id':'evt-1','evidence_ref':'proof-1'}
        first=self.mcp.call('task_report_progress',args)
        second=self.mcp.call('task_report_progress',args)
        self.assertEqual(first['echo'],second['echo'])
        self.assertEqual(first['echo']['action'],'REPORT_TEST_ONLY_PROGRESS')


if __name__=='__main__':unittest.main()
