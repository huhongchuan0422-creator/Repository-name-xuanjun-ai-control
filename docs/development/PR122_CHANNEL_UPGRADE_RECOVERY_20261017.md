# PR122 固定通道升级与恢复专项

对应独审 #6227685785。当前为候选源码与隔离测试，不是 Root 执行许可。

## 不变对象

冻结运行 ZIP d03a09d3110cf372d5c6209da4514fffd77f8487c6a36532744e80557ac353d8（Artifact12082187996）保持字节不变。新版升级器独立于该包交付，bundle() 强制核对这一准确 ZIP，不允许仅内部自洽的替代包。原 Guard 与原 Root 输入文件均不覆盖；原 Guard 固定的是旧升级器 SHA，不得用来执行新版升级器。新版必须获独立机制审核、准确源码/制品及新的 Owner 执行授权后才可送入私有目录。

Owner 已回传旧 Root 基线 Plan a7813acad46a212868751aebb06fe4c5b8a4845d7608cf9b3f26983df8c850ff，stdout d513816aa17fb93ef91c2994995f7f7eec69e1b88eeb5c4f95dd6344167589b6。此为 Owner 现场证据，不是开发方或审核方直接 Root 取证。安装时必须重新对真实状态与准确批准绑定。

## 正向事务

锁仍为 Root 保护的 .upgrade-lock 及当前 channel.py flock，不能删除、替换锁或绕过安装通道。获取锁后重查完整 Plan 和 gate，再核对 bundle。CONTROL 独占 mkdir 是不可复用的一次尝试占用；即使初始持久化失败，目录存在也拒绝再次 apply。所有正向调用包括参数/授权检查失败均禁止自动重试。

plan.json 与 approval.json 独占保存。events/ 下编号事件为追加文件，receipt.json 为最新视图。每个可变步骤先写 INTENT 并 fsync，再执行并同步对象及父目录，再写 DONE。恢复读取连续且绑定相同 Plan/批准的事件；receipt 落后于已持久化事件时，以事件为准；事件损坏、缺失或不完整为 UNKNOWN，禁止自动补写或猜测。

阶段：PREPARING、BACKUP_VERIFIED、STAGED、FENCED、OLD_MOVED、CANDIDATE_MOVED、CODE_REPLACED、TAR_REPLACED、GRANTED、BOUND。仅完整新候选、代码、TAR、旧备份、wrapper/sudoers 全部核验后才写 GRANTED。异常时即使日志写入失败也独立尝试 HOLD_UPGRADE 围栏；围栏本身失败为 UNKNOWN。硬进程退出在 GRANTED 后只可能留下完整已核验的新对象，不会把混合对象准入为 GRANTED。

初始 plan/approval/event 尚未完整持久化时没有修改业务对象；保留现场，禁止 apply 和自动 rollback，需另行审查恢复方案。不是声称任何磁盘故障都能自动恢复。

## 回滚与再次恢复

首次 rollback 只使用原事务明确批准的同事务回滚范围。rollback-started.json 独占标记阻止第二次普通 rollback。先验证所有来源备份和现有对象仅为获审旧/新版本，再进入围栏。回滚阶段 RB_FENCED、RB_PREPARED、RB_PARKED、RB_CANDIDATE、RB_CODE、RB_TAR、RB_GRANTED、ROLLED_BACK 同样逐项 INTENT/DONE 持久化。

恢复旧候选采用受控副本；部分复制仅当已有成员均匹配旧 Manifest 时才允许补齐，不能删除或覆盖未知成员。rename 已完成但 DONE 未写入时，用准确对象身份判别已执行动作，原目录与停放目录均保留。所有旧对象和固定策略核验后才恢复旧 GRANTED，最终再验并输出 ROLLED_BACK。

中断后只允许 Owner 使用 recover-rollback，须新的受保护独审锚批准 XUANJUN_CUSTOMER_CHANNEL_RECOVERY，绑定当前最后事件 SHA、Plan SHA、新升级器 SHA、事务、最多一次及2小时内有效期。批准评论ID不得为原 apply 评论；recovery-ID.json 独占占用，禁止复用。再次中断需再次独立批准，不能循环重试。此命令仅存在 Owner 升级器中，不加入 githubrunner wrapper/sudoers。

## Owner 信任保管链（现场仍待验收）

源码作者不能自行创建、冒用或编造 Owner 信任锚。UPGRADE_TRUST.json 必须由 Owner 受保护流程登记，Root:Root 0600、全部父目录 Root 且无组/其他写权限、非符号链接。登记真实独立主体及其与源码作者的隔离、保管证据SHA、准确批准评论与全文SHA。gate 重读评论、审核目的、版本/Plan/新包、升级器自身SHA、期限，并将完整 trust 文件SHA纳入锁内及激活前一致性比较。

安装准入还必须取得：Owner登记来源与时间、主体隔离/保管证据、信任文件元数据及SHA、真实评论全文SHA和一次执行占用回执。公开回执只展示上述非秘密元数据，不公开私有证据正文或任何凭据。不从 GitHub 登录名或自报角色推导独立性。当前上述生产保管链 NOT_VERIFIED；源码和合成信任测试不能关闭这一现场缺口。

## 测试证据口径

20个 unittest（原7+新增13），真实Root拥有的临时目录，真实文件系统、flock、fork/os._exit、fsync异常注入；固定生产路径全部重定位，Owner主机检查在夹具中替换，不调用真实 sudoers、服务或客户资料。正向26个硬退出子案例、回滚21个子案例；一次测试函数内的参数化案例不计为独立unittest项。另遍历完整成功路径的全部实际fsync调用，记录升级152处、回滚113处异常案例。不能把此结果记为国内生产恢复验收。Hosted Python3.11准确CI和制品哈希需另附真实回执。

## 仍然 HOLD

Root 升级/回滚执行许可未签发。专用账户、私有运行依赖、扫描器、受保护配置、六Unit、私有预览及真实身份/渠道验收尚未完成；通道升级不是客户中心生产安装许可。客户中心、真实资料/密钥、网站切换、DNS均不在本批范围。
