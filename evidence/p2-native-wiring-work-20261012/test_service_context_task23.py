from __future__ import print_function
import json
import os
import pathlib
import pwd
import socket
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT'])
STAGE1=ROOT/'stage1'
sys.path.insert(0,str(STAGE1))
import execution_ledger as ledger_module
import p2_gateway_relay as relay
from execution_ledger import ExecutionLedger,LeaseLost

class FakeSocket(object):
    def __init__(self,uid):
        self.uid=uid
        self.sent=b''
        self.done=False
    def getsockopt(self,*args):
        return struct.pack('3i',111,self.uid,222)
    def recv(self,n):
        if self.done:
            return b''
        self.done=True
        return b'{"operation":"preflight"}\n'
    def sendall(self,data):
        self.sent+=data

class Controller(object):
    def preflight(self,c):
        return {'ready':True}

class Activation(object):
    def __init__(self,path):
        self.value={'ledger_uuid':'00000000-0000-0000-0000-000000000001',
                    'generation':1,'epoch':2,
                    'instance':'00000000-0000-0000-0000-000000000002',
                    'db_path':path}
    def read(self,require_active=True):
        return dict(self.value)

class Tests(unittest.TestCase):
    def test_relay_rejects_unauthorized_peer_before_gateway_call(self):
        fake=FakeSocket(424242)
        with self.assertRaises(PermissionError):
            relay.serve_connection(fake,Controller(),31337)
        self.assertEqual(fake.sent,b'')

    def test_relay_allows_only_fixed_preflight(self):
        fake=FakeSocket(31337)
        relay.serve_connection(fake,Controller(),31337)
        value=json.loads(fake.sent.decode())
        self.assertTrue(value['ok'])
        self.assertTrue(value['result']['ready'])

    def test_dispatcher_keeps_protect_home_and_uses_relay(self):
        service=(ROOT/'deploy/xuanjun-development-dispatcher.service').read_text()
        self.assertIn('ProtectHome=yes',service)
        self.assertIn('Requires=xuanjun-p2-gateway-relay.socket',service)
        self.assertIn('p2_service_context_preflight.py',service)
        config=json.loads((STAGE1/'native_gateway_controller.py.json').read_text())
        self.assertEqual(config,{'relay_socket':'/run/xuanjun-development/p2-gateway.sock',
                                 'server_user':'xuanjun_dev'})
        relay_service=(ROOT/'deploy/xuanjun-p2-gateway-relay.service').read_text()
        self.assertIn('User=xuanjun_dev',relay_service)
        self.assertIn('ProtectHome=read-only',relay_service)
        wake=(ROOT/'deploy/xuanjun-github-intake.service').read_text()
        self.assertIn('mechanical_wake_service.py',wake)
        wake_py=(STAGE1/'mechanical_wake_service.py').read_text()
        self.assertIn('record_inventory_notices()',wake_py)

    def _db(self,path):
        db=sqlite3.connect(path)
        db.executescript("""
        CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL);
        CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,requested_at REAL,decided_at REAL);
        CREATE TABLE events(id INTEGER PRIMARY KEY,task_id TEXT,event TEXT,created REAL,details TEXT);
        """)
        db.execute("INSERT INTO tasks VALUES('t','CODEX_EXEC','PENDING','[]',NULL,NULL,4,'{}',9999)")
        db.commit()
        db.close()

    def test_production_inventory_caller_records_notice_in_existing_db(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite')
            self._db(path)
            activation=Activation(os.path.realpath(path))
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                                   clock=lambda:100,activation_store=activation)
            result=ledger.record_inventory_notices()
            self.assertFalse(result['dispatch_performed'])
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_delivery').fetchone()[0],2)
            db.close()

    def test_sqlite_connection_uses_pinned_fd_uri(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite')
            self._db(path)
            activation=Activation(os.path.realpath(path))
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                                   clock=lambda:100,activation_store=activation)
            original=sqlite3.connect
            seen=[]
            def connect(database,*args,**kwargs):
                seen.append(database)
                return original(database,*args,**kwargs)
            with patch.object(ledger_module.sqlite3,'connect',side_effect=connect):
                with ledger._pinned_transaction() as value:
                    db,identity=value
                    self.assertTrue(identity)
                    self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0],1)
            self.assertTrue(seen)
            self.assertRegex(seen[0],r'^file:/proc/self/fd/[0-9]+\?mode=rw$')

    def test_inode_swap_rolls_back_inventory_transaction(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite')
            self._db(path)
            activation=Activation(os.path.realpath(path))
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                                   clock=lambda:100,activation_store=activation)
            real=ledger.supervisor()
            original=real.record_inventory_notice
            def swap(db,intent,binding,identity):
                result=original(db,intent,binding,identity)
                replacement=path+'.new'
                self._db(replacement)
                os.replace(replacement,path)
                return result
            class Wrapper(object):
                def record_inventory_notice(self,*args):
                    return swap(*args)
            with patch.object(ledger,'supervisor',return_value=Wrapper()):
                with self.assertRaises(LeaseLost):
                    ledger.record_inventory_notices()
            db=sqlite3.connect(path)
            self.assertFalse(db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='supervision_events'").fetchone())
            db.close()

if __name__=='__main__':
    unittest.main(verbosity=2)
