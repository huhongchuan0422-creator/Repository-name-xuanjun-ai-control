# Independent QA review — FAIL / installation HOLD

Reviewed exact archive SHA256 `456ae23aa52e300021c9fb889df84d8eba34965769ce868e5ee6e43c29911a13`, source commit `f840b2e98724a9e5b940f73606ee0687b6ba98c8`, tree `2810ad1e2c596796469c75999f8d1d62ecb74d2d`, manifest SHA256 `4f77c7f11be7a3c96ecbd8c30c239189876a42a47e9d16cec0f875b8df3b16aa`.

## Verified

- All 51 manifest-listed runtime files exist and match hashes. Provenance runtime inventory equals manifest exactly. The 54 archive members are these 51 files plus manifest, verifier and provenance; no undeclared archive members.
- Statically reviewed pure archive verifier executed successfully with expected archive, commit and tree identities.
- All 35 Python files pass Python 3.6 grammar parsing and data-only compilation under local Python 3.12. This is grammar evidence, not Python 3.6 runtime execution or UK acceptance.
- Install, verify-only and rollback entrypoints exist. Rollback has explicit fencing, stopping new services and restoring provisioning/legacy files without restarting old writer. No installer or rollback operation executed.

## Blocking findings

1. **Production native wiring absent.** `stage1/development_service.py:21,361–366` imports and instantiates `CodexAppServerWorker`. No shipped module imports or instantiates `NativeChildAdapter` or `OpenClawGatewayNativeProvider`. `deploy/dispatcher.example.json` still specifies Codex executable/home/worker. Including adapter bytes in manifest fixes package omission but does not switch actual production execution to the required native provider.
2. **Provider receipt fabricates proof from request.** `stage1/native_child_adapter.py:126–143` obtains only session registry identity, then copies requested executor/epoch/commit/tree into `execution_identity` and sets an invented gateway-session unit `active=True`. It does not inspect actual workdir, artifact checkout, host unit/process/cgroup or lease/fence/epoch enforcement. Security-authorized pure fake-runner reproducer confirms a sparse registry containing only key/session/run IDs is accepted and falsely gains all requested artifact identity claims. A lease-guarded local checkpoint does not prove the remote executor honors that lease.
3. **Missing native observation incorrectly claims stopped process.** `stage1/native_child_adapter.py:150–164` treats absent session or unrecognized status as lost, with `process_alive=False` and `unit_active=False`. Fake-runner reproducer confirms an empty registry yields these false values despite no process evidence. Required behavior is unknown/HOLD until actual sole-writer and side-effect reconciliation establishes stop.
4. **Terminal recovery is model prose, not durable trusted report.** `stage1/native_child_adapter.py:169–186` returns the last assistant JSON message. Exact echoed identifiers cannot establish actual production effects, independently observed host status, or authoritative persisted report provenance.

## Scope and limitations

No host/network/Gateway calls, root actions, installation, service mutation, canonical ledger or lease/fence writes occurred. Approved execution was limited to the statically pure archive verifier and fake-runner provider negative tests inside an isolated temporary directory. Frozen archive contains no tests; upstream focused/stage1 test counts are not independently executed artifact tests here. Live Gateway parameter schema/model enforcement, installation plan, verify-only on the UK host, rollback exercise and production E2E remain unverified.

## Minimal next acceptance criteria

Wire the approved native adapter into the actual dispatcher with explicit fail-closed configuration. Obtain execution identity and stop/effect evidence from the trusted controller rather than synthesizing them, preserve UNKNOWN on absent observations, and use an authoritative durable report boundary. Re-freeze the minimal modified package and run independent QA/Security/Release against that exact archive before installation. Existing hash integrity PASS remains valid only for this reviewed archive and does not authorize installation.
