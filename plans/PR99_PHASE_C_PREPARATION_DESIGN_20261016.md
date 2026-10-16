# PR99 Phase-C：完整离线准备设计及实施清单（2026-10-16）

状态：OFFLINE_MECHANISM_CANDIDATE_READY_FOR_CONSOLIDATED_REVIEW / PRODUCTION_EXECUTION_NOT_AUTHORIZED。

当前准确C源码：e9052b4e9d7de8a3cf27b3ab5282a19d120878b4；Hosted134/134、零跳过，实际制品44绑定/30runtime已由开发方下载复算。四链路适配、停止状态安装、围栏预检、观察编排和PID1失联收尾已实现；真实私有身份/账号/schema/持续刷新部署及全部实机门禁尚未闭环。本文不是安装/启动许可或实机验收，完整当前证据见文末本轮集中候选与PR99_PHASE_C_STATE_20261016.json。下文保留初始设计和阶段历史，未实现的旧状态由文末当前记录取代。沿原PR99推进，不新建分支或任务队列。

## 已完成的前置，不再重做

韩国iZmj7a5kwr75qc1tul4kf9Z，kernel5.10.134-19.8.al8.x86_64/systemd239/Python3.11。Phase-B原17文件manifest f887b085508e3ed4831dbed22152e35af5e8aba95b85b899b4697c61449917de已安装。获批收尾源码19f0e27de89b50eb990573f5b2a3ad13bdd7b3eb及原包35caaf41040c734565e68ff0c3a25a40be7304b1d58838596aa73f5acb23ff24不变。Owner执行6208995784，返回OFFLINE_REPAIR_FINALIZE_PASS_WITH_SCOPE_LIMITS/exit0；同一dev25/inode4716空锁已报告释放，17文件/共享服务元数据未变，unit824fc0cb...9899b及transaction ee81a70b...4eb75未重写。

独立验收6209166651明确认可Owner-root回执，证据级别为PASS_WITH_SCOPE_LIMITS，不是独立root现场重采。185项/R2/R6/原制品继续继承。不可重跑B安装、repair、finalizer或借服务启动补验B。started_service_confinement=NOT_EXERCISED，C尚未授权。

## 现有代码的可复用接口与真正缺口

| 链路 | 原代码/准确契约 | 下一批必须实现并验证 |
|---|---|---|
| 真实GET网络 | korea/get_only_policy.py的ControlledHttpsTransport仅get、TLS hostname校验、固定目的IP、禁重定向；migration_shadow_entry.py的SignedReadonlyTransport | systemd239下真实内核出站围栏、准确IP准入/失效处理、启动后负向隔离；不能依赖不生效的IPAddressDeny |
| 只读凭据 | migration_shadow_entry.py _read_secure_file；ROLE=BINANCE_ACCOUNT_READONLY；拒BINANCE_TRADING/master key引用 | systemd239兼容的SecretRef托管/临时交付；真实账号/只读权限证明；不得把角色字符串当提供方权限证明 |
| WAL快照 | ReadOnlyBusinessDatabase、korea/snapshot_handoff.py；协议XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1 | 真实来源collector、closed generation publisher、受信签发/独立verifier及刷新接线；原接收器不能自己签PASS |
| 持续观察 | korea/shadow_acceptance.py；hash-bound window ledger、重启/资源/延迟/失败限制 | 有效Owner窗口参数、cgroup实际可读证据、逐周期fresh generation及中断恢复链 |

模板中的REPLACE_WITH_*、/run/credentials路径和owner_approved=false均不是可执行配置，不能原样交给Owner启动。原17文件离线release保持冻结；如C需新的runtime，另建内容寻址候选和新manifest，不覆盖B旧release或偷偷更新B事务。

## A. 已取真实元数据后的systemd239网络适配候选

原GitHub Run38859895705 / Korea Job116839560203（准确delivery71f9e115373bdc56cfe5dbbeeaaaae92b94fa642）已完成一次非root采集：UID1001、主机正确、无sudo/服务动作/provider/凭据/DB读取。候选专用UID/GID986、非交互shell；候选inactive/dead/PID0、PrivateNetwork=yes；systemd239、Python3.11.13、cgroup v1 memory controller可见；nftables1.0.4、nf_tables及nf_conntrack已加载；OpenSSL1.1.1k。版本和元数据不是root围栏验收。

