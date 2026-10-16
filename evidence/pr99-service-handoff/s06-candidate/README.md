# PR99 S06 私有运行合同采集：固定配置一次加密交接

R2离线恢复点已按#6217422554限定验收通过，不重新复制、不重审原B/C、源码、数据库或依赖环境。本批承接S06，为后续服务接续取得当前unit/drop-in及双机监听归属；不是服务安装或完整迁移。

## 精确新范围

韩国可信root运行本文件一次，确认已验收R2的私有final-receipt字段、准确新脚本SHA和新独审许可。通过既有固定东京ECDSA主机键及Owner终端root密码认证连接东京，不创建SSH密钥、账户或sudo权限。密码不写入参数、环境或日志。

东京新私有目录`/root/pr99-s06-runtime-contract-v1`；韩国新私有目录`/root/pr99-s06-runtime-received-v1`，均0700、独占创建。旧R2和历史失败目录不修改。

固定读取 `/etc/systemd/system/` 下以下10个root拥有、不可组/其他写入、常规非链接的当前unit：

- secure-secrets-portal.service
- xuanjun-wecom-customer-contact.service
- xuanjun-wecom-customer-service.service
- xuanjun-wecom-novel-ingress.service
- domestic-model-rpc-tunnel.service
- korea-novel-model-rpc-tunnel.service
- provider-neutral-tokyo-tunnel.service
- restricted-rpc-openai-shim.service
- tokyo-restricted-model-executor.service
- xj-tokyo-vpn.service

唯一drop-in：`/etc/systemd/system/tokyo-restricted-model-executor.service.d/provider-health-alert.conf`。

前后核对manager选定属性（包括PID/依赖/目录/EnvironmentFiles路径，不读取Environment值或ExecStart参数）与11份源文件SHA。任一load、fragment、drop-in集合或采样过程漂移即HOLD，不自动改变白名单。generic provider-neutral-tunnel unit只查询属性，不当成别名、不安装或修复。

附加私有元数据含选定监听端口的PID、exe/cwd/UID及cgroup所属service，用于闭合此前非root无法取得的归属。绝不读取/proc cmdline或environ。韩国取得同类本地监听元数据，尤其443。进程竞态、权限问题必须标UNKNOWN，不能宣称端到端认证或服务已搬迁。

**不打开EnvironmentFile、API/Token/SecretRef文件、SSH私钥、TLS私钥、数据库、业务日志或cron正文。** 不采集整个/etc、runtime或home。由于unit正文自身可能存在内联认证，不能宣称“凭据完全未读/绝无秘密”：仅固定unit原始字节进入root私有加密包，不解析、使用或对外显示任何凭据；不从其中加载环境、不执行配置。接收回执明确`unit_bytes_may_contain_inline_authentication=true`、`credentials_used=false`、`private_credentials_absence_proven=false`。独审必须明确接受这一私有配置原件保存边界，不能把本许可扩成环境文件/业务凭据迁移。

## 保存与传输

源码只在GitHub；**真实unit原件、私有元数据、明文tar、密文、恢复密钥和SSH日志都留在两端root私有目录，不上传GitHub/CI/聊天。** 允许这批新私有暂存对象及SSH连接，生产配置/服务不写。源文件单个上限256KiB，总载荷4MiB，所有读取均检查链接/父路径/root身份、限额及前后inode/大小/时间稳定性。

10个unit＋1个drop-in＋private-runtime.json，共12个常规成员。AES-256-CBC/PBKDF2/SHA256、随机私有key；加密并核对密文SHA后通过已固定SSH传输，接收端再次解密核对归档SHA、成员白名单、类型、数量及逐文件SHA。加密完整性依赖SSH及经该通道取得的摘要，不宣称CBC本身提供AEAD。原始unit不提取到/etc或任何生产目录，不导入应用。

本批单次≤12小时许可。单次准入由全新目标目录占用表示；源目录独占防止远端重入。失败、超时、SIGTERM/HUP保留现场，不自动清理、重试或回滚。SSH错误只进入韩国0600独占日志。信号/断电极小窗口可能只剩attempt目录或started标记；这种状态属于UNKNOWN，绝不视为未消费或直接重跑。文件fsync和目录fsync用于已完成写入的持久化，不声称跨机原子事务。

## 新机器许可合同（模板不是许可）

独审需直接签发本批准确脚本/提交/双机/动作的单次许可，并返回完整评论正文SHA。Owner-root须从独审渠道独立取得该SHA并显式确认身份；同GitHub账号不能提供密码学独审签名。

<!-- PR99_S06_RUNTIME_APPROVAL_V1
{"decision":"APPROVED_WITH_EXACT_PRECONDITIONS","action":"PR99_S06_PRIVATE_RUNTIME_CONTRACT_V1","max_attempts":1,"source_commit":"<准确提交40位>","script_sha256":"<runtime_contract.py准确SHA256>","source_host":"iZ6wee8q9z4t03hvqumwfhZ","target_host":"iZmj7a5kwr75qc1tul4kf9Z","issued_at":0,"expires_at":0}
PR99_S06_RUNTIME_APPROVAL_V1 -->

准入核实原GitHub评论ID、PR99归属、真实作者id332398908/login/type、完整正文SHA、动作、准确外部root固定提交和脚本SHA、期限及max_attempts=1。旧R2#6217030577已消费，且动作不同，不能作为本批许可。

获许可后从准确提交下载脚本到新root0700目录，校验独审提供的脚本SHA，再用Python3.11 `-I -B -u runtime_contract.py --approval-id ID --approval-sha256 BODY_SHA --source-commit SOURCE_SHA --script-sha256 SCRIPT_SHA --confirm-independent-auditor`执行一次。不得在许可前运行本入口。

全验成功才输出`S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS`。该终态仅代表12份私有配置/元数据已接收，`production_deployed=false`、`complete_service_config_closure=false`。非API认证材料/环境文件、容器/VPN配置、root/admin调度及最后数据切换仍要明确后续边界；不能把此包当成完整生产恢复方案。API继续延后，不新设API或Shadow前置。

## 验证范围

新增19项合成测试：准确准入及旧许可/伪造作者/错误PR/脚本/提交/时间/确认拒绝，私有文件链接/硬链接/写权限/大小和独占保护，归档成员/类型/路径/逐字节校验，真实合成OpenSSL往返，manager漂移及失败现场保留，两个真实子进程竞争单次目录，真实SIGTERM保留，真实合成子进程SSH stderr持久化。只有测试临时目录、模拟manager/主机身份，没有生产登录、配置读取或服务动作。

Hosted真实CI、精确制品绑定及后续root实机结果分别记录。通过本批源码/CI也不自动构成生产执行许可。
