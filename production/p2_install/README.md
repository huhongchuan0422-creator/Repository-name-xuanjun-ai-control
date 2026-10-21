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

## R03只读取证最小增量（PR17 #6282306415）

B1/B2继承真实检查点#6281846615/#6282254897，不重装。B3整体仍DRAFT。
新增 `production/p2_install/rebind_readback.py`，仅检查显式冻结的
`ISOLATED_TEST_ONLY` 私有证据镜像；不是03首次入口或同操作补写入口。
没有调用旧03–09、ActivationStore.reconcile/_locked/_append、native替换、TLS发布或Grant。

镜像根必须为本用户0700、规范绝对路径，叶名以`p2-b3-readback-`开头。
镜像内只读取原绝对资源路径的相对副本，八资源固定为：
activation/active.json、epochs.jsonl、既有activation.lock；
原native binding；原transaction下prior-native备份、TLS候选、outer及inner记录。
准确原路径由源码RESOURCES固定，调用者不能增加路径。实际生产路径不被直接打开。
只用O_RDONLY/NOFOLLOW、逐级受保护父目录和既有锁非阻塞flock；
缺锁不创建、不chmod。读取可更新atime；内容、inode、mtime、ctime、权限及目录结构不写。

输入为stdin JSON及外部固定的`--spec-sha256`（对排序、无空白、无末尾换行JSON计算SHA256）。
字段：schema=1、scope、root、phase=rebind_prepared_epoch、固定transaction_id、
context_sha256、原journal binding、before、after、原rebind proof、source_refs。
before包含原activation、完整旧journal SHA及native SHA；
after包含候选activation、native SHA及TLS候选SHA。
source_refs必须明确context/snapshot/candidate/plan/outer/inner的原引用及SHA。
outer/inner保持原canonical JSON加换行、0600及原记录结构；核同context/binding、03 INTENT或COMPLETE及准确completed前缀。
原proof与journal最终append关联，旧完整链SHA须匹配，备份必须匹配旧native。
输入摘要是调用者冻结身份，不是审批签名；引用字段本身不证明历史批准真实性或现场guard已通过。

复用未修改的原activation_control.py（SHA256
`169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4`）
validate/head/_journal/_read_descriptor_unlocked校验原schema、单调epoch及hash链。
不实例化CoreHostPhases、不重建旧写入对象，也不放宽原guard。

| 观测 | 阶段判定 | 后续 |
| --- | --- | --- |
| 日志已append8、descriptor仍7；native旧、备份/TLS未发布 | UNKNOWN，窗口ACTIVATION_APPEND_BEFORE_DESCRIPTOR | HOLD；不可重复append |
| 日志/descriptor均8、native新且原备份准确、TLS未发布 | UNKNOWN，窗口NATIVE_REPLACED_BEFORE_TLS_CANDIDATE | HOLD；不可重复替换 |
| 日志/descriptor/native/备份/TLS均与冻结after相符 | ALREADY_APPLIED | 仅效果观测；不补outer、不宣称B3 COMMITTED |
| 完整旧日志正向匹配、descriptor/native旧、03 INTENT、无新备份/TLS | PROVEN_NOT_APPLIED | 仅当前冻结资源判定；不是重试许可 |
| 缺原件/备份/引用、链损坏、绑定漂移、锁忙、containment或跨读变化 | UNKNOWN | HOLD；保留原现场 |

所有输出decision始终HOLD、write_authority=false。分类不能替代原guard、不能证明无历史未决事务。
本轮没有现场镜像/已认证context、snapshot、candidate、plan及真实03记录，因此现场R03=NOT_EXECUTED，
不把合成fixture冒充英国恢复通过；后续现场证据冻结/受控收敛仍未完成。

定向验收：`python -B tests/p2_install/test_rebind_readback.py -v`；
14项独立进程测试，包括两处SIGKILL fixture生产进程→新CLI读取、完整/未应用状态、
原件和备份缺失、损坏链、错误proof/请求/context、完成记录冲突、锁竞争、链接及权限。
每次CLI读前后核文件摘要/metadata和文件集合不变。fixture仅原schema合成证据，
不运行原rebind方法；不代表真实旧guard执行或生产准入已验收。
目标保持容器Python3.11（CI3.11/3.12）；宿主3.6.8不升级。

## R03输入来源冻结（PR17 #6282452861）

准确清单：[P2_B3_R03_INPUT_SOURCES_20261020.json](../../docs/P2_B3_R03_INPUT_SOURCES_20261020.json)。
本清单是静态来源索引，不是账本、安装请求或历史批准。
基线4df742208d8bee3bd7b61c0eb4c226e5133f879d；13项来源逐字节SHA256与Git Blob复算一致。
复用上轮双Python各14项CI，不重跑B1/B2或未变分类器。

已取得原schema/工厂/阶段源码和保存R7有限probe包；三组既有英国私有plan/seed仅继承定位及SHA。
保存packet的SHA为45b832dce9577b49e6ee718f1637862eebd775c6c10f87d9150ed0a87476fdf7，
其snapshot引用9bc4a56f28264698058245f47bce8747d9ee96218076c7bbb25d4f1b7aefd4d8
不是完整snapshot内容。原packet README明确私有完整observation不可用，plan准备另行处理、install_admission=NOT_GRANTED。
旧Stage-A交付也写private_plan=NOT_READ；不能据其成功probe或归档补出R03上下文。

同context的原context、完整snapshot、source-derived candidate、准确plan、outer/inner、
原native证明/完整激活链及03效果内容仍UNKNOWN；不把三组plan任挑一组和packet摘要拼接。
具体八项读回资源允许清单、三项原native支持证明、准确版本及每组私有定位见清单。
受限仓库搜索不证明英国私有文件不存在，本轮没有读取服务器。

下一最小操作仅设计为对既有六份private JSON及准确配套kit进行一次有界私有来源关联提取；
不实例化Driver、不调Grant/append/native替换/整序列，只输出脱敏身份摘要及缺项。
若需容器读取root0600私有原件，必须在具体操作中列出宿主root读取、新只读副本和权限映射，不能仅挂载就声称UID1002可读；
此轮未提交或执行服务器命令。缺历史仍UNKNOWN，不初始化空生产历史。

可选新身份仅为DRAFT_NOT_ADOPTED：
`ISOLATED_NEW:p2-uk-isolated-20261020:b3-r03-source-v1`，
用途为把B1实际release绑定到新声明的非激活隔离候选，不能标旧epoch恢复。
现有分类器固定旧TX及7→8，尚不能接受新身份；不得调用fixture()造1..7历史来凑兼容。
须明确选择历史来源关联，或在原03功能映射内定义新隔离初始化及真实config/binary/instance/DB/socket输入；
不默许改guard、另建AuthorityStore/账本或增加第八批。B3继续DRAFT，本轮server_operations=NOT_EXECUTED。

