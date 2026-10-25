"""Isolated P2 coordinator. No production Grant, root access or shell execution.

Adapters are trusted Python objects supplied by the application, never loaded
from task requests. Each adapter must implement execute/inspect/recover.
"""
import argparse
import hashlib
import multiprocessing
import json
import os
import re
import sqlite3
import stat
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

def _check_receipt_reference(request, rec):
    require(type(rec) is dict and
            type(rec.get("path")) is str and os.path.isabs(rec["path"]) and
            type(rec.get("sha256")) is str and HEX.fullmatch(rec["sha256"]),
            "RECEIPT_FORMAT")
    p = Path(rec["path"])
    root = Path(request["root"]).resolve()
    require(root in p.parents and p.resolve() == p and p.is_file() and
            not p.is_symlink(), "RECEIPT_LOCATION")
    content = p.read_bytes()
    require(len(content) <= 262144 and
            hashlib.sha256(content).hexdigest() == rec["sha256"],
            "RECEIPT_DIGEST")
    return rec

def _check_reply(request, reply, expected):
    require(type(reply) is dict and reply.get("schema") == 1
            and reply.get("scope") == "ISOLATED_TEST_ONLY", "REPLY_SCHEMA")
    for key in ("installation_id", "batch_id", "attempt_id"):
        require(reply.get(key) == request[key], "REPLY_IDENTITY")
    require(reply.get("status") == expected, "REPLY_STATUS")
    return _check_receipt_reference(request, reply.get("receipt"))

def _read_log_reference(root, candidate):
    """Read a bounded regular file by descriptor traversal inside root only."""
    require(type(candidate) is str and os.path.isabs(candidate),
            "FAILURE_LOG_NOT_ABSOLUTE")
    require("\x00" not in candidate, "FAILURE_LOG_INVALID_PATH")
    require(os.path.normpath(candidate) == candidate, "FAILURE_LOG_DOTDOT")
    root_path = os.path.normpath(root)
    prefix = root_path.rstrip("/") + "/"
    require(candidate.startswith(prefix), "FAILURE_LOG_OUTSIDE_ROOT")
    rel = candidate[len(prefix):]
    require(rel and rel != "." and not rel.startswith("../"), "FAILURE_LOG_OUTSIDE_ROOT")
    parts = rel.split("/")
    require(all(part not in ("", ".", "..") for part in parts), "FAILURE_LOG_DOTDOT")

    fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        # O_NONBLOCK prevents a FIFO/device-like leaf from stalling before
        # fstat can reject it as non-regular.
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=fd)
        try:
            info = os.fstat(leaf)
            require(stat.S_ISREG(info.st_mode), "FAILURE_LOG_NOT_REGULAR")
            require(info.st_size <= 1048576, "FAILURE_LOG_TOO_LARGE")
            chunks = []
            remaining = info.st_size
            while remaining:
                block = os.read(leaf, min(65536, remaining))
                require(block, "FAILURE_LOG_SHORT_READ")
                chunks.append(block)
                remaining -= len(block)
            content = b"".join(chunks)
            require(len(content) == info.st_size, "FAILURE_LOG_SHORT_READ")
            return content
        finally:
            os.close(leaf)
    finally:
        os.close(fd)

