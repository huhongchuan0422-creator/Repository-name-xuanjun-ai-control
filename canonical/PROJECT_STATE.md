# Canonical Project State

ARCHITECTURE_VERSION=V2.7
CONTROL_REPOSITORY=huhongchuan0422-creator/Repository-name-xuanjun-ai-control
CURRENT_STAGE=0
CURRENT_BATCH=STAGE0_ASSET_AUDIT
CURRENT_TASK=XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1
STATUS=IN_PROGRESS

## Owner priorities
1. Read and follow V2.7.
2. Re-audit Tokyo reusable assets.
3. Deploy/migrate the UK development control plane.
4. Migrate Binance production from Tokyo to Korea with isolation, shadow/canary, rollback and evidence.
5. After these migrations, continue strictly in V2.7 dependency order.
6. Interrupt Owner only for genuine human verification/authorization.

## Safety
TOKYO_TRADING_PRODUCTION_WRITE=DENY_UNTIL_MIGRATION_GATE
UK_TRADING_PRODUCTION_WRITE=DENY
KOREA_BINANCE_TARGET=ISOLATED_PREPARE_ONLY_UNTIL_CANARY
SECRETS_IN_GIT=DENY
MAIN_DIRECT_AGENT_PUSH=DENY

## Verified facts
- Private GitHub control repository exists and ChatGPT has push/admin-level repository permission through the connected GitHub integration.
- ChatGPT -> GitHub -> GitHub Actions -> log read -> automatic code repair -> rerun -> PASS was proven in an isolated V1 test repository.
- Tokyo canonical trading root was observed at /opt/trading-system.
- Tokyo discovery evidence from 2026-10-10 reported TOKYO_PRODUCTION_MUTATION=NO and MIGRATION_EXECUTED=NO.
- UK runtime/server facts are NOT_VERIFIED from available evidence.
- Korea is an existing isolated environment for novel/EasiCoin; Binance target capacity and isolation are NOT_VERIFIED.

## Next executable dependency
Establish authenticated self-hosted Runner execution paths for UK, Korea, and a Tokyo read-only migration source. Until then, repository-side preparation continues; server-side mutation remains blocked.