## Owner选择B：B3新隔离初始化准备（PR17 #6282590952）

继承2816e74fb05e915023c207ba6e911784875e4233、真实B1/B2；停止追旧六文件作为本次前置。
旧R03历史保持UNKNOWN，原7→8 guard/分类器不改；新目标明确ISOLATED_NEW，不造旧epoch成功记录。
固定输入见[PREPARATION.json](../../docs/p2-b3-initialize-20261020/PREPARATION.json)，
准确1056字节bootstrap配置见[binding-config.json](../../docs/p2-b3-initialize-20261020/binding-config.json)，
SHA256 f772644e9a8587cda9e0df4c1e53dc64d647195407d29c69ef52625ebb0160ad。
该配置是新隔离身份/路径绑定元数据，非应用进程配置；三个start/create_db/bind_socket开关均false。

### 最小实际用途与输入

本次最小子检查点：将B1真实release映射为一个新epoch1 PREPARED候选，供原后续阶段读回准确身份，
实现退出新进程inspect、同身份recover。不是旧epoch7恢复、不是整B3 03–09 COMMITTED，也不启动P3。
release直接继承已安装B1 MANIFEST SHA591855b35c820c486ae07bbb91e681b983a3a2310feaedb57ae7c87fc9b66592；
runtime模块继承499bcc43的真实B1文件SHA3993ab9bd0073a91d8110814e694b2c402ef5b53efb544a3bc44a1debd4231a1。
新instance=0891a51b-feea-520e-850a-c8fc7c840d94；新预留ledger_uuid=093955da-4b7d-5c8d-b85e-3adaa304c675。
二者按显式新identity做UUID5声明，不是观察到的旧实例/数据库，字符串摘要在PREPARATION中固定。
DB=/var/lib/xuanjun-p2-isolated-test/b3-initialize/data/ledger.sqlite3，仅预留、未创建，内容SHA=NOT_APPLICABLE_BEFORE_CREATION；
socket同根run/ledger.sock，仅预留、未bind，Unix socket无普通文件内容SHA；路径摘要单列，不替代内容摘要。
DB建立/打开仍在原B6后续阶段，socket/服务仍按原运行阶段，不提前加入本次初始化。

Owner实测已补齐固定镜像内/usr/bin/python3.11：canonical path同名、6809944字节、SHA256 9bee109da0dce17a7c9eeaca9f420cc6770a9fe143b9382d73bd22fe59b21a5f（#6282808058）；
既有3.11.2/UID1002/镜像ID不是ELF摘要。没有填占位SHA冒充冻结完成。
如需补取，准备命令仅创建一个无挂载/无网络/只读根的临时容器，读取它自身Python文件，
使用唯一名字+本次label限定异常清理；Docker会有临时元数据/overlay，不能称完全零写。本轮未执行。

### 准确顺序及待确认实际动作（尚无现场执行）

1. 实测binary pin已纳入完整expected descriptor及request；不重复取证或全环境核验。
2. 仅新增host b3-input-20261020只读输入（root:1002，目录0550/文件0440）及logs/b3-initialize-20261020（root0700）；
   工具复用原activation_control.py准确SHA169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4，
   不覆盖B1源码。仅宿主root读B1原回执/manifest并生成本次独立只读证据副本。
3. 仅新增b3-initialize及activation/data/run私有目录1002:1002 0700；宿主base仍root:root0700，无递归chmod/chown。
   不创建DB，不生成WAL，不bind socket，不安装systemd或启动业务进程。
4. 容器只挂本次input只读、本次root读写；固定镜像、UID1002、network none、read-only root、cap-drop ALL、
   no-new-privileges、512MiB/swap1GiB/pids96。Python3.11运行；宿主3.6.8不升级。
5. 必要薄适配已实现于initialize.py：O_EXCL/不覆盖发布本次intent与config、同请求冲突校验、对原Store精确调度及不可变回执。
   不新增安装器/账本/调度系统。fresh只在本次新根和已证实无历史时，以owner_uid=1002构造ActivationStore，再调用原prepare方法并指定expected_epoch=0，
   真正产生一条新epoch1 PREPARED日志及descriptor；保留原Store写前append、fsync、descriptor发布格式。
6. 独立进程inspect读回全字段/链/原receipt。原Store.read内部锁可能O_CREAT/fchmod已有本次锁0644，
   所以不把该动作称绝对只读；不允许inspect为缺历史创建descriptor。
7. 同请求recover先校验本次intent、config、所有expected身份、完整新journal且仅一条epoch1记录；
   append完成descriptor前中断，仅原Store.reconcile补同一descriptor，不重新prepare、不生成epoch2。
   descriptor及receipt已完成则只返回原回执；未知身份/损坏/冲突HOLD，保留原文件、临时文件及日志，不能清空重来。
8. 每步宿主保留stdout/stderr、容器状态、字段/摘要和恢复检查点；COMMITTED只指该初始化子检查点。
   全B3还需按原03–09对照验收，不能将本次子结果标整批通过。

原03–09对照逐项在PREPARATION.phase_mapping固定：03按Owner新初始化映射；
04旧实例停用不在本子操作且不能冒充生产静止PASS；05旧target替换不在本子操作；
06仅新身份声明不发布宿主Owner/Signer；07/08只限新私有目录不改B1/B2/旧generation/ACL；
09不消费或修改TLS，后续确有需求仍沿原B3内部处理，不新增第八批。

现状：真实binary、薄适配、固定request与14项双Python Hosted验收已交付；英国安装仍NOT_EXECUTED。
原14例/8例及B1/B2未变结果复用，不重复全审；本轮资料新增只做结构、摘要、身份和路径长度检查。
实际服务器目录/进程/权限变更全部NOT_EXECUTED，现场操作须按本次Owner要求待确认。

## B3薄适配最终交付（PR17 #6282808058/#6282750907）

固定入口为`production/p2_install/initialize.py execute|inspect|recover --request-sha256 <固定摘要>`，stdin同一request。
[最终固定命令/动作清单](../../docs/p2-b3-initialize-20261020/FINAL_OPERATION.md)；
[准确request](../../docs/p2-b3-initialize-20261020/request.json)。
request SHA256=d843a697e17e516aa92cb47a4c507527152f65d25b11ccdcc43d27b7fd878dbb；
预期原commit receipt SHA256=bede2ebc9f9c5458c92307c974358eb61947e7ec80a9611cc76735891ffae433。
外部请求不可加载模块；固定源码原Store逐字节验签，binary须匹配实际解释器path/bytes/SHA，缺失或漂移HOLD。
new epoch1完整历史/同身份核准后才可reconcile；不覆盖异身份descriptor，不追加epoch2。
DB/socket若意外存在，写前HOLD，不将其收为本批成果。

