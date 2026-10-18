# 服务器迁移完成进度

最新实机成果：2026-10-19 00:47:54 Asia/Shanghai，国内专用账户及三个停止候选服务单元已安装。**正式生产服务尚未启动，入口尚未切换，迁移未完成。Owner已取消独审/许可等待，剩余是执行方的技术接线与数据验收。** 以下较早章节保留历史，本节及末尾00:56更新为当前状态。

## 已完成的实机准备

| 项目 | 准确结果 |
|---|---|
| 四机RAM通道 | 2026-10-18当前STS/SWAS root只读4/4真实成功；run39124426535/job117666481531。Writer/Fence仍UNKNOWN；无需重配RAM或提供密码 |
| 恢复点与材料 | 原R2及165文件初步副本继承；不是最终切换快照 |
| 三应用v4隔离 | 3项HTTP200，临时进程已全停；run38992581089 |
| 国内版本源码 | 124文件实际落盘核验；run39001447378/job117305049170；Invoke t-sh070a0uibttwqo |
| 国内私有运行副本 | 2906文件、114962378字节、4链接核验；run39002237032/job117307415381；Invoke t-sh070a1ykb562o0；protected未变 |
| 原/目标环境对照 | run39002596266/job117308483429；东京3服务active、国内同名unit not-found；所选4源码环境引用及当前进程选定变量采样完成，不能据此宣称全部有效配置/鉴权完成 |

## 剩余6个节点

| 节点 | 当前状态与结束条件 |
|---|---|
| 1 运行配置与依赖 | 进行中。已定位东京客户端硬编码19443→国内18443并在新r2仅修正两处；补齐持久身份、系统库/写目录、有效环境及真实桥接认证 |
| 2 受控安装与回滚 | 三个停止/禁网候选unit已实机安装（run39146617633），专用账户已创建；正式Owner启动入口新增并通过双Python各17项测试，尚未实机激活，最终数据接线未完成 |
| 3 真实链路验收 | 待完成。r2两轮三应用HTTP200、两个正确回调路径每轮无效请求403、停止与监听清理均通过（run39004155870）；仍缺真实签名成功、上游及生产验收 |
| 4 最终数据与单Writer | 未执行。165文件数据为初步副本；必须最终快照、唯一写入者及对账 |
| 5 入口切换 | 未执行。保留现网站/current、桥接、winctl及原东京入口；切换及恢复须准确事务 |
| 6 东京退役 | HOLD。模型20443与反向19444仍依赖东京，英国替代执行端由原P2负责；四财务timer、VPN/Cloudflare职责需明确接续或取消后方可退役 |

## 当前执行与衔接

新复制品重启/清理批：准确提交b9d8b3739e66f77602a1ec0c7bc9908b10dcdb51；run39003075282/job117309891067 SUCCESS。两轮均三应用HTTP200、全部临时进程及监听已清理；错误请求404不算鉴权PASS。该批已结束，没有常驻后台迁移writer。本表不声称常驻后台迁移执行器已安装。

进度通知已取消提交更新触发，保留原PR99评论及审核事件，避免每次自身提交插入只读通知。通知不取得迁移writer权限。已消费v4、源码落盘、运行副本组装均禁止重放。

[国内实际落盘回执](../../evidence/pr99-service-handoff/s09-install-candidate/DOMESTIC_STAGE_RECEIPT_20261017.json)

权威状态：plans/PR99_PHASE_C_STATE_20261016.json；详细账本：plans/PR99_SERVICE_HANDOFF_EXECUTION_LEDGER_20261016.md。

## 2026-10-17 12:52 CST 实际续接成果

- r2源码124份落盘，122份保持r1字节，两份仅改桥接端口19443→18443；run39004046272/job117312742713，Invoke t-sh070a4jun5nfnk。
- r2私有运行副本2906文件/114962378字节/4链接；run39004107195/job117312919573，Invoke t-sh070a4mwpu2oe8。仍是初步数据，不是最终快照。
- r2新隔离批run39004155870/job117313065796，Invoke t-sh070a4pjzs5dkw：两轮三应用健康200；正确两个回调路径无效请求均403；临时应用全停、监听全消失、protected未变。403不等于签名成功/真实上游认证PASS。
- 停止/禁网候选安装及冲突安全回滚代码已实现；准确r2源码run39004183744/job117313146649九项测试通过，尚未实机安装，且不提供生产启动/切换入口。

旧12:21、r1复制品回执保留为历史。当前上述实机批均已结束，没有后台生产迁移writer，剩余仍为6个大节点。无需Owner重新授权、提供密码或复制代码。下一执行条件是原独审对准确停止安装事务及主机准入的决定；持久身份、完整运行配置、最终数据/单Writer和生产激活仍须完成。

[本轮真实回执](../../evidence/pr99-service-handoff/s09-install-candidate/R2_EXECUTION_RECEIPT_20261017.json)；[准确事务与测试包](../../evidence/pr99-service-handoff/s09-install-candidate/STOPPED_TRANSACTION_REVIEW.md)。


## 2026-10-17 13:16 CST — 执行入口与生产启动源码增量（未生产部署）

