# 未完成任务跟进索引

更新：2026-10-11，Asia/Shanghai；模型现场验收源 PR #17 `2a44143d`；以下当前状态取代历史失败记录。
这是既有任务与验收证据的索引，不建立第二个执行队列，也不向旧 Coordinator
投递 CODEX_EXEC。生产状态仍为 PARTIAL；代码测试通过不等于上线。

## 最新英国开发政策与B准入（覆盖历史模型条目）

当前任务临时仅允许openai/gpt-5.6-sol、fallbacks=[]。V3为当前B契约，覆盖V2模型guard和原spec旧模型语义；保留原spec字节/hash。两新增测试允许按新语义修改生成新diff，不必原样提交a1fa旧diff。当前策略不授权生产配置变更、6.1探测或自动恢复。原预算/断点和所有负例保留。

## 当前处理与下一动作

| 范围 | 当前状态及证据 | 下一动作及依赖 |
| --- | --- | --- |
| 英国模型/飞书 | 英国5.6真实最小推理PASS，唯一备用已配置；Owner收到飞书精确验收回复，收发PASS；该飞书消息模型元数据未核实 | 关联该消息运行日志；验收有界切换/主模型恢复及隔离Worker路径，不重复已成功安装或canary |
| 唯一执行者 | 13:38审计见3个Codex进程；不能据此判断原Work仍在写入 | 核对执行归属/活动与租约，取得唯一生产派发者证据后切换 |
| 英国隔离 | Docker/containerd active；项目隔离未验证；服务CPU/内存上限infinity | 只读盘点容器、网络、卷、身份和SecretRef；按项目环境增量隔离及资源限制 |
| CI失败暂停 | 本次候选补齐脱敏失败指纹、同指纹再失败暂停、重复SHA不刷新修复、断点保留3次预算 | 完整CI及冻结提交独立审查；跨子任务共享预算、全生命周期资源预算仍待补齐 |
| 看板字段/人工待办 | 本次候选补齐sha/qa_commit/reason、全部WAITING_HUMAN独立查询、目标模型与观测UNKNOWN分离 | 完整CI及审查；现有服务不重复安装，按已核实版本增量发布 |
| 派发器/数据库 | 现场仍是旧Coordinator；新执行侧表未激活 | 独占执行/隔离/审查通过后，数据库一致性备份与恢复验证，再受控迁移及切换 |
| Owner APPROVE/REJECT | 候选代码及CI已有；真实回复路由及防重放未验收 | 验证现有回调适配、防重放和客户正常处理；不得提前切正式Webhook |
| 连续真实开发/恢复 | 两个真实任务、独立QA、安全审计、发布证据及checkpoint续跑未验收 | 模型及新派发器就绪后贯穿两个任务；中断恢复与下一节点自动推进 |
| HTTPS实时看板 | 既有loopback页面及鉴权接口200；公网TLS未验证 | 核查现有TLS入口与域名，增量路由；外部鉴权/心跳/失败/人工队列验收 |
| 东京开发迁英国 | 已通过既有入口读取东京两个文件指纹；不等于全量资产盘点 | 完整开发资产与未提交工作盘点、备份、目标版本验证与恢复 |
| 东京生产迁韩国 | 四服务器Runner身份/访问已核实；韩国2CPU/约2GiB，已见小说/yibi服务名；资源适配和迁移未验收 | 目标只读盘点、独立隔离、生产备份恢复、shadow预验收、单交易执行者受控切换 |
| 国内运营/Telegram | 既有英国至国内隧道active；完整切换链未验收 | 依赖盘点与转发/客户/账务验收；保留回退，无实盘权限扩充 |
| 四层门禁 | CI已执行；任务准入、独立QA/安全审计和ReleaseGate仍缺完整落实证据 | 受保护门禁分别验收，证据绑定同commit/制品；开发者不能自批发布 |

东京全量迁移最晚验收期限：2026-10-19 23:59（10月20日前）。
参见 TOKYO_MIGRATION_DEADLINE_20261020.md，不以到期迫使未验收切换。

## 人工节点集中处理

仅受影响路径登记 WAITING_HUMAN；下列是待落实到权威台账的索引，
不声称这些记录已写入生产数据库。

- UK_WORKER_ACTIVATION：Owner已完成英国模型修复和飞书收发验收，不再要求重复。
  新App Server Worker候选已通过本地测试；隔离身份的现有ChatGPT认证、原生协议
  现场返回证据及每任务OS/cgroup边界仍须核实。该依赖不能阻塞独立盘点/确定性代码任务。
- KOREA_CAPACITY_AND_CONTROLLED_BOOTSTRAP：韩国Runner访问已核实，取消旧TARGET_ACCESS阻塞。
  2CPU/约2GiB目标仍需实际内存/CPU预算和受控部署入口；不得自动采购或停止已有项目。
