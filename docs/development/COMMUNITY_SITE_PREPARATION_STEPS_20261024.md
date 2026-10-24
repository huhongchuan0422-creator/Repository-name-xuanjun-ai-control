# b789 后原 UK 更新前准备：可执行候选与分阶段批准

这是源码候选，尚未根独审、未获任何现场写入授权，未在 UK 运行。Owner此前只读取证和
b789源码确认不授权本文件动作。默认无参数入口 exit2；不自发更新、不部署、不发现场命令。
新控制提交不是 f131 产品镜像源码。
原机须有既有 /usr/bin/python3（标准库及现成fd-based scandir能力；能力缺失HOLD，无pip/SDK安装），Docker与既有两个image；本包无新依赖。a932 controller、b789 HTTPS composition、111330B原载体
及固定 f131 镜像原字节复用。本文替代旧方案中“仍需私有 health 身份”的表述，验收仅真实Nginx
固定anonymous HTTPS单路径＋前后容器/镜像/路由/socket＋真实版本/时间；绝非独立双路。

## 1 固定对象和完整文件集

主机 iZd7oeikknn1z21sq6ji6zZ；原 root caller 仅作安装/控制，业务仍10001:1008。
当前已观察（05:26:43Z，不是未来新鲜准入）：
container818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c，
image sha256:0846f7cfc71d443095a6c5e3a59eabf5d2973eda90e29c831f335c163a2c8f32，
OCI2330dd55c07f58d7f45a7c4510a9761d0d4735d6。

新产品f13155ed63a3137d41766ee587d9b4b96a81477f / Tree
c31a9b1df006eeacd78ae3f9921073f3fe77d2c3；原 Run40059478387、artifact12546452389，
release image sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a。
outer57016858B/c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e；
inner57365044B/eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875；
OCI/stamp=f131、stamp0444、User10001:1008、11层根已核。
artifact有效至2026-10-27T03:44:30Z，过期停止；imageID不是archive/outerSHA/RepoDigest。
不下载新镜像、不build/pull/tag、不索凭据。已有精确加载镜像复用，不重复load。

所有绝对目标与文件SHA/bytes见同包 `site-preparation-manifest.json`，原载体逐文件精确SHA及
bytes见原 `control-oci2330-v1-manifest.json`，不维护第二套不同源码。拟路径：

| 路径 | owner/mode（规范，未观察为已安装） | 内容/影响 |
| --- | --- | --- |
| /opt/xuanjun-community-preview | 原已有root非组/其他可写父目录，不chmod现有父 | 不新建/替换父，不扫未知目录 |
| .../image-f131-40059478387 | 新root:root0700，存在须保护检查/冲突停 | 原授权运输接收公开脚本/载体和原镜像artifact |
| 上目录/community_preview_site_prepare.py、prepare-site.sh | root:root0600 | 本包精确源文件，只读输入 |
| 上目录/control-oci2330-v1.zip | root:root0600 | 111330B/aa8afb5c05240e3c4835680e8cec765fa4199f0b7f230e3adaced8bc489397f9 |
| 上目录/artifact12546452389.zip | root:root0600 | 原已审outer，不改名绕受限文件，不另建传输通道 |
| 上目录/community-backend-image.tar.gz、image-load-intent.json、image-load-observed.json | 新root:root0600 | 只有image-load阶段产生；intent后未知不重试 |
| .../site-prepare-v1.py | 新root:root0600 | 固定一次性准备caller；精确SHA验证，已存在只接受原字节 |
| .../site-prepare-approval.json | 原root独审生成、root:root0600 | 单阶段600秒运维许可，不能由脚本/HTTP自签 |
| .../writer-freeze-reference.json | root:root0600，原Owner真实证据 | 全writer冻结的审结引用；脚本不生成、不假定stop即证明 |
| .../control-oci2330-v1/{原manifest列8文件及所有子目录} | 文件root:root0600、目录root:root0700 | 原loader仅加载定义，原transport旧main/resume绝不调用 |
| .../update-journal | 新root:root0700 | 仅空父目录；安装不创建活跃attempt/审批，不清旧历史 |
| .../backup-2330-to-f131-v1 | 新root:root0700 | snapshot、restore-old、verify-f131、verify-downgrade隔离副本与私有manifest |
| 上目录/private-manifest.json、clone-results.json、未来backup-reference.json | root:root0600 | 文件集/密钥引用仅原主机保留，不打印/上传 |
| .../update-approval.json | 未来真实更新另批root:root0600 | 本准备不生成、不签发、不启用更新 |

