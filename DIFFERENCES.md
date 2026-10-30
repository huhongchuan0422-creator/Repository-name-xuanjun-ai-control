# Difference statement

## Preserved unchanged

- Frozen P3 core ZIP `34fda992…0252` and its 48-test scoped review.
- Frozen host-wiring successor ZIP `d41d8062…aa93` and its 13-test scoped review.
- Original P2 admission, activation, canonical ledger, task/spec, lease/fence,
  checkpoint CAS, outbox transaction, UNKNOWN, approval and recovery semantics.
- Default-off behavior and all field/deployment blockers.
- Independent reminder scope: this increment does not import or change the
  reminder implementation and does not add P2 as a prerequisite to an
  independently authorized reminder path.

## Added

- One inert Python module defining authenticated receipt, runner, evidence-reader,
  outbox transport and watchdog classification boundaries.
- Twenty-one isolated unit tests using only in-memory fixtures.
- Integration, gap, test and B7 dependency documentation.

## Explicitly not added

- No concrete runner/provider/transport, network or model call.
- No real ledger/activation/Writer lookup and no second task system.
- No daemon, timer, service, cgroup, database migration, credential, install or
  host callsite mutation.
- No automatic retry after uncertain launch/resume/stop/send/ACK.
- No fabricated ACK, STARTED, progress, STOPPED, SENT, ACKED, DONE, ACTIVE,
  COMMITTED, CP14, CP15, CP16 or field PASS.
