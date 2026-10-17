# Owner one-time completion sheet

This is one consolidated human action. It does not authorize production execution.

## 1. GitHub personal repository settings export

The repository owner is a **User**, not an Organization. Organization runner-group
and allowed-repository APIs are therefore `N/A` unless the UI explicitly shows that
the runner is organization-scoped.

Open repository **Settings → Actions → Runners** and export one screenshot/PDF showing
runner name, ID, status, labels, scope and any group. Then open **Settings → Actions →
General** and export: allowed Actions/reusable workflows, fork pull-request approval
policy, workflow token permission, and whether workflows may approve PRs. Finally,
export the workflow list and every `runs-on` value used by the exact PR head.

Already collected evidence (repo/workflows, host runner IDs/names/pool and zero
current `Runner.Worker`) must be reused. Do not re-export code. The current connector
does not expose Runner/Actions administration endpoints, which is the precise reason
for this UI-only item.

## 2. Independent Authority and verifier proposal

`NOT_PRESENT` means missing release evidence, not permission to proceed. Reuse the
existing signed-policy executor and acceptance verifier; do not create a new platform.

* Owner names an Authority custodian who is not the developer or verifier. The
  custodian keeps an Ed25519 private key in existing protected/offline custody and
  publishes only the public anchor and its hash.
* Owner names a different verifier custodian. A root-owned verifier and public anchor
  are bound by exact file hashes on the target host.
* Each authorization signs exact repository head/tree, runtime-manifest hash, policy
  hash/ID, phase, host/path/unit/action, database authority epoch, expiry and unique
  nonce. Nonces cannot cross transactions.
* The executor verifies before action; the independent verifier checks the real host,
  database and exchange result afterward. A developer signature or self-verification
  is invalid.

Creation, key installation and signing are outside this authorization and require
independent review plus Owner approval.

## 3. Suggested parameters for one Owner confirmation

These are evidence-based suggestions, **not approved values** and not permission to
trade.

| Parameter | Suggested value | Basis/stop rule |
|---|---:|---|
| Read-only Shadow | 24 continuous hours | covers daily behavior; restart proof required |
| RSS | p95 ≤ 512 MiB, peak ≤ 768 MiB | preserves 2 GiB host headroom |
| Host memory | `MemAvailable` ≥ 512 MiB; swap growth ≤ 128 MiB | stop on breach/OOM |
| CPU | p95 ≤ 70% of two cores | stop on sustained saturation |
| Disk | free ≥ 20% | stop before evidence/database pressure |
| GET latency | p95 ≤ 2 s, p99 ≤ 5 s | any timeout/UNKNOWN stops acceptance |
| Restart | cold start ≤ 60 s; reconciliation ≤ 120 s | no blind retry |
| Mismatches | 0 decision/position/order/protection/UNKNOWN/inflight | any one fails |
| Canary | at most 1 new entry, 15 minutes, total notional cap 10 USDT, maximum planned loss 1 USDT | suggestion only; exchange minimum and Owner cap both apply |
| Canary stop | any rejected guard, missing protection after 5 s, mismatch, timeout, UNKNOWN, unexpected fill or >1 USDT projected loss | lock Korea first |
| Maintenance | Tue–Sun 02:00–03:30 Asia/Shanghai | avoids known daily/weekly timer times; four 5-minute timers still need gated pause |
| Rollback | lock/revoke Korea within 5 min; reconcile within 15 min; Tokyo authority decision within 30 min | Korea-first, no double Writer |

Roles to confirm once: Owner parameter approver; independent Authority custodian;
independent verifier; Release Gate approver; evidence custodian. One person must not
occupy developer, Authority and verifier roles together.
