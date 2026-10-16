# PR99 Phase-C 离线适配候选

本包是可复核的适配源码、合成测试及配置模板，**不是安装器、安装批准或真实 Shadow 验收**。无默认生产配置，无默认密钥，不读环境变量凭据。导入、构建和测试不调用 nft/systemctl、提供方或真实数据库。原 Phase-B 的17文件、release/current、unit、事务、历史回执均保持原样。

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

- 新C精确配置及单次独立执行许可；可信root私有锚点及一次消费。**本包现有的install_controller仅安装停止状态的独立C候选；没有真实观察启动/退出/撤销控制器**，不复用旧B许可证。完成剩余准入前不可直接运行broker/worker模式。
- root核验UID986没有其他业务进程，新worker UID/GID及精确对象、原B冻结状态、共享服务元数据；准确nft程序/旧规则私有摘要/专用表不存在、语法及实际围栏读回/负向网络证明。nft -c不等于阻断证明。
- 真正的独立只读SecretRef、账号及提供方只读权限证明、受信custodian provider接线；真实值不进GitHub/env/argv/日志。生成短期私有交付和分别受控签名身份，配置只放引用/公钥/hash。
- 当前东京权威源库身份/授权账号/schema及WAL collector实际接线，固定身份的私有跨主机接收通道和逐周期新代；禁止把业务数据/回执正文上传GitHub。本测试只操作临时合成数据库。
- Owner确认观察参数（原24h/300s/288样本等仍是未批准建议）、准确expiry及资源预算；实际cgroup v1 peak/failcnt/oom_control可读性和双进程内存预算。
- root受控编排应先核围栏和凭据/快照，再仅一次启动新的worker依赖链；退出/失败后确认worker/broker均无进程，再撤销本轮临时交付，保留原SecretRef、围栏及证据。不能先删围栏，也不能因应用attempt文件而声称已完成root单次消费。失败不得自动第二轮。

这些实际绑定/控制器、root准入及真实隔离在后续**同一C集中执行包**补齐后才申请一次生产范围批准；本离线源码审阅不能代替它。Phase-D/E、数据库/Writer切换和东京退役继续HOLD。

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
