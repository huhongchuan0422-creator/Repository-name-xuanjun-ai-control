# P2 retained recovery governance mapping

Status: IN_DEVELOPMENT. This mapping does not create a task, queue, lease or install admission.
FEATURE_ID: P2_RETAINED_RECOVERY. This entry remains IN_DEVELOPMENT until complete acceptance evidence exists.

## 1 Functional design

Continue PR17 / PR58 and repair/p2-chatgpt-clean-review-20261013. Recover the retained epoch7 HOLD using a complete, finite, exact-version manual entry. Reuse the canonical ledger, retained TLS certificate and renewal proof, existing activation/fence interfaces and old service isolation. No historical notification replay, old writer restart or second task database.

Components: protected kit loader; snapshot and resource observers; approval reader; retained-state gate; finite phase coordinator; host adapters; bounded subprocess evidence; runtime identity/access adapters; independent failure containment. Inputs are authenticated code and manifests, private exact plan and fresh snapshot, reviewer approval and Owner consent for security effects. Private plan, credential material and raw host inventory are not public deliverables.

Every effect must have exact input bindings, bounded execution and observable terminal evidence. Failure means FENCE_STOP_RETAIN_NO_REPLAY with independently attempted cleanup groups and HOLD on uncertainty. This is limited failure containment, not a promise to reverse all side effects.

## 2 Development order and dependencies

Phase 2 of existing control-plane work; no priority or task change. Runtime source is frozen at 101b465ca3554bf34fef2d53d6006b96d85c4a63; the 107-file manifest is 26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa. Public source/test checkpoint 1238a03f2aef763861447c8f34ca9a4bfcdcce8c is still not the complete recovery release.

1. Finish concrete loader/coordinator/observer/admission composition and local affected tests.
2. Authenticate one complete diagnostic candidate, obtain exact Owner consent where required, collect fresh UK snapshot and narrowly scoped isolated mechanism proof.
3. Freeze complete source, immutable kit, manifests, plan and evidence. Pass Feature Compliance Gate and exact CI. Request one consolidated independent review in PR58, reusing unchanged verified scope.
4. Obtain fresh exact single-attempt approval, revalidate real-time gates, have Owner execute protected recovery, then record health and independent production acceptance separately.

Existing approval6170703284 is consumed. Current production remains HOLD. No dependent production step advances from simulated or local-only tests.

## 3 Acceptance criteria and evidence

- Design/order/acceptance all bind the same FEATURE_ID. Each exact CI result must actually be run and read back; partial gates do not imply the complete kit passed.
- Verify complete source and package manifests, allowed file set, private plan targets/plugins and version bindings independently.
- Test denial of changed files, unknown/expired authority, mismatched snapshot, active writers, partial effects, interruption, timeout, unbounded descendant pipes, failed cleanup and unknown results.
- Test exact Python 3.6.8 compatibility; distinguish fixtures, local process tests, shared CI, UK isolated tests, host preflight and production acceptance. Skips are not PASS.
- Test admitted context binds actual approval ID/body while the preapproval contract is independent of the not-yet-created comment ID.
- Existing tests include evidence/p2-epoch7-access-repair-20261014/preflight-ack/test_service_preflight_ack.py and test_exact_access_plan.py. tests/test_p2_retained_recovery_governance.py executes the existing15 ACL planner cases; it does not claim full recovery-kit coverage.
- Source checkpoint d03e7226 has shared runs38603941972/38603941911/38603941329 SUCCESS; native probe38603938016 SKIPPED. These do not certify all recovery helpers or production.
- Runtime-only checkpoint 1238a03f has independent raw-log readback for runtime CI 38614873783 (74/74,107 source hashes) and Feature Compliance Gate 38614874281 (7 checker cases,COMPLIANCE_PASS). Prior failed runs are retained as history.
- tests/test_p2_full_kit_checkpoint.py invokes the exact-checkout published kit generator, validates Git blob/SHA provenance, builds two identical archives, authenticates extraction, and requires all mandatory offline suites plus separate bootstrap/resume/tool tests without skipped required cases. tests/test_p2_full_kit_wrapper_contract.py checks the wrapper using explicitly synthetic results. The prior frozen helper source 3b87d10b66ae791086cdb05a554ad44ed0f4ad90 passed full-kit CI38644002796:1704 mandatory tests and157 bootstrap tests, zero skips. That result applies only to its exact bytes; the present continuation requires a new exact-commit full-kit result.
- Source profiles cover only the finite reviewed OpenClaw Gateway/relay/native bridge and nginx startup families. Installed source mismatch, unknown children or missing positive capability proof cause HOLD. No business-module or complete vendor-distribution audit is implied.
- Local Node SQLite diagnosis uses builtins and in-memory data only; it does not start OpenClaw or invoke a model. Its result cannot substitute for the required exact UK executable and execution identity proof.
- Full kit, fresh UK proof, consolidated independent approval, actual deployment and production acceptance are not yet complete.

