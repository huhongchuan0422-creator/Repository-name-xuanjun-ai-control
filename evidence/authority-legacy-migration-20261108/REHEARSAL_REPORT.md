# Isolated legacy authority migration rehearsal

## Candidate revision 2 local regression (2026-11-08)

No production service, DB, backup or process was touched. Local fixtures cover
canonical receipt hash/binding/substitution attacks; strict FORMAL schema and
profile rejection; signed freeze empty/stale/wrong-operation/tamper/state-change
rejection; every rollback failpoint; concurrent writer; FK/indexes; conservative
legacy rows; idempotency; and the schema-only/count/hash probe. Existing authority
operational/security suites retain first-registration CAS and formal trust tests.
Fresh independent QA, Security and Release review remains required.

Source was an isolated copy of
`canonical-ledger-pre-authority-20261108T063834Z.sqlite`; production DB and
services were not touched and no task row content was selected or exported.

* source SHA-256: `8e88a3d23159b9076e2e9513ef0076e812f7d0a695e19621295fb7b8a6f4fa1e`
* `quick_check`: `ok`
* application/user version: `0` / `0`
* exact schema fingerprint: `3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45`
* task count: 10 (count only)
* migration receipt: `COMMITTED`, operation `rehearsal-20261108`
* repeated apply and recover: returned the same receipt
* post-migration: `quick_check=ok`, 10 tasks, FORMAL singleton profile,
  zero claims, zero registrations, zero rows with authority other than NONE,
  or with a non-UNKNOWN attempt/lease or non-null epoch
* fault matrix: exclusive-lock boundary, each task ALTER, backfill, authority
  table creation, and pre-commit interruption all rolled back to the exact
  source fingerprint and then recovered on retry
* concurrent writer: exclusive lock acquisition failed closed
* prior-candidate restart reconciliation evidence is retained; revision 2 now
  rejects a different/missing operation receipt as explicit `INTEGRITY_*`
* FK and required-index checks passed after migration
* prior candidate unit result: 6 tests run, 5 passed, 1 environment-gated
  direct-backup test skipped; this skip is retained only as history and is not
  treated as PASS. Revision 2 uses `probe` or a Platform-controlled read-only copy.
* persistent unit output: `RAW_UNIT_TEST.log`, authenticated by `SHA256SUMS.txt`

This is candidate evidence only. Independent QA, Security, and Release review
remain required before any production migration.
