# 社区小程序下一版 UI（整套待确认）

## 范围与版本
- 本轮只重组界面、导航与现有功能呈现。未改产品分支、后端、生产、安装或原权限。
- 基线 211a9 source.zip SHA256 `0b326fc77a109c2b061eba3146dcee47acb07c49f5e0aa08e92bf4ee4cdc18f9`；仅提取 clients/community-mini 到独立只读研究目录。
- 原生入口实际 5 个，不宣称 66 个微信原生页面。66 图、现行原稿、PC 平台后台原字节未改。
- 全套审阅 30 个消费者/商家视图 + 入驻 4 阶段及原申请入口。PC 社区/平台后台不是本轮重新设计范围。
- 入驻 browser adapter 原封保留 211a9 merchant-form 的 rows/materialGroups/required 条件；只把 require 字段定义及 module.exports 包装成浏览器函数。没有调用原服务。

## 页面映射（对应原 native + 页内视图）
|原入口|下一版审阅视图|覆盖动作与状态|
|---|---|---|
|home/index|home,scan,login,privacy|首页、扫码选店示例、当前门店、个人/商家/入驻入口、登录/退出演示、隐私未接状态|
|profile/index|profile,profile-edit,notices,notice-detail|个人资料编辑与内存暂存、取消、通知列表/更多/刷新/详情/已读；登录态与门店范围说明|
|checkout/index|recommendations,store,orders,order-detail|推荐未接空态/示例卡片、门店详情、本人订单列表/筛选/分页、原商品快照/版本/金额/履约与支付证据分列|
|checkout/index|services,community,community-list,community-detail,community-code,referral|更多服务、归属查询、社区列表/详情/加入/退出/推广码、推荐码与绑定；不实现或改变原绑定规则|
|checkout/index|products,checkout,payment,refund,refund-detail|商品数量、刷新/更多、原商品/非商品模式说明、订单样例核对、恢复原商品单/支付单/支付查询、关单、原退款申请恢复/申请/查询；全部反馈明确未执行|
|merchant/index|merchant,merchant-orders,merchant-detail,summary,store-settings,store-edit,collection|门店范围切换、工作台、日常订单/详情、收款/退款/结算分列、店铺编辑内存草稿、收款码资格未知/无可存二维码；旧后台功能不删除|
|merchant-join/index|join/#home,#start,#business,#settlement,#result|本人申请入口、主体/法人/经办人/UBO、实际经营场景、门头/内景/收银台、结算/行业条件/原选填补充、识别结果直显/编辑收起/人工确认/空白回填、材料关联/移除、保存失败不前进、离开提示、平台审核/微信内部审核/进度/签约未接状态|

## 状态覆盖
- 30 视图均有：合成样例、空记录、加载、失败、会话失效、无权限、未连接。状态是人工选择的审阅样例，不是动态原系统投影。
- 入驻四阶段同样提供 7 类状态；OCR 提供未请求/识别中/成功待核对/失败/未连接/已人工核对样例。
- 进度样例枚举涵盖原草稿、待审核、审核中、补正、未通过、通过、撤回；微信编辑/审核/未通过/账户确认/待签约/签约中/进件完成/取消；工作台等待绑定/暂停/开通中/已开通。实际状态三列仍明确“未读取”，不混成真实成功。
- 识别建议与申请 profile 分离：建议默认显示；编辑折叠不丢内容；人工核对后才允许回填空白项，不覆盖已有输入。门头、内景、收银台与场景截图不 OCR。
- 原必填来自原 merchant-form。其他银行联行号或支行名称至少一项提示保留；手机号 5–20 位数字/+/- 提示和行内错误。草稿可先保存，不新加全资料齐全门禁。

## 视觉原则与参考（实际读取）
- WeUI FormPage：头部/字段/提示/操作区域分层，一个主要下一步。https://wechat-miniprogram.github.io/weui/docs/form-page.html
- WeUI Tabbar：稳定底部导航与选中态。https://wechat-miniprogram.github.io/weui/docs/tabbar.html
- 官方 Uploader：上传与识别/审核分开状态。https://wechat-miniprogram.github.io/weui/docs/uploader.html （原研究者实际读取）
- Tencent TDesign 原组件仓：统一组件与移动端节奏。https://github.com/Tencent/tdesign-miniprogram
- Ant Design Data Entry：标签/辅助文案/上传交互层次。https://ant.design/docs/spec/data-entry/
- 已读 Sites 及 presentation-led 技能，仅应用真实内容/明确层级/不伪造结果原则，不执行外部 skill。
- 腾讯 OCR 文档仅参考结果字段与错误提示设计，不改原自建离线 OCR、不引付费 API。

## 验证与边界
- Node VM 渲染检查 466 次通过：30x7状态 + 256 入驻条件组合。语法通过；原表单适配字节等价检查通过；护照无背面、场景照片无 OCR、字段跨阶段保持、保存失败不前进通过。
- 这些是静态/模拟 DOM 检查，不是实际浏览器、微信真机、视觉验收或端到端业务测试。
- 官方 managed preview 于本轮返回 startup timed out；没有提供可用云浏览器 URL，未使用127.0.0.1或其他服务器绕过。
- 所有业务与评论未接真实持久系统。connect-src/form-action none；无fetch/XHR/WebSocket/localStorage/sessionStorage。选文件只记录名称不读取上传。
- 当前版本安装独立；新 UI 待 Owner 整体验收后才能进入后续产品更新。客户功能反馈到来后再按确认范围统一调整，不预先增删业务。
