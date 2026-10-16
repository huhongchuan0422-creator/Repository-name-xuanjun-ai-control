# PR99 Phase-C 离线适配候选

本包是可复核的适配源码、合成测试及配置模板，**不是安装批准或真实 Shadow 验收**。无默认生产配置，无默认密钥，不读环境变量凭据。导入、构建和测试不调用 nft/systemctl、提供方或真实数据库。原 Phase-B 的17文件、release/current、unit、事务、历史回执均保持原样。

## 已实现的链路

1. `network.py` 生成独立 nft `inet` output 表。仅 UID986 的固定公网 IP/TCP443被本表允许，再拒绝该 UID 其余 IPv4/IPv6；新 worker UID 的 IP 出站全拒绝；其他 UID不受本表限制，不 flush/global policy。表名、UID、IP、期限严格校验。UID1000/admin、1001/Runner和986不能充当 worker。`ApprovedPinnedTransport`复用原 GET/TLS实现，直接使用准确且限时的固定 IP，不通过放行DNS绕过围栏。
2. `credentials.py` 从调用者明确注入的受信 SecretRef provider 取**一整对**合成/未来真实凭据。只读账号证明须经过独立验证；私有pending目录、原子no-replace整代发布、root持有目录和 broker UID986/0400文件，断点不清理、不重读重试。systemd239不使用LoadCredential；源SecretRef不更改。
3. `snapshots.py` 复用原WAL-aware readonly SQLite backup及同副本的权威snapshot_id选择。只对私有副本改为DELETE journal并完整性检查，绝不checkpoint/改源库。原严格handoff FIELDS不改，源端签名另置文件。接收方核签名、准确账号/runtime/generation/path/hash/时效后才切换整代指针。读者先固定代名，再取得原open-FD保护；并发换指针不会混代。签名失败、重复generation、未知ACK均不覆盖或自动重采。源码仅提供接收接口，**尚未配置实际跨主机传输身份/通道**。
4. `broker.py` 补齐真实独立网络证据接口：worker不持凭据或签名私钥；UID986的固定GET采集器自己发请求并签其实际结果。worker用root固定公钥核验nonce/run/window/账号/快照/response/network-policy/有效期，继续交给原AuthenticatedGetOnlyPager。Unix SO_PEERCRED来自内核，不接受请求内伪造身份。拒绝任意URL、方法、请求头和凭据；未知请求结果不重发。
5. `runtime.py` 将上述代固定、broker客户端、原对账及原观察ledger接通。每周期新generation、永久本地attempt、窗口hash/独立授权/期限、资源和失败门禁；没有cgroup证据立即失败，不能用0或RSS代替OOM。整窗成功仍是READONLY，绝不授权Writer。

## 为什么原占位核验CLI没有被当成完成

原 `IndependentReceiptVerifier`要求两个CLI，但原Shadow同时自制网络receipt，没有独立的真实证据来源。直接补一个输出verified=true的脚本不满足契约。本候选保持已审旧源码不动，在新的C候选内实现分离身份的GET采集及RSA/SHA256独立签发/公钥验证，复用原pager、handoff、对账和window接口。代码中没有通过为自报TLS回执签名来“核验”它的远端签名服务：broker只给**自己实际采集**的结果签名，不接受外部传入receipt/response。

RSA签发身份、源端publisher身份和执行授权身份在部署时必须使用分别绑定的公钥/私钥；测试只用临时生成的合成密钥。RSA/SHA256使用OpenSSL的dgst -sign/-verify，兼容接口依据：https://docs.openssl.org/1.1.1/man1/dgst/ 。韩国OpenSSL1.1.1k的真实签名/运行尚未实测，不能把本地/Hosted OpenSSL结果扩大为该主机实测。

## 两个专用进程的边界

原UID986 xuanjun_binance继续作为候选只读网络broker（原B单元保持inactive）。对账worker必须使用**新独立非交互用户**xuanjun_binance_shadow，实际UID/GID尚未分配，不可用admin/Runner/交易身份代替。测试1986只是合成数字，不是已创建账号。

新单元名是xuanjun-binance-phase-c-broker.service、xuanjun-binance-phase-c-worker.service；不替换旧B单元。broker保留空capabilities、只读代码/密钥/交付目录，允许AF_UNIX/INET/INET6且仅由nft准确限制出站；worker使用PrivateNetwork=yes和AF_UNIX、不可访问凭据/私钥，仅可写自己的证据目录。模板没有Install节、Restart=no、有限时/进程数/内存；新broker按StopWhenUnneeded停止，worker绑定broker生命周期。这些是**模板约束，不是systemd239实机隔离证明**。

