# 未完成任务跟进索引

更新：2026-10-11，Asia/Shanghai；模型现场验收源 PR #17 `2a44143d`；以下当前状态取代历史失败记录。
这是既有任务与验收证据的索引，不建立第二个执行队列，也不向旧 Coordinator
投递 CODEX_EXEC。生产状态仍为 PARTIAL；代码测试通过不等于上线。

## 当前处理与下一动作

| 范围 | 当前状态及证据 | 下一动作及依赖 |
| --- | --- | --- |
| 英国模型/飞书 | 5.6真实最小推理PASS：精确回复及openai/gpt-5.6-sol返回证据已核实；插件2026.9.9/Codex0.160.0；5.6唯一备用已配置、6.1仍为主 | 验收真实飞书回复及实际模型证据；有界切换、主模型恢复和开发Worker路径仍未完整验收；不重复安装或已成功canary |
| 唯一执行者 | 13:38审计见3个Codex进程；不能据此判断原Work仍在写入 | 核对执行归属/活动与租约，取得唯一生产派发者证据后切换 |
| 英国隔离 | Docker/containerd active；项目隔离未验证；服务CPU/内存上限infinity | 只读盘点容器、网络、卷、身份和SecretRef；按项目环境增量隔离及资源限制 |
| CI失败暂停 | 本次候选补齐脱敏失败指纹、同指纹再失败暂停、重复SHA不刷新修复、断点保留3次预算 | 完整CI及冻结提交独立审查；跨子任务共享预算、全生命周期资源预算仍待补齐 |
| 看板字段/人工待办 | 本次候选补齐sha/qa_commit/reason、全部WAITING_HUMAN独立查询、目标模型与观测UNKNOWN分离 | 完整CI及审查；现有服务不重复安装，按已核实版本增量发布 |
| 派发器/数据库 | 现场仍是旧Coordinator；新执行侧表未激活 | 独占执行/隔离/审查通过后，数据库一致性备份与恢复验证，再受控迁移及切换 |
| Owner APPROVE/REJECT | 候选代码及CI已有；真实回复路由及防重放未验收 | 验证现有回调适配、防重放和客户正常处理；不得提前切正式Webhook |
| 连续真实开发/恢复 | 两个真实任务、独立QA、安全审计、发布证据及checkpoint续跑未验收 | 模型及新派发器就绪后贯穿两个任务；中断恢复与下一节点自动推进 |
| HTTPS实时看板 | 既有loopback页面及鉴权接口200；公网TLS未验证 | 核查现有TLS入口与域名，增量路由；外部鉴权/心跳/失败/人工队列验收 |
| 东京开发迁英国 | 已通过既有入口读取东京两个文件指纹；不等于全量资产盘点 | 完整开发资产与未提交工作盘点、备份、目标版本验证与恢复 |
| 东京生产迁韩国 | 韩国身份/访问/容量/现有小说负载未现场核实；无迁移验收证据 | 目标只读盘点、独立隔离、生产备份恢复、shadow预验收、单交易执行者受控切换 |
| 国内运营/Telegram | 既有英国至国内隧道active；完整切换链未验收 | 依赖盘点与转发/客户/账务验收；保留回退，无实盘权限扩充 |
| 四层门禁 | CI已执行；任务准入、独立QA/安全审计和ReleaseGate仍缺完整落实证据 | 受保护门禁分别验收，证据绑定同commit/制品；开发者不能自批发布 |

东京全量迁移最晚验收期限：2026-10-19 23:59（10月20日前）。
参见 TOKYO_MIGRATION_DEADLINE_20261020.md，不以到期迫使未验收切换。

## 人工节点集中处理

仅受影响路径登记 WAITING_HUMAN；下列是待落实到权威台账的索引，
不声称这些记录已写入生产数据库。

- UK_FEISHU_REPLY_ACCEPTANCE：英国5.6最小推理已PASS，原403不再作为当前阻塞。
  Owner已完成受控修复，不需重复安装、白名单修复或5.6 canary。下一人工入口为
  真实飞书发起验收消息；需要回复及实际模型证据，不能据此宣称闭环PASS。
- TARGET_ACCESS：现场核对韩国目标身份/入口及已有负载；不能把缺少访问证据
  当作缺少Owner授权，也不能宣称已连通。
- PLATFORM_CONFIRMATION：需要时集中处理交易API新出口IP白名单与平台确认；
  不自动扩充实盘权限，不提前切正式Telegram Webhook。

## 跟进及验收规则

独立代码任务并行，共享生产数据库、正式切换及同账户交易执行串行。
每项区分候选、CI通过、审查通过、部署及E2E验收；记录精确版本、证据、
失败原因、依赖和下一动作。当前没有无人值守生产开发已激活的证据。
每小时只读检查GitHub及已有英国审计；仅有实质进展、新失败或新增人工待办
才通知，不把定时检查写成持续修复或持续部署。

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
