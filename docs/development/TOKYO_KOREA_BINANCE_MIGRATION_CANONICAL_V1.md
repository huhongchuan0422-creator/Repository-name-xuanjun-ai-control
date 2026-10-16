# Tokyo → Korea Binance canonical migration feature

### 1 Design

`FEATURE_ID=TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1` reuses the existing
canonical migration policy identifier.  The feature moves only the evidence-proven
Tokyo Binance production runtime and required state to an isolated Korea identity.
It does not migrate OpenClaw, Novel, Yibi, Finance/CRM code, website/customer/model
workloads, development runners, or historical artifacts.  Korea phases B/C are
read-only and may load only the dedicated Account Readonly credential.  The Writer
remains locked until a separately authorized single-Writer gate.

The current Tokyo evidence proves no persistent Binance Launcher is installed.
The only code-level production composition point is
`trading_execution.production_factory.build_production_trading_execution_service`;
its only non-test caller is the historical one-shot Owner smoke script.  That script
is not a production Launcher.  The Korea package therefore supplies a real GET-only
Shadow entry and records the missing persistent Launcher binding as a hard Phase-D
blocker instead of selecting one of the 95 candidates.

### 2 Development Sequence

1. Reuse the frozen Root/Gateway/95-path/credential/timer evidence.
2. Supplement the two Root HOLD receipts only for the 17 exact dracut links and the
   erroneous `WALK_COMPLETE` failure classification; do not widen link allowlists.
3. Close Gateway schedule kinds and configured event/stream/session ingress without
   presenting cron inventory as universal trigger coverage.
4. Package and test the isolated Korea GET-only Shadow entry, exact manifest,
   install/check/uninstall scripts, and default Writer lock.
5. Keep Finance/Billing timers running until an exact Phase-D maintenance gate;
   then drain, snapshot, reconcile and preserve one authoritative database route.
6. Establish independent Authority/Verifier custody only after Owner approval.
7. Request exact release authorization phase by phase.  Binance independent
   acceptance precedes Yibi retirement; Tokyo retirement is the final gate.

### 3 Acceptance

- Root supplement binds exactly the original 17 subject hashes on both hosts and
  records link text, target bytes/hash, parent permissions and RPM package source.
- `WALK_COMPLETE` is reported as a collector diagnostic defect, not a host failure.
- admin/root/githubrunner/yibi crontab, user/system systemd, system cron,
  transient units, wrappers and dynamic invocation coverage are classified with
  evidence; all 95 candidates remain UNKNOWN/DENY.
- Gateway output distinguishes the four persisted jobs from stream/event/session
  ingress and states every unresolved authority boundary.
- Korea Shadow runs from a deterministic manifest, refuses trading credentials and
  master keys, exposes no exchange write method, and fails closed for missing
  Authority/Verifier, credential, egress, database or pagination evidence.
- No persistent production Launcher is claimed until the production factory,
  strategy input, risk, protection, monitoring, recovery, database, credential and
  single-Writer Authority chain are bound and independently verified.
- The four Finance/Billing timers have exact pause/drain/final-snapshot/reconcile/
  resume-or-rollback conditions and never resume against a stale Tokyo copy.
- Focused tests, manifest/hash checks and Feature Compliance Gate pass in CI.
- Deployment, Binance calls, Shadow/Canary, Writer transfer, service control,
  credential/network changes, Yibi retirement and Tokyo retirement remain HOLD.

### 4 Failure, unknown outcome and rollback

Failure before an exchange request is a terminal HOLD for that attempt.  Timeout,
partial response, process loss or an unverified exchange result is UNKNOWN: retain
the transaction/epoch, capture process/session/database evidence, independently
reconcile, and never blind-retry.  Restart first runs recovery and refuses new
entries while UNKNOWN/inflight/ownership/protection mismatches exist.

Rollback is Korea-first: lock the Korea Writer, revoke its write credential/IP/epoch,
reconcile every unknown exchange result, restore the last accepted authoritative
database route, and only then issue a new Tokyo epoch.  Double Writer and stale-copy
timer resume are forbidden.

### 4 Fixed Phase-C root channel candidate

Owner requested a usable root execution channel. `migration-prep/korea/phase_c_channel.py` accepts only inspect/install; `grant_phase_c_channel.py` authenticates a separate exact independent grant approval before installing two no-wildcard sudoers commands. The frozen e9052b4e handoff and archive remain pinned, with their own private exact C install admission still required. This channel grant never installs C or runs services/nft/GET/DB operations. The new tests are registered through `tests/test_pr99_phase_c_channel.py`; real account/systemd/grant operations are models, Hosted visudo parses only temporary policy files. Root grant and migration remain NOT_EXECUTED until exact approval and Owner-root action. Operational contract: `migration-prep/korea/PHASE_C_CHANNEL.md`.
