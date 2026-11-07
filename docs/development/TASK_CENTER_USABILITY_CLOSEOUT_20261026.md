# 任务中心测试版可用性收尾（2026-10-26）

## 冻结基线与边界

- 现场基线：`62fd46a8e23683708c57900dc4ed386063334fa7`。
- R10 英国现场恢复：Owner 回执 `CONTINUATION_PASS`、退出码 `0`；本轮不重跑恢复。
- 运行模式：`TEST_ONLY`；真实模型出站：`DISABLED`。
- 本轮只修两项可见性缺口，不部署候选、不改现场数据库、身份、密钥、Nginx 或 unit。

## 可用入口与现有登录方式

- 登录页：`https://uk.wenwenwenyiyiyi.work/task-center-test/login.html`
- 已有 Owner 测试用户名：`owner`。
- 密码只存在英国主机 root-only 文件
  `/var/lib/xuanjun-task-center-test/v3/bootstrap-credentials.txt`。不得在聊天、日志或 URL 中输出；不得重置或新建账号。
- Owner 在既有获准 sudo 终端中读取现有凭据后登录；退出使用页面“退出”。

## 已复用的实际只读入口回执

- `/task-center-test/healthz`：TLS 校验成功、HTTP 200，返回
  `mode=TEST_ONLY`、`outbound=DISABLED`、`state=UP`。
- `/task-center-test/readyz`：TLS 校验成功、HTTP 200，返回
  `identity_adapter=CONFIGURED`、`mode=TEST_ONLY`、`state=READY`。
- 未登录访问 `/task-center-test/admin.html`：HTTP 302 到
  `/task-center-test/login.html`。
- 未登录访问 `/task-center-test/api/session`：HTTP 401。

这些回执证明 HTTPS 入口、健康、身份适配器和未登录边界；不证明登录后浏览器 E2E。

## 本轮最小修订

1. 任务详情从同一投影显示输入/输出版本、模块、规范化资源与该任务的回执时间线；无回执时明确“不据此推断未发生”。
2. 总览从服务端投影显示 P2、P3、社区/B5 的接入边界：
   - P2/P3：`NOT_IMPLEMENTED / NOT_EXECUTED`；
   - 社区/B5：`NOT_CONNECTED_EXTERNAL_FLOW / NOT_EXECUTED`。

未创建第二状态源；材料、资源、回执和边界均由 `/api/projection` 返回。

## 验证结果

- `python3 -m unittest -v tests.test_reusable_task_gateway tests.test_task_center_session_auth`
  - 33 项，退出码 0。
  - 覆盖登录/退出、CSRF、会话过期、管理/执行/QA/Security/验收角色、错角色/错任务/自审拒绝、刷新读取同一 SQLite 投影及本轮接入边界。
- `node tests/task_center_digital_twin.test.cjs`
  - 退出码 0。
  - 覆盖七板块、项目/任务下钻、中文及斜杠 ID、负责人、阻塞、下一动作、材料/资源、回执及接入边界渲染。

## 未验证与下一责任

- `BROWSER_UNVERIFIED`：当前执行环境没有可启动的受支持浏览器；已有 Chrome 会话也未启用可附着远程调试。因此未宣称登录后真实点击、刷新、退出或多角色浏览器 E2E 通过。
- 候选未部署；现场仍运行 62fd46a8。若 Owner 批准部署本候选，平台执行方须按既有原子 release/current、同一 DB/身份/密钥和回滚门禁生成准确部署包，再由浏览器验收人完成登录后 E2E。
- 生产 P2/P3、社区/B5 接线、真实模型密钥、付费 API 与生产调度均未实现/未执行。
