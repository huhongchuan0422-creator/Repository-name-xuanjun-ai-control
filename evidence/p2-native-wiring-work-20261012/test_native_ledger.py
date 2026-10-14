import os, sys, sqlite3, tempfile, unittest, json
sys.path.insert(0, os.path.join(os.environ['P2_SOURCE_ROOT'],'stage1'))
from execution_ledger import ExecutionLedger, LeaseLost
from native_ledger_bridge import execute
class Activation:
    def __init__(self,path):self.value={'ledger_uuid':'ledger','generation':1,'epoch':2,'instance':'instance','db_path':path}
    def read(self,require_active=True):return dict(self.value)
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=os.path.join(self.temp.name,'state.sqlite')
        conn=sqlite3.connect(self.path)
        for table, columns in ExecutionLedger.SCHEMAS.items():
            conn.execute('CREATE TABLE '+table+' ('+','.join(name+' '+kind+(' PRIMARY KEY' if pk else '') for name,kind,pk in columns)+')')
        conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',('t','CODEX_EXEC','PENDING','[]',None,None,0,'{}',100))
        conn.commit();conn.close()
        self.now=100;self.activation=Activation(self.path)
        self.ledger=ExecutionLedger(self.path,['owner/repo'],clock=lambda:self.now,approved_base_shas=['a'*40],activation_store=self.activation)
        self.ledger.register_spec('t',{'repo':'owner/repo','type':'CODEX_EXEC','prompt':'approved','heavy':True,'timeout_seconds':30,'base_sha':'a'*40},'owner',True)
        claim=self.ledger.claim('worker',60)
        self.request={k:claim[k] for k in ('task_id','spec_hash','fence','epoch','generation','instance')};self.request['lease']='worker'
    def tearDown(self):self.temp.cleanup()
    def test_real_sqlite_cas_preserves_pipeline_checkpoint(self):
        self.ledger.checkpoint('t','worker',1,{'phase':'IN_FLIGHT_CODEX','native_source_manifest':{'tree':'a'}})
        before=execute(self.ledger,{'operation':'read','request':self.request})
        record={'phase':'LAUNCH_INTENT','idempotency_key':'k'}
        after=execute(self.ledger,{'operation':'cas','request':self.request,'expected':None,'execution':record})
        self.assertEqual(after['task']['native_execution'],record)
        self.assertEqual(before['task']['source_manifest'],{'tree':'a'})
        self.ledger.checkpoint('t','worker',1,{'phase':'CODE_READY'})
        cp=self.ledger.observation('t')['checkpoint']
        self.assertEqual(cp['native_execution'],record);self.assertEqual(cp['phase'],'CODE_READY')
    def test_conflict_no_overwrite(self):
        self.ledger.native_compare_set(self.request,None,{'phase':'RUNNING'})
        with self.assertRaises(LeaseLost):self.ledger.native_compare_set(self.request,None,{'phase':'OTHER'})
        self.assertEqual(self.ledger.native_observation(self.request)['task']['native_execution']['phase'],'RUNNING')
    def test_pipeline_cannot_forge_native_receipt(self):
        with self.assertRaises(ValueError):self.ledger.checkpoint('t','worker',1,{'native_execution':{'phase':'TERMINAL'}})
    def test_expired_lease_rejected(self):
        self.now=161
        with self.assertRaises(LeaseLost):self.ledger.native_observation(self.request)
    def test_changed_epoch_rejected(self):
        self.activation.value['epoch']=3
        with self.assertRaises(LeaseLost):self.ledger.native_observation(self.request)
    def test_wrong_spec_rejected(self):
        with self.assertRaises(LeaseLost):self.ledger.native_observation(dict(self.request,spec_hash='f'*64))
    def test_wrong_fence_rejected(self):
        with self.assertRaises(LeaseLost):self.ledger.native_observation(dict(self.request,fence=2))
    def test_guard_validates_actual_lease(self):
        self.assertIs(execute(self.ledger,{'operation':'guard','request':self.request}),True)
    def test_expired_lease_can_read_stop_receipt_without_reclaim(self):
        self.ledger.native_compare_set(self.request,None,{'phase':'RUNNING','request':self.request})
        self.now=161
        observed=self.ledger.native_receipt_observation(self.request)
        self.assertEqual(observed['task']['native_execution']['phase'],'RUNNING')
        with self.assertRaises(LeaseLost):self.ledger.native_observation(self.request)
    def test_cleanup_receipt_cannot_choose_another_fence(self):
        self.ledger.native_compare_set(self.request,None,{'phase':'RUNNING','request':self.request})
        with self.assertRaises(LeaseLost):self.ledger.native_receipt_observation(dict(self.request,fence=9))
    def test_no_second_registry(self):
        conn=sqlite3.connect(self.path)
        names={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")};conn.close()
        self.assertEqual(names,set(ExecutionLedger.SCHEMAS)|{'execution_specs','worker_heartbeats'})
if __name__=='__main__':unittest.main(verbosity=2)
