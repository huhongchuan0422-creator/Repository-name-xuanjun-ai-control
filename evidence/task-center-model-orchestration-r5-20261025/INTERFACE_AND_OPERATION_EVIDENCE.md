# 接口与操作证据

## 应用入口

- 七板块：`GET /`、`GET /api/projection`。
- 管理后台：`GET /admin.html`；管理读写要求仅本机持有的
  `X-Test-Admin-Token`。提交、独审、验收和变更审核还需服务端 0600 映射文件
  对应的 `X-Test-Actor-Token`，请求体姓名不能代替认证主体。
- GET 投影通过 SQLite `mode=ro + query_only`，兼容活动 WAL；不实例化任何建表
  或迁移构造器。缺表返回 `READ_SCHEMA_MISSING`。
- 后台动作清单及启动命令见
  `docs/development/TASK_CENTER_MODEL_ORCHESTRATION_R5_20261025.md`。

## 同源与重启

任务、事件和 outbox 仍由原 Supervisor/Gateway 表管理；提供方、角色、评测、
请求、用量、候选、动作门禁只是同一 SQLite 内的关联事实。网页关闭后，
`model_scheduler_runtime.py` 可独立继续；重启后读取同一请求、lease、checkpoint、
结果和幂等键。丢失 Worker 的 RUNNING 请求收敛为 UNKNOWN，不自动重复调用。

## 本地运行观察

2026-10-25 在隔离临时目录实际执行：

1. `app-demo` 建 4 项目、8 任务。
2. `task_center_app.py` 绑定 `127.0.0.1` 随机端口，回执 STARTED。
3. GET 投影返回 schema 3、7 板块、8 任务。
4. 以隔离 fixture 凭据新增 disabled Provider；回读只有 `••••only`，JSON 全文无
   fixture 明文。
5. SIGINT 回执 STOPPED。

相关脱敏结果：`APP_DEMO_RESULT.json`、`API_PROJECTION.json`、
`ADMIN_PROJECTION_MASKED.json`。

## 安全动作边界

`ExecutionPolicyGateway.request_action` 只在租户、task/attempt、资产版本、预检、
当前授权（绑定 task/attempt/资产版本/Writer）、范围/变更单和 Writer 全匹配时写
`ADMITTED_TEST_ONLY`。它不连接云、
主机、源码远端或生产执行器，回执固定含 `external_execution=NOT_EXECUTED`。
可信读取、角色冲突复核、幂等检查与动作写入处于同一
`BEGIN IMMEDIATE`；Provider 价格变更和 Model 价格写入也使用互斥事务，避免
并发生成“付费 Provider + 免费/无单价 Model”。
