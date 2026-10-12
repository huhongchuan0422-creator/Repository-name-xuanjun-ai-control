"""Read-only Owner workbench over the existing Coordinator database. Python 3.6."""
import argparse
import hmac
import json
import os
import re
import sqlite3
import stat
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from activation_control import ActivationStore

REQUIRED = {'id', 'state', 'fence', 'updated'}
OPTIONAL = ('lease_owner', 'lease_until', 'checkpoint', 'depends')
ACTIVATION_KEYS = ('ledger_uuid', 'generation', 'epoch', 'instance', 'db_path')


def _task(row, selected, now):
    task = dict(zip(selected, row))
    for key in ('checkpoint', 'depends'):
        if key in task:
            try:
                task[key] = json.loads(task[key])
            except (ValueError, TypeError):
                task[key] = None
    # Expose only bounded checkpoint metadata, never prompts or free-form logs.
    cp = task.get('checkpoint')
    patterns = {'phase': r'[A-Z_]{1,40}', 'commit': r'[a-f0-9]{40}',
                'sha': r'[a-f0-9]{40}', 'qa_commit': r'[a-f0-9]{40}',
                'ci': r'(PASS|FAIL|PENDING|UNKNOWN|passed|failed)',
                'qa': r'(PASS|FAIL|PENDING|UNKNOWN|passed|failed)',
                'reason': r'[A-Z_]{1,80}', 'error_code': r'[A-Z_]{1,80}'}
    task['checkpoint'] = {k: cp[k] for k, pattern in patterns.items()
                          if isinstance(cp.get(k), str) and re.fullmatch(pattern, cp[k])} if isinstance(cp, dict) else {}
    # Keep the original pipeline evidence and support existing dashboard clients.
    for source, alias in (('sha', 'commit'), ('reason', 'error_code')):
        if source in task['checkpoint'] and alias not in task['checkpoint']:
            task['checkpoint'][alias] = task['checkpoint'][source]
    # Database RUNNING is a lease claim, not evidence of continued execution.
    task['execution_evidence'] = 'UNKNOWN'
    if task['state'] == 'RUNNING':
        lease = task.get('lease_until')
        task['lease_status'] = 'VALID' if isinstance(lease, (int, float)) and lease > now else 'STALE_OR_UNKNOWN'
    return task


