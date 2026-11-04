# 任务中心 R6 统一整包交付报告

## 状态

本包是隔离 `TEST_ONLY` 应用候选，不是生产安装许可。源码冻结于：

- HEAD `91553badf5f7ba6fa9b7fa9472f3f2fe66e6a549`
- Tree `2a180f793e271ef73be69dd9eab460a2a17ad090`
- Base `e659a53340bfba1b7296321b8021e5e5a6febaf5`

## 已实现

- Connection/API Key/OAuth PKCE 服务端管理、目的地绑定、掩码投影和审计。
- Provider/模型目录、真实隔离 HTTP adapter、额度/价格/预算/TPM/RPM/并发/熔断门禁。
- 角色模板、Skill 审核绑定、唯一 Writer、独立审核/返工/验收闭环。
- 任务 preflight、资产查询证据、动作 scope/授权/审批角色及零副作用拒绝。
- 自建 stdio MCP 工具层，复用原 loopback HTTP 业务入口和同一 SQLite。
- Codex SDK/App Server 共用持久执行意图、UNKNOWN/取消/迟到结果隔离和重启对账边界。
- MCP、Codex 和模型执行均遵守零新增付费：资格、额度或价格 UNKNOWN/过期时 HOLD；不自动切付费 API。

## 缺陷关闭映射

| 问题 | 代码入口 | 正反测试 |
|---|---|---|
| MCP userinfo 绕过 | `scripts/task_center_mcp.py` | `test_loopback_url_cannot_be_bypassed_with_userinfo` |
| Codex 断线误记 FAILED | `scripts/codex_execution_adapter.py` | `test_connection_and_malformed_receipt_after_send_are_unknown` |
| quota 过期仍发送 | `scripts/model_orchestration.py` | `test_stale_quota_verification_holds_before_adapter_call` |
| Codex actor/scope 未绑定 | `scripts/codex_execution_adapter.py` | `test_unassigned_actor_and_noncanonical_scope_have_zero_intents` |
| ACKED 被假取消 | `scripts/codex_execution_adapter.py` | `test_acked_cancel_is_request_not_false_terminal` |
| 资格变 UNKNOWN 仍发送 | `scripts/model_orchestration.py` | `test_qualification_unknown_after_queue_holds_before_adapter_call` |
| MCP 仅 mock | `tests/test_task_center_full_journey.py` | `test_project_to_model_to_independent_review_acceptance` |
| 审核角色触发 Codex | `scripts/codex_execution_adapter.py` | `test_reviewer_assignment_never_authorizes_codex_transport` |
| 已授权执行角色随后撤权 | `scripts/codex_execution_adapter.py` | `test_executor_role_revocation_after_intent_blocks_transport` |

此前 Security 六项失败以及上述失败历史均保留在 `PRE_*` 原始日志与双审报告中，未删除。

## 测试

- 适用回归：271/271 次执行，226 个不同测试标识，退出码 0。
- 受影响定向：93/93，退出码 0。
- 旧 SQLite 迁移 3 项：`NOT_EXECUTED`。
- 独立 QA：PASS，阻断 0。
- 独立 Security：PASS，阻断 0。

## 准确限制

- 真实 OAuth、外部 Provider、真实 Codex SDK/App Server、Hosted MCP/ChatGPT、真实账户与生产部署：`NOT_EXECUTED / UNVERIFIED`。
- 浏览器：`BROWSER_UNVERIFIED`。
- 外部旧 ChatGPT/Work 窗口唤醒：`UNSUPPORTED / UNVERIFIED`，MCP 不宣称接管。
- `NEW_PAID_API_USAGE=NONE`；未录入真实凭据、未发真实模型请求、未部署。
