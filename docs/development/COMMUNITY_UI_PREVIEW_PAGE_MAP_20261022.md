# 社区逐页UI预览清单

仅示例状态；无真实登录、API调用、业务写入或资金动作。消费者为原小程序界面投影，不是新增H5业务端。

|角色|页面|点击路径|原字段来源|
|---|---|---|---|
|商家小程序|订单|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|订单详情、退款与分账|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|消费者退款申请审核|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|退款预审|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|分账方案计算|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|门店资料|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|多门店管理|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|门店员工与权限 · 生成原客户中心邀请|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|门店员工与权限 · 保存门店员工权限|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|商品管理|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|商品定价与库存|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|广告管理与审核|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|广告事件报表|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|模拟对账|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|微信退款与分账处理|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|退款申请|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|分账回退|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|分账规则|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|分账申请|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|真实资金记录与对账|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|商家小程序|微信官方账单|原后台源码保留；不作为小程序手机菜单或本轮小程序覆盖证明|workbench.html|
|社区管理|个人资料与推荐关系|`#/community/community-0-0-0/list` → `detail` → `edit` → 演示保存返回列表|communities.html|
|社区管理|社区资料|`#/community/community-1-0-0/list` → `detail` → `edit` → 演示保存返回列表|communities.html|
|社区管理|打开社区|`#/community/community-2-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台审核|`#/platform/platform-3-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|社区管理|社区订单、收益与结算观察|`#/community/community-4-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台配置社区分账接收关系|`#/platform/platform-4-1-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台运营查询|`#/platform/platform-5-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|平台管理|平台商家管理|`#/platform/platform-6-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|社区管理|社区推广|`#/community/community-7-0-0/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|communities.html|
|商家小程序|订单与收款记录|`#/merchant/merchant-native-orders/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/merchant/index.wxml|
|商家小程序|收款统计|`#/merchant/merchant-native-summary/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/merchant/index.wxml|
|商家小程序|门店资料|`#/merchant/merchant-native-profile/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/merchant/index.wxml|
|商家小程序|商品与服务|`#/merchant/merchant-native-catalog/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/merchant/index.wxml|
|商家小程序|订单详情与退款状态|`#/merchant/merchant-native-detail/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/merchant/index.wxml|
|商家小程序|收款码与保存手机|`#/merchant/merchant-native-collection/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/merchant/index.wxml|
|商家入驻（同一小程序）|经营信息 1|`#/admission/admission-basic-0/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.html|
|商家入驻（同一小程序）|资料清单与版本|`#/admission/admission-materials/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.html|
|商家入驻（同一小程序）|管理员|`#/admission/admission-contact_info-/edit` → 演示保存返回 `admission-business`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|经营主体|`#/admission/admission-subject_info-business_license_info-/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|法人身份证|`#/admission/admission-subject_info-identity_info-id_card_info-/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|其他法人证件|`#/admission/admission-subject_info-identity_info-id_doc_info-/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|经营场景|`#/admission/admission-business_info-/edit` → 演示保存返回 `admission-business`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|结算规则|`#/admission/admission-settlement_info-/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|结算账户|`#/admission/admission-bank_account_info-/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|最终受益人资料|`#/admission/admission-beneficiary/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.js|
|商家入驻（同一小程序）|申请状态与补件|`#/admission/admission-result/edit` → 演示保存返回 `admission-result`；仅适用分支可见|onboarding.html|
|商家入驻（同一小程序）|主体与门店|`#/admission/admission-start/edit` → 演示保存返回 `admission-start`；仅适用分支可见|onboarding.html/onboarding.js|
|商家入驻（同一小程序）|办理人与经营场景|`#/admission/admission-business/edit` → 演示保存返回 `admission-business`；仅适用分支可见|onboarding.html/onboarding.js|
|商家入驻（同一小程序）|结算与资料复用|`#/admission/admission-settlement/edit` → 演示保存返回 `admission-settlement`；仅适用分支可见|onboarding.html/onboarding.js|
|平台管理|商家入驻审核|`#/platform/platform-admission/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|onboarding.html|
|用户小程序|首页与我的服务|`#/consumer/consumer-home/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/home/index.wxml|
|用户小程序|门店与服务|`#/consumer/consumer-stores/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|我的订单|`#/consumer/consumer-orders/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|个人资料|`#/consumer/consumer-profile/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/profile/index.wxml|
|用户小程序|社区与归属|`#/consumer/consumer-communities/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|推荐关系|`#/consumer/consumer-referrals/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|我的通知|`#/consumer/consumer-notices/list` → `detail` → `edit` → 只读操作说明后返回列表，不新增业务记录|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|商品篮子|`#/consumer/consumer-basket/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|退款申请|`#/consumer/consumer-refunds/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
|用户小程序|支付与订单恢复|`#/consumer/consumer-payment/list` → `detail` → `edit` → 演示保存返回列表|clients/community-mini/pages/checkout/index.wxml|
