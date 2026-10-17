# 社区分账客户可视化交付：现有资产、身份关联与上线阻塞登记（2026-10-15）

权威源：PR118 已审基线 `71024b22...`；Stage5 下一阶段 Draft PR122（原Issue #76关联），此文记录开发资产而不新设工作队列，不修改生产门禁。

## 资产复用表
| 能力 | 路径/已有系统 | 策略 | 状态 |
|---|---|---|---|
| 消费者金额、商家、平台模拟 | `demos/community-local-e2e/{index,merchant,platform}.html` | REUSE | 仅离线演示 |
| SaaS模块预览、选配、Owner | `demos/community-local-e2e/saas-panel.html` | REUSE | 离线API+UI候选 |
| 社区分账入口 | `demos/visual/community-payment/index.html` | EXTEND | 本PR加入AI/Telegram/飞书入口；未接后端身份 |
| 商户入驻/驳回/补正原型 | 现有演示附件与Stage5商户模块；需接入网站归档 | EXTEND | 静态内容非真实入驻 |
| Telegram客户沟通 | 现有`XuanJunAI_ServiceBot`及 CRM/Adapter | REUSE_CHECK | 需实际Webhook、身份绑定证据 |
| 飞书 | 既有对话/认证Bridge需按系统登记核验 | REUSE_CHECK | 未验证可用，绝不写CONNECTED |
| 公共大脑/模型路由 | 玄钧 Common Brain 与对话路由 | REUSE | 需确认网站受控鉴权及调用链 |
| 统一客户身份与消息证据 | SaaS Tenant/CRM/项目 + 不可变事件模型 | EXTEND | 安全设计入第8.2.7节；真实跨渠道绑定未实现 |
| 自有域名 | `wenwenwenyiyiyi.work` | REUSE | DNS/TLS/路由/发布未取得实机可访问证据 |
| 站点发布/回滚 | 现有国内网站与既有发布控制 | REUSE_CHECK | 当前无主机写入会话，不允许臆造部署 |

## 上线诊断（区分已知事实与未验证原因）
1. 当前开发执行环境测试 `getent ahostsv4 wenwenwenyiyiyi.work` 未解析；`curl -IL https://wenwenwenyiyiyi.work/visual/community-payment/` 返回 `curl: (6) Could not resolve host`。这证明**此执行环境未成功解析目标域名**，不证明域名全球DNS坏、证书过期或生产服务宕机。
2. 当前GitHub PR122仅源代码改动，没有受控网站发布连接或正式Release Gate授权；仓库创建页面≠网站路由自动生效。尚缺部署现场的Web root、Nginx location、证书、国内备案/接入状态、可用Runner及实际回滚路径证明。
3. 不做未经审查的DNS、Nginx、服务端或生产资金路径更改。先在有网络权限的受控Runner/网站主机**只读**核查域名解析、站点根路径、反代、TLS、HTTP 200/404和既有上线方式；复用原站点，不新买服务器。
4. 经准入后先将 `demos/visual/community-payment/index.html` 与依赖的 `demos/community-local-e2e/**` 安全只读制品映射为自有域名下的隔离预览路径（不能仅复制一个index却保留失效相对跳转）；预览资源应标DEMO。API与消息后端必须单独通过正式鉴权和安全审查，不能静态页面谎称支持提交留证。
5. 联合验收：无ChatGPT登录的普通PC/手机浏览器真正访问HTTPS网址，测试所有角色链接、模拟功能、申请审核、AI/Telegram/飞书身份状态、反馈API授权、不可变留证、版本/撤销、Rollback，证据准确绑定发布提交和制品SHA。

## 同一客户三入口强制关联
- 必须统一权威`customer_id + tenant_id + project_id`，外部渠道标识通过站内认证后的短期一次性挑战绑定，不因用户名相似自动合并。
- 记录发送人身份、平台来源、事件ID、内容摘要、服务端时间、版本、前序摘要与审计导出；禁止静默覆盖。
- 尚无真实Webhook/飞书签名/模型Provider/证据数据库回执时保持 `IDENTITY_LINK=UNKNOWN`、`AI=NOT_CONNECTED`、`FEISHU=PENDING`、`EVIDENCE_LEDGER=NOT_CONNECTED`。
- 资产登记更新引用已有PR和真实准确提交，下一开发者应先读此表和第8.2.7节，避免另建客服或CRM。

`FIRST_PARTY_CUSTOMER_PREVIEW_GATE=HOLD`
`OMNICHANNEL_FEEDBACK_IDENTITY_EVIDENCE_GATE=HOLD`
`PR122=Draft`、`PR118/P2_UNCHANGED=YES`、`PRODUCTION_DEPLOYED=NO`。
