# P2 remaining measured deployment gates

Already evidenced:
- Existing canonical ledger/CAS is reused; no second task DB/queue.
- Exact OpenClaw sandbox runtime is bound to canonical run/session/unit/cgroup and rechecked before every tool call.
- Container-side source namespace attestation is bound into admission and rechecked before dispatch.
- Receipt-less `LAUNCH_INTENT` is UNKNOWN/HOLD and never physically replayed.
- Gateway native socket role has process-chain identity checks rather than shared-UID-only trust.
- UK Gateway process identity and Python 3.6.8 are verified by zero-model self-hosted evidence.

Still required before installation:
1. Complete the currently queued UK dependency/unit/host-facts verify-only runs on the latest immutable source.
2. Freeze one candidate artifact with provenance and SHA256SUMS and record its artifact ID + archive hash.
3. Run independent QA and Security against that exact artifact; author self-test is not approval.
4. Run Release gate against the same artifact and reject any byte drift.
5. Produce reviewed verify-only, install and rollback commands from the frozen package; no guessed root command.
6. Owner executes the reviewed installation once on UK; then run E2E and fault injection.
7. Update the existing dashboard in its current layout with exact source/artifact/runtime/gate status.

P2_INSTALL remains HOLD until all seven are satisfied. Old `f998...` remains effect-unknown and must not be replayed.
