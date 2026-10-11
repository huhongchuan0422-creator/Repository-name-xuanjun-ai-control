# Work takeover evidence — 2026-10-11

Owner requests continuation of PR #17 without repeating completed deployment.
Observed source HEAD: cc3dcaa8b48e86bbb1880eb4180a83d344f47b56.

## Verified

- PR remains OPEN/Draft; no submitted GitHub reviews or discussion comments.
- Complete local suite independently rerun: 149 tests pass.
- UK integration run 38112633240, rerun job 114394691684:
  149 tests pass on the actual UK Runner at 05:08:55Z.
- At 05:09:07Z the fixed root audit reports OpenClaw, Coordinator,
  callback, dashboard, domestic customer tunnel and notification timer active.
- Dashboard loopback `/` and authenticated `/api/state` both return HTTP 200.
- Existing model configuration is openai/gpt-6.1-sol, fallback count zero.
- Production database has no execution ledger/spec/heartbeat side tables yet.
- Production Coordinator source hash remains
  70e0d03412f7729f396652df041930f689a6ea674e4e33bf370da1e40a90f9c7.

## Not verified / pending

- Exclusive production executor: NOT_VERIFIED. UI running state is not evidence
  of activity or inactivity. Read-only observation must precede any cutover.
- HTTPS dashboard URL: NOT_VERIFIED. nginx is inactive; another TLS server
  or upstream has not been inspected. Do not reinstall an active dashboard.
- Actual Sol inference and subscription entitlement: NOT_VERIFIED. Conventional
  Codex binaries and `/home/xuanjun_dev/.codex/auth.json` remain absent.
  OpenClaw main auth-profile files also absent at the two inspected paths.
  This does not rule out another configured authentication location.
- Owner reports Feishu error: selected model unavailable from the provider.
  This establishes a failed channel inference, not quota exhaustion.
  Historical policy was Sol-only and zero fallback; inspect actual provider/account/model
  catalog before changing authentication or provider configuration.
- Owner APPROVE/REJECT production route, per-job containment, controlled
  dispatcher activation, two real AI tasks, exact-commit CI/QA and checkpoint
  recovery remain pending. No CODEX_EXEC tasks may enter the old dispatcher.

No production deployment, schema migration, Telegram webhook change or trading
permission mutation was performed by the takeover. Production status: PARTIAL.

New PR CI runs the entire regression suite, including autonomous loop and QA
tests. Read-only takeover workflow exports source fingerprints and modification
times without process arguments, environment variables or credentials. It does
not claim to acquire an exclusive production writer lock.

## Owner-assisted actual model check at 05:21Z

Owner executed the hash-pinned Sol canary from commit 734bf7fa620989300575cb0e1d1e6e200f39edf0.
The OpenAI catalog before and after refresh both contain gpt-6.1-sol with
available=true. Actual Gateway agent request exits 1; no exact reply or returned
model/provider metadata is present. Inference is FAILED, cause UNKNOWN; do not
infer quota exhaustion or substitute another model.

The previous diagnostic discarded unclassified CLI stderr. A corrected bounded
diagnostic preserves credential-redacted error lines and recognizes Gateway
permission/transport and Codex runtime failure classes. The fixed no-argument
Runner capability is for this diagnostic only, never a shell or deploy command.

## Actual account-path rejection at 05:34Z

Owner installed the hash-pinned fixed no-argument diagnostic successfully on
the UK host. The real canary returned HTTP400 invalid_request_error:
`The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account.`
This is an account/client/runtime-path rejection, not evidence of quota
exhaustion. Which account eligibility, client version or runtime routing causes
it is still NOT_VERIFIED. Official model documentation says availability varies
by account and client; do not generalize this result to all ChatGPT sign-ins.
Feishu real reply remains unverified. No fallback or API purchase was enabled.
Do not rerun identical inference without new evidence or a targeted correction.

The exact rejection is already preserved in the bounded masked diagnostic even
though its narrow error classifier currently labels it UNKNOWN. Classification
alone does not change the live error. Preserve the installed helper's pinned
bytes pending an actual runtime/authorization correction.

Owner now requires all Tokyo assets migrated before 2026-10-20 (Asia/Shanghai):
development to UK, Binance production and Telegram forwarding to Korea,
operations on domestic. UK may also temporarily host community split and
public-welfare video projects with independently verified project/environment
isolation. See plans/TOKYO_MIGRATION_DEADLINE_20261020.md.

At 2026-10-11 13:49 Asia/Shanghai, Owner explicitly authorized 6.1 Sol primary
and 5.6 Sol as the sole fallback, with automatic safe recovery to 6.1 Sol.
This supersedes earlier no-fallback instructions. No live model configuration
has been changed by this documentation update. See plans/MODEL_POLICY_20261011.md.

## Owner-assisted 5.6 preflight at 06:48Z

Owner executed the hash-pinned 5.6 probe staged at commit 87655e84. It stopped
with NOT_STARTED_OAUTH_ROUTE_UNCONFIRMED before catalog refresh or inference.
This is not evidence that 5.6 is unavailable or that OAuth credentials expired.
The preflight incorrectly required provider and credential type on the same
JSON object; nested provider envelopes could therefore reject valid auth.
The corrected candidate inherits provider scope in the provider-filtered auth
response and emits only enum auth evidence plus masked diagnostics. Unknown,
foreign-only or mixed API-key auth remains blocked. Production model config,
login and channels have not been changed. Corrected live probe is pending.

## UK Owner evidence at 2026-10-11 15:00 Asia/Shanghai