- DOMESTIC_PROTECTED_INVENTORY：国内Runner不能读取/home/openclaw_ops；完整运营依赖需受控脱敏导出，不能放宽整个HOME权限。
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

## Feishu receipt and worker/control-gate increment — 2026-10-11

Owner posted the actual Feishu reply to the requested marker:
XJ_FEISHU_56_OK. Owner-observed channel receipt is PASS; the pasted reply has
no provider/model metadata, so the model used for this Feishu turn remains
NOT_VERIFIED. This does not establish bounded failover or 6.1 recovery.

Candidate code adds CodexAppServerWorker using the official stdio protocol:
initialize, account/read (existing managed ChatGPT only), thread/start with
native resolved model/provider, correlated turn/start and turn/completed.
It rejects API-key/unknown auth before starting a thread, mismatched/absent
native model evidence, model reroute, cross-thread/turn events, unapproved
server requests, delegation/MCP/dynamic tools, duplicate message identities,
lease loss, timeout and output overflow. It does not copy credentials, log in,
send channel messages, retry a possibly mutating task or deploy.
HOME and CODEX_HOME must be canonical and disjoint from the worktree; tool
read access is restricted and workspace tool networking disabled. External
per-job OS/cgroup containment and dedicated authentication remain separate
activation requirements; these must be verified before real code dispatch.

Ordinary CLI-backend tasks now cannot modify their own worker/dispatcher,
ledger, approval routing, AGENTS/config enforcement, workflow or installer/
systemd control paths. Both pre-commit index and full pre-push history are
checked. Reviewed base code remains readable; trusted maintenance remains
separate from generated code acceptance. Independent security/release review
is still required; this path check is not a complete four-layer acceptance.

Local regression: 204 tests PASS, including real OS-pipe protocol fixtures.
Fixtures are explicitly simulated and do not attest a UK Worker inference.
UK integration/CI for this increment must be checked separately.
An additive push trigger invokes the existing four-server read-only inventory
when its workflow changes on this feature branch; production writes are not
part of that inventory. Runner access, capacity and migration results remain
unverified until actual job evidence is collected.

Next: verify this candidate on the UK Runner, resolve isolated Worker auth and
containment, obtain controlled dispatcher activation and independent review,
then accept two real development tasks with exact-commit CI/QA/checkpoint
continuation. Do not submit CODEX_EXEC to the old Coordinator.
Official protocol reference: https://learn.chatgpt.com/docs/app-server.

## 统一派发职责及当前节点顺序 — 2026-10-11

Owner明确授权ChatGPT Work统一分发架构任务；英国OpenClaw通过已验收的
ChatGPT管理认证/Codex额度路径执行。无须Owner逐项在飞书下任务，也不要求
Owner为当前英国聊天Agent另连GitHub。候选来源是PR #17实时head_sha，不能
用旧缓存f837b29f或merge_commit_sha作为最新候选HEAD。Canonical已同步职责。
现有GitHub控制仓库是临时任务来源，既有数据库是运行权威；下表是原节点
的执行索引，不建立第二个队列。生产仍是旧派发器，以下均不伪称已派给Worker。

| 顺序/原节点 | Work负责的具体交付 | 英国执行与准入依赖 | 当前执行证据 |
| --- | --- | --- | --- |
| 并行：Stage 0、Stage 1 1.1–1.7 | 四服务器资产/容量/现有服务边界；英国隔离与既有认证复用 | 固定只读Runner；生产变更另经发布门禁 | Run 38124100959四主机实际成功，完整资产及隔离未验收 |
| 首要：Stage 1 1.8–1.9、1.11、1.13 | 最新HEAD准入、唯一派发者、lease/fencing、失败指纹/预算、新dispatcher受控激活 | 完整DB备份恢复、每任务隔离、冻结版本独立审查 | 新Worker/控制路径保护代码及UK 204项测试通过；新dispatcher未激活 |
| 同时：Stage 1 1.10、1.12 | HTTPS看板、全人工队列、APPROVE/REJECT及防重放 | 既有鉴权/TLS/回调复用；正式Webhook不得提前切 | 既有loopback200；新版本、公网TLS和真实批准拒绝未验收 |
| 随后：Stage 1 1.14–1.15 | 两个有界真实开发任务，各贯穿CI、独立QA/安全审计、发布准入；实际重启续跑 | 仅在上项准入通过后向既有ledger登记spec并取lease | 未开始真实Worker任务，不把代码/测试任务记成它的开发 |
| 并行迁移通道 | 东京全量盘点/一致性备份/恢复；英国开发、韩国生产与Telegram、国内运营依赖 | 10月19日23:59前验收；韩国容量/隔离、唯一交易执行者、必要白名单 | 四服务器访问已核实；复制/恢复/shadow/切换均未验收 |
| Stage 2以后原顺序 | 社区分账小程序及新商家积分规则，再公益视频；后续金融/GEO沿既定顺序 | Stage 1闭环门禁及该业务既有节点条件 | 新需求已登记；不越过阶段启动资金操作 |

