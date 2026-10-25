# 调度内核 R3 同候选集中收尾实测报告

## 冻结对象

- Owner 指定上一包：`7d60c26aaf32c40c0acdb3a01a39a0507452f19e2baecf2a575b456d320f341f`（104986 B，31/31 清单已由 Owner 核验）。
- 本轮实现提交：`7c32e3e0b4db28e6cc2e7c96e9926617a9eaed68`。
- 实现 tree：`03b026d8515cbc8562457d2ec37c55ccad4d8370`。
- 模式：`TEST_ONLY`；生产状态：`NOT_IMPLEMENTED / NOT_EXECUTED`。
- 本报告为作者侧离线实测，不代替独立 QA、浏览器 E2E、部署或生产验收。

## 三组集中修复结果

1. **半启动跨进程重启收敛：PASS（TEST_ONLY）**。真实独立子进程在 Fence claim 提交后以退出码 73 终止；重新打开同一 SQLite 后观测到 `RECEIVED + VALID + grant ELIGIBLE + 无 STARTED`。明确调用 `recover-unstarted` 后复用原 drain、资源失效覆盖及 rollback，资源 claim 为 0，任务回到 READY/NONE，旧 grant 为 `INTERRUPTED`，无伪造 STARTED，第二次恢复为空操作。
2. **长依赖等待解除后的计时：PASS**。任务等待超过 900 秒期间原 scan 不误判；完整版本/证据 ACK 消费后，在同一事务记录解锁时间并设置新的派发监督期限。随后的 scan 不立即 HOLD，原 checkpoint + 新鲜 resume grant 可合法启动；grant 有效期没有被刷新或复用。
3. **总图健康与卡点归属：PASS（机械/Node）**。投影现识别 `DEPENDENCY_WAIT`、`HOLD`、`FAILURE`、`CANCELLED`、`CAPABILITY_UNAVAILABLE`。任务负责人和解除责任方分离；依赖卡点取生产者 owner，非依赖卡点缺证据时为 `UNKNOWN`。影响按实际状态分类，不再固定为 `TASK_START_BLOCKED`。HOLD/FAILURE 板块不再显示 STABLE，异常可直达任务详情。

## 实测

- 支持的原 Supervisor：41/41 PASS。
- Writer Fence、Entry Review、Runtime、Gateway、CLI：109/109 PASS。
- Python 合计：150/150 PASS。
- Node 界面组合测试：1/1 PASS。
- 新增关键反例：独立进程 kill/reopen、grant 不重复消费、长等待 ACK→scan→start、HOLD/FAILURE、任务 owner 与解除责任方不同、解除责任未知。
- 原始逐项 stdout、版本、环境及退出码见 `RAW_TEST_LOG.txt`。

## 精确限制

- 3 项旧 v2 迁移 fixture 因宿主 SQLite 3.26.0 不支持其构造所用 `ALTER TABLE DROP COLUMN`，继续为 `NOT_EXECUTED`，未计入 150 PASS。
- 实际浏览器仍为 `BROWSER_UNVERIFIED`；Node 组合测试不冒充浏览器 E2E 或截图通过。
- `recover-unstarted` 只在调用者已确认旧 TEST_ONLY 进程退出后使用；本包不提供生产进程判活或分布式锁。
- 未部署、未真实派单、未连接生产 Gateway/Executor/outbox、未执行付款/暂停/恢复，未新增凭据权限。
- 社区、B5、P2、OCR 业务源码均未修改；本框架不成为其安装前置。

## 结论

`LOCAL_TEST_ONLY_AUTHOR_VERIFIED_CANDIDATE`。这不是合并、部署、生产启用或现场验收许可。
