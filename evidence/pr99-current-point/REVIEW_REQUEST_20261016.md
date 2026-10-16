# PR99 当前离线恢复点执行包送审材料（2026-10-16）

准确候选提交：c6ba6ac88d9d1eab1e2731a7fe9b3aa10afe320d。原PR99原分支继续，Draft不合并。继承#6215371855历史离线/环境验收和此前B/C，无重做。

本次交付实际可执行的韩国root协调器、东京只读WAL-aware备份/打包/目标校验模块、1363份当前服务器文件身份和20项新合成测试。不是只提交下一步计划，也不是生产执行回执。

## 真实新增验证

- 本地20/20 PASS；Hosted Python3.11.17原始Run38902948852 / Job116979411354：20/20 PASS，0SKIP，准确checkout上述提交。已读原始日志。
- 制品Artifact12046927098，ZIP60729字节；GitHub upload摘要与原始日志一致：715178c10fa783768cfc816033f9f0079fed09d33777c554809f16f71913f011。本窗口没有独立下载ZIP，不冒充独立审核。
- 内层TAR60130字节，SHA256：41f3c224cbed1d864104bc206d92a32339372a9d0ecfa9108a2da0123803db70。本地实际构建字节与CI原始摘要完全一致；5份绑定文件+1份BINDING，6个常规成员。
- BINDING.json SHA256：1785c311ab9eb0b5e88c43dbb2bb3da8dce3a519635d6ca7b0e2ad9a68161fa1。
- 本次所有生产Runner作业SKIPPED。原检查Run38902955010仅Hosted范围判定通过，原通道22/C134和原制品构建均SKIPPED，无重复历史测试或主机操作。

## 准确执行面

请审准确包中README合同、current_point.py、run_current_point.py及测试。只申请一次PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1：当前服务器1363份代码、固定SQLite在线backup恢复点、新私有加密包和韩国逐文件/DB完整性验算。不申请完整服务器迁移PASS。

许可须绑定两台固定主机、上述准确源码与BINDING摘要、当前服务器清单聚合7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de，真实签发/到期时刻（最长12小时）、max_attempts=1。GitHub作者身份+Owner-root从独审另取全文SHA并显式确认；不得把开发方评论当许可。审批机器段模板在README，禁止使用占位模板执行。

源目录/root/pr99-current-point-v1与目标/root/pr99-current-point-received-v1均专用新0700，不覆盖历史恢复、B/current、官网或现有配置。活库mode=ro，不immutable；只对新副本DELETE journal/integrity_check。采集时段写回执，明确非停Writer、非全树原子、非交易所对账或final checkpoint。正常SQLite共享内存读者协调不能描述成绝对零文件系统活动。

源私有明文副本/完整tar、密文、随机恢复密钥及日志按合同留存，目标密钥0600且不输出值；SSH主机键严格固定，root密码仅终端输入，不能写入GitHub/日志/参数。不增加SSH密钥、sudo或root通道动作。

任一步失败保留现场，不重试/清理/自动回滚。总准备300秒、backup90秒、copy1800秒等限制见合同。两端至少1.5GiB空闲；接收DB按1MiB分块，避免2GiB韩国主机整库读入内存。

## 不在本批内

真实交易/API/Writer、C安装、凭据配置、活库写入/checkpoint、服务/隧道/防火墙/DNS变更、Finance/Billing和东京退役均不申请。旧API延后。Portal/RPC/客服/小说/VPN尚需实际接续；root/admin cron仍UNKNOWN。任何本批成功都不能说明这些职责已迁走。

请一次集中给出新增执行包缺陷，或在准确制品字节复核通过后直接签发上述限定单次许可。不重审已通过历史范围、不仅再转交申请。
