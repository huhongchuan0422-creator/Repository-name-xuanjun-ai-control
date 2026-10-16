# PR99 Phase-C：完整离线准备设计及实施清单（2026-10-16）

状态：PREPARATION_DESIGN_RECORDED / EXECUTION_NOT_AUTHORIZED。本文不是运行许可、实现完成声明或实机验收。沿原PR99推进，不新建迁移架构、分支或任务队列。

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
- PHASE_C_ADAPTER_IMPLEMENTATION=NOT_COMPLETE
- PHASE_C_REVIEW_ARTIFACT=NOT_BUILT
- PHASE_C_ROOT_PREFLIGHT=NOT_EXECUTED
- PHASE_C_SERVICE_CONFINEMENT=NOT_EXERCISED
- PHASE_C_LIVE_GET/SHADOW=NOT_AUTHORIZED_NOT_RUN
- DATABASE_OR_WRITER_CUTOVER=HOLD
- TOKYO_RETIREMENT=HOLD

Owner当前不需重复取B资料或执行旧命令；未来必须需要其协助时，一次交付准确、已完整复审的root操作，不能把本设计文档当执行命令。