## 4 Governance adoption provenance

Owner instruction Sentinel_f557dd99420481918694d75d61687ced, 2026-10-14. Main232e8a732c45ed2f13eb747f02e883283475b499 contains Feature Compliance Gate. That historical main registry contained only GOVERNANCE_COMPLIANCE_GATE. The repair branch now includes these governance files and P2_RETAINED_RECOVERY; preserve upstream checker/workflow bytes and all concurrent registry entries when updating. Native protected-merge enforcement remains unverified; do not extrapolate from branch metadata.

## 5 Current retained-host compatibility continuation

The runtime107 files remain unchanged. This continuation corrects helper-side observation and composition against actual retained evidence:

- Validate the owned native-sidefile transition using its four exact buffers and journal, preserving the historical ledger-client binding separately from the newly rendered configuration.
- Accept only the exact two-name Python3.6 executable hard-link pair with native/package digest consistency and stable descriptor metadata. Unrelated files keep the single-link requirement; RPM signature authenticity is not asserted.
- Preserve the188-byte existing launcher and its configuration hash. Its fixed versioned dist/entry.js profile is distinct from the root openclaw.mjs profile: initial lexical Node alias, canonical process executable, fixed32-source scope, foreground Gateway main plus bridge, and at most one reviewed warning-adjusted relay child. Unknown aliases or source bytes HOLD.
- Keep pre-permission Node measurements explicitly non-admitting. Owner consent covers only the three named0775→0755 directory narrowings, retaining owner/group/content. Hold locks, validate inactive writers and PREPARED epoch7, and bind descriptor and Node identity before/after. Any partial change or uncertainty is HOLD, with no automatic retry or permission-widening rollback.
- Preserve the old staged kit. The new exact staging sibling is epoch7-recovery-candidate-r2; it does not create a second task, ledger or recovery authorization.

The latest UK receipts establish the native transition, Python pair, five SDK hashes and31 source files. Fresh Node-alias/binary/32nd-source verification, permission effects, new complete observation and isolated execution proof remain separate requirements. Local helper tests do not satisfy them. The three permission changes have not yet been applied at this source checkpoint.

Current validation must include all previous mandatory suites plus the new prerequisite-effect tests. A local run with nine socket-limited skips remains incomplete; hosted exact-commit CI must execute those tests. New byte changes cannot inherit an old install approval. Final package, plan, fresh host evidence and independent approval remain required before recovery.

## 6 Bound Owner diagnostic entry

The separate owner-diagnostic-r2 checkpoint pins the exact reviewed kit source4798cda235b24b31a18b57d3957fbc0d396d634b and immutable archive publication965c0f8bd7e5145dc353a9145388c733e0660ab5. Its dedicated hosted test compares wrapper/test bytes against the actual checkout HEAD blobs, validates all immutable download pins, verifies the real frozen archive and imports/selects the exact UK-only case without executing it, then runs34 mocked/pure boundary cases with zero skips. It never downloads, changes host permissions or starts a service in CI. The unchanged full kit retains its independent1982-case plus170-bootstrap CI receipt38669612327; this small outer checkpoint does not rerun that unchanged kit.

A successful outer CI is only delivery readiness for the explicitly authorized prerequisite and diagnostic command. Real three-directory effects, fresh UK observation and isolated mechanism proof remain separate. Any mismatch or partial effect is HOLD, with no automatic retry and no restoration of broader permissions. Final production recovery still requires its own exact independent approval and live admission.

The first r2 Owner diagnostic verified extraction but stopped at the UK fixture import stage before permission changes. Its historical disabled-suite mapping omitted the existing authenticated test_snapshot dependency. The outer-only correction adds exactly that SHA-bound alias; it neither rewrites the frozen kit/manifest nor changes production helpers. Hosted CI must now exercise this real cached-import/case-selection path while leaving the UID-specific case execution to the authorized UK diagnostic.

