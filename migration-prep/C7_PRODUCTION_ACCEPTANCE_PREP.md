# C7 production-acceptance preparation

This batch extends only C7. Accepted and unchanged S1-S5/C1-C6 are not reopened.

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
A hash written inside a signed request is not that measurement. Likewise, `24h`
is a proposed Shadow duration, not an executed acceptance fact.
