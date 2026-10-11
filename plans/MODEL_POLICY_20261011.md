# Current temporary UK development model policy — 2026-10-11 20:22 CST

CURRENT_PRIMARY=openai/gpt-5.6-sol
CURRENT_FALLBACKS=[]
CURRENT_ALLOWED_MODELS=openai/gpt-5.6-sol
CURRENT_SCOPE=UK_DEVELOPMENT_TASK_AND_COORDINATING_REPLIES_TEMPORARY
AUTOMATIC_6_1_PROBE_OR_RESTORE=DENY_UNTIL_EXPLICIT_OWNER_AUTHORITY
PAID_API=DENY
PRODUCTION_CONFIGURATION_MUTATION=NOT_AUTHORIZED

Owner confirms the temporary policy is only verified5.6, zero fallback. Work
read PR comment6108962828 and received the Owner confirmation at20:22:22 CST.
The comment attributes an earlier instruction to16:06:45 CST; that earlier
timestamp is executor-reported. Current confirmation is the authority adopted.

V3 governs current task model semantics and overrides the old6.1-primary rule
in original spec.models and V2.model_policy_guard. Original bytes/digests are
retained as history. Desired dashboard policy tests may assert primary5.6,
fallbacks=[] globally for this current task, not merely for one Worker attempt.
Actual model/provider remains UNKNOWN unless observed. No fresh model canary,
provider/account switch, production config change or automatic6.1 restoration.

The old a1fa6351 diff digest is provenance. NOT_VERIFIED old raw bytes does
not block authorized semantic repair; B may generate a corrected diff/new hash.
Continue original task/checkpoint/remaining budget and all quality gates.
If verified5.6 is unavailable, checkpoint model work; no fallback is permitted.

## Historical policy and model acceptance evidence
The following older6.1-primary/5.6-fallback policy is superseded for the current
UK development task wherever it conflicts with the operative section above.

# Owner model policy — 2026-10-11 13:49 Asia/Shanghai

This explicit Owner instruction supersedes earlier Sol-only / zero-fallback
requirements for development and OpenClaw replies. It does not change deployment,
trading, database, credential or formal webhook permissions.

## Desired policy (not evidence of active production configuration)

- Primary: `openai/gpt-6.1-sol` (`gpt-6.1-sol` for Codex CLI).
- Sole fallback: `openai/gpt-5.6-sol` (`gpt-5.6-sol` for Codex CLI).
- No Astra, Luna, Terra, other model, or unrestricted model/provider alias.
- Use the existing authorized authentication route. No automatic API-key billing
  or account substitution. Quota telemetry without evidence stays UNKNOWN.
- A model/account unsupported response may select the verified fallback. Generic
  code failures, failed CI/QA, lease loss and prompt/parameter errors must not be
  treated as model unavailability. Unknown inference outcomes must be reconciled
  before retrying any task that could have changed files or other state.
- Limit a logical attempt to the primary and sole fallback, without recursively
  replaying the task. If neither is usable, checkpoint and pause the affected
  model-dependent path; independent deterministic tasks continue.
- Recovery checks use a bounded, non-delivering, read-only minimal primary
  inference, with cooldown and one probe owner. Catalog availability alone is
  insufficient. Switch back only at the next safe task/turn boundary after a
  successful actual primary inference; never replay completed side effects.
- Record requested model, observed model/provider (UNKNOWN if absent), switching
  reason, time and checkpoint separately. Keep independent QA, security review
  and ReleaseGate requirements for either model.

## Live evidence and activation work

The UK host `iZd7oeikknn1z21sq6ji6zZ` returned HTTP 400 for the existing
ChatGPT/Codex route: gpt-6.1-sol is not supported on that route. This is not proof
of quota exhaustion or a general prohibition on all ChatGPT accounts.

Latest Owner-assisted evidence verifies real 5.6 minimal inference and activates
5.6 as the sole fallback; primary and exact two-model allowlist are preserved.
Feishu real reply, bounded failover and primary recovery remain NOT_VERIFIED.
Worker candidates permit both models but require observed model/provider evidence;
their automatic failover/recovery transport integration remains pending. The
root-pinned Sol-only diagnostic is historical and must not be rerun now.
See the latest acceptance section below; earlier failures are retained as history.

Activation requires checking the installed OpenClaw/Codex version and actual
allowlist, agent/session overrides and authentication route; minimally verifying
5.6 through that route; backing up and applying a reviewed exact configuration
change with a single configuration writer; and verifying actual Feishu reply,
bounded failover and safe recovery. Do not blindly rerun the old Sol-only canary
after enabling a fallback: it intentionally rejects a nonempty fallback list.