Hosted [39366424078](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39366424078)
head5752051795755e4a27ea5863e2a731e24f566f92：Python3.11/3.12各14项PASS，已读实际日志。
测试SIGKILL对象包含真实原Store.prepare在append之后、descriptor之前运行的子进程；
测试解释器是Hosted原字节的私有0500副本，未放宽文件权限检查，不冒充英国binary。
前序Hosted失败39366059105/39366255180/39366332332保留，具体FILE_PROTECTION指向Hosted group-writable interpreter。
旧14例/8例未重复；本轮新增14例独立于旧R03分类器。

可取得制品为固定Commit1f455da15131ddd885439f8903c85e14251663b7下
scripts/p2_b3_owner_initialize_20261020.py；78182字节，
SHA25636399b8c57a4acf116c8074a52acab34fd3ee258e41f31edb1f93ea6e629c4ad。
内含原Store、薄适配、固定request及预期文件；不是仅scratch路径。
宿主命令Python3.6语法/三动作stdin/制品内源码SHA核对PASS；本地Docker和英国安装NOT_EXECUTED。
成功仅标B3_NEW_INITIALIZATION_SUBCHECKPOINT_PASS且full_b3_complete=false，实际动作待Owner确认。

## B3真实初始化后的完整收口范围（PR17 #6283178324）

基线6a5548963c7f1a504a2f1347f7ca1a63a8f30afb，Owner选择B继续有效。
继承真实验收#6283178324：北京时间2026-10-20 12:07:24输出；
原终端源文件29575字节SHA2561a6a66fe2e7a01e206f3ed37af1e9fac185c50a5c854b585b5c34eeb5894914e。
三独立容器execute/inspect/recover均COMMITTED/exit0/已退出，三次10文件metadata一致；
seq1/epoch1/generation1/PREPARED，descriptor SHA6d3c95521492ba90640e723081a8d0f21fa2a2bfb3c896c0708ecb86e8ef93f1；
原receipt SHAbede2ebc9f9c5458c92307c974358eb61947e7ec80a9611cc76735891ffae433、
inode1844889、mtime_ns1792469243126487097。
准确summary=/var/lib/xuanjun-p2-isolated-test/logs/b3-initialize-20261020/summary.json。
终端附件SHA不是summary.json SHA；后者UNKNOWN，不能混用。
B1未变、无DB/socket、base未变仅继承固定脚本强制断言通过；未另取得独立原件快照。
实机SIGKILL=NOT_EXECUTED，既有Hosted注入不冒称现场注入。

### 完成、余项及旧动作适用性

| 原阶段 | 已有真实成果 / 新隔离语义 | 剩余必要步骤与验收 | 安装/只读/不适用的界线 |
| --- | --- | --- | --- |
| 03 | 新epoch1/PREPARED及固定config/request/原receipt已真实完成 | 仅引用该CP03，不再prepare/reconcile或重跑三CLI | 0次重复安装；旧7→8仍UNKNOWN，不作为前置 |
| 04 | 本次三个受控容器均已退出；初始化没有启动业务服务 | 将证据范围固定到本批新instance；核后续命令不启动/停用业务，保存CP04适用性记录 | 只读/适用性核验；不要求旧生产Writer静止，不执行systemctl stop。不能由此声明全宿主无Writer |
| 05 | 新根已发布bootstrap config/intent并绑定真实B1 release | 补齐实际供原B4消费的候选运行配置：固定真实入口/argv/cwd/env/health、版本/摘要及路径映射；发布到独立新配置路径并跨进程读回 | 必要新配置发布。原旧24目标替换不适用于已声明的新私有根，但缺应用配置不能靠N/A略过 |
| 06 | 新instance/预留ledger_uuid及真实UID1002/Python绑定已有证据 | 冻结并发布新隔离expected identity契约，关联CP03/候选配置与原组件稳定operation/config/receipt引用；实际PID/Socket peer身份保持NOT_STARTED | 必要新身份元数据发布；不伪造已运行进程、不发生产Signer/Owner批准，不写旧/etc身份文件 |
| 07 | 本次base root0700；B3根/data/run为1002:1002 0700按固定断言通过 | 对候选配置的准确父目录及后续读写主体做最小访问核验；新路径若需新增只在本批根内列清 | 默认只读检查；仅必要新路径创建/权限设置可合并。旧generation chmod不适用于新根，不能修改B1/B2 |
| 08 | 私有输入/输出挂载及uid/gid已实际核验 | 对B4交接所需精确路径补同UID可读写/非授权主体拒绝的证据，确认B1/B2原内容和权限继承边界 | 定向访问检查及必要新路径发布；不setfacl旧host路径、不以当前元数据直接冒称全部访问有效 |
| 09 | 初始化未消费/变更TLS；原Store只处理新PREPARED | 对固定候选运行配置判定是否涉及TLS：若明确只用隔离Unix socket且无TLS客户端/证书需求，保存有依据的限定N/A；若实际需要TLS，须先冻结真实配置/证书来源与只读元数据契约，再纳入本批计划 | 当前TLS适用性未闭合，不能先写PASS/N/A；不签发/续期/dry-run，不操作生产TLS |

04/05/07/08中的旧路径不适用结论只针对本次新私有根与本批声明效果，不能删除旧历史保护或改变原生产合同。
06目前只是逻辑身份声明，尚非旧两份进程身份文件等价验收。
09不是新增TLS签发步骤；是否需要只读取证由实际候选配置决定。

### 已确定的复用资产

- CP03现场：固定1f455da制品、6a554896交付、原receipt及本批summary；不重装。
- 制品ea31dbbec2a8710b964efb38fa2975684bbd9739，已有不覆盖发布/恢复/前批保护验收复用。
- 运行499bcc43f4c992b21035c22446ccc4d915873fb1，真实B1文件SHA3993ab9bd0073a91d8110814e694b2c402ef5b53efb544a3bc44a1debd4231a1；
  config_payload明确必需argv/cwd并产生env/health/timeout配置；stable_identity提供operation_id/config_sha256/commit_receipt。
- B1协调快照a766dcb307ce738dc508ad153f17e593d1fb7bfb，coordinator SHA1442301368044a98b606c2a4a9787fc521fb85040df2a736c3a9031102ebf8ab；
  journal SHAbfeebc4cb92dd70b9fc526460f669f3897023fc8b31658738ab7f451706af712。
  其既有组件接口/记录格式可复用，不宣称混合CLI/整P2已通，不初始化第二协调账本。
- 新初始化薄适配/原ActivationStore及CI39366424078双Python各14项，均不重写、不重测未变通过项。

