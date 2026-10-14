# Epoch 3 failure repair preparation — no install admission

The one resume approved in PR58 6161965867 was executed and failed. It is consumed.
Actual Owner evidence now reports PREPARED epoch 3; install and recovery HOLD;
rollback records only ACTIVATION_FENCED_EPOCH_3 and LEGACY_MASKS_PRESERVED.
Full provisioning rollback did NOT complete. PR17 failure checkpoint: 6162038229.

## Proven causes

1. UK Certbot 1.22.0 CLI parameter parsing rejects `-c /dev/null` with exit2,
   `File not found: /dev/null`. This was reproduced using ONLY
   cli.prepare_and_parse_args, not main/issuance; config/work/logs are empty.
   Standalone plugin is present. Do not blame DNS/ACME connectivity without evidence.
2. Original provisioning records dropin_parent_created before effects, but mkdir
   is after TLS. A TLS failure before mkdir therefore causes restore to throw
   HOLD_GATEWAY_DROPIN_DIRECTORY_MISSING. The field represents intent, not proof
   that mkdir happened. Original stderr was discarded, hiding the first cause.

## Implemented source repairs (not deployed)

- TLS lifecycle uses its own empty, regular, root0600 client.ini under the protected
  root0700 TLS directory. Create once with EXCL/NOFOLLOW and fsync. Issuance and
  later renewal both validate the same empty private file, never /dev/null and
  never unspecified system configuration. Missing/nonempty/aliased/loose config
  fails closed. This is a runtime repair, not an installer-only substitution.
- Failed command exit status, output digests and bounded outputs are saved in a
  private0600 TLS diagnostic receipt, not exposed in public logs. TLS directory
  fingerprint traversal now propagates scan errors instead of skipping them.
- A missing planned drop-in directory is accepted as a no-target-effect rollback
  state only if every provision target still matches authenticated previous bytes,
  ownership/mode or original mask/absence. Installed/drifted target + missing
  directory remains HOLD. Never create the directory to bypass the gate. Existing
  protected created directory keeps the original safe-removal validation.
- The existing tls_completion_overlay emits both repaired runtime modules; no
  new workflow, database or queue is introduced.

## Developer tests (separate from UK)

- Python3.6.8 isolated root namespace: config/diagnostic/fingerprint tests 13 PASS;
  exact generated rollback-helper AST partial-effect tests 12 PASS.
- Local system Python lifecycle regression 10 PASS (NOT a Python3.6 claim).
- Local Python3.6 original lifecycle suite crashes in the known ctypes environment
  problem during activation import; not a PASS. New UK full lifecycle testing is
  required. Helper AST tests alone do not establish full restore integration.
- Amended overlay was applied to the reconstructed actual pre-TLS input; emitted
  runtime helper bytes matched the tested source. No UK mutation or certificate
  request was made by these tests.

## Existing evidence remains protected

Install receipt SHA49cb3537b6d23419a670e2f5c0a73c34cf7cfea98f449b5bec6ef25179e1449b.
Recovery receipt SHA76de78cdd58e899bcb40b79162c8c44c4785cc13a88b541f5d850fe97181a766.
Activation SHA4f8f6f218a7f62b203a2961dffdeaec6d1bcf6d9f24f78fae7fccc2581b834cd.
TLS receipt SHAdd9de0ad6a64c25da4a60f48912a931de1f3b5d26c1c9445aa73cce70fb67340.
TLS fingerprint bbc70877d483a6ceb9ac6db79a7ecf4fbb465534f91018341bb4dbaa890e83ec.
Provision SHAb106258604fc7423786e18d46d249ef9826f8cd8c0eb29ed580c968bdbe8e3f0.
Bootstrap SHAab9386e0068796a7290847647c77242b7c83b88117e3036ca20998661c250cda.
Publisher SHAdde7083c8141d254eb254d90b4d442d8da31678995ce7aa21188e279cb4e5da8.
These are observations requiring fresh reconciliation, never permission to overwrite.

## Still required before ONE full independent review

- Reconcile all partially provisioned RPM/bootstrap/publisher objects and 24 target
  states against their durable receipts, plus complete old/new service isolation.
  Keep source DB, staged generation, backup and canonical queue; no second DB.
