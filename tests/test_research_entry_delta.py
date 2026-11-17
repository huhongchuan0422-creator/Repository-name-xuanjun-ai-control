import http.cookiejar
import json
import os
import sys
import unittest
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, os.path.dirname(__file__))
from test_task_center_session_auth import SessionAuthIntegrationTests

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.links.append(dict(attrs))

class ResearchEntryJourney(SessionAuthIntegrationTests):
    def test_prefixed_cookie_journey(self):
        from task_center_app import make_server
        from task_center_session_auth import FileTestIdentityProvider
        import threading
        server=make_server(self.db, b'0123456789abcdef0123456789abcdef', 'tenant-session', 'viewer', port=0,
          identity_provider=FileTestIdentityProvider(self.identity_path), session_store=self.sessions,
          base_path='/task-center-test/')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:%d/task-center-test/'%server.server_port
        try:
            def client(): return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def get(c,path): return c.open(urljoin(base,path),timeout=3)
            def login(c,user,password):
                req=Request(urljoin(base,'api/session/login'),data=json.dumps({'username':user,'password':password}).encode(),headers={'Content-Type':'application/json'})
                return json.loads(c.open(req,timeout=3).read())
            anon=client()
            with self.assertRaises(HTTPError) as denied: get(anon,'api/projection')
            self.assertEqual(denied.exception.code,401)
            with self.assertRaises(HTTPError) as denied: get(anon,'api/admin/digital-twin')
            self.assertEqual(denied.exception.code,403)
            viewer=client();login(viewer,'viewer','fixture-viewer-only')
            self.assertEqual(json.loads(get(viewer,'api/session').read())['roles'],['TASK_CENTER_VIEWER'])
            with self.assertRaises(HTTPError) as denied: get(viewer,'api/admin/digital-twin')
            self.assertEqual(denied.exception.code,403)
            admin=client();login(admin,'admin','fixture-password-only')
            html=get(admin,'task-center.html').read().decode();links=Links();links.feed(html)
            entry=next(x for x in links.links if x.get('id')=='researchEntry')
            self.assertIn('hidden',entry)
            entry_url=urljoin(base+'task-center.html',entry['href'])
            self.assertEqual(entry_url,base+'research-workbench/')
            page=admin.open(entry_url,timeout=3).read().decode();links=Links();links.feed(page)
            back=next(x for x in links.links if x.get('href')=='../task-center.html')
            self.assertEqual(urljoin(entry_url,back['href']),base+'task-center.html')
            self.assertEqual(get(admin,'api/projection').status,200)
            twin=json.loads(get(admin,'api/admin/digital-twin').read())
            self.assertEqual(twin['tenant_id'],'tenant-session')
            self.assertEqual(twin['permissions']['read_role'],'TASK_CENTER_ADMIN')
            self.assertEqual(get(admin,'task-center.html').status,200)
        finally:
            server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__': unittest.main()
