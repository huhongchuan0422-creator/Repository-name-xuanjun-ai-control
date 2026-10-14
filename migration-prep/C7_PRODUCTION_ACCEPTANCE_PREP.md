# C7 production-acceptance preparation

This batch extends only C7. Accepted and unchanged S1-S5/C1-C6 are not reopened.

## Real interfaces added

- `restricted_executor.py` schema 3 binds an independent verifier digest and a
  non-empty exact postcondition list into the signed request. A runner success is
  provisional until an independent readback covers every postcondition and binds
  the exact runner-result digest. Only `READONLY_INSPECT` may use an explicit
  zero-effect policy; all mutation actions require effect postconditions.
- `c7_acceptance.py` validates the raw private Writer map against all 95 public IDs
  without disclosing paths, and rejects caller-scoped or limited evidence as a
  production gate PASS.
- `c7-real-machine-execution-package.json` separates immediately authorized
  read-only evidence from later administrator, trust, install, retirement and
  cutover phases. Every mutating phase remains unauthorized.
- `c7_root_inventory.py` is the reviewed zero-argument root read-only collector
  for root/yibi/githubrunner crontabs, systemd metadata and sudoers closure. It
  emits only counts/digests and never raw cron, unit, environment or policy text.
  It is a candidate and was not installed or granted sudo in this batch.

## Evidence boundary

The package can verify evidence returned by GitHub administration, Gateway
administration, root readback, independent Authority and Korea root isolation.
It cannot create those authorities. Missing authoritative receipts remain HOLD;
unit tests, source hashes and caller-scoped lists never promote them.
