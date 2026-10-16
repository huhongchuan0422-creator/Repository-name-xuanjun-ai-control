"""Source-only authorization contract; identity and membership must come from a trusted server."""
GUIDES = {\n "company_identity": ("企业主体及代表授权", "经授权的项目通道提交，不收集登录密码。"),\n "domain_control": ("域名与DNS控制权", "以服务端一次性TXT挑战核验。"),\n "wechat_merchant": ("微信支付商户及分账能力", "官方商户平台核验；API密钥走SecretRef。"),\n "wechat_miniapp": ("微信小程序及公众号", "AppID可登记，AppSecret走SecretRef。"),\n "douyin_oauth": ("抖音开放平台应用", "按授权Scope使用OAuth。"),\n "x_oauth": ("X开发者应用", "使用OAuth并核查费用与权限。")\n}
class IntakeRejected(ValueError): pass
STATES=("NOT_STARTED","PARTIAL","SUBMITTED","UNDER_REVIEW","NEEDS_CORRECTION","ACCEPTED")
TRANSITIONS={
 ("NOT_STARTED","save_draft"):"PARTIAL",("PARTIAL","save_draft"):"PARTIAL",
 ("PARTIAL","submit"):"SUBMITTED",("SUBMITTED","start_review"):"UNDER_REVIEW",
 ("UNDER_REVIEW","request_changes"):"NEEDS_CORRECTION",("UNDER_REVIEW","approve"):"ACCEPTED",
 ("NEEDS_CORRECTION","save_draft"):"PARTIAL"
}
CUSTOMER_ACTIONS=frozenset(("save_draft","submit"))
REVIEW_ACTIONS=frozenset(("start_review","request_changes","approve"))
def can_submit(actor,project,contract_customer,verified_customer,memberships):
    return bool(actor and project and contract_customer and verified_customer and contract_customer==verified_customer and memberships.get((actor,project)) in ("customer_owner","project_editor"))
def authorize_action(actor,project,contract_customer,verified_customer,memberships,action,submitter=None,authenticated=False):
    if type(authenticated) is not bool or not authenticated or not actor or not project:
        raise IntakeRejected("TRUSTED_IDENTITY_REQUIRED")
    if action in CUSTOMER_ACTIONS:
        if not can_submit(actor,project,contract_customer,verified_customer,memberships):raise IntakeRejected("CUSTOMER_PROJECT_ACCESS_DENIED")
    elif action in REVIEW_ACTIONS:
        if memberships.get((actor,project))!="independent_reviewer" or (submitter is not None and actor==submitter):raise IntakeRejected("INDEPENDENT_REVIEW_REQUIRED")
    else:raise IntakeRejected("INVALID_ACTION")
    return True
def transition(state,action,authorized):
    if type(authorized) is not bool or not authorized:raise IntakeRejected("ACTION_AUTHORIZATION_REQUIRED")
    if (state,action) not in TRANSITIONS:raise IntakeRejected("INVALID_TRANSITION")
    return TRANSITIONS[(state,action)]
def apply_action(state,action,actor,project,contract_customer,verified_customer,memberships,submitter=None,authenticated=False):
    authorize_action(actor,project,contract_customer,verified_customer,memberships,action,submitter,authenticated)
    return transition(state,action,True)