Work负责形成有范围、依赖、预算、验收与冻结代码来源的任务spec；英国Worker
负责开发/测试分支，不能自增任务范围或自批发布。开发、独立QA、安全审计和
发布各自绑定同一commit/制品，禁止把一个模型verdict当作四层全部PASS。
真实派发回执须包含task_id、spec_hash、worker_id、fence、开始时间和checkpoint；
缺少这些证据则为NOT_DISPATCHED/NOT_VERIFIED，不称“后台持续开发”。

## 已执行增量及恢复边界

7ee62840ef0f18e863cfd6b0b67f4d3cd320f4fa的7条工作流均成功；英国Runner实际
204项测试通过，临时stage完成，PRODUCTION_DEPLOYMENT=NOT_EXECUTED。
完整新Worker模型路径仍待真实开发验收；Feishu成功回复不等于已执行开发spec。

新增CI_WAIT过期租约恢复候选：只有完整保存的spec/hash、任务确定性branch、
冻结40位SHA、有效PR编号和0–3补丁预算相符，才允许重新排队继续检查既有CI；
旧fence失效、预算保留、模型/提交/PR创建不重放。模型执行或PR副作用不明的
阶段仍WAITING_HUMAN。两个新增真实SQLite重启/反例测试加入后，本地206项
通过；本次候选的英国Runner/CI结果须另核，不把模拟测试当生产续跑PASS。


## 最新执行核对：2026-10-11 16:34

153a82f9的7条CI均成功；英国run 38125077152/job 114427643391实际206项测试
通过并stage，部署未执行。四主机run 38125077144完成：英国仍旧Coordinator、
无execution_specs/worker_heartbeats，新派发没有启动；英国四个控制服务资源
上限仍infinity、nginx not-found且观测监听无443；韩国小说/yibi-api/scheduler
active且无限CPU/内存，Docker/containerd单位not-found。以上已记录实测，
不把旧“服务名可能active”当当前结果。国内bridge已有明确256MiB/CPU上限。

新增待核实：旧固定模型摘要报primary=OTHER_OR_UNKNOWN、fallback_count=0，
其只识别6.1主模型，不能判定实际是5.6或非法模型；当前实际两模型策略需
受控核对。此前5.6最小推理和Owner飞书回执仍分别有效，不能据此假定当前
配置、连续开发或自动恢复已验收。无需重复成功安装或canary。

下一控制源桥接使用现有Runner私有仓库checkout，在每个精确SHA的临时stage
提供canonical与上述plans。Work统一批准spec；UK读取受保护控制源并按已
批准的既有任务准入、取lease和执行；不靠Owner逐项向飞书发送任务。
目前仍NOT_DISPATCHED，新派发器/隔离/独立审查为实际启动依赖。
社区新规则及付款后播报官方调研见COMMUNITY_POINTS_REQUIREMENTS_20261011.md；
该项目原映射为Stage 5，需求记录不代表业务开发或语音设备E2E已开始。

## Work向英国OpenClaw/Codex开发分工 — 2026-10-11

Owner再次授权将开发交给英国OpenClaw、使用已有Codex额度；Work继续负责
架构、任务准入、独立验收和发布决策。本段为既有节点的有界开发任务说明，
不是新任务系统、生产ledger记录、Worker接收回执或运行证明。
历史任务登记状态：WORK_APPROVED_SCOPE_PENDING_EXECUTOR_RECEIPT / NOT_DISPATCHED；
最新Owner转交的实际启动和候选回执见下节，尚非生产ledger/lease独立验证。
启动入口尚未交付；不能向旧Coordinator投递CODEX_EXEC来绕开这个缺口。

