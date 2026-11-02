# 同一套微信进件资料：去重与最简展示差异

依据：Issue76 #6333255236 05:18顶部澄清。本轮包含隔离UI投影及Owner追加授权的非必需附件规则修正；正式身份、角色及支付资格门禁不变。

## 资料只采集一次

本项目商户统一通过我们的服务商流程申请特约商户，不提供绑定既有微信商户号入口。已受理申请沿同一原单补件，不重复提交。商户号生成不代表JSAPI或分账产品开通/验收，继续原资格门禁。

本次微信进件草稿为唯一资料源。平台展示主体名称、联系人、门店及原项目归属时复用同一字段/私有材料引用，不新增银行卡或受益人台账。不得假设微信提供全部资料回读。仅本次服务商原申请已持有的获准草稿/材料可复用；微信状态仍须服务端核对同一原申请、主体、owner、服务商、门店/scene及签名证据；截图或前端选择不证明通过。

|原展示/字段|本轮投影差异|正式源码现状|
|---|---|---|
|平台legal_name与微信merchant_name|只在微信经营主体编辑一次，平台消费同一值|正式shared_application_fields从同一原申请微信草稿投影并在可编辑草稿同步；已提交/已审批历史快照不改写|
|平台contact与微信管理员电话|只在管理员信息编辑一次，平台复用|正式映射微信contact_info.mobile_phone；同一申请来源，不新建联系人或银行卡台账|
|门店名称/地址与线下经营场景|同一申请草稿共享键；场景页不再重复输入|原门店/项目/归属权限保留|
|银行卡|仅微信结算账户一处，不新增平台表|原加密存储与权限不变|
|受益人|企业且并非法人单一受益人时，按实际人数切换同一编辑组件|不固定展开四组，个体不展示|

## 四个主阶段

主体与门店 → 办理人与经营场景 → 结算与资料复用 → 核对与状态。阶段内只有适用资料的独立编辑页；不是把旧长表机械拆成15个必经步骤。身份证/其他证件互斥；经办人资料仅经办人分支出现；线下材料仅线下场景出现。草稿分步保存，切换条件保留已有值，但不把不适用值视为新要求。

投影保留原业务字段、原证件枚举；必填标*，选填明确，条件必填只在适用条件显示。草稿可不完整，演示保存不等于真实提交。银行卡支行全称/联行号依银行要求二选一，不能一律强制两项。

## 2026-11-01 Owner 增量：单列分步与 OCR 优先

商家填写端不再以桌面端左右两列长表作为最终交付形态。网页投影、小程序和后续正式端统一复用同一原申请与微信私有草稿，按“主体与法人资料 → 实际经营场景 → 结算资料 → 核对与进度”四阶段单列展示；每阶段可保存草稿、返回和继续，不建立第二份申请或第二套资料系统。

证照中可以可靠识别的内容必须采用“先上传 → OCR 建议 → 用户核对/纠错 → 只回填空白项”的流程，不要求商家再次抄写。当前获准映射仍只包括营业执照与大陆身份证正面：主体名称、统一社会信用代码、法定代表人、证件姓名/号码及证件地址等；不得擅自扩大到未经验证的证件或字段。OCR 不得覆盖已有内容，不得绕过申请/材料/版本绑定，也不得把识别成功表述为资料真实、平台审核通过或微信审核通过。

证照不存在或 OCR 不适用的内容才由用户选择或补充，包括联系人电话、实际经营场景、行业、爱心积分比例和自愿分账/申请比例。门头、店内环境、收银台照片不做无意义文字识别。生产 OCR 只有在固定依赖、权限、加密存储、真实宿主组成和真实证照验收全部通过后才能启用；当前源码准备和合成测试不得表述为已上线。

## 2026-11-01 Owner 增量：微信审核、商家确认与完成待办

平台必须通过原 `wechat_query` 接口对微信签名响应做确定性同步；当前人工查询不等于自动同步，后续零模型定时任务只能按既有申请、服务商和验签门禁查询，不得重复提交进件。平台待办按官方状态归并展示：`APPLYMENT_STATE_AUDITING` 为“待微信审核”；`APPLYMENT_STATE_TO_BE_CONFIRMED` 与 `APPLYMENT_STATE_TO_BE_SIGNED` 为“待商家确认/签约”；`APPLYMENT_STATE_SIGNING` 为“开通中”；`APPLYMENT_STATE_REJECTED` 为“补件/驳回”；`APPLYMENT_STATE_EDITTING`、`APPLYMENT_STATE_CANCELED` 和未知/冲突状态分别保留异常处理，不得静默消失。

