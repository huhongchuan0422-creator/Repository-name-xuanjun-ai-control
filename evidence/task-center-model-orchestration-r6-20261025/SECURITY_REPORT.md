# R6 最终同版独立 Security 报告

- 结论：PASS；阻断缺陷 0。
- HEAD：`91553badf5f7ba6fa9b7fa9472f3f2fe66e6a549`
- Tree：`2a180f793e271ef73be69dd9eab460a2a17ad090`
- 审查方式：只读，未修改冻结候选。

## 复核

- Codex actor 只允许 current writer、execution unit responsible party，或当前 attempt 下 `ASSIGNED + EXECUTOR + writer_allowed=1 + enabled=1` 的主体。
- intent 持久化 `requesting_principal`；发送前再次核权。撤权后记 `FAILED / REQUESTING_ACTOR_REVOKED`，不写 SENT、不进入 transport。
- REVIEWER assignment 创建被拒且 intent 数量为 0；EXECUTOR 创建后撤权时 transport 调用数为 0。
- OAuth/Connection、预算/TPM/并发、UNKNOWN/EXHAUSTED 零调用、禁止付费回退、MCP token/actor/loopback、Codex UNKNOWN/取消/迟到隔离、Writer/action scope/审批、Skill/模块和冻结审核门禁均无新增阻断。

## 独立复跑

- Targeted：93/93，退出码 0。
- Scoped：271/271，226 distinct，3 项旧迁移 `NOT_EXECUTED`，退出码 0。
- RAW_FINAL Targeted SHA256：`cc20fde2e9aa920750d2f58e75e95a4e1c24cef39432f2caccfbbbc99f136970`。
- RAW_FINAL Scoped SHA256：`925941cbe2523de0a8718690bef3887484ee4d3b47d6c4ab37f33ade53ff850e`。

## 边界

未执行真实 OAuth、外部 revoke、外部 Provider/付费模型、真实账户 quota、Hosted MCP/ChatGPT、Codex SDK/App Server、浏览器、staging/生产部署。仅 fixture/loopback；`NEW_PAID_API_USAGE=NONE`，真实账户额度/成本 `UNKNOWN`。

