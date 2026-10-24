# Implementation batch after preparation audit

Task: `TOKYO_KOREA_C1_C6_REMEDIATION_6169446383`

This batch extends exact reviewed HEAD `1929506900e5cc9e0e1eb3d56510c4638a3d57d1`
and tree `306d609af5a414c9447c8e2494258ed817a896d9`.
It does not modify the accepted S1–S5 semantics. Production remains HOLD.

## Implemented candidates

### GET-only reconciliation adapter

`readonly_reconciliation_adapter.py` no longer uses `immutable=1` on the live DB.
It opens the source with `mode=ro`, captures a coherent SQLite backup into the
separate evidence run, and uses immutable mode only on that closed copy. Main,
WAL and SHM identities are recorded before/after capture and after collection;
any change blocks final-snapshot admission. A concurrent-WAL commit counterexample
proves the captured copy sees the committed row rather than silently reading a stale
main file.

Every local read is bound to an exact `account_id`, `snapshot_id`, independent
capture time and max age. Every fixture page carries the same bindings and exact
BTCUSDT/ETHUSDT/SOLUSDT coverage. Algo and protective orders require dedicated
authoritative tables and are never inferred from ordinary order rows.

`FixtureGetOnlyPager` records capture timing and explicit simulated call receipts.
Its result is only `PASS_FIXTURE_ONLY`; `authenticated_get_receipts_verified=false`,
`final_snapshot_live_admissible=false`, and `binance_called=false`. Independent
current time, exchange server time, surface skew and capture deadline are checked.

### Restricted executor

`restricted_executor.py` accepts only a canonical policy file verified against an
independently stored Ed25519 public trust anchor and detached signature. Caller-
supplied policy dictionaries are rejected. Hashes are lowercase hex-64, runtime host
and OS identity are read locally, and allowlisted paths must be canonical, existing,
owner-bound, non-symlink and non-group/other-writable.

The request remains bound to exact host/path/unit/action, candidate hash, expiry,
authorized-request hash and a unique single-use nonce.
SQLite FULL/WAL transactions record INTENT before the injected runner and terminal
SUCCEEDED/FAILED/UNKNOWN results. Timeout, worker failure, partial success or unknown
outcome becomes UNKNOWN with inspection required and blind retry forbidden.

Runner results require an exact typed schema, effect list, per-effect evidence,
boolean postcondition and evidence digest. Missing fields, bool-as-int, unverified
effects, non-success, timeout or IPC uncertainty become `UNKNOWN` with no blind retry.
The cgroup/systemd spec remains data only and is explicitly `NOT_INVOKED_NOT_PROVEN`;
runtime containment is POSIX process-group best effort only.

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

`ControlledHttpsTransport` is the sole candidate HTTP transport. It exposes only
GET, bypasses environment proxies using raw sockets, denies redirects, requires DNS
results to fit a pinned IP set, and uses system-CA TLS hostname verification while
hashing the peer certificate into the receipt. The systemd template adds a default
deny egress placeholder. No root egress policy/IP set was installed, so real network
isolation and bypass closure remain unproven.

## Remaining release blockers

See `C7_EVIDENCE_GAPS.md` and `HUMAN_ACTIONS_REQUIRED.md`. Live authenticated GET
receipts, stable/frozen final checkpoint, production trust anchor, all UNKNOWN Writer
routes, root egress installation, real Shadow duration, canary and Korea-first
rollback evidence remain NOT RUN.

```text
PRODUCTION_MIGRATION_RELEASE=HOLD
PRODUCTION_EXECUTION_AUTHORIZED=NO
BINANCE_CALLED=NO
PRODUCTION_DEPLOYMENT=NO
RUNNER_OR_YIBI_MUTATION=NO
WRITER_STARTED=NO
```
