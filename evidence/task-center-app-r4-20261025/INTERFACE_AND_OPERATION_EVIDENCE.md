# 接口与操作证据

## 同源应用

- 启动入口：`scripts/task_center_app.py`
- 数据入口：`GET /api/projection`
- 权威数据：传入的 Supervisor SQLite；请求时重建，不读取静态快照。
- 页面：`/`、`/app.js`、`/styles.css`。
- 写端点：无；POST 返回 405。
- 绑定：仅 `127.0.0.1 / localhost / ::1`；非回环地址拒绝。
- 停止：前台 Ctrl-C 或 SIGTERM，均关闭 HTTPServer 并输出 STOPPED 回执。

## 实际启动回执

运行目录：`/tmp/xuanjun-task-center-r4-final.qMnpob`。

```json
{"mode":"TEST_ONLY","mutation_api":"DISABLED","production_status":"NOT_IMPLEMENTED","state":"STARTED","tenant_id":"tenant-app","url":"http://127.0.0.1:18766/"}
{"mode":"TEST_ONLY","state":"STOPPED"}
```

实际 API 摘要：schema 3，4 项目，8 任务，7 板块，2 异常；状态集合为
`FAILURE / LIVENESS_UNKNOWN / SUCCESS / WAITING_AUTHORIZATION /
WAITING_DEPENDENCY`。

## 页面操作路径（机械/HTTP 已验，浏览器未验）

1. `#overview`：七板块概要和异常直达。
2. `#board/<board>`：多项目分组、项目/状态/负责人筛选。
3. `#project/<board>/<project>`：项目任务和卡点摘要。
4. `#task/<board>/<task>?project=<project>`：任务、Writer、run/session、
   authority、checkpoint、异常证据；无进程证据固定显示 UNKNOWN。
5. 返回板块时保留 query 筛选；刷新按钮重新读取同库 API。

## P2/P3 接口边界

`ExternalReceiptContract` 只规范化 `source, tenant_id, task_id,
attempt_id, input_version, event_id, phase, status, evidence_ref,
permission_scope`。输出 `VALIDATED_NOT_CONSUMED`，不写 canonical ledger，
不生成 ACK 或启动事实。生产接线仍为 NOT_IMPLEMENTED。
