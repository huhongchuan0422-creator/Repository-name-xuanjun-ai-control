# P2 resumable installation rewrite

原任务PR17，基础journal实现基线 `23df8fa18b45946de96dac4f77a0aa181618eb05`；历史重写来源 `ad87e5b933f6daf70b574c6459bfb2b99898a755`。
本次只在总分支更新文档，不合并组件源码、不安装、不新建执行队列。

## 已有实现及不变边界

`journal.py`提供私有SQLite/WAL、会话排他锁、Plan/release绑定、RUNNING记录、前置读回、提交和明确无副作用对账。
已提交批次不重复安装，Plan变化不能重置账本；进程崩溃保留在途状态，未明副作用不得盲重试。
既有7项journal回归为历史元数据证据，不等于完整16阶段或英国安装通过。
真实应用数据库、生产AuthorityStore与本管理journal是不同资源。
生产Grant、签名、受保护传输、Registry及历史状态保留；其生产接线不在本轮隔离文档任务。
新隔离路径不要求连接原Grant后才能测试，不增加五次额度。

## 组件快照及剩余工作

本次仅同步准确快照，不把组件合并进总分支，不重复运行未变组件测试。

| 组件 | 准确Commit | CI / 证据 | 结论与限制 |
| --- | --- | --- | --- |
| 制品 | `ea31dbbec2a8710b964efb38fa2975684bbd9739` | [39303377908](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39303377908)，SUCCESS | 组件交付：并发篡改拒绝、三个SIGKILL窗口、重启recover、前批保护、0700；非英国验收 |
| 运行 | `499bcc43f4c992b21035c22446ccc4d915873fb1` | [39303903462](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39303903462)，SUCCESS | Unix Socket就绪、有界探针、独立日志收集、稳定操作/提交引用；非生产服务验收 |
| 协调 | `a766dcb307ce738dc508ad153f17e593d1fb7bfb` | [39308651562](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39308651562)，SUCCESS；[限定验收6275266088](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/134#issuecomment-6275266088) | Tree `768a7431c689ea07fc3e4361cb3df151d0cfe1e2`；仅重复PROGRESS重开、丢失响应恢复两缺陷关闭；整体PARTIAL |

三次CI的head_sha与上表一致，本轮只读核实；协调CI双Python各21项按Dots原验收继承，不重新运行。
[续做任务6275279160](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/134#issuecomment-6275279160)中的真实失败证据/稳定去重/轮次与根因计时仍待交付；另保留完整调用超时回收、begin前中断安全续接、混合CLI及文档收口未完成项。已存在基本真实组件链与CLI导入修复，不能继续把历史ADAPTER_UNAVAILABLE或“仅进程存活”写成当前快照；也不能由此推断完整链路已验收。

## 目标环境

英国宿主Python3.6.8只运行兼容启动脚本，不升级系统Python；组件目标是现有Docker Python3.11。Python3.12 CI只是额外兼容证据。
固定网络隔离、只读根、cap-drop=ALL、no-new-privileges、资源限制；不挂载生产DB/Signer/Registry/云凭据/Docker Socket。
离线容器不证明外部任务接入、真实通知/聊天唤醒或宿主systemd/cgroup能力。

## 原16阶段覆盖表（设计映射，非执行计划）

准确来源：基线 `2adaf2dfff6a2af25e922ba85160d2b0bf211257` 的
[evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_recovery_sequence.py](../../evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_recovery_sequence.py)，
`PHASES` blob `45984835fb4dfff475d0481cceebb24811380986`。
每个稳定键仅有一个主归属；跨批引用只读依赖，不安排再次执行。

| 原顺序 | 原稳定键 | 主归属 | 功能目标 | 实现边界 |
| --- | --- | --- | --- | --- |
| 01 | `stage_exact_release` | B1 | 准确版本制品发布 | 制品组件可复用；原宿主发布未证明 |
| 02 | `preserve_prior_receipts` | B2 | 历史回执保全 | 组件不可变回执可复用；原历史导入未接 |
| 03 | `rebind_prepared_epoch` | B3 | 准备迁移与配置提交 | 原epoch绑定未实现 |
| 04 | `quiesce_exact_epoch` | B3 | 准备迁移与配置提交 | 原宿主停用不在隔离组件能力内 |
| 05 | `replace_retained_targets` | B3 | 准备迁移与配置提交 | 原保留目标替换未实现 |
| 06 | `publish_reviewed_identities` | B3 | 准备迁移与配置提交 | 测试身份发布契约待定义；不等于生产批准 |
| 07 | `change_generation_access` | B3 | 准备迁移与配置提交 | 原代际访问切换未实现 |
| 08 | `apply_reviewed_access` | B3 | 准备迁移与配置提交 | 原访问策略适配未实现 |
| 09 | `rebind_tls_metadata_only` | B3 | 准备迁移与配置提交 | 仅元数据；生产TLS不操作，适配未实现 |
| 10 | `apply_fresh_sandbox` | B4 | 隔离应用运行环境 | 运行组件部分替代；不等于原sandbox配置等价 |
| 11 | `install_verified_plugin` | B5 | 独立插件版本 | 安全制品机制可复用；插件功能契约待接 |
| 12 | `reopen_existing_database` | B6 | 持久数据重开与访问 | 不涉及原生产DB；隔离数据适配待实现 |
| 13 | `verify_runtime_access` | B6 | 持久数据重开与访问 | 真实读写/访问判据待定义 |
| 14 | `activate_exact_epoch` | B7 | 切换与最终验收 | 原epoch激活未实现 |
| 15 | `activate_new_services` | B7 | 切换与最终验收 | 容器应用启动可复用；原服务激活未实现 |
| 16 | `post_install_checks` | B7 | 切换与最终验收 | 组件链证据有限；英国/原16阶段验收未执行 |

原七批准确名称/成员/顺序的仓库原稿：**NOT_FOUND**（检索范围为上述基线两份既有重写文档及PR17评论6275334072；不是声称整个历史从未存在）。既有README仅声明“seven batches remain a design draft”。以下B1–B7为本次候选功能边界，全部 **DRAFT / NOT_INSTALLABLE**。

候选归属已修订为连续区间：B3拥有03–09，B7仅拥有14–16。下述批次条件与后文提交/恢复屏障必须同时满足；顺序合法不等于批次已可安装。

## 七批候选的依赖、验收及恢复边界

| 批次（全部DRAFT） | 最小完整目标与拥有资源 | 依赖与进入条件 | 隔离验收目标（待执行项不是PASS） | 持久恢复点与失败处置 | 未完成项 |
| --- | --- | --- | --- | --- | --- |
| B1 准确版本制品 | 一个内容固定、可读回的release目录；只写自己的版本 | 固定Manifest/源摘要、独立私有root、大小及modes明确；不以移动分支作输入 | 真实execute→inspect；摘要/mode匹配；中断recover；后批失败后原文件/回执不变 | 保留源快照、部分文件、日志和原提交回执；校验后补齐缺失；冲突HOLD，禁止覆盖已正确版本 | 统一包Manifest和英国本批回执未生成 |
| B2 历史证据保全 | 独立只读证据版本和摘要索引，能证明原件未变 | 原件来源/读取范围/归属明确，B1工具版本固定；无原件标UNKNOWN | 复制授权隔离样本，重开校验完整索引；故障不改变源件或B1 | 保存原件、复制意图和索引；只恢复本批不完整副本，不删除原回执 | 历史证据导入适配器及完整事务发布未实现 |
| B3 准备迁移与配置提交 | 完成03–09：准确准备、停用、目标替换及测试配置提交；仅独立隔离目标 | B1/B2已提交且读回；精确资源所有权、原guard和跨进程恢复契约固定；不依赖B4–B7 | 按03–09原顺序执行并验证各前后判据，CP09后才关闭；未知副作用拒绝重放 | CP03–09逐阶段保存意图、备份、真实结果；只收敛原操作；失败可保持停止，不承诺自动恢复应用 | 适配器/资源隔离和批间可暂停未验；本批包含复合迁移效果，最小完整独立性未证明 |
| B4 隔离应用运行环境 | 原sandbox配置与有限隔离探针；长驻服务归B7/15 | B1准确可执行制品；B3配置；固定启动参数和截止时间；每批独立状态root | 有限验证进程PING/PONG（不能替代原sandbox判据或提前执行15）；超时/错误响应/管理CLI SIGKILL；查询与重开不重复启动 | 稳定operation_id/config_sha256/commit_receipt及PID身份、收集器状态；先inspect/recover，不盲launch | 原sandbox机制等价未证明；协调器完整超时回收/混合CLI未关闭 |
| B5 独立插件版本 | 一个版本化插件，可验证加载和功能响应，不覆盖B1 | B1制品接口、B4指定加载契约，独立插件root及回退引用 | 插件摘要、实际加载/功能响应、坏插件拒绝；前批应用/文件不变 | 保留插件版本、激活引用和原回执；只恢复或撤回本插件引用，不清空release | 插件功能/加载适配和恢复事务尚未实现；解包成功不算插件安装成功 |
| B6 持久数据重开与访问 | 独立隔离应用数据库重开、数据保持及权限有效 | B4/B5实际依赖按应用契约固定；隔离DB来源、Schema、备份/迁移策略明确；绝不使用未知原生产DB替代品 | 真实应用写入→退出→保留非空WAL状态→重启读回；拒绝越权；先前批次证据不变 | 保存应用DB/WAL及迁移意图、备份、事务/检查点；结果未知先对账，不删WAL、不空库重建 | 应用DB适配、非空WAL恢复和原访问等价未实现；协调管理SQLite不是该DB |
| B7 激活与最终验收 | 仅14–16：选定隔离实例激活、服务启动及整链验收；不再停用/替换04–05 | B1–B6已提交并真实读回；配置/版本固定，原阶段激活判据满足 | 14→15→16及丢失响应/SIGKILL恢复；确认效果身份唯一；CP16后关闭 | 保存CP14/15效果及CP16终态；未知先对账，不重放04–13，不反向回滚前批 | 原激活/服务/最终判据适配及英国现场未验；保持DRAFT |

每批关闭必须同时具备准确代码/Plan/资源摘要、真实效果读回、故障恢复证据和对前批不变的证明。表中恢复点是要求，不是声称相应适配器已经实现。跨批进程相同UID仍可能写其他root，目录分开不是隔离证明；权限/挂载/进程边界未证明时不能承诺后批失败完全不影响前批。

## B3/B7跨序依赖消解（续做PR17 #6280434467）

本修订取代上一版把04–05归B7的候选映射。最小边界调整是：**04、05由B7移入B3；B7仅保留14–16**。不拆开或重排任何原阶段，不增加执行入口，不重写安装器。阶段主归属是责任/恢复单元，不意味着已实现相应能力。

合法候选序列唯一为：
`B1[01] → B2[02] → B3[03,04,05,06,07,08,09] → B4[10] → B5[11] → B6[12,13] → B7[14,15,16]`。
批次进入只依赖此前批次COMMITTED及当前真实读回；不存在B3等待B7、B7提前执行04–05或后批反向等待。批内严格按原稳定键顺序执行，每阶段只有一个效果拥有者；原实现与容器替代只能择一绑定，不能同时执行。

### 唯一资源所有者及发布屏障

资源所有者指未来Plan中唯一被绑定的执行适配器，不是新增窗口或Writer；Work仍为唯一集成/安装责任窗口。本轮仅规定契约，适配器授权与权限隔离未实现/未验的不填PASS。

| 批次 | 唯一写入资源与阶段职责 | 提交点（均需真实读回，不以文字标记代替） | 恢复点与后批限制 |
| --- | --- | --- | --- |
| B1 | 仅本release内容目录，阶段01；后批只读其内容 | CP01：版本摘要、mode与原提交回执匹配 | 保留源快照/部分输出；后批不得覆盖B1文件 |
| B2 | 本次证据副本/摘要索引，阶段02；历史原件始终只读 | CP02：原件引用、复制版本和完整摘要索引一致 | 只补本批副本；不改原件或B1 |
| B3 | 迁移准备状态、受控停用记录、候选目标引用及配置/身份/访问/TLS元数据，阶段03–09；04–05不再归B7 | CP03–CP09逐阶段恢复证据；只有CP09与全部前置读回成立才批次COMMITTED | CP03后尚未停用；CP04后原实例已静止；CP05后目标已替换；CP06–09按原记录收敛。任一结果UNKNOWN保留意图、备份及停用状态先对账，禁止重放成功阶段。B7不得重新停用、替换目标或改B3配置；B3失败可能需要保持应用停止，不承诺自动恢复旧实例 |
| B4 | 本候选sandbox/运行隔离描述与本批有限验收进程，阶段10；不接管B3的目标引用 | CP10：原apply_fresh_sandbox判据及隔离实际读回成立 | 只清理本批可证明归属的验收进程；原sandbox状态未知HOLD；不得提前执行15 |
| B5 | 仅本插件版本/所属安装记录，阶段11；release原件只读 | CP11：原插件安装判据与功能验证成立 | 保留原版本及本次意图，按原恢复规则收敛；不得重启B4或激活15 |
| B6 | 仅已绑定隔离应用DB/WAL、连接/访问验证记录，阶段12–13；不是管理journal或生产AuthorityStore | CP12记录重开结果；CP13确认原访问判据，才批次COMMITTED | 保留DB/WAL/备份/事务；未知结果先读回，禁止空库替换；后批不可删WAL或迁移数据 |
| B7 | 仅隔离实例激活状态、阶段15拥有的服务进程及最终验收记录，阶段14–16；只读B1–B6版本和配置 | CP14激活结果、CP15服务归属/就绪结果是恢复点；CP16完整原post_install_checks通过后才批次COMMITTED | CP14/15部分成功不算整体完成；依原真实状态收敛，不再次执行04–05/03/06–13。不自动停止未知进程或反向回滚已冻结批次 |

B3写候选目标引用，B7写独立激活状态；如真实原实现共用同一路径/状态字段，必须指定该共享资源的单一拥有者和受控操作接口，禁止两个适配器各自写。确切资源路径、运行身份及CAS边界目前 **UNKNOWN**；不得据此表推断现有代码已完成资源拆分。

CP标签是设计中的证据位置名称，**不是已存在的checkpoint文件或新恢复API**。具体持久路径/摘要Schema、原生恢复调用、前后判据仍须绑定真实实现。原源码的阶段前guard、INTENT、阶段后guard及COMPLETE记录语义继承；保存COMPLETE失败时必须从原效果读回收敛，不能重新执行效果。

### 可恢复准备与完成的区分

- B3内部03为准备，04–05为停用/替换屏障，06–09为配置完成；内部任何CP都只允许恢复，不允许提前冻结整个B3。B3不等待B4–B7完成后才提交。
- B7仅在B6提交后进入，14–15为激活恢复点，16后才最终关闭。B7不再提供B3的前置工作。
- B4验收可使用本批有限探针，但“sandbox就绪”不等于阶段15服务已启动；不能将同一长驻进程先在B4启动、再在B7重复启动。有限验收进程和阶段15进程身份必须分别记录，不能以新探针替代原阶段完成判据。
- 这里是顺序合法性证明，不是原16阶段可按此Plan恢复的实现证明。原冻结入口是否支持跨进程分批、原guard是否允许批间暂停仍 **NOT_VERIFIED**；不能把原整条入口在每批重新运行。

### 七个最小完整功能节点仍未成立的反证及备选

旧归属存在B3→B7→B3直接循环；本修订消除了该图环。**顺序无环不等于七批均为最小完整功能**：B3的03–09仍含准备、停用、目标替换和权限配置多个效果，且暂停于CP04/05可能使应用不可用；缺少独立关闭/可用性与恢复证据，不能声称后批失败必不影响前批。

保留七个DRAFT工作包；暂不把它们直接编译为七次安装。若B3原语义不能独立闭合，最小局部备选是把B3细分为03、04–05、06–09三个有恢复屏障的子段（总计9个顺序段），但这些只是恢复子段，**也不自动成为9个独立完整功能节点**。在明确批间可暂停及原生恢复证据前，受影响的03–16只能视为一个未关闭迁移事务；B1/B2的独立制品/证据成果可以保留，不因后段失败重装。不得用改名或增加节点数伪造独立性。

本小任务结论：候选序列 **ORDER_VALID / ACYCLIC**；独立批次闭合、资源隔离、原阶段等价和英国安装 **NOT_VERIFIED / NOT_EXECUTED**。七批继续 **DRAFT / NOT_INSTALLABLE**。

## B3阶段03–09：真实接口与恢复缺口（PR17 #6280660117）

核对源码固定于 `6532479c5993bfc2e61ef3bcee8978cfa11ef7a3`，只读静态接口证据；不是现场状态证明。旧epoch7宿主实现与新容器组件不是等价替换。本节不删除、放宽原guard，不把旧单次机制扩为新许可。

### 首次入口、状态及共同guard

首次装配为 [epoch7_host_factory.py:599](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_host_factory.py#L599)，经 [epoch7_host_driver.py:14](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_host_driver.py#L14) 构造具体对象；装配本身不执行。
实际整序列调用为 [epoch7_recovery_sequence.py:533](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_recovery_sequence.py#L533)：先校验context/approval、持有安装锁、preflight、gate；要求outer和inner均不存在，再O_EXCL创建两记录并按PHASES执行。没有B3-only首次入口，也没有在09后暂停的公开参数。

`resume_once`同对象重复调用触发`SEQUENCE_OBJECT_ALREADY_USED`；新对象遇任一既有/部分记录触发`EXISTING_ATTEMPT_OR_OUTER_RECEIPT_HOLD`。
[epoch7_injected_recovery.py:160](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_injected_recovery.py#L160)的create拒绝既有记录，save要求当前对象已有last且未poisoned，并做完整记录CAS；没有从盘加载后采纳在途记录的公开恢复方法。
[epoch7_host_phases.py:207](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_host_phases.py#L207)要求准确outer INTENT和completed前缀。
[epoch7_injected_recovery.py:103](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_injected_recovery.py#L103)读回锁、批准、保留pins、非ACTIVE激活、当前generation/targets、原sandbox、身份和排他证据；current_targets/current_generation等会在执行中更新，但新实例从snapshot重置内存，不能推断可重建原恢复上下文。

共同持久资源：`epoch7-recovery-sequence.json`（outer）、`epoch7-recovery-execution.json`（inner）位于fs.TRANSACTION：
`/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5`。
这些是旧宿主代码常量，**不授权容器挂载或访问**。
安装锁`/run/xuanjun-p2-install.lock`；激活锁`/var/lib/xuanjun-development/activation/activation.lock`。激活描述符/journal由既有ActivationStore拥有，确切后端路径本节未展开核实，标UNKNOWN，不自行造路径。

### 每阶段实际资源和唯一拥有者

“所有者”为同一driver内部唯一效果对象；不是允许第二Writer。outer统一由OuterJournal写，inner统一由BoundJournal受保护CAS写。下表恢复判据是需核对的实际状态，**没有实现就不能执行续接**。

| 阶段 / 首次效果入口 | 真实读取与写入 | 唯一效果所有者及原guard | 已有记录与恢复判据 / 缺口 |
| --- | --- | --- | --- |
| 03 rebind_prepared_epoch | 读snapshot/candidate、native当前及epoch5/epoch3证明；ActivationStore先append epoch8 PREPARED再发布descriptor；备份epoch7-prior-native-binding.json，替换/etc/xuanjun-development/p2-native-binding.json；O_EXCL发布epoch8-tls-renewal-candidate.json | CoreHostPhases.rebind_prepared_epoch，_enter一次性；rebind_prepared_epoch7要求7→8、同canonical身份、准确旧head及锁；多资源不是单事务 | outer INTENT/COMPLETE与native备份存在；append完成descriptor未发布、native已换但TLS候选未发布均可能部分成功。需分别读回激活两头/native/候选；没有此阶段公开跨进程恢复入口 |
| 04 quiesce_exact_epoch | 读取observer.quiescence的identity_verified/coordinator_inactive/parent_unit_inactive/cgroups_empty/restart_inhibited；写ActivationStore PREPARED→QUIESCED | CoreHostPhases.quiesce_exact_epoch。此方法本身不调用systemctl stop；它要求静止证明，不负责凭空制造静止环境 | outer证据摘要及激活状态；进程和抑制状态须独立读回。不能把重复transition当作恢复；静止前提在隔离适配未实现 |
| 05 replace_retained_targets | 读gate.delta中24目标及准确payload；仅非RETAIN成员写入；逐目标先备份epoch7-target-before-<path SHA256>.private，再exact replace；不写应用DB | InjectedDriver.phase→RetainedTargetDelta.apply→ProtectedFilesystem；要求inner恰ADMITTED、fresh PROVISION、未started；每目标backup和before/after CAS | epoch8-runtime-provisioning.json逐目标PENDING/BACKUP_INTENT/REPLACE_INTENT/DONE，inner TARGET_DELTA_COMPLETE带provision摘要；已替换未写DONE必须查备份、实际目标和原意图。现有apply拒绝重入/既有PROVISION，不具备恢复采纳 |
| 06 publish_reviewed_identities | 仅gate.additions明确的/etc/xuanjun-development/p2-owner-process-identity.json与p2-ledger-server-identity.json；校验原absence、payload摘要；临时文件O_EXCL创建，最终通过os.link原子不覆盖发布，再unlink临时名并fsync父目录 | InjectedDriver.phase循环IdentityPublication.apply；只能两固定path；current_additive_targets须未发布，journal须不存在 | epoch7-owner-identity-publication.json、epoch7-server-identity-publication.json及inner identity_receipts；第一身份已发第二未发需逐个核验，不能覆盖已发身份；os.link后、临时名unlink前崩溃可能留下双硬链接（nlink=2），pin loader的nlink=1检查拒绝并保持HOLD，不能宣称自动恢复。空additions为受批准no-op；实际host compose要求两项，不能拿空列表代替 |
| 07 change_generation_access | 仅/var/lib/xuanjun-development/generations/1目录，保持inode/owner、按delta改mode至0700，不改state.sqlite | GenerationAccessStep.apply→chmod_generation_exact；inner须指定前阶段、准确before、无既有generation journal；无chown/递归/rollback/retry | epoch7-generation-access.json含before/after/observed_after/receipt，inner GENERATION_ACCESS_COMPLETE引用摘要；chmod成功而日志未完成需实际metadata核验；公开恢复入口未实现 |
| 08 apply_reviewed_access | 仅/opt/xuanjun-control-releases目录及/etc/xuanjun-development/p2-native-ledger-client.json；读准确owner/inode/ACL/default ACL及文件摘要，写system.posix_acl_access并fsync | ExactAccessApplier.__call__；ACL_ONE_EXACT_ATTEMPT、两固定path、before resolver、两次CAS、live guard和after不变项 | observed与started存在对象内存；outer保存聚合摘要，未见此applier独立持久逐路径意图/结果。第一path改完第二未改需真实ACL分项取证；不能靠重建对象或before模板续跑 |
| 09 rebind_tls_metadata_only | 读tls-lifecycle.json及新TLS config、保留证书/tree摘要；O_EXCL备份epoch7-prior-tls-lifecycle.json，CAS替换原TLS journal；不签发/续期/dry-run | CoreHostPhases.rebind_tls_metadata_only，_enter、准确phase/live guard，写前后TLS内容保持，返回严格tls_change | outer摘要与原TLS备份；替换完成outer未提交需校验原/新journal及证书tree，不重写已发布结果；公开阶段恢复入口未实现 |

源码依据：
- 03/04/09：[epoch7_host_phases.py:519](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_host_phases.py#L519)、[epoch7_host_phases.py:547](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_host_phases.py#L547)、[epoch7_host_phases.py:557](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_host_phases.py#L557)。
- 05/06/07：[epoch7_injected_recovery.py:233](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_injected_recovery.py#L233)、[epoch7_injected_recovery.py:332](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_injected_recovery.py#L332)、[epoch7_injected_recovery.py:295](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_injected_recovery.py#L295)。
- 05准确24路径全集为epoch7_delta.TARGETS（不能扩大为整个/etc或systemd目录），更改子集来自gate.delta；备份和替换判据见[epoch7_protected_fs.py:299](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_protected_fs.py#L299)与[epoch7_protected_fs.py:319](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_protected_fs.py#L319)。
- 08：[epoch7_exact_access.py:64](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_exact_access.py#L64)和[epoch7_exact_access.py:117](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6532479c5993bfc2e61ef3bcee8978cfa11ef7a3/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_exact_access.py#L117)。

跨B1/B3共享资源已识别：B1阶段01创建release内容并观察父目录；B3/08修改同一父目录ACL。因此“B1整个目录metadata永远不变”不成立。候选所有权必须按字段区分：B1拥有release文件内容；B3独占两指定path的ACL（及07指定generation mode）；B3拥有03重绑和04的PREPARED→QUIESCED转换；B7拥有14的QUIESCED→ACTIVE激活转换。03/04/14共享同一ActivationStore。只允许同一受控Store串行操作，不允许两个适配器独立写后端。目录ACL改变是否影响B1访问、原阶段01回执的适用性及字段级冻结判据，仍NOT_VERIFIED。

### 可直接复用与最小缺口接口（仅设计，不新增代码）

直接复用：准确Phase顺序、原context/guard和受保护IO、备份命名与hash、单目标CAS及写后读回、原失败先containment再发布诊断/HOLD的流程。containment可能停服务/恢复mask或sandbox，恢复核验必须查看containment结果，不能假定只发生失败阶段效果。poisoned journal、UNKNOWN cleanup或锁释放不明必须保留HOLD。
这些旧单次实现有价值，但不构成B3可分批恢复。

最小待适配契约（**NOT_IMPLEMENTED，本节命名是提议**）：
1. 只读取证接口：给定同一context/attempt及原outer/inner记录引用，返回受保护metadata、bytes/hash、逐资源before/after/conflict/unknown和containment状态；不执行写入，不接收任意路径。
2. 恢复判定接口：核验context/Plan、阶段completed前缀、原效果身份、原备份/回执与实际状态；明确ALREADY_APPLIED / PROVEN_NOT_APPLIED / UNKNOWN，不能用不存在本地回执推断无效果。
3. 同操作收敛接口：仅在原恢复机制允许时，按原CAS补原缺失结果，不重新创建claim、不重新消费Grant、不重放已成功效果；需要后续原阶段执行时须有明确持久状态重建、授权和batch停点支持。
在所核sequence/Core/retained/access接口内，以上跨进程恢复采纳与阶段09停点未实现。仓库其他Attempt5/原生恢复机制可能提供相关能力，**本轮未证明其覆盖这些具体B3对象与状态**，不能全库断言“没有恢复”，也不能直接拿其名称当作已接通。

### 最小离线恢复用例清单（计划，全部NOT_EXECUTED）

只用明确ISOLATED_TEST_ONLY样本、私有临时文件和可注入后端；不使用真实宿主路径/生产批准或Key。已有未变通过用例继承，不重复全量。

| 用例 | 注入窗口与应验结果 |
| --- | --- |
| R0 原入口负例 | 同driver重调、重建driver遇outer-only/inner-only/部分记录；原guard拒绝且不启动效果；不能为制造PASS修改guard |
| R03 激活及native分步 | activation append后/descriptor发布前、native替换后/TLS候选前中断；新进程只读取证，不重复append/替换；未知保持HOLD |
| R04 静止证明 | 不全静止、身份漂移或抑制丢失拒绝；QUIESCED提交后响应丢失只能读回，不再transition |
| R05 单目标替换 | 备份后、replace后/DONE前、若干DONE后中断；旧备份保留，已正确目标不覆盖；无恢复实现先断言HOLD |
| R06 两身份 | 第一发布成功第二未发、单身份发布后journal未确认，以及os.link后临时名unlink前进程崩溃留下nlink=2；预期pin检查HOLD，保留原记录/两链接现场，不盲目删除链接或重复发布；自动恢复NOT_IMPLEMENTED |
| R07 chmod | chmod后receipt/inner提交前中断；inode/owner/DB不变；mode正确不代表可绕journal guard重跑 |
| R08 ACL部分 | 第一path ACL已改第二未改；跨进程发现内存observed丢失，按实际路径判定；覆盖路径替换/ACL冲突；不能据聚合摘要推断全完成 |
| R09 TLS元数据 | TLS journal已换outer COMPLETE未保存；旧备份/证书tree不变，零TLS生命周期调用；缺/改备份HOLD |
| RX 共同收敛 | journal CAS漂移、poisoned、containment UNKNOWN、锁释放不明；不产生第二效果；09完成仍不得把无暂停能力的整序列宣称已分批关闭 |

本轮仅文档与源码一致性检查；没有运行上述恢复测试。B3恢复能力 **PARTIAL / NOT_VERIFIED**，七批仍 **DRAFT / NOT_INSTALLABLE**，安装与服务器操作 **NOT_EXECUTED**。

## 后续执行与政策边界

当前只是文档增量；七批已安装数 **0/7**，原16阶段执行数 **0/16**（沿用已知现场状态，本轮未做英国读取）。原生产AuthorityStore仍UNKNOWN，生产切换不在本任务。
新隔离协调器不新增五次额度或强制Grant准入；旧生产Grant/历史消费、数据库/WAL保留，不扩权。
每轮10次失败或1小时先到上报Dots并提出替代方法；同根因30分钟提前换思路。上报门槛不是安装额度，通知未真实接通标UNAVAILABLE。
Dots调度和节点验收；Work归集/集成/打包及后续获授权安装。本轮不新增独立人工审签，平台必需检查保留；评论自动唤醒NOT_VERIFIED。

详细环境和调度索引：[总集成记录](../../docs/P2_REWRITE_DISPATCH_20261020.md)。

## B2隔离证据导入准备（PR17 #6281853309）

B1已按[真实回执6281846615](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/17#issuecomment-6281846615)限定通过，继承f314，不重装。本节仅本轮B2准备，不回写上文历史快照为生产成功。

`evidence_import.py`只补B2来源绑定与确定性tar/INDEX适配；正式文件安装、inspect和部分安装recover均复用只读ea31制品组件，不新增安装器或调度账本。固定安装范围仅ISOLATED_TEST_ONLY；INDEX始终production_history=false，未知来源/缺摘要为UNKNOWN，不当作生产历史。测试用SYNTHETIC_TEST_ONLY与真实ISOLATED_B1_EVIDENCE分开记录。

| 来源/目标 | 准确绑定与当前状态 |
| --- | --- |
| 原receipt | `/var/lib/xuanjun-p2-isolated-test/artifacts/.p2_artifacts/receipts/p2-uk-isolated-20261020--b1-release.json`；SHA256 `2aa0616f8d9cc57e4dc367198fcb40b1d9cfe88ffa46221273c62cf4ad6e069a` |
| 原summary | `/var/lib/xuanjun-p2-isolated-test/logs/b1-first-install-20261020/summary.json`；真实文件SHA256仍UNKNOWN，不能用终端附件摘要替代 |
| 本批唯一容器RW根（待确认） | `/var/lib/xuanjun-p2-isolated-test/b2-evidence`，请求installation=p2-uk-isolated-20261020、batch=b2-preserve、attempt=b2-preserve-a1；目录/属主创建尚未授权或执行 |
| 独立副本/索引 | RW根下`versions/p2-uk-isolated-20261020--b2-preserve/{b1-receipt.json,b1-summary.json,INDEX.json}`；0600，后续消费者只读挂载 |
| 本批恢复点 | RW根下`b2-input.tar`、`b2-intent.json`及ea31原journal/snapshot/receipt/recovery；不覆盖旧记录。prepare发布中断残留保留，恢复按原spec摘要收敛；已提交重复导入不增加副本或回执 |

来源映射必须在最终命令冻结：原receipt与summary属主可能不同，不能把RO挂载等同于UID1002有读取权，更不能chmod原件。拟由获准宿主只读取两原件，核准确摘要/前后身份后生成本批来源快照；快照单独映射`/source` RO，ea31工具RO，只有b2-evidence RW。不挂B1整个根或生产历史；快照/工具准确host路径与元数据尚待最终操作绑定，当前不是可执行安装命令。

适配器请求除ea31原身份/root字段和inputs={}外，需source_root、origin_scope及sources两项，各含sha256与origin_ref；三动作使用同一份spec。来源路径仅相对source_root的两个固定文件名，读取逐级O_NOFOLLOW、常规文件/大小/读前后身份校验。原子不覆盖发布意图后，inspect/recover按原spec调用ea31，不依赖源件继续可用、不修改B1原件；归属或摘要冲突UNKNOWN，禁止清空重导。

本轮补定向合成测试：独立进程execute/inspect/recover及重复导入、真实SIGKILL后两窗口恢复（archive发布后/intent前及ea31第一文件落盘后）、未知来源、源摘要改变、身份改变拒绝、源内容/权限/inode/mtime不变。它们不构成英国B2验收。真实summary摘要缺失前，最终安装spec/包摘要/命令保持NOT_READY；仅可交两固定原件的最小只读摘要采集。B2现场操作NOT_EXECUTED，不增加B1/协调器/混合CLI/P3前置。