- 已实证当前原生GitHub工具可以通过Owner标签触发受保护PR工作流，纠正此前“没有任何可触发入口”的过度结论。入口只接收Owner332398908、PR99固定分支、准确HEAD标签，不由普通push执行Root；只限国内停止安装，不等于任意生产执行通道。
- 真实run39005472107/job117316933627：13:13:35 CST返回INDEPENDENT_HOST_ADMISSION_NOT_ISSUED_NO_CLOUD_CALL，发生在任何STS/SWAS前；云调用0、主机命令0。不是RAM或Secrets故障，不重发此已观测批。
- production_start.py新增最终检查点专用启动候选（final-v1，禁止r1/r2初步数据）、专用身份及准确字节准入、三服务监督启动/健康、失败仅停自有服务并保留数据、不复活原writer、不切入口。源SHA6ad51228f60690365ee4004c8c05b9c982eb2de70551ac8061142fcb4c93fa32；该候选未接通生产执行动作、未实机运行、并非完整生产准备PASS。
- 准确checkout23b9b42bbfa7655bb38c0c1ebc83f4edadc3efca，run39005621738/job117317379867 SUCCESS；原停止事务9项+新启动围堵4项均通过。属于临时文件及模拟systemctl检查，不是PID1或业务验收。
- 真正仍缺：原准确独立主机准入、真实最终检查点/原writer停止及唯一writer归属、专用运行身份与文件权限、完整生产触发/鉴权和站点切换接线。源码作者不制造这些真实输入，不把源码或入口测试记作迁移节点完成。
- 本轮无新的生产服务安装/启动/切换，仍剩6大节点，当前无后台部署writer。PR99三应用124源码/2906运行文件不是PR122网站/客户中心发布包；不得替换dots网站writer或混用网站安装范围。已通过未变内容继承，后续只对完整新增执行链集中验收。


## 2026-10-17 Owner交接：原迁移Work停止，dots待确认接手

完整交接：docs/PR99_SERVER_MIGRATION_DOTS_HANDOFF_20261017.md（文档提交b52affad1e7575a2e471ead621152eb1f74cf64a）。原分支保留，源码/私有日志/失败批不清理、不重置。本窗口本次归档回读后停止迁移代码、标签触发、云命令及部署。当前无本窗口已知在途/未知SWAS调用，无本地相关后台进程；未重发Root探针。最后主机r2验收已结束并清理，最后标签入口在任何云调用前HOLD。常规文档CI若自动启动不算后台部署writer。

Owner已授权dots接手，dots在原PR99核对最新HEAD和本文后确认单writer；接手确认前状态DOTS_PENDING_ACK，不虚构已自动接件。生产仍未安装/切换、剩余6大节点；完整入口、源码成熟度、准确run/Invoke、真实输入缺口、私有目录、跨PR边界及禁止重放批次见交接全文。PR99与PR122网站包不得混用；原通知任务只读并保持启用，不是迁移执行者。此次提交仅交接登记，没有新的主机操作。


## 2026-10-18 19:44 CST — 原执行窗口恢复当前四机只读通道

- 实际源码 Commit `4ebfb67d7fcf7178045938a740e3696e1675120d`，Tree `ccf4dcba0d99c8cd5f4603ed0f83b8f0addd51b4`。仅新增 `.github/workflows/pr99-current-readonly-recovery.yml`；原40文件修复候选未修改、未发布、未执行。本次不重放受限目录动态测试或WAL隔离检查。
- 原仓库Secrets→STS→SWAS当前实际成功4/4，root/hostname/nonce及实例绑定通过。新run [39124426535](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39124426535)，校验job117666462961、现场job117666481531均SUCCESS，原始日志已读。完成时间2026-10-18T19:44:26+08:00。
- 英国 Invoke `t-gbr70epxx2hnnk0`、韩国 `t-kor70epxx0fg8hs`、国内 `t-sh070epxy88f0u8`、东京 `t-jpn70epxxoto7pc` 全部Success。四次都是固定只读元数据命令，数据库打开0、业务请求0、服务动作0；不建立新的现场Writer。
- 查询各固定实例Pending/Running/Stopping状态时均返回空；这只是查询时观察，不是全局排他或fence证明。原事务/丢响应语义不因本次通道成功自动关闭。
- 东京三个原应用unit均loaded/active/running；国内三个新名迁移unit均not-found/inactive/MainPID0。准确final-v1、生产启动私有admission和生产启动STATE固定路径不存在。没有执行启停、安装、切换或东京退役。
- 当前唯一Writer及强制Fence仍UNKNOWN：所选进程/单元元数据不能代替权威写入者清单、epoch、排空和fence回执。新入口只恢复准确只读能力，不是生产准入。
- 原接收确认#6249117307保持有效，不再请求Owner提供原执行者或窗口链接。此前“当前没有可用执行通道”的表述在本只读范围内由上述新实机证据替代；不推断M99修复发布或生产许可已恢复。
- 本次准确新标签 `pr99-readonly-recover-4ebfb67d7fcf` 已消费；旧停止安装任务run39124426646为SKIPPED。不得重新添加标签或重跑现场job；只读批已结束，无本批后台命令。
- 回执：`evidence/pr99-service-handoff/aliyun-execution/channel-recovery-20261018.json`。动态验收、非空WAL、完整生产接线、准确修复Commit/CI/原独审及正式迁移许可仍未完成；六个生产大节点不因此关闭。东京继续保留，原通知保持启用。


## 2026-10-18 20:07 CST — 新增源码与真实写入句柄归属取证

原分支接续，未重跑四机恢复批。新源码 ea2666f07806c70afc282e9fc7b194bff1eb4219 / Tree39943f1d46df2e9510d259234ff183f61033c9c9：固定东京、国内运行目录的两轮有界/proc采样，记录PID/starttime、可写FD与共享可写映射、脱敏cgroup和调度入口元数据；不读取环境、业务文件正文或数据库。13项假回执/秘密字段拒绝用例及描述符分类测试Hosted成功，run39125683098/job117670184382。真实取证run39125713466/job117670301461，两机Success：国内t-sh070ero6pz7zsw，东京t-jpn70ero6ast62o。

后续仅针对新发现的两个现存国内PID及已观察starttime固定归属，源码a729a946a9211addd321b9347f3f375053e2b98f / Tree1a38c2cde0ddc7646320d5bd8dad3be13785f231；6项拒绝用例Hosted成功，run39125912196/job117670878570。实机run39125963077/job117671048852/Invoke t-sh070erzr1zgwzk Success，20:07:19 CST：
- PID90354/start91354061→windows-interaction-http.service；1个.db类文件可写FD。
- PID188767/start178248493→provider-neutral-domestic-bridge.service；同一inode上2个.db类文件可写FD。
此为文件名后缀及内核元数据，不是打开数据库后的SQLite格式或业务归属证明。两服务是应保留的国内既有职责，不能随东京三应用一起停止。

