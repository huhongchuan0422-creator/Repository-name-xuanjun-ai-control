# 长期权限完整包：集中验收清单

当前所有新增长期能力测试状态：NOT_RUN。此文件是测试计划，不是PASS回执。

## A. 身份、授权与信任根

1. 真正ChatGPT/Work/DOTS分别完成原生提交→测试回执→终态→停止交接；记录可信来源及参与人；同GitHub账号注释不自动成为独立审核。
2. 错UID/GID/peer、伪造入口、缺task/spec、另一主机、另一数据域、已撤销会话全部拒绝。
3. 开发者自签、参与开发的审核者、旧HEAD/旧tree审核、错artifact/过期授权拒绝；未变已审范围保持可复用。
4. 普通任务修改broker、sudo策略、unit、drop-in、授权表、GitHub可信工作流或审核来源时拒绝，不能靠PR同名check绕过。
5. root所有祖先/解释器/模块/环境/配置不可写；symlink、硬链接替换、ACL补充写权、mount namespace差异、TOCTOU替换均拒绝。
6. 任意shell/argv/PATH/LD_*/PYTHONPATH、用户可写安装脚本、任意systemctl unit及容器socket/root cron旁路不得获得root。
7. 历史英国NOPASSWD ALL与全部其他授权来源被准确识别；安装前不假定无宽权，撤销后有效权限实测证伪绕过。安全执行链必须与独立批准制品/可信系统基线核来源与差异；仅owner=root或同机自报hash不得通过。基线无法建立时HOLD并提出经批准的干净恢复方案，不推定已经入侵，也不推定已经可信。

## B. 开发、测试、制品与发布

8. UK/CN/KR的任务工作区/分支/依赖/测试/制品所需全部正常动作通过，不逐项追加sudo；业务仓库与控制仓库分离。
9. 越界写入、rename旧/新路径越界、共享核心非DOTS写入、prod DB/凭据读取、测试借道交易拒绝。
10. 同一任务和重叠路径并发CAS仅一成功；不同非重叠任务按资源预算可并行。恶意任务直接访问其他任务工作区/Git元数据、同UID进程ptrace/信号/proc敏感内容、可信调度socket、已打开FD、宿主挂载、共享HOME或缓存投毒均须实测拒绝；只改分支/目录名/cgroup不足以PASS。
11. 错commit/tree/parent/manifest、缺/多文件、任意root脚本、可变release symlink、过时review拒绝promotion。
12. 安装器只运行可信自身代码；待安装包中的脚本/测试/缓存不被root提前执行。固定工具hash变化拒绝。
13. 在已有不可变目录重复安装同bytes可安全核验；不同bytes/部分目录/非预期目标HOLD，不覆盖修成成功。
14. 单机失败不误标四机全成功；跨机前置未就绪不启用依赖能力；国内/韩国既有账号不因名称差异重建。

## C. 长期运营全范围

15. 固定unit服务status/reload/restart/stop/start/timer可完成经批准的普通场景；非项目unit、额外unit/drop-in参数拒绝。
16. UK inactive Runner/Writer不会被通用运维测试启动；韩国交易执行unit、策略/资金动作被独立门禁挡住。
17. 配置错误、健康检查失败、依赖down、磁盘满、端口占用、慢启动、退出失败均得到明确终态和安全停留。
18. 日志/指标/诊断按路径、字段、时间窗和大小限额返回；凭据、客户敏感字段、proc environ不泄露；权限拒绝不当成空日志。
19. 日志轮转、容量接近阈值、证书到期/续期失败、旧证书回滚、reload失败都有证据和负责人；只用既有固定域名/续期身份。
20. DB数据范围、只读事务、行/字段/时间限制生效；越权表/导出/跨环境写拒绝；schema维护只针对精确已审迁移。
21. 备份一致性、WAL/SHM处理、校验、保留、空间耗尽、传输中断、加密副本与隔离恢复演练覆盖；目标改变拒绝。
22. 恢复先停writer/取得维护gate，验证backup和目标；生产覆盖、账本权威切换、重复通知/交易回放不会自动执行。
23. 运行时/包更新只有批准集合，签名和旧版本回滚来源有效；不通过通配package命令获得任意root执行。

## D. 并发、重试、故障与撤销

24. lease到期但旧进程/cgroup未空时HOLD；不启动替代writer。停止后跨重启仍能核旧generation/epoch/fence。
25. 请求重复、乱序、迟到、网络掉线、响应丢失、客户端重试按幂等键对账；已经执行但返回未知不重复effect。
26. 在stage、备份、原子替换、journal/fsync、清理每一阶段模拟失败；部分文件保留且清楚列示，不吞错或自称回滚成功。验证durable authorized intent先于effect、durable outcome或UNKNOWN后于effect；远端审计不可用时只进入有界受保护spool，本地审计盘满/spool满/fsync失败须在新effect前拒绝。
27. SIGTERM/SIGKILL、主机/服务重启、断电模拟后保持可识别事务；不能用单元测试替代真实恢复验收。
28. 撤销在请求前/决策后执行前/执行中/结果后均有效；旧会话、旧lease、缓存授权、已有socket不能继续取得新能力。
29. 撤权失败、无法确认在途进程停止、外部效果未知时保持fence/HOLD；admin救援仍可用，不恢复旧宽权。成功撤销后记录REVOKED/DISABLED；仅在本次精确重新激活动作时确认有效、全部门禁重核及有效权限最终读回通过后，才可重新标ACTIVE。
30. 回滚映射精确覆盖原配置/units/owner/mode/ACL及依赖顺序；错hash、缺备份、非空cgroup、stale epoch拒绝。
31. 撤权和回滚不删除审计，不恢复已废弃writer，不回放历史模型调用/提交/推送/通知/交易。

## E. P2、GitHub及东京特殊验收

32. P2 A阶段只读保存证据验证，不运行prepare/新probe；NOT_RETAINED历史逐次FD值保持诚实，程序强制保证单列。
33. 真正Task5拓扑签批前B不能启动；B PREPARED_NOT_ADMITTED不等于C恢复授权；旧Epoch批准或建议正文不能替用。
34. GitHub管理员回读受信任workflow仓库/路径/来源绑定；缺失检查、伪同名检查、旧HEAD、改规则/信任根恶意PR确实不可合并。
35. 管理403/平台不支持来源绑定时治理状态HOLD，不拿截图/聊天授权或候选CI冒充已强制。
36. 东京只允许冻结迁移需要的helper/数据/目标；独审与精确安装授权分别核实，GET/HEAD补丁PASS不替代。
37. 东京退役须迁移验收/回滚窗口完成、业务无依赖、备份可用；随后撤销Runner/凭据/入口并读回，不新建长期体系。

## 终态格式

每个case必须记录：case_id、policy版本/hash、source commit/tree、artifact、host、实际执行身份、task/attempt/lease/fence/epoch、测试层（offline/hosted/live）、expected、observed、result、原始日志摘要、effect范围、cleanup、reviewer、证据链接。

仅在所有适用项有同版本可读证据、没有关键UNKNOWN、撤销演练已通过、独审有效、适用于当前激活的精确动作时确认有效，并完成重新激活与最终有效权限读回后，才能将该主机/能力标ACTIVE。撤销演练本身的终态是REVOKED/DISABLED；不能拿旧激活回执覆盖该现态。部分成功必须显示具体host/capability，整体仍PARTIAL/HOLD。
