# Tokyo -> Korea G1-G5 executable candidate

`TASK_ID=TOKYO_KOREA_MIGRATION_RELEASE_GATE_AFTER_INDEPENDENT_REVIEW`

Consumed independent review: PR99 comment `6166680343`, reviewing PR99 HEAD
`e2f7cb80f691eb5f7f7da9cc8c21d4af6f03b0ac`.

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
`INSPECT_ONLY_NO_BLIND_RETRY`. Repetition is a no-op only when the phase's
idempotency evidence matches.

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

`writer_fence.py` requires every write request, including protection, cancel,
close and manual-script actions, to present a signed, unexpired external lease
with a monotonically increasing epoch. Local file, memory or SQLite authority
is rejected. The lease is valid only after independent evidence proves:

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
legacy workspace. Therefore runtime path coverage and actual credential/IP
revocation are `NOT_EXECUTED`; G3 is executable candidate code, not a migrated
production fence.

The candidate scanner was run read-only against both declared roots after the
implementation: 95 source files matched (`FORMAL=12`, `LEGACY=17`,
`MANUAL_SCRIPT=58`, `PROTECTION=8`), discovery digest
`c80ccec7548264dce4322413d423a9a98869a3cb0f1675d27f91906a64068b65`.
Because no production path was patched or quarantined in this task,
`COVERAGE_STATUS=HOLD`; this is expected and prevents a false G3 PASS.

## G4 GET-only reconciliation and final snapshot

`final_snapshot.py` has a transport that rejects every method except `GET`.
It requires server time, account, balances, position mode, positions, ordinary
open orders, algo/protective orders, recent orders and trades. It also requires
ownership conflicts, UNKNOWN orders, in-flight requests and all DB-external
state classes to be resolved. Every surface is bounded to the exchange time
watermark.

The final checkpoint combines the reconciled exchange digest, authoritative
database file identities, pending/recovery/unknown/in-flight queues,
guard/watch state, ownership ledger and scheduler state in one content-addressed
manifest. New entries must be frozen and in-flight work drained. This tool was
tested only with fixtures; no live Binance call or final snapshot was made.

## G5 isolated Korea deployment, shadow/canary and rollback

`cutover_gate.py` requires dedicated user/directories/Secret namespace,
non-overlapping ports, dependency/runtime/permission/network checks and
unchanged novel/PostgreSQL/Redis. Isolated launch must have no trade credential,
Writer or scheduler. Shadow acceptance requires `NO_ORDER_WRITE`, same inputs,
matching decisions/positions/orders/protection, zero UNKNOWN/in-flight, restart
recovery and the declared duration.

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

Local migration tests: `37/37 PASS`; existing repository Python tests:
`207 PASS / 1 existing conditional skip`. Python compile, JSON validation,
workflow YAML parse and staged whitespace checks pass. Tests explicitly cover
failure, timeout, partial success, repeat/replay, phase skipping, stale epoch,
old-host reboot, unauthorized local authority, unknown orders, non-GET methods,
shadow timeout, Korea-first rollback and signature tampering.

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
