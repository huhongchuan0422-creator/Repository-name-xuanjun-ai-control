# PR99 / PR122 Shared Dependency Ledger — 2026-10-15

Status: `CANONICAL_DEPENDENCY_CANDIDATE / PRODUCTION_HOLD`.

This ledger unifies execution ordering without merging scopes. PR99 remains the
Tokyo-to-Korea minimal Binance runtime candidate at exact HEAD
`632bbe6f204a2c9ef778d3c91e425593c079abb1` / tree
`59a48168764e8465e62fd17a55504c29812365b3`; R2 independent rereview is pending
and accepted R6 evidence is unchanged. PR122 moves the apex website and only
its accepted dependencies to Domestic. UK remains the development and bounded
release-control plane. PR17 receives status only.

| Shared resource | Current host/path or service | Callers | Target ownership | Migration order | Data authority | Acceptance evidence required | Rollback and Tokyo retirement condition |
|---|---|---|---|---|---|---|---|
| `trading.db` | Tokyo `/opt/trading-system/database/data/trading.db` plus WAL/SHM semantics | Trading runtime; four Finance/Billing timers | Korea only after PR99 Phase D; never PR122 static package | PR99 B/C read-only copy → Writer/Authority wiring → exact fence/drain/final snapshot → one Korea epoch | **Tokyo now**; B/C copy non-authoritative | integrity, closed generation, row/cursor/inflight/order/position/protection reconciliation, independent verifier | Lock Korea first, revoke credential/IP/epoch, reconcile Exchange UNKNOWN, restore reconciled Tokyo checkpoint and new Tokyo epoch. Tokyo cannot retire while any authoritative DB or Writer remains there. |
| Finance/Billing timers | Tokyo `finance-collection-sync.timer`, `owner-commercial-ledger-sync.timer`, `billing-operations-weekly-settlement.timer`, `billing-operations-weekly-final-invoice.timer` | Finance collection, Commercial Ledger, settlement, final invoice | Either the four minimal jobs beside Korea DB or a narrow idempotent Korea Finance adapter; **UNKNOWN/HOLD** | Continue unchanged now; pause only in approved Phase D after both migration lines prove no dependency; resume only against authoritative DB | Their writes share `trading.db`; payment scheduler remains disabled and is not one of the four | exact unit/service state, drain, cursor, idempotency/replay/crash recovery, real route receipt | No blind retry. Resume Tokyo only after Korea is fenced and restored authority is reconciled. Website work must not pause them. |
| Credential Portal `18080` | Tokyo `secure-secrets-portal.service`, code under `/opt/trading-system`; apex locations include `/p/`, `/submit/*`, TikTok/Douyin integration and health | Owner/admin intake, exchange credential intake, operations SecretRefs, website integration UI | **SPLIT_REQUIRED/HOLD**: exchange credentials stay trading-side; operations/admin and public OAuth require separately accepted destinations | Do not include in PR99 B/C or PR122 static package. Keep Tokyo route until each endpoint has an accepted successor and callback plan | Credential stores remain their existing protected authorities; no shared master key copied | endpoint-by-endpoint identity, SecretRef routing, no plaintext, callback/CSRF/replay, target service and rollback evidence | Tokyo portal may stop only after every caller is migrated or removed. Apex DNS cannot cut while required routes would silently break. |
| CRM / Customer Context / CommonBrain | Tokyo authoritative source under `/opt/trading-system/ai_service`; Domestic runtime under `/home/openclaw_ops/v8-domestic-operations`; Domestic `customer_context.db` is opened by provider-neutral bridge | Website/customer preview, WeCom, Telegram, AI customer service | Domestic operations core, provider-neutral; never Korea Binance minimal package | Static site can prepare independently; authenticated preview/API/feedback waits for original developer and Domestic service acceptance | Customer/Conversation context authority remains provider-neutral runtime; exact production DB authority **HOLD** until runtime binding is re-proven | tenant/customer/project authorization, restart persistence, cross-channel identity, audit, model metadata, negative cross-tenant tests | Keep current path until new PID/health and business canaries pass. Static page PASS is not CRM/CommonBrain PASS. |
| Model bridge | Existing restricted provider-neutral model RPC/bridge between Domestic and Tokyo-side protected model route; exact final post-Tokyo executor ownership is **UNKNOWN** | CommonBrain/customer assistant; not static rendering | Separate protected executor route; not PR99 Binance B/C and not static bundle | Migrate only after executor, tunnel direction, RPC capability and harmless completion are proven | Model SecretRef remains protected and is not moved by either package | provider/model/responseModel/fallback/latency, RPC capability, redaction, new runtime PID/health | Keep current bridge until accepted replacement; business-bridge health alone is insufficient. Blocks Tokyo retirement, not static package preparation. |
| Telegram | Tokyo token/edge; provider-neutral flow to Domestic core; `/telegram-webhook/` and canary status currently route through `18080` | Customer channel and owner operations | Domestic core plus separately gated edge/token location | Independent of PR99 B/C and apex static files; migrate webhook/token only after destination and identity acceptance | Provider-neutral conversation/customer ledger; token remains protected | webhook secret, dedup, destination binding, outbound idempotency, real canary under customer-channel gate | Preserve current edge until replacement passes; no customer send in this task. |
| WeCom | Tokyo Nginx `wecom` routes to `127.0.0.1:18770/18780/18781` | Novel, customer service, customer contact callbacks | Domestic/customer operations only after separate callback migration | WeCom DNS and callbacks stay unchanged during apex move; migrate each service independently | Each existing callback/service data store remains authoritative until separately switched | signature, allowlist, replay/dedup, callback identity, data route, real canary and rollback | Do not change `wecom` DNS with apex. Tokyo cannot retire while any callback remains. |
| Novel tunnel | Tokyo `korea-novel-model-rpc-tunnel.service`, local `127.0.0.1:18761`; WeCom `/novel/` depends on it | Novel channel only | Protected Novel architecture; outside both migration packages | Preserve throughout PR99/PR122; decide separately after Novel acceptance | Existing Novel/PostgreSQL/Redis authorities unchanged | tunnel health, exact consumer, data stores, rollback and independent business acceptance | Never stop as collateral action. Blocks Tokyo retirement while consumed. |
| Apex Nginx | Tokyo `/etc/nginx/nginx.conf`, root `/var/www/wenwenwenyiyiyi.work`; Domestic currently only `winctl`/IP configs | Public site plus current apex dynamic routes | Domestic root-owned `/var/www/wenwenwenyiyiyi.work`; exact new apex server only | PR122 offline bundle → root staging → TLS/Host validation → independent review → DNS gate | Static files are immutable release content; dynamic authorities stay separate | syntax, 109 routes/assets, negative routes, Host/SNI, winctl before/after, dynamic-route responsibility | Roll back exact apex config/current pointer/DNS only. Never overwrite winctl or expose `/home/openclaw_ops`. |
| Certificate renewal | Tokyo `secure-secrets-certbot-renew.timer`; Domestic `certbot-openclaw-ip-renew.timer` covers existing IP cert, not apex | Existing Tokyo domains; Domestic IP/winctl; future apex | New exact apex cert lineage and isolated renewal unit on Domestic | Prepare offline now; issue only after ACME routing gate; install HTTPS only after SAN/chain proof | Certificate private keys remain host-local protected assets | initial issuance, SAN/chain, renewal dry-run, deploy hook `nginx -t` then reload, winctl unaffected | Keep Tokyo cert/renewal until DNS rollback window closes and all remaining Tokyo domains move. |
| Runners | Tokyo `xuanjun-tokyo-readonly`; Domestic `xuanjun-domestic-ops`; UK runner reported inactive/dead; PR99 production Runner custody still external | Evidence collection and controlled delivery | Role-scoped runners only; no cross-project generic root runner | Read-only/offline work can proceed independently; production actions wait for exact repo/job/identity scopes | GitHub/host receipts are evidence, not business data authority | runner identity, labels, repo scope, command boundary, root Gate and immutable artifact hash | Do not start UK runner or reuse P2. Tokyo Runner retires only after all evidence/rollback duties move. |
| UK release channel | UK `iZd7oeikknn1z21sq6ji6zZ/admin`, sudo-n reported; Nginx and Runner inactive/dead; P2 configs exist but remain stopped | PR122 development/audit and future controlled publish | UK control plane, once exact non-P2 channel is accepted | Offline docs do not wait; production publish waits for exact approved route | No website or trading data authority assigned to UK | host identity, repo/job, artifact custody, least privilege, receipt and rollback capability | No P2 start/recovery. Missing active channel keeps release HOLD but does not block offline preparation. |
| Yibi | Existing external trading/automation path | Current business operations | Exit only after independent Korea Binance production acceptance and Owner sequence | Last after PR99 production acceptance; unrelated to PR122 | Existing authority remains until approved cutover | real Binance acceptance, reconciliation and owner gate | A failed retirement must not trigger automatic restart; no action now. |
| PostgreSQL / Redis / MoreLogin | Existing protected services and stores | Novel/automation and other existing consumers | Unchanged/UNKNOWN until separate task | Not part of PR99 minimal runtime or PR122 static site | Existing authorities preserved | explicit consumer map and separate acceptance before any move | Must not stop, restart, copy or reconfigure as collateral work. |

