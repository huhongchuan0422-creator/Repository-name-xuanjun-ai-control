# 东京→韩国迁移：已授权主机盘点接线

沿用PR17及plans/MIGRATION_SEQUENCE_V1.md；不是新任务队列。Work17原PR72保持不动，P2归Dots。
Owner于2026-10-14明确：易币退出资源保障范围，小说暂保留，币安生产迁韩国，现有容量先承接，不预先扩容。

## 2026-10-15 Owner 范围纠正（优先于旧迁移包中的扩大解释）

本次只迁移**东京币安生产项目及其不可分割的生产依赖**。OpenClaw 整体、
开发任务、测试/CI、临时 Agent/子进程、官网、客服/WeCom、模型服务、小说、
易币和历史制品不因位于 `/opt/trading-system` 或东京主机就自动进入韩国。
每个对象必须先分类为 `PRODUCTION_REQUIRED`、`CONDITIONAL_DEPENDENCY`、
`DEVELOPMENT_OR_TEMPORARY` 或 `HISTORICAL_ONLY`；只有前两类且有直接依赖证据
的对象才能进入迁移 artifact。

韩国沿用当前 2核2G 配置；不以东京开发期间 OpenClaw Gateway 的 4.11GB
占用推导扩容要求。容量由最小生产负载在韩国的安装后/Shadow 实测决定，
检查 OOM、重启、MemoryAvailable、swap 增量、CPU、延迟、磁盘和 FD；失败则
保持 HOLD，不自动转化为购买扩容要求。

顺序为：币安最小生产闭包部署与只读验收 → Shadow → 东京 Writer 硬围栏 →
最终一致快照 → 韩国单 Writer/Canary/独立验收 → 迁移验收 PASS → 易币精确
归档确认并永久停用 → 确认东京全部币安生产依赖已迁出后再退役东京。
小说只保留数据与现状，不为迁移启动或删除。易币在币安验收前不做项目级
停用；只有精确残留对象被证明冲突时，才提交对象、端口/资源、影响和单独
Release Gate。生产继续 `HOLD`，本修订不授权任何写操作。

正式审核 `6172954908` 已接受上述范围修订，但要求把它从文档优先级升级为
执行器硬约束。`canonical-migration-policy.json` 现为唯一可执行阶段/范围策略；
`restricted_executor.py` 只接受 schema 4 的独立签名策略，并同时绑定该文件的
原始 SHA-256、固定 policy ID、阶段 ID 和所有既往阶段回执摘要。旧
`c7-real-machine-execution-package.json` 与
`c7-owner-scope-execution-package.json` 只保留为历史/证据输入，任何一个直接
送入执行器都会被拒绝。`YIBI_RETIRE` 只存在于阶段 F，且必须携带 A—E 全部
前序回执摘要；错误范围、旧顺序、缺前序、错 hash 均在 runner 调用前失败。

`production_dependency_inventory.py` 对私有 95 条 Writer 映射逐项读取实际
源码字节、import、数据路径引用、凭据引用名称、写操作标记、当前进程和可读
systemd/cron 触发引用，并生成私有全路径清单与仓库内脱敏清单。2026-10-15
现场结果为 95/95 字节匹配，当前用户进程及可读触发视图均未观察到直接入口；
但 Root、Gateway 全局和 GitHub Runner 管理覆盖未闭合，因此 95/95 仍为
`UNKNOWN/DENY`，不得把零观察解释为不存在。

韩国阶段 B/C 的凭据范围已进一步锁定为仅
`SecretRef:BINANCE_ACCOUNT_READONLY`。共享 `TRADING_CREDENTIAL_MASTER_KEY`
可能解开同库中的交易凭据行，因此与 `BINANCE_TRADING` 一起在 Shadow 阶段
明确禁止；只有后续单 Writer 阶段在独立验收和新精确 Release Gate 后才能
提出专用交易 SecretRef，不能由 Shadow 包继承。

## 本变更实际行为
新工作流仅在本仓库Owner提交的指定迁移分支PR运行，在东京与韩国调用已由Owner安装的root-owned固定零参数盘点helper。没有checkout、不运行PR代码、不新增sudo权限。先核验主机、Runner用户、helper所有者和模式，记录实际安装文件SHA256；原控制仓库目前为公开仓库，只允许输出已授权的脱敏资源及服务状态，不能上传业务数据、配置正文或密钥。
migration-prep/inspect-helper.sh现已按Owner实际收到的安装命令逐字重建；本地SHA256=61bed97a32e970dd868f2d223c68ab41c012c484d314cb714c768629aac263c2，与两台首次Actions记录完全一致。新工作流在调用前强制pin该摘要，检查root-owned非软链父目录且group/other不可写；打印当前调用者sudo -l有效策略作为脱敏证据。没有更新任何主机helper或sudoers。

sudo -l列表不是所有sudoers来源、包含文件和env策略的完整审计；工作流明确FULL_SUDOERS_POLICY_AUDIT=NOT_VERIFIED。GitHub Connector不提供/actions/runners访问政策GET，浏览器未登录；GLOBAL_RUNNER_ACCESS_POLICY=NOT_VERIFIED。当前公开仓库Default Runner全局隔离尚未验证，保持生产操作HOLD。限定盘点成功不能被当作生产准入。
root盘点授权于2026-10-21T00:00:00Z失效。

## G1-G5候选增量

独立审核 `6166680343` 后，新增 `G1_G5_EXECUTABLE_CANDIDATE.md` 及配套
Python候选。所有模块默认拒绝，不执行主机命令或交易所写操作；共享生产
Runner工作流已在本分支禁用，仅Hosted测试可运行。生产仍为HOLD。

