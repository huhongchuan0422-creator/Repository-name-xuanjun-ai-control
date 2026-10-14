# P2 epoch5 v4: single consolidated independent recovery review

This is a new one-attempt candidate for the SAME P2 transaction after consumed approval 6167552232 terminated in HOLD. No installation has been performed for epoch5. Developer is dot; independent reviewer remains ChatGPT Native Task5. This document requests review; it does not grant approval.

## Exact frozen inputs

- Candidate source: `66bc77d05fd32df7f932d23cb879456e02cf13d2`
- Source tree: `c3ac139fb3c69e6826c41a10abc847d999b09f07`
- Folder: `evidence/p2-epoch5-recovery-20261014/`
- Archive: `epoch5-recovery-kit-v4.tar.gz`, 267336 bytes
- Archive SHA256: `8b69ec24d3f55b7010cfd98c2982b7b55a4d1b5ce27f3bb2d3c012313ab8d075`
- Kit manifest SHA256: `12ec5e711b4a7de865e44323b887fefbac6cc7954d13609e58b7137bd34374e1`
- Entry SHA256: `c88330b7d7a685a049e43e29cd0413336255a34df8db4ae46f6fb4cc1acc24e6`
- Runtime manifest SHA256: `153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7`
- Compiled plan SHA256: `5938dad82a8597f8ac18af078843cfa30e8245729101b65dbc861e38f877edeb`
- Latest Owner UK read-only snapshot SHA256: `2fba12a5a18240f32f2ead5857bb9757815b0b4830a760c0db67217d33a42a1d`
- Files: 148 regular, 11 directories; 22 helpers, 19 test modules, 102 runtime files.
- Archive also supplied as `epoch5-recovery-kit-v4.base64.txt`; its readback exactly matched local archive encoding.
- Runtime provenance is `e058a82cf20acde95dd591dd3c95eaf4d4e7aa82` / tree `a27d226d96878e8230f4d4d28d93141d0f4900de`. This is the runtime-only TLS delta source, distinct from the final recovery helper candidate above.

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

## C1 complete repair and evidence, C2 still open

Work's independent review #6169553920 closed the v3 B1-B3 evidence gaps and inspected B4, but correctly found C1: timeout cleanup performed an unbounded second communicate(). This v4 changes the TLS runtime, affected tests, runtime provenance and all dependent kit/plan/entry bindings. Unchanged independent passes remain reusable; changed package bytes and bindings require independent checking.

The fix uses one monotonic 2-second cleanup budget after the original command timeout. Both pipe draining and direct-child reaping use only the remaining budget; pipes are closed independently when draining cannot complete. ProcessLookupError, kill failure, drain interruption and diagnostic-write failure cannot lead to an unbounded communicate()/wait(). Each retained diagnostic stream is capped at 1 MiB, with truncation and incomplete-drain flags. Direct-child exit is distinguished from descendants UNKNOWN. Python3.6's missing TimeoutExpired partial output is handled by bounded copies of already buffered bytes, without further pipe reads.

A detached descendant holding inherited pipes is NOT claimed terminated. Output is marked incomplete where appropriate; outer fencing and all six cleanup groups still execute. The accepted FENCE_STOP_RETAIN_NO_REPLAY boundary remains unchanged; this is not complete rollback.

- Final packaged CPython3.6.8: 224/224 PASS, 3.875 seconds. Includes 12 added checks; counts overlap and must not be added.
- Owner UK affected checks: 148/148 PASS, 4.932 seconds, exact v4 kit.
- Owner UK real escaped-pipe probes: 0.309 seconds; diagnostic-write-failure variant 0.304 seconds; normal timeout 0.158 seconds. Test deadline/cleanup budgets are 0.15+0.15 seconds, production cleanup budget is 2 seconds.
- Owner UK real TLS timeout injected into the recovery sequence: all six cleanup groups attempted, terminal HOLD, 0.373 seconds; diagnostic failure variant 0.365 seconds. Harmless subprocesses are real; service operations are mocked. These do not establish production recovery success.
- Owner UK complete verify-only PASS, epoch5, exact new plan and snapshot above. Production NOT_EXECUTED.
- Developer independently rebuilt twice with identical bytes; local data-only archive and sandbox plan reproduction PASS. These are developer tests, not independent approval.
- Shared CI run38574005891 / job115886227178: FAILURE, raw log inspected. 305 tests, one import error, six skipped; tests/test_stage5_browser_e2e.py cannot import playwright.sync_api. Trailing P2_CONTROLLER_EXACT_SOURCE_GATE_PASS does not change failure. python36-gates SKIPPED.
- Dedicated frozen-kit CI: NOT_RUN. Other successful workflows do not override failed shared CI.
- C2 belongs to the existing shared workflow/Stage5 path owner, routed in PR17 #6169655722. No second writer or workflow bypass. Reviewer must explicitly address its disposition; developer has not waived it.
- Real ACME renewal, installation, notification ACK, HTTPS/dashboard and full P2/P3 E2E remain NOT_RUN/PENDING.

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
