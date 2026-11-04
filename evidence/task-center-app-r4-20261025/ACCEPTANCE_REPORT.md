# 任务中心可运行应用候选 R4 验收报告

## 结论

`SCOPED_STATIC_PASS`。本结论只覆盖隔离 TEST_ONLY 源码、同库本地 HTTP
入口、投影/页面逻辑、P2/P3 只读契约和自动化回归；不代表浏览器 E2E、部署、
生产派单、P2/P3 接线或生产验收通过。

## 冻结版本

- R3 输入包 SHA256：`a5ea7c2d8e985948837634acf228d7f29d24bad3101156d96d507529aab7bfaf`
- R4 源码 Commit：`a1143f44a8eb72f51fc182d851bc815f6e47f733`
- R4 源码 Tree：`52077ff085012dc2585ecac2f077c5276c5e60e5`

## 实测

- 作用域 Python：181 项，PASS，退出码 0。
- Node 组合加载/路由/详情：1 项，PASS，退出码 0。
- 本地应用：真实启动、GET `/api/projection`、GET `/`、SIGTERM 安全停止。
- 动态数据：4 项目、8 任务、7 板块；同时出现 SUCCESS、FAILURE、
  WAITING_AUTHORIZATION、WAITING_DEPENDENCY、LIVENESS_UNKNOWN。
- 独立进程重开 SQLite 后投影逐字段一致。
- P2/P3 契约：SENT/ACK/RESULT/ACCEPTANCE 分离；跨租户、错版本、未知来源拒绝且零写入。

## 环境限制与未完成

- SQLite 3.26 不支持旧迁移夹具使用的 `ALTER TABLE DROP COLUMN`，3 项旧迁移测试
  继续 `NOT_EXECUTED`，与 R3 一致。
- 运行环境未提供已获准 Playwright/Chromium，浏览器点击和截图为
  `BROWSER_UNVERIFIED`；Node 不是浏览器 E2E。
- P2/P3 真实安装验收、生产 adapter、凭据、任务登记和外部投递均
  `NOT_IMPLEMENTED / NOT_EXECUTED`。
- 没有部署、真实派单、真实暂停/恢复或生产写入。

## 全仓发现但不纳入本包修复

一次全仓发现式运行尝试了 555 项，因无 Playwright、非 root、SQLite 3.26、
目录权限门禁及仓库其他社区模块的 Python 版本问题失败。该结果保留在
`FULL_DISCOVERY_FAILURE_SUMMARY.md`，没有将其冒充本包回归，也未越权修改其他项目。
