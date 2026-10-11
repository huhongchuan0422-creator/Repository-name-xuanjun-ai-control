# 自动领取与掉电恢复验收契约（现有闭环节点补充）

更新：2026-10-11 19:30 Asia/Shanghai。
状态：REQUIREMENTS_RECORDED；RUNTIME_NOT_DEPLOYED_NOT_ACCEPTED。
执行服务器：英国 iZd7oeikknn1z21sq6ji6zZ。
本契约补充现有 A1/A2/B/C 验收，不新建任务系统，不改变正在执行的 spec，
不重置修复预算，不授予生产数据库、旧 Coordinator、交易权限或正式 Webhook 变更。

## 本轮真实进度与门禁

Owner现场回执：A1完成 ae72ec7405540a59e63273a5711ed8f38e66b20e；A2本地冻结
9df09fa；B实现提交 fb2cc9081fa8d215bf186046b53bae9b9334ad7b，2个测试文件未提交；
228非过期测试与编译/diff检查通过；全量248项仍为241 PASS/3 FAIL/4 ERROR。
最新B为测试/bootstrap越界修改等待授权HOLD；Work已批准同任务范围扩展，
见WORK_APPROVED_B_SCOPE_EXTENSION_20261011.json，扩展接收/复工尚NOT_VERIFIED。
独立QA/安全尚未开始，尚无干净组合候选或部署证明。Work未取得A2完整SHA、B最终干净组合SHA和
新补丁/manifest字节，不能把原Work入口242项CI推广为本轮248项通过。
回执：evidence/uk-intake/OWNER_RELAYED_INTEGRATION_PROGRESS_20261011.json。
GitHub查不到这些本地对象只说明尚不能从远端验真，不否认本地开发成果。

B只依赖A2合同冻结，不必串行等待A1；B已有当前实现及断点，扩展只允许续接原尝试，不再重复创建/启动。
合同接口兼容须明确版本和方法/返回值，修调用方或实现的不一致，不凭猜测兼容。
callback合法请求应成功、伪造/过期/错Owner/错epoch仍403；不得关闭鉴权来清零。
manifest从最终安装文件实字节重算并外部绑定摘要；不能只把测试期望改成当前值。
保留2个未提交测试及失败证据，修复后正常提交，不删负例、不吞异常、不无限重试。
清零7项后冻结完整组合SHA/tree/manifest/patch；独立QA与安全对同一制品并行复验，
有分歧或新失败退回原任务断点。超预算/同指纹重复按原规则HOLD。

## 1. 谁拥有任务，谁拥有运行状态

GitHub现有控制库保留批准任务/spec、依赖、源码版本及可追踪证据。
A2唯一canonical ledger保存领取、尝试、阶段、检查点、预算、失败和人工节点。
intake journal只保存投递/回执，不另建任务队列，也不授权发布。
OpenClaw main负责协调，Worker/QA/安全在各自已批准隔离角色内执行。
“回复结束”不是完成；Work也不是由聊天结束自动生成的后台进程。
缺发布者或Work审查能力就登记该具体依赖，不能把整个任务静默标成进行中。

## 2. 领取与触发

GitHub push -> 既有Actions/英国Runner -> 校验来源/批准spec/摘要 ->
原子落盘不可变envelope -> systemd.path -> 同一非root intake ->
现有OAuth/CLI main -> 持久接收回执 -> A2准入/领取/实际角色启动。

不让Agent轮询GitHub，不另开公网Webhook或复制GitHub/OAuth凭证。
.path仅监听request目录变化；不能用DirectoryNotEmpty，因为请求保留用于核对。
同一服务的timer开机30秒补扫，服务结束120秒后再补扫；这不是每120秒的硬实时保证。
接件超时/效果不明不能反复发模型请求；先按持久回执和实际session证据核对。
同一个task/spec只登记一次，文档SHA改变不重启任务。角色实际启动与RECEIVED分开。

未领取请求不得因为后续文档SHA、Runner清理checkout或换另一任务而静默消失。
当前入口只考虑现时checkout来源，尚未证明多不同spec快速发布的补投。
发布端须保存未终结的批准任务引用/证据，重启核对全部未领取项；
补投仍经过原批准快照/来源门禁，禁止为了领取旧信封放宽来源校验。
GitHub/Runner离线时不伪造启动；恢复后核对批准快照和已接收记录再补发。

## 3. 运行、心跳、停顿

准入事务核对依赖、预算、artifact、generation/epoch/instance/fence，
再登记唯一执行attempt和unit/session身份。重复接件只返回已有任务状态。
Worker不能领取另一个执行实例，也不能改canonical ledger或权威权限。

必须分开保存监督器心跳、Worker实际存活及最后有效进度。
协调器替Worker续租不等于Worker仍在推进；只看RUNNING/会话存在不够。
独立监督器按有界周期检查真实session/unit/cgroup、进度和当前阶段的时间预算。
长模型调用沿用<=1200秒上限；CI/人工等待用明确等待态，不能当作卡死或完成。
心跳/进度失效，先持久记录原因并撤销旧fence，再通过窄broker停止固定unit，
确认父级及全部后代cgroup已空；未确认停止前不启动继任者。
额度不足持久暂停且保留剩余预算；只在确认可用后按同任务恢复，不重建新任务。

