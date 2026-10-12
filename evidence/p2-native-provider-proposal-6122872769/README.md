# P2 OpenClaw native provider proposal evidence

Status: SOURCE_PROPOSAL_ONLY / NOT_INSTALLED / NOT_ACTIVATED / NOT_RELEASE_ADMITTED.

This evidence is part of parent task `XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1` and PR17. It does not create a second queue, grant a writer lease, or change the UK runtime.

## Exact source basis

- Recovered source commit: `3888f859eeb440a63602b2e9822823447ea8294c`
- Recovered exact tree: `686786e69e4397b5834bac631a57545fa954a829`
- Recovery artifact: `11740719445`
- Recovery artifact ZIP SHA256: `39a6dd5170f0e660e423d1eee11894fbdb6d7e9729bcc8a62ddbf7f7ffe240c3`
- Local proposal commit: `98733eb78919e5d8a11805e9c8e4e78d31678aac`
- Local proposal tree: `5fc2b1652aa1c14224de045c7cfe4d535851b64c`

## Decision bound

Source receipt: PR17 comment `6122872769`.

The installed OpenClaw 2026.9.9 boundary exposes only `agent`, `agent.wait`, `sessions.list`, and `sessions.get`. It does not expose `sessions.spawn`, `subagents.list`, or NativeChildAdapter's internal names. The proposed `xuanjun.execution.start` and `xuanjun.execution.inspect` controller extension is not installed.

Accordingly the provider is inert by default and fails before any RPC unless both proposed controller methods are explicitly present and activation has been independently reviewed. Unknown start/status/report outcomes remain UNKNOWN/HOLD and are not replayed.

## Isolated verification

Executed with `PYTHONDONTWRITEBYTECODE=1`:

- Provider contract: 11/11 PASS
- Full recovered stage1 regression: 328/328 PASS
- Git diff whitespace check: PASS

This is deterministic fake-Gateway/source verification only. It is not UK runtime evidence, a package, an install plan, authentication proof, or independent QA/Security/Release approval.
