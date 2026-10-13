# CI receipt identity association — Stage1 1.9/1.10 source preparation

PR17 registration6137316223, same canonical parent and existing task names.
Python3.6+ standard library; pure function bind_ci_receipt. No network, database,
workflow trigger, model invocation, release decision or host operation.

The existing authenticated GitHub collector supplies expected policy plus raw
run and job objects. Policy must be independently established, not copied from
an untrusted receipt to make it pass. Exact repository, head SHA, workflow path,
run ID, run attempt and required job IDs/names must match. Each job also binds
run/head/attempt and a trusted runner ID, name, group ID and exact label set.
Required step names must be unambiguous and explicitly completed/successful.
Missing, duplicated, skipped, cancelled, wrong-version and unknown evidence HOLD.
The observation timestamp is collector freshness, not the CI completion time.
Future/stale observations HOLD; caller must fetch all expected jobs for the same
attempt, not silently combine paginated jobs from old attempts.

HOSTED_FIXTURE and UK_ISOLATED_FIXTURE are caller-approved expected scopes;
UK requires an explicitly identified self-hosted runner. Labels alone do not prove
geography, host ownership, installed services or end-to-end acceptance. Unknown
runner IDs or missing raw API fields require a fresh trusted mapping, never a
wildcard or default. Other optional cleanup steps may be skipped; every required
test step must be named in the trusted policy and successful.

CI_ASSOCIATION_VERIFIED proves only that supplied authenticated records associate
successful jobs/required steps with the expected head and attempt. It does NOT
verify test assertions/counts, log contents, artifact bytes, independent review,
release permission or installed acceptance. GitHub pull_request run.head_sha is
not necessarily the checked-out commit: checkout may use a synthetic merge.
Output checked_out_commit remains null until the existing separate provenance
collector verifies checkout logs/artifact bindings. No invented checkout SHA.

Raw API extras are ignored and never echoed. Unknown/malformed contracts raise
fixed ValueError codes. Runtime collector authentication, replay handling,
immutable evidence storage and enforcement remain in the existing canonical
ledger/entry gates, not in this utility. This is distinct from Work's Canary
coverage projection, which consumes already attributed evidence.

Run python3 -B -m unittest discover -s tests -p test_ci_receipt_binding.py -v.
The isolated workflow checks out the exact PR head, not the default merge ref.
No live GitHub collection or UK host acceptance is performed by the tests.