东京3应用仍active，采样时未持有所选运行根FD不代表已排空、没有空闲/定时Writer；cron正文及其他挂载命名空间未核验。当前权威Writer、强制Fence仍UNKNOWN。观察不签发fence或canonical assignment。

新增云命令3，全部终态成功；数据库打开0、服务动作0、业务请求0、生产切换0。准确标签已消费，禁止重加/重跑。原40文件M99修复未重发、受限动态测试和bwrap入口未重试；非空WAL能力及获准环境仍HOLD。新增代码/元数据链CI通过，未改P2的run39125912200失败保留，不能宣称全仓CI绿。

集中材料：evidence/pr99-service-handoff/aliyun-execution/WRITER_AND_ACCEPTANCE_DELTA_20261018.md。正式最多5次迁移Attempt许可未签发，未把本次3次只读取证计为生产Attempt。6个生产节点仍未关闭，本批无后台迁移命令，东京保留。


## 2026-10-18 20:35 CST — 非空WAL与丢失InvokeId两个独立源码节点

准确Commit9a737e2487a536dffd92d07e01ca0310e7366297，Treec97cd5805399d3cffe6175b629da40cd5834d0f7；只新增wal-memory-vfs目录及无云密钥的专用CI。原40文件候选保持原字节，未重发被拒候选、未重试M99动态反例/bwrap、未改隔离环境。

N1：官方SQLite原生API通过限域内存VFS读取主库/WAL字节，WAL索引也只在堆中；官方恢复、堆副本checkpoint、backup、完整性/schema核验、serialize。无路径/SQL输入，不打开原生产数据库或捕获文件，不擅自checkpoint生产库。13项合成数据测试涵盖仅WAL存在的已提交行、不同page size、截断/坏校验和/未提交尾部HOLD、时间/fence回调错误及多线程独立调用。不是M99动态验收或实机最终快照PASS，未接入/替换原生产捕获适配器。

N2：丢失InvokeId时，限DescribeCommandInvocations按完整命令hash/operation、固定实例和作用域做全分页精确匹配；0条UNKNOWN、多条/冲突HOLD，永不重发RunCommand。基于调用者原准入dirfd和命名空间校验，独占补写原cloud-start.invocation.json；不创建第二控制器根/账本/Writer。10项测试含分页、重启复用、完整内容绑定和部分记录保留。实际云查询及持久现场控制器接线仍未验收。

真实Hosted CI [39127878159](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39127878159)：Python3.11/job117676731028、Python3.12/job117676730889，各23/23 PASS，0跳过，原始日志已读。两份内层源码ZIP均17694字节/7成员/SHA256 38e7dc884c381478e682c7f502f1bc7e497b64ad67528c8e11d8a5dbdc8e89ae；本地按准确Commit/Tree重建一致。Artifact12136772337/12136514874；外层Actions压缩包摘要分别保留，不混同内层源码ZIP。

源码/测试节点已形成可复用检查点，独审/生产部署/实机验收仍待完成，不提前冻结关闭。完整数据/所有写入来源/强制Fence/排空和生产接线仍是原执行方实现责任，非Owner权限不足。M99正常放行是独立外部缺项，其他独立开发不因此重做/停掉。六个生产大节点未关闭；本增量云/主机调用0，东京、国内桥接及Windows现网未操作。


## 2026-10-18 20:51 CST — 两个节点的显式接线源码及双Python 41项CI

准确代码Commit d5bc04c6e03d558b122341120f37d038dba87155，Tree16208b878596af1ebfdb1444d9add99ca5991567。新增node_bindings.py及18项集成测试；原native WAL VFS未变。原40文件候选、原生产transport/start字节均未修改/重发。

- WAL：原PathGuard协议→已捕获main/WAL字节→官方内存VFS→原独占持有fd→原FINAL_FENCED_SQLITE_CANDIDATE回执；保留原始捕获，检查fence、期限及source drift，失败不产完成回执。没有另建guard、全局monkeypatch或pathname SQLite fallback。
- UNKNOWN：ReconciledQueryTransport包装原已发布DomesticStartTransport，发现InvokeId后只查询结果，沿用原回执校验和文件名，通过原目录fd持久化；dispatch恒HOLD。新增普通跨进程测试读取同一临时原记录，不调用RPC、不重发命令。该临时记录不冒充受信现场持久控制器。
- Hosted真实CI [39129030692](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39129030692)，Python3.11/job117680179245、Python3.12/job117680178875，各41/41 PASS，0跳过；日志已读，20:51:30 CST完成。源码ZIP27602字节/9成员，SHA256 276f17a2c8d39ae048815b1bd7228a3bc86be3fe330e509faf7b914654418ba7；本地按准确Commit/Tree重建与两份CI一致。Artifact12137780040/12137785062，外层Actions摘要另存。
- 集成测试的FixtureIO明确仅为普通路径合成夹具；未执行原PathGuard、目录祖先替换、M99反例、bwrap或现场操作。M99限制未解除，不据41项CI宣称动态路径安全PASS。
- 当前分支原final_material_adapter.py及material_paths.py读取404，完整原适配器仍只在未发布候选中。因此新增的是显式源码接线，不是完整生产捕获/控制器已激活。原候选正常发布、M99放行、原受信目录绑定及实机验收仍待完成；未换接口或环境重发被拒候选。
- 完整权威数据/全部写入来源、唯一Writer、强制Fence/排空、持久控制器和其余生产接线仍由原执行方负责完成，不归咎Owner RAM授权。正式许可未签发、六个生产大节点未关闭。本轮云/主机调用0；自动Root现场job为SKIPPED，无后台迁移writer；东京、国内桥接、Windows现网未操作。

详细回执：evidence/pr99-service-handoff/wal-memory-vfs/INTEGRATION_DELIVERY_20261018.json。新增代码与测试集中送原独审，未变已通过范围继承，未自签独立PASS。


## 2026-10-18 21:17 CST — 原执行任务接续：调度定义取证成功，源码回执缺陷保留

