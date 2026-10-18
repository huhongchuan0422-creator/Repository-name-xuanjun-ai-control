"""Official SQLite recovery/backup over a private, bounded bytes-only VFS.

No database path is accepted. Main/WAL are captured immutable caller bytes;
SQLite may change only disposable heap copies. No production fence is implied.
This does not exercise or replace M99 directory-replacement acceptance.
Public ABI: https://sqlite.org/c3ref/vfs.html and c3ref/io_methods.html.
"""
import ctypes as C
import hashlib
import json
import threading
import time
import uuid

P = C.c_void_p
I = C.c_int
L = C.c_longlong
S = C.c_char_p
PI = C.POINTER(I)
PL = C.POINTER(L)
PP = C.POINTER(P)
SQLITE_OK, SQLITE_ERROR, SQLITE_IOERR, SQLITE_NOTFOUND = 0, 1, 10, 12
SQLITE_CANTOPEN, SQLITE_FULL, SQLITE_DONE = 14, 13, 101
SQLITE_IOERR_SHORT_READ = SQLITE_IOERR | (2 << 8)
LIMIT = 64 * 1024 * 1024
_SERIAL = threading.RLock()
_QUARANTINED = []  # Keep C callbacks alive if an unexpected close ever fails.


class WalHold(RuntimeError):
    pass


class File(C.Structure):
    _fields_ = [('methods', P), ('slot', I)]


class Methods(C.Structure):
    _fields_ = [('version', I)] + [(name, P) for name in (
        'close', 'read', 'write', 'truncate', 'sync', 'size', 'lock', 'unlock',
        'reserved', 'control', 'sector', 'characteristics', 'shm_map', 'shm_lock',
        'shm_barrier', 'shm_unmap')]


class Vfs(C.Structure):
    # iVersion=1: do not expose unimplemented newer methods to SQLite.
    _fields_ = [('version', I), ('file_size', I), ('max_path', I), ('next', P),
               ('name', S), ('app', P)] + [(name, P) for name in (
        'open', 'delete', 'access', 'full_path', 'dl_open', 'dl_error', 'dl_sym',
        'dl_close', 'random', 'sleep', 'current_time', 'last_error')]


def _library():
    # No caller-selected library or SQL, no loadable-extension entry.
    try: lib = C.CDLL('libsqlite3.so.0')
    except OSError: raise WalHold('SQLITE_RUNTIME_UNAVAILABLE') from None
    signatures = {
        'sqlite3_libversion': (S, []), 'sqlite3_sourceid': (S, []),
        'sqlite3_vfs_register': (I, [C.POINTER(Vfs), I]),
        'sqlite3_vfs_unregister': (I, [C.POINTER(Vfs)]),
        'sqlite3_open_v2': (I, [S, PP, I, S]), 'sqlite3_close': (I, [P]),
        'sqlite3_exec': (I, [P, S, P, P, PP]), 'sqlite3_free': (None, [P]),
        'sqlite3_backup_init': (P, [P, S, P, S]),
        'sqlite3_backup_step': (I, [P, I]), 'sqlite3_backup_finish': (I, [P]),
        'sqlite3_wal_checkpoint_v2': (I, [P, S, I, PI, PI]),
        'sqlite3_serialize': (P, [P, S, PL, I]),
        'sqlite3_prepare_v2': (I, [P, S, I, PP, C.POINTER(S)]),
        'sqlite3_step': (I, [P]), 'sqlite3_finalize': (I, [P]),
        'sqlite3_column_count': (I, [P]), 'sqlite3_column_type': (I, [P, I]),
        'sqlite3_column_text': (S, [P, I]),
        'sqlite3_enable_load_extension': (I, [P, I]),
        'sqlite3_progress_handler': (None, [P, I, P, P]),
        'sqlite3_randomness': (None, [I, P]),
    }
    try:
        for name, (restype, args) in signatures.items():
            f = getattr(lib, name); f.restype = restype; f.argtypes = args
    except AttributeError:
        raise WalHold('SQLITE_OFFICIAL_API_UNAVAILABLE') from None
    return lib


