# P3 lifecycle / host-boundary isolated candidate (2026-10-30)

## Status

`SCOPED_LOCAL_CORRECTED_CANDIDATE` only. This is not installed, deployed, admitted, field
accepted, or connected to a real runner, ledger, Writer, outbox, provider, CI,
review service, or notification channel.

This correction was made in an isolated Git repository copied from the frozen
2026-10-30 candidate. The frozen source directory was not modified. It closes
the four defects recorded by the 2026-10-30 independent QA report plus the
completion-payload fence defect found by the 2026-10-31 independent QA rerun.

The candidate reuses, without modifying, the frozen inputs:

- P3 core ZIP SHA-256
  `34fda99283a3593daff6810f4c70b3d1b9d6afcee9c491a7030f6195e2ae0252`
  (historical scoped review: 48/48 on Python 3.12.14 and 3.6.8).
- Host-wiring successor ZIP SHA-256
  `d41d80623bf4e5017a277affcd5937e79ecdfa0615de7c1bf02943c4e9e2aa93`
  (historical scoped review: 13/13 on both runtimes).
- Handoff transport ZIP SHA-256
  `fdfb2baa971ea90694aef75c88b1d926b0fad51ea327ec4ab03d4ab1f4c982b5`.

No prior source is copied or silently rewritten. `src/p3_host_boundaries.py` is
the sole source increment and is intended to sit outside the frozen core until
independent review and a real host integration task approve the exact callsite.

## Preflight / no-duplicate result

Before authoring, the workspace was searched for the candidate name, frozen P3
archive names, key provider events, and receipt-provider/runner-adapter symbols.
No existing duplicate implementation or candidate directory was found outside
the handoff ZIP. Process inspection did not establish a P3 writer. One unrelated
root-owned `/opt/xuanjun-cloud-connection/.../lifecycle` process existed; it was
not inspected, interrupted, or treated as P3 authority.

The authoritative P2/P3 runner, canonical ledger/activation identity, task and
attempt, remote/source Writer state, and transfer-of-execution receipt remain
`UNKNOWN`. Therefore this candidate does not launch, resume, inspect, or stop a
real worker and makes no `STARTED` claim.

## Sole independent gap closed

The additive module defines and locally tests these fail-closed host contracts:

1. `TrustedReceiptProvider` and checksum-bound immutable receipt envelopes.
2. `RunnerAdapter.launch/resume/inspect/stop`; every effectful method returns an
   opaque reference to trusted evidence, never a caller assertion.
3. Separate runner ACK and STARTED paths. ACK explicitly carries
   `started=False`; only a bound STARTED receipt can call the original
   `ExecutionSupervisor.accept_started` API.
4. Exact progress and stop readers compatible with the frozen `P3Ledger` shapes.
5. Exact test/CI/QA/security/business readers bound to one commit and artifact,
   with distinct author/QA/security identities.
6. `OutboxTransport.send/lookup/ack` boundaries. Send/ACK uncertainty remains
   HOLD; lookup must match the original binding, opaque notification ID and
   attempt nonce. No redial/retry is authorized by the wrapper.
7. A completion reader that adds the exact current fence/run/session/resume/
   epoch/generation lineage required by frozen `reconcile_completed`.
8. Pure watchdog classification separating START timeout, progress stall,
   result missing, UNKNOWN side effects and completion recovery. It performs no
   ledger transition and no retry; the original core remains authoritative.
9. STARTED payload fence must equal the receipt subject fence before the frozen
   supervisor is called; completion acceptance and recovery subjects must match
   across the complete run lineage.
10. Once runner launch/resume or outbox send has been invoked, any missing,
    malformed, tampered or wrongly bound returned receipt is an explicit
    no-retry HOLD, because the effect may already have occurred.

## Admission and safety invariants

- `execution_enabled=False` and `notifications_enabled=False` are constructor
  defaults. Disabled execution fails before adapter invocation.
