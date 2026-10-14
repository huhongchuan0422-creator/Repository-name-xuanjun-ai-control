# C7 production-acceptance preparation

This batch extends only C7. Accepted and unchanged S1-S5/C1-C6 are not reopened.

## Owner-corrected business scope and shortest path

`BUSINESS_OUTCOME`: move the Tokyo Binance production project to Korea with exactly
one Writer, preserved risk/protection behavior, complete production data/state and a
tested Korea-first rollback; then retire Yibi; retire Tokyo only after every Binance
production dependency is proven moved or given an explicit non-Tokyo destination.

`INCLUDED`: minimal execution/runtime modules actually loaded by production; exchange
read/write transport; account/symbol and BTC/ETH/SOL state; production DB main/WAL/SHM
and ledgers; pending/recovery/unknown/inflight/ownership/epoch state; risk guards,
protective-order and position/order monitors; required scheduler/trigger/launcher;
protected credential references, exact egress/IP policy, logs/metrics and rollback
evidence. A Finance/Billing/Ledger timer is included only if direct data/transaction/
credential evidence proves it is required for the migrated Binance production loop;
otherwise it receives a separately recorded destination and is not installed in Korea.

`EXCLUDED`: OpenClaw Gateway and its sessions/agents/workspace; development tasks,
tests, caches and build agents; temporary Agent/subprocesses; GitHub Runner as a
business dependency; website, OAuth, customer/WeCom, model/RPC, self-media, Novel,
Yibi and their databases; unrelated Finance/CRM; old archives, backups and historical
releases. Existing tested code and backup artifacts are reused; no simulation-layer
development and no repeated backup/decrypt are part of this revision.

`CAPACITY`: Korea remains on its existing 2-core/2-GB-class configuration. The gate
measures the minimal installed production set during cold start, steady read-only
reconciliation, restart recovery and Shadow: no OOM/kernel kill, no unexpected
restart, bounded swap growth, positive memory/disk/FD headroom, and workload latency
within the independently approved production threshold. Tokyo OpenClaw 4.11GB is not
an input because OpenClaw is outside this migration artifact.

`ORDER`: (1) exact dependency inventory/classification; (2) install isolated minimal
Binance target with Writer/schedulers locked; (3) restore existing accepted backup to
an isolated copy and validate dependencies/restart/resources; (4) GET-only full
reconciliation and approved Shadow; (5) hard-fence all Tokyo Binance write paths;
(6) one bounded final WAL-aware snapshot/incremental capture; (7) grant Korea the only
Writer epoch and run bounded Canary; (8) independent production acceptance and
rollback drill; (9) only after PASS, confirm archive and permanently retire exact
Yibi units/triggers; (10) verify no Binance production dependency remains on Tokyo,
record separate destinations for development work, then request Tokyo retirement.

`ROLLBACK`: lock Korea Writer first, revoke Korea write credential/IP/epoch, inspect
unknown effects and reconcile against Exchange, keep Yibi and Novel unchanged, then
and only then consider a new Tokyo epoch from the verified final checkpoint. Never
allow two Writers and never blind retry an unknown-effect step.

## Real interfaces added

- `restricted_executor.py` schema 3 binds an independent verifier digest and a
  non-empty exact postcondition list into the signed request. A runner success is
  provisional until an independent readback covers every postcondition and binds
  the exact runner-result digest. Only `READONLY_INSPECT` may use an explicit
  zero-effect policy; all mutation actions require effect postconditions.
- `c7_acceptance.py` validates the raw private Writer map against all 95 public IDs
  without disclosing paths. Six self-asserted PASS dictionaries are only
  `FORMAL_RECEIPT_SHAPE_ONLY` and remain HOLD. Candidate readiness additionally
  requires a separately Ed25519-verified admission policy, a gate-specific signed
  receipt, original evidence bytes with a recomputed SHA-256, and a code-owned
  adapter. Commit/tree, subject, authority, adapter, transaction epoch, collection
  time, expiry, exact hosts and complete coverage are equality-bound; duplicate,
  contradictory, partial, expired, forged or adapter-rejected evidence remains HOLD.
- `c7-real-machine-execution-package.json` separates immediately authorized
  read-only evidence from later administrator, trust, install, retirement and
  cutover phases. Every mutating phase remains unauthorized.
- `c7_root_inventory.py` is the reviewed zero-argument root read-only collector
  for root/yibi/githubrunner crontabs, systemd metadata and sudoers closure. Every
  systemd root and entry has a redacted outcome record. Missing roots, walk/read
  errors, non-regular entries, dangling/out-of-root links, untraversed link
  directories and file-identity drift make the inventory `HOLD_INCOMPLETE`.
  Authorized links bind the link, resolved target, target identity, content hash and
  effective unit-name hash. Confirmed no-crontab and read failure are separate.
  The collector never emits raw cron, unit, environment, policy text or paths. It
  remains uninstalled and has no new sudo grant.

## Evidence boundary

The package can verify evidence returned by GitHub administration, Gateway
administration, root readback, independent Authority and Korea root isolation.
It cannot create those authorities. Missing authoritative receipts remain HOLD;
unit tests, source hashes and caller-scoped lists never promote them.

The independent result verifier remains a candidate contract until its actual
installed file, canonical location, ownership, mode and bytes are measured by a
separate authority and the verifier's post-state source is independently reachable.
A hash written inside a signed request is not that measurement. Shadow duration is
an Owner/auditor-approved acceptance parameter; any prior `24h` value is a proposal,
not an executed fact or a reason to widen migration scope.