`prepare.render_units`只在内存中渲染精确专用路径，拒绝旧B路径、变量/引号/换行/ExecStart注入和未替换token。`entry prepare`只验证准确runtime和配置、输出候选规则；不加载规则、不安装unit、不reload。broker/worker模式必须再取得独立签发、准确config/window/主机/角色绑定且限时的C执行准入。运行期attempt是防误操作/正常并发保护，**不替代可信root对独立单次许可的私有消费**。

## 生产准入仍缺什么（不可伪造或填默认值）

- 新C精确配置及单次独立执行许可；可信root私有锚点及一次消费。**install_controller仅安装停止状态候选；lifecycle提供既有受信网络/托管/快照预检之后的单次观察编排，不提供预检伪证明或自行放行**，不复用旧B许可证。完成剩余准入前不可直接运行broker/worker模式；新源码不构成许可。
- root核验UID986没有其他业务进程，新worker UID/GID及精确对象、原B冻结状态、共享服务元数据；准确nft程序/旧规则私有摘要/专用表不存在、语法及实际围栏读回/负向网络证明。nft -c不等于阻断证明。
- 真正的独立只读SecretRef、账号及提供方只读权限证明、受信custodian provider接线；真实值不进GitHub/env/argv/日志。生成短期私有交付和分别受控签名身份，配置只放引用/公钥/hash。
- 当前东京权威源库身份/授权账号/schema及WAL collector实际接线，固定身份的私有跨主机接收通道和逐周期新代；禁止把业务数据/回执正文上传GitHub。本测试只操作临时合成数据库。
- Owner确认观察参数（原24h/300s/288样本等仍是未批准建议）、准确expiry及资源预算；实际cgroup v1 peak/failcnt/oom_control可读性和双进程内存预算。
- root受控编排应先核围栏和凭据/快照，再仅一次启动新的worker依赖链；退出/失败后确认worker/broker均无进程，再撤销本轮临时交付，保留原SecretRef、围栏及证据。不能先删围栏，也不能因应用attempt文件而声称已完成root单次消费。失败不得自动第二轮。

这些实际绑定、root预检/准入及真实隔离在后续**同一C集中执行包**补齐后才申请一次生产范围批准；本离线源码审阅不能代替它。Phase-D/E、数据库/Writer切换和东京退役继续HOLD。

## 本轮补齐的私有接线及观察编排（仍非实机运行）

- `credentials.PinnedReadonlyProvider`只读取可信root明确投放并固定SHA的单份0400私有输入；不扫描生产SecretRef，不调用交易CredentialStore，不从环境/argv取得值。独立权限签名须绑定账号、只读角色、引用、期限及**整对Key/Secret的域分隔承诺**；交付及载入都重算，混代或篡改不通过。权限签名必须来自另外的真实权限核验，开发方不能自行将角色字符串变成权限证明。源输入、承诺和凭据不得上传GitHub。
- `private_transfer.py`连接明确批准的固定IP/端口、校验SNI/CA/双向证书及准确对端DER指纹，不使用DNS、代理、跳转或自动重连。它不创建监听器、隧道、证书或生产端点。长度有界的四文件帧上限为64MiB数据库、单项16KiB元数据，逐段期限及读超时；源RSA签名和接收端原有严格handoff再次校验。源库只在显式获准collector调用时打开；源端关闭副本保持UID0，签名回执绑定**韩国最终路径**。这是现有collector/receiver之间的实际传输适配，不是已投放的跨主机服务。
- 发送/接收都先建立永久私有attempt。错身份、半包、签名失败、未知ACK不覆盖current、不自动重发。ACK丢失时允许“接收方已提交而发送方未知”这种真实边界，必须保留双方现场；不能据接收成功再次采集同代。测试使用真实合成WAL和OpenSSL双向TLS（socketpair），无提供方/生产网络、业务数据。
- `lifecycle.py`在**已经完成并获得精确批准的root网络/托管/源快照预检**之后，监督一个新的只读观察窗口。它不加载nft、不提供网络负向探针伪证明，不投放凭据，不签自己的观察准入，也不导出数据库。缺少真实root网络证据、四项UID×IPv4/IPv6 DROP计数增量、准确表语义摘要、预先交付的整对凭据/匹配签名私钥/新鲜源快照、独立签名准入或root私有精确许可时，服务启动前拒绝。
- 生命周期许可与停止状态安装许可严格分离；核当前GitHub全文、准入签名、安装回执/plan/runtime/单元实际字节、角色和systemd239 typed属性，永久单次attempt及锁后才更新获准acceptance/admission。新broker改为`Type=notify`，在Unix socket真正listen后发送READY，worker依赖其就绪，避免启动竞态。原B及共享服务不变。
- 观察中检查撤销标记/私有锚点、定期当前GitHub批准、表语义漂移、B/共享对象及PID变化；失败、SIGTERM/SIGHUP、未知启动都只对新C单元发一次stop，不启动第二轮。只有MainPID0、inactive/failed和UID范围无进程全部成立，才将**本轮临时pair和broker私钥**原子移动至同一`/run`文件系统的0700隔离目录，保留证据及原SecretRef；不跨文件系统rename，不先撤围栏。live-admission在`/etc`原目录原子改名保留。停机未知时不撤销进程仍可能使用的材料，不报告成功。
- 成功仅在整窗时长、精确PASS样本/不同generation、原窗口资源门禁、停机/临时隔离及准确锁释放之后成立。账号/systemd/nft/时间测试为明确模型；这不是实机网络隔离、真实只读GET或24小时观察。控制器SIGKILL/主机掉电不能保证立即执行finally；候选服务自身RuntimeMaxSec、签名期限和Restart=no限制剩余运行，但独立失联看护和实际断电恢复证据仍须纳入生产准入，不能把此限制隐去。
- `source_schema.py`是下一轮**非root源码声明**探针：只输出既有15表的批准列名匹配和源码hash，不输出SQL/常量，不打开DB或导入生产模块。即使源码声明兼容，也不能当成现有DB schema/账号数据已验证。

