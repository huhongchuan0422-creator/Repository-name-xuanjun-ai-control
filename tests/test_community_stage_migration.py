Warning: truncated output (original token count: 113158)
Total output lines: 3361

"""Known Git DDL migrations, populated frozen evidence and failure isolation.

HISTORY_FIXTURES contains literal SCHEMA assignments extracted with ast.literal_eval
from the cited Git commits, never approximated from current DDL. The source hashes
record the exact fetched UTF-8 source files; fixture SQL fingerprints are checked
against the runtime registry independently for every recognized historical version.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import community_stage_migration as migration
from scripts.community_stage_recovery import restore
from scripts.community_stage_local import LocalStage
from scripts.community_saas_phase2 import Principal
from scripts.community_order_store import connect, create_order
from scripts.community_merchant_store import open_store
from scripts.community_ad_store import open_offline
from scripts.community_refund_preview_store import open_refund_store
from scripts.community_saas_modules import connect as module_connect, set_price, grant
from scripts.community_saas_offer_catalog import install as install_offers, create_offer, approve_offer, quote
from scripts.community_saas_order_preparation import install, install_lifecycle, prepare, advance
from scripts.community_saas_offline_handoff import install_reviews, create_review

HISTORY_FIXTURES = {'scripts/community_saas_modules.py:SCHEMA': {'3585cb0367c225f8abd7a89734b652efb66a7b4bac0843bdfdd8fab150baa0f9': {'schema': '\n'
                                                                                                                             'CREATE '
                                                                                                                             'TABLE '
                                                                                                                             'module_prices '
                                                                                                                             '(\n'
                                                                                                                             ' '
                                                                                                                             'module_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL, '
                                                                                                                             'version '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(version>0),\n'
                                                                                                                             ' '
                                                                                                                             'cny_minor '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(cny_minor>=0),\n'
                                                                                                                             ' '
                                                                                                                             'usd_minor '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(usd_minor>=0),\n'
                                                                                                                             ' '
                                                                                                                             'period_days '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(period_days>0),\n'
                                                                                                                             ' '
                                                                                                                             'active '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(active '
                                                                                                                             'IN '
                                                                                                                             '(0,1)),\n'
                                                                                                                             ' '
                                                                                                                             'PRIMARY '
                                                                                                                             'KEY(module_id,version));\n'
                                                                                                                             'CREATE '
                                                                                                                             'TABLE '
                                                                                                                             'module_entitlements '
                                                                                                                             '(\n'
                                                                                                                             ' '
                                                                                                                             'tenant_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,module_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,valid_from '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL,\n'
                                                                                                                             ' '
                                                                                                                             'valid_until '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL,price_version '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL,\n'
                                                                                                                             ' '
                                                                                                                             'source '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(source '
                                                                                                                             'IN '
                                                                                                                             "('OFFLINE_GRANT','PAID_ORDER_CONFIRMED','CUSTOM_DELIVERY')),\n"
                                                                                                                             ' '
                                                                                                                             'PRIMARY '
                                                                                                                             'KEY(tenant_id,module_id),CHECK(valid_from<valid_until));\n'
                                                                                                                             'CREATE '
                                                                                                                             'TABLE '
                                                                                                                             'module_events '
                                                                                                                             '(\n'
                                                                                                                             ' '
                                                                                                                             'id '
                                                                                                                             'INTEGER '
                                                                                                                             'PRIMARY '
                                                                                                                             'KEY '
                                                                                                                             'AUTOINCREMENT,\n'
                                                                                                                             ' '
                                                                                                                             'tenant_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,module_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,action '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,\n'
                                                                                                                             ' '
                                                                                                                             'old_until '
                                                                                                                             'INTEGER,new_until '
                                                                                                                             'INTEGER,occurred_at '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL);\n'
                                                                                                                             'CREATE '
                                                                                                                             'TRIGGER '
                                                                                                                             'module_events_immutable_update '
                                                                                                                             'BEFORE '
                                                                                                                             'UPDATE '
                                                                                                                             'ON '
                                                                                                                             'module_events\n'
                                                                                                                             'BEGIN '
                                                                                                                             'SELECT '
                                                                                                                             "RAISE(ABORT,'MODULE_EVENT_APPEND_ONLY'); "
                                                                                                                             'END;\n'
                                                                                                                             'CREATE '
                                                                                                                             'TRIGGER '
                                                                                                                             'module_events_immutable_delete '
                                                                                                                             'BEFORE '
                                                                                                                             'DELETE '
                                                                                                                             'ON '
                                                                                                                             'module_events\n'
                                                                                                                             'BEGIN '
                                                                                                                             'SELECT '
                                                                                                                             "RAISE(ABORT,'MODULE_EVENT_APPEND_ONLY'); "
                                                                                                                             'END;\n',
                                                                                                                   'source_commit': 'bab171c459df62e61acb8b4bb780507f35c43fc3',
                                                                                                                   'source_path': 'scripts/community_saas_modules.py',
                                                                                                                   'source_sha256': '6b5036582b92b43b2f89330b3278192b6fdc6e1361ab5bd6a6573ba57beec15d'},
                                              'c7e5b5a8cb0a2dd5d3fa060fdc0a6fc394d9e5f6f65bd52f43ce8216c1608581': {'schema': '\n'
                                                                                                                             'CREATE '
                                                                                                                             'TABLE '
                                                                                                                             'module_prices '
                                                                                                                             '(\n'
                                                                                                                             ' '
                                                                                                                             'module_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL, '
                                                                                                                             'version '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(version>0),\n'
                                                                                                                             ' '
                                                                                                                             'cny_minor '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(cny_minor>=0),\n'
                                                                                                                             ' '
                                                                                                                             'usd_minor '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(usd_minor>=0),\n'
                                                                                                                             ' '
                                                                                                                             'period_days '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(period_days>0),\n'
                                                                                                                             ' '
                                                                                                                             'active '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(active '
                                                                                                                             'IN '
                                                                                                                             '(0,1)),\n'
                                                                                                                             ' '
                                                                                                                             'PRIMARY '
                                                                                                                             'KEY(module_id,version));\n'
                                                                                                                             'CREATE '
                                                                                                                             'TABLE '
                                                                                                                             'module_entitlements '
                                                                                                                             '(\n'
                                                                                                                             ' '
                                                                                                                             'tenant_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,module_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,valid_from '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL,\n'
                                                                                                                             ' '
                                                                                                                             'valid_until '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL,price_version '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL,\n'
                                                                                                                             ' '
                                                                                                                             'source '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL '
                                                                                                                             'CHECK(source '
                                                                                                                             'IN '
                                                                                                                             "('OFFLINE_GRANT','PAID_ORDER_CONFIRMED','CUSTOM_DELIVERY')),\n"
                                                                                                                             ' '
                                                                                                                             'PRIMARY '
                                                                                                                             'KEY(tenant_id,module_id),CHECK(valid_from<valid_until));\n'
                                                                                                                             'CREATE '
                                                                                                                             'TABLE '
                                                                                                                             'module_events '
                                                                                                                             '(\n'
                                                                                                                             ' '
                                                                                                                             'id '
                                                                                                                             'INTEGER '
                                                                                                                             'PRIMARY '
                                                                                                                             'KEY '
                                                                                                                             'AUTOINCREMENT,\n'
                                                                                                                             ' '
                                                                                                                             'tenant_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,module_id '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,action '
                                                                                                                             'TEXT '
                                                                                                                             'NOT '
                                                                                                                             'NULL,\n'
                                                                                                                             ' '
                                                                                                                             'old_until '
                                                                                                                             'INTEGER,new_until '
                                                                                                                             'INTEGER,occurred_at '
                                                                                                                             'INTEGER '
                                                                                                                             'NOT '
                                                                                                                             'NULL);\n'
                                                                                                                             'CREATE '
                                                                                                                             'TRIGGER '
                                                                                                                             'module_events_immutable_update '
                                                                                                                             'BEFORE '
                                                                                                                             'UPDATE '
                                                                                                                             'ON '
                                                                                                                             'module_events\n'
                                                                                                                             'BEGIN '
                                                                                                                             'SELECT '
                                                                                                                             "RAISE(ABORT,'MODULE_EVENT_APPEND_ONLY'); "
                                                                                                                             'END;\n'
                                                                                                                             'CREATE '
                                                                                                                             'TRIGGER '
                                                                                                                             'module_events_immutable_delete '
                                                                                                                             'BEFORE '
                                                                                                                             'DELETE '
                                                                                                                             'ON '
                                                                                                                             'module_events\n'
                                                                                                                             'BEGIN '
                                                                                                                             'SELECT '
                                                                                                                             "RAISE(ABORT,'MODULE_EVENT_APPEND_ONLY'); "
                                                                                                                             'END;\n'
                                                                                                                             'CREATE '
                                                                                                                             'TRIGGER '
                                                                                                                             'module_events_no_replace '
                                                                                                                             'BEFORE '
                                                                                                                             'INSERT '
                                                                                                                             'ON '
                                                                                                                             'module_events\n'
                                                                                                                             'WHEN '
                                                                                                                             'EXISTS(SELECT '
                                                                                                                             '1 '
                                                                                                                             'FROM '
                                                                                                                             'module_events '
                                                                                                                             'WHERE '
                                                                                                                             'id=NEW.id)\n'
                                                                                                                             'BEGIN '
                                                                                                                             'SELECT '
                                                                                                                             "RAISE(ABORT,'IMMUTABLE_CONFLICT'); "
                                                                                                                             'END;\n',
                                                                                                                   'source_commit': '7b261b2bcb0c70c90b2342d3624d4f2acfc28abb',
                                                                                                                   'source_path': 'scripts/community_saas_modules.py',
                                                                   …93158 tokens truncated…                                                 'TEXT '
                                                                                                                                       'NOT '
                                                                                                                                       'NULL '
                                                                                                                                       'CHECK(currency '
                                                                                                                                       'IN '
                                                                                                                                       "('CNY','USD')),\n"
                                                                                                                                       ' '
                                                                                                                                       'created_at '
                                                                                                                                       'INTEGER '
                                                                                                                                       'NOT '
                                                                                                                                       'NULL, '
                                                                                                                                       'snapshot '
                                                                                                                                       'TEXT '
                                                                                                                                       'NOT '
                                                                                                                                       'NULL,\n'
                                                                                                                                       ' '
                                                                                                                                       'UNIQUE(tenant_id,quote_id,currency));\n'
                                                                                                                                       'CREATE '
                                                                                                                                       'TRIGGER '
                                                                                                                                       'IF '
                                                                                                                                       'NOT '
                                                                                                                                       'EXISTS '
                                                                                                                                       'saas_order_prep_immutable_update\n'
                                                                                                                                       'BEFORE '
                                                                                                                                       'UPDATE '
                                                                                                                                       'ON '
                                                                                                                                       'saas_order_preparations '
                                                                                                                                       'BEGIN '
                                                                                                                                       'SELECT '
                                                                                                                                       "RAISE(ABORT,'IMMUTABLE_ORDER_PREPARATION'); "
                                                                                                                                       'END;\n'
                                                                                                                                       'CREATE '
                                                                                                                                       'TRIGGER '
                                                                                                                                       'IF '
                                                                                                                                       'NOT '
                                                                                                                                       'EXISTS '
                                                                                                                                       'saas_order_prep_immutable_delete\n'
                                                                                                                                       'BEFORE '
                                                                                                                                       'DELETE '
                                                                                                                                       'ON '
                                                                                                                                       'saas_order_preparations '
                                                                                                                                       'BEGIN '
                                                                                                                                       'SELECT '
                                                                                                                                       "RAISE(ABORT,'IMMUTABLE_ORDER_PREPARATION'); "
                                                                                                                                       'END;\n'
                                                                                                                                       'CREATE '
                                                                                                                                       'TRIGGER '
                                                                                                                                       'saas_order_preparations_no_replace '
                                                                                                                                       'BEFORE '
                                                                                                                                       'INSERT '
                                                                                                                                       'ON '
                                                                                                                                       'saas_order_preparations\n'
                                                                                                                                       'WHEN '
                                                                                                                                       'EXISTS(SELECT '
                                                                                                                                       '1 '
                                                                                                                                       'FROM '
                                                                                                                                       'saas_order_preparations '
                                                                                                                                       'WHERE '
                                                                                                                                       'order_id=NEW.order_id '
                                                                                                                                       'OR '
                                                                                                                                       '(tenant_id=NEW.tenant_id '
                                                                                                                                       'AND '
                                                                                                                                       'quote_id=NEW.quote_id '
                                                                                                                                       'AND '
                                                                                                                                       'currency=NEW.currency))\n'
                                                                                                                                       'BEGIN '
                                                                                                                                       'SELECT '
                                                                                                                                       "RAISE(ABORT,'IMMUTABLE_CONFLICT'); "
                                                                                                                                       'END;\n',
                                                                                                                             'source_commit': '1ee695d4c2cb3eb75ec1447dbfb7167d7f8fd3e4',
                                                                                                                             'source_path': 'scripts/community_saas_order_preparation.py',
                                                                                                                             'source_sha256': 'af38b695ac5f5daa446c12da87e988e84f5730552c0c3312fd9dc44bf85ac71b'}}}


class HistoricalMigration(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        self.urlopen = patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        self.connect_mock = self.network.start(); self.opener_mock = self.urlopen.start()
        self.addCleanup(self.network.stop); self.addCleanup(self.urlopen.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 'source'
        self.source.mkdir(mode=0o700)
        self.scope = dict(tenant_id='tenantA', merchant_id='merchantA', store_id='storeA')
        for name, opener in [('orders', connect), ('merchants', open_store),
                             ('ads', open_offline), ('refunds', open_refund_store),
                             ('modules', module_connect)]:
            db = opener(str(self.source / (name + '.sqlite')))
            if name == 'modules': install_offers(db)
            db.close()
        db = sqlite3.connect(self.source / 'saas-orders.sqlite')
        install(db); install_lifecycle(db); install_reviews(db); db.close()
        for file in self.source.iterdir(): file.chmod(0o600)
        self.populate()

    def tearDown(self):
        self.assertEqual(self.connect_mock.call_count, 0)
        self.assertEqual(self.opener_mock.call_count, 0)

    def db(self, name):
        return sqlite3.connect(self.source / (name + '.sqlite'))

    def populate(self):
        db = self.db('orders')
        create_order(db, self.scope, 'purchase', 101); db.close()
        db = self.db('merchants')
        db.execute("INSERT INTO merchant_profiles VALUES('tenantA','merchantA','storeA','store','description','contact','ACTIVE',1)")
        db.execute("INSERT INTO catalog_items VALUES('tenantA','merchantA','storeA','sku','item','ACTIVE',1,1)")
        db.commit(); db.close()
        db = self.db('ads')
        db.execute("INSERT INTO metric_events VALUES('tenantA','merchantA','storeA','AD_SLOT_PAYMENT_AMOUNT','CLICK','event','campaign',10)")
        db.commit(); db.close()
        db = self.db('refunds')
        db.execute("INSERT INTO refund_events VALUES('tenantA','merchantA','storeA','legacy-preview','refund-event',1,'OFFLINE_PREVIEW')")
        db.commit(); db.close()
        q = self.db('modules'); orders = self.db('saas-orders')
        set_price(q, 'storefront_catalog', 1, 300, 45, 30)
        grant(q, 'tenantA', 'storefront_catalog', 10, 100, 1)
        line = dict(type='MODULE_FEE', label='original', cycle='MONTH', quantity=1,
                    cny_minor=300, usd_minor=45, cost_cny_minor=50, cost_usd_minor=5)
        create_offer(q, 'offer', 1, 'storefront_catalog', 'MONTHLY', [line], term_days=30)
        approve_offer(q, 'offer', 1, 'approval-original', 'cost-original', 10)
        quote(q, 'quote', 'tenantA', 'offer', 1, 10, 100)
        prepare(orders, q, 'order', 'tenantA', 'quote', 'CNY', 20)
        advance(orders, 'order', 'tenantA', 'waiting', 'AWAITING_EXTERNAL', 21)
        create_review(orders, 'review', 'tenantA', 'order', 'FINANCE_EVIDENCE', 22, 'original')
        q.close(); orders.close()

    def hashes(self, path=None):
        root = path or self.source
        return {name + '.sqlite': hashlib.sha256((root / (name + '.sqlite')).read_bytes()).hexdigest()
                for name in migration.NAMES}

    def historical(self, group, digest, *, empty=False):
        key, current = migration.GROUPS[group]
        fixture = HISTORY_FIXTURES[key][digest]
        name = 'modules' if group in ('modules', 'offers') else 'saas-orders'
        db = self.db(name)
        present = migration._template(current)
        if empty:
            for typ in ('trigger', 'index', 'table'):
                for kind, obj, table, sql in present:
                    if kind == typ:
                        db.execute('DROP ' + typ.upper() + ' IF EXISTS ' + migration._quoted(obj))
            db.executescript(fixture['schema'])
        else:
            for typ, obj, table, sql in present:
                if typ == 'trigger': db.execute('DROP TRIGGER ' + migration._quoted(obj))
            for typ, obj, table, sql in migration._template(fixture['schema']):
                if typ == 'trigger': db.execute(sql)
        db.commit(); db.close()

    def downgrade_populated(self):
        choices = {'modules': '3585cb0367', 'offers': 'd7e9989cdf',
                   'preparations': '5e232b5ada', 'lifecycle': 'fa2bbc303c',
                   'reviews': 'c35939f2db'}
        for group, prefix in choices.items():
            key = migration.GROUPS[group][0]
            digest = next(h for h in HISTORY_FIXTURES[key] if h.startswith(prefix))
            self.historical(group, digest)

    def test_populated_historical_schemas_conserve_every_row_and_reopen_current_runtime(self):
        self.downgrade_populated(); source_hashes = self.hashes()
        before = {}
        for name in migration.NAMES:
            db = self.db(name); before[name] = migration._rows(db); db.close()
            self.assertTrue(any(x['rows'] for x in before[name].values()))
        plan = migration.inspect(self.source, source_hashes)
        self.assertTrue(plan['stores']['modules']['changed'])
        self.assertTrue(plan['stores']['saas-orders']['changed'])
        self.assertEqual(self.hashes(), source_hashes)
        destination = self.root / 'upgraded'
        result = migration.migrate(self.source, source_hashes, destination)
        self.assertTrue(result['migration_executed']); self.assertFalse(result['production_installed'])
        for name in migration.NAMES:
            db = sqlite3.connect(destination / (name + '.sqlite'))
            self.assertEqual(migration._rows(db), before[name]); db.close()
        self.assertEqual(self.hashes(), source_hashes)
        restore(destination, result['manifest_sha256'], self.root / 'runtime')
        principal = Principal('tenantA', 'CUSTOMER')
        with LocalStage(self.root / 'runtime', {principal: self.scope}, self.scope) as stage:
            self.assertEqual(stage.runtime.saas.orders.execute('SELECT state FROM saas_order_lifecycle').fetchone()[0], 'AWAITING_EXTERNAL')
            self.assertEqual(stage.runtime.saas.quotes.execute('SELECT approval_ref FROM saas_offer_approvals').fetchone()[0], 'approval-original')
        self.assertTrue(migration.inspect(destination, result['files'])['supported'])

    def test_known_merchant_and_ad_v1_add_empty_media_tables_and_reopen_v2(self):
        merchant = self.db('merchants')
        merchant.execute('DROP TABLE catalog_item_content')
        merchant.execute('PRAGMA user_version=1')
        merchant.commit(); merchant.close()
        ads = self.db('ads')
        ads.execute('DROP TABLE campaign_creatives')
        ads.execute('PRAGMA user_version=1')
        ads.commit(); ads.close()
        source_hashes = self.hashes()
        plan = migration.inspect(self.source, source_hashes)
        self.assertTrue(plan['stores']['merchants']['changed'])
        self.assertTrue(plan['stores']['ads']['changed'])
        target = self.root / 'media-v2'
        result = migration.migrate(self.source, source_hashes, target)
        for name, table in (('merchants', 'catalog_item_content'), ('ads', 'campaign_creatives')):
            db = sqlite3.connect(target / (name + '.sqlite'))
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
            self.assertEqual(migration._catalog(db), migration._template(migration.SPECS[name][0]))
            db.close()
        self.assertEqual(self.hashes(), source_hashes)

    def test_every_pinned_git_schema_fixture_matches_exact_catalog_fingerprint(self):
        count = 0
        for group, (key, _) in migration.GROUPS.items():
            for digest, fixture in HISTORY_FIXTURES[key].items():
                with self.subTest(group=group, digest=digest):
                    self.assertEqual(migration._fingerprint(migration._template(fixture['schema'])), digest)
                    self.assertEqual(fixture['source_commit'], migration.HISTORY[key][digest])
                    self.assertRegex(fixture['source_sha256'], '^[0-9a-f]{64}$')
                    db = sqlite3.connect(':memory:')
                    try:
                        name = 'modules' if group in ('modules', 'offers') else 'saas-orders'
                        for other in migration.SPECS[name][2]:
                            sql = fixture['schema'] if other == group else migration.GROUPS[other][1]
                            db.executescript(sql)
                        db.execute('PRAGMA user_version=' + ('1' if name == 'modules' else '0'))
                        migration._identify(name, db); migration._upgrade(name, db)
                        self.assertEqual(migration._catalog(db), migration._template(migration.SPECS[name][0]))
                    finally: db.close()
                    count += 1
        self.assertEqual(count, 16)

    def test_legacy_unfrozen_quote_is_rejected_without_new_target(self):
        db = self.db('modules'); db.execute('DROP TRIGGER saas_quote_no_update')
        value = json.loads(db.execute('SELECT snapshot FROM saas_quotes').fetchone()[0])
        del value['offer_governed']
        db.execute('UPDATE saas_quotes SET snapshot=?', (json.dumps(value),)); db.commit()
        for typ, obj, table, sql in migration._template(migration.OFFER_SCHEMA):
            if obj == 'saas_quote_no_update': db.execute(sql)
        db.commit(); db.close()
        hashes = self.hashes()
        with self.assertRaisesRegex(ValueError, 'LEGACY_QUOTE_GOVERNANCE_UNRESOLVED'):
            migration.migrate(self.source, hashes, self.root / 'reject')
        self.assertFalse((self.root / 'reject').exists()); self.assertEqual(self.hashes(), hashes)

    def test_legacy_order_without_original_quote_digest_is_not_reconstructed(self):
        db = self.db('saas-orders'); db.execute('DROP TRIGGER saas_order_prep_immutable_update')
        value = json.loads(db.execute('SELECT snapshot FROM saas_order_preparations').fetchone()[0]); del value['quote_sha256']
        db.execute('UPDATE saas_order_preparations SET snapshot=?', (json.dumps(value),)); db.commit()
        for typ, obj, table, sql in migration._template(migration.PREP_SCHEMA):
            if obj == 'saas_order_prep_immutable_update': db.execute(sql)
        db.commit(); db.close()
        with self.assertRaisesRegex(ValueError, 'LEGACY_ORDER_FROZEN_EVIDENCE_UNRESOLVED'):
            migration.inspect(self.source, self.hashes())

    def test_unknown_ddl_cannot_be_guessed_from_user_version(self):
        db = self.db('modules'); db.execute('CREATE TABLE invented(id TEXT)'); db.commit(); db.close()
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_SOURCE_SCHEMA_OBJECT'):
            migration.inspect(self.source, self.hashes())

    def test_arbitrarily_missing_trigger_not_a_known_history_is_rejected(self):
        db = self.db('modules'); db.execute('DROP TRIGGER saas_quote_no_update'); db.commit(); db.close()
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_SOURCE_SCHEMA'):
            migration.inspect(self.source, self.hashes())

    def test_wrong_user_version_is_rejected_even_when_ddl_matches(self):
        db = self.db('modules'); db.execute('PRAGMA user_version=77'); db.close()
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_SOURCE_SCHEMA_VERSION'):
            migration.inspect(self.source, self.hashes())

    def test_unapproved_quote_remains_unapproved_and_cannot_prepare_order(self):
        q = self.db('modules')
        line = dict(type='MODULE_FEE', label='unapproved', cycle='MONTH', quantity=1,
                    cny_minor=500, usd_minor=75, cost_cny_minor=50, cost_usd_minor=5)
        create_offer(q, 'unapproved', 1, 'storefront_catalog', 'MONTHLY', [line], term_days=30)
        quote(q, 'preview', 'tenantA', 'unapproved', 1, 10, 100)
        frozen = q.execute("SELECT snapshot FROM saas_quotes WHERE quote_id='preview'").fetchone()[0]
        q.close(); self.downgrade_populated()
        target = self.root / 'unapproved-preserved'
        migration.migrate(self.source, self.hashes(), target)
        q = sqlite3.connect(target / 'modules.sqlite'); orders = sqlite3.connect(target / 'saas-orders.sqlite')
        try:
            self.assertEqual(q.execute("SELECT snapshot FROM saas_quotes WHERE quote_id='preview'").fetchone()[0], frozen)
            self.assertIs(json.loads(frozen)['offer_governed'], False)
            with self.assertRaisesRegex(ValueError, 'OFFER_APPROVAL_REQUIRED'):
                prepare(orders, q, 'unauthorized', 'tenantA', 'preview', 'CNY', 30)
            self.assertEqual(orders.execute('SELECT COUNT(*) FROM saas_order_preparations').fetchone()[0], 1)
        finally: q.close(); orders.close()

    def test_unmatched_quote_approval_evidence_cannot_be_upgraded(self):
        q = self.db('modules'); q.execute('DROP TRIGGER saas_offer_approvals_no_update')
        q.execute("UPDATE saas_offer_approvals SET approval_ref='different'"); q.commit()
        for typ, obj, table, sql in migration._template(migration.OFFER_SCHEMA):
            if obj == 'saas_offer_approvals_no_update': q.execute(sql)
        q.commit(); q.close()
        with self.assertRaisesRegex(ValueError, 'LEGACY_QUOTE_APPROVAL_EVIDENCE_UNRESOLVED'):
            migration.inspect(self.source, self.hashes())

    def test_bool_and_float_cannot_masquerade_as_frozen_quote_integers(self):
        q = self.db('modules')
        line = dict(type='MODULE_FEE', label='one', cycle='MONTH', quantity=1,
                    cny_minor=1, usd_minor=1, cost_cny_minor=1, cost_usd_minor=1)
        create_offer(q, 'one', 1, 'storefront_catalog', 'MONTHLY', [line], term_days=30)
        approve_offer(q, 'one', 1, 'one-approval', 'one-cost', 10)
        quote(q, 'one-quote', 'tenantA', 'one', 1, 10, 100)
        original = q.execute("SELECT snapshot FROM saas_quotes WHERE quote_id='one-quote'").fetchone()[0]
        q.close()
        cases = [('version', lambda x, v: x.__setitem__('version', v)),
                 ('line-money', lambda x, v: x['lines'][0].__setitem__('cny_minor', v)),
                 ('line-quantity', lambda x, v: x['lines'][0].__setitem__('quantity', v)),
                 ('breakdown', lambda x, v: x['totals_by_cycle']['MONTH'].__setitem__('cny_minor', v)),
                 ('non-payable-totals', lambda x, v: x['totals'].__setitem__('cny_minor', v))]
        for name, mutate in cases:
            for replacement in (True, 1.0):
                with self.subTest(field=name, value=replacement):
                    value = json.loads(original); mutate(value, replacement)
                    self.replace_snapshot('modules', 'saas_quotes', 'quote_id', 'one-quote',
                                          'saas_quote_no_update', migration.OFFER_SCHEMA, value)
                    hashes = self.hashes()
                    with self.assertRaisesRegex(ValueError, 'LEGACY_QUOTE_.*UNRESOLVED'):
                        migration.migrate(self.source, hashes, self.root / 'typed-quote')
                    self.assertFalse((self.root / 'typed-quote').exists())
                    self.assertEqual(self.hashes(), hashes)

    def test_duplicate_frozen_json_fields_are_not_silently_collapsed(self):
        db = self.db('modules'); raw = db.execute('SELECT snapshot FROM saas_quotes').fetchone()[0]
        db.execute('DROP TRIGGER saas_quote_no_update')
        raw = raw.replace('"version":1', '"version":false,"version":1')
        db.execute('UPDATE saas_quotes SET snapshot=?', (raw,)); db.commit()
        for typ, obj, parent, sql in migration._template(migration.OFFER_SCHEMA):
            if obj == 'saas_quote_no_update': db.execute(sql)
        db.commit(); db.close()
        with self.assertRaisesRegex(ValueError, 'LEGACY_FROZEN_JSON_UNRESOLVED'):
            migration.inspect(self.source, self.hashes())

    def replace_snapshot(self, store, table, column, ident, trigger, schema, value):
        db = self.db(store); db.execute('DROP TRIGGER ' + trigger)
        db.execute('UPDATE ' + table + ' SET snapshot=? WHERE ' + column + '=?',
                   (json.dumps(value), ident)); db.commit()
        for typ, obj, parent, sql in migration._template(schema):
            if obj == trigger: db.execute(sql)
        db.commit(); db.close()

    def test_order_frozen_snapshot_and_outer_version_need_exact_types(self):
        db = self.db('saas-orders')
        original = db.execute('SELECT snapshot FROM saas_order_preparations').fetchone()[0]; db.close()
        for field in ('outer-version', 'inner-version'):
            for replacement in (True, 1.0):
                with self.subTest(field=field, value=replacement):
                    value = json.loads(original)
                    if field == 'outer-version': value['offer_version'] = replacement
                    else: value['quote_snapshot']['version'] = replacement
                    # A freshly supplied digest does not make wrong-type JSON valid.
                    if field == 'inner-version':
                        value['quote_sha256'] = hashlib.sha256(json.dumps(value['quote_snapshot'],
                            ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    self.replace_snapshot('saas-orders', 'saas_order_preparations', 'order_id', 'order',
                        'saas_order_prep_immutable_update', migration.PREP_SCHEMA, value)
                    hashes = self.hashes()
                    with self.assertRaisesRegex(ValueError, 'LEGACY_ORDER_FROZEN_EVIDENCE_UNRESOLVED'):
                        migration.inspect(self.source, hashes)
                    self.assertEqual(self.hashes(), hashes)

    def test_earliest_order_ddl_already_rejects_duplicate_quote_currency(self):
        key = migration.GROUPS['preparations'][0]
        fixture = next(v for h, v in HISTORY_FIXTURES[key].items() if h.startswith('8be47324b8'))
        db = sqlite3.connect(':memory:')
        try:
            db.executescript(fixture['schema'])
            original = self.db('saas-orders')
            try: row = original.execute('SELECT * FROM saas_order_preparations').fetchone()
            finally: original.close()
            db.execute('INSERT INTO saas_order_preparations VALUES(?,?,?,?,?,?)', row)
            other = json.loads(row[-1]); other['order_id'] = 'second'
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed'):
                db.execute('INSERT INTO saas_order_preparations VALUES(?,?,?,?,?,?)',
                           ('second', *row[1:-1], json.dumps(other)))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM saas_order_preparations').fetchone()[0], 1)
        finally: db.close()

    def test_old_mutable_review_without_original_terminal_event_is_rejected(self):
        key = migration.GROUPS['reviews'][0]
        digest = next(h for h in HISTORY_FIXTURES[key] if h.startswith('0abe0d46ba'))
        self.historical('reviews', digest)
        db = self.db('saas-orders')
        db.execute("UPDATE saas_review_tasks SET state='RESOLVED'"); db.commit(); db.close()
        with self.assertRaisesRegex(ValueError, 'LEGACY_REVIEW_EVENT_BINDING_UNRESOLVED'):
            migration.inspect(self.source, self.hashes())

    def test_original_optional_extensions_can_be_added_without_erasing_module_rows(self):
        q = self.db('modules')
        for typ in ('trigger', 'index', 'table'):
            for kind, obj, table, sql in migration._template(migration.OFFER_SCHEMA):
                if kind == typ: q.execute('DROP ' + typ.upper() + ' IF EXISTS ' + migration._quoted(obj))
        q.commit(); q.close()
        key = migration.GROUPS['preparations'][0]
        fixture = next(v for h, v in HISTORY_FIXTURES[key].items() if h.startswith('8be47324b8'))
        file = self.source / 'saas-orders.sqlite'; file.unlink()
        db = sqlite3.connect(file); db.executescript(fixture['schema']); db.close(); file.chmod(0o600)
        receipt = migration.migrate(self.source, self.hashes(), self.root / 'extended')
        self.assertEqual(receipt['stores']['modules']['components']['offers']['state'], 'ABSENT_ORIGINAL_OPTIONAL_EXTENSION')
        db = sqlite3.connect(self.root / 'extended' / 'modules.sqlite')
        try:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM module_entitlements').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM saas_offer_approvals').fetchone()[0], 0)
        finally: db.close()

    def test_stale_hash_and_missing_hash_are_rejected_before_output(self):
        hashes = self.hashes(); hashes['ads.sqlite'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_SNAPSHOT_DIGEST_MISMATCH'):
            migration.migrate(self.source, hashes, self.root / 'new')
        self.assertFalse((self.root / 'new').exists())
        hashes.pop('ads.sqlite')
        with self.assertRaisesRegex(ValueError, 'INDEPENDENT_SIX_STORE_DIGESTS_REQUIRED'):
            migration.inspect(self.source, hashes)

    def test_original_snapshot_manifest_is_accepted_and_mismatch_rejected(self):
        receipt = migration.migrate(self.source, self.hashes(), self.root / 'candidate')
        self.assertTrue(migration.inspect(self.root / 'candidate', receipt['files'])['supported'])
        p = self.root / 'candidate' / 'snapshot.json'; value = json.loads(p.read_text()); value['payment_enabled'] = True
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'SOURCE_SNAPSHOT_MANIFEST_MISMATCH'):
            migration.inspect(self.root / 'candidate', receipt['files'])

    def test_live_lock_wal_and_journal_entries_fail_closed(self):
        for name in ('runtime.lock', 'orders.sqlite-wal', 'modules.sqlite-journal'):
            with self.subTest(name=name):
                p = self.source / name; p.touch()
                try:
                    with self.assertRaisesRegex(ValueError, 'EXCLUSIVE_OFFLINE_SNAPSHOT_REQUIRED'):
                        migration.inspect(self.source, self.hashes())
                finally: p.unlink()

    def test_symlink_and_hardlinked_source_files_are_rejected(self):
        hashes = self.hashes(); file = self.source / 'ads.sqlite'
        other = self.root / 'ads'; file.rename(other); file.symlink_to(other)
        with self.assertRaises(OSError): migration.inspect(self.source, hashes)
        file.unlink(); os.link(other, file)
        with self.assertRaisesRegex(ValueError, 'INVALID_SNAPSHOT_FILE'):
            migration.inspect(self.source, hashes)

    def test_unsafe_source_directory_and_destination_parent_symlink_are_rejected(self):
        self.source.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_DIRECTORY_REQUIRED'):
            migration.inspect(self.source, self.hashes())
        self.source.chmod(0o700)
        real = self.root / 'real'; real.mkdir(); linked = self.root / 'linked'; linked.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'SYMLINK_PATH_DENIED'):
            migration.migrate(self.source, self.hashes(), linked / 'new')
        self.assertEqual(list(real.iterdir()), [])

    def test_existing_destination_is_never_deleted_or_overwritten(self):
        target = self.root / 'existing'; target.mkdir(mode=0o700); marker = target / 'valuable'; marker.write_text('keep')
        with self.assertRaises(FileExistsError):
            migration.migrate(self.source, self.hashes(), target)
        self.assertEqual(marker.read_text(), 'keep')

    def test_fsync_failure_removes_only_the_new_destination(self):
        hashes = self.hashes()
        with patch.object(migration.os, 'fsync', side_effect=OSError('disk failed')):
            with self.assertRaisesRegex(OSError, 'disk failed'):
                migration.migrate(self.source, hashes, self.root / 'failed')
        self.assertFalse((self.root / 'failed').exists()); self.assertEqual(self.hashes(), hashes)

    def test_mid_write_failure_keeps_source_and_allows_fresh_retry(self):
        hashes = self.hashes(); original = migration._write_private; calls = []
        def fail(root, name, data):
            calls.append(name)
            if len(calls) == 3: raise OSError('interrupt')
            return original(root, name, data)
        with patch.object(migration, '_write_private', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'interrupt'):
                migration.migrate(self.source, hashes, self.root / 'failed')
        self.assertFalse((self.root / 'failed').exists()); self.assertEqual(self.hashes(), hashes)
        self.assertTrue(migration.migrate(self.source, hashes, self.root / 'retry')['migration_executed'])

    def test_directory_fsync_failure_removes_completion_marker_and_new_target(self):
        import stat
        hashes = self.hashes(); original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode): raise OSError('directory durability unknown')
            return original(fd)
        with patch.object(migration.os, 'fsync', side_effect=fail_directory):
            with self.assertRaisesRegex(OSError, 'directory durability unknown'):
                migration.migrate(self.source, hashes, self.root / 'uncertain')
        self.assertFalse((self.root / 'uncertain').exists()); self.assertEqual(self.hashes(), hashes)


    def test_success_syncs_new_target_before_parent_and_parent_failure_cleans_only_target(self):
        hashes = self.hashes(); target = self.root / 'durable-order'; original = migration._sync; calls = []
        def record(path, directory=False):
            calls.append((Path(path), directory))
            return original(path, directory)
        with patch.object(migration, '_sync', side_effect=record):
            result = migration.migrate(self.source, hashes, target)
        self.assertTrue(result['migration_executed'])
        self.assertEqual(calls[-2:], [(target, True), (target.parent, True)])
        self.assertEqual(self.hashes(), hashes)

        failed = self.root / 'parent-sync-failed'; calls = []
        def fail_parent(path, directory=False):
            path = Path(path); calls.append((path, directory))
            if path == failed.parent:
                raise OSError('parent directory durability unknown')
            return original(path, directory)
        with patch.object(migration, '_sync', side_effect=fail_parent):
            with self.assertRaisesRegex(OSError, 'parent directory durability unknown'):
                migration.migrate(self.source, hashes, failed)
        self.assertEqual(calls[-2:], [(failed, True), (failed.parent, True)])
        self.assertFalse(failed.exists())
        self.assertEqual(self.hashes(), hashes)

    def test_two_concurrent_writers_have_one_new_directory_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        hashes = self.hashes(); target = self.root / 'concurrent'
        def run():
            try: return migration.migrate(self.source, hashes, target)['files']
            except FileExistsError: return 'EXISTS'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(results.count('EXISTS'), 1)
        files = next(result for result in results if type(result) is dict)
        self.assertTrue(migration.inspect(target, files)['supported']); self.assertEqual(self.hashes(), hashes)

    def test_killed_process_has_no_completion_marker_and_new_target_recovers(self):
        hashes = self.hashes(); target = self.root / 'killed'
        code = ('import os,json,sys,socket,urllib.request; '
                'socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError("NETWORK_FORBIDDEN")); '
                'urllib.request.OpenerDirector.open=socket.socket.connect; '
                'from scripts import community_stage_migration as m; '
                'original=m._write_private; '
                'm._write_private=lambda root,name,blob: (original(root,name,blob),os._exit(29))[0]; '
                'm.migrate(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3])')
        result = subprocess.run([sys.executable, '-c', code, str(self.source), json.dumps(hashes), str(target)],
                                cwd=Path(__file__).resolve().parents[1], timeout=20, check=False)
        self.assertEqual(result.returncode, 29); self.assertFalse((target / 'snapshot.json').exists())
        with self.assertRaisesRegex(ValueError, 'EXCLUSIVE_OFFLINE_SNAPSHOT_REQUIRED'):
            migration.inspect(target, hashes)
        with self.assertRaises(FileExistsError): migration.migrate(self.source, hashes, target)
        self.assertEqual(self.hashes(), hashes)
        self.assertTrue(migration.migrate(self.source, hashes, self.root / 'recovered')['migration_executed'])


if __name__ == '__main__':
    unittest.main()
