# Work receipt verification — failed UK candidate 4bf32c0

VERDICT=ARTIFACT_IDENTITY_VERIFIED_QA_SECURITY_FAIL_RELEASE_HOLD
SOURCE_COMMIT=85ad1d7224485f3c57298e71a429eb576b8d943d
SOURCE_TREE=fd265cf40ac871cbaa93985cae28388e143739e8
SOURCE_FILES_VERIFIED=91
OWNER_REPORTED_CANDIDATE_COMMIT=4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2
REBUILT_CANDIDATE_TREE=fb8ee3bd3e2f175bcabc3eefe95aa182f3529b49
CANDIDATE_COMMIT_OBJECT_AVAILABLE=NO
QA_REPORTED_TREE_MATCH=YES
ARCHIVE_SHA256=c5368008106ec56c739bd594efda8cb161b6e16556c9d60dcd63aaa936a46062
ARCHIVE_BYTES=29050
PATCH_SHA256=82e81c2bbca62ff28dddab409f66ee53106283a1ebb3a9271c5c89b38e11aac0
PATCH_BYTES=102690
MANIFEST_SHA256=7a721baadf570decf6fae72747394e84fdac29fe1432fcef4f44a4bd85bf9eaf
MANIFEST_FILES_VERIFIED=33
PRODUCTION_DEPLOYMENT=NOT_EXECUTED
C_REAL_TASKS=NOT_STARTED

## Scope and reproducible identity

Archive was received as Owner attachment, bounded and inspected without unsafe
tar extraction; contains exactly patch, patch hash receipt and final QA report.
Work fetched the real upstream GitHub tree and missing blobs, independently
verified all 91 blob identities, built that exact tree, applied the exact patch
and obtained the QA-reported candidate tree. All 33 manifest file hashes match.
The upstream-object identity gap documented in the QA report is therefore closed.
Local candidate commit hash remains Owner/QA reported: the original commit object
was not delivered; verified content is the exact reconstructed tree and patch.

## Independent verification limits

Work ran all 232 uploaded candidate tests in this local environment: 231 passed,
one environment error, no production activity. test_development_service uses the
hardcoded absent /usr/libexec/platform-python3.6. No fake binary was installed or
test rewritten to report PASS. This local count is distinct from UK's 232/232
regression report; test portability is added to the next repair requirements.

A real temporary git repo/worktree without manual chmod reproduced
UNSAFE_WORKTREE_ENTRY. A local marker-only replacement .git/config clean-filter
probe reproduced execution in the caller process when git add reads Worker
metadata. Raw hash-object --no-filters --stdin did not run that filter. These
are local behavior evidence, not cross-UID UK isolation or production E2E.

Source review also confirms dispatcher NNP plus sudo-root invocation conflict,
separate dispatcher/callback DB paths, callback ordinary sqlite connect, no
durable dispatcher epoch and no actual restore activator. New frozen design
replaces shared metadata handoff and binds the activation/DB contract.

## Review verdicts and missing artifacts

Received original independent QA report: 232/232 regression, 4/6 additional
negative tests pass, 2 failures => QA FAIL; report preserved alongside patch.
Owner reports security 111 relevant tests pass but verdict FAIL. Full independent
security report was not included; SECURITY_REPORT_ARTIFACT=NOT_RECEIVED. Do not
promote partial tests to security acceptance.

## Current operational state

Executor stopped repeated same-path retries and retained checkpoint (Owner
reported). Work received artifacts and approved a new bounded design for the
existing A/B nodes. New executor delivery/start is NOT_VERIFIED; do not claim
UK Agents restarted because a repository document was published.
Prior root data-copy instruction is superseded by artifact upload; Owner need
not run it. Production/platform/C/HTTPS gates remain HOLD/NOT_VERIFIED.
