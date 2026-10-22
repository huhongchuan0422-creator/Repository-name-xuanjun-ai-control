# 社区逐页UI预览清单

仅示例状态；无真实登录、API调用、业务写入或资金动作。消费者为原小程序界面投影，不是新增H5业务端。

|角色|页面|点击路径|原字段来源|
|---|---|---|---|
|商家工作台|订单|`#/merchant/merchant-0-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|商家工作台|订单详情、退款与分账|`#/merchant/merchant-1-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|消费者退款申请审核|`#/merchant/merchant-1-1-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|商家工作台|退款预审|`#/merchant/merchant-1-2-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|分账方案计算|`#/merchant/merchant-1-3-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|门店资料|`#/merchant/merchant-2-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|多门店管理|`#/merchant/merchant-3-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|门店员工与权限 · 生成原客户中心邀请|`#/merchant/merchant-4-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|门店员工与权限 · 保存门店员工权限|`#/merchant/merchant-4-0-1/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|商品管理|`#/merchant/merchant-5-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|商品定价与库存|`#/merchant/merchant-6-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|广告管理与审核|`#/merchant/merchant-7-0-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|广告事件报表|`#/merchant/merchant-8-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|商家工作台|模拟对账|`#/merchant/merchant-9-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|商家工作台|微信退款与分账处理|`#/merchant/merchant-10-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|商家工作台|退款申请|`#/merchant/merchant-10-1-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|分账回退|`#/merchant/merchant-10-2-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|分账规则|`#/merchant/merchant-10-3-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|分账申请|`#/merchant/merchant-10-4-0/list` → `detail` → `edit` → 演示保存返回列表|workbench.html|
|商家工作台|真实资金记录与对账|`#/merchant/merchant-10-5-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|商家工作台|微信官方账单|`#/merchant/merchant-11-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|workbench.html|
|社区管理|个人资料与推荐关系|`#/community/community-0-0-0/list` → `detail` → `edit` → 演示保存返回列表|communities.html|
|社区管理|社区资料|`#/community/community-1-0-0/list` → `detail` → `edit` → 演示保存返回列表|communities.html|
|社区管理|打开社区|`#/community/community-2-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台审核|`#/platform/platform-3-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|社区管理|社区订单、收益与结算观察|`#/community/community-4-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台配置社区分账接收关系|`#/platform/platform-4-1-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台运营查询|`#/platform/platform-5-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台商家管理|`#/platform/platform-6-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|社区管理|社区推广|`#/community/community-7-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|商家入驻|经营信息 1|`#/admission/admission-basic-0/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.html|
|商家入驻|资料清单与版本|`#/admission/admission-materials/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.html|
|商家入驻|管理员|`#/admission/admission-contact_info-/edit` → 演示保存返回 `admission-business`；仅适用分支可见|onboarding.js|
|商家入驻|经营主体|`#/admission/admission-subject_info-business_license_info-/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻|法人身份证|`#/admission/admission-subject_info-identity_info-id_card_info-/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻|其他法人证件|`#/admission/admission-subject_info-identity_info-id_doc_info-/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻|经营场景|`#/admission/admission-business_info-/edit` → 演示保存返回 `admission-business`；仅适用分支可见|onboarding.js|
|商家入驻|结算规则|`#/admission/admission-settlement_info-/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.js|
|商家入驻|结算账户|`#/admission/admission-bank_account_info-/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.js|
|商家入驻|其他受益人资料|`#/admission/admission-beneficiary/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻|申请状态与补件|`#/admission/admission-result/edit` → 演示保存返回 `admission-result`；仅适用分支可见|onboarding.html|
|商家入驻|主体与门店|`#/admission/admission-start/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.html/onboarding.js|
|商家入驻|办理人与经营场景|`#/admission/admission-business/edit` → 演示保存返回 `admission-business`；仅适用分支可见|onboarding.html/onboarding.js|
|商家入驻|结算与资料复用|`#/admission/admission-settlement/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.html/onboarding.js|
|平台管理|商家入驻审核|`#/platform/platform-admission/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|onboarding.html|
|消费者小程序界面预览|首页与我的服务|`#/consumer/consumer-home/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/home/index.wxml|
|消费者小程序界面预览|门店与服务|`#/consumer/consumer-stores/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|我的订单|`#/consumer/consumer-orders/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|个人资料|`#/consumer/consumer-profile/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/profile/index.wxml|
|消费者小程序界面预览|社区与归属|`#/consumer/consumer-communities/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|推荐关系|`#/consumer/consumer-referrals/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|我的通知|`#/consumer/consumer-notices/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|商品篮子|`#/consumer/consumer-basket/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|退款申请|`#/consumer/consumer-refunds/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|消费者小程序界面预览|支付与订单恢复|`#/consumer/consumer-payment/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
