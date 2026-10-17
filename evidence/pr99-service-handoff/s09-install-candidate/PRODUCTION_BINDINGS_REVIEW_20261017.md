# PR99 production-facing source continuation, offline verification only

Base: `fd74a0294a60e61b0432a6f64315fd4ea3d5063a`. Continues the same PR99
branch and original private production-start STATE. This packet supplements the
54-test offline mechanism packet; it is not a second ledger or production permit.
No historical host batch, source snapshot, stopped install or label is replayed.

## Actual source integrations completed in this patch

### Existing production_start.py

The actual helper now durably records each create, daemon-reload, start and owned
stop intent/result under its original one-use STATE. The STATE creation is synced
before mutations. A timeout, interrupted call, partial file write or missing result
write is UNKNOWN, not an automatic retry or compensating command that races an
in-flight systemd job. Known terminal failures use exact-owned-unit containment;
those stop operations are journaled too. Existing data and partial files remain.

The real helper checks TCP bind availability, rather than treating an HTTP timeout
as proof that a port is free. Success requires all three health results and active
supervised MainPIDs. An empty health sample after deadline expiry is rejected.

The real admission loader now binds the exact source-fence, final checkpoint and
canonical-writer receipt chain. Besides their independently approved raw hashes,
it requires the writer inventory/epoch, drained and fenced source, no unresolved
shared writers, bounded observation times, exact final-data hashes within the final
release, database integrity/schema identity and exclusive domestic assignment.
These are structural checks beneath the EXISTING root-held independent admission,
not a new authority. Fixture truth values cannot prove any real source was fenced.

The changed helper's default CLI always holds. Its only CLI operation is
`query-only`, which reads exact original-state records and unit state without
repair, stop/start, resume or replay. Recovery validates the exact forward and
owned-rollback operation sequence, rejects extra record fields/orphan results, and
rejects continuation or rollback after an unknown forward effect. A rollback PASS
requires the complete successful owned-stop sequence. Direct start invocation still requires the
new helper hash in a newly reviewed exact independent private admission. The old
stopped-only workflow is unchanged and cannot invoke this production helper.

### Existing RPC channel reused, not replayed

`production_transport.py` reuses the actual signer/HTTP implementation in
`aliyun-execution/s07_private_coordinator.py`, pinned to SHA256
`8bc8d13d9be01e2c695608ee975d30914eab9c7eda5144c8d7cba0051a3fa37a`.
An AST projection imports only its fixed RPC definitions/imports/constants. It
never imports the historical consumed batch, its main/remote functions, or its
environment-based credential initializer. The original file stays byte-identical.

The new adapter requires explicit RPC and STS credential dependencies. It is
restricted to the known domestic region/instance and the exact final-release helper
path. The generated bounded bootstrap checks host/root, each path component,
regular single-link file and exact reviewed helper bytes before calling start.
The helper must already be independently staged at
`domestic-final-v1/production_start.py`; this patch does not stage it or claim it exists.

A private persistent controller record is synced before RunCommand. At most one
RunCommand may be submitted in that transaction directory, even if its response or
InvokeId write is lost. Subsequent calls only DescribeInvocationResult for the
saved exact InvokeId. Identity checks also apply to pending results. Cached results
require the full fixed schema, exact source/operation/invocation bindings and allowed
terminal status; cutover/retry flags must remain false and business acceptance pending.
Unexpected fields or forged success flags fail closed before any RPC. Unknowns,
malformed outputs, wrong source/operation IDs and terminal command failures never
become success/no-effect assumptions. Only a bound three-app start receipt is
accepted; cutover or business acceptance is not inferred. Credentials and raw
remote output never enter the saved records. No workflow invokes this adapter.

Lost-response-before-InvokeId remains UNKNOWN and requires an independent exact
invocation lookup; no unsupported API query or blind resubmission is invented.
An ephemeral Actions workspace is not a durable controller store across runs.

### Final SQLite materials

`final_materials.snapshot_sqlite_fenced` reuses the S07 SQLite backup/integrity
mechanism on private copied files. It captures both source database and WAL while
a caller verifies an external fence before/after. SQLite connects read-only to the
COPY, not the source. It creates a separate standalone final DB, verifies integrity
and the approved schema hash, verifies original source bytes/file set unchanged,
and preserves captured/partial artifacts. Replay is rejected. No API/trading
request, real source DB connection or source mutation occurs.

