"""Isolated P2 coordinator. No production Grant, root access or shell execution.

Adapters are trusted Python objects supplied by the application, never loaded
from task requests. Each adapter must implement execute/inspect/recover.
"""
import argparse
import hashlib
import importlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from .journal import Journal, Hold, canonical, digest, require

HEX = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[a-zA-Z0-9_.-]{1,128}$")
STATES = ("COMMITTED", "NO_EFFECT", "HOLD")

def _valid(request):
    require(type(request) is dict and request.get("schema") == 1
            and request.get("scope") == "ISOLATED_TEST_ONLY", "SCOPE")
    for key in ("installation_id", "batch_id", "attempt_id"):
        require(type(request.get(key)) is str and ID.fullmatch(request[key]), "IDENTITY")
    require(type(request.get("root")) is str and
            os.path.isabs(request["root"]) and
            os.path.normpath(request["root"]) == request["root"], "ROOT")
    require(type(request.get("inputs")) is dict, "INPUTS")
    require(type(request.get("version")) is str and
            HEX.fullmatch(request["version"]), "VERSION")
    require(type(request.get("deadline_utc")) is int and
            request["deadline_utc"] > 0, "DEADLINE")
    return request

def _receipt(request, status, evidence=None, error=None):
    return {"schema": 1, "scope": "ISOLATED_TEST_ONLY",
            "installation_id": request["installation_id"],
            "batch_id": request["batch_id"], "attempt_id": request["attempt_id"],
            "status": status, "receipt": evidence, "error": error}

def _check_reply(request, reply, expected):
    require(type(reply) is dict and reply.get("schema") == 1
            and reply.get("scope") == "ISOLATED_TEST_ONLY", "REPLY_SCHEMA")
    for key in ("installation_id", "batch_id", "attempt_id"):
        require(reply.get(key) == request[key], "REPLY_IDENTITY")
    require(reply.get("status") == expected, "REPLY_STATUS")
    rec = reply.get("receipt")
    require(type(rec) is dict and
            type(rec.get("path")) is str and os.path.isabs(rec["path"]) and
            type(rec.get("sha256")) is str and HEX.fullmatch(rec["sha256"]),
            "RECEIPT_FORMAT")
    # Only read receipts in the owned root; never accept an arbitrary path.
    p = Path(rec["path"])
    root = Path(request["root"]).resolve()
    require(root in p.parents and p.resolve() == p and p.is_file() and
            not p.is_symlink(), "RECEIPT_LOCATION")
    content = p.read_bytes()
    require(len(content) <= 262144 and
            hashlib.sha256(content).hexdigest() == rec["sha256"],
            "RECEIPT_DIGEST")
    return rec

