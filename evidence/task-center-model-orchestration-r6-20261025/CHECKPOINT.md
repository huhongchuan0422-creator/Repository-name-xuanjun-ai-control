# R6 恢复检查点

- 源码提交：`91553badf5f7ba6fa9b7fa9472f3f2fe66e6a549`
- 源码 Tree：`2a180f793e271ef73be69dd9eab460a2a17ad090`
- 已完成：Connection/OAuth、统一调用门禁、Writer/生命周期、Skill/实例、preflight、动作审批、MCP、Codex 适配边界、回归、独立 QA。
- 当前在途：无源码写入；同版 QA/Security 均 PASS，仅生成 Manifest、归档和下载回执。
- 测试：271/271（226 distinct）及定向 93/93 通过；退出码 0。
- 阻塞：真实 OAuth、真实 Provider/Codex/Hosted/浏览器/部署未获本包执行条件，只阻塞对应现场验收。
- 未完成：3 项旧 SQLite 迁移 `NOT_EXECUTED`；实际浏览器 `BROWSER_UNVERIFIED`。
- 下一步：冻结证据 Manifest 和归档并交下载回执；后续真实接线仍需独立授权与现场验收。
- 恢复命令：`cd /home/xuanjun_dev/xuanjun-scheduler-kernel-clone-7THQz4 && git status --short && git rev-parse HEAD HEAD^{tree} && PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_r5_scoped_tests.py`