据此优先适配原生nftables独立inet table/meta skuid986的出站围栏，不依赖systemd的BPF功能。官方手册确认inet同时覆盖IPv4/IPv6、meta skuid按socket UID匹配、不同base chain中accept不跳过后续drop；这些是设计依据，不证明韩国1.0.4的准确规则已加载或实际生效。来源：https://netfilter.org/projects/nftables/manpage.html 。

1. 未来受控root前检仍须验证真实UID986无其他业务进程、nft程序/父路径身份、现有全局规则的私有摘要、目标专用table不存在、相关内核表达式及语法；不modprobe、不升级kernel/systemd、不改global sysctl/Tailscale/桥接。
2. 新事务仅create自己的唯一inet table和output hook chain，不flush ruleset、不改INPUT/FORWARD或别的table/default policy。自身base chain policy accept保持其他UID原规则路径；每条限制必须先匹配UID986，允许准确提供方固定IP的TCP443，最后对UID986其余IPv4/IPv6出口drop。两种族的非批准流量都必须拒绝；不能静默只围IPv4。
3. 目标table已存在或规则/UID身份漂移一律HOLD，不能重用/覆盖未知对象。C实例停止且同UID无其他进程时，先校验batch再一次加载本事务自有table，读回准确规则/handle/hash；部分或未知结果停止不启动，不对全局ruleset作还原覆盖。
4. 原B offline unit保持不变。另一个获批C候选才可用新的受控unit和精确内容寻址runtime；其capabilities为空、NoNewPrivileges/code只读等保护维持。只有围栏和凭据/快照准入全通过才允许启动C，不能先解除PrivateNetwork试连。
5. 在新C许可覆盖的测试范围内验证禁止目的地/端口、UDP和未批准IPv6无法通行；应用层仍只GET。不能用真实订单POST做负测。单靠nft -c、内核模块已加载或systemctl配置文字均不是实际阻断证明。
6. 出站IP变化、expiry、规则漂移、计数/进程归属不明即HOLD，不扩大CIDR或临时放开DNS，不自动换IP重试。失败先停止且确认新C实例结束、撤销该实例临时只读交付，保留出站拒绝与证据；不得先删除围栏留下活进程。停止/撤销要由本次C方案和许可一次包含。
7. 不支持时集中提出替代，不启用不生效的BPF假设，不让其他共享服务承担网络配置变化。目前root enforcement、启动后confinement仍NOT_VERIFIED/NOT_EXERCISED。

本采集的iptables/ip6tables版本exit1不能解释为工具不可用：v1探针将可信symlink resolve后的xtables-nft-multi直接执行，丢失了调用别名argv0。因此这两项版本明确UNKNOWN。没有为了补这两项重跑全批；未来v2只修为验证canonical目标后保留绝对调用别名，已用本地真实multicall symlink测试通过，v2未在韩国运行。/proc/net/ip_tables_matches缺失和xt_owner未列出也不能证明编译/模块能力不存在。原始回执和v1来源hash保持不改。

## B. 凭据托管与交付候选

1. 只引用既有凭据系统内独立BINANCE_ACCOUNT_READONLY SecretRef，绑定真实账号和可核验的提供方只读权限；不复用交易key/master key，不把任何key/secret放GitHub、workflow env、argv、journal或公开制品。实际SecretRef身份/权限记录尚待核验，不要求Owner发送明文。
2. systemd239不使用LoadCredential。未来受信root交付器只能从准确获批SecretRef向/run中的单次专用目录交付；父目录root持有、可遍历权限最小，内容仅服务UID可读、mode0400，满足原_read_secure_file的禁止group/other位契约。C单元用ReadOnlyPaths约束该交付目录；专用UID不能兼任其他业务。
3. 两项凭据放同一不可变generation目录并一次切换引用，不能分开覆盖导致key/secret混代。准入校验owner/mode/nlink/路径链、有限大小、同一generation；更新失配HOLD。不得把检查失败降级成环境变量读取。
4. 托管源保留不变；撤销仅移除该C观察实例的临时交付并结束其读取进程，不自动删除原SecretRef或导出明文备份。交付/撤销必须在C包中测试中断/并发/重启，无任何实际凭据读取的离线测试只使用合成值。

## C. WAL collector / publisher / verifier闭合

