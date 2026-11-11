# PR99 当前离线恢复点单批执行候选

本批是当前源码与单个SQLite数据库的私有恢复点，不是交易上线或全服务器切换。API继续延后重建。原历史归档、密钥、恢复目录、独立环境、B/C、官网与现有通道均保留。

## 唯一动作

`PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1`，韩国Owner-root启动一次，既有严格校验的SSH连接到东京root；不增加密钥或sudo权限。

1. 韩国验证独审GitHub评论真实ID/作者ID332398908/login/type/PR99、完整正文SHA、准确源码提交、BINDING字节SHA、有效期及max_attempts=1。Owner必须从独审渠道另取正文SHA并明确确认独审来源。同一GitHub账号不等于密码学独审签名。
2. 创建专用独占目录，保留公开批准原文作为私有准入记录；任何失败不得自动重试、清理或复用旧许可。SSH认证失败也保留尝试目录，后续先检查现场。
3. 东京新目录`/root/pr99-current-point-v1`按冻结服务器清单逐文件复制1363份代码/依赖文件，逐次核验路径、文件类型、所有者、链接、字节和SHA。文件集变化或源码漂移立即停止，不使用GitHub源码覆盖服务器。
4. 固定权威库`/opt/trading-system/database/data/trading.db`，dev64771/inode1601016/UID1000；SQLite只读连接、WAL-aware backup生成新闭合副本。只对副本设置DELETE journal并做完整性检查，不checkpoint/修改活库、不查询或输出业务行、不做交易所对账。
5. 再验源码；打包新私有源码及DB副本；新随机恢复密钥0600，以AES-256-CBC/PBKDF2-200000/SHA256加密。源副本、完整私有明文tar、密文、密钥和日志保留在新0700目录，避免与此前“不保存历史完整明文归档”的结果混淆。
6. 韩国新目录`/root/pr99-current-point-received-v1`通过现有SSH复制密文、私有密钥和脱敏回执；验证密文SHA/大小、解密tar SHA、准确成员和逐文件SHA、闭合副本完整性。仅写新私有目录，不部署到生产路径。
7. 保存`final-receipt.json`，准确标记恢复时段、非全树原子、未停Writer、未对账、不是final trading checkpoint。传输期间源端可继续变化；本批结果不是保证停机时的最后状态，正式数据切换仍须最终增量和独立放行。

## 必须签发的批准合同

审核方核验本次准确包后另发真实评论；不得以此模板或开发方PASS代替许可。正文仅含一个以下机器段，epoch必须为实际签发/到期时间、最长12小时。所有占位符必须换成真实值：

```text
<!-- PR99_CURRENT_POINT_APPROVAL_V1
{"decision":"APPROVED_WITH_EXACT_PRECONDITIONS","action":"PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1","max_attempts":1,"source_commit":"<本批准确40位提交>","binding_sha256":"<BINDING.json的SHA256>","source_manifest_sha256":"7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de","source_host":"iZ6wee8q9z4t03hvqumwfhZ","target_host":"iZmj7a5kwr75qc1tul4kf9Z","issued_at":0,"expires_at":0}
PR99_CURRENT_POINT_APPROVAL_V1 -->
```

批准仅覆盖上述源码/整个固定SQLite恢复副本的私有复制和验证，不授权业务行导出到GitHub、API凭据读取/部署、活库写入、服务/防火墙/隧道变更、Finance、C安装、真实GET、Writer切换或东京退役。数据库作为不透明私有恢复资产处理，不能宣称其内部不含敏感信息。

## 准入后唯一启动形式

在韩国root取得经SHA验证的完整包，私有0700目录、文件root且不可组/他人写；使用Python3.11 `-I -B -u`运行`run_current_point.py`，参数必须来自独审真实许可：`--approval-id`、`--approval-sha256`、`--binding-sha256`、`--source-commit`、`--confirm-independent-auditor`。没有真实许可时不提供可直接复制执行的生产命令。

## 限额与失败

源码总量≤512MiB、每文件≤64MiB；DB≤512MiB；两端要求至少1.5GiB空闲。backup90秒、完整性检查60秒、东京总准备300秒、SSH单次传输1800秒。数据流分块，避免韩国2GiB主机一次读入完整数据库。普通只读SQLite/WAL访问可能涉及SQLite正常共享内存读者协调，不能把它描述为完全零文件系统活动；业务写入和活库checkpoint未调用。

若超时/部分成功，保留两端所有现场，检查新失败回执和SSH工作状态；禁止重新运行本包、删锁或直接覆盖。生产服务不被本包停止，因此不需要用恢复旧漏洞源码作为回滚。新私有文件保留不影响原服务。

## 验证边界

新增本地合成测试覆盖WAL提交/未提交、并发Writer、超时、错误库身份、损坏库、路径/链接/重复项、来源漂移、加解密及目标逐文件验算、假作者/错误版本/过期批准。它们不证明真实SSH/root/磁盘/私有DB执行通过；这部分需准入后实机回执。原185/134及已通过备份环境验收不重复。

## 后续通道接续

本包不切换Portal、RPC/模型隧道、WeCom/小说入口或VPN。东京已识别这些职责；迁移目标、双端配置、端口冲突、逐项切换/回滚、调用方验证需单独形成实际接续批。四项Finance/Billing timer继续保留；root/admin cron仍UNKNOWN。本批成功也不能关闭东京。
