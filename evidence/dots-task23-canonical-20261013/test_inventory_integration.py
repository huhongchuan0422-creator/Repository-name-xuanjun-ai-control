"""Fixture-only proposed shared delta; never opens an operational ledger."""
import copy,hashlib,json,os,sqlite3,sys,tempfile,unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','..','scripts'))
from task_supervisor_runtime import canonical_inventory_page,CANONICAL_RUN_COLUMNS
from proposed_methods_fixture import ProposedMethods,SCHEMA

class TransactionFixture(ProposedMethods):
    def __init__(self,binding):
        self.activation_binding=binding;self.activation_store=object();self.current=dict(binding)
        self.clock=lambda:100
    def _assert_activation(self):
        if self.current!=self.activation_binding:raise ValueError('ACTIVATION_CHANGED')

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=os.path.join(self.tmp.name,'fixture.sqlite')
        self.db=sqlite3.connect(self.path,isolation_level=None);self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL)')
        self.db.executescript(SCHEMA)
        self.checkpoint={};self.db.execute("INSERT INTO tasks VALUES('t','CODEX_EXEC','PENDING','[]',NULL,NULL,4,'{}',9999)")
        self.binding={'ledger_uuid':'00000000-0000-0000-0000-000000000001','instance':'00000000-0000-0000-0000-000000000002','generation':1,'epoch':2,'db_path':self.path}
        info=os.stat(self.path);self.identity='%d:%d'%(info.st_dev,info.st_ino)
        self.supervisor=TransactionFixture(self.binding)
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def observe(self):
        self.db.execute('BEGIN')
        try:return canonical_inventory_page(self.db,100,activation_binding=self.binding,ledger_identity=self.identity)['tasks'][0]
        finally:self.db.rollback()
    def record(self,intent):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result=self.supervisor.record_inventory_notice(self.db,intent,self.binding,self.identity)
            self.supervisor._assert_activation();self.db.commit();return result
        except BaseException:self.db.rollback();raise
    def count(self):return self.db.execute('SELECT count(*) FROM supervision_events').fetchone()[0]
    def test_fixture_and_delta_hash_binding(self):
        root=os.path.dirname(__file__)
        with open(os.path.join(root,'PROVENANCE.json')) as f:meta=json.load(f)
        for path,key in (('proposed_methods_fixture.py','fixture_sha256'),('execution_supervision_inventory.diff','patch_sha256')):
            with open(os.path.join(root,path),'rb') as f:self.assertEqual(hashlib.sha256(f.read()).hexdigest(),meta[key])

    def test_unsupervised_notice_durable_no_second_registry(self):
        tables=list(self.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        receipt=self.record(self.observe());self.assertFalse(receipt['dispatch_performed']);self.assertEqual(receipt['receiver_ack'],'NOT_PROVEN')
        self.assertEqual(self.count(),1);self.assertEqual(self.db.execute('SELECT count(*) FROM supervision_delivery').fetchone()[0],2)
        self.assertEqual([tuple(x) for x in tables],[tuple(x) for x in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
    def test_restart_duplicate_preserves_dead_letters(self):
        intent=self.observe();self.record(intent)
        self.db.execute("UPDATE supervision_delivery SET state='DEAD_LETTER',attempts=5")
        self.db.close();self.db=sqlite3.connect(self.path,isolation_level=None);self.db.row_factory=sqlite3.Row
        self.record(intent);self.assertEqual(self.count(),1)
        self.assertTrue(all(tuple(x)==('DEAD_LETTER',5) for x in self.db.execute('SELECT state,attempts FROM supervision_delivery')))
    def test_changed_fence_checkpoint_activation_rejected_without_events(self):
        intent=self.observe()
        for sql in ("UPDATE tasks SET fence=5","UPDATE tasks SET checkpoint='{\"changed\":true}'"):
            self.db.execute(sql)
            with self.assertRaises(ValueError):self.record(intent)
            self.assertEqual(self.count(),0)
            self.db.execute("UPDATE tasks SET fence=4,checkpoint='{}'")
        self.supervisor.current['epoch']=3
        with self.assertRaises(ValueError):self.record(intent)
        self.assertEqual(self.count(),0)
    def test_stale_replacement_run_and_all_entry_pairs(self):
        for origin in ('WORK','CHATGPT','DOTS'):
            for successor in ('WORK','CHATGPT','DOTS'):
                self.db.execute('DELETE FROM supervised_runs')
                columns=('task_id','spec_hash','executor','run_id','session_id','workdir','artifact','dispatched_at','start_deadline','progress_deadline','result_deadline','native_state','effects','budget_key','budget_spent','status','checkpoint','checkpoint_hash','writer_fence','writer_epoch')
                values=('t','b'*64,origin,'old-run','old-session','/fixture','artifact',0,50,50,50,'EXITED','UNKNOWN','budget',0,'STALLED','{}',hashlib.sha256(b'{}').hexdigest(),4,2)
                self.db.execute('INSERT INTO supervised_runs('+','.join(columns)+') VALUES('+','.join('?' for x in columns)+')',values)
                intent=self.observe();self.assertIn('TERMINAL_WITHOUT_RESULT',intent['attention'])
                self.db.execute('UPDATE supervised_runs SET executor=?,run_id=?,session_id=?',(successor,'new-run','new-session'))
                with self.assertRaises(ValueError):self.record(intent)
                self.assertEqual(self.count(),0)
    def test_terminal_without_next_action_is_visible_no_model_wake(self):
        self.db.execute("UPDATE tasks SET state='DONE'")
        intent=self.observe();self.assertIn('TERMINAL_CONTINUATION_UNVERIFIED',intent['attention'])
        self.assertEqual(intent['provider'],'CAPABILITY_UNAVAILABLE')
        self.assertFalse(self.record(intent)['dispatch_performed'])

if __name__=='__main__':unittest.main()
