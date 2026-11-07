from __future__ import print_function

import http.cookiejar
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.request import HTTPCookieProcessor,Request,build_opener,urlopen

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
import sys
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_center_session_auth import password_hash
from task_supervisor import Supervisor

KEY='0123456789abcdef0123456789abcdef'


class RuntimeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.authority_key=os.path.join(self.root,'authority.key')
        with open(self.authority_key,'w') as stream:stream.write(KEY+'\n')
        os.chmod(self.authority_key,0o600)
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY.encode())
        GatewayKernel(supervisor,authority).register_graph(
          authority.issue('tenant-runtime','seed'),demo_graph('tenant-runtime'))
        supervisor.close()
        self.model_key=os.path.join(self.root,'model.key')
        with open(self.model_key,'wb') as stream:stream.write(Fernet.generate_key()+b'\n')
        os.chmod(self.model_key,0o600)
        self.identities=os.path.join(self.root,'identities.json')
        fixture={'users':{'owner':{'password_hash':password_hash(
          'runtime-fixture-password'),'tenant_id':'tenant-runtime',
          'principal_id':'runtime-owner','roles':['TASK_CENTER_ADMIN'],
          'enabled':True}}}
        with open(self.identities,'w') as stream:json.dump(fixture,stream)
        os.chmod(self.identities,0o600)
        sock=socket.socket();sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        sock.close();self.command=[sys.executable,
          os.path.join(ROOT,'scripts','task_center_app.py'),'--db',self.db,
          '--test-authority-key-file',self.authority_key,
          '--tenant','tenant-runtime','--host',
          '127.0.0.1','--port',str(self.port),'--model-master-key-file',
          self.model_key,'--test-identity-file',self.identities]

    def tearDown(self):shutil.rmtree(self.root)

    def start(self):
        process=subprocess.Popen(self.command,stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,universal_newlines=True)
        deadline=time.time()+5
        while time.time()<deadline:
            if process.poll() is not None:
                out,err=process.communicate();self.fail('early exit %s %s'%(out,err))
            try:
                value=json.loads(urlopen('http://127.0.0.1:%d/healthz'%self.port,
                  timeout=.2).read().decode())
                if value['state']=='UP':return process
            except Exception:
                time.sleep(.05)
        process.terminate();process.wait();self.fail('health deadline')

    def stop(self,process):
        process.send_signal(signal.SIGTERM)
        out,err=process.communicate(timeout=5)
        self.assertEqual(process.returncode,0,(out,err))
        self.assertIn('"state": "STARTED"',out)
        self.assertIn('"state": "STOPPED"',out)
        self.assertNotIn('runtime-fixture-password',out+err)
        return out,err

    def test_start_health_login_stop_and_restart_rebuild_same_state(self):
        first=self.start()
        ready=json.loads(urlopen('http://127.0.0.1:%d/readyz'%self.port).read())
        self.assertEqual(ready['state'],'READY')
        jar=http.cookiejar.CookieJar();client=build_opener(HTTPCookieProcessor(jar))
        request=Request('http://127.0.0.1:%d/api/session/login'%self.port,
          data=json.dumps({'username':'owner','password':
          'runtime-fixture-password'}).encode(),method='POST',
          headers={'Content-Type':'application/json'})
        self.assertEqual(json.loads(client.open(request).read())['state'],'AUTHENTICATED')
        projection=json.loads(client.open('http://127.0.0.1:%d/api/projection'%
          self.port).read())
        self.assertEqual(len(projection['tasks']),3)
        self.stop(first)
        second=self.start()
        jar=http.cookiejar.CookieJar();client=build_opener(HTTPCookieProcessor(jar))
        request=Request('http://127.0.0.1:%d/api/session/login'%self.port,
          data=json.dumps({'username':'owner','password':
          'runtime-fixture-password'}).encode(),method='POST',
          headers={'Content-Type':'application/json'})
        client.open(request)
        rebuilt=json.loads(client.open('http://127.0.0.1:%d/api/projection'%
          self.port).read())
        self.assertEqual({x['task_id'] for x in rebuilt['tasks']},
                         {'demo-a','demo-b','demo-c'})
        self.stop(second)


if __name__=='__main__':unittest.main()
