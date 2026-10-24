"""NEW private-copy native save/verification and durable JSON acceptance.

Never installs application hooks, claims a production Writer or calls Binance.
"""
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from accept_native_atomic_copy import read_regular, native_factory, SOURCE_SHA, COPY_SHA
from credential_atomic_write import AtomicCredentialWriter, BoundCredentialStore, SCHEMA_SQL, request_digest
from durable_session_write import save_session, query_session


def main():
    assert os.geteuid() == 0
    assert os.uname().nodename.split('.')[0] == 'iZ6wee8q9z4t03hvqumwfhZ'
    os.umask(0o077)
    source = read_regular(Path('/opt/trading-system/accounts/credential_store.py'), 262144)
    snapshot = read_regular(Path('/root/pr99-precopy-dhtmwlx_/database.sqlite'), 67108864)
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA, 'SOURCE_CHANGED'
    assert hashlib.sha256(snapshot).hexdigest() == COPY_SHA, 'COPY_CHANGED'
    base = Path(tempfile.mkdtemp(prefix='pr99-native-verified-copy-', dir='/root'))
    print('DIRECTORY=' + str(base), flush=True)
    stage, db = 'COPY', None
    try:
        path = base / 'private-test.sqlite'
        with path.open('xb') as stream:
            stream.write(snapshot)
            stream.flush()
            os.fsync(stream.fileno())
        del snapshot
        db = sqlite3.connect(str(path))
        baseline = db.execute('SELECT * FROM credential_records ORDER BY id').fetchall()
        assert len(baseline) == 3
        for statement in SCHEMA_SQL:
            db.execute(statement)
        db.commit()
        stage = 'NATIVE_SAVE_AND_MARK_VERIFIED_PREPARATION'
        writer = AtomicCredentialWriter(db, lambda: True)  # Private test only.
        store = BoundCredentialStore(writer, native_factory(source, include_verification=True),
            {'test': base64.b64encode(os.urandom(32)).decode()}, 'test')
        prepared = store.prepare_verified_save(dict(status='ACTIVE',
            verification_state='HEALTHY', permission_state='READ_ONLY_VERIFIED',
            verified_time=datetime(2026, 10, 19), metadata={'synthetic_copy_only': True}),
            customer_id='pr99-copy-test', account_id='pr99-copy-test',
            credential_id='pr99-verified-copy-only', api_key='synthetic-key',
            api_secret='synthetic-secret', trade_permission=False, withdraw_permission=False)
        stage = 'SAME_DATABASE_COMMIT'
        assert writer.commit('verified-copy-only', prepared, None)['status'] == 'COMMITTED'
        row = writer.get('pr99-verified-copy-only')
        assert row['verification_state'] == 'HEALTHY'
        assert row['permission_state'] == 'READ_ONLY_VERIFIED'
        assert row['last_verified_time'] == '2026-10-19 00:00:00'
        assert store.load_credential('pr99-verified-copy-only')['api_secret'] == 'synthetic-secret'
        stage = 'REOPEN_AND_QUERY'
        db.close()
        db = sqlite3.connect(str(path))
        writer = AtomicCredentialWriter(db, lambda: True)
        assert writer.query('verified-copy-only', request_digest(prepared, None))['status'] == 'COMMITTED'
        assert db.execute('SELECT * FROM credential_records WHERE credential_id<>? ORDER BY id',
            ('pr99-verified-copy-only',)).fetchall() == baseline
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        stage = 'PRIVATE_SESSION_DURABLE_SAVE_AND_QUERY'
        session = base / 'synthetic-session.json'
        digest = save_session(session, {'status': 'USED', 'synthetic_copy_only': True}, lambda: True)
        assert query_session(session, digest, lambda: True) == 'DURABLE_MATCH'
        receipt = dict(status='NATIVE_VERIFIED_COPY_AND_SESSION_STORAGE_PASS',
            original_rows_unchanged=3, native_save_mark_verified_load=True,
            reopened_database_query=True, private_session_durable_query=True,
            original_application_session_recovery=False, production_writer_claimed=False,
            live_hook_installed=False, service_changes=0, migration_started=False)
        stage = 'SAVE_RECEIPT'
        target = base / 'receipt.json'
        save_session(target, receipt, lambda: True)
        print('STATUS=' + receipt['status'])
        print('NATIVE_SAVE_VERIFY_LOAD=PASS; REOPEN_QUERY=PASS; ORIGINAL_ROWS=3/3')
        print('PRIVATE_SESSION_STORAGE=PASS; APPLICATION_SESSION_RECOVERY=NOT_WIRED')
        print('RECEIPT=' + str(target))
        print('SHA256=' + hashlib.sha256(target.read_bytes()).hexdigest())
        print('LIVE_HOOK=NOT_INSTALLED; SERVICE_CHANGES=0; MIGRATION_STARTED=NO')
    except Exception as error:
        # Preserve the failed copy; disclose only fixed stage/type, never values.
        print('STATUS=HOLD; STAGE=' + stage + '; ERROR_TYPE=' + type(error).__name__)
        with (base / 'failure.json').open('xb') as stream:
            stream.write(json.dumps({'stage': stage, 'error_type': type(error).__name__}).encode())
            stream.flush()
            os.fsync(stream.fileno())
        raise SystemExit(2)
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    main()
