# Owner Workbench V2 — UI Candidate

状态：`LOCAL=UI_CANDIDATE / HOSTED=TEST_ONLY_READ_ONLY / NO_PRODUCTION_WRITE`

这是独立 vanilla HTML/CSS/JS 候选，只验证统一后台信息架构、视觉与交互。
它不创建后端、账本、Identity、CRM 或发布入口，不读取客户资料，不连接生产。

## 本地查看

直接打开 `index.html`。演示登录只切换本地界面，输入不会发送或保存。

由原 Task Center Host 访问 `/workbench/` 时，页面先读取同源真实 Session，再读取
`../api/admin/workbench` 的 `UNIFIED_ADMIN_PROJECTION_V1`。Hosted 读取失败会明确
显示失败并清空旧数据，绝不回退本地 fixture；初始加载、每次 hash 切页和手动刷新
都会依次重新读取 Session 与投影，迟到响应会被 generation fence 拒绝。未接项目、财务、自媒体和服务器保持
`NOT_CONNECTED/UNKNOWN`。该 API 仅接受管理员只读访问，不提供写 capability。

Hosted 配置侧栏按“大模型 / 自媒体 / 服务器”分开：大模型仅显示 ModelControl
TEST_ONLY 只读字段，并可显示其已持久化用量事件和已配单价导出的
估算成本。该值明确不是 Finance 账本、实际扣费或付款凭证，未知币种不会
被推断；自媒体和服务器显示候选来源、证据与精确缺口，保持
`allowed_actions=[]`。本地 `file:` 候选仍显著标记合成；Hosted 可见区域只使用
`TEST_ONLY / READ_ONLY`，不把 fixture 文案带入真实接口页。

页面包含：

- 简洁的标签页级演示登录/退出、严格互斥的登录与工作台、可展开十一项一级导航；
- Owner 固定七个管理模块：运营、客户、研发、验收交付、维护、共享生态、财务；
- 总览、客户项目、研发任务以及各模块统一的筛选/列表/详情/权限范围操作/操作日志；
- 预览与审核工作区、页面树、合成预览、反馈、版本对比和证据；
- 设计稿/合成演示/开发版本/已安装/已验收五层状态；
- 任务与 AI、自营业务、权限与设置；
- 加载、空、错误、无权限、版本冲突、未接入状态样例。

数字孪生在本候选中只保留带 `object_ref` 与 `target_route` 的 TEST_ONLY 对象跳转卡；
不复制原任务系统的可视化或运行事实。服务端 capability 才是权限权威，前端隐藏或
禁用按钮不构成授权。

币安仅作为“玄钧AI新生态内的自营业务”出现，不是独立品牌或币安官方客服。

## 测试

```bash
node demos/owner-workbench-v2/tests/workbench.test.cjs
```

测试覆盖候选边界、登录互斥/退出、Hosted 初始/切页/手动刷新、加载/失败/重试/迟到响应、十一项一级及全部二级导航、详情高亮、
跨项目状态清理、筛选、五层状态、心跳/进展分离、自营业务身份、权限拒绝、
异常状态、无 iframe/外部依赖、移动端和减少动画契约。

## 接线边界

Hosted 只消费原服务的只读投影。确认、审核、部署、权限和财务动作必须回
原服务执行鉴权与留痕。现有 `/task-center-test/`、`/customer/center/` 和旧预览
网址保持不变；本候选不得自行创建重定向或替换生产入口。
