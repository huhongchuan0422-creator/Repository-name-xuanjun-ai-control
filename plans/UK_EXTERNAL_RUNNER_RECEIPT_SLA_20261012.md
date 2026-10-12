# UK Runner event receipt SLA (source proposal)

Status: source-only proposal; not installed, merged or proof of P2/P3.

Every authorized `SUBMITTED` marker on PR #17 starts exactly one bounded GitHub-hosted, inference-free monitor. There is no schedule, periodic automation, model polling or dependency on the UK self-hosted Runner. The monitor accepts the Owner's exact task marker, then reads only trusted receipt identities for the same attempt.

| Deadline from `SUBMITTED` | Required receipt | Missing-receipt result |
|---|---|---|
| 2 minutes | `RECEIVED` | `RECEIVE_TIMEOUT_2M` |
| 5 minutes | `STARTED` | `START_TIMEOUT_5M` |
| every 10 minutes after start | `PROGRESS`, `COMPLETE`, `FAIL`, or `HOLD` | `PROGRESS_TIMEOUT_10M` |
| 60 minutes | terminal `COMPLETE`, `FAIL`, or `HOLD` | `TERMINAL_TIMEOUT_60M`; monitor stops |

Alerts are deterministic, idempotent per attempt+kind, include `::SKIP_COMPLETION::`, and never start/restart work. A timeout means actual UK state is `UNKNOWN`; reconcile the canonical ledger and side effects before any restart. Terminal success/failure/HOLD must still be emitted by the actual executor and bind task/spec/run/session/workdir/lease/fence/epoch/artifact evidence.

The workflow is event-started and bounded. It is not the UK intake, does not grant root/systemd/cgroup/credential/production authority, and cannot make P2 or P3 pass. It only prevents silence when the UK Runner is absent or stalled.