Owner确认另一核验窗口停止后，本原执行窗口继续同一PR99/分支；无新生产Writer、无重复交接。20:51两节点41项CI及未变结论继承，不把源码成果认作生产安装。

新增东京AST/调度只读源码960029b58f6dee751ffd068ca9b460f31e24acdb，Tree11004770252ddd0dd2eaff5e0f247938a86ce7f5。13项输出拒绝/AST不执行及脱敏测试，run39129774407/job117682373135 SUCCESS。
真实run39129846790/job117682605331/Invoke t-jpn70ewzbz4t62o Failed。只通过DescribeInvocationResult查询同一调用（run39130046782/job117683196015），取得固定原错误RuntimeError:SCHEDULER_NAME_BOUND，exit1。未重发旧批，原结果保留。

仅修复调度模板单元名校验，独立调度阶段c9a022848c4cb53e5bfa6cef1017c181476cd857/Tree13113dc792a43e1fc28f3d038135e5f5c580502f；模板名称及7项拒绝测试CI run39130253188/job117683783955 PASS。
真实run39130337276/job117684049239/Invoke t-jpn70exlhv86xa8 Success，2026-10-18T21:10:08.519621+08:00：
265份普通定义读取、30个符号链接跳过、17份相关候选定义。含三应用、财务/账务同步、两个timer、模型/tunnel/现有Runner等，不能据此指定全部为Writer或停掉。只扫描直接普通fragment，未证明effective配置、drop-in/链接/其他命名空间和动态来源。既有服务全未操作。

随后仅取未取得回执的源码阶段6d642ce56d1673782892e03f9a94b8b325edc189；13项输出/AST测试CI run39130563691/job117684685235 PASS。
真实run39130598500/job117684814509/Invoke t-jpn70exx16tf280主机Success，但回执校验HOLD。只查同一Invoke（run39130868561/job117685589430），保存输出32768字节、JSON不完整；不能恢复成已验收清单，不能按exit0认定成功。
针对回执传输大小新增有界压缩封装，原AST语义不变、不重扫已接收的调度定义。封装小于23000字节、解压不超过110000字节，校验准确长度/SHA及完整流，再执行原严格输出白名单；错误/截断/秘密字段和虚假fence仍HOLD。本提交仅发布该修复，尚未触发新现场采样。原旧Invoke、错误、输出摘要和标签全部保留，不移除重加或重跑旧job。

本轮3次新只读主机调用：1失败、1调度成功、1源码主机成功但回执UNKNOWN；两次错误/元数据查询均未发主机命令。数据库打开0、服务动作0、生产切换0。完整权威数据/全部Writer/Fence/排空、原候选正常发布、M99动态、正式许可及生产实机验收未关闭，六个生产大节点仍未关闭。受限M99和bwrap入口未重试，东京、国内桥接/Windows服务保留。无后台迁移Writer。
完整证据：evidence/pr99-service-handoff/aliyun-execution/SOURCE_SCHEDULER_OBSERVATION_20261018.json。


### 2026-10-18 21:26 CST｜原源码调用回执恢复，静态覆盖边界已落盘

东京压缩源码调用 run39131088206/job117686249811，Invoke t-jpn70eyimb7p0xs 主机Success；初始接收失败原因为HOST发送SOURCE_ONLY、接收端期待SOURCE_COMPACT的标识不一致。本执行窗口已修复查询端，未重发该主机命令。准确查询代码37bd947595c9042a1a411b8833bb734412e5fcea，Tree c3e36d1ed4a18eb0378e609b122589706c17d7e8；Hosted验证run39131509867/job117687469281通过13项元数据拒绝、6项封装拒绝、标识及只查动作边界。只查恢复run39131540878/job117687580596 SUCCESS，2026-10-18 21:26:31 CST；固定原Instance/Invoke绑定，未恢复原本地claim nonce，不冒充该独立绑定。

已接收静态清单：831份Python源码、8894117字节、247份调用候选，返回128行，119行未展开；其中101行为artifacts目录副本，不能全部当作现网Writer。源码清单摘要83f345c9a4a0ea3fda8aebe59b7c70768bbb5862ce2a57774b0d8b5d554675ed，无解析错误。此前265份普通调度定义/17相关候选的已接收证据继承，不重扫。调用名称、字典get的键名和历史副本不是实际写入或环境证明；完整数据路径、全部Writer、动态/闲置/共享/其他namespace覆盖仍未证明。

本轮累计4个只读主机命令，均终态；3次失败/结果查询均0主机命令。完整旧失败、截断结果及后续标识错误保留，不重加旧标签；本次静态回执接受不关闭权威数据或Fence节点。东京、国内桥接和Windows未操作，数据库打开0，生产安装/启停/切换0，无本窗口后台迁移Writer。原40文件候选未重发，M99 NOT_RUN，正常发布解除依据仍缺；个人上下文检索也未找到原始拒绝工具结果，二手转述不作为解除依据。6个生产大节点仍未关闭。

完整回执：evidence/pr99-service-handoff/aliyun-execution/SOURCE_SCHEDULER_OBSERVATION_20261018.json。


### 2026-10-18 21:33 CST｜运行进程配置与数据身份关联新证据

准确代码59ab9bf543d76904f1c6d8090fa6dec3d0171a5c，Tree53189eec2fcf6b77a2a906f412ddf4bc89e6d70d。固定范围为东京原3应用和国内Windows/桥接2保留服务，只读初始进程环境中的指定键，内部解析后仅输出文件metadata，不输出值/路径/完整URL。不是原PathGuard替代品，不执行M99反例。Hosted CI run39131976179/job117688820982通过5个路径用例、9个隐私/假准入拒绝及两种传输编码；原压缩程序实际嵌入HOST scope回归也通过run39131976140/job117688820540，未重发原源码扫描。