## 4. 检查点与副作用

每个外部动作前落盘IN_FLIGHT及动作幂等标识；动作证据核对后才标记完成阶段。
检查点绑定task/spec/base/候选tree+commit/generation/epoch/attempt，
并保存模型调用、patch轮次、CI/审查及发布标识，不保存凭证或原始敏感输出。
所有持久化边界遵循既有A2事务/同步/原子切换设计，不在这里新增第二份DB。

| 中断点 | 恢复条件与动作 |
|---|---|
| 信封临时文件未发布 | 不消费半文件；Runner按同批准标识重建并原子发布 |
| 已接收但尚未启动 | 对账接件journal与ledger；无实际启动证据且证明未执行才续准入 |
| 模型/工具调用中 | 核对原session/turn与产物；不能确认副作用则WAITING_HUMAN，不盲重跑 |
| 产物已完成未入库 | 校验冻结数据/原幂等标识；同摘要复用，禁止再做一轮模型开发 |
| commit/push/PR结果未知 | 查实际对象/远端HEAD/既有PR，已发生则记录；未知则HOLD |
| CI等待 | 按既有严格CI_WAIT规则核对相同SHA继续查询，不重新生成补丁 |
| 审查/批准已发生未解锁 | 同制品/决策ID事务对账，再解锁依赖，不重复批准或重复发布 |
| 数据库恢复/回滚切换中 | 保持maintenance gate；由既有root activator核对阶段完成或回退，不直接开派发 |

这是验收目标。当前代码只证明受限CI_WAIT自动重排；一般模型/工具续跑尚未验收。
磁盘损坏/丢失不由systemd重启解决，必须用已实测可恢复备份；不可确认的数据保持HOLD。

## 5. 断电后的启动顺序

挂载/持久存储就绪 -> 核对root-owned安装manifest与activation descriptor ->
窄broker/epoch日志/ledger服务进入恢复模式 -> 停止并核对旧实例 ->
验证schema/ledger generation/完整性 -> 对账未终结任务与外部副作用 ->
开启新epoch下的唯一派发 -> 恢复可证明安全的检查点 ->
启用intake watcher/timer及只读看板。

这些是逻辑顺序，实际systemd依赖和broker互锁必须在冻结A2制品中实现并验证；
本文件没有安装任何服务。接件可以先持久保存，实际任务启动必须等恢复准入。
旧lease不得因机器重启、时钟回拨或恢复旧DB重新有效；
进程内超时用单调时钟，跨重启采用boot/epoch身份核对，时间异常须拒绝旧租约。
epoch保存在数据库备份之外，恢复/回滚不降低；切换前所有旧DB用户/cgroup必须停止。
未经批准的schema迁移、未知旧Coordinator状态或缺身份/二进制，一律阻止激活。

## 6. 交付与可视化

完成必须有干净组合候选、完整SHA/tree、外部绑定manifest/patch摘要、
同制品CI/独立QA/安全、发布准入和现场E2E，不能凭Agent一句DONE解锁生产。
通过既有Runner受控回收机制回传不可变结果清单、补丁和审查证据，拒绝可执行回收。
现有collector只绑定旧4bf32c0失败证据，尚不等于已回收本轮A1/A2/B；
新回传入口必须随受控部署一起验证，不能静默等待Owner逐项中转。
固定接收摘要不取最新任意文件，不放宽整个HOME，不授予普通Worker GitHub写权限。

看板分别显示：接件、排队、实际执行、最后进度、恢复、额度暂停、
等待CI/QA/安全/Work、WAITING_HUMAN与完成。最后观测过期不能继续显示无条件运行。
全部人工节点集中展示原因/断点/所需动作，只阻塞相关依赖；独立任务继续。

## 7. 必须实际演练的场景

1. 新批准spec自动到达并取得绑定来源的RECEIVED和真实STARTED。
2. 重复事件/同spec文档新SHA，不重复建任务或模型启动。
3. watcher丢事件、启动已有请求、运行中事件及事件风暴后仍能补扫。
4. 多批准任务连续发布/Runnercheckout被清理，未领取任务不丢失。
5. 单Worker退出/卡死，协调器仍活着：能发现停顿并真实停止后代。
6. 接件前后、启动前后、模型中、产物冻结后、push/PR/CI边界受控中断。
7. 重启服务及隔离环境的主机重启，按checkpoint恢复；未知效果不重发。
8. DB恢复/回滚、时钟异常、旧/新派发器并发；旧epoch/fence均被拒绝。
9. 额度暂停/恢复，保留任务、产物、失败预算；仅6.1主/5.6备用及原OAuth路径。
10. 两个真实开发任务连续完成，HTTPS看板据真实账本更新、人工队列不遗漏。

故障演练在隔离环境先做，不为测试直接给生产主机断电。
本轮只记录需求与现场回执；部署/恢复/模型实测均NOT_EXECUTED。
