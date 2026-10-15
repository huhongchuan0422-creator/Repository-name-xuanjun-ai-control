# Repository execution rules

Before starting or resuming development, review or handoff, read
[开发执行与审核规则](docs/DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md),
including version **2026.10.15.1**. Record its version and the exact task baseline
in the original task/PR. This is the single rule source, not a new task queue.

- Reuse existing code, approvals for unchanged scope, original PR and canonical ledger.
- One writer per task; verify handoff before taking ownership.
- Deliver complete agreed batches, including wiring, failure paths, tests and registration.
- Progress reports do not end authorized work. Continue eligible work; record real blockers.
- Independently audit the full affected chain and artifacts; report findings together.
- Bind evidence to exact versions; never turn UNKNOWN/skipped/not run into PASS.
- Use the PR delivery contract template. Mechanical checks are not independent approval.
- Do not merge/deploy/change production authority merely because checks pass.
- Preserve unfinished changes and evidence during handoff; never claim unattended work without proof.
