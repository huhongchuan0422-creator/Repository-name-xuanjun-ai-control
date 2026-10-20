# 社区分账自有域名客户可视化预览发布方案（受控候选，不是发布批准）

## 业务目标与硬门禁

Owner明确授权：社区分账所有客户预览界面复用玄钧现有主域 `wenwenwenyiyiyi.work`，客户无需登录ChatGPT；同时保留消费者、商家、社区、分账方、平台管理、Owner、入驻申请、资料补正及审核等角色入口，支持可交互演示、跳转、客户反馈。此发布不等于真实微信支付/分账/资料审批上线。

当前PR122是Draft；PR118准确审核基线 `71024b22f0d6110f0507dbd8476468313f8846f2` 不变。PR17/P2生产门禁仍HOLD。**严禁通过部署演示前端绕过生产release gate、直接写网站根目录或重新启动旧writer。**

## 现有静态源码与建议映射

- 自有域名候选：`https://wenwenwenyiyiyi.work/visual/community-payment/`，必须由站点负责人按现有中文/英文路由确认后再生效。
- Portal：`demos/visual/community-payment/index.html`，包含主要角色入口说明和实际导航到下述模块页面；社区和分账方当前仅共用平台视图，尚非独立鉴权的客户界面。
- 消费者：`demos/community-local-e2e/index.html`
- 商家：`demos/community-local-e2e/merchant.html`
- 平台：`demos/community-local-e2e/platform.html`
- SaaS功能、套餐与Owner离线预览：`demos/community-local-e2e/saas-panel.html` 与对应 `.mjs`
- 另有客户评审的综合单页静态原型V1.1，11个角色/流程页面（含商家入驻申请和平台审核）：本会话制品 `community_visual_demo_v11.zip`；应先入受控源码仓库及制品哈希，再考虑进入网站静态资源目录。不能拿沙盒链接当正式客户URL。

## 必要的受控网站接线动作（需站点运行权限）

1. 检查当前域名解析、证书、nginx/静态网站路由/部署目录和已部署版本；避免修改现有网站其他路由。
2. 对候选URL创建独立静态目录或复用既有深层路由，路由的相对资源路径必须和静态制品目录实际一致，不可出现404及跨域问题。
3. 在经过发布门禁批准的测试/预览环境内使用精确commit及hash落地文件、测试无副作用、自动备份旧目标，回滚只影响本次新增预览目录。
4. 所有入驻资料与审核流程先使用隔离假数据；未接权限、加密附件存储、真实审批账本之前不能收集客户营业执照/银行账户/身份证/生产密钥。
5. 客户反馈服务必须接入经认证的第一方API、项目/角色权限、版本、操作记录；当前静态单页反馈不具服务器持久化，不得宣称已进入GitHub任务队列。
6. 从未登录ChatGPT的PC及手机访问真实URL，实测首页、各角色导航、返回、入驻提交/驳回/补正/重新提交、广告A/B、可调分账、网络刷新、响应式、安全隔离。真实公网地址存在前必须保持 `FIRST_PARTY_CUSTOMER_PREVIEW_GATE=HOLD`。
7. 审核通过并获正式部署授权后，在原PR/ledger记录URL、DNS/TLS证据、HEAD、TREE、构建hash、测试及回滚回执。没有原主机写入接口或发布批准时明确 `DEPLOYMENT_BLOCKED`，不能虚构上线。

## 当前事实

本轮已在PR122保存 first-party Portal 源码并将完整11屏综合静态演示包生成为可下载的候选制品。**在本执行环境中无法取得自有域名DNS解析，亦未发现可用的生产网站/主机发布工具**。所以网站发布尚未完成，`PUBLIC_PREVIEW_URL_VERIFIED=NO`、`FIRST_PARTY_CUSTOMER_PREVIEW_GATE=HOLD`、`PRODUCTION_DEPLOYED=NO`。