class Coordinator:
    def __init__(self, root, plan, adapters=None, now=None):
        self.root = root
        self.plan = plan
        self.adapters = adapters or {}
        self.now = now or (lambda: int(time.time()))
        self.journal = None

    def __enter__(self):
        self.journal = Journal(self.root, self.plan)
        db = self.journal.db
        db.execute("CREATE TABLE IF NOT EXISTS coordinator_requests ("
                   "attempt TEXT PRIMARY KEY, installation TEXT NOT NULL,"
                   "batch TEXT NOT NULL, request_hash TEXT NOT NULL,"
                   "request_json TEXT NOT NULL, created INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS coordinator_events ("
                   "id INTEGER PRIMARY KEY, attempt TEXT NOT NULL,"
                   "kind TEXT NOT NULL, observed INTEGER NOT NULL,"
                   "evidence TEXT NOT NULL)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS coordinator_once "
                   "ON coordinator_events(attempt,kind)")
        db.execute("CREATE TABLE IF NOT EXISTS coordinator_outbox ("
                   "id TEXT PRIMARY KEY, attempt TEXT NOT NULL, event TEXT NOT NULL,"
                   "state TEXT NOT NULL, detail TEXT NOT NULL)")
        return self

    def __exit__(self, *args):
        self.journal.close()
        self.journal = None

    def _adapter(self, batch):
        adapter = self.adapters.get(batch)
        require(adapter is not None and all(callable(getattr(adapter, x, None))
                    for x in ("execute", "inspect", "recover")),
                "ADAPTER_UNAVAILABLE")
        return adapter

    def _stored(self, attempt):
        row = self.journal.db.execute(
            "SELECT request_json FROM coordinator_requests WHERE attempt=?",
            (attempt,)).fetchone()
        return json.loads(row[0]) if row else None

    def _store(self, request):
        old = self._stored(request["attempt_id"])
        require(old is None or digest(old) == digest(request), "ATTEMPT_CONFLICT")
        if old is None:
            self.journal.db.execute(
                "INSERT INTO coordinator_requests VALUES(?,?,?,?,?,?)",
                (request["attempt_id"], request["installation_id"],
                 request["batch_id"], digest(request),
                 canonical(request).decode("ascii"), self.now()))
        return old is not None

    def _verify_previous(self, batch, evidence):
        prior = self.journal.db.execute(
            "SELECT request_json FROM coordinator_requests "
            "WHERE batch=? AND installation=? ORDER BY created DESC LIMIT 1",
            (batch, self._installation)).fetchone()
        if not prior:
            return False
        request = json.loads(prior[0])
        try:
            reply = self._adapter(batch).inspect(request)
            _check_reply(request, reply, "COMMITTED")
            return evidence.get("receipt") == reply["receipt"]
        except (OSError, ValueError, Hold):
            return False

    def _validate_plan(self, request):
        require(request["batch_id"] in self.plan["batches"], "UNKNOWN_BATCH")
        require(self.plan["release"] == request["version"], "RELEASE_MISMATCH")
        require(request["root"] == self.root, "ROOT_MISMATCH")

    def execute(self, request):
        _valid(request)
        self._validate_plan(request)
        self._installation = request["installation_id"]
        old = self._stored(request["attempt_id"])
        require(old is None or digest(old) == digest(request), "ATTEMPT_CONFLICT")
        row = self.journal.latest(request["batch_id"])
        if row and row[1] == "COMMITTED":
            return _receipt(request, "HOLD", error={"code":"ALREADY_COMMITTED"})
        if old:
            return self.recover(request)
        require(self.now() <= request["deadline_utc"], "EXPIRED")
        # The durable quota is shared by all batches of this installation.
        count = self.journal.db.execute(
            "SELECT COUNT(*) FROM coordinator_requests WHERE installation=?",
            (request["installation_id"],)).fetchone()[0]
        require(count < 5, "ATTEMPTS_EXHAUSTED")
        self._adapter(request["batch_id"])
        # A crash after storing request but before journal.begin is treated as
        # unknown, never as a new permission to launch another process.
        self._store(request)
        self.journal.begin(request["batch_id"], request["attempt_id"],
                           self._verify_previous)
        return self._reconcile(request, launch=True)

    def _reconcile(self, request, launch=False):
        adapter = self._adapter(request["batch_id"])
        try:
            if launch:
                result = adapter.execute(request)
            else:
                result = adapter.inspect(request)
            if not launch and result.get("status") == "HOLD":
                result = adapter.recover(request)
            if result.get("status") == "COMMITTED":
                rec = _check_reply(request, result, "COMMITTED")
                # Commit requires independent inspect/readback.
                checked = adapter.inspect(request)
                _check_reply(request, checked, "COMMITTED")
                require(checked["receipt"] == rec, "READBACK_CONFLICT")
                evidence = {"receipt": rec, "request_sha256": digest(request)}
                self.journal.finish(request["batch_id"], request["attempt_id"],
                                    evidence, lambda *unused: True)
                self.journal.db.execute(
                    "INSERT OR IGNORE INTO coordinator_events(attempt,kind,observed,evidence) VALUES(?,?,?,?)",
                    (request["attempt_id"],"COMPLETE",self.now(),canonical(evidence).decode("ascii")))
                return _receipt(request, "COMMITTED", rec)
            if result.get("status") == "NO_EFFECT":
                rec = _check_reply(request, result, "NO_EFFECT")
                checked = adapter.inspect(request)
                _check_reply(request, checked, "NO_EFFECT")
                require(checked["receipt"] == rec, "NO_EFFECT_CONFLICT")
                self.journal.reconcile_no_effect(
                    request["batch_id"], request["attempt_id"],
                    {"receipt":rec,"request_sha256":digest(request)},
                    lambda *unused: True)
                self.journal.db.execute(
                    "INSERT OR IGNORE INTO coordinator_events(attempt,kind,observed,evidence) VALUES(?,?,?,?)",
                    (request["attempt_id"],"FAIL",self.now(),
                     canonical({"result":"VERIFIED_NO_EFFECT"}).decode("ascii")))
                return _receipt(request, "NO_EFFECT", rec)
            return _receipt(request, "HOLD", error={"code":"UNKNOWN_EFFECT"})
        except (OSError, ValueError, KeyError, Hold) as exc:
            return _receipt(request, "HOLD",
                            error={"code":"RECONCILE_REQUIRED",
                                   "detail":type(exc).__name__})

    def inspect(self, request):
        _valid(request)
        self._validate_plan(request)
        old = self._stored(request["attempt_id"])
        require(old is not None and digest(old) == digest(request), "NOT_FOUND")
        row = self.journal.latest(request["batch_id"])
        if row and row[0] == request["attempt_id"] and row[1] == "COMMITTED":
            # Durable commit is not sufficient without live readback.
            reply = self._adapter(request["batch_id"]).inspect(request)
            rec = _check_reply(request, reply, "COMMITTED")
            require(json.loads(row[2]).get("receipt") == rec, "READBACK_DRIFT")
            return _receipt(request, "COMMITTED", rec)
        if row and row[0] == request["attempt_id"] and row[1] == "RETRYABLE":
            reply = self._adapter(request["batch_id"]).inspect(request)
            return _receipt(request, "NO_EFFECT",
                            _check_reply(request, reply, "NO_EFFECT"))
        return _receipt(request, "HOLD", error={"code":"IN_FLIGHT_OR_UNKNOWN"})

    def recover(self, request):
        _valid(request)
        self._validate_plan(request)
        old = self._stored(request["attempt_id"])
        require(old is not None and digest(old) == digest(request), "NOT_FOUND")
        row = self.journal.latest(request["batch_id"])
        if row and row[0] == request["attempt_id"] and row[1] in ("COMMITTED", "RETRYABLE"):
            return self.inspect(request)
        if row and row[0] == request["attempt_id"] and row[1] == "RUNNING":
            return self._reconcile(request, launch=False)
        return _receipt(request, "HOLD", error={"code":"UNSTARTED_OR_CONFLICT"})

    def tick(self):
        """Deterministic, idempotent timeout events; never claims wake ACK."""
        output = []
        for attempt, raw, created in self.journal.db.execute(
                "SELECT attempt,request_json,created FROM coordinator_requests"):
            request = json.loads(raw)
            events = self.journal.db.execute(
                "SELECT kind,observed FROM coordinator_events WHERE attempt=?",
                (attempt,)).fetchall()
            marks = dict(events)
            if "COMPLETE" in marks or "FAIL" in marks:
                continue
            # Heartbeats are intentionally ignored; only PROGRESS counts.
            progress = marks.get("PROGRESS", marks.get("STARTED", created))
            milestones = (("NO_RECEIPT_5M", self.now()-created >= 300 and "RECEIVED" not in marks),
                          ("NO_START_15M", self.now()-created >= 900 and "STARTED" not in marks),
                          ("NO_PROGRESS_15M", self.now()-progress >= 900),
                          ("BLOCKED_30M", self.now()-created >= 1800))
            for event, due in milestones:
                if not due:
                    continue
                key = digest([attempt,event])
                self.journal.db.execute(
                    "INSERT OR IGNORE INTO coordinator_outbox VALUES(?,?,?,?,?)",
                    (key,attempt,event,"UNAVAILABLE",
                     canonical({"provider":"UNAVAILABLE","next":"inspect/reconcile",
                                "deadline_utc":request["deadline_utc"]}).decode("ascii")))
                output.append({"attempt_id":attempt,"event":event,
                               "delivery":"UNAVAILABLE","id":key})
        return output

def cli():
    parser = argparse.ArgumentParser(description="Isolated P2 coordinator")
    parser.add_argument("action", choices=("execute","inspect","recover","tick"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--request")
    args = parser.parse_args()
    with open(args.plan, encoding="utf-8") as source:
        plan = json.load(source)
    request = None
    if args.action != "tick":
        require(bool(args.request), "REQUEST_REQUIRED")
        with open(args.request, encoding="utf-8") as source:
            request = json.load(source)
    try:
        with Coordinator(args.root, plan) as c:
            result = c.tick() if args.action == "tick" else getattr(c,args.action)(request)
        print(json.dumps(result,sort_keys=True))
        if args.action != "tick" and result["status"] == "HOLD":
            return 2
        return 0
    except (Hold, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"status":"HOLD","error":{"code":str(exc)}}))
        return 2

if __name__ == "__main__":
    sys.exit(cli())
