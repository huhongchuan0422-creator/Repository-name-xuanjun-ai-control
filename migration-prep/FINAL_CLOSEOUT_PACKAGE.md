# Tokyo → Korea Binance final closeout package

## Consolidated R1-R6 remediation after independent review 6181062368

The accepted parent is `82025a45acefb7ef4ae3708bc37f71000ad32b92` /
`db8bbf12b405d9cdb3a9805e4523414935b884a2`. Unchanged accepted evidence is
reused. This delta changes only the Korea B/C candidate and focused tests:

* R1: deterministic self-contained runtime builder and clean-extract validator;
  isolated import cannot fall back to workspace files.
* R2: mutation follows full preflight, private staging, second byte verification,
  transaction ownership, effective-unit verification and hash-bound uninstall.
* R3: evidence `observation_run_id` is separate from the authoritative business
  `snapshot_id` selected in the closed WAL-aware copy by account/freshness.
* R4: the real entry shares server-time, surface-window, pagination and state
  checks; raw network evidence is independently verified and the whole capture has
  one deadline.
* R5: PASS exits 0, HOLD exits 2, UNKNOWN exits 3; failures retain a structured
  receipt and never report success through exit 0.
* R6: the unit uses an Owner-parameterized bounded continuous sampler with
  restart-resumable window evidence and resource/latency aggregation. The
  unapproved template cannot run.

Offline focused tests exercise only-extracted-artifact validation, the real default
entry on a redacted production-shaped SQLite schema with an existing snapshot id,
clock skew, slow response, malformed response, incomplete pagination, verifier
rejection, nonzero failure exits, installer failure boundaries and continuous-window
aggregation. No Binance or production host is contacted.

Feature: `TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1`

Baseline: `4a6215e0d27e1560de3eca4ccbc5dbeaa492aaff` / `e2c647630e7fbeefbf35a3835bdb4573a0c5d3de`

Production: `HOLD`

## Closed evidence

* Both original Root Collector receipts remain `HOLD_INCOMPLETE/exit 2`; no PASS was
  manufactured. Exact supplements cover only the frozen 17 dracut links: target
  bytes/hash, root-owned 0755 parent chain, 0644 targets and RPM provenance. Tokyo is
  `dracut-059-3.alnx4.x86_64`; Korea is
  `dracut-049-246.git20260728.0.1.1.al8.x86_64`.
* `WALK_COMPLETE` is a collector diagnostic defect: it is emitted when `os.walk`
  completes, then counted as failed because only `PASS` is accepted. It is not a host
  finding and the frozen collector was not changed.
* Tokyo coverage includes root/admin/githubrunner/yibi crontab, system cron files,
  root-visible user units, transient units, active processes, wrapper/dynamic-call
  capability and at-queue tool availability. No direct WP001–WP095 binding was found.
* Gateway has four persisted scheduler jobs. Five enabled bundled hooks cover gateway
  startup, agent bootstrap, command logging, session compaction and memory reset. The
  Feishu channel is a real external session ingress. Neither hooks nor channel ingress
  is the cron list, and neither contains a direct WP001–WP095 binding. Only the
  research-only community-signal scheduler references `binance-eth-trader`.
* Zero direct bindings is not non-reachability: all 95 remain `UNKNOWN/DENY` and are
  not copied into the runtime artifact.

## Real runtime closure

No persistent production order Launcher is installed or proven. The accepted code
composition point is `build_production_trading_execution_service`; the one-shot
Owner smoke script is not a daemon or scheduler. Its required repositories,
reconciliation providers, watchdog, market freshness, anomaly/recovery state,
production risk/loss/FOMC/manual-intervention guards, protection gate, persisted risk
limits, authorization and credential provider are listed in
`production-runtime-closure.json`.

Therefore A is not complete for a production Writer and D/E remain blocked. This is
not solved by choosing a candidate file. The actual B/C deliverable is narrower and
real: a stdlib-only GET-only Shadow entry, deterministic manifest, dedicated identity,
disabled deny-all unit, install/check/uninstall commands, WAL-aware closed-copy read
and independent exact-hash verifier hook. It loads only the dedicated read-only
SecretRef and has no write method or scheduler.

## Database and credentials

See `SHARED_DATABASE_CUTOVER_PLAN.md`. Four Finance/Billing timers continue running.
B/C uses an isolated consistent copy and a dedicated read-only credential. The
trading credential and shared master key are forbidden. Phase D requires one
authoritative database, exact pause/drain/final snapshot/delta reconciliation, and a
proven post-cutover Finance route before timer resumption.

## Installation commands (future Gate only)

These commands are documentation, not authorization:

```text
sudo ./migration-prep/korea/install-candidate.sh SOURCE_ROOT EXPECTED_MINIMAL_MANIFEST_SHA256
sudo ./migration-prep/korea/check-candidate.sh --expected-transaction /etc/xuanjun-binance/install-transaction.json --expected-manifest-sha256 EXPECTED_MINIMAL_MANIFEST_SHA256
sudo ./migration-prep/korea/uninstall-candidate.sh --confirm-disabled-candidate-only --transaction-sha256 EXPECTED_TRANSACTION_SHA256
```

Install creates no credential, IP allowlist or active service. The base unit is
deny-all and disabled. A later Phase-C signed action must materialize the read-only
credential/config and an exact root-owned `IPAddressAllow` drop-in; application-level
GET enforcement remains mandatory.

## Acceptance and compliance

The design, development sequence, acceptance references and reuse decision are in
`docs/development/TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1.md`. The main-branch
Feature Compliance Gate is reused byte-for-byte and the feature is registered as
`CANDIDATE`, not verified/deployed. Focused tests and the full migration-prep suite
must pass on the exact final head; hosted CI receipts are recorded only after the
head exists.

Human settings, suggested thresholds and independent Authority/verifier design are
consolidated in `OWNER_ONE_TIME_COMPLETION.md`; phase scopes and every outcome state
are in `PHASE_AUTHORIZATION_AND_OUTCOME_MATRIX.md`.
# R2/R6 residual independent-review boundary (receipt 6181898666)

- Installer rollback removes only directories created by the current attempt
  and still matching the recorded device/inode.  Pre-existing empty targets
  survive every rejection path; identity changes or removal failures are
  retained and reported as `CLEANUP=PARTIAL`.
- Snapshot admission and consumption share one authenticated open descriptor
  and private immutable generation copy.  Path rotation before or after SQLite
  backup cannot change the database consumed for the accepted receipt.
- WAL/SHM presence, stale replay, incomplete rotation, and missing cgroup v1/v2
  peak/OOM evidence fail closed.
- No candidate test claims Korea installation, real publisher/verifier wiring,
  or continuous Shadow acceptance.  Production migration remains HOLD.
