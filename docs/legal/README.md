# 玄钧云汇协议与合同草案库

状态：CANDIDATE_DRAFT_ONLY；22份草案，未正式签署、未部署。

## 放置与使用

正文是本目录 templates 下的版本化 Markdown，registry.json 记录哈希、受众及业务位置；demos/legal/ 是生成的阅读页。正式计划为 /legal/，当前仅静态候选文件链接，既有自定义 /demo/ HTTP服务的路由映射须在后续集成验收，不假定已可在线访问。

| 文件 | 适用环节 |
|---|---|
| [社区分账商户入驻协议](templates/merchant-onboarding.md) | 商户入驻提交前、商户工作台 |
| [社区交易多方分账协议](templates/community-split.md) | 分账规则确认/变更、社区后台、分账方后台 |
| [社区分账技术服务与消费者使用条款](templates/community-service.md) | 付款前、消费者帮助中心 |
| [玄钧云汇隐私政策](templates/privacy.md) | 站点页脚、注册、入驻、反馈、购买 |
| [社区交易退款、分账冲回与责任规则](templates/refund-responsibility.md) | 支付确认前、退款申请、商户/分账方对账 |
| [玄钧云汇平台服务协议](templates/platform-terms.md) | 注册、平台页脚 |
| [SaaS模块订阅、买断与订单条款](templates/saas-order.md) | 模块购买前、SaaS工作台 |
| [软件与AI定制开发主合同](templates/custom-development.md) | 客户项目签约、合同中心 |
| [定制项目需求范围、报价与验收任务书](templates/custom-sow.md) | 定制合同附件A |
| [项目变更单与阶段验收交付单](templates/change-acceptance.md) | 项目变更、阶段/最终验收 |
| [双向保密协议](templates/nda.md) | 需求交流前、分包合作 |
| [个人信息与客户数据委托处理附件](templates/data-processing.md) | 企业合同附件、供应商接入 |
| [托管部署、维护与服务等级协议](templates/sla.md) | 部署/维护订单附件 |
| [第三方订阅与云资源代购委托协议](templates/procurement.md) | 代购付款前 |
| [AI服务、BYOK与模型使用附加条款](templates/ai-service.md) | AI功能启用、模型付款/配置 |
| [专项服务包、赠送权益与抵扣规则](templates/service-package-rights.md) | 服务包购买前、权益中心 |
| [推荐合作与佣金结算协议](templates/referral.md) | 推荐计划加入前、佣金工作台 |
| [开发者合作、模块上架与知识产权协议](templates/developer-marketplace.md) | 开发者入驻、模块上架 |
| [广告投放与素材授权服务合同](templates/advertising.md) | 广告下单、素材提交 |
| [公益项目合作与信息披露协议](templates/charity.md) | 公益项目接入前 |
| [内容创作、小说与素材委托及授权协议](templates/content-license.md) | 小说/内容项目签约 |
| [电子签约、授权与合同证据规则](templates/esign-evidence.md) | 正式签约前、合同中心 |

## 正式启用前一次补齐

实际签约主体及登记号/地址/联系方式；商户和接收方授权与渠道资格；具体费率/税务/支付币种/结算周期；服务包SKU/奖励系数；客服与退款时限；数据字段/供应商/处理地区/保存期限；合法争议机制；独立法律审查及Owner发布门禁。未填不生效、不进入真实签约或支付。

不收集真实证件或签名到公开仓库；生产签署文件和授权证据仅进入既有受控存储。本轮没有签约平台采购、账户开通或真实法律文件签发。

## 定制签约建议

前期用第三方电子签约SaaS网页发起，不必先开发自有签名系统；需求、报价、知识产权/复用、里程碑和后续费用随主合同一次签。量起来再接API，并核验真实身份/代表授权、可靠电子签名、回调验证、证据导出/迁出与隐私。纸签备选，聊天为补充证据。

## 核对的法规与官方资料（2026-10-15）

- 电子签名法（2019修正）：https://scjgj.beijing.gov.cn/cxfw/flfgcxfw/qyjgl/202006/t20200621_1929596.html
- 民法典：https://www.moj.gov.cn/pub/sfbgw/zwgkztzl/2025nianzhuanti/2025mfdxcy/2025mfdxcy_mfdql/202505/t20250507_518708.html
- 消费者权益保护法实施条例（预付款书面约定/退款）：https://www.mee.gov.cn/zcwj/gwywj/202403/t20240320_1068830.shtml
- 个人信息保护法：https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm
- 非银行支付机构监督管理条例官方解读：https://www.moj.gov.cn/pub/sfbgw/zcjd/202312/t20231215_491722.html

以上为核对资料，不表示任何主管机关认可本平台，也不是对具体地区或合同的最终法律意见。模板须与实际产品、资质、消费者/企业身份及适用法律核对。
