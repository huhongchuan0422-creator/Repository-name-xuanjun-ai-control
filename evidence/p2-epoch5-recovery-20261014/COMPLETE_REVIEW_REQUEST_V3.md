# P2 epoch5 v3: single consolidated independent recovery review

This is a new one-attempt candidate for the SAME P2 transaction after consumed approval 6167552232 terminated in HOLD. No installation has been performed for epoch5. Developer is dot; independent reviewer remains ChatGPT Native Task5. This document requests review; it does not grant approval.

## Exact frozen inputs

- Candidate source: `2077f4bb24654904ac950e677efa538ce4f627a6`
- Source tree: `fffd3ed502a9087ba431e7724774760381a434ce`
- Folder: `evidence/p2-epoch5-recovery-20261014/`
- Archive: `epoch5-recovery-kit-v3.tar.gz`, 264661 bytes
- Archive SHA256: `9c186c8d9788ff12307bc95362d00a9315ba8f18d899c8e41fa4e45a51a5e4c0`
- Kit manifest SHA256: `48d4b86f48aaa3440ac8744a9e0fe99dacf4cddc1050777a7911c9a71fd89180`
- Entry SHA256: `ce7aae1b452519f6bf195c9566e37d77dce80b5518b40c10634ea38ecef3387a`
- Runtime manifest SHA256: `3332a6e63b11b75420f1bd0f1a264c89528a92a771f6bc1399f2a38009f324ef`
- Compiled plan SHA256: `949dee6ed4d1a1c271f584bd995f61da238aa92171974ec05bc23bfa930465e2`
- Latest Owner UK read-only snapshot SHA256: `0efce6f1a662c0f275db02c7114ed7ed4d43d95ffbbbc1b402f053669862dc9f`
- Files: 148 regular, 11 directories; 22 helpers, 19 test modules, 102 runtime files.
- Archive also supplied as `epoch5-recovery-kit-v3.base64.txt`; its readback exactly matched local archive encoding.
- Runtime provenance is `bb6ed0d40eabbb535623b0a5341cddedc9b9e38a` / tree `5c18914a59172d9a005dafaae3d4c86701240210`. This is the runtime-only TLS delta source, distinct from the final recovery helper candidate above.

## Why recovery is required

The prior attempt issued the real certificate, then entered Certbot renewal dry-run. Certbot 1.22.0 internally slept 261.68085359228326 seconds; the enclosing 240-second command deadline expired. Terminal HOLD retained the certificate and resources; Activation was fenced to PREPARED epoch5. Six cleanup observations completed. Earlier approval is consumed and cannot authorize this attempt.

The new TLS runtime uses `--no-random-sleep-on-renew` in both normal renewal and staging dry-run. UK parse-only checks independently exercised both modes without ACME calls. Timeout diagnostics are now durable and bounded. This candidate reuses the issued certificate and performs only a staging renewal dry-run; it does not invoke certonly, force renewal or reissue the production certificate.

## Finite recovery scope and failure boundary

1. Verify exact kit, source, original plan, new compiled plan, fresh independent approval and live host snapshot under the existing installation lock.
2. Validate retained NSS/RPM/bootstrap/publisher resources, original and retained release sources, original database/WAL/SHM set, backup/generation, legacy isolation, process/cgroup/scheduler/Runner exclusion and private references.
3. Create a NEW exclusive epoch5 attempt receipt; preserve all earlier attempts and evidence. Stage only the new exact runtime release. Rebind the existing PREPARED epoch5 identity to PREPARED epoch6, then quiesce it.
4. Preserve and verify the issued certificate; perform controlled dry-run and exact 24-target provisioning, plugin binding, sandbox/ledger access and boot preparation through the existing reviewed interfaces.
5. Activate only after database/cutover and runtime binding checks; perform pinned postchecks. Real production and business E2E remain separate independent acceptance.
6. On any failure, fence first, independently attempt every stop/verification/boot/mask recovery group, persist individual evidence, retain side effects, enter HOLD and forbid automatic retry.

Failure policy remains `FENCE_STOP_RETAIN_NO_REPLAY`. It is NOT full rollback and may require manual reconciliation. Existing Owner acceptance is PR58 #6167524365. If reviewer considers scope materially changed, state that before approval. Never restart legacy writers, replay historical Telegram notifications, delete the original database/receipts, rerun old isolation or reuse consumed approval.

## Newly closed preflight mismatches