## Execution order protections

1. PR99 B/C and PR122 D1 can prepare and be independently reviewed in parallel.
2. PR99 Phase D cannot pause timers or switch `trading.db` until its Writer,
   Authority, Finance route and rollback gates pass; PR122 has no authority over
   those resources.
3. PR122 can stage static files without touching `18080`, CRM/CommonBrain,
   Telegram, WeCom or Novel. Apex cutover remains blocked until every required
   apex dynamic route is either accepted at a new destination or deliberately
   removed by a separate approval.
4. Any shared service stop, credential revocation, database authority switch,
   network change or DNS change requires a pre-check proving the other migration
   line is unaffected and an exact rollback receipt.
5. PR99 PASS does not authorize Tokyo retirement. PR122 PASS does not complete
   Binance migration. Tokyo retirement is a later standalone Gate after both
   lines and all shared rows above are closed.


## 2026-10-15 21:50 Asia/Shanghai manual handoff: portal source evidence

This supplements the existing split scope; it does not authorize a service,
database, key, DNS or TLS change. OpenClaw remains stopped.

- Domestic isolated static recovery and read-only host probes passed as
  Owner-terminal evidence in PR122 comments6193348374/6193367992. Production
  cutover is still HOLD.
- Tokyo observed entry `scripts/secure_secrets_portal_server.py` SHA256
  `528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006`.