| 批次/既有节点 | 英国OpenClaw开发交付 | 完成证据和依赖 |
| --- | --- | --- |
| A：Stage 1 1.8–1.9、1.11、1.13，最高优先级 | 为现有DevelopmentLoop、ExecutionLedger、DevelopmentPipeline、CodexAppServerWorker补可执行服务入口及配置校验；绑定控制仓库最新HEAD、可信spec准入和GitHub写入并发保护；准备有回滚的英国安装/切换命令；实现唯一派发者和每任务资源隔离 | 真实子进程集成验证、入口启动/退出/故障和双派发者负例；数据库一致性备份及恢复校验必须先于生产迁移；隔离须证明Worker不能访问生产DB/交易密钥；冻结commit独立QA、安全审计后再发布。开发阶段只写隔离worktree，不执行生产切换 |
| B：Stage 1 1.10、1.12，可与A并行开发 | 复用现有Owner看板及回调，补部署入口、鉴权HTTPS代理配置和全量人工队列；接通既有APPROVE/REJECT、防重放及任务fence | 同commit测试/制品、鉴权和拒绝重放负例；上线后外部HTTPS实际进度/心跳/人工队列验收；真实Owner审批/拒绝另行记录。不提前切正式Telegram Webhook |
| C：Stage 1 1.14–1.15，依赖A的生产准入，相关发布验收依赖B | 从既有权威台账登记两个Work批准的真实开发任务，逐个贯穿开发、CI、独立QA、安全审计和发布准入；在明确checkpoint实际重启并自动继续 | 每任务task_id/spec_hash/worker_id/fence/开始时间/实际模型、冻结SHA、PR、CI和独立审查制品可对应；第二任务无需Owner逐项催促；恢复保留补丁预算，禁止重放模型/提交/PR副作用；代码DONE和生产E2E分开 |

执行合同：候选基线为本段提交的父HEAD f07c808938b308ee294d82646aa167942a975036；
接收时必须核对PR #17实时head_sha及本段来源commit，陈旧基线不得写入。
A、B为控制平面维护开发，仅限上述目标文件及必要测试/安装配置，需专门可信
维护准入和独立审查；不得放宽普通CODEX_EXEC的控制路径保护或自批发布。
各任务单次模型执行最多20分钟、补丁最多3轮；重复失败按现有指纹规则暂停；
并行仅限独立worktree和已验证资源容量。超时/未知副作用保留checkpoint和原因，
进入WAITING_HUMAN；其他独立任务继续。预算调整只能由Work重新准入。

只允许openai/gpt-6.1-sol主、openai/gpt-5.6-sol唯一备用；复用已有ChatGPT管理
认证及Codex额度。已知6.1账户路径拒绝时有界选择已验证5.6，禁止其他模型、
Astra、未经授权付费API；6.1真实最小探测恢复后仅在任务边界切回。
不能因飞书聊天成功推定新Worker的独立认证/隔离已通过，不能复制OAuth到Git。

本次Runner交付只暂存以上说明并测试候选源码；工作流不会调用模型、写生产DB、
部署、迁移或发飞书/Telegram消息。只有受控入口返回真实lease/启动回执，
才把状态改为RUNNING。缺少入口的阻塞必须明确报告，不能称后台持续开发。

## 交接调整及多Agent启动回执 — 2026-10-11 17:27

Owner转交：英国OpenClaw已从Runner checkout核对85ad1d72，A/B独立开发目录
已启动。现场16:33记录OpenClaw PrivateTmp=yes，与Runner的/tmp视图不同；
撤销/tmp作为聊天Agent输入的要求，不关闭隔离、不要求Owner重连GitHub。
使用已核验checkout，复制源码至独立工作目录；控制源SHA与开发基线分别记录。
Work是GitHub集成/发布的唯一写入协调者；A/B可返回补丁，不必自行获取令牌。

- main：协调/快速响应；A=/root/lane_a，入口/隔离/SQLite备份恢复开发中。
- B=/root/lane_b：Owner报告冻结commit c49238abb9fa8a7fc90206d9d8308ac446f0988c，
  patch SHA256 ab58ff792f18b2c8daff53699ab43dd3241a5ae53575c98aaa399cdb1231236b；
  开发者报告213 tests/nginx渲染PASS，未推送、未部署，尚不采信为独立验收。
- /root/independent_qa：独立qa-b重建并验证候选等价性和负例，STARTED自报。
- /root/security_audit：权限/凭证/鉴权/fence/TLS/systemd/事务只读审计，STARTED自报。
- B退出运行槽，当前main+A+QA+安全审计；子Agent禁止递归招募。
  以上模型5.6继承是执行方报告，需会话/原生元数据另核；不代表生产派发已部署。
- C仍NOT_STARTED，等待A生产准入。没有新的生产数据库或旧Coordinator变更证据。

17:29 Owner追加执行方证据：A冻结85dd740d94f6c8d24979764dcbd40f3c48faabad，
patch SHA256 117fbab62fca0ed459e4c45c1b8174f9819b511fbef059ec327f1ab4fc458b03，
开发者报告211测试PASS、部署准入NO。B独立QA报告树等价、213全量和6额外负例
PASS、配置/systemd静态验证PASS；部署HOLD。QA继续A，安全审计继续A/B，另有
独立目录组合候选集成，未推送或部署。这些尚待回收实际补丁及QA/审计制品，
不能与Work自身新增交接测试的计数混为同一候选；组合commit需重新冻结并审查。

