# 全仓发现式测试失败历史（保留，不作本包结果）

曾执行 `python3 -m unittest discover -s tests -p 'test_*.py'`，共尝试 555 项，
结果为 11 failures、98 errors、1 skipped。主要环境/越界原因：

- Playwright 未安装，2 个浏览器模块导入失败；
- P2 保护入口 8 个夹具要求 root，当前 euid=1002；
- SQLite 3.26 不支持 3 个 v2 迁移夹具的 DROP COLUMN；
- 运行目录权限不满足 release-manifest 的受信目录门禁；
- 其他社区广告模块在 Python 3.6 使用 `str.isascii()`，属于本任务范围外。

本轮没有修改这些模块，也没有把全仓发现式失败隐藏或改写为通过。正式本包回归
只采用 R3 已定义的 Supervisor/Fence/entry/Gateway 作用域及本轮新增应用/契约测试。
