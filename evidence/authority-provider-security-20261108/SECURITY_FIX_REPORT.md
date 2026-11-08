# Security continuation report

Baseline: commit `c7a039ac440d9abb9b861abc188f93549979f6b3`, tree
`1ae37193c123038265d834d54e9deeccc543f42c`. The prior c7/05c5/0ff failure
history is not rewritten. Independent QA's formal-equivalent runtime result
(Python 3.11.18, SQLite 3.46.1, cryptography 42.0.8) remains 66/66 PASS.

## Finding-to-fix map

1. Release: exact signed schema binds filename, artifact SHA, source SHA,
   commit, tree, and `deployment_authorized:false`; all field tampering rejects.
   Reversible inspect/apply/query/recover maintains rotated backup, atomic state,
   immutable content-addressed artifact copies, and receipts.
2. Identity: arbitrary callable injection is rejected. Production uses the
   constructor-controlled `TrustedRegistrationVerifier`; test injection requires
   an explicit TEST_ONLY type and environment gate.
3. Replay: signed request purpose is mandatory. Atomic shared key is
   `(issuer, instance, purpose, target_sha256, request_id)`. Multi-process attack regression
   proves one authorization winner; STATUS_QUERY, AUTHORIZATION_CONSUME,
   INSPECT, and RECOVER are isolated, including cross-target-SHA replay. Guard
   error/UNKNOWN rejects. Lifecycle APPLYING persists before copying; copy
   ambiguity becomes UNKNOWN and RECOVER reconciles the pending digest or rolls
   back to the prior active digest under the original state generation.
4. Regression: `tests.test_authority_security_regressions` plus authority and
   operational suites ran 18/18 PASS; raw output is `RAW_SECURITY_TEST.log`.
5. The prior `/tmp` artifacts, manifests and logs were copied byte-for-byte into
   `pre-fix/`; `PRE_FIX_SHA256SUMS.txt` verifies every copy.

## Environment evidence

The NO_PROXY full-suite attempt is preserved in `RAW_FULL_TEST.log`; it reached
441 lines before the bounded 60-second harness terminated it, so it is explicitly
**not** claimed as PASS. Earlier local SQLite migration-fixture failures remain
environment failures and are not converted to PASS. Syntax compilation and
`git diff --check` passed.

No deployment, registration, installation, or production mutation occurred.
