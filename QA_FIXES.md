# Independent QA defect closure

Source finding: `deliveries/b6-p3-independent-qa-20261030/QA_REPORT.md`.

1. STARTED payload fence is compared with the already verified receipt subject
   fence before `supervisor.accept_started` can be called.
2. Completion recovery requires every `RUN_SUBJECT_KEYS` value in its subject
   to equal the acceptance subject, preventing task-only cross-run mixing.
3. After runner launch/resume returns, receipt verification or ACK-shape failure
   yields `UNKNOWN_RUNNER_EFFECT_HOLD`, `automatic_retry=false`.
4. After outbox send returns, receipt verification or payload-shape failure
   yields `UNKNOWN_NO_REDIAL`, `automatic_retry=false`.
5. Recovery payload `current_fence` must equal the already verified
   `RECOVERY_LINEAGE` receipt subject fence. A valid same-subject receipt with
   only the payload fence changed is rejected as `COMPLETION_LINEAGE_CHANGED`.

`tests/test_p3_qa_counterexamples.py` contains one regression for each finding.
The original 21 expectations remain unchanged. Its positive completion fixture
now binds the expected current fence in both receipt subject and payload, as
required by the corrected contract.
