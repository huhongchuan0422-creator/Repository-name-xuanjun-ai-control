# 人工实施顺序与逐阶段准入

所有阶段目前均未在本轮执行。只有Owner决定采用人工、原授权明确适用时，才由唯一执行人使用自己正常获准入口实施；本包不要求重登受保护浏览器或建立新通道。

|阶段|固定输入/操作边界|进入条件和验收|当前|
|---|---|---|---|
|G0 决定/绑定|0177d391、原主机、执行身份、范围、唯一Attempt、适用UTC窗口和受控次数；记录原成功/失败检查点|Owner决定采用；核原独审和适用授权，不能把本包当许可|未决定/未执行|
|G1 包来源|沿已核/usr/bin/python3.11，有限查询其SourceRPM/签名摘要和实际_ssl/_sqlite3所属库包；对照官方厂商补丁记录|不读密钥，不扫目录；关联不明或补丁要求不符HOLD对应环境，不自行升级|待有限只读证据|
|G2 依赖/源码保管|新准确release的30成员，独立venv-py3116；新精确18包锁及每轮子SHA；使用原官方包渠道|先核当前目标不存在或原事务归属，禁止覆盖未知stage；依赖逐SHA、pip check通过；获取失败保留原调用/下载文件，不换镜像或盲重试|准确源码/锁已齐，轮子实物未含|
|G3 身份/配置/状态|同一xuanjun_oauth authority身份；准确配置与四用途秘密分离；原批准数据库路径|先定父链/文件权限：服务可读，非授权人不可读，root-owned源码不可写。root0700暂存目录不能直接当作非root可读配置。确认首次初始化来源或已有DB历史；仅显式已审initialize_new_database可用于获准的全新库|身份/配置/权限/状态需绑定|
|G4 导入/沙箱/启动|同一xuanjun-cloud-oauth.service；独立解释器候选unit只改ExecStart；当前精确source Manifest/配置SHA|先隔离venv导入及pip check；再以同一实际服务身份验证私有文件可读/受禁路径不可读；保留所有硬化。正常unit启动只监听127.0.0.1:18770，实际退出码/状态/版本可查|未执行，不创建临时unit来假验收|
|G5 HTTPS/出口|原已签证书/pre-egress准确候选；仅新域所属改动；一次nonce/UTC/真实peer取证及撤除|先准入准确日志路径/时间及既有Nginx配置备份；测试后受控reload。英国请求禁代理/CA验证/5秒/无认证/body且不自动重试；收集后撤除并验证。歧义、UNKNOWN或撤除失败保持introspect403|源码隔离测试已过，现场未执行|
|G6 resource/新平台|英国成功安装复用；真实resource/audience/subjects/client绑定；新App+独立隧道，旧连接不动|正常登记产生真实值回填；平台不支持静态client则停，不自加DCR/CIMD；初始catalog=[]，无业务Writer|配置/登记未齐|
|G7 真实OAuth验收|Owner正常同意；授权码+S256、真实身份、过期/错主体、刷新轮换/撤销、重启恢复|逐项实测回执；示例/Hosted不能充实机。真实subject从验证链取得，参数/_meta不能自证|未执行|
|G8 各业务分别|各自原项目catalog/双端根/操作/预算/事务准入|UK认证合格后B5按原完整选择，不拆预算；国内/韩国各自在自身条件齐时验收，不等待三机齐备|原门禁不变|

## 配置与首次初始化的准确来源
- source/deployment/cloud-connection/oauth/authority.example.json、resource.example.json只供字段模式参考，包含null/空clients并enabled=false，禁止直接改enabled后上线。
- authority需要settings恰为issuer/audience/github_client_id/clients/subjects；client条目恰为redirect_uris/auth_method/secret_hash/resource_client；用户主体仅原两GitHub数字ID对应主体。
- authority非root专用身份；resource按原受保护读取身份。四用途秘密分别为session、GitHub App、introspection、平台隧道，不交叉复用，不进命令/URL/日志/本包。
- source/production/cloud_connection/oauth_authority.py的initialize_new_database是显式初始化函数，create_app不创建库；source/production/cloud_connection/oauth_entrypoint.py只mode=rw连接原状态。必须先解决首次/已有历史来源，不临时另写schema/建空库。
- 新source按Manifest独立release绑定，run.py会检查root属主/父链/内容SHA。不能只复制新增unit而漏其完整source闭包，也不覆盖英国原release。
- 原/etc/xuanjun-cloud-oauth root0700是既有staging事实。如何只为authority身份提供配置读取而不扩大他人权限，须有准确所有权/父链访问方案及适用授权；不提供盲目chmod/chown命令。该项为部署输入，不是重开源码独审。

## unit与回退
选用xuanjun-cloud-oauth-py3116.service.candidate的内容，但目标仍原xuanjun-cloud-oauth.service；不得同时创建第二份并运行。EnvironmentFile中的两个SHA应来自本次实际配置及Manifest，不能填测试值。实际unit/env/current/config均需记录SHA/归属，HostPins未知不猜。
