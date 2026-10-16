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

- 新C精确配置及单次独立执行许可；可信root私有锚点、一次消费和控制器。**本包没有root安装/启动控制器**，也不复用旧B许可证。完成这些前不可直接运行broker/worker模式。
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