真实执行run39132016839/job117688962517 SUCCESS：东京Invoke t-jpn70ezn4z8m03k、国内Invoke t-sh070ezngkvod8g，均Success。东京三应用初始进程环境没有TRADING_DATABASE_URL，不能据此确认最终库；默认值、dotenv或运行时配置仍须解析，不把UNKNOWN作通过。国内Windows PID90354关联device64771/inode1845988/uid1001/259497984字节常规文件；桥接PID188767关联device64771/inode835654/uid1001/991字节常规文件。两者关联的MAIN身份不同；这不排除其他共享文件/Writer，也不证明文件格式为SQLite。均保留原位，不纳入迁移选择；Windows所关联文件大小还超过现有64MiB捕获上限，不擅自扩大上限或尝试捕获。所选配置路径在采样时未见对应-wal/-shm，不证明全局无WAL。

本增量2个新只读主机调用已终态；无数据库打开/服务启停/业务请求/生产写入。此前源码/调度4个主机调用及3次0主机命令查询按原回执继承。完整数据/全部Writer/Fence/排空、受信持久捕获控制器、原候选正常发布与M99动态、正式迁移许可及生产验收仍缺，6大节点不关闭；本窗口未领取现场Writer，没有后台迁移任务。

回执：evidence/pr99-service-handoff/aliyun-execution/RUNTIME_DATA_BINDING_OBSERVATION_20261018.json。


### 2026-10-18 22:07 CST｜数据库参数追踪与实际存储路径新增证据

Owner21:47指令后继续原任务。源码dd84570b→55e13ab3→5b65f8e3→f17d79836d51e75d9ad1428756629ee2218b7cc1，最新Tree50266966ec254b2c61794b83adbfac57345ab3c3。新增有限AST表达式解析与存储调用追踪，不导入业务源码，不执行SQL/业务构造器。普通解析测试14→18项、严格白名单拒绝及字面量脱敏Hosted通过；不是原M99目录替换动态反例。

真实现场均Success：run39133483528/job117693235818/Invoke t-jpn70f1f5xrkzk0；run39133710438/job117693883274/t-jpn70f1p4i6d2ww；run39134112999/job117695045265/t-jpn70f26m8rbhfk；run39134555244/job117696334458/t-jpn70f2pr9vi6tc。所有完整日志已读。本批4个新只读命令已终态，未重加旧标签或重跑旧job。

前两次调用虽然主机成功，database_url解析仍UNRESOLVED，完整保留，不作数据验收。调用处证明所追踪数据库工厂使用database_url变量；三个入口未发现直接调用本次所选工厂，门户有环境加载逻辑。不能由初始进程环境无TRADING_DATABASE_URL推出无数据库或数据默认值已确认。

存储追踪读取6个相关模块，核对3个入口准确SHA，取得17个源码引用运行路径及metadata：门户状态、OperationsSecretRef values/metadata/audit、两类客服、Telegram canary和桥接配置等。17个引用路径存在不等于17份最终迁移数据；凭据、token、env、业务内容均未读取。database/repositories.py导出入口未解析，以及accounts CredentialStore、Douyin/TikTok存储依赖和构造器keyword路径绑定仍未覆盖；源码字面量路径不是完整运行时配置，不提前关闭权威数据节点。国内保留服务和东京均未启停/覆盖。

Hosted验证：39133422979/job117693036912、39133671326/job117693752919、39134049933/job117694853284、39134466847/job117696053242。原WAL/InvokeId d5bc04c6未改，41/41历史通过直接继承。本批原40文件未重发，M99受限入口未执行，正常解除依据仍缺；完整Writer/Fence/安全排空、持久控制器实机接线及正式许可未完成。生产安装/数据库打开/业务请求/切换均0，六大节点未关闭。本窗口未领取生产Writer，无后台生产迁移作业。

完整回执：evidence/pr99-service-handoff/aliyun-execution/DATABASE_AND_STORAGE_TRACE_20261018.json。


## 2026-10-18 22:45 CST｜原执行窗口存储绑定修复与数据库候选观察

CODE_COMMIT=138eda930f64eee29cf8f4868336bb4106aa9a76；CODE_TREE=af65402f2887401b069fc09aa80572578f7c425d。

已修复包目录/函数内导入遗漏、构造器关键字与路径参数链、条件/循环/self字段的UNKNOWN保守传播，以及同模块数据库工厂调用遗漏；不执行业务源码。最终Hosted run39137183207/job117703977165：19项新增+18项继承表达式测试、6项拒绝检查及回执/命令边界PASS。原WAL/InvokeId 41/41未变通过继承。13文件精确SHA清单见STORAGE_BINDING_SOURCE_MANIFEST_20261018.json；这是只读源码集绑定，不是生产安装包。

真实新增现场：run39135913524/job117700287011，t-jpn70f4bywoar5s主机Success、接收端误拒绝未解析receiver的.read_text/.replace等方法名；保留失败。修复后只查原Invoke，run39136149304/job117700977671恢复12模块、21路径metadata，未重跑主机；有31行存储细节因输出边界未展开。原本地nonce claim未恢复，不声称独立nonce核对，绑定原云InstanceId/InvokeId。

凭据库已追到database.connection.SessionLocal。run39136502136/job117701988723、t-jpn70f50rrw71mo Success：源码默认候选MAIN dev64771/inode1601016/46907392字节/uid1000；WAL/SHM采样缺失。源默认不冒充有效运行配置或最终数据选择。run39136896590/job117703141520、t-jpn70f5houiw35s Success，22:38:38北京时间：201进程/1991描述符、1次句柄变化，未见匹配fd/共享可写映射。不能据空样本推断无闲置/定时Writer、已Fence或可复制。数据库内容未打开、生产服务无操作。

仍由本执行窗口负责：完整有效配置/权威数据与其他状态目录、闲置/调度/共享Writer覆盖、实际强制Fence/排空、原持久fd控制器和完整捕获链的实机绑定。现有GitHub新源码写入和STS/SWAS只读均真实可用，不要求Owner重配RAM或找另一个执行方。原受限40文件发布原始拒绝/正常解除依据仍缺；已知bwrap EPERM不是已证明的发布拒绝原文，二者不混同。M99不重试、不换环境/接口规避；需原限制平台提供正常验收放行，尚未提交平台支持工单。源码增量交原独审，作者不代签许可。

