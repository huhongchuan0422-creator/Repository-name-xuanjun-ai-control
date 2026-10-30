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

`tests/test_p3_qa_counterexamples.py` contains one regression for each finding.
The original 21-test file and its expectations are unchanged from the imported
frozen candidate.