源码复审 `6167112786` 的五组问题已集中整改：G5 显式检查 Redis 等
全部隔离字段；G4 强制经 GET-only transport 采集并校验实时性、分页、
符号覆盖、本地差异和同一冻结窗口；G3 使用固定信任策略及 Ed25519
签名且在未集成生产 authority 前永不返回执行授权；G1/G2/G5 阶段历史
必须为连续、成功、摘要绑定的回执；幂等账本改为 SQLite 事务，deadline
在隔离子进程中执行且超时后的既有副作用明确保持不确定/HOLD。

正式审核 `6167741893` 的 S1–S5 已在同一候选批次继续收敛：重启判定
绝不返回 `ALLOW`；无外部可信结果源的阶段回执只标记
`FORMAT_VALID_CANDIDATE`；checkpoint 自洽哈希只标记
`STRUCTURALLY_VALID_ONLY`，并列出签名冻结回执、独立 Authority、实时 GET-only
复核和 Owner Release Gate；G5 所有布尔与计数字段执行精确类型校验；有界调用
改用 Pipe ACK，不依赖 `Queue.empty()`，并在超时后收敛 POSIX 子进程组、始终将
可能副作用标记为 UNKNOWN/HOLD。以上仍不构成生产执行权。

## 已有证据与剩余工作
- 东京Owner控制台2026-10-14T09:17:59Z：固定helper调用通过；国内模型与韩国小说模型隧道active。
- 韩国Owner控制台2026-10-14T09:19:34Z：固定helper调用通过；小说active；易币API/调度active；可用内存1311988kB/磁盘26G。
- 这些是Owner提供的现场回执；本PR取得真正Actions调用及hash后另记，不能预填PASS。
- 备份导出、数据库一致性恢复、易币可回退停用、隔离安装、行情/持仓/订单对账、影子验证、重启及回滚、唯一订单writer切换均未执行；不能通过本盘点放行。
- 需完整资产清单与受保护配置/数据库位置，方能冻结备份与部署操作包，不能猜路径或把活跃SQLite直接复制作为一致性备份。
- 英国只读重跑job115771246865仍排队；不会等待它阻塞东京/韩国独立盘点。不能伪造旧Work STOP或canonical writer接手。

## 本地验证
bash -n通过；helper额外参数拒绝(exit2)通过。非目标主机拒绝另验。
原cdd07e1491d0f0e5cfd7706f6b494df142df04aa获独立限定通过(review5515796568/comment6165218990)，两机实调用38542109818通过。新增hash/父路径增量仍需新HEAD CI和独立复审。本PR不合并/不执行生产变更。

## sudoers审计候选与公开日志收敛
新工作流不再公开sudo -l正文，仅记录可读取结果。
root_policy_audit.py是只读Root审计候选，不通过Runner自动执行：用visudo本身枚举实际解析来源，检查每个来源文件及父路径所有者、权限及软链，核对固定helper摘要，验证当前githubrunner只存在固定零参数grant及env_reset，拒绝广泛/多重grant、危险环境规则和检查期间源文件变化。仅输出数量、限定结果与hash，不输出策略正文或凭据。
该检查不是完整sudoers语义证明；输出full_sudoers_semantic_audit=NOT_VERIFIED。不能据此关闭全部规则/环境审计，更不能替代Runner全局访问政策。私有Root主机执行尚未进行，本地5项拒绝/合法路径测试通过；Hosted另取得回执。Python3.6语法兼容但实机解释器尚未验收。


## 2026-10-16 韩国Phase-B实机安装已提交，安全验收HOLD

Owner按独审6207630392执行一次准确632bbe6f安装，事务install-f887b085508e3ed4，SHA256c79182446ab8c2e447cb6942061710fb4a864addb4b9718f967402ef8c30cfe2；disabled/inactive/PID0/锁释放和六命名单元元数据未变均有Owner输出。现场同时出现LoadCredential未知及BPF/cgroup防火墙无效的明确告警，因此不能接受旧检查器末尾的PHASE_B=PASS作隔离通过；当前PHASE_B_SECURITY_ACCEPTANCE=HOLD，Phase-C与东京退役仍HOLD。完整结果见原PR99#6207782855。

本批只修正源码检查器的零退出告警误报并增加首次锁/用户/目标变更之前的能力预检，新17项Shell专项本地通过。真实兼容隔离方案仍需主机能力验证、准确修复计划与独审后才能执行；不覆盖/重装现有现场，不升级全机systemd/kernel或改全局防火墙。新的源码未部署，不重复已关闭R2/R6的独立审核。未变原137测试作为历史基线保留；源变更按既有CI自动验证，不冒充重复的root验收。


## Complete old-systemd Phase-B compatibility repair candidate (2026-10-16)

Owner-root reports systemd239/kernel5.10 and a distinct temporary net namespace
with only lo. A complete, separately admitted repair is in
[korea-offline-repair/README.md](korea-offline-repair/README.md). It preserves
original 17 Runtime files, release/current/venv and replaces only the installed
unit plus the transaction unit hash, using PrivateNetwork=yes/AF_UNIX and only
the existing no-network self_check. All service starts and Phase-C remain
forbidden. Exact single-use review+Owner-root admission, backups, partial-failure
preservation and final manager/disabled/inactive/lock checks are included.
This is a new review candidate; no repair approval, root anchor or actual
replacement has been performed. The earlier fresh-install fail-closed guard
remains separate and has not been deployed. Do not rerun the old installer.