- Owner supplied source-only archive `PR122_PORTAL_SOURCE_REVIEW.tar.gz`,
  SHA256 `10b9c11fb8a6e07d9edab449faf9c72f6bb36e65ced79d7d65fbf1b69c28bd23`:
  77 regular Python files,1137922 uncompressed bytes; archive paths/types
  checked, entry identity matched. Source inspected statically; not imported,
  executed or deployed.

### Confirmed dependencies and safe reuse boundary

1. `build_service` unconditionally constructs `CredentialRepository` and
   its status bridge. CredentialStore/intake setup additionally depends on
   the protected master key. Existing database.connection defaults to
   trading.db unless explicitly configured; source inspection does not prove
   the live DATABASE_URL or authorize a new DB authority.
2. `--state-root` relocates form-session roots but OAuth state/token stores,
   status/disconnect and icon still reference global DEFAULT_STATE_ROOT.
   OperationsSecretRefStore and Telegram runtime/Bridge paths are separate
   hardwired roots. Merely changing the CLI flag is not a complete migration.
3. OAuth helpers and operations SecretRef/file-session components can be
   reused in an isolated successor, but the existing portal's trading imports
   and ordinary credential-intake initialization must not be copied as a
   Domestic deployment. Source names/SecretRefs are not permission to copy
   actual values.
4. TelegramCanary's default bridge reads a cert-pin file and connects to
   loopback19443. It also maintains webhook secrets/path and dedup state.
   Starting a copied process without its accepted bridge and state would not
   preserve the existing channel. No webhook reset or customer send is allowed
   as a migration shortcut.
5. The acquisition script's AST import traversal missed lazy `_EXPORTS`
   mappings loaded by package __getattr__. Directly identified missing files:
   database/repositories/{anomaly_repository,audit_repository,
   credential_repository,customer_repository,referral_partner_repository,
   trading_execution_repository}.py and
   database/models/trading_integration_snapshots.py. This is an intake
   limitation, not evidence the live deployment lacks these files; further
   transitive/dynamic imports remain unverified. Collect the source-only
   database package submodules in one supplement, never database/data or
   runtime files. Do not label the77-file archive a complete executable closure.

### Next bounded work and acceptance

- Complete source intake, map endpoint-to-store-to-caller, and reuse existing
  Domestic portability and provider-neutral bridge assets. Review required
  target runtime paths/identities without disclosing credentials.
