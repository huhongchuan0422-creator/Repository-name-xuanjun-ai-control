import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch
import native_pipeline_runtime as runtime
import p2_service_context_preflight as service

class ServicePreflightAckTests(unittest.TestCase):
    def setUp(self):
        self.controller=Mock()
        self.ack={k:True for k in ('ready','canonical_existing','isolation_enforced','outbox_existing')}
        self.controller.preflight.return_value=self.ack
        self.runtime=runtime.NativePipelineRuntime(self.controller)
        self.argv=['--config','/fixture/config','--native-controller','/fixture/controller','--native-controller-sha256','a'*64]
    def test_returns_validated_controller_ack(self):
        self.assertIs(self.runtime.preflight({}),self.ack)
        self.controller.preflight.assert_called_once_with({})
        for name in ('admit','launch','notify','report','stop'):
            getattr(self.controller,name).assert_not_called()
    def test_actual_service_main_accepts_validated_ack(self):
        out=io.StringIO()
        with patch.object(service.pwd,'getpwnam',return_value=Mock(pw_uid=1003)),patch.object(service.os,'geteuid',return_value=1003),patch.object(service,'load_config',return_value={'scope':'fixture'}),patch.object(service,'load_reviewed_controller',return_value=self.runtime),contextlib.redirect_stdout(out):
            self.assertEqual(service.main(self.argv),0)
        self.assertEqual(json.loads(out.getvalue()),{'state':'P2_SERVICE_CONTEXT_PREFLIGHT_PASS','model_calls':0,'launch_performed':False,'dispatcher_uid':1003})
        self.controller.launch.assert_not_called();self.controller.notify.assert_not_called()
    def test_all_required_flags_remain_literal_true(self):
        for flag in self.ack:
            for rejected in (False,None,1,'true'):
                value=dict(self.ack);value[flag]=rejected;self.controller.preflight.return_value=value
                with self.assertRaises(runtime.NativeContractError):self.runtime.preflight({})
    def test_missing_flags_rejected(self):
        for flag in self.ack:
            value=dict(self.ack);del value[flag];self.controller.preflight.return_value=value
            with self.assertRaises(runtime.NativeContractError):self.runtime.preflight({})
    def test_nondict_rejected(self):
        for value in (None,True,[], 'ready'):
            self.controller.preflight.return_value=value
            with self.assertRaises(runtime.NativeContractError):self.runtime.preflight({})
    def test_controller_failure_is_not_success(self):
        self.controller.preflight.side_effect=RuntimeError('fixture failure')
        with self.assertRaises(RuntimeError):self.runtime.preflight({})
    def test_wrong_service_identity_still_rejected_before_load(self):
        with patch.object(service.pwd,'getpwnam',return_value=Mock(pw_uid=1003)),patch.object(service.os,'geteuid',return_value=1004),patch.object(service,'load_config') as load:
            with self.assertRaisesRegex(SystemExit,'HOLD_DISPATCHER_UID'):service.main(self.argv)
            load.assert_not_called()

if __name__=='__main__':unittest.main()