正式迁移许可未签发；6个生产大节点仍未关闭，生产迁移/切换尚未启动，没有本批后台生产迁移任务。东京、国内桥接和Windows保留。完整回执：evidence/pr99-service-handoff/aliyun-execution/STORAGE_BINDING_REPAIR_20261018.json。


## 2026-10-18 23:13 CST｜有效数据关联与原持有fd控制器新增源码

CODE_COMMIT=210bcf02eb53ace39420c6b3eb5d2bcda3c711ac；CODE_TREE=50ef767de1c980ab0b4e68c9c813b2238d004027。本次10文件仅新增runtime-controller源码/测试/文档及无云密钥的CI，未改原40文件、原生产入口/transport或已通过WAL恢复节点。

新增：三应用有效配置→数据对象→Writer/激活源的显式关联校验；完整成员/共享保留冲突检查；借用原Journal/原锁/目录fd的持久控制器；阶段/前序回执严格校验；已有INTENT和UNKNOWN只查询、不重发/自动继续；原持有输出fd的Fence证明保存；固定systemd/cgroup/内核标志接口。原完整准入、真实排空证明和原PathGuard缺少任一即HOLD，不另建Writer/epoch/路径Guard，不自签授权，不提供东京解冻/恢复入口。

Hosted [39139479365](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39139479365)：Python3.11/job117710747116、3.12/job117710747444，各45/45 PASS、0跳过，日志已读。含跨进程原账本锁/已有INTENT查询恢复、跳步/错误前序/撤销准入拒绝、部分记录保留及Linux接口mock。45为去掉继承重复用例后的独立数量；不是45项M99或实机测试。内层ZIP66090字节/10成员/SHA256 39539b35e1b0d443bfab12a0a8cadde9eda38bbff2c766b16570ac4a76fdf613；本地重建一致。Artifact12140468584/12141490347，外层Actions摘要与内层源码ZIP分列保存。原5依赖逐字节SHA固定，原WAL41项通过直接继承。

**Owner指定的前两项实机门禁仍未关闭**：数据关联代码已有，但完整现场有效配置、权威数据与全部闲置/手动/调度/共享Writer覆盖尚缺；原控制器接线和Fence代码已有，但尚无获准环境中的真实原fd/排空源/内核Fence/完整捕获链验收。普通fixture授权与路径回调不冒充受信现场签发。以上仍由本原执行窗口负责，不要求Owner重配RAM或再找执行方。

原受限40文件拒绝原文/正常发布解除仍缺，M99 NOT_RUN；不重试或换账户/API/环境规避。新源码仅集中送原独审，正式迁移许可未签发，未自签PASS。当前inspection及recover-readonly现场job均SKIPPED，本增量云/主机命令0、服务动作0、生产Writer0、生产迁移/切换0，无后台迁移作业。东京、国内桥接和Windows保留，6个生产大节点未关闭。

完整回执：evidence/pr99-service-handoff/runtime-controller/DELIVERY_20261018.json。


## 2026-10-18 23:30 CST｜原账本—排空/Fence—WAL/普通文件捕获接线增量

CODE_COMMIT=d50e272b1dbfbd0a460efb76f372e0ac69073593；CODE_TREE=1020429488d2ca4b82eff0f148c5ac21634e3d32。9个受影响路径，新增capture_session.py与11项普通联动测试，另增加固定东京root拒绝测试，总57项；原45项受影响测试同批回归，未重复原未变41项WAL算法整套。

CaptureSession.perform只接fence_source/final_snapshot：先原INTENT落盘，再接真实排空依赖、SourceFence、原持有fd证明与原guard上的已发布WAL恢复/普通文件捕获；现有INTENT只核对已有输出，未知不重发、不重跑SQLite、不重设Fence。捕获合同绑定输入与完整COPY_FENCED文件集合；从原账本成功Fence RESULT读取实际hash，避免预先绑定未来尚不存在的Fence摘要。Fence证明新增事务/plan/operation绑定，Linux后端强制固定东京root。源主库/WAL原始捕获保留，不checkpoint生产库；缺guard或准入不走pathname fallback。

真实Hosted [39140766515](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39140766515)，Python3.11/job117714545568、3.12/job117714545348各57/57 PASS、0跳过，原始日志已读。合成非空WAL中17行提交恢复到候选结果，普通状态文件同时捕获；部分输出、代码/合同/准入变化及未记RESULT时的只查恢复均覆盖。该合成测试使用真实已发布SQLite内存VFS；路径/授权/排空/内核状态仍为普通fixture，不是原PathGuard、M99或现场接受。

内层源码ZIP90673字节/12成员/SHA256 9cf2fed279747a6c84af8a22bd513a4d5d26d33f99e99b446160d8b9025bf9eb；两Python日志和本地准确版本重建一致。Artifacts12140784219、12141776616，外层Actions摘要单列。原5源码依赖及4份原WAL/测试依赖固定SHA；未改WAL算法、未重发原40文件。

本轮可独立完成的两阶段源码接线已形成送审检查点；**完整实际有效配置/全部Writer清单仍未获证，原fd/guard/真实排空及内核Fence/捕获链的实机验收仍未执行**。不能将源码联动完成视为两项实机门禁已关闭。获准环境、原受限候选正常发布/M99及独审许可仍缺，未绕过限制。后续传输/核对/正式Writer assignment/安装/切换/业务与恢复验收不由本两阶段接口宣称完成。

增量送原独审，未变结论继承，作者不自签PASS或正式许可。当前inspection/recover-readonly现场job均SKIPPED；本增量新主机命令0、生产Writer0、服务动作0、迁移/切换0，无后台迁移任务。东京及国内桥接/Windows保留，6个生产大节点仍未关闭。完整回执见evidence/pr99-service-handoff/aliyun-execution/CAPTURE_SESSION_DELIVERY_20261018.json。


