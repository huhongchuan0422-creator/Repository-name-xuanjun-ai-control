# 玄钧AI新统一管理后台：Owner确认后分批接入计划 V1

> 框架设计基线已获Owner确认；下表仍按“源码框架、真实接线、部署、验收”分别计状态，不能互相替代。

| 批次 | 独立功能 | 原数据来源 | 验收 | 回滚 |
|---|---|---|---|---|
| 0 | 冻结导航、设计token、组件、移动规则 | Owner确认的UI候选 | 文档/CSS同版、独立源码审核；浏览器截图单列 | `SOURCE_IMPLEMENTED`，浏览器验收待补 |
| 1 | AppShell、候选登录、总览、只读入口目录 | 候选为本地演示状态；正式版依赖现有Identity/RBAC、入口注册表 | 登录互斥/退出、导航/返回/权限状态/响应式 | 源码框架已开工；正式Identity与Hosted均`NOT_CONNECTED` |
| 2 | 项目列表、项目详情、阶段/待办 | CRM、Customer Project Center、Project Delivery投影 | 同一项目/版本/责任/UNKNOWN准确 | 断开adapter，显示NOT_CONNECTED |
| 3 | 预览与审核中心只读版 | PR122 Preview/Changes、页面/UI版本、证据索引 | 页面与版本绑定、旧受保护入口可追溯返回 | 关闭中心路由，不动原preview |
| 4 | 意见草稿、逐页提交、复验 | 原项目/验收服务的鉴权写接口 | 幂等、权限、版本冲突、拒绝原因、审计 | 停写入口，保留只读与原记录 |
| 5 | 任务/AI/孪生只读接线 | Task Supervisor、GatewayKernel、ModelControl、Evidence | 心跳与成果分离、UNKNOWN、恢复链准确 | 断开投影，不停止原任务系统 |
| 6 | 应用、客服、商业、自营、治理分域接入 | 各原Registry/CRM/Ledger/Monitoring | 跨租户拒绝、角色分离、财务事实不推断 | 按adapter逐域关闭 |
| 7 | 安装与验收入口 | 原受控安装/恢复和客户验收服务 | 同版Commit/制品/安装/验收证据 | 移除入口，不改安装系统 |

每批只接一个可独立验收的增量；不因某安装入口未就绪阻塞其他只读页面，也不以源码/测试/预览替代安装或客户验收。
