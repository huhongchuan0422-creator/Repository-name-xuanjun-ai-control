"""Fail-closed SQLite schema attestation for offline Stage5 stores.

Inspects actual columns, DDL, constraints and named triggers rather than just
table names. This protects the supported exact schema, not an auto-migration.
"""
import re
import sqlite3

def _normalize(sql):
    return re.sub(r"\s+", " ", re.sub(r"\bIF NOT EXISTS\b", "", sql, flags=re.I)).strip().rstrip(";")

def objects(db):
    return {(typ,name):_normalize(sql)
            for typ,name,sql in db.execute(
                "SELECT type,name,sql FROM sqlite_master "
                "WHERE type IN ('table','trigger','index') AND name NOT LIKE 'sqlite_%'")}

def verify(db, schema, expected_tables, version=1, extra_schema=None):
    reference=sqlite3.connect(":memory:")
    try:
        reference.executescript(schema)
        if extra_schema is not None:reference.executescript(extra_schema)
        actual=objects(db)
        wanted=objects(reference)
        if actual!=wanted or db.execute("PRAGMA user_version").fetchone()[0]!=version:
            raise ValueError("UNRECOGNIZED_DATABASE_SCHEMA")
        observed={name for typ,name in actual if typ=="table"}
        if observed!=set(expected_tables):
            raise ValueError("UNRECOGNIZED_DATABASE_SCHEMA")
    finally:
        reference.close()

def transactional_install(db, schema, checker):
    # Do not clobber an outer transaction; fail closed instead of silently
    # committing the caller's work, which executescript otherwise would do.
    if db.in_transaction:
        raise ValueError("SCHEMA_INSTALL_DURING_TRANSACTION")
    try:
        db.executescript("BEGIN IMMEDIATE;\n"+schema+"\nCOMMIT;")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    checker()
