# V2.7 execution and agent gates — 2026-10-10

## Scope and authority
V2.7 architecture remains canonical. This control repository is Git/CI/evidence orchestration only, **not** a new Task Registry, secret store, or production authority. Do not deploy new trading, finance or CRM runtime from this batch. Status must come from executed evidence, not these plans.

## Current confirmed
- UK and Korea self-hosted runners installed; earlier preflight status reported PASS, independently recheck with batch.
- Tokyo runner `xuanjun-tokyo-readonly` registered and systemd active/enabled. First tokyo-discovery job succeeded. Recursive permissions/trust boundary remains PARTIAL.
- Domestic runner `xuanjun-domestic-ops` registered and systemd active/enabled per Owner SSH 2026-10-10 21:09 CST; first GitHub job pending.
- V2.7 Stage 1 overall NOT VERIFIED. Binance Korea migration not executed. No implicit production authority.

## Smallest executable sequence
1. Manual dispatch of `V2.7 Four Server Read-Only Batch`. Review every job and record unknowns.
2. Evaluate runner threat model: repository workflow author can run shell as runner account; `contents: read` is NOT local filesystem isolation. Ensure production secrets and sensitive configurations are unreadable by runner, check ACLs and writable subtrees without publishing secret values. Require protected environment, restricted dispatch authors, review controls for workflows; ideally a truly isolated minimal-privilege execution service for production inventories.
3. Stage 0 asset map: inventory existing Tokyo/Domestic services, configs by sanitized hash and schema; confirm UK assets and Korea isolation; do not copy credentials or production data to GitHub. Existing asset `REUSE/EXTEND/MIGRATE/DEPRECATE/MISSING/UNKNOWN`.
4. Stage 1 UK nodes 1.1–1.6 first; reuse Git, Docker, Runner and prior audit. Only the missing parts of 1.3/1.4/1.5/1.6 should be implemented. Node 1.7 OpenClaw from verified existing code/config migration without production credentials.
5. Nodes 1.8–1.15 only after existing Task Registry, Canonical State, Model Router, Gateway and Agent Orchestrator evidence are read. Avoid duplicate implementations.
6. Korea Binance migration is separate gated track. 2C/2GB memory preflight and novel/EasiCoin collision checks before deploying. Shadow mode NO_ORDER_WRITE, position/state reconciliation, recovery/rollback, then separately authorized bounded cutover before Tokyo expiry.

## Six on-demand roles (V2.7 §9.5)
- PROJECT_COORDINATOR: fast Owner acknowledgement, structured task assignment and exception summary; no long blocking work.
- DEVELOPER: task branch; dev/test implementation; no protected main or production write.
- TEST_QA_ENGINEER: independent criteria and verification; read-only frozen artifact.
- INDEPENDENT_AUDITOR: security, policy and critical correctness; cannot modify audited commit.
- INFRASTRUCTURE_PLATFORM_ENGINEER: blueprint and isolated dev env only; deployment via scoped gateway.
- SRE_SECURITY_ENGINEER: monitoring, rollback, IAM checks; never bypass Release Gate.

Start by mapping verified existing agents and queues onto these roles; do **not** install six speculative daemons. Only coordinator is responsive to Owner; tasks use async queue/lease; max two heavy tasks, depth <=1, 3 patch attempts total, stop after repeated same fingerprint; all limits subject to verified resources. The 10s acknowledgement and 60s task ID are acceptance targets, not claims of production performance.

## GitHub/open source reuse gate
- First check Tokyo, Domestic, UK, this repo, prior modules, Canonical, tests.
- For a genuinely complex generic missing component, programmatically shortlist up to 3 mature, maintained candidates and verify *actual LICENSE*, maintenance, SAST, dependency security, sandbox. Record in OPEN_SOURCE_REUSE_REGISTRY. Simple components are implemented directly. Do not pull third-party code into production or dev control plane without quarantine review.

## Security gates
- No raw secrets, environment dumps, customer identifiers, tokens, production Git patches or full logs in Actions outputs/artifacts.
- Jobs here are diagnostic only and explicitly opt-in via manual dispatch; successful workflow output does not establish protected production permissions.
- No generic unrestricted shell execution, no sudo grants, no Docker group for prod runner, no change to trading/finance routes.
- Any new production write requires separately evidenced permission, approved Release Gate, reversible deployment and measured Canary.
- Await exact evidence for human-only 2FA, API whitelist, approval and payments. Other branches continue independently.

## Acceptance & documentation
Evidence references: job URLs, timestamps, exact commit, environment, tested constraints, relevant error fragments. Preserve UNKNOWN. Node state may be PASS only when all V2.7 acceptance criteria hold. Update canonical state after each independently validated gate.