def snapshot(path, now=None, limit=200, activation=None):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('invalid limit')
    now = time.time() if now is None else now
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True,
                         timeout=3, isolation_level=None)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        columns = {r[1] for r in db.execute('PRAGMA table_info(tasks)')}
        if not REQUIRED <= columns:
            raise ValueError('COORDINATOR_SCHEMA_INCOMPATIBLE')
        selected = ['id', 'state', 'fence', 'updated']
        selected.extend(c for c in OPTIONAL if c in columns)
        # Identifiers come only from the fixed allowlist above.
        rows = db.execute('SELECT ' + ','.join(selected) +
                          ' FROM tasks ORDER BY updated DESC,id LIMIT ?', (limit,)).fetchall()
        counts = dict(db.execute('SELECT state,COUNT(*) FROM tasks GROUP BY state'))
        tasks = [_task(row, selected, now) for row in rows]
        # Human work must not disappear when newer automated tasks fill the
        # recent-task window. Read the entire queue in the same transaction.
        human_rows = db.execute('SELECT ' + ','.join(selected) +
                                " FROM tasks WHERE state='WAITING_HUMAN' ORDER BY updated DESC,id").fetchall()
        human_queue = [_task(row, selected, now) for row in human_rows]
        queue_rows = db.execute(
            'SELECT ' + ','.join(selected) +
            " FROM tasks WHERE state NOT IN ('DONE','FAILED') "
            'ORDER BY updated DESC,id').fetchall()
        queue = [_task(row, selected, now) for row in queue_rows]
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        wake_timeline = []
        if 'mechanical_wake_events' in tables:
            wake_columns = ('task_id','attempt','threshold_seconds','triggered_at',
                            'action','run_id','session_id','last_progress',
                            'checkpoint','status','result','error','next_check')
            wake_rows = db.execute(
                'SELECT ' + ','.join(wake_columns) +
                ' FROM mechanical_wake_events ORDER BY triggered_at DESC LIMIT 100').fetchall()
            for values in wake_rows:
                event = dict(zip(wake_columns, values))
                try:
                    checkpoint = json.loads(event['checkpoint'])
                except (TypeError, ValueError):
                    checkpoint = {}
                event['checkpoint'] = {key: checkpoint[key] for key in
                    ('phase','commit','sha','reason','error_code')
                    if isinstance(checkpoint.get(key), str)
                    and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', checkpoint[key])}
                try:
                    result = json.loads(event['result']) if event['result'] else None
                except (TypeError, ValueError):
                    result = None
                event['result'] = ({'state': result['state']}
                                   if isinstance(result, dict)
                                   and isinstance(result.get('state'), str)
                                   and re.fullmatch(r'[A-Z0-9_]{1,80}', result['state'])
                                   else None)
                if event['error'] is not None and not re.fullmatch(
                        r'[A-Za-z][A-Za-z0-9_]{0,79}', event['error']):
                    event['error'] = 'REDACTED_INVALID_ERROR'
                wake_timeline.append(event)
        heartbeats = []
        if 'worker_heartbeats' in tables:
            heartbeat_cols = {r[1] for r in db.execute('PRAGMA table_info(worker_heartbeats)')}
            if {'worker_id', 'task_id', 'fence', 'seen_at', 'phase'} <= heartbeat_cols:
                heartbeats = [dict(zip(('worker_id','task_id','fence','seen_at','phase'), r))
                              for r in db.execute('SELECT worker_id,task_id,fence,seen_at,phase FROM worker_heartbeats ORDER BY seen_at DESC LIMIT 20')]
        for collection in (tasks, human_queue, queue):
            for task in collection:
                matches = [h for h in heartbeats
                           if h['task_id'] == task['id']
                           and h['fence'] == task['fence']
                           and h['worker_id'] == task.get('lease_owner')
                           and 0 <= now - h['seen_at'] <= 60]
                if (task['state'] == 'RUNNING'
                        and task.get('lease_status') == 'VALID' and matches):
                    task['execution_evidence'] = 'FRESH_WORKER_HEARTBEAT'
        done = db.execute("SELECT MAX(updated) FROM tasks WHERE state='DONE'").fetchone()[0]
        return {'observed_at': now, 'source': 'CANONICAL_LEDGER_READ_ONLY',
                'counts': counts, 'tasks': tasks, 'truncated': sum(counts.values()) > limit,
                'heartbeats': heartbeats, 'last_completed_at': done,
                'services': {'openclaw': 'UNKNOWN', 'codex_model_access': 'UNKNOWN',
                             'github_runner': 'UNKNOWN', 'telegram': 'UNKNOWN'},
                'model_policy': {'primary': 'openai/gpt-5.6-sol',
                                 'fallbacks': [],
                                 'source': 'OWNER_CONFIGURATION_INTENT'},
                'model': 'UNKNOWN', 'fallbacks': None,
                'human_queue': human_queue, 'queue': queue,
                'wake_timeline': wake_timeline,
                'activation': activation}
    finally:
        db.close()


def active_snapshot(activation_store, now=None, limit=200):
    """Read one active generation and reject an activation switch mid-read."""
    active = activation_store.read(require_active=True)
    binding = {key: active[key] for key in ACTIVATION_KEYS}
    result = snapshot(active['db_path'], now=now, limit=limit,
                      activation={key: active[key] for key in
                                  ('ledger_uuid', 'generation', 'epoch', 'instance')})
    after = activation_store.read(require_active=True)
    if any(after[key] != binding[key] for key in ACTIVATION_KEYS):
        raise RuntimeError('ACTIVATION_CHANGED_DURING_SNAPSHOT')
    return result


def read_token(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError('UNSAFE_TOKEN_FILE')
    with open(path) as stream:
        token = stream.read().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token):
        raise ValueError('INVALID_TOKEN')
    return token


def handler(activation_store, token, page):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, data, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; connect-src 'self'")
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/':
                self.respond(200, page, 'text/html; charset=utf-8')
                return
            if self.path != '/api/state':
                self.respond(404, b'{}', 'application/json')
                return
            supplied = self.headers.get('Authorization', '')
            if not hmac.compare_digest(supplied.encode('utf-8'), ('Bearer ' + token).encode('ascii')):
                self.respond(401, b'{"error":"AUTH_REQUIRED"}', 'application/json')
                return
            try:
                data = json.dumps(active_snapshot(activation_store), ensure_ascii=True,
                                  allow_nan=False).encode('utf-8')
            except (sqlite3.Error, ValueError, OSError, TypeError, RuntimeError):
                self.respond(503, b'{"error":"STATE_UNAVAILABLE"}', 'application/json')
                return
            self.respond(200, data, 'application/json')
    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--activation-descriptor', required=True)
    ap.add_argument('--activation-epoch-journal', required=True)
    ap.add_argument('--activation-lock', required=True)
    ap.add_argument('--token-file', required=True)
    ap.add_argument('--port', type=int, default=18556)
    args = ap.parse_args()
    with open(str(Path(__file__).with_name('owner_dashboard.html')), 'rb') as stream:
        page = stream.read()
    # Python 3.6 has no ThreadingHTTPServer; local reverse proxy handles buffering.
    from http.server import HTTPServer
    activation = ActivationStore(args.activation_descriptor,
                                 args.activation_epoch_journal,
                                 args.activation_lock)
    activation.read(require_active=True)
    HTTPServer(('127.0.0.1', args.port),
               handler(activation, read_token(args.token_file), page)).serve_forever()


if __name__ == '__main__':
    main()