`fence.py`补齐与观察控制器分开的、单次准确root准入的围栏执行入口：只为已安装且两UID均空闲的新C候选创建专用inet表；先核准入、B/共享元数据、全局无同名表和nft语法，再仅一次从固定stdin加载已审compile_rules文本。为UID986及新worker各发IPv4/IPv6 loopback TCP负向连接（127.0.0.1/::1:9、无载荷、非provider），必须逐项看到该UID准确DROP规则的内核包计数正增量；仅连接超时/拒绝不算围栏证明。读回表语义摘要，其他stateless全局规则及共享对象不变、两UID重新无进程且准确锁释放后才输出root私有NETWORK_PROOF，其准确hash还须绑定后续独立live批准。已存在表、部分加载/未知、无计数增量、语义/共享漂移全部保留HOLD；不delete/flush或自动重试，不读凭据/业务库或启动服务。测试nft/systemd/UID计数是明确模型，实际韩国内核仍NOT_EXERCISED。nft命令/JSON/UID与counter依据官方文档：https://netfilter.org/projects/nftables/manpage.html 。

东京真实源码探针已完成：原队列Run38871973602、Job116877943391、delivery5830a6e6f69744132fb74b341abb9929ae1632d6；50份源码中13张所需表的声明与既有列契约匹配，algo_order_snapshots及protective_order_snapshots未解析到声明。此结果不是DB缺表证明；实际只读schema/权威状态仍需现场准入后确认。绝不创建空表、编造零订单或用普通订单冒充保护单来凑验收。

当前真实缺口：独立只读SecretRef/提供方权限证明与托管投放；专用传输双端身份及固定私有端点；权威账号/实际schema与持续collector投放；root围栏实机执行及内核负向证据；独立失联看护及实机验证；准确窗口参数、单次许可和可信root执行渠道。围栏加载代码已实现但未在主机执行，失联看护不能冒充已实现。上述适配代码不补造这些值，不申请拆散的生产安装批准。

## 构建与验证

仅在开发/Hosted环境运行；以下不是服务器命令：