上述 `...` 均严格指 /opt/xuanjun-community-preview，程序无可变路径参数/HTTP入口。
source数据仅 `/var/lib/xuanjun-community-preview/data` 和同根 `/config` **完整两树**，包含
原Center/objects/历史、业务SQLite及WAL/SHM、解密必要原key/config/原provider引用文件。
不按猜测DB名漏文件，不读未知根目录。超出这两根的配置引用不会扩扫/改写；隔离打开失败即
HOLD，需原负责人提供准确现有受保护文件在此两根内的证明；不复制新秘密到未知位置。
不改原挂载、用户、端口、账户、Nginx文件或P2，不碰旧stage/rollback记录。

## 2 可执行入口和许可文件（仅未来审批后执行，不是本轮命令）

已有正常运输由原负责人接收本包公开文件和既有原镜像artifact。若INPUT确缺，批准阶段A
仅新建上述单个root0700 INPUT目录，不用mkdir -p，不chmod/覆盖已存在目录；原BASE必须已
存在且受保护。接收文件root0600；先按manifest逐文件核SHA。禁止从受限附件换URL搬运。

`prepare-site.sh` 是原root准备caller的有界安装包装：固定UK/root、nofollow父链、保护模式、
原许可SHA/host/stage/时间/源码SHA均核后，仅install阶段允许EXCL安装固定ENTRY。已有ENTRY
必须同SHA；其他阶段不补装/覆盖ENTRY。再exec同一个 `/usr/bin/python3 -I -B -S` caller。
不是新部署通道/服务/权限授予。入口仍只调用既有loader/transport，测试不执行该包装现场部分。

每阶段由根审结实际范围后在原主机创建固定许可文件，严格字段如下，未知不填假值：
`format=1; host=固定UK; stage=本次唯一阶段; entry_sha256=manifest中的精确源码SHA;
issued_at/expires_at=真实整数时间、最多600秒; all_writers_frozen_evidence_sha256;
snapshot_manifest_sha256`。install/image-load两证据必须null；snapshot只freeze证据非空；
validate-clones只snapshot证据必填。bool不能充整数。引用是SHA，不是权限/credential；真正权限
来自root受保护文件和Owner本阶段具体授权。脚本不生成该许可或密钥。

以下是完整调用模板，**REVIEW_ONLY，不是已获准现场执行**；变量只能取根审结的该阶段
固定许可原字节SHA，无真实值就不执行，不能拿示例hash补：

```sh
# 已按本包manifest在既有原授权运输落固定INPUT；root事先逐文件核hash。
# PHASE只能为install / image-load / snapshot / validate-clones；一阶段一许可。
# PERMIT_SHA为Owner已具体批准且根已核的原主机固定许可64hex SHA。
/bin/sh /opt/xuanjun-community-preview/image-f131-40059478387/prepare-site.sh "$PHASE" "$PERMIT_SHA"
```

源码无参数只HOLD；CLI没有stop/start/update/恢复活动data选项。所有阶段锁固定ENTRY inode，
等待锁不阻塞（忙即HOLD），permit在锁后/复制阶段/每次clone前复核；不运行两个准备writer。
读写固定父/leaf O_NOFOLLOW，保护模式、nlink/类型/大小/前后identity与fsync；任一缺失、
空间不足、冲突、过期/未知保留部分文件停止，不删除、补造、覆盖或后台重试。
子进程stdout16KiB、stderr不输出、10/120秒硬预算、私有临时输出文件、RLIMIT_FSIZE/CORE、
kill/reap仅保证CLI子进程回收；**不证明Docker daemon中load或推理/clone容器已取消**。

## 3 阶段A：安装与镜像载入（与维护/更新分开批准）

一次批准清单：仅INPUT和ENTRY公开载体接收/安装、原8个载体文件和子目录、journal空父、
最多1次固定image load和两份本机加载记录；不停止现服务，不读取私有data/config正文。

