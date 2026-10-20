"""Offline migration of *known Git schemas* into a new six-store snapshot.

Input is a stopped, separately digested snapshot, never the live state directory.
Historical DDL is fingerprinted by component, not inferred from user_version.
Only existing rows plus new empty tables and stricter triggers are supported.
Frozen quote/order evidence is never repaired, defaulted or re-approved here.
The hosting Center, its encrypted objects and key recovery remain its owner’s.
"""
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
from pathlib import Path

from scripts.community_stage_recovery import NAMES, _private_root, _create, _read, _sync
from scripts.community_order_store import DDL as ORDER_SCHEMA
from scripts.community_merchant_store import SCHEMA as MERCHANT_SCHEMA
from scripts.community_ad_store import SCHEMA as AD_SCHEMA
from scripts.community_refund_preview_store import SCHEMA as REFUND_SCHEMA
from scripts.community_saas_modules import SCHEMA as MODULE_SCHEMA
from scripts.community_saas_offer_catalog import SCHEMA as OFFER_SCHEMA
from scripts.community_saas_order_preparation import SCHEMA as PREP_SCHEMA, LIFECYCLE_SCHEMA
from scripts.community_saas_offline_handoff import REVIEW_SCHEMA

REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
BASE_HISTORY = {
    'orders': ('scripts/community_order_store.py', '7a89888c175d19c95784d59ed99ff61a603a78de',
               'f709461db4abf7535d0755539559633d60357b39a8928c7c9eab719b1ba95162'),
    'merchants': ('scripts/community_merchant_store.py', 'aae3a7cd17aa9d4268f2b87aca365c1fbcfaa7b6',
                  '803810818b7d96a6df8391ece6b2965fe3064fc41c90b94e8485fdd8f652d8d3'),
    'ads': ('scripts/community_ad_store.py', 'b35d9bc4b6773054336d4ccb10bd1251b1119d5c',
            'f39590ba4344ae4e1f68cadcca3f13c06899d75efeb3f97762283fb05f42f3de'),
    'refunds': ('scripts/community_refund_preview_store.py', 'e03f592db03ce5f1d6ed85db77cc523679907300',
                'ebaa300938fc041d091fcb99f71591d4810b83913a11604b331e526e5cfbf6c5'),
}
# Canonical sqlite_master fingerprints read from the original Git history.
# Each value is an exact source commit, with the source path in the group key.
HISTORY = {'scripts/community_saas_modules.py:SCHEMA': {'3585cb0367c225f8abd7a89734b652efb66a7b4bac0843bdfdd8fab150baa0f9': 'bab171c459df62e61acb8b4bb780507f35c43fc3',
                                              'c7e5b5a8cb0a2dd5d3fa060fdc0a6fc394d9e5f6f65bd52f43ce8216c1608581': '7b261b2bcb0c70c90b2342d3624d4f2acfc28abb'},
 'scripts/community_saas_offer_catalog.py:SCHEMA': {'0a0f20f9909a7df42cb74c192c6231abba130ebde7ba8d258097201afea2b916': '0b47f98d656f0ac7b182a724746a72b7f7028e40',
                                                    '8ad186b84451b51792cface756777740447cd3772233c592fd4233fc8b9fbf67': '45bcb41e7d63950da30da22409ff73c3933f8060',
                                                    'cd5f00e890b6dc6cfb6b0772a0045c2ceb2f68e3925179e747988b654a36f06a': '39e8cb9bb5416289a74e14fa486844eff191fac2',
                                                    'd7e9989cdf495266e250a9ed0b122215c7f392ae7cf688b074bbb23e0493f15d': '6578f9dd820451a52e93ab1afe2687a3eb205fcb'},
 'scripts/community_saas_offline_handoff.py:REVIEW_SCHEMA': {'0abe0d46bab97041a768b41b88eec81ffa65d72f630ed52d43fd08f2475e2370': '3ecc67f1ad4bc2259a8af2629d780b878c1c3690',
                                                             '12f50d8b7a66ab436fffcb9f505cd37ae9151b277b977afd49b82c4a396c5aec': 'bb4bfd9178f700838713abdefdb042462e9ca715',
                                                             'c35939f2db9c2db6c907738a0dfe50a4208bf6373578e64b94e0c2891b88173e': '72f1eeb87ab66b628aaa2b7ea458421bb91055f2',
                                                             'db5af9dcae213639a578dfd152a0a8590154562fc65ab4253c28f1025d1db6e4': '9b223db35f43a40f0f74c5f1bbf645829cd8da46'},
 'scripts/community_saas_order_preparation.py:LIFECYCLE_SCHEMA': {'1c10b4583e424dbe2d8260c5625e1b57652b73c58a35706a3e189b58b8bd3887': 'e5c3ff22ffb887eb8a18c9f5d51ed11c5a799c91',
                                                                  'd143634167e9d98050ba619357bb3bdf3b8554ee8484c9670e42c4e61596ac10': '1ee695d4c2cb3eb75ec1447dbfb7167d7f8fd3e4',
                                                                  'fa2bbc303c1f3166e4a6c2dd90a55c3411f60fa5b7a5e4931a63e1b905b05d17': '9f878bae5f05a1cda27e73ec663e63c0cf144f17'},
 'scripts/community_saas_order_preparation.py:SCHEMA': {'5e232b5adac8c0ca0d195eda92ea65546d2ca0723c0bcee5cb415401607690ac': 'e96463cd4924cf6b1aa7270983d7ace8fd8f4288',
                                                        '8be47324b885c94ff4285f5b153421d60cc78daa01de27adc4d4845e9bcb6caf': '8e4b8a073e96ef1381bb1afe95c3b5c9346ea66a',
                                                        'ccd675efc26a07de52e62a3120b5ad5cc2398a84039f1549be5e117507ed533a': '1ee695d4c2cb3eb75ec1447dbfb7167d7f8fd3e4'}}

