# XUANJUN_EXISTING_ASSET_MAP_V1

Evidence status vocabulary: REUSE / EXTEND / MIGRATE / DEPRECATE / MISSING / NOT_VERIFIED.

| Asset | Location | Status | Evidence / known path | Intended use |
|---|---|---|---|---|
| Binance canonical project | Tokyo | MIGRATE | /opt/trading-system | Source for controlled Korea migration |
| Trading execution | Tokyo | MIGRATE | /opt/trading-system/trading_execution | Preserve behavior; migrate by artifact/config evidence, not redesign |
| Binance integration | Tokyo | MIGRATE | /opt/trading-system/binance_integration | Controlled Korea migration |
| CRM | Tokyo/Domestic assets | REUSE | /opt/trading-system/crm and Domestic runtime packages | Shared abstraction where V2.7 requires |
| Finance/Billing | Tokyo/Domestic | REUSE/EXTEND | finance-collection-sync.service; backups and runtime assets | Reuse for 玄钧AI新 Finance Core; do not rebuild |
| Customer/Common Brain | Tokyo/Domestic | REUSE | domestic-real-ai-runtime artifacts; Customer Brain r10 evidence | Reuse model/provider-neutral patterns |
| Model RPC | Tokyo/Domestic | REUSE | tokyo-restricted-model-executor.service; domestic-model-rpc-tunnel.service | Reuse patterns/interfaces |
| OpenClaw | Tokyo/Domestic | REUSE/MIGRATE | existing OpenClaw binaries and gateways | Reuse for UK standard runtime |
| Windows Operator | Domestic/Windows | REUSE | existing Windows interaction stack | Human/platform recovery only |
| Monitoring/backup | Tokyo/Domestic | REUSE/EXTEND | /opt/trading-system/monitor, backup, backups | Adapt to UK/Korea |
| Secure SecretRef | Tokyo/Domestic | REUSE/EXTEND | runtime secretref stores / secure portal | Never copy raw secrets into Git |
| GitHub control plane | Private GitHub | EXTEND | this repository | Canonical Git/CI/task/evidence plane |
| UK development server/runtime | UK | NOT_VERIFIED | no authoritative runtime evidence available yet | Stage 1 target |
| Korea existing environment | Korea | EXTEND | novel/EasiCoin environment known; Binance capacity not verified | Create strict Binance isolation target |
| Korea Binance production | Korea | MISSING | migration not yet executed | Target after preflight/shadow/canary |

## Tokyo reusable asset snapshot
Observed candidates include: signal, ai_service, crm, binance_integration, accounts, tests, artifacts, knowledge, deployment, scripts, core, trading_execution, research, logs, monitor, database/models, secure secret references, deployment assets and extensive versioned backups.

## Rules
- No architecture-wide rewrite of an EXISTING_AND_REUSABLE capability.
- Do not copy production secrets into repository artifacts.
- Any migration must preserve rollback and production-side evidence.
- Unknown stays UNKNOWN/NOT_VERIFIED; never convert absence of evidence into PASS.