1. install：验证原ZIP111330B及SHA、内部manifestSHA
   e780675ef48c4cd077000c943c5ffe57b390277b6246d43939f54590aabd199a，
   所有文件集/SHA/bytes/路径/mode。INSTALL及journal父任一已存在即停止，不覆盖旧状态。
   成功仅安装原载体/空journal父；不load模块执行更新，不生成update-approval/activeattempt。
2. image-load：核原outer/inner精确长度/摘要，已核digest固定全部11层/config/stamp原字节。
   只窄inspect固定releaseID的ID/OS/架构/User/OCI；精确已加载则reuse无load/无新tar写入。
   只有固定ID的精确NoSuchImage响应才判缺失；CLI错误/超时不是不存在，均HOLD。
   确缺才EXCL写准确tar和durable intent，单次原Docker socket image load，最后精确inspect
   及observed记录。无load结果/过时/不匹配不重试，不pull/build/tag/启动容器。
3. 磁盘：公开输入约58MB outer＋111330B载体，解包tar57365044B。仅对本地已审原artifact
   读取公开层metadata（不重建/不运行模型）得到：11个layer tar合计155941888B、7690个层条目、
   逻辑payload150394848B。daemon保守预留3×layer-tar+1GiB=1541567488B及30888inode；
   INPUT另预留2×inner+1GiB=1188471912B及192inode。实际磁盘/inode仍须现场真值，不预填PASS。
   image-load源码先只窄读原Docker info的DockerRootDir/Driver；仅classic overlay2受支持。
   只对该真实root及固定overlay2、image/overlay2、tmp目录做nofollow/root保护metadata与
   fstatvfs，不列目录/读Docker数据/Env。四目录必须同设备并各满足预算，读后info必须一致；
   containerd/未知driver/分离设备/空间不明全部HOLD，不能把DockerRootDir猜成/var/lib/docker。
   这项有限metadata属于未来A的明确范围，不是扫未知根；本轮未执行。安装自身需至少
   1GiB安全余量+2×载体及192inode。image load intent后不确定停止，不自动清理/重试。

## 4 阶段B：冻结、完整快照、真实隔离恢复/降级（单独维护批准）

一次批准清单必须包括：当前精确旧container/image/原两根、全writer排他冻结责任/实际方法、
最多一次旧服务stop及必要恢复start的**精确范围**、两根私有数据读/本机备份写、最多三个
固定隔离容器run及失败时仅这些probe的处置；所有secret仅原主机root保护保留，无输出上传。
源码本身不stop/start旧服务。未证全部writer冻结不执行snapshot，不能把测试lambda算证明。

1. 若Owner具体批准维护窗口，停止仅原已核ID的候选命令为
   `/usr/bin/docker --host unix:///var/run/docker.sock container stop --time 20 818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c`。
   这只是待审命令，不由本准备caller执行；执行前必须新鲜绑定原ID/image、原服务确为唯一writer。
   stop超时/被SIGKILL/结果未知不证明优雅关闭；不能跳过SQLite/WAL及全writer核实。
   维护恢复若另获同一具体批准，最多原ID `container start` 一次，先核无clone写活动data且无新
   正式writer，socket原状态；该start不是回滚健康PASS。实际更新仍不在B动作内。
   根依据实际进程/原宿主关闭事实完成writer排他审结，原root0600 freeze-reference必须含
   format1/host/精确old_id/old_image/roots两根/真实issued/expires最多600秒/
   all_writers_frozen=true/owner_review_reference_sha256。这是Owner真实冻结责任/审结引用，
   **不是程序独立证明无其他writer**。程序还通过已验loader加载原composition，真实
   inspect_bound复用完整旧ID/image/mount/isolation验证旧已停、socket确消失，复制前/后复核；
   不把仅停止HTTP或仅旧容器False当全部writer证明。无法证排他/仍在WAL写入即停止。
2. snapshot：两根预读计数/字节、预算检查，EXCL创建固定BACKUP/snapshot，完整流式复制，
   保留目录/文件owner/group/mode及原字节；拒link/hardlink/设备/跨设备子挂载/深度>32/
   非私有权限；最大20000项、4GiB/根、相对路径1024B、每根3MiB保守manifest预算，fd-based scandir有界枚举，单次遍历120秒，前后元数据/完整文件集/SHA一致。
   不排除key、Center、objects、WAL/SHM/lock。重新读回副本，原两根再比一致后才fsync发布
   私有manifest。失败保留部分私有副本，既存BACKUP不能复用/删除。源无变化才可继续。
