# Canary evidence coverage — V2.7 1.15 source preparation

WORK owns scope PR17 comment6136253099. This pure function consumes normalized
receipts from the existing acceptance machinery; it never runs tasks or gates
deployment. Caller authenticates each receipt, binds run/evidence to the exact
source commit and artifact SHA256, verifies independently reviewed runtime logs,
and checks policy, freshness and current activation before any real decision.

Required cases: two task E2Es, duplicate event, worker failure, restart recovery,
old writer rejection, unknown-effect HOLD, outbox ACK, authenticated dashboard,
rollback. These are coverage categories, not a substitute for each detailed
Stage1/security scenario in Issue19 and the Owner operations plan. A PASS for a
negative case means the expected refusal/HOLD/recovery was actually observed.

Receipt keys are exactly case, commit, artifact_sha256, evidence_sha256,
environment, status, run_id. Only environment=UK_RUNTIME and status=PASS with
valid digest/run reference count. HOSTED_CI, FIXTURE, UNKNOWN, absent cases,
wrong versions, malformed input and any duplicate case yield HOLD. Caller must
reconcile retries into one authoritative receipt per case, retaining old evidence
outside this projection. Failure cannot be masked by appending a successful copy.

COVERAGE_COMPLETE is only caller-supplied receipt coverage. It does not validate
signatures, inspect logs, prove execution or imply independent release approval.
All output grants are false. Fixtures intentionally demonstrate shape acceptance,
not UK PASS. Source development is independent; activation is blocked by P2 and
Stage1 dependencies. Independent QA/Security/Release and UK acceptance NOT_RUN.