1. 来源必须先绑定真实东京权威SQLite路径、账号和现有安全备份能力（目前不能凭源码猜路径）。未来源端collector复用read-only/WAL-aware backup，业务snapshot_id在同一闭合副本中取得；不停止生产Writer、不checkpoint/冻结原库、不把业务表导出GitHub。当前没有授权任何真实DB导出。
2. closed SQLite和原handoff FIELDS组成一个generation：schema_version/protocol/feature_id/account_id/database_path/database_sha256/snapshot_generation_id/captured_at_ms/published_at_ms/runtime_manifest_sha256/publisher_identity_sha256。不向严格FIELDS中私加签名字段；签名/可信收据在单独受保护通道上验证。
3. 独立签发/核验身份必须由受信根持有，接收方不能用自己可写的回执清单验证自己。原IndependentReceiptVerifier要求verify-snapshot-handoff和verify-shadow-receipt两个准确CLI输出，必须有实际实现及root固定文件hash/公钥或独立证据来源；不能只写verified=true，也不能把同Shadow进程自报TLS信息当独立证明。
4. destination先核source身份、账号、freshness、closed DB无wal/shm、hash和独立认证，再commit整代。读者在周期开始固定该代，旧代在所有读取结束前保留；不把两个固定文件分别rename冒充pair原子提交。原open-FD/materialize保护复用，但publish发生在receipt读取与DB打开之间的竞争也必须覆盖。
5. 每个观察周期有新鲜代，静态一次copy不能满足24小时窗口。未来需要明确generation接收/发布/保留周期与失败回执，弱网重传只认generation ID及hash，未知ACK不重做capture/覆盖，失配停止。
6. collector、签发器、传递、publisher与独立verifier尚未实机接线，当前只能离线实现/合成WAL fixture测试。不能声称实际授权可用或真实数据路线已经完成。

## D. 持续观察与终态

1. 继续原模板24小时/300秒/最少288样本/零失败/不允许重启，以及RSS512MiB、MemAvailable512MiB、swap增长128MiB、p95 2s/p99 5s；这些仍只是候选值，owner_approved保持false，不能因方案文档而自动批准。
2. root前检只读确认真实cgroup版本和适用memory peak/events或v1 max_usage/failcnt/oom_control路径及可读性；不能用进程RSS或假零OOM顶替。韩国2GiB还承载原业务，围栏/资源预算不得侵占共享服务或调整其配置来“凑通过”。
3. 同一window同时绑定exact C runtime/配置/凭据角色/账号/源库/发布者/核验器/网络规则hash/expiry；重复窗口、进程重叠、证据对象漂移、超时、样本缺口或任一失败均HOLD。精确失败禁止自动第二轮。
4. C成功仍只有PASS_READONLY_SHADOW_WINDOW，不发交易、不切DB/Writer、不撤东京。D/E/G仍另有独立门禁。

## 一次性集中交付要求及后续工作

同一原PR99分支集中提交以上适配的实际源码、完整绑定制品、离线故障/并发测试、准确C配置和root前检/安装/失败停止/撤销/回滚计划；只在这份完整候选准备好后送审一次，不按四条链分批索取许可。原B代码/185审结不重做，不为填模型分数重启主机服务。

当前下一动作是开发方完成C兼容适配与托管/快照/验证接线的离线实现，并把可安全取得的实际元数据归档。非root Runner不足以证明root围栏或私有SecretRef有效。原PR99 inspection job因公共共享production runner策略固定if:false，不能擅自解除来取证；不另启第二队列或恢复P2/UK。

### 进度分类（避免把设计当完成）
- PHASE_B=PASS_WITH_SCOPE_LIMITS（独立6209166651）
- PHASE_C_DESIGN=RECORDED
- PHASE_C_ADAPTER_IMPLEMENTATION=OFFLINE_ADAPTERS_IMPLEMENTED_ROOT_CONTROLLER_PENDING
- PHASE_C_REVIEW_ARTIFACT=HOSTED_BUILD_PENDING
- PHASE_C_ROOT_PREFLIGHT=NOT_EXECUTED
- PHASE_C_SERVICE_CONFINEMENT=NOT_EXERCISED
- PHASE_C_LIVE_GET/SHADOW=NOT_AUTHORIZED_NOT_RUN
- DATABASE_OR_WRITER_CUTOVER=HOLD
- TOKYO_RETIREMENT=HOLD

Owner当前不需重复取B资料或执行旧命令；未来必须需要其协助时，一次交付准确、已完整复审的root操作，不能把本设计文档当执行命令。

## 本轮实际离线实现（延续本计划，不替换原B）

