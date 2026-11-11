# Tokyo -> Korea real-infrastructure preparation

Task: `TOKYO_KOREA_REAL_INFRASTRUCTURE_PREPARATION_6168475895`

This package follows the candidate-only independent pass in PR99 comment
`6168449880` and the next-action card `6168475895`.  It does not reopen or
modify S1-S5.  The exact candidate remains commit
`f733cd4eca6be23e41be185f7d6421d0ff9cd522`, tree
`31c262997b3850450cb7c1da2b4d9c472d9cf0ff`.

## Business outcome and boundary

The intended outcome is one reviewable, fail-closed operation package for a
future Tokyo-to-Korea migration.  This batch only collected read-only host
evidence and prepared the package.  It did not stop or deploy a service,
retire a Runner, change a credential or IP allowlist, call Binance, freeze a
database, start a Writer or scheduler, touch an order, or repeat backup,
decrypt, extract, or restore work.

`execution_authorized=false`, `production_migration_release=HOLD`, and PR99
must remain Draft.

## Read-only evidence collected

### 95 Writer candidates

The frozen discovery was replayed from the exact candidate tree against the
same two roots.  It reproduced all `95` records and the prior digest
`c80ccec7548264dce4322413d423a9a98869a3cb0f1675d27f91906a64068b65`.
Class counts remain `FORMAL=12`, `LEGACY=17`, `MANUAL_SCRIPT=58`, and
`PROTECTION=8`.

The private per-path map records the source hash, conservative marker,
static role, current process/systemd reachability, credential-reference
category, proposed fence/quarantine treatment, and unresolved inventory
fields.  Its redacted aggregate is:

- `DIRECT_WRITE_CAPABLE_SOURCE=81`
- `WRITE_ORCHESTRATION_OR_HELPER=9`
- `OFFLINE_OR_TEST_MARKER_HIT=4`
- `CONSERVATIVE_MARKER_ONLY=1`
- direct execution of one of the 95 exact source files observed in current
  process argv or systemd unit files: `0`
- files with static credential-reference categories: `64`

These are source classifications, not proof of runtime safety.  The Gateway
automation inventory available to this turn was caller-scoped, and root,
`yibi`, and `githubrunner` crontabs were outside the available privilege.
Therefore every `not observed` result remains subordinate to
`GLOBAL_TRIGGER_INVENTORY_INCOMPLETE`, and G3 stays
`HOLD_NOT_INTEGRATED`.

The full map is retained privately under the Xuanjun coordination artifact
directory.  Only its count and digests are suitable for the public PR.

### Production Runners

Direct host evidence at the capture point showed:

| Host | Unit | State | Listener | Unit file |
| --- | --- | --- | --- | --- |
| Tokyo `iZ6wee8q9z4t03hvqumwfhZ` | `actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.xuanjun-tokyo-readonly.service` | `active/enabled`, restart count `0` | present | `root:root`, mode `0664` |
| Korea `iZmj7a5kwr75qc1tul4kf9Z` | `actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.xuanjun-korea-binance.service` | `active/enabled`, restart count `0` | present | `root:root`, mode `0664` |

On both hosts, `sudo -l -U githubrunner` exposed only the fixed, zero-argument
`/usr/local/sbin/xuanjun-migration-inspect-v1` grant.  The helper hash remained
`61bed97a32e970dd868f2d223c68ab41c012c484d314cb714c768629aac263c2`.

The current tool surface has no GitHub administrative Runner inventory or
remove-token capability.  Local service/process evidence therefore does not
prove the current GitHub administrative registration record, and the future
G1 operation is blocked until an authorized GitHub administrator can baseline
and verify agent IDs `4` and `3`.  Workflow-local skipping remains irrelevant
to global isolation.

Temporary helper/sudoers retirement is a separate explicit phase after both
Runner removals and independent SSH/OpenClaw canaries.  It must not be bundled
implicitly with Runner exit.

### Korea Yibi retirement and shared-service protection

The complete declared Yibi unit set exists:

- active/enabled: `yibi-api.service`, `yibi-scheduler.service`;
- static/inactive: `yibi-daily-report.service`,
  `yibi-health-check.service`;
- disabled/inactive: `yibi-mailbox-reader.service`,
  `yibi-worker.service`;
- active/enabled/waiting: `yibi-daily-report.timer`,
  `yibi-health-check.timer`.

Autostart links exist for API, scheduler, and both timers.  The API listens on
loopback `8000`.  Unit metadata proves API/scheduler depend on shared
PostgreSQL and Redis, so stopping shared dependencies is explicitly forbidden.

Protected baselines were active with zero restarts:

- `xuanjun-novel-factory.service`, listener/runtime preserved;
- `postgresql.service`, loopback `5432`;
- `redis.service`, loopback `6379`.

No Yibi match appeared in the readable system cron files or the `admin`
crontab.  The caller-visible OpenClaw inventory contained no Yibi job, but the
inventory explicitly reported restricted scope.  Root, `yibi`, and
`githubrunner` crontabs and the Gateway-wide OpenClaw inventory are still
`UNKNOWN_PERMISSION_BLOCKED`; permanent retirement may not start until those
unknowns are closed.