源码交接：Work批准范围→现有GitHub/Runner checkout→A/B独立目录。
结果交接：各工作目录根部保留唯一UTF-8 .patch/.diff→Runner只读回收→Work核对
补丁哈希/基线并在最新HEAD上集成→冻结合并候选CI→独立QA/安全审计→发布准入。
不得在Runner正在checkout的目录开发或长期存放唯一结果，避免清理覆盖。
现有scripts/uk-work-result-collect.py不执行补丁、模型或部署；只读取两个固定
目录根部、拒绝symlink/未知路径/超限/潜在密钥/多候选歧义。A/B补丁绑定上述
Owner给出的冻结哈希；目录不可见或无读取权限只返回明确状态，不放宽HOME权限。
基线上下文、真实模型、QA、安全及生产状态始终NOT_VERIFIED，直到独立证据齐全。

已启动A/B保留85ad1d72基线，不因Work更新交接说明丢弃开发成果；Work回收时
核对相对该基线的差异，再按最新HEAD并发保护集成。冲突由Work处理，不强推。
独立QA和安全审计须针对最后实际拟发布的冻结commit重新确认，不能把仅针对B
本地候选的结论直接推广到A+B合并结果。正式切换仍须备份恢复、资源边界和
唯一执行者现场证据；Owner人工节点集中登记，不能以聊天回执代替运行权威台账。


## A+B第二版冻结与回收边界 — 2026-10-11 17:43 Asia/Shanghai

Owner转交的首次组合候选09325583b59ed29e177682d4adccba7975730f0a独立QA /
安全复验FAIL/HOLD，已撤销发布候选资格并退回修复；227项为开发自测，不能
覆盖复验失败。失败包括缺codex_worker运行依赖、helper不可执行/组可写、
workdir进入ledger子树、systemd239参数不兼容、sudo解释器PATH提权、停止
/inactive未闭环、身份/路径过宽、非root-owned immutable安装、manifest无
外部摘要锚/TOCTOU、callback/dispatcher DB不一致及epoch/恢复激活未程序化。
原A/B单独候选也不具发布资格，不回收它们作为安装源。

第二版执行方冻结报告（尚待Work回收实际内容）：
- SOURCE_COMMIT仍为85ad1d7224485f3c57298e71a429eb576b8d943d。
- 组合commit：93d5b04ed1ced8042e3982125a486e0bd1d43ec8。
- 源补丁：/home/xuanjun_dev/xuanjun-uk-dev-20261011/integration-ab.patch。
- patch SHA256：efe8607e8d54bf083ae8e696b953ee18aeb4c390ab7bc746cd2d1d09ddc2e1a6。
- Owner提供的manifest SHA256：244a848aa322310a85a2bd0248908c079130cfa494a9dd3c17416eca768a41eb。
- 229 tests、非root安装烟测、helper0755为执行方开发自测报告；未回收独立制品。
- 对同一第二版候选的独立QA和安全复审已重新STARTED（Owner转交），结果未出。
  发布/部署HOLD；C NOT_STARTED；无新的生产变更证据。

英国Runner在c001d176c3eb7108d68492a10bd356175d708f09的真实job114438142799
完成213项Work交接测试，但读取开发HOME为READ_ACCESS_NOT_VERIFIED，实际
补丁尚未回收。新增一次性scripts/uk-work-handoff-bootstrap.py只能由英国
Owner root在核对脚本摘要后执行：固定源文件、固定第二版哈希、256KiB上限、
无symlink/祖先替换，先核对补丁再建立root-owned数据回收目录：
/var/lib/xuanjun-work-handoff/returns/93d5b04ed1ced8042e3982125a486e0bd1d43ec8/。
目录root:githubrunner组0750、candidate.patch root:githubrunner组0640；只复制
数据，原文件和HOME权限不改，无通用sudo、服务重启、模型、数据库或部署。
同内容重跑不覆盖，不同内容拒绝；原子发布及文件/目录fsync。root初始化结果
尚NOT_VERIFIED，只影响结果回收，不阻止开发/独立复审在自己的工作目录继续。

Runner只读collector只接收这份精确外部哈希的组合文本补丁，拒绝潜在密钥、
symlink/git元数据/二进制/重命名/歧义路径；可接收脚本0755作为待审数据，
不执行、不应用、不安装、不准入任何路径。manifest摘要当前仅Owner报告，
不是已验证内容；Work必须重建SOURCE基线、核对补丁和manifest文件实际字节，
逐文件审查并在最新PR HEAD上并发保护集成。独立QA/安全复审必须绑定最终拟
发布commit和artifact，不能沿用旧失败版本或将Work交接测试计数当229项。

现场仍需验证：窄helper实际安装/权限及systemd239运行；无UID0 Worker和生产
路径读取；SQLite备份恢复含PRAGMA、fsync、WAL/SHM及失败回滚；旧Coordinator
inactive、epoch唯一派发与lease丢失实际停止；两真实任务CI/QA/安全/批准拒绝/
断点续跑；新看板外部HTTPS与真实心跳/全量人工队列。代码自测不替代这些门禁。

