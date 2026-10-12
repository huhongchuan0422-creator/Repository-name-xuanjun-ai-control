# Consolidated P2 installer preparation — source repair in progress

Owner requests one complete installation transaction, not more inert canary packages.
Origin archive SHA256 4145afe30eac74024ce46772508d560ec2790a12b06fdec3368e45df58b87ff0.
Original UK checkpoint and fence17RR remain untouched/revoked. One Work preparation writer operates only on the exported isolated copy.

UK baseline test correction: keep a pristine rollback fixture before the mutation callback. Missing-callable assertion must use the pristine valid receipt. Production validator remains fail-closed.
True UK Python3.6.8 baseline: run38191583141/job114625277281,296/296 PASS.
Independent QA/Security/release approval remains PENDING.

New deployment finding: ActivationStore opens its root-owned0600 activation lock O_RDWR and fchmods it on every use. The non-root ledger and GitHub intake guard_head path therefore cannot obtain the lock. Candidate change: authority opens/creates O_RDWR and fixes mode0644; non-owner reader opens an existing lock O_RDONLY, never creates/chmods it. Both retain owner, regular-file, no-group/other-write validation and Linux flock serialization. Five targeted tests passed locally; new full UK regression is triggered by this commit, not yet accepted here.
Protected activation parent must exclude worker traversal. Read permission on a lock does not grant authority to replace root activation files. Real separate-UID deployment proof remains mandatory.

Further concrete installation gaps:
- shared /run/xuanjun-development directory has conflicting broker root/no-write and dispatcher owner0700 lock requirements; use an independently provisioned dispatcher lock subdirectory in final rendered config.
- github_issue_consumer only persists INTAKE_READY rows; it is not the complete Work task admission/execution-spec adapter. Reuse existing approved Work intake instead of pretending this timer completes event admission.
- existing fixed audit proves old callback/dashboard200, but no usable auth path in its narrow known locations; absence in those locations is not proof OAuth is absent globally. No credential copying/new API is permitted.
- final Git commit/tree verification, canonical old ledger/lease migration, guarded Coordinator stop, exact immutable rollback and authenticated HTTPS route need a complete transaction implementation and host bindings.

No root install, systemd/service mutation, canonical task/ledger write, model call, credential access or customer message by the validation workflows. SOURCE_PREPARATION only; P2 NOT_INSTALLED; P3 NOT_STARTED. Do not install this evidence subtree.