GROUPS = {
    'modules': ('scripts/community_saas_modules.py:SCHEMA', MODULE_SCHEMA),
    'offers': ('scripts/community_saas_offer_catalog.py:SCHEMA', OFFER_SCHEMA),
    'preparations': ('scripts/community_saas_order_preparation.py:SCHEMA', PREP_SCHEMA),
    'lifecycle': ('scripts/community_saas_order_preparation.py:LIFECYCLE_SCHEMA', LIFECYCLE_SCHEMA),
    'reviews': ('scripts/community_saas_offline_handoff.py:REVIEW_SCHEMA', REVIEW_SCHEMA),
}
SPECS = {
    'orders': (ORDER_SCHEMA, (1,), ()),
    'merchants': (MERCHANT_SCHEMA, (1,), ()),
    'ads': (AD_SCHEMA, (0, 1), ()),
    'refunds': (REFUND_SCHEMA, (2,), ()),
    'modules': (MODULE_SCHEMA + OFFER_SCHEMA, (1,), ('modules', 'offers')),
    'saas-orders': (PREP_SCHEMA + LIFECYCLE_SCHEMA + REVIEW_SCHEMA, (0,),
                    ('preparations', 'lifecycle', 'reviews')),
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def _same(left, right):
    # Python equality conflates True/1 and 1.0/1 inside nested immutable JSON.
    return _canonical(left) == _canonical(right)


def _frozen_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('LEGACY_FROZEN_JSON_UNRESOLVED')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('LEGACY_FROZEN_JSON_UNRESOLVED')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _catalog(db):
    def normalize(sql):
        return re.sub(r'\s+', ' ', re.sub(r'\bIF NOT EXISTS\b', '', sql,
                                       flags=re.I)).strip().rstrip(';')
    return sorted((typ, name, table, normalize(sql)) for typ, name, table, sql in
                  db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                             "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"))


