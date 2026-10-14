# Phase authorization and outcome matrix

Every phase requires a new exact signed authorization and predecessor receipts.
This package authorizes none of them.

| Phase | Exact scope after approval | Success | Failure / timeout / partial / unknown | Restart handling |
|---|---|---|---|---|
| A dependency closure | read-only evidence only | persistent launcher, DB route, credentials, triggers and 95-state independently closed | HOLD; preserve UNKNOWN/DENY | resume from signed evidence checkpoint |
| B isolated install | exact manifest to dedicated identity/directories; service disabled; deny-all egress | hashes/self-check/unit validation pass; protected services unchanged | uninstall only disabled code/unit; preserve state/evidence | no service start; idempotent check before any retry |
| C read-only/Shadow | dedicated read-only credential, GET-only transport, pinned-IP drop-in, accepted thresholds | continuous threshold window and restart reconciliation pass | lock/stop candidate, revoke read-only route; no Writer impact | reconcile evidence, then restart a new authorized observation window |
| D fence/snapshot | pause exact four timers, drain, final WAL-aware snapshot, assign one DB/Writer epoch | one authoritative DB, one Writer, full reconciliation | Korea locked first; capture process/DB/exchange state; no blind retry | new authorization only after unknowns resolved |
| E Canary/acceptance | Owner-approved bounded single Writer/Canary | guard, protection, exchange and independent receipts all pass | immediate Korea lock; revoke write authority; reconcile unknown fills/orders | no automatic replay or second order |
| F Yibi retirement | only after independent Binance acceptance | exact archive/retirement receipt | remain stopped only if retirement command completed and verified; unknown is investigated | never restart after confirmed permanent retirement |
| G Tokyo retirement | final separate Gate after every remaining production dependency is safe | observation window and rollback evidence pass | Tokyo remains available | no retirement retry without state inspection |

`SUCCESS` requires the expected post-state, not exit code alone. `FAILED` means a
known rejected/no-change result. `PARTIAL` and `UNKNOWN` are blocking states. A
timeout is always `UNKNOWN` until process, transaction, session, database and exchange
side effects are independently measured.
