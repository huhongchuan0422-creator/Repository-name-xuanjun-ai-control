# 可复用调度内核与数字孪生接线验收报告

## 1. 受测基线与范围

- 原主线：`bd8048e891dd6f41451f9791f7d0769e81077c6e`。
- 复用的 PR143 Draft 基线：`8aa66c43ebfa19a760e5270157e14464f2f46c1c`。
- 原 PR143 文件 `scripts/task_supervisor.py`、`scripts/task_writer_fence.py` 及其测试未修改。
- 新增范围：同一 Supervisor SQLite 上的动态开发任务图、依赖版本/证据、消费 ACK、checkpoint、安全让出、恢复许可、只读孪生投影和 TEST_ONLY CLI。
- Owner 范围纠正已执行：不存在 OCR 业务 adapter；本包不是业务请求调度平台，仅服务原7个开发子路。原7子路的正式 ID 由原 Task/Node Registry 提供，本包不硬编码或另造。

## 2. 实际实现

| 能力 | 实际结果 | 边界 |
|---|---|---|
| 动态图 | 任意无环开发任务图、版本依赖、优先级、资源及模块字段 | 图注册当前调用原单任务 API；崩溃中断的原生批量事务仍待补 |
| 唯一状态源 | 任务状态继续位于原 `tasks/events/outbox`；扩展表仅存约束、ACK、checkpoint、grant 和投影元数据 | 没有生产双写 |
| 持久事件 | TERMINAL、事件和 outbox 原子；SENT/RECEIVED/CONSUMED_ACK 分开 | 外部真实投递 adapter NOT_IMPLEMENTED |
| 版本证据 | 依赖必须同时匹配 producer、output version、evidence ref | 旧版/乱序不解锁 |
| Writer/资源 | 复用 PR143 LOCAL_ONLY fence；错误/未释放资源阻止恢复 | 分布式资源锁 NOT_IMPLEMENTED |
| 等待恢复 | 原 task、prior attempt checkpoint、依赖 event、grant expiry、单次消费 | TEST_ONLY executor；生产 Executor NOT_IMPLEMENTED |
| 租户隔离 | 服务端 HMAC TEST authority；裸 tenant_id、跨租户任务/事件拒绝 | 生产身份提供者 NOT_IMPLEMENTED |
| 数字孪生 | 独立进程从同一 DB 重建任务、依赖、checkpoint、authority 与时间线 | 无浏览器 UI、无服务端部署 |
| 模块契约 | `xuanjun.scheduler.kernel`、`xuanjun.digital-twin.projection` | 均为 TEST_ONLY |

## 3. 验收结果

- 新增集成：`11/11 PASS`。
- 未变 PR143 可执行门禁与新增集成合并：`41/41 + 77/77 PASS`，退出码均为 `0`。
- 单命令闭环与独立进程重启投影字节一致：`cmp EXIT_CODE=0`。
- 覆盖：动态多任务图、两租户、重复、乱序、旧版本、重启、等待不误报超时、资源冲突、不可抢占、checkpoint 错配、跨租户拒绝、投影一致、恢复失败不冒成功。
- 3 项未变 v2 migration fixture：宿主 SQLite 3.26 缺 `DROP COLUMN`，状态 `NOT_EXECUTED`，未冒 PASS。

## 4. 未执行与剩余项

- 生产部署、真实 dispatch、真实消息 adapter、真实云账户、凭据、权限变更：`NOT_EXECUTED`。
- 生产 Gateway/Executor/分布式锁/身份提供者：`NOT_IMPLEMENTED`。
- 社区、B5、P2、OCR 业务源码：未修改，也不是本框架前置条件。
- 浏览器/生产数字孪生 UI 接线：本包只交可复算 JSON 投影；`BROWSER_UNVERIFIED`。
- PR143 仍为 Draft；本包不能当合并、部署或生产验收许可。