3. validate-clones：从原private-manifest真SHA和全部文件集核只读snapshot。EXCL复制两个
   新根restore-old/verify-f131，分别用准确旧image/f131 **原PlatformHost.open→check_integrity
   →close**，不listen、不调用provider、不启用OCR/支付或创建身份。配置只读clone挂载，
   data仅clone可写；用户10001:1008、只读rootfs、network none、无宿主端口/socket挂载、
   capdropALL、nonewprivileges、384MiB/0.5CPU/64pids、tmpfs32MiB、pullnever。
   固定probe名 xuanjun-community-preview-{restore-old|verify-f131|verify-downgrade}-probe-f131。
   不挂活动data/config；原配置绝对引用由原挂载同路径保持，不重写密钥/账号/权限。
4. f131 clone关闭后，完整复制其实际结果至新verify-downgrade，再用旧image原宿主打开。
   对所有原DB integrity_check/FK、Center既有check_integrity（含对象解密/SHA/审计链）和
   全表逻辑行摘要三方严格相等；未知schema/新增迁移行/业务差异不放宽为只数行，HOLD根审。
   snapshot末次验证不变。只有实际三个容器完成和真实比对才有clone-results；本轮测试的
   Docker/语义结果为合成，不能当现场PASS。
5. 输出仅manifestSHA/总字节/结果摘要/时间，字段/secret/文件相对路径留root私有manifest。
   clone-results不自动签发backup-reference、不证明旧health或productionacceptance。
   根独验实际副本/逻辑结果及降级语义后才可另在该固定BACKUP创建root0600原backup-reference，
   供b789现有backup_reference(fd)绑定；不得把本计划/合成结果/HTTP200填成恢复证明。
6. 维护期间当前writer必须持续冻结；若为保留服务而重启旧容器，则本快照仅历史恢复演练，
   不是之后更新当前回退点。临近更新还须同窗口真实一致性快照/验证和600秒finalcurrent。
   本源码不会靠重新写tested_at把旧快照变新鲜；不拆碎现场重查、不现在刷新600秒。

空间/动作硬边界：快照最多两根各4GiB，snapshot+old+f131+downgrade四完整份；当前实现
预留至少7×实测两根总字节+1GiB、7×项数+128inode，另需daemon镜像层/overlay/tmpfs预算。
这不是已有现场容量值。最多3个隔离run --rm、各120秒CLI；超时不证明容器已停，先保留命名
容器/attempt，根在原批准边界内窄观察这些probe实际ID再决定停，不能盲重run/清理/启动旧writer。
源码不自动rm旧容器/数据、清journal、修权限、重建账户。Docker inspect内部可能读取Env，
Python仅固定白名单投影，不透传Env/secret；clone内部读config是此阶段另批敏感本机读取。

## 5 阶段C仍需单独批准：原更新与回退验收真实限制

现成执行路径仍为原rootloader.load(原manifestSHA)→b789.compose(真实approvalSHA,
真实backup_fd,execution_enabled=True)→原a932 Controller.run/特定KNOWN_FAILURE recover。
本包不调用、不修改控制器或此合同，不自动组装空审批，不把源码准备当可执行更新许可。

只有临近执行一次统一刷新same-attempt600秒current、五摘要、固定名称/socket/route、f131加载
状态、受保护新备份及新鲜许可，方能给Owner一份最终tuple/动作。真正更新才最多stop旧→rename
保留旧→run新；失败仅原有KNOWN_FAILURE串行恢复。UNKNOWN保留记录停，不重试/强行recover。

**旧2330响应无backend observed_at/runtimeSHA**。b789允许legacy rollback不要求新runtimeSHA，
但a932仍必须真实新鲜backend时间。现有旧HTTP200 READY不能成为rollback health PASS，
即使隔离数据兼容通过也不解除该限制。Owner须在更新前明确决定是否接受“失败后可能恢复
旧容器进程但验收保持HOLD、不能自动宣称ROLLED_BACK”的运营风险/维护方案，或先安排原范围
旧版本可审验收来源方案。不能伪造本地时间、放宽controller、临时修生产或冒Nginx私有头。