def _fingerprint(catalog):
    return hashlib.sha256(_canonical(catalog)).hexdigest()


def _template(schema):
    db = sqlite3.connect(':memory:')
    try:
        db.executescript(schema)
        return _catalog(db)
    finally:
        db.close()


def _integrity(db):
    if (db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or
            db.execute('PRAGMA foreign_key_check').fetchall()):
        raise ValueError('MIGRATION_DATABASE_INTEGRITY_FAILED')


def _identify(name, db):
    schema, versions, groups = SPECS[name]
    version = db.execute('PRAGMA user_version').fetchone()[0]
    actual, target = _catalog(db), _template(schema)
    if version not in versions:
        raise ValueError('UNKNOWN_SOURCE_SCHEMA_VERSION:' + name)
    if not groups:
        path, commit, digest = BASE_HISTORY[name]
        if actual != target or _fingerprint(actual) != digest:
            raise ValueError('UNKNOWN_SOURCE_SCHEMA:' + name)
        return {'schema_sha256': _fingerprint(actual), 'user_version': version,
                'components': {}, 'changed': False, 'source_commit': commit,
                'source_path': path, 'source_url': 'https://github.com/' + REPOSITORY +
                '/blob/' + commit + '/' + path}
    covered, matches = set(), {}
    for group in groups:
        key, sql = GROUPS[group]
        names = {row[1] for row in _template(sql)}
        part = [row for row in actual if row[1] in names]
        covered.update(row[1] for row in part)
        if not part and group in ('offers', 'lifecycle', 'reviews'):
            # These were independent additive extensions in the original API.
            matches[group] = {'state': 'ABSENT_ORIGINAL_OPTIONAL_EXTENSION'}
            continue
        digest = _fingerprint(part)
        commit = HISTORY[key].get(digest)
        if commit is None:
            raise ValueError('UNKNOWN_SOURCE_SCHEMA:' + name + ':' + group)
        path = key.split(':')[0]
        matches[group] = {'schema_sha256': digest, 'source_commit': commit,
                          'source_path': path,
                          'source_url': 'https://github.com/' + REPOSITORY +
                          '/blob/' + commit + '/' + path}
    if covered != {row[1] for row in actual}:
        raise ValueError('UNKNOWN_SOURCE_SCHEMA_OBJECT:' + name)
    # A historical table/column/constraint change needs an explicit data map.
    # This implementation only adds empty tables and strengthens triggers.
    wanted = {(row[0], row[1]): row for row in target}
    if any(row[0] != 'trigger' and wanted.get((row[0], row[1])) != row
           for row in actual):
        raise ValueError('SOURCE_TABLE_MAPPING_UNDEFINED:' + name)
    return {'schema_sha256': _fingerprint(actual), 'user_version': version,
            'components': matches, 'changed': actual != target}


def _quoted(name):
    return '"' + name.replace('"', '""') + '"'


def _rows(db):
    """Typed row digests include rowid and sqlite_sequence; preserve every byte."""
    def scalar(value):
        if isinstance(value, bytes):
            return ['blob', value.hex()]
        if isinstance(value, float):
            return ['real', value.hex() if math.isfinite(value) else repr(value)]
        return [type(value).__name__, value]
    result = {}
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND (name NOT LIKE 'sqlite_%' OR name='sqlite_sequence') ORDER BY name")
    for name, in tables:
        digest, count = hashlib.sha256(), 0
        for row in db.execute('SELECT rowid,* FROM ' + _quoted(name) + ' ORDER BY rowid'):
            raw = _canonical([scalar(value) for value in row])
            digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
            count += 1
        result[name] = {'rows': count, 'sha256': digest.hexdigest()}
    return result