References: https://learn.chatgpt.com/docs/models,
https://developers.openai.com/api/docs/models/gpt-5.6-sol,
https://docs.openclaw.ai/concepts/models,
https://docs.openclaw.ai/concepts/model-failover.

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

## Latest UK real inference acceptance — 2026-10-11

Source: Owner-posted output of the root/UK-host/hash-guarded
scripts/uk-codex-post-align.py staged from commit
2a44143da7cbb3a0794bf3a08d73ea4ce701ca83; source SHA256
046f49f137117d288f7bd0ef98604bdb2e344a242413d33f443046eedb96b97d.
This is Owner-assisted live evidence, not an independent Runner reproduction.

- Selected plugin inspection exits 0; selected @openclaw/codex is 2026.9.9,
  declared and installed Codex versions are both 0.160.0; policy_ok=true.
- install_repeated=false: the successful continuation did not repeat installation.
- Actual fresh 5.6 request exits 0, exact_reply=true,
  returned_model=openai/gpt-5.6-sol, returned_provider=openai,
  inference_verified=true, error_code=NONE.
- sole_fallback_configured=true: the validated CAS configuration activation
  completed. Primary remains openai/gpt-6.1-sol, sole fallback is
  openai/gpt-5.6-sol, allowlist remains exactly these two models.
- subscription_quota_pool=UNKNOWN. No unauthorized API billing was enabled.
- channel_delivery=false, feishu_e2e=NOT_VERIFIED, production_pass=false.
  Bounded primary-to-fallback routing and primary recovery remain NOT_VERIFIED.
  The prior 5.6 403 is historical: this new minimal inference passed. The exact
  cause of the earlier rejection is not proven solely by this success.
- No new dispatcher/dashboard deployment, container isolation acceptance,
  database migration, trading permission change or formal webhook cutover is
  established by this result.

The original Sol-only fixed diagnostic must not be reused with a nonempty
fallback list. Do not repeat the successful installation or minimal 5.6 probe.
Next model-path acceptance is an Owner-initiated Feishu reply through its actual
route, with observed model/provider evidence; an echo alone is not a complete
failover/recovery or autonomous-development E2E acceptance.

## Feishu receipt and worker/control-gate increment — 2026-10-11

Owner posted the actual Feishu reply to the requested marker:
XJ_FEISHU_56_OK. Owner-observed channel receipt is PASS; the pasted reply has
no provider/model metadata, so the model used for this Feishu turn remains
NOT_VERIFIED. This does not establish bounded failover or 6.1 recovery.

Candidate code adds CodexAppServerWorker using the official stdio protocol:
initialize, account/read (existing managed ChatGPT only), thread/start with
native resolved model/provider, correlated turn/start and turn/completed.
It rejects API-key/unknown auth before starting a thread, mismatched/absent
native model evidence, model reroute, cross-thread/turn events, unapproved
server requests, delegation/MCP/dynamic tools, duplicate message identities,
lease loss, timeout and output overflow. It does not copy credentials, log in,
send channel messages, retry a possibly mutating task or deploy.
HOME and CODEX_HOME must be canonical and disjoint from the worktree; tool
read access is restricted and workspace tool networking disabled. External
per-job OS/cgroup containment and dedicated authentication remain separate
activation requirements; these must be verified before real code dispatch.

Ordinary CLI-backend tasks now cannot modify their own worker/dispatcher,
ledger, approval routing, AGENTS/config enforcement, workflow or installer/
systemd control paths. Both pre-commit index and full pre-push history are
checked. Reviewed base code remains readable; trusted maintenance remains
separate from generated code acceptance. Independent security/release review
is still required; this path check is not a complete four-layer acceptance.

Local regression: 204 tests PASS, including real OS-pipe protocol fixtures.
Fixtures are explicitly simulated and do not attest a UK Worker inference.
UK integration/CI for this increment must be checked separately.
An additive push trigger invokes the existing four-server read-only inventory
when its workflow changes on this feature branch; production writes are not
part of that inventory. Runner access, capacity and migration results remain
unverified until actual job evidence is collected.

Next: verify this candidate on the UK Runner, resolve isolated Worker auth and
containment, obtain controlled dispatcher activation and independent review,
then accept two real development tasks with exact-commit CI/QA/checkpoint
continuation. Do not submit CODEX_EXEC to the old Coordinator.
Official protocol reference: https://learn.chatgpt.com/docs/app-server.
