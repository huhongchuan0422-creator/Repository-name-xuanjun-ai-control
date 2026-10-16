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

## A. systemd239网络适配候选

优先评估仅针对专用xuanjun_binance UID的独立IPv4/IPv6 OUTPUT链，应用层仍只GET。此为待核实候选，绝非已证明主机支持：

1. 受控root只读前检确定iptables/ip6tables后端版本、owner/conntrack能力、专用UID、该UID无其他服务/进程、现有chain身份/规则摘要；不modprobe、不更改global sysctl/Tailscale/桥接，不升级kernel/systemd。
2. 新事务只管理自己的有名chain和OUTPUT中精确uid jump。不得flush/restore全局规则、修改INPUT/FORWARD、替换全局默认policy或碰其他UID。固定非私网/非环回目的IP的TCP443白名单、末尾拒绝；IPv4/IPv6必须同时围住。
3. 原candidate停止且同UID无其他进程时先安装完整拒绝链，再绑定uid jump，读回精确规则。半成功/后端不支持=HOLD，不启动；不得静默降级为仅应用层限制或仅IPv4。
4. C单元去除offline PrivateNetwork/AF_UNIX仅能随新获批C候选准确变更。保留去capabilities/NoNewPrivileges/只读code及其他sandbox；出站围栏先通过才允许新C进程启动。旧B单元/事务受保护，不原地手调成C。
5. 启动后先证明禁止目的地、端口、UDP/未批准IPv6及provider写方法拒绝。实际提供方调用之前要有专门允许的测试地址/方法范围，不能用真实订单路径发POST“做负测”。真实GET必须在凭据和snapshot准入后另纳入同一C许可。
6. IP轮换/围栏漂移/超时立即暂停该观察窗口；不得自动放宽CIDR、临时放行DNS或换IP重试。临时失效是HOLD，不假报源站问题。
7. 失败先只停止新C实例并撤销该实例只读交付，保留其出站拒绝规则和证据；不能先删除围栏留下活进程。任何目标不明时保持HOLD。上述停止/撤销边界应由C许可一次包含，不能靠事后临时扩权。

如UID级方案无法在此主机提供可验证隔离，应停止并集中提出替代；不得启用BPF假设、全局开forwarding或为通过测试解除现有隔离。当前主机是否具有这些能力仍UNKNOWN，需要受控前检，不伪造已可执行网络方案。

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
