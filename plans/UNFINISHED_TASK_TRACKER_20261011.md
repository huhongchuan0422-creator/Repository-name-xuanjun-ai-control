# 未完成任务跟进索引

更新：2026-10-11，Asia/Shanghai；核查基线 PR #17 `0c7919a1`；现场证据截至15:00。
这是既有任务与验收证据的索引，不建立第二个执行队列，也不向旧 Coordinator
投递 CODEX_EXEC。生产状态仍为 PARTIAL；代码测试通过不等于上线。

## 当前处理与下一动作

| 范围 | 当前状态及证据 | 下一动作及依赖 |
| --- | --- | --- |
| 英国模型/飞书 | Owner已备份并验证两模型精确allowlist；6.1主配置、fallbacks=[]；5.6新隔离请求403 Owner归属拒绝；OpenClaw2026.9.9/Codex0.158.0 | 对照实际插件版本及脱敏请求归属/准入证据定位403；未定位前不重复canary、不盲目重登；5.6、飞书、切换及主模型恢复均未验收 |
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

- UK_MODEL_REQUEST_OWNERSHIP：Owner已完成英国白名单备份修复及版本检查，
  不再要求重复该人工步骤。新的5.6请求失败于403请求Owner归属校验；需要
  现场实际插件版本及脱敏准入证据，不能据此要求重登或购买API。英国Runner
  固定入口仍为旧Sol-only诊断，不得复用它反复探测已知不支持的6.1路径。
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
