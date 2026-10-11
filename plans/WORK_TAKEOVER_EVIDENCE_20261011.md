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
  Preserve Sol-only and zero fallback; inspect actual provider/account/model
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