## 6 一次向Owner确认的精确范围（本轮不索现场批准）

A：公开载体固定路径安装＋至多单次固定f131load，所需根审结源码SHA/载体SHA/镜像摘要、
上述已证层空间上限与未来原Docker info指向目录的metadata/fstatvfs实际容量、现存路径冲突判断。无服务停启/私有正文读取；输入/staging与镜像占用、有限Docker存储metadata读取已明列。

B：在A已核后，具体维护窗口、唯一writer冻结证明、现服务至多一次stop/恢复start范围、
完整data/config仅原机保护备份、固定三个隔离clone验证及未知容器清理责任、真实容量预算。
无权限/credential/付款/OCR启用、无私有文件上传、无活动data恢复。

C：另给600秒same-attempt完整最终tuple后才批准实际更新；先处理旧rollback时间限制及备份
持续冻结/最终快照一致性。本轮没有C授权，不能把A/B许可扩成部署。

尚缺的是上述真实现场证据/具体授权，不是等待一个不存在的部署自行出现。可以审代码和准备
A，但没有私有备份实测、daemon实际容量及旧rollback验收决策时不能无条件一次更新。

## 7 266d 独审两项阻断修复（仍仅源码候选）

基线266d399404ef7db2e014a94dac1be93983827afe；原29项、路径/副本/比较及全部原pins保留。
根的容量阶段跨期和非timeout异常均为本地合成复现，不是UK事故。本次新增15项，合计44项。

许可仍来自原固定root保护文件/既有stage，没有新增权限或凭据。该文件及freeze引用须使用
原canonical编码 `json.dumps(value,sort_keys=True,separators=(',',':')).encode()`；原字节SHA、
字段/类型/stage/root/host/source约束不变。authorize在哈希、canonical和受保护读取后再次核
原ENTRY、许可原字节与权限，最后才取时；snapshot的冻结期限及image原artifact期限也保持。

原文件/目录primitive及私有树复制在紧邻创建、内容写入、元数据及fsync前复核，故容量查询、
最后space检查、tar写完、intent canonical序列化、intent落盘等耗时点跨期后，下一对应动作
不执行。tar/intent/load各自独立有界，先前在有效期内产生的部分文件保留，不删现场重试。
原load后核对及observed发布前的复核保留。薄bootstrap只同步同一ENTRY安装的临近复核及
精确源码SHA，不新增stage/输入/通道；默认关闭和A/B/C需另批均不变。

两处Popen从返回实例起立即进入try/finally；时钟、轮询、输出读取/解析、普通异常和中断
均进入同一finish_child。观察退出采用Linux原有waitid(WNOWAIT)，先不回收leader，使本次
PID/PGID在cleanup前不能被复用；核其仍为本次session leader，只向该group发SIGKILL，
无论信号/归属核对是否失败都尝试wait(timeout=2)。失去归属时不猜PID/不信号无关group。
清理失败一律CHILD_CLEANUP_UNKNOWN_NO_RETRY，不返回成功，不泄露底层异常正文。
spawn前失败没有已知child，不能猜processgroup。原输出/timeout/kill-reap预算保留，
没有循环清理/重试或新权限。既有Linux Python须支持waitid/WNOWAIT；能力缺失即清理后HOLD，
不安装/升级解释器。parent在Popen前复核，child在原资源限制设置后、exec前再核同一stage。

新增合成用例覆盖：capacity/space跨期、权限/许可/源码撤销、artifact期限、intent canonical
耗时、tar/intent完成后跨期、authorize自身读取跨期/权限变化、非canonical拒绝、输出临时文件
分配跨期零spawn；两种child的普通异常/BaseException、deadline异常、kill/wait/ownership错误、
成功路径清理失败拒绝、spawn失败不猜组。真实本地合成Python子进程证实回收，另一本窗口
自建无关Python子进程仍存活；不是Docker/UK执行或生产身份。原29项和新增15项实跑。

SIGKILL/wait只针对本次CLI原processgroup；Docker daemon中的load及clone不会因此保证取消。
若此前已经合法开始动作，后续跨期或清理失败仍保持UNKNOWN并保留intent/副本，不能声称
所有执行已停止/允许重试。旧2330无backend time、现场A/B/C未批准、OCR生产权限HOLD不变。
