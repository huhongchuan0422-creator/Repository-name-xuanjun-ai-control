# 玄钧云汇客户专属敏感凭据提交与上线后更新规则 V1

状态：DESIGN_REGISTERED / IMPLEMENTATION_PENDING / PRODUCTION_HOLD。原项目PR122、统一Customer/Project/RBAC及既有SecretRef为唯一对接对象；不新建第二套秘密存储，也不更改已运行服务。

## 页面与身份授权
客户中心每个项目提供「项目资料」和单独的「凭据与授权」二级页面。用户登录后，服务端验证原合同Customer ID、Tenant、Project及该项目成员权限，才可访问。普通文档与秘钥分流，绝不经飞书、Telegram、网页AI聊天或普通附件上传秘密。企业项目可分别授予credential_submitter、credential_rotator、credential_approver和只读审计角色；高风险密钥须再次认证或双人批准。角色撤销即时取消访问及未完成轮换。

## 类型与操作
- API Key/AppSecret：仅新增、替换、有效性验证、激活、撤销；秘密写入国内受控Secret Portal，前端只接一次性授权凭据及SecretRef，不回显明文。
- OAuth：重新授权、断开和查看Scope/到期；优先官方OAuth而非人工传Token。
- 支付类私钥、提现/资金操作凭据：默认HOLD，最小权限、独立核实主体、支付机构规则、双人批准和隔离验证，不能用户自行一键换成未验密钥。
- 系统根密钥、加密主密钥、平台管理员凭据：不属于客户自行更改范围。
后台仅显示凭据别名、关联项目、作用域、最小可识别标识、授权状态、版本、到期及最后检查时间，禁止日志/通知/导出/回显完整敏感值。

## 安全轮换状态机
NOT_CONFIGURED→PENDING_SUBMISSION→STAGED→VALIDATING→AWAITING_APPROVAL（高风险）→READY→ACTIVE；更换时旧版保持ACTIVE，直到新凭据完成真实能力验证、必要审批及原子切换后，旧版进入RETIRED/REVOKED；任何失败、超时或结果不明进入HOLD/UNKNOWN_RECONCILE，禁止盲重放或静默停用旧凭据。每次版本都绑定actor、Project、SecretRef、操作幂等ID、审核记录及切换回执。确保凭据滚动更新、服务不中断（外部提供商不支持重叠期时需明确计划停机窗口）。

## 页面信息与客户教程
展示对应官方申请入口、认证要求、所需Scope、最小权限、费用与有效期（未知明确待核）、回调域名设置、获取步骤、验证标准、更新前影响、回滚/人工支持。客户可逐项分批提交；已审核项目资料不能因新凭据更新被覆盖。

## 验收要求
真实未登录、非原客户、错误项目、权限已撤销、错误角色、CSRF、旧版本重放、幂等同键异载荷、并发双轮换、验证失败、provider超时/UNKNOWN、旧版仍在用、退款/结算高风险、审计/SecretRef泄漏、备份恢复和服务重启均有负向测试。正式生产配置及密钥决不进入公开GitHub。账号/文件存储/Secret Portal/渠道真实接线由Work及生产Owner受控集成；本设计不是生产已完成证明。
