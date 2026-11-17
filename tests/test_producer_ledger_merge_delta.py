import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch
import task_center_app as app
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from reusable_scheduler_cli import demo_graph
from task_supervisor import Supervisor

KEY=b'0123456789abcdef0123456789abcdef'

class ProducerLedgerMerge(unittest.TestCase):
    def test_old_cli_and_ledger_arguments_reach_same_server(self):
        captured={}
        class Stop(Exception): pass
        def server(*args,**kw):captured.update(kw);raise Stop()
        args=['--db','/unused-fixture-db','--test-authority-key','fixture-key','--tenant','fixture-tenant',
              '--mcp-dispatch-config-file','/fixture-dispatch','--correction-observer-interval','300',
              '--delivery-ledger-root','/fixture-ledger','--delivery-ledger-namespace','fixture',
              '--delivery-ledger-writer','fixture-writer']
        with patch.object(app,'make_server',side_effect=server),patch.object(app,'load_dispatch_config',return_value={'fixture':'dispatch'}) as loader:
            with self.assertRaises(Stop):app.main(args)
        loader.assert_called_once_with('/fixture-dispatch')
        self.assertEqual(captured['mcp_dispatch_config'],{'fixture':'dispatch'})
        self.assertEqual(captured['correction_observer_interval'],300)
        self.assertEqual(captured['delivery_ledger_reader'].tenant_id,'fixture-tenant')
    def test_legacy_new_state_is_preserved_in_read_only_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            db=os.path.join(temp,'fixture.sqlite'); supervisor=Supervisor(db)
            auth=TestTenantAuthority(KEY);gateway=GatewayKernel(supervisor,auth)
            gateway.register_graph(auth.issue('tenant-fixture','seed'),demo_graph('tenant-fixture'))
            supervisor.db.execute("UPDATE tasks SET state='NEW' WHERE task_id='demo-b'");supervisor.db.commit();supervisor.close()
            result=app.read_only_projection(db,KEY,'tenant-fixture','viewer')
            row=next(x for x in result['tasks'] if x['task_id']=='demo-b')
            self.assertEqual((row['state'],row['runtime_status']),('NEW','NEW'))
            app.read_only_public_projection(db,KEY,'tenant-fixture','viewer')

if __name__=='__main__':unittest.main()
