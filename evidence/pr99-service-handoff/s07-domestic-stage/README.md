# S07 国内私有代码和依赖安装事务

执行依据：Owner明确直接迁移授权PR99 #6219362469。不复用已消费的S06/R2许可，不声称新的独立生产验收PASS。此批在韩国发起，使用Owner终端输入国内root密码，严格绑定经国内Runner读取的ECDSA主机公钥。未授权任意Runner root shell，不修改旧Phase-C固定通道。

## 准确执行范围

1. 本地只读加载已获审resolver准确字节10d24ddfea39347930115a4dc57e81b0b41461c10bd71e70b7f7d15afeb3fea4及其原来固定的辅助函数；不调用任何旧采集main。核对S06和R2已接受回执、R2原1363源码聚合及每份实际源码hash。
2. 按Owner于2026-10-17 00:01真实解析报告的三个入口闭包摘要，选取Portal、企业微信客户联系、企业微信客服的静态源码并集。Portal必须是R4生产遏制版本57e38fc9...；包中不含数据库、EnvironmentFiles、unit原件、SSH/TLS密钥或私有凭据文件。源码可能有内联私有信息，保持私有，不证明其绝不存在。
3. 私有源码仅在韩国/root新目录和SSH加密链路中流转，参数不携带密码或源码内容。国内root接收前检查主机/Python3.11、准确包hash、三个入口摘要、R4代码hash、纯.py安全相对路径/字节限额和新目录均不存在。登录失败不会先占用韩国固定安装尝试目录。
4. 只创建国内`/opt/xuanjun-migration-s07`和`/var/lib/xuanjun-pr99-s07-stage-v1`两个新root0700前缀。源码root0400。不得覆盖任何既有路径、账户、unit、配置或current。只安装独立venv和三个静态依赖cryptography50.0.1、requests2.34.2、SQLAlchemy2.0.54；与韩国既有已验收环境元数据核对准确版本。网络仅用于官方PyPI二进制wheel及其依赖，不访问业务API。
5. pip check、三个第三方包导入及版本核对；不import应用源码。重算安装源码hash，并前后对照现有Nginx、国内桥接、Work预览及三个既有后台unit属性、Work current和首页摘要。变化时保留新目录并HOLD，不覆盖历史、自动回滚、清理或重试。
6. 实际成功终态为`DOMESTIC_S07_PRIVATE_CODE_AND_ENV_INSTALLED_PASS`。这证明私有代码和依赖真正安装到国内，不代表systemd服务或生产业务已启动。此工具没有useradd、unit创建、daemon-reload、服务动作、反代切换或数据库/凭据迁移功能。

## 后续真实切换还需哪些材料

静态源码的两处动态加载、运行数据/配置和账号身份尚未由AST证明。不能把空运行目录当成旧业务状态恢复。后续应基于实际unit和私有业务合同接续运行材料、生成准确启停/反代/回滚事务并验收，之后才算S07完成。旧小说入口`/opt/xuanjun-novel-wecom/wecom_novel_ingress.py`、VPN守卫`/usr/local/sbin/xj-tokyo-vpn-guard`未在R2源码中，S08不能以本批代替。

当前三条SSH关系已有Owner实证：国内19444反向到东京20443；韩国19444反向到东京20443并将韩国18760转到东京18761；东京19443转到国内18443。目标已有端口和生产隧道不改。解析器的proxy_configuration_present也会因-F配置出现，不能单凭该布尔值宣称存在有效ProxyJump或认证等价。

## 测试与证据限制

新增10项安装机制测试覆盖包/成员hash、R4准入、错依赖/角色、路径穿越、真实私有文件创建及权限、已有文件/软链不覆盖、部分失败保留、共享状态漂移HOLD和禁止重入。依赖安装与systemd/网站状态在测试中使用合成模型；不冒充真实国内pip/root安装验收，不运行应用、API或数据库。原S06/R2及历史测试不重跑。

国内真实预检Run38929243716/Job117068662907，UID1002：Python3.11.6、x86_64、目标前缀ABSENT、约14GB可用，SSH公钥由本机root所有公开.pub读取。此非root证据不等于后续root安装权限；Owner终端SSH再验证root及固定主机。安装期间每15秒给进度，私有日志保留。任何未知结果保留现场，禁止把可重建的候选当成生产切换成功。东京继续运行，不操作Finance、Writer、API重建、UK/P2或韩国MoreLogin。