class Coordinator:
    def __init__(self, root, plan, adapters=None, now=None, component_roots=None, grant=None):
        self.root = root
        self.plan = plan
        self.adapters = adapters or {}
        self.component_roots = component_roots or {}
        self.grant = grant
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
        # Legacy schema briefly enforced one event per (attempt,kind), but
        # PROGRESS is intentionally repeatable. Drop the legacy index before
        # any operation that could validate it against preserved history.
        db.execute("DROP INDEX IF EXISTS coordinator_once")
        db.execute("CREATE TABLE IF NOT EXISTS coordinator_outbox ("
                   "id TEXT PRIMARY KEY, attempt TEXT NOT NULL, event TEXT NOT NULL,"
                   "state TEXT NOT NULL, detail TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS coordinator_outbox_links ("
                   "stable_id TEXT PRIMARY KEY, legacy_id TEXT NOT NULL UNIQUE,"
                   "installation TEXT NOT NULL, event TEXT NOT NULL,"
                   "round_id TEXT NOT NULL, linked INTEGER NOT NULL)")
        # Historic isolated round rows are preserved, but are not admission or quota.
        db.execute("CREATE TABLE IF NOT EXISTS coordinator_failures (seq INTEGER PRIMARY KEY, installation TEXT, cause TEXT, observed INTEGER, evidence TEXT)")
        cols = [x[1] for x in db.execute("PRAGMA table_info(coordinator_failures)")]
        if "event_key" not in cols:
            db.execute("ALTER TABLE coordinator_failures ADD COLUMN event_key TEXT")
        if "compatibility" not in cols:
            db.execute("ALTER TABLE coordinator_failures ADD COLUMN compatibility TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS coordinator_failure_event_key ON coordinator_failures(event_key)")
        self._migrate_legacy_failures()
        return self

    def __exit__(self, *args):
        self.journal.close()
        self.journal = None

    def _failure_key(self, request, event_id):
        return digest([request["installation_id"],
                       request.get("round_id", "DEFAULT"),
                       request["batch_id"], request["attempt_id"], event_id])

    def _migrate_legacy_failures(self):
        """Annotate legacy rows without rewriting their evidence or first UTC."""
        db = self.journal.db
        rows = db.execute(
            "SELECT seq,installation,cause,evidence,event_key,compatibility "
            "FROM coordinator_failures ORDER BY seq").fetchall()
        for seq, installation, cause, raw, event_key, compatibility in rows:
            if event_key is not None or compatibility is not None:
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                db.execute("UPDATE coordinator_failures SET compatibility='UNKNOWN' WHERE seq=?",
                           (seq,))
                continue
            attempt = data.get("attempt_id")
            event_id = data.get("event_id")
            request = self._stored(attempt) if type(attempt) is str else None
            if (request is not None and request.get("installation_id") == installation
                    and type(event_id) is str and ID.fullmatch(event_id)
                    and data.get("request_sha256", digest(request)) == digest(request)):
                key = self._failure_key(request, event_id)
                existing = db.execute(
                    "SELECT seq FROM coordinator_failures WHERE event_key=?",
                    (key,)).fetchone()
                if existing is None:
                    db.execute(
                        "UPDATE coordinator_failures SET event_key=?,compatibility='MIGRATED_EXPLICIT' "
                        "WHERE seq=?", (key, seq))
                else:
                    db.execute(
                        "UPDATE coordinator_failures SET compatibility='DUPLICATE_KNOWN' WHERE seq=?",
                        (seq,))
            elif (request is not None and request.get("installation_id") == installation
                    and data.get("request_sha256") == digest(request)
                    and event_id is None):
                # Old automatic records had only attempt + request digest. They
                # are matchable only by an automatic redelivery with the same
                # persisted cause; explicit events must never be folded here.
                db.execute(
                    "UPDATE coordinator_failures SET compatibility='LEGACY_AUTO' WHERE seq=?",
                    (seq,))
            else:
                db.execute(
                    "UPDATE coordinator_failures SET compatibility='UNKNOWN' WHERE seq=?",
                    (seq,))

    def _match_legacy_failure(self, request, cause, event_id,
                              allow_identity_merge, key):
        rows = self.journal.db.execute(
            "SELECT seq,evidence,compatibility FROM coordinator_failures "
            "WHERE installation=? AND cause=? AND event_key IS NULL ORDER BY seq",
            (request["installation_id"], cause)).fetchall()
        for seq, raw, compatibility in rows:
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if (allow_identity_merge and compatibility == "LEGACY_AUTO"
                    and data.get("attempt_id") == request["attempt_id"]
                    and data.get("request_sha256") == digest(request)
                    and data.get("event_id") is None):
                self.journal.db.execute(
                    "UPDATE coordinator_failures SET event_key=?,"
                    "compatibility='MIGRATED_AUTO_MATCH' WHERE seq=?",
                    (key, seq))
                return True
            if (not allow_identity_merge
                    and data.get("attempt_id") == request["attempt_id"]
                    and data.get("event_id") == event_id
                    and data.get("request_sha256") in (None, digest(request))):
                self.journal.db.execute(
                    "UPDATE coordinator_failures SET event_key=?,"
                    "compatibility='MIGRATED_EXPLICIT' WHERE seq=?",
                    (key, seq))
                return True
        return False

    def _counted_failure_groups(self, installation=None):
        """Return threshold groups using only failures proven unique."""
        groups = {}
        rows = self.journal.db.execute(
            "SELECT installation,cause,observed,evidence,event_key,compatibility "
            "FROM coordinator_failures ORDER BY seq").fetchall()
        for inst, cause, observed, raw, event_key, compatibility in rows:
            if installation is not None and inst != installation:
                continue
            # NULL-key legacy rows are not proven unique. DUPLICATE_KNOWN is
            # retained as evidence but never contributes to escalation.
            if event_key is None or compatibility == "DUPLICATE_KNOWN":
                continue
            try:
                evidence = json.loads(raw)
            except ValueError:
                evidence = {}
            rid = evidence.get("round_id")
            if not rid:
                attempt = evidence.get("attempt_id")
                stored = self._stored(attempt) if attempt else None
                rid = stored.get("round_id","DEFAULT") if stored else "DEFAULT"
            round_key = (inst,rid)
            state = groups.setdefault(
                round_key,{"count":0,"first":observed,"causes":{}})
            state["count"] += 1
            state["first"] = min(state["first"],observed)
            root_cause = evidence.get("root_cause")
            if type(root_cause) is not str or not ID.fullmatch(root_cause):
                root_cause = cause
            state["causes"][root_cause] = min(
                state["causes"].get(root_cause,observed),observed)
        return groups

    def _infer_legacy_outbox_round(self, installation, event, old):
        """Infer a missing legacy round only when exactly one round fits."""
        first = old.get("first_utc")
        if type(first) is not int:
            return None
        candidates = []
        for (inst,rid), state in self._counted_failure_groups(
                installation).items():
            if state["first"] != first:
                continue
            if event == "CHANGE_METHOD_30M":
                cause = old.get("cause")
                if type(cause) is not str or state["causes"].get(cause) != first:
                    continue
            candidates.append(rid)
        return candidates[0] if len(candidates) == 1 else None

    def _failure_outbox_insert(self, key, installation, event, detail):
        db = self.journal.db
        if (db.execute("SELECT 1 FROM coordinator_outbox WHERE id=?",
                       (key,)).fetchone()
                or db.execute(
                    "SELECT 1 FROM coordinator_outbox_links WHERE stable_id=?",
                    (key,)).fetchone()):
            return False
        for old_id, raw in db.execute(
                "SELECT id,detail FROM coordinator_outbox "
                "WHERE attempt=? AND event=?", (installation,event)).fetchall():
            try:
                old = json.loads(raw)
            except ValueError:
                continue
            old_round = old.get("round_id")
            if old_round is None:
                old_round = self._infer_legacy_outbox_round(
                    installation,event,old)
            if old_round != detail.get("round_id"):
                continue
            matched = False
            if event == "CHANGE_METHOD_30M":
                matched = (old.get("cause") == detail.get("cause")
                           and old.get("first_utc") == detail.get("first_utc"))
            elif event == "REPORT_DOTS_10_OR_60":
                # Failure count may grow after the legacy report. Once its
                # exact round/first failure are identified, it remains the same
                # notification and must not be re-emitted.
                matched = old.get("first_utc") == detail.get("first_utc")
            if matched:
                db.execute(
                    "INSERT OR IGNORE INTO coordinator_outbox_links "
                    "VALUES(?,?,?,?,?,?)",
                    (key,old_id,installation,event,detail["round_id"],self.now()))
                return False
        db.execute("INSERT INTO coordinator_outbox VALUES (?,?,?,?,?)",
                   (key,installation,event,"UNAVAILABLE",
                    canonical(detail).decode("ascii")))
        return True

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
            reply = self._call(self._adapter(batch),"inspect",request,10)
            _check_reply(request, reply, "COMMITTED")
            return self._matches(request,evidence["receipt"],reply["receipt"])
        except (OSError, ValueError, Hold):
            return False

    def _validate_plan(self, request):
        require(request["batch_id"] in self.plan["batches"], "UNKNOWN_BATCH")
        require(self.plan["release"] == request["version"], "RELEASE_MISMATCH")
        require(request["batch_id"] in self.component_roots, "ROOT_UNBOUND")
        require(request["root"] == self.component_roots[request["batch_id"]], "ROOT_MISMATCH")
        require(request["root"] != self.root, "ROOT_SHARED")

    def _matches(self, request, commit, observed):
        if commit == observed: return True
        try:
            data = json.loads(Path(observed["path"]).read_text())
            if (data.get("request_sha256") == digest(request)
                    and data.get("commit_receipt_sha256") == commit["sha256"]
                    and data.get("effect_verified") is True):
                return True
            original = json.loads(Path(commit["path"]).read_text())
            operation = original.get("operation_id")
            config = original.get("config_sha256")
            return (type(operation) is str and HEX.fullmatch(operation)
                    and type(config) is str and HEX.fullmatch(config)
                    and original.get("status") == "COMMITTED"
                    and data.get("status") == "COMMITTED"
                    and data.get("operation_id") == operation
                    and data.get("config_sha256") == config
                    and data.get("commit_receipt") == commit
                    and all(data.get(k) == request[k] for k in
                            ("installation_id","batch_id","attempt_id")))
        except (OSError, ValueError, KeyError):
            return False

    def _commit_from_reply(self, request, reply, observed):
        """Return the immutable original commit receipt for a COMMITTED reply.

        Runtime observations have a new observation receipt on every inspect,
        while commit_receipt remains the immutable original start receipt.
        Components that use one immutable receipt for both commit and inspect
        legitimately omit commit_receipt and therefore fall back to observed.
        """
        commit = reply.get("commit_receipt")
        if commit is None:
            return observed
        _check_receipt_reference(request, commit)
        require(self._matches(request, commit, observed), "COMMIT_LINK_CONFLICT")
        return commit

    def _call(self, adapter, method, request, seconds):
        parent, child = multiprocessing.Pipe(False)
        def worker():
            parent.close()
            try: child.send(("OK", getattr(adapter,method)(request)))
            except BaseException as e: child.send(("ERROR",type(e).__name__))
            finally: child.close()
        process = multiprocessing.Process(target=worker)
        process.start()
        child.close()
        try:
            if not parent.poll(min(86400,max(0,seconds))):
                process.terminate()
                process.join(2)
                raise Hold("TIMEOUT_UNKNOWN")
            status, value = parent.recv()
            require(status == "OK", "ADAPTER_ERROR")
            return value
        finally:
            parent.close()
            if process.is_alive(): process.terminate()
            process.join(2)

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
        self._adapter(request["batch_id"])
        # A crash after storing request but before journal.begin is treated as
        # unknown, never as a new permission to launch another process.
        self._store(request)
        self.journal.begin(request["batch_id"], request["attempt_id"],
                           self._verify_previous)
        return self._reconcile(request, launch=True)

    def _record_failure(self, request, cause, evidence, event_id,
                        allow_identity_merge=False):
        """Append one genuine failure, preserving legacy rows and first UTC.

        Identity comes from an actual failed operation/event, never the changing
        observation receipt or current wall clock. No dedupe based on cause alone.
        """
        _valid(request)
        require(self._stored(request["attempt_id"]) == request, "FAILURE_IDENTITY")
        require(type(cause) is str and ID.fullmatch(cause), "FAILURE_CAUSE")
        require(type(event_id) is str and ID.fullmatch(event_id), "FAILURE_EVENT_ID")
        require(type(evidence) is dict and len(canonical(evidence)) <= 8192, "FAILURE_EVIDENCE")
        key = self._failure_key(request, event_id)
        if self.journal.db.execute(
                "SELECT 1 FROM coordinator_failures WHERE event_key=?", (key,)).fetchone():
            return False
        if self._match_legacy_failure(request,cause,event_id,
                                      allow_identity_merge,key):
            return False

        # If the first failure was captured before the component identity was
        # observable, conservatively attach the later real identity to that
        # exact automatic placeholder. Explicit UNKNOWN events and other
        # attempts are never merged.
        merge_row = None
        known_operation = evidence.get("operation_id")
        if (allow_identity_merge and type(known_operation) is str
                and known_operation != "UNKNOWN"):
            unknown_event = "auto-" + digest([request["attempt_id"], "UNKNOWN"])[:32]
            unknown_key = digest([request["installation_id"],
                                  request.get("round_id", "DEFAULT"),
                                  request["batch_id"], request["attempt_id"],
                                  unknown_event])
            merge_row = self.journal.db.execute(
                "SELECT seq,evidence FROM coordinator_failures WHERE event_key=?",
                (unknown_key,)).fetchone()

        # Preserve original data and digest only references which are verifiable.
        details = dict(evidence)
        references = {}
        for label in ("receipt", "commit_receipt"):
            rec = evidence.get(label)
            if rec is None:
                references[label] = {"status":"UNKNOWN"}
            else:
                try:
                    _check_receipt_reference(request, rec)
                    references[label] = {"status":"VERIFIED", "path":rec["path"],
                                         "sha256":rec["sha256"]}
                except (Hold, OSError, ValueError, KeyError):
                    references[label] = {"status":"UNKNOWN"}
        log = evidence.get("log")
        if type(log) is str:
            try:
                content = _read_log_reference(request["root"], log)
                references["log"] = {"status":"VERIFIED","path":log,
                                     "sha256":hashlib.sha256(content).hexdigest()}
            except Hold as exc:
                references["log"] = {"status":"UNKNOWN","reason":str(exc)}
            except OSError as exc:
                references["log"] = {"status":"UNKNOWN",
                                     "reason":"FAILURE_LOG_OSERROR_" + str(exc.errno)}
        else:
            references["log"] = {"status":"UNKNOWN","reason":"FAILURE_LOG_MISSING"}
        saved = {"event_id":event_id,"event_key":key,"cause":cause,
                 "root_cause":cause,
                 "installation_id":request["installation_id"],
                 "round_id":request.get("round_id","DEFAULT"),
                 "batch_id":request["batch_id"],"attempt_id":request["attempt_id"],
                 "request_sha256":digest(request),
                 "operation_id":evidence.get("operation_id") or "UNKNOWN",
                 "config_sha256":evidence.get("config_sha256") or "UNKNOWN",
                 "error":evidence.get("error",{"code":cause}),
                 "references":references, "checkpoint":evidence.get("checkpoint","UNKNOWN")}

        if merge_row is not None:
            seq, raw = merge_row
            try:
                prior = json.loads(raw)
            except ValueError:
                prior = {}
            expected_unknown = "auto-" + digest([request["attempt_id"], "UNKNOWN"])[:32]
            safe_merge = (
                prior.get("event_id") == expected_unknown
                and prior.get("operation_id") == "UNKNOWN"
                and prior.get("checkpoint") == "RECONCILE_REQUIRED"
                and prior.get("installation_id") == request["installation_id"]
                and prior.get("round_id") == request.get("round_id","DEFAULT")
                and prior.get("batch_id") == request["batch_id"]
                and prior.get("attempt_id") == request["attempt_id"]
                and prior.get("request_sha256") == digest(request))
            if safe_merge:
                resolution = prior.get("identity_resolution")
                if resolution is None:
                    prior["identity_resolution"] = {
                        "operation_id": saved["operation_id"],
                        "config_sha256": saved["config_sha256"],
                        "observed_error": saved["error"],
                        "observed_references": saved["references"]}
                    self.journal.db.execute(
                        "UPDATE coordinator_failures SET evidence=? WHERE seq=?",
                        (canonical(prior).decode("ascii"), seq))
                elif resolution.get("operation_id") != saved["operation_id"]:
                    # Conflicting later identities are distinct/unknown, never
                    # silently folded into the original event.
                    merge_row = None
                if merge_row is not None:
                    return False

        self.journal.db.execute(
            "INSERT OR IGNORE INTO coordinator_failures(installation,cause,observed,evidence,event_key) VALUES(?,?,?,?,?)",
            (request["installation_id"],cause,self.now(),canonical(saved).decode("ascii"),key))
        return True

    def _automatic_failure(self, request, cause, response=None):
        response = response if type(response) is dict else {}
        err = response.get("error")
        if type(err) is not dict:
            err = {"code":cause}
        operation = response.get("operation_id") or "UNKNOWN"
        actual = err.get("code")
        if type(actual) is not str or not ID.fullmatch(actual):
            actual = cause
        # Stable failure identity is the actual operation, not a later
        # observation/status code. Thus LAUNCH_UNKNOWN -> START_OUTCOME_UNKNOWN
        # during recovery remains one failure event and preserves first evidence.
        event_id = "auto-" + digest([request["attempt_id"], operation])[:32]
        self._record_failure(request,actual,
            {"operation_id":operation,"config_sha256":response.get("config_sha256"),
             "error":err,"receipt":response.get("receipt"),
             "commit_receipt":response.get("commit_receipt"),
             "log":err.get("log"),"checkpoint":"RECONCILE_REQUIRED"},event_id,
            allow_identity_merge=True)

    def _reconcile(self, request, launch=False):
        adapter = self._adapter(request["batch_id"])
        try:
            if launch:
                result = self._call(adapter,"execute",request,request["deadline_utc"]-self.now())
            else:
                result = self._call(adapter,"inspect",request,10)
            if not launch and result.get("status") == "HOLD":
                result = self._call(adapter,"recover",request,10)
            if result.get("status") == "COMMITTED":
                observed = _check_reply(request, result, "COMMITTED")
                # A direct execute COMMITTED reply is itself the original
                # commit receipt. During RUNNING recovery the first reply is
                # an observation, so use an explicit component commit_receipt
                # when the component contract provides one.
                commit = observed if launch else self._commit_from_reply(
                    request, result, observed)
                # Commit requires a second independent inspect/readback. A
                # fresh observation receipt may differ. Legacy trusted
                # observations can prove linkage by request/commit hashes;
                # runtime additionally exposes the exact original receipt.
                checked = self._call(adapter,"inspect",request,10)
                checked_observed = _check_reply(request, checked, "COMMITTED")
                if checked.get("commit_receipt") is not None:
                    checked_commit = _check_receipt_reference(
                        request, checked.get("commit_receipt"))
                    require(checked_commit == commit,
                            "COMMIT_RECEIPT_CONFLICT")
                require(self._matches(request,commit,checked_observed),
                        "READBACK_CONFLICT")
                evidence = {"receipt": commit,
                            "observation": observed,
                            "request_sha256": digest(request)}
                self.journal.finish(request["batch_id"], request["attempt_id"],
                                    evidence, lambda *unused: True)
                self.journal.db.execute(
                    "INSERT OR IGNORE INTO coordinator_events(attempt,kind,observed,evidence) VALUES(?,?,?,?)",
                    (request["attempt_id"],"COMPLETE",self.now(),canonical(evidence).decode("ascii")))
                return _receipt(request, "COMMITTED", commit)
            if result.get("status") == "NO_EFFECT":
                rec = _check_reply(request, result, "NO_EFFECT")
                checked = self._call(adapter,"inspect",request,10)
                _check_reply(request, checked, "NO_EFFECT")
                require(self._matches(request,rec,checked["receipt"]), "NO_EFFECT_CONFLICT")
                self.journal.reconcile_no_effect(
                    request["batch_id"], request["attempt_id"],
                    {"receipt":rec,"request_sha256":digest(request)},
                    lambda *unused: True)
                self.journal.db.execute(
                    "INSERT OR IGNORE INTO coordinator_events(attempt,kind,observed,evidence) VALUES(?,?,?,?)",
                    (request["attempt_id"],"FAIL",self.now(),
                     canonical({"result":"VERIFIED_NO_EFFECT"}).decode("ascii")))
                return _receipt(request, "NO_EFFECT", rec)
            self._automatic_failure(request,"UNKNOWN_EFFECT",result)
            return _receipt(request, "HOLD", error={"code":"UNKNOWN_EFFECT"})
        except (OSError, ValueError, KeyError, Hold) as exc:
            self._automatic_failure(request,"RECONCILE_REQUIRED",
                                    {"error":{"code":str(exc),"class":type(exc).__name__}})
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
            reply = self._call(self._adapter(request["batch_id"]),"inspect",request,10)
            if reply.get("status") != "COMMITTED":
                return _receipt(request,"HOLD",error={"code":"COMMITTED_EFFECT_DRIFT"})
            try:
                rec = _check_reply(request,reply,"COMMITTED")
                require(self._matches(request,json.loads(row[2])["receipt"],rec),"READBACK_DRIFT")
            except (Hold,OSError,ValueError,KeyError):
                return _receipt(request,"HOLD",error={"code":"READBACK_DRIFT"})
            return _receipt(request, "COMMITTED", rec)
        if row and row[0] == request["attempt_id"] and row[1] == "RETRYABLE":
            reply = self._call(self._adapter(request["batch_id"]),"inspect",request,10)
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
        if row is None:
            reply = self._call(self._adapter(request["batch_id"]),"inspect",request,10)
            if reply.get("status") == "NO_EFFECT":
                rec = _check_reply(request,reply,"NO_EFFECT")
                # No journal effect was ever started; a fresh attempt may execute after proof.
                return _receipt(request,"NO_EFFECT",rec)
            return _receipt(request,"HOLD",error={"code":"PRE_BEGIN_UNKNOWN"})
        return _receipt(request, "HOLD", error={"code":"UNSTARTED_OR_CONFLICT"})

    def event(self, request, kind, evidence):
        _valid(request)
        require(self._stored(request["attempt_id"]) == request, "EVENT_IDENTITY")
        require(kind in ("RECEIVED","STARTED","PROGRESS","HEARTBEAT","HOLD","COMPLETE","FAIL"),"EVENT_KIND")
        require(type(evidence) is dict and len(canonical(evidence)) <= 4096,"EVENT_EVIDENCE")
        self.journal.db.execute("INSERT INTO coordinator_events(attempt,kind,observed,evidence) VALUES(?,?,?,?)",(request["attempt_id"],kind,self.now(),canonical(evidence).decode("ascii")))
        return {"status":"RECORDED","kind":kind}

    def failure(self, request, cause, evidence):
        require(type(evidence) is dict and type(evidence.get("event_id")) is str,
                "FAILURE_EVENT_ID_REQUIRED")
        return self._record_failure(request,cause,evidence,evidence["event_id"])

    def tick(self):
        """Deterministic, idempotent timeout events; never claims wake ACK."""
        output = []
        for attempt, raw, created in self.journal.db.execute(
                "SELECT attempt,request_json,created FROM coordinator_requests"):
            request = json.loads(raw)
            events = self.journal.db.execute(
                "SELECT kind,MAX(observed) FROM coordinator_events WHERE attempt=? GROUP BY kind",
                (attempt,)).fetchall()
            marks = dict(events)
            if "COMPLETE" in marks or "FAIL" in marks:
                continue
            # Heartbeats are intentionally ignored; only PROGRESS counts.
            progress = marks.get("PROGRESS", marks.get("STARTED", created))
            milestones = (("NO_RECEIPT_5M", self.now()-created >= 300 and "RECEIVED" not in marks),
                          ("NO_START_15M", self.now()-created >= 900 and "STARTED" not in marks),
                          ("NO_PROGRESS_15M", self.now()-progress >= 900),
                          ("BLOCKED_30M", self.now()-created >= 1800),
                          ("METHOD_STOP_60M", self.now()-created >= 3600))
            for event, due in milestones:
                if not due:
                    continue
                key = digest([attempt,event])
                cursor = self.journal.db.execute(
                    "INSERT OR IGNORE INTO coordinator_outbox VALUES(?,?,?,?,?)",
                    (key,attempt,event,"UNAVAILABLE",
                     canonical({"provider":"UNAVAILABLE","next":"inspect/reconcile",
                                "deadline_utc":request["deadline_utc"]}).decode("ascii")))
                if cursor.rowcount == 1:
                    output.append({"attempt_id":attempt,"event":event,
                                   "delivery":"UNAVAILABLE","id":key})
        # Retained duplicate/unknown legacy rows remain queryable evidence
        # but do not inflate threshold counts until a stable event identity is
        # known.
        groups = self._counted_failure_groups()
        for (installation,rid),state in groups.items():
            for cause,first in state["causes"].items():
                if self.now()-first >= 1800:
                    event = "CHANGE_METHOD_30M"
                    key = digest([installation,rid,cause,event])
                    detail = {"round_id":rid,"cause":cause,"first_utc":first,
                              "recipient":"DOTS","next":"change method"}
                    if self._failure_outbox_insert(
                            key,installation,event,detail):
                        output.append({"installation_id":installation,"round_id":rid,
                                       "event":event,"delivery":"UNAVAILABLE","id":key})
            if state["count"] >= 10 or self.now()-state["first"] >= 3600:
                event = "REPORT_DOTS_10_OR_60"
                key = digest([installation,rid,event])
                detail = {"round_id":rid,"failures":state["count"],
                          "first_utc":state["first"],"recipient":"DOTS",
                          "next":"evaluate a different method"}
                if self._failure_outbox_insert(
                        key,installation,event,detail):
                    output.append({"installation_id":installation,"round_id":rid,
                                   "event":event,"delivery":"UNAVAILABLE","id":key})
        return output

