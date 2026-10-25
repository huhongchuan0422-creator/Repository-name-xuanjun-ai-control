# 七板块数字孪生界面证据

## 可复跑入口

1. 用 CLI `register` 写入任意合法 TEST_ONLY 图。
2. 用 CLI `export-ui` 从同一 SQLite 生成 `demos/task-center-digital-twin/digital-twin-data.js`。
3. 离线打开 `demos/task-center-digital-twin/index.html`。

## 已机械验证

- `projection.schema=2`，七板块完整且空板块仍显示 `NO_DATA`。
- 多项目、跨板块、部分板块、双租户隔离及依赖卡点投影由 Python 集成测试覆盖。
- `task_center_digital_twin.test.cjs` 覆盖：总览、板块路由、项目筛选、异常直达、详情、返回定位参数。
- 示例生成结果：2 个任务、7 个板块、1 个依赖异常；数据文件由 CLI 生成，`app.js` 不硬编码成功状态。

## 未验证

- OpenClaw Browser status：`enabled=true`、`engine=chromium`，但 `running=false`、`detectedBrowser=null`、`detectedExecutablePath=null`。
- 因此实际点击、浏览器布局、360/390/768/1440 视口和截图均为 `BROWSER_UNVERIFIED`。
- 未安装浏览器、未新增服务、未用 Node 测试冒充浏览器 E2E。
