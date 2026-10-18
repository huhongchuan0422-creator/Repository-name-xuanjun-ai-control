# 服务器迁移完成进度

最后写入句柄归属实机成果：2026-10-18 20:07:19 Asia/Shanghai；最后三应用复制品隔离验收仍为2026-10-17 12:52:15。**生产迁移尚未完成，剩余6个大节点。** 文件落盘不算服务接续；此表沿用原PR99任务，不另建队列。

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
| 2 受控安装与回滚 | 未安装。停止/禁网候选安装与冲突安全回滚已实现，r2准确源码9项CI测试通过（run39004183744）；尚未独立准入或实机安装；完整生产激活接线仍未完成 |
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