微信查询返回的 `sign_url` 是超级管理员账户验证/签约官方链接，不是数字认证码。只有验签、申请号、服务商和当前申请绑定都通过后，后台才能在待商家操作阶段显示由本系统本地生成的二维码及“复制官方链接”；禁止使用第三方二维码服务外传链接，禁止生成示例码冒充官方认证入口。`APPLYMENT_STATE_FINISHED` 才从待办移入“已完成/历史”，且仍不自动等于分账产品授权、收款资格或客户业务验收完成。

## 已发现的平台额外材料与处理建议

原 `community_merchant_onboarding.py` 的 BASE 一律包含 `storefront_photo`、`interior_photo`、`settlement_proof`；`_required` 经办人分支追加 `operator_authorization`。这不是当前微信所有场景的通用必填合同。原平台审核和微信资料内部审核也有独立审批门禁。

|额外要求|核对结果与最小建议|本轮处理|
|---|---|---|
|所有场景门头/店内照片|仅线下经营场景按微信要求提供；纯小程序不加这层门槛|正式_required按当前同一申请场景决定；纯小程序不要求，线下/混合仍要求|
|settlement_proof|当前特约商户提交API未见通用独立结算证明附件必填，原平台为何需要该附件无已持有依据|正式清单改为选填；缺失或需补件不阻止提交/平台审批，上传与私有下载入口保留|
|经办人授权函|当前官方字段标记即将下线、无需传入，与原平台一律必需不一致|按Owner本轮追加指令改为选填；经办人证件仍按原微信要求处理|
|重复平台资质审批|平台保留门店/项目/归属核对，微信资料及可信结果复用|正式独立审核状态不伪装成已取消|

资料草稿、平台处理、微信提交、微信审核结果分开显示。本地示例不生成微信通过或资金到账状态。Owner已追加批准上述非微信必需附件规则修正。新UI明确保存经营场景；同一原微信进件草稿中已声明的场景优先，旧未声明记录保守沿用线下清单，不迁移或删除历史。纯小程序/线下/混合、选填附件需补件不挡审批、场景切换保留历史及无效场景零建号均纳入定向测试。仍未部署，也未取消原身份与独立审核权限。

## 官方依据与版本限制

微信支付合作伙伴文档“提交申请单_特约商户进件”，路径 `/v3/applyment4sub/applyment/`：
https://pay.wechatpay.cn/doc/v3/partner/4012719997

2026-10-22读取的页面标示更新时间2025-03-26。对应原 `community_wechat_applyment.py`、`community_applyment_conditions.py`。当前行业/银行目录及微信实际审核仍具权威性，预览不查询真实银行或行业接口、不扩大主体类型、不替换验证器。

附件选择仅记录隔离文件名、大小和版本示例，不上传或读取正文；PDF/PNG/JPEG、5MB边界保留。正式附件私有下载和历史能力没有改动，本地投影不能冒充真实材料已提交。

## Issue76 cashier optional material and exact route evidence closeout

The optional `cashier_photo` uses the existing encrypted/scanned original application
upload and revision contract; it is never in BASE or required materials. Replacement
and `remove_material(application,revision,kind,expected_wechat_version)` clear only the
trusted cashier slot association in the same transaction and preserve all objects,
versions and review history. Removal is limited to cashier, owner and editable state.

`wechat_cashier_link(application,expected_version,media_id)` accepts only an existing
admitted media record for the current application's current cashier SHA. It modifies
only its server-managed `cashier_media_id` entry in
`addition_info.business_addition_pics`, preserving other entries and the shared limit
of five. Unknown bindings, stale versions, full arrays and read-only review states
reject without overwriting. This does not open real WeChat media/submission gates.

Native upload/replace/delete/read use the real original contract. HTML remains an
isolated local selection/name/size demonstration, and must never label local selection
as server upload. All three scene photographs bypass OCR; document OCR remains pending.

The original static allowlist now includes the existing route-gallery. The scoped
browser test clicks/renders the 34 main and 32 sub design routes at 390 and 1440,
records exact URL/mode/conditions, source Commit/Tree, screenshot hashes and navigation
in `ui-evidence/route-render-manifest.json`. It also inventories prior test images
without inventing missing provenance. These are projection renders, not acceptance of
66 live functions. Old screenshots remain tied to their original SHA.