## 2026-10-18 23:49 CST｜入口封闭与排空证明绑定修复、启动顺序现场回执

CODE_COMMIT=861dd13691705a4752a4f9140bfd5d098c4da660；CODE_TREE=5d24397215c8c8a7ff0d8174e6c6e594a7c1c55c。修正空队列采样不能替代持续封闭的缺口：原真实排空源必须确认入口已封闭、精确全部相关写入/激活来源、原事务/plan/inventory/epoch及原plan内有效期；每个mask/stop/freeze前重验同一封闭记录。记录过期、丢失、来源缺项、跨事务/plan或变化均HOLD，部分效果保留，查询不重放。新增8项反例，原57项受影响回归，共65项。该源码没有实现或部署现网入口封闭接口，mock响应不等于现场排空。

Hosted [39142171346](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39142171346)，Python3.11/job117718654654、3.12/job117718654994各65/65 PASS。完整日志已读；内层ZIP95596字节、12成员，SHA256 bdfe88be3f2fe960be5a95b59f32bdebb92ff149fcab41d00f0694b443a16e2e，与本地准确Commit/Tree重建一致。Artifact12141757554/12142031196，外层Actions摘要分列保存。不是M99/实机验收。

另取得缺失的固定启动源码控制流：[39141834572](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39141834572)/job117717694949，Invoke t-jpn70fbdpsmzw8w Success，2026-10-18 23:44:39 CST。4文件SHA与既有源码pin一致，返回脱敏语法，不导入业务、不读环境/数据库；确认数据库模块级engine/SessionLocal绑定发生在门户build_service/load_local_credential_env调用之前。凭据文件具体键已脱敏，不推测该键；这一顺序观察仍不是当前进程有效配置或权威数据签认。只发本次新范围1个只读命令并已终态，未重发旧标签/Invoke。

**本执行窗口自己的现场部分尚未全部完成，并非仅余审核签发**：完整有效配置/权威数据/全部写入源、真实入口封闭与排空实现、原准入fd/guard控制器及Fence/捕获链实机验收仍缺；后续传输/核对/Writer assignment/安装切换亦未由本候选完成。现有东京STS/SWAS只读通道实际可用，不要求Owner再配RAM。原40文件拒绝原文及正常发布解除未取得，M99未运行/不重试，作者不自签独审或迁移许可。当前没有后台迁移任务；生产Writer/数据库打开/服务启停/迁移切换均0，东京和国内桥接/Windows保留，6个生产大节点未关闭。

完整证据：evidence/pr99-service-handoff/aliyun-execution/SEALED_DRAIN_DELIVERY_20261018.json；现场回执：CONFIG_FLOW_RECEIPT_20261018.json。


## 2026-10-19 00:10 CST｜实际应用入口封闭/排空组件新增源码

CODE_COMMIT=5c671a774a4b52ae3974b902a6c850d31b6ad533；CODE_TREE=7d561d8385857217d12efd7d98d5c27cca341842。新增ingress_gate.py/test_ingress_gate.py，原extension manifest绑定新增模块，制品与说明更新；原65项受影响用例回归，加21项新测试，总86。

ApplicationIngressGate实际管理有界普通队列和同步事务：接收时绑定原任务ID，封闭新入口与登记任务在同一互斥区；封闭后原已接任务可继续完成，等待最多60秒。异常/处理器返回后准入丢失均保留UNKNOWN，终态对账不再次调用handler；原ID不重复接收。向原预持有一次性fd保存封闭记录，部分写入/变更不覆盖；该fd独占借用不新建迁移锁/Writer/epoch/Journal/路径。内核PID/start_ticks/boot摘要与gate实例绑定，原封闭记录跨同进程重建及真实新进程只报UNKNOWN_PRIOR_PROCESS，空队列不能冒充已排空；缺真实启动对账证明也不能认证。

真实Hosted [39143742970](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39143742970)，Python3.11/job117723264458、3.12/job117723264662各86/86 PASS；完整日志已读。内层ZIP122644字节、14成员，SHA256=4cc00db693756c1707a26766af6ed917f87d6d8ecf07580fcf1426a46bb7939e，两CI与本地准确Commit/Tree重建一致。Artifacts12142766892/12142423617，外层Actions摘要另列。新增测试实际使用普通queue/thread/fd/flock及真实子进程，并非M99/现网服务测试。原未变WAL与原40文件未改/未重发，受限入口不重试。

**仅组件源码完成，现场第二类阻塞不关闭**：尚未将原三个应用的全部同步写入/异步队列和其他origin接到该组件，没有安装新端点或把单进程观察伪装成全局可信排空。完整数据/全部来源、原guard/controller/fd/捕获链实机验收、原候选正常发布与M99、独审许可、正式迁移验收共6类仍未闭合，详细责任与缺项见证据blockers。现网接线并非只等独审。

本批主机命令/数据库打开/服务启停/生产Writer/迁移切换均0；无本窗口后台迁移任务。东京、国内桥接/Windows保留，不要求Owner重配RAM、贴代码/密码或再找执行窗口。源码增量供原独审，不自签许可。完整证据：evidence/pr99-service-handoff/aliyun-execution/APPLICATION_INGRESS_DELIVERY_20261019.json。


## 2026-10-19 00:56 CST｜Owner直接执行：账户及三个停止候选单元已实机安装

本节覆盖早期“等待独审/正式许可”的当前状态：Owner于00:29明确取消这两项等待，并于00:49再次确认。本窗口直接接续执行，不要求Owner逐项批准。真实技术条件和实际平台拒绝仍按原错误处理；不将UNKNOWN判为通过。

