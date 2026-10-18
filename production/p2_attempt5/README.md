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

首次部署仍需一份准确安装许可覆盖配置、服务、前置目录、原16阶段激活和最多5次Attempt。配置SHA必须由独立批准记录提供，不能现场自行计算后宣称批准。entry.py和assembly.py也必须由受信执行通道校验准确SHA后启动；--assembly-sha256在导入前强制核验模块。新Grant必须绑定增量包的新Source Commit/Tree及新Manifest SHA；entry核验整个增量文件闭包并仅把原f4f Kit作为独立历史依赖导入，不能用旧f4f Grant授权新增胶水。--assembly-manifest及其SHA显式绑定新版本，旧Kit内Manifest字节不改。serve只打开已注册、未过期且未停止的Grant数据库；不签发许可。run仍由NativeRecovery认证原独立审核ID/批准正文SHA、源码与策略，同Grant可安全续接。

不会自动重发RPC。提交后签名/回复失败返回HOLD，已有PermitCycle负责以原Attempt绑定可信查询/收敛。进程正常退出仅删除其自己inode的socket，持久数据库/锁/额度/回执不删；崩溃遗留socket拒绝覆盖，需原许可范围内确认进程/事务后安全恢复，不能直接unlink重试。共享库的flock仅附加本地进程排他，不代替真实跨主机Writer证明。服务退出/重启不初始化历史；成功及5次耗尽由原核心终止。

SQLite父链保护不放宽；不chmod/chown旧业务目录，不打开旧业务DB，不能把旧state.sqlite当作AuthorityStore。新数据库首次创建及独立Grant注册是受信管理员的部署前置，代码不自行补空历史。

## 验证与交付

新增27项真实Unix socket/跨进程/签名/SQLite集成与反例，配合25项Issuer、21项AuthorityStore、10项ReceiptProvider受影响回归，总计83项/环境。主机副作用明确为SYNTHETIC_TEST_ONLY；不代表英国生产验收。当地运行环境拒绝AF_UNIX socket创建（EPERM），未申请提升或换通道绕过；完整动态测试由隔离Hosted Linux容器完成。原951项不重跑。verify.py逐字比较全部Attempt5核心源码与f4f74fdd，输出精确Commit/Tree、文件SHA、日志、Manifest及独立装配包；继承Kit和Manifest SHA固定记录。

本次增量尚待独立审核。INSTALLATION=NOT_EXECUTED；INSTALL_PERMIT=NOT_ISSUED；P2_RELEASE=HOLD。


## 生产配置登记与只读查询（本轮新增）

核查结论：此前entry.configuration仅能从调用者已知的准确路径/SHA读取配置；仓库交付没有生产配置登记索引或只读查询命令。英国现场是否另有入口仍UNKNOWN，不能由仓库缺失推断现场不存在。此处新增原架构内的root管理登记层，不替换Issuer/AuthorityStore，不改已审核心。

正式入口：production/p2_attempt5/registry_cli.py，严格-I -B -S。
操作register/query；两者都必须显式给出registration-id、record-sha256、assembly-sha256、registry-code-sha256；register另需binding-file。
规范登记根为/etc/xuanjun-p2/registry（代码约定路径，尚未部署，不声称现场存在）。也允许许可固定另一个完整registry-root，不发现、不遍历、不猜路径。根目录须事先按获准部署步骤建立root/0700；代码不创建根目录。

register仅以O_EXCL/root0600写一个内容寻址SHA固定的registration-id.json，逐段写入/fsync文件与目录；同ID同内容可幂等确认但不重写；冲突、链接或部分输出HOLD并保留。不会覆写旧配置/登记文件、创建共享库、注册Grant、获取Writer或Lease；未知生产事务仍保持未知，不以登记代替对账。
query只用受保护O_RDONLY+O_NOFOLLOW读取准确记录及其固定来源文件；不创建文件/锁/数据库、不执行adapter、不读私钥，不网络查找，不改变Quota。输出只有登记ID及各项摘要，不输出私有路径、配置正文或source_id正文。正常文件读取可能产生系统atime，不宣称零系统元数据变化。

登记记录严格schema=1、registration_id、hostname、config(path/sha256)、sources四项（issuer/adapter/authority_store/writer_fence，每项固定path/sha256）。record-sha256即规范JSON UTF8 LF完整字节摘要；拒绝重复键、非有限数、路径穿越和大于64KiB。
配置仍沿用既有严格字段结构。四份来源文件均要求root/0600、受保护无链接父链、固定SHA，严格schema/kind/hostname/source_id/subject；subject必须与配置中的Issuer+公钥DER摘要、adapter路径/SHA、AuthorityStore路径、完整principal分别一致，UNKNOWN或缺少来源不得登记。
source_id是受信root管理员保存的来源索引，并非由程序新签发的审批或跨主机证明。登记验证的是“受保护来源文件与配置准确绑定”，不是独立证明来源声明真实。可信原件、登记写入权限及准确摘要必须由同一受控部署/审批范围提供。query的authority_live_state/writer_fence_live_state始终UNKNOWN、installation_permission=NOT_INFERRED，不能据此放行安装。

entry.py的serve/run均新增强制registry-root、registry-id、registry-record-sha256参数，在创建Issuer、Provider、Ledger或Driver前，按新装配Manifest的文件SHA载入registry模块并核验该登记及所有来源，要求实际config路径/SHA/解析值完全一致；缺登记、旧登记、来源漂移、换配置即HOLD，无自动登记或兼容绕过开关。旧配置和旧Grant不被修改/复活；仍由原NativeRecovery认证安装许可与实际Writer/Fence/事务。
登记与新生产适配器不是同一个能力：build_driver/build_host_readback/public_modulus仍需实际源码与可信现场绑定，本次不冒称已经闭合完整serve/run生产链。

本轮新增28项登记/查询、并发、重启进程、正式CLI、幂等、部分失败保留、来源绑定、SHA/父链/权限/链接拒绝及不触碰DB/Grant/私钥/adapter测试。受影响Hosted验收为111项/环境=新增28+原装配27+Issuer25+Authority21+Receipt10；25份核心文件仍与f4f逐字相同，不重跑951项，不重审已通过未变部分。登记本身不需要从未知事务创建新账本，也不要求Owner再跑D1。
当前本地命令执行器不可用（exec-server缺失），未反复尝试或扩权；源码使用既有GitHub开发连接提交，测试与制品由隔离Hosted闭环。现场登记部署仍NOT_EXECUTED；正式登记/安装许可及独立审核以原PR58有效记录为准。
