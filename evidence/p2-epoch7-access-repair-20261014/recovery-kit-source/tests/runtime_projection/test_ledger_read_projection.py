import json, unittest
from unittest import mock
from ledger_read_projection import project

class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.active={'ledger_uuid':'uuid','generation':1,'epoch':8,'instance':'instance','db_path':'/private/db','ledger_socket':'/run/ledger.sock'}
        self.store=mock.Mock(); self.store.read.return_value=dict(self.active)
        self.ledger=mock.Mock(); self.ledger.observation.return_value={'id':'task','fence':3}
        self.snapshot=mock.Mock(return_value={'tasks':[]})
    def request(self,op,payload):
        return dict({k:self.active[k] for k in ('ledger_uuid','generation','epoch','instance')},operation=op,payload=payload)
    def invoke(self,r,uid):return project(r,uid,1004,self.store,self.ledger,self.snapshot)
    def test_broker_only_observation(self):
        out=json.loads(self.invoke(self.request('BROKER_OBSERVATION',{'task_id':'task'}),0).decode())
        self.assertTrue(out['accepted']);self.ledger.observation.assert_called_once_with('task');self.snapshot.assert_not_called()
        self.assertEqual(self.ledger.method_calls,[mock.call.observation('task')])
    def test_dashboard_uses_server_database(self):
        out=json.loads(self.invoke(self.request('DASHBOARD_SNAPSHOT',{'limit':200}),1004).decode())
        self.assertEqual(out['result'],{'tasks':[]});self.ledger.observation.assert_not_called()
        self.assertEqual(self.snapshot.call_args[0],('/private/db',))
    def test_cross_role_denied(self):
        for op,payload,uid in [('BROKER_OBSERVATION',{'task_id':'task'},1004),('DASHBOARD_SNAPSHOT',{'limit':1},0),('DASHBOARD_SNAPSHOT',{'limit':1},1002)]:
            with self.assertRaises(PermissionError):self.invoke(self.request(op,payload),uid)
        self.ledger.observation.assert_not_called();self.snapshot.assert_not_called()
    def test_no_arbitrary_path_or_sql(self):
        for payload in ({'limit':1,'db_path':'/other'},{'sql':'select 1'},{'limit':True},{'limit':501}):
            with self.assertRaises(ValueError):self.invoke(self.request('DASHBOARD_SNAPSHOT',payload),1004)
    def test_mutating_operation_denied(self):
        for op in ('CLAIM','NATIVE_GATEWAY','OWNER_DECISION','SQL','LAUNCH'):
            with self.assertRaises(PermissionError):self.invoke(self.request(op,{}),0)
    def test_stale_before_read(self):
        r=self.request('BROKER_OBSERVATION',{'task_id':'task'});r['epoch']=7
        with self.assertRaises(PermissionError):self.invoke(r,0)
        self.ledger.observation.assert_not_called()
    def test_switch_during_read(self):
        self.store.read.side_effect=[self.active,dict(self.active,epoch=9)]
        with self.assertRaises(RuntimeError):self.invoke(self.request('BROKER_OBSERVATION',{'task_id':'task'}),0)
    def test_response_bounded(self):
        self.snapshot.return_value={'oversized':'x'*1048576}
        with self.assertRaises(ValueError):self.invoke(self.request('DASHBOARD_SNAPSHOT',{'limit':1}),1004)
    def test_invalid_nonfinite_rejected(self):
        self.snapshot.return_value={'value':float('nan')}
        with self.assertRaises(ValueError):self.invoke(self.request('DASHBOARD_SNAPSHOT',{'limit':1}),1004)
    def test_provider_error_preserved(self):
        self.snapshot.side_effect=OSError('read failure')
        with self.assertRaises(OSError):self.invoke(self.request('DASHBOARD_SNAPSHOT',{'limit':1}),1004)

if __name__=='__main__':unittest.main()
