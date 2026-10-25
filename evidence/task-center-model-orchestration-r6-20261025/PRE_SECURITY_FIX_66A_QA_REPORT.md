# R6 独立 QA 复审报告

- 审查角色：独立 QA（只读，不修改冻结候选）
- 结论：PASS
- HEAD：`66af5fce81fdf87112b4218aba96beba3653f0c7`
- Tree：`d2488d3ab89b5b466e8f8e22f78aae640d361700`
- tracked/index diff：均为 0

## 复审结果

1. MCP 使用结构化 URL 解析，拒绝 userinfo、外部 hostname、路径、query 和 fragment。
2. 进入 Codex transport `send` 后的断线、畸形回执等均收敛为 `UNKNOWN`；只有可证明的预发送 transport unavailable 记为 `FAILED`。
3. quota `AVAILABLE` 在原子 reservation 中检查 3600 秒时效，过期即发送前 HOLD。
4. Codex actor、goal、scope、acceptance、asset version、reuse evidence 与权威 unit/spec/preflight 绑定；拒绝时 intent 零写入。
5. `ACKED` 后取消进入 `CANCEL_REQUESTED`，不再假称远端已取消。
6. 已排队请求的最新模型资格不是 `QUALIFIED` 时发送前 HOLD。
7. Full journey 实际经过 MCP → loopback HTTP 的 claim/list/context 路径。

## 机械证据

- Scoped：269/269 次执行，224 个不同测试标识，退出码 0。
- Targeted：91/91，退出码 0。
- Scoped 日志 SHA256：`acc99211ce78107b6c97d599aa5afdfd4817416339c6f520b6b77024c4ffa6ad`。
- Targeted 日志 SHA256：`52487df2b57fc2b8f2350be08b44e92a81dbc027c2e77b7573d4320e747a70e2`。
- 两份日志均在首部绑定相同 HEAD/Tree。
- 3 项旧 SQLite 迁移明确 `NOT_EXECUTED`。

## 未执行边界

浏览器 `BROWSER_UNVERIFIED`；真实 OAuth grant、Codex SDK、App Server、Hosted/ChatGPT 安装、真实模型调用及生产部署均 `NOT_EXECUTED / UNVERIFIED`。