## 第三版覆盖第二版发布候选 — 2026-10-11 17:48 Asia/Shanghai

Owner转交第三版冻结，前两版均作废为发布候选（保留失败历史，不删除成果）：
- commit：4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2。
- patch SHA256：82e81c2bbca62ff28dddab409f66ee53106283a1ebb3a9271c5c89b38e11aac0。
- manifest SHA256：7a721baadf570decf6fae72747394e84fdac29fe1432fcef4f44a4bd85bf9eaf。
- 执行方开发自测232项PASS、安装/三个入口--help烟测PASS；报告修复同fd
  manifest/source校验竞态和dispatcher/worker受控worktree所有权交接。
- 独立QA/安全定向复验进行中，结果未出。平台级dispatcher epoch、canonical
  callback DB、restore activator、真实用户/二进制/root helper安装和unit inactive
  仍HOLD；C NOT_STARTED，生产PASS尚无证据。

Work回收入口只绑定上述第三版，不执行任何旧候选。根源补丁路径维持
/home/xuanjun_dev/xuanjun-uk-dev-20261011/integration-ab.patch（路径沿用Owner
上一版说明，当前字节待核）；root数据回收目录按第三版commit隔离：
/var/lib/xuanjun-work-handoff/returns/4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2/。
若源文件已变为另一版本，则哈希失败即停止，不选择最新文件或安装旧版本。
manifest摘要仍只Owner报告，回收补丁不等于该manifest文件/独立制品已验真。
第二版回收代码7434ea01de0d5143915c1ae6946af3c24e1f7ad2的英国job114441178840
实际成功；对应222项Work交接测试与第三版232项开发自测分开记录。

## 最终失败回执、产物已回收与新设计准入 — 2026-10-11 18:04 Asia/Shanghai

第三版4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2最终代码QA=FAIL，安全=FAIL
（Owner报告安全结论；完整安全报告未随包交付）。独立QA的232回归PASS不覆盖
额外负例4PASS/2FAIL；普通worktree首次进入与Worker新文件回交失败。Worker
可替换.git元数据并借Git clean filter在Dispatcher身份执行命令，为CRITICAL。
执行方本轮重复重试已按规则checkpoint并HOLD，不再称开发/独立复验运行中；
旧候选作为修复基线保留，不能安装；C NOT_STARTED，生产零变更为Owner回报。

Owner上传交付包，Work已独立核对压缩包/补丁/manifest摘要，取GitHub真实85ad
上游对象和91个文件blob重建源树，应用补丁得到fb8ee3bd3e2f175bcabc3eefe95aa182f3529b49，
与独立QA树完全一致；manifest的33个文件哈希通过。当前候选Git commit对象
未交付，4bf32c00身份由Owner/QA报告；准确验真范围是源tree、补丁和重建tree。
原root数据回收命令已由上传替代，Owner目前不需到英国执行命令。
产物和完整QA报告按数据保留在evidence/uk-candidate-4bf32c0/；没有把失败补丁
应用到PR运行代码。Work本地复跑232测试有1个环境错误：测试硬编码缺失的
/usr/libexec/platform-python3.6；不造假补二进制/改测试来报告PASS。两项独立
本地行为探针复现worktree拒绝和.git clean-filter执行；不是英国跨UID证明。

新的有界维护设计已由Work审查准入，见GIT_FREE_IMPORT_ACTIVATION_REPAIR_20261011.md
与WORK_APPROVED_AB_REPAIR_SPEC_20261011.json：A1采用无.git快照及无过滤纯数据
导入，替换整条shared worktree交接；A2采用持久epoch、统一activation descriptor
及restore activator，并解决NNP/sudo链冲突；B通过有限ledger socket批准/拒绝，
不维护另一任务DB。新预算单次模型<=20min、总补丁<=3轮，同指纹再现停止；
保留旧预算和断点，不自动重置旧任务。唯一模型6.1主/5.6备用，不启用其他模型/API。

Work任务源提交/Runner交付与英国执行方实际接收/启动分开登记：当前仅新设计
准入和控制源发布，EXECUTOR_RECEIPT=NOT_VERIFIED / NEW_REPAIR_STARTED=NOT_VERIFIED。
不以GitHub CI成功称英国Agent复工；新修复不能向旧Coordinator投递CODEX_EXEC。
独立QA/安全须针对新冻结组合候选复审；现场二进制/身份/broker/unit停止/epoch/
canonical DB/WAL恢复及HTTPS仍HOLD，修复阶段无生产切换授权。完整安全报告
缺失仅阻塞该证据项；可独立实现/审查的新设计继续，人工平台节点集中处理。


## 18:16 receipt update: A1/A2 running after manual activation

