# Issue76/PR122｜微信服务商接入离线增量（2026-10-17）

## 实际完成

- 新增纯标准库 `scripts/community_wechat_sp_offline_guard.py`：小程序支付前草案输入约束、客户两处广告位置（PREPAY_AD、POSTPAY_AD）、金额（分、CNY）、SP商户号格式、缺少真实sub_mchid的OFFLINE_CANDIDATE_ONLY状态；即便提供sub_mchid，也只认UNVERIFIED。
- 对未经可信微信支付签名和服务端订单对账的通知一律隔离：不得凭客户端`SUCCESS`或`verified`声明改变Finance余额、订单、分账或退款。
- 新增10项离线测试，专用GitHub-hosted CI已执行。测试不会读取微信支付Secrets。
- 代码为**独立适配契约候选**，不是新订单/账本/结算引擎。原商户/店铺/报价/订单/退款实现继续由Stage5既有代码负责：`scripts/community_saas_phase2.py`、`scripts/community_saas_order_preparation.py`及原社区分账模块。此分支不覆盖原Work的PR122 writer路径。

## 真实服务商接线边界

Owner已配置微信小程序上传密钥、服务商商户号、商户API私钥、证书序列号、APIv3密钥。原受保护探针使用`GET /v3/certificates`取得HTTP 404 RESOURCE_NOT_EXISTS。微信支付公钥模式下该接口不能当作服务商认证PASS，不在此分支调用真实支付API。

生产还缺：受控Customer/Store服务端主体绑定、合法真实`sub_mchid`及微信支付商户授权、微信支付公钥/公钥ID的可信验证来源、订单金额和回调验签/解密的真实服务端接线、幂等持久事务与Finance对账、分账权限和真实小额验收。所有资金门禁仍HOLD。

## 下一阶段对接条件

1. 在现有Stage5业务代码中增加可审核的`provider-neutral`支付适配器接口；不新增第二套Finance或订单数据库。
2. 让可信服务端提交签名验证及商户绑定证明，再由原订单状态机消费；**不能**把纯字典`verified=true`当认证。
3. 两处广告继续作为客户端展位控制，不能改变订单总额、支付回调或分账资金。
4. 先隔离CI+独立审核，生产变更和真实交易需要现有发布门禁。

以上不涉及实际支付或现场部署。

## 二期：小程序双广告位离线支付页面投影

- `scripts/community_wechat_sp_mock_checkout_view.py` 提供只读视图函数，依赖原 `community_wechat_sp_offline_guard` 验证金额、商户绑定版本、两广告槽及CNY分金额；只接已有订单ID，不增加订单/Finance表。
- 小程序付款前广告可显示；付款后广告只在明确的 `MOCK_PAID_SIMULATED` 本地模拟状态显示，失败/取消/等待不显示。两广告均不可证明微信支付成功。
- 拒绝跨tenant/store读视图与客户端自报真实 `SUCCESS/PAID`；所有输出 `payment_verified=False, finance_effect=NONE, provider_payment=HOLD, profitsharing=HOLD`。
- `tests/test_community_wechat_sp_mock_checkout_view.py` 新增8项离线回归，与原10项合计18项。精确源HEAD `6ef7704009064cded7919b5cea7c27faa52727d9` CI #39001031043 / Job117303789308 原始日志 `Ran 18 tests ... OK`，Actions success；该证据仅覆盖离线源候选，不是微信真实小程序浏览器/支付签名/结算验收。
- 仍沿用Issue76/PR122和现有业务模块，不接触Work现任writer路径、不改原代码。生产与真实资金全部HOLD。下一阶段交既有集成owner接入现有小程序页面和订单读模型，之后集中独审。
