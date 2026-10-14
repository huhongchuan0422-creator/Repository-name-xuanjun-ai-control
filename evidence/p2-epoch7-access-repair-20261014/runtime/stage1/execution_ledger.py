"""Fenced execution over the existing task registry; no production migration.

Callers provision CODEX_EXEC rows through the authoritative task API and call
assert_live immediately before each external operation. No lease scheme can
roll back a side effect that completed before a process crashed. Expired leases
with uncertain effects require human review. Only a fully bound read-only
CI_WAIT checkpoint can be requeued automatically, followed by reconciliation.
"""
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
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

    def __init__(self, db_path, allowed_repositories, clock=None, max_heavy=2,
                 approved_base_shas=None, activation_store=None):
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
        self.activation_store = activation_store
        self.activation_binding = None
        if activation_store is not None:
            active = activation_store.read(require_active=True)
            if os.path.realpath(db_path) != active['db_path']:
                raise SchemaMismatch('database is not the active canonical generation')
            self.activation_binding = {
                key: active[key] for key in
                ('ledger_uuid', 'generation', 'epoch', 'instance', 'db_path')}
        if approved_base_shas is not None:
            if (not approved_base_shas or any(not isinstance(value, str)
                    or re.fullmatch(r'[0-9a-f]{40}', value) is None
                    for value in approved_base_shas)):
                raise ValueError('approved base SHAs must be full lowercase commits')
            self.approved_base_shas = frozenset(approved_base_shas)
        else:
            self.approved_base_shas = None
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

    @staticmethod
    def _db_identity(fd):
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise SchemaMismatch('canonical database inode unsafe')
        return '%d:%d' % (info.st_dev,info.st_ino)

    def _assert_db_identity(self,fd,identity):
        try:
            current_identity=self._db_identity(fd)
        except SchemaMismatch:
            raise LeaseLost('canonical database fd changed')
        if current_identity!=identity:
            raise LeaseLost('canonical database fd changed')
        current=os.lstat(self.db_path)
        observed='%d:%d' % (current.st_dev,current.st_ino)
        if not stat.S_ISREG(current.st_mode) or observed!=identity:
            raise LeaseLost('canonical database path changed')
        return True

    @contextlib.contextmanager
    def _pinned_transaction(self):
        self._assert_activation()
        fd=os.open(self.db_path,os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        conn=None
        try:
            identity=self._db_identity(fd)
            self._assert_db_identity(fd,identity)
            try:
                uri='file:/proc/self/fd/%d?mode=rw' % fd
                conn=sqlite3.connect(uri,uri=True,timeout=10,isolation_level=None)
            except sqlite3.OperationalError:
                self._assert_db_identity(fd,identity)
                raise SchemaMismatch('existing authoritative database unavailable')
            conn.row_factory=sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            try:
                conn.execute('BEGIN IMMEDIATE')
                self._assert_activation();self._assert_db_identity(fd,identity)
                yield conn,identity
                self._assert_activation();self._assert_db_identity(fd,identity)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        finally:
            try:
                if conn is not None:
                    conn.close()
            finally:
                os.close(fd)

    @contextlib.contextmanager
    def _transaction(self):
        with self._pinned_transaction() as value:
            yield value[0]

    def _assert_activation(self):
        """Fence every transaction to the exact active dispatcher identity."""
        if self.activation_store is None:
            return True
        active = self.activation_store.read(require_active=True)
        observed = {key: active[key] for key in self.activation_binding}
        if observed != self.activation_binding:
            raise LeaseLost('dispatcher activation epoch is no longer live')
        return True

    def supervisor(self, clock=None, max_delivery_attempts=3, claim_ttl=30):
        """Return supervision adapters bound to this exact canonical generation."""
        from execution_supervision import ExecutionSupervisor
        return ExecutionSupervisor(self.db_path, clock or self.clock,
                                   max_delivery_attempts=max_delivery_attempts,
                                   claim_ttl=claim_ttl,
                                   activation_store=self.activation_store)

    def record_inventory_notices(self,limit=100):
        if self.activation_store is None or self.activation_binding is None:
            raise LeaseLost('inventory notice requires active canonical generation')
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('inventory notice limit')
        from execution_supervision import ExecutionSupervisor
        from task_supervisor_inventory_adapter import canonical_inventory_page
        with self._pinned_transaction() as value:
            conn,identity=value
            required=('supervised_runs','supervision_events','supervision_delivery')
            if any(not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() for name in required):
                raise SchemaMismatch('existing supervision schema required')
            # Reuse canonical events as a durable, activation-bound scan checkpoint.
            # No task/checkpoint/lease is fabricated or overwritten.
            event='INVENTORY_SCAN_CHECKPOINT_V1'
            previous=conn.execute('SELECT details FROM events WHERE event=? ORDER BY id DESC LIMIT 1',
                                  (event,)).fetchone()
            after_id=None;sweep_end=None
            if previous is not None:
                raw=previous['details']
                if not isinstance(raw,str) or len(raw)>65536:
                    raise SchemaMismatch('inventory scan checkpoint invalid')
                try:
                    checkpoint=json.loads(raw)
                except (ValueError,TypeError):
                    raise SchemaMismatch('inventory scan checkpoint invalid')
                if not isinstance(checkpoint,dict) or set(checkpoint)!={'schema','binding','ledger_identity','after_id','sweep_end'} or type(checkpoint['schema']) is not int or checkpoint['schema']!=1:
                    raise SchemaMismatch('inventory scan checkpoint invalid')
                if checkpoint['binding']==self.activation_binding and checkpoint['ledger_identity']==identity:
                    after_id=checkpoint['after_id'];sweep_end=checkpoint['sweep_end']
                    if (after_id is None)!=(sweep_end is None) or (after_id is not None and
                            (not isinstance(after_id,str) or not after_id or len(after_id)>8192
                             or not isinstance(sweep_end,str) or not sweep_end or len(sweep_end)>8192
                             or after_id>=sweep_end)):
                        raise SchemaMismatch('inventory scan cursor invalid')
            # A finite high-water mark makes each sweep finish despite new tasks.
            # IDs inserted behind the cursor are covered by the next sweep.
            if sweep_end is None:
                sweep_end=conn.execute('SELECT MAX(id) FROM tasks').fetchone()[0]
                if sweep_end is not None and (not isinstance(sweep_end,str) or not sweep_end or len(sweep_end)>8192):
                    raise SchemaMismatch('inventory scan high-water mark invalid')
            supervisor=ExecutionSupervisor.__new__(ExecutionSupervisor)
            supervisor.db_path=self.db_path;supervisor.clock=self.clock
            supervisor.activation_store=self.activation_store
            supervisor.activation_binding=dict(self.activation_binding)
            supervisor.max_delivery_attempts=3;supervisor.claim_ttl=30
            receipts=[];observed=0;pages=0;complete=sweep_end is None
            while not complete and pages<64:
                pages+=1
                page=canonical_inventory_page(conn,self._now(),after_id=after_id,limit=limit,
                    activation_binding=self.activation_binding,ledger_identity=identity)
                last=after_id
                for intent in page['tasks']:
                    task_id=intent['id']
                    if task_id>sweep_end:
                        complete=True;break
                    observed+=1;last=task_id
                    if intent['decision']=='HOLD_AND_NOTIFY_REQUIRES_ADMISSION':
                        receipts.append(supervisor.record_inventory_notice(
                            conn,intent,self.activation_binding,identity))
                complete=complete or page['complete'] or (last is not None and last>=sweep_end)
                if complete:
                    break
                cursor=page['next_cursor']
                if not isinstance(cursor,str) or not cursor or len(cursor)>8192 or (after_id is not None and cursor<=after_id) or cursor!=last:
                    raise ValueError('inventory cursor did not advance')
                after_id=cursor
            checkpoint={'schema':1,'binding':dict(self.activation_binding),
                        'ledger_identity':identity,'after_id':None if complete else after_id,
                        'sweep_end':None if complete else sweep_end}
            self._event(conn,None,event,self._now(),checkpoint)
            return {'state':'INVENTORY_NOTICE_PASS' if complete else 'INVENTORY_NOTICE_BOUNDED_PROGRESS',
                    'ledger_identity':identity,'observed':observed,'pages':pages,
                    'notices':receipts,'sweep_complete':complete,'scan_pending':not complete,
                    'dispatch_performed':False}


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
        if self.approved_base_shas is not None and spec['base_sha'] not in self.approved_base_shas:
            raise ValueError('base commit is not an approved control source')
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

    def _safe_ci_wait(self, conn, row):
        """An expired read-only poll can continue; a model/tool turn cannot.

        Validate the persisted authority and immutable task/branch identities,
        not just a caller-supplied phase label. Pipeline reconciliation rechecks
        local and remote HEAD before any continuation work is performed.
        """
        try:
            cp = json.loads(row['checkpoint'])
            if not isinstance(cp, dict) or cp.get('phase') != 'CI_WAIT':
                return False
            stored = conn.execute('SELECT * FROM execution_specs WHERE task_id=?',
                                  (row['id'],)).fetchone()
            if stored is None or not isinstance(stored['revision'], int) or stored['revision'] < 1:
                return False
            spec = json.loads(stored['spec'])
            packed = self._validate_spec(spec)
            digest = hashlib.sha256(packed.encode('utf-8')).hexdigest()
            approved = {'repo': spec['repo'], 'instructions': spec['prompt'],
                        'base_sha': spec['base_sha']}
            identity = hashlib.sha256(self._dump(approved).encode('utf-8')).hexdigest()
            branch = 'codex/task-' + hashlib.sha256(row['id'].encode('utf-8')).hexdigest()[:24]
            budget = cp.get('patch_attempts')
            return (stored['hash'] == digest == cp.get('spec_hash')
                    and cp.get('spec_digest') == identity
                    and cp.get('branch') == branch
                    and isinstance(cp.get('sha'), str)
                    and re.fullmatch(r'[0-9a-f]{40}', cp['sha']) is not None
                    and type(cp.get('pr')) is int and cp['pr'] > 0
                    and isinstance(cp.get('workdir'), str)
                    and Path(cp['workdir']).is_absolute()
                    and type(budget) is int and 0 <= budget <= 3
                    and cp.get('production_pass') is False)
        except (ValueError, TypeError, KeyError):
            return False

    def _recover(self, conn, now):
        rows = conn.execute("SELECT * FROM tasks WHERE kind='CODEX_EXEC' "
                            "AND state='RUNNING' AND (lease_until IS NULL OR lease_until<=?)",
                            (now,)).fetchall()
        for row in rows:
            if self._safe_ci_wait(conn, row):
                conn.execute("UPDATE tasks SET state='PENDING',lease_owner=NULL,"
                             'lease_until=NULL,fence=fence+1,updated=? WHERE id=?',
                             (now, row['id']))
                self._event(conn, row['id'], 'CI_WAIT_RECOVERED', now,
                            {'previous_fence': row['fence'], 'automatic_retry': True,
                             'model_turn_replayed': False})
                continue
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
                result = {'task_id': row['id'], 'worker_id': worker_id, 'fence': fence,
                        'lease_until': now + ttl, 'spec': spec, 'revision': revision,
                        'spec_hash': digest, 'checkpoint': checkpoint}
                if self.activation_binding is not None:
                    result.update(self.activation_binding)
                return result
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
        self._assert_activation()
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
            if self.activation_binding is not None:
                result.update(self.activation_binding)
            self._assert_activation()
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

    def _native_bound(self, conn, request):
        if (not isinstance(request, dict)
                or any(type(request.get(k)) is not int or request[k] < 1
                       for k in ('fence', 'epoch', 'generation'))
                or any(not isinstance(request.get(k), str) or not request[k]
                       for k in ('task_id', 'lease', 'instance'))
                or not isinstance(request.get('spec_hash'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', request['spec_hash'])):
            raise LeaseLost('native claim types rejected')
        row = self._live(conn, request['task_id'], request['lease'], request['fence'], self._now())
        stored = conn.execute('SELECT * FROM execution_specs WHERE task_id=?',
                              (request['task_id'],)).fetchone()
        if stored is None or stored['hash'] != request['spec_hash']:
            raise LeaseLost('native spec binding changed')
        spec = json.loads(stored['spec'])
        if hashlib.sha256(self._validate_spec(spec).encode('utf-8')).hexdigest() != stored['hash']:
            raise SchemaMismatch('native spec integrity mismatch')
        if self.activation_binding is None or any(request.get(key) != self.activation_binding[key]
                for key in ('generation', 'epoch', 'instance')):
            raise LeaseLost('native activation binding changed')
        return row

    def native_observation(self, request):
        with self._transaction() as conn:
            row = self._native_bound(conn, request)
            checkpoint = json.loads(row['checkpoint'])
            if not isinstance(checkpoint, dict):
                raise SchemaMismatch('native checkpoint invalid')
            task = {key: request[key] for key in
                    ('task_id', 'spec_hash', 'lease', 'fence', 'epoch', 'generation', 'instance')}
            task.update({'state': row['state'], 'lease_until': row['lease_until'],
                         'source_manifest': checkpoint.get('native_source_manifest'),
                         'request_contract': checkpoint.get('native_request_contract'),
                         'native_execution': checkpoint.get('native_execution')})
            return {'task': task, 'request': dict(request),
                    'native_expected': checkpoint.get('native_execution')}

    def native_tool_observation(self, session_key):
        if (not isinstance(session_key, str)
                or not re.fullmatch(r'agent:(?:developer|platform-engineer):xuanjun-p2:[0-9a-f]{64}', session_key)):
            raise ValueError('native tool session rejected')
        with self._transaction() as conn:
            rows = conn.execute('SELECT checkpoint FROM tasks LIMIT 1001').fetchall()
            if len(rows) > 1000:
                raise ValueError('native task lookup limit')
            matches = []
            for row in rows:
                record = json.loads(row['checkpoint']).get('native_execution')
                if isinstance(record, dict) and record.get('session_key') == session_key:
                    matches.append(record)
            if len(matches) != 1 or matches[0].get('phase') != 'RUNNING':
                raise LeaseLost('native tool admission not bound to active run')
            record = matches[0]
            self._native_bound(conn, record['request'])
            return {'native_execution': record}

    def native_receipt_observation(self, request):
        """Read a persisted execution for stop/reconciliation after lease loss.

        This grants no dispatch, checkpoint mutation or renewed execution lease.
        The caller supplies a release-pinned canonical DB path, not an RPC path.
        """
        conn = sqlite3.connect(Path(self.db_path).resolve().as_uri() + '?mode=ro',
                               uri=True, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN')
            self._validate_schema(conn)
            self._validate_side_schema(conn)
            row = self._task(conn, request['task_id'])
            checkpoint = json.loads(row['checkpoint'])
            record = checkpoint.get('native_execution')
            keys = ('task_id', 'spec_hash', 'lease', 'fence', 'epoch', 'generation', 'instance')
            if not isinstance(record, dict) or any(
                    record.get('request', {}).get(k) != request.get(k) for k in keys):
                raise LeaseLost('persisted native receipt binding mismatch')
            task = {key: request[key] for key in keys}
            task.update({'native_execution': record,
                         'source_manifest': checkpoint.get('native_source_manifest')})
            conn.commit()
            return {'task': task, 'request': dict(request), 'native_expected': record}
        finally:
            conn.close()

    def native_compare_set(self, request, expected, execution):
        if not isinstance(execution, dict):
            raise ValueError('native execution must be an object')
        packed = self._dump(execution)
        if len(packed.encode('utf-8')) > 524288:
            raise ValueError('native execution too large')
        with self._transaction() as conn:
            row = self._native_bound(conn, request)
            checkpoint = json.loads(row['checkpoint'])
            if self._dump(checkpoint.get('native_execution')) != self._dump(expected):
                raise LeaseLost('native checkpoint compare-and-set conflict')
            checkpoint['native_execution'] = execution
            conn.execute('UPDATE tasks SET checkpoint=?,updated=? WHERE id=?',
                         (self._dump(checkpoint), self._now(), request['task_id']))
            self._event(conn, request['task_id'], 'NATIVE_EXECUTION_CHECKPOINTED',
                        self._now(), {'fence': request['fence'], 'phase': execution.get('phase')})
        return self.native_observation(request)

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
            row = self._live(conn, task_id, worker_id, fence, now)
            previous = json.loads(row['checkpoint'])
            if ('native_execution' in value and self._dump(value['native_execution'])
                    != self._dump(previous.get('native_execution'))):
                raise ValueError('controller checkpoint requires native CAS')
            if 'native_execution' in previous:
                value = dict(value, native_execution=previous['native_execution'])
                packed = self._dump(value)
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

    def owner_decision(self, task_id, expected_fence, decision, request_id,
                       update_id, owner_id, owner_chat, actor,
                       actor_authorized):
        """Consume one registered Owner request in the canonical transaction.

        Authentication/HMAC parsing remains in B's transport. This method is
        the only bounded mutation exposed by its ledger socket and atomically
        covers replay, request, approval, task and event state.
        """
        if (actor_authorized is not True or not isinstance(actor, str)
                or not actor.strip()):
            raise PermissionError('authorized Owner transport required')
        if decision not in ('APPROVE', 'REJECT'):
            raise ValueError('invalid Owner decision')
        if (not isinstance(task_id, str) or not task_id
                or type(expected_fence) is not int or expected_fence < 1
                or not isinstance(request_id, str) or not request_id
                or type(update_id) is not int):
            raise ValueError('invalid Owner request identity')
        owner_id, owner_chat = str(owner_id), str(owner_chat)
        with self._transaction() as conn:
            for table, required in {
                    'owner_callback_requests': {'request_id', 'task_id', 'fence',
                                                'owner_id', 'owner_chat',
                                                'expires_at', 'consumed'},
                    'owner_callback_replays': {'update_id', 'request_id'}}.items():
                columns = {row['name'] for row in
                           conn.execute('PRAGMA table_info(%s)' % table).fetchall()}
                legacy_replay = table=='owner_callback_replays' and columns==required|{'task_id'}
                if legacy_replay:
                    extra=next(row for row in conn.execute('PRAGMA table_info(owner_callback_replays)').fetchall() if row['name']=='task_id')
                    if extra['type'].upper()!='TEXT' or extra['notnull']!=0 or extra['pk']!=0:
                        raise SchemaMismatch('unsafe legacy Owner replay task column')
                if columns != required and not legacy_replay:
                    raise SchemaMismatch('Owner callback schema mismatch: ' + table)
            now = self._now()
            request = conn.execute(
                'SELECT * FROM owner_callback_requests WHERE request_id=?',
                (request_id,)).fetchone()
            if (request is None or request['task_id'] != task_id
                    or request['fence'] != expected_fence
                    or request['owner_id'] != owner_id
                    or request['owner_chat'] != owner_chat
                    or request['expires_at'] <= now or request['consumed'] != 0):
                raise PermissionError('missing, expired or consumed Owner request')
            row = self._task(conn, task_id)
            approval = conn.execute(
                'SELECT decision FROM approvals WHERE task_id=?', (task_id,)).fetchone()
            if (row['state'] != 'WAITING_HUMAN' or row['fence'] != expected_fence
                    or approval is None or approval['decision'] != 'PENDING'):
                raise LeaseLost('stale Owner task fence')
            replay_columns={row['name'] for row in conn.execute('PRAGMA table_info(owner_callback_replays)').fetchall()}
            if 'task_id' in replay_columns:
                conn.execute('INSERT INTO owner_callback_replays(update_id,request_id,task_id) VALUES(?,?,?)',(update_id,request_id,task_id))
            else:
                conn.execute('INSERT INTO owner_callback_replays(update_id,request_id) VALUES(?,?)',(update_id,request_id))
            changed = conn.execute(
                'UPDATE owner_callback_requests SET consumed=1 '
                'WHERE request_id=? AND consumed=0', (request_id,)).rowcount
            if changed != 1:
                raise LeaseLost('Owner request consumption lost CAS')
            new_state = 'PENDING' if decision == 'APPROVE' else 'FAILED'
            conn.execute('UPDATE approvals SET decision=?,decided_at=? WHERE task_id=?',
                         (decision, now, task_id))
            changed = conn.execute(
                'UPDATE tasks SET state=?,updated=? WHERE id=? '
                "AND state='WAITING_HUMAN' AND fence=?",
                (new_state, now, task_id, expected_fence)).rowcount
            if changed != 1:
                raise LeaseLost('Owner task decision lost CAS')
            details = {'actor': actor, 'request_id': request_id,
                       'update_id': update_id, 'fence': expected_fence}
            if self.activation_binding is not None:
                details.update({key: self.activation_binding[key] for key in
                                ('generation', 'epoch', 'instance')})
            self._event(conn, task_id, 'OWNER_' + decision, now, details)
            return {'accepted': True, 'state': new_state,
                    'task_id': task_id, 'fence': expected_fence}