This supersedes the earlier NOT_VERIFIED start status for this bounded repair only. Exact receipt: evidence/uk-intake/OWNER_RELAYED_REPAIR_START_20261011.json.

- Source/spec remain 76c0cfe7f7a4dd9ed52a9dc719897c95c437ba8b / deb334171fdbc10d9ab8abff046493526ca5c992428d514629a86cf32859fc6a.
- UK main reports A1 and A2 STARTED, openai/gpt-5.6-sol OAuth/Codex, independent a1/a2 directories, no current development blocker. Evidence is Owner-relayed, not independently inspected process state.
- B waits for A2_CONTRACT_FREEZE; C still NOT_STARTED. Failed release candidate and failure budget/checkpoints are preserved. No duplicate task creation or redispatch is permitted.
- Automatic Runner→OpenClaw intake remains NOT_DEPLOYED / NOT_ACCEPTED. Work will develop the bounded intake increment separately from A1/A2 files: detect approved source, validate spec digest, wake main coordinator only, and record durable idempotent receipt/start. Import the current manual receipt first. A changed documentation SHA with identical task/spec must never restart it.
- Production admission remains HOLD; no DB, old Coordinator, trading permission or formal Webhook mutation was reported. No new Owner server command is requested at this code-development stage.


## Work intake candidate: code review PASS, automatic activation still HOLD

Work implemented scripts/uk-work-intake.py outside A1/A2's exclusive files. It publishes approved maintenance source as bounded data, checks raw Git object provenance, checks spec/digest/permissions/model/budget, wakes only main under the existing non-root OAuth identity, and records durable sanitized receipts. Publication binding is control SHA+spec digest; execution deduplication is parent task+spec digest, so documentation commits cannot restart current tasks. The active manual spec is imported as an already-started Owner-relayed receipt without inference.

Local full regression 242 PASS / intake 20 PASS; Python3.6 AST and local systemd template verification PASS. Independent Work code and security reviewers first returned FAIL; metadata spoofing, receipt secrets/false PASS, Git replace, auth-to-send freshness gap, late publisher overwrite, malformed JSON/output limit and FIFO blocking were fixed and negative-tested. Final reviews PASS for this intake candidate scope. Script SHA256 40d87f1deee7cd0a2183744ce385b80d278a34eeed136feb83683810a2b675e8. This does not qualify UK A1/A2's forthcoming artifact or production release.

Workflow calls only a separately installed root-owned, hash-matching module. With no installation it reports WAITING_REVIEWED_PLATFORM_INSTALL and NOT_EXECUTED; no model/Agent start is added to the ordinary source staging path. Platform gate: controlled installation integrated with the frozen A2 platform contract, actual publisher/consumer UID+group-read boundaries, systemd239 timer/reboot, fixed Gateway profile and OAuth route, automatic new-spec receipt and replay/crash tests. Details: plans/WORK_INTAKE_ACTIVATION_CONTRACT_20261011.md. No timer/root installation or production change has occurred. Current A1/A2 source/spec stay pinned to 76c0cfe7/deb33417; preserve checkpoints and budget; B/C dependencies unchanged.

## Event intake and interrupted-task follow-up — 2026-10-11 19:00 CST

Owner relayed UK verification that intake module/config/directories/timer are
not installed. Work adds a candidate systemd.path for atomic inbox publication
and changes the shared consumer timer to boot reconciliation plus 120 seconds
after inactivity. No GitHub polling token, public webhook, alternate task queue
or repeated A1/A2 assignment is added. Event delivery remains NOT_DEPLOYED.

Intake receipts do not monitor child tasks. Persistent progress/lease expiry,
actual cgroup stop, side-effect reconciliation and safe checkpoint recovery
belong to A2's canonical runtime and must be live-tested before unattended PASS.
Existing code can automatically recover verified CI_WAIT only; general expired
model/tool phases remain WAITING_HUMAN. An active Work chat and read-only hourly
tracking are not continuous execution. Display awaiting Work/paused/stale with
cause and next action, and keep independent ready tasks moving.

## Latest integration and power-recovery acceptance — 2026-10-11 19:29 CST

Owner现场回执：A1完成ae72ec7405540a59e63273a5711ed8f38e66b20e；A2本地冻结9df09fa；B从fb2cc90续修，2个未提交测试文件。248项为241通过/3失败/4错误（activation-store兼容、callback403、manifest同步），未达到全量PASS。独立QA/安全NOT_STARTED，未部署，生产无变更为Owner回报。新补丁/manifest和A2/B完整SHA未回收，不以Work入口242项CI替代这些失败。回执见evidence/uk-intake/OWNER_RELAYED_INTEGRATION_PROGRESS_20261011.json。

