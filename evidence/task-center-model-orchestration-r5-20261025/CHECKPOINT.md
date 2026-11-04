# R5 恢复检查点

- 实现 Commit：`998566d52634ff3cb5b3bd2d68df8cad5f2966a7`
- 实现 Tree：`1b4783e64f36172825d534855c2ff3c28888c989`
- 已完成：同库后台、Provider/密钥、两个适配器、评测/路由、角色/Skill、持久
  队列、租约/UNKNOWN、成本/用量、项目入口、独审返工、动作门禁、WAL 只读投影、
  路由修复、独立主体认证、候选不可回退、canonical 验收撤权、版本化动作授权、
  SSRF（已验证地址与实际 socket 绑定）/未知副作用/迟到结果门禁、attempt 级
  preflight/变更绑定、验收崩溃收敛和集中回归。
- 在途：无生产或外部动作。
- 未完成：真实浏览器、真实 Provider、部署和 P2/P3/社区/B5 接线。
- 测试：232/232 次作用域执行 PASS；187 个不同标识；旧迁移 3 项
  NOT_EXECUTED；Node UI PASS。
- 恢复：校验 Manifest 和归档 SHA，解包后运行
  `python3 scripts/run_r5_scoped_tests.py` 与
  `node tests/task_center_digital_twin.test.cjs`。
