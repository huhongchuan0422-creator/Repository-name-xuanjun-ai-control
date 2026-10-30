# P3 host carrier, installation gates, and acceptance split

## Current result

This successor is an immutable, **default-off** host-integration carrier.  It
does not create a second ledger, task registry, service, runner, provider,
outbox, watchdog, credential, or task.  It is **not installed** and is not a P3
release.

The unchanged reviewed base is Commit
`875121c4e329ae47650b66a9a3b9c28ba4f1574b`, Tree
`6422b209c22e353914fb06733ea44b0db9b8ad48`.  Its independent QA result remains
`26/26 PASS`; independent Security remains `8/8 PASS` plus `22/22` checksum
members.  Those unchanged results are reused and are not relabelled as review
of this installation increment.

## New bounded integration

`src/p3_host_callsite.py` is the only host callsite adapter.  It:

1. accepts the already-existing `P3Ledger`; it has no ledger constructor;
2. verifies the actual imported bytes for the frozen lifecycle, reminder,
   wiring, activation, and reviewed host-boundary modules;
3. returns `PREPARED_DEFAULT_OFF` without reading admission or composing a loop
   while `execution_enabled=false`;
4. when a later host explicitly enables it, requires one exact current run
   subject and rechecks `p2_accepted`, `p3_release_accepted`, unique Writer,
   execution authority, validity interval, and full lineage before calling the
   original `compose_existing_host`; and
5. keeps notifications independently disabled unless their separate authority
   is present.  It never obtains authority from request/user data.

The carrier preserves the exact original frozen ZIPs instead of rewriting them.
The reviewed `p3_host_boundaries.py` bytes are also unchanged.

## Installation-before-use prerequisites

All of the following are required before the carrier installer may stage even
the default-off release:

- current real P2 field-acceptance receipt and matching same-instance query;
- explicit P3 release receipt and exact release approval;
- carrier Commit/Tree, manifest SHA, archive SHA, and a unique attempt;
- actual current host module/callsite path and imported source readback;
- current canonical ledger/activation descriptor identity, task/spec pins,
  attempt, lease/fence/epoch, sole Writer, and old-Writer-stop evidence;
- exact existing runner/provider/outbox/watchdog implementations and their host
  identities; and
- the existing controlled install entry must fresh-read all the above plus its
  lock, attempt, and consumed record immediately before each filesystem effect.
  The carrier consumes that existing verifier callback and does not define a
  second approval or task system.  No new sudo, credential, persistent access,
  or permission is included.

The installer copies manifested bytes into one immutable release directory and
writes `INSTALLED_DEFAULT_OFF_NOT_BOUND`.  Its command-line entry exposes only
verify/readback/recover; install/rollback are library calls for the existing
controlled entry, so a request body cannot substitute authority.  It does
**not** edit the current host
callsite, service, activation descriptor, ledger/WAL, task rows, outbox, or
provider.  An interrupted attempt is recovered by `recover`/`readback`; the
same intent is never replayed.  Rollback is a separate root-gated operation and
only quarantines an unbound, never-executed default-off release while preserving
evidence.

## After-install, before-live prerequisites

Installation is not enablement.  Before binding the existing host callsite:

- read back every installed member and imported module hash;
- prove no competing original loop/Writer and preserve the existing ledger;
- bind the real host-owned admission and immutable receipt readers;
- bind the approved existing runner `launch/resume/inspect/stop` interface,
  host watchdog/cgroup/descendant-stop controls, and original outbox
  send/lookup/ACK interface;
- run the affected carrier/callsite tests and formal artifact-bound CI; and
- independently approve the new carrier/installer/callsite delta.

Only after the real P2 acceptance and explicit P3 release are still current may
the existing host set `execution_enabled=true`.  `notifications_enabled` stays
false until independently authorized.  Unknown launch/send/install effects are
HOLD and reconciled; they are never blindly retried.

## Post-enable real-task acceptance

These are deliberately **post-install** and do not block carrier preparation:

1. real ACK then separately bound STARTED receipt;
2. real progress, stop/effect, checkpoint, test, CI, QA, Security, and business
   receipts on one task/artifact lineage;
3. worker exit/restart, stale progress, result-missing, completion recovery,
   duplicate event, notification-loss, and UNKNOWN-side-effect recovery;
4. original outbox delivery/lookup/ACK with no redial under uncertainty; and
5. two consecutive authorized real tasks, each independently accepted, proving
   automatic successor advance without a second Writer.

Until these pass, field acceptance remains false.  B7 is unrelated and remains
closed by its B6 `COMMITTED` plus same-instance fresh-query gate.
