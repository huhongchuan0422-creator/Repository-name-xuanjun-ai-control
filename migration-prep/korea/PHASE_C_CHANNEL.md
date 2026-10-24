# 韩国 Phase-C 固定 Runner root 通道候选

本批只解决真实执行通道，不代表服务器已经迁移。Owner长期运维授权继续有效；每个具体生产动作仍按既有准确许可执行。

## 三层边界

1. Owner-root首先核对独立签发的通道安装许可正文完整SHA，并运行准确SHA的grant_phase_c_channel.py。
2. 安装器只新增固定dispatcher、清环境wrapper和两条无通配sudoers：githubrunner UID1001只能调用固定路径的inspect或install，不能传其他参数、脚本路径、命令、环境或stdin来源。安装后持久有效；不会安装C、启动服务、加载围栏或读凭据/数据库。
3. install只能对固定root私有路径中的冻结e9052b4e归档及root_handoff.py执行。归档SHA89826357…cc520，handoff SHA12bec6d2…3c35；root私有计划绝不从Runner checkout导入。原handoff再次校验安装许可、root锚点、当前GitHub正文和完整归档后，才导入并调用原安装器。缺许可或输入就拒绝，通道许可不能替代C安装许可。

固定入口 /usr/local/sbin/xuanjun-pr99-phase-c。
固定输入 /etc/xuanjun-pr99-release/phase-c-inputs/{root_handoff.py,review.tar.gz,install-plan.json}。
原安装准入仍是 /etc/xuanjun-pr99-release/phase-c-offline-install-admission.json。
公钥仍是 /etc/xuanjun-pr99-release/phase-c-public-inputs/{broker,source,authority}.pem。
通道永久尝试与回执 /var/lib/xuanjun-pr99-phase-c-channel-grant-v1。

inspect只检查固定输入的存在、root身份/模式，及三份明确PUBLIC KEY文件的实际hash；不读计划正文、root许可正文、任何PRIVATE KEY、凭据或数据库，不打印真实账号。
任何不安全父路径/软硬链接/可写输入/哈希漂移均失败。root本身是可信主体。原公共仓库Runner的全局准入风险没有被本通道自动解决；安全边界是root私有不可篡改输入、冻结字节及独立准确动作许可，不把workflow if当全局权限隔离。

## 通道安装许可合同

首尾marker是 PR99_PHASE_C_CHANNEL_GRANT_APPROVAL_V1。
准确JSON字段由grant_phase_c_channel.verify固定：
schema_version=1、decision=APPROVED_WITH_EXACT_PRECONDITIONS、action=PR99_KOREA_FIXED_PHASE_C_CHANNEL_GRANT_V1、
host=iZmj7a5kwr75qc1tul4kf9Z、max_attempts=1、approval_comment_id真实值、source_commit本批准确提交、
installer_sha256/dispatcher_sha256/wrapper_sha256/sudoers_sha256均为实际字节摘要、
runner=githubrunner、runner_uid=1001、issued_at/expires_at为整数，最长12小时。
arbitrary_root_commands_allowed、phase_c_install_allowed、service_actions_allowed、network_changes_allowed、credentials_allowed、database_export_allowed、writer_allowed均必须false。
phase_c_install_allowed=false约束本次通道安装过程；以后调用install仍需另一份原C精确安装许可。
Owner-root提供从独审取得的真实评论ID和全文SHA；安装器原始API读取两次并校验精确正文/PR99/动作/版本/hash/期限，副作用前拒绝缺失/旧/伪造批准。未获许可前不输出可直接运行的root安装命令。

安装器从不导入下载的dispatcher，先核其固定SHA再compile语法；候选sudoers先用visudo验证，原配置和安装后完整sudoers也验证。私有永久claim防重入/并发，原文件已存在就拒绝；部分失败保留新旧文件及记录，不自动覆盖、清理或回滚。失败后不得重跑。

## 后续运行与范围

通道申请仅覆盖grant安装和随后一次inspect取真实缺失输入状态；C安装仍NOT_AUTHORIZED。nft、观察与故障注入不在此sudoers中，必须在其准确执行方案/批准下另行绑定固定动作；不提前开放全权sudo或交易能力。东京继续运行。
新代码不修改冻结C runtime/制品、B17文件或185测试；在同一原PR99分支和既有Hosted job中只验证本批。原production inspection if:false维持不变，没有下发主机任务或新队列。

审核应一次覆盖安装器、dispatcher、wrapper/sudoers、原handoff调用及失败/并发/权限漂移，并核对9绑定/10常规条目。原C134及B185不重跑。新增测试中的主机、账号及visudo控制流为明确模型；Hosted另用真实visudo对临时sudoers做语法检查，不写Hosted系统sudoers。

完整服务器迁移仍需真实私有身份/源真值/传输、围栏/PID1、只读观察以及后续唯一Writer切换验收，不能通过授权通道跳过。

## C1/C2 准入整改（原审核6212980863）

C1：原始GitHub响应record.user必须同时为id整数332398908、login=huhongchuan0422-creator、type=User；不能使用正文自报作者、author_association或缺失user的回退。批准JSON新增auditor_role=INDEPENDENT_AUDITOR，并必须由Owner-root通过--confirm-independent-auditor明确登记该主体的独审身份；正文角色字符串本身不产生信任。两次API读回均验证实际作者，期间变更拒绝。通过后将GitHub ID/login/role、确认来源和准确源SHA持久保存在0600私有消费登记内。

这是实际GitHub账户身份加Owner-root从独立渠道取得的正文SHA和显式角色登记，不是独立审计人的密码学签名。同一GitHub账户被多个聊天入口共用时，GitHub元数据不能区分聊天窗口；Owner必须依据独立审核渠道取得准确正文SHA，不将开发方自报PASS当独审。这项限制不被隐藏。

C2：原安装器不能内嵌其自身新Git提交SHA（会造成自引用）。改为要求Owner-root的准确启动命令提供--expected-source-commit，值固定为本次复审的新提交、与下载URL一致；绝不从批准正文、分支HEAD或默认值推导。验证器将批准source_commit逐字等于此独立root固定值，旧28057fc1、其他合法40位及缺失固定值都拒绝。批准同时绑定新安装器实际字节SHA，旧许可不能批准修正版。最终Owner命令必须硬编码审核冻结的新SHA；不能使用从远端批准里提取出来的期望值。

仅安装器、相关测试与本合同/原开发文档改动。Dispatcher、wrapper、sudoers和冻结C runtime未变。新增6项回归合计22项，旧B185和C134不重跑。旧Owner暂存目录28057fc1保持不变；修正版尚未许可/执行。
