# Tokyo -> Korea G1-G5 executable candidate

`TASK_ID=TOKYO_KOREA_MIGRATION_RELEASE_GATE_AFTER_INDEPENDENT_REVIEW`

Consumed independent review: PR99 comment `6166680343`, reviewing PR99 HEAD
`e2f7cb80f691eb5f7f7da9cc8c21d4af6f03b0ac`.

Consumed source review: PR99 comment `6167112786`, reviewing exact candidate
`eb900d13388a0afad940d3974d00b54af0ec06ae`. The five requested remediation
groups are implemented together; production remains HOLD.

Consumed consolidated security rereview: PR99 comment `6167741893`, reviewing
exact HEAD `dea50155d0b4989cc30c3bd2f1b808516e2d6ccd` / tree
`63d48c963f876b8b674414b9bdd33948eb21835a`. Residual S1-S5 are remediated in
one candidate-only batch; no production permission is added.

## Boundary

This commit is candidate code and isolated tests only. It does not remove a
Runner, stop or mask Yibi, start a restored application, call a live exchange,
change a credential/IP allowlist, grant a writer epoch, enable a scheduler, or
cut over production. `PRODUCTION_MIGRATION_RELEASE=HOLD`.

Existing encrypted archives, restored databases and backup receipts are
inputs marked `DO_NOT_REPEAT`; this candidate neither opens nor copies them.

`migration_gate_cli.py` is the only command-line entry. It can render G1/G2
plans, evaluate supplied observations, perform read-only writer discovery and
verify a detached archive signature. It has no command-execution, service,
GitHub-admin or exchange-write transport.

## Reuse audit

```text
REUSE_AUDIT_RESULT=MINIMAL_INCREMENT_REQUIRED
WHY_EXISTING_ASSET_CANNOT_BE_REUSED=Existing branch contains inspection and preparation documents but no executable G1-G5 state machine or authenticated archive-binding verifier.
WHY_MINIMAL_PATCH_NOT_ENOUGH=The five gates cross Runner, systemd, exchange credential/IP authority, GET-only reconciliation and two-host rollback order; one local flag cannot cover them.
WHY_INTEGRATION_ONLY_NOT_ENOUGH=Formal and legacy/manual writers do not share one already-deployed mandatory authorization boundary.
NEW_IMPLEMENTATION_JUSTIFICATION=Add only fail-closed candidate evaluators, discovery, durable idempotency and isolated tests; leave production runtime untouched.
```

## G1 production Runner retirement

Exact identities are pinned in `gate_inventory.json`:

- Tokyo: host `iZ6wee8q9z4t03hvqumwfhZ`, agent `4`, Runner
  `xuanjun-tokyo-readonly`, Default pool, exact systemd service, user
  `githubrunner`, workdir `/home/githubrunner/actions-runner`.
- Korea: host `iZmj7a5kwr75qc1tul4kf9Z`, agent `3`, Runner
  `xuanjun-korea-binance`, Default pool, exact systemd service, user
  `githubrunner`, workdir `/home/githubrunner/actions-runner`.

`runner_retirement.py` generates official stop -> uninstall -> GitHub remove ->
privilege-residue cleanup -> verification phases. Removal needs a protected,
short-lived GitHub token supplied only to `config.sh remove`; the token never
enters a report or command file. Helper and sudoers cleanup is separate and
must be followed by `visudo -c`. Success also requires agent IDs absent from
GitHub administration, no service/listener/autostart residue, and a harmless
SSH/OpenClaw canary. Timeout or partial success returns `HOLD` and
`INSPECT_ONLY_NO_BLIND_RETRY`. Repetition is a no-op only when the complete
phase history is a continuous prefix of receipt objects whose phase, successful
result SHA-256 and unique execution ID match. Strings, reordered/duplicated
phases, gaps, failed results and malformed digests fail closed. G1, G2 and G5
use the same validator.

Well-formed receipts without an independently backed result loader and
authority verifier are explicitly `FORMAT_VALID_CANDIDATE`. When those two
interfaces are supplied, each execution ID/phase is bound to the loaded result
and the result is re-hashed, but the outcome is still
`AUTHORITY_BOUND_DURABLE_RESULTS_CANDIDATE` with
`production_authorized=false`. Phase actions are structured candidate advice,
never production commands.

