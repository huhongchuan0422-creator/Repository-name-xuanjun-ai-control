# 七板块数字孪生界面证据

## 可复跑入口

1. 用 CLI `register` 写入任意合法 TEST_ONLY 图。
2. 用 CLI `export-ui` 从同一 SQLite 生成 `demos/task-center-digital-twin/digital-twin-data.js`。
3. 离线打开 `demos/task-center-digital-twin/index.html`。

## 已机械验证

- `projection.schema=2`，七板块完整且空板块仍显示 `NO_DATA`。
- 多项目、跨板块、部分板块、双租户隔离、依赖卡点、HOLD 和 FAILURE 投影由 Python 集成测试覆盖。
- 总图板块健康从同源任务事实计算；HOLD/FAILURE 不再冒充 STABLE。
- 异常字段区分 `task_responsible_party` 与 `resolution_responsible_party`；缺少解除责任证据时明确为 `UNKNOWN`。
- `task_center_digital_twin.test.cjs` 覆盖：总览、板块路由、项目筛选、异常直达、详情、返回定位参数及两类责任方渲染。
- 示例数据由 CLI 从真实本地 TEST_ONLY 事件生成，`app.js` 不硬编码健康或成功状态。

## 未验证

- OpenClaw Browser status：`enabled=true`、`engine=chromium`，但 `running=false`、`detectedBrowser=null`、`detectedExecutablePath=null`。
- 因此实际点击、浏览器布局、360/390/768/1440 视口和截图均为 `BROWSER_UNVERIFIED`。
- 未安装浏览器、未新增服务、未用 Node 测试冒充浏览器 E2E。