当前B已在修复，不重派A1/A2或B；完成合同冻结即可并行B，无需再串行等A1。保留未提交测试与旧断点/预算，callback保持非法请求拒绝，manifest绑定实际最终字节。通过后冻结同一组合制品，独立QA/安全并行复验；C仍等真实发布准入。

Owner要求把任务领取、触发、中断和重启完整落实，验收矩阵见plans/TASK_INTAKE_POWER_RECOVERY_ACCEPTANCE_20261011.md。复用GitHub批准源、A2唯一ledger、既有intake journal及窄broker；事件接件和执行监督分层，未知副作用不盲重跑。自动投递和新制品自动回传尚未现场验收；本契约不修改当前spec、不产生新任务或生产授权。

### 19:32 scope HOLD resolved by Work authorization; receipt still needed

Owner最新回报B实现fb2cc9081fa8d215bf186046b53bae9b9334ad7b，228非过期测试/compile/diff通过；248仍241/3失败/4错误，工作树不干净，正在等测试/bootstrap范围批准。Work已批准plans/WORK_APPROVED_B_SCOPE_EXTENSION_20261011.json，仅续接原B，允许三个明确旧测试模块及uk-dev-bootstrap契约对齐；不改DB-string兼容、不削弱鉴权/负例、不执行部署，不重置预算。扩展接收/复工回执NOT_VERIFIED。先修本地测试与清洁冻结，再同制品独立QA/安全；旧242项Work入口CI不能覆盖本次248项。

## 20:05 isolated checkout correction and bounded test extension V2

Owner已核验上次扩展89d22f并对齐4个文件；早前本地248全绿由两个未提交测试diff支撑，不能作为冻结验收。新冻结925cfba3171ebb43a872ef2a0ab7ffc390a5a516隔离复跑为245/248，1失败/2错误，独立QA/安全尚未开始、未部署。最小diff a1fa635117286a0ccdf4c83060d9e8042719c07401b3fa13226ca176cc168861仍仅Owner摘要回执，未取得实际字节。

Work批准WORK_APPROVED_B_SCOPE_EXTENSION_V2_20261011.json，仅新增test_development_service.py及test_owner_dashboard.py，原任务/断点/预算不变。broker v2测试不得删UID0/peer/epoch/fence/资源边界负例。模型测试须分开：单次已准入Worker可固定5.6零内部fallback；Owner全局仍6.1主/5.6唯一备用。把全局策略改为仅5.6零备用未批准；如实现误标全局字段，应在原B已授权dashboard源码范围修正，不能改断言掩盖。V2接收/续跑尚NOT_VERIFIED。隔离最终干净提交248全绿后，再同制品并行独立QA/安全审查。

### 20:41 CST：Work修正持续HOLD的契约冲突

Owner/executor反馈已超过10分钟，无真实任务进程；V2已领取、但旧6.1模型
guard阻止B。Work发布V3，采用Owner已确认的临时5.6-only/fallbacks=[]；
不需要Owner再授权。两获批测试与原B dashboard源范围均保留，NOT_VERIFIED
旧diff内容不是编辑禁止，允许语义修复及新hash。禁止负例削弱或测试跳过。

原任务/925cfba断点/tree5f02ee1/剩余预算不变；无重建任务、A1A2重启、
预算重置、生产权限扩充。冻结245/248仍是现行测试证据。
下一步V3接收与实际RESUMED回执→提交修复→clean checkout全量→同制品
独立QA/安全。发布指令不算启动；V3接收/续跑NOT_VERIFIED。

### 20:53 CST：7ed631a冻结完成，安全失败纠正优先

- V3已真实接收续跑；原B断点提交7ed631a.../treeaee5715...；clean248/248、QA PASS为执行者回执，报告字节尚未返回Work。
- PR6109228044明确纠正6109204309的安全PASS：HIGH1入口仍允许6.1（可复现）；HIGH2 broker代码/平台边界未完整验收。因此当前QA_PASS_SECURITY_FAIL_HOLD，不采用较晚到达的绿色汇总作为覆盖证据。
- Work扩围精确模型源码/相关测试，保持同任务/断点/原预算，单一集成writer；固定5.6默认与allowlist，显式6.1须在派发前拒绝。不改生产配置，不删负例，不重派A1A2。
- broker归Work的A2 PLATFORM/Release Gate。先提供实际源码路径与可执行入口/边界测试矩阵，区分缺实现与缺现场安装；缺实现不能通过平台HOLD掩盖。现场root/身份/binary/epoch/fence/停止和恢复仍需受控准入。
- 请求patch b26...、install manifest c157...、外部evidence manifest9b53...与QA/纠正security报告，区分不同摘要。现GitHub找不到7ed对象不否定本地工作，但Work未复现/收件不能判发布。
- 模型修复、制品回传、broker边界盘点可独立继续；新源码冻结后全量+同制品双审，C/生产/HTTPS未验收。不需要Owner再授权上述代码工作。
