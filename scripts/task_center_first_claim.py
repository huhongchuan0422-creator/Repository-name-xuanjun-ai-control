"""Scoped first-registration assembly; not an SSO, cookie or role issuer.

Only existing signed custody and protected DevelopmentHost bindings are used.
The Owner signature authenticates this exact first-registration contract only.
No OAuth scopes, admin principal, session, task or signing key is generated.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from task_supervisor import Supervisor,canonical
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from execution_policy_gateway import ExecutionPolicyGateway
from task_writer_fence import Fence
from task_center_mcp_development import DevelopmentHost,load_host
from task_center_mcp_claim import ClaimHost
from secure_file_input import read_owned_secret_file


class FirstClaimAssembly:
    def __init__(self,development_host):
        if (not isinstance(development_host,DevelopmentHost)
                or not isinstance(getattr(development_host,"claim_host",None),ClaimHost)):
            raise ValueError("EXISTING_SIGNED_REGISTRATION_HOST_REQUIRED")
        self.host=development_host
        self.claim=development_host.claim_host

    def principal_mapper(self,verified):
        # Map cryptographically verified developer, never username/role labels.
        rows=[b for b in self.host.bindings if b["phase"]=="EXECUTOR"
            and b["task_id"]==verified["task_id"]
            and b["contract_sha256"]==verified["contract_sha256"]
            and b["authority_identity"]==verified["developer"]]
        if len(rows)!=1:raise ValueError("EXACT_REGISTERED_DEVELOPER_MAPPING_REQUIRED")
        return {k:rows[0][k] for k in ("tenant_id","principal_id","project_id","role_id","role_version")}

    def run(self,db_path,authority_key,task_id,action,*,admission_check=None):
        if action not in ("register","claim","status"):
            raise ValueError("EXACT_FIRST_REGISTRATION_ACTION_REQUIRED")
        if not os.path.isfile(db_path):raise ValueError("EXISTING_CANONICAL_DATABASE_REQUIRED")
        # Formal verifier never adopts or promotes a TEST_ONLY ledger.
        s=Supervisor(db_path,development_identity_verifier=self.claim.verifier)
        try:
            g=GatewayKernel(s,TestTenantAuthority(authority_key))
            rows=[b for b in self.host.bindings if b["task_id"]==task_id and b["phase"]=="EXECUTOR"]
            if len(rows)!=1:raise ValueError("EXACT_REGISTERED_DEVELOPER_MAPPING_REQUIRED")
            binding=rows[0]
            identity={k:binding[k] for k in ("tenant_id","principal_id","project_id")}
            context=g.tenants.issue(identity["tenant_id"],identity["principal_id"])
            def project(expected):
                row=s.db.execute("SELECT project_id FROM gateway_task_metadata WHERE task_id=?",(task_id,)).fetchone()
                if row is None or row[0]!=expected:raise ValueError("CURRENT_CANONICAL_CLAIM_SCOPE_REQUIRED")
            def current():
                g.assert_task_context(context,task_id)
                project(identity["project_id"])
                contract=self.host.pinned_contract(task_id,identity["tenant_id"],project)
                task=s._task(task_id)
                if (task["spec_sha256"]!=contract["spec_sha256"]
                        or task["checkpoint_sha256"]!=contract["checkpoint_sha256"]
                        or task["entry"]!=contract["entry"]):
                    raise ValueError("CURRENT_CANONICAL_CLAIM_SCOPE_REQUIRED")
                custody=copy.deepcopy(self.claim.custody_provider(dict(identity),task_id))
                if not isinstance(custody,dict) or set(custody)!={"owner_grant","developer_credential","caller","lock_root","valid_until"}:
                    raise ValueError("EXISTING_REGISTRATION_CUSTODY_REQUIRED")
                pin=hashlib.sha256(canonical(contract).encode()).hexdigest()
                verified=self.claim.verifier.verify(custody["owner_grant"],custody["developer_credential"],task_id,pin)
                mapped=self.principal_mapper(verified)
                if (verified["owner"]!={"issuer":"owner-auth","subject":task["owner"]}
                        or verified["developer"]!=contract["developer"]
                        or any(mapped[k]!=identity[k] for k in identity)):
                    raise ValueError("CANONICAL_OWNER_CLAIM_REQUIRED")
                if admission_check is not None:admission_check()
                return contract,custody
            contract,custody=current()
            if action=="register":
                # Exact Owner-signed metadata, not a general admin capability.
                result=s.register_development_contract(task_id,contract,admission_check=current)
                result.update(task_id=task_id,action=action,browser_session_created=False,authority_created=False)
                return result
            registered=s.development_contract(task_id)
            if canonical(registered)!=canonical(contract):
                raise ValueError("CURRENT_CANONICAL_CLAIM_SCOPE_REQUIRED")
            if action=="claim":
                policy=ExecutionPolicyGateway(g,context)
                resources=g.canonical_resources(task_id)
                def claim_admission():
                    _,live=current()
                    # Custody replacing the original caller/grant cannot redirect
                    # an already-prepared claim at its storage-owner boundary.
                    if canonical(live)!=canonical(custody):raise ValueError("REGISTRATION_CUSTODY_CHANGED")
                    role=s.db.execute("SELECT phase,enabled,writer_allowed FROM role_templates WHERE tenant_id=? AND role_id=? AND version=?",
                        (identity["tenant_id"],binding["role_id"],binding["role_version"])).fetchone()
                    if role is None or tuple(role)!=("EXECUTOR",1,1):
                        raise ValueError("CURRENT_CLAIM_ROLE_ALLOWLIST_REQUIRED")
                    policy.require_dispatch_ready(task_id)
                    g.assert_start_allowed(context,task_id,resources)
                claim_admission()
                fence=Fence(s,custody["lock_root"])
                try:
                    fence.claim_first_development_writer(task_id,contract["entry"],custody["caller"],resources,
                        custody["valid_until"],custody["owner_grant"],custody["developer_credential"],admission_check=claim_admission)
                finally:fence.close()
            task=s._task(task_id)
            result={k:task[k] for k in ("task_id","state","attempt_id","lease_id","fence","epoch","authority_state")}
            result.update(action=action,claim_is_execution=False,browser_session_created=False,
                execution_started=task["started_at"] is not None)
            return result
        finally:s.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description="Original signed first-registration only; never SSO")
    parser.add_argument("--db",required=True)
    parser.add_argument("--mcp-development-config-file",required=True)
    parser.add_argument("--authority-key-file",required=True)
    parser.add_argument("--task-id",required=True)
    parser.add_argument("--action",choices=("register","claim","status"),required=True)
    args=parser.parse_args(argv)
    host=load_host(args.mcp_development_config_file)
    assembly=FirstClaimAssembly(host)
    key=read_owned_secret_file(args.authority_key_file,"AUTHORITY_KEY").rstrip(chr(13)+chr(10)).encode()
    result=assembly.run(args.db,key,args.task_id,args.action)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        code=str(exc)
        if not code or len(code)>160 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for c in code):
            code="FIRST_REGISTRATION_REJECTED"
        sys.stderr.write(code+chr(10));raise SystemExit(69)