## 7. Typed unit properties and r3 successor

Owner's complete read-only diagnostic established two stable rounds of19 inactive units with no reload request. On the observed systemd interface the three fixed timers omit MainPID, ControlPID and ControlGroup; the three fixed sockets omit MainPID. The shared exact-unit contract preserves these absent observations, while requiring all applicable service/socket properties and validating any supplied optional PID as zero and timer ControlGroup as empty. Independent associated-service, recursive cgroup, process, descriptor, mask and scheduler checks remain mandatory. Unknown unit types, malformed values, changed field presence or unexplained runtime state fail closed.

Tests cover the recorded19-unit selected-property projection (not original CLI stdout), pure contract failures, parser/live/transition/compiler seams and full107-file plan composition with synthetic host facts. Runtime107 remains unchanged. New helper staging uses only epoch7-recovery-candidate-r3, preserving the installed r2 generation. Earlier r2 test results are historical and cannot certify these changed helper bytes. The fresh collector observed the Node identity and fixed32nd source successfully, but the approved directory changes remain unapplied; new complete prerequisite/observation/probe and final review are still required.

## 8. Bound r3 diagnostic delivery gate

The r3 helper source460a53e0f702fb416811e785a6ef8d6c39b2d003 passed exact full-kit CI38677450098:2012 mandatory cases plus173 bootstrap cases, zero skips. Its immutable archive is published at02822b674a7c8a0c9c395cbf5664b3d24bff2516, SHA256 c56a11e78914d567f91a94118d676d49f65775161b3c46b16583ece1403c1d85,1015797 bytes. Binary GitHub readback matches. This evidence does not grant installation admission.

The separate owner-diagnostic-r3 wrapper binds that source/tree/archive/manifest/extractor/entry and only the existing approved prerequisite, observation and scoped isolated probe. tests/test_p2_owner_diagnostic_r3.py requires the actual archived cached import closure and exact UK case selection without executing that case in hosted CI, plus36 mocked boundaries and exact checkout/blob verification. The historical r2 gate remains executable against its explicitly preserved extractor. No historical approval or old staged directory is reused for new code. Fresh actual Owner output, private plan binding and consolidated independent review remain required.

## 9. R4 continuation after completed Owner prerequisites

Owner's r3 receipt4d85a064583ca92079f0df489838aa76cfb21f530a3725217689f33356fcbe91 records successful completion of the three authorized0775→0755 directory narrowings and one disposable UK UID/ACL fixture. The subsequent core observation remained HOLD; its exact private hash is2192823493290c4829bfda8a4f6397e94d1ae053266075c1f0da9f63d319e0c9. Neither permissions nor that fixture may be blindly repeated.

The next fixed r4 generation preserves r3. Its distinct continuation validates the exact prior receipt/observation and their source/manifest linkage, verifies the same current0755 directory metadata without mutation, and invokes one existing observe/probe operation. It has no permission-repair or UID-fixture execution path. New publication pins and exact CI remain required; local tests cannot enable delivery on their own.

Actual bounded metadata established that all20 original-plan directory tuples match live UID/GID/mode. The collector excluded the exact declared /var/lib/xuanjun-development root because it only accepted a trailing-slash prefix. R4 adds only exact-root equality while retaining all declared metadata checks. The fixed /home/xuanjun_dev/.config is root:root0755, without ACL/capability; its openclaw child is absent. R4 permits only that exact root-owned profile in addition to the existing developer-owned profile. No other home-directory authority rule is generalized. Missing-parent proofs recheck held ancestors/root and independently close all descriptors; no nonexistent file/directory pin is fabricated.

Failure classification remains explicit. The unchanged approval worker's short local timeout exhausted cleanup during one aggregate run; it failed closed, and the exact-byte isolated75-case rerun passed. The unchanged diagnostics fixture also produced a scheduling-sensitive success instead of its expected timeout; its exact-byte39-case rerun passed. Those reruns do not erase the original failures. Independent deterministic analysis additionally found an actual terminal-EOF deadline-check omission in the diagnostics helper. The candidate now rechecks the absolute deadline after selector/event processing and around the terminal poll. Nine deterministic regressions cover late/exact-boundary completion, first-failure precedence and no signalling of reaped identities; all39 existing tests remain unchanged. The48-case diagnostics suite passes both Python versions, while exact final full-kit CI is still required. No deadline or required assertion is weakened to manufacture PASS.
