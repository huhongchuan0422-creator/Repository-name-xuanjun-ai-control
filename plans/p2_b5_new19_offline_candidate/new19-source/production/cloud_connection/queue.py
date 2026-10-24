"""Connection queue candidate. Does not launch a worker or grant production access.

The receiving adapter must supply the authenticated actor, never a JSON actor
claim. Installed code and target policy are separately pinned by the host.
DISPATCHING/UNKNOWN cannot be claimed again, including after process restart.
"""
import hashlib
import json
import re
import sqlite3
import os
import stat


class Hold(Exception):
    pass


TARGETS = {
    'uk': ('1107191612880779', 'eu-west-1', '40dfc6a47d5e4363b9da7d0d6ab01cb1'),
    'korea': ('1691189778575891', 'ap-northeast-2', '09207081a09a466aa0079b07b5e3e7ca'),
    'domestic': ('1384884686754410', 'cn-shanghai', '3a22c458934142eea89ec6e3bf481a57'),
}
FIELDS = {'schema', 'request_id', 'project', 'target', 'operation',
          'executor_sha256', 'arguments', 'expires_unix'}
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
EXISTING_SCHEMA = {
    'connection_jobs': "CREATE TABLE connection_jobs ( request_id TEXT PRIMARY KEY, project TEXT NOT NULL, request_json TEXT NOT NULL, request_sha TEXT NOT NULL, actor_id INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('READY','DISPATCHING','UNKNOWN','SUCCESS','FAILED')), invoke_id TEXT, receipt_json TEXT)",
    'connection_active_project': "CREATE UNIQUE INDEX connection_active_project ON connection_jobs(project) WHERE state IN ('DISPATCHING','UNKNOWN')",
    'connection_no_delete': "CREATE TRIGGER connection_no_delete BEFORE DELETE ON connection_jobs BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CONNECTION_HISTORY'); END",
    'connection_no_replace': "CREATE TRIGGER connection_no_replace BEFORE INSERT ON connection_jobs WHEN EXISTS(SELECT 1 FROM connection_jobs WHERE request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'IMMUTABLE_REQUEST'); END",
    'connection_no_rebind': "CREATE TRIGGER connection_no_rebind BEFORE UPDATE OF request_id,project,request_json,request_sha,actor_id ON connection_jobs BEGIN SELECT RAISE(ABORT,'IMMUTABLE_REQUEST'); END",
}


