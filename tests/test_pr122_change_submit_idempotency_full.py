import base64
import hashlib
import hmac
import http.client
import json
import socket
import sqlite3
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from scripts.pr122_customer_change_authority import import_snapshot
from scripts.pr122_customer_core import Center, canonical, digest
from scripts.pr122_customer_http import App, COOKIE
from scripts.pr122_customer_providers import Providers
from tests.pr122_customer_change_fixture import PAGE_BYTES, PAGE_SHA, seed, snapshot
from tests import test_pr122_customer_center as _center_tests

ORIGIN = "https://wenwenwenyiyiyi.work"
PAGE = "/preview/consumer/"
KEY = "stable-key-00000001"


class ChangeSubmitIdempotencyFullTests(unittest.TestCase):
    def setUp(self):
        self.fixture = _center_tests.CustomerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        seed(self.fixture)
        root = self.fixture.root
        key = self.fixture.key
        def factory():
            return Center(root,{"v1":key},"v1",clock=lambda:self.fixture.now,mail_ready=True,scanner=lambda raw:True)
        self.server=ThreadingHTTPServer(("127.0.0.1",0),App(factory,Providers({}),ORIGIN,"deploy/pr122-customer-center/ui",source_identity=lambda connection,headers:"fixture-client").handler())
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.finish_server)
    def finish_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10)
    def auth_headers(self,name="owner"):
        u=self.fixture.users[name];return {"Cookie":COOKIE+"="+u["token"],"X-CSRF-Token":u["csrf"]}
    def request(self,body,name="owner",operation="change_submit_idempotent"):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=10)
        h={"Host":"wenwenwenyiyiyi.work","Origin":ORIGIN,"Content-Type":"application/json",**self.auth_headers(name)}
        raw=json.dumps(body,separators=(",",":"),ensure_ascii=False).encode()
        c.request("POST","/customer/center/api/"+operation,raw,h);r=c.getresponse();data=r.read();out=(r.status,json.loads(data));c.close();return out
    def body(self,**updates):
        v={"project":"project-a","page":PAGE,"version":PAGE_SHA,"text":"移动付款按钮","intent":"RECTIFICATION","idempotency_key":KEY};v.update(updates);return v
    def request_rows(self,project=None):
        c=sqlite3.connect(self.fixture.root/"center.sqlite")
        try:
            q="SELECT project,case_id,id,actor,payload FROM change_events WHERE kind='REQUEST'";args=()
            if project is not None:q+=" AND project=?";args=(project,)
            return c.execute(q,args).fetchall()
        finally:c.close()
    def test_same_key_same_body_returns_original_case_and_single_request(self):
        a=self.request(self.body());b=self.request(self.body());self.assertEqual((a[0],b[0]),(200,200));self.assertEqual(a[1]["id"],b[1]["id"]);self.assertEqual(a[1]["event_id"],b[1]["event_id"]);self.assertEqual(len(self.request_rows()),1)
    def test_same_key_different_body_conflicts_without_second_write(self):
        self.assertEqual(self.request(self.body())[0],200);self.assertEqual(self.request(self.body(text="不同正文"))[0],409);self.assertEqual(len(self.request_rows()),1)
    def test_invalid_key_and_legacy_endpoint_compatibility(self):
        self.assertEqual(self.request(self.body(idempotency_key="bad"))[0],400);legacy=self.body();legacy.pop("idempotency_key");self.assertEqual(self.request(legacy,operation="change_submit")[0],200);self.assertEqual(len(self.request_rows()),1)
    def test_legacy_invalid_text_still_consumes_original_quota_without_request(self):
        legacy=self.body();legacy.pop("idempotency_key");legacy["text"]=""
        self.assertEqual(self.request(legacy,operation="change_submit")[0],400)
        c=sqlite3.connect(self.fixture.root/"center.sqlite")
        try:
            key=self.fixture.c.idx("change-submit:"+self.fixture.owner+":project-a")
            row=c.execute("SELECT n FROM rate_limits WHERE k=?",(key,)).fetchone()
        finally:c.close()
        self.assertEqual(row[0] if row else None,1);self.assertEqual(len(self.request_rows()),0)
    def test_idempotent_retry_does_not_consume_quota_twice(self):
        self.assertEqual(self.request(self.body())[0],200)
        c=sqlite3.connect(self.fixture.root/"center.sqlite")
        try:
            key=self.fixture.c.idx("change-submit:"+self.fixture.owner+":project-a")
            first=c.execute("SELECT n FROM rate_limits WHERE k=?",(key,)).fetchone()[0]
        finally:c.close()
        self.assertEqual(first,1)
        self.assertEqual(self.request(self.body())[0],200)
        c=sqlite3.connect(self.fixture.root/"center.sqlite")
        try:second=c.execute("SELECT n FROM rate_limits WHERE k=?",(key,)).fetchone()[0]
        finally:c.close()
        self.assertEqual(second,1);self.assertEqual(len(self.request_rows()),1)
    def test_expired_session_and_bad_csrf_are_rejected_before_write(self):
        u=self.fixture.users["owner"];old=u["csrf"];u["csrf"]="wrong"
        try:self.assertEqual(self.request(self.body())[0],403)
        finally:u["csrf"]=old
        self.fixture.now+=3601;self.assertEqual(self.request(self.body())[0],403);self.assertEqual(len(self.request_rows()),0)
    def test_project_revocation_and_preview_version_drift_rejected(self):
        self.assertEqual(self.request(self.body(version="e"*64))[0],403);self.fixture.imported(2,[]);self.assertEqual(self.request(self.body())[0],403);self.assertEqual(len(self.request_rows()),0)
    def install_second_customer_and_preview(self):
        f=self.fixture
        p2={**f.p,"id":"project-b","tenant":"tenant-b","customer":"customer-b","owner_email":"other@example.com","contract_ref":"contract-b","order_ref":"order-b","title":"第二客户项目","reviewer_emails":[]}
        f.imported(2,[f.p,p2]);env=snapshot(f,revision=2);p=f.c.db.execute("SELECT * FROM projects WHERE id='project-b'").fetchone()
        m={"project":"project-b","contract_ref":"contract-b","source_commit":"b"*40,"artifact_sha256":digest(b"fixture artifact project-b"),"review_ref":"https://github.com/example/repo/pull/1#issuecomment-2","pages":[{"path":PAGE,"sha256":PAGE_SHA}]}
        env["payload"]["previews"].append({"project":"project-b","project_revision":p["revision"],"manifest":m,"manifest_sha256":digest(canonical(m)),"blobs":{PAGE_SHA:base64.b64encode(PAGE_BYTES).decode()}})
        env["signature"]=hmac.new(f.auth,canonical(env["payload"]),hashlib.sha256).hexdigest();import_snapshot(f.c,env,f.auth)
    def test_same_key_isolated_across_customer_and_project(self):
        self.install_second_customer_and_preview();a=self.request(self.body());b=self.request(self.body(project="project-b"),name="other");self.assertEqual((a[0],b[0]),(200,200));self.assertNotEqual(a[1]["id"],b[1]["id"]);self.assertEqual(len(self.request_rows()),2)
    def test_concurrent_same_key_real_center_connections_commit_once(self):
        barrier=threading.Barrier(6);results=[];lock=threading.Lock()
        def worker():
            barrier.wait();result=self.request(self.body())
            with lock:results.append(result)
        ts=[threading.Thread(target=worker) for _ in range(6)]
        [t.start() for t in ts];[t.join(30) for t in ts]
        self.assertTrue(all(not t.is_alive() for t in ts));self.assertEqual(sorted(x[0] for x in results),[200]*6);self.assertEqual(len({x[1]["id"] for x in results}),1);self.assertEqual(len({x[1]["event_id"] for x in results}),1);self.assertEqual(len(self.request_rows()),1)
    def test_committed_request_with_lost_response_retries_safely(self):
        body=self.body();raw=json.dumps(body,separators=(",",":"),ensure_ascii=False).encode();u=self.fixture.users["owner"]
        req=("POST /customer/center/api/change_submit_idempotent HTTP/1.1\r\nHost: wenwenwenyiyiyi.work\r\n"+f"Origin: {ORIGIN}\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\nCookie: {COOKIE}={u['token']}\r\nX-CSRF-Token: {u['csrf']}\r\nConnection: close\r\n\r\n").encode()+raw
        s=socket.create_connection(("127.0.0.1",self.server.server_port),timeout=10);s.sendall(req);deadline=time.time()+5
        while time.time()<deadline and len(self.request_rows())==0:time.sleep(0.02)
        self.assertEqual(len(self.request_rows()),1);s.close();retry=self.request(body);self.assertEqual(retry[0],200);rows=self.request_rows();self.assertEqual(len(rows),1);self.assertEqual(retry[1]["id"],rows[0][1]);self.assertEqual(retry[1]["event_id"],rows[0][2])

if __name__=="__main__":unittest.main(verbosity=2)
