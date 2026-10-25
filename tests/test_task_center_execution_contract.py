from __future__ import print_function

import copy
import os
import shutil
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
import sys
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_center_execution_contract import ExternalReceiptContract
from task_supervisor import Supervisor


KEY = b'0123456789abcdef0123456789abcdef'


class ExternalReceiptContractTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.supervisor = Supervisor(os.path.join(self.root, 'state.sqlite3'))
        self.authority = TestTenantAuthority(KEY)
        self.gateway = GatewayKernel(self.supervisor, self.authority)
        self.a = self.authority.issue('tenant-a', 'adapter-a')
        self.b = self.authority.issue('tenant-b', 'adapter-b')
        self.gateway.register_graph(self.a, demo_graph('tenant-a'))
        self.contract = ExternalReceiptContract(self.gateway, self.a)
        self.receipt = {
            'source': 'P2', 'tenant_id': 'tenant-a', 'task_id': 'demo-b',
            'attempt_id': 'attempt-1', 'input_version': 'input-v1',
            'event_id': 'event-1', 'phase': 'SENT', 'status': 'SENT',
            'evidence_ref': 'receipt-evidence',
            'permission_scope': 'TEST_ONLY_NO_DISPATCH'}

    def tearDown(self):
        self.supervisor.close(); shutil.rmtree(self.root)

    def test_p2_p3_phase_mapping_is_validation_only(self):
        for source in ('P2', 'P3'):
            for phase in ('SENT', 'ACK', 'RESULT', 'ACCEPTANCE'):
                value = copy.deepcopy(self.receipt)
                value.update(source=source, phase=phase, status=phase)
                result = self.contract.normalize(value)
                self.assertEqual(result['mapping_state'],
                                 'VALIDATED_NOT_CONSUMED')
                self.assertEqual(result['production_adapter'],
                                 'NOT_IMPLEMENTED')

    def test_cross_tenant_and_wrong_version_reject_without_writes(self):
        before = self.supervisor.db.total_changes
        wrong = copy.deepcopy(self.receipt); wrong['tenant_id'] = 'tenant-b'
        with self.assertRaisesRegex(ValueError, 'CROSS_TENANT'):
            self.contract.normalize(wrong)
        wrong = copy.deepcopy(self.receipt); wrong['input_version'] = 'v-old'
        with self.assertRaisesRegex(ValueError, 'VERSION_MISMATCH'):
            self.contract.normalize(wrong)
        self.assertEqual(before, self.supervisor.db.total_changes)

    def test_raw_tenant_or_unknown_source_cannot_bypass_context(self):
        wrong = copy.deepcopy(self.receipt); wrong['source'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'P2_P3'):
            self.contract.normalize(wrong)
        other = ExternalReceiptContract(self.gateway, self.b)
        with self.assertRaisesRegex(ValueError, 'CROSS_TENANT'):
            other.normalize(self.receipt)


if __name__ == '__main__':
    unittest.main()
