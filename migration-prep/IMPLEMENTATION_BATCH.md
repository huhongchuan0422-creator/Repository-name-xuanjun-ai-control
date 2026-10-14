# Implementation batch after preparation audit

Task: `TOKYO_KOREA_IMPLEMENTATION_AFTER_PREPARATION_AUDIT_6168878707`

This batch extends exact reviewed tree `beb05bf8eb1cfa64ae436464d4fdf69e6b98cf5f`.
It does not modify the accepted S1–S5 semantics. Production remains HOLD.

## Implemented candidates

### GET-only reconciliation adapter

`readonly_reconciliation_adapter.py` opens the production business database using
SQLite URI `mode=ro&immutable=1` plus `PRAGMA query_only=ON`, selects the latest
snapshot group, parses persisted exchange payloads, applies open/algo/protective
class filters, reads all eight sidecar classes, and detects unresolved anomalies,
unknown attempts and in-flight requests. It verifies the DB byte identity before and
after collection. Output uses exclusive-create, mode-0600 files under a mode-0700
run directory outside the business DB tree.

`FixtureGetOnlyPager` enforces all ten surfaces, cursor continuity, terminal page,
page/count bounds and exact BTCUSDT/ETHUSDT/SOLUSDT coverage. This batch injects
fixtures only. The module contains no network client, credential loader, business-DB
write, freeze, schedule or service control.

### Restricted executor

`restricted_executor.py` validates exact host/path/unit/action sets, candidate hash,
expiry, authority ID, exact authorized-request hash and a unique single-use nonce.
SQLite FULL/WAL transactions record INTENT before the injected runner and terminal
SUCCEEDED/FAILED/UNKNOWN results. Timeout, worker failure, partial success or unknown
outcome becomes UNKNOWN with inspection required and blind retry forbidden.

The cgroup/systemd confinement output is data only (`DynamicUser`, strict filesystem,
no privileges, control-group kill, deadline). The module has no sudo, SSH, systemd,
root or host transport. `restricted-executor-allowlist.json` is the exact candidate
scope; novel/PostgreSQL/Redis are forbidden.

### 95 Writer paths

`writer-coverage-public.json` contains all 95 stable IDs, source/path hashes, classes,
static roles and policies without exposing private paths. Every record covers dynamic
import, direct/manual launch and protection behavior. Because the administrator-wide
trigger and credential reachability evidence is incomplete, all 95 remain UNKNOWN
and the candidate enforcement is DENY. The runtime evaluator hash-binds the path and
source; a future known Writer can only reach `CONTRACT_VALID_NOT_AUTHORIZED` after
external epoch, scoped credential and scheduler-gate evidence. Protection paths allow
only risk-exit actions and are still fenced.

This is an actual fail-closed launcher/import policy candidate, but it is not yet a
global production fence: complete entrypoint integration, scoped credentials and the
administrator-wide trigger inventory remain required.

### Korea deployment candidate

`korea/` packages an independent Python 3.11 stdlib-only runtime, dedicated identity
and directories, protected SecretRef names, hardened systemd unit, loopback ports,
Shadow/Canary standards and Korea-first rollback. It does not reuse Yibi's venv or
include a Trading credential.

An IP firewall cannot prove a method inside TLS. The package combines a root-owned
destination allowlist prerequisite with `get_only_policy.py`, which enforces exact
HTTPS host, GET method and allowlisted endpoint path at the application layer.
Neither layer was installed or exercised against Binance in this batch.

## Remaining release blockers

See `HUMAN_ACTIONS_REQUIRED.md`. Additionally, live GET-only adapter binding,
independent signed manifest, all UNKNOWN Writer routes, root egress installation,
real Shadow duration, canary and Korea-first rollback evidence remain NOT RUN.

```text
PRODUCTION_MIGRATION_RELEASE=HOLD
PRODUCTION_EXECUTION_AUTHORIZED=NO
BINANCE_CALLED=NO
PRODUCTION_DEPLOYMENT=NO
RUNNER_OR_YIBI_MUTATION=NO
WRITER_STARTED=NO
```
