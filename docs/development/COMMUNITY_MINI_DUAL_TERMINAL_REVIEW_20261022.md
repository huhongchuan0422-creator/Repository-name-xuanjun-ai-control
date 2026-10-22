# 社区窗口4：同一小程序与双端预览

依据：Issue76 #6333869015；本轮沿原分支、继承525d9ff及当前源码。准确源码候选以本轮GitHub提交、Hosted head_sha、制品MANIFEST为准，不能用线上2330dd55冒充本候选。

## 打开与检查

1. 从本轮 `community-isolated-ui-review` 制品解压 `community-ui-preview.html`，用Chrome/Edge打开。它是可点击、无网络的浏览器投影；保存只影响本地示例。不能把它叫微信真机、小程序开发者工具或角色业务验收。
2. 用户小程序 → 门店与服务 → 商家入驻 → 四阶段。切换企业/个体、办理人/证件/经营场景/实际受益人数，进入适用资料编辑，输入示例值，再上一步、下一步、保存、刷新验证草稿。用户/商家强制手机投影，同一个AppID和app.json。
3. 商家小程序 → 入驻进度与补件，或订单与收款记录 → 详情 → 返回；门店资料 → 编辑示例 → 保存。收款统计与正式收款码页不会显示真实到账或合成码。原PC商家21模块源码保留为功能对照，不再机械当小程序菜单。
4. 社区管理、平台管理各选手机与PC；菜单 → 列表 → 详情 → 操作/编辑 → 返回。原未授权的写操作、真实平台审批、微信与资金操作在隔离投影不执行。平台审核不等于微信认证。
5. 源码包内 `clients/community-mini` 为同一原生小程序项目；准备同版本后端后，沿原 `prepare-mini.cjs`、原配置及原上传门禁打开开发者工具。本轮不部署、不上传官方预览、不换凭据，也未把当前线上旧版作为新源码后端。

## 正式源码接线

|终端/页面|原接口或服务|边界|
|---|---|---|
|同一小程序商家展示页→商家入驻|checkout原入口→pages/merchant-join|不创建第二App，不赋商家角色|
|四阶段/原申请/进度/补件|/mini/merchant→MerchantOnboarding/WechatApplyment|mini原会话→原Center；原owner、材料扫描、版本及状态校验|
|正式单套资料|shared_application_fields|legal_name=本次草稿merchant_name；contact=本次草稿mobile_phone；银行卡/受益人不另建台账|
|已提交/已审核申请|原平台历史快照+当前原微信草稿投影|不重写历史；继续微信草稿不重新提交平台|
|商家工作台/订单/统计|原CenterOperations、community.orders/order_detail/summary|实时用户/项目/角色/门店及onboarding门禁；原口径不变|
|门店与商品查看、门店资料编辑|merchant_settings / community.profile|仅已有商家管理员可改资料；普通用户不能继承角色|
|认证/签约指引|已验签原wechat_query的sign_url及证明|固定微信官方来源；未取得则显示等待，不造URL|
|收款码及相册保存|原payment activation_guard→CollectionCodes→正式版官方小程序码→wx.saveImageToPhotosAlbum|只允许已开通原门店/商家管理员；release、check_path=true；IO前后复核；无模拟回退|
|社区/平台手机与PC|原communities/onboarding/web-session源码与逐页投影|保留双端，正式权限不变|

收款码打开原收银页的服务端scene映射；不把开发预览码、任意URL二维码、商户号生成或图片保存当支付成功。未配置原payment产品/未完成可信微信进件/未发布对应正式页面时，码取得保持拒绝或UNKNOWN。已打印码的扫码交易仍走原实时商户、订单和支付门禁。

官方微信状态查询定义： https://pay.wechatpay.cn/doc/v3/partner/4012697168
官方小程序API引用： https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/mp-access-token/getStableAccessToken.html 和 https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/qrcode-link/qr-code/getUnlimitedQRCode.html 。本轮小程序文档网页读取失败，接口代码经隔离传输边界测试，不声称已做官方实机调用或取得正式码。

## 验证口径与失败保留

- 原Center原生控制器→真实HTTP→原SQLite同一申请、单套字段、返回恢复、商家查询已加入定向集成。微信登录交换为隔离fixture；业务服务、会话/权限及存储不由mock替代。没有真实证件、银行卡、进件或支付调用。
- 代码传输测试用明确不可扫码的合成字节，不交付为收款图片；覆盖未开通拒绝、IO期间撤权、正式版参数及错误不回退。
- Owner“条件不能点击/输入”在本地Chromium旧交付及525d9ff文件未复现；不写已定位根因或客户验收通过。增加单文件条件切换、下一步/返回/刷新和双终端检查，保留Owner反馈待真机/原打开环境复验。
- 第一轮UI检查因原生文件变更后未重新生成摘要失败，保留失败日志；统一冻结源码再生成检查，不移除生成一致性门禁。
- 首次全mini检查有两条历史WXML断言失败；精确原checkout blob a9d2d083066d110c1f2cf1514748a703576f4ba2同样复现。旧断言要求把内部交付资料/反馈塞入消费者收银页，与已在当前源码生效的customer-pages隔离要求直接冲突。本轮只改这两条旧UI断言遵循现行消费者边界，保留全部私有材料、反馈传输/分页/权限/恢复测试，不把内部SaaS资料变成社区登录前置。
- 开发者工具、手机体验、真实微信认证/签约、正式码扫码及真实支付分别保持未验收。CI通过不等于客户验收。

## 真实剩余与一次性现场输入

- 本轮源码、离线投影与自动测试可交；现场仍运行旧源码，新mini端点尚未部署。无新线上预览URL。
- 需在另行批准的同一候选发布中同步后端与mini，复用原AppID、私有配置和受保护账号；不要求Owner粘贴凭据。
- 原环境目前无已核真实商户/完整角色验收；需真实申请主体获准资料、原平台审核/门店开通、微信官方认证签约和JSAPI/适用分账产品证据。没有这些，不尝试真实进件支付或伪造完成。
- 开发者工具与真机需Owner在原工具环境配合体验。原打开条件控件问题须在该环境复验；浏览器投影不能替代。
- 手机端已补日常查看及门店编辑；原商品维护、价格库存、退款、分账、广告、账单等源码保留。尚未把这些全部维护操作接入新手机页面，不能称全量商家小程序功能已闭合。
- 因本轮无部署授权，连到同版本后端的完整客户预览尚未交付；离线可点击投影仅用于本轮UI和导航复验。
