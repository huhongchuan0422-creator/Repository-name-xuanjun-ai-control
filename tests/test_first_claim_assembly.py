"""Real signature/canonical APIs, synthetic custody; never live identity proof."""
import base64
import contextlib
import copy
import io
import json
import sqlite3
import unittest
from pathlib import Path
from task_center_first_claim import FirstClaimAssembly,main
from task_center_mcp_development import DevelopmentHost
from task_supervisor import Supervisor
import test_mcp_canonical_claim_http as fixture

class FirstClaimAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ClaimHTTPTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.f.s.db.execute("DELETE FROM events WHERE kind='DEVELOPMENT_CONTRACT'");self.f.s.db.commit()
        rows=copy.deepcopy(self.f.host.bindings)
        for policy in self.f.contract["trusted_reviewers"]:
            b=dict(rows[0],principal_id=policy["subject"],role_id=policy["subject"],phase="REVIEWER",
                review_kind=policy["role"],authority_identity={k:policy[k] for k in ("issuer","subject")},
                actions=["task_development_review","task_development_status"],executor_profile=None)
            rows.append(b)
        self.host=DevelopmentHost(rows,contract_provider=lambda task:self.f.contract,native_source_provider=lambda *args:None)
        self.host.claim_host=self.f.host
        self.assembly=FirstClaimAssembly(self.host)
    def run_action(self,action,**kw):return self.assembly.run(self.f.path,fixture.KEY,"demo-b",action,**kw)
    def count(self,kind):return self.f.s.db.execute("SELECT count(*) FROM events WHERE kind=?",(kind,)).fetchone()[0]
    def test_register_claim_status_without_browser_identity_or_minted_scope(self):
        before=self.f.s.db.execute("SELECT count(*) FROM task_center_sessions").fetchone()[0]
        registered=self.run_action("register");self.assertFalse(registered["duplicate"])
        self.assertTrue(self.run_action("register")["duplicate"])
        claimed=self.run_action("claim");self.assertEqual(claimed["state"],"RECEIVED")
        self.assertFalse(claimed["execution_started"]);self.assertFalse(claimed["browser_session_created"])
        status=self.run_action("status")
        for k in ("state","attempt_id","lease_id","fence","epoch","authority_state"):
            self.assertEqual(claimed[k],status[k])
        with self.assertRaises(ValueError):self.run_action("claim")
        self.assertEqual(self.f.s.db.execute("SELECT count(*) FROM resource_claims").fetchone()[0],1)
        self.assertEqual(self.f.s.db.execute("SELECT count(*) FROM task_center_sessions").fetchone()[0],before)
    def test_forged_owner_signature_cannot_register_or_claim(self):
        self.f.grant["signature"]=base64.b64encode(b"0"*64).decode()
        with self.assertRaisesRegex(ValueError,"OWNER_GRANT_SIGNATURE_INVALID"):self.run_action("register")
        self.assertEqual(self.count("DEVELOPMENT_CONTRACT"),0)
        self.assertEqual(self.f.s._task("demo-b")["authority_state"],"NONE")
    def test_contract_or_mapper_drift_is_not_an_authority(self):
        self.host.bindings[0]["authority_identity"]={"issuer":"native","subject":"intruder"}
        with self.assertRaisesRegex(ValueError,"CANONICAL_DEVELOPMENT_IDENTITY_REQUIRED"):self.run_action("register")
        self.assertEqual(self.count("DEVELOPMENT_CONTRACT"),0)
    def test_register_final_transaction_guard_rolls_back(self):
        calls=[]
        def live():
            calls.append(1)
            if len(calls)==2:raise ValueError("FIXTURE_REVOKED_AT_STORAGE_OWNER")
        with self.assertRaisesRegex(ValueError,"FIXTURE_REVOKED_AT_STORAGE_OWNER"):
            self.run_action("register",admission_check=live)
        self.assertEqual(self.count("DEVELOPMENT_CONTRACT"),0)
        self.assertEqual(len(calls),2)
    def test_claim_final_guard_rolls_back_lease_and_resource_claims(self):
        self.run_action("register");calls=[]
        def live():
            calls.append(1)
            if len(calls)==3:raise ValueError("FIXTURE_REVOKED_AT_STORAGE_OWNER")
        with self.assertRaisesRegex(ValueError,"FIXTURE_REVOKED_AT_STORAGE_OWNER"):
            self.run_action("claim",admission_check=live)
        self.assertEqual(self.f.s._task("demo-b")["authority_state"],"NONE")
        self.assertEqual(self.f.s.db.execute("SELECT count(*) FROM resource_claims").fetchone()[0],0)
    def test_test_only_database_is_never_adopted_or_promoted(self):
        path=str(self.f.root/"test-only.sqlite");s=Supervisor(path);s.close()
        with self.assertRaisesRegex(ValueError,"AUTHORITY_RUNTIME_PROFILE_MISMATCH"):
            self.assembly.run(path,fixture.KEY,"demo-b","register")
        with sqlite3.connect(path) as db:self.assertEqual(db.execute("SELECT profile FROM authority_runtime_profile").fetchone()[0],"TEST_ONLY")
    def test_protected_config_cli_consumes_exact_original_references(self):
        from cryptography.hazmat.primitives import serialization
        def file(name,raw):
            p=self.f.root/name;p.write_bytes(raw);p.chmod(0o600);return str(p)
        public=file("owner.pem",self.f.private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        custody=file("custody.json",json.dumps({"demo-b":{"tenant_id":"tenant-a","principal_id":"developer","project_id":"project-mcp","custody":self.f.custody}}).encode())
        contract=file("contract.json",json.dumps({"demo-b":self.f.contract}).encode())
        cfg=file("development.json",json.dumps(dict(schema_version=1,enabled=True,bindings=self.host.bindings,
            review_keyring_file=None,writer_context_file=None,native_source_file=file("native.json",b"{}"),contract_file=contract,
            claim_registration=dict(owner_public_key_file=public,custody_file=custody))).encode())
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--db",self.f.path,"--mcp-development-config-file",cfg,
                "--authority-key-file",file("authority",fixture.KEY),"--task-id","demo-b","--action","register"]),0)
        result=json.loads(output.getvalue());self.assertFalse(result["browser_session_created"])
        self.assertNotIn("signature",output.getvalue());self.assertEqual(self.count("DEVELOPMENT_CONTRACT"),1)

    def test_custody_caller_replacement_cannot_redirect_claim(self):
        self.run_action("register");calls=[]
        def custody(identity,task):
            calls.append(1)
            if len(calls)==2:self.f.custody["caller"]["run_id"]="replaced-run"
            return self.f.custody
        self.f.host.custody_provider=custody
        with self.assertRaisesRegex(ValueError,"REGISTRATION_CUSTODY_CHANGED"):self.run_action("claim")
        self.assertEqual(self.f.s._task("demo-b")["authority_state"],"NONE")
    def test_valid_signature_for_different_canonical_owner_is_not_authority(self):
        self.f.s.db.execute("UPDATE tasks SET owner='another-owner' WHERE task_id='demo-b'");self.f.s.db.commit()
        with self.assertRaisesRegex(ValueError,"CANONICAL_OWNER_CLAIM_REQUIRED"):self.run_action("register")
        self.assertEqual(self.count("DEVELOPMENT_CONTRACT"),0)

if __name__=="__main__":unittest.main()