def _upgrade(name, db):
    before = _rows(db)
    wanted = _template(SPECS[name][0])
    actual = _catalog(db)
    if actual != wanted:
        db.execute('BEGIN IMMEDIATE')
        try:
            for typ, obj, table, sql in actual:
                if typ == 'trigger':
                    db.execute('DROP TRIGGER ' + _quoted(obj))
            present = {row[1] for row in actual if row[0] != 'trigger'}
            # Tables first so triggers can only reference complete schemas.
            for typ in ('table', 'index', 'trigger'):
                for kind, obj, table, sql in wanted:
                    if kind == typ and (typ == 'trigger' or obj not in present):
                        db.execute(sql)
            if _catalog(db) != wanted:
                raise ValueError('TARGET_SCHEMA_ATTESTATION_FAILED')
            after = _rows(db)
            if (any(after.get(table) != rows for table, rows in before.items()) or
                    any(rows['rows'] for table, rows in after.items() if table not in before)):
                raise ValueError('MIGRATION_DATA_NOT_CONSERVED')
            _integrity(db)
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return before


def _evidence_checks(dbs):
    """Reject absent immutable meaning rather than inventing migration defaults."""
    quotes, orders = dbs['modules'], dbs['saas-orders']
    if orders.execute('SELECT EXISTS(SELECT 1 FROM saas_order_preparations '
                      'GROUP BY tenant_id,quote_id,currency HAVING COUNT(*)>1)').fetchone()[0]:
        raise ValueError('LEGACY_DUPLICATE_QUOTE_ORDER_UNRESOLVED')
    from scripts.community_saas_offer_catalog import get_offer, CYCLES
    for row in quotes.execute('SELECT quote_id,tenant_id,offer_id,offer_version,created_at,'
                              'expires_at,fx_source,fx_at,snapshot FROM saas_quotes'):
        value = _frozen_json(row[-1])
        needed = {'totals_by_cycle', 'offer_governed', 'approval_ref', 'cost_evidence_ref'}
        if type(value) is not dict or not needed.issubset(value):
            raise ValueError('LEGACY_QUOTE_GOVERNANCE_UNRESOLVED')
        if not _same((value.get('tenant_id'), value.get('offer_id'), value.get('version'),
                value.get('created_at'), value.get('expires_at'),
                value.get('fx_source'), value.get('fx_at')), row[1:8]):
            raise ValueError('LEGACY_QUOTE_BINDING_UNRESOLVED')
        offer = get_offer(quotes, row[2], row[3])
        if any(not _same(value.get(key), part) for key, part in offer.items()):
            raise ValueError('LEGACY_QUOTE_SOURCE_VALUES_UNRESOLVED')
        breakdown = {}
        for cycle in sorted(CYCLES):
            lines = [line for line in offer['lines'] if line['cycle'] == cycle]
            if lines:
                breakdown[cycle] = {}
                for currency in ('cny_minor', 'usd_minor'):
                    amounts = [line[currency] for line in lines]
                    breakdown[cycle][currency] = (None if None in amounts else
                        sum(line[currency] * line['quantity'] for line in lines))
        totals = {}
        for currency in ('cny_minor', 'usd_minor'):
            amounts = [line[currency] for line in offer['lines']]
            totals[currency] = (None if None in amounts else
                sum(line[currency] * line['quantity'] for line in offer['lines']))
        if (not _same(value['totals_by_cycle'], breakdown) or
                not _same(value.get('totals'), totals) or type(value['offer_governed']) is not bool):
            raise ValueError('LEGACY_QUOTE_AMOUNT_EVIDENCE_UNRESOLVED')
        approval = quotes.execute('SELECT approval_ref,cost_evidence_ref FROM saas_offer_approvals '
                                  'WHERE offer_id=? AND version=?', row[2:4]).fetchone()
        if (value['offer_governed'] and (approval is None or approval !=
                (value['approval_ref'], value['cost_evidence_ref']))) or (
                not value['offer_governed'] and (value['approval_ref'] is not None or
                                               value['cost_evidence_ref'] is not None)):
            raise ValueError('LEGACY_QUOTE_APPROVAL_EVIDENCE_UNRESOLVED')
    from scripts.community_saas_order_preparation import read, quote_provenance, status
    for oid, tenant, qid, currency, created, frozen in orders.execute(
            'SELECT order_id,tenant_id,quote_id,currency,created_at,snapshot FROM saas_order_preparations'):
        try:
            _frozen_json(frozen)
            value = read(orders, oid, tenant)
            if not _same([value.get(k) for k in ('order_id', 'tenant_id', 'quote_id', 'currency', 'created_at')],
                         [oid, tenant, qid, currency, created]):
                raise ValueError('ORDER_COLUMN_TYPES_CHANGED')
            quote_provenance(orders, oid, tenant)
            status(orders, oid, tenant)
            source = quotes.execute('SELECT snapshot FROM saas_quotes WHERE quote_id=? AND tenant_id=?',
                                    (qid, tenant)).fetchone()
            if source is None or not _same(value['quote_snapshot'], _frozen_json(source[0])):
                raise ValueError('MISSING_OR_CHANGED_SOURCE_QUOTE')
            q = value['quote_snapshot']
            expected_amounts = {cycle: amounts[currency.lower() + '_minor']
                                for cycle, amounts in q['totals_by_cycle'].items()}
            if (not _same(value.get('offer_version'), q['version']) or
                    not _same(value.get('amounts_by_cycle_minor'), expected_amounts)):
                raise ValueError('ORDER_FROZEN_AMOUNT_TYPES_CHANGED')
            if not value['quote_snapshot'].get('offer_governed'):
                raise ValueError('ORIGINAL_APPROVAL_EVIDENCE_MISSING')
        except (KeyError, TypeError, ValueError):
            raise ValueError('LEGACY_ORDER_FROZEN_EVIDENCE_UNRESOLVED') from None
    for table in ('saas_order_lifecycle', 'saas_order_lifecycle_events', 'saas_review_tasks'):
        if orders.execute('SELECT EXISTS(SELECT 1 FROM ' + table + ' x LEFT JOIN '
                          'saas_order_preparations p ON x.order_id=p.order_id '
                          'WHERE p.order_id IS NULL)').fetchone()[0]:
            raise ValueError('LEGACY_ORPHAN_ORDER_EVIDENCE_UNRESOLVED')
    if orders.execute('SELECT EXISTS(SELECT 1 FROM saas_review_events e LEFT JOIN '
                      'saas_review_tasks t ON e.task_id=t.task_id '
                      'WHERE t.task_id IS NULL OR t.tenant_id!=e.tenant_id)').fetchone()[0]:
        raise ValueError('LEGACY_ORPHAN_REVIEW_EVIDENCE_UNRESOLVED')
    for task, tenant, created, state in orders.execute(
            'SELECT task_id,tenant_id,created_at,state FROM saas_review_tasks'):
        events = orders.execute('SELECT tenant_id,action,occurred_at FROM saas_review_events '
                                'WHERE task_id=?', (task,)).fetchall()
        if ((state == 'PENDING' and events) or (state != 'PENDING' and
                (len(events) != 1 or events[0][0:2] != (tenant, state) or
                 events[0][2] < created))):
            raise ValueError('LEGACY_REVIEW_EVENT_BINDING_UNRESOLVED')


