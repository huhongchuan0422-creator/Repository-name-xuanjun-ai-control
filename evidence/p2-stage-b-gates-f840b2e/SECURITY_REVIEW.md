# Independent Security review — exact P2 frozen package

Decision: **FAIL for installation/release admission**. Safe isolated static review and fake-runner tests are allowed. UK execution, installation and production E2E were not performed.

Reviewed identity: commit `f840b2e98724a9e5b940f73606ee0687b6ba98c8`, tree `2810ad1e2c596796469c75999f8d1d62ecb74d2d`, archive SHA256 `456ae23aa52e300021c9fb889df84d8eba34965769ce868e5ee6e43c29911a13`, manifest SHA256 `4f77c7f11be7a3c96ecbd8c30c239189876a42a47e9d16cec0f875b8df3b16aa`. Source-retention provenance lists six changed paths relative to retained 3888; no code was deleted by this review. Historical source retention is an export provenance claim, not independently reconstructed original Git ancestry.

## Blocking findings

1. **P1 — requested identity promoted to attested execution proof.** `stage1/native_child_adapter.py:126–143` verifies only a session row/id and constructs `execution_identity.epoch/git_commit/git_tree` from the caller binding, plus `execution_unit.active=True` unconditionally. No actual isolated unit/cgroup, workdir, checked-out bytes, enforced lease/fence/epoch or budget is inspected. The adapter accepts these manufactured fields as STARTED at lines 250–278. A pure fake-runner reproduction supplied an already `done` session row and obtained `active=True` with an unattested epoch. This is a code-level violation, not merely missing host acceptance evidence.

2. **P1 — missing or unrecognized registry state becomes proof of no live execution.** `native_child_adapter.py:150–163` maps missing rows/unknown statuses to `lost`, `process_alive=False`, `unit_active=False`; `supervise:361–364` then records `RESULT_MISSING` with `effects='none'`. Registry absence (including list limit 200, line 71) cannot prove process/unit death or absence of external effects. Unknown must remain unknown until authoritative controller reconciliation.

3. **P1 — model text can terminate an execution.** `native_child_adapter.py:169–186` retrieves arbitrary assistant JSON from a conversation, without an authoritative durable result receipt or run-bound execution attestation. `supervise:351–360` accepts matching echoed fields and moves to result delivery without requiring the writer to be terminal/stopped. Conversation text is not an independent result/effects proof. The task prompt itself instructs the model to echo requested identities at lines 85–93.

4. **Release prerequisite — provider is shipped but not runtime-wired.** Package-wide search finds `NativeChildAdapter` and `OpenClawGatewayNativeProvider` only in their defining file. `stage1/development_service.py:337–367` still constructs `CodexAppServerWorker` directly. No concrete native notifier/recipient implementation or native runtime entry wiring is supplied. Inclusion in the manifest fixes packaging omission but does not install an operational native provider. Actual RPC parameter/response contracts for `cwd`, provider/model and session metadata have not been verified by this static review; supported method names alone do not establish these contracts.

## Positive checks and scope

- Archive digest, manifest digest and every manifest-listed payload hash passed independent verification; archive entries had no symlink/hardlink or path traversal.
- All shipped Python files passed in-memory syntax compilation without executing their top-level logic.
- Provider command uses argv, not a shell; only installed method names `agent`, `agent.wait`, `sessions.list`, `sessions.get` appear in this provider. No proposed `xuanjun.execution.start/inspect` is represented as installed.
- Installer retains root-protected reviewed-plan digest, exclusive lock, staged journal and explicit rollback flow; no installer was executed. `scripts/uk-p2-install.py` and `p2_fixed_host_runtime.py` can mutate `/etc`, activation/ledger files and systemd if invoked; running their operation modes is outside this review. Even `verify-only` acquires/creates its installation lock and instantiates stores, so it must not be treated as a side-effect-free local test.
- This is a bounded source review with concrete blocking defects, not an exhaustive proof of all retained modules. Existing earlier approvals do not transfer to this archive. No OAuth/credential contents were accessed; no model/API/host/lease/fence writes occurred. A Python import for the pure injected-runner reproduction may create a local `__pycache__` in the unpacked review copy; the immutable archive bytes were not modified.

Minimal safe follow-up: keep this package frozen and HOLD; correct the proof boundary so native identity/state/results come from authoritative controller observations, preserve UNKNOWN on unproved effects, connect the real runtime/notifier, then freeze a new exact artifact and rerun independent gates. Do not substitute echoed bindings or assistant JSON for those guarantees.