The existing archive evidence is reused.  No archive, backup, decryption,
extraction, or restore was repeated.  Failure after any Yibi stop/mask phase
must keep Yibi disabled and may restore only a changed protected shared
dependency; it must never re-enable Yibi.

### Credentials, trust anchor, and G4 preparation

Read-only SQLite metadata in the authoritative Tokyo trading database showed
one active/healthy production `BINANCE_ACCOUNT_READONLY` record with no trade
or withdrawal permission, one active/healthy production `BINANCE_TRADING`
record with trade permission and no withdrawal permission, and one
active/healthy `FINANCE_COLLECTION_READONLY` record.  No credential value was
read or printed, and no Binance endpoint was called.

The production env file exists with mode `0600`; only key-name presence was
checked.  An unloaded process environment must not be confused with a missing
master key.

No detached signature, public key, or independently managed Ed25519 trust
anchor was found in the declared migration evidence/artifact scope.  This is
`NOT_PROVEN_IN_DECLARED_PACKAGE`, not a claim that no key exists anywhere.

The future reconciliation contract is fixed to GET-only calls for server time,
account, balances, position mode, positions, open orders, algo/protective
orders, recent orders, and user trades.  Required symbols are
`BTCUSDT/ETHUSDT/SOLUSDT`; pagination must be complete, exchange/local skew
must be at most `10,000 ms`, and the capture must finish within `30,000 ms`.
Positions, orders, protective orders, recent orders and trades must match the
read-only local mirror, with zero unknown, in-flight, or ownership conflicts.

Existing Owner read-only scripts are not the final-freeze executor: they call
GET endpoints but also create/persist local records.  No real G4 authority
adapter is currently bound to the candidate.  A future executor must open the
production database read-only, write evidence only to a new root-private
artifact location, and prove that all exchange methods were GET.  Until that
adapter and the exact sidecar sources are independently reviewed,
`LIVE_GET_ONLY_RECONCILIATION=BLOCKED_NOT_RUN` and
`FINAL_CHECKPOINT=BLOCKED_NOT_RUN`.

### Korea isolation baseline

The dedicated user `xuanjun_binance` and directories
`/opt/xuanjun-binance`, `/var/lib/xuanjun-binance`,
`/etc/xuanjun-binance`, and `/var/log/xuanjun-binance` are absent.  Candidate
loopback ports `18080/18081/19080/19081` were unoccupied at capture time.
Korea has a root-owned `/usr/bin/python3.11`; the system default remains Python
3.6.8.  The Yibi virtual environment also resolves to `/usr/bin/python3.11`,
but it must not be reused by the new isolated runtime.

`firewalld` and `nftables` services were inactive, so a GET-only outbound
policy is not proven.  A root-managed egress design and a protected credential
namespace compatible with systemd 239 remain required before deployment.

The Tokyo code-only private manifest contains `133` files / `1,096,806` bytes,
excluding venv, runtime, database, backup, log, and secret files.  It is a
source identity, not a deployable release archive; no runtime archive was
built or transferred in this batch.

## Prepared operation package

`production-operation-package.json` binds the exact targets, ordered phases,
side effects, fail-closed responses, acceptance conditions, rollback ordering,
and consolidated human approval nodes.  It is deliberately data-only:

- it contains no credential, token, signing key, IP allowlist value, or order
  instruction;
- it has no privileged executor binding;
- every mutating phase is marked `authorized=false`;
- failure, timeout, partial success, or missing receipt always returns HOLD and
  forbids blind retry;
- Korea must be fenced, credential-revoked and IP-removed before Tokyo can ever
  receive a new Writer epoch during rollback.

## Consolidated blockers and human node

The next review must keep production HOLD unless one later, explicit execution
authorization names all of the following:

1. GitHub administrator baseline/removal verification and two short-lived
   remove tokens delivered through a protected flow;
2. root authority for each host and a bounded maintenance window;
3. Gateway-wide OpenClaw inventory plus root/`yibi`/`githubrunner` crontab
   evidence;
4. independently managed Ed25519 public-key fingerprint and detached signature;
5. reviewed G3 coverage for all 95 paths, with no unknown scheduler or
   credential access;
6. a reviewed no-local-mutation G4 adapter, exact sidecar sources, and final
   freeze duration;
7. an isolated Korea runtime artifact, egress policy, secret namespace, shadow
   duration and canary thresholds;
8. separate authorization for helper/sudoers cleanup, if desired.

Until then:

```text
REAL_INFRASTRUCTURE_READONLY_EVIDENCE=PARTIAL_PASS
OPERATION_PACKAGE=PREPARED_NON_EXECUTING
G1=BLOCKED_GITHUB_ADMIN
G2=BLOCKED_GLOBAL_TRIGGER_INVENTORY
G3=HOLD_95_PATHS_NOT_INTEGRATED
G4=BLOCKED_REAL_ADAPTER_AND_NOT_RUN
G5=BLOCKED_ISOLATED_RUNTIME_AND_EGRESS
PRODUCTION_MIGRATION_RELEASE=HOLD
```
