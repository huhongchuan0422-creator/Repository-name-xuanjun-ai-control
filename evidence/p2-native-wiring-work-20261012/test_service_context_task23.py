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
from execution_supervision import ExecutionSupervisor,SCHEMA as SUPERVISION_SCHEMA

class FakeSocket(object):
    def __init__(self,uid):
        self.uid=uid
        self.sent=b''
        self.done=False
        self.timeout=None
    def settimeout(self,value):
        self.timeout=value
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
    def __init__(self): self.calls=0
    def preflight(self,c):
        self.calls+=1
        return {'ready':True}

class TimeoutSocket(FakeSocket):
    def recv(self,n):
        raise socket.timeout('fixture timeout')

class OversizeSocket(FakeSocket):
    def recv(self,n):
        if self.done:return b''
        self.done=True
        return b'x'*(relay.MAXIMUM+1)

class Activation(object):
    def __init__(self,path):
        self.value={'ledger_uuid':'00000000-0000-0000-0000-000000000001',
                    'generation':1,'epoch':2,
                    'instance':'00000000-0000-0000-0000-000000000002',
                    'db_path':path}
    def read(self,require_active=True):
        return dict(self.value)

class Tests(unittest.TestCase):
    def test_relay_rejects_unauthorized_peer_and_keeps_serving(self):
        controller=Controller()
        fake=FakeSocket(424242)
        result=relay.serve_connection(fake,controller,31337)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'],'PermissionError')
        self.assertEqual(fake.timeout,5)
        valid=FakeSocket(31337)
        result=relay.serve_connection(valid,controller,31337)
        self.assertTrue(result['ok'])
        self.assertTrue(result['result']['ready'])

    def test_relay_allows_only_fixed_preflight(self):
        fake=FakeSocket(31337)
        relay.serve_connection(fake,Controller(),31337)
        value=json.loads(fake.sent.decode())
        self.assertTrue(value['ok'])
        self.assertTrue(value['result']['ready'])

    def test_relay_partial_timeout_and_oversize_are_bounded_then_valid_survives(self):
        controller=Controller()
        timeout=TimeoutSocket(31337)
        result=relay.serve_connection(timeout,controller,31337)
        self.assertFalse(result['ok'])
        self.assertIn(result['error'],('TimeoutError','timeout'))
        self.assertEqual(controller.calls,0)
        oversize=OversizeSocket(31337)
        result=relay.serve_connection(oversize,controller,31337)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'],'ValueError')
        self.assertEqual(controller.calls,0)
        valid=FakeSocket(31337)
        result=relay.serve_connection(valid,controller,31337)
        self.assertTrue(result['ok'])
        self.assertEqual(controller.calls,1)

    def test_dispatcher_keeps_protect_home_and_uses_relay(self):
        service=(ROOT/'deploy/xuanjun-development-dispatcher.service').read_text()
        self.assertIn('ProtectHome=yes',service)
        self.assertIn('Requires=xuanjun-p2-gateway-relay.socket',service)
        self.assertIn('p2_service_context_preflight.py',service)
        config=json.loads((STAGE1/'native_gateway_controller.py.json').read_text())
        self.assertEqual(config,{'relay_socket':'/run/xuanjun-development/p2-gateway.sock',
                                 'server_user':'xuanjun_dev',
                                 'client_group':'xuanjun-dispatcher'})
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
        db.executescript(SUPERVISION_SCHEMA)
        db.execute('PRAGMA journal_mode=WAL')
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
            original=ExecutionSupervisor.record_inventory_notice
            swapped=[False]
            def swap(supervisor,db,intent,binding,identity):
                result=original(supervisor,db,intent,binding,identity)
                if not swapped[0]:
                    swapped[0]=True
                    replacement=path+'.new'
                    self._db(replacement)
                    os.replace(replacement,path)
                return result
            with patch.object(ExecutionSupervisor,'record_inventory_notice',new=swap):
                with self.assertRaises(LeaseLost):
                    ledger.record_inventory_notices()
            self.assertTrue(swapped[0])
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_delivery').fetchone()[0],0)
            db.close()


    def test_inventory_paginates_beyond_first_hundred_and_restart_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite')
            self._db(path)
            db=sqlite3.connect(path)
            for i in range(1,151):
                db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
                    ('t%03d'%i,'CODEX_EXEC','PENDING','[]',None,None,4,'{}',9999))
            db.execute("UPDATE tasks SET depends=? WHERE id='t001'",
                       ('['*65+'0'+']'*65,))
            db.commit();db.close()
            activation=Activation(os.path.realpath(path))
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                                   clock=lambda:100,activation_store=activation)
            result=ledger.record_inventory_notices(limit=20)
            self.assertEqual(result['observed'],151)
            self.assertGreater(result['pages'],1)
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],151)
            late=db.execute("SELECT event_key FROM supervision_events WHERE task_id='t150'").fetchone()[0]
            db.execute("UPDATE supervision_delivery SET state='DEAD_LETTER',attempts=5 WHERE event_key=?",(late,))
            db.commit();db.close()
            restarted=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                                      clock=lambda:101,activation_store=activation)
            again=restarted.record_inventory_notices(limit=17)
            self.assertEqual(again['observed'],151)
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],151)
            self.assertTrue(all(tuple(x)==('DEAD_LETTER',5) for x in
                db.execute("SELECT state,attempts FROM supervision_delivery WHERE event_key=?",(late,))))
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0].lower(),'wal')
            db.close()

    def test_path_replacement_before_sqlite_connect_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite')
            self._db(path)
            activation=Activation(os.path.realpath(path))
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                                   clock=lambda:100,activation_store=activation)
            original=ledger_module.sqlite3.connect
            swapped=[False]
            def connect(database,*args,**kwargs):
                if isinstance(database,str) and database.startswith('file:/proc/self/fd/') and not swapped[0]:
                    swapped[0]=True
                    replacement=path+'.new'
                    self._db(replacement)
                    os.replace(replacement,path)
                return original(database,*args,**kwargs)
            with patch.object(ledger_module.sqlite3,'connect',side_effect=connect):
                with self.assertRaises(LeaseLost):
                    ledger.record_inventory_notices()
            self.assertTrue(swapped[0])

    def test_rejected_hardlinked_database_does_not_leak_fds(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._db(path)
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'])
            os.link(path,path+'.hardlink')
            before=len(os.listdir('/proc/self/fd'))
            for unused in range(3):
                with self.assertRaises(ledger_module.SchemaMismatch):
                    with ledger._pinned_transaction(): pass
            self.assertEqual(len(os.listdir('/proc/self/fd')),before)

    def test_connect_and_pragma_initialization_failures_close_complete_lifetime(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._db(path)
            ledger=ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'])
            before=len(os.listdir('/proc/self/fd'))
            for error in (sqlite3.OperationalError('fixture'),RuntimeError('fixture')):
                with patch.object(ledger_module.sqlite3,'connect',side_effect=error):
                    with self.assertRaises((ledger_module.SchemaMismatch,RuntimeError)):
                        with ledger._pinned_transaction(): pass
                self.assertEqual(len(os.listdir('/proc/self/fd')),before)
            class BrokenConnection(object):
                row_factory=None
                closed=False
                def execute(self,*args): raise RuntimeError('pragma fixture')
                def close(self): self.closed=True
            broken=BrokenConnection()
            with patch.object(ledger_module.sqlite3,'connect',return_value=broken):
                with self.assertRaises(RuntimeError):
                    with ledger._pinned_transaction(): pass
            self.assertTrue(broken.closed)
            self.assertEqual(len(os.listdir('/proc/self/fd')),before)

    def _populate(self,path,count):
        self._db(path)
        db=sqlite3.connect(path);db.execute('DELETE FROM tasks')
        for i in range(count):
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                ('t%05d'%i,'CODEX_EXEC','PENDING','[]',None,None,4,'{}',9999))
        db.execute('UPDATE tasks SET depends=? WHERE id=?',
            ('['*65+'0'+']'*65,'t00000'))
        db.commit();db.close()

    def _ledger(self,path,activation):
        return ExecutionLedger(path,['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'],
                               clock=lambda:100,activation_store=activation)

    def test_sixty_five_pages_make_durable_progress_and_restart_finishes(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._populate(path,65)
            activation=Activation(os.path.realpath(path))
            first=self._ledger(path,activation).record_inventory_notices(limit=1)
            self.assertEqual(first['observed'],64);self.assertEqual(first['pages'],64)
            self.assertTrue(first['scan_pending']);self.assertFalse(first['sweep_complete'])
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],64)
            checkpoint=json.loads(db.execute("SELECT details FROM events WHERE event='INVENTORY_SCAN_CHECKPOINT_V1' ORDER BY id DESC LIMIT 1").fetchone()[0])
            self.assertEqual(checkpoint['after_id'],'t00063')
            self.assertEqual(checkpoint['sweep_end'],'t00064');db.close()
            second=self._ledger(path,activation).record_inventory_notices(limit=1)
            self.assertEqual(second['observed'],1);self.assertTrue(second['sweep_complete'])
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],65)
            db.close()

    def test_default_population_over_6400_is_not_rolled_back_or_starved(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._populate(path,6401)
            activation=Activation(os.path.realpath(path))
            first=self._ledger(path,activation).record_inventory_notices()
            self.assertEqual(first['observed'],6400);self.assertTrue(first['scan_pending'])
            second=self._ledger(path,activation).record_inventory_notices()
            self.assertEqual(second['observed'],1);self.assertTrue(second['sweep_complete'])
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],6401)
            self.assertEqual(db.execute("SELECT count(*) FROM supervision_events WHERE task_id='t06400'").fetchone()[0],1)
            db.close()

    def test_finite_sweep_wraps_for_insertions_before_and_after_cursor(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._populate(path,65)
            activation=Activation(os.path.realpath(path))
            self._ledger(path,activation).record_inventory_notices(limit=1)
            db=sqlite3.connect(path)
            for name in ('a-new','z-new'):
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                    (name,'CODEX_EXEC','PENDING','[]',None,None,4,'{}',9999))
            db.commit();db.close()
            finish=self._ledger(path,activation).record_inventory_notices(limit=1)
            self.assertEqual(finish['observed'],1);self.assertTrue(finish['sweep_complete'])
            sweep=self._ledger(path,activation).record_inventory_notices()
            self.assertEqual(sweep['observed'],67);self.assertTrue(sweep['sweep_complete'])
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],67)
            db.close()

    def test_notice_failure_rolls_back_cursor_and_can_retry_same_slice(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._populate(path,65)
            activation=Activation(os.path.realpath(path));ledger=self._ledger(path,activation)
            with patch.object(ExecutionSupervisor,'record_inventory_notice',side_effect=RuntimeError('fixture')):
                with self.assertRaises(RuntimeError): ledger.record_inventory_notices(limit=1)
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],0)
            db.close()
            self.assertEqual(ledger.record_inventory_notices(limit=1)['observed'],64)

    def test_new_activation_does_not_reuse_old_scan_cursor(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._populate(path,65)
            activation=Activation(os.path.realpath(path))
            self._ledger(path,activation).record_inventory_notices(limit=1)
            activation.value['epoch']+=1
            again=self._ledger(path,activation).record_inventory_notices(limit=1)
            self.assertEqual(again['observed'],64);self.assertTrue(again['scan_pending'])

    def test_corrupt_checkpoint_holds_without_notice_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'ledger.sqlite');self._populate(path,65)
            activation=Activation(os.path.realpath(path))
            db=sqlite3.connect(path)
            db.execute("INSERT INTO events(task_id,event,created,details) VALUES(NULL,'INVENTORY_SCAN_CHECKPOINT_V1',0,'bad')")
            db.commit();db.close()
            with self.assertRaises(ledger_module.SchemaMismatch):
                self._ledger(path,activation).record_inventory_notices(limit=1)
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM supervision_events').fetchone()[0],0)
            db.close()

if __name__=='__main__':
    unittest.main(verbosity=2)
