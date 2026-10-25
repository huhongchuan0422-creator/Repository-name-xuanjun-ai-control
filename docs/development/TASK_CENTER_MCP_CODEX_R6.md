# 任务中心 MCP / Codex 接入（R6，TEST_ONLY）

## 状态与边界

- `scripts/task_center_mcp.py` 是自建、stdio MCP 外壳；它只调用现有任务中心 HTTP 业务入口，不建立第二任务库，也不开放 Shell、SQL 或任意文件读取。
- `scripts/codex_execution_adapter.py` 在同一 SQLite 中持久化发送意图、执行标识和事件；任务、attempt、Writer/fence/epoch 仍由原 Gateway/Supervisor 判定。
- Codex SDK 与 App Server 共用上述执行意图和状态机。当前已实现具体的 App Server stdio JSON-RPC 传输：`initialize/initialized → thread/start 或 thread/resume → turn/start`，并持续消费交错通知、审批请求和 `turn/completed`。响应按官方嵌套 `result.thread.id/sessionId`、`result.turn.id` 读取；`turn/interrupt` 的空响应只表示取消请求已收，须等待 `turn/completed.status=interrupted` 才写 `CANCELLED`。重启通过 `thread/resume` 与 `thread/turns/list` 对账。SDK 仍只有明确的适配边界，具体 SDK transport 为 `NOT_IMPLEMENTED`。
- `task_center_app.py` 可在显式提供固定 `--codex-app-server-command-json` 时启动 TEST_ONLY 后台循环；它从同一 SQLite 领取持久意图、恢复待对账执行并消费取消请求，网页关闭不影响该循环。命令来自服务启动配置，不来自任务或模型输出。
- 本包没有安装 Codex SDK、没有连接真实 App Server 账户、没有创建真实 OAuth grant、没有调用真实模型或部署服务。真实账户及 Hosted 能力均为 `NOT_EXECUTED` / `UNVERIFIED`。
- MCP 自建不代表模型调用无限免费。任何模型调用都必须通过 `model_quota_status`：资格、余量或费用为 `UNKNOWN` 时发送前 `HOLD`；`EXHAUSTED` 时停止；不自动切换付费 API、不充值。

## 连接类型

`service_connections.purpose` 只接受：

1. `MODEL_INFERENCE`：模型推理 API。
2. `MCP_TOOL`：MCP 工具连接。
3. `CODEX_EXECUTION`：Codex SDK / App Server 执行连接。

连接的鉴权成功、OAuth 已连接、模型调用成功和业务验收是四类不同事实，不能互相替代。凭据仅在服务端加密保存，投影只返回掩码。

## MCP 工具

`task_list`、`task_read_context`、`task_claim`、`task_report_progress`、
`task_save_checkpoint`、`task_submit_artifact`、`task_request_review`、
`task_query_result`。

工具参数不能指定租户、主体、角色、数据库、命令或路径。服务端使用配置时绑定的 actor token 重新核验主体；领取使用原子 Writer/fence 入口，提交使用原候选与独立审核门禁。示例配置见 `examples/task-center-mcp.example.json`；所有 token 文件必须由当前用户持有且权限为 `0600`。

## Codex 状态规则

`PENDING → SENDING → ACKED/RUNNING/WAITING_APPROVAL → EXECUTION_COMPLETED/SUCCEEDED/FAILED`。
取消、发送结果不明和迟到结果分别处理：

- 发送前取消不发送；发送中取消进入 `CANCEL_REQUESTED`。
- 超时、断线或重启发现 `SENDING/ACKED/RUNNING/WAITING_APPROVAL` 均进入 `UNKNOWN` 待对账，不得自动再启动一份；具有持久 `thread_id` 的 App Server 执行只做 `thread/resume` 附着，不创建新 turn。
- 发送中收到取消时，迟到 ACK 仍保存 execution/session/thread/turn 标识；随后调用 transport interrupt，RPC 空响应仍保持 `CANCEL_REQUESTED`，只有 `turn/completed.status=interrupted` 才收敛为 `CANCELLED`。
- 旧 attempt/fence 的迟到结果只写历史事件，`accepted=0`，不推进当前任务。
- turn 完成只落 `EXECUTION_COMPLETED`，聊天结束或进程退出也不是业务验收；成果仍需绑定 SHA、清单和独立审核。

## 本地启动顺序

1. 按任务中心 README 生成本地 TEST_ONLY SQLite、Fernet key、管理员 token 和 actor token 文件。
2. 启动 `scripts/task_center_app.py` 的 loopback HTTP 服务。仅在已核准且本机已有 App Server 可执行文件时，额外传入例如 `--codex-app-server-command-json '["codex","app-server"]'`；本包没有替用户安装或启动真实账户连接。
3. 将示例中的绝对路径、端口和绑定主体替换为本机值，再由支持 stdio MCP 的获准客户端加载。

不应把 token 写入 JSON 示例、源码、日志或前端存储。Hosted/ChatGPT 插件安装、真实账户授权、真实 Codex SDK/App Server 连接和生产部署均需另行验收。

## R6 集中收口门禁

- Codex intent 必须绑定 `CODEX_EXECUTION` connection 及其配置版本、启用中的 provider 及其配置版本，并绑定一小时内核验为 `AVAILABLE` 的可归因额度来源。既有套餐内额度可用；免费/TEST_ONLY 来源还必须对应 `KNOWN_FREE` provider。入队后发送前重新核验连接、provider、价格状态和额度；配置改变、`UNKNOWN/EXHAUSTED` 或已知付费目的地均零调用且无付费 fallback。
- OAuth revoke 原子失效 pending/exchanging flow 并递增连接版本；迟到兑换结果不能恢复 `ACTIVE`。刷新结果不明或解析失败会清除旧 refresh token 并要求重新授权，避免重放可能已旋转的 token。
- 缺失或部分 usage 写入逐次记录为未知，不生成伪 0 token 汇总，预留费用维持 `UNKNOWN` 待对账。
- Skill 的已审内容、版本和摘要由服务端装入真实出站 messages；撤销或错版在发送前归 HOLD。
- 验收清单由任务冻结的 acceptance 集合决定；缺项、空证据、自降 `required`、FAIL/NOT_EXECUTED 或版本不符均拒绝。

## 官方协议依据

- ChatGPT Plugins: https://learn.chatgpt.com/docs/plugins
- Model Context Protocol: https://learn.chatgpt.com/docs/extend/mcp
- Codex SDK: https://learn.chatgpt.com/docs/codex-sdk
- Codex App Server: https://learn.chatgpt.com/docs/app-server
- OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