class MemoryVfs:
    """One source connection per unique VFS, serialized by this module.

    Database locks are no-ops ONLY because these heap bytes cannot be opened by
    another VFS/process and this object never exposes its connection. This is
    not a filesystem-lock replacement and must never wrap an original file.
    """
    def __init__(self, lib, main, wal, progress):
        self.lib, self.progress = lib, progress
        self.files = [bytearray(main), None if wal is None else bytearray(wal)]
        self.shm = []
        self.callbacks = []
        self.failed = False
        self.opened = []
        self.denied = 0
        self.write_calls = 0
        self.registered = False
        self.name = ('pr99-wal-' + uuid.uuid4().hex).encode()
        self.methods = Methods(); self.methods.version = 2
        self.vfs = Vfs(); self.vfs.version = 1
        self.vfs.file_size = C.sizeof(File); self.vfs.max_path = 100
        self.vfs.name = self.name
        self._callbacks()

    def callback(self, table, field, restype, args, function, failure=SQLITE_IOERR):
        def guarded(*values):
            try:
                self.progress()
                return function(*values)
            except BaseException:
                self.failed = True
                return failure
        cb = C.CFUNCTYPE(restype, *args)(guarded)
        self.callbacks.append(cb)
        setattr(table, field, C.cast(cb, P))

    def data(self, file):
        slot = C.cast(file, C.POINTER(File)).contents.slot
        if slot not in (0, 1) or self.files[slot] is None:
            raise WalHold('VFS_FILE_IDENTITY')
        return self.files[slot]

    def _callbacks(self):
        cb, m, v = self.callback, self.methods, self.vfs
        cb(m, 'close', I, [P], lambda f: SQLITE_OK)
        def read(f, dst, count, offset):
            if not 0 <= count <= LIMIT or not 0 <= offset <= LIMIT:
                return SQLITE_IOERR
            data = self.data(f)
            C.memset(dst, 0, count)
            raw = bytes(data[offset:offset+count])
            if raw: C.memmove(dst, raw, len(raw))
            return SQLITE_OK if len(raw) == count else SQLITE_IOERR_SHORT_READ
        cb(m, 'read', I, [P, P, I, L], read)
        def write(f, src, count, offset):
            if not 0 <= count <= LIMIT or not 0 <= offset <= LIMIT - count:
                return SQLITE_FULL
            data = self.data(f); end = offset + count
            if len(data) < end: data.extend(b'\0' * (end-len(data)))
            data[offset:end] = C.string_at(src, count)
            self.write_calls += 1
            return SQLITE_OK
        cb(m, 'write', I, [P, P, I, L], write)
        def truncate(f, size):
            if not 0 <= size <= LIMIT: return SQLITE_FULL
            data = self.data(f)
            if size < len(data): del data[size:]
            else: data.extend(b'\0' * (size-len(data)))
            return SQLITE_OK
        cb(m, 'truncate', I, [P, L], truncate)
        cb(m, 'sync', I, [P, I], lambda *a: SQLITE_OK)
        def size(f, out): out[0] = len(self.data(f)); return SQLITE_OK
        cb(m, 'size', I, [P, PL], size)
        cb(m, 'lock', I, [P, I], lambda *a: SQLITE_OK)
        cb(m, 'unlock', I, [P, I], lambda *a: SQLITE_OK)
        def reserved(f, out): out[0] = 0; return SQLITE_OK
        cb(m, 'reserved', I, [P, PI], reserved)
        cb(m, 'control', I, [P, I, P], lambda *a: SQLITE_NOTFOUND)
        cb(m, 'sector', I, [P], lambda *a: 4096)
        # In particular: NEVER advertise IMMUTABLE (which could ignore the WAL).
        cb(m, 'characteristics', I, [P], lambda *a: 0)
        def shm_map(f, page, size, extend, out):
            out[0] = None
            if C.cast(f, C.POINTER(File)).contents.slot != 0 or not 0 <= page < 64 or size != 32768:
                return SQLITE_IOERR
            if page >= len(self.shm):
                if not extend: return SQLITE_OK
                while len(self.shm) <= page: self.shm.append(C.create_string_buffer(size))
            out[0] = C.cast(self.shm[page], P).value
            return SQLITE_OK
        cb(m, 'shm_map', I, [P, I, I, I, PP], shm_map)
        cb(m, 'shm_lock', I, [P, I, I, I], lambda *a: SQLITE_OK)
        cb(m, 'shm_barrier', None, [P], lambda *a: None, None)
        cb(m, 'shm_unmap', I, [P, I], lambda *a: SQLITE_OK)
        def open_file(vfs, name, rawfile, flags, out):
            f = C.cast(rawfile, C.POINTER(File)); f.contents.methods = None
            slots = {b'/pr99/source.db': 0, b'/pr99/source.db-wal': 1}
            if name not in slots:
                self.denied += 1; return SQLITE_CANTOPEN
            slot = slots[name]
            if self.files[slot] is None:
                # Only a private WAL may be created; never an on-disk fallback.
                if slot != 1 or not flags & 4: return SQLITE_CANTOPEN
                self.files[slot] = bytearray()
            self.opened.append(slot)
            f.contents.slot = slot; f.contents.methods = C.cast(C.pointer(m), P).value
            out[0] = flags
            return SQLITE_OK
        cb(v, 'open', I, [P, S, P, I, PI], open_file)
        def delete(vfs, name, sync):
            if name == b'/pr99/source.db-wal': self.files[1] = None; return SQLITE_OK
            self.denied += 1; return SQLITE_IOERR
        cb(v, 'delete', I, [P, S, I], delete)
        def access(vfs, name, flags, out):
            out[0] = int(name == b'/pr99/source.db' or
                         name == b'/pr99/source.db-wal' and self.files[1] is not None)
            return SQLITE_OK
        cb(v, 'access', I, [P, S, I, PI], access)
        def full_path(vfs, name, count, out):
            if name != b'/pr99/source.db' or count <= len(name):
                self.denied += 1; return SQLITE_CANTOPEN
            C.memmove(out, name+b'\0', len(name)+1); return SQLITE_OK
        cb(v, 'full_path', I, [P, S, I, P], full_path)
        cb(v, 'dl_open', P, [P, S], lambda *a: None, None)
        cb(v, 'dl_sym', P, [P, P, S], lambda *a: None, None)
        cb(v, 'dl_close', None, [P, P], lambda *a: None, None)
        def dl_error(vfs, count, out):
            if count: C.memset(out, 0, count)
        cb(v, 'dl_error', None, [P, I, P], dl_error, None)
        def randomness(vfs, count, out):
            if not 0 <= count <= 4096: return 0
            self.lib.sqlite3_randomness(count, out); return count
        cb(v, 'random', I, [P, I, P], randomness, 0)
        cb(v, 'sleep', I, [P, I], lambda *a: 0, 0)
        def current(vfs, out): out[0] = time.time()/86400.0+2440587.5; return SQLITE_OK
        cb(v, 'current_time', I, [P, C.POINTER(C.c_double)], current)
        cb(v, 'last_error', I, [P, I, P], lambda *a: 0, 0)

    def __enter__(self):
        if self.lib.sqlite3_vfs_register(C.byref(self.vfs), 0) != SQLITE_OK:
            raise WalHold('VFS_REGISTRATION_FAILED')
        self.registered = True
        return self

    def __exit__(self, *args):
        if self.registered and not getattr(self, 'keepalive', False):
            self.lib.sqlite3_vfs_unregister(C.byref(self.vfs)); self.registered = False