- v1 UK 191/191 tests passed, but full preflight failed on native bootstrap publication identity. The prior attempt had legitimately rebound native binding. v2 recognizes only the exact original journal row and exact observed root-owned current binding metadata/hash; other six rows retain original requirements. Independent original-to-current transform remains mandatory.
- v2 UK 64/64 affected checks passed, but full preflight rejected bytecode in the retained prior release. Grouped Owner read-only diagnosis found exactly 13 smoke caches, all equivalent to compilation of verified retained source and stable across repeated inventory. All remaining grouped host gates completed without a reported blocker.
- v3 accepts ONLY these 13 pinned paths/hashes on the exact retained release. It performs FD-anchored fail-closed recursive inventories before/after, exact source/rendered inventory comparison, ownership/mode checks, Python3.6 header/source timestamp+size verification, full code-object equivalence and exact original staging identity. It never imports, executes, deletes or rewrites caches. Extra/missing/changed/link/race/unreadable files fail closed.
- The previously reviewed original release's separate 13-cache validation remains intact. New staged package disallows bytecode entirely.

## Evidence categories (do not add overlapping counts)

- Current source local CPython3.6.8 aggregate: 212/212 PASS.
- Final packaged-file CPython3.6.8 aggregate: 212/212 PASS, 2.122 seconds.
- New cache-specific tests: 16, included in 212.
- Final UK affected checks: 80/80 PASS, 2.336 seconds, bound to kit 48d4…9180.
- Final UK complete verify-only: PASS, epoch5, plan 949d…65e2 and snapshot 0efc…dc9f, NOT installation admission.
- Previous UK 191/191 and 64/64 are historical, not additional distinct final tests.
- GitHub CI for this candidate: NOT_RUN. UK Runner remains isolated; no CI result is claimed.
- Real ACME renewal, installation, notification ACK, HTTPS/dashboard and full P2/P3 E2E: NOT_RUN/PENDING.
- Two local builds produced byte-identical archive.
- Developer offline archive, Git blob and original/new102 comparison passed.
- Developer offline old/new24 target, three plugin, Activation/TLS and compiled-plan reproduction passed. Reviewer must independently execute; developer reproduction is not independent approval.

## Independent reproduction without production access

All aids below are for a reviewer sandbox, NEVER the UK host. Inspect them before execution.

1. `verify_frozen_kit_offline.py` is data-only. It does not extract or execute archive code. Use binary or the base64 companion; provide the exact candidate Git tree JSON and original manifest. It checks all 148 file bytes, 22 helper/19 test/entry Git blob correspondence, runtime102, 100 unchanged+two pinned runtime repairs, permissions and provenance.
2. `reproduce_plan_offline.py` runs only four pinned helper definitions and the pinned pure identity renderer in a temporary sandbox. No host driver/installer/main/services/network. Inputs are the old archive, new archive and original plan. It rechecks old/new102, old/new24 rendered targets, three plugins, Activation/TLS and the exact compiled-plan SHA.
3. Old original archive and manifest references remain in commit `2ba30d06d6eac206d0f4ad4052270f265b29323c` under `evidence/p2-install-preparation-20261013/original-102-runtime-archive.base64.txt` and `original-runtime-manifest.review-reference.json`. Verify old archive SHA `c2d593d662fbce4a0c2fa454cc4a18dbec327c0bd0bf3d6d72849d9a5a79970d`, old manifest `9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3`.
4. The historical original-plan material is in original PR58 review request #6159620928, already independently authenticated in #6167232965 and reproduced in #6167494542. Original plan is 22468 bytes, SHA `ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a`. Retrieve through the reviewer's existing authorized source. This submission does not republish private plan contents or credentials.
5. Detailed UK operational inventory is retained privately; the public grouped summary deliberately omits private host paths, database hashes, service inventory and scheduler fingerprint. The public final receipt contains test/version/snapshot bindings. Report any genuinely necessary evidence-access limitation in this round, rather than claiming an independent reproduction that was not performed.

## Requested complete decision

Review the full modified helper/runtime call chain and all affected failure paths, not merely the latest diff. Reuse unchanged independently passed original102/installer/containment portions, while checking new integration and boundaries. Concentrate all confirmed defects, evidence gaps and capabilities unavailable in this round, with severity, exact code, repair and acceptance conditions.

Either issue one fresh exact-version approval after all required checks, or a single consolidated HOLD list. Do not split one known scope into serial piecemeal reviews. This candidate is frozen; changed bytes require rebinding and appropriate affected checks.

The independent reviewer, not the developer, must issue any machine approval. Format is specified by `epoch5_approval.py`: marker `CHATGPT_NATIVE_TASK5_EXACT_EPOCH5_RECOVERY_ACCEPTANCE` followed by exactly the JSON returned by expected(plan_sha, kit_sha, runtime_sha, snapshot_sha), with the four exact values above. Decision is `APPROVED_ONE_EXACT_EPOCH5_RESUME_WITH_FENCED_RETAIN_ON_FAILURE`; expected epoch5, proposed PREPARED epoch6, authorized_attempts1. Account provenance authenticates the repository account; the process must still establish reviewer independence.

Even after approval, the entry re-reads the real GitHub comment and verifies author, body hash, exact bindings and live snapshot. Unknown drift or consumed attempt must HOLD. No production command is authorized by this review request itself.
