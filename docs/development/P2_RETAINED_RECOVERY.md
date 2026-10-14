# P2 retained recovery governance mapping

Status: IN_DEVELOPMENT. This mapping does not create a task, queue, lease or install admission.
FEATURE_ID: P2_RETAINED_RECOVERY. This entry remains IN_DEVELOPMENT until complete acceptance evidence exists.

## 1 Functional design

Continue PR17 / PR58 and repair/p2-chatgpt-clean-review-20261013. Recover the retained epoch7 HOLD using a complete, finite, exact-version manual entry. Reuse the canonical ledger, retained TLS certificate and renewal proof, existing activation/fence interfaces and old service isolation. No historical notification replay, old writer restart or second task database.

Components: protected kit loader; snapshot and resource observers; approval reader; retained-state gate; finite phase coordinator; host adapters; bounded subprocess evidence; runtime identity/access adapters; independent failure containment. Inputs are authenticated code and manifests, private exact plan and fresh snapshot, reviewer approval and Owner consent for security effects. Private plan, credential material and raw host inventory are not public deliverables.

Every effect must have exact input bindings, bounded execution and observable terminal evidence. Failure means FENCE_STOP_RETAIN_NO_REPLAY with independently attempted cleanup groups and HOLD on uncertainty. This is limited failure containment, not a promise to reverse all side effects.

## 2 Development order and dependencies

Phase 2 of existing control-plane work; no priority or task change. Current source checkpoint d03e72268eaf9b4251dedeab651ba5b4b6daf566 is an intermediate runtime checkpoint, not the complete recovery release.

1. Finish concrete loader/coordinator/observer/admission composition and local affected tests.
2. Authenticate one complete diagnostic candidate, obtain exact Owner consent where required, collect fresh UK snapshot and narrowly scoped isolated mechanism proof.
3. Freeze complete source, immutable kit, manifests, plan and evidence. Pass Feature Compliance Gate and exact CI. Request one consolidated independent review in PR58, reusing unchanged verified scope.
4. Obtain fresh exact single-attempt approval, revalidate real-time gates, have Owner execute protected recovery, then record health and independent production acceptance separately.

Existing approval6170703284 is consumed. Current production remains HOLD. No dependent production step advances from simulated or local-only tests.

## 3 Acceptance criteria and evidence

- Design/order/acceptance all bind the same FEATURE_ID. Exact CI remains pending until actually run and read back.
- Verify complete source and package manifests, allowed file set, private plan targets/plugins and version bindings independently.
- Test denial of changed files, unknown/expired authority, mismatched snapshot, active writers, partial effects, interruption, timeout, unbounded descendant pipes, failed cleanup and unknown results.
- Test exact Python3.6.8 compatibility; distinguish fixtures, local process tests, shared CI, UK isolated tests, host preflight and production acceptance. Skips are not PASS.
- Test admitted context binds actual approval ID/body while the preapproval contract is independent of the not-yet-created comment ID.
- Existing tests include evidence/p2-epoch7-access-repair-20261014/preflight-ack/test_service_preflight_ack.py and test_exact_access_plan.py. tests/test_p2_retained_recovery_governance.py executes the existing15 ACL planner cases; it does not claim full recovery-kit coverage.
- Source checkpoint d03e7226 has shared runs38603941972/38603941911/38603941329 SUCCESS; native probe38603938016 SKIPPED. These do not certify all recovery helpers or production.
- Full kit, fresh UK proof, consolidated independent approval, actual deployment and production acceptance are not yet complete.

## 4 Governance adoption provenance

Owner instruction Sentinel_f557dd99420481918694d75d61687ced, 2026-10-14. Main232e8a732c45ed2f13eb747f02e883283475b499 contains Feature Compliance Gate. Its registry currently has only GOVERNANCE_COMPLIANCE_GATE. Existing repair branch lacks these governance files; preserve upstream checker/workflow bytes and all concurrent registry entries when integrating. Native protected-merge enforcement remains unverified; do not extrapolate from branch metadata.
