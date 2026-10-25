# 任务中心 MCP / Codex 接入（R6，TEST_ONLY）

## 状态与边界

- `scripts/task_center_mcp.py` 是自建、stdio MCP 外壳；它只调用现有任务中心 HTTP 业务入口，不建立第二任务库，也不开放 Shell、SQL 或任意文件读取。
- `scripts/codex_execution_adapter.py` 在同一 SQLite 中持久化发送意图、执行标识和事件；任务、attempt、Writer/fence/epoch 仍由原 Gateway/Supervisor 判定。
- Codex SDK 与 App Server 共用上述执行意图和状态机。SDK 用于自动化执行边界；App Server 仅作为需要会话、审批和流式事件时的传输边界。
- 本包没有安装 Codex SDK、没有启动 App Server、没有创建真实 OAuth grant、没有调用真实模型或部署服务。对应状态均为 `NOT_EXECUTED` / `UNVERIFIED`。
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

`PENDING → SENDING → ACKED/RUNNING/WAITING_APPROVAL → SUCCEEDED/FAILED`。
取消、发送结果不明和迟到结果分别处理：

- 发送前取消不发送；发送中取消进入 `CANCEL_REQUESTED`。
- 超时、断线或重启发现 `SENDING` 均进入 `UNKNOWN`，不得自动再启动一份。
- 旧 attempt/fence 的迟到结果只写历史事件，`accepted=0`，不推进当前任务。
- turn 完成、聊天结束或进程退出不是业务验收；成果仍需绑定 SHA、清单和独立审核。

## 本地启动顺序

1. 按任务中心 README 生成本地 TEST_ONLY SQLite、Fernet key、管理员 token 和 actor token 文件。
2. 启动 `scripts/task_center_app.py` 的 loopback HTTP 服务。
3. 将示例中的绝对路径、端口和绑定主体替换为本机值，再由支持 stdio MCP 的获准客户端加载。

不应把 token 写入 JSON 示例、源码、日志或前端存储。Hosted/ChatGPT 插件安装、真实账户授权、真实 Codex SDK/App Server 连接和生产部署均需另行验收。

## 官方协议依据

- ChatGPT Plugins: https://learn.chatgpt.com/docs/plugins
- Model Context Protocol: https://learn.chatgpt.com/docs/extend/mcp
- Codex SDK: https://learn.chatgpt.com/docs/codex-sdk
- Codex App Server: https://learn.chatgpt.com/docs/app-server
- OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
