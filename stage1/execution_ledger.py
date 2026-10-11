"""Fenced execution over the existing task registry; no production migration.

Callers provision CODEX_EXEC rows through the authoritative task API and call
assert_live immediately before each external operation. No lease scheme can
roll back a side effect that completed before a process crashed: expired leases
therefore require human review, never an automatic retry.
"""
import contextlib
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time


class SchemaMismatch(ValueError):
    pass


class LeaseLost(RuntimeError):
    pass


class InvalidDAG(ValueError):
    pass


class ExecutionLedger(object):
    TYPE_WHITELIST = frozenset(['CODEX_EXEC'])
    SPEC_KEYS = frozenset(['repo', 'type', 'prompt', 'heavy', 'timeout_seconds', 'base_sha'])
    SCHEMAS = {
        'tasks': [('id', 'TEXT', 1), ('kind', 'TEXT', 0), ('state', 'TEXT', 0),
                  ('depends', 'TEXT', 0), ('lease_owner', 'TEXT', 0),
                  ('lease_until', 'REAL', 0), ('fence', 'INTEGER', 0),
                  ('checkpoint', 'TEXT', 0), ('updated', 'REAL', 0)],
        'approvals': [('task_id', 'TEXT', 1), ('decision', 'TEXT', 0),
                      ('requested_at', 'REAL', 0), ('decided_at', 'REAL', 0)],
        'events': [('id', 'INTEGER', 1), ('task_id', 'TEXT', 0),
                   ('event', 'TEXT', 0), ('created', 'REAL', 0),
                   ('details', 'TEXT', 0)],
    }

    def __init__(self, db_path, allowed_repositories, clock=None, max_heavy=2):
        if not allowed_repositories or isinstance(allowed_repositories, str):
            raise ValueError('explicit repository whitelist required')
        if any(not isinstance(repo, str) or not repo.strip()
               for repo in allowed_repositories):
            raise ValueError('invalid repository whitelist')
        if not isinstance(max_heavy, int) or isinstance(max_heavy, bool) or not 1 <= max_heavy <= 2:
            raise ValueError('heavy concurrency must be 1 or 2')
        self.db_path = db_path
        self.repositories = frozenset(allowed_repositories)
        self.clock = clock or time.time
        self.max_heavy = max_heavy
        # Opening a missing DB does not silently bootstrap a competing registry.
        with self._transaction() as conn:
            self._validate_schema(conn)
            conn.execute('CREATE TABLE IF NOT EXISTS execution_specs '
                         '(task_id TEXT PRIMARY KEY REFERENCES tasks(id), '
                         'spec TEXT NOT NULL, revision INTEGER NOT NULL, hash TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS worker_heartbeats '
                         '(worker_id TEXT NOT NULL, task_id TEXT PRIMARY KEY REFERENCES tasks(id), '
                         'fence INTEGER NOT NULL, seen_at REAL NOT NULL, phase TEXT NOT NULL)')
            self._validate_side_schema(conn)

    @contextlib.contextmanager
    def _transaction(self):
        try:
            uri = Path(self.db_path).resolve().as_uri() + '?mode=rw'
            conn = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
        except sqlite3.OperationalError:
            raise SchemaMismatch('existing authoritative database unavailable')
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def _validate_schema(cls, conn):
        for table, expected in cls.SCHEMAS.items():
            rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
            observed = [(r['name'], r['type'].upper(), r['pk']) for r in rows]
            if observed != expected:
                raise SchemaMismatch('authoritative schema mismatch: ' + table)

    @staticmethod
    def _validate_side_schema(conn):
        schemas = {
            'execution_specs': [('task_id', 'TEXT', 1), ('spec', 'TEXT', 0),
                                ('revision', 'INTEGER', 0), ('hash', 'TEXT', 0)],
            'worker_heartbeats': [('worker_id', 'TEXT', 0), ('task_id', 'TEXT', 1),
                                  ('fence', 'INTEGER', 0), ('seen_at', 'REAL', 0),
                                  ('phase', 'TEXT', 0)]}
        for table, expected in schemas.items():
            rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
            if [(r['name'], r['type'].upper(), r['pk']) for r in rows] != expected:
                raise SchemaMismatch('side table schema mismatch: ' + table)
            foreign = conn.execute('PRAGMA foreign_key_list(%s)' % table).fetchall()
            if not any(r['table'] == 'tasks' and r['from'] == 'task_id'
                       and r['to'] == 'id' for r in foreign):
                raise SchemaMismatch('side table task foreign key missing: ' + table)

    @staticmethod
    def _dump(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False)

    def _now(self):
        now = self.clock()
        if not isinstance(now, (float, int)) or not math.isfinite(now):
            raise ValueError('invalid clock')
        return float(now)

    def _event(self, conn, task_id, event, now, details):
        conn.execute('INSERT INTO events(task_id,event,created,details) VALUES(?,?,?,?)',
                     (task_id, event, now, self._dump(details)))

    @staticmethod
    def _task(conn, task_id):
        row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise ValueError('unknown task')
        return row

    def _dag(self, conn, focus=None, quarantine=False):
        rows = conn.execute('SELECT * FROM tasks').fetchall()
        graph, invalid = {}, set()
        for row in rows:
            try:
                depends = json.loads(row['depends'])
                if not isinstance(depends, list) or any(not isinstance(d, str) for d in depends):
                    raise ValueError('invalid dependencies')
                if len(set(depends)) != len(depends):
                    raise ValueError('duplicate dependencies')
            except (TypeError, ValueError):
                depends = []
                invalid.add(row['id'])
            graph[row['id']] = depends
        children = {key: [] for key in graph}
        remaining = {}
        for key, deps in graph.items():
            if any(dep not in graph for dep in deps):
                invalid.add(key)
            known = [dep for dep in deps if dep in graph]
            remaining[key] = len(known)
            for dep in known:
                children[dep].append(key)
        ready = [key for key, degree in remaining.items() if degree == 0]
        while ready:
            key = ready.pop()
            for child in children[key]:
                remaining[child] -= 1
                if remaining[child] == 0:
                    ready.append(child)
        # Kahn leftovers include cycles and all their dependent descendants.
        invalid.update(key for key, degree in remaining.items() if degree)
        affected = list(invalid)
        while affected:
            for child in children[affected.pop()]:
                if child not in invalid:
                    invalid.add(child)
                    affected.append(child)
        if focus is not None and focus in invalid:
            raise InvalidDAG('task dependency graph is invalid')
        if quarantine and invalid:
            registered = set(r[0] for r in conn.execute('SELECT task_id FROM execution_specs'))
            now = self._now()
            for row in rows:
                if row['id'] not in invalid or row['id'] not in registered or row['kind'] != 'CODEX_EXEC':
                    continue
                if row['state'] not in ('PENDING', 'RUNNING', 'PAUSED_RESOURCE'):
                    continue
                conn.execute("UPDATE tasks SET state='WAITING_HUMAN',lease_owner=NULL,"
                             'lease_until=NULL,fence=fence+1,updated=? WHERE id=?',
                             (now, row['id']))
                self._pending_approval(conn, row['id'], now)
                self._event(conn, row['id'], 'INVALID_DAG_QUARANTINED', now,
                            {'automatic_retry': False})
            rows = conn.execute('SELECT * FROM tasks').fetchall()
        return rows, graph

    def _quarantine(self, conn, row, reason, now):
        if row['kind'] != 'CODEX_EXEC' or row['state'] not in ('PENDING', 'RUNNING', 'PAUSED_RESOURCE'):
            return
        conn.execute("UPDATE tasks SET state='WAITING_HUMAN',lease_owner=NULL,"
                     'lease_until=NULL,fence=fence+1,updated=? WHERE id=?',
                     (now, row['id']))
        self._pending_approval(conn, row['id'], now)
        self._event(conn, row['id'], reason, now, {'automatic_retry': False})

    def _validate_spec(self, spec):
        if not isinstance(spec, dict) or set(spec) != self.SPEC_KEYS:
            raise ValueError('trusted spec must contain only approved fields')
        if spec['repo'] not in self.repositories or spec['type'] not in self.TYPE_WHITELIST:
            raise ValueError('repository/type not whitelisted')
        if not isinstance(spec['base_sha'], str) or re.fullmatch(r'[0-9a-fA-F]{40}', spec['base_sha']) is None:
            raise ValueError('full 40-hex base commit required')
        if not isinstance(spec['prompt'], str) or not spec['prompt'].strip():
            raise ValueError('trusted prompt required')
        if len(spec['prompt'].encode('utf-8')) > 256 * 1024:
            raise ValueError('prompt too large')
        if not isinstance(spec['heavy'], bool):
            raise ValueError('heavy must be boolean')
        timeout = spec['timeout_seconds']
        if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not math.isfinite(timeout) or not 0 < timeout <= 86400:
            raise ValueError('bounded positive timeout required')
        return self._dump(spec)

    def register_spec(self, task_id, spec, author, author_authorized):
        # This is an attestation from the trusted owner/control plane, never a
        # field accepted from issue bodies, webhook payloads or model output.
        if author_authorized is not True or not isinstance(author, str) or not author.strip():
            raise PermissionError('authorized author attestation required')
        packed = self._validate_spec(spec)
        digest = hashlib.sha256(packed.encode('utf-8')).hexdigest()
        with self._transaction() as conn:
            now = self._now()
            row = self._task(conn, task_id)
            if row['kind'] != spec['type']:
                raise ValueError('task/spec kind mismatch')
            if row['state'] not in ('PENDING', 'WAITING_HUMAN', 'PAUSED_RESOURCE'):
                raise ValueError('task cannot be edited in its current state')
            self._dag(conn, focus=task_id)
            old = conn.execute('SELECT spec,revision,hash FROM execution_specs WHERE task_id=?',
                               (task_id,)).fetchone()
            if old and old['spec'] == packed and old['hash'] == digest:
                return {'revision': old['revision'], 'hash': digest}
            revision = old['revision'] + 1 if old else 1
            conn.execute('INSERT OR REPLACE INTO execution_specs VALUES(?,?,?,?)',
                         (task_id, packed, revision, digest))
            if row['state'] == 'WAITING_HUMAN':
                conn.execute('UPDATE tasks SET fence=fence+1,updated=? WHERE id=?', (now, task_id))
                self._pending_approval(conn, task_id, now)
            self._event(conn, task_id, 'EXECUTION_SPEC_REGISTERED', now,
                        {'author': author, 'revision': revision, 'hash': digest})
        return {'revision': revision, 'hash': digest}

    def _pending_approval(self, conn, task_id, now):
        conn.execute('INSERT OR REPLACE INTO approvals VALUES(?,?,?,?)',
                     (task_id, 'PENDING', now, None))

    def _recover(self, conn, now):
        rows = conn.execute("SELECT id,fence FROM tasks WHERE kind='CODEX_EXEC' "
                            "AND state='RUNNING' AND (lease_until IS NULL OR lease_until<=?)",
                            (now,)).fetchall()
        for row in rows:
            conn.execute("UPDATE tasks SET state='WAITING_HUMAN',lease_owner=NULL,"
                         'lease_until=NULL,fence=fence+1,updated=? WHERE id=?',
                         (now, row['id']))
            self._pending_approval(conn, row['id'], now)
            self._event(conn, row['id'], 'LEASE_EXPIRED_UNCERTAIN_EFFECTS', now,
                        {'previous_fence': row['fence'], 'automatic_retry': False})
        return [row['id'] for row in rows]

    def recover_expired(self):
        with self._transaction() as conn:
            return self._recover(conn, self._now())

    @staticmethod
    def _ttl(ttl):
        if isinstance(ttl, bool) or not isinstance(ttl, (float, int)) or not math.isfinite(ttl) or not 0 < ttl <= 86400:
            raise ValueError('bounded positive lease TTL required')

    def claim(self, worker_id, ttl=60):
        self._ttl(ttl)
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError('worker identity required')
        with self._transaction() as conn:
            now = self._now()
            self._recover(conn, now)
            rows, graph = self._dag(conn, quarantine=True)
            states = {r['id']: r['state'] for r in rows}
            specs = {}
            by_id = {row['id']: row for row in rows}
            for stored in conn.execute('SELECT * FROM execution_specs').fetchall():
                row = by_id.get(stored['task_id'])
                if row is None or row['kind'] != 'CODEX_EXEC':
                    continue
                try:
                    spec = json.loads(stored['spec'])
                    packed = self._validate_spec(spec)
                    if hashlib.sha256(packed.encode('utf-8')).hexdigest() != stored['hash']:
                        raise ValueError('spec integrity mismatch')
                    if not isinstance(stored['revision'], int) or stored['revision'] <= 0:
                        raise ValueError('invalid spec revision')
                    if spec['type'] != row['kind']:
                        raise ValueError('task/spec kind mismatch')
                except (TypeError, ValueError):
                    self._quarantine(conn, row, 'INVALID_SPEC_QUARANTINED', now)
                    continue
                specs[stored['task_id']] = (spec, stored['revision'], stored['hash'])
            rows = conn.execute('SELECT * FROM tasks').fetchall()
            states = {r['id']: r['state'] for r in rows}
            heavy_running = sum(1 for r in rows if r['state'] == 'RUNNING'
                                and (r['id'] not in specs or specs[r['id']][0]['heavy']))
            for row in sorted(rows, key=lambda r: (r['updated'], r['id'])):
                if row['kind'] != 'CODEX_EXEC' or row['state'] != 'PENDING' or row['id'] not in specs:
                    continue
                if any(states[dep] != 'DONE' for dep in graph[row['id']]):
                    continue
                spec, revision, digest = specs[row['id']]
                if spec['type'] != row['kind']:
                    raise ValueError('task/spec kind mismatch')
                if spec['heavy'] and heavy_running >= self.max_heavy:
                    continue
                try:
                    checkpoint = json.loads(row['checkpoint'])
                    if not isinstance(checkpoint, dict):
                        raise ValueError('checkpoint must be an object')
                except (TypeError, ValueError):
                    self._quarantine(conn, row, 'INVALID_CHECKPOINT_QUARANTINED', now)
                    continue
                fence = row['fence'] + 1
                conn.execute("UPDATE tasks SET state='RUNNING',lease_owner=?,"
                             'lease_until=?,fence=?,updated=? WHERE id=?',
                             (worker_id, now + ttl, fence, now, row['id']))
                conn.execute('INSERT OR REPLACE INTO worker_heartbeats VALUES(?,?,?,?,?)',
                             (worker_id, row['id'], fence, now, 'EXECUTING'))
                self._event(conn, row['id'], 'EXECUTION_CLAIMED', now,
                            {'worker_id': worker_id, 'fence': fence, 'spec_hash': digest})
                return {'task_id': row['id'], 'worker_id': worker_id, 'fence': fence,
                        'lease_until': now + ttl, 'spec': spec, 'revision': revision,
                        'spec_hash': digest, 'checkpoint': checkpoint}
        return None

    def _live(self, conn, task_id, worker_id, fence, now):
        row = self._task(conn, task_id)
        if row['kind'] != 'CODEX_EXEC' or row['state'] != 'RUNNING' or row['lease_owner'] != worker_id or row['fence'] != fence or row['lease_until'] is None or row['lease_until'] <= now:
            raise LeaseLost('execution lease is no longer live')
        return row

    def observation(self, task_id):
        """Read one consistent authoritative snapshot without mutations.

        This returns metadata and the persisted checkpoint only, never the
        trusted prompt, spec, raw events, credential files or diagnostic output.
        A credential-bearing checkpoint fails closed instead of being exposed.
        """
        try:
            uri = Path(self.db_path).resolve().as_uri() + '?mode=ro'
            conn = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
        except sqlite3.OperationalError:
            raise SchemaMismatch('existing authoritative database unavailable')
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN')
            self._validate_schema(conn)
            self._validate_side_schema(conn)
            row = self._task(conn, task_id)
            try:
                checkpoint = json.loads(row['checkpoint'])
                if not isinstance(checkpoint, dict):
                    raise ValueError('invalid checkpoint')
            except (TypeError, ValueError):
                raise ValueError('persisted checkpoint must be a JSON object')
            packed = self._dump(checkpoint)
            protected = re.compile(
                r'(?i)(?:"(?:api[ _-]?key|access[ _-]?token|refresh[ _-]?token|'
                r'password|secret|authorization|private[ _-]?key|bot[ _-]?token)"\s*:|'
                r'\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{8,}|'
                r'(?<!\d)\d{5,15}:[A-Za-z0-9_-]{20,}|bearer\s+[^\s"\\]+|'
                r'-----BEGIN [A-Z ]*PRIVATE KEY-----)')
            if protected.search(packed) or (row['lease_owner'] and protected.search(row['lease_owner'])):
                raise ValueError('checkpoint contains protected credentials')
            result = {'task_id': row['id'], 'state': row['state'],
                      'fence': row['fence'], 'lease_owner': row['lease_owner'],
                      'lease_until': row['lease_until'], 'checkpoint': checkpoint}
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def assert_live(self, task_id, worker_id, fence):
        with self._transaction() as conn:
            self._live(conn, task_id, worker_id, fence, self._now())
        return True

    def heartbeat(self, task_id, worker_id, fence, ttl=60, phase='EXECUTING'):
        self._ttl(ttl)
        if not isinstance(phase, str) or re.fullmatch(r'[A-Z][A-Z0-9_]{0,31}', phase) is None:
            raise ValueError('invalid heartbeat phase')
        with self._transaction() as conn:
            now = self._now()
            self._live(conn, task_id, worker_id, fence, now)
            conn.execute('UPDATE tasks SET lease_until=?,updated=? WHERE id=?',
                         (now + ttl, now, task_id))
            conn.execute('INSERT OR REPLACE INTO worker_heartbeats VALUES(?,?,?,?,?)',
                         (worker_id, task_id, fence, now, phase))
        return now + ttl

    def checkpoint(self, task_id, worker_id, fence, value):
        if not isinstance(value, dict):
            raise ValueError('checkpoint must be an object')
        packed = self._dump(value)
        with self._transaction() as conn:
            now = self._now()
            self._live(conn, task_id, worker_id, fence, now)
            conn.execute('UPDATE tasks SET checkpoint=?,updated=? WHERE id=?',
                         (packed, now, task_id))
            self._event(conn, task_id, 'EXECUTION_CHECKPOINTED', now, {'fence': fence})

    def finish(self, task_id, worker_id, fence, state, effects='unknown'):
        if state not in ('DONE', 'FAILED', 'WAITING_HUMAN', 'PAUSED_RESOURCE'):
            raise ValueError('invalid finish state')
        if effects not in ('none', 'known', 'unknown'):
            raise ValueError('invalid effects classification')
        if state == 'PAUSED_RESOURCE' and effects != 'none':
            state = 'WAITING_HUMAN'
        with self._transaction() as conn:
            now = self._now()
            self._live(conn, task_id, worker_id, fence, now)
            conn.execute('UPDATE tasks SET state=?,lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?',
                         (state, now, task_id))
            if state == 'WAITING_HUMAN':
                self._pending_approval(conn, task_id, now)
            self._event(conn, task_id, 'EXECUTION_FINISHED', now,
                        {'fence': fence, 'state': state, 'effects': effects})
        return state

    def resume_resource(self, task_id, actor, actor_authorized, automatic=False):
        if actor_authorized is not True or not isinstance(actor, str) or not actor.strip() or not isinstance(automatic, bool):
            raise PermissionError('authorized resource resume required')
        with self._transaction() as conn:
            row = self._task(conn, task_id)
            if row['kind'] != 'CODEX_EXEC' or row['state'] != 'PAUSED_RESOURCE':
                raise ValueError('task is not resource-paused')
            now = self._now()
            conn.execute("UPDATE tasks SET state='PENDING',lease_owner=NULL,lease_until=NULL,fence=fence+1,updated=? WHERE id=?", (now, task_id))
            self._event(conn, task_id, 'RESOURCE_RESUMED', now,
                        {'actor': actor, 'automatic': automatic, 'authorized': True})

    def resume_human(self, task_id, actor):
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError('review actor required')
        with self._transaction() as conn:
            row = self._task(conn, task_id)
            approval = conn.execute('SELECT decision FROM approvals WHERE task_id=?',
                                    (task_id,)).fetchone()
            if row['kind'] != 'CODEX_EXEC' or row['state'] != 'WAITING_HUMAN':
                raise ValueError('task is not awaiting human review')
            if approval is None or approval['decision'] != 'APPROVE':
                raise PermissionError('explicit approval record required')
            now = self._now()
            conn.execute("UPDATE tasks SET state='PENDING',lease_owner=NULL,lease_until=NULL,fence=fence+1,updated=? WHERE id=?", (now, task_id))
            self._event(conn, task_id, 'HUMAN_REVIEW_RESUMED', now, {'actor': actor})
