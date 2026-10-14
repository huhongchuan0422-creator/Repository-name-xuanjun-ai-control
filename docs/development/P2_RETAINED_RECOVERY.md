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
- tests/test_p2_full_kit_checkpoint.py invokes the exact-checkout published kit generator, validates Git blob/SHA provenance, builds two identical archives, authenticates extraction, and requires all mandatory offline suites plus separate bootstrap/resume/tool tests without skipped required cases. tests/test_p2_full_kit_wrapper_contract.py checks the wrapper using explicitly synthetic results. The full-kit gate result remains PENDING until its actual run is recorded.
- Source profiles cover only the finite reviewed OpenClaw Gateway/relay/native bridge and nginx startup families. Installed source mismatch, unknown children or missing positive capability proof cause HOLD. No business-module or complete vendor-distribution audit is implied.
- Local Node SQLite diagnosis uses builtins and in-memory data only; it does not start OpenClaw or invoke a model. Its result cannot substitute for the required exact UK executable and execution identity proof.
- Full kit, fresh UK proof, consolidated independent approval, actual deployment and production acceptance are not yet complete.

## 4 Governance adoption provenance

Owner instruction Sentinel_f557dd99420481918694d75d61687ced, 2026-10-14. Main232e8a732c45ed2f13eb747f02e883283475b499 contains Feature Compliance Gate. Its registry currently has only GOVERNANCE_COMPLIANCE_GATE. The repair branch now includes these governance files and P2_RETAINED_RECOVERY; preserve upstream checker/workflow bytes and all concurrent registry entries when updating. Native protected-merge enforcement remains unverified; do not extrapolate from branch metadata.