def _prepare(source, expected_files):
    root = _private_root(source)
    names = {name + '.sqlite' for name in NAMES}
    if (type(expected_files) is not dict or set(expected_files) != names or
            any(type(x) is not str or re.fullmatch('[0-9a-f]{64}', x) is None
                for x in expected_files.values())):
        raise ValueError('INDEPENDENT_SIX_STORE_DIGESTS_REQUIRED')
    # Live runtime.lock/WAL/journal and any extra files are not snapshots.
    entries = {p.name for p in root.iterdir()}
    if entries not in (names, names | {'snapshot.json'}):
        raise ValueError('EXCLUSIVE_OFFLINE_SNAPSHOT_REQUIRED')
    if 'snapshot.json' in entries:
        manifest = json.loads(_read(root, 'snapshot.json', 32768))
        if (type(manifest) is not dict or manifest.get('format') != 1 or
                manifest.get('purpose') != 'OFFLINE_RESTORE_CANDIDATE' or
                manifest.get('files') != expected_files or
                manifest.get('cross_database_atomic') is not False or
                manifest.get('payment_enabled') is not False or
                manifest.get('center_backup') != 'EXISTING_CENTER_OWNER_REQUIRED'):
            raise ValueError('SOURCE_SNAPSHOT_MANIFEST_MISMATCH')
    dbs, plans = {}, {}
    try:
        for name in NAMES:
            filename = name + '.sqlite'
            blob = _read(root, filename, 128 * 1024 * 1024)
            if hashlib.sha256(blob).hexdigest() != expected_files[filename]:
                raise ValueError('SOURCE_SNAPSHOT_DIGEST_MISMATCH:' + name)
            # Deserialize a bounded byte snapshot; never open/write the source DB.
            if len(blob) < 100 or blob[:16] != b'SQLite format 3\x00' or blob[18:20] != b'\x01\x01':
                raise ValueError('OFFLINE_DELETE_JOURNAL_SNAPSHOT_REQUIRED:' + name)
            db = sqlite3.connect(':memory:'); dbs[name] = db
            db.deserialize(blob)
            _integrity(db)
            plans[name] = _identify(name, db)
        for name, db in dbs.items():
            plans[name]['preserved_tables'] = _upgrade(name, db)
        _evidence_checks(dbs)
        return dbs, plans
    except BaseException:
        for db in dbs.values():
            db.close()
        raise