- Prepare a minimal separated website/OAuth successor (if this remains the
  approved migration route), explicit disabled/rejected trading credential
  paths, preserved URL/Origin/CSRF/session/state semantics, and fake-transport
  tests with production writes unavailable. No new platform/rewrite is implied.
- Existing Owner management/finance credential routes require their own
  accepted protected destination; they cannot silently return success or be
  removed during static cutover. Telegram/WeCom/Novel follow existing separate
  rows. No whole trading.db/master-key/credential directory transfer.
- Before new host execution, bind complete source/package and configuration,
  independently review changed scope, prove loopback identity/health and exact
  route/tenant/permission/state restoration. Static tests are not OAuth/
  Telegram live-channel acceptance.
- TLS/ACME/Nginx candidate preparation may proceed independently, but apex
  DNS/cutover waits for every required dynamic route's accepted successor or
  explicitly approved removal. Any interim proxy plan is only a separate
  candidate until upstream TLS/SNI, existing access restrictions, secret-safe
  logs, failed/UNKNOWN behavior, rollback and Owner scope are reviewed.
- Tokyo retirement remains a standalone gate across both PR99 and PR122 and
  all remaining domains/callers, not a result of domestic static-site PASS.


## 2026-10-15 23:35 Asia/Shanghai: OAuth source/artifact gate closed; host gates remain open

This entry supersedes only the OAuth candidate development/review TODO above.
It does not advance production or alter any PR99/shared-resource authority.

| Gate | Exact evidence | State |
|---|---|---|
| R1–R3 OAuth source correction | Independent review PR122#6195784574; exact commit d584cd60b31bf09ee45f27a73ad227bcd0e1110f | PASS_WITH_SCOPE_LIMITS |
| Original artifact bytes and bindings | Independent review PR122#6195906963; Artifact11985605874; 15 binding files +7 modules,16 regular TAR entries | PASS |
| Accurate feature-commit CI | Push38759580678/job116506986251 checks out d584cd60...;45/45 | PASS_CANDIDATE_ONLY |
| PR integration preview | PR38759587631/job116507008501; merge preview79d235c includes d584cd60... | PASS_PREVIEW_ONLY |
| Merged main / live provider / Domestic corrected host acceptance | No corresponding execution receipt | NOT_RUN |
| Production, DNS/TLS cutover, Tokyo retirement | Separate gates below and shared rows remain unresolved | HOLD |

Frozen functional tree:1c36452d4756f8b017f33644922ea05a5b4f0adb.
Original ZIP SHA256:e0e55cbb30c9816c71f1ecc8317574845f98e69b676903aa0d78b3a134718fa4.
Inner review TAR SHA256:aeff6534cdafb1986d788444dc52be56bba49b1b41b8a7c6773d6b40187e9041.
These approvals bind that exact candidate and artifact, not subsequent shared
branch HEADs. Existing static RG1 source, releases and receipts remain unchanged.
Do not rebuild, repackage or rerun45 tests merely to acknowledge this gate.

### One next integration scope, with explicit stop conditions

1. **Protected state compatibility/custody — NOT_IMPLEMENTED/NOT_RUN.**
   The reviewed seven-module candidate uses a new private SQLite store and
   rejects legacy plaintext session/secret directories. It is not a drop-in
   installer for Tokyo18080. Before host activation, prepare one reviewed,
   account/provider-bound custody and reconciliation path for required
   credentials, sessions, OAuth lifecycle and verified account bindings.
   Do not put real secrets in GitHub/chat/artifacts or copy trading.db/master
   keys. If continuity cannot be established, keep the old protected authority
   and route, rather than silently making sessions/account state disappear.
2. **Required route successors — INCOMPLETE.**
   Cover every existing required apex route: public aliases/static files,
   mixed /p and /submit capabilities, OAuth status/callback/start/disconnect,
   health and Telegram edge/status. The current OAuth candidate explicitly
   returns503 for non-OAuth and disconnect capabilities. No accepted removal
   or interim proxy has been granted. Keep all affected old callers served;
   unresolved routes block apex cutover.
3. **Bounded isolated host acceptance — NOT_RUN.**
   Only after configuration, state custody and exact execution scope are
   reviewed may a fresh private candidate runtime use a nonproduction
   loopback port. Verify user/path/mode, state restoration, identity/Origin,
   restart/rollback and negative routes; prove provider-timeout/write-lock
   contention and parallel capacity noted in source audit. No live provider
   call or customer send is included without its separate scope.
