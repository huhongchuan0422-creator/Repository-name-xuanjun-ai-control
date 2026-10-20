# Migration Sequence V1

## A. Stage 0
1. Read V2.7 canonical architecture and execution order.
2. Confirm Git state and existing evidence.
3. Audit Tokyo, Domestic, UK and Korea execution assets.
4. Produce/revise XUANJUN_EXISTING_ASSET_MAP_V1.
5. Establish secure execution paths.

## B. UK AI Development Control Plane
Follow V2.7 nodes in order:
1. 1.1 Infrastructure Provisioning Foundation
2. 1.2 Source Control Foundation
3. 1.3 Standard Development Environment
4. 1.4 CI Foundation
5. 1.5 Deployment Foundation
6. 1.6 Observability and Recovery
7. 1.7 OpenClaw standard runtime
8. 1.8 Task Gateway
9. 1.9 Node Registry
10. 1.10 Owner Node Review
11. 1.11 Development Drift Guard
12. 1.12 Dot integration
13. 1.13 AI Usage Governor
14. 1.14 AI Eval Foundation
15. 1.15 End-to-end development Canary

UK must not receive TRADING_PRODUCTION_WRITE.

## C. Binance Tokyo -> Korea migration
Migration is a separate production safety track and does not redefine 玄钧AI新 V2.7 architecture.

Order:
1. Korea preflight: CPU/RAM/disk/network/time sync/kernel/runtime/users/firewall/monitoring/backup.
2. Establish dedicated Binance system user, directories, service names, ports, SecretRef namespace and firewall rules isolated from novel/EasiCoin.
3. Tokyo read-only manifest: code commit, dirty state, services, packages, containers, configs by hash, database schemas/state references, timers/cron, dependency locks, runtime versions, model routes, outbound IP dependencies, Binance whitelist dependencies.
4. Build signed/versioned migration artifact; exclude raw secrets.
5. Transfer artifact to Korea.
6. Offline install and deterministic tests.
7. Read-only exchange/API connectivity checks.
8. Shadow execution with NO_ORDER_WRITE.
9. State reconciliation and restart/recovery tests.
10. Canary with explicitly bounded production authority only after all guards pass.
11. Cutover gate: Korea PASS + rollback package + Tokyo retained as rollback source.
12. Post-cutover evidence and observation window.
13. Only then decommission Tokyo trading production components.

## Hard stops
- Missing human login/2FA/API whitelist/secret authorization.
- Any unbounded order-write authority.
- Reconciliation mismatch.
- No rollback evidence.
- UK runner or Korea/Tokyo execution identity not verified.