def recover(main, wal, expected_schema_sha256, progress=lambda: None, seconds=30):
    """Return (standalone bytes, non-authoritative implementation receipt).

    Caller must capture a stable, fenced main+WAL set and retain it on any error.
    No filename, SQLite URI or caller SQL is accepted or derived from data.
    """
    if type(main) is not bytes or not 100 <= len(main) <= LIMIT or main[:16] != b'SQLite format 3\0':
        raise WalHold('SQLITE_MAIN_BOUND_OR_HEADER')
    if wal is not None and (type(wal) is not bytes or len(wal) > LIMIT):
        raise WalHold('SQLITE_WAL_BOUND_OR_TYPE')
    frames = 0
    if wal:
        # Framing only; SQLite, never this module, validates checksums/commits
        # and applies WAL pages. Reject an ignored/corrupt/uncommitted tail.
        if len(wal) < 32 or wal[:4] not in (b'7\x7f\x06\x82', b'7\x7f\x06\x83'):
            raise WalHold('SQLITE_WAL_FRAMING')
        page = int.from_bytes(wal[8:12], 'big')
        if page < 512 or page > 65536 or page & (page-1) or (len(wal)-32) % (24+page):
            raise WalHold('SQLITE_WAL_FRAMING')
        frames = (len(wal)-32)//(24+page)
        if not frames: raise WalHold('SQLITE_WAL_EMPTY_FRAMES')
    if type(expected_schema_sha256) is not str or len(expected_schema_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_schema_sha256):
        raise WalHold('SQLITE_SCHEMA_BINDING')
    if type(seconds) not in (int, float) or not 0 < seconds <= 90:
        raise WalHold('SQLITE_DEADLINE_BOUND')
    deadline = time.monotonic() + seconds
    def check():
        if time.monotonic() >= deadline: raise WalHold('SQLITE_DEADLINE')
        progress()
    with _SERIAL:
        if _QUARANTINED: raise WalHold('SQLITE_PRIOR_CLOSE_UNKNOWN_PROCESS_RESTART_REQUIRED')
        lib = _library(); src, dst = P(), P(); backup = None
        def ok(code):
            if code != SQLITE_OK: raise WalHold('SQLITE_OPERATION_FAILED_' + str(code))
        def execute(db, text):
            error = P()
            code = lib.sqlite3_exec(db, text, None, None, C.byref(error))
            if error: lib.sqlite3_free(error)
            ok(code)
        def rows(db, sql):
            stmt = P(); tail = S()
            ok(lib.sqlite3_prepare_v2(db, sql, -1, C.byref(stmt), C.byref(tail)))
            result = []
            try:
                while True:
                    check(); code = lib.sqlite3_step(stmt)
                    if code == SQLITE_DONE: return result
                    if code != 100: ok(code)
                    result.append([None if lib.sqlite3_column_type(stmt, i) == 5
                                   else lib.sqlite3_column_text(stmt, i).decode('utf-8')
                                   for i in range(lib.sqlite3_column_count(stmt))])
                    if len(result) > 20000: raise WalHold('SQLITE_RESULT_BOUND')
            finally: lib.sqlite3_finalize(stmt)
        def tick(_):
            try: check(); return 0
            except BaseException: return 1
        callback = C.CFUNCTYPE(I, P)(tick)
        with MemoryVfs(lib, main, wal, check) as vfs:
            try:
                check()
                ok(lib.sqlite3_open_v2(b'/pr99/source.db', C.byref(src), 2 | 65536, vfs.name))
                # Explicit MEMORY guarantees no default filesystem DB for destination.
                ok(lib.sqlite3_open_v2(b':memory:', C.byref(dst), 2 | 4 | 128 | 65536, None))
                for db in (src, dst):
                    ok(lib.sqlite3_enable_load_extension(db, 0))
                    lib.sqlite3_progress_handler(db, 1000, C.cast(callback, P), None)
                    execute(db, b'PRAGMA temp_store=MEMORY;PRAGMA trusted_schema=OFF;')
                if wal:
                    rows(src, b'SELECT name FROM sqlite_master LIMIT 1')
                    logged, checkpointed = I(-1), I(-1)
                    # Checkpoint ONLY the disposable VFS heap copies, never an
                    # original/captured file. Every physical input WAL frame
                    # must be in SQLite's validated committed prefix.
                    ok(lib.sqlite3_wal_checkpoint_v2(src, b'main', 0,
                        C.byref(logged), C.byref(checkpointed)))
                    if logged.value != frames or checkpointed.value != frames:
                        raise WalHold('SQLITE_WAL_NOT_FULLY_COMMITTED_AND_VALID')
                execute(src, b'PRAGMA query_only=ON;')
                backup = lib.sqlite3_backup_init(dst, b'main', src, b'main')
                if not backup: raise WalHold('SQLITE_BACKUP_INIT')
                while True:
                    check(); code = lib.sqlite3_backup_step(backup, 128)
                    if code == SQLITE_DONE: break
                    if code != SQLITE_OK: ok(code)
                code = lib.sqlite3_backup_finish(backup); backup = None; ok(code)
                if rows(dst, b'PRAGMA integrity_check') != [['ok']]:
                    raise WalHold('SQLITE_INTEGRITY')
                schema = rows(dst, b"SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")
                encoded = (json.dumps(schema, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
                if hashlib.sha256(encoded).hexdigest() != expected_schema_sha256:
                    raise WalHold('SQLITE_SCHEMA_MISMATCH')
                size = L(); raw = lib.sqlite3_serialize(dst, b'main', C.byref(size), 0)
                if not raw: raise WalHold('SQLITE_SERIALIZE_FAILED')
                try:
                    if not 100 <= size.value <= LIMIT: raise WalHold('SQLITE_OUTPUT_BOUND')
                    result = bytearray(C.string_at(raw, size.value))
                    # After official recovery+backup this is a complete main DB.
                    # Official deserialize guidance requires rollback format for
                    # a standalone in-memory image; inputs are never normalized.
                    result[18:20] = b'\x01\x01'; result = bytes(result)
                finally: lib.sqlite3_free(raw)
                check()
                if vfs.failed or vfs.denied: raise WalHold('VFS_FAILURE_OR_DENIED_ACCESS')
                receipt = {'status': 'COPIED_BYTES_RECOVERED_NOT_FENCE_OR_MIGRATION',
                    'input_main_sha256': hashlib.sha256(main).hexdigest(),
                    'input_wal_sha256': None if wal is None else hashlib.sha256(wal).hexdigest(),
                    'nonempty_wal_supplied': bool(wal), 'output_sha256': hashlib.sha256(result).hexdigest(),
                    'schema_sha256': expected_schema_sha256, 'integrity': 'PASS',
                    'sqlite_version': lib.sqlite3_libversion().decode(),
                    'sqlite_source_id': lib.sqlite3_sourceid().decode(),
                    'vfs_opened_slots': sorted(set(vfs.opened)),
                    'validated_committed_wal_frames': frames,
                    'checkpoint_scope': 'DISPOSABLE_HEAP_COPIES_ONLY' if wal else 'NONE',
                    'vfs_disk_fallback': False, 'source_database_opened': False,
                    'production_fence_verified': False}
                if wal and 1 not in vfs.opened: raise WalHold('SQLITE_WAL_NOT_OPENED')
                return result, receipt
            finally:
                if backup: lib.sqlite3_backup_finish(backup)
                live = []
                for db in (dst, src):
                    if db and lib.sqlite3_close(db) != SQLITE_OK:
                        live.append(db)
                if live:
                    # Never free a ctypes callback or unregister its VFS while
                    # SQLite might still call it. No subsequent recovery allowed.
                    vfs.keepalive = True
                    _QUARANTINED.append((vfs, lib, callback, live))
                    raise WalHold('SQLITE_CLOSE_FAILED_PROCESS_RESTART_REQUIRED')