本轮只从已有固定B1 tar读取上述三源码并按原manifest核对来源，没有重新安装或跑组件测试。
代码缺口直接来自config_payload实际字段和当前bootstrap配置的差异；不能把bootstrap metadata当作可运行服务配置。
已有服务fixture只能复用其Unix socket探针/恢复测试机制，不能未选定真实入口就把测试fixture伪称最终P2服务。

### 一次集中收口的执行边界与恢复点

拟在同一获准隔离UID/固定镜像/私有根权限内，合成**一条**有界Owner命令，内部严格顺序：
CP03引用核对 → CP04范围/停止状态判据 → CP05配置发布 → CP06身份关联发布 →
CP07新目录访问核验 → CP08交接权限核验 → CP09 TLS适用性结论及整批收口回执。
每步独立记录本次输入摘要、before/after或不适用依据、原证据引用和结果；不重调CP03。
只在该完整范围、具体文件清单、实际动作及测试固定后交确认，不能执行一半再临时加步骤。
不为凑一条命令把需新权限/凭据/TLS签发/服务启动的动作混入：出现这类需求先停在对应项、修订完整清单，不默许审批扩大。

| 中断位置 | 恢复点 |
| --- | --- |
| CP04前/后 | 原CP03 descriptor/receipt保持；只重新读取未定检查，不重新初始化 |
| CP05文件部分发布 | 保留临时/已发布文件及逐文件摘要；同请求核对后只发布缺失项，不覆盖已提交配置 |
| CP06第一身份已发/第二未发 | 分项核对原文件和关联摘要，只补未发布项；未知身份HOLD |
| CP07/08访问证据不全 | 保留已发布配置/身份；只补原精确路径未完成检查，不回滚B1/B2或CP03 |
| CP09前/回执响应丢失 | 重读CP04–08原结果及同配置TLS判据；只发布缺失终态回执，返回原已提交回执 |

恢复机制须沿既有组件不覆盖发布/inspect/recover实现；本节是完整计划，不伪称CP04–09适配或恢复代码已完成。
本次新配置/收口回执新增允许改变的是新文件及其父目录metadata；CP03原十文件内容/inode/mtime/权限继续保留，
不能机械要求整个B3目录以后永远不能增加文件。确切新路径在最终命令冻结前一次列齐。

### Owner次数、准确缺项及工作责任

- **已实际执行：1次B3初始化命令**，内含3个独立容器动作；不是3次Owner安装，更不代表已跑完03–09。
- **现有可直接交付的剩余安装命令：0条。剩余Owner实际执行次数：UNKNOWN。**
- **收口设计目标：正常路径再1条集中Owner命令**，内部CP04–09逐步检查点；当前不是已证明能一次安装完的承诺。
  失败后所需恢复次数依实际错误UNKNOWN；不回到B1/B2/CP03重装。
- Work先在源码/制品侧一次闭合下列缺项，Owner无需追加查旧六文件、Writer/Grant/RAM：

1. **实际运行输入未固定**：B4接收的真实P2程序入口及完整argv/cwd/env/health和代码/配置摘要；
   当前B1快照、Python binary、bootstrap UUID已齐，但bootstrap无argv/cwd，不能当正式启动配置。
2. **新身份/访问/TLS适用性合同未固定**：06的expected/observed分工与消费方；
   07/08精确路径+主体；09是否确有TLS需求。先由选定配置和原组件接口确定，不凭空加生产权限。
3. **CP04–09集中薄接线/定向验收尚未交付**：复用组件，补必要串接与逐步不可变证据；
   一次覆盖发布中断、响应丢失、身份冲突、前批保护，再冻结最终单命令及权限清单。

这三项是源码/输入消费契约缺口，不是新的英国环境前置。
若其中任何项仍UNKNOWN，保持对应项HOLD，不能靠“只剩一条命令”或把不适用写PASS强行关闭B3。
B4–B7/P3、生产切换、真实DB/socket/服务启动不并入本轮B3收口；不新增第八批。
本轮服务器操作/新Hosted/功能测试均NOT_EXECUTED，只有方案/来源一致性检查。


### B3剩余源码本轮实际交付（任务6283318033）

状态PARTIAL，B1/B2/CP03不重装。新增`b3_contracts.py`和`b3_checkpoint.py`，实现原CP03四份来源只读摘要消费、expected/observed身份区分、精确路径主体、实际调用者访问检查、TLS未知HOLD，以及复用原发布原语和原初始化锁的不可变证据留存。留存不等于安装阶段提交，所有输出明确`installation_stage_complete=false`。

源码与实际测试绑定在[DELIVERY.json](../../docs/p2-b3-rest-20261020/DELIVERY.json)。测试版本4fd1cfc008b81ce6d583e6bc2ca2c30c4c0ec8ed；[Hosted 39369848274](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39369848274) SUCCESS，Python3.11/3.12各18通过、1跳过。跳过的是独立UID拒绝探测，不能作为拒绝成功证据。SIGKILL后新进程recover、重复返回原引用、冲突不覆盖及CP03原件不变的定向测试通过。

已查真实p2_attempt5/p2_recovery入口、Provider、Observer和原sandbox消费链。它们分别依赖root、历史签名恢复、Grant/Registry/Signer或固定宿主profile，不存在已确定的本次UID1002新隔离应用消费配置。499运行组件是进程管理器，a766协调器为有限CLI，二者均不自动成为应用服务；不拿测试服务补位。实际argv/cwd/env/health仍UNAVAILABLE，实际TLS仍UNKNOWN。

尚未完成：CP04–09消费方集中接线、正式逐阶段完成回执、实际应用消费验证、独立主体拒绝证据与最终英国操作包。没有最终Owner安装命令，剩余次数UNKNOWN，1条仍为未验证目标。本轮无服务器操作、无权限/凭据/DB/socket/服务变更，不恢复旧历史前置。


### B3真实ledger消费接线（任务6283494928，替代上一轮入口缺项）

真实被装应用明确为原`runtime/stage1/ledger_service.py`，不再要求Owner选择应用。
新增显式非启动检查分支及同目录`ledger_prepared.py`；`production/p2_install/b3_ledger.py`集中接通CP04–09，
复用原只读/发布原语和初始化锁；真实ActivationStore链只读，不prepare/reconcile/transition。
配置与expected identity独立发布；HOLD观察与成功终态分开、请求intent固定、前置回执摘要强制串联。
原build业务AST不变，原ACTIVE/callback UID1004/native及Owner身份/fd3守卫保留，准备profile不能用于启动。