The snapshot receipt remains a candidate. It does not issue a canonical writer
assignment or independently authenticate a fence. Schema/data selection still
belongs to the reviewed private inventory. The existing generic final-file and
route CAS helpers remain bounded offline mechanisms, not a selected live route.

## Actual verification

Python 3.12.14, local filesystem, 2026-10-17:

`python3 -B -m unittest discover -s evidence/pr99-service-handoff/s09-install-candidate -p 'test_*.py' -v`

114 tests PASS, 0 skipped (54 prior + 60 added). Compileall passes. Both changed
production entry CLIs return their explicit HOLD without dispatch. The original
stopped helper's manifest command still succeeds.

New coverage includes actual production-start code with real temporary unit,
intent, operation and receipt files; systemd and host identity boundaries are
mocked. Tests cover success, replay, each relevant timeout/partial write, failed
supervision, port occupancy, exact-owned rollback, foreign units and read-only
queries. The actual admission loader reads a full temporary 100-file final release
and all three bound receipts, then rejects a rehashed preliminary checkpoint.

The actual legacy RPC signer is exercised with an injected HTTP responder. The
new transport tests cover pre-dispatch persistence, no environment credential read,
no import-time HTTP, lost response/InvokeId, repeat/new operation rejection, pending
and mismatched identity, plain/base64 receipts, no credential persistence and an
end-to-end offline call into the real modified start helper.

Real temporary SQLite WAL tests verify a WAL-only committed row survives backup,
source AND captured main/WAL bytes remain unchanged, integrity is OK, and schema,
fence, source drift, timeout, replay and symlink negatives reject safely.

No real host, systemd/PID1, STS/SWAS, credentials, production database, real business
signature, nginx, DNS or external HTTPS was exercised. This is still not a whole
repository test result or production approval. Hosted CI for these new bytes is
pending publication; the previous 54-test hosted result does not cover this patch.

## Exact remaining blockers and incomplete bindings

The public, known start/RPC/SQLite bindings above are implemented and tested. The
following cannot be safely selected or manufactured from the public handoff:

1. Complete authoritative app/shared-data writer inventory, actual enforced source
   fence and drain evidence, final data/schema inventory, canonical epoch and
   reviewed assignment. The production fence/assignment adapter is still unbound;
   stopping only the three known units cannot prove other shared writers are absent.
2. Existing dedicated identity, complete effective runtime environment/permissions,
   approved private file/receipt hashes and pre-staged exact final release/helper.
   This patch neither creates identities nor grants persistent access.
3. Original independent authority's new exact full-action admission covering the
   changed helper, receipt contract, fixed transport and allowed containment. Old
   source approval and stopped-only permission do not cover these changed bytes.
4. A persistent private controller location and authoritative lost-InvokeId lookup
   within the existing execution channel. Ephemeral CI records cannot supply it.
5. Real signed business callback/bridge pin/HMAC and upstream acceptance inputs.
   The 12-stage coordinator's business adapter remains unbound, not auto-passing.
6. Exact live domain/route/current snapshot and ownership contract separating PR99
   from PR122, plus approved nginx validation/reload and HTTPS rollback probes.
   No live cutover adapter is selected, and existing website/current stays protected.

Completing these facts is necessary before the remaining fixed host adapters can
be bound and independently reviewed. Therefore the full migration pipeline is NOT
finished and this packet must not be reported as “all code complete, only quota or
approval remains.” It reduces concrete code gaps without guessing production facts.
Tokyo retirement, P2, Finance, trading and PR122 website deployment remain untouched.

## Workflow and source boundary

The entire 58-workflow audit from the preceding packet was compared against this
base's Git tree. Only the hosted PR99 verification workflow had changed; all cloud,
label-controlled and self-hosted workflow blobs remain identical to the audited
base. This patch only extends that existing ubuntu-24.04 test job's path filters;
it adds no production trigger, workflow dispatch, label, cloud secret or runner.
The changed source-manifest binding now includes production_transport.py. The
new production_start.py hash requires fresh independent review, not inherited PASS.
Canonical migration ledger/state are left to the existing sole writer to update.
