# PR122 Owner真实保管链与新版入口准备

继承 #6227830181 已通过恢复机制，不改升级器、原Guard或冻结运行包。

新增脚本只支持 prepare。目标国内主机，真实Owner Root且非githubrunner提权；固定机制ZIP/TAR/Manifest/新升级器/运行ZIP及独审评论全文SHA。不得导入或执行升级器，更不写 /var/lib 原通道、UPGRADE_TRUST、sudoers、服务或网站。

## 准确许可与一次占用

现场执行前必须另行签发 XUANJUN_PR122_OWNER_CUSTODY_PREPARE，决定 OWNER_CUSTODY_PREPARE_APPROVED。JSON绑定 attempt_id=pr122-owner-channel-custody-20261017、host、新入口launcher_sha256、review_zip_sha256、helper_sha256、audit_comment_id=6227830181、audit_body_sha256、max_attempts=1、channel_write_allowed=false、apply_allowed=false、issued_unix/expires_unix（最多2小时）。代码核对真实GitHub评论全文SHA和自身准确字节。

独占创建 /root/pr122-owner-channel-custody-20261017 消费本次准备；保存批准、审核原文、实际UTC/Root UID及输入身份。不覆盖、不清理、不重试。输入从非Root持久路径 /home/githubrunner/pr122-owner-inputs/channel-custody-20261017/REVIEW.zip 读取，准确SHA后才解析；由Owner另行按准确入口SHA核验后启动，旧Guard及已消费许可不能复用。

## Owner实际声明与证据

必须从 /dev/tty 交互取得Owner本人保管主体、源码作者主体、真实独立审核主体、其原始证据SHA以及明确确认短语。相同作者/审核主体、没有有效证据SHA、普通管道或未明确确认均拒绝。

不能由开发作者替Owner输入。必须由Owner实际看过原审核窗口及其核查工作，核对独审评论原文，才能声明主体独立。外部证据应是实际原审核窗口/独立签发记录，须保存在Owner保护范围；不能编造SHA或把自报角色字符串当证明。入口不声称仅凭声明或一个SHA就能数学证明独立性。

生成 OWNER_CUSTODY.json 明确标识为 OWNER_PROTECTED_TTY_STATEMENT_NOT_CRYPTOGRAPHIC_INDEPENDENCE_PROOF。目录Root0700、文件Root0400；实际声明与原证据只私有保存，公开receipt仅含非秘密哈希、权限、UTC/UID/主机及执行状态，不公开主体原文或凭据。

prepare成功仍是 CUSTODY_PREPARED_AWAIT_INDEPENDENT_ACCEPTANCE，不是独审保管链PASS。随后由独立审核方核查实际声明来源、独立主体证据、准确评论、文件元数据与一次占用回执；有条件可通过受保护渠道读取私有证据，不能将开发方合成测试写成现场事实。

## 输出与后续边界

保存新 approved-upgrade.py（SHA832900dd...）和原运行ZIP供后续准确执行；不覆盖旧 /root/pr122-customer-channel-upgrade-inputs。写UPGRADE_TRUST与REBIND必须另外被准确许可包含，且由Owner受保护流程登记，不能由本prepare预先生效。后续使用本次实际custody文件SHA绑定安装信任锚及新单次REBIND批准，执行入口须再次审核绑定；prepare没有授权升级或签发安装权。

## 验证

13个Root私有夹具测试：真实包完整解析而不执行、实际Root文件权限、一次占用、TTY限制、同主体拒绝、缺少原始证据/确认拒绝、过期/编辑/范围扩大/换入口、Runner身份、符号链接、持久化失败不覆盖。Hosted fixture声明不是真Owner声明。国内尚未执行，保管链仍NOT_VERIFIED。

本地环境不支持chown至UID1002，相关完整测试交由Hosted真实Root执行，不跳过也不改生产UID检查。非Root暂存传输会在准确许可签发后先完成并跨任务验字节，再给Owner短启动命令，避免再次粘贴数百行。

## 真实TTY补测修正

原 open(/dev/tty,r+) 在真实非seekable终端触发 UnsupportedOperation，先前模拟TTY未覆盖。改为原始FileIO加TextIOWrapper，保持同一TTY确认规则、Owner身份、权限及全部准入边界。新增真实os.openpty双向读写回归，显式复现旧打开方式失败、新方式成功。未执行国内prepare，旧许可不能用于新源码SHA，须替代准确批准。
