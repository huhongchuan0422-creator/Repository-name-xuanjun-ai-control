"""Offline project intake authorization: no production login or storage."""
GUIDES = {
  "company_identity": ("企业身份与授权", "登录企业认证系统，准备营业执照和签约代表授权证明，在项目私有材料通道提交。"),
  "domain_control": ("域名验证", "登录域名DNS服务商，添加平台生成的限时TXT校验记录，核验后移除。"),
  "wechat_merchant": ("微信支付商户与分账资格", "登录微信支付商户平台申请商户号/分账授权；支付密钥只用受控SecretRef，不可发客服。"),
  "wechat_miniapp": ("微信小程序应用", "在微信公众平台创建/认证小程序，登记AppID和回调域名；AppSecret仅经受控SecretRef。"),
  "douyin_oauth": ("抖音开放平台", "在抖音开放平台申请应用和真实所需权限，使用官方OAuth授权；不提交token明文。"),
  "x_oauth": ("X开发者授权", "通过X开发者后台确认接口权限、费用和回调域名，使用OAuth或受控SecretRef。"),
}
class IntakeRejected(ValueError): pass

def can_submit(actor, project, contract_customer, verified_customer, memberships):
    return bool(actor and project and contract_customer and verified_customer and contract_customer == verified_customer and (actor,project) in memberships and memberships[(actor,project)] in ("customer_owner","project_editor"))

def transition(state, action, verified):
    if not verified: raise IntakeRejected("PROJECT_IDENTITY_REQUIRED")
    states={("NOT_STARTED","save_draft"):"PARTIAL",("PARTIAL","save_draft"):"PARTIAL",("PARTIAL","submit"):"SUBMITTED",("SUBMITTED","request_changes"):"NEEDS_CORRECTION",("NEEDS_CORRECTION","save_draft"):"PARTIAL",("SUBMITTED","approve"):"ACCEPTED"}
    if (state,action) not in states:raise IntakeRejected("INVALID_TRANSITION")
    return states[(state,action)]
