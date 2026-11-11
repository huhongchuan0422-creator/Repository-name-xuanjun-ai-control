# PR99 当前离线恢复点 R2：保留首次现场的准确增量修正

原候选c6ba6ac8、许可#6216441589已尝试一次并停止，不得重跑或删除旧现场。R2需新的准确源码/BINDING/单次许可。操作仍限PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1，不授权服务、API、Finance、DNS、Writer或东京退役。

## 实机证据及原因边界

Owner韩国root失败SHA256：44f232571ce267f6a5cf9c801b1fba366fd9fa8f4a82d01aa592c249592bd35d。
Owner东京root失败SHA256：9c23719696b63b0ca4552eb67ffd99948a62c9cec9af0a4774e4890f8a21565b；SOURCE_FILE_SET_DRIFT。
东京当次有prepare.started，receipt.json、payload/database/trading.db、payload.enc均不存在。证据来自Owner终端，不冒充本窗口直接root登录。

Run38909367025 / Job117001011398（东京UID1001）实际比较：冻结1363、当前可见1363、新增0、缺失0；带onerror扫描发现五个PermissionError历史备份子树。原非root采样未设置onerror，遗漏了遍历错误；root采集可进入这些子树，存在枚举口径差异。尚未取得root全部新增路径，不声称逐路径证明了root全部差异。R2必须在准确排除后仍匹配原1363文件集，否则继续HOLD。

## 不改变已获审输入

source-identities.json原字节SHA256：4114048fe0ecf17ed5e4185b0bbc37d114ed485a2340f8cce2418817cc6ae941。
选定1363文件，19,350,718字节，聚合7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de。

原清单本就含436份backup/历史源码副本。本次不删除这些已批准文件，只排除原来未枚举到的五个准确子树；不把选定集声称全为当前应用或整个服务器源码闭包。全部仅写私有恢复目录，不部署历史Portal或旧入口。

## 完整增量

1. EXCLUDED_SUBTREES硬编码五个准确历史相对目录，遍历前排除，不排除整个backup，不扩大复制范围；其余新增/缺失/内容/权限/链接/变化仍拒绝。
2. 其他os.walk错误立即HOLD，不再静默称完整。
3. 全新源/root/pr99-current-point-v2、目标/root/pr99-current-point-received-v2，独占0700。旧v1不改名、不chmod、不删除、不覆盖。新尝试仍失败停留、禁止重试。
4. 新写入前校验韩国旧私有目录、失败SHA、旧传输进度未出现。东京新目录前校验旧失败SHA、原collector与source-identities SHA，以及旧receipt/数据库副本/密文/密钥未出现；任何变化即停。这是新精确准入，不是无条件resume。
5. SSH每步stderr写韩国独占0600私有日志，退出码纳入失败原因，不再丢弃诊断。原始日志不公开。

原SQLite WAL-aware备份、副本DELETE journal和完整性检查、权威DB dev64771/inode1601016/UID1000、加密、SSH主机键、接收逐文件验证、API/服务禁令继承原审。只读源不checkpoint，不查询或输出业务行，不冻结Writer，不宣称final checkpoint。SQLite普通读者协调不声称零文件系统活动。源和目标私有明文副本/tar、密文、恢复密钥与日志按原合同留存，密钥不公开。

## 新许可机器合同

仍使用原PR99_CURRENT_POINT_APPROVAL_V1 marker。独审必须以真实值替换占位符，模板不是许可：

<!-- PR99_CURRENT_POINT_APPROVAL_V1
{"decision":"APPROVED_WITH_EXACT_PRECONDITIONS","action":"PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1","max_attempts":1,"source_commit":"<R2准确提交>","binding_sha256":"<R2 BINDING SHA256>","source_manifest_sha256":"7e9859b04806aba717cbd7414d2aff52c041d810c78d5be902168898ae8300de","source_host":"iZ6wee8q9z4t03hvqumwfhZ","target_host":"iZmj7a5kwr75qc1tul4kf9Z","issued_at":0,"expires_at":0}
PR99_CURRENT_POINT_APPROVAL_V1 -->

批准正文应关联旧许可6216441589和两端旧失败SHA，限准确五子树排除、错误日志修正和新v2私有目录一次执行，最长12小时。Owner-root须从独审渠道取得完整正文SHA并显式确认。真实GitHub作者ID/login/type、PR99、准确源码/新BINDING、时效、max_attempts验证保留；同账号评论不当作密码学独审签名。

## 执行与验收

新许可后韩国Owner-root用Python3.11 -I -B -u运行本包run_current_point.py一次，输入新ID、正文SHA、新提交、新BINDING和独审确认；密码仅终端输入。代码先验旧现场，再建新目录并采集。原许可不能用于此版本。

限额沿原批：源码512MiB、单文件64MiB、DB512MiB，两端空闲至少1.5GiB；backup90秒、完整性60秒、准备300秒、单次传输1800秒。DB分块接收，适应韩国2GiB。全验通过才报CURRENT_OFFLINE_POINT_RECEIVED_PASS；失败/超时/未知保留现场，不重试/清理/自动回滚。

## 新测试与继承

新增RecoveryR2七项：五子树准确排除且保留其他backup；其他新增文件拒绝；遍历错误拒绝；旧失败SHA及原件保护；矛盾旧传输进度拒绝；真实合成子进程stderr私有保留及独占；远端旧失败校验先于新目录且旧原件不变。

原20项及B/C/历史验收继承。备份、加解密、接收和准入等未改函数以源码段一致性核验，不重跑未变套件。合成fixture不写成真实双端root验收。服务接续、最终增量、单Writer与东京退役继续未完成。
