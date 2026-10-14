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

## Retained provisioning and receipt preservation implementation

Added epoch3_preserve.py: exclusive protected archive, byte-pinned copies of six
historical receipts, preservation of the empty TLS tree and original TLS journal,
with fsync and evidence retention on partial failure. Eight local Python3.6.8
root-mapped filesystem tests PASS. No production paths were modified.

Added epoch3_retained_runtime.py: validates all24 prior target bindings, prepares
new TLS binding, records a new provisioning attempt, applies TLS and target files,
and installs the exact plugin without replaying RPM/NSS/bootstrap/publisher work.
Generic restore and prerequisite replay/removal are explicitly rejected. Eight
local Python3.6.8 fixture orchestration tests PASS; these mock host effects and
are not UK integration evidence. Failure policy is FENCE_STOP_RETAIN_NO_REPLAY,
not a claim that the full previous environment can be automatically restored.

Still incomplete: concrete admission/approval and full preflight, release staging,
native binding update, activation/service containment and postchecks must be wired
and tested as one driver before the consolidated independent review. No new
production recovery is approved or executed by this checkpoint.

## Window handoff checkpoint 2026-10-14 09:05 UTC

Saved epoch3_host_preflight.py (12 local Python3.6.8 fixture tests PASS) and
 epoch3_service_containment.py (11 local Python3.6.8 fixture tests PASS).
The preflight composes retained state, exact old release validation, retained NSS,
old/new process exclusion, reviewed scheduler/cgroup scans, copied DB manifest
checks, activation journal and before/after comparisons. It has NOT run on UK.
Containment attempts every fixed-unit stop even when an earlier stop fails, then
separately observes all process/cgroup states. Host-effect calls are mocked in
these tests; successful unit tests do not prove production containment.

This is preservation of incomplete work for a window change, NOT a review request
or installation grant. No executable complete recovery CLI exists yet. Remaining:
exact approval verification, protected release staging, native binding CAS, actual
activation/service wiring and post-install checks, complete integrated fault
injection, UK read-only verification, then ONE consolidated independent review.
Do not use old install/resume commands; both previous approvals were consumed.
The local writer will stop after committing and writing the PR17 handoff. UK and
other windows' live writer states require fresh observation; no lease was granted.

## Concrete recovery kit implemented, 2026-10-14 09:29 UTC (not approved)

Owner resumed this same Dots writer; PR17 continuation6164984803 supersedes the
window-stop checkpoint6164978196. No other source writer was started here.

Added complete candidate loader and HostDriver wiring: exact new PR58 approval,
original private plan recompilation, existing install lock, fresh full host
preflight, exclusive attempt, exact release staging, historical evidence
preservation, PREPARED3->4 journal rebind, native binding CAS, fresh TLS reference,
quiescence, retained provisioning, database access, activation, service startup,
original exact postchecks, and fence/stop/retain failure containment. No default
resume or automatic retry. New approval marker and policy deliberately cannot
match the two consumed prior approvals. Kit loader verifies all helpers/runtime
files before importing them. Test-only and verify-only do not grant installation.

The original native binding mode was confirmed from Owner evidence as0644; CAS
preserves this identity and privately backs up bytes. Fixed preservation receipt
newline and new provisioning file-digest newline during integration checks.
Missing not-yet-installed units require explicit systemd not-found/inactive/dead
and empty cgroups; generic query failures remain rejected.

Local Python3.6.8 aggregate160/160 PASS. Actual candidate installer staged all102
files into a temporary local release and all six --help smoke invocations passed.
The packaged test-only entry also ran160/160 PASS under local isolated Python3.6.8,
with only fixed hostname/kit location adapted to a temporary test directory.
Host effects/GitHub in driver integration are mocked; ActivationStore and durable
attempt journals use real temporary files. This is not UK acceptance. An initial
aggregate invocation omitted required test environment variables (14 errors);
corrected invocation passed, and the failed log is retained locally.

Two independently built archives matched byte-for-byte:
archive SHA256633c83a5bb608e040c1811aaac70f3dabd2ff9b8d10265046296bcee409aa53d
kit manifest SHA2560adcefaaad639a7fa70f69e57d21f1375aeeef15a30a3921e39ba7a17748a3a3
entry SHA2564aa0acb554978a79b2abe87b78f29d74f1e3901349a96670727030fdcacd6d43
private compiled plan SHA2560966ab156508228670faaadbba97ff62e19dac8451cced3598eda4eb0bea7f76
The kit has19 helpers,17 test modules,102 runtime files plus provenance/manifest.

Still required before ONE full review: UK test-only and fresh verify-only snapshot,
complete exact-version review packet and Owner commands. No resume approval exists.
The old install receipt remains historical HOLD; the new protected
transaction/epoch3-recovery-execution.json is the new attempt receipt. It must be
read with the historical receipts, never silently interpret the old HOLD as new
success. Production acceptance stays PENDING even after new postchecks pass.


## Complete pre-install chain audit and final failure-containment increment

Owner first-kit UK receipt SHA256 e0864a402a7a62dcfd76812456b0aacc59ffd7e60c4c1ce9b4b9b66a8c49d25c:
Python3.6.8 160/160 PASS; full verify-only PASS; snapshot
e297a8db0b4f2e2641ee3aeb6c94119a7ec5034a50a44a0e93723c996205df4e.
This receipt binds the first kit, not the final increment below.

Complete-path audit found and fixed missing failure restart inhibition: restore
previous boot enable states and remask both original Owner endpoint units, in
addition to existing Gateway/coordinator mask restoration. These three cleanup
operations are independently attempted; failures are UNKNOWN/HOLD. Read the
pinned original provisioning receipt even when preservation failed before archive
creation. Validate both current Owner unit bytes before replacing either.

Final local Python3.6.8 aggregate168/168 PASS; final packaged affected-only34/34
PASS. Real local installer staging and six help-smoke checks PASS; all24 staged
source hashes and fully rendered targets match the private compiled plan; all3
plugin references match; activation dispatcher and TLS config match. Native
ledger-client target bytes are unchanged so its retained native binding hash is
still valid. These are local checks, not production acceptance.

Final reproducible archive SHA256:
a9c6bb2fa9bfc0114256216a6c15fe2dde241b28174e633f118e5000052524d8
Kit manifest:89eb2624d3aaee99117e6292f547852a61cce88d119cbb0fab57e0539c8aed5b
Entry:0152ae2b5f2bef0063175b25d1db0991845d6b9d17ba364f0dbb05280cde3fef
Runtime and compiled plan hashes unchanged. Existing UK160 tests are retained;
only final34 affected tests and full fresh verify-only are requested next.
ONE independent full review follows that final receipt. No piecemeal approval,
no current production recovery authority, no production execution.