Source: Owner-posted host-guarded command outputs; not an independent Runner
reproduction. Host: iZd7oeikknn1z21sq6ji6zZ (UK).

- Owner applied a native-validated, backed-up atomic configuration update. The
  defaults allowlist is exactly openai/gpt-6.1-sol and openai/gpt-5.6-sol. A main
  agent explicit model policy, if present, was updated to the same allowlist.
- Backup: /home/xuanjun_dev/.openclaw/openclaw.json.xj-model-backup-fac5565d095b47f3b7ee169c403a3640.
- A fresh isolated main-agent 5.6 request then failed with HTTP 403:
  "Codex cannot verify the owner of this model request. Start a fresh request before retrying."
  No exact nonce reply or returned model/provider was verified. The earlier
  model-allowlist denial is no longer the observed failure. This new error does
  not establish expired OAuth, quota exhaustion, or 5.6 account incompatibility.
- The follow-up read-only version/config check reports OpenClaw 2026.9.9,
  managed Codex 0.158.0, primary openai/gpt-6.1-sol, fallbacks=[], and the exact
  two-model allowlist. No app-server command override was configured;
  homeScope/transport were DEFAULT_OR_UNKNOWN, not a verified explicit value.
- Production configuration mutation occurred for the allowlist only. Sole
  fallback activation did not occur because actual 5.6 inference failed.
  Feishu E2E, bounded failover, primary recovery and production loop remain
  NOT_VERIFIED. No channel delivery or production cutover was performed.

Upstream OpenClaw source at 11d3d04a1279781a770f6a6aa09e6322b064b80a,
extensions/codex/src/app-server/inference-dispatch.ts, emits the exact Owner
error at multiple request-metadata/custody authorization failures. Issue
https://github.com/openclaw/openclaw/issues/165739 describes the same message
for re-tasked native children, but our fresh main-agent CLI request is a different
scenario. Installed source equivalence and the rejected custody step are
NOT_VERIFIED. This is a diagnostic lead, not a confirmed cause or fixed release.
Next: identify the actual installed plugin and redacted admission/causal metadata
before choosing a narrowly scoped repair. Preserve ownership enforcement; no
wildcard policy, speculative credential replacement, paid API substitution,
repeated unchanged inference, or blind runtime upgrade.

## Installed UK plugin identity, Owner output at 15:21 Asia/Shanghai

Owner's root read reports managed @openclaw/codex 2026.9.8, declared dependency
@openai/codex 0.158.0, and actual @openai/codex 0.158.0. The plugin and its
binary match each other; core remains 2026.9.9. The extensions/codex path was
NOT_READABLE_OR_INVALID and does not establish a broken managed install.
The official v2026.9.9 plugin requires Codex 0.160.0. Comparing official plugin
manifests at v2026.9.8 and v2026.9.9 found identical declared capabilities and
Doctor contracts. The cohort difference is a repair candidate, not a proven
cause of HTTP 403 or evidence that an update fixes inference.

scripts/uk-codex-runtime-align.py prepares one root/host-guarded native repair:
exact baseline check; existing OAuth only; native verified state backup;
config concurrent-change guard; one pinned official plugin replacement through
the running Gateway's drain/publication route with activation policy preserved;
post-install dependency and OAuth checks; one fresh, non-delivering 5.6 probe.
Only verified exact reply plus model/provider evidence permits native-validated
CAS activation of 5.6 as the sole fallback. Timeout/uncertain install is never
retried automatically. No service restart, doctor --fix, login, paid API,
trading change, database restore or formal webhook cutover is performed.
Native installation may perform the declared plugin config/state repairs after
backup, through the native owner. Feishu, primary recovery and full failover E2E
remain NOT_VERIFIED even when the individual inference succeeds.

Local validation: 192 tests pass including policy rejection, wrong-host guard,
validation failure, concurrent config preservation and exact fallback config.
Root runtime repair has NOT_EXECUTED until Owner runs the staged hash-pinned
program; its CI staging is not deployment or production inference evidence.
Official references: https://docs.openclaw.ai/cli/plugins/install and
https://docs.openclaw.ai/cli/backup. Rollback uses the retained native verified
state backup and the exact old plugin package; no live database restore is
attempted automatically because it would discard new state without review.

## Owner runtime alignment attempt, 15:32 Asia/Shanghai

The first native backup failed reading our root-owned 0600 configuration backup
inside .openclaw. No installation or inference occurred in that first attempt.
Owner moved that exact backup to /home/.xuanjun-root-private-backups, preserving
root ownership and 0600 mode; the parent is root-only 0700.
The next attempt returned UK_VERIFIED_STATE_BACKUP at
/home/xuanjun_dev/.xj-runtime-backup-e69ee31a90ad43d1bf8f5b4c60576c9c.
The native pinned installation command returned exit 0, then the script stopped
at STOP_INSTALLED_VERSION_OR_POLICY_NOT_VERIFIED_NO_INFERENCE. This means no
model request or fallback activation ran. It does not establish active-version
success. Our versions() reads the old fixed npm project, which may be stale
after native generation replacement; policy rejection is also possible.

uk-codex-post-align.py inspects selected plugin metadata and resolves the actual
selected package/dependency location instead of reinstalling. Only the exact
2026.9.9/0.160.0 pair, preserved two-model policy and existing OAuth permit a
single new 5.6 request. An exclusive attempt marker prevents unchanged repeated
probes. Verified model/provider and exact reply are required before existing
validated CAS fallback activation. No repeated install, restart or DB restore.
This continuation remains NOT_EXECUTED until the Owner runs its staged hash.
