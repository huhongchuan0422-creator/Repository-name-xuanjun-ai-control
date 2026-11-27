"""Native canonical registration fixtures; no production source or signed grant."""
import copy
import hashlib
import unittest
from task_supervisor import Supervisor,canonical
import test_contract_registration_delta as registration

class NativeContractRegistration(unittest.TestCase):
    def setUp(self):
        self.f=registration.RegistrationDelta();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.contract=copy.deepcopy(self.f.contract)
        self.contract["allowed_files"]=["scripts/development_entry_intake.py","tests/test_development_entry_intake.py"]
        self.f.write(self.f.contract_path,{"demo-b":self.contract})
        pin=hashlib.sha256(canonical(self.contract).encode()).hexdigest()
        for b in self.f.host.bindings:
            b["contract_sha256"]=pin
            if b["phase"]=="EXECUTOR":b["executor_profile"]=None
        self.f.host.native_source_provider=lambda *args: (_ for _ in ()).throw(AssertionError("registration must not fetch a candidate"))
    def test_pinned_native_contract_registers_without_local_profile_or_runner(self):
        status,result=self.f.post(self.f.request())
        self.assertEqual(status,200,result);self.assertFalse(result["duplicate"])
        status,result=self.f.post(self.f.request())
        self.assertEqual(status,200,result);self.assertTrue(result["duplicate"])
        s=Supervisor(self.f.f.db)
        try:self.assertEqual(s.development_contract("demo-b"),self.contract)
        finally:s.close()
    def test_missing_both_execution_modes_is_still_rejected(self):
        self.f.host.native_source_provider=None
        status,result=self.f.post(self.f.request())
        self.assertEqual((status,result["detail"]),(400,"HOST_EXECUTOR_PROFILE_REQUIRED"))
    def test_contract_drift_does_not_use_native_mode_to_bypass_pin(self):
        changed=dict(self.contract,target_base_sha="d"*40)
        self.f.write(self.f.contract_path,{"demo-b":changed})
        status,result=self.f.post(self.f.request())
        self.assertEqual((status,result["detail"]),(400,"CURRENT_PINNED_DEVELOPMENT_SCOPE_REQUIRED"))

if __name__=="__main__":unittest.main()