原分支新增migration-prep/korea/phase_c独立包：nft规则编译/无DNS固定IP传输、原子只读凭据整代交付、WAL闭合副本/源端签名/接收/整代指针/固定代读取、独立GET broker与签名客户端、原pager/对账/window接线、双进程cgroup资源采样、严格准入/Manifest核验、systemd239单元模板及确定性审核打包。原8份复用源码与原分支逐字节核对相同，原B17/原unit/transaction/current未改。

已完成44项离线测试实现；本地Python3.12运行41通过、3明确跳过（本地namespace仅映射UID0，且禁止新建AF_UNIX listener）。Hosted Python3.11必须44项零跳过才记CI通过，当前待读取准确HEAD实际日志。不以跳过冒充所有权/跨UID拒绝或真实Unix监听通过。完整合成周期使用真实SQLite WAL、OpenSSL签名与原对账；观察窗口的时钟/资源/少量UID为显式模型，不是实际观察时长。

特别说明：原Shadow自报网络receipt不是独立证据，原占位CLI未被伪填verified=true；新C候选用不同UID的固定GET采集器只签自己实际获得的响应，worker无私钥/凭据，用外部固定公钥验证。broker仍UID986，worker需新独立用户，1986仅是测试数字。共享admin1000/Runner1001不允许作worker。

本批仍不包含生产安装/启动控制器。真实SecretRef/账号只读证明、源库身份/schema/collector及受信跨主机接收接线、新worker身份、观察参数与实际root围栏/签名身份/单次准入尚未绑定。README逐项列明，不能把“适配源码已实现”称为完整C执行包、实机隔离或服务器迁移完成。未来同一C集中执行包补齐这些准确绑定、root一次消费/失败停止撤销后才申请生产范围批准；本次不向Owner发旧命令、不启动服务或重复申请B审核。

### 已读回的实际CI与制品（只补证据，不重跑）

源码08c7e90cc02de270bd63c4dfc0de9803d6a6a81c，Run38864763014/Job116854934203，准确checkout，Hosted Python3.11.17，44/44、skip0、SUCCESS。此前本地无法执行的真实UID986交付/worker拒读和Unix SO_PEERCRED监听测试在Hosted通过；仍不是韩国systemd239实测。生产inspection job维持if:false/SKIPPED。

实际下载Artifact12030856104，ZIP c95fe723429aa294d30bd72df13b5449ec5be8ea523cc65ea3c316982c212be5，TAR a41487dbb26b2ce353ee238e39e14683f3d119cc91dde79f498b0f81beb98e09（59363字节），27常规条目、26文件绑定和22 runtime文件hash均复算通过，与本地确定性TAR逐字节一致。这是开发方真实字节复核，不自称独立审核通过。

本次不请求对未齐全的C生产方案分段签许可；先保留这批实际实现与可复算制品，原B不重审。下一准确缺口仍为真实只读托管/源端collector/跨主机私有接收绑定、新worker身份、完整root一次控制器及新的C准入；无现有Korea C固定root通道，不能使用已消费B许可绕过。

## 后续实现：停止状态C安装控制器与东京真实接口元数据

本轮新增authorization.py、install_controller.py及仅标准库root_handoff.py。入口在首次导入候选代码前核验准确归档/plan/许可/hash；创建受保护的新交接目录，子进程-I -B。root单次安装器只可创建新的停止C候选与专用非交互worker，核冻结B17/current/unit/transaction/六共享服务，daemon-reload一次后typed D-Bus/角色/字节读回、准确空锁释放后才成功。不加载nft、不启用/启动服务、不读取真实凭据或DB。owner_approved保持false、live-admission必须不存在。新源码并非实际root执行或已获安装许可，完整C观察启动/退出/撤销控制器仍待真实托管与传递绑定后实现。

测试覆盖准确/旧/错误/过期/编辑撤回批准、root私有锚点/载入源码身份、归档炸弹/路径/字节、父目录与umask077、bootstrap导入顺序及退出码、真实私有文件模式、部分安装、中断、并发、reload失败、锁漂移、共享服务与旧B保护。新增原生Python环境探针确认env-i/LANG=C可由CPython添加LC_CTYPE=C.UTF-8，准入显式接受此标准locale，仍拒绝PYTHON/SSL/loader等额外注入。77项本地70通过7受namespace/Unix约束跳过，Hosted Python3.11须新准确HEAD零跳过；旧B185不重跑。