已完成现场动作：
- 国内专用账户xuanjun-s07已创建，UID992/GID991，无登录shell、未建home。[run39145761696](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39145761696)，job117729165434，Invoke t-sh070fg0jfiifpc，00:36:36 CST。
- 三个原新名候选unit已安装，保持停止；同一原安装STATE和lock，原R2准确字节和真实验收回执。[run39146617633](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39146617633)，job117731669674，Invoke t-sh070fh0ruuncao，00:47:54 CST。新增unit3、daemon-reload1、start/enable均0、数据库和路由动作0，protected未变。
- 首次安装run39146426810/job117731113279/Invoke t-sh070fgsorn44cg真实失败PRIVATE_INPUT_MODE，完整脱敏回执保留。纠正批先确认原安装STATE不存在、目标unit不存在且停止，再将原R2验收回执0644收紧为0600；相同字节和身份。没有删除重加旧label、重放UNKNOWN或伪造成功。

新增正式启动入口源码：CODE_COMMIT=370cc24a4b8c07dc0100ff2c89f9dd6e53a0c243；CODE_TREE=43b4e036b08276ae37758850bd4b7eca4a37cea7。owner-start/owner_production_start.py明确使用Owner直接授权，不要求reviewer ID或新许可；保留真实最终文件/Fence/checkpoint/canonical Writer assignment校验。借用同一原停止安装锁，原精确停止候选安全退役后才创建正式unit；原生产STATE和UNKNOWN不重发语义保留。

[Hosted CI39147242803](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39147242803)：Python3.11/job117733460568、3.12/job117733460335各17/17 PASS，0跳过；完整日志及Commit/Tree/源码SHA已核对。包含普通临时文件上完整启动核心调用链与未知native启动结果保留测试。原生systemctl均为mock，不是实机生产启动/M99。新正式入口尚未落到主机或执行。

**生产迁移仍未完成**：实际有效配置/权威数据及所有相关写入来源仍需完成；真实入口排空、原控制器/fd、内核Fence、完整最终捕获/接收/核对尚未实机完成；最终checkpoint与canonical assignment没有生成，不能拿R2初步数据作生产库；业务/鉴权/上游/切换/恢复验收未执行。这些是本执行方未完成的技术工作，不是Owner授权、独审或许可等待。原40文件未重发，M99未运行，原发布拒绝原文仍NOT_FOUND；本批独立Owner源码已正常发布，不声称GitHub全局不可写。

三个现场命令批均已终态；当前无本窗口后台迁移任务、没有领取生产数据Writer或执行切换。东京、国内桥接、Windows、Nginx保留。英国P2不在本批范围。无需重配RAM、贴密码/密钥或重新交接。

完整回执：evidence/pr99-service-handoff/aliyun-execution/OWNER_DIRECT_INSTALL_DELIVERY_20261019.json。


## 2026-10-19 01:41 CST｜最终核对/原Writer接线113项通过，启动程序实机安装完成

CODE_COMMIT=ca609d47a9182436a8d47c59170869cf73002f7f；CODE_TREE=1ea6bb60c2cc829d8ec9647464f066646b340da5。新增final_handoff.py与owner_contract.py：源侧原Fence/捕获证明通过原只读查询绑定，目标完整fd集合核对后生成真实最终检查点；Writer交接必须调用原权威CAS/查询，不因本地字典或文件存在判为完成。原INTENT、原Journal、同epoch及UNKNOWN只查不重发保留。明确Owner直接授权，不恢复独审/许可等待，不伪造reviewer ID。捕获证明容量在显式2MiB界内扩展，默认16KiB保留。

[Hosted CI39149998909](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39149998909)，Python3.11/job117741497185、3.12/job117741497425各113/113 PASS、0跳过，完整日志已读。内层ZIP165444字节/17成员/SHA256 2fe9c9e96e5a18bffc08aa3ec761e93b19548873de36c5203fc09537cb9cbcdf，两CI日志与本地准确版本重建一致；Artifact12144852807、12144533637。首次113项run39149747623中2项直接调用fixture未补source_manifest patch，已只修测试夹具；生产源检查未放宽。原始失败保留。该测试使用真实普通fd/WAL恢复；native Fence/Writer权威仍fixture，不是实机验收/M99。

新增真实现场结果：国内/opt/xuanjun-migration-s07/bin/owner_production_start.py已安装为0400，34425字节，SHA256 7936650e5911f71216c1dfe1873754bcf09ddac45894df3214018dd5f21ace40，与原17项已通过启动源码完全一致。[run39150685559](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39150685559)/job117743595644，三个顺序Invoke t-sh070flru0exclc、t-sh070flsgsglce8、t-sh070flt3leq3uo均Success；最终完整字节和定义编译核对，服务动作/生产Writer/生产数据传输/路由均0，protected未变。它是未启动程序安装，不能等同生产服务运行。

保留先前安装失败：run39150037603/job117741639911/Invoke t-sh070fl01lqes5c为Failed。只查原调用的run39150467881/job117742925892确认exit2/URLError，发生于下载源码阶段、在文件写入之前；原输出未包含完整URL错误细节，不猜测为平台授权拒绝。正常修复仍用原账号/STS/SWAS，以3个小于原11000字节上限的精确载荷顺序传输，乱序/已用阶段/部分写入冲突均保留，未移除重加旧label或重放失败Invoke；未接触原受限40文件候选。

**尚未达到可以连续执行真实迁移的技术条件**：实际有效配置→完整权威数据与全部写入来源、原持久控制器/fd/guard与真实入口排空/内核Fence接线、真实源查询及完整私有传输/目标接收、实际checkpoint/canonical Writer assignment、生产启动及业务/鉴权/上游/切换/恢复验收仍待完成。新增接口和合成fixture未实例化这些native权威，不把它们标记PASS。原40文件发布原拒绝仍NOT_FOUND，M99未运行/未重试；不新增Owner审核许可等待。

这批现场命令均已终态，无本窗口后台迁移任务，无生产Writer领取或切换。东京、国内桥接/Windows/Nginx保留，英国P2不在范围。现有通知已调整为取得实际迁移就绪证据再通知，普通源码/测试/文档更新不重复提醒；未新建自动化。

完整证据：evidence/pr99-service-handoff/aliyun-execution/FINAL_HANDOFF_DELIVERY_20261019.json。