[交付索引](../../docs/p2-b3-ledger-20261020/DELIVERY.json)和[完整动作清单](../../docs/p2-b3-ledger-20261020/OPERATIONS.md)
绑定真实源码、695字节请求、预期配置/profile摘要和Hosted源码制品。
测试源码d011a67d6994971e148c4e81b4c9e7baef481289；[Hosted39371811001](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39371811001)
SUCCESS，Python3.11/3.12各14通过、0跳过，包含实际UID1002准备、实际独立UID拒绝、全顺序/中断/响应丢失。
Hosted证明不替代英国现场：UID1002+cap-drop ALL会在CP08记录UNAVAILABLE/HOLD；独立现场观察及其接入未冻结。
完整B3仍false，最终Owner命令未冻结，次数UNKNOWN；B1/B2/CP03未重装，本轮无英国动作、无新权限/凭据或服务启动。


## B3→B4有限消费接线增量（PR17 #6284216737）

继承英国实际准备回执[#6284188828](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/17#issuecomment-6284188828)，CP03及CP04–09准备子范围已通过，不重装B1/B2/B3。full_b3_complete=false、service_started=false保持；旧历史UNKNOWN不作新前置。

本轮源码0c09b3ae24fcb3e2697a94ef190337a792bca102，Tree5756fee7e7b0e172858af209775637cafcb577c5；[Hosted39377081631](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39377081631) SUCCESS：双Python各11项、精确3.6.8宿主3项、两角色真实Docker及真实宿主main重开验收。复用原111运行文件及499bcc43运行组件原字节。薄适配实际调用原ledger准备CLI与原sandbox policy，不启动正常ledger、不改原guard。有限进程身份为独立role/PID的UID1002，不把未知service_uid或B7启动授权写PASS。

本轮只证明CP10新隔离有限契约；原宿主OpenClaw全sandbox等价NOT_CLAIMED，英国B4运行NOT_EXECUTED。B5/B6/B7/P3未前移。详细固定制品、路径/角色挂载、截止时间、退出/恢复及完整单命令候选见[本批操作清单](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/repair/p2-resumable-install-20261020/docs/p2-b4-20261020/OPERATIONS.md)。新目录/进程动作仍待Owner按完整清单确认，七批总体验收不因本轮Hosted成功自动关闭。


### B6 offline application persistence adapter — corrected preactivation mapping

Original stage source: `recovery-kit-source/helpers/epoch7_runtime_effects.py`, Git blob
`d3dbd171ce33d9d48ed31beaa1622ca38819b54f`: CP12 lines424–455 and CP13 lines457–462.
B6[12,13] precedes B7[14–16]. CP13 requires QUIESCED plus original `ledger-access.json`
state REOPENED, then `runtime_access_check(context, diagnostics)` validated through
`check_observation`. It does NOT require or cause ACTIVE.

The initial25dc5854 eight passing cases are retained as **database recovery/access observations**,
including the ACTIVE-only observation, not proof that preactivation CP13 is wired or complete.
`observe_database_evidence` preserves the original `require_active` and `_assert_activation`
for its legacy CP13-labelled ACTIVE observation. It never gets promoted to original stage13.
The public B6 `observe(request, 'CP12'|'CP13', previous_outcome)` maps phase conditions and
currently returns HOLD. PREPARED and ACTIVE are refused for phase completion. QUIESCED may
produce useful schema/WAL readback evidence but cannot advance without the missing effect
and role/path consumer binding. No accepted path to original CP13 PASS is implemented yet.

| Original predicate | Current isolated object | Binding/result |
|---|---|---|
| Exact QUIESCED descriptor | Original ActivationStore journal+descriptor, full expected identity including DB path | Read-only validated; PREPARED/ACTIVE cannot satisfy preactivation phase |
| CP12 REOPENED and database inode/access effect | Existing DB FD, original Schema, task/event/WAL readback | Readback available; trusted REOPENED effect receipt/transaction identity not supplied, HOLD |
| Original database consumer1003:1006, generation policy0700 and DB0600 | Request current UID/GID and private root checks | Only actual observing subject; B3 preparer1002 is not mapped service1003/callback role; no assumed equivalence, HOLD |
| Original runtime_access_check + context/check_observation | No trusted consumer/context/role-path proof in current isolated request | UNAVAILABLE, HOLD; extra hand-filled runtime_access PASS rejected by strict request fields |
| Legacy CP12 forbids WAL/SHM and performs guarded ownership handoff | New-isolation fixture intentionally preserves nonempty WAL, performs no chown/transfer | Persistence recovery proved separately; access-policy equivalence requires explicit original adapter/evidence, not asserted |

Existing source binding unchanged: `runtime/stage1/execution_ledger.py` SHA256
`8c607f0e2222d906b8450b302dad014a69dfedcb710a257731454e0d97aaf8c6`, blob
`ca96518cda81be2820d693de5a2659a34bb0e802`; original `activation_control.py` SHA256
`169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4`.
Original `_validate_schema`, `_validate_side_schema` and journal/descriptor validation reused;
no duplicated business DB or coordinator journal. The constructor is not called by observation,
because it may create side tables. Fixed original source bytes are verified before loading.

Request fields remain scope=ISOLATED_TEST_ONLY, profile=B6_EXISTING_APPLICATION_DATABASE_OBSERVATION,
root, db_path, uid/gid, activation={descriptor,epoch_journal,lock_path,owner_uid}, expected=full
original descriptor, task_ids. Canonical owner-private isolated paths and regular single-link
DB/WAL/SHM are checked. No missing DB bootstrap, DDL/DML, migration, chown, activation transition,
WAL deletion, task replay or new permit. UNKNOWN only reads back; it never settles unknown external
effects or manufactures REOPENED. Existing DB/WAL/transaction and prior batch receipts are retained.
SQLite may update/create its own SHM on readonly WAL open; no zero-write claim. Query busy timeout1s
and5s SQLite progress deadline retained. Observations are not durable phase COMMITTED receipts.

`python -B tests/p2_install/test_b6_persistence.py -v`: local Python3.12 **12 cases PASS**.
Original8 cases retained: writer SIGKILL leaves nonempty WAL; separate processes read a WAL-only
marker absent from main-only test copy; DB/WAL SHA and prior batch fixture unchanged; missing
DB/schema, wrong identity/subject/path, symlink and original ACTIVE-fence negatives, UNKNOWN no replay.
New4: PREPARED no advance/activation; QUIESCED without trusted effect/access consumer HOLD with
readback and unchanged activation/WAL; ACTIVE observation not accepted as preactivation CP13;
hand-filled access PASS refused. Activation transitions only provision temporary test fixtures.

Remaining integration: trusted isolated CP12 REOPENED effect provenance; service/callback role and
path access mapping; original access checker/context/observation binding; explicit new-isolation
WAL versus legacy no-sidecar/ownership equivalence. Missing contracts block only preactivation
acceptance, not existing persistence tests. B6 CP12/13 site completion NOT_EXECUTED, not closed.
No B7 activation is moved forward; B1–B5/old guard/config remain unchanged. B5 checkpoint waits
for long-term channel, no Owner ferry task.
Historical note for a74a3c: B6 Hosted coverage was not yet included then. Superseded by
3c0d0d8a / run39638090841: both Python3.11/3.12 ran the original12 B6 tests, PASS/zero skip.


### B6 retained B3 history binding (CP12/13 still HOLD)

New B6 entry: `observe_prepared(request, anchors, stage, previous_outcome='KNOWN')`.
It accepts the existing DB observation request **without** `expected`; extra expected/PASS
fields are rejected. `anchors` has exactly `cp03_receipt_sha256` and
`preparation_receipt_sha256`, from the caller's retained, independently obtained receipts.
A caller-supplied digest establishes byte identity, not historical authenticity or a new permit.
No evidence source is inferred merely from a filename or a hand-filled identity.

Read-only `consume_preparation` reuses `b3_contracts.pinned_file` (per-component
O_NOFOLLOW/dirfd, bounded regular-file read, before/after metadata and SHA), the original
B3 safe intent reader and pure `b3_ledger.documents`. It never calls B3 dispatch,
cp03_identity, check_prepared against the current state, reconcile, or an arbitrary callback.
Original terminal/pending two-link publication is accepted (1 or 2 links, no group/other writes),
not mistaken for a corrupt single-link file. The prepared tree remains owner-private.

| Source / binding | Read-only consumption |
|---|---|
| Original commit-receipt.json and binding-config.json | Pinned CP03 receipt -> original config digest; ISOLATED_NEW/PREPARED, installation, UUID/instance/generation, release/config/binary and reserved DB/socket paths |
| Original ActivationStore chain | Original native full journal validation and descriptor/head agreement; first canonical PREPARED record/descriptor match CP03 digests; current same immutable identity/epoch must be QUIESCED, with exactly its original transition; no new epoch or ACTIVE adoption |
| CP04--09 and preparation-receipt.json | Walk backwards from pinned final SHA through CP09 to CP04 and CP03; schema/stage/request/predecessor/status checked; missing/changed links HOLD |
| intent/config/profile/invocation/expected-identity | Original request SHA and canonical intent, CP07 file digests, pure original documents equality, CP05 consumer/invocation, CP06 identity, CP09 TLS binding; role separation unchanged |
| Original application / interpreter bytes | Fixed names from original source map, exact source SHA and bounded binary bytes/SHA; no source execution by consumption, no substitute runtime profile |
| Current DB observation | Derive expected only from history-bound current descriptor, reuse original DB validators/readonly FD readback; check current descriptor again after observation |

Historical PREPARED is not the current-state predicate: current QUIESCED is validated separately.
PREPARED/ACTIVE, descriptor-journal drift, changed instance/generation/release/config/binary,
DB/path escape, symlink ancestor, missing originals, wrong source version, broken SHA chain and
hand-filled expected/PASS all HOLD. Temporary fixture scope additionally permits the original
`/tmp/p2-b3-test-*/b3-initialize` shape, so the real original non-starting consumer can validate
fixture config before a fixture DB exists. This is not a new onsite path or identity.

Positive output `BOUND_HISTORY_ONLY` proves exact input binding and current observing subject's
readonly DB path access; it is nested evidence, never a phase COMMITTED result.
`service_uid=UNKNOWN`, callback role and `runtime_roles_granted_access=false` are preserved.
CP08 is consumed as pinned historical preparation evidence, not reissued as fresh runtime denial.
Still missing for real CP12/13: trusted REOPENED effect/inode/transaction provenance,
service/callback role-path access consumer and validated observation, and explicit legacy
no-sidecar/ownership versus isolated WAL equivalence. `phase_complete=false`, site HOLD.

Affected tests: original 12 retained plus 10 new history cases, **22 PASS / zero skip locally
on Python3.12**. Original-format fixture uses pure original documents and the actual original
non-starting prepared-config consumer, then independent-process B6 binding/readback; it does not
rerun B3 dispatch/cp03_identity. Historical CP08 record is fixture-only, not a new independent
OS denial proof. Negatives also cover reanchored contradictory identity/version, state drift,
missing originals, path escape/symlink, hand input and original two-link publication.
The existing workflow (unchanged this round) runs this file on Python3.11/3.12; Hosted results
are reported with the exact new commit in PR17. Earlier 12-case Hosted run39638090841 remains
valid for its unchanged scope. No server/SDK/permission/B5 work, WAL deletion, DB bootstrap,
activation transition or B7 advancement is performed by the adapter.

### B6 real integration input/action decision — f0366810 continuation

Task: PR17#6321856078. **DRAFT / SOURCE_AND_ROLE_DECISIONS_REQUIRED**.
This freezes the integration route and its gaps; it is not an executable installation package.
No new wrapper, source guard, server action, DB, permission, SDK or B7 change this round.
The source baseline is f03668104441b250234bf7ebdea4d85065550234. Unchanged B6 Hosted
run39640271883 (Python3.11/3.12 each22, zero skip) is reused; no repeated runtime tests.

#### Same-instance input facts and provenance

| Input | Frozen source / actual limit |
|---|---|
| Accepted CP03 | PR17#6283178324; receipt bede2ebc9f9c5458c92307c974358eb61947e7ec80a9611cc76735891ffae433; original descriptor 6d3c95521492ba90640e723081a8d0f21fa2a2bfb3c896c0708ecb86e8ef93f1; seq/epoch/generation1 PREPARED, no DB/socket then |
| Original identity | Retained original fixed CP03 payload receipt bytes match that accepted receipt SHA: installation p2-uk-isolated-20261020; instance0891a51b-feea-520e-850a-c8fc7c840d94; ledger_uuid093955da-4b7d-5c8d-b85e-3adaa304c675; generation1, epoch1; must rebind actual current original files before any future effect |
| Release/config/binary | Original release591855b35c820c486ae07bbb91e681b983a3a2310feaedb57ae7c87fc9b66592; binding-config f772644e9a8587cda9e0df4c1e53dc64d647195407d29c69ef52625ebb0160ad; Python9bee109da0dce17a7c9eeaca9f420cc6770a9fe143b9382d73bd22fe59b21a5f, 6809944B, /usr/bin/python3.11, actual3.11.2 via#6282808058 |
| CP04--09 history | PR17#6284188828; original prepared/preparation-receipt.json SHA34d1530271efaabb4b65c5c44d2e76bd04258247dfc36a9a613aa829ec18dc8b; request199938d73d46f5a841cd56f5f51f814256b28bdc5c7cc88d43e3ff07226ee5b9; PREPARATION_COMMITTED, service_started=false, cp03_unchanged=true |
| B4 inheritance | PR17#6284722235; CP10_FINITE_COMMITTED, b3_unchanged=true, service_started=false; b4_sandbox.py consumes original non-starting check and records database_opened=false; it is not an application DB source |
| Canonical target | /var/lib/xuanjun-p2-isolated-test/b3-initialize/data/ledger.sqlite3; socket at the same root/run/ledger.sock; retain these descriptor paths and identity, do not substitute coordinator management DB or old production history |
| Actual DB source | UNKNOWN / NOT_DELIVERED_IN_REVIEWED_INPUTS: no bound application snapshot, export receipt, file SHA/size, table manifest or same-instance source provenance in the above accepted records. Historical absence does not prove current onsite ABSENT. No server read performed here |
| Current state | Last accepted onsite CP03/B3/B4 evidence is PREPARED/non-starting. Current onsite descriptor/DB/sidecars UNKNOWN, not a fresh QUIESCED observation. Hosted transitions and WAL fixtures are not these onsite objects |

The SHA-matching retained payload supplies exact original identity fields; it does not replace a
fresh fixed-scope read of the current descriptor, journal, DB and sidecars before a future effect.
Do not search old production DB/history to manufacture a source for this ISOLATED_NEW instance.

#### Actual reusable interfaces and non-reusable assumptions

All paths below are under evidence/p2-epoch7-access-repair-20261014 at the fixed source baseline.

| Interface | Concrete behavior / reuse decision |
|---|---|
| runtime/stage1/ledger_install_stage.py:35--77 stage_existing_registry | Requires an existing source registry, measured five-key quiescence proof, separate rollback and staging paths. Consistent backup preserves original tables, then original ExecutionLedger side tables and callback migration are applied only to the staged copy. Returns STAGED_NOT_ACTIVE, not REOPENED. This is not an initial base-schema/business-data creator |
| runtime/stage1/ledger_backup.py:17--124 database_manifest/verify/backup/stage_restore | Original manifest covers physical SHA/size, schema, table counts/digests and pragmas. stage_restore accepts an existing verified backup containing base+side schemas; restores into a fresh target and checks logical equivalence/no sidecars. It does not bind UUID/instance itself, grant access or emit CP12 REOPENED. Need source-custody association from the retained export receipt, not SQLite filename |
| runtime/stage1/execution_ledger.py:36--47,79--87,242--266 | Original tasks/approvals/events schema and execution_specs/worker_heartbeats foreign-key validation. Constructor validates existing base tables before side DDL; it cannot create the first three tables or be used as an initial empty DB builder. B6 observation keeps readonly validators, not constructor side effects |
| runtime/stage1/uk_owner_callback_core.py:28--44,259--280 | Original callback schema validation plus offline owner_callback_requests/owner_callback_replays migration; never a replacement for base application tables. Check callback schema too: stage_restore.verify alone only validates base+execution side tables |
| recovery-kit-source/helpers/epoch7_runtime_effects.py:410--462 | Only identified original effect emitting durable ledger-access.json REOPENED: ACCESS_INTENT -> guarded ownership transfer -> ACCESS_DONE -> bounded real consumer quick_check -> same inode/metadata and no-sidecar recheck -> REOPENED. CP13 then requires QUIESCED+REOPENED and check_observation. No such isolated effect producer is implemented by f036 B6 |
| Same file:187--189,249--265,331--335; epoch7_host_factory.py:82--89 | Legacy command uses runuser/xuanjun-dispatcher and /usr/bin/python3, fixed old DB/release/transaction, old epoch7->8 context, root-owned initial DB0600 and named1003:1006 policy. Do not invoke that host driver against the new instance or patch away those guards |
| recovery-kit-source/helpers/epoch7_runtime_acceptance.py:25--31,71--88,278--348 | Original actual-subject preactivation access worker and strictly bound observation exist. It requires real NSS/group/unit policy and pinned rendered paths; reports database_operations=0 and service_namespace_reproduced=false. It is a file/path access predicate, not an application request or proof of DB write access |
| runtime/stage1/activation_control.py:310--338 | Existing same-epoch PREPARED->QUIESCED CAS requires identity_verified/coordinator_inactive/parent_unit_inactive/cgroups_empty/restart_inhibited. Proof must be produced by bounded actual measurements of this isolated instance; a dict of true fixture values is not onsite evidence. No ACTIVE transition in B6 |

Original roles are gateway/relay1002:1002, dispatcher1003:1003, ledger1003:1006,
callback/dashboard1004:1006, per original ROLES. These are original policy targets, not newly
provisioned or verified identities in the container. Current isolated service_uid remains UNKNOWN.
CP13's original access compiler also covers all six roles and protected configuration paths;
testing only a UID1002 preparer or two roles cannot be labelled complete original CP13.

Two concrete binding conflicts must be fixed by a future functional B6 adapter, not by passing true:
1. f036 b6_persistence.py:67--84,228--232,269--272 couples root/data/run/activation and DB ownership
   to the observing preparer UID, and derives ActivationStore.owner_uid from it. A real1003 DB owner
   after CP12 transfer will fail this current evidence path. Keep the history reader at its own
   proven subject; add separately measured runtime-consumer evidence with exact OS UID/GID/groups,
   descriptor, source pins and DB inode. Neither result authorizes the other role.
2. B3's existing private ancestors and activation custody are1002-owned preparation objects;
   ledger_service.py:19--31 uses root-owned trusted ActivationStore plus callback/native/Owner
   verifiers on actual startup. Chowning only a0600 DB cannot fix700 ancestor traversal or establish
   trusted activation. Container account names, persistent-directory ownership, read access to
   root-owned live activation/config and the eventual B7 custody handoff need an explicit policy.
   Do not chmod/chown B3 history, treat preparer profile as runtime config, or mount ephemeral WAL.

#### Selected data/WAL route and exact alternatives

Preferred **conditional** route is import of a real authorized isolated application snapshot,
with original base+side+callback schemas and source-custody evidence. No such snapshot is selected yet.
If a base-only *existing* registry is supplied, use original stage_existing_registry on a separate
staged copy with its real measured proof; never fabricate the base tables or add dummy tasks.
If there is no real existing isolated data source, a first business initialization contract and its
actual initializer/data are a new required business decision. Owner's earlier choice B established
a new identity and reserved paths; it did not supply a business DB. No executable first-base-schema
initializer was identified among the above original installation interfaces.

WAL boundary can be reconciled without deleting source WAL **only for a fresh target**:
retain the source DB/WAL/SHM evidence, take a consistent logical SQLite backup including committed
WAL rows, and validate table/pragmas/schema equivalence into a separate no-sidecar staging DB.
Publish once to the originally reserved canonical target only if it is proven absent; CP12 can
then check a no-sidecar target while the nonempty source WAL remains preserved.
Readonly SQLite may still create/update its SHM coordination file: list that effect explicitly,
retain before/after evidence and choose compatible read-only source mounts. Never use immutable=1
to pretend committed WAL rows have been included. Original DB/WAL data preservation must be measured.
This is a proposal, not proof that such a source/target currently exists.

If that canonical target already exists with WAL, preserve it and its unknown transactions.
Do not stage over it, copy just its main file, delete/truncate/checkpoint its WAL to satisfy legacy
CP12, or silently change the descriptor DB path/generation. Its current inode/effects must first be
reconciled; a WAL-tolerant isolated CP12 policy would be a separate explicit compatibility decision,
not original legacy CP12 PASS. Do not use RestoreActivator.restore: it requires current ACTIVE,
creates a later epoch/generation and activates the result, violating this B6 scope.

New functional work needed after source/policy selection: one finite B6 import/reopen/access bridge
using the original schema/backup validators, original transition, original effect state meanings and
existing protected receipt publication/lock mechanisms. It must produce real effects and measured
recovery evidence; a further observer that merely returns HOLD is not the implementation.
Original backup uses list(src.iterdump()) and replace-at-target: source size/row budget and exclusive
target publication/recovery must be bounded before reuse under512MiB; do not assume an arbitrary DB
fits memory or that target precheck alone protects against replacement races.

#### One controlled sequence, checkpoints and acceptance (candidate only)

These are internal checkpoints of B6[12,13], not additional installation batches.
Candidate-only new output root: /var/lib/xuanjun-p2-isolated-test/b6-persistence.
Actual final names/manifest/command SHA remain NOT_FROZEN until source and policy are supplied.

| Step | Exact action / possible writes | Durable stop/recovery point | Required acceptance |
|---|---|---|---|
| 1 Input freeze | Same-instance historical pins plus bounded current descriptor/journal, canonical DB and its exact sidecars only; source snapshot SHA/manifest and custody. Existing B1--B5 records readonly; no host-wide census or old Writer search | Retained input fingerprints; unknown/existing conflict stops before mutations | Same instance/epoch/generation/release/config/binary; actual source semantics and current target status established |
| 2 Isolation/quiescence | Exclusive existing install lock; measure only selected new-instance consumers, mount ownership, restart policy and process/cgroup containment; CAS PREPARED->QUIESCED only if still PREPARED and all five measurements prove it. Already QUIESCED must reconcile same head, no repeated transition | Before/after native journal/descriptor head; journal-appended/descriptor-not-published crash remains stopped for original reconciliation | No fixture proof, no ACTIVE, no old host services stopped; immutable identity unchanged |
| 3 Data preservation/import | Source remains unchanged; create new private rollback/staging outputs and bounded manifests/logs in candidate B6 root; original restore or staged migration as selected. No business task execution | Intent before creating outputs; manifest/table counts/digests and source sidecar fingerprints. Partial target or missing response retains all bytes, classify actual effect before any continuation | Base+side+callback schemas; original task/approval/event and callback state/pragmas preserved, no unknown running/leased task adopted |
| 4 First canonical publication | Only after proof target was reserved and absent; finite protected, non-overwriting publication with original DB path and full source/staged/current inode association. Existing implementation gap: final exclusive publication/partial recovery is not yet delivered | Publication intent, exact inode and staged content manifest. Existing or ambiguous target never auto-replaced; preserve staging and destination | Actual canonical file persists, no empty-schema substitute; source and prior receipts unchanged |
| 5 Runtime custody/access preparation | Only the explicitly approved new-instance account/mount/ancestor and activation-custody actions; immutable history stays protected. This is a permission boundary and cannot be hidden inside a read-only command | Per-path prior/after metadata and named operation receipt; no recursive chmod/chown or rollback of previous batches | Actual subject/groups can traverse exact persistent paths; no credential/production mount; runtime role separate from preparer |
| 6 CP12 real reopen | Under same-instance QUIESCED guard, publish ACCESS_INTENT; perform only approved exact ownership effect, record ACCESS_DONE; actual selected runtime subject opens existing DB mode=ro, quick_check and original schema validators; bind PID/UID/GID/groups, descriptor head, path/inode, schema/source hashes and bounded result; then durable REOPENED | Before transfer, after transfer/before receipt, after child/response loss, after REOPENED publication. Do not reinvoke non-retry original entry; read actual metadata/child result/receipt. Unproven result remains UNKNOWN with DB/WAL retained | Real consumer exit+strict result+same DB identity; no target sidecars on selected legacy-equivalent fresh-target route; REOPENED from this operation, not copied fixture status |
| 7 CP13 preactivation access | Read CP12 REOPENED plus current QUIESCED and real scoped role/path evidence; run the applicable original path predicates for all required mapped consumers, no listener/model/task writes | Separate bound observations, failure/timeout logs and new-process readback; ownership mismatch does not trigger chmod automatically | Strict context+request/role/path/SHA association; actual OS consumers and expected denials; no hand-filled PASS or claim of service namespace/HTTP startup |
| 8 Reopen verifier process | Exit finite children; new process reads the same real files/receipts and proves prior B1--B5 inputs unchanged; no service start | Final CP12/CP13 receipt+input/output manifest and per-step resume state; partial earlier checkpoints retained | Only both actual predicates pass may B6 commit. Unknown effects stop that step; no full seven-batch restart, no B7 activation |

Proposed operational boundaries: reuse frozen Python3.11 container/image, host wrapper compatible
with3.6.8, network none/read-only root/cap-drop ALL/no-new-privileges and original resource limits.
A privileged *host* custody operation, additional role container or persistent mount is a new
specific action to list for confirmation, not an implicit permission from this plan. Existing
cap-drop container cannot create accounts, set arbitrary UIDs, chown root trust or stand in for
the old root/runuser worker; no privilege escalation or runtime installation is part of this round.

Centralized decisions still required, with exact dependency owner:
- Application data owner: supply one authorized real isolated snapshot/export plus table manifest,
  size/SHA and association to this original UUID/instance, or define a genuine first business
  initialization contract. Transport alone supplies none of these semantics.
- P2 integration/Owner policy: approve the explicit mapping of existing runtime roles, groups,
  persistent paths and live activation custody. Actual NSS/image bytes are currently UNKNOWN;
  existing preparer and permission records remain unchanged.
- P2 compatibility policy: choose fresh-target consistent import with preserved source WAL
  (recommended conditional route), or define an explicit isolated WAL-bearing canonical CP12
  contract. Do not assert both no-sidecar and nonempty canonical WAL at once.
- Functional adapter work: implement and test the identified bounded import/publication, actual
  role reopen and effect recovery bridge after those inputs are fixed; current f036 is evidence
  consumption only, and the original fixed legacy effect cannot simply be retargeted.

No server command or approval question is issued by this document-only task. The remaining
installation invocation count is UNKNOWN until those concrete choices/inputs are closed; one
normal controlled command is a packaging goal, not a promised number of successful attempts.

