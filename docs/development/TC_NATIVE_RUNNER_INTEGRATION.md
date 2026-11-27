# Original fixed-plan native runner integration

The runner and its 12 integration tests were reconciled from original HEAD37c453f6 plus preserved patch23b4fed010d786fc3da5a1ad241f95c9c07512d9665cd8e9f6360c84a6910e0f into this independent candidate. Original dirty worktree is not changed. Before/after reverse/forward patch application verifies original blob IDs and runner base SHA0a83dc891d74f537b7c12faaa6e4c6610132c92c1c2cd0f2681ce078520639d6.

Runtime payload: scripts/native_sandbox_runner.py. It is not a process launcher available to HTTP/tool arguments. Original trusted bootstrap constructs BubblewrapNativeRunner(canonical_db_path, canonical_repository_root, original_contract_target_base_sha, approved_test_plan_sha256). Plan is plan_manifest(root, base), digest over that exact manifest; never substitute the portable HEAD for the real immutable task base or auto-approve its digest. Then supply that object and same approved digest to existing development_main native_runner/native_test_plan_sha256 or original launch native_runner_factory/native_test_plan_sha256. No DB/profile/grant/controller change.

Runtime requirements retained from original runner: /usr/bin/git, /usr/bin/bwrap with supported user namespaces/mount isolation, /usr/bin/python3.6, libseccomp.so.2 in isolated /usr, existing canonical DB and exact original Git base/support blobs. Network/subprocess/candidate filesystem writes are denied by original harness. Installer must check supported target runtime, not blindly copy a venv or downgrade protection. Formal host Python3.11/cryptography42.0.8 is separate from the runner child pinned by the old plan. Changing the child/plan requires a separately verified plan digest, not a string substitution at deployment.

The fixed harness audits import scaffolding and reachable pure validation functions before candidate import/call. Host PASSED requires audited + boundary probes + all host behavioral checks + exit0. Candidate test file is syntax-only, not trusted to return verdict. Unknown process effects use canonical intent/status/lookup without rerun. This source fix does not establish receipt trust for arbitrary runner objects.

Actual current verification:
- test_native_runner_source_audit: 7 passed. Runs the actual harness audit on healthy and forged candidates without executing candidate code; log records runner/harness/intake/test SHA. This is NOT bubblewrap isolation or a task execution receipt.
- First original full isolated integration method attempted, failed with FileNotFoundError before process creation: current sandbox lacks /usr/bin/bwrap and /usr/bin/python3.6. No mocked successful receipt, no skip or weakened assertion. Remaining 11 original integration cases must run unchanged in the original supported environment; the negative cases and full positive need same-file SHA-bound proof before activating this runner.

Tests in original supported target:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts:tests <host-python-with-original-lock> -m unittest test_native_sandbox_runner -v
Record candidate commit plus SHA256 of scripts/native_sandbox_runner.py/tests/test_native_sandbox_runner.py and full output. Do not use TEST_ONLY fixture authority as production registration.

Rollback: remove only this newly introduced runner payload/restore prior trusted injection, retaining unknown canonical intent and process facts for reconciliation. Never delete events or replay an execution with an unknown outcome. No service/config/DB mutation is performed by this source delivery.

Production identity remains a separate unsatisfied dependency: this runner supplies neither verify_login/current_provenance nor principal mapping/contract signing. Existing development_identity_adapter supports signed owner registration for one canonical developer contract, not an SSO login protocol. Existing load_host/claim_registration consumes protected contract/public-key/custody references; it cannot manufacture them. Real references/issuer custody must come through the original auth/runtime responsibility chain, not a generated key or chat identity.