没有要求Owner取资料。原PR122载体55ef5b94ef66ec9286b9aae9a165b019499a69a7通过同一v27队列仅一次Tokyo非root取证：Run38867192724/Job116862631607 SUCCESS，其余主机job全SKIPPED，无checkout/sudo/模块导入/HTTP/服务动作。源代码仅AST标识符与hash，不输出源码/常量/默认值；accounts.credential_store、secure_credential_intake、dual_api_readiness及repositories初始化4份均取得接口。源库/opt/trading-system/database/data/trading.db仅lstat，46907392字节、uid/gid1000、mode0644；没有打开DB、读schema或业务记录。mode/可stat不等于完成ACL或数据泄露核验，不自行chmod源库。

实际存在readonly角色描述接口，但凭据存储接口也有master_key及TRADING_CREDENTIAL_MASTER_KEY标记；不据此猜测/调用load_credential，更不能复用交易master key。真实只读SecretRef/权限、源库schema和私有collector/传递身份仍未证明。这是当前实际接入缺口，不能用源码名称或模型PASS代替。全部真实结果保存evidence/pr99-phase-c/TOKYO_SOURCE_CONTRACT_METADATA_20261016.json。

本次仍不发起拆分的生产执行申请；完整C执行包及真实绑定齐备后统一送审，不让Owner复跑旧命令。既有官网、DNS、B现场、东京和共享业务均未操作。

### 新准确源码CI/制品终态

源码32801fc886824447aaf51f4afd4a22d7c7b0ce1f，Run38868898561/Hosted Job116868059787，Python3.11.17，77/77 PASS/skip0，生产inspection仍if:false/SKIPPED。已读取原始日志，新增root安装/交接模型与旧适配集成一起验证；韩国Root执行仍0。

实际下载Artifact12032422528并复算：ZIP 8d256daf7b90cf5f565d4587cec1236b9887b5895a08211bbb3e843ac1c699f7；TAR 8200ccb5d86f09cb1d03a449921eddba4ab421e73cee6736a7ce9d951339bacd（82181字节），34普通条目、33/33绑定及25/25runtime hash匹配，本地重建TAR逐字节一致。旧08c7e90c制品保留历史，不将其审核/CI扩大到新安装器。新包是可复核候选，不是独立审核PASS或安装许可。

本批控制器/交接器的离线实现完成；实际只读托管/私有传递绑定与live运行、失败停止/撤销控制器仍待完成，真实C观察未开始。完整C生产执行方案齐全再统一送审，未要求Owner分段批许可或搬运数据。


## 本轮集中候选（2026-10-16，取代此前“控制器未实现”的当前状态）

准确源码 `e9052b4e9d7de8a3cf27b3ab5282a19d120878b4`。已完成整对权限承诺托管、固定身份mTLS四文件传递/远端路径签名、停止状态安装、独立root围栏加载及UID×IPv4/IPv6计数验证、只读观察单次编排、PID1 notify/watchdog/BindsTo与独立stop_guard。Root监督器纳入第三份独立cgroup资源计量，公开回执只含安全状态字段。实际执行根权限与真实只读秘密从未由源码/测试自动取得。

精确Hosted Run38874982348/Job116887738948，Python3.11.17，134/134、0 skip；本地134中127通过/7环境skip，未混写。Artifact12035120742实际ZIP下载复算，44绑定/30runtime/45常规条目，ZIP b1ea59d05c8da17ddb037cc4699a75d2b2d5b4f58cf54e7ba0a6e6d2572c43e9，TAR 898263578775de2d0486f2d2c18986192305a8edbe213279c5c4d7b4e35cc520，与本地确定性重建逐字节一致；开发方字节核验不是独审结论。

东京源声明实际Run38871973602/Job116877943391：50源、15表中13声明匹配，algo_order_snapshots与protective_order_snapshots未解析；没有打开DB，不得造空表凑数。韩国Run38874822582/Job116887220927：UID1001、systemd239对四份候选unit纯解析exit0/无诊断，无generators/Root/服务操作；不是实际隔离或watchdog验收。

一次性集中送原独审核整批C源码/闭包/制品和异常边界；原B/R2/R6/185及已通过网站范围继续继承。不申请拆散的安装或启动许可。真实SecretRef/只读权限、签名及mTLS身份/私有端点、权威账号/实际schema/持续刷新、窗口参数和受限root通道尚未绑定，任何生产Root或真实GET均必须另外满足精确执行门禁。C实机未开始，生产迁移/Writer/东京退役继续HOLD。
