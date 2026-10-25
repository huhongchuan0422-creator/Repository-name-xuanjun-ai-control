# 调度内核 R2 与七板块数字孪生集中验收

## 冻结对象

- 上一候选包：`10dfefea04fae66a3f186d1ad4c1be5a2bc7445e4032026a56b5f809cc96ee91`
- 上一证据提交：`60ea60204cdb999ff5242c447b41f9b2b7fad456`
- 本轮实现提交：`9ce4bf87f2d0b2b6faa1b30e80941249edc47c7c`
- 实现 tree：`8758742e03cc11543af012f43ec020a0a8c7a5ce`
- 模式：`TEST_ONLY`；生产状态：`NOT_IMPLEMENTED / NOT_EXECUTED`

## 六项缺口结果

1. **跨租户写前门禁：PASS**。`progress`、`complete_success` 先验证可信上下文；负例证明 `tasks/events/outbox/gateway_checkpoints` 均无变化。
2. **实际启动门禁：PASS**。启动前核消费 ACK、完整事件身份、版本、证据、撤销状态及适用 resume grant；未 ACK、错证据、撤销、缺许可均拒绝。
3. **规范资源集合：PASS**。错误、额外、遗漏资源均在 Fence claim 前拒绝且零 claim。
4. **完整事件身份：PASS**。`tenant + producer task + producer attempt + event` 贯穿 inbox、依赖和投递回执；跨任务同名事件并存、幂等重放和重启通过。
5. **半启动收敛：PASS**。claim 后 grant 撤销/失败走 Fence revocation，删除 REVOKED claim 并恢复 READY；无 VALID claim、无 STARTED 事实、grant 不重复消费。
6. **Supervisor.scan 依赖等待：PASS**。Gateway 持久写 `WAIT_DEPENDENCIES`，原 scan 直接识别；合法等待任务不会因 READY 超时转 HOLD，ACK 后解除标记。

## 投影与界面

- 投影 schema 2 固定七板块：运营、客户、研发、验收交付、维护、共享生态、财务。
- 总览只显示板块任务数、活跃数、阻塞数和健康摘要。
- 板块工作台支持项目、状态、负责人筛选；异常按钮直接绑定 board/project/task/node。
- 任务详情显示同源 attempt、epoch、权限、checkpoint、阻塞、下一动作和证据要求。
- `register` 支持任意合法图；测试覆盖多项目、跨板块、只经过部分板块、回流依赖表达及双租户隔离。
- Node 组合测试验证路由、筛选、异常定位和详情渲染；实际 Chromium/Firefox 未发现，因此为 `BROWSER_UNVERIFIED`，不宣称浏览器 E2E 或截图通过。

## 实测

- 支持的原 Supervisor：41/41 PASS。
- Writer Fence、Entry Review、Runtime、R2 Gateway、CLI：106/106 PASS。
- Python 合计：147/147 PASS；这是本轮按实际命令重新计数，不把旧 118 与新增测试重复相加。
- Node 界面组合测试：1/1 PASS。
- 任意图 `register`、同源 `export-ui`、demo 与独立进程 restart projection：退出码均 0；重启前后 JSON `cmp=0`。
- 原始 stdout、环境、退出码：`RAW_TEST_LOG.txt`。

## 精确限制

- 3 项旧 v2 迁移 fixture 因宿主 SQLite 3.26.0 不支持其构造使用的 `ALTER TABLE DROP COLUMN`，状态为 `NOT_EXECUTED`，未计入 147 PASS。
- 浏览器工具状态虽 enabled，但无 detected browser/executable，状态 `BROWSER_UNVERIFIED`；未安装、未启动新服务、未绕过限制。
- 未部署、未真实派单、未接生产 Gateway/Executor/outbox、未执行支付/暂停/恢复、未新增凭据权限。
- 社区/B5/P2/OCR 业务源码未修改；调度中心不承接证照 OCR 业务。

## 结论

`LOCAL_TEST_ONLY_CANDIDATE_PASS`。这不是合并、部署、生产启用或现场验收许可。
