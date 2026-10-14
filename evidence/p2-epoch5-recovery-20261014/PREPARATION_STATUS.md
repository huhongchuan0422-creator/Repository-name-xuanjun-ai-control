# P2 epoch5 retained-certificate recovery preparation

Status: NOT_READY_FOR_REVIEW_OR_INSTALL. This is a development checkpoint on the existing P2 branch, not a new task queue or release approval.

The epoch3 attempt consumed approval 6167552232 and ended in HOLD. Owner observed epoch5 PREPARED and successful final stop/mask verification. See PR17 comment 6167913450 for the original receipt bindings.

The issuance succeeded; the renewal dry-run logged a 261.68085359228326-second random delay against the caller's 240-second deadline. Certbot v1.22.0 officially defines `--no-random-sleep-on-renew` in `certbot/_internal/cli/__init__.py`. The new candidate applies this option to both dry-run and periodic renewal. Timeout diagnostics now retain private evidence; these logs must not be published verbatim.

Local tests: 36/36 under Python3.6.8 in a root-mapped local namespace. These are unit/mocked lifecycle and observation tests, NOT UK host validation, ACME validation, CI, or production acceptance. Initial test-only use of Mock.call_args.kwargs was corrected to the Python3.6 tuple API; the final run passes. The frozen epoch3 kit and source remain unchanged.

`observe_epoch5.py` only inventories current retained state and parses Certbot arguments in an isolated temporary config. It does not request a certificate, renew, resume, restart services, connect to the database, change activation, or grant admission. Output contains file hashes/metadata, not credential contents. A passed observation is not a full live install preflight.

Remaining consolidated deliverables:
- Bounded retained-certificate continuation, preserving all old receipts and refusing unknown/partially applied target states.
- Exact epoch5 -> new PREPARED generation of the existing activation journal, native binding and 24 rendered targets; no old writer restart or task/notification replay.
- Full scanner reuse for database/FD/scheduler/cgroup/runner exclusion, fresh snapshot and single-attempt approval binding.
- Complete failure containment, attempt-consumption and private-journal tests, actual UK read-only validation, frozen package and one consolidated independent review request.

Do not use any old resume command or old approval. No production recovery command is provided by this checkpoint.