```
python3 -I -B -c "import sys,unittest;sys.path.insert(0,'migration-prep');s=unittest.defaultTestLoader.discover('migration-prep/korea/phase_c',pattern='test_*.py');r=unittest.TextTestRunner(verbosity=2).run(s);raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

文件身份测试要求root所有权的合成临时目录。当前本地user namespace只映射UID0，不能伪称执行了UID986交付或真实Unix listener；这些项目要求Hosted root测试补齐，跳过不能算完整CI通过。本地其余测试使用真实SQLite WAL、OpenSSL签名、文件权限及原子rename，窗口时钟/资源和少量UID为明确模型，不是观察了真实60秒/24小时。

`artifact.build(root, exact_commit, output)`生成确定性TAR、独立runtime Manifest和REVIEW_BINDING；严格固定源列表，只打包本批代码、复用依赖、测试/模板/本文。无业务DB、实际凭据、私钥、生产配置或安装权限。runtime入口要求root固定Manifest与逐文件hash/身份，不是只相信版本字符串。制品下载后按原始字节核验，不能用开发者的PASS声明替代独立审核。

## 独立C候选安装控制器（源码已实现，未经许可/实机执行）

`authorization.py`和`install_controller.py`补齐后续安装支持，不要求现在把它拆成一个审批节点。真实只读托管和传递绑定未齐前，不申请执行。具体行为：

- 必须在准确韩国主机，以干净环境root从root持有的准确归档源码运行。载入的整个runtime逐文件与归档比较；根目录/父路径/文件owner-mode、普通文件、非link检查真实执行，不要求/root父目录为0700。
- `root_handoff.py`为仅标准库的独立交接入口：先核root私有锚点、批准全文/当前GitHub正文、归档/plan/交接器/控制器准确hash，再在/var/lib新建0700专用目录安全展开；**首次导入候选模块之前**完成源字节认证。禁止重复使用交接目录，压缩展开限制16MiB，不使用/tmp或/var/tmp作为可信导入路径；整个子进程-I -B、干净环境，错误保留日志。它本身也必须由Owner-root独立核验准确SHA后运行，不能自我授权。
- 原始归档/严格清单/精确commit/controller/具体plan SHA须与独立许可匹配；root私有锚点0700/0600，批准全文哈希、GitHub当前原始正文、准确主机/动作/版本/时效/max1和所有禁止项逐项校验；过期、旧批准、编辑/撤回或GitHub不可达均停止，未创建永久attempt。root锚点本身须由可信root渠道从独立审核取得，开发方不能自行代签。
- 公钥输入只能来自固定root私有phase-c-public-inputs目录的broker/source/authority.pem三份文件。交接文件、归档和plan也须在root所有且父路径不可被他人写入的位置；不从Runner checkout或world-writable临时路径直接导入代码。实际密钥/托管/传递接线仍未进行。
- root副作用前核固定B的17文件、manifest/current/unit/transaction和disabled/inactive/PID0、六共享unit元数据、新C全部目标不存在、UID986和新worker身份/进程、三份**不同**公钥的实际hash/RSA有效性。源库、密钥和凭据内容都不读。
- 一次性私有attempt与独立锁，创建专用非交互worker（仅在准确plan/permit明确允许且UID/GID未冲突时），新内容寻址release/配置/公钥/私有证据目录、三个未启用的单元；只保存候选nft文本，**不加载网络规则**。owner_approved保持false，live-admission文件必须不存在。
- root创建0755/0711目录时显式处理umask077，整代no-replace发布及fsync，绝不覆盖B。systemd-analyze verify不启用generators；daemon-reload只一次，然后读回实际角色、单元文件与typed D-Bus PrivateNetwork/RestrictAddressFamilies（兼容239的[unprintable]），保持static/disabled、inactive/dead/PID0。
- 成功必须在准确空锁身份核验并释放后才记PASS；任何中断/未知/部分写入、权限/锁漂移、共享对象变化，保留新旧现场和有界私有失败回执，不自动清理、回滚或重试。不执行服务start/enable/stop、真实GET、凭据操作、数据库操作或东京操作。

安装终态仅为`C_OFFLINE_CANDIDATE_INSTALLED_NOT_STARTED`，不能当成C Shadow成功。其测试使用真实root持有的临时文件/权限、原子发布与公钥解析，但账号/systemd/root服务动作及17份B内容是明确合成模型，**不是韩国生产安装**。生产CLI没有test-root/model参数；测试Context不可从命令行选择。准确生产常量继续绑定原已接受B哈希；没有重跑B185或更改原B安装器。

## 东京源码接口元数据取证

`source_contracts.py`仅为非root独立探针，不属于Korea runtime闭包。固定读取4份.py代码的AST、标识符接口与hash，另对已知源库路径lstat；不输出源码/常量值/默认值/文档串，不导入生产模块，不读取凭据文件或DB字节。真实接口与路径元数据结果另存evidence，不能用角色标记出现推导真实SecretRef已存在、权限正确或完整调用链已审。

原v27队列本轮一次性东京job，无checkout/sudo，其他主机job跳过。取证代码SHA256 `0b4c7804c3f786fdadc57548c85d48c683530fc1a76bf9d47fe72727a10cb545`，delivery `55ef5b94ef66ec9286b9aae9a165b019499a69a7`，Run38867192724/Job116862631607。4源接口已取，权威候选库路径/46907392字节等仅为stat；schema与业务内容没有打开。CredentialStore接口含master_key及交易master-key标记，因此不能未审调用load_credential或将交易master key作为C只读托管捷径；实际独立只读provider仍NOT_PROVEN。