def open_existing_file(path):
    """Walk each parent without following links; caller owns the returned fd."""
    fd=os.open('/',os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts=path.split('/')[1:]
        for part in parts[:-1]:
            if not part or part in ('.','..'):raise Hold('QUEUE_EXISTING_PATH')
            nxt=os.open(part,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
        if not parts[-1] or parts[-1] in ('.','..'):raise Hold('QUEUE_EXISTING_PATH')
        return os.open(parts[-1],os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,dir_fd=fd)
    finally:os.close(fd)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Hold('DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def decode(raw):
    if not isinstance(raw, str) or len(raw.encode()) > 16384:
        raise Hold('REQUEST_BOUND')
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda v: (_ for _ in ()).throw(Hold('NONFINITE')))
    except (ValueError, TypeError) as exc:
        raise Hold('REQUEST_JSON') from exc


def validate(request, actor_id, allowed_actors, executor_sha256, now, project_actions=None, approved_objects=None):
    if type(actor_id) is not int or actor_id not in allowed_actors:
        raise Hold('UNTRUSTED_SUBMITTER')
    if type(request) is not dict or set(request) != FIELDS:
        raise Hold('REQUEST_FIELDS')
    if type(request['schema']) is not int or request['schema'] != 1:
        raise Hold('SCHEMA')
    for key in ('request_id', 'project'):
        if type(request[key]) is not str or not TOKEN.fullmatch(request[key]):
            raise Hold('INVALID_ID')
    if request['target'] not in TARGETS:
        raise Hold('UNREGISTERED_TARGET')
    if (type(executor_sha256) is not str or not SHA.fullmatch(executor_sha256)
            or request['executor_sha256'] != executor_sha256):
        raise Hold('EXECUTOR_VERSION')
    if (type(request['expires_unix']) is not int
            or not now < request['expires_unix'] <= now + 86400):
        raise Hold('EXPIRY')
    # No arbitrary shell, path, URL, user or root command is accepted here.
    # Production management operations require a separately reviewed policy.
    if request['operation'] == 'probe':
        expected = {}
    elif request['operation'] == 'fetch_os_release':
        expected = {'path': '/etc/os-release', 'max_bytes': 65536}
    elif request['operation'] == 'fetch_approved_object' and approved_objects is not None:
        approved_objects.validate(request, actor_id, now)
        return
    elif request['operation'] == 'project_fixed_action' and project_actions is not None:
        project_actions.validate(request, actor_id, now)
        return
    else:
        raise Hold('OPERATION_NOT_ENROLLED')
    if request['arguments'] != expected or type(request['arguments']) is not dict:
        raise Hold('ARGUMENTS')


class Queue:
    """Host-private SQLite file; not an AuthorityStore or an installation quota."""
    def __init__(self, path, executor_sha256, allowed_actors, project_actions=None,
                 approved_objects=None, existing_readonly=False, existing_custody=False):
        self.project_actions = project_actions
        self.approved_objects = approved_objects
        self.executor_sha256 = executor_sha256
        self.allowed_actors = frozenset(allowed_actors)
        if existing_readonly is True or existing_custody is True:
            if existing_readonly is not False and existing_custody is not False:
                raise Hold('QUEUE_EXISTING_MODE_CONFLICT')
            # A maintenance observer cannot initialize an empty application DB.
            # This path is fixed by the reviewed caller, never a request field.
            if (type(path) is not str or not path.startswith('/') or
                    os.path.normpath(path) != path):
                raise Hold('QUEUE_EXISTING_PATH')
            fd = open_existing_file(path)
            try:
                before = os.fstat(fd)
                live = os.stat(path, follow_symlinks=False)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                        before.st_uid != os.geteuid() or
                        stat.S_IMODE(before.st_mode) not in (0o600, 0o400) or
                        (before.st_dev, before.st_ino) != (live.st_dev, live.st_ino)):
                    raise Hold('QUEUE_EXISTING_IDENTITY')
                mode='rw' if existing_custody is True else 'ro'
                self.db = sqlite3.connect('file:' + path + '?mode='+mode, uri=True,
                                          timeout=0, isolation_level=None)
                after = os.fstat(fd)
                current = os.stat(path, follow_symlinks=False)
                if ((before.st_dev, before.st_ino, before.st_size,
                     before.st_mtime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or
                    (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)):
                    self.db.close()
                    raise Hold('QUEUE_EXISTING_CHANGED')
            finally:
                os.close(fd)
            try:
                names = {row[0]: (row[1],row[2]) for row in self.db.execute(
                    "SELECT name,type,sql FROM sqlite_master WHERE name IN "
                    "('connection_jobs','connection_active_project',"
                    "'connection_no_delete','connection_no_replace','connection_no_rebind')")}
                types={'connection_jobs':'table','connection_active_project':'index',
                       'connection_no_delete':'trigger','connection_no_replace':'trigger',
                       'connection_no_rebind':'trigger'}
                if (set(names)!=set(EXISTING_SCHEMA) or
                        any(names[n][0]!=types[n] or
                            re.sub(r'\s+',' ',names[n][1]).strip()!=EXISTING_SCHEMA[n]
                            for n in EXISTING_SCHEMA)):
                    raise Hold('QUEUE_EXISTING_SCHEMA')
                columns = [row[1] for row in self.db.execute(
                    'PRAGMA table_info(connection_jobs)')]
                if columns != ['request_id','project','request_json','request_sha',
                               'actor_id','state','invoke_id','receipt_json']:
                    raise Hold('QUEUE_EXISTING_COLUMNS')
                self.db.execute('PRAGMA query_only='+('OFF' if existing_custody is True else 'ON'))
            except BaseException:
                self.db.close()
                raise
            return
        if existing_readonly is not False or existing_custody is not False:
            raise Hold('QUEUE_EXISTING_MODE')
        self.db = sqlite3.connect(path, timeout=0, isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA recursive_triggers=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS connection_jobs (
            request_id TEXT PRIMARY KEY, project TEXT NOT NULL,
            request_json TEXT NOT NULL, request_sha TEXT NOT NULL,
            actor_id INTEGER NOT NULL, state TEXT NOT NULL
              CHECK(state IN ('READY','DISPATCHING','UNKNOWN','SUCCESS','FAILED')),
            invoke_id TEXT, receipt_json TEXT);
          CREATE UNIQUE INDEX IF NOT EXISTS connection_active_project
            ON connection_jobs(project) WHERE state IN ('DISPATCHING','UNKNOWN');
          CREATE TRIGGER IF NOT EXISTS connection_no_delete
            BEFORE DELETE ON connection_jobs BEGIN
              SELECT RAISE(ABORT,'IMMUTABLE_CONNECTION_HISTORY'); END;
          CREATE TRIGGER IF NOT EXISTS connection_no_replace
            BEFORE INSERT ON connection_jobs
            WHEN EXISTS(SELECT 1 FROM connection_jobs WHERE request_id=NEW.request_id)
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_REQUEST'); END;
          CREATE TRIGGER IF NOT EXISTS connection_no_rebind
            BEFORE UPDATE OF request_id,project,request_json,request_sha,actor_id
            ON connection_jobs BEGIN SELECT RAISE(ABORT,'IMMUTABLE_REQUEST'); END;
        ''')

    def close(self):
        self.db.close()

    def submit(self, raw, authenticated_actor_id, now):
        request = decode(raw)
        validate(request, authenticated_actor_id, self.allowed_actors,
                 self.executor_sha256, now, self.project_actions, self.approved_objects)
        body = canonical(request)
        digest = hashlib.sha256(body.encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT request_sha,actor_id,state FROM connection_jobs '
                                  'WHERE request_id=?', (request['request_id'],)).fetchone()
            if old:
                if old[:2] != (digest, authenticated_actor_id):
                    raise Hold('REQUEST_ID_REBOUND')
                state = old[2]
            else:
                self.db.execute('INSERT INTO connection_jobs VALUES(?,?,?,?,?,?,NULL,NULL)',
                                (request['request_id'], request['project'], body,
                                 digest, authenticated_actor_id, 'READY'))
                state = 'READY'
            self.db.execute('COMMIT')
            return {'request_id': request['request_id'], 'state': state}
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def begin_dispatch(self, request_id, now):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT request_json,actor_id,state FROM connection_jobs '
                                  'WHERE request_id=?', (request_id,)).fetchone()
            if row is None or row[2] != 'READY':
                raise Hold('NOT_READY_QUERY_EXISTING_ONLY')
            request = decode(row[0])
            validate(request, row[1], self.allowed_actors, self.executor_sha256, now, self.project_actions, self.approved_objects)
            self.db.execute("UPDATE connection_jobs SET state='DISPATCHING' WHERE request_id=?",
                            (request_id,))
            self.db.execute('COMMIT')
            return request
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def record_invoke(self, request_id, invoke_id):
        if type(invoke_id) is not str or not TOKEN.fullmatch(invoke_id):
            raise Hold('INVOKE_ID')
        c = self.db.execute("UPDATE connection_jobs SET invoke_id=? WHERE request_id=? "
                            "AND state='DISPATCHING' AND invoke_id IS NULL", (invoke_id, request_id))
        if c.rowcount != 1:
            raise Hold('INVOKE_REBIND_OR_STATE')

    def unknown(self, request_id):
        self.db.execute("UPDATE connection_jobs SET state='UNKNOWN' WHERE request_id=? "
                        "AND state='DISPATCHING'", (request_id,))

    def terminal(self, request_id, invoke_id, receipt):
        # The transport validator supplies this receipt after checking target,
        # instance, nonce, exit status and file digest. This is not that validator.
        if type(receipt) is not dict or receipt.get('state') not in ('SUCCESS', 'FAILED'):
            raise Hold('TERMINAL_RECEIPT')
        c = self.db.execute('UPDATE connection_jobs SET state=?,receipt_json=? '
                            "WHERE request_id=? AND invoke_id=? AND state IN ('DISPATCHING','UNKNOWN')",
                            (receipt['state'], canonical(receipt), request_id, invoke_id))
        if c.rowcount != 1:
            raise Hold('QUERY_BINDING_OR_ALREADY_TERMINAL')

    def inspect(self, request_id):
        row = self.db.execute('SELECT state,invoke_id,receipt_json FROM connection_jobs '
                              'WHERE request_id=?', (request_id,)).fetchone()
        if row is None:
            raise Hold('REQUEST_NOT_FOUND')
        return {'state': row[0], 'invoke_id': row[1],
                'receipt': json.loads(row[2]) if row[2] else None,
                'redispatch_allowed': row[0] == 'READY'}
