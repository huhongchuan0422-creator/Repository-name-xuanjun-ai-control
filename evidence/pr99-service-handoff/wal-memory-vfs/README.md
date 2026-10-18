# PR99 independent WAL and lost-invocation nodes

Original PR99/branch and 40-file candidate remain the baseline. These new modules
do not overwrite or republish that candidate, run the refused M99 directory tests,
retry bwrap, change isolation settings, issue admission or operate a host.

## N1 — recover captured main + nonempty WAL entirely in memory

`sqlite_wal_vfs.recover(main_bytes, wal_bytes, expected_schema_sha256, progress)`
returns a complete standalone database and an implementation receipt. No path,
URI or caller SQL is accepted. `libsqlite3.so.0` is the official native SQLite
runtime. Its VFS receives exactly two private heap slots, main and WAL; the
WAL index is private heap too. No default filesystem VFS fallback exists for
source data. The destination is explicitly `:memory:` with SQLITE_OPEN_MEMORY.

SQLite performs WAL checksum/commit recovery, private-copy checkpoint, backup,
integrity checking and serialization. The Python module checks WAL byte framing,
not page recovery. The official checkpoint must report every supplied frame in
the validated committed prefix; corrupt, truncated or uncommitted tails HOLD
rather than return old-main success. This deliberately rejects recoverable but
ambiguous tails. Checkpoint writes affect disposable heap copies ONLY; original
bytes are unchanged, and no production/captured database file is opened.

After backup, only output header format bytes18/19 are normalized for a standalone
in-memory image as documented by SQLite deserialize. Input header/WAL are never
altered. Expected schema must match. Each source file, result and VFS write is
bounded to64MiB; WAL index is bounded to2MiB. Native memory/resource acceptance
on the real migration executor is still required. Deadline/progress errors HOLD.
An unexpected close failure quarantines live callbacks and blocks further calls
until a new process; callbacks are not freed beneath SQLite.

13 synthetic-data tests include WAL-only committed rows, missing-WAL contrast,
multiple page sizes, corrupt/truncated/uncommitted tails, schema mismatch,
deadline/fence callback failure, per-call isolation and unlisted-file rejection.
They do not close M99-R1 or establish a production fence/consistent live capture.
The existing dirfd capture/output adapter still needs a separately reviewed
explicit integration; no automatic monkeypatch/fallback is installed.

## N2 — recover lost InvokeId without dispatch replay

`lost_invoke_reconciliation.bind_missing_invoke(directory_fd,
assert_directory_binding, rpc, credentials)` consumes the ORIGINAL persistent
controller intent and writes only its missing `cloud-start.invocation.json`.
It creates no controller root, Writer, epoch, grant or second authority ledger.
The admitted original PathGuard/authority must supply the fd and binding check.
A temporary Actions directory is not accepted as persistent by this contract.

Only DescribeCommandInvocations is called. Aliyun documents that CommandName is
ignored when InstanceId is supplied, so all bounded instance pages are filtered
locally. Exact operation-bound name, full command SHA256, type/user/directory,
timeout, empty parameters and single fixed domestic instance must match. Zero
matches stays UNKNOWN; duplicates/conflicts, partial pages or changing totals
HOLD. Discovery of an ID is not operation success, failure, absence of effects,
or permission to resume. Existing production_transport.query_only can read the
original-schema record after a trusted caller supplies this binding step.

10 tests use fake RPC and private temporary records. They cover crash/lost-ID
state, restart without RPC/replay, ambiguity, pagination drift, complete-content
binding, wrong instances, redaction and preservation of partial records. No
cloud calls or migration attempts are made by tests.

## Delivery and preserved checkpoints

Run only this node's tests: `python -B -m unittest discover -s . -p 'test_*.py' -v`.
`build_node_artifact.py` creates a reproducible source ZIP and a separate receipt
binding source Commit/Tree, exact file hashes, artifact SHA256 and SQLite runtime.
Hosted CI runs Python3.11 and3.12 without cloud secrets or root deployment jobs.

N1/N2: implemented and locally tested; Hosted evidence is recorded separately.
Neither node is production-installed, independently accepted or frozen closed.
Rollback is non-activation/removal of the new opt-in package; no existing runtime
module was replaced and no original controller record may be erased as rollback.

Remaining independent work: authoritative data/writer/scheduler inventory,
enforced fence/drain, trusted persistent executor integration, runtime and
business/cutover acceptance. M99 restricted dynamic acceptance requires the
original platform's normal clearance; no alternate environment is inferred.
Only the original independent reviewer may issue the eventual exact production
permit with at most five controlled Attempts. Production status stays HOLD.

Primary references:
- https://www.sqlite.org/vfs.html
- https://www.sqlite.org/c3ref/io_methods.html
- https://www.sqlite.org/c3ref/backup_finish.html
- https://www.sqlite.org/c3ref/deserialize.html
- https://help.aliyun.com/zh/simple-application-server/developer-reference/api-swas-open-2020-06-01-describecommandinvocations