def cli():
    parser = argparse.ArgumentParser(description="Isolated P2 coordinator")
    parser.add_argument("action", choices=("execute","inspect","recover","tick"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--request")
    parser.add_argument("--component-root", action="append", default=[], help="fixed batch=/absolute/private/root")
    parser.add_argument("--runtime", action="store_true", help="use fixed isolated runtime adapter (no plugins)")
    args = parser.parse_args()
    with open(args.plan, encoding="utf-8") as source:
        plan = json.load(source)
    request = None
    if args.action != "tick":
        require(bool(args.request), "REQUEST_REQUIRED")
        with open(args.request, encoding="utf-8") as source:
            request = json.load(source)
    try:
        roots = {}
        for mapping in args.component_root:
            key, sep, value = mapping.partition("=")
            require(sep and key in plan["batches"] and os.path.isabs(value), "ROOT_MAPPING")
            roots[key] = value
        adapters = {}
        if args.runtime:
            from production import p2_runtime as fixed_runtime
            class RuntimeAdapter:
                execute = staticmethod(fixed_runtime.execute)
                inspect = staticmethod(fixed_runtime.inspect)
                recover = staticmethod(fixed_runtime.recover)
            adapters = {key:RuntimeAdapter() for key in roots}
        with Coordinator(args.root, plan, adapters=adapters, component_roots=roots) as c:
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
