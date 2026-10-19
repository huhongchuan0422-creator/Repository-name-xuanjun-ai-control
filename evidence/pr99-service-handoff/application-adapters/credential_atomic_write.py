"""Same-database credential/binding commits on an already configured SQLite DB.

No DB path, schema, Writer, lock, or migration journal is created here. The
original controller supplies an existing connection, schema and Writer guard.
Schema installation and real application startup are separate site actions.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from credential_key_binding import CredentialBindingHold, fingerprint
from credential_write_preparation import prepare_native_save

# Run only during an explicit schema installation, never implicitly on open.
SCHEMA_SQL = (
    'CREATE TABLE pr99_credential_key_bindings ('
    'credential_id TEXT PRIMARY KEY, record_sha256 TEXT NOT NULL, key_ref TEXT NOT NULL)',
    'CREATE TABLE pr99_credential_write_results ('
    'operation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, '
    'credential_id TEXT NOT NULL, record_sha256 TEXT NOT NULL)'
)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def request_digest(prepared, expected):
    return hashlib.sha256(encode({'prepared': prepared, 'expected': expected}).encode()).hexdigest()


class AtomicCredentialWriter:
    def __init__(self, connection, assert_writer):
        if not isinstance(connection, sqlite3.Connection) or not callable(assert_writer):
            raise CredentialBindingHold('EXISTING_CONNECTION_AND_WRITER_REQUIRED')
        self.db = connection
        self.guard = assert_writer
        # Merely opening a coordinator must not start or commit a transaction.
        for table in ('credential_records', 'pr99_credential_key_bindings',
                      'pr99_credential_write_results'):
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  (table,)).fetchone() is None:
                raise CredentialBindingHold('EXPLICIT_SCHEMA_INSTALL_REQUIRED')

    def _guard(self):
        if self.guard() is not True:
            raise CredentialBindingHold('ORIGINAL_WRITER_NOT_HELD')

    def get(self, credential_id):
        cursor = self.db.execute('SELECT * FROM credential_records WHERE credential_id=?',
                                 (credential_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        result = dict(zip([c[0] for c in cursor.description], row))
        if 'metadata_json' in result:
            result['metadata'] = json.loads(result['metadata_json'] or '{}')
        return result

    def binding(self, credential_id):
        row = self.db.execute('SELECT record_sha256,key_ref FROM '
                              'pr99_credential_key_bindings WHERE credential_id=?',
                              (credential_id,)).fetchone()
        return None if row is None else dict(record_sha256=row[0], key_ref=row[1])

    def query(self, operation_id, digest):
        self._guard()
        row = self.db.execute('SELECT request_sha256,credential_id,record_sha256 FROM '
                              'pr99_credential_write_results WHERE operation_id=?',
                              (operation_id,)).fetchone()
        if row is None:
            return {'status': 'UNKNOWN_QUERY_ONLY'}
        if row[0] != digest:
            raise CredentialBindingHold('OPERATION_ID_CONFLICT')
        record, binding = self.get(row[1]), self.binding(row[1])
        if record is None or binding is None or fingerprint(record) != row[2] or binding['record_sha256'] != row[2]:
            raise CredentialBindingHold('COMMITTED_RECORD_CHANGED')
        return {'status': 'COMMITTED', 'credential_id': row[1], 'record_sha256': row[2]}

    def commit(self, operation_id, prepared, expected_record_sha256):
        """CAS save + binding + idempotency result in ONE SQLite transaction.

        None means create only. A digest means update that exact prior record.
        Outer original durable controller remains responsible for recording an
        intent before calling; an unknown previous dispatch calls query only.
        """
        self._guard()
        if self.db.in_transaction:
            raise CredentialBindingHold('BORROWED_TRANSACTION_BUSY')
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 200:
            raise CredentialBindingHold('OPERATION_ID_REQUIRED')
        try:
            record, binding = dict(prepared['record']), dict(prepared['binding'])
            digest = fingerprint(record)
            if (prepared['state'] != 'PREPARED_NOT_COMMITTED' or
                    binding['record_sha256'] != digest or not isinstance(binding['key_ref'], str) or
                    not binding['key_ref']):
                raise ValueError()
            columns = {r[1] for r in self.db.execute('PRAGMA table_info(credential_records)')}
            allowed = {'credential_id','customer_id','account_id','exchange','environment',
                       'key_ciphertext','key_nonce','secret_ciphertext','secret_nonce',
                       'algorithm','key_version','status','fingerprint','permission_state',
                       'verification_state','trade_permission','withdraw_permission',
                       'legacy_migration_required','metadata'}
            if set(record) - allowed:
                raise ValueError()
            values = dict(record)
            if 'metadata' in values:
                values['metadata_json'] = encode(values.pop('metadata'))
            if not set(values) <= columns:
                raise ValueError()
            request_sha = request_digest(prepared, expected_record_sha256)
        except Exception:
            raise CredentialBindingHold('WRITE_INPUT_CONTRACT_INVALID') from None
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self._guard()
            prior = self.query(operation_id, request_sha)
            if prior['status'] == 'COMMITTED':
                self.db.rollback()
                return prior
            current = self.get(record['credential_id'])
            if (current is None) != (expected_record_sha256 is None):
                raise CredentialBindingHold('RECORD_CAS_CONFLICT')
            if current is not None and fingerprint(current) != expected_record_sha256:
                raise CredentialBindingHold('RECORD_CAS_CONFLICT')
            if 'updated_time' in columns:
                values['updated_time'] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ')
            if current is None and 'created_time' in columns:
                values['created_time'] = values.get('updated_time') or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ')
            if current is None:
                keys = sorted(values)
                # Column names only come from the fixed allowlist and inspected schema.
                self.db.execute('INSERT INTO credential_records (' + ','.join(keys) +
                                ') VALUES (' + ','.join('?' for k in keys) + ')',
                                [values[k] for k in keys])
            else:
                keys = sorted(k for k in values if k != 'credential_id')
                self.db.execute('UPDATE credential_records SET ' +
                                ','.join(k+'=?' for k in keys) + ' WHERE credential_id=?',
                                [values[k] for k in keys] + [record['credential_id']])
            stored = self.get(record['credential_id'])
            if fingerprint(stored) != digest:
                raise CredentialBindingHold('STORED_RECORD_MISMATCH')
            self.db.execute('INSERT INTO pr99_credential_key_bindings VALUES (?,?,?) '
                            'ON CONFLICT(credential_id) DO UPDATE SET '
                            'record_sha256=excluded.record_sha256,key_ref=excluded.key_ref',
                            (record['credential_id'], digest, binding['key_ref']))
            self.db.execute('INSERT INTO pr99_credential_write_results VALUES (?,?,?,?)',
                            (operation_id, request_sha, record['credential_id'], digest))
            self._guard()
            self.db.commit()
        except BaseException:
            # A commit error can be ambiguous; never return success or auto-replay.
            try:
                self.db.rollback()
            except Exception:
                pass
            raise CredentialBindingHold('WRITE_UNKNOWN_QUERY_ONLY') from None
        return self.query(operation_id, request_sha)


class BoundCredentialStore:
    """Native encryption and decryption with explicit durable binding selection."""
    def __init__(self, writer, native_store_factory, key_inputs, write_key_ref):
        self.writer, self.factory = writer, native_store_factory
        self.keys = dict(key_inputs)
        self.write_ref = write_key_ref
        if write_key_ref not in self.keys:
            raise CredentialBindingHold('WRITE_KEY_UNBOUND')

    def prepare_save(self, **arguments):
        return prepare_native_save(self.factory, self.write_ref,
                                   self.keys[self.write_ref], **arguments)

    def load_credential(self, credential_id):
        from credential_key_binding import BoundCredentialReader
        binding = self.writer.binding(credential_id)
        if binding is None:
            raise CredentialBindingHold('UNBOUND_RECORD')
        return BoundCredentialReader(self.writer, self.factory,
                                     {credential_id: binding}, self.keys).load_credential(credential_id)