- Build and bind the corrected runtime candidate. Two runtime files change, so
  the original102 approval is reusable evidence for unchanged files only; old
  manifest, rendered identities, activation descriptor and admission must NOT
  silently pretend those bytes are unchanged.
- Define one exact epoch3 reconciliation/resume transaction: preserved prior
  failure evidence, durable single-attempt record, no replay of completed resource
  creation, bounded activation/release rebinding while inactive, authenticated
  rollback/retain policy. A simple epoch2-to-3 constant edit is insufficient.
- Include persistent renewal repair, actual-package integration and failure-path
  tests, compatible UK tests and fresh host snapshot, precise Owner command and
  failure procedure in the SAME review packet. No partial approval requests.
- Only after new independent exact approval may Owner execute; any drift/unknown
  effects enters HOLD. No automatic retry, NSS cleanup, package erase, credentials
  replay, legacy writer restart or historical notification replay is authorized.

CURRENT_STATUS=SOURCE_REPAIRS_IN_PROGRESS_NOT_INSTALLABLE
PRODUCTION_RESUME_RETRY=FORBIDDEN_PENDING_NEW_COMPLETE_REVIEW

## Finite activation rebind primitive (offline tests only)

A recovery-only helper now uses the existing ActivationStore journal and lock to
append an exact PREPARED epoch3 -> PREPARED epoch4 release identity change. It
preserves database path, generation, ledger UUID, instance, socket and binary hash.
It requires caller-bound snapshot/approval/plan and old/new descriptor hashes,
plus live exclusion/installation-lock/resource proof; it does NOT itself verify
GitHub approval or measure host gates. Production caller wiring is still required.
No ACTIVE grant or new ledger is created. Failure after durable append but before
descriptor publication leaves journal/descriptor mismatch and rejects retry.
13 tests PASS on local system Python. The local Python3.6.8 interpreter exits139
before test output on ActivationStore import; Python3.6 execution is NOT PASS.
This helper has never run on the UK host and is not independently approved.

## Single-attempt sequencing (driver wiring still pending)

The recovery sequence verifies approval before and inside the existing install
lock, binds a fresh preflight snapshot, consumes an exclusive durable attempt,
and records INTENT/COMPLETE around each effect. Failure fences activation, stops
only new allowed services, then requires verified stopped state before preserving
legacy masks. Failure retains prerequisite/bootstrap/publisher/database resources;
no generic full runtime.restore or retry. Failed containment is UNKNOWN and remains
HOLD; receipt-write failure is separately reported.11 local Python3.6.8 sequence
fixture tests PASS, including failure injection at all9 phases. These injected
operations do NOT prove actual host driver integration, which remains unfinished.

## Local compatibility blocker resolved; retained-state/journal implementation

Rebuilding the local CPython3.6.8 extension modules with CFLAGS=-O0
-fno-strict-aliasing restored ctypes and uuid imports. No UK Python/server changes
were made. The existing local math-symbol toolchain compatibility patch remains;
this local build is not asserted byte-identical to UK Python. Re-ran the13 actual
ActivationStore rebind tests and10 actual delta-package TLS tests under this local
Python3.6.8 successfully. Earlier exit139 remains historical, not erased.

epoch3_retained_state.py now concretely reuses the fixed-host collector and full
publisher verifier, rejects all mismatched retained states, binds the old native
bootstrap bytes and computes new binding bytes in memory, then rechecks pinned
receipts. No secret bytes are printed.13 local Python3.6.8 validation/rejection
tests PASS using the supplied Owner observation; portable synthetic fixtures also
exist. The complete host capture has not been run on UK as a single combined gate.

epoch3_attempt_journal.py implements the exclusive durable attempt in the EXISTING
transaction directory. It rejects existing attempts, uses fsync and atomic receipt
updates, rejects stale/unclaimed updates, and preserves uncertain files on write
failure.10 root-mapped local Python3.6.8 filesystem tests PASS. This is not a second
task queue. It still requires the full recovery caller to hold the install lock.

Remaining: wire actual retained provisioning, TLS transaction preservation,
activation and service operations, exact approval and full host preflight into
one concrete entrypoint; validate full integration before consolidated review.
