"""Stage1 development-only durable queue. No process execution or GitHub credentials."""
import json
import sqlite3
import time
from pathlib import Path

STATES = {"PENDING", "RUNNING", "WAITING_HUMAN", "PAUSED_RESOURCE", "DONE", "FAILED"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, deps TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'PENDING',
 heavy INTEGER NOT NULL DEFAULT 1,
 lease_owner TEXT, lease_until REAL, fence INTEGER NOT NULL DEFAULT 0,
 checkpoint TEXT NOT NULL DEFAULT '{}', updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
"""

class Queue:
    def __init__(self, path):
        self.path = str(Path(path))
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def add(self, task_id, deps=(), heavy=True):
        if task_id in deps or not task_id:
            raise ValueError("invalid task id/dependency")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO tasks(id,deps,heavy,updated) VALUES(?,?,?,?)",
                            (task_id, json.dumps(list(deps)), int(heavy), time.time()))

    def get(self, task_id):
        row = self.db.execute("SELECT id,deps,state,heavy,lease_owner,lease_until,fence,checkpoint FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None
        return dict(zip(("id","deps","state","heavy","lease_owner","lease_until","fence","checkpoint"),
                        (row[0],json.loads(row[1]),row[2],bool(row[3]),row[4],row[5],row[6],json.loads(row[7]))))

    def claim(self, owner, now=None, ttl=120, max_heavy=2):
        if not owner or ttl <= 0 or max_heavy < 1:
            raise ValueError("invalid lease arguments")
        now = time.time() if now is None else now
        self.db.execute("BEGIN IMMEDIATE")
        try:
            # Expired workers may have performed external work. Recover to PENDING;
            # fencing tokens prevent their stale acknowledgements.
            self.db.execute("UPDATE tasks SET state='PENDING', lease_owner=NULL, lease_until=NULL,updated=? WHERE state='RUNNING' AND lease_until<=?", (now,now))
            active = self.db.execute("SELECT COUNT(*) FROM tasks WHERE state='RUNNING' AND heavy=1").fetchone()[0]
            done = {r[0] for r in self.db.execute("SELECT id FROM tasks WHERE state='DONE'")}
            all_ids = {r[0] for r in self.db.execute("SELECT id FROM tasks")}
            candidate = None
            for tid,deps_json,heavy in self.db.execute("SELECT id,deps,heavy FROM tasks WHERE state='PENDING' ORDER BY updated,id"):
                deps = json.loads(deps_json)
                if any(d not in all_ids for d in deps):
                    continue
                if not all(d in done for d in deps):
                    continue
                if heavy and active >= max_heavy:
                    continue
                candidate = tid
                break
            if candidate:
                self.db.execute("UPDATE tasks SET state='RUNNING',lease_owner=?,lease_until=?,fence=fence+1,updated=? WHERE id=?",
                                (owner,now+ttl,now,candidate))
            self.db.execute("COMMIT")
            return self.get(candidate) if candidate else None
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def finish(self, task_id, owner, fence, state, checkpoint=None, now=None):
        if state not in {"DONE","FAILED","WAITING_HUMAN","PAUSED_RESOURCE"}:
            raise ValueError("invalid terminal/blocked state")
        now = time.time() if now is None else now
        payload = json.dumps(checkpoint if checkpoint is not None else {})
        cur = self.db.execute(
            "UPDATE tasks SET state=?,lease_owner=NULL,lease_until=NULL,checkpoint=?,updated=? "
            "WHERE id=? AND state='RUNNING' AND lease_owner=? AND fence=? AND lease_until>?",
            (state,payload,now,task_id,owner,fence,now))
        return cur.rowcount == 1

    def resume(self, task_id, from_state):
        if from_state not in {"WAITING_HUMAN","PAUSED_RESOURCE","FAILED"}:
            raise ValueError("invalid resume state")
        cur = self.db.execute("UPDATE tasks SET state='PENDING',updated=? WHERE id=? AND state=?",
                              (time.time(),task_id,from_state))
        return cur.rowcount == 1

    def snapshot(self):
        return [self.get(row[0]) for row in self.db.execute("SELECT id FROM tasks ORDER BY id")]
