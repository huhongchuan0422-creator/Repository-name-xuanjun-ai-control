"""Actual temporary canonical SQLite composition; all sessions are fixtures."""
import contextlib
import copy
import unittest
import test_owner_access_gate as fixture
from owner_controller_adapter import OwnerFoundationController


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.context = fixture.OwnerAccessIntegrationTests(methodName='runTest')
        self.context.setUp()
        self.closed = False
        self.requested = []

    def tearDown(self):
        self.context.tearDown()

    @contextlib.contextmanager
    def supplier(self, task_id):
        self.requested.append(task_id)
        try:
            yield self.context.arguments
        finally:
            self.closed = True

    def test_actual_read_and_context_cleanup(self):
        controller = OwnerFoundationController(self.supplier, lambda binding: binding['task_id'] == 'target')
        result = controller.read('target')
        self.assertEqual(len(result['views']), 7)
        self.assertFalse(result['execution_granted'])
        self.assertEqual(self.requested, ['target'])
        self.assertTrue(self.closed)

    def test_supplier_cannot_rebind_requested_task(self):
        controller = OwnerFoundationController(self.supplier, lambda _: True)
        with self.assertRaisesRegex(ValueError, 'CONTROLLER_TASK_BINDING_MISMATCH'):
            controller.read('other')
        self.assertTrue(self.closed)

    def test_denial_cleans_context_without_sql(self):
        statements = []
        self.context.fixture.context.reader.set_trace_callback(statements.append)
        controller = OwnerFoundationController(self.supplier, lambda _: False)
        with self.assertRaisesRegex(ValueError, 'OWNER_READ_ACCESS_DENIED'):
            controller.read('target')
        self.assertEqual(statements, [])
        self.assertTrue(self.closed)

    def test_request_cannot_supply_dependencies(self):
        controller = OwnerFoundationController(self.supplier, lambda _: True)
        with self.assertRaises(TypeError):
            controller.read('target', db='client-db')
        with self.assertRaises(ValueError):
            controller.read({'task_id': 'target', 'authenticated': True})
        self.assertEqual(self.requested, [])


if __name__ == '__main__':
    unittest.main()
