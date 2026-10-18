# P2生产装配增量

接续PR17/PR58。唯一开发Writer为Work；窗口1已停止，窗口4负责现场。
继承f4f74fdd核心、951项及Dots#6248479254，不重跑D1/Prepare，不用旧安装工作流。

## 能力分层

已实现未部署：既有IssuerService、AuthorityStore、NativeRecovery、PermitCycle；新增assembly.py提供真实RSA/OpenSSL文件描述符签名、公钥DER SHA信任钉扎、Linux Unix socket/SO_PEERCRED双向root身份认证、固定principal及Grant绑定、唯一Issuer进程锁、既有共享数据库打开、NativeRecovery/PermitCycle装配。entry.py提供明确serve/run启动入口，严格隔离解释器、逐父链无链接/保护校验、独立SHA固定的配置/loader/装配模块/现场适配器。原核心和Kit字节均不修改，增量包另行绑定。

真实接口尚缺现场实现或证明：由已批准的独立适配器提供build_host_readback(config)、build_driver(config)、public_modulus(config)。此为明确外部接线接口，不是已完成生产读回；不得用本测试的host函数替代。没有适配器文件及独立批准SHA即拒绝启动，不自动生成、猜测或接受布尔verified标志。适配器变更须集中增量审核，原核心不重复审核。

现场UNKNOWN：Issuer/公钥来源及现有私钥路径、主机实际执行身份、Writer/Lease/Fence/Epoch、唯一共享库与历史、Run/Job/InvokeId和原事务/备份checkpoint；UNKNOWN不等于源码缺陷。root是本地Unix通道信任边界，不声称跨主机认证；本实现适用于同主机独立受保护Issuer，远端部署必须用原受信通道并另核准确身份绑定。

## 与窗口4六类取证唯一对齐

1. 执行身份/唯一Writer→固定root本地身份、principal.host/actor_id/writer_id；原生阶段锁及服务端Fence照旧。
2. Issuer/Signer/Transport→已部署入口/源码SHA、独立信任的RSA公钥DER SHA和模数、认证通道；禁止传私钥/token到公开任务。
3. 共享AuthorityStore/Ledger→准确现存数据库/账本路径、owner/mode、保全及备份；服务不初始化数据库、不注册Grant、不恢复额度。配置的Grant必须已在该唯一服务库独立注册；不得复制服务数据库开第二Writer。
4. 原事务及16阶段→host_readback逐操作按IssuerService原schema认证真实Run/Job/InvokeId、payload/Grant/Attempt绑定与副作用；build_driver装配原FiniteLiveControls/HostContainment/持久journals，NativeRecovery继续强制检查并认证PR58，不提供fixture开关。
5. 备份/检查点→真实backup/checkpoint/log SHA及恢复条件；缺失/部分写入/UNKNOWN拒绝推进，不删状态、不SKIP。
6. 新版本目录/运行入口→独立Kit根、增量装配代码根及SHA、root保护路径、配置与日志/账本在Kit外；不得修改旧冻结文件或旧三件套。

## 运行与恢复边界

首次部署仍需一份准确安装许可覆盖配置、服务、前置目录、原16阶段激活和最多5次Attempt。配置SHA必须由独立批准记录提供，不能现场自行计算后宣称批准。entry.py和assembly.py也必须由受信执行通道校验准确SHA后启动；--assembly-sha256在导入前强制核验模块。serve只打开已注册、未过期且未停止的Grant数据库；不签发许可。run仍由NativeRecovery认证原独立审核ID/批准正文SHA、源码与策略，同Grant可安全续接。

不会自动重发RPC。提交后签名/回复失败返回HOLD，已有PermitCycle负责以原Attempt绑定可信查询/收敛。进程正常退出仅删除其自己inode的socket，持久数据库/锁/额度/回执不删；崩溃遗留socket拒绝覆盖，需原许可范围内确认进程/事务后安全恢复，不能直接unlink重试。共享库的flock仅附加本地进程排他，不代替真实跨主机Writer证明。服务退出/重启不初始化历史；成功及5次耗尽由原核心终止。

SQLite父链保护不放宽；不chmod/chown旧业务目录，不打开旧业务DB，不能把旧state.sqlite当作AuthorityStore。新数据库首次创建及独立Grant注册是受信管理员的部署前置，代码不自行补空历史。

## 验证与交付

新增22项真实Unix socket/跨进程/签名/SQLite集成与反例，配合25项Issuer、21项AuthorityStore、10项ReceiptProvider受影响回归，总计78项/环境。主机副作用明确为SYNTHETIC_TEST_ONLY；不代表英国生产验收。当地运行环境拒绝AF_UNIX socket创建（EPERM），未申请提升或换通道绕过；完整动态测试由隔离Hosted Linux容器完成。原951项不重跑。verify.py逐字比较全部Attempt5核心源码与f4f74fdd，输出精确Commit/Tree、文件SHA、日志、Manifest及独立装配包；继承Kit和Manifest SHA固定记录。

本次增量尚待独立审核。INSTALLATION=NOT_EXECUTED；INSTALL_PERMIT=NOT_ISSUED；P2_RELEASE=HOLD。
