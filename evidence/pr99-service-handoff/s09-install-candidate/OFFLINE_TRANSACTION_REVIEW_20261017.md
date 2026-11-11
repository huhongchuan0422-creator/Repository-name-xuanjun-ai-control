# PR99 offline transaction continuation candidate

Base: `18f8fd8aae7a3af90263b8ef10414663c0a6b14e`, original branch
`build/tokyo-korea-migration-prep-20261014`. This is a source/test review packet,
not a second progress ledger, private admission, final checkpoint or deployment receipt.
The canonical state and execution ledger remain unchanged by this patch.

## Implemented and actually exercised

- `migration_transaction.py`: fixed 12-stage order from protected-state inspection,
  source fencing, final snapshot/receipt verification and reconciliation through
  writer assignment, stopped installation, owned start, business acceptance,
  route snapshot, cutover and HTTPS acceptance. Exact event/HEAD/owner/attempt
  validation is present, but the production entry unconditionally returns HOLD.
- Existing `production_start.py` supplies HOST, RELEASE and STATE constants.
  Operation storage is reserved beneath its existing STATE, not a separate authority.
  Exact hashes bind this controller, final-material helper and both existing helpers.
  The existing host helpers are **not invoked or changed** by this candidate.
- Durable one-use local intent/consumption, exclusive lock, fsync, chained records,
  source drift and expiry checks before each modeled effect; result-write failure,
  transport timeout or malformed receipt becomes UNKNOWN/query-only. No redispatch
  and no new transaction are allowed over an existing consumed transaction store.
- Recovery only queries the last operation with its exact binding; a resolved
  result never auto-resumes execution, rollback, source writer or the whole task.
- Known partial failures model exact route restoration before stopping owned apps.
  Unknown or failed containment remains HOLD. Data and diagnostic artifacts stay.
- `final_materials.py`: actual bounded temporary-file copy under a caller-verified
  pre/post fence, exact receipt/file-set/hash verification, preservation on drift,
  traversal/link/hardlink rejection, and exact regular-file compare-and-swap route
  replacement/restoration. No source writer is restarted, no nginx is reloaded.
- Existing stopped-transaction tests now explicitly model root ownership for their
  temporary fixtures on non-root test runners. The production UID-0 requirement
  is unchanged; these tests are not evidence of actual root ownership or PID1.

## Verified test results and limits

Python 3.12.14, local cloud filesystem, 2026-10-17:

`python3 -B -m unittest discover -s evidence/pr99-service-handoff/s09-install-candidate -p 'test_*.py' -v`

54 tests PASS (original 13 + 41 new), 0 skipped; compileall PASS.
The failure/timeout tests iterate each of the 12 stages. Tests additionally cover
receipt/plan/source drift, replay, second attempt, concurrent lock, partial journal,
post-effect result-write failure, query failure, wrong query identity, expired input,
real fixture copies, changed fence/source, exact receiving set, preserved partial
files, route conflicts, foreign-route rollback and a crash after file replacement.

The 12-stage execution adapter is an in-memory fixture. The file snapshot and
route tests use real temporary filesystem bytes. No actual SQLite/WAL integrity,
root service operation, PID1/systemd239, SWAS/STS, private final data, real signed
callback, upstream HMAC, DNS/HTTPS or production rollback was tested. Hosted CI
has not run for these exact candidate bytes at packet creation. This is not a full
repository test run. The existing 9+4 tests are inherited with the noted fixture fix.

## Remaining code and real inputs: do not call this production-ready

There is intentionally **no production adapter** or enabled production workflow.
The existing stopped workflow remains stopped-only. Full host transaction integration
is still incomplete, not merely waiting for an approval flag. Remaining work includes:

1. Original independent root-held exact full-action admission loader and verification,
   bound to reviewed source, private plan, operation and authorized rollback scope.
   A positive integer review ID or a digest in a fixture is never that permission.
2. Fixed-host existing STS/SWAS transport integration with durable pre-dispatch intent,
   InvokeId/result binding and a genuinely read-only operation-ID lookup when a
   RunCommand response is lost before its InvokeId is recorded. The public existing
   transport cannot safely infer absence or re-dispatch from that uncertainty.
3. Exact, independently verified source writer/shared-data inventory and enforced
   fence, real consistent final checkpoint (including database/WAL/schema integrity),
   private source/receiver transport, reconciliation and canonical-writer assignment.
   A caller-provided fence hash is an interface, not proof that any writer stopped.
4. Prepared dedicated production identity/permissions and unit/drop-in ownership;
   wire existing stopped/start helpers into the common operation state without
   replaying their existing consumed directories or changing protected services.
5. Real business signature/bridge pin/HMAC acceptance and supervised restart checks.
6. Exact authorized route and old configuration/current binding, ownership lock with
   other writers, nginx validation/reload, external HTTPS acceptance and verified
   post-rollback HTTPS. The regular-file CAS helper does not handle symlink `current`
   or make arbitrary filesystem replacement race-free against another writer.

Those inputs are absent from the public handoff. This patch does not invent them,
self-issue permissions or claim final snapshot, production installation/cutover,
Tokyo retirement, full server migration or PR122 website completion. P2, trading,
Finance timers, DNS, existing website/current, bridge and winctl remain outside all
executed tests. The source and receipts of historical successful host batches remain
unchanged and must not be replayed.

## Trigger audit and hosted-only verification

All 58 `.github/workflows` files at the pinned base were retrieved and inspected.
The changed source paths and the reused `pr99-stopped-transaction-validation.yml`
can cause only GitHub-hosted offline checks for this commit/PR synchronize:

- All 17 `aliyun-*` workflows are workflow_dispatch-only. No dispatch is performed.
- `pr99-controlled-stopped-install.yml` is labeled-only. No label is added or replayed.
- Self-hosted entry/migration inspection jobs are hard-disabled, manual-only, or
  restricted to main/different paths. `v27-four-server-batch-readonly.yml` requires
  its own path change and exact historical commit-message/manual conditions; this
  patch does not modify it and must not use historical execution commit messages.
- Existing generic control-plane, feature-compliance and intake test jobs are hosted;
  the comment intake writer only applies to its explicit issue-17 marker event.
- The reused PR99 test job is `ubuntu-24.04`, contents:read, without cloud secrets,
  and checks out the exact event HEAD with persist-credentials:false. It runs the
  local unit tests and the existing read-only unit manifest command only.
- No new workflow, production label, RunCommand payload, dispatch, credential,
  self-hosted runner, permission expansion or external call is added.

This audit covers the pinned branch's workflow files and these proposed changes;
external repository apps/webhooks are not established by that source audit. Recheck
HEAD and any intervening workflow changes before publication. Review can proceed on
these bounded offline mechanisms; the complete production chain remains unfinished.