This PR disables its own self-hosted inspection job. Hosted tests continue;
no candidate push should schedule either production Runner.

## G2 permanent Yibi retirement

Pinned units:

- services: `yibi-api`, `yibi-scheduler`, `yibi-daily-report`,
  `yibi-health-check`, `yibi-mailbox-reader`, `yibi-worker`;
- timers: `yibi-daily-report.timer`, `yibi-health-check.timer`.

`yibi_retirement.py` stops triggers first, then services, disables and masks
every Yibi unit. It never targets novel/PostgreSQL/Redis. Acceptance requires
no Yibi process/listener/timer/cron/OpenClaw trigger and byte/identity-stable
shared dependencies. System cron discovery found no Yibi match. Current
OpenClaw automation visibility is restricted, so global trigger inventory is
`NOT_VERIFIED_RESTRICTED_SCOPE` and production retirement remains blocked
until an administrator proves the complete inventory. Failure recovery may
restore only an accidentally changed shared/novel dependency; it explicitly
forbids starting, enabling or unmasking Yibi.

## G3 hard Writer fence

`writer_fence.py` validates a contract for every prospective write request,
including protection, cancel, close and manual-script actions. The lease must
be signed with Ed25519 by an allowlisted authority whose public-key SHA-256 and
store identity are pinned independently. Verification fields are exact booleans,
fingerprints are non-empty SHA-256 values, and requested, lease and externally
signed current epochs must be identical. Local file, memory or SQLite authority
is rejected. The lease is valid only after signed evidence proves:

1. previous epoch revoked;
2. old-host trading credential revoked;
3. old-host IP removed from exchange allowlist;
4. current credential and allowlist fingerprints verified;
5. a production Release Gate ID exists.

Host mismatch, stale epoch, old Tokyo reboot, expired lease, replay conflict or
unknown action fails closed. `discover_writer_paths()` scans formal and legacy
roots conservatively and binds each finding to its source SHA. Reachable paths
must call the fence and have scoped credential access; quarantined manual or
legacy paths must have neither credential nor scheduler access. Any new,
missing or changed path returns `HOLD`.

Candidate limitation: this commit does not patch `/opt/trading-system` or the
legacy workspace and has no production authority adapter. Contract evaluation
always returns `execution_authorized=false` and
`scope=CONTRACT_SIMULATOR_ONLY_NOT_PRODUCTION_AUTHORITY`. Therefore runtime
path coverage and actual credential/IP revocation are `NOT_EXECUTED`; G3 cannot
authorize an exchange write in this candidate.

`reboot_verdict()` returns only `DENY` or
`CONTRACT_VALID_NOT_AUTHORIZED`; a valid simulator contract can never be
misread as `ALLOW` after reboot.

The candidate scanner was run read-only against both declared roots after the
implementation: 95 source files matched (`FORMAL=12`, `LEGACY=17`,
`MANUAL_SCRIPT=58`, `PROTECTION=8`), discovery digest
`c80ccec7548264dce4322413d423a9a98869a3cb0f1675d27f91906a64068b65`.
Because no production path was patched or quarantined in this task,
`COVERAGE_STATUS=HOLD`; this is expected and prevents a false G3 PASS.

## G4 GET-only reconciliation and final snapshot

`final_snapshot.py` itself invokes every surface through a transport that
rejects every method except `GET` and records request/response digests. Exchange
time must be fresh against the request clock; collection has a maximum duration;
every state surface must prove complete pagination and exact symbol coverage.
Positions, ordinary/algo/protective orders, recent orders and trades are
explicitly compared with normalized local mirrors. UNKNOWN, in-flight and
ownership conflicts remain blockers.

The final checkpoint combines the reconciled exchange digest, authoritative
database file identities, pending/recovery/unknown/in-flight queues,
guard/watch state, ownership ledger and scheduler state in one content-addressed
manifest. The authoritative filename set is exact; every sidecar has a frozen
content digest captured in the same bounded freeze window, and exchange
reconciliation must also occur inside that window. Semantic verification runs
in addition to the manifest hash, so recomputing JSON after weakening a sidecar
does not pass. This tool was tested only with fixtures; no live Binance call or
final snapshot was made.