def inspect(source, expected_files):
    """Read-only source preflight, including a disposable in-memory migration."""
    dbs, plans = _prepare(source, expected_files)
    try:
        return {'source_read_only': True, 'supported': True, 'stores': plans,
                'production_installed': False, 'center_backup': 'EXISTING_CENTER_OWNER_REQUIRED'}
    finally:
        for db in dbs.values():
            db.close()


def _write_private(root, name, blob):
    fd = os.open(str(root / name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(blob); out.flush(); os.fsync(out.fileno())


def migrate(source, expected_files, destination):
    """Create a validated new snapshot, never overwrite/activate any generation.

    A killed process may leave an incomplete destination without snapshot.json;
    it is inadmissible and must not be opened as runtime state. A fresh target
    can be retried against the unchanged source and independently held hashes.
    """
    dbs, plans = _prepare(source, expected_files)
    target = None
    try:
        # mkdir is exclusive. Failure does not confer ownership of an old path.
        target = _create(destination)
        files = {}
        for name, db in dbs.items():
            blob = db.serialize()
            filename = name + '.sqlite'
            _write_private(target, filename, blob)
            files[filename] = hashlib.sha256(blob).hexdigest()
        # Completion marker is last, with the exact original restore contract.
        manifest = {'format': 1, 'purpose': 'OFFLINE_RESTORE_CANDIDATE',
                    'cross_database_atomic': False, 'center_backup': 'EXISTING_CENTER_OWNER_REQUIRED',
                    'payment_enabled': False, 'files': files}
        raw = _canonical(manifest)
        _write_private(target, 'snapshot.json', raw)
        # Durability order: files (in _write_private), completion marker, target
        # directory entry set, then the parent entry that names this new target.
        _sync(target, directory=True)
        _sync(target.parent, directory=True)
        return {'migration_executed': True, 'source_unchanged': True, 'stores': plans,
                'source_files': dict(expected_files), 'files': files,
                'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                'production_installed': False, 'payment_enabled': False,
                'center_backup': 'EXISTING_CENTER_OWNER_REQUIRED'}
    except BaseException:
        if target is not None:
            shutil.rmtree(target)
        raise
    finally:
        for db in dbs.values():
            db.close()
