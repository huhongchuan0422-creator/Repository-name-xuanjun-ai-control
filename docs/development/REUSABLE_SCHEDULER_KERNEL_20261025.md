# 可复用调度内核与数字孪生接线（TEST_ONLY）

## 基线与边界

- 源基线：`8aa66c43ebfa19a760e5270157e14464f2f46c1c`（PR143 Draft）。
- 复用：`task_supervisor.py` 的唯一 `tasks/events/outbox`、Schema v3、Writer fence 与 LOCAL_ONLY 锁。
- 新增表只保存图元数据、依赖版本要求、消费 ACK、checkpoint、恢复许可、模块契约和读取投影；不复制任务终态。
- 生产 Gateway、真实 Executor、云账户、部署与凭据均为 `NOT_IMPLEMENTED / NOT_EXECUTED`。
- 固定七板块为运营、客户、研发、验收交付、维护、共享生态、财务；框架只协调跨板块任务、依赖、执行状态、验收和交接，不把各模块的业务处理搬入调度内核。
- OCR 业务接线已按 Owner 纠正明确排除；社区商家证照/OCR 仍由社区分账商家平台处理。调度中心只可承载“开发 OCR 模块”这类开发任务。

## 本地运行

```bash
python3 -m unittest -v \
  tests.test_reusable_task_gateway tests.test_reusable_scheduler_cli
node tests/task_center_digital_twin.test.cjs
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-scheduler-arbitrary.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  register --tenant tenant-demo \
  --graph examples/reusable-scheduler-task-graph.json
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-scheduler-test.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  demo --tenant tenant-a --lock-root /tmp/xuanjun-scheduler-locks
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-scheduler-test.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  project --tenant tenant-a
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-scheduler-test.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  export-ui --tenant tenant-a \
  --output demos/task-center-digital-twin/digital-twin-data.js
```

CLI 只读取指定本地数据库并输出 JSON 投影，不创建服务、不监听端口。
`demo` 在同一数据库执行 TEST_ONLY 闭环；随后 `project` 是一次独立进程重启读取。
`register` 是任意合法任务图的本地入口，不依赖固定 A/B/C demo；接口图样例见
`examples/reusable-scheduler-task-graph.json`。`export-ui` 从同一数据库生成离线
`digital-twin-data.js`，随后双击 `demos/task-center-digital-twin/index.html`。

## 事实阶段

1. `Supervisor.record(TERMINAL)` 在一个 SQLite 事务中写任务终态、完成事件和 outbox。
2. `mark_outbox_sent` 只记录 `SENT`；不代表消费。
3. `receive_outbox` 持久去重后为 `RECEIVED`。
4. `acknowledge_event` 校验租户、版本和证据后才写 `CONSUMED_ACK` 及依赖 `RECEIVED`。
5. `issue_resume_grant` 为 `ELIGIBLE`；`consume_resume_grant` 为 `STARTED`；任务成功仍由独立 TERMINAL 回执确定。

## 本轮安全收口

- `progress` 与 `complete_success` 在任何事件、outbox、checkpoint 写入前校验可信租户上下文；跨租户拒绝保持所有表零变化。
- 实际 `start` 同时验证完整消费 ACK、依赖版本/证据、未撤销事实、适用 checkpoint/resume grant，再进入 Writer claim。
- claim 资源必须与图登记的规范化资源集合完全相等；错误、额外或遗漏均在 claim 前拒绝。
- inbox、消费回执和依赖引用使用 `tenant + producer task + producer attempt + event` 完整身份，同名事件可跨任务合法并存。
- claim 后 grant CAS 遇过期/撤销时执行本地 fence revocation，并把未开始 claim 收敛回 READY；不会留下 VALID 半启动或重复消费。
- Gateway 每次从持久依赖表计算合法等待集合并显式传给原 `Supervisor.scan`；仅 READY 且仍等待的任务免于“未接单超时”，活跃任务不能被豁免。

## 数字孪生界面

- 总览只显示七板块任务数、活跃数、阻塞数和健康摘要，不铺任务明细或单个 AI 状态。
- 点击板块进入工作台，可按项目、状态和负责人筛选；点击异常直接进入绑定的板块/项目/任务卡点。
- 任务详情显示同源的任务、节点、attempt、epoch、权限、checkpoint、阻塞、下一动作和证据要求。
- hash 路由保留板块、项目与筛选条件；界面健康和异常均来自 `projection(schema=2)`，不是 `app.js` 硬编码成功状态。
- 本机无可用 Chromium/Firefox 可执行文件；浏览器点击/截图为 `BROWSER_UNVERIFIED`。Node 组合测试只证明路由、筛选、异常定位和详情渲染逻辑，不冒充真实浏览器 E2E。

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
- 七板块投影与界面均为 TEST_ONLY 设计/模拟；生产数据采集、实时进程探测和真实控制入口仍为 `NOT_IMPLEMENTED`。