- Each possible side effect re-reads exact, time-bounded admission containing
  actual P2 acceptance, explicit P3 release, unique Writer, execution authority,
  and the same task/spec/artifact/run/session/fence/epoch/generation lineage.
- Notification calls additionally require independent notification authority.
- Admission or receipt reader errors become a closed error/HOLD, never success.
- An adapter exception after invocation is `UNKNOWN_*_HOLD`; it is not retried.
- A returned but unverifiable runner ACK is also
  `UNKNOWN_RUNNER_EFFECT_HOLD`; a returned but unverifiable send receipt is
  `UNKNOWN_NO_REDIAL`. Neither result authorizes redial.
- STOP evidence requires writer and descendants stopped plus effects NONE/KNOWN.
- Completion recovery requires full acceptance plus a separate immutable current
  recovery-lineage receipt. The caller must invoke frozen
  `P3Ledger.reconcile_completed`; this increment never fabricates DONE.
- This candidate creates no DB, WAL, task registry, scheduler, daemon, service,
  cgroup, credential, endpoint, timer, model call, external message, or approval.

## Exact integration mapping (not executed)

After real P2/P3 admission and independent review:

- Inject one host-authenticated `TrustedReceiptProvider` backed by immutable
  receipt storage. Request/user bodies must never select the provider or supply
  `verified=True` as authority.
- Construct `EvidenceReaders`; pass `progress`, `stop`, and phase-appropriate
  `acceptance`/`completion` into the already-admitted frozen `P3Ledger` through a
  host callback that reads the current supervised status. Do not create another
  ledger or select recovery mode from request data.
- Construct `RunnerController` around the approved existing runner. For resume,
  pass the frozen supervisor's `validate_launch` immediately before the native
  call. Persist original dispatch/admission first. Treat returned ACK as only
  `ACKNOWLEDGED_AWAITING_STARTED`; later consume a separately persisted STARTED
  receipt through `accept_started`.
- Feed `inspect` evidence into the original supervisor observation path. Feed
  STOP evidence into `P3Ledger.reconcile_stopped`, then use the original Owner
  approval and frozen resume chain. Do not turn STOP into resume authority.
- Adapt outbox results only into the frozen original claim/send/lookup/ACK
  transaction. This module never marks the canonical outbox directly.
- Run `WatchdogClassifier` from the existing short-lived mechanical watchdog;
  apply transitions only through the frozen ledger/supervisor methods.

## Reproduce tests

From workspace root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s deliveries/p3-lifecycle-candidate-20261030/tests -v
```

Observed locally: Python 3.6.8, 21/21 PASS. A Python 3.12 executable was not
present in this environment, so this new increment has no current 3.12 rerun.
Historical core/host results are not relabelled as tests of this increment.

For this corrected isolated repository, run the supplied suite and the added QA
counterexamples separately:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest -v tests.test_p3_host_boundaries
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest -v tests.test_p3_qa_counterexamples
```

Observed locally on Python 3.6.8 after the second correction: original supplied
suite 21/21 PASS, the existing four QA counterexamples 4/4 PASS, the new
completion-fence counterexample 1/1 PASS, and combined discovery 26/26 PASS.
The positive completion fixture was aligned so its receipt subject carries the
expected current fence; its test expectation was not changed. These are
Writer-local isolated tests, not
independent QA, security, Hosted CI, install, field execution or acceptance.

## Remaining external blockers

Real P2 field acceptance; explicit P3 release; active descriptor/journal and DB;
actual imported source identity; authoritative task/spec pins; sole Writer and
old-writer stop evidence; approved runner launch/resume/inspect/stop API; real
ACK/STARTED receipts; trusted progress/stop/test/CI/review readers; host
watchdog/cgroup controls; real outbox transport lookup/ACK; two consecutive real
tasks and same-artifact gates all remain pending/UNKNOWN.

See `B7_ENTRY_GATE.md` for B7 dependency-only documentation. No CP14/15/16 code
or operation is included.
