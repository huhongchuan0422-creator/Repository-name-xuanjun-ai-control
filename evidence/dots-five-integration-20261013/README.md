# Five independent Stage1 integration work packages

Registration: PR17 comment 6138184452. Parent remains
XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1 / Issue19.
Sole source writer: DOTS_NATIVE. No new task DB, queue, runtime admission,
P2 shared-source change, model call, deployment or release grant.

## Deliverables and reuse

1. `test_owner_digest_canonical_integration.py`: real frozen
   `owner_dashboard.snapshot` + PR52 digest. Persistent temporary SQLite,
   recent-window overflow, redaction, restart, stale evidence, no writes.
   Empty `GROUP BY` results lack an explicit WAITING_HUMAN=0; the existing
   digest correctly holds. Shared caller must provide authoritative zero
   from its transaction; this suite does not silently normalize unknowns.
2. `test_delivery_restart_paging_integration.py`: real frozen
   ExecutionSupervisor outbox + PR57 view, concurrent WAL writer with
   one pinned reader transaction, restart, uncertain send, stale fence and
   activation change. No claim that reopening or a DB row proves delivery.
3. `test_supervisor_restart_integration.py`: real frozen supplemental schema
   and producer + PR50 inventory adapter. Eleven tasks, real dispatch-record
   persistence, deadlines, complete pagination, WAL isolation, unchanged DB.
   `dispatch()` here records a temporary fixture; no native process launches.
4. `ci_receipt_collection.py`: caller-authenticated read-only GitHub collector
   feeding PR59. Attempt-specific jobs, at most two 100-row pages /128 jobs,
   exact total, duplicates and before/after run changes fail closed.
5. `source_diff_collection.py`: complete caller-bound raw Git `-z` diff into
   PR60 path checks, both rename ends, supported regular modes, bounded bytes
   and records, unsafe paths/symlinks/submodules rejected. Test creates a real
   temporary Git repository, commits and rename; never pushes it.

## Input and trust boundaries

Collectors do not discover credentials, accept arbitrary URLs, start work,
register claims or admit writers. CI reader must authenticate official GitHub,
limit response bytes/time and redact transport errors; run metadata snapshots
are not atomic API attestations. The association checker is injected from the
pinned existing implementation, not replaced. Test results, checkout identity
and artifact bytes require their own evidence.

The diff caller must authenticate/pin its repository and both commits, obtain
complete successful output from `git diff --raw -z --no-abbrev --no-ext-diff
--no-textconv BASE HEAD --` (with rename detection configured if desired), and
supply `complete=True` only after success. A claimed complete flag is not proof.
No shell is executed by the adapter. Empty output is not a writable task.
Current claim revision and authority must still be atomically rechecked by the
existing write gateway. The adapter grants nothing.

## Frozen fixtures, not current P2 approval

`dependencies.json` pins six reviewed modules by commit + SHA256. Bootstrap
checks them before import; no copied alternative policy implementation.
Historical artifact11786072168: tar SHA256
25999a0491a94ce8b9c1c24262ccba38bdfc737e32193ae2825c7de9202a205b;
manifest SHA256 9c8ded6c3c17c88e76361085b8ee752f997d947c51506656099b22e033777d4c,
77 file hashes checked. These existing fixtures are intentionally immutable.
They are NOT the current P2 package, installed ledger, live service, scheduler
restart, native wake, notification ACK, or UK production E2E.
Activation is explicitly injected fixture identity. Tables and Git repositories
exist only in fresh temporary directories. Missing fixture inputs fail rather
than skip; artifact expiration becomes an explicit CI blocker.

## Validation

Actual local Python3.6.8: 44/44 passed; Python3.12: 44/44 passed.
New checks only; previous 63/189 results are not re-run or relabelled.
Hosted CI: pending exact commit receipt. Independent review: pending Work.
UK execution of these new checks: NOT_RUN. Installed/live acceptance: NOT_RUN.

Run with PYTHONPATH containing this directory and repository root,
DOTS_TEST_DEPENDENCIES pointing to hash-checked pinned sources and
P2_TEST_PACKAGE to the complete validated historical package. CI bootstrap
uses an ephemeral read-only Actions token for fixed repository contents/artifact endpoints,
strips Authorization on cross-origin redirect and does not pass token into
test step. No service/systemd/sudo/production credentials or model routing.
