import json, unittest
from unittest import mock
from ledger_read_client import BrokerObservationClient,dashboard_read
from ledger_read_projection import project

class ReadClientTests(unittest.TestCase):
    def setUp(self):
        self.active={'ledger_uuid':'u','generation':1,'epoch':8,'instance':'i','db_path':'/private/db','ledger_socket':'/run/ledger.sock'}
        self.store=mock.Mock();self.store.read.return_value=self.active
        self.ledger=mock.Mock();self.ledger.observation.return_value={'id':'task','fence':1}
        self.snapshot=mock.Mock(return_value={'tasks':[]})
    def transport(self,uid):
        def call(path,request):
            self.assertEqual(path,self.active['ledger_socket'])
            return json.loads(project(request,uid,1004,self.store,self.ledger,self.snapshot).decode())
        return call
    def test_combined_broker_projection(self):
        client=BrokerObservationClient(self.store,self.transport(0))
        self.assertEqual(client.observation('task'),{'id':'task','fence':1})
        self.assertFalse(hasattr(client,'claim'));self.assertFalse(hasattr(client,'launch'))
    def test_combined_dashboard_projection(self):
        self.assertEqual(dashboard_read(self.store,self.transport(1004)),{'tasks':[]})
    def test_no_default_transport(self):
        with self.assertRaises(ValueError):BrokerObservationClient(self.store,None)
    def test_wrong_epoch_response(self):
        def transport(path,request):
            r={k:self.active[k] for k in ('ledger_uuid','generation','epoch','instance')}
            r.update(accepted=True,operation='BROKER_OBSERVATION',result={},epoch=7)
            return r
        with self.assertRaises(RuntimeError):BrokerObservationClient(self.store,transport).observation('task')
    def test_role_rejection_propagates(self):
        with self.assertRaises(PermissionError):BrokerObservationClient(self.store,self.transport(1004)).observation('task')
    def test_invalid_limit(self):
        for limit in (0,501,True,'1'):
            with self.assertRaises(ValueError):dashboard_read(self.store,self.transport(1004),limit)
    def test_transport_error_propagates(self):
        transport=mock.Mock(side_effect=OSError('offline'))
        with self.assertRaises(OSError):BrokerObservationClient(self.store,transport).observation('task')

if __name__=='__main__':unittest.main()
