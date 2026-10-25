# 失败审查历史（保留，不覆盖）

## 冻结候选 a16a7cff（REJECT）

独立 QA 与安全审查均从 Git object 解包到临时目录复核，并拒绝
`a16a7cff0159efc940f73ea035a4798fb4c011bf`。确认的阻断包括：

1. 候选验收未闭合 canonical task 的 SUCCESS、撤权与 outbox。
2. 返工可复用同一 artifact，ACCEPTED 可回退，SHA 只验长度。
3. Reviewer/Acceptor 仅为管理员请求体字符串，角色分配可先后绕过自批门禁。
4. preflight、scope change 与 authorization 未完整绑定当前资产版本/attempt/Writer。
5. Provider 限速不统计真实调用尝试，迟到旧 Worker 可覆盖 UNKNOWN。
6. `KNOWN_PAID` 缺单价时被错误计为已知零成本。
7. Provider URL 可指向私网/含 userinfo，默认允许重定向。
8. 模型请求幂等只比较 payload，跨任务可误判重复；传输异常可能盲重试。
9. 首次管理员 GET 依赖尚未显式初始化的模型表。

该版虽有 213 次执行/168 个不同测试标识通过，仍被判定 `BLOCK/REJECT`；这证明
作者回归全绿不等于独立验收。上述失败不从历史删除。集中修复提交为
`53c954b80f6e4285f14f48531eb378c6b378a5ee`，其复审结论另见最终 QA/Security
报告。

## 冻结候选 c77bdc7b（REJECT）

第二轮独立 QA 与安全审查从 Git object 解包复核并拒绝
`c77bdc7b20dbff149c0ccd01fa59e9cb44dbf3cb`。可执行反例包括：DNS
校验与真实连接之间二次解析、preflight/变更未绑定 attempt/Writer、可信
Executor 可跨角色审批扩范围、动作幂等未绑定完整授权身份、canonical 完成后
候选落账前崩溃无法收敛、较旧候选可覆盖更新提交、付费 Provider 下伪装免费
Model 缺少单价，以及 benchmark 绕过调用尝试限速。该版虽有 220 次执行/
175 个不同测试标识通过，仍为 `BLOCK/REJECT`。

上述反例集中修入 `0382a028c72b3c39207f5ec2a424d8656f05fcaa`，并进一步在
`0c8eb1dba79bfb05400687b888ff32d0fa23e769` 将 vetted sockaddr 与实际
socket 直接绑定，消除 `socket.create_connection` 的隐式二次解析。最终独审
结论另见同版 QA/Security 报告。

0c8 同版 QA 继续发现 terminal outbox artifact 未与候选绑定、跨 attempt 的
相同 preflight body 会命中旧主键两项问题。最终实现
`09edb47dc742ac55da7266f2decc53937f50c3ab` 补齐 terminal artifact 门禁，并将
attempt/Writer 纳入 preflight 身份。0c8 不作为最终通过版本。

09ed 同版安全审查再发现“先审批 scope change、后分配同主体为 Executor”的顺序
绕过。`da722968781bfaeca80265b363ede6c1b8e896fb` 在动作实际准入点重新核验审批人
当前角色，使角色冲突后的旧审批失效；09ed 的 QA PASS 不被移作 da722 的同版
验收结论。

da722 同版 QA 通过普通顺序负例后，进一步通过双连接并发注入发现角色复核与
动作写入之间的 TOCTOU；同版安全复审另发现 Provider 从免费切换为付费时，旧
免费模型仍可能按零成本运行。最终实现
`0e476771799c9bae422bb97659f4d17e951bdc25` 将动作准入完整包入
`BEGIN IMMEDIATE`，并在 Provider 价格切换时强制现有模型具备明确付费单价。

0e476 同版独审进一步证明 Provider 兼容检查本身也必须与 Provider 写入、Model
写入互斥。最终实现 `998566d52634ff3cb5b3bd2d68df8cad5f2966a7` 将两条价格
写路径各自完整放入 `BEGIN IMMEDIATE`，并加入双连接竞态回归；0e476 不作为
最终通过版本。
