# R5 独立同版 QA 报告

## 结论

`PASS`（仅限冻结的 TEST_ONLY 本地候选）。

- Commit：`998566d52634ff3cb5b3bd2d68df8cad5f2966a7`
- Tree：`1b4783e64f36172825d534855c2ff3c28888c989`
- 独立 `git archive` SHA256：
  `2c562c2a02ff37defb3d0aaf04cbe5ec4f69fa5fd60b12ebdd25b4921b9c58f0`
- 审核在独立临时目录执行，未修改源仓库。

## 实测

- Scoped：232/232 次执行通过，187 个不同测试标识，退出码 0。
- 关键定向复跑：13/13 通过，退出码 0。
- Node UI：1/1 通过，退出码 0。
- Task Center 三个 JS 文件语法检查：退出码均为 0。
- DNS 假 socket 探针：OpenAI-compatible、SiliconFlow 均只解析一次并连接
  已固定地址，退出码 0。

## 独立确认

- 动作准入的角色复核、幂等判定和 action INSERT 位于同一
  `BEGIN IMMEDIATE`；并发角色写入被锁阻止。
- Provider 转付费与 Model 写入双向互斥，不能生成付费 Provider 配免费或缺
  单价 Model。
- canonical 完成后候选落账失败可恢复；terminal artifact、最新候选、attempt、
  authorization/Writer/change/preflight 和幂等身份均严格绑定。
- DNS 无二次解析连接窗口。

## 限制

- 3 项旧 SQLite V2 迁移测试明确 `NOT_EXECUTED`。
- 未执行真实浏览器、外部 Provider、真实密钥、付费调用、部署或生产接线。

独立日志已收入包内：`INDEPENDENT_QA_SCOPED_LOG.txt`、
`INDEPENDENT_QA_CRITICAL_LOG.txt`、`INDEPENDENT_QA_NODE_LOG.txt`。
