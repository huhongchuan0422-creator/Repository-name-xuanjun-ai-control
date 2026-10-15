关联原任务、完整批次、行为变化及实际验证。先读 AGENTS.md 和唯一规则文档。

- 完成实现、接线、异常、自检、登记后集中送审；Draft备份不等于交付。
- 下方填写唯一 `xj-delivery` JSON块；HEAD/规则哈希/完整变更文件清单须为实际值。
- 每个节点：id、state（DONE或EXTERNAL_BLOCKED）、criteria与evidence数组；DONE时blocker/owner/next_action/next_check为null，外部阻塞时全部给出具体内容。
- coverage须含permissions、input_files、concurrency_idempotency、timeout_interrupt、restart_recovery、partial_unknown、transaction_cleanup；每项写state（TESTED或NOT_APPLICABLE）和evidence数组，不适用必须说明理由。
- continuation.eligible_remaining必须为空才能完整送审；可推进工作仍存在时继续开发。next_action写下一责任方和动作。
- 证据区分静态、本地、模拟、Hosted、浏览器、实机、生产；声明和CI结构绿灯均不是独立批准。

示例结构（替换全部占位值并补齐节点、覆盖域及文件）：

```xj-delivery
{
  "rules_version": "2026.10.15.1",
  "rules_sha256": "填写规则文档真实SHA256",
  "head_sha": "填写当前PR真实HEAD",
  "task": "#17",
  "batch": "完整批次及验收边界",
  "developer": "真实开发身份",
  "changed_files": [],
  "nodes": [],
  "coverage": {},
  "wiring_evidence": [],
  "continuation": {"eligible_remaining": [], "next_action": "完成本批实现后集中独立审核"}
}
```

正式门禁的规则哈希取受保护默认分支版本；候选自测不是正式批准。修改治理信任根走独立审核的维护批次，普通PR不靠自行改hash解锁。
