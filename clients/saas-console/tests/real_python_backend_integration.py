#!/usr/bin/env python3
"""Isolated real-Python-HTTP integration against the exact PR122 backend checkout.

This does NOT use a Node/fetch fake server. It imports Center/App/HTTPServer and
the repository's signed preview fixtures from XJ_PR122_BACKEND_ROOT, which must
be checked out exactly at EXPECTED_BACKEND_COMMIT.
"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

EXPECTED_BACKEND_COMMIT="1b48e5fe8015afd9035ff269f9b432d9a68223b2"
root_env=os.environ.get("XJ_PR122_BACKEND_ROOT")
if not root_env:
    raise SystemExit("HOLD_MISSING_XJ_PR122_BACKEND_ROOT")
BACKEND_ROOT=Path(root_env).resolve()
if not (BACKEND_ROOT/".git").exists():
    raise SystemExit("HOLD_BACKEND_ROOT_NOT_GIT_CHECKOUT")
head=subprocess.check_output(["git","-C",str(BACKEND_ROOT),"rev-parse","HEAD"],text=True).strip()
if head!=EXPECTED_BACKEND_COMMIT:
    raise SystemExit("HOLD_BACKEND_COMMIT_MISMATCH:"+head)
os.chdir(BACKEND_ROOT)
sys.path.insert(0,str(BACKEND_ROOT))

from scripts.pr122_customer_core import canonical,digest
from scripts.pr122_customer_change_authority import import_snapshot
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_http import COOKIE
from tests.test_pr122_customer_http import HttpTests
from tests.pr122_customer_change_fixture import PAGE_SHA,PAGE_BYTES,snapshot


class SaaSRealPythonHTTPIntegration(unittest.TestCase):
    """Synthetic identity/tenant only; no Hosted/customer/production credentials."""

    def setUp(self):
        self.f=HttpTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()

        # Add a second tenant/customer at the canonical project authority layer.
        p2={**self.f.p,"id":"project-b","tenant":"tenant-b","customer":"customer-b",
            "owner_email":"other@example.com"}
        self.f.imported(2,[self.f.p,p2])

        # Install a signed TRUSTED_CUSTOMER_FRONTEND preview snapshot for project-a.
        envelope=snapshot(self.f,revision=1)
        entry=envelope["payload"]["previews"][0]
        entry["manifest"]["execution_scope"]="TRUSTED_CUSTOMER_FRONTEND"
        entry["manifest_sha256"]=digest(canonical(entry["manifest"]))
        envelope["signature"]=hmac.new(
            self.f.auth,canonical(envelope["payload"]),hashlib.sha256
        ).hexdigest()
        import_snapshot(self.f.c,envelope,self.f.auth)

    def request_json(self,path,body=None,headers=None,method=None):
        status,h,raw=self.f.request(path,body,headers,method)
        data=json.loads(raw) if raw else {}
        return status,h,data

    def http_login(self):
        status,h,data=self.request_json(
            "api/login",{"email":"owner@example.com","password":"correct-password-123"}
        )
        self.assertEqual(status,200)
        self.assertIn("csrf",data)
        self.assertNotIn("token",data)
        cookie=h["Set-Cookie"].split(";",1)[0]
        self.assertTrue(cookie.startswith(COOKIE+"="))
        return {"Cookie":cookie,"X-CSRF-Token":data["csrf"]}

    def test_customer_journey_real_python_http(self):
        f=self.f
        auth=self.http_login()

        status,_,me=self.request_json("api/me",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual([p["id"] for p in me["projects"]],["project-a"])
        self.assertEqual(me["projects"][0]["tenant"],"tenant-a")
        self.assertEqual(me["projects"][0]["customer"],"customer-a")
        self.assertEqual(me["projects"][0]["role"],"OWNER")

        self.assertEqual(self.request_json("api/checklist/project-a",headers=auth)[0],200)
        self.assertEqual(self.request_json("api/checklist/project-b",headers=auth)[0],403)

        status,_,listing=self.request_json("api/previews/project-a",headers=auth)
        self.assertEqual(status,200)
        page=next(p for p in listing["pages"] if p["path"]=="/preview/consumer/")
        self.assertEqual(page["sha256"],PAGE_SHA)
        self.assertTrue(page["url"].startswith("/customer/center/preview/project-a/"))

        before=f.c.db.execute("SELECT count(*) FROM preview_serves").fetchone()[0]
        preview_path=page["url"].removeprefix("/customer/center/")
        status,headers,raw=f.request(preview_path,headers=auth)
        self.assertEqual(status,200)
        self.assertIn(b"feedback.js",raw)
        self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])
        after=f.c.db.execute("SELECT count(*) FROM preview_serves").fetchone()[0]
        self.assertEqual(after,before+1)

        status,_,msg=self.request_json(
            "api/message",{"project":"project-a","body":"SaaS synthetic customer question"},auth
        )
        self.assertEqual(status,200)
        self.assertEqual(msg["status"],"ARCHIVED")
        status,_,messages=self.request_json("api/messages/project-a",headers=auth)
        self.assertEqual(status,200)
        self.assertTrue(any(m["body"]=="SaaS synthetic customer question" for m in messages["messages"]))

        legacy={"project":"project-a","page":"/preview/consumer/","version":PAGE_SHA,
                "text":"SaaS synthetic feedback","intent":"RECTIFICATION"}
        status,_,created=self.request_json("api/change_submit",legacy,auth)
        self.assertEqual(status,200)
        self.assertEqual(created["state"],"REQUESTED")
        status,_,cases=self.request_json("api/changes/project-a",headers=auth)
        self.assertEqual(status,200)
        match=next(c for c in cases["cases"] if c["id"]==created["id"])
        self.assertEqual(match["events"][0]["payload"]["request"],"SaaS synthetic feedback")
        self.assertEqual(match["events"][0]["payload"]["page_sha256"],PAGE_SHA)

        idem={**legacy,"text":"SaaS synthetic idempotent feedback",
              "idempotency_key":"SaaS_frontend_test_key_001"}
        s1,_,r1=self.request_json("api/change_submit_idempotent",idem,auth)
        s2,_,r2=self.request_json("api/change_submit_idempotent",idem,auth)
        self.assertEqual((s1,s2),(200,200))
        self.assertEqual((r1["id"],r1["event_id"]),(r2["id"],r2["event_id"]))
        conflict={**idem,"text":"same key different body"}
        self.assertEqual(self.request_json("api/change_submit_idempotent",conflict,auth)[0],409)

        other_headers={"Cookie":COOKIE+"="+f.users["other"]["token"],
                       "X-CSRF-Token":f.users["other"]["csrf"]}
        self.assertEqual(self.request_json("api/changes/project-a",headers=other_headers)[0],403)

    def test_signed_delivery_current_preview_and_retest_real_python_http(self):
        f=self.f
        auth=self.http_login()
        service=Changes(f.c)
        path="/project/consumer/"

        body={"project":"project-a","page":path,"version":PAGE_SHA,
              "text":"move synthetic button","intent":"RECTIFICATION"}
        status,_,request=self.request_json("api/change_submit",body,auth)
        self.assertEqual(status,200)

        assessed=service.assess(
            f.reviewer,"project-a",request["id"],request["revision"],
            "IN_SCOPE_SMALL",10,[],[],"synthetic free fix"
        )
        self.assertEqual(assessed["state"],"FREE_APPROVED")
        request_sha=service._request_sha(service._events(f.owner,"project-a",request["id"]))

        envelope=snapshot(f,revision=2)
        data=envelope["payload"]
        entry=data["previews"][0]
        new_bytes=(b'<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1">'
                   b'<title>SaaS adjusted private preview</title><body><h1>Adjusted</h1></body></html>')
        new_sha=digest(new_bytes)
        entry["manifest"]["execution_scope"]="TRUSTED_CUSTOMER_FRONTEND"
        entry["manifest"]["pages"]=[{"path":path,"sha256":new_sha}]
        entry["manifest_sha256"]=digest(canonical(entry["manifest"]))
        entry["blobs"]={new_sha:base64.b64encode(new_bytes).decode()}
        delivery={"project":"project-a","case":request["id"],"request_sha256":request_sha,
                  "page":path,"before_sha256":PAGE_SHA,"after_sha256":new_sha,
                  "summary":"synthetic delivery","test_report_sha256":"c"*64,
                  "deployment_receipt_sha256":"d"*64,"published_at":f.now}
        data["deliveries"]=[delivery]
        envelope["signature"]=hmac.new(f.auth,canonical(data),hashlib.sha256).hexdigest()
        import_snapshot(f.c,envelope,f.auth)

        status,_,listing=self.request_json("api/previews/project-a",headers=auth)
        self.assertEqual(status,200)
        current=next(p for p in listing["pages"] if p["path"]==path)
        self.assertEqual(current["sha256"],new_sha)

        preview_path=current["url"].removeprefix("/customer/center/")
        self.assertEqual(f.request(preview_path,headers=auth)[0],200)
        served=f.c.db.execute(
            "SELECT count(*) FROM preview_serves WHERE project=? AND page_sha256=?",
            ("project-a",new_sha)
        ).fetchone()[0]
        self.assertGreaterEqual(served,1)

        status,_,updates=self.request_json(
            "api/change_updates",{"project":"project-a","page":path,"version":new_sha},auth
        )
        self.assertEqual(status,200)
        self.assertEqual(len(updates["updates"]),1)
        update=updates["updates"][0]
        self.assertEqual(update["before_sha256"],PAGE_SHA)
        self.assertEqual(update["after_sha256"],new_sha)
        self.assertEqual(update["case"],request["id"])
        self.assertEqual(update["state"],"AWAIT_RETEST")

        retest={"project":"project-a","case":request["id"],"revision":update["revision"],
                "page":path,"version":new_sha,"delivery_sha256":update["delivery_sha256"],
                "action":"ACCEPT","reason":"synthetic retest accepted"}
        status,_,result=self.request_json("api/change_retest",retest,auth)
        self.assertEqual(status,200)
        self.assertEqual(result["state"],"RETEST_ACCEPTED")
        self.assertFalse(result["automatic_charge"])

        status,_,cases=self.request_json("api/changes/project-a",headers=auth)
        self.assertEqual(status,200)
        case=next(c for c in cases["cases"] if c["id"]==request["id"])
        self.assertEqual(case["events"][-1]["kind"],"RETEST")
        self.assertEqual(case["events"][-1]["payload"]["state"],"RETEST_ACCEPTED")


if __name__=="__main__":
    unittest.main(verbosity=2)
