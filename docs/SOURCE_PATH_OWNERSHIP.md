# Source path ownership preflight — Stage1 1.11 source preparation

PR17 registration6137316223; same parent and canonical tasks, no second registry.
Python3.6+ standard library; pure check_source_paths. No claims are created,
released or transferred. No runtime lease/fence/epoch, stop, push or dispatch.

Caller supplies an authenticated COMPLETE snapshot of current active source
claims from the existing task contracts/ledger, with repository, revision and
observation time, plus the complete base/head-bound changed path list from the
existing GitHub/native intake. No new task IDs are minted by this module.
Exact expected snapshot revision, repository and freshness must match. STOPPED
claims may be omitted only after the existing authority verifies actual stop and
handoff; a self-reported flag must not hide an active writer. The module does not
prove completeness/authenticity from the caller's complete=true assertion.

Each claim contains claim_id, existing task_id, writer and explicit paths.
A trailing slash means a directory prefix at a real segment boundary; otherwise
scope means exactly one file. No globs, absolute paths, dot segments, empty path
segments, .git segments, backslashes, whitespace or non-ASCII paths are accepted.
Git paths are treated as case-sensitive. Local filesystem/case-fold/symlink
semantics must be checked by existing intake before using these observations.
Overlapping scopes of another task or writer HOLD. A second active writer for
the same task HOLDs even when its declared paths are disjoint. Overlapping claims
for the same task AND same writer are harmless. Rename checks both the previous
and new paths; deletion requires ownership too. Unowned changes cannot pass.

SOURCE_PATHS_MATCH is an observation, NOT a writer grant or execution admission.
Output binds expected base/head and source-claim revision; that does not itself
prove the supplied change list belongs to those commits. Runtime must atomically
recheck the current authority/revision and complete compare manifest before any
mutation. Old snapshots/results cannot authorize a later push. Existing signed
review/syntax/drift gates remain mandatory. Snapshot construction and this check
must not create a second source-of-truth or runtime task queue.

Input bounds: 1024 claims, 4096 total scopes, 256 changed records, 300 characters
per path. Malformed inputs raise fixed ValueError codes; missing ownership,
conflict, stale/incomplete snapshots yield visible HOLD. No input mutation.
Run python3 -B -m unittest discover -s tests -p test_source_path_ownership.py -v.
Tests and exact-head hosted CI are source evidence only, not deployed enforcement.
