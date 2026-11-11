# Shared `trading.db` cutover plan

Status: design and acceptance package only; no timer, service or database action is authorized.

## Current fact

Four active Tokyo Finance/Billing timers write the same `trading.db`. They remain
running now. A read-only Korea B/C copy is never authoritative and never receives
the trading credential or a master key capable of decrypting trading rows.

No existing accepted component was found that can preserve the four jobs while
remotely committing their exact writes to a Korea-owned SQLite database. The
status-only/provider-neutral bridges do not provide this database write contract.
Therefore post-cutover timer resumption remains blocked until one of two exact
options is independently accepted:

1. move only the four evidence-proven jobs and their minimal transitive dependencies
   beside the Korea authoritative database; or
2. reuse the existing authenticated/replay-protected bridge patterns to add one
   narrowly typed Korea-side Finance/Billing command adapter. It must expose only
   the four required operations, use idempotency keys and transaction receipts,
   and perform all SQLite writes on Korea.

Option 2 is the preferred minimum because it does not migrate unrelated Finance,
CRM or OpenClaw. It is not implemented or authorized in this package. Direct file
replication, dual-primary writes and writes to a stale Tokyo copy are prohibited.

## Phase D transaction

1. Fence new trading entries while Korea Writer remains locked.
2. Stop only the four timer schedules under an exact Release Gate; do not stop
   PostgreSQL, Redis, Novel, MoreLogin, Yibi or unrelated timers.
3. Wait for the four corresponding services to become inactive. A timeout, lost
   process, SQLite lock, partial result or unknown exit becomes `UNKNOWN/HOLD`;
   capture process, transaction and database state and do not blind-retry.
4. Prove no database Writer or in-flight order operation remains.
5. Record pre-snapshot database, WAL and SHM identities; use SQLite online backup
   while the source remains authoritative, then close the final delta window and
   record post-snapshot identities.
6. Verify file hash, `integrity_check`, table/row counts, unresolved/UNKNOWN/
   inflight ledgers, orders, positions, protection state, Finance/Billing cursors
   and the incremental interval since the prior B/C copy.
7. Transfer the closed copy and re-verify it. Only the Release Gate may assign a
   new Korea authority epoch. There is never more than one authoritative database.
8. Keep the four timers paused until Option 1 or 2 above has passed its own CI,
   replay/idempotency, crash-recovery and real receipt acceptance.

## Resume conditions

Resume the four jobs only when the job route targets the current authoritative
database, every prior in-flight operation is reconciled, duplicate/replay tests pass,
and an independent verifier confirms the real route. Never resume against the old
Tokyo file after Korea becomes authoritative.

## Korea-first rollback

Lock Korea Writer first; revoke its write credential/IP/epoch; reconcile all unknown
exchange outcomes; restore a reconciled Tokyo checkpoint and grant a new Tokyo epoch;
then, and only then, resume the four jobs against the restored Tokyo authority. No
step may assume a timed-out command had no side effect.
