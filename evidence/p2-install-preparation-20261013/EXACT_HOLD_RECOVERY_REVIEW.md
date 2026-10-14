# P2 original transaction recovery candidate — independent review required

The Owner's first admitted install failed after LEGACY_QUIESCED. Seven deployed
release inputs are correctly identity-rendered by the original installer, but
the provisioner compares them with unrendered package hashes. All seven observed
UK hashes were reproduced with the original renderer from artifact 11865804223.
The attempted prerequisite rollback then refuses its own retained generation,
database backup and activation evidence. Original canonical DB hash is unchanged.

This additive recovery executor changes no original package/manifest/plan bytes.
It verifies all 102 original payloads and their deterministic installed bytes,
then supplies raw original inputs ONLY for the exact provision source paths.
The deployed source is rechecked when read; target/backup/receipt reads retain
their original behavior. All 24 real plan bindings render to their reviewed hashes.

It admits only the exact original HOLD, existing STAGED cutover and fenced
epoch 2 PREPARED identity. Original canonical DB, backup, generation, epoch log,
prerequisite receipts, masks, scheduler baseline and process/FD inventory must
reconcile. Existing NSS, binaries, directories, release and staged DB are reused;
none is recreated, restaged, overwritten or deleted to make a check pass.

verify-only has no installation admission and acquires the existing install lock.
It reuses original runtime preflight with two bounded replacements: verified
existing prerequisite identity instead of first-install absence, and fresh old
unit quiescence instead of first-install absence of already-staged DB files.
Unknown state, sidecars, concurrent holders, scheduler drift or another attempt
remain HOLD. Scope outside the measured control realm remains UNKNOWN.

resume requires a NEW independent comment starting exactly with
CHATGPT_NATIVE_TASK5_EXACT_HOLD_RECOVERY_ACCEPTANCE followed by the strict JSON
object enforced in approval(). Its code hash and snapshot hash must match.
The first-install approval 6160188919 cannot authorize this recovery. Duplicate
attempts are refused. The original HOLD receipt is preserved before changes.

The recovery transitions epoch 2 PREPARED → QUIESCED → ACTIVE through the original
ActivationStore. It executes reviewed provisioning and runtime activation, then
the hash-pinned original complete_install_executor.py post_install_checks, including
actual NSS/services/ACME renewal dry-run/HTTPS certificate and auth boundaries.
Success is postchecked installation only; Relay/Outbox/model E2E/P3 remain PENDING.

Failure fences again and contains any activation prefix, restores returned
provisioning when safe, preserves legacy masks, retains prerequisites/data and
records HOLD. An uncertain provision/inner restore is not blindly rerun. No
successful full NSS rollback is claimed. There is no independent public rollback
CLI in this candidate; bounded failure rollback is integrated into resume.

Developer tests: 13 isolated tests PASS, including real renderer/provision binding
integration, file drift/symlink rejection, hold/version/epoch negatives, old-approval
rejection, actual ActivationStore transitions, provision/activation/postcheck/nested
restore failure, evidence retention and duplicate-attempt denial. These are local
developer tests, NOT independent QA, UK recovery acceptance or production PASS.
Python 3.6 syntax parse: PASS. No paid model calls or host deployment performed.

Reproduce after extracting ORIGINAL artifact 11865804223 and decoding the original
22468-byte plan from PR58 comment 6159620928:

    P2_SOURCE_ROOT=/absolute/xuanjun-p2-package \
    P2_ORIGINAL_PLAN=/absolute/protected-core-install-plan.json \
    python3 -B evidence/p2-install-preparation-20261013/test_recover_exact_hold.py

Before approval, reviewer must assess the recovery admission, no-replay semantics,
retained prerequisite policy, source shim, exception/fencing/partial-effect paths,
and UK verify-only snapshot. No production recovery command is approved yet.

Canonical task/transaction/PR17/PR58 remain unchanged. Runner remains isolated.
No new task queue, approval binding push or installation workflow is created.