4. **TLS/ingress and final release — HOLD.**
   Keep winctl and all existing domains/certificates unchanged. Accepted
   dynamic destinations, exact Nginx Host/SNI/109-route responsibility,
   host-local apex certificate/renewal proof, immutable release/rollback
   binding and final independent release receipt precede any DNS change.
   This ledger is a planning/status record, not execution authorization.
5. **Tokyo retirement — separate HOLD.**
   Resolve every shared resource row, PR99 authority and all Telegram/WeCom/
   Novel/model dependencies before any Tokyo service stop or decommission.

Current execution boundary: no server operation is authorized by the above
audit receipts. No Domestic workflow/runner, service, bridge, tunnel,19443/18443,
root permission, DNS/TLS, PR99/P2 or OpenClaw operation was performed in this
acknowledgement. OpenClaw remains stopped. No whole-server migration completion
is claimed. The next missing deliverable is the consolidated custody + route +
isolated runtime acceptance implementation/configuration, not more R1–R3 review.


## 2026-10-16 主域切换独审完成：覆盖上表的历史网站入口状态

依据独审PR122#6206608746和Run38839813239，apex实际DNS及HTTPS入口已在国内47.101.152.210，两地首页/health200、HTTP308、Work首页及current保持。国内apex证书、专用续期timer/hook已按主计划§9.13完成相应范围。上表“Domestic只有winctl/IP”“apex等待切换”等历史描述不再代表当前状态；不得重复DNS或网站发布。正式IP审计收尾PENDING，完整后台迁移尚未完成。

| 剩余依赖 | 当前安全保留 | 下一交付（不执行迁移） | 当前阻塞 |
|---|---|---|---|
| 混合Portal18080 | 东京原服务继续；R4断开HTTP已正式禁用 | 逐端点继承/状态托管兼容与单一写入权计划 | 交易侧分离、旧会话/SecretRef与已审SQLite候选之间兼容尚未实现 |
| CRM/CommonBrain | 国内18443及原数据权威保留 | 精确既有runtime/身份/DB权威绑定；仅元数据，不导出业务数据 | 运行数据权威与业务canary尚未独立验收 |
| 模型桥与执行器 | 东京19443/国内18443链路保持 | 无害推理/受限RPC后继、证书pin及目标归属的既有材料续接 | 最终去东京执行器未获准；不修改隧道 |
| Telegram/WeCom | 原token/边缘/回调、去重、既有路由保留 | 各服务凭据托管、在途、唯一写入、受控canary和回滚绑定 | 尚未完成渠道专项验收；不发送客户消息或重设webhook |
| 交易/Finance | 东京数据库与四timer权威维持 | PR99原路径结果同步 | PR122无切换/停timer权限，不另开交易迁移队列 |
| 东京退役 | 保留主机和回滚资产 | 仅在S01—S11全部依赖关闭后准备最终退役审查 | 以上任一未完成即HOLD |

本记录是对已有依赖的收敛，不表示新增服务或重新开发已审OAuth。安全/日志服务元数据仅作为本次IP边界补证，不读取配置/原始日志/凭据/DB，不作为全部外围安全策略证明。


### 2026-10-16：PR99 R2复审关闭，转入原韩国Phase-B安装准备

已回读正式独审PR99#6206991380：准确632bbe6f204a2c9ef778d3c91e425593c079abb1、tree59a48168764e8465e62fd17a55504c29812365b3，R2_TERMINAL_FIX=PASS_WITH_SCOPE_LIMITS，R2同版本重入终态CLOSED，R6原结论继承，Hosted137/137继承。不再重复修复/测试/复审R2。此前本账本和主计划的R2待审表述仅为历史状态。

下一既定节点是原PR99 Korea Phase B自包含候选构建/Manifest绑定，再按精确批准进行独立root离线安装及check：专用身份/venv/release、disabled/inactive unit、IPAddressDeny=any、无Allow、绝不启动Shadow/交易。不把R2源码批准扩大为安装授权。已查原137项Run38670647659无Artifact，不能声称运行制品已交付。Phase C实时只读Shadow另需精确网络许可、只读账户授权、持续闭合WAL快照发布/独立验证及完整验收窗口，目前真实路径未安装；Finance共享DB及四timer权威保持。PR99 Draft/交易迁移HOLD，东京不停止。
