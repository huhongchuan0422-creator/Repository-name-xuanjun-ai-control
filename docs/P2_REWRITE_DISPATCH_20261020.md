# P2重写：16阶段与7批隔离安装对应记录

原任务PR17；原分支repair/p2-resumable-install-20261020；本次基线2adaf2dfff6a2af25e922ba85160d2b0bf211257。
续做[原评论6275334072](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/17#issuecomment-6275334072)，只更新两份文档，不新增队列、不执行安装。

## 来源与继承

完整开发规则及后续更新见[开发执行与反馈规则](DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md)、[原恢复设计](development/P2_RETAINED_RECOVERY.md)、[三入口交接](THREE_NATIVE_ENTRY_HANDOFF.md)。
本轮Owner明确拆分重写、取消新增隔离五次准入和额外人工独审，覆盖旧文档对此重写路径的冲突文字；不改变旧生产权限/Grant/历史。
已有两份文档的“七批尚为草案”结论继承，历史组件快照保留在Git历史，不冒充当前版本。

## 准确组件证据快照

本次仅同步准确快照，不把组件合并进总分支，不重复运行未变组件测试。

| 组件 | 准确Commit | CI / 证据 | 结论与限制 |
| --- | --- | --- | --- |
| 制品 | `ea31dbbec2a8710b964efb38fa2975684bbd9739` | [39303377908](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39303377908)，SUCCESS | 组件交付：并发篡改拒绝、三个SIGKILL窗口、重启recover、前批保护、0700；非英国验收 |
| 运行 | `499bcc43f4c992b21035c22446ccc4d915873fb1` | [39303903462](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39303903462)，SUCCESS | Unix Socket就绪、有界探针、独立日志收集、稳定操作/提交引用；非生产服务验收 |
| 协调 | `a766dcb307ce738dc508ad153f17e593d1fb7bfb` | [39308651562](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39308651562)，SUCCESS；[限定验收6275266088](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/134#issuecomment-6275266088) | Tree `768a7431c689ea07fc3e4361cb3df151d0cfe1e2`；仅重复PROGRESS重开、丢失响应恢复两缺陷关闭；整体PARTIAL |

三次CI的head_sha与上表一致，本轮只读核实；协调CI双Python各21项按Dots原验收继承，不重新运行。
[续做任务6275279160](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/134#issuecomment-6275279160)中的真实失败证据/稳定去重/轮次与根因计时仍待交付；另保留完整调用超时回收、begin前中断安全续接、混合CLI及文档收口未完成项。已存在基本真实组件链与CLI导入修复，不能继续把历史ADAPTER_UNAVAILABLE或“仅进程存活”写成当前快照；也不能由此推断完整链路已验收。

## Exact execution environment contract

UK host: iZd7oeikknn1z21sq6ji6zZ. Host Python: /usr/bin/python3 3.6.8. Existing Docker image: xuanjun-p2-sandbox:prep-base-20261013; container Python previously observed as 3.11. Packaging must pin and verify the actual image/interpreter identity before acceptance, without repeating already verified delivery files.

Host bootstrap must remain Python 3.6.8 compatible and may only stage/read receipts and invoke the fixed isolated Docker command. Components should run explicitly inside the pinned Python 3.11 container, not be accidentally imported by host Python. Python 3.12 CI is extra portability evidence, not a substitute for target Python 3.11 execution. No system Python replacement.

Preserve network=none, cap-drop=ALL, no-new-privileges, read-only root filesystem, pids/memory bounds and private tmpfs. Only independent isolated storage is writable; no production DB/Signer/Registry/cloud credentials/host Docker socket mounts. Child-workload write access to coordinator and other component state must be resolved explicitly: component directory names alone do not isolate same-UID processes.


## 原16阶段覆盖表（设计映射，非执行计划）

准确来源：基线 `2adaf2dfff6a2af25e922ba85160d2b0bf211257` 的
[evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_recovery_sequence.py](../evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers/epoch7_recovery_sequence.py)，
`PHASES` blob `45984835fb4dfff475d0481cceebb24811380986`。
每个稳定键仅有一个主归属；跨批引用只读依赖，不安排再次执行。

| 原顺序 | 原稳定键 | 主归属 | 功能目标 | 实现边界 |
| --- | --- | --- | --- | --- |
| 01 | `stage_exact_release` | B1 | 准确版本制品发布 | 制品组件可复用；原宿主发布未证明 |
| 02 | `preserve_prior_receipts` | B2 | 历史回执保全 | 组件不可变回执可复用；原历史导入未接 |
| 03 | `rebind_prepared_epoch` | B3 | 隔离配置与身份版本 | 原epoch绑定未实现 |
| 04 | `quiesce_exact_epoch` | B7 | 切换与最终验收 | 原宿主停用不在隔离组件能力内 |
| 05 | `replace_retained_targets` | B7 | 切换与最终验收 | 原保留目标替换未实现 |
| 06 | `publish_reviewed_identities` | B3 | 隔离配置与身份版本 | 测试身份发布契约待定义；不等于生产批准 |
| 07 | `change_generation_access` | B3 | 隔离配置与身份版本 | 原代际访问切换未实现 |
| 08 | `apply_reviewed_access` | B3 | 隔离配置与身份版本 | 原访问策略适配未实现 |
| 09 | `rebind_tls_metadata_only` | B3 | 隔离配置与身份版本 | 仅元数据；生产TLS不操作，适配未实现 |
| 10 | `apply_fresh_sandbox` | B4 | 隔离应用运行环境 | 运行组件部分替代；不等于原sandbox配置等价 |
| 11 | `install_verified_plugin` | B5 | 独立插件版本 | 安全制品机制可复用；插件功能契约待接 |
| 12 | `reopen_existing_database` | B6 | 持久数据重开与访问 | 不涉及原生产DB；隔离数据适配待实现 |
| 13 | `verify_runtime_access` | B6 | 持久数据重开与访问 | 真实读写/访问判据待定义 |
| 14 | `activate_exact_epoch` | B7 | 切换与最终验收 | 原epoch激活未实现 |
| 15 | `activate_new_services` | B7 | 切换与最终验收 | 容器应用启动可复用；原服务激活未实现 |
| 16 | `post_install_checks` | B7 | 切换与最终验收 | 组件链证据有限；英国/原16阶段验收未执行 |

原七批准确名称/成员/顺序的仓库原稿：**NOT_FOUND**（检索范围为上述基线两份既有重写文档及PR17评论6275334072；不是声称整个历史从未存在）。既有README仅声明“seven batches remain a design draft”。以下B1–B7为本次候选功能边界，全部 **DRAFT / NOT_INSTALLABLE**。

B编号是功能索引，不是允许按B1→B7执行的顺序。原阶段03→04→05→06以及13→14→15→16的约束不能被候选分组覆盖：B3含03及06–09，B7含04–05及14–16，故存在跨批屏障，尚不能冻结为一次关闭的独立节点。必须在同一版本Plan中解决准备/切换资源所有权和这些屏障，或修订候选边界，证明合法转换后才能安装；不得运行原阶段又运行其容器替代以重复实现副作用。

## 七批候选的依赖、验收及恢复边界

| 批次（全部DRAFT） | 最小完整目标与拥有资源 | 依赖与进入条件 | 隔离验收目标（待执行项不是PASS） | 持久恢复点与失败处置 | 未完成项 |
| --- | --- | --- | --- | --- | --- |
| B1 准确版本制品 | 一个内容固定、可读回的release目录；只写自己的版本 | 固定Manifest/源摘要、独立私有root、大小及modes明确；不以移动分支作输入 | 真实execute→inspect；摘要/mode匹配；中断recover；后批失败后原文件/回执不变 | 保留源快照、部分文件、日志和原提交回执；校验后补齐缺失；冲突HOLD，禁止覆盖已正确版本 | 统一包Manifest和英国本批回执未生成 |
| B2 历史证据保全 | 独立只读证据版本和摘要索引，能证明原件未变 | 原件来源/读取范围/归属明确，B1工具版本固定；无原件标UNKNOWN | 复制授权隔离样本，重开校验完整索引；故障不改变源件或B1 | 保存原件、复制意图和索引；只恢复本批不完整副本，不删除原回执 | 历史证据导入适配器及完整事务发布未实现 |
| B3 隔离配置与身份版本 | 一个可验证且不激活生产的测试配置版本；ISOLATED_TEST_ONLY | B1/B2可读回；测试身份/访问/TLS元数据Schema及资源所有权固定；03/04/05/06跨批屏障已解决 | 测试身份、配置摘要和访问负例；重开仍同版本；无生产Signer/TLS/Registry访问 | 保存旧配置引用、新配置意图和每次CAS结果；未知发布先对账；只回退本批拥有资源 | epoch、访问策略、TLS元数据适配及跨批屏障未实现；不能先执行03再假称本批完成 |
| B4 隔离应用运行环境 | 独立应用实例、Unix Socket就绪、进程/日志归属 | B1准确可执行制品；B3配置；固定启动参数和截止时间；每批独立状态root | 真实制品程序启动及PING/PONG；超时/错误响应/管理CLI SIGKILL；查询与重开不重复启动 | 稳定operation_id/config_sha256/commit_receipt及PID身份、收集器状态；先inspect/recover，不盲launch | 原sandbox机制等价未证明；协调器完整超时回收/混合CLI未关闭 |
| B5 独立插件版本 | 一个版本化插件，可验证加载和功能响应，不覆盖B1 | B1制品接口、B4指定加载契约，独立插件root及回退引用 | 插件摘要、实际加载/功能响应、坏插件拒绝；前批应用/文件不变 | 保留插件版本、激活引用和原回执；只恢复或撤回本插件引用，不清空release | 插件功能/加载适配和恢复事务尚未实现；解包成功不算插件安装成功 |
| B6 持久数据重开与访问 | 独立隔离应用数据库重开、数据保持及权限有效 | B4/B5实际依赖按应用契约固定；隔离DB来源、Schema、备份/迁移策略明确；绝不使用未知原生产DB替代品 | 真实应用写入→退出→保留非空WAL状态→重启读回；拒绝越权；先前批次证据不变 | 保存应用DB/WAL及迁移意图、备份、事务/检查点；结果未知先对账，不删WAL、不空库重建 | 应用DB适配、非空WAL恢复和原访问等价未实现；协调管理SQLite不是该DB |
| B7 切换与最终验收 | 在独立隔离实例内完成选定新版本激活与整链读回；保存旧目标 | B1–B6实际闭环；04/05在06之前的屏障有已验证方案；精确目标所有权及恢复Plan固定 | 真实完整CLI、响应丢失/SIGKILL恢复、原PID/原提交回执保持；证明每阶段唯一效果 | 保存切换前引用、停用/替换意图、激活结果和独立读回；局部已成功只收敛不重放；不自动回滚前批 | 原宿主quiesce/目标替换/epoch/systemd激活未实现；原16阶段/英国验收未执行 |

每批关闭必须同时具备准确代码/Plan/资源摘要、真实效果读回、故障恢复证据和对前批不变的证明。表中恢复点是要求，不是声称相应适配器已经实现。跨批进程相同UID仍可能写其他root，目录分开不是隔离证明；权限/挂载/进程边界未证明时不能承诺后批失败完全不影响前批。

## 后续执行与政策边界

当前只是文档增量；七批已安装数 **0/7**，原16阶段执行数 **0/16**（沿用已知现场状态，本轮未做英国读取）。原生产AuthorityStore仍UNKNOWN，生产切换不在本任务。
新隔离协调器不新增五次额度或强制Grant准入；旧生产Grant/历史消费、数据库/WAL保留，不扩权。
每轮10次失败或1小时先到上报Dots并提出替代方法；同根因30分钟提前换思路。上报门槛不是安装额度，通知未真实接通标UNAVAILABLE。
Dots调度和节点验收；Work归集/集成/打包及后续获授权安装。本轮不新增独立人工审签，平台必需检查保留；评论自动唤醒NOT_VERIFIED。
