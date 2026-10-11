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

5.6 inference, Feishu real reply, two-model failover and primary recovery are
NOT_VERIFIED. Existing worker code and the root-pinned Sol-only diagnostic still
enforce the previous model. The policy document itself does not alter those programs or configuration.
The later Owner-assisted allowlist change below is a separate observed change,
and still must not be reported as an inference or channel repair.

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
