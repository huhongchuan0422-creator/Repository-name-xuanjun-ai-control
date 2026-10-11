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
enforce the previous model. This policy document does not alter those programs
or production configuration and must not be reported as a deployed repair.

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
