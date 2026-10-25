# 可复用调度内核与数字孪生接线（TEST_ONLY）

## 基线与边界

- 源基线：`8aa66c43ebfa19a760e5270157e14464f2f46c1c`（PR143 Draft）。
- 复用：`task_supervisor.py` 的唯一 `tasks/events/outbox`、Schema v3、Writer fence 与 LOCAL_ONLY 锁。
- 新增表只保存图元数据、依赖版本要求、消费 ACK、checkpoint、恢复许可、模块契约和读取投影；不复制任务终态。
- 生产 Gateway、真实 Executor、云账户、部署与凭据均为 `NOT_IMPLEMENTED / NOT_EXECUTED`。
- 范围仅为原7个开发子路共用的开发任务、依赖、执行状态、验收和交接。七子路身份继续引用原定义，本包不新造子路、不调度业务请求。
- OCR 业务接线已按 Owner 纠正明确排除；社区商家证照/OCR 仍由社区分账商家平台处理。调度中心只可承载“开发 OCR 模块”这类开发任务。

## 本地运行

```bash
python3 -m unittest -v tests.test_reusable_task_gateway
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-scheduler-test.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  demo --tenant tenant-a --lock-root /tmp/xuanjun-scheduler-locks
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-scheduler-test.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  project --tenant tenant-a
```

CLI 只读取指定本地数据库并输出 JSON 投影，不创建服务、不监听端口。
`demo` 在同一数据库执行 TEST_ONLY 闭环；随后 `project` 是一次独立进程重启读取。
接口图样例见 `examples/reusable-scheduler-task-graph.json`。

## 事实阶段

1. `Supervisor.record(TERMINAL)` 在一个 SQLite 事务中写任务终态、完成事件和 outbox。
2. `mark_outbox_sent` 只记录 `SENT`；不代表消费。
3. `receive_outbox` 持久去重后为 `RECEIVED`。
4. `acknowledge_event` 校验租户、版本和证据后才写 `CONSUMED_ACK` 及依赖 `RECEIVED`。
5. `issue_resume_grant` 为 `ELIGIBLE`；`consume_resume_grant` 为 `STARTED`；任务成功仍由独立 TERMINAL 回执确定。

## SaaS 模块契约

| module_id | 状态 | 说明 |
|---|---|---|
| `xuanjun.scheduler.kernel` | TEST_ONLY | 动态图、持久事件、checkpoint/resume |
| `xuanjun.digital-twin.projection` | TEST_ONLY | 从同一 SQLite 重建只读投影 |

租户上下文必须由服务端可信入口断言。本包以 HMAC TEST authority 验证这一边界；仅提交 `tenant_id` 会被拒绝。生产身份提供者和密钥管理不在本包内。

## 已知剩余项

- PR143 尚为 Draft，本包不是合并或生产许可。
- 没有真实分布式锁、生产 Executor adapter 或外部消息投递 adapter。
- `release_revoked_resources` 仅在同库已存在 checkpoint、零在途、对账完成、完整 revocation coverage 时释放 LOCAL_ONLY claim；生产资源释放需原资源系统回执。
- 图注册已先做完整结构/环验证；当前 Supervisor 单任务注册 API 仍是逐任务提交，进程在注册中途崩溃时需要后续原生批量注册事务完善。