A self-consistent recomputed checkpoint that preserves only structural rules is
reported as `STRUCTURALLY_VALID_ONLY`, never authenticated. Optional retained
input verification re-hashes the retained exchange snapshot and re-reads every
authoritative file identity, but still returns candidate evidence only. Release
continues to require pinned signed freeze receipts, independent Authority
binding, fresh live GET-only revalidation and the separate Owner Release Gate.

## G5 isolated Korea deployment, shadow/canary and rollback

`cutover_gate.py` explicitly checks every required field, including Redis,
without positional slicing. It requires dedicated user/directories/Secret namespace,
non-overlapping ports, dependency/runtime/permission/network checks and
unchanged novel/PostgreSQL/Redis. Isolated launch must have no trade credential,
Writer or scheduler. Shadow acceptance requires `NO_ORDER_WRITE`, same inputs,
matching decisions/positions/orders/protection, zero UNKNOWN/in-flight, restart
recovery and the declared duration.

Every positive and negative isolation/shadow flag must be an exact boolean;
`0`, `None`, empty strings and other falsey/truthy substitutes are rejected.
UNKNOWN/in-flight counters must be exact non-negative integers and booleans are
not accepted as counts.

Forward order cannot skip: isolated deploy -> runtime -> shadow -> Tokyo fence
-> final checkpoint -> Korea sole authority -> bounded canary -> observation.
Rollback cannot grant Tokyo a new epoch until Korea Writer is locked, Korea
credential revoked, Korea IP removed, unknown outcomes reconciled, the final
checkpoint restored and GET-only reconciliation passes. Timeout, partial or
uncertain evidence is `HOLD`; double Writer is always forbidden.

## Archive authenticity binding

`archive_binding.py` signs the already-recorded artifact identity using a
detached Ed25519 key and verifies it against a separately pinned public-key
SHA-256. Tests prove tampered metadata fails. The subject is also committed at
`evidence/migration/archive-binding-subject.json`, independently binding the
reported hash to an exact Git commit rather than a same-directory checksum.

No trusted offline Ed25519 public-key fingerprint/signature was provided in
this task. Therefore:

```text
GIT_COMMIT_BOUND_SUBJECT=PENDING_EXACT_COMMIT
ED25519_IMPLEMENTATION_TEST=PASS
PRODUCTION_ARCHIVE_AUTHENTICATED_BINDING=BLOCKED_MISSING_INDEPENDENT_TRUST_ANCHOR
```

The AES-CBC archive and a checksum beside it are never described as
authenticated integrity.

## Isolated test receipt

The remediation suite adds field-by-field G5 isolation negatives; stale-clock,
capture-duration, pagination, symbol-coverage and state-difference G4 negatives;
string/empty/unsigned G3 negatives; forged/reordered/failed phase histories;
two-process ledger races, transaction-crash recovery, a non-returning deadline,
and partial-side-effect uncertainty. Exact final test and CI counts are recorded
only after the consolidated candidate is rerun.

The idempotency ledger is now a SQLite `BEGIN IMMEDIATE` transaction with a
unique key, WAL recovery and FULL synchronous durability. It is not an external
Writer authority. Deadline calls run in a child process through a one-way Pipe
with bounded READY/result acknowledgements. The child enters a distinct POSIX
process group before the callable starts; forced termination targets that group
and never treats direct-child exit as proof that descendants or effects are
gone. Timeout, missing result IPC or a lingering child is explicitly uncertain
and requires inspection/reconciliation instead of claiming rollback or retry
safety.

## External blockers before production

- GitHub administrative Runner removal token and administrative absence proof.
- Full OpenClaw trigger inventory on Korea with administrator scope.
- Separate authorization to stop/disable/mask Yibi and remove Runner residue.
- Runtime integration of the Writer fence into every discovered path.
- Actual trading-credential revocation and exchange IP allowlist evidence.
- Protected GET-only Binance credential and a bounded maintenance window.
- Final checkpoint produced in that window.
- Korea isolated deployment/runtime/shadow/canary evidence.
- Independently managed Ed25519 trust anchor and signature for the existing
  archive identity.
- Independent Auditor and Release Gate decisions on the exact commit.

Any missing, timed-out, partial, stale or conflicting evidence keeps
`PRODUCTION_MIGRATION_RELEASE=HOLD`.
