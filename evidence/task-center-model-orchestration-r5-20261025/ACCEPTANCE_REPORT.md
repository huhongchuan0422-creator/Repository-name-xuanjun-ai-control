# 任务中心后台与多模型统一调度 R5 验收报告

## 结论

`SCOPED_STATIC_PASS`。覆盖 TEST_ONLY 源码、同库后台、隔离 HTTP Provider、
持久调度循环、统一动作申请门禁和离线回归；不代表真实浏览器、真实模型、付费
调用、部署、生产派单或生产验收。

独立 QA 与独立 Security 均从同一最终 Git commit/tree 的独立 archive 复核并
给出 scoped `PASS`；早期拒绝及其反例完整保留在 `FAILED_REVIEW_HISTORY.md`。

## 冻结绑定

- R4 参考包 SHA256：`a4f56010920aa4864f1882a2e1bfaaef88abf750161f2d9fe572b5575b3195dd`
- 开始 HEAD：`9cf3ee929a3ac4b34dd61d4ed3ac867a2bfaa98e`
- 初版被双审拒绝 Commit：`a16a7cff0159efc940f73ea035a4798fb4c011bf`
- 最终实现 Commit：`998566d52634ff3cb5b3bd2d68df8cad5f2966a7`
- 最终实现 Tree：`1b4783e64f36172825d534855c2ff3c28888c989`

## 实测

- `python3 scripts/run_r5_scoped_tests.py`：232/232 次执行 PASS，退出码 0；
  对应 187 个不同测试标识。原始输出见 `RAW_PYTHON_TEST_LOG.txt`。
- 旧 SQLite 3.26 不支持 `ALTER TABLE DROP COLUMN` 的 3 个迁移测试明确
  `NOT_EXECUTED`，由可复跑脚本按完整测试 ID 排除。
- `node tests/task_center_digital_twin.test.cjs`：PASS，退出码 0；覆盖普通、中文、
  含斜杠 ID 编解码和异常直达。
- `node --check demos/task-center-digital-twin/admin.js`：退出码 0。
- 独立 QA：232/232、187 个不同测试标识、退出码 0；关键定向 13/13。
- 独立 Security：232/232 及定向 48/48，均退出码 0。
- 真实本地应用启动后读取 7 板块/8 任务；服务端保存隔离 fixture 密钥后只回读
  `••••only`，管理投影不含明文；GET 与 SIGINT 停止均正常。
- 完整 HTTP 旅程真实通过：建项目→领取 TEST_ONLY Writer→隔离能力评测→
  Executor/Reviewer/Acceptor 分工→持久调用→独审报缺→返工通过→独立验收→
  总图同库回显。

## 覆盖的拒绝与恢复

缺目标/验收、跨租户、过期授权、历史或只读权限冒充当前许可、UNKNOWN 冒不存在、
非当前 Writer、错资产版本、未批准扩范围、自审、未通过审核即验收、重复动作、
重复模型请求、任务权限撤销、Provider 停用、401、429、超时/迟到、Worker lease
丢失、迟到 Worker 结果 CAS、真实调用尝试限速、并发/熔断、价格未知、付费单价
缺失、私网/凭据 URL、重定向和重启恢复。

## 限制

- 浏览器交互和截图：`BROWSER_UNVERIFIED`；Node/HTTP 不冒充浏览器 E2E。
- 真实 Provider、真实 API 密钥、付费调用：`NOT_EXECUTED`。
- 生产部署、生产 Executor、外部动作、P2/P3/社区/B5 接线：
  `NOT_IMPLEMENTED / NOT_EXECUTED`。
- 首次失败的作用域 runner 因仓库根路径未加入 `sys.path` 而生成 10 个导入错误；
  历史保留为 `RAW_PYTHON_TEST_LOG_FAILED_IMPORT.txt`。修复 runner 后同一提交范围
  重新执行；修复后的最终同版执行为上述 232/232。修复前成功日志保留为
  `RAW_PYTHON_TEST_LOG_PRE_HARDENING.txt`。
- R4 的 181 次 Python 执行对应 136 个不同测试标识；本报告不沿用错误的
  “181 个不同用例”口径。
